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

/// HTTP client for the drone's `/api/*` endpoints, served directly by the
/// on-drone backend (`wifi_manager.py`) on :8765. The web dashboard (nginx :80)
/// has been removed; the app talks to 8765 straight, no reverse proxy.
/// Covers LED, sounds/TTS (Entertainment) and wifi/auth (Settings).
final class DroneAPI {
    /// Backend port that `wifi_manager.py` binds (previously behind nginx :80).
    static let port = 8765
    var host = ""
    private let session = URLSession(configuration: .ephemeral)

    /// An error reply of the drone (or "no drone"). `code` is the stable code
    /// drones from 1.0.2 send; the message is already in plain words.
    struct APIError: LocalizedError {
        let message: String
        var code: String? = nil
        var errorDescription: String? { message }
    }

    /// Plain words for any error of a request: the drone's reply, or no answer.
    static func describe(_ error: Error) -> String {
        if let e = error as? APIError { return e.message }
        if let e = error as? URLError { return DroneErrorText.noAnswer(e.localizedDescription) }
        return error.localizedDescription
    }

    /// The stable code of an error reply, if the drone sent one.
    static func code(_ error: Error) -> String? { (error as? APIError)?.code }

    /// True when a request died because the network under it went away (not
    /// because the drone refused it). Drones before the reply-first fix switch
    /// Wi-Fi before answering apply-now, so their reply is always lost this way.
    static func isLinkDrop(_ error: Error) -> Bool {
        guard let e = error as? URLError else { return false }
        return [.timedOut, .networkConnectionLost, .notConnectedToInternet,
                .cannotConnectToHost, .cannotFindHost].contains(e.code)
    }

    private func url(_ path: String) -> URL? { URL(string: "http://\(host):\(Self.port)\(path)") }

