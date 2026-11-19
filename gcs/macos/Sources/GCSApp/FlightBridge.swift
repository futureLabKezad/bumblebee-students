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

import CryptoKit
import Foundation

/// HTTP status (0 = no answer from the drone) and the JSON body of a mission-server reply.
struct MissionReply: Equatable {
    var code: Int
    var json: String
}

/// The six commands of the drone's mission server (bb_mission, port 8766). The app still
/// never arms, changes modes, sends setpoints or writes PX4 parameters: these ask the
/// drone's guarded runner, which checks everything again on the drone. Every call names
/// the drone: a takeoff asked about one drone is never sent to another.
@MainActor
protocol MissionCommands: AnyObject {
    func mapStatus(host: String) async -> MissionReply
    func putMap(host: String, map: [String: Any]) async -> MissionReply
    func check(host: String, program: String) async -> MissionReply
    /// `mapSha`: the map the person saw in «Взлёт?»; the drone refuses another one.
    func start(host: String, program: String, token: String, mapSha: String,
               battery: Bool, rc: Bool, people: Bool) async -> MissionReply
    func stop(host: String) async -> MissionReply
    func status(host: String, since: Int64) async -> MissionReply
}

/// What the app's own «Взлёт?» dialog shows: the map the DRONE has, not what the page says.
struct TakeoffRequest: Equatable {
    var host: String
    var mapName: String
    var mapSha: String
    var markerCount: Int
    var programLines: Int
    var programSha: String
}

/// The answer to «Взлёт?»: yes; no (the window was shown and declined, or nobody answered);
/// or not asked at all (hidden section, another drone, an open question of the app) -- then
/// `why` tells the page the reason.
struct TakeoffAnswer: Equatable {
    var yes: Bool
    var asked: Bool
    var why: String

    static let go = TakeoffAnswer(yes: true, asked: true, why: "")
    static func declined(_ why: String = "takeoff cancelled in the app’s window") -> TakeoffAnswer {
        TakeoffAnswer(yes: false, asked: true, why: why)
    }
    static func notAsked(_ why: String) -> TakeoffAnswer {
        TakeoffAnswer(yes: false, asked: false, why: why)
    }
}

/// The text of «Взлёт?». Names are someone's free text: they come last and cleaned.
enum TakeoffText {
    static let maxNameChars = 32

    /// The first 12 hex digits of a hash (anything else in it is dropped).
    static func short(_ sha: String) -> String {
        String(sha.filter { $0.isASCII && $0.isHexDigit }.prefix(12))
    }

    /// Letters, digits, space, '_', '-', '.', 32 at most: a name cannot imitate the lines above it.
    static func safeName(_ name: String) -> String {
        var out = ""
        for ch in name {
            if out.count >= maxNameChars { break }
            if ch.isLetter || ch.isNumber || ch == " " || ch == "_" || ch == "-" || ch == "." { out.append(ch) }
        }
        let text = out.trimmingCharacters(in: .whitespaces)
        return text.isEmpty ? "(no name)" : text
    }

    static func body(_ r: TakeoffRequest, droneName: String, link: String) -> String {
        let who = droneName.isEmpty || droneName == r.host ? r.host : "\(safeName(droneName)) (\(r.host))"
        return "Drone \(who) will arm the motors and fly the program.\n"
            + "Program: \(r.programLines) lines, sha \(short(r.programSha)).\n"
            + "Map on the drone: \(r.markerCount) markers, sha \(short(r.mapSha)).\n"
            + "Map name: \(safeName(r.mapName))\n"
            + "Telemetry: \(link)\n\n"
            + "RC in hand: CH8 stops. People are away from the field."
    }
}

/// At most so many messages and characters per second; what is over is dropped unparsed.
final class MessageBudget {
    private let maxMessages: Int
    private let maxChars: Int
    private let nowMs: () -> Int64
    private var windowStart: Int64?
    private var messages = 0
    private var chars = 0

