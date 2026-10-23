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
import AppKit
@testable import GCSApp

/// The real RosbridgeClient and MJPEGStream against small fake servers on a
/// random 127.0.0.1 port (never the drone ports, so a mock drone running on
/// this Mac is left alone). Slow-ish: the keep-alive timings are real.
final class SocketTests: XCTestCase {

    /// Runs the main run loop (where the clients live) until `cond` holds.
    @discardableResult
    private func spin(until timeout: TimeInterval, _ cond: () -> Bool) -> Bool {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            if cond() { return true }
            RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        }
        return cond()
    }

    // MARK: - rosbridge: link states, silent drop, reconnect

    func testRosbridgeFrozenSilentDropAndReconnect() throws {
        let server = try FakeRosbridge()
        let store = TelemetryStore()
        var alerts = 0
        store.playAlert = { alerts += 1 }
        let client = RosbridgeClient(store: store, port: Int(server.port))
        store.startClock()
        defer { client.disconnect(); store.stopClock(); server.stop() }

        client.connect(host: "127.0.0.1")
        XCTAssertTrue(spin(until: 3) { store.link == .ok }, "link OK on fresh connected State")
        XCTAssertEqual(store.armedDisplay, .armed)
        XCTAssertEqual(server.subscribedTopics.count, 6)
        XCTAssertEqual(server.ops, ["subscribe"], "the app only subscribes")

        // Socket open, nothing published: "Telemetry frozen" after 3 s.
        server.publishing = false
        let frozeAt = Date()
        XCTAssertTrue(spin(until: 5) { store.link == .telemetryFrozen })
        XCTAssertLessThan(Date().timeIntervalSince(frozeAt), 4.5)
        XCTAssertEqual(alerts, 1, "armed drone lost its FC data: one alert")
        XCTAssertTrue(store.fcLost)
        XCTAssertEqual(store.armedDisplay, .armedLinkLost)

        // The peer stops answering pings (drone off): dropped within ping
        // interval + timeout.
        server.answerPings = false
        let silentAt = Date()
        XCTAssertTrue(spin(until: 8) { store.link == .noDrone && !store.rosConnected })
        XCTAssertLessThan(Date().timeIntervalSince(silentAt), 6.6)
        XCTAssertTrue(store.logs.contains { $0.text == "rosbridge lost — reconnecting…" })

        // The drone is back: the client reconnects by itself.
        server.answerPings = true
        server.publishing = true
        XCTAssertTrue(spin(until: 7) { store.link == .ok }, "reconnected after the 3 s pause")
        XCTAssertFalse(store.fcLost, "banner clears once the link is OK")
        XCTAssertEqual(alerts, 1)
        XCTAssertGreaterThanOrEqual(server.accepted, 2)
    }

    func testRosbridgeFCNotConnected() throws {
        let server = try FakeRosbridge()
        server.fcConnected = false
        let store = TelemetryStore()
        store.playAlert = {}
        let client = RosbridgeClient(store: store, port: Int(server.port))
        defer { client.disconnect(); server.stop() }
        client.connect(host: "127.0.0.1")
        XCTAssertTrue(spin(until: 3) { store.link == .fcNotConnected })
        XCTAssertEqual(store.armedDisplay, .unknown, "never DISARMED without a connected FC")
    }

    func testRosbridgeNoServerIsNoDroneAndOneCollapsedLine() throws {
        let server = try FakeRosbridge()
        let port = Int(server.port)
        server.stop()   // nothing listens on this port any more
        let store = TelemetryStore()
        let client = RosbridgeClient(store: store, port: port)
        defer { client.disconnect() }
        client.connect(host: "127.0.0.1")
        spin(until: 7.5) { false }
        XCTAssertEqual(store.link, .noDrone)
        let down = store.logs.filter { $0.key == "rosbridge-down" }
        XCTAssertEqual(down.count, 1)
        XCTAssertGreaterThanOrEqual(down.first?.count ?? 0, 2, "retries counted on one line")
        XCTAssertEqual(down.first?.text, "rosbridge not reachable — retrying…")
    }

    // MARK: - MJPEG: one connection, no stale frame, reconnect

    func testSwitchingTopicsKeepsExactlyOneConnection() throws {
        let server = try FakeMJPEGServer()
        defer { server.stop() }
        let stream = MJPEGStream()
        defer { stream.stop() }
        let base = "http://127.0.0.1:\(server.port)/stream?topic="
        stream.start(url: URL(string: base + "a")!)
        XCTAssertTrue(spin(until: 3) { stream.image != nil }, "frames arrive")
        XCTAssertNotNil(stream.lastFrameAt)

        for i in 0..<20 {
            stream.start(url: URL(string: base + (i % 2 == 0 ? "b" : "a"))!)
            XCTAssertNil(stream.image, "a new topic never shows the old topic's frame")
            spin(until: 0.05) { false }
        }
        XCTAssertTrue(spin(until: 3) { server.openConnections == 1 && stream.image != nil },
                      "open: \(server.openConnections)")
        spin(until: 0.5) { false }
        XCTAssertEqual(server.openConnections, 1)

        stream.stop()
        XCTAssertTrue(spin(until: 3) { server.openConnections == 0 }, "stop closes it")
    }

    func testStreamComesBackAfterTheServerDropsIt() throws {
        let server = try FakeMJPEGServer()
        defer { server.stop() }
        let stream = MJPEGStream()
        defer { stream.stop() }
        stream.start(url: URL(string: "http://127.0.0.1:\(server.port)/stream?topic=a")!)
        XCTAssertTrue(spin(until: 3) { stream.image != nil })
        server.dropAll()
        XCTAssertTrue(spin(until: 5) { server.accepted >= 2 && server.openConnections == 1 },
                      "reopened by itself")
    }

    func testSilentServerIsDroppedByTheIdleWatchdog() throws {
        let server = try FakeMJPEGServer()
        defer { server.stop() }
        let stream = MJPEGStream()
        stream.idleTimeout = 1.0      // 10 s on the drone; shortened here
        defer { stream.stop() }
        stream.start(url: URL(string: "http://127.0.0.1:\(server.port)/stream?topic=a")!)
        XCTAssertTrue(spin(until: 3) { stream.image != nil })
        server.sending = false        // socket stays open, no bytes: a powered-off drone
        let first = stream.lastFrameAt
        XCTAssertTrue(spin(until: 6) { server.accepted >= 2 }, "half-open connection replaced")
        XCTAssertEqual(stream.lastFrameAt, first, "no new frame while silent")
        XCTAssertNotNil(stream.image, "the old frame stays, under the Video lost overlay")
        server.sending = true
        XCTAssertTrue(spin(until: 5) { (stream.lastFrameAt ?? .distantPast) > (first ?? .distantPast) },
                      "video resumes")
    }
}

