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

"""flight_marker_loop.py -- fly U-shaped loop 0->1->2->3->13->12->11->1->0, land precisely on 0.

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

# Apply indoor-ArUco PX4 tuning through the vpe_fix gate.
# Auto-reverts to original PX4 values on disarm; nothing is persisted.
drone.apply_flight_profile('INDOOR_ARUCO')

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

if not drone.check_aruco(timeout=10):
    exit(1)
if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    exit(1)

drone.print_pos('START')

# Sequence: 0 -> 1 -> 2 -> 3 -> 13 -> 12 -> 11 -> 1 -> 0
# Bridge waypoints inserted on the two column-to-column gaps (y=2.1 and y=0.7)
# to keep at least one ArUco marker in camera view during the 1 m sideways step.
WAYPOINTS = [
    ( 0.00, 0.70),  # 1
    ( 0.00, 1.40),  # 2
    ( 0.00, 2.10),  # 3
    (-0.50, 2.10),  # bridge 3 -> 13
    (-1.00, 2.10),  # 13
    (-1.00, 1.40),  # 12
    (-1.00, 0.70),  # 11
    (-0.50, 0.70),  # bridge 11 -> 1
    ( 0.00, 0.70),  # 1 (back)
]

try:
    drone.takeoff(height=1.3, speed=0.4)
    drone.hover(seconds=1.5)

    cruise_z = get_cruise_z()

    aborted = False
    for (wx, wy) in WAYPOINTS:
        if not drone.fly_to(x=wx, y=wy, z=cruise_z, speed=0.1, tolerance=0.25):
            print('Waypoint (%.2f, %.2f) failed -- aborting mission' % (wx, wy))
            aborted = True
            break

        # Hover with vision watchdog: emergency land if vision silent >3s.
        hover_end = time.time() + 1.0
        vision_silent_since = None
        while time.time() < hover_end and not drone.should_land:
            if drone._aruco_markers_used == 0 or drone._markers_used_age() > 1.0:
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
        drone.fly_to(x=0.0, y=0.0, z=cruise_z, speed=0.1, tolerance=0.25)
finally:
    drone.safe_land(x=0, y=0, precision_speed=0.1)
