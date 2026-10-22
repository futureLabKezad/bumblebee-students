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

enum Section: String, CaseIterable, Identifiable {
    case dashboard = "Dashboard"
    case entertainment = "Entertainment"
    case settings = "Settings"
    var id: String { rawValue }
    var icon: String {
        switch self {
        case .dashboard: return "gauge.with.dots.needle.bottom.50percent"
        case .entertainment: return "music.note"
        case .settings: return "wifi"
        }
    }
}

@main
struct GCSMacApp: App {
    @StateObject private var app = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .environmentObject(app.scanner)
                .environmentObject(app.telemetry)
                .environmentObject(app.metrics)
                .environmentObject(app.handoff)
                .frame(minWidth: 1100, minHeight: 720)
                .preferredColorScheme(.dark)
                .onAppear {
                    app.scanner.startDiscovery()   // continuous Bonjour/mDNS
                    app.scanner.scan()              // one-shot subnet fallback
                    app.handoff.requestLocation()   // settle WiFi-scan permission up front
                    DockIcon.install()
                }
        }
        .windowStyle(.titleBar)
        .commands {
            CommandGroup(after: .toolbar) {
                Button("Reconnect") { app.reconnect() }.keyboardShortcut("r", modifiers: .command)
                Button("Rescan Network") { app.scanner.scan() }.keyboardShortcut("k", modifiers: .command)
                Button("Disconnect") { app.disconnect() }.keyboardShortcut("d", modifiers: [.command, .shift])
            }
        }
    }
}

/// A drone the operator has connected to before — remembered across launches so
/// the fleet shows up by name without a fresh scan.
struct KnownDrone: Codable, Identifiable, Equatable {
    var id: String { host }   // ip/host, stable
    var host: String
    var name: String
}

@MainActor
final class AppState: ObservableObject {
    let scanner = DroneScanner()
    let telemetry = TelemetryStore()
    let metrics = MetricsClient()
    let api = DroneAPI()
    let handoff = WifiHandoff()
    private(set) lazy var ros = RosbridgeClient(store: telemetry)

    @Published var droneHost = ""
    @Published var connected = false
    @Published var lastHost: String? = UserDefaults.standard.string(forKey: "lastHost")
    @Published var knownDrones: [KnownDrone] = AppState.loadKnown()
    /// Bumped by Reconnect so the camera views reopen their streams too.
    @Published var videoEpoch = 0

    private var activity: NSObjectProtocol?
    private static let knownKey = "knownDrones"

    func connect(to ip: String) {
        let ip = ip.trimmingCharacters(in: .whitespaces)
        guard !ip.isEmpty else { return }
        // Another drone: nothing of the previous one may stay on screen (trail,
        // charts, log, values, armed, Pi metrics). The same drone keeps its log.
        if ConnectKind.of(previousHost: droneHost, newHost: ip) == .newDrone {
            telemetry.resetAll()
            metrics.reset()
        }
        droneHost = ip
        api.host = ip
        ros.connect(host: ip)
        metrics.start(host: ip)
        telemetry.startClock()
        connected = true
        lastHost = ip
        UserDefaults.standard.set(ip, forKey: "lastHost")
        rememberDrone(host: ip)
        beginKeepAwake()
    }

    /// Upsert a drone into the remembered fleet, keyed by host. Prefers a
    /// Bonjour-provided friendly name when the scanner has one.
    private func rememberDrone(host: String) {
        let name = scanner.found.first(where: { $0.ip == host })?.name ?? host
        if let idx = knownDrones.firstIndex(where: { $0.host == host }) {
            if name != host { knownDrones[idx].name = name }
        } else {
            knownDrones.append(KnownDrone(host: host, name: name))
        }
        if let data = try? JSONEncoder().encode(knownDrones) {
            UserDefaults.standard.set(data, forKey: Self.knownKey)
        }
    }

    private static func loadKnown() -> [KnownDrone] {
        guard let data = UserDefaults.standard.data(forKey: knownKey),
              let list = try? JSONDecoder().decode([KnownDrone].self, from: data) else { return [] }
        return list
    }

    func reconnect() {
        guard connected, !droneHost.isEmpty else { return }
        ros.connect(host: droneHost)
        metrics.start(host: droneHost)
        videoEpoch += 1
    }

    func disconnect() {
        ros.disconnect()
        metrics.stop()
        telemetry.stopClock()
        connected = false
        endKeepAwake()
    }

    private func beginKeepAwake() {
        guard activity == nil else { return }
        activity = ProcessInfo.processInfo.beginActivity(
            options: [.idleDisplaySleepDisabled, .userInitiated], reason: "Drone live video")
    }
    private func endKeepAwake() {
        if let a = activity { ProcessInfo.processInfo.endActivity(a); activity = nil }
    }
}

/// The Bumblebee app icon, bundled as a resource so it can be reused for the
/// dock icon and in-app logos.
enum AppIcon {
    static let image: NSImage? = Bundle.module.image(forResource: "AppIcon")
}

/// Sets the bundled bee icon as the dock/app icon at runtime, so it shows even
/// when launched outside a fully-assembled .app bundle.
enum DockIcon {
    static func install() {
        if let img = AppIcon.image {
            NSApplication.shared.applicationIconImage = img
        }
    }
}
