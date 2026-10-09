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

import Foundation
@preconcurrency import CoreWLAN
import CoreLocation

/// Fleet default PSK for a drone's setup hotspot (SSID "Bumblebee-XXXX").
/// The hotspot is raised by the drone's wifi-watchdog when it has no known WiFi.
let kHotspotPSK = "12345678"
/// Prefix every drone setup hotspot advertises.
let kHotspotPrefix = "Bumblebee-"
/// A drone in NetworkManager "shared" (AP) mode is the gateway at this address.
let kHotspotGatewayHost = "10.42.0.1"

/// One-tap WiFi hand-off: find a drone's setup hotspot over the air, join it,
/// push the Mac's own WiFi credentials to the drone, then wait for the drone to
/// come back on the shared network — all via CoreWLAN plus the drone's existing
/// `/api/wifi/*` backend. No System Keychain access (the target password is
/// entered once in-app), so macOS shows no admin prompt.
@MainActor
final class WifiHandoff: NSObject, ObservableObject, CLLocationManagerDelegate {
    enum Phase: Equatable {
        case idle
        case needLocationPermission
        case scanning
        case picking                 // hotspots listed for selection
        case joiningHotspot(String)
        case pushingCreds
        case waitingForDrone
        case done(String)            // resolved drone host
        case failed(String)

        var isBusy: Bool {
            switch self {
            case .scanning, .joiningHotspot, .pushingCreds, .waitingForDrone: return true
            default: return false
            }
        }
    }

    struct Hotspot: Identifiable, Equatable {
        let id: String       // ssid
        var ssid: String { id }
        var rssi: Int
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var hotspots: [Hotspot] = []
    /// The Mac's current WiFi SSID — the network we hand to the drone.
    @Published private(set) var currentSSID: String = ""

    private let loc = CLLocationManager()
    private var networksBySSID: [String: CWNetwork] = [:]

    override init() {
        super.init()
        loc.delegate = self
    }

    private var interface: CWInterface? { CWWiFiClient.shared().interface() }

    func reset() { phase = .idle }

    func refreshCurrentSSID() { currentSSID = interface?.ssid() ?? "" }

    // MARK: - Location (required for WiFi scan / SSID on macOS 14+)

    private func locationAuthorized() -> Bool {
        switch loc.authorizationStatus {
        case .authorizedAlways, .authorized, .authorizedWhenInUse: return true
        default: return false
        }
    }

    /// True once the system has made a decision we can't change in-app (denied
    /// or restricted) — the UI then points at System Settings instead of a
    /// prompt that will never appear again.
    var locationBlocked: Bool {
        loc.authorizationStatus == .denied || loc.authorizationStatus == .restricted
    }

    /// Proactively raise the system Location prompt if the user hasn't decided
    /// yet. Called at app launch so the permission is settled before setup.
    func requestLocation() {
        if loc.authorizationStatus == .notDetermined {
            loc.requestWhenInUseAuthorization()
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            if self.locationAuthorized(), self.phase == .needLocationPermission {
                await self.scanHotspots()
            }
        }
    }

    // MARK: - Scan for drone hotspots

