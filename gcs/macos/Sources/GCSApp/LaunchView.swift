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
import AppKit

/// One opening of the setup sheet; `drone` is the hotspot SSID tapped, if any.
struct SetupRequest: Identifiable {
    let id = UUID()
    let drone: String?
}

/// Connect screen — one unified panel. Drones on the network appear by name
/// via Bonjour, and drone hotspots nearby every ~12 s; switched-off drones grey
/// out and leave. The last drone is found again by its id. A footer takes an
/// address by hand and checks that a drone answers there before connecting.
/// Copy is English and type is SF (system); the orange/blue palette lives in
/// `ConnectTheme` and is scoped to this screen + the splash. Decisions in
/// DiscoveryLogic.swift.
struct LaunchView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var scanner: DroneScanner
    @EnvironmentObject var handoff: WifiHandoff
    @State private var manualIP = ""
    @State private var manualProblem: String?
    @State private var manualUnanswered: String?
    @State private var checkingManual = false
    @State private var lastPingOK = false
    /// The open "Add a drone" sheet and the drone it was opened for. One value
    /// for both, passed by `.sheet(item:)`: with a separate flag the sheet was
    /// built from a stale copy and never saw the drone that was tapped.
    @State private var setup: SetupRequest?

    private let rowHeight: CGFloat = 69

    var body: some View {
        GeometryReader { geo in
            ZStack {
                ConnectTheme.background.ignoresSafeArea()

                VStack(spacing: 18) {
                    header
                    if handoff.onDroneHotspot { OnDroneHotspotBanner(ssid: handoff.currentSSID) }

                    if let last = app.lastDrone {
                        let ip = KnownFleet.currentIP(of: last, found: scanner.foundIDs)
                        LastDroneCard(drone: last, ip: ip, reachable: lastReachable(last, ip),
                                      connect: { app.connect(to: ip, expectedID: last.verified ? last.droneID : nil) },
                                      forget: { app.forget(last) })
                            .task(id: ip) { await watchLast(ip) }
                    }

                    dronesPanel(listMaxHeight: max(rowHeight * 2, geo.size.height - 490))
                    footer
                    CopyDiagnosticsButton(compact: true)
                }
                .frame(maxWidth: 560)
                .padding(.horizontal, 24)
                .padding(.vertical, 20)
            }
        }
        .foregroundStyle(ConnectTheme.text)
        .sheet(item: $setup) { request in
            ProvisioningView(preselected: request.drone)
        }
        .task { await watchHotspots() }
    }

    /// The last drone is "live" if discovery lists it, or a ping to :9090 at
    /// its address answered within the last 10 s. Otherwise the dot is grey.
    private func lastReachable(_ last: KnownDrone, _ ip: String) -> Bool {
        if last.verified, scanner.visibleIDs.contains(last.droneID) { return true }
        return lastPingOK
    }

    private func watchLast(_ ip: String) async {
        while !Task.isCancelled {
            lastPingOK = await scanner.isReachable(ip)
            try? await Task.sleep(nanoseconds: UInt64(Liveness.period * 1_000_000_000))
        }
    }

    /// New drone hotspots show up by themselves: a Wi-Fi scan every 12 s while
    /// this screen is open and no setup runs (a scan takes the adapter off its
    /// channel for a moment; there is no video here).
    private func watchHotspots() async {
        while !Task.isCancelled {
            handoff.refreshCurrentSSID()
            if setup == nil, !handoff.phase.isProvisioning { await handoff.scanHotspots() }
            try? await Task.sleep(nanoseconds: 12_000_000_000)
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(spacing: 14) {
            if let icon = AppIcon.image {
                Image(nsImage: icon)
                    .resizable().interpolation(.high)
                    .frame(width: 64, height: 64)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
            VStack(spacing: 6) {
                (Text("Bumblebee ").foregroundColor(ConnectTheme.text)
                    + Text("GCS").foregroundColor(ConnectTheme.orange))
                    .font(.system(size: 26, weight: .bold)).tracking(-0.3)
                Text("Select a drone to connect")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(ConnectTheme.muted)
                Text(AppVersion.label)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(ConnectTheme.muted)
            }
        }
    }

    // MARK: - Drones (auto-discovered, unified list)

    private struct HotspotItem: Identifiable {
        let hotspot: WifiHandoff.Hotspot
        let kind: HotspotRow
        var id: String { hotspot.id }
    }

    private var hotspotItems: [HotspotItem] {
        handoff.hotspots.compactMap { h in
            let kind = HotspotRow.of(ssid: h.ssid, known: app.knownDrones, visibleIDs: scanner.visibleIDs)
            return kind == .hidden ? nil : HotspotItem(hotspot: h, kind: kind)
        }
    }

    private func dronesPanel(listMaxHeight: CGFloat) -> some View {
        let drones = scanner.drones, unknown = scanner.unknownDevices, hotspots = hotspotItems
        let rows = CGFloat(drones.count + hotspots.count) * rowHeight + CGFloat(unknown.count) * 40
        return VStack(spacing: 0) {
            HStack(spacing: 8) {
                Text("AVAILABLE DRONES")
                    .font(.system(size: 11, design: .monospaced)).tracking(1.4)
                    .foregroundStyle(ConnectTheme.faint)
                if scanner.scanning {
                    ProgressView().controlSize(.small).scaleEffect(0.7)
                }
                Spacer()
                Button { setup = SetupRequest(drone: nil) } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "plus").font(.system(size: 11, weight: .bold))
                        Text("Add drone").font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundStyle(ConnectTheme.orange)
                }
                .buttonStyle(.plain)
                .help("Set up a new drone so it joins this Mac's WiFi")
                .padding(.trailing, 10)
                Button { scanner.scan(); Task { await handoff.scanHotspots() } } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ConnectTheme.blueSoft)
                }
                .buttonStyle(.plain)
                .help("Rescan the network")
                .disabled(scanner.scanning)
            }
            .padding(.bottom, 10)

            if handoff.phase == .needLocationPermission {
                locationBanner.padding(.bottom, 10)
            }
            if case .joiningHotspot(let ssid) = handoff.phase, setup == nil {
                statusLine("Joining \(ssid)… this Mac leaves its WiFi meanwhile.")
            }
            if case .failed(let f) = handoff.phase, setup == nil, f.kind == .droneSilent {
                statusLine("\(f.title). \(f.detail)", color: ConnectTheme.orange)
            }

            if !drones.isEmpty || !hotspots.isEmpty || !unknown.isEmpty {
                ScrollView {
                    VStack(spacing: 9) {
                        ForEach(drones) { d in
                            DiscoveredRow(drone: d) { app.connect(to: d.ip, expectedID: d.droneID) }
                        }
                        // Drones only reachable via their own setup hotspot.
                        ForEach(hotspots) { item in
                            HotspotDroneRow(hotspot: item.hotspot, kind: item.kind,
                                            setup: { setup = SetupRequest(drone: item.hotspot.ssid) },
                                            direct: { connectDirect(item.hotspot.ssid) })
                        }
                        ForEach(unknown) { d in
                            UnknownDeviceRow(device: d) { app.connect(to: d.ip) }
                        }
                    }
                }
                .frame(height: min(rows, listMaxHeight))
            } else {
                emptyState(scanner.scanning || !scanner.hasScanned ? "Looking for drones…"
                                                                   : "No drones found",
                           scanner.discoveryError
                               ?? "Drones on this WiFi appear here by themselves. A new drone shows up about 30 s after power-on — then tap Add.")
            }
        }
    }

    /// Work with a drone over its own hotspot (no shared WiFi needed).
    private func connectDirect(_ ssid: String) {
        let expected = HotspotRow.id(of: ssid)
        Task {
            await handoff.connectDirect(hotspotSSID: ssid) { host in
                app.connect(to: host, expectedID: expected)
            }
        }
    }

    private func statusLine(_ text: String, color: Color = ConnectTheme.muted2) -> some View {
        Text(text)
            .font(.system(size: 11.5, design: .monospaced))
            .foregroundStyle(color)
            .frame(maxWidth: .infinity, alignment: .leading)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.bottom, 8)
    }

    /// macOS hides WiFi names (and so new drones) until Location is allowed.
    private var locationBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "location.circle").font(.system(size: 18)).foregroundStyle(ConnectTheme.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("Allow WiFi access to see new drones").font(.system(size: 13, weight: .semibold))
                Text("macOS shows WiFi names only to apps with Location Services on.")
                    .font(.system(size: 11, design: .monospaced)).foregroundStyle(ConnectTheme.muted2)
            }
            Spacer()
            Button("Allow") {
                handoff.requestLocation()
                if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices") {
                    NSWorkspace.shared.open(url)
                }
            }
            .buttonStyle(.plain).font(.system(size: 13, weight: .semibold))
            .foregroundStyle(ConnectTheme.orange)
        }
        .padding(.vertical, 11).padding(.horizontal, 14)
        .background(ConnectTheme.orange.opacity(0.07))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.orange.opacity(0.4), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func emptyState(_ title: String, _ subtitle: String) -> some View {
        VStack(spacing: 6) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(ConnectTheme.text)
            Text(subtitle)
                .font(.system(size: 11.5, design: .monospaced))
                .foregroundStyle(ConnectTheme.muted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 22).padding(.horizontal, 15)
    }

    // MARK: - Footer: manual address

    private var footer: some View {
        let trimmed = manualIP.trimmingCharacters(in: .whitespaces)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 10) {
                Text("IP").font(.system(size: 11, design: .monospaced)).tracking(1.3)
                    .foregroundStyle(ConnectTheme.faint)
                TextField("172.20.10.4", text: $manualIP)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14, design: .monospaced))
                    .foregroundStyle(ConnectTheme.text)
                    .onSubmit(connectManual)
                    .onChange(of: manualIP) { _, _ in manualProblem = nil; manualUnanswered = nil }
                if checkingManual { ProgressView().controlSize(.small) }
                Button(action: connectManual) {
                    Text("Connect")
                        .font(.system(size: 13, weight: .semibold))
                        .padding(.vertical, 9).padding(.horizontal, 18)
                        .background(trimmed.isEmpty ? Color.white.opacity(0.06) : ConnectTheme.blue)
                        .foregroundStyle(trimmed.isEmpty ? ConnectTheme.faint : .white)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .disabled(trimmed.isEmpty || checkingManual)
            }
            .padding(.leading, 16).padding(.trailing, 6).padding(.vertical, 10)
            .background(ConnectTheme.rowBg)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.hairline, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 12))

            if let p = manualProblem {
                Text(p).font(.system(size: 11.5, design: .monospaced)).foregroundStyle(ConnectTheme.orange)
            }
            if let host = manualUnanswered {
                HStack(alignment: .top) {
                    Text(ManualAddress.noAnswer(host))
                        .font(.system(size: 11.5, design: .monospaced)).foregroundStyle(ConnectTheme.orange)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Connect anyway") { app.connect(to: host) }
                        .buttonStyle(.plain).font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ConnectTheme.blueSoft)
                }
            }
        }
    }

    /// A typed address goes to the dashboard only when something answers on
    /// :9090 there (else a message and "Connect anyway"): a typo never becomes
    /// the remembered drone.
    private func connectManual() {
        let ip = manualIP.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !ip.isEmpty, !checkingManual else { return }
        if let p = ManualAddress.problem(ip) { manualProblem = p; return }
        checkingManual = true
        Task {
            let open = await scanner.isReachable(ip, timeout: 1.5)
            checkingManual = false
            if open { app.connect(to: ip) } else { manualUnanswered = ip }
        }
    }
}

