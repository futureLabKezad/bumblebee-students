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

/// "Copy diagnostics": one plain-text report a teacher can paste into a
/// message when something goes wrong in class. Built from values only, so
/// GCSAppTests checks it; it never holds a Wi-Fi password. The Windows app
/// writes the same report (Logic/Diagnostics.cs).
struct DiagnosticsInput {
    struct FoundDrone { var name: String; var ip: String; var droneID: String?; var live: Bool }
    struct Remembered { var name: String; var droneID: String; var lastIP: String }

    var now: Date
    var app: String                  // "GCS 1.1.0 (build 2)"
    var os: String                   // "macOS 26.0 (arm64)"
    var connected: Bool
    var droneHost: String
    var droneName: String
    var droneID: String?
    var droneSoftware: String?       // first line of /etc/bumblebee_version, via /api/info
    var link: String                 // "OK", "Telemetry frozen", ...
    var armed: String                // "DISARMED", "UNKNOWN", ...
    var mode: String
    var control: String
    var battery: String
    var computerWifi: String         // "" = unknown (no Location permission)
    var onDroneHotspot: Bool
    var found: [FoundDrone]
    var unknownDevices: Int
    var hotspots: [String]
    var remembered: [Remembered]
    var messages: [String]           // newest first, already "HH:mm:ss text"
    var lastCrash: String?
}

enum Diagnostics {
    static let maxMessages = 30

    static func report(_ d: DiagnosticsInput) -> String {
        var out: [String] = []
        out.append("Bumblebee GCS diagnostics — \(local.string(from: d.now)) (UTC \(utc.string(from: d.now)))")
        out.append("App: \(d.app) · \(d.os)")
        out.append("")
        if d.connected {
            var drone = "\(d.droneName) · \(d.droneHost) · id \(d.droneID ?? "unknown")"
            drone += " · software \(d.droneSoftware ?? "unknown (before 1.0.2)")"
            out.append("Drone: \(drone)")
            out.append("Link: \(d.link) · State: \(d.armed) · Mode: \(d.mode) · Control: \(d.control)")
            out.append("Battery: \(d.battery)")
        } else {
            out.append("Drone: not connected")
        }
        out.append("This computer's Wi-Fi: \(d.computerWifi.isEmpty ? "unknown" : d.computerWifi)"
                   + (d.onDroneHotspot ? " (a drone's own hotspot)" : ""))
        out.append("")
        out.append("Drones found (\(d.found.count)):")
        for f in d.found {
            out.append("  \(f.name) · \(f.ip) · id \(f.droneID ?? "unknown")\(f.live ? "" : " · not answering")")
        }
        if d.unknownDevices > 0 { out.append("  + \(d.unknownDevices) other device(s) with port 9090 open") }
        out.append("Drone hotspots nearby: \(d.hotspots.isEmpty ? "none" : d.hotspots.joined(separator: ", "))")
        out.append("Remembered drones (\(d.remembered.count)):")
        for r in d.remembered {
            out.append("  \(r.name) · id \(r.droneID.isEmpty ? "unknown" : r.droneID) · last \(r.lastIP)")
        }
        out.append("")
        out.append("Last messages (newest first):")
        let msgs = d.messages.prefix(maxMessages)
        if msgs.isEmpty { out.append("  none") }
        for m in msgs { out.append("  \(m)") }
        out.append("")
        out.append("Last crash: \(d.lastCrash ?? "none recorded")")
        return out.joined(separator: "\n")
    }

    private static let local: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        return f
    }()
    private static let utc: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()
}
