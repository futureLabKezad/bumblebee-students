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

// The Settings screen's decisions, kept apart from SwiftUI so GCSAppTests can
// check them: what an error reply means, whether a password can be sent, which
// networks must not be touched, whether we still talk to the same drone and
// what to do after "Apply Now". The Windows app follows the same rules
// (Logic/SettingsLogic.cs).

// MARK: - Error replies

/// Plain words for an error reply of the drone. Drones from 1.0.2 send a
/// stable `code` with each error; older ones only `error`, shown as it is.
enum DroneErrorText {
    static func text(code: String?, error: String?, status: Int) -> String {
        switch code {
        case "armed":
            return "Refused: the drone is ARMED. Disarm it first."
        case "fc_unknown":
            return "Refused: the flight controller is not answering, so the drone counts as armed. "
                + "Check that the flight controller is powered and connected."
        case "protected_network":
            return "That is a drone's own setup hotspot: it cannot be saved, joined or removed here."
        case "bad_password_length":
            return PasswordCheck.Result.length.text ?? ""
        case "unknown_network":
            return "The drone has no saved network with that name."
        case "nmcli_timeout":
            return "The drone's network manager did not answer in time. Try again."
        case "nmcli_failed":
            return "The drone's network manager reported an error (details in the drone's log)."
        case "led_unavailable":
            return "The drone's LED driver is not running."
        case "drone_unavailable":
            return "The drone's flight library did not load (see the drone's log)."
        case "tts_unavailable":
            return "Speech is not installed on this drone."
        default:
            if let e = error, !e.isEmpty { return e }
            return "HTTP \(status)"
        }
    }

    /// The request never got an answer (drone off, out of range, other network).
    static func noAnswer(_ detail: String) -> String { "No answer from the drone (\(detail))." }
}

/// Why the drone's last requested Wi-Fi join failed (`last_error.reason`).
enum JoinReasonText {
    static func text(reason: String, ssid: String) -> String {
        switch reason {
        case "wrong_password": return "wrong password for \(ssid)"
        case "not_found": return "the drone can't see \(ssid)"
        case "no_ip": return "\(ssid) didn't give the drone an address"
        case "timeout": return "joining \(ssid) took too long"
        case "armed", "fc_unknown": return "not switched to \(ssid): the drone counted as armed"
        default: return "the drone couldn't join \(ssid)"
        }
    }

    /// Banner for a recorded failure, or nil when there is none or it is older
    /// than `maxAge` (the drone keeps it until the next Apply Now). Drones
    /// before 1.0.1 send no time: their failure is shown without one.
    static func banner(ssid: String, reason: String, time: Date?, now: Date,
                       maxAge: TimeInterval = 30 * 60) -> String? {
        if let t = time, now.timeIntervalSince(t) > maxAge { return nil }
        let what = text(reason: reason, ssid: ssid)
        guard let t = time else { return "Last Wi-Fi change failed: \(what)." }
        return "Last Wi-Fi change at \(Self.clock.string(from: t)) failed: \(what)."
    }

    private static let clock: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f
    }()
}

// MARK: - Networks

enum WifiNames {
    static let hotspotProfile = "bumblebee-hotspot"

    /// A drone's own setup hotspot (any drone's, by profile name or SSID) or a
    /// drone-side pending profile: never offered, saved, joined or removed.
    static func isProtected(_ name: String) -> Bool {
        let n = name.trimmingCharacters(in: .whitespaces).lowercased()
        return n == hotspotProfile || n.hasPrefix("bumblebee-") || n.hasSuffix(".bb-pending")
    }

    /// nmcli reports an open network's security as "" or "--".
    static func isSecured(_ security: String) -> Bool {
        let s = security.trimmingCharacters(in: .whitespaces)
        return !s.isEmpty && s != "--"
    }

    /// Whether `ssid` (a scan SSID) and `profile` (a NetworkManager profile
    /// name, as status.ssid reports it) are the same network. Profiles from the
    /// image's netplan are named "netplan-wlan0-<SSID>".
    static func same(ssid: String, profile: String) -> Bool {
        guard !ssid.isEmpty, !profile.isEmpty else { return false }
        return profile == ssid || profile == "netplan-wlan0-" + ssid
    }
}

/// What may be sent as a Wi-Fi password. The drone strips spaces at both ends,
/// so such a password would silently change: refused here with a reason.
enum PasswordCheck {
    enum Result: Equatable {
        case ok, missing, length, spaces

