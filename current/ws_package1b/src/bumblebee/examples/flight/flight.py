# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
flight.py -- single- or multi-marker ArUco preflight, takeoff to 0.8m, hover, land.

Preflight gates:
  1. >=1 ArUco marker visible.
  2. yaw_world locked. Two paths in aruco_detect:
       - Multi-marker (>=2 in view continuously for 1.5s) -- fast, geometric.
       - Single-marker (>=1 in view continuously for 3.0s, yaw spread <8 deg) -- slow,
         relies on warm-start tvec to suppress IPPE mirror flip.
  3. EKF2 position stable for 3s.

During flight a vision watchdog only triggers safe_land if vision goes silent
for >3.0s (no markers at all) -- single-marker continuous flight is allowed
because the per-frame quality controls in aruco_detect handle it.

Uses drone.py library. Run: python3 flight.py
"""

import math
import sys
import time
sys.path.insert(0, "/home/lb/ros2_ws/src/bumblebee/examples")
import drone
import flight_profile as _fp

PROFILE_NAME = "INDOOR_ARUCO_SLOW"
PROFILE_MIN_RATIO = 0.9   # refuse takeoff if gate applied fewer than this

# Register Ctrl+C handler for graceful landing on interrupt
drone.enable_safe_interrupt()

# Apply slow-speed profile through vpe_fix gate. Every MPC override reverts
# automatically on ARMED->DISARMED, so the drone "borrows" these settings only
# for the duration of this script. Strict check: if the gate is degraded
# (cache cold, MAVROS slow, FCU silent) it silently returns 0 and the drone
# would otherwise fly on default PX4 MPC (aggressive). Refuse takeoff in that
# case instead of silently flying with the wrong tuning.
expected = len(_fp.PROFILES[PROFILE_NAME])
try:
    applied = drone.apply_flight_profile(PROFILE_NAME)
except Exception as e:
    print("PREFLIGHT FAIL: apply_flight_profile raised: %s" % e)
    drone._shutdown()
    sys.exit(3)

if applied is None:
    applied = 0
threshold = int(math.ceil(expected * PROFILE_MIN_RATIO))
if applied < threshold:
    print("PREFLIGHT FAIL: only %d/%d profile params applied (<%d%%)."
          " Refusing takeoff -- PX4 would fly on defaults, not %s."
          " Check /tmp/bumblebee.log for vpe_fix gate state."
          % (applied, expected, int(PROFILE_MIN_RATIO * 100), PROFILE_NAME))
    drone._shutdown()
    sys.exit(3)
print("Profile gate OK: %d/%d %s params applied" % (applied, expected, PROFILE_NAME))

# Preflight gate 1 -- at least one marker visible.
try:
    drone.require_aruco(min_markers=1, timeout=15.0)
except RuntimeError as e:
    print("PREFLIGHT FAIL: %s" % e)
    drone._shutdown()
    sys.exit(1)

# Preflight gate 2 -- yaw lock (multi-marker fast path or single-marker slow path).
if not drone.wait_yaw_lock(timeout=20.0):
    print("PREFLIGHT FAIL: yaw_world not locked")
    drone._shutdown()
    sys.exit(1)

# Preflight gate 3 -- EKF stable. Single-marker tolerant by default.
if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    print("PREFLIGHT FAIL: position never converged")
    drone._shutdown()
    sys.exit(1)

# Preflight gate 4 -- vpe_fix actually pushing pose_cov into MAVROS at >=8 Hz.
# Catches vpe_fix self-lock (z-jump self-lock incident 2026-05-26).
print("=== WAITING FOR VPE LINK (>= 8 Hz on /mavros/mavros/pose_cov) ===")
try:
    drone.require_vpe_link(min_hz=8.0, window=2.0, timeout=15.0)
    print("  vpe link OK")
except RuntimeError as e:
    print("PREFLIGHT FAIL: %s" % e)
    drone._shutdown()
    sys.exit(1)

# Capture takeoff XY so safe_land can do a precision approach back to it.
# print_pos_fresh blocks until x/y/z are finite (or 1.5s) -- guards against TF
# gaps after preflight that would otherwise propagate NaN into safe_land.
start = drone.print_pos_fresh("START", timeout=4.0)
if math.isnan(start.x) or math.isnan(start.y):
    print("PREFLIGHT FAIL: START position NaN after 1.5s; aborting")
    drone._shutdown()
    sys.exit(2)
start_x, start_y = start.x, start.y

try:
    # Lower than 1.0 m -- at this altitude marker 0 (0.19m) stays in frame.
    drone.takeoff(height=1.5, speed=0.4)

    # Hover with vision watchdog: bail to safe_land only if vision goes
    # completely silent (no markers at all) for >3s.
    deadline = time.time() + 5.0
    vision_silent_since = None
    while time.time() < deadline and not drone.should_land:
        m_age = drone._markers_used_age()
        if drone._aruco_markers_used == 0 or m_age > 1.0:
            if vision_silent_since is None:
                vision_silent_since = time.time()
            elif time.time() - vision_silent_since > 3.0:
                print("VISION SILENT >3s during hover -- safe_land")
                break
        else:
            vision_silent_since = None
        time.sleep(0.1)
finally:
    # Land back over the takeoff point. Tolerance 0.18m sits above the
    # single-marker XY noise floor (~0.15m) to avoid limit-cycle oscillation.
    drone.safe_land(x=start_x, y=start_y,
                    precision_speed=0.1,
                    precision_tolerance=0.18)
