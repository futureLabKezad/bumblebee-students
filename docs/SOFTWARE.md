# Bumblebee.O — Software Description

*Educational quadcopter «BUMBLEBEE.O». Version of this description: 2026-11-23. Русская версия: [SOFTWARE_RU.md](SOFTWARE_RU.md).*

This page describes the software that runs on the Bumblebee drones **today** and how students work with it.
Downloads (SD-card image, updates, ground station, simulator) are on the [main page of this repository](../README.md).

> **Two code lines.** The public release you can download is **drone image 1.0.1 + update 1.0.2** (branch `main`).
> The drones of the Future Lab polygon run a newer, safer flight code **r2j** (branch `feat/drone-image-r2j`, not yet in `main`)
> plus two trial changes (pose filter V1.1 and front-camera frame-rate cut, branches `exp/posefix-v11`, `exp/camera-r2m-cam`).
> Where the two lines behave differently, this page says so with **[r2j]** and **[1.0.2]**.

## 1. Architecture

| Level | Where it runs | What it does |
|---|---|---|
| 1 — On-board software | Raspberry Pi 5 on the drone + PX4 on the Pixhawk 6C | Flight control, sensors, ArUco positioning, ROS 2 |
| 2 — Ground station and student tools | Student's laptop / PC | Bumblebee GCS app; Python flight programs (`drone.py`); rviz2 / rqt |
| 3 — Simulator | Student's PC (Windows, WSL2) | Gazebo Harmonic + PX4 SITL: test a program before the real drone |

The laptop and the drone talk over Wi-Fi (ROS 2 / DDS, MAVLink, HTTP). Gazebo and PX4 are third-party open-source projects;
we supply the integration and a ready image.

## 2. On-board software (Raspberry Pi 5)

The drone starts everything by itself (systemd service `bumblebee` → `ros2 launch bumblebee bumblebee.launch.py`).

### 2.1 Operating system and middleware

