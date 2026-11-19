# [TEST COPY 16.11, map_final.txt: only the map list replaced, make_v2b.py; image file sha256 44963213062f1de9921839d202478bfda79290fcf2babc8885f26e7ced70b228]
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

drone.set_aruco_map([   # map_final.txt 16.11 (owner field measurement), TEST copy
    {'id':  0, 'length': 0.19, 'x':  0.000, 'y':  0.000, 'rot_z':  1.5446},
    {'id':  1, 'length': 0.29, 'x':  0.055, 'y':  0.966, 'rot_z':  1.5341},
    {'id':  2, 'length': 0.29, 'x':  0.085, 'y':  1.945, 'rot_z':  1.5551},
    {'id':  3, 'length': 0.29, 'x':  0.021, 'y':  2.921, 'rot_z': -1.5464},
    {'id':  4, 'length': 0.29, 'x': -1.215, 'y': -0.930, 'rot_z': -1.5830},
    {'id':  5, 'length': 0.29, 'x': -0.583, 'y':  0.953, 'rot_z': -1.5760},
    {'id':  6, 'length': 0.29, 'x': -0.590, 'y':  1.924, 'rot_z': -1.5743},
    {'id':  7, 'length': 0.29, 'x': -0.594, 'y':  2.954, 'rot_z': -1.5882},
    {'id':  8, 'length': 0.29, 'x': -0.595, 'y': -0.001, 'rot_z': -1.5970},
    {'id':  9, 'length': 0.29, 'x':  0.733, 'y':  0.016, 'rot_z': -1.5830},
    {'id': 10, 'length': 0.29, 'x':  0.714, 'y':  0.948, 'rot_z': -1.5656},
    {'id': 11, 'length': 0.29, 'x': -1.227, 'y':  0.953, 'rot_z':  1.5760},
    {'id': 12, 'length': 0.29, 'x': -1.227, 'y':  1.933, 'rot_z':  1.5656},
    {'id': 13, 'length': 0.29, 'x': -1.191, 'y':  2.928, 'rot_z':  1.5865},
    {'id': 14, 'length': 0.29, 'x':  0.722, 'y':  1.942, 'rot_z': -1.5848},
    {'id': 15, 'length': 0.29, 'x': -1.249, 'y':  0.013, 'rot_z': -1.5952},
    {'id': 16, 'length': 0.29, 'x': -0.584, 'y': -0.927, 'rot_z':  1.5691},
    {'id': 20, 'length': 0.29, 'x':  0.043, 'y': -0.932, 'rot_z':  1.5621},
    {'id': 18, 'length': 0.29, 'x':  0.752, 'y': -0.934, 'rot_z':  1.5743},
    {'id': 19, 'length': 0.29, 'x':  0.704, 'y':  2.910, 'rot_z':  1.5464},
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
