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

// The connect screen's decisions, kept apart from SwiftUI so GCSAppTests can
// check them: which drones are remembered and how, when a row is live, stale
// or gone, what is a drone and what is just a device with port 9090 open, and
// what a drone hotspot in the Wi-Fi list means. The Windows app follows the
// same rules (Logic/DiscoveryLogic.cs).

// MARK: - Remembered drones

/// A drone this computer connected to before. Keyed by its hardware id (the
/// last 4 hex digits of its Wi-Fi MAC: Bonjour TXT `id`, /api/wifi/status,
/// hotspot SSID suffix), so a new address after DHCP or a direct connection
/// over its hotspot (10.42.0.1 on every drone) still names the same drone.
/// Drone software without an id is kept by address, marked unverified.
struct KnownDrone: Codable, Identifiable, Equatable {
    var droneID: String          // "" = drone software without an id
    var name: String
    var lastIP: String
    var lastSeen: Date

    var id: String { droneID.isEmpty ? "ip:" + lastIP : droneID }
    var verified: Bool { !droneID.isEmpty }
}

enum KnownFleet {
    /// The fleet after a successful connection to `ip` (`droneID` nil or "" if
    /// the drone has none). An entry with an id replaces an unverified entry of
    /// the same address; most recent first.
    static func upsert(_ list: [KnownDrone], droneID: String?, name: String, ip: String, now: Date) -> [KnownDrone] {
        let id = (droneID ?? "").uppercased()
        var out = list.filter { k in
            if !id.isEmpty { return k.droneID != id && !(k.droneID.isEmpty && k.lastIP == ip) }
            return !(k.droneID.isEmpty && k.lastIP == ip)
        }
        let old = list.first { !id.isEmpty ? $0.droneID == id : ($0.droneID.isEmpty && $0.lastIP == ip) }
        let keepName = old.map { name == ip ? $0.name : name } ?? name
        out.insert(KnownDrone(droneID: id, name: keepName, lastIP: ip, lastSeen: now), at: 0)
        return out
    }

    /// The fleet without one drone ("Forget").
    static func forget(_ list: [KnownDrone], key: String) -> [KnownDrone] {
        list.filter { $0.id != key }
    }

    /// Entries of the 1.1.0 format (host + name, no id) and the old "last host".
    static func migrate(hosts: [(host: String, name: String)], lastHost: String?, now: Date) -> [KnownDrone] {
        var out = hosts.map { KnownDrone(droneID: "", name: $0.name, lastIP: $0.host, lastSeen: .distantPast) }
        if let last = lastHost, !last.isEmpty {
            out.removeAll { $0.lastIP == last }
            let name = hosts.first { $0.host == last }?.name ?? last
            out.insert(KnownDrone(droneID: "", name: name, lastIP: last, lastSeen: now), at: 0)
        }
        return out
    }

    /// Where the last drone is now: the address Bonjour reports for its id, or
    /// its last known address (drones without an id, or not seen yet).
    static func currentIP(of drone: KnownDrone, found: [(ip: String, droneID: String?)]) -> String {
        if drone.verified, let hit = found.first(where: { $0.droneID?.uppercased() == drone.droneID }) {
            return hit.ip
        }
        return drone.lastIP
    }
}

// MARK: - Rows that may be gone

/// A found row is re-probed (TCP :9090) every `period` seconds. One miss greys
/// it out, `goneAfter` misses in a row remove it: a drone switched off leaves
/// the list within about half a minute, a short Wi-Fi blip only greys it.
enum Liveness: Equatable {
    case live, unsure, gone

    static let period: TimeInterval = 10
    static let goneAfter = 3
    /// Bonjour sends "removed" on a short Wi-Fi blip too: wait this long.
    static let lostGrace: TimeInterval = 8

    static func of(misses: Int) -> Liveness {
        misses <= 0 ? .live : (misses < goneAfter ? .unsure : .gone)
    }
}

// MARK: - Drone or just a device with port 9090

/// A host found by the subnet scan has TCP 9090 open: rosbridge on a drone, or
/// anything else (Prometheus, a student's laptop). It counts as a drone only
/// when the drone's own REST API or metrics answer like a drone.
enum DeviceKind: Equatable {
    case drone(droneID: String?, name: String?)
    case unknownDevice

    /// `wifiStatus`: the JSON of GET :8765/api/wifi/status (nil: no answer or
    /// not JSON); `metrics`: the JSON of GET :8888/.
    static func classify(wifiStatus: [String: Any]?, metrics: [String: Any]?) -> DeviceKind {
        if let s = wifiStatus, s["mode"] is String {
            let id = (s["id"] as? String).flatMap { $0.isEmpty ? nil : $0.uppercased() }
            return .drone(droneID: id, name: id.map { "Bumblebee-\($0)" })
        }
        if let m = metrics, m["cpu_pct"] != nil || m["mem_total"] != nil {
            let host = (m["name"] as? String) ?? (m["hostname"] as? String)
            return .drone(droneID: nil, name: (host?.isEmpty ?? true) ? nil : host)
        }
        return .unknownDevice
    }
}

// MARK: - Drone hotspots in the Wi-Fi list

/// A `Bumblebee-XXXX` network nearby. Its suffix is the drone's id: a drone we
/// know that lost its classroom Wi-Fi shows the same hotspot as a new one.
enum HotspotRow: Equatable {
    case hidden                  // the same drone is already listed on the network
    case lostWifi(name: String)  // a known drone working as its own hotspot
    case new

    static func id(of ssid: String) -> String? {
        guard ssid.lowercased().hasPrefix("bumblebee-") else { return nil }
        let rest = String(ssid.dropFirst("bumblebee-".count)).uppercased()
        return rest.isEmpty ? nil : rest
    }

    static func of(ssid: String, known: [KnownDrone], visibleIDs: Set<String>) -> HotspotRow {
        guard let id = id(of: ssid) else { return .new }
        if visibleIDs.contains(id) { return .hidden }
        if let k = known.first(where: { $0.droneID == id }) { return .lostWifi(name: k.name) }
        return .new
    }
}

// MARK: - Typed address

enum ManualAddress {
    /// nil when `text` is an IPv4 address or a host name, else why not.
    static func problem(_ text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.isEmpty { return nil }
        let parts = t.split(separator: ".", omittingEmptySubsequences: false)
        if parts.count == 4, parts.allSatisfy({ !$0.isEmpty && $0.allSatisfy(\.isNumber) }) {
            return parts.allSatisfy({ Int($0).map { (0...255).contains($0) } ?? false })
                ? nil : "Not a valid IP address."
        }
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: ".-"))
        if t.unicodeScalars.allSatisfy({ allowed.contains($0) }), t.first != ".", t.first != "-",
           t.contains(where: \.isLetter) {
            return nil
        }
        return "Type an IP address (e.g. 192.168.1.50) or a name like bumblebee-20ec.local."
    }

    static func noAnswer(_ host: String) -> String {
        "No drone answers at \(host) (port 9090). Check the address, or connect anyway "
            + "if the drone is still starting."
    }
}

/// The id answering at an address is not the drone that was picked.
enum ConnectIdentity {
    static func mismatchText(expectedName: String, foundID: String) -> String {
        "At this address answers Bumblebee-\(foundID), not \(expectedName). "
            + "Its address may have changed: pick it again in the drone list."
    }
}
