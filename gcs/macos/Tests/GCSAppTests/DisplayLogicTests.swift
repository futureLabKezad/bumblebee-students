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

/// Battery text, low-battery hysteresis, chart span, attitude source and pitch
/// sign, the log book and the video status.
final class DisplayLogicTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 2_000_000)
    private func at(_ s: Double) -> Date { t0.addingTimeInterval(s) }

    // MARK: - Battery

    func testBatteryNotMeasured() {
        // BAT1_SOURCE=-1: PX4 sends the UINT16_MAX mV sentinel and remaining -1.
        XCTAssertEqual(BatteryReading.classify(voltage: 65.535, percentage: -0.01), .notMeasured)
        XCTAssertEqual(BatteryReading.classify(voltage: 65.53500366210938, percentage: 0.5), .notMeasured)
        XCTAssertEqual(BatteryReading.classify(voltage: 0, percentage: 0.5), .notMeasured)
        XCTAssertEqual(BatteryReading.classify(voltage: -1, percentage: 0.5), .notMeasured)
        XCTAssertEqual(BatteryReading.classify(voltage: .nan, percentage: 0.5), .notMeasured)
        XCTAssertEqual(BatteryReading.classify(voltage: nil, percentage: 0.5), .notMeasured)
        XCTAssertEqual(BatteryReading.classify(voltage: 24.1, percentage: -0.01), .notMeasured)
    }

    func testBatteryMeasured() {
        XCTAssertEqual(BatteryReading.classify(voltage: 24.1, percentage: 0.83), .measured(voltage: 24.1, percent: 83))
        XCTAssertEqual(BatteryReading.classify(voltage: 24.1, percentage: .nan), .measured(voltage: 24.1, percent: nil))
        XCTAssertEqual(BatteryReading.classify(voltage: 24.1, percentage: nil), .measured(voltage: 24.1, percent: nil))
        XCTAssertEqual(BatteryReading.classify(voltage: 24.1, percentage: 1.7), .measured(voltage: 24.1, percent: nil),
                       "a fraction above 1 is not a percentage we trust")
    }

    func testBatteryDisplayTexts() {
        let none = BatteryDisplay(nil)
        XCTAssertEqual(none.tileValue, "—")
        XCTAssertEqual(none.barText, "—")

        let nm = BatteryDisplay(.notMeasured)
        XCTAssertEqual(nm.tileValue, "Not measured")
        XCTAssertEqual(nm.tileCaption, "check with a tester")
        XCTAssertEqual(nm.barText, "Not measured — check with a tester")
        XCTAssertEqual(nm.barPercent, 0)
        XCTAssertEqual(nm.level, .neutral)
        XCTAssertEqual(nm.icon, "minus.plus.batteryblock", "neutral icon, not a full battery")

        let ok = BatteryDisplay(.measured(voltage: 24.1, percent: 83))
        XCTAssertEqual(ok.tileValue, "83%")
        XCTAssertNil(ok.tileCaption)
        XCTAssertEqual(ok.barText, "24.10 V · 83%")
        XCTAssertEqual(ok.barPercent, 83)
        XCTAssertEqual(ok.level, .good)
        XCTAssertEqual(ok.icon, "battery.75percent")

        let low = BatteryDisplay(.measured(voltage: 20.4, percent: 12))
        XCTAssertEqual(low.level, .critical)
        XCTAssertEqual(low.icon, "battery.0percent")
        XCTAssertEqual(BatteryDisplay(.measured(voltage: 22, percent: 40)).level, .low)

        let vOnly = BatteryDisplay(.measured(voltage: 24.1, percent: nil))
        XCTAssertEqual(vOnly.tileValue, "24.10 V")
        XCTAssertEqual(vOnly.barText, "24.10 V")
        XCTAssertEqual(vOnly.level, .neutral)
    }

    func testIconNamesExist() {
        let names = [BatteryDisplay(nil).icon, BatteryDisplay(.notMeasured).icon]
            + [100.0, 80, 60, 30, 5].map { BatteryDisplay(.measured(voltage: 24, percent: $0)).icon }
        for n in names {
            XCTAssertNotNil(NSImage(systemSymbolName: n, accessibilityDescription: nil), n)
        }
    }

    // MARK: - Low battery hysteresis

    func testLowBatteryLogsOnceAndRearmsAboveTwenty() {
        var l = LowBatteryLatch()
        XCTAssertFalse(l.update(percent: 40))
        XCTAssertTrue(l.update(percent: 14.9), "first drop below 15 %")
        XCTAssertTrue(l.active)
        XCTAssertFalse(l.update(percent: 14))
        XCTAssertFalse(l.update(percent: 16))
        XCTAssertFalse(l.update(percent: 14), "jitter around 15 % is not a new warning")
        XCTAssertFalse(l.update(percent: 20))
        XCTAssertTrue(l.active, "20 % exactly does not re-arm")
        XCTAssertFalse(l.update(percent: 20.5))
        XCTAssertFalse(l.active)
        XCTAssertTrue(l.update(percent: 13), "re-armed above 20 %")
        l.reset()
        XCTAssertFalse(l.active)
    }

    // MARK: - Chart span

    func testAltitudeNoiseDoesNotFillTheChart() {
        let data = (0..<100).map { 1.0 + 0.01 * sin(Double($0)) }
        let r = ChartScale.range(data, minSpan: 1.0)
        XCTAssertEqual(r.hi - r.lo, 1.0, accuracy: 1e-9)
        XCTAssertEqual(r.lo, 0.5, accuracy: 0.011)
        XCTAssertEqual(r.hi, 1.5, accuracy: 0.011)
        XCTAssertLessThanOrEqual(r.lo, data.min()!)
        XCTAssertGreaterThanOrEqual(r.hi, data.max()!)
    }

    func testChartSpanKeepsRealRangeAndFixedBounds() {
        let r = ChartScale.range([0, 3], minSpan: 1.0)
        XCTAssertEqual(r.lo, 0); XCTAssertEqual(r.hi, 3)
        let f = ChartScale.range([1, 2], fixedMin: 0, fixedMax: 100)
        XCTAssertEqual(f.lo, 0); XCTAssertEqual(f.hi, 100)
        let flat = ChartScale.range([2, 2, 2], minSpan: 1.0)
        XCTAssertEqual(flat.lo, 1.5); XCTAssertEqual(flat.hi, 2.5)
        let skew = ChartScale.range([0, 0.9, 0.9, 0.9], minSpan: 1.0)
        XCTAssertLessThanOrEqual(skew.lo, 0, "centred on the data range, so nothing is clipped")
        XCTAssertGreaterThanOrEqual(skew.hi, 0.9)
        let floor = ChartScale.range([0.1, 0.2], fixedMin: 0, minSpan: 1.0)
        XCTAssertEqual(floor.lo, 0); XCTAssertEqual(floor.hi, 1)
    }

    // MARK: - Attitude and pitch sign

    func testPositivePitchIsNoseDownAndShowsMoreGround() {
        // +10° about the body Y axis (left, REP-103): the nose goes down.
        let h = 5.0 * Double.pi / 180
        let e = quatToEuler(0, sin(h), 0, cos(h))
        XCTAssertEqual(e.pitch, 10, accuracy: 1e-9)
        XCTAssertEqual(e.roll, 0, accuracy: 1e-9)
        // Screen y grows downward: a negative offset moves the horizon up, so
        // the lower half (ground) gets bigger, as on a real attitude indicator.
        XCTAssertLessThan(Horizon.offset(pitchDeg: e.pitch, pxPerDeg: 2), 0)
        XCTAssertEqual(Horizon.offset(pitchDeg: 10, pxPerDeg: 2), -20)
        XCTAssertGreaterThan(Horizon.offset(pitchDeg: -10, pxPerDeg: 2), 0, "nose up: more sky")
    }

    func testIMUOrientationValidity() {
        XCTAssertTrue(AttitudeSource.imuOrientationValid(x: 0, y: 0, z: 0, w: 1, covariance0: 0))
        XCTAssertTrue(AttitudeSource.imuOrientationValid(x: 0, y: 0, z: 0, w: 1, covariance0: nil))
        XCTAssertFalse(AttitudeSource.imuOrientationValid(x: 0, y: 0, z: 0, w: 1, covariance0: -1), "-1 = no orientation")
        XCTAssertFalse(AttitudeSource.imuOrientationValid(x: 0, y: 0, z: 0, w: 0, covariance0: 0), "|q| = 0")
        XCTAssertFalse(AttitudeSource.imuOrientationValid(x: 0, y: 0, z: 0, w: 1.5, covariance0: 0))
    }

    func testAttitudeComesFromIMUAndFallsBackToPose() {
        var a = AttitudeSource()
        let h = 5.0 * Double.pi / 180
        XCTAssertNotNil(a.fromPose(x: 0, y: 0, z: 0, w: 1, now: at(0)), "no IMU orientation yet: pose is used")
        XCTAssertNil(a.fromIMU(x: 0, y: 0, z: 0, w: 1, covariance0: -1, now: at(0.1)), "invalid IMU orientation")
        XCTAssertNotNil(a.fromPose(x: 0, y: 0, z: 0, w: 1, now: at(0.2)), "still pose")
        let e = a.fromIMU(x: 0, y: sin(h), z: 0, w: cos(h), covariance0: 0, now: at(1))
        XCTAssertEqual(e?.pitch ?? 0, 10, accuracy: 1e-9)
        XCTAssertNil(a.fromPose(x: 0, y: 0, z: 0, w: 1, now: at(2)), "IMU orientation is fresh: pose is ignored")
        XCTAssertNotNil(a.fromPose(x: 0, y: 0, z: 0, w: 1, now: at(3.5)), "IMU quiet > 2 s: pose again")
        a.reset()
        XCTAssertNotNil(a.fromPose(x: 0, y: 0, z: 0, w: 1, now: at(1.5)))
    }

    // MARK: - Log book

    func testRepeatedReconnectLinesCollapse() {
        var b = LogBook()
        b.add("rosbridge connected (10.0.0.5)", time: "10:00:00")
        for i in 0..<9 {
            b.add("rosbridge lost — reconnecting…", key: "rosbridge-down", time: "10:00:\(10 + i)")
        }
        XCTAssertEqual(b.entries.count, 2)
        XCTAssertEqual(b.entries[0].line, "rosbridge lost — reconnecting… ×9")
        XCTAssertEqual(b.entries[0].time, "10:00:18")
        XCTAssertEqual(b.entries[1].line, "rosbridge connected (10.0.0.5)")
        b.add("rosbridge connected (10.0.0.5)", time: "10:01:00")
        b.add("rosbridge lost — reconnecting…", key: "rosbridge-down", time: "10:02:00")
        XCTAssertEqual(b.entries.count, 4, "a new drop after a reconnect is a new line")
        XCTAssertEqual(b.entries[0].line, "rosbridge lost — reconnecting…")
    }

    func testPX4LinesAreNotPushedOutByAppLines() {
        var b = LogBook()
        b.add("[FCU] Preflight Fail: ekf2 missing data", source: .fcu, time: "09:59:00")
        b.add("[FCU] Accel #0 fail", source: .fcu, time: "09:59:01")
        for i in 0..<200 { b.add("app line \(i)", time: "10:00:00") }
        let fcu = b.entries.filter { $0.source == .fcu }
        XCTAssertEqual(fcu.map(\.text), ["[FCU] Accel #0 fail", "[FCU] Preflight Fail: ekf2 missing data"])
        XCTAssertEqual(b.entries.filter { $0.source == .app }.count, LogBook.appCap)
        XCTAssertEqual(b.entries.first?.text, "app line 199", "newest first")
    }

    func testPX4LinesHaveTheirOwnCap() {
        var b = LogBook()
        for i in 0..<(LogBook.fcuCap + 5) { b.add("[FCU] \(i)", source: .fcu, time: "t") }
        XCTAssertEqual(b.entries.count, LogBook.fcuCap)
        XCTAssertEqual(b.entries.first?.text, "[FCU] \(LogBook.fcuCap + 4)")
        b.clear()
        XCTAssertTrue(b.entries.isEmpty)
    }

    func testCollapseKeepsEntryIdentity() {
        var b = LogBook()
        b.add("rosbridge lost — reconnecting…", key: "rosbridge-down", time: "a")
        let id = b.entries[0].id
        b.add("rosbridge not reachable — retrying…", key: "rosbridge-down", time: "b")
        XCTAssertEqual(b.entries[0].id, id)
        XCTAssertEqual(b.entries[0].line, "rosbridge lost — reconnecting… ×2", "the first text stays")
    }

    // MARK: - Video

    func testVideoStatus() {
        XCTAssertEqual(VideoStatus.of(lastFrameAt: nil, startedAt: nil, now: at(9)), .waiting)
        XCTAssertEqual(VideoStatus.of(lastFrameAt: nil, startedAt: at(0), now: at(2.9)), .waiting)
        XCTAssertEqual(VideoStatus.of(lastFrameAt: nil, startedAt: at(0), now: at(3.0)), .noFrames)
        XCTAssertEqual(VideoStatus.of(lastFrameAt: at(5), startedAt: at(0), now: at(7.9)), .live)
        XCTAssertEqual(VideoStatus.of(lastFrameAt: at(5), startedAt: at(0), now: at(8.0)), .live, "3.0 s old is still live")
        XCTAssertEqual(VideoStatus.of(lastFrameAt: at(5), startedAt: at(0), now: at(12.4)), .lost(seconds: 7))
    }

    func testModeNumbersFromMAVROS() {
        XCTAssertEqual(ModeText.normalize("CMODE(50593792)"), "AUTO.LOITER")
        XCTAssertEqual(ModeText.normalize("CMODE(393216)"), "OFFBOARD")       // main 6
        XCTAssertEqual(ModeText.normalize("CMODE(196608)"), "POSCTL")         // main 3
        XCTAssertEqual(ModeText.normalize("CMODE(100925440)"), "AUTO.LAND")   // 0x06040000
        XCTAssertEqual(ModeText.normalize("CMODE(4096)"), "CMODE(4096)", "unknown numbers stay as they are")
        XCTAssertEqual(ModeText.normalize("CMODE(x)"), "CMODE(x)")
        XCTAssertEqual(ModeText.normalize("POSCTL"), "POSCTL")
        XCTAssertEqual(ModeText.normalize(""), "")
    }
}