    func scanHotspots() async {
        guard let iface = interface else { phase = .failed("No WiFi interface on this Mac"); return }
        guard locationAuthorized() else {
            phase = .needLocationPermission
            loc.requestWhenInUseAuthorization()
            return
        }
        phase = .scanning
        refreshCurrentSSID()
        do {
            let nets = try await Self.scan(iface)
            var map: [String: CWNetwork] = [:]
            var list: [Hotspot] = []
            for n in nets {
                guard let s = n.ssid, s.hasPrefix(kHotspotPrefix) else { continue }
                map[s] = n
                list.append(Hotspot(id: s, rssi: n.rssiValue))
            }
            networksBySSID = map
            hotspots = list.sorted { $0.rssi > $1.rssi }
            phase = .picking
        } catch {
            phase = .failed("WiFi scan failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Full hand-off

    /// Join `hotspotSSID`, push (`targetSSID`,`targetPassword`) to the drone,
    /// let the Mac rejoin its network, then wait for the drone. Calls
    /// `onDrone(host)` with the resolved drone address on success.
    func provision(hotspotSSID: String,
                   targetSSID: String,
                   targetPassword: String,
                   onDrone: @escaping (String) -> Void) async {
        guard let iface = interface else {
            phase = .failed("No WiFi interface on this Mac"); return
        }
        // 1) Join the drone's setup hotspot. CoreWLAN's associate can throw a
        //    transient error ("tmpErr") when the interface is busy switching —
        //    retry a few times, re-fetching a fresh CWNetwork each attempt.
        phase = .joiningHotspot(hotspotSSID)
        var lastErr = ""
        var joined = false
        for attempt in 1...4 {
            var net = networksBySSID[hotspotSSID]
            if net == nil {
                net = (try? await Self.scan(iface))?.first(where: { $0.ssid == hotspotSSID })
            }
            guard let net else { lastErr = "hotspot no longer in range"; break }
            do { try iface.associate(to: net, password: kHotspotPSK); joined = true; break }
            catch {
                lastErr = error.localizedDescription
                if attempt < 4 { try? await Task.sleep(nanoseconds: 2_000_000_000) }
            }
        }
        guard joined else {
            phase = .failed("Couldn't join \(hotspotSSID): \(lastErr)"); return
        }

        // 2) Wait for the drone backend on the hotspot gateway.
        phase = .pushingCreds
        let api = DroneAPI()
        api.host = kHotspotGatewayHost
        guard await Self.waitForBackend(api) else {
            phase = .failed("Drone didn't respond on its hotspot (10.42.0.1)"); return
        }
        // 3) Push the Mac's WiFi and apply it on the drone (no auth required).
        do {
            try await api.saveNetwork(ssid: targetSSID, password: targetPassword)
        } catch {
            phase = .failed("Couldn't set WiFi on the drone: \(error.localizedDescription)"); return
        }
        do {
            try await api.applyNow(ssid: targetSSID)
        } catch where DroneAPI.isLinkDrop(error) {
            // The drone dropped its hotspot to join targetSSID before the reply
            // reached us (older drone software) — that is the expected outcome.
        } catch {
            phase = .failed("Couldn't set WiFi on the drone: \(error.localizedDescription)"); return
        }

        // 4) The drone drops its hotspot to join `targetSSID`; macOS then
        //    auto-rejoins the remembered network. Nudge it if we can see it.
        phase = .waitingForDrone
        if let home = try? await Self.scan(iface).first(where: { $0.ssid == targetSSID }) {
            try? iface.associate(to: home, password: targetPassword)
        }

        // 5) Wait for the drone to reappear on the shared network via Bonjour.
        // Drones with current software advertise their hardware id in the
        // Bonjour TXT record and use it in the hotspot SSID (Bumblebee-<id>),
        // so we can wait for exactly the drone we just provisioned.
        let expectedID = String(hotspotSSID.dropFirst(kHotspotPrefix.count))
        if let host = await Self.waitForDrone(expectedID: expectedID) {
            phase = .done(host)
            onDrone(host)
        } else {
            phase = .failed("Drone didn't come back online — check the WiFi password and retry")
        }
    }

    // MARK: - Helpers

    /// CoreWLAN scan is blocking; run it off the main thread.
    private static func scan(_ iface: CWInterface) async throws -> Set<CWNetwork> {
        try await withCheckedThrowingContinuation { cont in
            DispatchQueue.global(qos: .userInitiated).async {
                do { cont.resume(returning: try iface.scanForNetworks(withSSID: nil)) }
                catch { cont.resume(throwing: error) }
            }
        }
    }

    /// Poll the drone's backend until it answers (or times out).
    private static func waitForBackend(_ api: DroneAPI, timeout: TimeInterval = 25) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if (try? await api.wifiStatus()) != nil { return true }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        return false
    }

    /// Wait for the provisioned drone to appear via Bonjour, returning its IP.
    /// A drone advertising the expected `id` is taken at once; a drone with no
    /// `id` runs older software and is accepted as before. A drone with a
    /// different `id` is only taken if nothing better shows up within
    /// `mismatchGrace` — e.g. a drone updated while on its hotspot, whose
    /// hotspot SSID still carries the old random suffix.
    private static func waitForDrone(expectedID: String, timeout: TimeInterval = 60,
                                     mismatchGrace: TimeInterval = 25) async -> String? {
        await withCheckedContinuation { cont in
            Task { @MainActor in
                var resumed = false
                var fallback: String?
                func finish(_ ip: String?) {
                    guard !resumed else { return }
                    resumed = true
                    cont.resume(returning: ip)
                }
                let browser = BonjourDroneBrowser(
                    onFound: { ip, _, id in
                        if id == nil || id == expectedID { finish(ip) } else if fallback == nil { fallback = ip }
                    },
                    // The drone's own hotspot address is a stale record from
                    // before the switch. Resolve again until the new one shows.
                    accept: { ip in ip != kHotspotGatewayHost })
                browser.start()
                DispatchQueue.main.asyncAfter(deadline: .now() + mismatchGrace) {
                    if let ip = fallback { finish(ip) }
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    browser.stop()                       // keeps browser alive until fired
                    finish(fallback)
                }
            }
        }
    }
}
