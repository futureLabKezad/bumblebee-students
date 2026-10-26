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

/// Entertainment decisions: when sounds may be sent, the countdown text and
/// the names the drone knows.
final class EntertainmentLogicTests: XCTestCase {
    func testSoundsOnlyWhenDisarmedIsKnown() {
        XCTAssertNil(SoundGate.blockedReason(armed: false))
        XCTAssertTrue(SoundGate.blockedReason(armed: true)!.contains("ARMED"))
        XCTAssertTrue(SoundGate.blockedReason(armed: nil)!.contains("unknown"))
    }

    func testRemaining() {
        XCTAssertEqual(LedText.remaining(105), "stops by itself in 1:45")
        XCTAssertEqual(LedText.remaining(7), "stops by itself in 0:07")
        XCTAssertNil(LedText.remaining(0))
        XCTAssertNil(LedText.remaining(nil), "drones before 1.0.2 send no countdown")
    }

    func testSentIsNotPlayed() {
        XCTAssertEqual(LedText.sent("beep"), "Sent to the drone: beep")
    }

    func testCatalogMatchesTheDrone() {
        // wifi_manager.py: ANIMATIONS = 7 LED animations | SHOWS (4).
        XCTAssertEqual(Set(LedCatalog.animations),
                       ["breathing", "rainbow", "police", "strobe", "fire", "theater", "rainbow_theater"])
        XCTAssertEqual(Set(LedCatalog.shows), ["party", "siren", "alarm", "victory"])
        XCTAssertEqual(LedCatalog.label("rainbow_theater"), "Rainbow Theater")
    }
}