    init(maxMessages: Int, maxChars: Int, nowMs: @escaping () -> Int64) {
        self.maxMessages = maxMessages
        self.maxChars = maxChars
        self.nowMs = nowMs
    }

    func allow(_ count: Int) -> Bool {
        let now = nowMs()
        if let start = windowStart, now >= start, now - start < 1000 {
            // the same second
        } else {
            windowStart = now
            messages = 0
            chars = 0
        }
        if messages >= maxMessages || chars + count > maxChars { return false }
        messages += 1
        chars += count
        return true
    }
}

/// Between the «Полёт» web page (gcs/web, inside WKWebView) and the drone. The page has no
/// network to the drone (its Content-Security-Policy); it posts messages
/// {bb: 1, id, cmd, body, since} and gets {bb: 1, id, code, data} back. Only the commands
/// below exist. The page is not trusted (it runs a student's Python and loads students' maps):
///   * a takeoff needs a permission this bridge itself saw in the drone's reply to a check
///     of this very program, the three check marks, no mission running, and a click in the
///     app's own dialog (confirmTakeoff), which page code cannot press; one permission opens
///     the dialog once, and after «Отмена» there is a pause;
///   * while the dialog is open the map and the program on the drone cannot be changed from
///     here, and the drone is told which map the person saw;
///   * messages are limited per second and one request of a kind runs at a time;
///   * Stop needs nothing and is never dropped.
/// The same rules as Logic/FlightBridge.cs of the Windows app. No UI types here:
/// Tests/GCSAppTests/FlightBridgeTests.swift.
@MainActor
final class FlightBridge {
    static let maxMessageChars = 400_000
    static let maxProgramChars = 100_000       // the mission server's own limit
    static let maxMessagesPerSecond = 20
    static let maxCharsPerSecond = 1_000_000
    static let permissionSeconds = 120         // the drone's own life of a start token
    static let cancelPauseSeconds = 5

    private struct Permission {
        var token: String
        var host: String
        var programSha: String
        var mapSha: String
        var untilMs: Int64
    }

    private let api: MissionCommands
    private let confirmTakeoff: @MainActor (TakeoffRequest) async -> TakeoffAnswer
    private let drone: @MainActor () -> (host: String, name: String)
    private let nowMs: () -> Int64
    private let budget: MessageBudget
    private var inFlight = Set<String>()
    private var stopTask: Task<MissionReply, Never>?
    private var permission: Permission?
    private var starting = false
    private var noDialogUntilMs = Int64.min
    private var stops = 0                          // every Stop asked here or by the app's own button
    private var floodStopAtMs: Int64?

    /// A mission this app started (or saw in a status reply) is running on the drone.
    private(set) var missionActive = false
    var onMissionActiveChanged: (@MainActor () -> Void)?

    /// «Взлететь» was clicked and the start request is on its way to the drone.
    private(set) var takeoffInFlight = false
    var onTakeoffInFlightChanged: (@MainActor () -> Void)?

    /// The app's own STOP FLIGHT button tells the bridge: a start that is still on its way
    /// must not win the race (the bridge stops again once that start is settled).
    func noteStop() { stops += 1 }

    init(api: MissionCommands,
         confirmTakeoff: @escaping @MainActor (TakeoffRequest) async -> TakeoffAnswer,
         drone: @escaping @MainActor () -> (host: String, name: String),
         nowMs: @escaping () -> Int64 = { Int64(ProcessInfo.processInfo.systemUptime * 1000) }) {
        self.api = api
        self.confirmTakeoff = confirmTakeoff
        self.drone = drone
        self.nowMs = nowMs
        budget = MessageBudget(maxMessages: Self.maxMessagesPerSecond, maxChars: Self.maxCharsPerSecond, nowMs: nowMs)
    }

