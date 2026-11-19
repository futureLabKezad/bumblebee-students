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

import XCTest
@testable import GCSApp

private let kSha = "8a8ab61a53b9c6a5"
private let kToken = "0123456789abcdef0123456789abcdef"
private let kProgram = "import drone\ndrone.takeoff(0.9)\ndrone.land()"
private let kHost = "10.0.0.7"
private let kStop = #"{"bb":1,"id":9,"cmd":"mission_stop"}"#

private func statusJSON(running: Bool = false, confirmed: Bool = true, sha: String = kSha) -> String {
    "{\"running\":\(running),\"map\":{\"active\":{\"sha\":\"\(sha)\",\"name\":\"field_real\",\"n\":20},\"confirmed\":\(confirmed)}}"
}

private func checkJSON(token: String = kToken, sha: String = kSha) -> String {
    "{\"check\":{\"ok\":true},\"map\":{\"sha\":\"\(sha)\",\"name\":\"field_real\",\"n\":20},\"map_confirmed\":true,"
        + "\"token\":\"\(token)\",\"token_ttl_s\":120.0}"
}

private func message(_ cmd: String, id: Int = 1, body: [String: Any]? = nil, since: Int? = nil) -> String {
    var m: [String: Any] = ["bb": 1, "id": id, "cmd": cmd]
    if let body = body { m["body"] = body }
    if let since = since { m["since"] = since }
    let data = (try? JSONSerialization.data(withJSONObject: m)) ?? Data()
    return String(decoding: data, as: UTF8.self)
}

private func startMessage(battery: Bool = true, rc: Bool = true, people: Bool = true,
                          token: String = kToken, program: String = kProgram) -> String {
    let confirm: [String: Any] = ["battery_multimeter": battery, "rc_in_hand_ch8": rc,
                                  "people_clear": people, "takeoff_clicked": true]
    return message("mission_start", id: 5, body: ["program": program, "token": token, "confirm": confirm])
}

private func code(_ reply: [String: Any]) -> Int { reply["code"] as? Int ?? -1 }
private func problem(_ reply: [String: Any]) -> String { (reply["data"] as? [String: Any])?["code"] as? String ?? "" }

/// Lets the tasks already queued on the main actor run up to their next wait.
@MainActor
private func settle() async {
    for _ in 0..<20 { await Task.yield() }
}

/// A request (or the person's answer) that waits until the test opens the gate.
@MainActor
private final class Gate {
    private var waiters: [CheckedContinuation<Void, Never>] = []
    private var isOpen = false

