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
flight_profile.py -- declarative PX4 tuning profiles for auto-flight.

Each profile is a dict mapping PX4 param name -> the value to apply for the
duration of the auto-flight. Values are pushed through the vpe_fix gate by
`drone.apply_flight_profile()`. The gate:

  - reads the current PX4 value first and stores it as the "original",
  - writes the profile value,
  - reverts every override on the ARMED->DISARMED edge (auto-flight end)
    and on a clean shutdown.

Nothing is persisted to PX4 EEPROM by this stack: the moment auto-flight
finishes, PX4'"'"'s active config is identical to whatever it was before the
script started. Manual PX4 tuning via QGC is sacred.

Adding a new profile: drop another entry into PROFILES below. Keep the
"INDOOR_ARUCO" profile in sync with what your indoor ArUco flights expect.
"""

# Profile: indoor ArUco map flights (flight_marker.py, flight_marker_loop.py).
# EKF2 sensor-fusion config is intentionally NOT in any profile: it is owned
# by the operator via QGC (EEPROM) so manual flight and auto flight share the
# same EKF settings. Touching EKF2 here clobbered the operator'"'"'s baro fallback
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

    # --- Safety / arming behaviour ---
    'COM_SPOOLUP_TIME':       0.0,
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
# All overrides revert through vpe_fix on ARMED->DISARMED -- same temporary
# contract as the other profiles. EKF2 config stays in QGC (see INDOOR_ARUCO).
INDOOR_ARUCO_SLOW = {
    # --- XY position/velocity loop: gentle corrections ---
    'MPC_XY_P':               0.25,    # softer XY position loop (was 0.4)
    'MPC_XY_VEL_P_ACC':       1.2,     # less velocity reaction
    'MPC_XY_VEL_I_ACC':       0.10,    # less integral wind-up
    'MPC_XY_VEL_D_ACC':       0.05,    # less differential kick
    'MPC_ACC_HOR':            1.0,     # slow horizontal accel (was 2.5)
    'MPC_JERK_MAX':           1.5,     # smoother trajectories
    'MPC_XY_CRUISE':          0.2,     # cruise XY
    'MPC_XY_VEL_MAX':         0.25,    # hard XY cap
    'MPC_TKO_SPEED':          0.2,     # slow takeoff
    'MPC_LAND_SPEED':         0.3,     # slow landing
    'MPC_YAWRAUTO_MAX':       30.0,    # deg/s -- slow auto yaw

    # --- Safety / arming behaviour (same as INDOOR_ARUCO) ---
    'COM_SPOOLUP_TIME':       0.0,
    'COM_DISARM_PRFLT':       30.0,
}


PROFILES = {
    'INDOOR_ARUCO':      INDOOR_ARUCO,
    'INDOOR_ARUCO_SLOW': INDOOR_ARUCO_SLOW,
}
