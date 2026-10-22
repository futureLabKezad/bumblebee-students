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
import AppKit
@testable import GCSApp

/// What the tiles, captions, colours and video overlays show, decided outside
/// SwiftUI: the views only map a Tone to a Theme colour.
final class PresentationLogicTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 4_000_000)
    private func at(_ s: Double) -> Date { t0.addingTimeInterval(s) }

    // MARK: - Armed tile colours (spec 3)

    func testUnknownIsCautionAndArmedLinkLostIsDanger() {
        XCTAssertEqual(ArmedDisplay.unknown.tone, .caution)
        XCTAssertEqual(ArmedDisplay.unknown.valueTone, .caution, "UNKNOWN in the caution colour")
        XCTAssertEqual(ArmedDisplay.armedLinkLost.tone, .danger)
        XCTAssertEqual(ArmedDisplay.armedLinkLost.valueTone, .danger, "ARMED? link lost in the danger colour")
        XCTAssertEqual(ArmedDisplay.armed.tone, .danger)
        XCTAssertEqual(ArmedDisplay.armed.valueTone, .plain)
        XCTAssertEqual(ArmedDisplay.disarmed.tone, .neutral)
        XCTAssertEqual(ArmedDisplay.disarmed.valueTone, .plain)
    }

    // MARK: - Link tile and sidebar

    func testLinkTones() {
        XCTAssertEqual(LinkState.ok.tone, .ok)
        XCTAssertEqual(LinkState.noDrone.tone, .warn)
        XCTAssertEqual(LinkState.fcNotConnected.tone, .danger)
        XCTAssertEqual(LinkState.telemetryFrozen.tone, .danger)
    }

    func testLinkCaption() {
        XCTAssertNil(LinkState.noDrone.caption(socketAnswered: false, stateNote: "no data yet"))
        XCTAssertEqual(LinkState.noDrone.caption(socketAnswered: true, stateNote: "no data yet"), "waiting for FC data",
                       "socket open, first State still on its way")
        XCTAssertEqual(LinkState.telemetryFrozen.caption(socketAnswered: true, stateNote: "no data 4 s"), "no data 4 s")
        XCTAssertNil(LinkState.ok.caption(socketAnswered: true, stateNote: nil))
        XCTAssertNil(LinkState.fcNotConnected.caption(socketAnswered: true, stateNote: nil))
    }

    func testSidebarLine() {
        XCTAssertEqual(LinkState.ok.sidebarText(socketAnswered: true), "linked")
        XCTAssertEqual(LinkState.noDrone.sidebarText(socketAnswered: false), "linking…")
        XCTAssertEqual(LinkState.noDrone.sidebarText(socketAnswered: true), "waiting for FC data")
        XCTAssertEqual(LinkState.fcNotConnected.sidebarText(socketAnswered: true), "FC not connected")
        XCTAssertEqual(LinkState.telemetryFrozen.sidebarText(socketAnswered: true), "Telemetry frozen")
    }

    // MARK: - Who is in control plate

    func testControlPlate() {
        XCTAssertEqual(ControlOwner.program.tone, .primary)
        XCTAssertEqual(ControlOwner.pilot.tone, .ok)
        XCTAssertEqual(ControlOwner.px4.tone, .warn)
        XCTAssertEqual(ControlOwner.disarmed.tone, .neutral)
        XCTAssertEqual(ControlOwner.unknown.tone, .caution)
        XCTAssertEqual(ControlOwner.unknown.valueTone, .caution)
        XCTAssertEqual(ControlOwner.pilot.valueTone, .plain)
        XCTAssertEqual(ControlOwner.unknown.caption(armed: nil), "waiting for FC data")
        XCTAssertNil(ControlOwner.unknown.caption(armed: true), "armed in a mode we do not know: no FC wait")
        XCTAssertNil(ControlOwner.pilot.caption(armed: true))
    }

    func testIconNamesExist() {
        var names = [LinkState.ok, .noDrone, .fcNotConnected, .telemetryFrozen].map(\.icon)
        names += [ArmedDisplay.armed, .disarmed, .unknown, .armedLinkLost].map(\.icon)
        names += [ControlOwner.program, .pilot, .px4, .disarmed, .unknown].map(\.icon)
        for n in names {
            XCTAssertNotNil(NSImage(systemSymbolName: n, accessibilityDescription: nil), n)
        }
    }

    // MARK: - Mode tile and mode-change line (spec 8, 12)

    func testModeTileValue() {
        XCTAssertEqual(ModeText.display(nil), "—", "no State yet")
        XCTAssertEqual(ModeText.display(""), "—")
        XCTAssertEqual(ModeText.display(" offboard "), "OFFBOARD")
        XCTAssertEqual(ModeText.display("AUTO.LAND"), "AUTO.LAND")
    }

    func testModeChangeLine() {
        XCTAssertEqual(ModeText.changeLine("POSCTL"), "mode → POSCTL (pilot, position hold)")
        XCTAssertEqual(ModeText.changeLine("OFFBOARD"), "mode → OFFBOARD (program in control)")
        XCTAssertEqual(ModeText.changeLine("AUTO.MISSION"), "mode → AUTO.MISSION (PX4 automatic)")
        XCTAssertEqual(ModeText.changeLine(""), "mode → unknown")
        XCTAssertEqual(ModeText.changeLine("RATTITUDE"), "mode → RATTITUDE", "a name we do not know, as it is")
    }

    func testModeChangeIsAVisibleLogLine() {
        let s = TelemetryStore()
        s.playAlert = {}
        s.socketOpened(host: "h", now: at(0))
        s.ingest(topic: "/mavros/state", msg: ["connected": true, "armed": false, "mode": "POSCTL"], now: at(0.5))
        s.ingest(topic: "/mavros/state", msg: ["connected": true, "armed": false, "mode": "ALTCTL"], now: at(1.0))
        XCTAssertEqual(s.logs.first?.text, "mode → ALTCTL (pilot, altitude hold)")
        XCTAssertTrue(s.logs.contains { $0.text == "mode → POSCTL (pilot, position hold)" })
    }

    // MARK: - Battery colour

    func testBatteryTones() {
        XCTAssertEqual(BatteryDisplay(nil).tone, .neutral)
        XCTAssertEqual(BatteryDisplay(.notMeasured).tone, .neutral, "not measured is neutral, not green")
        XCTAssertEqual(BatteryDisplay(.measured(voltage: 24, percent: 80)).tone, .ok)
        XCTAssertEqual(BatteryDisplay(.measured(voltage: 22, percent: 40)).tone, .warn)
        XCTAssertEqual(BatteryDisplay(.measured(voltage: 20, percent: 10)).tone, .danger)
        XCTAssertEqual(BatteryDisplay(.measured(voltage: 24, percent: nil)).tone, .neutral)
    }

    // MARK: - Video overlay and hints (spec 10)

    func testArucoHints() {
        XCTAssertEqual(VideoHints.idleHint(topic: "/aruco_detect/debug"),
                       "ArUco image appears only when the drone is armed or in OFFBOARD")
        XCTAssertEqual(VideoHints.idleHint(topic: "/aruco_map/image"), "ArUco map: armed or OFFBOARD only")
        XCTAssertNil(VideoHints.idleHint(topic: "/main_camera/image_raw"), "cameras stream all the time")
        XCTAssertNil(VideoHints.idleHint(topic: "/second_camera/image_raw"))
    }

    func testVideoOverlay() {
        let hint = "ArUco image appears only when the drone is armed or in OFFBOARD"
        // A live picture: nothing on top.
        XCTAssertEqual(VideoOverlay.of(status: .live, hasImage: true, idleHint: nil), VideoOverlay.none)
        // Frozen frame older than 3 s: "Video lost" over it, with the hint on ArUco.
        XCTAssertEqual(VideoOverlay.of(status: .lost(seconds: 4), hasImage: true, idleHint: nil), .lost(seconds: 4, hint: nil))
        XCTAssertEqual(VideoOverlay.of(status: .lost(seconds: 9), hasImage: true, idleHint: hint), .lost(seconds: 9, hint: hint))
        // No frame yet.
        XCTAssertEqual(VideoOverlay.of(status: .waiting, hasImage: false, idleHint: hint), .waiting)
        XCTAssertEqual(VideoOverlay.of(status: .noFrames, hasImage: false, idleHint: nil), .waiting,
                       "cameras: keep waiting (the stream retries by itself)")
        XCTAssertEqual(VideoOverlay.of(status: .noFrames, hasImage: false, idleHint: hint), .hint(hint),
                       "ArUco with no frame for 3 s: the hint, not an endless spinner")
    }

    func testVideoOverlayFollowsTheStreamClock() {
        let started = at(0)
        func overlay(_ now: Double, frameAt: Double?, hint: String?) -> VideoOverlay {
            let st = VideoStatus.of(lastFrameAt: frameAt.map(at), startedAt: started, now: at(now))
            return VideoOverlay.of(status: st, hasImage: frameAt != nil, idleHint: hint)
        }
        XCTAssertEqual(overlay(2.9, frameAt: nil, hint: "h"), .waiting)
        XCTAssertEqual(overlay(3.0, frameAt: nil, hint: "h"), .hint("h"))
        XCTAssertEqual(overlay(5.0, frameAt: 2.0, hint: nil), VideoOverlay.none, "3.0 s old is still live")
        XCTAssertEqual(overlay(5.1, frameAt: 2.0, hint: nil), .lost(seconds: 3, hint: nil))
    }

    // MARK: - Chart min/max labels (spec 9)

    func testAltitudeChartShowsItsMinAndMax() {
        let noise = [0.80, 0.81, 0.79, 0.80]
        let l = ChartScale.axisLabels(noise, minSpan: 1.0)
        XCTAssertEqual(l?.top, "1.30")
        XCTAssertEqual(l?.bottom, "0.30")
        XCTAssertNil(ChartScale.axisLabels([0.8], minSpan: 1.0), "no line yet, no scale")
        let bat = ChartScale.axisLabels([50, 51], fixedMin: 0, fixedMax: 100)
        XCTAssertEqual(bat?.top, "100.00")
        XCTAssertEqual(bat?.bottom, "0.00")
    }
}