        var text: String? {
            switch self {
            case .ok: return nil
            case .missing: return "This network needs a password."
            case .length: return "A Wi-Fi password has 8 to 63 characters (or exactly 64 hex digits)."
            case .spaces: return "The password starts or ends with a space; the drone cannot use such a password."
            }
        }
    }

    /// `needsPassword`: the network is protected and not saved on the drone yet
    /// (a saved one keeps its password when the field is left empty).
    static func check(_ password: String, needsPassword: Bool) -> Result {
        if password.isEmpty { return needsPassword ? .missing : .ok }
        if password.first == " " || password.last == " " { return .spaces }
        let size = password.utf8.count
        if size == 64 { return password.allSatisfy(\.isHexDigit) ? .ok : .length }
        return (8...63).contains(size) ? .ok : .length
    }

    /// A network not in the scan and not saved is taken as protected.
    static func needsPassword(saved: Bool, secured: Bool?) -> Bool {
        !saved && (secured ?? true)
    }
}

// MARK: - Same drone

/// Settings changes the drone at the address it connected to. The id it
/// reports there must still be the id seen at the start: a drone's own hotspot
/// is 10.42.0.1 on every drone, and DHCP can hand an address to another drone.
enum DroneIdentity: Equatable {
    case same
    case unknown                 // older drone software reports no id
    case different(String)       // the id answering now

    static func check(expected: String?, reported: String?) -> DroneIdentity {
        guard let e = expected?.uppercased(), !e.isEmpty,
              let r = reported?.uppercased(), !r.isEmpty else { return .unknown }
        return e == r ? .same : .different(r)
    }

    var blocks: Bool { if case .different = self { return true } else { return false } }

    static func differentText(now: String, expected: String) -> String {
        "This address now answers as Bumblebee-\(now), not Bumblebee-\(expected). "
            + "Nothing was changed. Reconnect from the drone list."
    }
}

// MARK: - After Apply Now

/// The drone leaves the network it is on for `target`. Where to look for it.
enum ApplyFollowUp: Equatable {
    case waitHere                // this computer is on target (or cannot tell): find the drone by its id
    case otherNetwork(String)    // this computer is on another network
    case noID                    // older drone software: it cannot be recognised afterwards

    static func decide(target: String, computerSSID: String, droneID: String?) -> ApplyFollowUp {
        guard let id = droneID, !id.isEmpty else { return .noID }
        if computerSSID.isEmpty || WifiNames.same(ssid: computerSSID, profile: target) { return .waitHere }
        return .otherNetwork(computerSSID)
    }

    func text(drone: String, target: String) -> String {
        switch self {
        case .waitHere:
            return "\(drone) is switching to \(target)… looking for it there."
        case .otherNetwork(let mine):
            return "\(drone) is switching to \(target). This computer is on \(mine): "
                + "connect it to \(target) and pick the drone in the list."
        case .noID:
            return "\(drone) is switching to \(target). Its software is too old to be found "
                + "automatically: pick it in the drone list once it is there."
        }
    }

    static func notFoundText(drone: String, id: String, target: String) -> String {
        "\(drone) did not show up on \(target). If the password was wrong it goes back to its "
            + "previous network within about 2 minutes; if it cannot, it shows its own hotspot "
            + "Bumblebee-\(id) in the drone list."
    }
}

// MARK: - Finding the drone again

/// Whether a drone Bonjour reports is the one we wait for. With an id only
/// that id counts. Without one (drone software before 1.0.1) a drone without
/// an id counts only after `settle` seconds: the browser first reports every
/// drone already on the network, and taking the first of those connected to
/// another team's drone.
enum DroneMatch {
    static let settle: TimeInterval = 5

    static func accepts(expectedID: String?, foundID: String?, secondsSinceStart: TimeInterval) -> Bool {
        if let e = expectedID, !e.isEmpty { return foundID?.uppercased() == e.uppercased() }
        return (foundID ?? "").isEmpty && secondsSinceStart >= settle
    }
}

// MARK: - The password typed in "Add drone"

/// What happens to the remembered Wi-Fi password once a setup ended. It is
/// saved only when it worked (or the drone got far enough to show it is
/// right), and forgotten after "wrong password": a typo must not be offered
/// again next time.
enum PasswordMemory: Equatable {
    case save, forget, keep

    /// `failure` nil: the setup succeeded.
    static func after(failure: WifiHandoff.Failure.Kind?) -> PasswordMemory {
        guard let kind = failure else { return .save }
        switch kind {
        case .wrongPassword: return .forget
        case .isolated, .notFound, .noAddress: return .save
        case .droneSilent, .other: return .keep
        }
    }
}