// MARK: - Status dot (flat, no glow)

private struct Dot: View {
    let color: Color
    var size: CGFloat = 8
    var body: some View {
        Circle().fill(color).frame(width: size, height: size)
    }
}

// MARK: - The Mac sits on a drone's WiFi

/// macOS remembers the drone hotspots it joined and may hop onto one by itself
/// (shared password): then this Mac sees that drone, not the classroom.
struct OnDroneHotspotBanner: View {
    let ssid: String
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "wifi.exclamationmark").foregroundStyle(ConnectTheme.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text("This Mac is on \(ssid), a drone's own WiFi").font(.system(size: 13, weight: .semibold))
                Text("Pick your classroom WiFi in the menu bar. To stop macOS from joining drone networks by itself, remove them in System Settings → Wi-Fi → Known Networks.")
                    .font(.system(size: 11, design: .monospaced)).foregroundStyle(ConnectTheme.muted2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 10).padding(.horizontal, 14)
        .background(ConnectTheme.orange.opacity(0.07))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.orange.opacity(0.4), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

// MARK: - Last drone (hero action)

private struct LastDroneCard: View {
    let drone: KnownDrone
    let ip: String
    var reachable: Bool
    let connect: () -> Void
    let forget: () -> Void
    @State private var hover = false

    var body: some View {
        HStack(spacing: 16) {
            Button(action: connect) {
                HStack(spacing: 14) {
                    Dot(color: reachable ? ConnectTheme.green : ConnectTheme.faint, size: 10)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(drone.name == ip ? "Last drone" : drone.name).font(.system(size: 16, weight: .semibold))
                        Text("\(ip) · \(reachable ? "last connection" : "not answering")"
                             + (drone.verified ? "" : " · unverified"))
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(ConnectTheme.muted2)
                    }
                    Spacer(minLength: 8)
                    HStack(spacing: 7) {
                        Text("Connect").font(.system(size: 14, weight: .semibold))
                        Text("→").font(.system(size: 14, design: .monospaced))
                    }
                    .foregroundStyle(ConnectTheme.orange)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            Button("Forget", action: forget)
                .buttonStyle(.plain).font(.system(size: 11, design: .monospaced))
                .foregroundStyle(ConnectTheme.faint)
                .help("Remove this drone from the remembered list")
        }
        .padding(.vertical, 16).padding(.horizontal, 20)
        .background(
            LinearGradient(colors: [ConnectTheme.orange.opacity(0.12), ConnectTheme.orange.opacity(0.02)],
                           startPoint: .leading, endPoint: .trailing)
        )
        .overlay(RoundedRectangle(cornerRadius: 14)
            .stroke(ConnectTheme.orange.opacity(hover ? 0.7 : 0.4), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .onHover { hover = $0 }
    }
}

// MARK: - Discovered drone row

private struct DiscoveredRow: View {
    let drone: DroneScanner.Drone
    let connect: () -> Void
    @State private var hover = false
    @State private var btnHover = false

    private var name: String { drone.name == drone.ip ? "Drone" : drone.name }
    private var detail: String {
        var parts = [drone.ip]
        parts.append(drone.droneID.map { "id \($0)" } ?? "id unknown")
        if drone.liveness == .unsure { parts.append("not answering") }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: 14) {
            Dot(color: drone.liveness == .live ? ConnectTheme.green : ConnectTheme.faint)
            VStack(alignment: .leading, spacing: 3) {
                Text(name).font(.system(size: 14.5, weight: .semibold))
                Text(detail)
                    .font(.system(size: 11.5, design: .monospaced))
                    .foregroundStyle(ConnectTheme.muted2)
            }
            Spacer(minLength: 8)
            Button(action: connect) {
                Text("Connect")
                    .font(.system(size: 13, weight: .semibold))
                    .padding(.vertical, 9).padding(.horizontal, 16)
                    .background(btnHover ? ConnectTheme.blue : ConnectTheme.blue.opacity(0.1))
                    .foregroundStyle(btnHover ? .white : ConnectTheme.blueSoft)
                    .overlay(RoundedRectangle(cornerRadius: 9)
                        .stroke(btnHover ? ConnectTheme.blue : ConnectTheme.blue.opacity(0.5), lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 9))
            }
            .buttonStyle(.plain)
            .onHover { btnHover = $0 }
        }
        .padding(.vertical, 13).padding(.horizontal, 15)
        .background(hover ? ConnectTheme.blue.opacity(0.05) : ConnectTheme.rowBg)
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(hover ? ConnectTheme.blue.opacity(0.45) : ConnectTheme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .opacity(drone.liveness == .live ? 1 : 0.6)
        .onHover { hover = $0 }
    }
}

// MARK: - A host with port 9090 open that does not answer like a drone

private struct UnknownDeviceRow: View {
    let device: DroneScanner.Drone
    let connect: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Dot(color: ConnectTheme.faint, size: 6)
            Text("Unknown device · \(device.ip) · port 9090 open, not a drone")
                .font(.system(size: 11.5, design: .monospaced))
                .foregroundStyle(ConnectTheme.faint)
            Spacer()
            Button("Connect anyway", action: connect)
                .buttonStyle(.plain).font(.system(size: 11, weight: .semibold))
                .foregroundStyle(ConnectTheme.muted2)
        }
        .padding(.vertical, 6).padding(.horizontal, 15)
    }
}

// MARK: - Drone-hotspot row (needs setup, or lost its WiFi)

private struct HotspotDroneRow: View {
    let hotspot: WifiHandoff.Hotspot
    let kind: HotspotRow
    let setup: () -> Void
    let direct: () -> Void
    @State private var hover = false

    private var title: String {
        if case .lostWifi(let name) = kind { return name }
        return hotspot.ssid
    }
    private var subtitle: String {
        if case .lostWifi = kind { return "lost its WiFi · running its own hotspot \(hotspot.ssid)" }
        return "new drone · not on your WiFi yet"
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: "antenna.radiowaves.left.and.right")
                .font(.system(size: 13))
                .foregroundStyle(ConnectTheme.orange)
                .frame(width: 12)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.system(size: 14.5, weight: .semibold))
                Text(subtitle)
                    .font(.system(size: 11.5, design: .monospaced))
                    .foregroundStyle(ConnectTheme.muted2)
            }
            Spacer(minLength: 8)
            Text("\(hotspot.rssi) dBm")
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(ConnectTheme.faint)
            Button("Direct", action: direct)
                .buttonStyle(.plain).font(.system(size: 12, weight: .semibold))
                .foregroundStyle(ConnectTheme.blueSoft)
                .help("Join this drone's own WiFi. The Mac has no internet while connected directly.")
            Button(action: setup) {
                HStack(spacing: 6) {
                    Text(kind == .new ? "Add" : "Bring back").font(.system(size: 13, weight: .semibold))
                    Text("→").font(.system(size: 13, design: .monospaced))
                }
                .foregroundStyle(ConnectTheme.orange)
            }
            .buttonStyle(.plain)
        }
        .padding(.vertical, 13).padding(.horizontal, 15)
        .background(hover ? ConnectTheme.orange.opacity(0.06) : ConnectTheme.rowBg)
        .overlay(RoundedRectangle(cornerRadius: 12)
            .stroke(hover ? ConnectTheme.orange.opacity(0.5) : ConnectTheme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .onHover { hover = $0 }
    }
}
