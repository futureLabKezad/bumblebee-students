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
    @State private var section: Section? = .dashboard

    var body: some View {
        NavigationSplitView {
            sidebar
                .navigationSplitViewColumnWidth(min: 210, ideal: 224, max: 260)
        } detail: {
            VStack(spacing: 0) {
                // Safety banners stay on top of every section until they clear.
                if telemetry.fcLost { AlarmBanner(text: FcLostAlarm.text, icon: "exclamationmark.octagon.fill") }
                if let low = telemetry.lowBattery { AlarmBanner(text: low, icon: "battery.25percent") }
                // Inline switch (not a computed property) so the detail column
                // reliably re-renders when `section` changes.
                Group {
                    switch section ?? .dashboard {
                    case .dashboard: DashboardView()
                    case .entertainment: EntertainmentView()
                    case .settings: SettingsView()
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .navigationTitle(app.droneHost)
            .toolbar { toolbarContent }
        }
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
                app.disconnect()
            } label: {
                Label("Disconnect", systemImage: "power").frame(maxWidth: .infinity)
            }
            .buttonStyle(GhostButtonStyle())
            .padding(Theme.s3)
        }
        .background(.ultraThinMaterial)
    }

    private func navRow(_ s: Section) -> some View {
        let active = (section ?? .dashboard) == s
        return Button { section = s } label: {
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
            StatusDot(color: linkDotColor, pulsing: telemetry.link != .ok)
            VStack(alignment: .leading, spacing: Theme.s0 - 1) {
                Text(app.droneHost).font(Theme.hostMono)
                Text(linkLine)
                    .font(Theme.sectionLbl).foregroundStyle(Theme.muted)
            }
            Spacer(minLength: 0)
        }
        .padding(Theme.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .glassCard(Theme.rControl)
    }

    private var linkLine: String {
        switch telemetry.link {
        case .ok: return "linked"
        case .noDrone: return telemetry.rosConnected ? "waiting for FC data" : "linking…"
        case .fcNotConnected: return "FC not connected"
        case .telemetryFrozen: return "telemetry frozen"
        }
    }

    private var linkDotColor: Color {
        switch telemetry.link {
        case .ok: return Theme.ok
        case .noDrone: return Theme.warn
        case .fcNotConnected, .telemetryFrozen: return Theme.danger
        }
    }

    @ToolbarContentBuilder private var toolbarContent: some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            Button { app.reconnect() } label: { Image(systemName: "arrow.triangle.2.circlepath") }
                .help("Reconnect")
            Button { app.scanner.scan() } label: { Image(systemName: "dot.radiowaves.left.and.right") }
                .help("Rescan network")
        }
    }
}
