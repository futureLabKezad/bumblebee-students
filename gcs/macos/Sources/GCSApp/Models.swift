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

// MARK: - Theme (parity with the web dashboard)

enum Theme {
    // Surfaces
    static let bg            = Color(hex: 0x0a0c10)
    static let bgDeep        = Color(hex: 0x10141d)   // 4th shade, base of the app gradient
    static let surface       = Color(hex: 0x111318)
    static let surfaceRaised = Color(hex: 0x161a22)
    static let border        = Color(hex: 0x232a39)
    static let hairline      = Color(hex: 0x1a2030)

    /// Canonical app background — every screen uses this for a uniform glass base.
    static let appGradient = LinearGradient(colors: [bg, bgDeep], startPoint: .top, endPoint: .bottom)

    // Accents / status
    static let accent   = Color(hex: 0xf5c842)
    static let accent2  = Color(hex: 0x3b82f6)
    static let ok       = Color(hex: 0x22c55e)
    static let warn     = Color(hex: 0xf97316)
    static let danger   = Color(hex: 0xef4444)
    static let text     = Color(hex: 0xe2e8f0)
    static let muted    = Color(hex: 0x64748b)

    // Accent semantics — read call sites by role, not by hue.
    static let primary  = accent2   // interactive: buttons, links, selection, focus
    static let caution  = accent    // aviation-amber: caution / important status only
    static let selectionBg = accent2.opacity(0.18)   // nav rows, selected chips
    static let hoverBg     = accent2.opacity(0.10)   // hover affordance

    // Categorical data palette — neutral series colors for charts/bars.
    static let dataBlue   = accent2
    static let dataTeal   = Color(hex: 0x06b6d4)
    static let dataGreen  = ok
    static let dataOrange = warn

    // Spacing scale
    static let s0: CGFloat = 2
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s5: CGFloat = 24
    static let s6: CGFloat = 32
    static let s7: CGFloat = 40

    // Corner radii
    static let rSmall: CGFloat = 4
    static let rMedia: CGFloat = 6
    static let rControl: CGFloat = 8
    static let rPanel: CGFloat = 10
    static let rLogo: CGFloat = 18

    // SF Symbol icon sizes
    static let iconSm: CGFloat = 11
    static let iconMd: CGFloat = 15
    static let iconLg: CGFloat = 18
    static let iconXl: CGFloat = 22

    // Typography — SF Pro for chrome, SF Mono for telemetry values.
    static let title      = Font.system(size: 15, weight: .semibold)
    static let label      = Font.system(size: 11, weight: .medium)
    static let sectionLbl = Font.system(size: 10, weight: .semibold, design: .default)
    static let value      = Font.system(.body, design: .monospaced)
    static let valueBig   = Font.system(size: 22, weight: .semibold, design: .monospaced)
    static let mono       = Font.system(.body, design: .monospaced)
    static let monoSmall  = Font.system(.caption, design: .monospaced)
    // Chrome / text scale
    static let brand      = Font.system(size: 14, weight: .bold)
    static let logoTitle  = Font.system(size: 24, weight: .bold)
    static let body       = Font.system(size: 13, weight: .regular)
    static let bodyStrong = Font.system(size: 13, weight: .semibold)
    static let bodyMed    = Font.system(size: 12, weight: .medium)
    static let button     = Font.system(size: 13, weight: .semibold)
    static let buttonSm   = Font.system(size: 12, weight: .medium)
    static let chip       = Font.system(size: 11, weight: .medium)
    // Mono / telemetry scale
    static let statValue  = Font.system(size: 17, weight: .semibold, design: .monospaced)
    static let hostMono   = Font.system(size: 12, weight: .semibold, design: .monospaced)
    static let logMono    = Font.system(size: 10, design: .monospaced)
    static let badge      = Font.system(size: 10, weight: .bold, design: .monospaced)
    static let micro      = Font.system(size: 8, design: .monospaced)

    // Opacity / glass tokens
    static let edgeHi      = Color.white.opacity(0.22)   // glass edge highlight (top)
    static let edgeLo      = Color.white.opacity(0.04)   // glass edge highlight (bottom)
    static let ghostStroke = Color.white.opacity(0.10)   // ghost button border
    static let fillFaint   = Color.white.opacity(0.06)   // unselected chip fill
    static let scrim       = Color.black.opacity(0.4)    // overlay button backdrop
    static let gridLine    = Color(hex: 0x232a39).opacity(0.5)   // map grid (border @ 0.5)
    static let axisLine    = Color(hex: 0x64748b).opacity(0.6)   // map axes (muted @ 0.6)

    // Elevation
    static let shadowColor: Color = .black.opacity(0.3)
    static let shadowRadius: CGFloat = 8
    static let shadowY: CGFloat = 3