    /// One message from the page (JSON text) -> the reply for the page (JSON text);
    /// nil when the message is not for the bridge or is over the budget (no reply is sent).
    func handle(_ message: String) async -> String? {
        let length = message.utf16.count
        if length > Self.maxMessageChars { return nil }
        if !budget.allow(length) {
            // Over the budget nothing is parsed and nothing is answered -- but a Stop is never
            // lost: what looks like one still goes to the drone, once a second at most.
            if length <= 256 && message.contains("\"mission_stop\"") { floodStop() }
            return nil
        }
        guard let root = Self.object(message),
              Self.integer(root["bb"]) == 1,
              let id = Self.integer(root["id"]),
              let cmd = root["cmd"] as? String else { return nil }
        let reply = await dispatch(cmd, root)
        return Self.compose(id: id, reply: reply)
    }

    private func dispatch(_ cmd: String, _ root: [String: Any]) async -> MissionReply {
        let body = root["body"] as? [String: Any]
        let (host, name) = drone()
        switch cmd {
        case "hello":
            return MissionReply(code: 200, json: Self.text(["host": host, "name": name, "connected": !host.isEmpty]))
        case "mission_stop":
            return await stop(host: host)                // always, with no checks
        case "map_status", "map_put", "mission_check", "mission_start", "mission_status":
            break
        default:
            return Self.problem("unknown command", "bad_request")
        }
        if starting && cmd == "mission_start" {
            return Self.problem("a takeoff is already being confirmed in the app’s window", "busy")
        }
        if starting && (cmd == "map_put" || cmd == "mission_check") {
            return Self.problem("the “Take off?” window is open: the map and the program cannot be changed now", "busy")
        }
        if inFlight.contains(cmd) {
            return Self.problem("the app is still waiting for the drone’s answer to the same command", "busy")
        }
        inFlight.insert(cmd)
        defer { inFlight.remove(cmd) }
        switch cmd {
        case "map_status":
            return await api.mapStatus(host: host)
        case "map_put":
            guard let map = body?["map"] as? [String: Any] else {
                return Self.problem("no map in the request", "bad_request")
            }
            return await api.putMap(host: host, map: map)
        case "mission_check":
            let (text, bad) = Self.program(in: body)
            guard let program = text else { return bad }
            permission = nil                             // a new check replaces the old permission
            let reply = await api.check(host: host, program: program)
            permission = grantedPermission(in: reply, host: host, program: program)
            return reply
        case "mission_start":
            return await start(body, host: host)
        default:                                         // mission_status
            let since = max(0, Self.integer(root["since"]) ?? 0)
            let reply = await api.status(host: host, since: since)
            if reply.code == 200, let running = Self.bool(Self.object(reply.json)?["running"]) { setActive(running) }
            return reply
        }
    }

    /// Stops asked at the same time share one request to the drone.
    private func stop(host: String) async -> MissionReply {
        noteStop()
        if let running = stopTask { return await running.value }
        let task = Task { @MainActor in await self.api.stop(host: host) }
        stopTask = task
        let reply = await task.value
        stopTask = nil
        return reply
    }

    /// A Stop among messages over the budget: sent without parsing and without a reply.
    private func floodStop() {
        let now = nowMs()
        if stopTask != nil { return }
        if let last = floodStopAtMs, now >= last, now - last < 1000 { return }
        floodStopAtMs = now
        let host = drone().host
        Task { @MainActor in _ = await self.stop(host: host) }      // nobody waits for this one
    }

    /// What to tell the person about a Stop the bridge sent by itself.
    private static func stopSaid(_ stop: MissionReply, _ done: String) -> String {
        stop.code == 200 ? done + "." : "STOP did NOT reach the drone: stop with the RC (CH8)."
    }

    private func setTakeoffInFlight(_ value: Bool) {
        if takeoffInFlight == value { return }
        takeoffInFlight = value
        onTakeoffInFlightChanged?()
    }

