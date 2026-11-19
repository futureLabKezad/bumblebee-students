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
import Network
@testable import GCSApp

/// MissionAPI against a small fake server on a random 127.0.0.1 port (never the drone
/// ports, so a mock drone running on this Mac is left alone): the six paths, their bodies,
/// a dropped connection, a missing answer. The same cases as MissionApiSocketTests of the
/// Windows app.
final class MissionAPITests: XCTestCase {
    private let local = "127.0.0.1"

    @MainActor
    func testTheSixPathsAndTheirBodies() async throws {
        let server = try FakeMissionServer { _, _ in (200, #"{"ok":true}"#) }
        defer { server.stop() }
        let api = MissionAPI(port: Int(server.port))
        var codes: [Int] = []
        codes.append(await api.mapStatus(host: local).code)
        let marker: [String: Any] = ["id": 0]
        let map: [String: Any] = ["name": "m", "markers": [marker]]
        codes.append(await api.putMap(host: local, map: map).code)
        codes.append(await api.check(host: local, program: "import drone  # привет").code)
        codes.append(await api.start(host: local, program: "p", token: "abcd", mapSha: "8a8a",
                                     battery: true, rc: true, people: false).code)
        codes.append(await api.stop(host: local).code)
        codes.append(await api.status(host: local, since: 7).code)
        XCTAssertEqual(codes, [200, 200, 200, 200, 200, 200])

        let seen = server.requests
        XCTAssertEqual(seen.map { $0.method + " " + $0.target }, [
            "GET /api/map/status", "POST /api/map", "POST /api/mission/check", "POST /api/mission/start",
            "POST /api/mission/stop", "GET /api/mission/status?since=7",
        ])
        guard seen.count == 6 else { return }
        let put = try XCTUnwrap(Self.object(seen[1].body))
        let markers = try XCTUnwrap((put["map"] as? [String: Any])?["markers"] as? [[String: Any]])
        XCTAssertEqual(markers.first?["id"] as? Int, 0)
        XCTAssertTrue(seen[2].body.contains("привет"), "Cyrillic as it is: the drone limits the body in bytes")
        let start = try XCTUnwrap(Self.object(seen[3].body))
        let confirm = try XCTUnwrap(start["confirm"] as? [String: Any])
        XCTAssertEqual(confirm["battery_multimeter"] as? Bool, true)
        XCTAssertEqual(confirm["rc_in_hand_ch8"] as? Bool, true)
        XCTAssertEqual(confirm["people_clear"] as? Bool, false)
        XCTAssertEqual(confirm["takeoff_clicked"] as? Bool, true)
        XCTAssertEqual(start["token"] as? String, "abcd")
        XCTAssertEqual(start["map_sha"] as? String, "8a8a")
        XCTAssertEqual(seen[4].body, "", "Stop carries nothing")
    }

    @MainActor
    func testADronesRefusalIsPassedOnAsItCame() async throws {
        let server = try FakeMissionServer { _, _ in (409, #"{"error":"дрон взведён","code":"armed"}"#) }
        defer { server.stop() }
        let reply = await MissionAPI(port: Int(server.port)).check(host: local, program: "x")
        XCTAssertEqual(reply.code, 409)
        XCTAssertTrue(reply.json.contains("armed"))
    }

    @MainActor
    func testStopAndACheckAreTriedAgainWhenTheConnectionIsDropped() async throws {
        // every odd request is dropped without an answer, every even one is answered
        let server = try FakeMissionServer { _, number in number % 2 == 1 ? nil : (200, #"{"result":"ok"}"#) }
        defer { server.stop() }
        let api = MissionAPI(port: Int(server.port))
        let stopped = await api.stop(host: local)
        XCTAssertEqual(stopped.code, 200)
        XCTAssertEqual(server.requests.count, 2)
        let checked = await api.check(host: local, program: "x")
        XCTAssertEqual(checked.code, 200)
        XCTAssertEqual(server.requests.count, 4)
    }

    @MainActor
    func testAStartIsNeverSentTwice() async throws {
        let server = try FakeMissionServer { _, _ in nil }          // the connection drops, the answer is lost
        defer { server.stop() }
        let reply = await MissionAPI(port: Int(server.port)).start(host: local, program: "p", token: "abcd",
                                                                   mapSha: "8a8a", battery: true, rc: true, people: true)
        XCTAssertEqual(reply.code, 0)
        XCTAssertEqual(server.requests.count, 1)
    }

    @MainActor
    func testNoServerOrNoDroneIsCodeZero() async throws {
        let server = try FakeMissionServer { _, _ in (200, "{}") }
        let port = Int(server.port)
        server.stop()                                               // nothing listens on this port any more
        let silent = await MissionAPI(port: port).mapStatus(host: local)
        XCTAssertEqual(silent.code, 0)
        XCTAssertTrue(silent.json.contains("no_answer"))
        let none = await MissionAPI().stop(host: "")
        XCTAssertEqual(none.code, 0)
        XCTAssertTrue(none.json.contains("no_drone"))
    }

    private static func object(_ json: String) -> [String: Any]? {
        (try? JSONSerialization.jsonObject(with: Data(json.utf8))) as? [String: Any]
    }
}

/// A tiny HTTP/1.1 server standing in for the drone's mission server (bb_mission, :8766):
/// one request per connection; the test's closure gives the reply, or nil to drop the
/// connection without one. The closure runs on the server's queue.
private final class FakeMissionServer {
    struct Request {
        var method: String
        var target: String
        var body: String
    }

    private let queue = DispatchQueue(label: "fake.mission")
    private let listener: NWListener
    private let handler: @Sendable (Request, Int) -> (Int, String)?
    private var _requests: [Request] = []
    private(set) var port: UInt16 = 0

    var requests: [Request] { queue.sync { _requests } }

    init(_ handler: @escaping @Sendable (Request, Int) -> (Int, String)?) throws {
        self.handler = handler
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        listener = try NWListener(using: params)
        let ready = DispatchSemaphore(value: 0)
        listener.stateUpdateHandler = { if case .ready = $0 { ready.signal() } }
        listener.newConnectionHandler = { [weak self] connection in self?.accept(connection) }
        listener.start(queue: queue)
        guard ready.wait(timeout: .now() + 3) == .success, let p = listener.port?.rawValue else {
            throw NSError(domain: "FakeMissionServer", code: 1)
        }
        port = p
    }

    func stop() {
        listener.cancel()
    }

    private func accept(_ connection: NWConnection) {
        connection.start(queue: queue)
        read(connection, Data())
    }

    private func read(_ connection: NWConnection, _ soFar: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, isComplete, error in
            guard let self = self else { connection.cancel(); return }
            var buffer = soFar
            if let data = data { buffer.append(data) }
            if let request = Self.parse(buffer) {
                self.answer(connection, request)
            } else if isComplete || error != nil {
                connection.cancel()
            } else {
                self.read(connection, buffer)
            }
        }
    }

    private func answer(_ connection: NWConnection, _ request: Request) {
        _requests.append(request)
        guard let (code, json) = handler(request, _requests.count) else {
            connection.cancel()
            return
        }
        let body = Data(json.utf8)
        var reply = Data(("HTTP/1.1 \(code) X\r\nContent-Type: application/json; charset=utf-8\r\n"
            + "Content-Length: \(body.count)\r\nConnection: close\r\n\r\n").utf8)
        reply.append(body)
        connection.send(content: reply, completion: .contentProcessed { _ in connection.cancel() })
    }

    /// The request once its head and its whole body (Content-Length) are in the buffer.
    private static func parse(_ buffer: Data) -> Request? {
        guard let split = buffer.range(of: Data("\r\n\r\n".utf8)) else { return nil }
        let head = String(decoding: buffer[buffer.startIndex..<split.lowerBound], as: UTF8.self)
        let lines = head.components(separatedBy: "\r\n")
        let first = (lines.first ?? "").split(separator: " ").map(String.init)
        guard first.count >= 2 else { return nil }
        var length = 0
        for line in lines.dropFirst() {
            let parts = line.split(separator: ":", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
            if parts.count == 2, parts[0].lowercased() == "content-length" { length = Int(parts[1]) ?? 0 }
        }
        let bodyStart = split.upperBound
        guard buffer.endIndex - bodyStart >= length else { return nil }
        let body = String(decoding: buffer[bodyStart..<(bodyStart + length)], as: UTF8.self)
        return Request(method: first[0], target: first[1], body: body)
    }
}