    /// The colour of a Tone decided in TelemetryLogic.swift.
    static func color(_ tone: Tone) -> Color {
        switch tone {
        case .plain: return text
        case .primary: return primary
        case .ok: return ok
        case .warn: return warn
        case .caution: return caution
        case .danger: return danger
        case .neutral: return muted
        }
    }
}

// MARK: - Connect / Splash palette (scoped to the startup screens only)
//
// Adapted from the "Bumblebee Connect" design: a warmer radial-glow backdrop with
// an orange brand accent and a blue action color. Kept separate from `Theme` so the
// rest of the app (dashboard, settings, etc.) stays on the amber cockpit palette.
enum ConnectTheme {
    static let bg        = Color(hex: 0x0b0d12)   // page base
    static let bgGlow    = Color(hex: 0x131722)   // radial glow center
    static let text      = Color(hex: 0xe6ebf2)
    static let orange    = Color(hex: 0xff9d1a)   // brand accent (logo, last-drone)
    static let blue      = Color(hex: 0x2f81f7)   // primary action (scan / connect)
    static let blueHover = Color(hex: 0x4c92ff)
    static let blueSoft  = Color(hex: 0x7fb0ff)   // outline-button text
    static let green     = Color(hex: 0x35d07f)   // reachable / linked
    static let muted     = Color(hex: 0x7c8494)
    static let muted2    = Color(hex: 0x8b93a2)
    static let faint     = Color(hex: 0x535b6a)   // placeholders, dividers, "IP" label
    static let hairline  = Color.white.opacity(0.08)
    static let rowBg     = Color.white.opacity(0.02)

    /// radial-gradient(130% 100% at 50% -10%, #131722 0%, #0b0d12 60%)
    static let background = RadialGradient(
        gradient: Gradient(stops: [
            .init(color: bgGlow, location: 0),
            .init(color: bg, location: 0.6),
        ]),
        center: UnitPoint(x: 0.5, y: -0.1),
        startRadius: 0, endRadius: 760)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xff) / 255,
                  green: Double((hex >> 8) & 0xff) / 255,
                  blue: Double(hex & 0xff) / 255,
                  opacity: 1)
    }
}

// MARK: - Math helpers

struct Euler { var roll: Double; var pitch: Double; var yaw: Double } // degrees

func quatToEuler(_ x: Double, _ y: Double, _ z: Double, _ w: Double) -> Euler {
    let roll  = atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    let sp    = max(-1, min(1, 2 * (w * y - z * x)))
    let pitch = asin(sp)
    let yaw   = atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    let r = 180.0 / Double.pi
    return Euler(roll: roll * r, pitch: pitch * r, yaw: yaw * r)
}

// MARK: - System metrics (:8888 JSON)

struct SystemMetrics: Equatable {
    var cpuTemp: Double?
    var cpuPct: Double?
    var load1: Double?
    var load5: Double?
    var load15: Double?
    var cpuCount: Int?
    var memUsed: Int?
    var memTotal: Int?
    var memPct: Double?
}

// MARK: - Telemetry store (fed by RosbridgeClient on the main thread)

/// One "who is in control" event, shown as its own line under the tiles.
struct ControlEventLine: Equatable {
    let time: String
    let text: String
    let mode: String
}

/// Everything the dashboard shows, plus the arrival time of every source so a
/// panel can tell live data from a frozen link. Values are nil until their
/// first message: the screen shows "—", never a made-up 0. All methods run on
/// the main thread; the decisions live in TelemetryLogic.swift.
final class TelemetryStore: ObservableObject {
    // Link
    @Published var rosConnected = false                 // the socket answered (pong or message)
    @Published private(set) var socketOpenedAt: Date?
    @Published private(set) var link: LinkState = .noDrone
    @Published private(set) var now = Date()            // clock for "no data N s"

    // /mavros/state
    @Published private(set) var stateAt: Date?
    @Published private(set) var stateConnected: Bool?
    @Published private(set) var stateArmed: Bool?
    @Published private(set) var mode: String?
    @Published private(set) var lastKnownArmed: Bool?   // from the last OK link; kept for "ARMED? link lost"
    @Published private(set) var controlEvent: ControlEventLine?
    @Published private(set) var fcLost = false          // "Flight controller link lost" banner

    /// Armed as the screen may show it: nil (unknown) unless the link is OK.
    var armed: Bool? { ArmedDisplay.known(link: link, reported: stateArmed) }
    var armedDisplay: ArmedDisplay { ArmedDisplay(armed: armed, lastKnownArmed: lastKnownArmed) }
    var owner: ControlOwner { ControlOwner(armed: armed, mode: mode) }

    // Battery
    @Published private(set) var battery: BatteryReading?
    @Published private(set) var batteryAt: Date?
    @Published private(set) var lowBattery: String?     // red banner text while latched

