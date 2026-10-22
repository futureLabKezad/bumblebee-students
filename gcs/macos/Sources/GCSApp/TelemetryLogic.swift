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

// The dashboard's decisions, kept apart from SwiftUI so GCSAppTests can check
// them: is the link alive, is a value fresh, is the drone armed, who flies it,
// what the battery line says. The Windows app follows the same rules.

// MARK: - Freshness

/// How long each source may stay quiet before its panel greys out.
enum Freshness {
    static let state: TimeInterval = 3.0     // /mavros/state, as drone.py get_fcu_status
    static let pose: TimeInterval = 2.0
    static let velocity: TimeInterval = 2.0
    static let imu: TimeInterval = 2.0
    static let battery: TimeInterval = 5.0   // throttled to 1 Hz
    static let metrics: TimeInterval = 6.0   // polled every 2 s
    static let video: TimeInterval = 3.0

    enum Status: Equatable {
        case never                  // nothing arrived yet: show "—", never 0
        case fresh
        case stale(seconds: Int)

        var isFresh: Bool { self == .fresh }

        /// Caption for a greyed panel; nil while the data is fresh.
        var note: String? {
            switch self {
            case .fresh: return nil
            case .never: return "no data yet"
            case .stale(let s): return "no data \(s) s"
            }
        }
    }

    static func status(_ lastAt: Date?, limit: TimeInterval, now: Date) -> Status {
        guard let at = lastAt else { return .never }
        let age = now.timeIntervalSince(at)
        return age <= limit ? .fresh : .stale(seconds: Int(age))
    }
}

// MARK: - Link state

/// What the Link tile says. Only the socket and /mavros/state decide it; the
/// other topics just grey their own panels (pose may never come on a table).
enum LinkState: Equatable {
    case noDrone            // no open rosbridge socket
    case fcNotConnected     // fresh State says connected == false
    case telemetryFrozen    // socket open, no State for more than 3 s
    case ok                 // fresh State, connected == true

    var text: String {
        switch self {
        case .noDrone: return "No drone"
        case .fcNotConnected: return "FC not connected"
        case .telemetryFrozen: return "Telemetry frozen"
        case .ok: return "OK"
        }
    }

    /// `socketOpenedAt` is nil while no socket is open. A State older than the
    /// socket came over the previous one and does not count.
    static func evaluate(socketOpenedAt: Date?, stateAt: Date?, stateConnected: Bool?, now: Date) -> LinkState {
        guard let opened = socketOpenedAt else { return .noDrone }
        if let at = stateAt, at >= opened, now.timeIntervalSince(at) <= Freshness.state {
            return stateConnected == true ? .ok : .fcNotConnected
        }
        // No fresh State on this socket: frozen once 3 s have passed since the
        // last State or, if none came yet, since the socket opened. Before that
        // the first State is still on its way (State comes about once a second).
        var since = opened
        if let at = stateAt, at > opened { since = at }
        return now.timeIntervalSince(since) > Freshness.state ? .telemetryFrozen : .noDrone
    }
}

// MARK: - Armed (true / false / unknown)

/// The State tile. DISARMED only from a fresh, connected State: an old or
/// missing State is UNKNOWN, and if the drone was last seen armed it reads
/// "ARMED? link lost".
enum ArmedDisplay: Equatable {
    case armed, disarmed, unknown, armedLinkLost

    /// The armed flag the screen may trust: only over an OK link.
    static func known(link: LinkState, reported: Bool?) -> Bool? {
        link == .ok ? reported : nil
    }

    init(armed: Bool?, lastKnownArmed: Bool?) {
        switch armed {
        case true?: self = .armed
        case false?: self = .disarmed
        case nil: self = lastKnownArmed == true ? .armedLinkLost : .unknown
        }
    }

    var text: String {
        switch self {
        case .armed: return "ARMED"
        case .disarmed: return "DISARMED"
        case .unknown: return "UNKNOWN"
        case .armedLinkLost: return "ARMED? link lost"
        }
    }

    var caption: String? { self == .unknown ? "waiting for FC data" : nil }
}

// MARK: - Mode names

/// PX4 mode with a short plain explanation under the Mode tile.
enum ModeText {
    static let pilotModes: Set<String> = ["POSCTL", "ALTCTL", "STABILIZED", "ACRO", "MANUAL"]