    func wait() async {
        if isOpen { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func open() {
        isOpen = true
        let all = waiters
        waiters = []
        all.forEach { $0.resume() }
    }
}

private final class TestClock {
    var ms: Int64 = 10_000
}

/// What a callback of the bridge reported (a class: the callbacks only hold a reference).
private final class Seen {
    var flags: [Bool] = []
    var count = 0
}

@MainActor
private final class FakeAPI: MissionCommands {
    var calls: [String] = []
    var statusReply = MissionReply(code: 200, json: statusJSON())
    var checkReply = MissionReply(code: 200, json: checkJSON())
    var next = MissionReply(code: 200, json: #"{"ok":true}"#)
    var startReply = MissionReply(code: 200, json: "{\"started\":true,\"run\":\"run_1\",\"map_sha\":\"\(kSha)\"}")
    var startedHost: String?
    var startedProgram: String?
    var startedToken: String?
    var startedMapSha: String?
    var mapName: String?
    var since: Int64 = -1
    var hold: Gate?                 // a request waits for this (the drone is slow)
    var startHold: Gate?            // the start request is on its way for this long

    private func after(_ reply: MissionReply) async -> MissionReply {
        if let hold = hold { await hold.wait() }
        return reply
    }

    func mapStatus(host: String) async -> MissionReply {
        calls.append("map_status")
        return await after(next)
    }

    func putMap(host: String, map: [String: Any]) async -> MissionReply {
        calls.append("map_put")
        mapName = map["name"] as? String
        return await after(next)
    }

    func check(host: String, program: String) async -> MissionReply {
        calls.append("check:" + program)
        return await after(checkReply)
    }

    func start(host: String, program: String, token: String, mapSha: String,
               battery: Bool, rc: Bool, people: Bool) async -> MissionReply {
        calls.append("start")
        startedHost = host
        startedProgram = program
        startedToken = token
        startedMapSha = mapSha
        if let startHold = startHold { await startHold.wait() }
        return startReply
    }

    func stop(host: String) async -> MissionReply {
        calls.append("stop")
        return await after(next)
    }

    func status(host: String, since: Int64) async -> MissionReply {
        calls.append("status")
        self.since = since
        return await after(statusReply)
    }
}

@MainActor
private final class Rig {
    let api = FakeAPI()
    let clock = TestClock()
    var asked: [TakeoffRequest] = []
    var answer: @MainActor (TakeoffRequest) async -> TakeoffAnswer = { _ in .go }
    var droneHost = kHost
    private(set) var bridge: FlightBridge!

    init() {
        let clock = self.clock
        bridge = FlightBridge(
            api: api,
            confirmTakeoff: { [unowned self] request in
                self.asked.append(request)
                return await self.answer(request)
            },
            drone: { [unowned self] in (host: self.droneHost, name: "Bumblebee-20EC") },
            nowMs: { clock.ms })
    }

    func send(_ text: String) async throws -> [String: Any] {
        let answer = await bridge.handle(text)
        let reply = try XCTUnwrap(answer)
        let object = try JSONSerialization.jsonObject(with: Data(reply.utf8)) as? [String: Any]
        return try XCTUnwrap(object)
    }

    func checkProgram(_ program: String = kProgram) async throws -> [String: Any] {
        try await send(message("mission_check", id: 3, body: ["program": program]))
    }

    /// The honest page: check on the drone, then «ВЗЛЁТ». A second passes first: the message budget.
    func checkThenStart(_ program: String = kProgram) async throws -> [String: Any] {
        clock.ms += 1000
        _ = try await checkProgram(program)
        return try await send(startMessage(program: program))
    }
}

/// The «Полёт» page talks to the drone only through FlightBridge, and the page is not
/// trusted: only the six commands; a takeoff only with a permission the bridge itself saw
/// the drone give, three check marks AND the app's own dialog; Stop always.
/// The same cases as FlightBridgeTests.cs of the Windows app.
@MainActor
final class FlightBridgeTests: XCTestCase {

    func testWhatIsNotABridgeMessageGetsNoReply() async {
        let rig = Rig()
        for bad in ["not json", "[1,2]", "{}", #"{"bb":2,"id":1,"cmd":"hello"}"#, #"{"bb":1,"cmd":"hello"}"#,
                    #"{"bb":1,"id":"x","cmd":"hello"}"#, #"{"bb":1,"id":1,"cmd":5}"#, #"{"bb":1.5,"id":1,"cmd":"hello"}"#,
                    #"{"bb":true,"id":1,"cmd":"hello"}"#] {
            let reply = await rig.bridge.handle(bad)
            XCTAssertNil(reply, bad)
        }
        let long = "{\"bb\":1,\"id\":1,\"cmd\":\"hello\",\"pad\":\"" + String(repeating: "x", count: FlightBridge.maxMessageChars) + "\"}"
        let reply = await rig.bridge.handle(long)
        XCTAssertNil(reply)
        XCTAssertTrue(rig.api.calls.isEmpty)
    }

    func testHelloNamesTheDroneTheAppIsConnectedTo() async throws {
        let rig = Rig()
        let r = try await rig.send(message("hello", id: 7))
        XCTAssertEqual(r["id"] as? Int, 7)
        XCTAssertEqual(code(r), 200)
        let data = try XCTUnwrap(r["data"] as? [String: Any])
        XCTAssertEqual(data["host"] as? String, kHost)
        XCTAssertEqual(data["connected"] as? Bool, true)
        let none = Rig()
        none.droneHost = ""
        let r2 = try await none.send(message("hello"))
        XCTAssertEqual((r2["data"] as? [String: Any])?["connected"] as? Bool, false)
    }

    func testOnlyTheSixCommandsExist() async throws {
        let rig = Rig()
        for cmd in ["arm", "set_param", "navigate", "exec", "", "MISSION_STOP"] {
            let r = try await rig.send(message(cmd, body: ["x": 1]))
            XCTAssertEqual(code(r), 0)
            XCTAssertEqual(problem(r), "bad_request")
        }
        XCTAssertTrue(rig.api.calls.isEmpty)
    }

    func testMapAndCheckAndStatusArePassedOn() async throws {
        let rig = Rig()
        let map: [String: Any] = ["name": "m", "markers": [Any]()]
        let put = try await rig.send(message("map_put", body: ["map": map]))
        XCTAssertEqual(code(put), 200)
        XCTAssertEqual((put["data"] as? [String: Any])?["ok"] as? Bool, true)
        XCTAssertEqual(rig.api.mapName, "m")
        let badMap = try await rig.send(message("map_put", id: 2, body: ["map": "text"]))
        XCTAssertEqual(code(badMap), 0)
        let checked = try await rig.checkProgram("import drone")
        XCTAssertEqual((checked["data"] as? [String: Any])?["token"] as? String, kToken)
        _ = try await rig.send(message("mission_status", id: 4, since: 42))
        XCTAssertEqual(rig.api.since, 42)
        _ = try await rig.send(message("mission_status", id: 5, since: -9))
        XCTAssertEqual(rig.api.since, 0)
        XCTAssertEqual(rig.api.calls, ["map_put", "check:import drone", "status", "status"])
        let tooLong = try await rig.send(message("mission_check", id: 6,
            body: ["program": String(repeating: "x", count: FlightBridge.maxProgramChars + 1)]))
        XCTAssertEqual(code(tooLong), 0)
    }

    func testTakeoffNeedsTheThreeMarksAndAWellFormedToken() async throws {
        let rig = Rig()
        _ = try await rig.checkProgram()
        for msg in [startMessage(battery: false), startMessage(rc: false), startMessage(people: false),
                    startMessage(token: ""), startMessage(token: "zz-not-hex-zz"),
                    startMessage(token: String(repeating: "a", count: 7)),
                    startMessage(token: String(repeating: "a", count: 129))] {
            let r = try await rig.send(msg)
            XCTAssertEqual(code(r), 0)
        }
        XCTAssertTrue(rig.asked.isEmpty)                       // the dialog is not even shown
        XCTAssertFalse(rig.api.calls.contains("status"))
        XCTAssertFalse(rig.api.calls.contains("start"))
    }

    func testTheDialogOpensOnlyForAPermissionTheBridgeSawTheDroneGive() async throws {
        let rig = Rig()
        var r = try await rig.send(startMessage())
        XCTAssertEqual(problem(r), "bad_token")                // no check at all
        _ = try await rig.checkProgram()
        r = try await rig.send(startMessage(token: "00000000"))
        XCTAssertEqual(problem(r), "bad_token")                // a made-up token
        r = try await rig.send(startMessage(program: kProgram + "\n# more"))
        XCTAssertEqual(problem(r), "changed")
        rig.clock.ms += Int64(FlightBridge.permissionSeconds + 1) * 1000
        r = try await rig.send(startMessage())
        XCTAssertEqual(problem(r), "bad_token")                // too old
        rig.api.checkReply = MissionReply(code: 200, json: #"{"check":{"ok":false,"errors":[{"text":"x"}]},"map_confirmed":true}"#)
        _ = try await rig.checkProgram()
        r = try await rig.send(startMessage())
        XCTAssertEqual(problem(r), "bad_token")                // the drone gave none
        rig.api.checkReply = MissionReply(code: 200, json: checkJSON())
        _ = try await rig.checkProgram()
        rig.droneHost = "10.0.0.8"
        r = try await rig.send(startMessage())
        XCTAssertEqual(problem(r), "bad_token")                // given by another drone
        XCTAssertTrue(rig.asked.isEmpty)
        XCTAssertFalse(rig.api.calls.contains("start"))
    }

    func testTakeoffIsAskedInTheAppWithTheMapTheDroneHas() async throws {
        let rig = Rig()
        let r = try await rig.checkThenStart()
        XCTAssertEqual(code(r), 200)
        XCTAssertEqual((r["data"] as? [String: Any])?["run"] as? String, "run_1")
        XCTAssertEqual(rig.asked, [TakeoffRequest(host: kHost, mapName: "field_real", mapSha: kSha, markerCount: 20,
                                                  programLines: 3, programSha: FlightBridge.sha256Hex(kProgram))])
        XCTAssertEqual(rig.api.startedHost, kHost)
        XCTAssertEqual(rig.api.startedProgram, kProgram)
        XCTAssertEqual(rig.api.startedToken, kToken)
        XCTAssertEqual(rig.api.startedMapSha, kSha)
        XCTAssertEqual(rig.api.calls, ["check:" + kProgram, "status", "start"])
        XCTAssertTrue(rig.bridge.missionActive)
    }

    func testOnePermissionOpensTheDialogOnceAndCancelIsFollowedByAPause() async throws {
        let rig = Rig()
        rig.answer = { _ in .declined() }
        var r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "cancelled")
        XCTAssertEqual(rig.asked.count, 1)
        XCTAssertNil(rig.api.startedHost)
        r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "cancelled")                // the pause: no window, even after a new check
        XCTAssertEqual(rig.asked.count, 1)
        rig.clock.ms += Int64(FlightBridge.cancelPauseSeconds) * 1000 + 1
        r = try await rig.send(startMessage())
        XCTAssertEqual(problem(r), "bad_token")                // that permission went with the refused try
        XCTAssertEqual(rig.asked.count, 1)
        r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "cancelled")                // a new check after the pause: asked again
        XCTAssertEqual(rig.asked.count, 2)
    }

    func testAWindowThatWasNotShownGivesItsReasonAndNoPause() async throws {
        let rig = Rig()
        rig.answer = { _ in .notAsked("the Flight section is not shown now") }
        var r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "not_asked")
        XCTAssertEqual((r["data"] as? [String: Any])?["error"] as? String, "the Flight section is not shown now")
        rig.answer = { _ in .go }
        r = try await rig.checkThenStart()
        XCTAssertEqual(code(r), 200)                            // at once: no pause
    }

