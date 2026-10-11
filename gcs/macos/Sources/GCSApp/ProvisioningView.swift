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

/// "Add a drone": pick a new drone nearby, confirm this Mac's WiFi password,
/// and the app does the rest — it talks to the drone over the drone's own
/// WiFi, hands it this Mac's network, brings the Mac back and connects. The
/// drone's own WiFi is an implementation detail; it only surfaces as the
/// "connect directly" fallback when the shared network cannot work.
struct ProvisioningView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var handoff: WifiHandoff
    @Environment(\.dismiss) private var dismiss
    /// Drone picked on the launch screen: added right away if the WiFi
    /// password is already known.
    var preselected: String? = nil

    @State private var password = ""
    @State private var editingPassword = false
    @State private var lastDrone: String?          // hotspot SSID of the last attempt
    @State private var needPassword = false
    @FocusState private var passwordFocused: Bool

    private let rescan = Timer.publish(every: 5, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            ConnectTheme.background.ignoresSafeArea()
            VStack(alignment: .leading, spacing: 18) {
                header
                Divider().overlay(ConnectTheme.hairline)
                content
                Spacer(minLength: 0)
            }
            .padding(28)
        }
        .frame(width: 560, height: 580)
        .foregroundStyle(ConnectTheme.text)
        .onAppear {
            handoff.reset()
            handoff.refreshCurrentSSID()
            loadPassword()
            Task {
                await handoff.scanHotspots()
                if let drone = preselected, !homeWifi.isEmpty {
                    if password.isEmpty { needPassword = true; passwordFocused = true; lastDrone = drone }
                    else { add(drone) }
                }
            }
        }
        .onReceive(rescan) { _ in
            // Keep the list fresh while the user is choosing (new drones appear
            // ~30 s after power-on).
            if handoff.phase == .picking || handoff.phase == .idle {
                Task { await handoff.scanHotspots() }
            }
        }
        .onChange(of: doneHost) { _, host in
            if let host { app.connect(to: host); dismiss() }
        }
        .onChange(of: homeWifi) { _, _ in
            // The Mac moved to another network while the window was open.
            if !handoff.phase.isBusy { loadPassword() }
        }
    }

    private var doneHost: String? { if case let .done(h) = handoff.phase { return h }; return nil }
    private var failure: WifiHandoff.Failure? { if case let .failed(f) = handoff.phase { return f }; return nil }
    private var homeWifi: String { handoff.homeSSID }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Add a drone").font(.system(size: 20, weight: .bold))
                Text(headerSubtitle)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(ConnectTheme.muted)
            }
            Spacer()
            Button("Close") { handoff.reset(); dismiss() }
                .buttonStyle(.plain)
                .foregroundStyle(ConnectTheme.muted)
                .disabled(handoff.phase.isBusy)
        }
    }

    // MARK: - Content

    @ViewBuilder private var content: some View {
        if handoff.phase.isBusy && handoff.phase != .scanning {
            progressView
        } else if let failure {
            failureView(failure)
        } else if handoff.phase == .needLocationPermission {
            permissionView
        } else {
            pickView
        }
    }

    // Choosing a drone.
    private var pickView: some View {
        VStack(alignment: .leading, spacing: 14) {
            sectionLabel("NEW DRONES NEARBY")
            if handoff.hotspots.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 10) {
                        ProgressView().controlSize(.small)
                        Text("Looking for drones…").font(.system(size: 14, weight: .semibold))
                    }
                    Text("Turn the drone on. In about 30 seconds its lights breathe blue and it shows up here.")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(ConnectTheme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(ConnectTheme.rowBg)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.hairline, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 12))
            } else {
                ScrollView {
                    VStack(spacing: 8) { ForEach(handoff.hotspots) { droneRow($0) } }
                }
                .frame(maxHeight: 200)
            }

            sectionLabel("YOUR WIFI")
            wifiCard
            if let drone = preselected, needPassword {
                HStack {
                    Spacer()
                    primaryButton("Add \(drone)") { add(drone) }
                }
            }
        }
    }

    private func droneRow(_ h: WifiHandoff.Hotspot) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "airplane.circle.fill").font(.system(size: 22))
                .foregroundStyle(ConnectTheme.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(h.ssid).font(.system(size: 14.5, weight: .semibold))
                Text("new drone · \(signalWord(h.rssi)) signal")
                    .font(.system(size: 11.5, design: .monospaced)).foregroundStyle(ConnectTheme.muted2)
            }
            Spacer()
            Button { add(h.ssid) } label: {
                Text("Add").font(.system(size: 13, weight: .semibold))
                    .padding(.vertical, 8).padding(.horizontal, 18)
                    .background(homeWifi.isEmpty ? Color.white.opacity(0.06) : ConnectTheme.blue)
                    .foregroundStyle(homeWifi.isEmpty ? ConnectTheme.faint : .white)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.plain)
            .disabled(homeWifi.isEmpty)
        }
        .padding(.vertical, 11).padding(.horizontal, 14)
        .background(ConnectTheme.rowBg)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // This Mac's network + its password (asked once, remembered on this Mac).
    private var wifiCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "wifi").foregroundStyle(ConnectTheme.blueSoft)
                Text(homeWifi.isEmpty ? "Not connected" : homeWifi).font(.system(size: 14, weight: .semibold))
                Spacer()
                if !editingPassword && !password.isEmpty {
                    Text("password saved").font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(ConnectTheme.green)
                    Button("Change") { editingPassword = true; passwordFocused = true }
                        .buttonStyle(.plain).font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(ConnectTheme.blueSoft)
                }
            }
            if editingPassword || password.isEmpty {
                SecureField("Password for \(homeWifi.isEmpty ? "your WiFi" : homeWifi)", text: $password)
                    .textFieldStyle(.plain).font(.system(size: 14, design: .monospaced))
                    .focused($passwordFocused)
                    .padding(.horizontal, 12).padding(.vertical, 9)
                    .background(Color.white.opacity(0.04))
                    .overlay(RoundedRectangle(cornerRadius: 8)
                        .stroke(needPassword ? ConnectTheme.orange : ConnectTheme.hairline, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                Text(needPassword ? "Enter the password first — the drone needs it to join \(homeWifi)."
                                  : "The drone needs it to join this network. Saved on this Mac.")
                    .font(.system(size: 10.5, design: .monospaced))
                    .foregroundStyle(needPassword ? ConnectTheme.orange : ConnectTheme.faint)
            }
        }
        .padding(14)
        .background(ConnectTheme.rowBg)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // Live checklist while the app works.
    private var progressView: some View {
        let step = currentStep
        let drone = lastDrone ?? "the drone"
        return VStack(alignment: .leading, spacing: 14) {
            sectionLabel("ADDING \(drone.uppercased())")
            VStack(alignment: .leading, spacing: 12) {
                checkRow("Connecting to \(drone)", index: 1, current: step)
                checkRow("Sending your WiFi \(homeWifi)", index: 2, current: step)
                checkRow("Drone joins \(homeWifi), Mac comes back", index: 3, current: step)
                checkRow(step == 4 ? "Checking what went wrong…" : "Finding the drone on \(homeWifi)",
                         index: 4, current: step)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(ConnectTheme.rowBg)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.hairline, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            Text("This takes up to a minute. The Mac briefly leaves \(homeWifi) and comes back on its own — keep this window open.")
                .font(.system(size: 11.5, design: .monospaced))
                .foregroundStyle(ConnectTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var currentStep: Int {
        switch handoff.phase {
        case .joiningHotspot: return 1
        case .pushingCreds: return 2
        case .waitingForDrone: return 3
        case .diagnosing: return 4
        default: return 0
        }
    }

    private func checkRow(_ text: String, index: Int, current: Int) -> some View {
        HStack(spacing: 10) {
            Group {
                if index < current {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(ConnectTheme.green)
                } else if index == current {
                    ProgressView().controlSize(.small)
                } else {
                    Image(systemName: "circle").foregroundStyle(ConnectTheme.faint)
                }
            }
            .frame(width: 18)
            Text(text).font(.system(size: 13.5, weight: index == current ? .semibold : .regular))
                .foregroundStyle(index > current ? ConnectTheme.muted : ConnectTheme.text)
        }
    }

    // Failure with the reason the drone reported, and what to do.
    private func failureView(_ f: WifiHandoff.Failure) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 22))
                    .foregroundStyle(ConnectTheme.orange)
                VStack(alignment: .leading, spacing: 6) {
                    Text(f.title).font(.system(size: 15, weight: .semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Text(f.detail).font(.system(size: 12.5))
                        .foregroundStyle(ConnectTheme.muted2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if f.kind == .wrongPassword {
                wifiCard
                    .onAppear { editingPassword = true; password = ""; passwordFocused = true }
            }
            HStack(spacing: 10) {
                if let drone = lastDrone {
                    primaryButton("Try again") { add(drone) }
                    if f.offerDirect {
                        secondaryButton("Connect directly to the drone") { direct(drone) }
                    }
                }
                Spacer()
                Button("Back") { handoff.reset(); Task { await handoff.scanHotspots() } }
                    .buttonStyle(.plain).foregroundStyle(ConnectTheme.muted)
            }
            if f.offerDirect {
                Text("Directly: the Mac joins the drone's own WiFi. Works anywhere, but the Mac has no internet while connected.")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(ConnectTheme.faint)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var permissionView: some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "location.circle").font(.system(size: 36)).foregroundStyle(ConnectTheme.orange)
            Text("Allow WiFi access to find drones").font(.system(size: 15, weight: .semibold))
            Text("macOS only lets apps see WiFi names when Location Services are on for them. Turn on Location Services and Bumblebee GCS, then come back.")
                .font(.system(size: 12.5))
                .foregroundStyle(ConnectTheme.muted2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 10) {
                primaryButton("Open Settings") { openLocationSettings() }
                secondaryButton("I've allowed it") { handoff.requestLocation(); Task { await handoff.scanHotspots() } }
            }
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .onAppear { handoff.requestLocation() }
    }

    private var headerSubtitle: String {
        if homeWifi.isEmpty {
            return handoff.onDroneHotspot ? "This Mac is on a drone's WiFi — connect it to your WiFi first"
                                          : "Connect this Mac to WiFi first"
        }
        return handoff.onDroneHotspot ? "It will join \(homeWifi); this Mac goes back to it afterwards"
                                      : "It will join \(homeWifi), the same WiFi as this Mac"
    }

    private func loadPassword() {
        password = AppKeychain.password(for: homeWifi) ?? ""
        editingPassword = password.isEmpty
    }

    // MARK: - Actions

    private func add(_ drone: String) {
        guard !password.isEmpty else {
            needPassword = true; editingPassword = true; passwordFocused = true
            return
        }
        needPassword = false
        editingPassword = false
        lastDrone = drone
        AppKeychain.setPassword(password, for: homeWifi)
        let target = homeWifi, pass = password
        Task {
            await handoff.provision(hotspotSSID: drone, targetSSID: target,
                                    targetPassword: pass, onDrone: { _ in })
        }
    }

    private func direct(_ drone: String) {
        Task { await handoff.connectDirect(hotspotSSID: drone, onDrone: { _ in }) }
    }

    private func openLocationSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices") {
            NSWorkspace.shared.open(url)
        }
    }

    // MARK: - Bits

    private func signalWord(_ rssi: Int) -> String {
        rssi >= -55 ? "strong" : rssi >= -70 ? "good" : "weak"
    }

    private func sectionLabel(_ s: String) -> some View {
        Text(s).font(.system(size: 11, design: .monospaced)).tracking(1.3)
            .foregroundStyle(ConnectTheme.faint)
    }

    private func primaryButton(_ title: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(.system(size: 13, weight: .semibold))
                .padding(.vertical, 9).padding(.horizontal, 16)
                .background(ConnectTheme.blue).foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 8))
        }
        .buttonStyle(.plain)
    }

    private func secondaryButton(_ title: String, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(.system(size: 13, weight: .semibold))
                .padding(.vertical, 9).padding(.horizontal, 14)
                .foregroundStyle(ConnectTheme.blueSoft)
                .overlay(RoundedRectangle(cornerRadius: 8).stroke(ConnectTheme.blue.opacity(0.5), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}