    // Pose (local position estimate)
    @Published private(set) var posX: Double?
    @Published private(set) var posY: Double?
    @Published private(set) var posZ: Double?
    @Published private(set) var poseAt: Date?

    // Attitude (IMU orientation, or the pose when the IMU has none)
    @Published private(set) var roll: Double?
    @Published private(set) var pitch: Double?
    @Published private(set) var yaw: Double?
    @Published private(set) var attitudeAt: Date?

    // Velocity
    @Published private(set) var vx: Double?
    @Published private(set) var vy: Double?
    @Published private(set) var vz: Double?
    @Published private(set) var velocityAt: Date?
    var speedH: Double? {
        guard let vx = vx, let vy = vy else { return nil }
        return (vx * vx + vy * vy).squareRoot()
    }
    var speedV: Double? { vz.map { abs($0) } }

    // IMU
    @Published private(set) var gyroMag: Double?   // deg/s
    @Published private(set) var accelMag: Double?  // m/s²
    @Published private(set) var imuAt: Date?

    // Trails / charts
    @Published var posTrail: [CGPoint] = []
    @Published var chartAlt: [Double] = []
    @Published var chartSpd: [Double] = []
    @Published var chartBat: [Double] = []

    @Published private(set) var logBook = LogBook()
    var logs: [LogEntry] { logBook.entries }

    /// Plays the system alert sound; tests replace it.
    var playAlert: () -> Void = { NSSound.beep() }

    private let posMax = 200
    private let chartMax = 120
    private var attitudeSource = AttitudeSource()
    private var lowBatteryLatch = LowBatteryLatch()
    private var alarm = FcLostAlarm()
    private var controlEvents = ControlEvents()
    private var clock: Timer?

    // MARK: Clock

    /// Re-checks the link twice a second while connected, so a silent State
    /// turns into "Telemetry frozen" and the captions count up.
    func startClock() {
        guard clock == nil else { return }
        let t = Timer(timeInterval: 0.5, repeats: true) { [weak self] _ in self?.tick() }
        RunLoop.main.add(t, forMode: .common)
        clock = t
    }

    func stopClock() {
        clock?.invalidate()
        clock = nil
    }

    func tick(now: Date = Date()) {
        self.now = now
        refreshLink(now: now)
    }

    // MARK: Log

    func log(_ msg: String, key: String? = nil) {
        logBook.add(msg, key: key, time: Self.timeString())
    }

    func pushTrail(_ x: Double, _ y: Double) {
        posTrail.append(CGPoint(x: x, y: y))
        if posTrail.count > posMax { posTrail.removeFirst(posTrail.count - posMax) }
    }

    func pushChart(_ kp: ReferenceWritableKeyPath<TelemetryStore, [Double]>, _ v: Double) {
        self[keyPath: kp].append(v)
        let arr = self[keyPath: kp]
        if arr.count > chartMax { self[keyPath: kp].removeFirst(arr.count - chartMax) }
    }

    // MARK: Socket

    func socketOpened(host: String, now: Date = Date()) {
        rosConnected = true
        socketOpenedAt = now
        log("rosbridge connected (\(host))")
        refreshLink(now: now)
    }

    /// The socket closed or stopped answering (`reason`, see DropReason).
    /// Repeated failures collapse into one line with a counter.
    func socketDropped(wasLinked: Bool, reason: String? = nil, now: Date = Date()) {
        rosConnected = false
        socketOpenedAt = nil
        log(DropReason.line(wasLinked: wasLinked, reason: reason), key: "rosbridge-down")
        refreshLink(now: now)
    }

    /// Link, armed, alarm and control events from the current State and socket.
    func refreshLink(now: Date) {
        let l = LinkState.evaluate(socketOpenedAt: socketOpenedAt, stateAt: stateAt,
                                   stateConnected: stateConnected, now: now)
        if l != link { link = l }
        if l == .ok, let a = stateArmed, a != lastKnownArmed { lastKnownArmed = a }
        if alarm.update(link: l, lastKnownArmed: lastKnownArmed) {
            playAlert()
            log(FcLostAlarm.text)
        }
        if alarm.active != fcLost { fcLost = alarm.active }
        let m = mode ?? ""
        if let ev = controlEvents.update(owner: owner, mode: m) {
            controlEvent = ControlEventLine(time: Self.timeString(), text: ev, mode: m)
            log(ev)
        }
    }

    // MARK: Messages