// MARK: - Fake rosbridge (WebSocket)

/// Publishes /mavros/state at 5 Hz; answers pings only while `answerPings`.
private final class FakeRosbridge {
    private let queue = DispatchQueue(label: "fake.rosbridge")
    private let listener: NWListener
    private var conns: [NWConnection] = []
    private var timer: DispatchSourceTimer?
    private var _publishing = true, _answer = true, _fc = true
    private var _topics = Set<String>(), _ops = Set<String>(), _accepted = 0

    var publishing: Bool { get { queue.sync { _publishing } } set { queue.sync { _publishing = newValue } } }
    var answerPings: Bool { get { queue.sync { _answer } } set { queue.sync { _answer = newValue } } }
    var fcConnected: Bool { get { queue.sync { _fc } } set { queue.sync { _fc = newValue } } }
    var subscribedTopics: Set<String> { queue.sync { _topics } }
    var ops: [String] { queue.sync { _ops.sorted() } }
    var accepted: Int { queue.sync { _accepted } }
    private(set) var port: UInt16 = 0

    init() throws {
        let ws = NWProtocolWebSocket.Options()
        ws.autoReplyPing = false
        let params = NWParameters.tcp
        params.defaultProtocolStack.applicationProtocols.insert(ws, at: 0)
        params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        listener = try NWListener(using: params)
        let ready = DispatchSemaphore(value: 0)
        listener.stateUpdateHandler = { if case .ready = $0 { ready.signal() } }
        listener.newConnectionHandler = { [weak self] c in self?.accept(c) }
        listener.start(queue: queue)
        guard ready.wait(timeout: .now() + 3) == .success, let p = listener.port?.rawValue else {
            throw NSError(domain: "FakeRosbridge", code: 1)
        }
        port = p
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now(), repeating: 0.2)
        t.setEventHandler { [weak self] in self?.publish() }
        t.resume()
        timer = t
    }

    func stop() {
        timer?.cancel()
        listener.cancel()
        queue.sync { conns.forEach { $0.cancel() }; conns.removeAll() }
    }

    private func accept(_ c: NWConnection) {
        _accepted += 1
        conns.append(c)
        c.start(queue: queue)
        receive(c)
    }

    private func receive(_ c: NWConnection) {
        c.receiveMessage { [weak self] data, ctx, _, error in
            guard let self = self else { return }
            if error != nil { c.cancel(); self.conns.removeAll { $0 === c }; return }
            let meta = ctx?.protocolMetadata(definition: NWProtocolWebSocket.definition) as? NWProtocolWebSocket.Metadata
            switch meta?.opcode {
            case .ping?:
                if self._answer {
                    let pong = NWProtocolWebSocket.Metadata(opcode: .pong)
                    let out = NWConnection.ContentContext(identifier: "pong", metadata: [pong])
                    c.send(content: data ?? Data(), contentContext: out, isComplete: true, completion: .idempotent)
                }
            case .text?:
                if let d = data, let obj = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                    if let op = obj["op"] as? String { self._ops.insert(op) }
                    if let topic = obj["topic"] as? String { self._topics.insert(topic) }
                }
            case .close?:
                c.cancel(); self.conns.removeAll { $0 === c }; return
            default: break
            }
            self.receive(c)
        }
    }

    private func publish() {
        guard _publishing else { return }
        let msg: [String: Any] = ["op": "publish", "topic": "/mavros/state",
                                  "msg": ["connected": _fc, "armed": _fc, "mode": _fc ? "OFFBOARD" : ""]]
        guard let data = try? JSONSerialization.data(withJSONObject: msg) else { return }
        let meta = NWProtocolWebSocket.Metadata(opcode: .text)
        let ctx = NWConnection.ContentContext(identifier: "text", metadata: [meta])
        for c in conns where c.state == .ready {
            c.send(content: data, contentContext: ctx, isComplete: true, completion: .idempotent)
        }
    }
}