    func testAStopWhileTheStartIsOnItsWayWins() async throws {
        let rig = Rig()
        let sent = Gate()
        rig.api.startHold = sent
        let flying = Seen()
        rig.bridge.onTakeoffInFlightChanged = { [unowned rig] in flying.flags.append(rig.bridge.takeoffInFlight) }
        _ = try await rig.checkProgram()
        let start = Task { @MainActor in await rig.bridge.handle(startMessage()) }
        await settle()
        XCTAssertTrue(rig.bridge.takeoffInFlight)
        var r = try await rig.send(kStop)                       // it may reach the drone first: «нечего останавливать»
        XCTAssertEqual(code(r), 200)
        sent.open()
        let startText = await start.value
        r = try XCTUnwrap(JSONSerialization.jsonObject(with: Data((startText ?? "").utf8)) as? [String: Any])
        XCTAssertEqual(problem(r), "stopped")                   // so the bridge stops again after the start
        XCTAssertEqual(rig.api.calls, ["check:" + kProgram, "status", "start", "stop", "stop"])
        XCTAssertEqual(flying.flags, [true, false])

        let app = Rig()                                         // the same with the app's own STOP FLIGHT
        let sent2 = Gate()
        app.api.startHold = sent2
        _ = try await app.checkProgram()
        let start2 = Task { @MainActor in await app.bridge.handle(startMessage()) }
        await settle()
        app.bridge.noteStop()
        sent2.open()
        let text2 = await start2.value
        XCTAssertTrue((text2 ?? "").contains("\"stopped\""), text2 ?? "nil")
        XCTAssertEqual(app.api.calls.last, "stop")
    }

