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
import Combine
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
    /// Drones this Mac connected to, most recent first (DiscoveryLogic.swift).
    @Published private(set) var knownDrones: [KnownDrone] = AppState.loadKnown()
    /// Bumped by Reconnect so the camera views reopen their streams too.
    @Published var videoEpoch = 0
    /// Id of the drone this session talks to (last 4 hex digits of its MAC, as
    /// in Bonjour TXT and /api/wifi/status); nil until known or on drone
    /// software without one. Settings refuses changes when another id answers.
    @Published var droneID: String?
    /// Set when the drone answering at the address is not the one picked.
    @Published var identityMismatch: String?

    /// The last drone, for the connect screen's first card.
    var lastDrone: KnownDrone? { knownDrones.first }

    /// The drone's name for confirmations and messages.
    var droneName: String {
        if let n = scanner.found.first(where: { $0.ip == droneHost })?.name, n != droneHost { return n }
        if let id = droneID, !id.isEmpty { return "Bumblebee-\(id)" }
        return droneHost
    }

    /// An animation or show this session started and has not stopped since.
    /// Disconnect, another drone and quitting stop it (best effort); the drone
    /// itself stops every animation after 2 minutes anyway.
    var startedLedAnimation = false

    private var activity: NSObjectProtocol?
    private var terminateObserver: NSObjectProtocol?
    private var linkedSink: AnyCancellable?
    private static let knownKey = "knownDronesV2"

    init() {
        terminateObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.stopOwnLedAnimation(blocking: true) }
        }
        // A drone is remembered only once it answered: a mistyped address or a
        // device that is not a drone never becomes the "last drone".
        linkedSink = telemetry.$rosConnected.removeDuplicates().sink { [weak self] linked in
            guard linked else { return }
            DispatchQueue.main.async { self?.rememberCurrent() }
        }
    }

    /// Stops the animation this session started on the current drone.
    func stopOwnLedAnimation(blocking: Bool = false) {
        guard startedLedAnimation, !droneHost.isEmpty else { return }
        startedLedAnimation = false
        let api = DroneAPI()
        api.host = droneHost
        if blocking {
            api.ledResetNow(timeout: 1.5)
        } else {
            Task { try? await api.ledReset() }
        }
    }

    /// `expectedID`: the id of the drone picked (Last drone card, a Bonjour
    /// row); the id answering at `ip` is checked against it.
    func connect(to ip: String, expectedID: String? = nil) {
        let ip = ip.trimmingCharacters(in: .whitespaces)
        guard !ip.isEmpty else { return }
        // Another drone: nothing of the previous one may stay on screen (trail,
        // charts, log, values, armed, Pi metrics). The same drone keeps its log.
        if ConnectKind.of(previousHost: droneHost, newHost: ip) == .newDrone {
            stopOwnLedAnimation()
            telemetry.resetAll()
            metrics.reset()
            droneID = nil
        }
        identityMismatch = nil
        droneHost = ip
        api.host = ip
        ros.connect(host: ip)
        metrics.start(host: ip)
        telemetry.startClock()
        connected = true
        beginKeepAwake()
        checkIdentity(host: ip, expectedID: expectedID)
    }

    /// Reads the id answering at `host`; remembers the drone when it answers.
    private func checkIdentity(host: String, expectedID: String?) {
        Task {
            guard let status = try? await api.wifiStatus(), host == droneHost else { return }
            if let id = status.id {
                droneID = id
                if let want = expectedID, !want.isEmpty, want.uppercased() != id.uppercased() {
                    let name = knownDrones.first { $0.droneID == want.uppercased() }?.name ?? "Bumblebee-\(want)"
                    identityMismatch = ConnectIdentity.mismatchText(expectedName: name, foundID: id)
                    return
                }
            }
            rememberCurrent()
        }
    }

    /// Upsert the current drone into the remembered fleet (by id when known).
    private func rememberCurrent() {
        guard connected, !droneHost.isEmpty, identityMismatch == nil else { return }
        knownDrones = KnownFleet.upsert(knownDrones, droneID: droneID, name: droneName, ip: droneHost, now: Date())
        saveKnown()
    }

    /// "Forget" on the connect screen.
    func forget(_ drone: KnownDrone) {
        knownDrones = KnownFleet.forget(knownDrones, key: drone.id)
        saveKnown()
    }

    private func saveKnown() {
        if let data = try? JSONEncoder().encode(knownDrones) {
            UserDefaults.standard.set(data, forKey: Self.knownKey)
        }
    }

    /// The fleet, or the 1.1.0 entries (host + name, by IP) moved over once.
    private static func loadKnown() -> [KnownDrone] {
        let d = UserDefaults.standard
        if let data = d.data(forKey: knownKey),
           let list = try? JSONDecoder().decode([KnownDrone].self, from: data) { return list }
        struct Old: Codable { var host: String; var name: String }
        let old = (d.data(forKey: "knownDrones")).flatMap { try? JSONDecoder().decode([Old].self, from: $0) } ?? []
        return KnownFleet.migrate(hosts: old.map { ($0.host, $0.name) }, lastHost: d.string(forKey: "lastHost"), now: Date())
    }

    func reconnect() {
        guard connected, !droneHost.isEmpty else { return }
        ros.connect(host: droneHost)
        metrics.start(host: droneHost)
        videoEpoch += 1
    }

    func disconnect() {
        stopOwnLedAnimation()
        ros.disconnect()
        metrics.stop()
        telemetry.stopClock()
        connected = false
        identityMismatch = nil
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
