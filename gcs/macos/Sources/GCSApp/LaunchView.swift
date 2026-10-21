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

/// Connect screen — one unified panel. Drones auto-appear by name via Bonjour
/// (no manual "scan" step); a single footer combines the two fallbacks —
/// entering an IP by hand and setting up a brand-new drone over its hotspot.
/// Copy is English and type is SF (system); the orange/blue palette lives in
/// `ConnectTheme` and is scoped to this screen + the splash.
/// One opening of the setup sheet; `drone` is the hotspot SSID tapped, if any.
struct SetupRequest: Identifiable {
    let id = UUID()
    let drone: String?
}

struct LaunchView: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var scanner: DroneScanner
    @EnvironmentObject var handoff: WifiHandoff
    @State private var manualIP = ""
    @State private var lastPingOK = false
    /// The open "Add a drone" sheet and the drone it was opened for. One value
    /// for both, passed by `.sheet(item:)`: with a separate flag the sheet was
    /// built from a stale copy and never saw the drone that was tapped.
    @State private var setup: SetupRequest?

    var body: some View {
        ZStack {
            ConnectTheme.background.ignoresSafeArea()

            VStack(spacing: 22) {
                header

                if let last = app.lastHost {
                    LastDroneCard(ip: last, reachable: lastReachable(last)) { app.connect(to: last) }
                        .task(id: last) {
                            lastPingOK = false
                            lastPingOK = await scanner.isReachable(last)
                        }
                }

                dronesPanel
                footer
            }
            .frame(maxWidth: 560)
            .padding(.horizontal, 24)
        }
        .foregroundStyle(ConnectTheme.text)
        .sheet(item: $setup) { request in
            ProvisioningView(preselected: request.drone)
        }
        .task { await handoff.scanHotspots() }   // surface drone hotspots in the list
    }

    /// The last drone is "live" if discovery already found it, or a one-off
    /// ping to :9090 answered. Otherwise the dot stays gray.
    private func lastReachable(_ ip: String) -> Bool {
        scanner.found.contains { $0.ip == ip } || lastPingOK
    }

    // MARK: - Header

    private var header: some View {
        VStack(spacing: 16) {
            if let icon = AppIcon.image {
                Image(nsImage: icon)
                    .resizable().interpolation(.high)
                    .frame(width: 72, height: 72)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
            VStack(spacing: 7) {
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

    private var dronesPanel: some View {
        VStack(spacing: 0) {
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

            if !scanner.found.isEmpty || !handoff.hotspots.isEmpty {
                VStack(spacing: 9) {
                    ForEach(scanner.found) { d in
                        DiscoveredRow(drone: d) { app.connect(to: d.ip) }
                    }
                    // Drones only reachable via their own setup hotspot (offline
                    // from this WiFi). Tapping opens the hand-off wizard.
                    ForEach(handoff.hotspots) { h in
                        HotspotDroneRow(hotspot: h) { setup = SetupRequest(drone: h.ssid) }
                    }
                }
            } else {
                emptyState(scanner.scanning || !scanner.hasScanned ? "Looking for drones…"
                                                                   : "No drones found",
                           scanner.discoveryError
                               ?? "Drones on this WiFi appear here automatically. A new drone shows up about 30 s after power-on — then tap Add.")
            }
        }
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

    // MARK: - Footer: manual IP

    private var footer: some View {
        let trimmed = manualIP.trimmingCharacters(in: .whitespaces)
        return HStack(spacing: 10) {
            Text("IP").font(.system(size: 11, design: .monospaced)).tracking(1.3)
                .foregroundStyle(ConnectTheme.faint)
            TextField("172.20.10.4", text: $manualIP)
                .textFieldStyle(.plain)
                .font(.system(size: 14, design: .monospaced))
                .foregroundStyle(ConnectTheme.text)
                .onSubmit(connectManual)
            Button(action: connectManual) {
                Text("Connect")
                    .font(.system(size: 13, weight: .semibold))
                    .padding(.vertical, 9).padding(.horizontal, 18)
                    .background(trimmed.isEmpty ? Color.white.opacity(0.06) : ConnectTheme.blue)
                    .foregroundStyle(trimmed.isEmpty ? ConnectTheme.faint : .white)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.plain)
            .disabled(trimmed.isEmpty)
        }
        .padding(.leading, 16).padding(.trailing, 6).padding(.vertical, 10)
        .background(ConnectTheme.rowBg)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(ConnectTheme.hairline, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private func connectManual() {
        let ip = manualIP.trimmingCharacters(in: .whitespaces)
        guard !ip.isEmpty else { return }
        app.connect(to: ip)
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

// MARK: - Last drone (hero action)

private struct LastDroneCard: View {
    let ip: String
    var reachable: Bool
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 16) {
                HStack(spacing: 14) {
                    Dot(color: reachable ? ConnectTheme.green : ConnectTheme.faint, size: 10)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Last drone").font(.system(size: 16, weight: .semibold))
                        Text("\(ip) · last connection")
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(ConnectTheme.muted2)
                    }
                }
                Spacer(minLength: 8)
                HStack(spacing: 7) {
                    Text("Connect").font(.system(size: 14, weight: .semibold))
                    Text("→").font(.system(size: 14, design: .monospaced))
                }
                .foregroundStyle(ConnectTheme.orange)
            }
            .padding(.vertical, 18).padding(.horizontal, 20)
            .background(
                LinearGradient(colors: [ConnectTheme.orange.opacity(0.12), ConnectTheme.orange.opacity(0.02)],
                               startPoint: .leading, endPoint: .trailing)
            )
            .overlay(RoundedRectangle(cornerRadius: 14)
                .stroke(ConnectTheme.orange.opacity(hover ? 0.7 : 0.4), lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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

    var body: some View {
        HStack(spacing: 14) {
            Dot(color: ConnectTheme.green)
            VStack(alignment: .leading, spacing: 3) {
                Text(name).font(.system(size: 14.5, weight: .semibold))
                Text("\(drone.ip) · rosbridge :9090")
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
        .onHover { hover = $0 }
    }
}

// MARK: - Drone-hotspot row (needs setup)

private struct HotspotDroneRow: View {
    let hotspot: WifiHandoff.Hotspot
    let setup: () -> Void
    @State private var hover = false

    var body: some View {
        Button(action: setup) {
            HStack(spacing: 14) {
                Image(systemName: "antenna.radiowaves.left.and.right")
                    .font(.system(size: 13))
                    .foregroundStyle(ConnectTheme.orange)
                    .frame(width: 12)
                VStack(alignment: .leading, spacing: 3) {
                    Text(hotspot.ssid).font(.system(size: 14.5, weight: .semibold))
                    Text("new drone · not on your WiFi yet")
                        .font(.system(size: 11.5, design: .monospaced))
                        .foregroundStyle(ConnectTheme.muted2)
                }
                Spacer(minLength: 8)
                Text("\(hotspot.rssi) dBm")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(ConnectTheme.faint)
                HStack(spacing: 6) {
                    Text("Add").font(.system(size: 13, weight: .semibold))
                    Text("→").font(.system(size: 13, design: .monospaced))
                }
                .foregroundStyle(ConnectTheme.orange)
            }
            .padding(.vertical, 13).padding(.horizontal, 15)
            .background(hover ? ConnectTheme.orange.opacity(0.06) : ConnectTheme.rowBg)
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(hover ? ConnectTheme.orange.opacity(0.5) : ConnectTheme.hairline, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}
