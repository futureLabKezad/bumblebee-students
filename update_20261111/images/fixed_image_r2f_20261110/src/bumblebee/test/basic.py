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

import time
import threading
import pytest
import rclpy
from rclpy.node import Node
from mavros_msgs.msg import State
from bumblebee import srv


@pytest.fixture(scope='module')
def ros_node():
    rclpy.init()
    node = Node('bumblebee_test')
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    yield node
    rclpy.shutdown()


def _wait_for_message(node, msg_type, topic, timeout=10.0):
    e = threading.Event()
    result = [None]
    def cb(msg):
        result[0] = msg
        e.set()
    sub = node.create_subscription(msg_type, topic, cb, 1)
    e.wait(timeout=timeout)
    node.destroy_subscription(sub)
    return result[0]


def test_state(ros_node):
    state = _wait_for_message(ros_node, State, 'mavros/state', timeout=10)
    assert state is not None
    assert state.connected == False
    assert state.armed == False
    assert state.guided == False
    assert state.mode == ''


def test_simple_offboard_services_available(ros_node):
    from std_srvs.srv import Trigger
    services = [
        ('get_telemetry',    srv.GetTelemetry),
        ('navigate',         srv.Navigate),
        ('navigate_global',  srv.NavigateGlobal),
        ('set_position',     srv.SetPosition),
        ('set_velocity',     srv.SetVelocity),
        ('set_attitude',     srv.SetAttitude),
        ('set_rates',        srv.SetRates),
        ('land',             Trigger),
    ]
    for name, srv_type in services:
        client = ros_node.create_client(srv_type, name)
        assert client.wait_for_service(timeout_sec=5.0), 'Service %s not available' % name


def test_web_video_server():
    import urllib.request
    urllib.request.urlopen('http://localhost:8080').read()


def test_long_callback(ros_node):
    from bumblebee import long_callback

    @long_callback
    def cb(i):
        cb.counter += i
    cb.counter = 0
    cb(2)
    time.sleep(0.1)
    cb(3)
    time.sleep(1)
    assert cb.counter == 5
