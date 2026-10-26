# 🛠️ Drone Source Code

The complete on-board software of the Bumblebee drone, originally extracted from the official SD card image (`030726` / V1.0.0-beta, see [SD Card Image](https://github.com/futureLabKezad/bumblebee-students/wiki/SD‐Card‐Image)). The current release image **1.0.1** (`bumblebee-1.0.1-rpi5.img.xz`, [release v1.0.1](https://github.com/futureLabKezad/bumblebee-students/releases/tag/v1.0.1)) is that V1.0.0-beta base with the files of `tools/MANIFEST` from this tree installed and the per-drone state removed, built by `image/make_release_image.sh`. On the drone this lives in `/home/lb/ros2_ws/src`.

## Layout

| Path | What it is |
| --- | --- |
| `ros2_ws/src/bumblebee/` | Main package: C++ flight core `simple_offboard`, launch files, `scripts/` (wifi manager/watchdog, identity and ROS domain, flight-controller baud detection, ROS watchdog, LED, sys metrics, RC helpers), `examples/` (drone.py, LED/sound shows), web dashboard `www/`, `test/` |
| `ros2_ws/src/aruco_pose/` | ArUco marker detection and map-based pose estimation |
| `ros2_ws/src/bumblebee_bridge/` | I2C bridge to the ATtiny companion (LED strips, gripper servo, wheel) |
| `ros2_ws/src/bumblebee_description/` | URDF model and meshes of the drone |
| `system/systemd/` | systemd units: `bumblebee.service` (+ drop-ins), `wifi-manager`, `wifi-watchdog`, `notify-manager`, `sys_metrics`, `bumblebee-identity` (+ `bumblebee-identity-recheck.timer`), `bumblebee-clock-jump.timer`, `bumblebee-ros-watchdog`, I2C recovery; `ros-env.conf` (ROS domain + Fast DDS over UDP for every ROS service) |
| `system/start_bumblebee.sh` | Entry point started by `bumblebee.service` (waits up to 20 s for the first NTP sync, detects the flight-controller baud, reads the drone's ROS domain) |
| `system/mavros_params.yaml` | MAVROS configuration (`/home/lb/mavros_params.yaml` on the drone); its `fcu_url` (`/dev/ttyAMA0:115200`) is only the fallback of `ros2_ws/src/bumblebee/scripts/fcu_detect.py` |
| `system/networkmanager/` | NetworkManager hooks (hotspot fallback, identity) and Wi-Fi power save off |
| `system/sysctl.d/`, `system/profile.d/` | Bigger socket buffers for Fast DDS; the drone's ROS domain for login shells |
| `system/i2c_recover.sh` | I2C bus recovery run at boot (`/usr/local/sbin/` on the drone) |
| `image/` | `make_release_image.sh` builds the release SD image from the V1.0.0-beta base; `verify_release_image.sh` checks it (82 checks) |
| `tools/` | Update a running drone (`make_bundle.sh`, `install_on_drone.sh`, `deploy.sh`, `MANIFEST`) and `check_drone.sh` (read-only health report) |

## Building on the drone

```bash
ssh lb@bumblebee-xxxx.local  # or lb@<drone-ip>; password: lb
source /opt/ros/jazzy/setup.bash
cd ~/ros2_ws
colcon build --symlink-install --packages-select bumblebee
```

How it all fits together: [System Architecture](https://github.com/futureLabKezad/bumblebee-students/wiki/System‐Architecture) · [Launch Pipeline](https://github.com/futureLabKezad/bumblebee-students/wiki/Launch‐Pipeline) · [System Services](https://github.com/futureLabKezad/bumblebee-students/wiki/System‐Services)

## Drone name and ROS domain

Every drone runs the same image. `ros2_ws/src/bumblebee/scripts/set_identity.sh` names it after its wlan0 MAC: hostname `bumblebee-xxxx` (last 4 hex digits), shown as `Bumblebee-XXXX` (also its hotspot SSID), reachable as `bumblebee-xxxx.local`. A custom name goes in `/home/lb/drone_name` (bound to that drone's MAC in `drone_name.mac`). Before 1.0.1 drones took IP-derived names (`bumblebee-4` …); those are retired.

Each drone also gets its own `ROS_DOMAIN_ID` (1–101, `ros2_ws/src/bumblebee/scripts/ros_domain.py`), written to `/etc/bumblebee/ros.env` and `/etc/environment`, so drones on one Wi-Fi never see each other's topics. A clash with another drone is resolved automatically (re-checked every minute; the flight stack only moves while PX4 reports disarmed). On a laptop running rviz, rqt or the `ros2` CLI, set the drone's domain first:

```bash
export ROS_DOMAIN_ID=<n>     # n: ros.env on the drone, Bonjour TXT ros_domain, or tools/check_drone.sh
```

Every ROS service and login shell also runs Fast DDS over UDP (`FASTDDS_BUILTIN_TRANSPORTS=UDPv4` in `system/systemd/ros-env.conf` and `ros.env`) with bigger socket buffers (`system/sysctl.d/60-bumblebee-dds.conf`): with the default shared-memory transport the drone's nodes stopped exchanging data 1–2 minutes after start (Fast-DDS #6569). Discovery keeps the ROS default range (subnet), so a laptop on the same Wi-Fi with the drone's domain sees its topics.

The stack restarts itself after a clock jump (the Pi has no RTC; `start_bumblebee.sh` waits up to 20 s for the first NTP sync, `bumblebee-clock-jump.timer` handles a later one) and when `/mavros/state` stops arriving through rosbridge (`bumblebee-ros-watchdog`: 60 s grace, at most 3 restarts per boot, 10 min back-off). The flight stack is only restarted while PX4's own heartbeat says disarmed.

## Updating a running drone

The update installs the files listed in `tools/MANIFEST`. It backs up everything
it replaces and writes `~/.bumblebee-update/<timestamp>/rollback.sh`, refuses to
run unless PX4 reports disarmed (`--force` skips the check, only with the drone on
the ground), and only restarts the Wi-Fi / metrics / identity services and the
ROS watchdog; it does not restart `bumblebee.service` itself. (On a drone coming
from V1.0.0-beta, the `bumblebee-identity` run may restart the flight stack once
to move it onto the drone's own ROS domain, only while PX4 reports disarmed.)
It also refuses while an Ubuntu package update runs (`unattended-upgrade`,
`apt`, `dpkg`; no `--force` for that), and switches Ubuntu's automatic updates
off: `apt-daily.timer` and `apt-daily-upgrade.timer` are disabled and
`/etc/apt/apt.conf.d/99-bumblebee-no-auto-upgrades` sets `APT::Periodic` to 0.
On a drone in class they installed packages and restarted the ROS stack while
it was in use; system updates come with Bumblebee releases instead. Rollback
switches them back on.
**Reboot the drone afterwards** (`sudo reboot`) to finish.

Build a bundle and copy it to the drone by any means (scp, USB stick):

```bash
drone/tools/make_bundle.sh                       # -> bumblebee-update.tgz
# on the drone, as lb:
tar -xzf bumblebee-update.tgz && bash bb-update/install_on_drone.sh
```

The bundle carries the version in `drone/VERSION` (e.g. `1.0.2-rc1`) and the
commit it was built from. The install writes them as the first line of
`/etc/bumblebee_version` (the image's own lines follow, prefixed `before:`), so
`GET /api/info` and `check_drone.sh` report the update; rollback restores the
old file.

Or do both over SSH from a laptop:

```bash
drone/tools/deploy.sh bumblebee-xxxx.local       # keeps the drone's current name
drone/tools/deploy.sh <drone-ip> --reset-name    # forget a custom name in /home/lb/drone_name
```

Roll back with `bash ~/.bumblebee-update/<timestamp>/rollback.sh` on the drone,
then reboot it (`sudo reboot`): until then the flight stack keeps running with
the update.

Health check (read-only, changes nothing): copy `tools/check_drone.sh` to the drone and run `bash check_drone.sh` as lb.

## Tests

```bash
pip install tornado bcrypt
(cd drone/ros2_ws/src/bumblebee && python3 -m unittest discover -v -s test -p 'test_*.py')
python3 gcs/tools/mock_drone.py     # mock drone for the GCS apps (real wifi_manager.py)
```

CI (`.github/workflows/ci.yml`) runs the same tests on every push.
