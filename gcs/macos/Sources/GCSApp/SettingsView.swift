// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import SwiftUI

/// The drone's Wi-Fi: status, scan, saved networks, add/update. Every change
/// re-reads the drone's id first and is refused if another drone answers;
/// the decisions are in SettingsLogic.swift.
struct SettingsView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var handoff: WifiHandoff

    @State private var status: DroneAPI.WifiStatus?
    @State private var statusAt: Date?
    @State private var statusError: String?
    @State private var info: DroneAPI.DroneInfo?

    @State private var scanResults: [DroneAPI.ScanNet] = []
    @State private var scanning = false
    @State private var scanned = false

    @State private var saved: [String]?
    @State private var savedError: String?

    @State private var addSSID = ""
    @State private var addPass = ""
    @State private var msg: (text: String, kind: StatusBanner.Kind)?
    @State private var busy = false
    @State private var confirmMode: String?
    @State private var confirmRemove: String?
    @State private var now = Date()

    private var droneLabel: String { info?.name ?? app.droneName }
    private var droneID: String? { app.droneID ?? status?.id }
    private var identity: DroneIdentity { DroneIdentity.check(expected: app.droneID, reported: status?.id) }

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.s3) {
                if case .different(let other) = identity {
                    StatusBanner(text: DroneIdentity.differentText(now: other, expected: app.droneID ?? "?"),
                                 kind: .error)
                }
                statusPanel
                scanPanel
                savedPanel
                addPanel
                if let m = msg { StatusBanner(text: m.text, kind: m.kind) }
            }
            .padding(Theme.s4)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
        .background(Theme.appGradient)
        .task { await refreshStatusLoop() }
        .task { info = await app.api.info(); await loadSaved() }
        .confirmationDialog(confirmModeTitle, isPresented: Binding(
            get: { confirmMode != nil }, set: { if !$0 { confirmMode = nil } })) {
            Button("Switch to \(confirmMode ?? "")", role: .destructive) {
                if let m = confirmMode { switchMode(m) }
                confirmMode = nil
            }
            Button("Cancel", role: .cancel) { confirmMode = nil }
        } message: {
            Text(confirmMode == "hotspot"
                 ? "\(droneLabel) will show its own hotspot Bumblebee-\(droneID ?? "XXXX"); this Mac loses it until it joins that hotspot."
                 : "\(droneLabel) drops its hotspot and joins a saved network (~60 s).")
        }
        .confirmationDialog(confirmRemoveTitle, isPresented: Binding(
            get: { confirmRemove != nil }, set: { if !$0 { confirmRemove = nil } })) {
            Button("Remove and disconnect", role: .destructive) {
                if let n = confirmRemove { remove(n, confirmActive: true) }
                confirmRemove = nil
            }
            Button("Cancel", role: .cancel) { confirmRemove = nil }
        } message: {
            Text("\(droneLabel) is using \(confirmRemove ?? "") right now. Removing it disconnects the drone: "
                 + "it joins another saved network, or shows its own hotspot Bumblebee-\(droneID ?? "XXXX").")
        }
    }

    private var confirmModeTitle: String { "Switch \(droneLabel) to \(confirmMode ?? "")?" }
    private var confirmRemoveTitle: String { "Remove \(confirmRemove ?? "") from \(droneLabel)?" }

    // MARK: - Status

    private var statusPanel: some View {
        let stale = statusError != nil && status != nil
        return Panel(title: "WiFi Status", icon: "wifi", note: stale ? staleNote : nil, dimmed: stale) {
            Readout(label: "Drone", value: droneLabel + (droneID.map { " · id \($0)" } ?? " · id unknown"))
            if let s = status {
                Readout(label: "Mode", value: s.mode.uppercased(),
                        color: s.mode == "client" ? Theme.ok : Theme.warn)
                Readout(label: "Network", value: s.ssid.isEmpty ? "—" : s.ssid)
                Readout(label: "IP", value: s.ip.isEmpty ? "—" : s.ip)
                LabeledBar(label: "Signal", value: "\(s.signal)%", pct: Double(s.signal),
                           color: s.signal > 60 ? Theme.ok : (s.signal > 30 ? Theme.warn : Theme.danger))
                if let e = s.lastError,
                   let text = JoinReasonText.banner(ssid: e.ssid, reason: e.reason, time: e.time, now: now) {
                    StatusBanner(text: text, kind: .caution)
                }
                HStack {
                    Button { Task { await refreshStatus() } }
                        label: { Label("Refresh", systemImage: "arrow.clockwise") }
                        .buttonStyle(GhostButtonStyle())
                    Button("Switch Mode") { confirmMode = (s.mode == "client") ? "hotspot" : "client" }
                        .buttonStyle(AccentButtonStyle())
                        .disabled(busy || identity.blocks)
                    Spacer()
                }
            } else if let e = statusError {
                Text(e).font(Theme.monoSmall).foregroundStyle(Theme.caution)
                Button { Task { await refreshStatus() } }
                    label: { Label("Retry", systemImage: "arrow.clockwise") }
                    .buttonStyle(GhostButtonStyle())
            } else {
                Text("loading…").font(Theme.monoSmall).foregroundStyle(Theme.muted)
            }
        }
    }

    private var staleNote: String {
        let since = statusAt.map { Self.clock.string(from: $0) } ?? "—"
        return "no answer since \(since)"
    }

    // MARK: - Scan

    private var scanPanel: some View {
        Panel(title: "Available Networks", icon: "antenna.radiowaves.left.and.right") {
            HStack {
                Button { doScan() } label: {
                    if scanning { ProgressView().controlSize(.small) } else { Text("Scan") }
                }.buttonStyle(GhostButtonStyle()).disabled(scanning)
                Spacer()
            }
            if scanned && scanResults.isEmpty && !scanning {
                Text("no networks found").font(Theme.monoSmall).foregroundStyle(Theme.muted)
            }
            ForEach(scanResults) { n in scanRow(n) }
        }
    }

    @ViewBuilder private func scanRow(_ n: DroneAPI.ScanNet) -> some View {
        let otherDrone = WifiNames.isProtected(n.ssid)
        HStack(spacing: Theme.s2) {
            Circle().fill(n.inUse ? Theme.ok : Theme.muted).frame(width: 7, height: 7)
            Image(systemName: n.secured ? "lock.fill" : "lock.open")
                .font(.system(size: Theme.iconSm)).foregroundStyle(Theme.muted)
                .help(n.secured ? "Protected (\(n.security))" : "Open network")
            Text(n.ssid).font(Theme.monoSmall).foregroundStyle(otherDrone ? Theme.muted : Theme.text)
            Spacer()
            Text("\(n.signal)%").font(Theme.monoSmall)
                .foregroundStyle(n.signal > 60 ? Theme.ok : (n.signal > 30 ? Theme.warn : Theme.danger))
            Badge(text: n.band + "G", color: bandColor(n.band))
            if otherDrone {
                Text("a drone's hotspot").font(Theme.monoSmall).foregroundStyle(Theme.muted)
            } else {
                Button("Connect") { addSSID = n.ssid; addPass = "" }
            }
        }
    }

    // MARK: - Saved

    private var savedPanel: some View {
        Panel(title: "Saved Networks", icon: "bookmark.fill") {
            if let list = saved {
                if list.isEmpty { Text("none").font(Theme.monoSmall).foregroundStyle(Theme.muted) }
                ForEach(list, id: \.self) { name in
                    HStack(spacing: Theme.s2) {
                        Text(name).font(Theme.monoSmall)
                        if isInUse(name) { Badge(text: "IN USE", color: Theme.ok) }
                        Spacer()
                        Button("Remove", role: .destructive) { askRemove(name) }
                            .disabled(busy || identity.blocks)
                    }
                }
            } else if let e = savedError {
                Text("Couldn't load the saved networks: \(e)").font(Theme.monoSmall).foregroundStyle(Theme.caution)
                Button("Retry") { Task { await loadSaved() } }.buttonStyle(GhostButtonStyle())
            } else {
                Text("loading…").font(Theme.monoSmall).foregroundStyle(Theme.muted)
            }
        }
    }

    private func isInUse(_ name: String) -> Bool { status?.mode == "client" && status?.ssid == name }

    // MARK: - Add / update

    private var selectedScan: DroneAPI.ScanNet? { scanResults.first { $0.ssid == addSSID } }
    private var addIsSaved: Bool {
        let name = addSSID.trimmingCharacters(in: .whitespaces)
        return saved?.contains { $0 == name || WifiNames.same(ssid: name, profile: $0) } ?? false
    }
    private var formProblem: String? {
        let name = addSSID.trimmingCharacters(in: .whitespaces)
        if name.isEmpty { return nil }
        if WifiNames.isProtected(name) {
            return "That is a drone's own hotspot: it cannot be used as the drone's network."
        }
        let needs = PasswordCheck.needsPassword(saved: addIsSaved, secured: selectedScan?.secured)
        return PasswordCheck.check(addPass, needsPassword: needs).text
    }
    private var canSend: Bool {
        !addSSID.trimmingCharacters(in: .whitespaces).isEmpty && formProblem == nil && !busy && !identity.blocks
    }

    private var addPanel: some View {
        Panel(title: "Add / Update Network", icon: "plus.circle") {
            GlassTextField(placeholder: "SSID", text: $addSSID, icon: "wifi")
            if selectedScan?.secured != false {
                GlassTextField(placeholder: addIsSaved ? "Password (empty: keep the saved one)" : "Password",
                               text: $addPass, icon: "key", secure: true)
            }
            if let p = formProblem { Text(p).font(Theme.monoSmall).foregroundStyle(Theme.caution) }
            HStack {
                Button("Save + Apply Now") { applyNow() }
                    .buttonStyle(AccentButtonStyle()).disabled(!canSend)
                Button("Save for next boot") { applyBoot() }
                    .buttonStyle(GhostButtonStyle()).disabled(!canSend)
                if busy { ProgressView().controlSize(.small) }
                Spacer()
            }
            Text("A new password is tried first: if it is wrong, the drone keeps its old one and comes back.")
                .font(Theme.monoSmall).foregroundStyle(Theme.muted)
        }
    }

    // MARK: - Actions

    private func show(_ text: String, _ kind: StatusBanner.Kind) { msg = (text, kind) }

    private func applyStatus(_ s: DroneAPI.WifiStatus) {
        status = s
        statusAt = Date()
        statusError = nil
        if app.droneID == nil, let id = s.id { app.droneID = id }
    }

    private func refreshStatus() async {
        now = Date()
        do { applyStatus(try await app.api.wifiStatus()) }
        catch { statusError = DroneAPI.describe(error) }
    }

    private func refreshStatusLoop() async {
        while !Task.isCancelled {
            await refreshStatus()
            try? await Task.sleep(nanoseconds: 15_000_000_000)
        }
    }

    private func loadSaved() async {
        do { saved = try await app.api.savedNetworks(); savedError = nil }
        catch { savedError = DroneAPI.describe(error) }
    }

    /// The status read right before a change. nil (and a message) when the
    /// drone does not answer or another drone answers at this address.
    private func statusForChange() async -> DroneAPI.WifiStatus? {
        do {
            let s = try await app.api.wifiStatus()
            applyStatus(s)
            if case .different(let other) = DroneIdentity.check(expected: app.droneID, reported: s.id) {
                show(DroneIdentity.differentText(now: other, expected: app.droneID ?? "?"), .error)
                return nil
            }
            return s
        } catch {
            statusError = DroneAPI.describe(error)
            show(DroneAPI.describe(error), .error)
            return nil
        }
    }

    /// One change at a time; buttons stay disabled until it is over.
    private func run(_ op: @escaping () async -> Void) {
        guard !busy else { return }
        busy = true
        msg = nil
        Task { await op(); busy = false }
    }

    private func switchMode(_ mode: String) {
        run {
            guard await statusForChange() != nil else { return }
            do {
                try await app.api.wifiSetMode(mode)
                show(mode == "hotspot"
                     ? "\(droneLabel) is switching to its hotspot Bumblebee-\(droneID ?? "XXXX")."
                     : "\(droneLabel) is leaving its hotspot for a saved network (~60 s).", .success)
            } catch { show(DroneAPI.describe(error), .error) }
        }
    }

    private func askRemove(_ name: String) {
        if isInUse(name) { confirmRemove = name } else { remove(name, confirmActive: false) }
    }

    private func remove(_ name: String, confirmActive: Bool) {
        run {
            guard await statusForChange() != nil else { return }
            do {
                try await app.api.removeNetwork(name, confirmActive: confirmActive)
                if confirmActive {
                    show("Removing \(name): \(droneLabel) disconnects now.", .success)
                } else {
                    show("Removed \(name).", .success)
                    await loadSaved()
                }
            } catch where DroneAPI.code(error) == "active_network" {
                confirmRemove = name           // the drone says it is in use: ask first
            } catch { show(DroneAPI.describe(error), .error) }
        }
    }

    private func applyBoot() {
        let ssid = addSSID.trimmingCharacters(in: .whitespaces), pass = addPass
        run {
            guard await statusForChange() != nil else { return }
            do {
                try await app.api.saveNetwork(ssid: ssid, password: pass)
                try await app.api.applyBoot(ssid: ssid)
                show("Saved \(ssid) on \(droneLabel): it is used at the next start-up, "
                     + "or when the current network goes away. This password could not be tested now.", .success)
                await loadSaved()
            } catch { show(DroneAPI.describe(error), .error) }
        }
    }

    private func applyNow() {
        let ssid = addSSID.trimmingCharacters(in: .whitespaces), pass = addPass
        run {
            guard let s = await statusForChange() else { return }
            let id = app.droneID ?? s.id
            let drone = droneLabel
            do {
                try await app.api.saveNetwork(ssid: ssid, password: pass)
                try await app.api.applyNow(ssid: ssid)
            } catch where DroneAPI.isLinkDrop(error) {
                // Drone software before 1.0.1 switches before replying: it is on its way.
            } catch {
                show(DroneAPI.describe(error), .error)
                return
            }
            handoff.refreshCurrentSSID()
            let next = ApplyFollowUp.decide(target: ssid, computerSSID: handoff.currentSSID, droneID: id)
            show(next.text(drone: drone, target: ssid), .info)
            guard next == .waitHere, let id else { return }
            if let host = await WifiHandoff.waitForDrone(expectedID: id, timeout: 90) {
                if host != app.droneHost { app.connect(to: host) } else { app.reconnect() }
                app.droneID = id
                show("\(drone) is on \(ssid) (\(host)).", .success)
            } else {
                show(ApplyFollowUp.notFoundText(drone: drone, id: id, target: ssid), .caution)
            }
        }
    }

    private func doScan() {
        scanning = true
        Task {
            defer { scanning = false; scanned = true }
            do { scanResults = try await app.api.wifiScan() }
            catch { show("Scan failed: \(DroneAPI.describe(error))", .error) }
        }
    }

    private func bandColor(_ b: String) -> Color {
        b == "5" ? Theme.ok : (b == "6" ? Theme.accent2 : Theme.warn)
    }

    private static let clock: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()
}
