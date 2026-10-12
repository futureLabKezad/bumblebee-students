# Changelog

All notable changes to the Bumblebee student platform are documented here.
Versioning follows [SemVer](https://semver.org/); each release has a tag `vX.Y.Z`,
a release page in the [wiki](https://github.com/futureLabKezad/bumblebee-students/wiki)
and downloadable builds.

## v1.0.1 — 2026-10-12

Drone SD image **1.0.1** (`bumblebee-1.0.1-rpi5.img.xz`, release
[v1.0.1](https://github.com/futureLabKezad/bumblebee-students/releases/tag/v1.0.1))
and ground station **Bumblebee GCS 1.1.0** (release
[gcs-v1.1.0](https://github.com/futureLabKezad/bumblebee-students/releases/tag/gcs-v1.1.0)).
One image for every drone, several drones on one Wi-Fi. Flight code, cameras
and PX4 parameters are unchanged.

### Fixed
- The drone's ROS 2 nodes stopped exchanging data 1–2 minutes after start
  (Fast DDS shared-memory transport, Fast-DDS #6569). Every service now uses
  Fast DDS over UDP (`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` in the systemd drop-in
  `ros-env.conf` and in `/etc/bumblebee/ros.env`) with 4–8 MB socket buffers
  (`drone/system/sysctl.d/60-bumblebee-dds.conf`).
- No telemetry or sound when PX4's TELEM baud did not match the fixed
  `115200`: the MAVLink baud on `/dev/ttyAMA0` is now detected at every start
  (`fcu_detect.py`, read-only, remembered in `~/.bumblebee/fcu_url`; typical
  PX4 setting 921600). The `fcu_url` in `mavros_params.yaml` is only the
  fallback.
- The clock step at the first NTP sync (the Pi has no RTC) broke ROS 2:
  `start_bumblebee.sh` waits up to 20 s for it, and `bumblebee-clock-jump.timer`
  restarts the ROS services after a later jump (the flight stack only while
  PX4 reports disarmed).
- No RC signal meant "wheel full reverse": `wheel_rc.py` now stops the wheel
  when there is no signal (0 µs, or outside 800–2200 µs) or no RC frame for
  1 s, and `servo_rc.py` leaves the servo alone.
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
- Every drone flashed from the V1.0.0-beta image was named `Bumblebee-4` and
  shared the same SSH host keys and machine-id; the name is now bound to the
  wlan0 MAC and re-derived on a cloned card, and the release image generates
  its own keys and machine-id on first boot.
- macOS GCS: rescan no longer hides Bonjour-found drones; IPv6-first resolves
  no longer drop drones; Local Network denial is shown; "linked" only after
  the rosbridge socket really answers; `swift build` works again.
- `colcon build` installs the scripts that actually run on the image
  (`vpe_fix.py`, `aruco_detect.py`, `camera_fix.py` from `src/python/`) and
  the previously missing `qos_relay.py`.

### Added
- Release image `bumblebee-1.0.1-rpi5.img.xz` (2.0 GB, 8.4 GB raw, any SD
  card ≥ 16 GB; flash with Raspberry Pi Imager → *Use custom*, no OS
  customisation), built reproducibly from the V1.0.0-beta base by
  `drone/image/make_release_image.sh` and checked by
  `drone/image/verify_release_image.sh` (82 checks). First boot grows the root
  partition and generates the drone's own SSH host keys and machine-id.
- Drone identity from the wlan0 MAC (`set_identity.sh`): hostname
  `bumblebee-xxxx`, shown as `Bumblebee-XXXX`, reachable as
  `bumblebee-xxxx.local`; a custom name in `/home/lb/drone_name` is bound to
  that drone's MAC (`drone_name.mac`). The IP-derived names (`bumblebee-4` …)
  and the hostname `lb` are retired. Bonjour `_bumblebee._tcp` TXT: `name`,
  `id`, `ros_domain`, `rosbridge=9090`, `mjpeg=8080`, `metrics=8888`,
  `api=8765`.
- Several drones on one Wi-Fi: each drone has its own `ROS_DOMAIN_ID` (1–101,
  derived from the MAC by `ros_domain.py`) in `/etc/bumblebee/ros.env` (all ROS
  services and login shells) and `/etc/environment`. If another drone already
  advertises the same domain, the drone that notices moves to a free one;
  re-checked every minute (`bumblebee-identity-recheck.timer`), and the flight
  stack is only restarted onto a new domain while PX4 reports disarmed. On a
  laptop (rviz, rqt, `ros2` CLI): `export ROS_DOMAIN_ID=<n>` of that drone
  (`ros.env` on the drone, Bonjour TXT `ros_domain`, or
  `drone/tools/check_drone.sh`).
- `bumblebee-ros-watchdog.service`: restarts the ROS services if
  `/mavros/state` stops arriving through rosbridge — only while PX4 reports
  disarmed, 60 s grace, at most 3 restarts per boot, 10 min back-off.
- Wi-Fi: with no known network in range the hotspot `Bumblebee-XXXX`
  (password `12345678`, drone at `10.42.0.1`) is up within seconds; the GCS
  "Add drone" button sends the home Wi-Fi over it, and the drone reports why
  a join failed (e.g. wrong password). Wi-Fi power save is off
  (`zz-bumblebee-wifi-powersave.conf`).
- LED animation `rainbow_theater` and shows `party`, `siren`, `alarm`,
  `victory` used by the macOS GCS. The show's melody is played by
  `wifi_manager.py` (silent while armed); the LED scripts stay I2C-only.
- `drone/system/`: drone-only config captured from the image (nginx, udev,
  sudoers, NetworkManager dispatcher/conf, sysctl, profile.d, camera tuning
  and calibration).
- Update a running drone without reflashing: `drone/tools/make_bundle.sh`
  builds `bumblebee-update.tgz`; on the drone `install_on_drone.sh` installs
  it with backup and `rollback.sh` (refuses unless PX4 reports disarmed,
  `--force` on the ground; reboot afterwards). `drone/tools/deploy.sh` does
  both over SSH; `drone/tools/check_drone.sh` is a read-only health report.
- `gcs/tools/mock_drone.py`: test the GCS against the real drone backend
  without hardware. Tests in `drone/ros2_ws/src/bumblebee/test/` (Wi-Fi API
  and watchdog, identity, ROS domain, FCU baud detection, clock jump, ROS
  watchdog).
- Bumblebee GCS 1.1.0, ready to run: universal Mac `.dmg` (Apple Silicon and
  Intel, macOS 14+) and self-contained Windows 10/11 x64 `.zip`; drones are
  listed automatically by name, "Add drone" sets a new drone up. CI
  (`.github/workflows/ci.yml`) builds both and runs the drone unit tests on
  every push; a `gcs-v*` tag publishes them on a GitHub Release.

### Known issues
- Battery is not shown (the GCS shows "—"): PX4 battery measurement is off
  (`BAT1_SOURCE = -1` in `PX4_parameters/*.params`).
- ESCs beep after ~10 min at zero throttle (ESC beacon) — harmless, an ESC
  firmware setting.
- The ArUco map picture appears only when armed or in OFFBOARD
  (`aruco_detect` parameter `gate_by_flight_state`).

### Builds
- Drone SD image 1.0.1: release
  [v1.0.1](https://github.com/futureLabKezad/bumblebee-students/releases/tag/v1.0.1)
  (with `.sha256`). GCS 1.1.0 for Mac and Windows: release
  [gcs-v1.1.0](https://github.com/futureLabKezad/bumblebee-students/releases/tag/gcs-v1.1.0).
  The V1.0.0-beta builds of v1.0.0 stay available for rollback.

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