// MARK: - Fake MJPEG server (HTTP multipart)

/// Serves a small JPEG every 100 ms as multipart/x-mixed-replace, like
/// ros_mjpeg_server.py, and counts open connections.
private final class FakeMJPEGServer {
    private let queue = DispatchQueue(label: "fake.mjpeg")
    private let listener: NWListener
    private var conns: [NWConnection] = []
    private var timer: DispatchSourceTimer?
    private var _accepted = 0, _sending = true, _lastPath = ""
    private let jpeg: Data
    private(set) var port: UInt16 = 0

    var accepted: Int { queue.sync { _accepted } }
    var openConnections: Int { queue.sync { conns.count } }
    var sending: Bool { get { queue.sync { _sending } } set { queue.sync { _sending = newValue } } }
    var lastPath: String { queue.sync { _lastPath } }

    init() throws {
        let img = NSImage(size: NSSize(width: 8, height: 8))
        img.lockFocus(); NSColor.red.setFill(); NSRect(x: 0, y: 0, width: 8, height: 8).fill(); img.unlockFocus()
        guard let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
              let j = rep.representation(using: .jpeg, properties: [:]) else {
            throw NSError(domain: "FakeMJPEGServer", code: 2)
        }
        jpeg = j
        let params = NWParameters.tcp
        params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: .any)
        listener = try NWListener(using: params)
        let ready = DispatchSemaphore(value: 0)
        listener.stateUpdateHandler = { if case .ready = $0 { ready.signal() } }
        listener.newConnectionHandler = { [weak self] c in self?.accept(c) }
        listener.start(queue: queue)
        guard ready.wait(timeout: .now() + 3) == .success, let p = listener.port?.rawValue else {
            throw NSError(domain: "FakeMJPEGServer", code: 1)
        }
        port = p
        let t = DispatchSource.makeTimerSource(queue: queue)
        t.schedule(deadline: .now(), repeating: 0.1)
        t.setEventHandler { [weak self] in self?.sendFrames() }
        t.resume()
        timer = t
    }

    func stop() {
        timer?.cancel()
        listener.cancel()
        queue.sync { conns.forEach { $0.cancel() }; conns.removeAll() }
    }

    /// Server restart: every client connection is closed.
    func dropAll() {
        queue.sync { conns.forEach { $0.cancel() }; conns.removeAll() }
    }

    private func accept(_ c: NWConnection) {
        _accepted += 1
        c.stateUpdateHandler = { [weak self] st in
            switch st {
            case .failed, .cancelled: self?.conns.removeAll { $0 === c }
            default: break
            }
        }
        c.start(queue: queue)
        c.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] data, _, _, _ in
            guard let self = self, let d = data, let req = String(data: d, encoding: .utf8) else { c.cancel(); return }
            self._lastPath = req.split(separator: " ").dropFirst().first.map(String.init) ?? ""
            let head = "HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n"
                + "Cache-Control: no-cache\r\nConnection: close\r\n\r\n"
            c.send(content: head.data(using: .utf8), completion: .idempotent)
            self.conns.append(c)
            self.watchClose(c)
        }
    }

    /// The client closing shows up as EOF on read.
    private func watchClose(_ c: NWConnection) {
        c.receive(minimumIncompleteLength: 1, maximumLength: 4096) { [weak self] _, _, isComplete, error in
            if isComplete || error != nil {
                c.cancel()
                self?.conns.removeAll { $0 === c }
            } else {
                self?.watchClose(c)
            }
        }
    }

    private func sendFrames() {
        guard _sending else { return }
        var part = "--frame\r\nContent-Type: image/jpeg\r\nContent-Length: \(jpeg.count)\r\n\r\n".data(using: .utf8)!
        part.append(jpeg)
        part.append("\r\n".data(using: .utf8)!)
        for c in conns {
            c.send(content: part, completion: .contentProcessed { [weak self] err in
                if err != nil { c.cancel(); self?.conns.removeAll { $0 === c } }
            })
        }
    }
}
