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

/// Minimal rosbridge v2 client over a WebSocket (ws://host:9090).
///
/// Subscribes to the six telemetry topics the dashboard needs and pushes parsed
/// values into a TelemetryStore on the main thread. Auto-reconnects on drop.
/// The GCS is monitor-only, so this client never publishes or calls services.
///
/// Everything here runs on the main thread (the URLSession delivers there and
/// connect/disconnect come from the UI), so `generation` is checked where the
/// store is written: a message of a socket that has since been closed or
/// replaced by another drone's is dropped, never shown.
final class RosbridgeClient: NSObject {
    private let store: TelemetryStore
    private let port: Int
    private var task: URLSessionWebSocketTask?
    private var session: URLSession!
    private var host = ""
    private var active = false
    /// Bumped by every connect, drop and disconnect.
    private(set) var generation = 0
    private var linked = false              // this socket has answered
    private var watchdog = PingWatchdog()
    private var pingTimer: Timer?

    /// `throttleMs`: rosbridge sends at most one message per interval (0 = all),
    /// keeping only the newest. A linked flight controller streams pose and
    /// velocity at 30 Hz and the IMU at 50 Hz; the screen needs far less, and
    /// rosbridge (Python) plus the Wi-Fi carry ~40 msg/s instead of ~115.
    private struct Sub { let topic: String; let type: String; let throttleMs: Int }
    private let subs: [Sub] = [
        .init(topic: "/mavros/state",                    type: "mavros_msgs/msg/State",          throttleMs: 0),
        .init(topic: "/mavros/statustext/recv",          type: "mavros_msgs/msg/StatusText",     throttleMs: 0),
        .init(topic: "/mavros/battery",                   type: "sensor_msgs/msg/BatteryState",   throttleMs: 1000),
        .init(topic: "/mavros/mavros/pose",               type: "geometry_msgs/msg/PoseStamped",  throttleMs: 100),
        .init(topic: "/mavros/mavros/velocity_local",     type: "geometry_msgs/msg/TwistStamped", throttleMs: 100),
        .init(topic: "/mavros/mavros/data",               type: "sensor_msgs/msg/Imu",            throttleMs: 50),
    ]

    /// `port` is 9090 on every drone; tests point it at a local fake.
    init(store: TelemetryStore, port: Int = 9090) {
        self.store = store
        self.port = port
        super.init()
        session = URLSession(configuration: .ephemeral, delegate: nil, delegateQueue: .main)
    }

    func connect(host: String) {
        disconnect()
        self.host = host
        active = true
        generation += 1
        openSocket(generation)
    }

    func disconnect() {
        active = false
        generation += 1
        closeSocket()
        store.resetForReconnect()
    }

    private func closeSocket() {
        pingTimer?.invalidate()
        pingTimer = nil
        watchdog.reset()
        linked = false
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
    }

    private func openSocket(_ gen: Int) {
        guard active, gen == generation, let url = URL(string: "ws://\(host):\(port)") else { return }
        let t = session.webSocketTask(with: url)
        task = t
        t.resume()
        // rosbridge has no explicit "ready" handshake; subscribe immediately.
        for s in subs { send(subscribe: s) }
        // Ping every 2 s. A pong (or any message) shows the upgrade to :9090
        // has completed; no pong within 4 s means the link died silently
        // (drone off, out of Wi-Fi range), which TCP alone notices only after
        // a minute or more.
        ping(gen)
        let timer = Timer(timeInterval: PingWatchdog.interval, repeats: true) { [weak self] _ in
            self?.ping(gen)
        }
        RunLoop.main.add(timer, forMode: .common)
        pingTimer = timer
        receive(gen)
    }

    private func ping(_ gen: Int) {
        guard active, gen == generation, let t = task else { return }
        let id = watchdog.sent(now: Date())
        t.sendPing { [weak self] error in
            DispatchQueue.main.async {
                guard let self = self, gen == self.generation, error == nil else { return }
                self.watchdog.answered(id)
                self.markLinked(gen)
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + PingWatchdog.timeout + 0.05) { [weak self] in
            guard let self = self, self.active, gen == self.generation else { return }
            if self.watchdog.timedOut(now: Date()) { self.handleDrop(gen) }
        }
    }

    private func markLinked(_ gen: Int) {
        guard !linked, active, gen == generation else { return }
        linked = true
        store.socketOpened(host: host)
    }

    private func send(subscribe s: Sub) {
        var msg: [String: Any] = ["op": "subscribe", "topic": s.topic, "type": s.type]
        if s.throttleMs > 0 {
            msg["throttle_rate"] = s.throttleMs
            msg["queue_length"] = 1
        }
        guard let data = try? JSONSerialization.data(withJSONObject: msg),
              let str = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(str)) { _ in }
    }

    private func receive(_ gen: Int) {
        task?.receive { [weak self] result in
            DispatchQueue.main.async {
                guard let self = self, gen == self.generation else { return }
                switch result {
                case .failure:
                    self.handleDrop(gen)
                case .success(let message):
                    self.markLinked(gen)
                    switch message {
                    case .string(let s): self.deliver(text: s, gen: gen)
                    case .data(let d): self.deliver(text: String(decoding: d, as: UTF8.self), gen: gen)
                    @unknown default: break
                    }
                    self.receive(gen)
                }
            }
        }
    }

    private func handleDrop(_ gen: Int) {
        guard active, gen == generation else { return }
        let wasLinked = linked
        generation += 1
        let next = generation
        closeSocket()
        store.socketDropped(wasLinked: wasLinked)
        // Reconnect after 3 s (matches web behaviour).
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [weak self] in
            guard let self = self, self.active, next == self.generation else { return }
            self.openSocket(next)
        }
    }

    // MARK: - Message parsing

    /// One rosbridge frame of socket `gen`; ignored unless that socket is the
    /// current one. JSON5 parsing accepts the bare NaN that Python's json
    /// writes for an unmeasured battery voltage.
    func deliver(text: String, gen: Int, now: Date = Date()) {
        guard gen == generation,
              let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data, options: [.json5Allowed]) as? [String: Any],
              (obj["op"] as? String) == "publish",
              let topic = obj["topic"] as? String,
              let msg = obj["msg"] as? [String: Any] else { return }
        store.ingest(topic: topic, msg: msg, now: now)
    }
}
