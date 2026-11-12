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

import os
import time
import threading
import rclpy
from rclpy.node import Node
from mavros_msgs.srv import ParamGet
from mavros_msgs.msg import State, EstimatorStatus
from geometry_msgs.msg import PoseStamped

rclpy.init()
node = Node('final_check')
_executor = rclpy.executors.SingleThreadedExecutor()
_executor.add_node(node)
threading.Thread(target=_executor.spin, daemon=True).start()


def _call(client, req, timeout=3.0):
    future = client.call_async(req)
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        time.sleep(0.01)
    return future.result() if future.done() else None


param_get_client = node.create_client(ParamGet, 'mavros/param/get')

s = [None]; lp = [None]; es = [None]
node.create_subscription(State,           '/mavros/state',              lambda m: s.__setitem__(0, m), 1)
node.create_subscription(PoseStamped,     '/mavros/local_position/pose', lambda m: lp.__setitem__(0, m), 1)
node.create_subscription(EstimatorStatus, '/mavros/estimator_status',    lambda m: es.__setitem__(0, m), 1)

time.sleep(3)

vpe = os.popen('ps aux | grep vpe_fix | grep -v grep').read().strip()

print('\n========= PREFLIGHT CHECK ==========')
print('vpe_fix.py:      ', 'OK' if vpe else 'NOT RUNNING')
if s[0]:
    print('PX4 connected:   ', s[0].connected)
    print('Mode:            ', s[0].mode)
    print('Armed:           ', s[0].armed)
if lp[0]:
    print('Local z:         %.2fm' % lp[0].pose.position.z)
if es[0]:
    print('EKF attitude:    ', es[0].attitude_status_flag)
    print('EKF vert abs:    ', es[0].pos_vert_abs_status_flag)

# READ-ONLY check. preflight.py never writes to PX4. If a value is wrong,
# set it manually via QGC (preferred) or temporarily through the vpe_fix
# gate:  drone.set_param('NAME', value, persistent=True)
EXPECTED_PARAMS = {
    'COM_RC_OVERRIDE': 3,
    'COM_RC_IN_MODE': 0,
    'COM_SPOOLUP_TIME': 1,
    'COM_DISARM_PRFLT': 30,
    'CBRK_IO_SAFETY': 22027,
    'EKF2_EV_CTRL': 11,
}
print('\n--- PX4 Parameters (read-only check) ---')
all_ok = True
for name, expected in EXPECTED_PARAMS.items():
    try:
        req = ParamGet.Request()
        req.param_id = name
        r = _call(param_get_client, req)
        if r is None:
            print('%-22s TIMEOUT' % (name + ':'))
            continue
        val = r.value.integer if r.value.integer else int(r.value.real)
        match = (val == expected)
        if not match:
            all_ok = False
            print('%-22s WARN (got %d, exp %d) -- set via QGC or '
                  "drone.set_param('%s', %d, persistent=True)"
                  % (name + ':', val, expected, name, expected))
        else:
            print('%-22s OK' % (name + ':'))
    except Exception:
        print('%-22s ERR' % (name + ':'))

rc = os.popen('timeout 2 ros2 topic echo /mavros/rc/in --once 2>/dev/null | grep rssi').read().strip()
print('\n--- RC Signal ---')
print('RC:', rc if rc else 'NO SIGNAL')
print('\n=====================================')
print('STATUS:', 'READY TO FLY' if all_ok and vpe else 'ISSUES FOUND')

node.destroy_node()
rclpy.shutdown()
