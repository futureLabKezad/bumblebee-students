#!/usr/bin/env python3
"""make_descent.py (Claude «Симулятор», 11.11.2026; chat 1 00:36 п.1, T45 «садиться по зрению»). STUDY ONLY, NOT SCORED,
SIMULATOR ONLY. descent_after_floor.py = hover r6 (/work/c6_hover_script_r6_20261110/hover_marker0.py, not changed) with:
  - HOVER_S 65 -> 15 (the launcher's --inject-on '[HOVER] t=' 10 floor_near_off comes at ~10 s of the hover);
  - after the hover: one slow fly_to straight down over marker 0 from the hover height (START z + 1.0) to START z + 0.2 at
    DESC_SPEED 0.05 m/s (drone.py navigate_wait vision watchdog W stays as it is: if vision is gone > 6 s it lands - that
    is part of the answer), then a 3 s watch at 0.2 m, then the usual safe_land;
  - a READ-ONLY monitor thread prints every 0.2 s: '[VIS] markers_used=N vision_age=S' from drone module globals
    (_aruco_markers_used, vision_pose_age()); it sends nothing. Height comes from the [FLY_TO] lines (0.5 s) and the ULog.
Writes ./descent_after_floor.py (open 'x')."""
import hashlib
R6 = '/work/c6_hover_script_r6_20261110/hover_marker0.py'
s = open(R6, encoding='utf-8').read()
assert hashlib.sha256(s.encode()).hexdigest().startswith('a11b195ce1507607')
rep = [
    ('"""\nhover_marker0.py -- take off', '"""\ndescent_after_floor.py (T45 study, Claude 11.11; made by make_descent.py from hover r6) -- STUDY ONLY.\nhover_marker0.py -- take off'),
    ('HOVER_S = 65.0 ', 'HOVER_S = 15.0   # T45: was 65.0;'),
    ('import math\nimport sys\nimport time\n', 'import math\nimport sys\nimport threading\nimport time\n'),
    ('                held, reason = hold_over_marker0(HOVER_S)\n',
     '                held, reason = hold_over_marker0(HOVER_S)\n'
     '                if reason is None:   # T45: slow descent over marker 0 after floor_near_off\n'
     '                    reason = descend_study()\n'),
    ("t_takeoff = None   # r5 (S4)",
     "DESC_LOW_H = 0.2     # T45: descend to START z + this\n"
     "DESC_SPEED = 0.05    # T45: m/s\n"
     "_mon_stop = threading.Event()\n\n\n"
     "def _monitor():\n"
     "    \"\"\"T45: read only, sends nothing; markers in frame and new-pose age every 0.2 s.\"\"\"\n"
     "    while not _mon_stop.is_set():\n"
     "        try:\n"
     "            print('[VIS] markers_used=%d vision_age=%.2f' % (int(drone._aruco_markers_used), drone.vision_pose_age()), flush=True)\n"
     "        except Exception as e:\n"
     "            print('[VIS] read failed: %s' % e, flush=True)\n"
     "        _mon_stop.wait(0.2)\n\n\n"
     "def descend_study():\n"
     "    \"\"\"T45: one slow fly_to down over marker 0, then a 3 s watch. Returns reason or None.\"\"\"\n"
     "    print('=== T45 DESCENT START from z %.2f to z %.2f at %.2f m/s ===' % (hover_z, start.z + DESC_LOW_H, DESC_SPEED), flush=True)\n"
     "    th = threading.Thread(target=_monitor, daemon=True); th.start()\n"
     "    try:\n"
     "        if not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=start.z + DESC_LOW_H, speed=DESC_SPEED, tolerance=0.05):\n"
     "            return not_reached('T45 descent target')\n"
     "        _, r, _ = watch(3.0, '[LOW]', vision_limit=1e9)\n"
     "        return r\n"
     "    finally:\n"
     "        _mon_stop.set()\n"
     "        print('=== T45 DESCENT END ===', flush=True)\n\n\n"
     "t_takeoff = None   # r5 (S4)"),
]
for a, b in rep:
    assert s.count(a) == 1, a
    s = s.replace(a, b)
with open('/work/t45_descent_20261111/descent_after_floor.py', 'x', encoding='utf-8', newline='\n') as f:
    f.write(s)
print('descent sha16', hashlib.sha256(s.encode()).hexdigest()[:16])