    /// nil before any State and for names we do not know (shown as they are).
    static func explain(_ mode: String?) -> String? {
        guard let raw = mode else { return nil }
        let m = raw.trimmingCharacters(in: .whitespaces).uppercased()
        switch m {
        case "": return "unknown"
        case "OFFBOARD": return "program in control"
        case "POSCTL": return "pilot, position hold"
        case "ALTCTL": return "pilot, altitude hold"
        case "STABILIZED", "ACRO", "MANUAL": return "pilot, manual"
        case "AUTO.LAND": return "PX4 landing"
        case "AUTO.LOITER": return "PX4 holding"
        case "AUTO.RTL": return "PX4 returning"
        case "AUTO.TAKEOFF": return "PX4 taking off"
        default: return m.hasPrefix("AUTO.") ? "PX4 automatic" : nil
        }
    }
}

// MARK: - Who is in control (display only)

enum ControlOwner: Equatable {
    case program, pilot, px4, disarmed, unknown

    init(armed: Bool?, mode: String?) {
        guard let armed = armed else { self = .unknown; return }
        guard armed else { self = .disarmed; return }
        let m = (mode ?? "").trimmingCharacters(in: .whitespaces).uppercased()
        if m == "OFFBOARD" {
            self = .program
        } else if ModeText.pilotModes.contains(m) {
            self = .pilot
        } else if m.hasPrefix("AUTO.") {
            self = .px4
        } else {
            self = .unknown
        }
    }

    var text: String {
        switch self {
        case .program: return "Program"
        case .pilot: return "Pilot"
        case .px4: return "PX4"
        case .disarmed: return "Disarmed"
        case .unknown: return "Unknown"
        }
    }
}

/// Turns changes of who is in control into one visible event line ("Pilot
/// took control", "PX4 is landing"). The first look after connecting and the
/// gaps while the link is down are not events.
struct ControlEvents {
    private var lastOwner: ControlOwner?
    private var lastMode = ""

    mutating func reset() { lastOwner = nil; lastMode = "" }

    mutating func update(owner: ControlOwner, mode: String) -> String? {
        guard owner != .unknown else { return nil }
        let prevOwner = lastOwner, prevMode = lastMode
        lastOwner = owner
        lastMode = mode
        guard let prev = prevOwner else { return nil }
        if owner == prev {
            // Same hands on the drone: only PX4 changing its own manoeuvre is news.
            guard owner == .px4, mode != prevMode else { return nil }
        }
        return Self.text(owner: owner, mode: mode)
    }

    static func text(owner: ControlOwner, mode: String) -> String? {
        switch owner {
        case .program: return "Program took control"
        case .pilot: return "Pilot took control"
        case .disarmed: return "Disarmed"
        case .unknown: return nil
        case .px4:
            switch mode.uppercased() {
            case "AUTO.LAND": return "PX4 is landing"
            case "AUTO.RTL": return "PX4 is returning"
            case "AUTO.LOITER": return "PX4 is holding"
            case "AUTO.TAKEOFF": return "PX4 is taking off"
            default: return "PX4 took control"
            }
        }
    }
}

// MARK: - Flight-controller-lost alarm

/// The drone cannot beep when MAVROS loses the FC (the buzzer sits on the FC),
/// so the laptop does: once, when the link goes from OK to "FC not connected"
/// or "Telemetry frozen" while the drone was last seen armed. The banner stays
/// until the link is OK again.
struct FcLostAlarm {
    static let text = "Flight controller link lost"
    private(set) var active = false
    private var previous: LinkState = .noDrone

    mutating func reset() { active = false; previous = .noDrone }

    /// Returns true exactly when the alert sound should play.
    mutating func update(link: LinkState, lastKnownArmed: Bool?) -> Bool {
        defer { previous = link }
        if link == .ok { active = false; return false }
        guard previous == .ok, link == .fcNotConnected || link == .telemetryFrozen,
              lastKnownArmed == true else { return false }
        active = true
        return true
    }
}

// MARK: - Battery

/// One /mavros/battery message. PX4 without a power module (BAT1_SOURCE=-1)
/// sends the 65.535 V sentinel (or NaN / 0) and remaining -1: that is "not
/// measured", which must not look like a full battery.
enum BatteryReading: Equatable {
    case notMeasured
    case measured(voltage: Double, percent: Double?)