    private func start(_ body: [String: Any]?, host: String) async -> MissionReply {
        let (text, bad) = Self.program(in: body)
        guard let program = text else { return bad }
        let token = body?["token"] as? String ?? ""
        guard Self.isToken(token) else { return Self.noPermission() }
        let confirm = body?["confirm"] as? [String: Any]
        let battery = Self.bool(confirm?["battery_multimeter"]) == true
        let rc = Self.bool(confirm?["rc_in_hand_ch8"]) == true
        let people = Self.bool(confirm?["people_clear"]) == true
        guard battery && rc && people else {
            return Self.problem("tick the three items: battery, RC and CH8, people away", "not_confirmed")
        }
        let now = nowMs()
        if now < noDialogUntilMs {
            permission = nil                         // the page spent its permission on this try as well
            return Self.problem("the takeoff was just cancelled: wait \(Self.cancelPauseSeconds) s and check the program on the drone again",
                                "cancelled")
        }
        // Only a permission this bridge saw the drone give, for this program, on this drone -- and only once.
        guard let granted = permission, granted.token == token, granted.host == host,
              now <= granted.untilMs else { return Self.noPermission() }
        let programSha = Self.sha256Hex(program)
        guard granted.programSha == programSha else {
            return Self.problem("the program changed after the check: check it on the drone again", "changed")
        }
        self.permission = nil
        starting = true
        defer { starting = false }
        // From here a Stop (the page's or the app's own button) cancels this takeoff, wherever
        // it catches it: before the window is answered, or crossing the start request on the network.
        let stopsBefore = stops

        // What the person is asked about is what the DRONE reports, not what the page claims.
        let status = await api.status(host: host, since: Int64(Int32.max))
        guard status.code == 200 else { return status }
        guard let r = Self.object(status.json) else {
            return Self.problem("the drone sent an unclear answer about the mission and the map", "bad_reply")
        }
        let running = Self.bool(r["running"]) != false          // «running» missing: taken as running
        let map = r["map"] as? [String: Any]
        let confirmed = Self.bool(map?["confirmed"]) == true
        let active = map?["active"] as? [String: Any]
        let mapName = active?["name"] as? String ?? ""
        let sha = active?["sha"] as? String ?? ""
        let count = Int(Self.integer(active?["n"]) ?? 0)
        if running { return Self.problem("a mission is already running on the drone: STOP first", "busy") }
        if !confirmed || sha.isEmpty {
            return Self.problem("the map on the drone is not confirmed by the detector: first “Send the map to the drone”",
                                "map_not_confirmed")
        }
        if sha != granted.mapSha {
            return Self.problem("the map on the drone changed after the check: check the program on the drone again", "changed")
        }
        let lines = program.unicodeScalars.filter { $0 == "\n" }.count + 1
        let request = TakeoffRequest(host: host, mapName: mapName, mapSha: sha, markerCount: count,
                                     programLines: lines, programSha: programSha)
        let answer = await confirmTakeoff(request)
        if !answer.yes {
            // the pause follows a window that was shown; without a window the page gets the reason
            if answer.asked { noDialogUntilMs = nowMs() + Int64(Self.cancelPauseSeconds) * 1000 }
            return Self.problem(answer.why.isEmpty ? "takeoff cancelled in the app’s window" : answer.why,
                                answer.asked ? "cancelled" : "not_asked")
        }
        if drone().host != host {
            return Self.problem("the app is now connected to another drone: no takeoff", "cancelled")
        }
        if stops != stopsBefore {
            return Self.problem("STOP was pressed while the “Take off?” window was open: no takeoff", "stopped")
        }
        setTakeoffInFlight(true)
        let reply = await api.start(host: host, program: program, token: token, mapSha: sha,
                                    battery: battery, rc: rc, people: people)
        setTakeoffInFlight(false)
        if reply.code == 0 {
            // No answer: the drone may have started all the same.
            let stopped = await api.stop(host: host)
            return Self.problem("the drone did not answer the start command. " + Self.stopSaid(stopped, "STOP sent to be safe"),
                                "no_answer")
        }
        guard reply.code == 200 else { return reply }
        setActive(true)
        if stops != stopsBefore {
            let stopped = await api.stop(host: host)
            return Self.problem("STOP was pressed while the start was on its way to the drone. " + Self.stopSaid(stopped, "Mission stopped"),
                                "stopped")
        }
        if let flown = Self.object(reply.json)?["map_sha"] as? String, flown != sha {
            let stopped = await api.stop(host: host)
            return Self.problem("the drone started the mission with another map than the one in the “Take off?” window. "
                                + Self.stopSaid(stopped, "STOP sent"), "map_mismatch")
        }
        return reply
    }