    // Generic request returning raw Data + status.
    private func request(_ method: String, _ path: String,
                         json: [String: Any]? = nil) async throws -> (Data, Int) {
        guard !host.isEmpty, let url = url(path) else { throw APIError(message: "no drone") }
        var req = URLRequest(url: url, timeoutInterval: 6.0)
        req.httpMethod = method
        if let json = json {
            req.httpBody = try JSONSerialization.data(withJSONObject: json)
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let (data, resp) = try await session.data(for: req)
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        return (data, status)
    }

    /// The APIError for a reply that is not 200.
    private static func failure(_ data: Data, _ status: Int) -> APIError {
        let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let code = obj?["code"] as? String
        return APIError(message: DroneErrorText.text(code: code, error: obj?["error"] as? String, status: status),
                        code: code)
    }

    /// The reply object of a request that must answer 200.
    @discardableResult
    private func ok(_ method: String, _ path: String, json: [String: Any]? = nil) async throws -> [String: Any] {
        let (data, status) = try await request(method, path, json: json)
        guard status == 200 else { throw Self.failure(data, status) }
        return ((try? JSONSerialization.jsonObject(with: data)) as? [String: Any]) ?? [:]
    }

    /// The JSON reply of a GET that must answer 200 (an error reply is not data).
    private func jsonObject(_ method: String, _ path: String,
                            json: [String: Any]? = nil) async throws -> Any {
        let (data, status) = try await request(method, path, json: json)
        guard status == 200 else { throw Self.failure(data, status) }
        return try JSONSerialization.jsonObject(with: data)
    }

    // MARK: - LED

    func ledColor(r: Int, g: Int, b: Int) async throws {
        try await ok("POST", "/api/led/color", json: ["r": r, "g": g, "b": b])
    }
    func ledAnimation(_ name: String) async throws {
        try await ok("POST", "/api/led/animation", json: ["name": name])
    }
    func ledReset() async throws {
        try await ok("POST", "/api/led/reset")
    }

    /// What the LEDs do now. `remaining` (seconds until an animation stops by
    /// itself) comes from drones 1.0.2+, nil before.
    struct LedStatus: Equatable {
        var ledOK: Bool
        var animation: String?
        var busy: Bool
        var remaining: Int?
    }
    func ledStatus() async throws -> LedStatus {
        let o = (try await jsonObject("GET", "/api/led/status")) as? [String: Any] ?? [:]
        return LedStatus(ledOK: o["led_ok"] as? Bool ?? false,
                         animation: (o["animation"] as? String).flatMap { $0.isEmpty ? nil : $0 },
                         busy: o["busy"] as? Bool ?? false,
                         remaining: o["remaining_s"] as? Int)
    }

    // MARK: - Sounds / TTS

    /// Returns the server response object (may contain "tune"/"phonemes").
    @discardableResult
    func playTune(_ tune: String, format: String) async throws -> [String: Any] {
        try await ok("POST", "/api/sounds/play", json: ["tune": tune, "format": format])
    }

    @discardableResult
    func tts(text: String, lang: String) async throws -> [String: Any] {
        try await ok("POST", "/api/sounds/tts", json: ["text": text, "lang": lang])
    }

    // MARK: - WiFi / auth

    struct WifiStatus {
        var mode: String; var ssid: String; var ip: String; var signal: Int
        /// Drone hardware id (as in its Bonjour TXT record); nil on older drone software.
        var id: String? = nil
        /// Why the drone's last WiFi join requested by the app failed, if it did.
        var lastError: JoinError? = nil
    }
    /// Reported by the drone in /api/wifi/status after a failed apply-now.
    /// `reason`: wrong_password | not_found | no_ip | timeout | failed (1.0.2:
    /// also armed | fc_unknown when it refused at the last moment).
    struct JoinError: Equatable {
        var ssid: String; var reason: String; var message: String
        var time: Date? = nil
    }
    struct ScanNet: Identifiable {
        let id = UUID(); var ssid: String; var signal: Int; var inUse: Bool; var band: String; var freq: Int
        var security: String = ""
        var secured: Bool { WifiNames.isSecured(security) }
    }

    /// Who the drone is (GET /api/info, drones 1.0.2+; nil from older ones).
    struct DroneInfo: Equatable { var name: String; var id: String; var version: String }
    func info() async -> DroneInfo? {
        guard let o = (try? await jsonObject("GET", "/api/info")) as? [String: Any],
              let name = o["name"] as? String else { return nil }
        return DroneInfo(name: name, id: o["id"] as? String ?? "", version: o["version"] as? String ?? "")
    }

    func wifiStatus() async throws -> WifiStatus {
        let obj = (try await jsonObject("GET", "/api/wifi/status")) as? [String: Any] ?? [:]
        return WifiStatus(mode: obj["mode"] as? String ?? "—",
                          ssid: obj["ssid"] as? String ?? "—",
                          ip: obj["ip"] as? String ?? "—",
                          signal: obj["signal"] as? Int ?? 0,
                          id: (obj["id"] as? String).flatMap { $0.isEmpty ? nil : $0 },
                          lastError: (obj["last_error"] as? [String: Any]).map {
                              JoinError(ssid: $0["ssid"] as? String ?? "",
                                        reason: $0["reason"] as? String ?? "failed",
                                        message: $0["message"] as? String ?? "",
                                        time: ($0["time"] as? Double).map { Date(timeIntervalSince1970: $0) })
                          })
    }
    func wifiSetMode(_ mode: String) async throws { try await ok("POST", "/api/wifi/mode", json: ["mode": mode]) }
    func login(pin: String) async throws -> Bool {
        let (_, status) = try await request("POST", "/api/auth/login", json: ["pin": pin])
        return status == 200
    }
    func logout() async throws { _ = try? await request("POST", "/api/auth/logout") }

    func wifiScan() async throws -> [ScanNet] {
        let arr = (try await jsonObject("GET", "/api/wifi/scan")) as? [[String: Any]] ?? []
        return arr.map {
            ScanNet(ssid: $0["ssid"] as? String ?? "",
                    signal: $0["signal"] as? Int ?? 0,
                    inUse: $0["in_use"] as? Bool ?? false,
                    band: $0["band"] as? String ?? "",
                    freq: $0["freq"] as? Int ?? 0,
                    security: $0["security"] as? String ?? "")
        }
    }
    func savedNetworks() async throws -> [String] {
        let arr = (try await jsonObject("GET", "/api/wifi/networks")) as? [[String: Any]] ?? []
        return arr.compactMap { $0["name"] as? String }
    }
    /// `confirmActive`: the user confirmed removing the network the drone uses
    /// now (drones 1.0.2+ refuse it otherwise with code active_network).
    func removeNetwork(_ ssid: String, confirmActive: Bool = false) async throws {
        var body: [String: Any] = ["ssid": ssid]
        if confirmActive { body["confirm_active"] = true }
        try await ok("DELETE", "/api/wifi/network", json: body)
    }
    func saveNetwork(ssid: String, password: String) async throws { try await ok("POST", "/api/wifi/save", json: ["ssid": ssid, "password": password]) }
    func applyNow(ssid: String) async throws { try await ok("POST", "/api/wifi/apply-now", json: ["ssid": ssid]) }
    func applyBoot(ssid: String) async throws { try await ok("POST", "/api/wifi/apply-boot", json: ["ssid": ssid]) }
}
