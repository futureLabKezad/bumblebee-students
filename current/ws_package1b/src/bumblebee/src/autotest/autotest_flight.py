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
from math import nan, inf
from bumblebee import srv
from std_srvs.srv import Trigger
from sensor_msgs.msg import Range
from util import handle_response

rclpy.init()
node = Node('autotest_flight')
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
navigate_global_client = node.create_client(srv.NavigateGlobal, 'navigate_global')
set_yaw_client       = node.create_client(srv.SetYaw,       'set_yaw')
set_yaw_rate_client  = node.create_client(srv.SetYawRate,   'set_yaw_rate')
set_position_client  = node.create_client(srv.SetPosition,  'set_position')
set_velocity_client  = node.create_client(srv.SetVelocity,  'set_velocity')
set_attitude_client  = node.create_client(srv.SetAttitude,  'set_attitude')
set_rates_client     = node.create_client(srv.SetRates,     'set_rates')
land_client          = node.create_client(Trigger,          'land')


def get_telemetry(**kwargs):
    req = srv.GetTelemetry.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return _call(get_telemetry_client, req)


navigate      = _make_caller(navigate_client,      srv.Navigate.Request)
navigate_global = _make_caller(navigate_global_client, srv.NavigateGlobal.Request)
set_yaw       = _make_caller(set_yaw_client,       srv.SetYaw.Request)
set_yaw_rate  = _make_caller(set_yaw_rate_client,  srv.SetYawRate.Request)
set_position  = _make_caller(set_position_client,  srv.SetPosition.Request)
set_velocity  = _make_caller(set_velocity_client,  srv.SetVelocity.Request)
set_attitude  = _make_caller(set_attitude_client,  srv.SetAttitude.Request)
set_rates     = _make_caller(set_rates_client,     srv.SetRates.Request)
land          = _make_caller(land_client,           Trigger.Request)


def interrupt(sig, frame):
    print('\nInterrupted, landing...')
    land()
    sys.exit(0)


signal.signal(signal.SIGINT, interrupt)


def navigate_wait(x=0, y=0, z=0, yaw=nan, speed=0.5, frame_id='body', tolerance=0.2, auto_arm=False):
    res = navigate(x=x, y=y, z=z, yaw=yaw, speed=speed, frame_id=frame_id, auto_arm=auto_arm)
    if not res.success:
        return res
    while rclpy.ok():
        telem = get_telemetry(frame_id='navigate_target')
        if math.sqrt(telem.x ** 2 + telem.y ** 2 + telem.z ** 2) < tolerance:
            return res
        time.sleep(0.2)


def print_distance():
    e = threading.Event()
    result = [None]
    def cb(msg):
        result[0] = msg
        e.set()
    sub = node.create_subscription(Range, 'rangefinder/range', cb, 1)
    e.wait(timeout=3.0)
    node.destroy_subscription(sub)
    if result[0]:
        print('Distance: {:.2f}'.format(result[0].range))


input('Take off and hover 1 m [enter] ')
navigate_wait(z=1, frame_id='body', auto_arm=True)
print_distance()
start = get_telemetry()

input('Fly forward 2 m [enter] ')
navigate_wait(x=2, frame_id='navigate_target')
print_distance()

input('Climb 0.5 m [enter] ')
navigate_wait(z=0.5, frame_id='navigate_target')
print_distance()

input('Rotate left 90° [enter] ')
navigate(yaw=math.pi / 2, frame_id='navigate_target')
time.sleep(3)

input('Use set_velocity to fly forward 2 m speed 1 [enter]')
set_velocity(vx=1, vy=0.0, vz=0, frame_id='body')
time.sleep(2)
set_position(frame_id='body')

input('Rotate right 90° using set_yaw [enter] ')
set_yaw(yaw=-math.pi / 2, frame_id='navigate_target')
time.sleep(3)

input('Use set_attitude to fly backwards [enter]')
set_attitude(roll=0, pitch=-0.3, yaw=0, thrust=0.5, frame_id='body')
time.sleep(0.3)
set_position(frame_id='body')

input('Use set_attitude to fly right [enter]')
set_attitude(roll=0.3, pitch=0, yaw=0, thrust=0.5, frame_id='body')
time.sleep(0.5)
set_position(frame_id='body')

input('Use set_rates to fly right [enter]')
set_rates(roll_rate=1.2, thrust=0.5)
time.sleep(0.4)
set_position(frame_id='body')

input('Rotate 360° to the right using set_yaw_rate [enter]')
set_yaw_rate(yaw_rate=-1)
time.sleep(2 * math.pi)
set_position(frame_id='body')

input('Return to start point heading forward [enter]')
navigate_wait(x=start.x, y=start.y, z=start.z, yaw=inf, speed=1, frame_id='map')

input('Land [enter]')
land()