    func ingest(topic: String, msg: [String: Any], now: Date = Date()) {
        switch topic {
        case "/mavros/state":
            stateAt = now
            stateConnected = msg["connected"] as? Bool
            stateArmed = msg["armed"] as? Bool
            if let raw = msg["mode"] as? String, case let m = ModeText.normalize(raw), m != mode {
                mode = m
                log(ModeText.changeLine(m))
            }
            refreshLink(now: now)

        case "/mavros/statustext/recv":
            let sev = (msg["severity"] as? Int) ?? 99
            if sev <= 4, let txt = msg["text"] as? String {
                logBook.add("[FCU] \(txt)", source: .fcu, time: Self.timeString())
            }

        case "/mavros/battery":
            let r = BatteryReading.classify(voltage: msg["voltage"] as? Double,
                                            percentage: msg["percentage"] as? Double)
            battery = r
            batteryAt = now
            if case .measured(let v, let p?) = r {
                pushChart(\.chartBat, p)
                if lowBatteryLatch.update(percent: p) {
                    log(String(format: "WARNING LOW BATTERY: %.2f V (%.0f%%)", v, p))
                }
                lowBattery = lowBatteryLatch.active ? String(format: "Low battery: %.2f V · %.0f%%", v, p) : nil
            }

        case "/mavros/mavros/pose":
            guard let pose = msg["pose"] as? [String: Any],
                  let p = pose["position"] as? [String: Any],
                  let x = p["x"] as? Double, let y = p["y"] as? Double, let z = p["z"] as? Double
            else { return }
            posX = x; posY = y; posZ = z
            poseAt = now
            if let o = pose["orientation"] as? [String: Any],
               let e = attitudeSource.fromPose(x: (o["x"] as? Double) ?? 0, y: (o["y"] as? Double) ?? 0,
                                               z: (o["z"] as? Double) ?? 0, w: (o["w"] as? Double) ?? 1, now: now) {
                setAttitude(e, now: now)
            }
            pushTrail(x, y)
            pushChart(\.chartAlt, z)

        case "/mavros/mavros/velocity_local":
            guard let twist = msg["twist"] as? [String: Any],
                  let l = twist["linear"] as? [String: Any] else { return }
            vx = (l["x"] as? Double) ?? 0
            vy = (l["y"] as? Double) ?? 0
            vz = (l["z"] as? Double) ?? 0
            velocityAt = now
            if let s = speedH { pushChart(\.chartSpd, s) }

        case "/mavros/mavros/data":
            guard let av = msg["angular_velocity"] as? [String: Any],
                  let la = msg["linear_acceleration"] as? [String: Any] else { return }
            let gx = (av["x"] as? Double) ?? 0, gy = (av["y"] as? Double) ?? 0, gz = (av["z"] as? Double) ?? 0
            let ax = (la["x"] as? Double) ?? 0, ay = (la["y"] as? Double) ?? 0, az = (la["z"] as? Double) ?? 0
            gyroMag = (gx * gx + gy * gy + gz * gz).squareRoot() * 180 / Double.pi
            accelMag = (ax * ax + ay * ay + az * az).squareRoot()
            imuAt = now
            if let o = msg["orientation"] as? [String: Any],
               let qx = o["x"] as? Double, let qy = o["y"] as? Double,
               let qz = o["z"] as? Double, let qw = o["w"] as? Double {
                let cov0 = (msg["orientation_covariance"] as? [Any])?.first as? Double
                if let e = attitudeSource.fromIMU(x: qx, y: qy, z: qz, w: qw, covariance0: cov0, now: now) {
                    setAttitude(e, now: now)
                }
            }

        default: break
        }
    }

    private func setAttitude(_ e: Euler, now: Date) {
        roll = e.roll; pitch = e.pitch; yaw = e.yaw
        attitudeAt = now
    }

    // MARK: Resets

    /// Reconnect (same drone) or disconnect: armed becomes unknown until a new
    /// State arrives on the new socket. The log and the last values stay; their
    /// panels grey out by age.
    func resetForReconnect() {
        rosConnected = false
        socketOpenedAt = nil
        stateAt = nil; stateConnected = nil; stateArmed = nil
        mode = nil
        refreshLink(now: Date())
    }

    /// Connect to a different drone: nothing of the previous one stays.
    func resetAll() {
        alarm.reset(); controlEvents.reset(); lowBatteryLatch.reset(); attitudeSource.reset()
        resetForReconnect()
        lastKnownArmed = nil; controlEvent = nil; fcLost = false
        battery = nil; batteryAt = nil; lowBattery = nil
        posX = nil; posY = nil; posZ = nil; poseAt = nil
        roll = nil; pitch = nil; yaw = nil; attitudeAt = nil
        vx = nil; vy = nil; vz = nil; velocityAt = nil
        gyroMag = nil; accelMag = nil; imuAt = nil
        posTrail = []; chartAlt = []; chartSpd = []; chartBat = []
        logBook.clear()
    }

    private static let timeFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f
    }()

    static func timeString() -> String { timeFormatter.string(from: Date()) }
}