| Component | Version on the drone | Role |
|---|---|---|
| Ubuntu Server | 24.04.4 LTS, kernel 6.8.0-1065-raspi | Operating system |
| ROS 2 | Jazzy Jalisco (LTS) | Middleware for the on-board nodes |
| MAVROS | 2.14 with three upstream fixes (#2138, #2149, #2093), own build | Bridge ROS 2 ↔ PX4 (MAVLink 2) |
| libcamera | built from source (Raspberry Pi fork) | Camera driver |
| Python | 3.12 | Student programs and part of the nodes |

### 2.2 Network

- **Client mode:** the drone joins your Wi-Fi (DHCP). Its name is `Bumblebee-XXXX` (from the Wi-Fi MAC); the GCS finds it by name.
- **Hotspot mode:** with no known Wi-Fi around, the drone raises its own network `Bumblebee-XXXX` (password `12345678`), drone address `10.42.0.1`.
  Press **Add drone** in the GCS to move the drone to your Wi-Fi.
- **Several drones on one Wi-Fi:** each drone has its own ROS domain. Before `ros2`, rviz2 or rqt on a laptop run
  `export ROS_DOMAIN_ID=<n>` with that drone's number (see [drone/README.md](../drone/README.md)).
- **SSH:** user `lb`. The default password is in [drone/README.md](../drone/README.md) — **change it after the first boot.**

### 2.3 Flight controller

| Item | Value |
|---|---|
| Hardware | Holybro Pixhawk 6C, separate from the Raspberry Pi |
| Firmware | PX4 Autopilot 1.16.1 (`px4_fmu-v6c_default`) |
| Airframe | Generic Quadrotor X (`SYS_AUTOSTART` 4001); motors by PWM 400 Hz |
| Link to the Pi | MAVLink 2, UART `/dev/ttyAMA0`, **921 600 baud** (the drone finds the speed itself at start) |
| Optical flow and rangefinder | Holybro H-Flow over CAN (DroneCAN) |
| QGroundControl | over Wi-Fi, TCP port 5760 |

Flight modes used: **Stabilized, Altitude, Position** (RC switch, channel 6), **Offboard** (student programs), **Land**.
PX4 settings of the training drones limit the horizontal speed to 0.25 m/s.

### 2.4 ROS 2 nodes on the drone

| Node | What it does |
|---|---|
| `/mavros` | Link to PX4: telemetry, commands, parameters |
| `/simple_offboard` | High-level flight services: `navigate`, `land`, `get_telemetry`, `set_position`, `set_velocity`, `set_attitude`, `set_rates`, `set_yaw`, `set_yaw_rate`, `set_altitude`, `navigate_global`, `release`. **[r2j]** lands the drone 2 s after a flight script dies (script lease) |
| `/aruco_detect` | Finds ArUco markers in the down camera, computes the drone pose on the marker map |
| `/vpe_publisher` (`vpe_fix.py`) | **Sends the pose from the markers to PX4** (vision position, ~30 Hz). Second job: safe PX4 parameter writes (`/vpe_fix/set_param`, `/vpe_fix/revert_all`). **[r2j]** sends poses only in OFFBOARD and LAND |
| `setpoint_freshness` **[r2j]** | Drops stale (> 0.5 s) flight commands before MAVROS |
| `main_camera`, `second_camera` (+ `*_camera_fix`) | Down and front cameras. **[trial r2m_cam]** front camera thinned to 5 frames/s |
| `wheel_rc`, `servo_rc` | Wheel module (RC channel 7) and clamp servo (RC channel 9) |
| `rosbridge_websocket`, `ros_mjpeg_server` (port 8080), `tf2_web_republisher` | Web access: GCS, web panel, camera video |
| static TF, `qos_relay`, `bumblebee_unified_controller` | Frames, QoS bridging, LED/servo board |

Separate services (not ROS launch): `notify-manager` (LED and sound notifications), `wifi-manager`, watchdogs.

### 2.5 Positioning (no GPS)

- Position comes from **ArUco markers on the floor** seen by the down fisheye camera; PX4 fuses it with the H-Flow optical flow and rangefinder.
- Marker map of the polygon (`aruco_pose/map/map.txt`): **20 markers, ID 0–16, 18, 19, 20** (no 17); marker 0 is 0.19 m, the others 0.29 m.
- Heading lock: 2 markers for 1.5 s, **or** one marker for 3 s with a heading spread under 8°.
- **[trial V1.1]** a doubtful single-marker pose is sent to PX4 with a large error instead of being dropped.

### 2.6 LED, sound, wheel and clamp

- LED: 6 strips (`LED_1` … `LED_6`), pixels 0–10, board on I2C `/dev/i2c-1`, address `0x30`.
  Animations `led_solid`, `led_blink`, `led_breathe`, `led_rainbow`, `led_rotate`, `led_wipe`, `led_pulse`, `led_strobe`; pixels with `set_led(strip, led, r, g, b)`.
- Sound: the **PX4 flight-controller buzzer** plays the tunes (`/mavros/play_tune`): `play_sound('takeoff')`, `play_tune(drone.TUNE_MARIO)`, `list_sounds()`.
- I2C board `0x30`: servo angle 0–255, wheel motor speed 0–255 (128 = stop), two temperatures (`read_temperature()`).

## 3. Working from the laptop

| Tool | What for |
|---|---|
| **Bumblebee GCS 1.3.0** (Windows 10/11 x64, macOS 14+) | Finds drones by name, adds a new drone to your Wi-Fi, shows telemetry, LED and sound. **Watch-only:** it never arms, changes mode or writes PX4 parameters. **Flight** section: marker-map editor with a map of how many markers the camera sees, Python program check, 2D simulation. *The mission server it talks to is not installed on any drone yet.* |
| SSH / VS Code Remote-SSH | Edit and run programs on the drone |
| rviz2, rqt, rqt_image_view | Pose, markers, TF, topics (set `ROS_DOMAIN_ID` first) |
| QGroundControl | PX4 parameters and calibration (teacher) |

Student programs live on the drone in `~/ros2_ws/src/bumblebee/examples/`.

## 4. `drone.py` — Python library

```python
import sys
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone
```

### 4.1 Start and safety
| Function | Description |
|---|---|
| `enable_safe_interrupt()` | Ctrl+C sets `should_land=True` so the script can land cleanly |
| `check_flight_profile(profile_name)` **[r2j]** | Reads the PX4 profile `INDOOR_ARUCO_SLOW`; the examples refuse to take off (exit code 3) if it differs |
| `get_fcu_status()`, `read_px4_params()` | Flight-controller state, read PX4 parameters |

### 4.2 Telemetry
| Function | Returns |
|---|---|
| `get_telemetry(frame_id=...)` | x, y, z, vx, vy, vz, roll, pitch, yaw, voltage, mode, armed, connected |
| `get_pos(frame_id='map')` | `(x, y, z)` |
| `print_pos(phase='INFO')`, `print_pos_fresh()` | Prints `[phase] x=… y=… z=… armed=… mode=…` |
| `vision_pose_age()` | Seconds since the last marker pose |

### 4.3 Flight (blocking)
| Function | Defaults | Description |
|---|---|---|
| `takeoff(height=1.0, speed=0.4, vision_timeout=25.0)` | | Arms (after checks) and climbs; climb timeout 30 s |
| `fly_to(x, y, z=1.0, speed=0.5)` | `tolerance=0.2` | Fly to a point in `map` |
| `move(x=0, y=0, z=0, speed=0.5)` | | Move relative to the drone (`body`: forward / left / up) |
| `navigate_wait(...)` | `frame_id='body'`, `vision_timeout=6.0` | Full control: frame, yaw, tolerance, timeout |
| `hover(seconds=3.0)` | | Hold position |
| `safe_land(x=None, y=None)` | `precision_tolerance=0.07`, `timeout=25` | Recommended landing; over a point if given; checks touchdown |
| `land()` | | Sends LAND and returns at once |

### 4.4 Flight (non-blocking) and modes
| Function | Description |
|---|---|
| `navigate(**kwargs)` | Sends a target and returns at once |
| `set_mode(mode)` | Change PX4 mode. **[r2j]** refused while a pilot flies (armed, not OFFBOARD) |
| `arming(value)` | **[r2j]** `arming(True)` is always refused — motors start only through `takeoff()` / `navigate(auto_arm=True)` after checks; `arming(False)` works only on the ground. **[1.0.2]** arms and disarms |
| `set_param(param_id, value, ttl_sec=0.0, persistent=False)` | PX4 parameter through `vpe_fix`, reverted on disarm |
| `apply_flight_profile(name)` | **[r2j]** only checks (writes nothing; set values once in QGC). **[1.0.2]** writes `INDOOR_ARUCO` / `INDOOR_ARUCO_SLOW` |

`set_position`, `set_velocity`, `set_attitude`, `set_rates`, `set_yaw`, `set_yaw_rate` are **ROS services** of `simple_offboard`, not `drone.py` functions.

### 4.5 Markers
| Function | Description |
|---|---|
| `check_aruco(timeout=10, min_markers=1)` | **[r2j]** returns the list of seen IDs (empty = none) |
| `require_aruco(min_markers=1, timeout=15.0)` | Raises `RuntimeError` if not enough markers |
| `set_aruco_map(markers, map_file)` | **[r2j]** checks the script's map against the drone's map (error on mismatch). **[1.0.2]** writes the map |
| `wait_yaw_lock(timeout)`, `yaw_lock_age()` | Wait for heading lock; seconds since the last lock |
| `require_vpe_link(min_hz=8.0, timeout=15.0)` | Wait for a steady pose stream to PX4 |
| `wait_position_stable(stable_secs=3, ...)` | Wait until the PX4 position is steady (0.15 m) |

### 4.6 LED, sound, servo
`set_led`, `led_solid`, `led_blink`, `led_breathe`, `led_rainbow`, `led_rotate`, `led_wipe`, `led_pulse`, `led_strobe`, `led_off`,
`led_take_control`, `led_release_control`, `play_sound(name)`, `play_tune(tune)`, `list_sounds()`, `beep()`,
`set_servo_angle`, `set_servo_speed`, `read_temperature`.

### 4.7 Built-in guards (during every manoeuvre)
- No new marker pose for 6 s (25 s during takeoff) → **LAND**.
- No telemetry for more than 5 s → manoeuvre refused, **LAND**.
- Position jump faster than ~3 m/s → **LAND**.
- Height more than 0.5 m below the arming point → **[r2j] LAND** ([1.0.2] disarm).
- **[r2j]** Climb 0.6 m above the target → **LAND**; script dies → `simple_offboard` lands in 2 s.

## 5. Coordinate frames

| `frame_id` | Zero | Use |
|---|---|---|
| `map` | Zero of the marker map (marker 0 in `map.txt`) | Absolute points: `fly_to(1.5, 0, 1.0)` |
| `body` | Drone centre, X forward, Y left, Z up | Relative moves: `move(1.0, 0, 0)` = 1 m forward |
| `aruco_<id>` | Centre of marker `<id>` (while it is in view) | Fly / land over a marker |

ROS convention: +X forward, **+Y left**, +Z up.

## 6. Main ROS 2 topics and services

| Name | Type | Notes |
|---|---|---|
| `/mavros/mavros/pose` | `geometry_msgs/PoseStamped` | PX4 position and attitude (remapped from `local_position/pose`) |
| `/mavros/mavros/velocity_body` | `geometry_msgs/TwistStamped` | Velocity in the drone frame |
| `/mavros/state` | `mavros_msgs/State` | Mode, armed, connected (RELIABLE + TRANSIENT_LOCAL) |
| `/aruco_detect/markers` | `aruco_pose/MarkerArray` | Markers seen in the frame |
| `/aruco_detect/markers_used` | `std_msgs/Int32` | Number of markers used for the pose, every frame |
| `/aruco_detect/yaw_locked` | `std_msgs/Bool` | Heading lock, every frame |
| `/navigate`, `/get_telemetry`, `/land` | services of `simple_offboard` | Fly to a point, telemetry, land |
| `/vpe_fix/set_param`, `/vpe_fix/revert_all` | services | Safe PX4 parameter write / revert |

Publisher and subscriber QoS must match — otherwise data silently does not arrive.

## 7. Examples

Ready scripts: `examples/flight/flight.py`, `flight_marker.py`, `flight_marker_loop.py` (they check the PX4 profile first).

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

drone.enable_safe_interrupt()
if not drone.check_aruco(timeout=10):
    sys.exit("No markers seen.")
if not drone.wait_position_stable(stable_secs=3):
    sys.exit("Position is not steady.")
drone.takeoff(0.9)
drone.hover(5.0)
drone.safe_land(x=0, y=0)
```

```python
drone.takeoff(0.9)
drone.fly_to(1.5, 0.0, 0.9)    # +X of the marker map
drone.fly_to(1.5, 1.5, 0.9)    # +Y of the map (left of +X)
drone.fly_to(0.0, 0.0, 0.9)    # back to the map zero
drone.safe_land()
```

```python
drone.led_solid(0, 255, 0, duration=2.0)   # green: ready
drone.play_sound('takeoff')
drone.takeoff(0.9)
drone.safe_land()
drone.play_sound('land')
```

Take off to about 0.9 m or higher: PX4 learns the hover thrust only above ~1 m.

## 8. Simulator (Gazebo)

- **Gazebo Harmonic + PX4 SITL** (PX4 v1.16.0, model `gz_x500_mono_cam_down`) with the same ROS 2 nodes (`aruco_detect`, `vpe_fix`, `simple_offboard`) and the same `drone.py`
  (LED, buzzer, servo and wheel are stubs).
- **Windows:** ready WSL2 image `BumblebeeSim` (~3.7 GB, link on the main page); run a program with `sim-run flight.py`.
  Linux: `ros2 launch bumblebee_sim bumblebee_sim.launch.py` or `run_sim.sh`.
- MAVROS ↔ PX4 SITL: `udp://:14540@127.0.0.1:14580`.
- **Important:** the simulator is not the drone. Gazebo processes the camera about 3 times faster than the Raspberry Pi
  (drone detector ≈ 8.5 frames/s) and uses its own marker map. A program that flies in Gazebo must still be tested carefully on the drone.

## 9. Versions and licences

| Component | Where | Version | Author | Licence |
|---|---|---|---|---|
| Ubuntu Server | drone | 24.04.4 LTS | Canonical | open source |
| ROS 2 | drone, PC | Jazzy | Open Robotics | Apache 2.0 |
| MAVROS | drone | 2.14 + fixes | ROS community | GPLv3 / LGPLv3 / BSD |
| PX4 Autopilot | Pixhawk 6C, SITL | 1.16.1 (SITL 1.16.0) | PX4 / Dronecode | BSD 3-Clause |
| libcamera | drone | Raspberry Pi fork | Raspberry Pi / libcamera | LGPL |
| Bumblebee nodes, `drone.py`, GCS, simulator setup | drone, PC | 1.0.2 / r2j; GCS 1.3.0 | FutureLab | **Apache 2.0** |
| `simple_offboard`, `aruco_pose` (derived from Clover) | drone | — | Copter Express / FutureLab | MIT |
| Gazebo | PC | Harmonic | Open Robotics | Apache 2.0 |

© 2026 FutureLab — Future Lab Industries L.L.C – S.P.C, Abu Dhabi, UAE. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
