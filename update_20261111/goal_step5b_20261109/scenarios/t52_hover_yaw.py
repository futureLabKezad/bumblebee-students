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
t52_hover_yaw.py (T52 sign check, Claude 11.11; from hover r6) -- STUDY ONLY: hover 20 s, yaw +90 deg and back.
hover_marker0.py -- take off to 0.75 m, fly to the centre of marker 0, climb there to 1.0 m,
hover 65 s, land (goal criteria C6 / Zh4). r3: variant B. r4: waits for the takeoff height
before fly_to. r5: vision watchdog on new vpe_fix poses (image r2f), silence counted from the
takeoff. r6: the move to marker 0 is done below the C6 height band, then the climb.

The same file runs in Gazebo (C6) and on the drone (Zh4, started by the owner only).
Needs the fixed image (drone.check_flight_profile, /work/param_profile_fix_01): this
script writes NO PX4 parameter; it only checks the INDOOR_ARUCO_SLOW profile and
refuses to fly if PX4 does not already hold it.

Where it hovers (r3, variant B, chat 1 09.11): over map (0, 0) = the centre of marker 0.
In variant B PX4 fuses the vision pose, so 'map' is the marker frame. The drone is
placed on marker 0, but not exactly on its centre (the Gazebo stand puts it 8 cm off,
like an imprecise placement live); r6: takeoff climbs straight up to START z + LOW_H, then
fly_to() moves it slowly to (0, 0) at that height, then a second fly_to() climbs slowly
over (0, 0) to the hover height. Hover height stays as in r2: START z + 1.0 m (in the
variant B runs 'map' z on the ground is not 0, e.g. -0.31 in s9_c6_04).
Safety: if START is more than MAX_START_OFFSET_M from map (0, 0), 'map' is not the
marker frame (variant A: in Gazebo run s04, 06.11, START read (0.00, 1.53) on marker 0)
or the drone stands far from marker 0 -- the script refuses before arming (exit 1).
The check cannot prove the frame: a drone within 0.5 m (e.g. on marker 8 or 9) flies at
most 0.5 m, slowly, towards marker 0.
How close it stays to marker 0 is measured from outside (Gazebo ground truth; marker
log and video on the drone), not by this script.

r4 (chat 1, 10.11): after takeoff() the script waits, sending nothing, until the
estimate is within SETTLE_DZ below the takeoff target height (the navigate_target
frame), and only then calls fly_to(). Why (s9_c6r3_03, ULog): takeoff() returns as
soon as the drone is within 0.15 m of its target, i.e. at about 0.90 m, right on the
C6 height band edge. In the image, simple_offboard's nav_from_sp flag is cleared by
the pre-OFFBOARD state messages during the auto-arm takeoff, so the next navigate
(fly_to) may start from the vehicle position instead of the setpoint: the height
setpoint fell from 1.01 to 0.90 and climbed back at the 0.1 m/s fly_to speed, and the
drone sagged to 0.897 (C6 height error 0.103). Waiting first means that drop, if it
happens, is at most a few cm and inside the band.

