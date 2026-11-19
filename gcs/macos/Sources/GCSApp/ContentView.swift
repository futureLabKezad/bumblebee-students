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

struct RootView: View {
    @EnvironmentObject var app: AppState
    @State private var booted = false

    var body: some View {
        Group {
            if !booted {
                SplashView()
            } else if app.connected {
                MainShell()
            } else {
                LaunchView()
            }
        }
        .background(Theme.bg)
        .foregroundStyle(Theme.text)
        .task {
            // Hold the static boot screen briefly, then cut to the connect screen.
            // The network scan already started in AppMain.onAppear, so drones can
            // populate while the splash is up.
            try? await Task.sleep(nanoseconds: 1_300_000_000)
            booted = true
        }
    }
}

struct MainShell: View {
    @EnvironmentObject var app: AppState
    @EnvironmentObject var telemetry: TelemetryStore
    @EnvironmentObject var handoff: WifiHandoff
    @State private var section: Section? = .dashboard
    /// «Полёт» of this connection: the page, its bridge to the drone and STOP FLIGHT. It lives
    /// as long as this shell, so the editor's text and Python stay when another section is shown.
    @StateObject private var flight = FlightModel()
    @State private var askDisconnect = false

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 210, ideal: 224, max: 260)
        } detail: {
            VStack(spacing: 0) {
                // Safety banners stay on top of every section until they clear.
                if telemetry.fcLost { AlarmBanner(text: FcLostAlarm.text, icon: "exclamationmark.octagon.fill") }
                if let low = telemetry.lowBattery { AlarmBanner(text: low, icon: "battery.25percent") }
                // On a drone's hotspot by choice ("Connect directly") is fine; macOS
                // hopping onto one by itself is not.
                if handoff.onDroneHotspot && app.droneHost != kHotspotGatewayHost {
                    OnDroneHotspotBanner(ssid: handoff.currentSSID).padding(Theme.s2)
                }
                // Inline switch (not a computed property) so the detail column
                // reliably re-renders when `section` changes.
                Group {
                    switch section ?? .dashboard {
                    case .dashboard: DashboardView()
                    case .flight: FlightView(model: flight)
                    case .entertainment: EntertainmentView()
                    case .settings: SettingsView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .navigationTitle(app.droneHost)
            .toolbar { toolbarContent }
            .task {
                while !Task.isCancelled {
                    handoff.refreshCurrentSSID()
                    try? await Task.sleep(nanoseconds: 15_000_000_000)
                }
            }
            .alert("Not the drone you picked", isPresented: Binding(
                get: { app.identityMismatch != nil }, set: { if !$0 { app.identityMismatch = nil } })) {
                Button("Disconnect", role: .cancel) { app.disconnect() }
                Button("Stay connected") { app.identityMismatch = nil }
            } message: {
                Text(app.identityMismatch ?? "")
            }
        }
        .onAppear { flight.revive(app: app, reopen: section == .flight) }
        .onDisappear { flight.close() }     // Disconnect, another drone: «Взлёт?» closes as «no», the page stops
    }

    // MARK: - Sidebar

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: Theme.s2) {
                if let icon = AppIcon.image {
                    Image(nsImage: icon)
                        .resizable().interpolation(.high)
                        .frame(width: 22, height: 22)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.rMedia, style: .continuous))
                }
                Text("Bumblebee GCS").font(Theme.brand)
                Text(AppVersion.short).font(Theme.label).foregroundStyle(Theme.muted)
            }
            .padding(.horizontal, Theme.s4).padding(.top, Theme.s7).padding(.bottom, Theme.s3)

            connectionCard
                .padding(.horizontal, Theme.s3).padding(.bottom, Theme.s4)

            VStack(spacing: 2) {
                ForEach(Section.allCases) { s in
                    navRow(s)
                }
            }
            .padding(.horizontal, Theme.s2)

            Spacer(minLength: 0)

            Button {
                // Disconnect takes the Flight page and STOP FLIGHT off the screen while the
                // program on the drone flies on: ask first.
                if flight.missionActive { askDisconnect = true } else { app.disconnect() }
            } label: {
                Label("Disconnect", systemImage: "power").frame(maxWidth: .infinity)
            }
            .buttonStyle(GhostButtonStyle())
            .padding(Theme.s3)
            .alert("A flight program is running", isPresented: $askDisconnect) {
                Button("Stay connected", role: .cancel) {}
                Button("Stop the flight") { Task { await flight.stopFlight(app: app) } }
                Button("Disconnect anyway", role: .destructive) { app.disconnect() }
            } message: {
                Text("Disconnecting does not stop it, and the app cannot stop a drone it is not connected to. "
                     + "The RC (CH8) always stops it.")
            }
        }
        .background(.ultraThinMaterial)
    }

    private func navRow(_ s: Section) -> some View {
        let active = (section ?? .dashboard) == s
        return Button {
            if s == .flight { flight.open(app: app) }     // the first opening loads the page
            section = s
        } label: {
            HStack(spacing: Theme.s2) {
                Image(systemName: s.icon).frame(width: Theme.iconLg)
                Text(s.rawValue).font(active ? Theme.bodyStrong : Theme.body)
                Spacer(minLength: 0)
            }
            .foregroundStyle(active ? Theme.text : Theme.muted)
            .padding(.horizontal, Theme.s2).padding(.vertical, Theme.s2 + 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(active ? Theme.selectionBg : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: Theme.rControl))
            .contentShape(Rectangle())   // full-row tap target
        }
        .buttonStyle(.plain)
    }

    private var connectionCard: some View {
        HStack(spacing: Theme.s2) {
            StatusDot(color: Theme.color(telemetry.link.tone), pulsing: telemetry.link != .ok)
            VStack(alignment: .leading, spacing: Theme.s0 - 1) {
                Text(app.droneHost).font(Theme.hostMono)
                Text(telemetry.link.sidebarText(socketAnswered: telemetry.rosConnected))
                    .font(Theme.sectionLbl).foregroundStyle(Theme.muted)
            }
            Spacer(minLength: 0)
        }
        .padding(Theme.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(Theme.rControl)
    }

    @ToolbarContentBuilder private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            // The app's own Stop for a flight program, always there, in every section: it does not
            // depend on the web page (hidden, busy, broken), and a program may be flying that this
            // window did not start (the app was restarted or connected again).
            if !flight.stopNote.isEmpty {
                Text(flight.stopNote).font(Theme.label).foregroundStyle(Theme.muted)
            }
            Button { Task { await flight.stopFlight(app: app) } } label: {
                Text("STOP FLIGHT")
                    .font(Theme.bodyStrong).foregroundStyle(Color.white)
                    .padding(.horizontal, Theme.s3).padding(.vertical, 4)
                    .background(Theme.danger)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.rControl))
            }
            .buttonStyle(.plain)
            .help("Stop the flight program")
            Button { app.reconnect() } label: { Image(systemName: "arrow.triangle.2.circlepath") }
                .help("Reconnect")
            Button { app.scanner.scan() } label: { Image(systemName: "dot.radiowaves.left.and.right") }
                .help("Rescan network")
        }
    }
}
