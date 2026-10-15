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


import math
import signal
import sys
import time
import threading
import rclpy
from rclpy.node import Node
from math import nan
from bumblebee import srv
from std_srvs.srv import Trigger
from sensor_msgs.msg import Range
from aruco_pose.msg import MarkerArray
from util import handle_response

rclpy.init()
node = Node('autotest_aruco')
_executor = rclpy.executors.MultiThreadedExecutor()
_executor.add_node(node)
threading.Thread(target=_executor.spin, daemon=True).start()


def _call(client, req, timeout=5.0):
    future = client.call_async(req)
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        time.sleep(0.01)
    if not future.done():
        raise Exception('Service call timed out')
    return future.result()


def _make_caller(client, req_type):
    def caller(**kwargs):
        req = req_type()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(client, req)
    return handle_response(caller)


get_telemetry_client = node.create_client(srv.GetTelemetry, 'get_telemetry')
navigate_client      = node.create_client(srv.Navigate,     'navigate')
land_client          = node.create_client(Trigger,          'land')

navigate = _make_caller(navigate_client, srv.Navigate.Request)
land     = _make_caller(land_client,     Trigger.Request)


def get_telemetry(**kwargs):
    req = srv.GetTelemetry.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return _call(get_telemetry_client, req)


def interrupt(sig, frame):
    print('\nInterrupted, landing...')
    land()
    sys.exit(0)


signal.signal(signal.SIGINT, interrupt)


def wait_for_message(msg_type, topic, timeout=3.0):
    e = threading.Event()
    result = [None]
    def cb(msg):
        result[0] = msg
        e.set()
    sub = node.create_subscription(msg_type, topic, cb, 1)
    e.wait(timeout=timeout)
    node.destroy_subscription(sub)
    if result[0] is None:
        raise Exception('Timeout waiting for ' + topic)
    return result[0]


def print_current_map_position():
    telem = get_telemetry()
    dist = wait_for_message(Range, 'rangefinder/range').range
    print('Map position:\tx={:.1f}\ty={:.1f}\tz={:.1f}\tyaw={:.1f}\tdist={:.2f}'.format(
        telem.x, telem.y, telem.z, telem.yaw, dist))


def navigate_wait(x=0, y=0, z=0, yaw=nan, speed=0.5, frame_id='body', tolerance=0.2, auto_arm=False):
    res = navigate(x=x, y=y, z=z, yaw=yaw, speed=speed, frame_id=frame_id, auto_arm=auto_arm)
    if not res.success:
        return res
    while rclpy.ok():
        telem = get_telemetry(frame_id='navigate_target')
        if math.sqrt(telem.x ** 2 + telem.y ** 2 + telem.z ** 2) < tolerance:
            return res
        time.sleep(0.2)


# Try to disable optical flow via parameter update (replaces dynamic_reconfigure)
try:
    import subprocess
    result = subprocess.run(['ros2', 'param', 'get', '/optical_flow', 'enabled'],
                           capture_output=True, text=True, timeout=2)
    flow_available = result.returncode == 0
except Exception:
    flow_available = False

if not flow_available:
    print('Cannot configure optical flow, skip')


markers = wait_for_message(MarkerArray, 'aruco_map/map', timeout=3)
left   = min(marker.pose.position.x for marker in markers.markers)
bottom = min(marker.pose.position.y for marker in markers.markers)
width  = max(marker.pose.position.x for marker in markers.markers)
height = max(marker.pose.position.y for marker in markers.markers)
center_x = left + width / 2
center_y = bottom + height / 2

print('Map rect: %g %g - %g %g' % (left, bottom, width, height))

input('Take off and hover 1 m [enter] ')
navigate_wait(x=0, y=0, z=1, frame_id='body', auto_arm=True)
print_current_map_position()

input('Go to corner %g %g 1.5 speed 1 [enter] ' % (width, height))
navigate_wait(x=width, y=height, z=1.5, speed=1, frame_id='aruco_map')
print_current_map_position()

input('Go to center %g %g 1.5 speed 5 [enter] ' % (center_x, center_y))
navigate_wait(x=center_x, y=center_y, z=1.5, speed=5, frame_id='aruco_map')
print_current_map_position()

if flow_available:
    input('Disable optical flow and keep hovering [enter] ')
    subprocess.run(['ros2', 'param', 'set', '/optical_flow', 'enabled', 'false'])
    time.sleep(5)

    input('Enable optical flow back [enter] ')
    subprocess.run(['ros2', 'param', 'set', '/optical_flow', 'enabled', 'true'])

input('Go to side 1 %g 2 heading top [enter] ' % (center_y))
navigate_wait(x=1, y=center_y, z=2, yaw=1.57, frame_id='aruco_map')
print_current_map_position()

marker_id = markers.markers[0].id
input('Go to marker %d z=1.5 [enter] ' % marker_id)
navigate_wait(x=0, y=0, z=1.5, yaw=0, frame_id='aruco_%d' % marker_id)
print_current_map_position()

input('Perform landing [enter] ')
land()
