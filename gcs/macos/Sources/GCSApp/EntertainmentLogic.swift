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

// The Entertainment screen's decisions, kept apart from SwiftUI so GCSAppTests
// can check them. The Windows app follows the same rules
// (Logic/EntertainmentLogic.cs).

enum LedCatalog {
    /// Animations the drone knows (wifi_manager.py ANIMATIONS), LEDs only.
    static let animations = ["breathing", "rainbow", "police", "strobe", "fire", "theater", "rainbow_theater"]
    /// Shows: LEDs plus a buzzer melody the drone repeats while disarmed.
    static let shows = ["party", "siren", "alarm", "victory"]

    /// "rainbow_theater" -> "Rainbow Theater".
    static func label(_ name: String) -> String {
        name.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

/// The buzzer sits on the flight controller: the drone (1.0.2+) refuses tunes
/// and speech unless a fresh, linked state says disarmed, so PX4's own warning
/// tones are never covered. The buttons follow the same rule.
enum SoundGate {
    /// nil: sounds may be sent. `armed` as the dashboard trusts it (nil = unknown).
    static func blockedReason(armed: Bool?) -> String? {
        switch armed {
        case false?: return nil
        case true?: return "Sounds are off while the drone is ARMED, so PX4's own warning tones can be heard."
        case nil: return "Sounds are off: the drone's state is unknown (no live flight-controller data)."
        }
    }
}

enum LedText {
    /// "stops by itself in 1:45" for the seconds the drone reports; nil without.
    static func remaining(_ seconds: Int?) -> String? {
        guard let s = seconds, s > 0 else { return nil }
        return String(format: "stops by itself in %d:%02d", s / 60, s % 60)
    }

    /// The drone accepted the tune; whether the buzzer plays is up to PX4.
    static func sent(_ what: String) -> String { "Sent to the drone: \(what)" }
}
