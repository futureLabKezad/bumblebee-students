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
import Security

/// Tiny wrapper over the app's own login-keychain for remembering the WiFi
/// password the operator types during drone setup. This is the app's private
/// generic-password item — NOT the System "AirPort" keychain — so reading and
/// writing it never triggers a macOS admin authorization prompt.
enum AppKeychain {
    private static let service = "com.bumblebee.gcs.wifi"

    static func password(for ssid: String) -> String? {
        guard !ssid.isEmpty else { return nil }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: ssid,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess,
              let data = out as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func remove(for ssid: String) {
        guard !ssid.isEmpty else { return }
        let account: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: ssid,
        ]
        SecItemDelete(account as CFDictionary)
    }

    static func setPassword(_ password: String, for ssid: String) {
        guard !ssid.isEmpty else { return }
        let account: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: ssid,
        ]
        SecItemDelete(account as CFDictionary)
        guard let data = password.data(using: .utf8) else { return }
        var add = account
        add[kSecValueData as String] = data
        SecItemAdd(add as CFDictionary, nil)
    }
}
