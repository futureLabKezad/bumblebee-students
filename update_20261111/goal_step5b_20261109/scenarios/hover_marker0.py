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
hover_marker0.py -- take off to 1.0 m, hover 60 s over marker 0, land (goal criteria C6 / Zh4).

The same file runs in Gazebo (C6) and on the drone (Zh4, started by the owner only).
Needs the fixed image (drone.check_flight_profile, /work/param_profile_fix_01): this
script writes NO PX4 parameter; it only checks the INDOOR_ARUCO_SLOW profile and
refuses to fly if PX4 does not already hold it.

Where it hovers: straight above the takeoff point. The drone is placed on marker 0.
Not map (0, 0): there is no 'aruco_map' TF frame in the image (aruco_detect publishes
'aruco_map_detected'; the C++ aruco_map node is disabled), and 'map' equals the marker
frame only when PX4 fuses the vision pose (EKF2_EV_CTRL != 0). With the vision pose off
(20EC, Gazebo 4034/4035) 'map' is the EKF frame: in Gazebo run s04 (06.11, 4035) the
drone stood on marker 0 and START read map (0.00, 1.53), so fly_to(0, 0) would have
taken it 1.5 m away. How close it stays to marker 0 is measured from outside (Gazebo
ground truth; marker log and video on the drone), not by this script.

Finding F1 is NOT worked around here: the marker detector sleeps until the drone is
armed in OFFBOARD, so require_aruco() before arming sees 0 markers and the script
refuses (exit 1) on an image without the F1 fix. Gazebo trials use the launcher's
labelled option --trial-aruco-always.

Ctrl+C: lands (safe_land) and the motors stop on touchdown. Pilot wins: if the RC
takes the drone out of OFFBOARD, the script stops and sends nothing more.

Exit codes: 0 hovered the full time and landed; 1 preflight failed (nothing armed);
3 profile check failed (nothing armed); 4 flight cut short (Ctrl+C, vision, pilot,
FCU) or landing not confirmed; 2 = drone.py saw a fall.

