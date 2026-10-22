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

/// The store wired to the logic types: what one rosbridge message, a drop, a
/// reconnect or a switch to another drone does to the screen state.
final class TelemetryStoreTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 3_000_000)
    private func at(_ s: Double) -> Date { t0.addingTimeInterval(s) }

    private var alerts = 0
    private func makeStore() -> TelemetryStore {
        let s = TelemetryStore()
        s.playAlert = { [weak self] in self?.alerts += 1 }
        return s
    }

    private func state(_ s: TelemetryStore, connected: Bool = true, armed: Bool, mode: String, at time: Date) {
        s.ingest(topic: "/mavros/state", msg: ["connected": connected, "armed": armed, "mode": mode], now: time)
    }

    private func fill(_ s: TelemetryStore) {
        s.socketOpened(host: "10.0.0.4", now: at(0))
        state(s, armed: true, mode: "POSCTL", at: at(0.5))
        s.ingest(topic: "/mavros/battery", msg: ["voltage": 20.4, "percentage": 0.12], now: at(0.6))
        s.ingest(topic: "/mavros/mavros/pose", msg: ["pose": [
            "position": ["x": 1.0, "y": 2.0, "z": 0.8],
            "orientation": ["x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0]]], now: at(0.7))
        s.ingest(topic: "/mavros/mavros/velocity_local", msg: ["twist": ["linear": ["x": 0.3, "y": 0.4, "z": -0.1]]], now: at(0.8))
        s.ingest(topic: "/mavros/mavros/data", msg: [
            "angular_velocity": ["x": 0.0, "y": 0.0, "z": 1.0],
            "linear_acceleration": ["x": 0.0, "y": 0.0, "z": 9.81]], now: at(0.9))
        s.ingest(topic: "/mavros/statustext/recv", msg: ["severity": 4, "text": "Low battery"], now: at(1.0))
    }

    // MARK: - Before the first value

    func testNothingIsZeroBeforeData() {
        let s = makeStore()
        XCTAssertNil(s.posX); XCTAssertNil(s.posZ); XCTAssertNil(s.vx); XCTAssertNil(s.speedH)
        XCTAssertNil(s.roll); XCTAssertNil(s.pitch); XCTAssertNil(s.yaw)
        XCTAssertNil(s.gyroMag); XCTAssertNil(s.accelMag)
        XCTAssertNil(s.battery); XCTAssertNil(s.mode); XCTAssertNil(s.armed)
        XCTAssertEqual(s.link, .noDrone)
        XCTAssertEqual(s.armedDisplay, .unknown)
    }

    // MARK: - Link and armed

    func testLinkAndArmedFollowTheState() {
        let s = makeStore()
        s.socketOpened(host: "10.0.0.4", now: at(0))
        XCTAssertEqual(s.link, .noDrone, "waiting for the first State")
        s.tick(now: at(3.5))
        XCTAssertEqual(s.link, .telemetryFrozen)
        state(s, armed: false, mode: "POSCTL", at: at(4))
        XCTAssertEqual(s.link, .ok)
        XCTAssertEqual(s.armed, false)
        XCTAssertEqual(s.armedDisplay, .disarmed)
        s.tick(now: at(7.5))
        XCTAssertEqual(s.link, .telemetryFrozen)
        XCTAssertNil(s.armed, "stale State: armed is unknown")
        XCTAssertEqual(s.armedDisplay, .unknown)
    }

    func testFCNotConnectedMakesArmedUnknown() {
        let s = makeStore()
        s.socketOpened(host: "h", now: at(0))
        state(s, armed: true, mode: "OFFBOARD", at: at(0.5))
        XCTAssertEqual(s.armedDisplay, .armed)
        XCTAssertEqual(s.owner, .program)
        // MAVROS on losing the FC: connected=false, armed=false.
        state(s, connected: false, armed: false, mode: "", at: at(1.5))
        XCTAssertEqual(s.link, .fcNotConnected)
        XCTAssertNil(s.armed)
        XCTAssertEqual(s.armedDisplay, .armedLinkLost, "never a calm DISARMED")
        XCTAssertEqual(s.owner, .unknown)
    }

    func testFCLostAlarmSoundsOnceAndShowsTheBanner() {
        let s = makeStore()
        s.socketOpened(host: "h", now: at(0))
        state(s, armed: true, mode: "OFFBOARD", at: at(0.5))
        XCTAssertFalse(s.fcLost)
        state(s, connected: false, armed: false, mode: "", at: at(1.5))
        XCTAssertEqual(alerts, 1)
        XCTAssertTrue(s.fcLost)
        s.tick(now: at(2)); s.tick(now: at(2.5))
        XCTAssertEqual(alerts, 1, "once")
        XCTAssertTrue(s.logs.contains { $0.text == "Flight controller link lost" })
        state(s, armed: false, mode: "POSCTL", at: at(3))
        XCTAssertFalse(s.fcLost, "banner goes away when the link is OK again")
    }

    func testFrozenTelemetryWhileArmedAlarms() {
        let s = makeStore()
        s.socketOpened(host: "h", now: at(0))
        state(s, armed: true, mode: "POSCTL", at: at(0.5))
        s.tick(now: at(3.0))
        XCTAssertEqual(alerts, 0)
        s.tick(now: at(3.6))
        XCTAssertEqual(s.link, .telemetryFrozen)
        XCTAssertEqual(alerts, 1)
        XCTAssertTrue(s.fcLost)
    }

    func testNoAlarmWhenDisarmed() {
        let s = makeStore()
        s.socketOpened(host: "h", now: at(0))
        state(s, armed: false, mode: "POSCTL", at: at(0.5))
        state(s, connected: false, armed: false, mode: "", at: at(1.5))
        XCTAssertEqual(alerts, 0)
        XCTAssertFalse(s.fcLost)
    }

    func testControlEventLine() {
        let s = makeStore()
        s.socketOpened(host: "h", now: at(0))
        state(s, armed: false, mode: "POSCTL", at: at(0.5))
        XCTAssertNil(s.controlEvent)
        state(s, armed: true, mode: "POSCTL", at: at(1.0))
        XCTAssertEqual(s.controlEvent?.text, "Pilot took control")
        state(s, armed: true, mode: "AUTO.LAND", at: at(1.5))
        XCTAssertEqual(s.controlEvent?.text, "PX4 is landing")
        XCTAssertEqual(s.controlEvent?.mode, "AUTO.LAND")
        XCTAssertTrue(s.logs.contains { $0.text == "PX4 is landing" })
    }

    // MARK: - Drop, reconnect, switch

    func testDropMakesArmedUnknownAndCollapsesReconnectLines() {
        let s = makeStore()
        s.socketOpened(host: "h", now: at(0))
        state(s, armed: true, mode: "POSCTL", at: at(0.5))
        s.socketDropped(wasLinked: true, now: at(1))
        XCTAssertEqual(s.link, .noDrone)
        XCTAssertEqual(s.armedDisplay, .armedLinkLost)
        for i in 0..<5 { s.socketDropped(wasLinked: false, now: at(4 + Double(i) * 3)) }
        let down = s.logs.filter { $0.key == "rosbridge-down" }
        XCTAssertEqual(down.count, 1)
        XCTAssertEqual(down.first?.line, "rosbridge lost — reconnecting… ×6")
        // The State from the old socket does not make the new socket OK.
        s.socketOpened(host: "h", now: at(20))
        XCTAssertNotEqual(s.link, .ok)
    }

    func testReconnectKeepsTheLogButNotTheArmedFlag() {
        let s = makeStore()
        fill(s)
        let logCount = s.logs.count
        s.resetForReconnect()
        XCTAssertNil(s.armed)
        XCTAssertEqual(s.armedDisplay, .armedLinkLost, "it was armed: never DISARMED after Cmd+R")
        XCTAssertNil(s.mode)
        XCTAssertFalse(s.rosConnected)
        XCTAssertEqual(s.logs.count, logCount, "same drone keeps its log")
        XCTAssertFalse(s.posTrail.isEmpty)
    }

    func testSwitchingDronesClearsEverything() {
        let s = makeStore()
        fill(s)
        XCTAssertNotNil(s.lowBattery)
        s.resetAll()
        XCTAssertTrue(s.posTrail.isEmpty)
        XCTAssertTrue(s.chartAlt.isEmpty); XCTAssertTrue(s.chartSpd.isEmpty); XCTAssertTrue(s.chartBat.isEmpty)
        XCTAssertTrue(s.logs.isEmpty)
        XCTAssertNil(s.posX); XCTAssertNil(s.posY); XCTAssertNil(s.posZ)
        XCTAssertNil(s.vx); XCTAssertNil(s.vy); XCTAssertNil(s.vz)
        XCTAssertNil(s.roll); XCTAssertNil(s.pitch); XCTAssertNil(s.yaw)
        XCTAssertNil(s.gyroMag); XCTAssertNil(s.accelMag)
        XCTAssertNil(s.battery); XCTAssertNil(s.lowBattery)
        XCTAssertNil(s.mode); XCTAssertNil(s.armed); XCTAssertNil(s.lastKnownArmed)
        XCTAssertEqual(s.armedDisplay, .unknown)
        XCTAssertNil(s.controlEvent)
        XCTAssertFalse(s.fcLost)
        XCTAssertNil(s.poseAt); XCTAssertNil(s.velocityAt); XCTAssertNil(s.imuAt)
        XCTAssertNil(s.batteryAt); XCTAssertNil(s.attitudeAt); XCTAssertNil(s.stateAt)
    }

    func testLateRosbridgeDataFromThePreviousConnectionIsDropped() {
        let s = makeStore()
        let client = RosbridgeClient(store: s)
        let old = client.generation
        let msg = #"{"op":"publish","topic":"/mavros/mavros/pose","msg":{"pose":{"position":{"x":5.0,"y":6.0,"z":1.0},"orientation":{"x":0,"y":0,"z":0,"w":1}}}}"#
        client.deliver(text: msg, gen: old)
        XCTAssertEqual(s.posX, 5.0, "current generation is applied")
        s.resetAll()
        client.disconnect()   // what connect(to: another drone) does first
        client.deliver(text: msg, gen: old)
        XCTAssertNil(s.posX, "late message of the old socket is ignored")
        client.deliver(text: msg, gen: client.generation)
        XCTAssertEqual(s.posX, 5.0)
    }

    func testLateMetricsFromThePreviousDroneAreDropped() {
        let m = MetricsClient()
        let old = m.generation
        m.apply(["cpu_temp": 51.0, "cpu_pct": 12.0], gen: old, now: at(0))
        XCTAssertEqual(m.metrics.cpuTemp, 51.0)
        XCTAssertEqual(m.lastAt, at(0))
        m.reset()
        XCTAssertNil(m.metrics.cpuTemp)
        XCTAssertNil(m.lastAt)
        m.apply(["cpu_temp": 70.0], gen: old, now: at(1))
        XCTAssertNil(m.metrics.cpuTemp, "reply to the old drone's request")
        m.apply(["cpu_temp": 40.0], gen: m.generation, now: at(2))
        XCTAssertEqual(m.metrics.cpuTemp, 40.0)
    }

    // MARK: - Battery and log

    func testBatterySentinelIsNotMeasured() {
        let s = makeStore()
        let client = RosbridgeClient(store: s)
        // PX4 with BAT1_SOURCE=-1, voltage NaN as rosbridge may send it.
        client.deliver(text: #"{"op":"publish","topic":"/mavros/battery","msg":{"voltage":NaN,"percentage":-0.01}}"#,
                       gen: client.generation)
        XCTAssertEqual(s.battery, .notMeasured)
        s.ingest(topic: "/mavros/battery", msg: ["voltage": 65.535, "percentage": -0.01], now: at(1))
        XCTAssertEqual(s.battery, .notMeasured)
        XCTAssertTrue(s.chartBat.isEmpty)
        XCTAssertNil(s.lowBattery)
    }

    func testLowBatteryIsLoggedOnceWithABanner() {
        let s = makeStore()
        for i in 0..<60 {
            s.ingest(topic: "/mavros/battery", msg: ["voltage": 20.4, "percentage": 0.12], now: at(Double(i)))
        }
        XCTAssertEqual(s.logs.filter { $0.text.hasPrefix("WARNING LOW BATTERY") }.count, 1)
        XCTAssertEqual(s.lowBattery, "Low battery: 20.40 V · 12%")
        s.ingest(topic: "/mavros/battery", msg: ["voltage": 23.0, "percentage": 0.25], now: at(61))
        XCTAssertNil(s.lowBattery)
    }

    func testPX4MessagesSurviveALongOutage() {
        let s = makeStore()
        for i in 0..<3 {
            s.ingest(topic: "/mavros/statustext/recv", msg: ["severity": 4, "text": "warning \(i)"], now: at(Double(i)))
        }
        s.ingest(topic: "/mavros/statustext/recv", msg: ["severity": 6, "text": "info is not shown"], now: at(3))
        s.socketOpened(host: "h", now: at(4))
        for i in 0..<40 { s.socketDropped(wasLinked: i == 0, now: at(5 + Double(i) * 3)) }
        for i in 0..<40 { s.log("app line \(i)") }
        XCTAssertEqual(s.logs.filter { $0.source == .fcu }.count, 3)
        XCTAssertEqual(s.logs.filter { $0.text.hasPrefix("[FCU]") }.count, 3)
    }

    // MARK: - Attitude

    func testAttitudeFromIMUOrientationWithPoseFallback() {
        let s = makeStore()
        let h = 5.0 * Double.pi / 180
        s.ingest(topic: "/mavros/mavros/pose", msg: ["pose": [
            "position": ["x": 0.0, "y": 0.0, "z": 0.0],
            "orientation": ["x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0]]], now: at(0))
        XCTAssertEqual(s.pitch ?? 99, 0, accuracy: 1e-9)
        XCTAssertNil(s.gyroMag)
        s.ingest(topic: "/mavros/mavros/data", msg: [
            "orientation": ["x": 0.0, "y": sin(h), "z": 0.0, "w": cos(h)],
            "orientation_covariance": [0.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "angular_velocity": ["x": 0.0, "y": 0.0, "z": 0.0],
            "linear_acceleration": ["x": 0.0, "y": 0.0, "z": 9.81]], now: at(0.5))
        XCTAssertEqual(s.pitch ?? 0, 10, accuracy: 1e-9, "IMU orientation wins")
        XCTAssertEqual(s.attitudeAt, at(0.5))
        s.ingest(topic: "/mavros/mavros/pose", msg: ["pose": [
            "position": ["x": 0.0, "y": 0.0, "z": 0.0],
            "orientation": ["x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0]]], now: at(1))
        XCTAssertEqual(s.pitch ?? 0, 10, accuracy: 1e-9, "pose does not overwrite a fresh IMU attitude")
        XCTAssertEqual(s.posZ, 0)
        XCTAssertEqual(s.poseAt, at(1))
        // IMU without orientation (covariance -1) does not touch the angles.
        s.ingest(topic: "/mavros/mavros/data", msg: [
            "orientation": ["x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0],
            "orientation_covariance": [-1.0, 0, 0, 0, 0, 0, 0, 0, 0],
            "angular_velocity": ["x": 0.0, "y": 0.0, "z": 0.0],
            "linear_acceleration": ["x": 0.0, "y": 0.0, "z": 9.81]], now: at(1.5))
        XCTAssertEqual(s.pitch ?? 0, 10, accuracy: 1e-9)
        XCTAssertEqual(s.accelMag ?? 0, 9.81, accuracy: 1e-9)
        XCTAssertEqual(s.imuAt, at(1.5))
    }
}
