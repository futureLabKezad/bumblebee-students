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

/// Link state, freshness, tri-state armed, who is in control and the
/// "flight controller link lost" alarm.
final class LinkLogicTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 1_000_000)
    private func at(_ s: Double) -> Date { t0.addingTimeInterval(s) }

    // MARK: - Link state

    func testNoSocketIsNoDrone() {
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: nil, stateAt: at(0), stateConnected: true, now: at(0.5)), .noDrone)
    }

    func testFreshConnectedStateIsOK() {
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: at(1), stateConnected: true, now: at(2)), .ok)
    }

    func testFreshDisconnectedStateIsFCNotConnected() {
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: at(1), stateConnected: false, now: at(2)), .fcNotConnected)
        // A State without the field is not proof of a linked FC either.
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: at(1), stateConnected: nil, now: at(2)), .fcNotConnected)
    }

    func testStateOlderThanThreeSecondsIsFrozen() {
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: at(1), stateConnected: true, now: at(4.0)), .ok,
                       "exactly 3.0 s old still counts as fresh")
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: at(1), stateConnected: true, now: at(4.1)), .telemetryFrozen)
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: at(1), stateConnected: false, now: at(4.1)), .telemetryFrozen)
    }

    func testNoStateWithinThreeSecondsOfConnectingIsFrozen() {
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: nil, stateConnected: nil, now: at(2.9)), .noDrone,
                       "still waiting for the first State")
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(0), stateAt: nil, stateConnected: nil, now: at(3.1)), .telemetryFrozen)
    }

    func testStateFromBeforeTheSocketOpenedDoesNotCount() {
        // A State kept from the previous socket must not make the new one OK.
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(10), stateAt: at(9.5), stateConnected: true, now: at(10.5)), .noDrone)
        XCTAssertEqual(LinkState.evaluate(socketOpenedAt: at(10), stateAt: at(9.5), stateConnected: true, now: at(13.5)), .telemetryFrozen)
    }

    func testLinkTexts() {
        XCTAssertEqual(LinkState.noDrone.text, "No drone")
        XCTAssertEqual(LinkState.fcNotConnected.text, "FC not connected")
        XCTAssertEqual(LinkState.telemetryFrozen.text, "Telemetry frozen")
        XCTAssertEqual(LinkState.ok.text, "OK")
    }

    // MARK: - Freshness

    func testFreshnessLimits() {
        XCTAssertEqual(Freshness.state, 3.0)
        XCTAssertEqual(Freshness.pose, 2.0)
        XCTAssertEqual(Freshness.velocity, 2.0)
        XCTAssertEqual(Freshness.imu, 2.0)
        XCTAssertEqual(Freshness.battery, 5.0)
        XCTAssertEqual(Freshness.metrics, 6.0)
        XCTAssertEqual(Freshness.video, 3.0)
    }

    func testFreshnessStatus() {
        XCTAssertEqual(Freshness.status(nil, limit: 2, now: at(5)), .never)
        XCTAssertEqual(Freshness.status(at(4), limit: 2, now: at(5)), .fresh)
        XCTAssertEqual(Freshness.status(at(3), limit: 2, now: at(5)), .fresh)
        XCTAssertEqual(Freshness.status(at(0), limit: 2, now: at(5.7)), .stale(seconds: 5))
    }

    func testFreshnessNotes() {
        XCTAssertNil(Freshness.Status.fresh.note)
        XCTAssertEqual(Freshness.Status.stale(seconds: 7).note, "no data 7 s")
        XCTAssertEqual(Freshness.Status.never.note, "no data yet")
        XCTAssertTrue(Freshness.Status.fresh.isFresh)
        XCTAssertFalse(Freshness.Status.never.isFresh)
        XCTAssertFalse(Freshness.Status.stale(seconds: 3).isFresh)
    }

    // MARK: - Armed (tri-state)

    func testArmedIsKnownOnlyOnAnOKLink() {
        XCTAssertEqual(ArmedDisplay.known(link: .ok, reported: true), true)
        XCTAssertEqual(ArmedDisplay.known(link: .ok, reported: false), false)
        for link in [LinkState.noDrone, .fcNotConnected, .telemetryFrozen] {
            XCTAssertNil(ArmedDisplay.known(link: link, reported: false), "\(link) must not show DISARMED")
            XCTAssertNil(ArmedDisplay.known(link: link, reported: true))
        }
    }

    func testArmedTile() {
        XCTAssertEqual(ArmedDisplay(armed: true, lastKnownArmed: true), .armed)
        XCTAssertEqual(ArmedDisplay(armed: false, lastKnownArmed: true), .disarmed)
        XCTAssertEqual(ArmedDisplay(armed: nil, lastKnownArmed: nil), .unknown)
        XCTAssertEqual(ArmedDisplay(armed: nil, lastKnownArmed: false), .unknown)
        XCTAssertEqual(ArmedDisplay(armed: nil, lastKnownArmed: true), .armedLinkLost)

        XCTAssertEqual(ArmedDisplay.armed.text, "ARMED")
        XCTAssertEqual(ArmedDisplay.disarmed.text, "DISARMED")
        XCTAssertEqual(ArmedDisplay.unknown.text, "UNKNOWN")
        XCTAssertEqual(ArmedDisplay.unknown.caption, "waiting for FC data")
        XCTAssertEqual(ArmedDisplay.armedLinkLost.text, "ARMED? link lost")
        XCTAssertNil(ArmedDisplay.disarmed.caption)
    }

    // MARK: - Mode names

    func testModeExplanations() {
        let expected: [String: String] = [
            "OFFBOARD": "program in control",
            "POSCTL": "pilot, position hold",
            "ALTCTL": "pilot, altitude hold",
            "STABILIZED": "pilot, manual",
            "ACRO": "pilot, manual",
            "MANUAL": "pilot, manual",
            "AUTO.LAND": "PX4 landing",
            "AUTO.LOITER": "PX4 holding",
            "AUTO.RTL": "PX4 returning",
            "AUTO.TAKEOFF": "PX4 taking off",
            "AUTO.MISSION": "PX4 automatic",
            "AUTO.PRECLAND": "PX4 automatic",
            "": "unknown",
        ]
        for (mode, text) in expected {
            XCTAssertEqual(ModeText.explain(mode), text, mode)
        }
        XCTAssertNil(ModeText.explain(nil), "no State yet: nothing to explain")
        XCTAssertNil(ModeText.explain("RATTITUDE"), "unknown names are shown as they are")
    }

    // MARK: - Who is in control

    func testControlOwner() {
        XCTAssertEqual(ControlOwner(armed: true, mode: "OFFBOARD"), .program)
        for m in ["POSCTL", "ALTCTL", "STABILIZED", "ACRO", "MANUAL"] {
            XCTAssertEqual(ControlOwner(armed: true, mode: m), .pilot, m)
        }
        XCTAssertEqual(ControlOwner(armed: true, mode: "AUTO.LAND"), .px4)
        XCTAssertEqual(ControlOwner(armed: true, mode: "AUTO.RTL"), .px4)
        XCTAssertEqual(ControlOwner(armed: false, mode: "OFFBOARD"), .disarmed)
        XCTAssertEqual(ControlOwner(armed: nil, mode: "OFFBOARD"), .unknown)
        XCTAssertEqual(ControlOwner(armed: true, mode: ""), .unknown)
        XCTAssertEqual(ControlOwner(armed: true, mode: nil), .unknown)
        XCTAssertEqual(ControlOwner.program.text, "Program")
        XCTAssertEqual(ControlOwner.pilot.text, "Pilot")
        XCTAssertEqual(ControlOwner.px4.text, "PX4")
        XCTAssertEqual(ControlOwner.disarmed.text, "Disarmed")
        XCTAssertEqual(ControlOwner.unknown.text, "Unknown")
    }

    func testControlEvents() {
        var ev = ControlEvents()
        XCTAssertNil(ev.update(owner: .disarmed, mode: "POSCTL"), "first look is not an event")
        XCTAssertEqual(ev.update(owner: .pilot, mode: "POSCTL"), "Pilot took control")
        XCTAssertNil(ev.update(owner: .pilot, mode: "POSCTL"))
        XCTAssertNil(ev.update(owner: .pilot, mode: "ALTCTL"), "pilot changing hold mode is not a hand-over")
        XCTAssertEqual(ev.update(owner: .program, mode: "OFFBOARD"), "Program took control")
        XCTAssertEqual(ev.update(owner: .pilot, mode: "POSCTL"), "Pilot took control")
        XCTAssertEqual(ev.update(owner: .px4, mode: "AUTO.LOITER"), "PX4 is holding")
        XCTAssertEqual(ev.update(owner: .px4, mode: "AUTO.LAND"), "PX4 is landing")
        XCTAssertNil(ev.update(owner: .unknown, mode: "AUTO.LAND"), "link lost: no event")
        XCTAssertNil(ev.update(owner: .px4, mode: "AUTO.LAND"), "same as before the gap")
        XCTAssertEqual(ev.update(owner: .px4, mode: "AUTO.RTL"), "PX4 is returning")
        XCTAssertEqual(ev.update(owner: .px4, mode: "AUTO.TAKEOFF"), "PX4 is taking off")
        XCTAssertEqual(ev.update(owner: .px4, mode: "AUTO.MISSION"), "PX4 took control")
        XCTAssertEqual(ev.update(owner: .disarmed, mode: "AUTO.MISSION"), "Disarmed")
        ev.reset()
        XCTAssertNil(ev.update(owner: .pilot, mode: "POSCTL"), "after a reset the first look is not an event")
    }

    // MARK: - FC-lost alarm

    func testAlarmFiresOnceWhenAnArmedDroneLosesItsFC() {
        var a = FcLostAlarm()
        XCTAssertFalse(a.update(link: .ok, lastKnownArmed: true))
        XCTAssertTrue(a.update(link: .fcNotConnected, lastKnownArmed: true), "sound")
        XCTAssertTrue(a.active)
        XCTAssertFalse(a.update(link: .fcNotConnected, lastKnownArmed: true), "only once")
        XCTAssertFalse(a.update(link: .noDrone, lastKnownArmed: true))
        XCTAssertTrue(a.active, "banner stays until the link is OK again")
        XCTAssertFalse(a.update(link: .ok, lastKnownArmed: true))
        XCTAssertFalse(a.active)
        XCTAssertTrue(a.update(link: .telemetryFrozen, lastKnownArmed: true), "frozen telemetry counts too")
    }

    func testAlarmStaysQuietWhenDisarmedOrNotFromOK() {
        var a = FcLostAlarm()
        XCTAssertFalse(a.update(link: .ok, lastKnownArmed: false))
        XCTAssertFalse(a.update(link: .fcNotConnected, lastKnownArmed: false))
        XCTAssertFalse(a.active)

        var b = FcLostAlarm()
        XCTAssertFalse(b.update(link: .noDrone, lastKnownArmed: true))
        XCTAssertFalse(b.update(link: .telemetryFrozen, lastKnownArmed: true), "never was OK on this link")

        var c = FcLostAlarm()
        XCTAssertFalse(c.update(link: .ok, lastKnownArmed: true))
        XCTAssertFalse(c.update(link: .noDrone, lastKnownArmed: true), "a closed socket is a different alarm")
        XCTAssertFalse(c.active)
        XCTAssertEqual(FcLostAlarm.text, "Flight controller link lost")
    }

    // MARK: - Ping watchdog

    func testPingWatchdog() {
        XCTAssertEqual(PingWatchdog.interval, 2.0)
        XCTAssertEqual(PingWatchdog.timeout, 4.0)
        var w = PingWatchdog()
        XCTAssertFalse(w.timedOut(now: at(100)), "nothing sent")
        let a = w.sent(now: at(0))
        XCTAssertFalse(w.timedOut(now: at(3.9)))
        XCTAssertTrue(w.timedOut(now: at(4.1)))
        w.answered(a)
        XCTAssertFalse(w.timedOut(now: at(10)))

        let b = w.sent(now: at(10))
        let c = w.sent(now: at(12))
        w.answered(c)   // pongs come in order: c answers b too
        XCTAssertFalse(w.timedOut(now: at(20)))
        XCTAssertNotEqual(b, c)

        _ = w.sent(now: at(20))
        w.reset()
        XCTAssertFalse(w.timedOut(now: at(30)))
    }

    // MARK: - Switching drones

    func testConnectKind() {
        XCTAssertEqual(ConnectKind.of(previousHost: "", newHost: "10.0.0.5"), .newDrone)
        XCTAssertEqual(ConnectKind.of(previousHost: "10.0.0.4", newHost: "10.0.0.5"), .newDrone)
        XCTAssertEqual(ConnectKind.of(previousHost: "10.0.0.5", newHost: "10.0.0.5"), .sameDrone)
    }
}
