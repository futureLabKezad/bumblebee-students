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

/// Connect-screen decisions: remembered drones by id, liveness, drone or
/// device, drone hotspots, typed addresses.
final class DiscoveryLogicTests: XCTestCase {
    private let t0 = Date(timeIntervalSince1970: 6_000_000)

    // MARK: - Remembered drones

    func testRememberedByIDNotByAddress() {
        var fleet = KnownFleet.upsert([], droneID: "20ec", name: "Bumblebee-20EC", ip: "192.168.1.50", now: t0)
        fleet = KnownFleet.upsert(fleet, droneID: "20EC", name: "Bumblebee-20EC", ip: "192.168.1.77", now: t0)
        XCTAssertEqual(fleet.count, 1, "a new address is the same drone")
        XCTAssertEqual(fleet[0].lastIP, "192.168.1.77")
        XCTAssertEqual(fleet[0].droneID, "20EC")
        XCTAssertTrue(fleet[0].verified)
    }

    func testDirectConnectionsOfTwoDronesAreTwoDrones() {
        var fleet = KnownFleet.upsert([], droneID: "AAAA", name: "Bumblebee-AAAA", ip: "10.42.0.1", now: t0)
        fleet = KnownFleet.upsert(fleet, droneID: "BBBB", name: "Bumblebee-BBBB", ip: "10.42.0.1", now: t0)
        XCTAssertEqual(fleet.map(\.droneID), ["BBBB", "AAAA"], "most recent first; same address, two drones")
    }

    func testAnIDReplacesTheUnverifiedEntryOfItsAddress() {
        var fleet = KnownFleet.upsert([], droneID: nil, name: "192.168.1.50", ip: "192.168.1.50", now: t0)
        XCTAssertFalse(fleet[0].verified)
        XCTAssertEqual(fleet[0].id, "ip:192.168.1.50")
        fleet = KnownFleet.upsert(fleet, droneID: "20EC", name: "Bumblebee-20EC", ip: "192.168.1.50", now: t0)
        XCTAssertEqual(fleet.count, 1)
        XCTAssertEqual(fleet[0].droneID, "20EC")
    }

    func testAKnownNameIsNotReplacedByAnAddress() {
        var fleet = KnownFleet.upsert([], droneID: "20EC", name: "Lab-3", ip: "192.168.1.50", now: t0)
        fleet = KnownFleet.upsert(fleet, droneID: "20EC", name: "192.168.1.51", ip: "192.168.1.51", now: t0)
        XCTAssertEqual(fleet[0].name, "Lab-3")
    }

    func testForget() {
        let fleet = KnownFleet.upsert([], droneID: "20EC", name: "x", ip: "1.2.3.4", now: t0)
        XCTAssertTrue(KnownFleet.forget(fleet, key: "20EC").isEmpty)
    }

    func testOldEntriesMoveOver() {
        let fleet = KnownFleet.migrate(hosts: [("10.0.0.5", "Bumblebee-5"), ("10.0.0.6", "Bumblebee-6")],
                                       lastHost: "10.0.0.6", now: t0)
        XCTAssertEqual(fleet.first?.lastIP, "10.0.0.6", "the old last host stays the last drone")
        XCTAssertEqual(fleet.first?.name, "Bumblebee-6")
        XCTAssertEqual(fleet.count, 2)
        XCTAssertTrue(fleet.allSatisfy { !$0.verified })
        XCTAssertTrue(KnownFleet.migrate(hosts: [], lastHost: nil, now: t0).isEmpty)
    }

    func testTheLastDroneIsFoundByItsID() {
        let last = KnownDrone(droneID: "20EC", name: "Bumblebee-20EC", lastIP: "192.168.1.50", lastSeen: t0)
        XCTAssertEqual(KnownFleet.currentIP(of: last, found: [("192.168.1.77", "20EC")]), "192.168.1.77")
        XCTAssertEqual(KnownFleet.currentIP(of: last, found: [("192.168.1.50", "ABCD")]), "192.168.1.50",
                       "not listed: its last address")
        let old = KnownDrone(droneID: "", name: "x", lastIP: "10.0.0.5", lastSeen: t0)
        XCTAssertEqual(KnownFleet.currentIP(of: old, found: [("10.0.0.9", nil)]), "10.0.0.5")
    }

    // MARK: - Liveness

    func testLiveness() {
        XCTAssertEqual(Liveness.of(misses: 0), .live)
        XCTAssertEqual(Liveness.of(misses: 1), .unsure)
        XCTAssertEqual(Liveness.of(misses: 2), .unsure)
        XCTAssertEqual(Liveness.of(misses: 3), .gone)
        XCTAssertLessThanOrEqual(Liveness.period * Double(Liveness.goneAfter), 30, "gone within about 30 s")
    }

    // MARK: - Drone or device

    func testADroneAnswersLikeADrone() {
        XCTAssertEqual(DeviceKind.classify(wifiStatus: ["mode": "client", "id": "20ec"], metrics: nil),
                       .drone(droneID: "20EC", name: "Bumblebee-20EC"))
        XCTAssertEqual(DeviceKind.classify(wifiStatus: ["mode": "client"], metrics: nil),
                       .drone(droneID: nil, name: nil), "drone software without an id")
        XCTAssertEqual(DeviceKind.classify(wifiStatus: nil, metrics: ["cpu_pct": 12.0, "name": "Bumblebee-7"]),
                       .drone(droneID: nil, name: "Bumblebee-7"), "REST down, metrics up")
    }

    func testOtherDevicesAreNotDrones() {
        XCTAssertEqual(DeviceKind.classify(wifiStatus: nil, metrics: nil), .unknownDevice)
        XCTAssertEqual(DeviceKind.classify(wifiStatus: ["status": "ok"], metrics: ["hostname": "laptop"]), .unknownDevice,
                       "a JSON answer that is not the drone's")
    }

    // MARK: - Drone hotspots

    func testHotspotRows() {
        let known = [KnownDrone(droneID: "20EC", name: "Lab-3", lastIP: "1.2.3.4", lastSeen: t0)]
        XCTAssertEqual(HotspotRow.of(ssid: "Bumblebee-20EC", known: known, visibleIDs: []), .lostWifi(name: "Lab-3"))
        XCTAssertEqual(HotspotRow.of(ssid: "Bumblebee-20EC", known: known, visibleIDs: ["20EC"]), .hidden,
                       "the same drone is on the network already")
        XCTAssertEqual(HotspotRow.of(ssid: "Bumblebee-ABCD", known: known, visibleIDs: []), .new)
        XCTAssertEqual(HotspotRow.id(of: "Bumblebee-20ec"), "20EC")
        XCTAssertNil(HotspotRow.id(of: "Classroom"))
    }

    // MARK: - Typed address

    func testManualAddress() {
        XCTAssertNil(ManualAddress.problem("192.168.1.50"))
        XCTAssertNil(ManualAddress.problem(" 10.42.0.1 "))
        XCTAssertNil(ManualAddress.problem("bumblebee-20ec.local"))
        XCTAssertNil(ManualAddress.problem("localhost"))
        XCTAssertNotNil(ManualAddress.problem("192.168.1.256"))
        XCTAssertNotNil(ManualAddress.problem("192.168.1"))
        XCTAssertNotNil(ManualAddress.problem("http://192.168.1.5"))
        XCTAssertNotNil(ManualAddress.problem("192 168 1 5"))
        XCTAssertNil(ManualAddress.problem(""), "empty: the button is disabled anyway")
    }
}
