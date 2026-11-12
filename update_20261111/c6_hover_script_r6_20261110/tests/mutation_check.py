#!/usr/bin/env python3
"""Do the tests catch broken scripts? Each mutation is applied to a COPY of
hover_marker0.py in a temporary folder; the tests must FAIL on every copy.
Run: python3 -I tests/mutation_check.py"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = open(os.path.join(ROOT, 'hover_marker0.py'), encoding='utf-8').read()

MUTATIONS = [
    ('profile check removed -> apply_flight_profile (writes in port-rc3)',
     "matched, expected, problems = drone.check_flight_profile(PROFILE_NAME)",
     "matched = expected = drone.apply_flight_profile(PROFILE_NAME); problems = []"),
    ('mismatch ignored', "if matched < expected:", "if False:"),
    ('Ctrl+C before takeoff ignored', "    if drone.should_land:\n        refuse(1,",
     "    if False:\n        refuse(1,"),
    ('pilot takeover ignored', "if s['mode'] != 'OFFBOARD':", "if False:"),
    ('hover re-sends setpoint to current position', "        time.sleep(0.1)\n",
     "        drone.hover(0.1)\n"),
    ('no landing on Ctrl+C in hover', "            reason = 'Ctrl+C'\n            break",
     "            pass"),
    ('hover 60 s (r1)', "HOVER_S = 65.0", "HOVER_S = 60.0"),
    ('height 1.5 m', "HOVER_H = 1.0 ", "HOVER_H = 1.5 "),
    ('NaN start check off', "if start is None or any(", "if start is None and any("),
    ('r3: lands over START instead of marker 0', "safe_land(x=MARKER0_X, y=MARKER0_Y,",
     "safe_land(x=start.x, y=start.y,"),
    ('r3: no fly_to (r2: hovers over START)', "elif not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=low_z,",
     "elif False and drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=low_z,"),
    ('r3: fly_to START instead of marker 0', "drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=low_z,",
     "drone.fly_to(x=start.x, y=start.y, z=low_z,"),
    ('r3: absolute z 1.0 instead of START z + 1.0', "hover_z = start.z + HOVER_H", "hover_z = HOVER_H"),
    ('r3: START offset check off', "if start_off > MAX_START_OFFSET_M:", "if False:"),
    ('r3: START offset limit 1.6 m', "MAX_START_OFFSET_M = 0.5 ", "MAX_START_OFFSET_M = 1.6 "),
    ('r3: START offset limit 0.6 m', "MAX_START_OFFSET_M = 0.5 ", "MAX_START_OFFSET_M = 0.6 "),
    ('r3: offset from START x only', "math.hypot(start.x - MARKER0_X, start.y - MARKER0_Y)",
     "abs(start.x - MARKER0_X)"),
    ('r3: fly_to failure ignored', "            reason = not_reached('marker 0 centre')\n", "            reason = None\n"),
    ('r3: fly_to fast 0.5 m/s', "FLY_SPEED = 0.1 ", "FLY_SPEED = 0.5 "),
    ('r3: fly_to no settle', "z=low_z, speed=FLY_SPEED,\n                              tolerance=FLY_TOL, settle_speed=FLY_SETTLE)",
     "z=low_z, speed=FLY_SPEED,\n                              tolerance=FLY_TOL)"),
    ('r4: no settle (r3)', "        reason = settle_at_target_height('takeoff height', after_takeoff=True)\n", "        reason = None\n"),
    ('r4: settle 15 cm (= takeoff tolerance)', "SETTLE_DZ = 0.03 ", "SETTLE_DZ = 0.15 "),
    ('r4: settle 1 sample', "SETTLE_SAMPLES = 3 ", "SETTLE_SAMPLES = 1 "),
    ('r4: settle timeout 60 s', "SETTLE_TIMEOUT_S = 15.0 ", "SETTLE_TIMEOUT_S = 60.0 "),
    ('r4: settle sign flipped', "return None if math.isnan(dz) else -dz", "return None if math.isnan(dz) else dz"),
    ('r4: settle in the map frame', "drone.get_pos(frame_id='navigate_target')", "drone.get_pos(frame_id='map')"),
    ('r4: settle timeout flies on', "    if reason is None and not done:\n        reason = '%s not reached in %.0fs'",
     "    if False:\n        reason = '%s not reached in %.0fs'"),
    ('r4: settle read error counts as reached', "    except Exception:\n        return None\n",
     "    except Exception:\n        return 0.0\n"),
    ('r4: count not reset on a bad check', "if b is not None and b <= SETTLE_DZ else 0", "if b is not None and b <= SETTLE_DZ else count[0]"),
    ('r4: height checked before safety', "        if drone.should_land:\n            reason = 'Ctrl+C'\n            break\n",
     "        if done is not None and done():\n            done_hit = True\n            break\n"
     "        if drone.should_land:\n            reason = 'Ctrl+C'\n            break\n"),
    ('r5: watchdog on the raw markers_used (r4)', "        silent = vision_silent_for(now)\n",
     "        silent = 0.0 if drone._aruco_markers_used > 0 else 99.0\n"),
    ('r5: silence counted from the first pose (no S4)', "    if t_takeoff is not None:\n        age = min(",
     "    if t_takeoff is not None and age != float('inf'):\n        age = min("),
    ('r5: silence reset at each watch start', "    t0 = time.monotonic()\n    fcu_unknown_since = None\n",
     "    global t_takeoff\n    t0 = time.monotonic()\n    t_takeoff = t0\n    fcu_unknown_since = None\n"),
    ('r5: takeoff time never set', "    t_takeoff = time.monotonic()\n", "    pass\n"),
    ('r5: no r2f image check', "if not hasattr(drone, 'vision_pose_age'):", "if False:"),
    ('r5: vision age limit 2 s', "VISION_AGE_S = 1.0 ", "VISION_AGE_S = 2.0 "),
    ('r5: vision silent 6 s', "VISION_SILENT_S = 3.0 ", "VISION_SILENT_S = 6.0 "),
    ('r5: vision watchdog off', "            reason = 'vision silent >%.0fs (no new vpe_fix pose for %.1fs)' % (limit - VISION_AGE_S, silent)\n            break\n",
     "            pass\n"),
    ('r6: takeoff straight to the hover height (r5)', "drone.takeoff(height=LOW_H,", "drone.takeoff(height=HOVER_H,"),
    ('r6: move to marker 0 at the hover height', "z=low_z, speed=FLY_SPEED", "z=hover_z, speed=FLY_SPEED"),
    ('r6: low z absolute', "low_z = start.z + LOW_H", "low_z = LOW_H"),
    ('r6: no climb', "elif not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=hover_z,",
     "elif False and drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=hover_z,"),
    ('r6: climb over START instead of marker 0', "drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=hover_z,",
     "drone.fly_to(x=start.x, y=start.y, z=hover_z,"),
    ('r6: climb failure ignored', "            reason = not_reached('hover height over marker 0')\n", "            reason = None\n"),
    ('r6: climb no settle_speed', "z=hover_z, speed=CLIMB_SPEED,\n                              tolerance=FLY_TOL, settle_speed=FLY_SETTLE)",
     "z=hover_z, speed=CLIMB_SPEED,\n                              tolerance=FLY_TOL)"),
    ('r6: no settle after the climb', "            reason = settle_at_target_height('hover height')\n", "            reason = None\n"),
    ('r6: hover even if the climb settle failed', "            if reason is None:\n                held, reason = hold_over_marker0(HOVER_S)\n",
     "            held, reason = hold_over_marker0(HOVER_S)\n"),
    ('r6: LOW_H 0.5', "\nLOW_H = 0.75 ", "\nLOW_H = 0.5 "),
    ('r6: LOW_H 0.9', "\nLOW_H = 0.75 ", "\nLOW_H = 0.9 "),
    ('r6: climb fast 0.4 m/s', "CLIMB_SPEED = 0.1 ", "CLIMB_SPEED = 0.4 "),
    ('r6 A: first settle ends without a new pose', "        if after_takeoff and not drone.vision_pose_age() <= VISION_AGE_S:\n            return False\n", ""),
    ('r6 A: first settle with the r5 limit', "settle_at_target_height('takeoff height', after_takeoff=True)",
     "settle_at_target_height('takeoff height')"),
    ('r6 A: 25 s limit in every watch', "    limit = TAKEOFF_VISION_S if after_takeoff else None\n", "    limit = TAKEOFF_VISION_S\n"),
    ('r6 A: no wait for vision after 15 s (review)', "if reason is None and not done and after_takeoff and count[0] >= SETTLE_SAMPLES:",
     "if False:"),
    ('r6 A: wait-on cut without the vision silent prefix', "                reason = 'vision silent >%.0fs at", "                reason = 'no pose >%.0fs at"),
    ('r6 A: first settle limit 60 s', "TAKEOFF_VISION_S = 25.0 ", "TAKEOFF_VISION_S = 60.0 "),
    ('r6 A: climb settle also waits for vision', "settle_at_target_height('hover height')", "settle_at_target_height('hover height', after_takeoff=True)"),
    ('F1 bypass: aruco check skipped', "    drone.require_aruco(min_markers=1, timeout=15.0)\n", "    pass\n"),
]

bad = 0
for name, old, new in MUTATIONS:
    assert SRC.count(old) == 1, 'mutation anchor not unique/absent: ' + name
    d = tempfile.mkdtemp(prefix='c6mut_')
    try:
        os.makedirs(os.path.join(d, 'tests'))
        open(os.path.join(d, 'hover_marker0.py'), 'w', encoding='utf-8').write(SRC.replace(old, new))
        shutil.copy(os.path.join(HERE, 'test_hover_marker0.py'), os.path.join(d, 'tests'))
        r = subprocess.run([sys.executable, '-I', '-W', 'ignore', os.path.join(d, 'tests', 'test_hover_marker0.py')],
                           capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        caught = r.returncode != 0
        bad += not caught
        print('%-8s %s' % ('CAUGHT' if caught else 'MISSED', name))
    finally:
        shutil.rmtree(d)
print('%d/%d mutations caught' % (len(MUTATIONS) - bad, len(MUTATIONS)))
sys.exit(1 if bad else 0)