Run: python3 hover_marker0.py
"""

import math
import sys
import time
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

PROFILE_NAME = 'INDOOR_ARUCO_SLOW'
HOVER_H = 1.0             # m above the takeoff point (the drone stands on marker 0)
HOVER_S = 60.0
VISION_SILENT_S = 3.0     # as flight.py: land if no marker at all for longer than this
FCU_UNKNOWN_S = 3.0       # land if /mavros/state stays stale longer than this


def refuse(code, why):
    print('PREFLIGHT FAIL: %s' % why)
    drone._shutdown()
    sys.exit(code)


def check_interrupt():
    if drone.should_land:
        refuse(1, 'Ctrl+C before takeoff -- not flying')


def hold_over_marker0(seconds):
    """Watch the hover. The setpoint stays where takeoff() put it (above START):
    nothing is re-sent here, so the hold never follows a drifting estimate.
    Returns (held_s, reason); reason is None when the full time elapsed."""
    print('=== HOVER %.0fs over marker 0 START ===' % seconds)
    t0 = time.monotonic()
    vision_silent_since = None
    fcu_unknown_since = None
    next_print = t0
    reason = None
    while True:
        now = time.monotonic()
        if now - t0 >= seconds:
            break
        if drone.should_land:
            reason = 'Ctrl+C'
            break
        s = drone.get_fcu_status()
        if not s['ok']:
            if fcu_unknown_since is None:
                fcu_unknown_since = now
            elif now - fcu_unknown_since > FCU_UNKNOWN_S:
                reason = 'FCU state unknown >%.0fs' % FCU_UNKNOWN_S
                break
        else:
            fcu_unknown_since = None
            if not s['armed']:
                reason = 'disarmed'
                break
            if s['mode'] != 'OFFBOARD':
                reason = 'pilot/failsafe has control (mode=%s)' % s['mode']
                break
        if drone._aruco_markers_used == 0 or drone._markers_used_age() > 1.0:
            if vision_silent_since is None:
                vision_silent_since = now
            elif now - vision_silent_since > VISION_SILENT_S:
                reason = 'vision silent >%.0fs' % VISION_SILENT_S
                break
        else:
            vision_silent_since = None
        if now >= next_print:
            next_print += 1.0
            try:
                x, y, z = drone.get_pos()
                print('[HOVER] t=%.0f x=%.2f y=%.2f z=%.2f markers=%d'
                      % (now - t0, x, y, z, drone._aruco_markers_used))
            except Exception as e:
                print('[HOVER] t=%.0f position not read: %s' % (now - t0, e))
        time.sleep(0.1)
    held = time.monotonic() - t0
    print('=== HOVER END held=%.1fs reason=%s ===' % (held, reason or 'full time'))
    return held, reason


# Start the ROS node first, then the Ctrl+C handler (its log line needs the node).
drone.get_fcu_status()
drone.enable_safe_interrupt()

# Profile: read only. The old apply_flight_profile() of port-rc3 WRITES PX4 params,
# so it is never used here; an image without check_flight_profile is refused.
if not hasattr(drone, 'check_flight_profile'):
    refuse(3, 'drone.py has no check_flight_profile (image without the 09.11 fix)')
try:
    matched, expected, problems = drone.check_flight_profile(PROFILE_NAME)
except Exception as e:
    refuse(3, 'check_flight_profile raised: %s' % e)
if matched < expected:
    refuse(3, 'only %d/%d PX4 params match profile %s (%s). Set them in QGC (owner card).'
           % (matched, expected, PROFILE_NAME, '; '.join(problems)))
print('Profile check OK: %d/%d %s params match' % (matched, expected, PROFILE_NAME))
check_interrupt()

# Preflight gates, as flight.py of the fixed image.
try:
    drone.require_aruco(min_markers=1, timeout=15.0)
except RuntimeError as e:
    refuse(1, '%s (on an image without the F1 fix the detector sleeps until arming)' % e)
check_interrupt()
if not drone.wait_yaw_lock(timeout=20.0):
    refuse(1, 'yaw_world not locked')
check_interrupt()
if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    refuse(1, 'position never converged')
check_interrupt()
try:
    drone.require_vpe_link(min_hz=8.0, window=2.0, timeout=15.0)
except RuntimeError as e:
    refuse(1, str(e))
check_interrupt()

# The hover point is the takeoff point: the drone stands on marker 0 (owner / Gazebo spawn).
start = drone.print_pos_fresh('START', timeout=4.0)
if start is None or any(math.isnan(v) for v in (start.x, start.y, start.z)):
    refuse(1, 'START position NaN')
print('Hover point = START over marker 0: map (%.2f, %.2f), %.1f m up' % (start.x, start.y, HOVER_H))
check_interrupt()

held, reason = 0.0, 'not started'
landed = False
try:
    # takeoff() climbs straight up to (START x, START y, START z + HOVER_H) and leaves
    # that setpoint in place; nothing else is sent during the hover.
    if not drone.takeoff(height=HOVER_H, speed=0.4):
        reason = 'takeoff not completed'
    else:
        held, reason = hold_over_marker0(HOVER_S)
    if drone.should_land:
        reason = 'Ctrl+C'
finally:
    # Ctrl+C: should_land is set, so safe_land skips the approach and lands at once.
    # Pilot wins: safe_land sends nothing when the RC has taken the drone.
    landed = drone.safe_land(x=start.x, y=start.y, precision_speed=0.1,
                             precision_tolerance=0.18)
if drone.should_land and reason is None:
    reason = 'Ctrl+C during landing'

ok = reason is None and landed
print('C6 HOVER RESULT: %s held=%.1fs reason=%s landed=%s'
      % ('OK' if ok else 'CUT', held, reason or 'full time', landed))
drone._shutdown()
sys.exit(0 if ok else 4)
