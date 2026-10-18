---
name: bumblebee-work-plan
description: MAIN RULES — the agreed work plan for finishing the Bumblebee SD image; consult before any task in this workspace
type: project
source: copy of the Mac-side Claude memory, 17.10.2026 (session metadata removed)
---

User asked (2026-10-08) to treat this plan as the main rules for all Bumblebee work. Context: [[bumblebee-sd-image-project]].

**Goal:** an SD image that is reproducibly built from the repo with one command, works out of the box, and is safe for a classroom.

**Ground rules**
1. The real image (`V1.0.0-beta`/`030726`) is ground truth; the wiki is secondary and often wrong. Every claim is checked against the image or code; unverified ones are marked «(проверить)».
2. Nothing lives only on the drone. Every file on the image (code, configs, udev, nginx, NM profiles, polkit, calibrations, venvs, libcamera build) must come from the repo via the build. Never edit `install/` by hand.
3. Professional process: git, branches, PRs with review, CI (colcon build + tests), versioning and CHANGELOG, a pinned list of dependencies.
4. Do not break flight: behaviour changes to simple_offboard / vpe_fix / aruco / PX4 params only with a test plan (simulator first, then the drone) and the user's approval. Never write I2C from timers or failsafe paths.
5. Security by default. (The concrete security issues of the drone image and their plan are in the owner's private notes; they are not part of the simulator work.)
6. Only one source per thing: remove duplicates (drone.py, mavros_params, camera_fix, vpe_fix, sys_metrics, led_default) and dead ROS 1 code.
7. Ask before outward-facing actions (push, PRs to futureLabKezad, publishing images).

**Phases**
- **Phase 0, inventory:** mount the image's rootfs (user provides the file), diff the drone against the repo, write the full system map and backlog.
- **Phase 1, reproducibility:** pull everything missing into the repo (qos_relay, canonical vpe_fix/aruco_detect, udev, nginx, NM hotspot, polkit, wifi-manager config, camera tuning/calibration); fix the colcon build (catkin → ament for bumblebee_description, aruco_pose under OpenCV 4.x, install lists); add a CI build.
- **Phase 2, image pipeline:** a scripted build of the image from stock Ubuntu 24.04 for RPi5 (e.g. a chroot/qemu or pi-gen-like script); first-boot provisioning (per-drone identity; details in the owner's private notes); log rotation; versioning in `/etc/bumblebee_version`.
- **Phase 3, security and reliability:** security hardening per the owner's private notes, i2c_recover robustness, a single LED owner, a single ATtiny protocol, wifi_watchdog bugs.
- **Phase 4, correctness and docs:** fix the drone.py bugs (arming service name, set_aruco_map), dead launch args, PX4 safety params (a decision for the user), and align the wiki with reality.

**How to apply:** before starting any task, place it in a phase and check it against the rules; when unsure about flight-critical or outward-facing steps, ask.
