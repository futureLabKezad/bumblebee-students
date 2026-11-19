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

"""[TEST COPY 16.11 r2 (points rounded to 0.01 m, make_r2.py), map_final.txt: map and points recomputed, make_v2.py; image file sha256 7f36db429eb26f7e878aa16ee7998b883eeaa00e184b5a5c5dc07544318e1d1d]
flight_marker_loop.py -- fly U-shaped loop 0->1->2->3->13->12->11->1->0, land precisely on 0.

The map is defined directly in this script.

Run: python3 flight_marker_loop.py
"""

import sys
import math
import time
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone


def get_cruise_z(retries=20, interval=0.2):
    """Read current altitude, retrying until non-NaN (handles intermittent TF2 gaps)."""
    for _ in range(retries):
        _, _, z = drone.get_pos()
        if not math.isnan(z):
            return z
        time.sleep(interval)
    raise RuntimeError('Could not read altitude after %d attempts' % retries)


drone.enable_safe_interrupt()

# Check (read only) the indoor-ArUco PX4 tuning. Until 09.11.2026 this script
# wrote INDOOR_ARUCO in flight; a write is saved to PX4 flash and could stay
# after a crash. PX4 can hold one set of values, so all examples now check
# INDOOR_ARUCO_SLOW, set once by the owner in QGC; refuse to fly if they differ.
try:
    _matched, _total, _problems = drone.check_flight_profile('INDOOR_ARUCO_SLOW')
except Exception as e:
    print('PREFLIGHT FAIL: check_flight_profile raised: %s' % e)
    drone._shutdown()
    sys.exit(3)
if _matched < _total:
    print('PREFLIGHT FAIL: only %d/%d PX4 params match INDOOR_ARUCO_SLOW (%s).'
          ' Refusing to fly. Set these values in QGC (owner card).'
          % (_matched, _total, '; '.join(_problems)))
    drone._shutdown()
    sys.exit(3)

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

if not drone.check_aruco(timeout=10):
    exit(1)
if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    exit(1)

drone.print_pos('START')

# Sequence: 0 -> 1 -> 2 -> 3 -> 13 -> 12 -> 11 -> 1 -> 0
# Bridge waypoints inserted on the two column-to-column gaps (y=2.1 and y=0.7)
# to keep at least one ArUco marker in camera view during the 1 m sideways step.
WAYPOINTS = [   # map_final.txt: the centres of the same markers
    ( 0.06,  0.97),  # 1
    ( 0.09,  1.95),  # 2
    ( 0.02,  2.92),  # 3
    (-0.59,  2.95),  # bridge 3 -> 13 (over marker 7)
    (-1.19,  2.93),  # 13
    (-1.23,  1.93),  # 12
    (-1.23,  0.95),  # 11
    (-0.58,  0.95),  # bridge 11 -> 1 (over marker 5)
    ( 0.06,  0.97),  # 1 (back)
]

try:
    drone.takeoff(height=1.3, speed=0.4)
    drone.hover(seconds=1.5)

    cruise_z = get_cruise_z()

    aborted = False
    for (wx, wy) in WAYPOINTS:
        # F7 (r2d): 0.12 m and nearly stopped -- a margin under the 0.25 m of C7
        if not drone.fly_to(x=wx, y=wy, z=cruise_z, speed=0.1, tolerance=0.12, settle_speed=0.05):
            print('Waypoint (%.2f, %.2f) failed -- aborting mission' % (wx, wy))
            aborted = True
            break

        # Hover with vision watchdog: emergency land if vision silent >3s.
        hover_end = time.time() + 1.0
        vision_silent_since = None
        while time.time() < hover_end and not drone.should_land:
            if drone.vision_pose_age() > 1.0:   # r2f (T35): new vpe_fix poses only
                if vision_silent_since is None:
                    vision_silent_since = time.time()
                elif time.time() - vision_silent_since > 3.0:
                    print('flight_marker_loop: vision silent >3.0s -- emergency land')
                    aborted = True
                    break
            else:
                vision_silent_since = None
            time.sleep(0.1)
        if aborted:
            break

    if not aborted:
        drone.fly_to(x=0.0, y=0.0, z=cruise_z, speed=0.1, tolerance=0.12, settle_speed=0.05)
finally:
    drone.safe_land(x=0, y=0, precision_speed=0.1)