    static func classify(voltage: Double?, percentage: Double?) -> BatteryReading {
        guard let v = voltage, v.isFinite, v > 0, v < 65.5 else { return .notMeasured }
        if let p = percentage, p < 0 { return .notMeasured }
        var pct: Double? = nil
        if let p = percentage, p.isFinite, p <= 1 { pct = p * 100 }
        return .measured(voltage: v, percent: pct)
    }
}

/// Battery tile and bar text for a reading (nil = nothing arrived yet).
struct BatteryDisplay: Equatable {
    enum Level: Equatable { case neutral, good, low, critical }

    static let neutralIcon = "minus.plus.batteryblock"

    let tileValue: String
    let tileCaption: String?
    let barText: String
    let barPercent: Double
    let icon: String
    let level: Level

    init(_ reading: BatteryReading?) {
        switch reading {
        case nil:
            tileValue = "—"; tileCaption = nil; barText = "—"; barPercent = 0
            icon = Self.neutralIcon; level = .neutral
        case .notMeasured?:
            tileValue = "Not measured"; tileCaption = "check with a tester"
            barText = "Not measured — check with a tester"; barPercent = 0
            icon = Self.neutralIcon; level = .neutral
        case .measured(let v, let p?)?:
            tileValue = String(format: "%.0f%%", p); tileCaption = nil
            barText = String(format: "%.2f V · %.0f%%", v, p); barPercent = p
            icon = Self.icon(percent: p)
            level = p > 55 ? .good : (p > 25 ? .low : .critical)
        case .measured(let v, nil)?:
            tileValue = String(format: "%.2f V", v); tileCaption = nil
            barText = String(format: "%.2f V", v); barPercent = 0
            icon = Self.neutralIcon; level = .neutral
        }
    }

    private static func icon(percent p: Double) -> String {
        if p >= 88 { return "battery.100percent" }
        if p >= 63 { return "battery.75percent" }
        if p >= 38 { return "battery.50percent" }
        if p >= 13 { return "battery.25percent" }
        return "battery.0percent"
    }
}

/// "LOW BATTERY" once below 15 %, armed again only above 20 %, so a value
/// hovering around the threshold does not flood the log.
struct LowBatteryLatch {
    static let low = 15.0
    static let rearm = 20.0
    private(set) var active = false

    mutating func reset() { active = false }

    /// Returns true when the warning should be logged now.
    mutating func update(percent: Double) -> Bool {
        if !active, percent < Self.low { active = true; return true }
        if active, percent > Self.rearm { active = false }
        return false
    }
}

// MARK: - Charts

enum ChartScale {
    /// Vertical range of a chart. Without fixed bounds the range is at least
    /// `minSpan` wide and centred on the data, so 1–2 cm of altitude noise
    /// stays a flat line instead of filling the chart.
    static func range(_ data: [Double], fixedMin: Double? = nil, fixedMax: Double? = nil,
                      minSpan: Double = 1.0) -> (lo: Double, hi: Double) {
        var lo = fixedMin ?? data.min() ?? 0
        var hi = fixedMax ?? data.max() ?? 1
        let span = max(minSpan, 1e-6)
        if hi - lo < span {
            switch (fixedMin, fixedMax) {
            case (nil, nil):
                let mid = (lo + hi) / 2
                lo = mid - span / 2
                hi = mid + span / 2
            case (nil, _?):
                lo = hi - span
            default:
                hi = lo + span
            }
        }
        return (lo, hi)
    }
}

// MARK: - Attitude

enum Horizon {
    /// Vertical shift of the horizon in screen points (y grows downward).
    /// Pitch is in the ROS convention (+ = nose down, REP-103, like
    /// get_telemetry()), so a positive pitch moves the horizon up: more ground.
    static func offset(pitchDeg: Double, pxPerDeg: Double) -> Double {
        -pitchDeg * pxPerDeg
    }
}

/// Where roll/pitch/yaw come from: the IMU orientation when MAVROS fills it
/// (it does not depend on a position estimate), else the pose.
struct AttitudeSource {
    private(set) var lastIMUAt: Date?

    mutating func reset() { lastIMUAt = nil }

    /// orientation_covariance[0] == -1 means "no orientation"; a quaternion
    /// far from unit length is not one either.
    static func imuOrientationValid(x: Double, y: Double, z: Double, w: Double, covariance0: Double?) -> Bool {
        if let c = covariance0, c == -1 { return false }
        let n = (x * x + y * y + z * z + w * w).squareRoot()
        return abs(n - 1) <= 0.05
    }