r5 (chat 1, 10.11): the script's own vision watchdog uses the r2f image signal
drone.vision_pose_age() (seconds since vpe_fix published a NEW pose; +inf if none yet)
instead of the raw /aruco_detect/markers_used count, which also counts false markers that
vpe_fix rejects (T35). Vision is present when that age is <= VISION_AGE_S (1 s); the flight
is cut when it has been absent longer than VISION_SILENT_S (3 s), i.e. no new pose for more
than 4 s. As in image r2g (S4, owner's "yes"): the silence is counted at the latest from the
takeoff, not from the first pose, so a drone that never got a pose, or lost vision during
the climb or fly_to, is not given a fresh 4 s when the watch starts. Needs image r2f or later.

r6 (chat 1, 10.11; T40): the C6 evaluator opens its window at the first entry into the height
band 1.0 +- 0.10 m (criteria, not changed here). In r4/r5 that entry happened during the
takeoff climb, before the move to the marker 0 centre; when the lift-off drift was large
(0.18-0.26 m; near the floor vision drops for up to 3.5 s), the slow 0.1 m/s move to the
centre fell inside the window (control A, 10.11: 93.9 % within 10 cm). r6 changes the order
only: takeoff() to LOW_H = 0.75 m, wait for that height (r4 settle), fly_to() the marker 0
centre at that height, then fly_to() straight up to 1.0 m over the centre at CLIMB_SPEED,
wait for that height (the same settle), then the 65 s hover and the landing as in r5. Why
0.75 m and not lower (Gazebo ULogs, 27 runs, read only): on the climb a vision pose reached
PX4 in only 16-70 % of 0.25 s slots below 0.70 m, but in 95 % at 0.70-0.75 m and 100 % at
0.75-0.95 m (a hold below 0.70 m would risk the 4 s watchdog cut); the takeoff overshoot above
its target was at most +0.053 m, so a 0.75 m takeoff stays below the band edge 0.90 m.
Vision after the low takeoff (variant A, chat 1): takeoff() returns 0.15 m short of its target,
at about 0.60 m, but after the spin-up vision came back only at 0.64-0.73 m (Gazebo); at 0.60 m
the last pose was up to 6.5 s old. So in the FIRST settle only (still the takeoff leg, below the
band) the silence limit is TAKEOFF_VISION_S = 25 s from the takeoff, the same limit the image's
takeoff() applies to its climb, and that settle ends only when the height is reached AND a new
pose is at most VISION_AGE_S old. The height must still come within SETTLE_TIMEOUT_S (15 s) of
the settle start; if it did but vision is not back yet, the wait goes on until the watchdog
cuts at 25 s from the takeoff ('vision silent >24s', review 10.11). From then on the r5
watchdog is unchanged (4 s, counted from the takeoff at the latest).

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
LOW_H = 0.75              # r6: takeoff and the move to marker 0 at this height (below the C6 band 0.90-1.10)
CLIMB_SPEED = 0.1         # r6: slow climb over marker 0 from LOW_H to HOVER_H
HOVER_S = 20.0   # T52: was 65.0;           # r2 (chat 1, 09.11): the C6 window (from the band entry) must reach 60 s; e3 had 59.6
MARKER0_X = 0.0           # r3: centre of marker 0 in 'map' (variant B: map = marker frame)
MARKER0_Y = 0.0
MAX_START_OFFSET_M = 0.5  # r3: START farther than this from (0, 0) -> refuse (map is not the marker frame)
FLY_SPEED = 0.1           # r3: slow move to the centre, as flight_marker_loop.py of the image
FLY_TOL = 0.12            # r3: arrival tolerance, as flight_marker_loop.py
FLY_SETTLE = 0.05         # r3: arrival only when nearly stopped (F7), as flight_marker_loop.py
SETTLE_DZ = 0.03          # r4: fly_to only once the estimate is within 3 cm below the takeoff target
SETTLE_SAMPLES = 3        # r4: ... on 3 successive checks (0.1 s apart)
SETTLE_TIMEOUT_S = 15.0   # r4: not there after this -> flight cut, land (r3 EKF replay: 4-5 s)
VISION_AGE_S = 1.0        # r5: vision present = new vpe_fix pose within this (r2f README, flight.py)
VISION_SILENT_S = 3.0     # as flight.py: land if vision absent for longer than this (no new pose > 4 s)
TAKEOFF_VISION_S = 25.0   # r6 A: first settle only -- no new pose this long since the takeoff -> cut (= drone.takeoff vision_timeout)
FCU_UNKNOWN_S = 3.0       # land if /mavros/state stays stale longer than this


def refuse(code, why):
    print('PREFLIGHT FAIL: %s' % why)
    drone._shutdown()
    sys.exit(code)


def check_interrupt():
    if drone.should_land:
        refuse(1, 'Ctrl+C before takeoff -- not flying')


def below_takeoff_target():
    """r4: how far the estimate is below the current navigate target (m), or None.
    In the navigate_target frame (translation = target, rotation = yaw only) z is
    drone z - target z, so 'below' is -z. Read only."""
    try:
        dz = drone.get_pos(frame_id='navigate_target')[2]
    except Exception:
        return None
    return None if math.isnan(dz) else -dz


def hold_over_marker0(seconds):
    """Watch the hover. The setpoint stays where fly_to() put it (over marker 0):
    nothing is re-sent here, so the hold never follows a drifting estimate.
    Returns (held_s, reason); reason is None when the full time elapsed."""
    print('=== HOVER %.0fs over marker 0 START ===' % seconds)
    held, reason, _ = watch(seconds, '[HOVER]')
    print('=== HOVER END held=%.1fs reason=%s ===' % (held, reason or 'full time'))
    return held, reason


def settle_at_target_height(what, after_takeoff=False):
    """r4: wait, sending nothing, until the estimate is within SETTLE_DZ below the
    current navigate target on SETTLE_SAMPLES successive checks. Returns reason or None.
    r6: used after takeoff() (what='takeoff height') and after the climb over marker 0
    (what='hover height').
    r6 A: after_takeoff=True (first settle, below the band): vision may still be absent from the
    spin-up; the silence limit is TAKEOFF_VISION_S from the takeoff and the settle ends only with
    a new pose at most VISION_AGE_S old."""
    print('=== SETTLE: waiting until <=%.2f m below the %s%s (max %.0fs) ==='
          % (SETTLE_DZ, what, ' and a new vpe_fix pose' if after_takeoff else '', SETTLE_TIMEOUT_S))
    count = [0]

    def reached():
        b = below_takeoff_target()
        count[0] = count[0] + 1 if b is not None and b <= SETTLE_DZ else 0
        if after_takeoff and not drone.vision_pose_age() <= VISION_AGE_S:
            return False
        return count[0] >= SETTLE_SAMPLES
    limit = TAKEOFF_VISION_S if after_takeoff else None
    waited, reason, done = watch(SETTLE_TIMEOUT_S, '[SETTLE]', reached, vision_limit=limit)
    if reason is None and not done and after_takeoff and count[0] >= SETTLE_SAMPLES:
        # r6 A (review 10.11): the height is there, vision is not back yet: wait on, up to
        # TAKEOFF_VISION_S from the takeoff; the watchdog cuts at that limit ('vision silent >').
        more = t_takeoff + TAKEOFF_VISION_S + 0.5 - time.monotonic()
        if more > 0:
            print('=== SETTLE: height reached, waiting for a new vpe_fix pose (until %.0fs after the takeoff) ==='
                  % TAKEOFF_VISION_S)
            more_waited, reason, done = watch(more, '[SETTLE]', reached, vision_limit=limit)
            waited += more_waited
        if reason is None and not done:
            silent = vision_silent_for(time.monotonic())
            if silent <= VISION_AGE_S:
                reason = '%s not held until vision came back' % what
            else:
                reason = 'vision silent >%.0fs at %.0fs after the takeoff (no new vpe_fix pose for %.1fs)' % (
                    VISION_AGE_S, TAKEOFF_VISION_S, silent)
    if reason is None and not done:
        reason = '%s not reached in %.0fs' % (what, SETTLE_TIMEOUT_S)
    print('=== SETTLE END waited=%.1fs reason=%s ===' % (waited, reason or 'height reached'))
    return reason


t_takeoff = None   # r5 (S4): monotonic time of the takeoff() call; vision silence counts from here at the latest


def vision_silent_for(now):
    """r5: seconds without a NEW vpe_fix pose (image r2f), counted at the latest from the takeoff."""
    age = drone.vision_pose_age()
    if t_takeoff is not None:
        age = min(age, now - t_takeoff)
    return age


def not_reached(what):
    """fly_to() returned False: say whether the pilot/failsafe has the drone (read only)."""
    fs = drone.get_fcu_status()
    return '%s not reached (fcu ok=%s armed=%s mode=%s)' % (
        what, fs.get('ok'), fs.get('armed'), fs.get('mode'))


def watch(seconds, tag, done=None, vision_limit=None):
    """Watch the flight for up to `seconds`, sending nothing. Stops early when done()
    is true. Returns (elapsed_s, reason, done_hit); reason is None unless cut short.
    vision_limit (r6 A, first settle only): silence limit in s instead of the r5 one."""
    limit = VISION_AGE_S + VISION_SILENT_S if vision_limit is None else vision_limit
    t0 = time.monotonic()
    fcu_unknown_since = None
    next_print = t0
    reason = None
    done_hit = False
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
        silent = vision_silent_for(now)
        if not silent <= limit:   # NaN counts as silent
            reason = 'vision silent >%.0fs (no new vpe_fix pose for %.1fs)' % (limit - VISION_AGE_S, silent)
            break
        if done is not None and done():
            done_hit = True
            break
        if now >= next_print:
            next_print += 1.0
            try:
                x, y, z = drone.get_pos()
                print('%s t=%.0f x=%.2f y=%.2f z=%.2f vision_age=%.2f'
                      % (tag, now - t0, x, y, z, drone.vision_pose_age()))
            except Exception as e:
                print('%s t=%.0f position not read: %s' % (tag, now - t0, e))
        time.sleep(0.1)
    return time.monotonic() - t0, reason, done_hit


# Start the ROS node first, then the Ctrl+C handler (its log line needs the node).
drone.get_fcu_status()
drone.enable_safe_interrupt()

# Profile: read only. The old apply_flight_profile() of port-rc3 WRITES PX4 params,
# so it is never used here; an image without check_flight_profile is refused.
if not hasattr(drone, 'check_flight_profile'):
    refuse(3, 'drone.py has no check_flight_profile (image without the 09.11 fix)')
# r5: the vision watchdog needs vision_pose_age() (image r2f or later); refuse before arming
if not hasattr(drone, 'vision_pose_age'):
    refuse(1, 'drone.py has no vision_pose_age (image before r2f) -- not flying')
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

# r3 (variant B): the hover point is map (0, 0) = centre of marker 0; the drone stands on
# marker 0 (owner / Gazebo spawn), a few cm off its centre.
start = drone.print_pos_fresh('START', timeout=4.0)
if start is None or any(math.isnan(v) for v in (start.x, start.y, start.z)):
    refuse(1, 'START position NaN')
start_off = math.hypot(start.x - MARKER0_X, start.y - MARKER0_Y)
if start_off > MAX_START_OFFSET_M:
    refuse(1, 'START map (%.2f, %.2f) is %.2f m from marker 0 (limit %.2f): map is not the '
           'marker frame (variant B needs the vision pose fused) or the drone stands far from marker 0'
           % (start.x, start.y, start_off, MAX_START_OFFSET_M))
hover_z = start.z + HOVER_H
low_z = start.z + LOW_H
print('Hover point = marker 0 centre: map (%.2f, %.2f), z %.2f (START z + %.1f m); '
      'START (%.2f, %.2f) is %.2f m off' % (MARKER0_X, MARKER0_Y, hover_z, HOVER_H,
                                           start.x, start.y, start_off))
print('r6 order: takeoff to z %.2f (START z + %.2f m), move to marker 0 there, climb to z %.2f'
      % (low_z, LOW_H, hover_z))
check_interrupt()

held, reason = 0.0, 'not started'
landed = False
try:
    # r6: takeoff() climbs straight up to (START x, START y, START z + LOW_H), below the C6
    # band; r4: the script waits (sending nothing) until the drone is nearly there; fly_to()
    # moves slowly to marker 0 at that height; a second fly_to() climbs slowly over marker 0
    # to the hover height and leaves that setpoint in place; the script waits for that height
    # (same settle); nothing else is sent during the hover.
    t_takeoff = time.monotonic()
    if not drone.takeoff(height=LOW_H, speed=0.4):
        reason = 'takeoff not completed'
    else:
        reason = settle_at_target_height('takeoff height', after_takeoff=True)
        if reason is not None:
            pass
        elif not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=low_z, speed=FLY_SPEED,
                              tolerance=FLY_TOL, settle_speed=FLY_SETTLE):
            reason = not_reached('marker 0 centre')
        elif not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=hover_z, speed=CLIMB_SPEED,
                              tolerance=FLY_TOL, settle_speed=FLY_SETTLE):
            reason = not_reached('hover height over marker 0')
        else:
            reason = settle_at_target_height('hover height')
            if reason is None:
                held, reason = hold_over_marker0(HOVER_S)
                for yaw_t, tag in ((math.pi / 2, '[YAW90]'), (0.0, '[YAW0]')):   # T52: yaw turn over marker 0, position target unchanged
                    if reason is not None:
                        break
                    print('=== T52 %s yaw %.2f rad ===' % (tag, yaw_t), flush=True)
                    drone.navigate_wait(x=MARKER0_X, y=MARKER0_Y, z=hover_z, yaw=yaw_t, speed=FLY_SPEED, frame_id='map', tolerance=FLY_TOL)
                    _, reason, _ = watch(8.0, tag)
    if drone.should_land:
        reason = 'Ctrl+C'
finally:
    # Ctrl+C: should_land is set, so safe_land skips the approach and lands at once.
    # Pilot wins: safe_land sends nothing when the RC has taken the drone.
    landed = drone.safe_land(x=MARKER0_X, y=MARKER0_Y, precision_speed=0.1,
                             precision_tolerance=0.18)
if drone.should_land and reason is None:
    reason = 'Ctrl+C during landing'

ok = reason is None and landed
print('C6 HOVER RESULT: %s held=%.1fs reason=%s landed=%s'
      % ('OK' if ok else 'CUT', held, reason or 'full time', landed))
drone._shutdown()
sys.exit(0 if ok else 4)
