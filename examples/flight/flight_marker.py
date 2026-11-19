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
[TEST COPY 16.11 r2 (points rounded to 0.01 m, make_r2.py), map_final.txt: map and points recomputed, make_v2.py; image file sha256 1e0063fb3557a516767122a3031d38678be10e58efb2cc07a3e83df538e529fb]
flight_marker.py -- fly from marker 0 to marker 2, return, land precisely.

Map: column of ArUco tags along +Y. Drone takes off above marker 0, cruises
over marker 2 at (0, 1.4), holds, then returns via marker 1 (0, 0.7) and
precision-lands on marker 0.

The slow MPC profile + intermediate return waypoint avoid the reverse-leg
drift seen with the aggressive INDOOR_ARUCO profile: softer accel/jerk
keeps pitch shallow during reversal, so the down-facing camera stays
roughly vertical and ArUco detection does not drop.

Before every fly_to we actively wait for a multi-marker quorum
(markers_used >= 2 with fresh detection). Without it, single-marker
IPPE plus periodic vpe_fix gate closures cause EKF pose snaps mid-flight
and large MPC overshoot.

Run: python3 flight_marker.py
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


def hover_vw(seconds, silent_limit=6.0):
    """Hover with a vision watchdog.

    Returns True if the full duration elapses with vision healthy.
    Returns False if vpe_fix published no NEW pose (drone.vision_pose_age() > 1 s, r2f)
    for longer than silent_limit -- caller should abort the mission and
    fall through to safe_land.
    """
    end = time.time() + seconds
    silent_since = None
    while time.time() < end and not drone.should_land:
        if drone.vision_pose_age() > 1.0:   # r2f (T35): new vpe_fix poses only
            if silent_since is None:
                silent_since = time.time()
            elif time.time() - silent_since > silent_limit:
                print('flight_marker: vision silent >%.1fs -- aborting' % silent_limit)
                return False
        else:
            silent_since = None
        time.sleep(0.1)
    return True


def wait_quorum(min_markers=2, timeout=15.0, max_age=1.0):
    """Block until aruco_detect reports >= min_markers with fresh detection.

    Returns True once quorum holds for a single tick. Returns False on
    timeout -- caller should abort to safe_land rather than fly with a
    single-marker geometry that is prone to IPPE flips and EKF snaps.
    """
    deadline = time.time() + timeout
    print('Waiting for quorum >=%d markers (timeout %.1fs)...' % (min_markers, timeout))
    while time.time() < deadline and not drone.should_land:
        mu = drone._aruco_markers_used
        age = drone._markers_used_age()
        if mu >= min_markers and age <= max_age:
            print('  quorum OK: markers=%d age=%.2fs' % (mu, age))
            return True
        time.sleep(0.1)
    print('  quorum NOT reached in %.1fs (last markers=%d age=%.2fs)' % (
        timeout, drone._aruco_markers_used, drone._markers_used_age()))
    return False


# Register Ctrl+C handler for graceful landing on interrupt
drone.enable_safe_interrupt()

# Check (read only) the slow indoor-ArUco PX4 tuning profile. Softer MPC +
# lower jerk/accel keeps the drone level enough during direction reversals
# to retain ArUco lock. Since 09.11.2026 nothing is written to PX4 (a write
# is saved to PX4 flash and could stay after a crash): the owner sets these
# values once in QGC; refuse to fly if they differ.
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

# ---------------------------------------------------------------------------
# Define the ArUco map for this mission
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if not drone.check_aruco(timeout=10):
    exit(1)

if not drone.wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0):
    exit(1)

drone.print_pos('START')

# ---------------------------------------------------------------------------
# Flight
# ---------------------------------------------------------------------------
try:
    drone.takeoff(height=0.9, speed=0.4)
    if not hover_vw(1.5):
        raise SystemExit('vision lost during takeoff hover')

    # Use actual cruise altitude after takeoff -- avoids large Z changes mid-flight
    cruise_z = get_cruise_z()

    # Forward leg: cruise above marker 2. Need multi-marker quorum first to
    # give the EKF a clean baseline before the first long sideways trip.
    if not wait_quorum(min_markers=2, timeout=15.0):
        raise SystemExit('no multi-marker quorum before forward leg')
    # F7 (r2d): 0.12 m and nearly stopped -- a margin under the 0.25 m of C7
    if not drone.fly_to(x=0.09, y=1.95, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05):
        raise SystemExit('waypoint above marker 2 not reached')   # r2e: finally -> safe_land
    if not hover_vw(2.0):
        raise SystemExit('vision lost above marker 2')

    # Return leg with intermediate waypoint at marker 1 so EKF re-settles
    # before the final approach segment.
    if not wait_quorum(min_markers=2, timeout=15.0):
        raise SystemExit('no multi-marker quorum before return mid waypoint')
    if not drone.fly_to(x=0.06, y=0.97, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05):
        raise SystemExit('waypoint above marker 1 not reached')
    if not hover_vw(1.0):
        raise SystemExit('vision lost above marker 1')

    if not wait_quorum(min_markers=2, timeout=15.0):
        raise SystemExit('no multi-marker quorum before final approach')
    if not drone.fly_to(x=0, y=0, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05):
        raise SystemExit('waypoint above marker 0 not reached')

finally:
    drone.safe_land(x=0, y=0, precision_speed=0.1)
