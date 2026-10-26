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

/// Settings decisions: error texts, password rules, protected networks, same
/// drone, what happens after Apply Now, and finding the drone again.
final class SettingsLogicTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 5_000_000)

    // MARK: - Error replies

    func testCodesWinOverTheDronesText() {
        XCTAssertTrue(DroneErrorText.text(code: "armed", error: "x", status: 409).contains("ARMED"))
        XCTAssertTrue(DroneErrorText.text(code: "fc_unknown", error: "x", status: 503).contains("counts as armed"))
        XCTAssertTrue(DroneErrorText.text(code: "bad_password_length", error: "x", status: 400).contains("8 to 63"))
        XCTAssertTrue(DroneErrorText.text(code: "protected_network", error: "x", status: 409).contains("hotspot"))
    }

    func testOlderDronesTextIsShownAsItIs() {
        XCTAssertEqual(DroneErrorText.text(code: nil, error: "led unavailable", status: 503), "led unavailable")
        XCTAssertEqual(DroneErrorText.text(code: "something_new", error: "new text", status: 400), "new text")
        XCTAssertEqual(DroneErrorText.text(code: nil, error: nil, status: 500), "HTTP 500")
    }

    func testJoinReasons() {
        XCTAssertEqual(JoinReasonText.text(reason: "wrong_password", ssid: "Lab"), "wrong password for Lab")
        XCTAssertEqual(JoinReasonText.text(reason: "not_found", ssid: "Lab"), "the drone can't see Lab")
        XCTAssertTrue(JoinReasonText.text(reason: "fc_unknown", ssid: "Lab").contains("armed"))
        XCTAssertEqual(JoinReasonText.text(reason: "failed", ssid: "Lab"), "the drone couldn't join Lab")
    }

    func testOldFailureIsNotShownForever() {
        let fresh = JoinReasonText.banner(ssid: "Lab", reason: "wrong_password", time: t0, now: t0.addingTimeInterval(60))
        XCTAssertNotNil(fresh)
        XCTAssertTrue(fresh!.contains("wrong password for Lab"))
        XCTAssertNil(JoinReasonText.banner(ssid: "Lab", reason: "wrong_password", time: t0,
                                           now: t0.addingTimeInterval(31 * 60)))
        XCTAssertNotNil(JoinReasonText.banner(ssid: "Lab", reason: "timeout", time: nil, now: t0),
                        "older drones send no time: shown without one")
    }

    // MARK: - Networks

    func testProtectedNames() {
        for n in ["bumblebee-hotspot", "Bumblebee-20EC", "BUMBLEBEE-ABCD", " bumblebee-x ", "Lab.bb-pending"] {
            XCTAssertTrue(WifiNames.isProtected(n), n)
        }
        for n in ["Lab", "Bumblebees", "my-bumblebee-net", ""] {
            XCTAssertFalse(WifiNames.isProtected(n), n)
        }
    }

    func testSecurity() {
        XCTAssertTrue(WifiNames.isSecured("WPA2"))
        XCTAssertTrue(WifiNames.isSecured("WPA1 WPA2"))
        XCTAssertFalse(WifiNames.isSecured(""))
        XCTAssertFalse(WifiNames.isSecured("--"))
        XCTAssertFalse(WifiNames.isSecured(" -- "))
    }

    func testScanSSIDMatchesItsProfile() {
        XCTAssertTrue(WifiNames.same(ssid: "Classroom", profile: "Classroom"))
        XCTAssertTrue(WifiNames.same(ssid: "Classroom", profile: "netplan-wlan0-Classroom"))
        XCTAssertFalse(WifiNames.same(ssid: "Class", profile: "Classroom"))
        XCTAssertFalse(WifiNames.same(ssid: "", profile: ""))
    }

    // MARK: - Passwords

    func testPasswordLength() {
        XCTAssertEqual(PasswordCheck.check("1234567", needsPassword: true), .length)
        XCTAssertEqual(PasswordCheck.check("12345678", needsPassword: true), .ok)
        XCTAssertEqual(PasswordCheck.check(String(repeating: "a", count: 63), needsPassword: true), .ok)
        XCTAssertEqual(PasswordCheck.check(String(repeating: "a", count: 64), needsPassword: true), .ok, "64 hex digits")
        XCTAssertEqual(PasswordCheck.check(String(repeating: "z", count: 64), needsPassword: true), .length, "64 non-hex")
        XCTAssertEqual(PasswordCheck.check(String(repeating: "a", count: 65), needsPassword: true), .length)
        XCTAssertEqual(PasswordCheck.check("пароль12", needsPassword: true), .ok, "16 bytes in UTF-8")
        XCTAssertEqual(PasswordCheck.check("абвг", needsPassword: true), .ok, "8 bytes")
        XCTAssertEqual(PasswordCheck.check("абв", needsPassword: true), .length, "6 bytes")
    }

    func testSpacesAtTheEndsAreRefusedNotTrimmed() {
        XCTAssertEqual(PasswordCheck.check(" password", needsPassword: true), .spaces)
        XCTAssertEqual(PasswordCheck.check("password ", needsPassword: true), .spaces)
        XCTAssertEqual(PasswordCheck.check("pass word", needsPassword: true), .ok)
    }

    func testEmptyPassword() {
        XCTAssertEqual(PasswordCheck.check("", needsPassword: true), .missing)
        XCTAssertEqual(PasswordCheck.check("", needsPassword: false), .ok)
        XCTAssertTrue(PasswordCheck.needsPassword(saved: false, secured: true))
        XCTAssertFalse(PasswordCheck.needsPassword(saved: false, secured: false), "open network in the scan")
        XCTAssertTrue(PasswordCheck.needsPassword(saved: false, secured: nil), "not in the scan: taken as protected")
        XCTAssertFalse(PasswordCheck.needsPassword(saved: true, secured: true), "saved: keeps its password")
    }

    // MARK: - Same drone

    func testIdentity() {
        XCTAssertEqual(DroneIdentity.check(expected: "20EC", reported: "20ec"), .same)
        XCTAssertEqual(DroneIdentity.check(expected: "20EC", reported: "ABCD"), .different("ABCD"))
        XCTAssertEqual(DroneIdentity.check(expected: nil, reported: "ABCD"), .unknown)
        XCTAssertEqual(DroneIdentity.check(expected: "20EC", reported: nil), .unknown)
        XCTAssertEqual(DroneIdentity.check(expected: "20EC", reported: ""), .unknown)
        XCTAssertTrue(DroneIdentity.different("ABCD").blocks)
        XCTAssertFalse(DroneIdentity.unknown.blocks)
        XCTAssertFalse(DroneIdentity.same.blocks)
    }

    // MARK: - After Apply Now

    func testFollowUp() {
        XCTAssertEqual(ApplyFollowUp.decide(target: "Lab", computerSSID: "Lab", droneID: "20EC"), .waitHere)
        XCTAssertEqual(ApplyFollowUp.decide(target: "netplan-wlan0-Lab", computerSSID: "Lab", droneID: "20EC"), .waitHere)
        XCTAssertEqual(ApplyFollowUp.decide(target: "Lab", computerSSID: "", droneID: "20EC"), .waitHere,
                       "no Location permission: try to find it anyway")
        XCTAssertEqual(ApplyFollowUp.decide(target: "Lab", computerSSID: "Home", droneID: "20EC"), .otherNetwork("Home"))
        XCTAssertEqual(ApplyFollowUp.decide(target: "Lab", computerSSID: "Lab", droneID: nil), .noID)
        XCTAssertTrue(ApplyFollowUp.otherNetwork("Home").text(drone: "Bumblebee-20EC", target: "Lab").contains("Home"))
    }

    // MARK: - Finding the drone again

    func testMatchByID() {
        XCTAssertTrue(DroneMatch.accepts(expectedID: "20EC", foundID: "20ec", secondsSinceStart: 0))
        XCTAssertFalse(DroneMatch.accepts(expectedID: "20EC", foundID: "ABCD", secondsSinceStart: 30))
        XCTAssertFalse(DroneMatch.accepts(expectedID: "20EC", foundID: nil, secondsSinceStart: 30))
    }

    func testWithoutAnIDDronesAlreadyThereDoNotCount() {
        XCTAssertFalse(DroneMatch.accepts(expectedID: nil, foundID: nil, secondsSinceStart: 0.5),
                       "reported at once: it was on the network before the setup")
        XCTAssertTrue(DroneMatch.accepts(expectedID: nil, foundID: nil, secondsSinceStart: 6))
        XCTAssertFalse(DroneMatch.accepts(expectedID: nil, foundID: "ABCD", secondsSinceStart: 6),
                       "a drone with an id is not the old one we wait for")
    }

    // MARK: - Password typed in Add drone

    func testPasswordIsKeptOnlyWhenItWorked() {
        XCTAssertEqual(PasswordMemory.after(failure: nil), .save)
        XCTAssertEqual(PasswordMemory.after(failure: .wrongPassword), .forget)
        XCTAssertEqual(PasswordMemory.after(failure: .isolated), .save)
        XCTAssertEqual(PasswordMemory.after(failure: .noAddress), .save)
        XCTAssertEqual(PasswordMemory.after(failure: .notFound), .save)
        XCTAssertEqual(PasswordMemory.after(failure: .droneSilent), .keep)
        XCTAssertEqual(PasswordMemory.after(failure: .other), .keep)
    }

    // MARK: - Apply Now, followed through the drone's status

    private func status(_ mode: String = "client", _ ssid: String = "Future Lab",
                        error reason: String? = nil) -> ApplyWatch.Poll {
        .status(mode: mode, ssid: ssid,
                lastError: reason.map { DroneAPI.JoinError(ssid: "Future Lab", reason: $0, message: "") })
    }

    func testApplyIsNotDoneWhileTheDroneHasNotLeftYet() {
        // The 26.10 bench bug: "is on Future Lab" right after the reply, before the switch.
        var st = ApplyWatch.State()
        XCTAssertEqual(ApplyWatch.step(&st, poll: status(), elapsed: 1, target: "Future Lab"), .waiting,
                       "too early to ask")
        XCTAssertEqual(ApplyWatch.step(&st, poll: status(), elapsed: 6, target: "Future Lab"), .waiting,
                       "still there and never gone: not decided yet")
        XCTAssertEqual(ApplyWatch.step(&st, poll: .noAnswer, elapsed: 9, target: "Future Lab"), .waiting)
        XCTAssertTrue(st.sawGone)
        XCTAssertEqual(ApplyWatch.step(&st, poll: status(), elapsed: 21, target: "Future Lab"), .joined)
    }

    func testAFastRejoinThatWasNeverSeenCountsAfterSettling() {
        var st = ApplyWatch.State()
        XCTAssertEqual(ApplyWatch.step(&st, poll: status(), elapsed: 19, target: "Future Lab"), .waiting)
        XCTAssertEqual(ApplyWatch.step(&st, poll: status(), elapsed: 20, target: "Future Lab"), .joined)
    }

    func testWrongPasswordIsReportedNotTakenForSuccess() {
        // The drone came back on its old password and says why (5.4 on the bench).
        var st = ApplyWatch.State()
        _ = ApplyWatch.step(&st, poll: .noAnswer, elapsed: 8, target: "Future Lab")
        let v = ApplyWatch.step(&st, poll: status(error: "wrong_password"), elapsed: 95, target: "Future Lab")
        XCTAssertEqual(v, .failed(reason: "wrong_password", triedSSID: "Future Lab", currentSSID: "Future Lab"))
        XCTAssertEqual(ApplyWatch.failedText(drone: "Bumblebee-20EC", reason: "wrong_password",
                                             triedSSID: "Future Lab", currentSSID: "Future Lab"),
                       "Bumblebee-20EC did not switch: wrong password for Future Lab. "
                       + "It kept its saved settings and is on Future Lab.")
    }

    func testRefusedAtTheLastMomentIsAFailureToo() {
        var st = ApplyWatch.State()
        let v = ApplyWatch.step(&st, poll: status(error: "fc_unknown"), elapsed: 6, target: "Future Lab")
        XCTAssertEqual(v, .failed(reason: "fc_unknown", triedSSID: "Future Lab", currentSSID: "Future Lab"))
    }

    func testOtherNetworkOrHotspotIsNotJoinedAndTimesOut() {
        var st = ApplyWatch.State()
        _ = ApplyWatch.step(&st, poll: .noAnswer, elapsed: 6, target: "Lab 2")
        XCTAssertEqual(ApplyWatch.step(&st, poll: status("client", "Future Lab"), elapsed: 30, target: "Lab 2"), .waiting)
        XCTAssertEqual(ApplyWatch.step(&st, poll: status("hotspot", "bumblebee-hotspot"), elapsed: 60, target: "Lab 2"),
                       .waiting)
        XCTAssertEqual(ApplyWatch.step(&st, poll: .noAnswer, elapsed: 150, target: "Lab 2"), .notFound)
        XCTAssertEqual(ApplyWatch.step(&st, poll: status("client", "netplan-wlan0-Lab 2"), elapsed: 40, target: "Lab 2"),
                       .joined, "a netplan profile of the target counts")
    }

    func testOldRefusalBannerGoesOnceTheDroneIsHealthy() {
        XCTAssertTrue(RefusalBanner.stillTrue(code: "fc_unknown", link: .telemetryFrozen, armed: nil))
        XCTAssertTrue(RefusalBanner.stillTrue(code: "armed", link: .ok, armed: true))
        XCTAssertFalse(RefusalBanner.stillTrue(code: "fc_unknown", link: .ok, armed: false))
        XCTAssertFalse(RefusalBanner.stillTrue(code: "armed", link: .ok, armed: false))
        XCTAssertTrue(RefusalBanner.stillTrue(code: "nmcli_failed", link: .ok, armed: false), "other errors stay")
        XCTAssertTrue(RefusalBanner.stillTrue(code: nil, link: .ok, armed: false))
    }
}
