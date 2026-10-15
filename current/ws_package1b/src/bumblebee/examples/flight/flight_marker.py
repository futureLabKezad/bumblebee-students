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
    Returns False if /aruco_detect/markers_used stayed at 0 (or stale >1s)
    for longer than silent_limit -- caller should abort the mission and
    fall through to safe_land.
    """
    end = time.time() + seconds
    silent_since = None
    while time.time() < end and not drone.should_land:
        if drone._aruco_markers_used == 0 or drone._markers_used_age() > 1.0:
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

# Apply the slow indoor-ArUco PX4 tuning profile via the vpe_fix gate.
# Softer MPC + lower jerk/accel keeps the drone level enough during
# direction reversals to retain ArUco lock. All param changes auto-revert
# on the ARMED -> DISARMED edge so PX4 EEPROM stays untouched.
drone.apply_flight_profile('INDOOR_ARUCO_SLOW')

# ---------------------------------------------------------------------------
# Define the ArUco map for this mission
# ---------------------------------------------------------------------------
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
    drone.takeoff(height=0.7, speed=0.4)
    if not hover_vw(1.5):
        raise SystemExit('vision lost during takeoff hover')

    # Use actual cruise altitude after takeoff -- avoids large Z changes mid-flight
    cruise_z = get_cruise_z()

    # Forward leg: cruise above marker 2. Need multi-marker quorum first to
    # give the EKF a clean baseline before the first long sideways trip.
    if not wait_quorum(min_markers=2, timeout=15.0):
        raise SystemExit('no multi-marker quorum before forward leg')
    drone.fly_to(x=0, y=1.4, z=cruise_z, speed=0.10, tolerance=0.25)
    if not hover_vw(2.0):
        raise SystemExit('vision lost above marker 2')

    # Return leg with intermediate waypoint at marker 1 so EKF re-settles
    # before the final approach segment.
    if not wait_quorum(min_markers=2, timeout=15.0):
        raise SystemExit('no multi-marker quorum before return mid waypoint')
    drone.fly_to(x=0, y=0.7, z=cruise_z, speed=0.10, tolerance=0.25)
    if not hover_vw(1.0):
        raise SystemExit('vision lost above marker 1')

    if not wait_quorum(min_markers=2, timeout=15.0):
        raise SystemExit('no multi-marker quorum before final approach')
    drone.fly_to(x=0, y=0, z=cruise_z, speed=0.10, tolerance=0.25)

finally:
    drone.safe_land(x=0, y=0, precision_speed=0.1)
