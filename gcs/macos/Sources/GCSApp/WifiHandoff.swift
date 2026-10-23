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
        // setup steps, in order
        case joiningHotspot(String)  // 1. talking to the new drone over its own WiFi
        case pushingCreds            // 2. handing it our WiFi name + password
        case waitingForDrone         // 3. drone joins our WiFi, the Mac comes back, we find it
        case diagnosing              // it did not show up: asking the drone why
        case done(String)            // resolved drone host
        case failed(Failure)

        var isBusy: Bool {
            switch self {
            case .scanning, .joiningHotspot, .pushingCreds, .waitingForDrone, .diagnosing: return true
            default: return false
            }
        }

        /// Setting a drone up (a background rescan is not: it blocks no button).
        var isProvisioning: Bool { isBusy && self != .scanning }
    }

    /// A failed setup, explained in user terms.
    struct Failure: Equatable {
        enum Kind: Equatable {
            case wrongPassword, notFound, noAddress, isolated, droneSilent, other
        }
        let kind: Kind
        let title: String
        let detail: String
        /// Offer "connect directly to the drone" (no shared WiFi needed).
        var offerDirect: Bool { kind != .wrongPassword }
    }

    struct Hotspot: Identifiable, Equatable {
        let id: String       // ssid
        var ssid: String { id }
        var rssi: Int
    }

    @Published private(set) var phase: Phase = .idle
    @Published private(set) var hotspots: [Hotspot] = []
    /// The Mac's current WiFi SSID. Can be a drone's own hotspot: macOS
    /// remembers the ones it joined and may hop onto them by itself.
    @Published private(set) var currentSSID: String = ""
    /// Last ordinary (non-drone) network this Mac was on.
    @Published private(set) var rememberedHome: String =
        UserDefaults.standard.string(forKey: WifiHandoff.homeSSIDKey) ?? ""
    private static let homeSSIDKey = "lastHomeSSID"

    /// True while the Mac sits on a drone's own WiFi.
    var onDroneHotspot: Bool { currentSSID.hasPrefix(kHotspotPrefix) }

    /// The network we hand to the drone: the Mac's WiFi, never a drone
    /// hotspot. On a hotspot it is the network the Mac was on before (and
    /// returns to after the hand-off); empty when there is none to offer.
    var homeSSID: String { onDroneHotspot ? rememberedHome : currentSSID }

    private let loc = CLLocationManager()
    private var networksBySSID: [String: CWNetwork] = [:]

    override init() {
        super.init()
        loc.delegate = self
    }

    private var interface: CWInterface? { CWWiFiClient.shared().interface() }

    func reset() { phase = .idle }

    func refreshCurrentSSID() {
        let ssid = interface?.ssid() ?? ""
        if ssid != currentSSID { currentSSID = ssid }
        if !ssid.isEmpty, !ssid.hasPrefix(kHotspotPrefix), ssid != rememberedHome {
            rememberedHome = ssid
            UserDefaults.standard.set(ssid, forKey: Self.homeSSIDKey)
        }
    }

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
        // A rescan must never overwrite a setup that is running.
        guard !phase.isProvisioning else { return }
        guard let iface = interface else {
            phase = .failed(Failure(kind: .other, title: "This Mac has no WiFi", detail: "Turn WiFi on and try again."))
            return
        }
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
            // "Add" may have been pressed while we scanned: keep that setup.
            if phase == .scanning { phase = .picking }
        } catch {
            if phase == .scanning {
                phase = .failed(Failure(kind: .other, title: "WiFi scan failed",
                                        detail: error.localizedDescription))
            }
        }
    }

    // MARK: - Full hand-off

    /// Set up a new drone: join its own WiFi (`hotspotSSID`), hand it
    /// `targetSSID`/`targetPassword`, bring the Mac back to `targetSSID` and
    /// find exactly that drone there. If it does not show up, ask the drone why
    /// (it re-raises its WiFi ~45 s after a failed join) and explain it.
    func provision(hotspotSSID: String,
                   targetSSID: String,
                   targetPassword: String,
                   onDrone: @escaping (String) -> Void) async {
        guard let iface = interface else {
            phase = .failed(Failure(kind: .other, title: "This Mac has no WiFi", detail: "Turn WiFi on and try again."))
            return
        }
        // 1) Join the drone's own WiFi.
        phase = .joiningHotspot(hotspotSSID)
        if let err = await joinHotspot(hotspotSSID, iface) {
            phase = .failed(Failure(kind: .droneSilent, title: "Couldn't reach \(hotspotSSID)",
                                    detail: "\(err). Make sure the drone is on and glowing blue, then try again."))
            await returnHome(iface, targetSSID, targetPassword)
            return
        }

        // 2) Talk to it and hand over our WiFi.
        phase = .pushingCreds
        let api = DroneAPI()
        api.host = kHotspotGatewayHost
        guard let status = await Self.waitForBackend(api) else {
            phase = .failed(Failure(kind: .droneSilent, title: "The drone didn't answer",
                                    detail: "The Mac joined \(hotspotSSID) but the drone's software didn't respond. Wait a minute after power-on and try again."))
            await returnHome(iface, targetSSID, targetPassword)
            return
        }
        // The drone we are talking to tells us its id, so we can recognise
        // exactly this drone once it is on the shared network.
        let expectedID = status.id
        do {
            try await api.saveNetwork(ssid: targetSSID, password: targetPassword)
            try await api.applyNow(ssid: targetSSID)
        } catch where DroneAPI.isLinkDrop(error) {
            // Older drone software switches WiFi before replying — expected.
        } catch {
            phase = .failed(Failure(kind: .other, title: "Couldn't send the WiFi settings",
                                    detail: error.localizedDescription))
            await returnHome(iface, targetSSID, targetPassword)
            return
        }

        // 3) The drone joins our WiFi; bring the Mac back and look for it.
        phase = .waitingForDrone
        await returnHome(iface, targetSSID, targetPassword)
        if let host = await Self.waitForDrone(expectedID: expectedID) {
            phase = .done(host)
            onDrone(host)
            return
        }

        // 4) Not there: find out why.
        phase = .diagnosing
        phase = .failed(await diagnose(iface: iface, hotspotSSID: hotspotSSID,
                                       targetSSID: targetSSID, targetPassword: targetPassword))
    }

    /// Work with a drone over its own WiFi (no shared network; the Mac has no
    /// internet meanwhile). Returns the drone's address on success.
    func connectDirect(hotspotSSID: String, onDrone: @escaping (String) -> Void) async {
        guard let iface = interface else { return }
        phase = .joiningHotspot(hotspotSSID)
        if let err = await joinHotspot(hotspotSSID, iface) {
            phase = .failed(Failure(kind: .droneSilent, title: "Couldn't reach \(hotspotSSID)", detail: err))
            return
        }
        let api = DroneAPI()
        api.host = kHotspotGatewayHost
        guard await Self.waitForBackend(api) != nil else {
            phase = .failed(Failure(kind: .droneSilent, title: "The drone didn't answer",
                                    detail: "Wait a minute after power-on and try again."))
            return
        }
        phase = .done(kHotspotGatewayHost)
        onDrone(kHotspotGatewayHost)
    }

    /// After a failed setup the drone raises its WiFi again; read the reason it
    /// recorded, then put the Mac back on `targetSSID`.
    private func diagnose(iface: CWInterface, hotspotSSID: String,
                          targetSSID: String, targetPassword: String) async -> Failure {
        var net: CWNetwork?
        let deadline = Date().addingTimeInterval(75)
        while Date() < deadline {
            net = (try? await Self.scan(iface))?.first(where: { $0.ssid == hotspotSSID })
            if net != nil { break }
            try? await Task.sleep(nanoseconds: 3_000_000_000)
        }
        guard let net else {
            // Its WiFi did not come back, so the drone is most likely on
            // targetSSID — but this Mac cannot reach it there.
            return Failure(kind: .isolated,
                           title: "The drone joined \(targetSSID), but this Mac can't see it",
                           detail: "Some networks keep devices apart (guest WiFi, \"AP isolation\"). Use another network — for example a phone hotspot — or connect directly to the drone.")
        }
        var reason: DroneAPI.JoinError?
        if (try? iface.associate(to: net, password: kHotspotPSK)) != nil {
            let api = DroneAPI()
            api.host = kHotspotGatewayHost
            reason = await Self.waitForBackend(api, timeout: 20)?.lastError
        }
        await returnHome(iface, targetSSID, targetPassword)

        switch reason?.reason {
        case "wrong_password":
            return Failure(kind: .wrongPassword, title: "Wrong password for \(targetSSID)",
                           detail: "The drone couldn't log in to \(targetSSID). Check the password and try again.")
        case "not_found":
            return Failure(kind: .notFound, title: "The drone can't see \(targetSSID)",
                           detail: "Move the drone closer to the router. If \(targetSSID) is a 5 GHz-only network, use one that also has 2.4 GHz.")
        case "no_ip":
            return Failure(kind: .noAddress, title: "\(targetSSID) didn't give the drone an address",
                           detail: "The router didn't respond (DHCP). Restart the router or use another network.")
        default:
            return Failure(kind: .other, title: "The drone couldn't join \(targetSSID)",
                           detail: reason.map { $0.message.isEmpty ? "Try again." : $0.message } ?? "Try again, or connect directly to the drone.")
        }
    }

    /// Join the drone's setup WiFi; nil on success, else a short error.
    private func joinHotspot(_ ssid: String, _ iface: CWInterface) async -> String? {
        // CoreWLAN's associate can throw a transient error ("tmpErr") while the
        // interface is busy switching — retry with a fresh CWNetwork.
        var lastErr = "its WiFi is not in range"
        for attempt in 1...4 {
            var net = networksBySSID[ssid]
            if net == nil || attempt > 1 {
                net = (try? await Self.scan(iface))?.first(where: { $0.ssid == ssid })
            }
            guard let net else { lastErr = "its WiFi is not in range"; break }
            do { try iface.associate(to: net, password: kHotspotPSK); return nil }
            catch {
                lastErr = error.localizedDescription
                if attempt < 4 { try? await Task.sleep(nanoseconds: 2_000_000_000) }
            }
        }
        return lastErr
    }

    /// Put the Mac back on the network it came from (macOS would also do it on
    /// its own, but slower).
    private func returnHome(_ iface: CWInterface, _ ssid: String, _ password: String) async {
        guard !ssid.isEmpty, iface.ssid() != ssid else { return }
        if let home = (try? await Self.scan(iface))?.first(where: { $0.ssid == ssid }) {
            try? iface.associate(to: home, password: password)
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
    fileprivate static func waitForBackend(_ api: DroneAPI, timeout: TimeInterval = 25) async -> DroneAPI.WifiStatus? {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if let status = try? await api.wifiStatus() { return status }
            try? await Task.sleep(nanoseconds: 1_000_000_000)
        }
        return nil
    }

    /// Wait for the provisioned (or re-networked) drone to appear via Bonjour,
    /// returning its IP. With an id (current drone software) only that exact
    /// drone is accepted, never another team's drone. Without one (older drone
    /// software) see DroneMatch: drones already on the network do not count.
    static func waitForDrone(expectedID: String?, timeout: TimeInterval = 60) async -> String? {
        await withCheckedContinuation { cont in
            Task { @MainActor in
                var resumed = false
                func finish(_ ip: String?) {
                    guard !resumed else { return }
                    resumed = true
                    cont.resume(returning: ip)
                }
                let started = Date()
                let browser = BonjourDroneBrowser(
                    onFound: { ip, _, id in
                        if DroneMatch.accepts(expectedID: expectedID, foundID: id,
                                              secondsSinceStart: Date().timeIntervalSince(started)) {
                            finish(ip)
                        }
                    },
                    // The drone's own hotspot address is a stale record from
                    // before the switch. Resolve again until the new one shows.
                    accept: { ip in ip != kHotspotGatewayHost })
                browser.start()
                DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                    browser.stop()                       // keeps browser alive until fired
                    finish(nil)
                }
            }
        }
    }
}