    mutating func fromIMU(x: Double, y: Double, z: Double, w: Double, covariance0: Double?, now: Date) -> Euler? {
        guard Self.imuOrientationValid(x: x, y: y, z: z, w: w, covariance0: covariance0) else { return nil }
        lastIMUAt = now
        return quatToEuler(x, y, z, w)
    }

    /// nil while a valid IMU orientation is fresh.
    func fromPose(x: Double, y: Double, z: Double, w: Double, now: Date) -> Euler? {
        if let at = lastIMUAt, now.timeIntervalSince(at) <= Freshness.imu { return nil }
        return quatToEuler(x, y, z, w)
    }
}

// MARK: - rosbridge keep-alive

/// A WebSocket ping every 2 s; a ping without a pong for 4 s means the link
/// died silently (drone switched off, out of Wi-Fi range).
struct PingWatchdog {
    static let interval: TimeInterval = 2.0
    static let timeout: TimeInterval = 4.0
    private var pending: [Int: Date] = [:]
    private var lastID = 0

    mutating func reset() { pending.removeAll() }

    mutating func sent(now: Date) -> Int {
        lastID += 1
        pending[lastID] = now
        return lastID
    }

    /// Pongs come in order, so one answers every earlier ping too.
    mutating func answered(_ id: Int) {
        pending = pending.filter { $0.key > id }
    }

    func timedOut(now: Date) -> Bool {
        pending.values.contains { now.timeIntervalSince($0) > Self.timeout }
    }
}

// MARK: - Switching drones

enum ConnectKind: Equatable {
    case newDrone       // clear trail, charts, log, values
    case sameDrone      // reconnect: keep the log

    static func of(previousHost: String, newHost: String) -> ConnectKind {
        previousHost == newHost ? .sameDrone : .newDrone
    }
}

// MARK: - Log

struct LogEntry: Identifiable, Equatable {
    enum Source: Equatable { case app, fcu }
    let id: Int
    let source: Source
    let key: String?
    let text: String
    var time: String
    var count = 1
    var seq: Int

    /// The text with a repeat counter ("rosbridge lost — reconnecting… ×9").
    var line: String { count > 1 ? "\(text) ×\(count)" : text }
}

/// Messages panel: PX4 statustext and the app's own lines are capped apart, so
/// reconnect or battery lines never push out a PX4 warning. App lines with a
/// key collapse into the newest line with that key and count up.
struct LogBook {
    static let appCap = 20
    static let fcuCap = 50

    private(set) var app: [LogEntry] = []   // newest first
    private(set) var fcu: [LogEntry] = []   // newest first
    private var counter = 0

    mutating func add(_ text: String, source: LogEntry.Source = .app, key: String? = nil, time: String) {
        counter += 1
        if source == .app, let key = key, let first = app.first, first.key == key {
            app[0].count += 1
            app[0].time = time
            app[0].seq = counter
            return
        }
        let e = LogEntry(id: counter, source: source, key: key, text: text, time: time, seq: counter)
        switch source {
        case .app:
            app.insert(e, at: 0)
            if app.count > Self.appCap { app.removeLast(app.count - Self.appCap) }
        case .fcu:
            fcu.insert(e, at: 0)
            if fcu.count > Self.fcuCap { fcu.removeLast(fcu.count - Self.fcuCap) }
        }
    }

    /// Both lists, newest first.
    var entries: [LogEntry] { (app + fcu).sorted { $0.seq > $1.seq } }

    mutating func clear() { app.removeAll(); fcu.removeAll() }
}

// MARK: - Video

enum VideoStatus: Equatable {
    case waiting            // no frame yet, stream opened less than 3 s ago
    case noFrames           // still no frame after 3 s
    case live
    case lost(seconds: Int) // the last frame is older than 3 s

    static func of(lastFrameAt: Date?, startedAt: Date?, now: Date) -> VideoStatus {
        if let at = lastFrameAt {
            let age = now.timeIntervalSince(at)
            return age > Freshness.video ? .lost(seconds: Int(age)) : .live
        }
        guard let s = startedAt else { return .waiting }
        return now.timeIntervalSince(s) >= Freshness.video ? .noFrames : .waiting
    }
}
