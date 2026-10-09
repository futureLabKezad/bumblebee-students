# Changelog

All notable changes to the Bumblebee student platform are documented here.
Versioning follows [SemVer](https://semver.org/); each release has a tag `vX.Y.Z`,
a release page in the [wiki](https://github.com/futureLabKezad/bumblebee-students/wiki)
and downloadable builds.

## Unreleased

### Fixed
- GCS Wi-Fi hand-off always reported failure: the drone switched networks
  before replying to `apply-now`. The drone now replies first; the macOS GCS
  also tolerates the lost reply from older drones.
- Drone re-raised its hotspot (with a new random SSID) 5 s into a GCS- or
  watchdog-initiated join, so returning from the hotspot to a known network
  rarely worked. Deliberate switches are now marked and left alone; a failed
  join (GCS-requested or the watchdog's own) brings the hotspot straight back
  (with a 10 min back-off per network),
  the hotspot is not dropped while the GCS uses it or after "hotspot mode" was
  chosen in the GCS, the newest provisioned / visible network is tried first,
  and the SSID is stable: `Bumblebee-<hwid>`.
- Every drone flashed from the V1.0.0-beta image was named `Bumblebee-4`;
  the name is now bound to the wlan0 MAC and re-derived on a cloned card.
- macOS GCS: rescan no longer hides Bonjour-found drones; IPv6-first resolves
  no longer drop drones; Local Network denial is shown; "linked" only after
  the rosbridge socket really answers; `swift build` works again.
- `colcon build` installs the scripts that actually run on the image
  (`vpe_fix.py`, `aruco_detect.py`, `camera_fix.py` from `src/python/`) and
  the previously missing `qos_relay.py`.

### Added
- LED animation `rainbow_theater` and shows `party`, `siren`, `alarm`,
  `victory` used by the macOS GCS. The show's melody is played by
  `wifi_manager.py` (silent while armed); the LED scripts stay I2C-only.
- `drone/system/`: drone-only config captured from the image (nginx, udev,
  sudoers, NetworkManager dispatcher/conf, camera tuning and calibration).
- `drone/tools/deploy.sh`: update a running drone with backup and rollback.
- `gcs/tools/mock_drone.py`: test the GCS against the real drone backend
  without hardware. Tests: `test/test_wifi_manager.py` (REST API, fake
  nmcli) and `test/test_wifi_watchdog.py` (watchdog against a simulated
  NetworkManager).

## v1.0.0 — 2026-07-29

First official release.

### Added
- `drone/` — complete on-board source code extracted from the official SD image `030726`
  (ROS 2 Jazzy workspace: `bumblebee`, `aruco_pose`, `bumblebee_bridge`,
  `bumblebee_description`; systemd units and system scripts).
- `examples/` — `drone.py` flight API and flight/LED/misc example scripts.
- `simulation/` — `bumblebee_sim` ROS 2 package with the `clover_aruco` Gazebo world
  (grass field, cable towers, landing pad, ArUco markers) and Windows installer scripts.
- `gcs/` — Ground Control Station sources for macOS (SwiftUI) and Windows (WinUI 3),
  including the SimDrone localhost mock.
- `lectures/` — three lecture decks and the Lecture 1 Python notebook.
- Wiki: setup guides for Gazebo on Windows/macOS, Ground Control Station,
  SD Card Image; Downloads section with hosted builds.
- Apache License 2.0 (`LICENSE`, `NOTICE`).

### Builds
- Gazebo simulator for Windows, GCS for Windows/macOS, drone SD-card image —
  links and SHA-256 checksums on the release page in the wiki.
