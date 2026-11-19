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

/// HTTP client of the drone's mission server (bb_mission, :8766): the map and the flight
/// program of the «Полёт» section. Exactly the six paths below (gcs/tools/check_watch_only.py
/// lists them); a reply is passed on as it came, a missing answer is code 0.
@MainActor
final class MissionAPI: MissionCommands {
    static let port = 8766

    private let portNumber: Int
    /// Past the system proxy, like DroneAPI. A few connections at most: the page cannot
    /// make the app flood the drone.
    private let session: URLSession
    /// Stop has its own connections: it never waits behind the other requests.
    private let stopSession = URLSession(configuration: .drone)

    private static let timeout: TimeInterval = 12        // POST /api/map waits up to 3 s for the detector's answer
    /// Stop is tried again when the drone did not answer (the command is harmless twice): 9 s in all.
    private static let stopTimeouts: [TimeInterval] = [2, 3, 4]
    private static let maxReplyBytes = 4 * 1024 * 1024

    init(port: Int = MissionAPI.port) {
        portNumber = port
        let config = URLSessionConfiguration.drone
        config.httpMaximumConnectionsPerHost = 4
        session = URLSession(configuration: config)
    }

    func mapStatus(host: String) async -> MissionReply {
        await send(session, Self.timeout, host, "GET", "/api/map/status")
    }

    func putMap(host: String, map: [String: Any]) async -> MissionReply {
        await send(session, Self.timeout, host, "POST", "/api/map", json: ["map": map])
    }

    func check(host: String, program: String) async -> MissionReply {
        await send(session, Self.timeout, host, "POST", "/api/mission/check", json: ["program": program])
    }

    /// Called by FlightBridge only after the person clicked «Взлететь» in the app's own dialog.
    /// Never repeated by itself: the drone's permission is good for one start.
    func start(host: String, program: String, token: String, mapSha: String,
               battery: Bool, rc: Bool, people: Bool) async -> MissionReply {
        let confirm: [String: Any] = ["battery_multimeter": battery, "rc_in_hand_ch8": rc,
                                      "people_clear": people, "takeoff_clicked": true]
        return await send(session, Self.timeout, host, "POST", "/api/mission/start",
                          json: ["program": program, "token": token, "map_sha": mapSha, "confirm": confirm],
                          again: false)
    }

    func stop(host: String) async -> MissionReply {
        var last = MissionReply(code: 0, json: "")
        for timeout in Self.stopTimeouts {
            last = await send(stopSession, timeout, host, "POST", "/api/mission/stop", again: false)
            if last.code != 0 || host.isEmpty { break }     // the drone answered, or there is no drone to ask
        }
        return last
    }

    func status(host: String, since: Int64) async -> MissionReply {
        await send(session, Self.timeout, host, "GET", "/api/mission/status", query: "?since=" + String(since))
    }

    /// `again`: one more try when the connection was dropped under the request (the small
    /// server on the drone closes idle connections, and a request sent into one is lost).
    private func send(_ session: URLSession, _ timeout: TimeInterval, _ host: String, _ method: String,
                      _ path: String, json: [String: Any]? = nil, query: String = "",
                      again: Bool = true) async -> MissionReply {
        if host.isEmpty { return FlightBridge.problem("the app is not connected to a drone", "no_drone") }
        guard let url = URL(string: "http://" + host + ":" + String(portNumber) + path + query) else {
            return Self.silent("wrong drone address")
        }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = method
        if let json = json {
            // JSONSerialization writes Cyrillic as it is, not \uXXXX: the drone limits a body in bytes.
            guard JSONSerialization.isValidJSONObject(json),
                  let body = try? JSONSerialization.data(withJSONObject: json, options: [.withoutEscapingSlashes]) else {
                return FlightBridge.problem("the request cannot be written as JSON", "bad_request")
            }
            request.httpBody = body
            request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        }
        do {
            let (data, response) = try await session.data(for: request)
            if data.count > Self.maxReplyBytes { return Self.silent("the drone’s answer is too large") }
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            return MissionReply(code: code, json: String(decoding: data, as: UTF8.self))
        } catch let error as URLError where error.code == .networkConnectionLost && again {
            return await send(session, timeout, host, method, path, json: json, query: query, again: false)
        } catch {
            return Self.silent(error.localizedDescription)
        }
    }

    private static func silent(_ why: String) -> MissionReply {
        FlightBridge.problem("the mission server on the drone does not answer (it may not be installed on this drone): " + why,
                             "no_answer")
    }
}
