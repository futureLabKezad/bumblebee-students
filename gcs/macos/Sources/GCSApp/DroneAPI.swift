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

    struct APIError: LocalizedError { let message: String; var errorDescription: String? { message } }

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

    @discardableResult
    private func ok(_ method: String, _ path: String, json: [String: Any]? = nil) async throws -> Bool {
        let (data, status) = try await request(method, path, json: json)
        if status == 200 { return true }
        if let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let err = obj["error"] as? String {
            throw APIError(message: err)
        }
        throw APIError(message: "HTTP \(status)")
    }

    private func jsonObject(_ method: String, _ path: String,
                            json: [String: Any]? = nil) async throws -> Any {
        let (data, _) = try await request(method, path, json: json)
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

    // MARK: - Sounds / TTS

    /// Returns the server response object (may contain "tune"/"phonemes").
    @discardableResult
    func playTune(_ tune: String, format: String) async throws -> [String: Any] {
        let (data, status) = try await request("POST", "/api/sounds/play",
                                               json: ["tune": tune, "format": format])
        let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        if status != 200 { throw APIError(message: (obj["error"] as? String) ?? "HTTP \(status)") }
        return obj
    }

    @discardableResult
    func tts(text: String, lang: String) async throws -> [String: Any] {
        let (data, status) = try await request("POST", "/api/sounds/tts",
                                               json: ["text": text, "lang": lang])
        let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        if status != 200 { throw APIError(message: (obj["error"] as? String) ?? "HTTP \(status)") }
        return obj
    }

    // MARK: - WiFi / auth

    struct WifiStatus { var mode: String; var ssid: String; var ip: String; var signal: Int }
    struct ScanNet: Identifiable { let id = UUID(); var ssid: String; var signal: Int; var inUse: Bool; var band: String; var freq: Int }

    func wifiStatus() async throws -> WifiStatus {
        let obj = (try await jsonObject("GET", "/api/wifi/status")) as? [String: Any] ?? [:]
        return WifiStatus(mode: obj["mode"] as? String ?? "—",
                          ssid: obj["ssid"] as? String ?? "—",
                          ip: obj["ip"] as? String ?? "—",
                          signal: obj["signal"] as? Int ?? 0)
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
                    freq: $0["freq"] as? Int ?? 0)
        }
    }
    func savedNetworks() async throws -> [String] {
        let arr = (try await jsonObject("GET", "/api/wifi/networks")) as? [[String: Any]] ?? []
        return arr.compactMap { $0["name"] as? String }
    }
    func removeNetwork(_ ssid: String) async throws { try await ok("DELETE", "/api/wifi/network", json: ["ssid": ssid]) }
    func saveNetwork(ssid: String, password: String) async throws { try await ok("POST", "/api/wifi/save", json: ["ssid": ssid, "password": password]) }
    func applyNow(ssid: String) async throws { try await ok("POST", "/api/wifi/apply-now", json: ["ssid": ssid]) }
    func applyBoot(ssid: String) async throws { try await ok("POST", "/api/wifi/apply-boot", json: ["ssid": ssid]) }
}
