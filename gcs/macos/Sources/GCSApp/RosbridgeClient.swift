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
final class RosbridgeClient: NSObject {
    private let store: TelemetryStore
    private var task: URLSessionWebSocketTask?
    private var session: URLSession!
    private var host = ""
    private var active = false
    private var generation = 0

    private struct Sub { let topic: String; let type: String }
    private let subs: [Sub] = [
        .init(topic: "/mavros/state",                    type: "mavros_msgs/msg/State"),
        .init(topic: "/mavros/statustext/recv",          type: "mavros_msgs/msg/StatusText"),
        .init(topic: "/mavros/battery",                   type: "sensor_msgs/msg/BatteryState"),
        .init(topic: "/mavros/mavros/pose",               type: "geometry_msgs/msg/PoseStamped"),
        .init(topic: "/mavros/mavros/velocity_local",     type: "geometry_msgs/msg/TwistStamped"),
        .init(topic: "/mavros/mavros/data",               type: "sensor_msgs/msg/Imu"),
    ]

    init(store: TelemetryStore) {
        self.store = store
        super.init()
        session = URLSession(configuration: .ephemeral)
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
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        DispatchQueue.main.async { self.store.resetForReconnect() }
    }

    private func openSocket(_ gen: Int) {
        guard active, gen == generation, let url = URL(string: "ws://\(host):9090") else { return }
        let t = session.webSocketTask(with: url)
        task = t
        t.resume()
        // rosbridge has no explicit "ready" handshake; subscribe immediately.
        for s in subs { send(subscribe: s) }
        // Only report "linked" once the socket really answers: a WebSocket
        // ping succeeds only after the upgrade to :9090 has completed.
        t.sendPing { [weak self] error in
            guard let self = self, error == nil, gen == self.generation, self.active else { return }
            DispatchQueue.main.async {
                self.store.rosConnected = true
                self.store.log("rosbridge connected (\(self.host))")
            }
        }
        receive(gen)
    }

    private func send(subscribe s: Sub) {
        let msg: [String: Any] = ["op": "subscribe", "topic": s.topic, "type": s.type]
        guard let data = try? JSONSerialization.data(withJSONObject: msg),
              let str = String(data: data, encoding: .utf8) else { return }
        task?.send(.string(str)) { _ in }
    }

    private func receive(_ gen: Int) {
        task?.receive { [weak self] result in
            guard let self = self, gen == self.generation else { return }
            switch result {
            case .failure:
                self.handleDrop(gen)
            case .success(let message):
                switch message {
                case .string(let s): self.handle(text: s)
                case .data(let d): self.handle(text: String(decoding: d, as: UTF8.self))
                @unknown default: break
                }
                self.receive(gen)
            }
        }
    }

    private func handleDrop(_ gen: Int) {
        guard active, gen == generation else { return }
        DispatchQueue.main.async {
            self.store.rosConnected = false
            self.store.log("rosbridge lost — reconnecting…")
        }
        // Reconnect after 3 s (matches web behaviour).
        DispatchQueue.global().asyncAfter(deadline: .now() + 3) { [weak self] in
            guard let self = self, self.active, gen == self.generation else { return }
            self.openSocket(gen)
        }
    }

    // MARK: - Message parsing

    private func handle(text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              (obj["op"] as? String) == "publish",
              let topic = obj["topic"] as? String,
              let msg = obj["msg"] as? [String: Any] else { return }

        DispatchQueue.main.async { self.apply(topic: topic, msg: msg) }
    }

    private func apply(topic: String, msg: [String: Any]) {
        switch topic {
        case "/mavros/state":
            if let mode = msg["mode"] as? String, mode != store.mode {
                store.mode = mode
                store.log("mode → \(mode)")
            }
            if let armed = msg["armed"] as? Bool { store.armed = armed }
            store.touched()

        case "/mavros/statustext/recv":
            let sev = (msg["severity"] as? Int) ?? 99
            if sev <= 4, let txt = msg["text"] as? String { store.log("[FCU] \(txt)") }

        case "/mavros/battery":
            let v = (msg["voltage"] as? Double) ?? Double.nan
            let pRaw = (msg["percentage"] as? Double) ?? Double.nan
            if v.isFinite && v > 0 && v < 60 { store.batteryVoltage = v } else { store.batteryVoltage = nil }
            var pct: Double? = nil
            if pRaw.isFinite && pRaw >= 0 && pRaw <= 1 {
                pct = pRaw * 100
            } else if let v = store.batteryVoltage {
                pct = max(0, min(100, (v / 6 - 3.3) / (4.2 - 3.3) * 100)) // 6S estimate
            }
            store.batteryPct = pct
            if let pct = pct {
                store.pushChart(\.chartBat, pct)
                if pct < 15, let v = store.batteryVoltage {
                    store.log(String(format: "WARNING LOW BATTERY: %.2f V", v))
                }
            }
            store.touched()

        case "/mavros/mavros/pose":
            guard let pose = msg["pose"] as? [String: Any],
                  let p = pose["position"] as? [String: Any],
                  let o = pose["orientation"] as? [String: Any] else { return }
            store.posX = (p["x"] as? Double) ?? 0
            store.posY = (p["y"] as? Double) ?? 0
            store.posZ = (p["z"] as? Double) ?? 0
            let e = quatToEuler((o["x"] as? Double) ?? 0, (o["y"] as? Double) ?? 0,
                                (o["z"] as? Double) ?? 0, (o["w"] as? Double) ?? 1)
            store.roll = e.roll; store.pitch = e.pitch; store.yaw = e.yaw
            store.pushTrail(store.posX, store.posY)
            store.pushChart(\.chartAlt, store.posZ)
            store.touched()

        case "/mavros/mavros/velocity_local":
            guard let twist = msg["twist"] as? [String: Any],
                  let l = twist["linear"] as? [String: Any] else { return }
            store.vx = (l["x"] as? Double) ?? 0
            store.vy = (l["y"] as? Double) ?? 0
            store.vz = (l["z"] as? Double) ?? 0
            store.pushChart(\.chartSpd, store.speedH)
            store.touched()

        case "/mavros/mavros/data":
            guard let av = msg["angular_velocity"] as? [String: Any],
                  let la = msg["linear_acceleration"] as? [String: Any] else { return }
            let gx = (av["x"] as? Double) ?? 0, gy = (av["y"] as? Double) ?? 0, gz = (av["z"] as? Double) ?? 0
            let ax = (la["x"] as? Double) ?? 0, ay = (la["y"] as? Double) ?? 0, az = (la["z"] as? Double) ?? 0
            store.gyroMag = (gx * gx + gy * gy + gz * gz).squareRoot() * 180 / Double.pi
            store.accelMag = (ax * ax + ay * ay + az * az).squareRoot()

        default: break
        }
    }
}
