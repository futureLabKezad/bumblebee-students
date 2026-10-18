---
name: bumblebee-sd-image-project
description: Background of the Bumblebee project - drone software architecture, the reproducible SD image (stage 1, done), verified real-drone facts
type: project
source: condensed copy of the Mac-side Claude memory (17.10.2026); network names, addresses, credentials, share links, key paths, account names and security details removed (this folder is published in a public repository)
---

Since 2026-10-08 the owner (Future Lab) has been reworking the Bumblebee drone software "like professional
programmers". Repository: `futureLabKezad/bumblebee-students` (on-drone code in `drone/ros2_ws/src`, systemd units
in `drone/system/`), plus its wiki. Main rules: [[bumblebee-work-plan]].

**Architecture of the real drone (from the original V1.0.0-beta image, which is ground truth; the wiki is often wrong):**
Raspberry Pi 5, Ubuntu 24.04 arm64, ROS 2 Jazzy. PX4 1.16.1 on an FMU-v6C over `/dev/ttyAMA0` <-> MAVROS 2.14 <->
C++ `simple_offboard` (Clover port) <-> Python `drone.py` API. Vision: self-built libcamera 0.7.0 -> v4l2_camera ->
camera_fix.py -> aruco_detect.py (OpenCV venv) -> vpe_fix.py -> `/mavros/mavros/pose_cov` -> EKF2. ATtiny on I2C
0x30 (servo / wheel / LED).

**Stage 1 (done, released):** reproducible SD image built from the repo; GitHub release v1.0.1 (image), GCS apps
gcs-v1.1.0 (macOS and Windows), PR #5 merged into main on 2026-10-13. Lessons that matter for the simulator:
- The drone's FC talks MAVLink at 921600 baud (repo snapshot px4_v0_0_1); the image detects it (fcu_detect.py).
- A ROS graph stall was caused by the Fast DDS shared-memory transport in systemd services. Fix:
  `FASTDDS_BUILTIN_TRANSPORTS=UDPv4` for the services. The simulator mirrors this (UDPv4, loopback only).
- PX4 `BAT1_SOURCE=-1` in the reference parameters: the battery voltage is not measured (65.535 V = unknown).
- Per-drone `ROS_DOMAIN_ID` derived from the MAC address (set_identity / ros_domain.py).

Известные проблемы безопасности образа дрона описаны в непубличных заметках владельца; к работе в симуляторе не относятся.

**Real Bumblebee physical data (from the owner, 2026-10-13/14), used by the simulator model:**
total mass 4274 g (2337 g without its 4 batteries); motors T-Motor MN4006 KV380; props T-Motor MF1503L (15");
motor-to-motor diagonal ~63 cm; 4 x LiPo HV 6S1P 4500 mAh (4.35 V/cell max), ~484 g each, in parallel (6S,
~18000 mAh). For the later battery parameter group: BAT1_V_CHARGED should be 4.35 (reference params say 4.2),
BAT1_CAPACITY ~18000 - consequence check first. The colourless 'Cube' in the owner's GLB = the electronics boards
(FC, Raspberry Pi); there is NO gripper. Cameras: SainSmart OV5647 fisheye 160 deg. ESC: ReadyToSky 45A
(BLHeli_S; the 10-minute beep is the beacon, disabled with "Beacon Delay = Infinite" in ESC Configurator over a USB
linker, not through PX4 1.16). Optical flow: H-Flow = PAA3905 + AFBR-S50 in one module.

**Drift between repo and image (stage 1 findings):** qos_relay.py was missing; vpe_fix.py / aruco_detect.py ran
from install/ copies; bumblebee_description is Clover-derived (0.7-1.5 kg) and is NOT the real drone.

History only (Mac): the image was built in a Lima VM `bbbuild`; the owner flashes images with Raspberry Pi Imager.
