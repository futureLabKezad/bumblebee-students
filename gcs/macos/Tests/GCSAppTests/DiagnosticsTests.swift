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

/// The "Copy diagnostics" report and the crash log's last entry.
final class DiagnosticsTests: XCTestCase {
    private func input(connected: Bool = true) -> DiagnosticsInput {
        DiagnosticsInput(
            now: Date(timeIntervalSince1970: 1_792_745_000),
            app: "GCS 1.2.0 (build 3)", os: "macOS 26.0 (arm64)",
            connected: connected, droneHost: "192.168.1.50", droneName: "Bumblebee-20EC", droneID: "20EC",
            droneSoftware: "Bumblebee 1.0.2-rc1 (repo v1.0.1-26-g28071be), update installed 2026-10-23T05:57:04Z",
            link: "OK", armed: "DISARMED", mode: "POSCTL", control: "Disarmed", battery: "Not measured — check with a tester",
            computerWifi: "Classroom", onDroneHotspot: false,
            found: [.init(name: "Bumblebee-20EC", ip: "192.168.1.50", droneID: "20EC", live: true),
                    .init(name: "Drone", ip: "192.168.1.60", droneID: nil, live: false)],
            unknownDevices: 1, hotspots: ["Bumblebee-ABCD"],
            remembered: [.init(name: "Bumblebee-20EC", droneID: "20EC", lastIP: "192.168.1.50")],
            messages: (1...40).map { "10:00:\(String(format: "%02d", $0 % 60)) line \($0)" },
            lastCrash: nil)
    }

    func testTheReportNamesWhatMatters() {
        let r = Diagnostics.report(input())
        XCTAssertTrue(r.contains("App: GCS 1.2.0 (build 3) · macOS 26.0 (arm64)"))
        XCTAssertTrue(r.contains("Drone: Bumblebee-20EC · 192.168.1.50 · id 20EC · software Bumblebee 1.0.2-rc1"))
        XCTAssertTrue(r.contains("Link: OK · State: DISARMED · Mode: POSCTL · Control: Disarmed"))
        XCTAssertTrue(r.contains("This computer's Wi-Fi: Classroom"))
        XCTAssertTrue(r.contains("Drone · 192.168.1.60 · id unknown · not answering"))
        XCTAssertTrue(r.contains("+ 1 other device(s) with port 9090 open"))
        XCTAssertTrue(r.contains("Drone hotspots nearby: Bumblebee-ABCD"))
        XCTAssertTrue(r.contains("Last crash: none recorded"))
    }

    func testOnlyTheNewestMessages() {
        let r = Diagnostics.report(input())
        XCTAssertTrue(r.contains("line 1\n") || r.contains("line 1 "), "the newest (first) is kept")
        XCTAssertTrue(r.contains("line 30"))
        XCTAssertFalse(r.contains("line 31"), "at most \(Diagnostics.maxMessages) messages")
    }

    func testNotConnected() {
        let r = Diagnostics.report(input(connected: false))
        XCTAssertTrue(r.contains("Drone: not connected"))
        XCTAssertFalse(r.contains("Link:"))
    }

    func testOlderDroneSoftware() {
        var i = input()
        i.droneSoftware = nil
        XCTAssertTrue(Diagnostics.report(i).contains("software unknown (before 1.0.2)"))
    }

    func testCrashLogLastEntry() {
        let log = """
            2026-10-20T09:00:00Z GCS 1.1.0 uncaught exception NSRangeException: index 3
            0 CoreFoundation ...

            2026-10-22T11:30:00Z GCS 1.2.0 uncaught exception NSInvalidArgumentException: nil key
            0 CoreFoundation ...
            """
        XCTAssertEqual(CrashLog.lastEntryHeader(log),
                       "2026-10-22T11:30:00Z GCS 1.2.0 uncaught exception NSInvalidArgumentException: nil key")
        XCTAssertNil(CrashLog.lastEntryHeader(""))
    }
}
