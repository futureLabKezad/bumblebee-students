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

"""aruco_z_test.py -- record drone position and prompt the user when to lift/lower.

Run on the drone:
    python3 aruco_z_test.py

The script prints action prompts on screen at fixed times. Follow them.
Schedule (35s total):
   0-7s   : drone on the floor, do not move
   8-17s  : LIFT ~30 cm and HOLD (still)
   18-27s : on the floor again
   28-35s : LIFT again to verify repeatability
"""

import sys
import math
import time
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

DURATION = 35.0
RATE_HZ = 10.0
CSV_PATH = '/tmp/aruco_z_test.csv'

# (t_start, t_end, label)
PHASES = [
    (0.0,  7.0, 'ON FLOOR (do not move)'),
    (8.0, 17.0, 'LIFT ~30 cm AND HOLD'),
    (18.0, 27.0, 'BACK ON FLOOR'),
    (28.0, 35.0, 'LIFT ~30 cm AGAIN'),
]

drone.set_aruco_map([
    {'id':  0, 'length': 0.19, 'x':  0.00, 'y':  0.00},
    {'id':  1, 'length': 0.29, 'x':  0.00, 'y':  0.73},
    {'id':  2, 'length': 0.29, 'x':  0.00, 'y':  1.42},
    {'id':  3, 'length': 0.29, 'x':  0.00, 'y':  2.11},
    {'id':  4, 'length': 0.29, 'x': -0.72, 'y': -0.73, 'rot_z': -1.571},
    {'id':  5, 'length': 0.29, 'x': -0.36, 'y':  0.73, 'rot_z': -1.571},
    {'id':  6, 'length': 0.29, 'x': -0.36, 'y':  1.42, 'rot_z': -1.571},
    {'id':  7, 'length': 0.29, 'x': -0.36, 'y':  2.11, 'rot_z': -1.571},
    {'id':  8, 'length': 0.29, 'x': -0.36, 'y':  0.00, 'rot_z': -1.571},
    {'id':  9, 'length': 0.29, 'x':  0.48, 'y':  0.00, 'rot_z': -1.571},
    {'id': 10, 'length': 0.29, 'x':  0.48, 'y':  0.73, 'rot_z': -1.571},
    {'id': 11, 'length': 0.29, 'x': -0.72, 'y':  0.73},
    {'id': 12, 'length': 0.29, 'x': -0.72, 'y':  1.42},
    {'id': 13, 'length': 0.29, 'x': -0.72, 'y':  2.11},
    {'id': 14, 'length': 0.29, 'x':  0.48, 'y':  1.42, 'rot_z': -1.571},
    {'id': 15, 'length': 0.29, 'x': -0.72, 'y':  0.00, 'rot_z': -1.571},
    {'id': 16, 'length': 0.29, 'x': -0.36, 'y': -0.73},
    {'id': 20, 'length': 0.29, 'x':  0.00, 'y': -0.73},
    {'id': 18, 'length': 0.29, 'x':  0.48, 'y': -0.73},
    {'id': 19, 'length': 0.29, 'x':  0.48, 'y':  2.11},
])

print('Waiting for ArUco marker visibility (5s)...')
drone.check_aruco(timeout=5)

print('')
print('====================================================')
print('  Z DRIFT / INVERSION TEST')
print('  Follow on-screen action prompts.')
print('  Starting in 3 seconds...')
print('====================================================')
time.sleep(1)
print('  3...')
time.sleep(1)
print('  2...')
time.sleep(1)
print('  1...')
time.sleep(1)
print('  GO!')
print('')

start = time.monotonic()
period = 1.0 / RATE_HZ
samples = []
current_phase = -1

while True:
    t = time.monotonic() - start
    if t >= DURATION:
        break

    # Detect phase transition and print a big banner
    new_phase = -1
    for i, (s, e, lbl) in enumerate(PHASES):
        if s <= t < e:
            new_phase = i
            break
    if new_phase != current_phase:
        current_phase = new_phase
        if new_phase >= 0:
            lbl = PHASES[new_phase][2]
            print('')
            print('  >>>>>>>>>>  %s  <<<<<<<<<<' % lbl)
            print('')

    try:
        x, y, z = drone.get_pos()
    except Exception:
        x = y = z = float('nan')
    samples.append((t, x, y, z))
    print('  t=%5.1fs   x=%6.3f  y=%6.3f  z=%6.3f' % (t, x, y, z))
    time.sleep(period)

with open(CSV_PATH, 'w') as f:
    f.write('t,x,y,z,phase\n')
    for (t, x, y, z) in samples:
        phase = ''
        for s, e, lbl in PHASES:
            if s <= t < e:
                phase = lbl
                break
        f.write('%.3f,%.4f,%.4f,%.4f,%s\n' % (t, x, y, z, phase))

# Per-phase z stats
print('')
print('====================================================')
print('  SUMMARY')
print('====================================================')
for s, e, lbl in PHASES:
    zs = [z for (t, _, _, z) in samples if s <= t < e and not math.isnan(z)]
    if zs:
        print('  %-28s z_avg=%6.3f  z_min=%6.3f  z_max=%6.3f' %
              (lbl, sum(zs) / len(zs), min(zs), max(zs)))
print('')
print('  CSV: %s' % CSV_PATH)