    private func setActive(_ active: Bool) {
        if missionActive == active { return }
        missionActive = active
        onMissionActiveChanged?()
    }

    /// The permission in the drone's reply to a check (it gives one only for a clean program and a confirmed map).
    private func grantedPermission(in reply: MissionReply, host: String, program: String) -> Permission? {
        guard reply.code == 200, let r = Self.object(reply.json),
              let token = r["token"] as? String, Self.isToken(token),
              let mapSha = (r["map"] as? [String: Any])?["sha"] as? String, !mapSha.isEmpty else { return nil }
        var life = Double(Self.permissionSeconds)
        if let ttl = r["token_ttl_s"] as? NSNumber, Self.bool(ttl) == nil {
            life = min(max(ttl.doubleValue, 0), Double(Self.permissionSeconds))
        }
        return Permission(token: token, host: host, programSha: Self.sha256Hex(program), mapSha: mapSha,
                          untilMs: nowMs() + Int64(life * 1000))
    }

    // MARK: - Small helpers

    private static func isToken(_ token: String) -> Bool {
        let bytes = Array(token.utf8)
        guard bytes.count >= 8, bytes.count <= 128 else { return false }
        for b in bytes {
            switch b {
            case 0x30...0x39, 0x41...0x46, 0x61...0x66: continue      // 0-9 A-F a-f
            default: return false
            }
        }
        return true
    }

    private static func noPermission() -> MissionReply {
        problem("no valid permission: press “Check the program on the drone” again", "bad_token")
    }

    /// The program text of a request, or the error reply.
    private static func program(in body: [String: Any]?) -> (String?, MissionReply) {
        guard let program = body?["program"] as? String else {
            return (nil, problem("no program in the request", "bad_request"))
        }
        if program.utf16.count > maxProgramChars { return (nil, problem("the program is too long", "bad_request")) }
        return (program, MissionReply(code: 0, json: ""))
    }

    /// As the drone computes it: SHA-256 of the UTF-8 text, hex.
    static func sha256Hex(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    /// A reply made by the app itself (code 0: the drone was not asked or did not answer).
    static func problem(_ text: String, _ code: String) -> MissionReply {
        MissionReply(code: 0, json: Self.text(["error": text, "code": code]))
    }

    private static func object(_ json: String) -> [String: Any]? {
        guard let data = json.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    private static func text(_ object: [String: Any]) -> String {
        guard JSONSerialization.isValidJSONObject(object),
              let data = try? JSONSerialization.data(withJSONObject: object, options: [.withoutEscapingSlashes]) else {
            return "{}"
        }
        return String(decoding: data, as: UTF8.self)
    }

    /// true / false of a JSON boolean; nil for anything else (a JSON number 1 is not «true»).
    private static func bool(_ value: Any?) -> Bool? {
        guard let n = value as? NSNumber, CFGetTypeID(n as CFTypeRef) == CFBooleanGetTypeID() else { return nil }
        return n.boolValue
    }

    /// A JSON number that is a whole number; nil for booleans, fractions and anything else.
    private static func integer(_ value: Any?) -> Int64? {
        guard let n = value as? NSNumber, bool(n) == nil else { return nil }
        let d = n.doubleValue
        guard d == d.rounded(), abs(d) < 9e15 else { return nil }
        return n.int64Value
    }

    /// {bb, id, code, data}: data is the drone's JSON object as it came, or an error object.
    private static func compose(id: Int64, reply: MissionReply) -> String {
        let data: [String: Any] = object(reply.json)
            ?? ["error": reply.code == 0 ? "no answer from the drone" : "the drone sent an unclear answer"]
        return text(["bb": 1, "id": id, "code": reply.code, "data": data])
    }
}