    func testAStartWithoutAnAnswerIsFollowedByAStop() async throws {
        let rig = Rig()
        rig.api.startReply = FlightBridge.problem("silent", "no_answer")
        let r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "no_answer")
        XCTAssertTrue(((r["data"] as? [String: Any])?["error"] as? String ?? "").contains("STOP"))
        XCTAssertEqual(rig.api.calls.last, "stop")
        XCTAssertFalse(rig.bridge.missionActive)
    }

    func testNoDialogWhenAMissionRunsOrTheMapIsNotTheCheckedOneOrTheDroneIsSilent() async throws {
        let rig = Rig()
        let cases: [(MissionReply, String)] = [
            (MissionReply(code: 200, json: statusJSON(running: true)), "busy"),
            (MissionReply(code: 200, json: #"{"map":{"active":null,"confirmed":true}}"#), "busy"),     // «running» missing
            (MissionReply(code: 200, json: statusJSON(confirmed: false)), "map_not_confirmed"),
            (MissionReply(code: 200, json: #"{"running":false,"map":{"active":null,"confirmed":false}}"#), "map_not_confirmed"),
            (MissionReply(code: 200, json: statusJSON(sha: "ffff0000ffff0000")), "changed"),             // not the checked map
            (FlightBridge.problem("silent", "no_answer"), "no_answer"),
            (MissionReply(code: 200, json: "<html>"), "bad_reply"),
        ]
        for (reply, expected) in cases {
            rig.api.statusReply = reply
            let r = try await rig.checkThenStart()
            XCTAssertEqual(problem(r), expected)
        }
        XCTAssertTrue(rig.asked.isEmpty)
        XCTAssertNil(rig.api.startedHost)
    }

    func testWhileTheDialogIsOpenTheMapAndTheProgramStayAndStopStillWorks() async throws {
        let rig = Rig()
        let gate = Gate()
        rig.answer = { _ in
            await gate.wait()
            return .go
        }
        _ = try await rig.checkProgram()
        let first = Task { @MainActor in await rig.bridge.handle(startMessage()) }
        await settle()
        var r = try await rig.send(startMessage())
        XCTAssertEqual(problem(r), "busy")
        let other: [String: Any] = ["name": "other", "markers": [Any]()]
        r = try await rig.send(message("map_put", body: ["map": other]))
        XCTAssertEqual(problem(r), "busy")
        r = try await rig.checkProgram("import drone")
        XCTAssertEqual(problem(r), "busy")
        r = try await rig.send(message("mission_status", id: 2, since: 0))
        XCTAssertEqual(code(r), 200)
        XCTAssertNil(rig.api.mapName)
        XCTAssertFalse(rig.api.calls.contains("check:import drone"))
        gate.open()
        let firstReply = await first.value
        let started = try XCTUnwrap(firstReply)
        XCTAssertTrue(started.contains("\"code\":200"))
        XCTAssertEqual(rig.api.calls.filter { $0 == "start" }.count, 1)

        let stopped = Rig()                                     // a Stop while the window is open: sent, and no takeoff after «yes»
        let late = Gate()
        stopped.answer = { _ in
            await late.wait()
            return .go
        }
        _ = try await stopped.checkProgram()
        let second = Task { @MainActor in await stopped.bridge.handle(startMessage()) }
        await settle()
        r = try await stopped.send(kStop)
        XCTAssertEqual(code(r), 200)
        late.open()
        let secondReply = await second.value
        XCTAssertTrue((secondReply ?? "").contains("\"stopped\""), secondReply ?? "nil")
        XCTAssertNil(stopped.api.startedHost)
        XCTAssertEqual(stopped.api.calls.filter { $0 == "stop" }.count, 1)
    }

    func testAnotherDroneWhileTheDialogIsOpenMeansNoStart() async throws {
        let rig = Rig()
        rig.answer = { [unowned rig] _ in
            rig.droneHost = "10.0.0.8"            // the app was switched meanwhile
            return .go
        }
        let r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "cancelled")
        XCTAssertNil(rig.api.startedHost)
    }

    func testAMissionStartedWithAnotherMapThanShownIsStoppedAtOnce() async throws {
        let rig = Rig()
        rig.api.startReply = MissionReply(code: 200, json: #"{"started":true,"run":"run_1","map_sha":"1111222233334444"}"#)
        let r = try await rig.checkThenStart()
        XCTAssertEqual(problem(r), "map_mismatch")
        XCTAssertEqual(rig.api.calls.last, "stop")
    }

    func testStopAlwaysGoesThrough() async throws {
        let rig = Rig()
        rig.droneHost = ""
        var r = try await rig.send(kStop)
        XCTAssertEqual(code(r), 200)
        for _ in 0..<(FlightBridge.maxMessagesPerSecond + 5) { _ = await rig.bridge.handle(message("hello")) }
        var dropped = await rig.bridge.handle(message("hello"))
        XCTAssertNil(dropped)                                   // over the budget
        // A Stop over the budget is not parsed and not answered, but it still goes to the drone -- once a second at most.
        dropped = await rig.bridge.handle(kStop)
        XCTAssertNil(dropped)
        await settle()
        XCTAssertEqual(rig.api.calls.filter { $0 == "stop" }.count, 2)
        dropped = await rig.bridge.handle(kStop)
        XCTAssertNil(dropped)
        await settle()
        XCTAssertEqual(rig.api.calls.filter { $0 == "stop" }.count, 2)
        rig.clock.ms += 1000
        r = try await rig.send(kStop)
        XCTAssertEqual(code(r), 200)
        XCTAssertEqual(rig.api.calls.filter { $0 == "stop" }.count, 3)
    }

    func testThePageCannotFloodTheAppOrTheDrone() async throws {
        let rig = Rig()
        let status = message("mission_status", since: 0)
        for _ in 0..<FlightBridge.maxMessagesPerSecond {
            let reply = await rig.bridge.handle(status)
            XCTAssertNotNil(reply)
        }
        let dropped = await rig.bridge.handle(status)
        XCTAssertNil(dropped)                                   // the 21st in a second is dropped
        XCTAssertEqual(rig.api.calls.count, FlightBridge.maxMessagesPerSecond)
        let big = "{\"bb\":1,\"id\":1,\"cmd\":\"hello\",\"pad\":\"" + String(repeating: "x", count: FlightBridge.maxCharsPerSecond / 3) + "\"}"
        let chars = Rig()                                       // and so is what is over a million characters a second
        let big1 = await chars.bridge.handle(big)
        let big2 = await chars.bridge.handle(big)
        let big3 = await chars.bridge.handle(big)
        XCTAssertNotNil(big1)
        XCTAssertNotNil(big2)
        XCTAssertNil(big3)
        rig.clock.ms += 1000
        let again = await rig.bridge.handle(status)
        XCTAssertNotNil(again)

        let held = Rig()                                        // one request of a kind at a time
        let gate = Gate()
        held.api.hold = gate
        let first = Task { @MainActor in await held.bridge.handle(status) }
        await settle()
        let second = try await held.send(status)
        XCTAssertEqual(problem(second), "busy")
        let stop1 = Task { @MainActor in await held.bridge.handle(kStop) }
        let stop2 = Task { @MainActor in await held.bridge.handle(kStop) }
        await settle()
        gate.open()
        for task in [first, stop1, stop2] {
            let value = await task.value
            let text = try XCTUnwrap(value)
            XCTAssertTrue(text.contains("\"code\":200"), text)
        }
        XCTAssertEqual(held.api.calls.filter { $0 == "status" }.count, 1)
        XCTAssertEqual(held.api.calls.filter { $0 == "stop" }.count, 1)     // two stops, one request
        let after = try await held.send(status)
        XCTAssertEqual(code(after), 200)
    }

    func testMissionActiveFollowsTheStartAndTheStatus() async throws {
        let rig = Rig()
        let changes = Seen()
        rig.bridge.onMissionActiveChanged = { changes.count += 1 }
        _ = try await rig.checkThenStart()
        XCTAssertTrue(rig.bridge.missionActive)
        rig.clock.ms += 1000
        _ = try await rig.send(message("mission_status", id: 4, since: 0))     // {"running":false,...}
        XCTAssertFalse(rig.bridge.missionActive)
        XCTAssertEqual(changes.count, 2)
    }

    func testTheTakeoffTextCannotBeFakedByAName() {
        let name = "field_real», 20 markers, sha 8a8ab61a53b9 «\nDrone 10.0.0.9"
        let request = TakeoffRequest(host: kHost, mapName: name, mapSha: "1f3c1f3c1f3c1f3c", markerCount: 12,
                                     programLines: 25, programSha: FlightBridge.sha256Hex(kProgram))
        let lines = TakeoffText.body(request, droneName: kHost, link: "OK").components(separatedBy: "\n")
        XCTAssertEqual(lines[0], "Drone 10.0.0.7 will arm the motors and fly the program.")
        XCTAssertTrue(lines[1].hasPrefix("Program: 25 lines, sha " + String(FlightBridge.sha256Hex(kProgram).prefix(12))))
        XCTAssertEqual(lines[2], "Map on the drone: 12 markers, sha 1f3c1f3c1f3c.")
        XCTAssertTrue(lines[3].hasPrefix("Map name: "))
        XCTAssertFalse(lines[3].contains("»"))
        XCTAssertFalse(lines[3].contains(","))
        XCTAssertLessThanOrEqual(TakeoffText.safeName(name).count, TakeoffText.maxNameChars)
        XCTAssertEqual(lines.count, 7)                          // the name added no line
        XCTAssertEqual(TakeoffText.safeName("«»,;\n"), "(no name)")
        XCTAssertEqual(TakeoffText.short("abc123zz"), "abc123")
    }

    func testTheProgramHashIsTheDronesOne() {
        // sha256 of the UTF-8 text, hex, as bb_mission/mission_server.py sha_text() computes it
        XCTAssertEqual(FlightBridge.sha256Hex(""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        XCTAssertEqual(FlightBridge.sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    }

    func testASilentOrBrokenDroneReplyBecomesAnErrorObject() async throws {
        let rig = Rig()
        rig.api.next = MissionReply(code: 502, json: "<html>bad gateway</html>")
        let r = try await rig.send(kStop)
        XCTAssertEqual(code(r), 502)
        XCTAssertNotNil((r["data"] as? [String: Any])?["error"])
    }
}
