#!/usr/bin/env python3
"""make_descent_r2.py (Claude 11.11). descent_after_floor_r2.py = descent_after_floor.py (r1, ccbba76a, kept) with the descent
in 0.1 m steps (one fly_to per step) instead of one fly_to 0.8 m down: r1 runs t45_desc_01/02 were cut at once by drone.py's
guard «Altitude overshoot: z > target + 0.6 -- runaway climb, landing» (navigate_wait). Same speed 0.05 m/s, tolerance 0.05.
After each step the [STEP] line prints the reached step. Writes ./descent_after_floor_r2.py (open 'x')."""
import hashlib
s = open('/work/t45_descent_20261111/descent_after_floor.py', encoding='utf-8').read()
assert hashlib.sha256(s.encode()).hexdigest().startswith('ccbba76a3231c6bc')
a = ("        if not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=start.z + DESC_LOW_H, speed=DESC_SPEED, tolerance=0.05):\n"
     "            return not_reached('T45 descent target')\n")
b = ("        n = int(round((HOVER_H - DESC_LOW_H) / 0.1))   # r2: 0.1 m steps (drone.py overshoot guard: z > target + 0.6)\n"
     "        for k in range(1, n + 1):\n"
     "            zt = hover_z - 0.1 * k\n"
     "            if not drone.fly_to(x=MARKER0_X, y=MARKER0_Y, z=zt, speed=DESC_SPEED, tolerance=0.05):\n"
     "                return not_reached('T45 descent step %d (z %.2f)' % (k, zt))\n"
     "            print('[STEP] %d reached z %.2f (START z + %.2f)' % (k, zt, zt - start.z), flush=True)\n")
assert s.count(a) == 1
s = s.replace(a, b).replace('descent_after_floor.py (T45 study, Claude 11.11; made by make_descent.py from hover r6)',
                            'descent_after_floor_r2.py (T45 study, Claude 11.11; r2 = 0.1 m steps; make_descent_r2.py)', 1)
with open('/work/t45_descent_20261111/descent_after_floor_r2.py', 'x', encoding='utf-8', newline='\n') as f:
    f.write(s)
print('r2 sha16', hashlib.sha256(s.encode()).hexdigest()[:16])
