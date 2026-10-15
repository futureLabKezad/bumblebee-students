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

# Information: https://bumblebee.coex.tech/en/simple_offboard.html#navigateglobal

import math
import time
import threading
import rclpy
from rclpy.node import Node
from bumblebee.srv import GetTelemetry, Navigate, NavigateGlobal, SetPosition, SetVelocity, SetAttitude, SetRates
from std_srvs.srv import Trigger

rclpy.init()
node = Node('flight')
_executor = rclpy.executors.SingleThreadedExecutor()
_executor.add_node(node)
threading.Thread(target=_executor.spin, daemon=True).start()


def _call(client, req, timeout=5.0):
    future = client.call_async(req)
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        time.sleep(0.01)
    return future.result()


get_telemetry_client  = node.create_client(GetTelemetry,  'get_telemetry')
navigate_client       = node.create_client(Navigate,       'navigate')
navigate_global_client = node.create_client(NavigateGlobal, 'navigate_global')
land_client           = node.create_client(Trigger,        'land')


def get_telemetry(**kwargs):
    req = GetTelemetry.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return _call(get_telemetry_client, req)


def navigate(**kwargs):
    req = Navigate.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return _call(navigate_client, req)


def navigate_global(**kwargs):
    req = NavigateGlobal.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return _call(navigate_global_client, req)


def land():
    return _call(land_client, Trigger.Request())


def wait_arrival(tolerance=0.2):
    while rclpy.ok():
        telem = get_telemetry(frame_id='navigate_target')
        if math.sqrt(telem.x ** 2 + telem.y ** 2 + telem.z ** 2) < tolerance:
            break
        time.sleep(0.2)


start = get_telemetry()

if math.isnan(start.lat):
    raise Exception('No global position, install and configure GPS sensor: https://bumblebee.coex.tech/gps')

print('Start point global position: lat={}, lon={}'.format(start.lat, start.lon))

print('Take off 3 meters')
navigate(x=0, y=0, z=3, frame_id='body', auto_arm=True)
wait_arrival()

print('Fly 1 arcsecond to the North (approx. 30 meters)')
navigate_global(lat=start.lat + 1.0/60/60, lon=start.lon, z=start.z + 3, yaw=math.inf, speed=5)
wait_arrival()

print('Fly to home position')
navigate_global(lat=start.lat, lon=start.lon, z=start.z + 3, yaw=math.inf, speed=5)
wait_arrival()

print('Land')
land()
