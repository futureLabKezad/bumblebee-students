#!/usr/bin/env python3
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
set_params.py -- READ-ONLY DIAGNOSTIC.

This script does NOT write to PX4. The vpe_fix gate is the only sanctioned
writer of PX4 parameters, and it no longer pushes a boot-time baseline:
params are applied on demand only when a flight script calls
drone.set_param(...), which routes through /vpe_fix/set_param and is
auto-reverted on disarm / shutdown / TTL. PX4 config set manually via QGC
or mavlink_shell is authoritative -- we do not clobber it at boot.

The `params` dict below is a HUMAN-READABLE REFERENCE of "typical" tuning
values that have worked for indoor ArUco flight. Editing it has NO RUNTIME
EFFECT. To apply a value, call `drone.set_param('NAME', value)` from a
flight script.

Running this script prints a warning and exits 0 without touching MAVROS.
"""

import time
import threading
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from mavros_msgs.msg import State
from mavros_msgs.srv import ParamPull, ParamSetV2
from rcl_interfaces.msg import ParameterValue, ParameterType

# ----------------------------------------------------------------------------
# Reference-only "typical" tuning values for indoor ArUco flight. This dict
# is documentation, not a source of truth: it is never read at runtime.
# DO NOT add code that loops over this dict and writes to MAVROS.
# ----------------------------------------------------------------------------
params = {
    # EKF2 vision params (EV_CTRL, EVP_NOISE, EVA_NOISE, EV_DELAY, HGT_REF) are
    # owned by vpe_fix.py — set there at startup with retry. Do not duplicate
    # them here (single source of truth).

    # --- Arming / safety ---
    'COM_SPOOLUP_TIME': 0.0,    # no spoolup delay
    'COM_DISARM_PRFLT': 30.0,   # disarm after 30s on ground

    # --- Position controller (XY) — soft but capable of holding position ---
    'MPC_XY_P':         0.35,   # position P gain (compromise: drone still pulls back to setpoint)
    'MPC_XY_VEL_P_ACC': 1.2,    # PX4 min velocity P gain
    'MPC_XY_VEL_I_ACC': 0.2,    # low integrator gain
    'MPC_XY_VEL_D_ACC': 0.1,    # PX4 min velocity D gain

    # --- Trajectory / speed — smooth start/stop, low max speed ---
    'MPC_ACC_HOR':      2.0,    # PX4 min horizontal acceleration m/s^2
    'MPC_JERK_MAX':     2.0,    # very smooth jerk profile m/s^3
    'MPC_XY_CRUISE':    0.3,    # cruise speed during fly_to (m/s)
    'MPC_XY_VEL_MAX':   0.8,    # absolute XY speed cap (m/s) -- room to recover from drift

    # --- Vertical (Z) — gentle takeoff and landing for ArUco visibility ---
    'MPC_TKO_SPEED':    0.3,    # initial takeoff climb rate (m/s)
    'MPC_LAND_SPEED':   0.4,    # final descent rate (m/s) -- slow to keep marker in FOV
    'MPC_Z_VEL_MAX_UP': 0.5,    # cap upward velocity (m/s)
    'MPC_Z_VEL_MAX_DN': 0.5,    # cap downward velocity (m/s)
}

# ----------------------------------------------------------------------------
# Read-only diagnostic guard. Exit before any MAVROS interaction so this
# script can never write to PX4. To apply a value, use:
#   drone.set_param('NAME', value)                # auto-revert on disarm
#   drone.set_param('NAME', value, persistent=True)  # keep value
# ----------------------------------------------------------------------------
print('=' * 60)
print('WARNING: set_params.py is READ-ONLY.')
print('All PX4 param writes must go through /vpe_fix/set_param (the gate).')
print('Use drone.set_param() from a flight script.')
print('=' * 60)
raise SystemExit(0)

rclpy.init()
node = Node('set_params')
_executor = rclpy.executors.SingleThreadedExecutor()
_executor.add_node(node)
threading.Thread(target=_executor.spin, daemon=True).start()

# Wait for MAVROS set service
set_client = node.create_client(ParamSetV2, '/mavros/mavros/set')
print('Waiting for /mavros/mavros/set service...')
if not set_client.wait_for_service(timeout_sec=60.0):
    print('ERROR: /mavros/mavros/set not available')
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(1)

# Wait for pull service
pull_client = node.create_client(ParamPull, '/mavros/mavros/pull')
print('Waiting for /mavros/mavros/pull service...')
if not pull_client.wait_for_service(timeout_sec=30.0):
    print('ERROR: /mavros/mavros/pull not available')
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(1)

# Wait for MAVROS FCU connection
connected = [False]
state_qos = QoSProfile(
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)
def state_cb(msg):
    connected[0] = msg.connected

sub = node.create_subscription(State, '/mavros/state', state_cb, state_qos)
print('Waiting for MAVROS FCU connection...')
deadline = time.time() + 60.0
while not connected[0] and time.time() < deadline:
    time.sleep(0.5)

if not connected[0]:
    print('ERROR: MAVROS not connected to FCU after 60s')
    node.destroy_node()
    rclpy.shutdown()
    raise SystemExit(1)

# Force-pull PX4 parameter table into MAVROS cache
print('Pulling PX4 parameter table from FCU...')
pull_req = ParamPull.Request()
pull_req.force_pull = True
pull_future = pull_client.call_async(pull_req)
deadline = time.time() + 60.0
while not pull_future.done() and time.time() < deadline:
    time.sleep(0.2)

if pull_future.done() and pull_future.result().success:
    print('Param pull OK: %d params received' % pull_future.result().param_received)
else:
    print('WARNING: param pull failed or timed out, continuing anyway')

print('Applying %d parameters...' % len(params))

ok = 0
for name, value in sorted(params.items()):
    try:
        pval = ParameterValue()
        if isinstance(value, int):
            pval.type = ParameterType.PARAMETER_INTEGER
            pval.integer_value = value
        else:
            pval.type = ParameterType.PARAMETER_DOUBLE
            pval.double_value = float(value)
        req = ParamSetV2.Request()
        req.force_set = True
        req.param_id = name
        req.value = pval
        future = set_client.call_async(req)
        deadline = time.time() + 8.0
        while not future.done() and time.time() < deadline:
            time.sleep(0.02)
        if not future.done():
            print('  TIMEOUT %s' % name)
            continue
        res = future.result()
        if res.success:
            print('  OK  %s = %s' % (name, value))
            ok += 1
        else:
            print('  FAIL %s (not found on this firmware)' % name)
    except Exception as e:
        print('  ERR  %s: %s' % (name, e))

print('\n%d/%d params set.' % (ok, len(params)))
node.destroy_node()
rclpy.shutdown()
