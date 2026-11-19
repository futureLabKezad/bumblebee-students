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
flight_profile.py -- PX4 tuning profiles for auto-flight (checked, not written).

Each profile is a dict mapping PX4 param name -> the value PX4 must already
hold for the auto-flight. Since 09.11.2026 the scripts do NOT write these
values: PX4 saves every parameter write it gets over MAVLink to flash
(PX4 v1.16.1 src/lib/parameters/parameters.cpp:449-450), so a value written
before a flight would stay after a crash, a kill switch or a lost Pi. Earlier
text here said these writes never reach PX4 storage; that was wrong.

How it works now:
  - the owner sets the profile values once in QGC (owner card, old values
    saved first, PX4 param rule 5);
  - `drone.check_flight_profile(name)` reads them (read only) straight from
    MAVROS and returns (matched, total, problems);
  - a script refuses to fly unless matched == total.

PX4 can hold only one set of values, so all examples check the same profile,
INDOOR_ARUCO_SLOW. COM_SPOOLUP_TIME is not in any profile: 0 would also switch
off PX4's check window right after arming (failsafe.cpp:592-601); the drone
keeps its own value (1 s on 20EC).

Adding a new profile: drop another entry into PROFILES below, and change the
same values on the drone and in the Gazebo airframe (the simulator follows
the drone).
"""

# Profile: indoor ArUco map flights. Not used by the examples since 09.11.2026:
# 12 of its 14 values differ from 20EC; all examples check INDOOR_ARUCO_SLOW.
# EKF2 sensor-fusion config is intentionally NOT in any profile: it is owned
# by the operator via QGC (EEPROM) so manual flight and auto flight share the
# same EKF settings. Touching EKF2 here clobbered the operator's baro fallback
# (BARO_NOISE was being inflated to 20.0, which silenced the barometer once
# vpe_fix gate closed during takeoff -- caused IMU-only drift / runaway).
INDOOR_ARUCO = {
    # --- MPC tuning: indoor ArUco profile, soft & forgiving ---
    'MPC_XY_P':               0.4,
    'MPC_XY_VEL_P_ACC':       1.5,
    'MPC_XY_VEL_I_ACC':       0.15,
    'MPC_XY_VEL_D_ACC':       0.08,
    'MPC_ACC_HOR':            2.5,
    'MPC_JERK_MAX':           3.0,
    'MPC_XY_CRUISE':          0.3,
    'MPC_XY_VEL_MAX':         0.4,
    'MPC_TKO_SPEED':          0.3,
    'MPC_LAND_SPEED':         0.4,
    'MPC_Z_VEL_MAX_UP':       0.5,
    'MPC_Z_VEL_MAX_DN':       0.5,

    # --- Safety / arming behaviour (COM_SPOOLUP_TIME: drone's own value) ---
    'COM_DISARM_PRFLT':       30.0,
}


# Profile: minimum-speed variant for first-flight verification and when the
# operator wants the drone to crawl rather than chase the marker. Softens the
# XY position/velocity loop, horizontal accel and jerk so MPC corrects gently
# instead of snapping toward the setpoint -- this avoids the pitch-tilt that
# pushed the down camera off the markers on direction reversal in
# flight_marker.py. Z-loop and vertical accel/vel are intentionally NOT
# touched: previously this profile lowered MPC_Z_P, MPC_Z_VEL_MAX_UP/DN and
# MPC_ACC_UP/DOWN_MAX, which left the altitude controller too slow to catch
# the baro/IMU drift during takeoff when the vpe_fix gate briefly closes,
# causing PX4 to AUTO.LAND mid-climb (incident on flight.py, 2026-06-08).
# Since 09.11.2026 the owner sets these values once in QGC and the scripts
# only check them. EKF2 config stays in QGC too (see INDOOR_ARUCO).
INDOOR_ARUCO_SLOW = {
    # --- XY position/velocity loop: gentle corrections ---
    'MPC_XY_P':               0.25,    # softer XY position loop (was 0.4)
    'MPC_XY_VEL_P_ACC':       1.2,     # less velocity reaction
    'MPC_XY_VEL_I_ACC':       0.10,    # less integral wind-up
    'MPC_XY_VEL_D_ACC':       0.05,    # less differential kick
    'MPC_ACC_HOR':            1.0,     # slow horizontal accel (was 2.5)
    # MPC_JERK_MAX and MPC_TKO_SPEED are not checked (09.11.2026). PX4 v1.16.1
    # does not use them in OFFBOARD: auto smoothing uses MPC_JERK_AUTO, and the
    # OFFBOARD climb limit is MPC_Z_VEL_MAX_UP (MulticopterPositionControl.cpp:
    # 486-488). Both shape the owner's manual Altitude flight instead
    # (FlightTaskManualAltitudeSmoothVel.cpp:94, FlightTaskManualAltitude.cpp:
    # 246-257), so their drone values are chosen there, not by this profile.
    'MPC_XY_CRUISE':          0.2,     # cruise XY
    'MPC_XY_VEL_MAX':         0.25,    # hard XY cap
    'MPC_LAND_SPEED':         0.3,     # slow landing
    'MPC_YAWRAUTO_MAX':       30.0,    # deg/s -- slow auto yaw

    # --- Safety / arming behaviour (COM_SPOOLUP_TIME: drone's own value) ---
    'COM_DISARM_PRFLT':       30.0,     # = 20EC
}


PROFILES = {
    'INDOOR_ARUCO':      INDOOR_ARUCO,
    'INDOOR_ARUCO_SLOW': INDOOR_ARUCO_SLOW,
}
