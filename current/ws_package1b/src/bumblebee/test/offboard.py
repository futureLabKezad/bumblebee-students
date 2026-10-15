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

"""Integration test for simple_offboard node.

Requires simple_offboard to be running. Mocks mavros publishers/services
to drive the node through its state machine and verify responses.
"""

import time
import threading
import pytest
from pytest import approx
import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
from rclpy.time import Time
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
import mavros_msgs.msg
from mavros_msgs.srv import SetMode
from geometry_msgs.msg import PoseStamped
from bumblebee import srv
from bumblebee.msg import State
from std_srvs.srv import Trigger
from math import nan, inf
import tf2_ros


_latch_qos = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    reliability=ReliabilityPolicy.RELIABLE,
)


@pytest.fixture(scope='module')
def node():
    rclpy.init()
    n = Node('offboard_test')
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(n)
    threading.Thread(target=executor.spin, daemon=True).start()
    yield n
    rclpy.shutdown()


@pytest.fixture(scope='module')
def tf_buffer(node):
    buf = tf2_ros.Buffer()
    tf2_ros.TransformListener(buf, node)
    return buf


def _call(node, client, req, timeout=5.0):
    future = client.call_async(req)
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        time.sleep(0.01)
    if not future.done():
        raise Exception('Service %s timed out' % client.srv_name)
    return future.result()


def _wait_for_message(node, msg_type, topic, timeout=5.0):
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


def get_state(node):
    return _wait_for_message(node, State, '/simple_offboard/state', timeout=1)


def get_navigate_target(tf_buffer):
    target = tf_buffer.lookup_transform('map', 'navigate_target', Time(), Duration(seconds=1))
    assert target.child_frame_id == 'navigate_target'
    return target


def test_offboard(node, tf_buffer):
    navigate_client      = node.create_client(srv.Navigate,     'navigate')
    set_position_client  = node.create_client(srv.SetPosition,  'set_position')
    set_altitude_client  = node.create_client(srv.SetAltitude,  'set_altitude')
    set_yaw_client       = node.create_client(srv.SetYaw,       'set_yaw')
    set_yaw_rate_client  = node.create_client(srv.SetYawRate,   'set_yaw_rate')
    set_velocity_client  = node.create_client(srv.SetVelocity,  'set_velocity')
    set_attitude_client  = node.create_client(srv.SetAttitude,  'set_attitude')
    set_rates_client     = node.create_client(srv.SetRates,     'set_rates')
    get_telemetry_client = node.create_client(srv.GetTelemetry, 'get_telemetry')
    land_client          = node.create_client(Trigger,          'land')

    def navigate(**kwargs):
        req = srv.Navigate.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, navigate_client, req)

    def set_position(**kwargs):
        req = srv.SetPosition.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_position_client, req)

    def set_altitude(**kwargs):
        req = srv.SetAltitude.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_altitude_client, req)

    def set_yaw(**kwargs):
        req = srv.SetYaw.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_yaw_client, req)

    def set_yaw_rate(**kwargs):
        req = srv.SetYawRate.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_yaw_rate_client, req)

    def set_velocity(**kwargs):
        req = srv.SetVelocity.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_velocity_client, req)

    def set_attitude(**kwargs):
        req = srv.SetAttitude.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_attitude_client, req)

    def set_rates(**kwargs):
        req = srv.SetRates.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, set_rates_client, req)

    def get_telemetry(**kwargs):
        req = srv.GetTelemetry.Request()
        for k, v in kwargs.items():
            setattr(req, k, v)
        return _call(node, get_telemetry_client, req)

    def land():
        return _call(node, land_client, Trigger.Request())

    res = navigate()
    assert res.success == False
    assert res.message.startswith('State timeout')

    telem = get_telemetry()
    assert telem.connected == False

    # mocked state publisher
    state_pub = node.create_publisher(mavros_msgs.msg.State, '/mavros/state', _latch_qos)
    state_msg = mavros_msgs.msg.State(mode='OFFBOARD', armed=True)

    def publish_state():
        while rclpy.ok():
            state_msg.header.stamp = node.get_clock().now().to_msg()
            state_pub.publish(state_msg)
            time.sleep(0.5)

    threading.Thread(target=publish_state, daemon=True).start()
    time.sleep(0.5)

    # set_mode service mock
    def set_mode_cb(request, response):
        state_msg.mode = request.custom_mode
        response.mode_sent = True
        return response

    node.create_service(SetMode, '/mavros/set_mode', set_mode_cb)

    telem = get_telemetry()
    assert telem.connected == False

    res = navigate()
    assert res.success == False
    assert res.message.startswith('No connection to FCU')

    state_msg.connected = True
    time.sleep(1)

    telem = get_telemetry()
    assert telem.connected == True

    res = navigate()
    assert res.success == False
    assert res.message.startswith('No local position')

    local_position_pub = node.create_publisher(PoseStamped, '/mavros/local_position/pose', _latch_qos)
    local_position_msg = PoseStamped()
    local_position_msg.header.frame_id = 'map'
    local_position_msg.pose.position.x = 1.0
    local_position_msg.pose.position.y = 2.0
    local_position_msg.pose.position.z = 3.0
    local_position_msg.pose.orientation.w = 1.0

    def publish_local_position():
        while rclpy.ok():
            local_position_msg.header.stamp = node.get_clock().now().to_msg()
            local_position_pub.publish(local_position_msg)
            time.sleep(1.0 / 30)

    threading.Thread(target=publish_local_position, daemon=True).start()
    time.sleep(0.5)

    # check body frame
    body = tf_buffer.lookup_transform('map', 'body', Time(), Duration(seconds=1))
    assert body.child_frame_id == 'body'
    assert body.transform.translation.x == approx(1)
    assert body.transform.translation.y == approx(2)
    assert body.transform.translation.z == approx(3)

    res = navigate(x=3, y=2, z=1, frame_id='map')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 3
    assert state.y == 2
    assert state.z == 1
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'map'
    target = get_navigate_target(tf_buffer)
    assert target.header.frame_id == 'map'
    assert target.transform.translation.x == approx(3)
    assert target.transform.translation.y == approx(2)
    assert target.transform.translation.z == approx(1)
    assert target.transform.rotation.x == 0
    assert target.transform.rotation.y == 0
    assert target.transform.rotation.z == 0
    assert target.transform.rotation.w == 1

    # try to set only the y
    res = navigate(x=nan, y=1, z=nan)
    assert res.success == False
    assert res.message.startswith('x and y can be set only together')

    # set z in body frame
    res = navigate(x=nan, y=nan, z=1, frame_id='body')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 3
    assert state.y == 2
    assert state.z == 4
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'map'

    # set xy in test frame
    res = navigate(x=1, y=2, z=nan, frame_id='test')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 1
    assert state.y == 2
    assert state.z == 4
    assert state.yaw == 0
    assert state.xy_frame_id == 'test'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'test'

    # auto_arm should not invalidate the setpoint if not effective
    res = navigate(x=nan, y=nan, z=1, frame_id='map', auto_arm=True)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 1
    assert state.y == 2
    assert state.z == 1
    assert state.yaw == 0
    assert state.xy_frame_id == 'test'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'map'

    # auto_arm should invalidate the setpoint if effective
    state_msg.mode = 'STABILIZED'
    time.sleep(1)
    res = navigate(x=nan, y=nan, z=1, frame_id='map', auto_arm=True)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 1
    assert state.y == 2
    assert state.z == 1
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'map'
    state_msg.mode = 'OFFBOARD'
    time.sleep(1)

    # set_attitude should invalidate the setpoint
    res = set_attitude()
    assert res.success == True

    res = navigate(x=5, y=6, z=nan, yaw=nan, frame_id='map')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 5
    assert state.y == 6
    assert state.z == 3
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'map'

    # test set_altitude
    res = set_altitude(z=7, frame_id='test')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 5
    assert state.y == 6
    assert state.z == 7
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test'
    assert state.yaw_frame_id == 'map'

    # test set_yaw
    res = set_yaw(yaw=0.5, frame_id='test2')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 5
    assert state.y == 6
    assert state.z == 7
    assert state.yaw == 0.5
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test'
    assert state.yaw_frame_id == 'test2'

    # test set_yaw_rate
    res = set_yaw_rate(yaw_rate=2)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW_RATE
    assert state.x == 5
    assert state.y == 6
    assert state.z == 7
    assert state.yaw_rate == 2
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test'

    # navigate(yaw=nan) should keep yaw rate mode
    res = navigate(x=nan, y=nan, z=nan, yaw=nan)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW_RATE
    assert state.x == 5
    assert state.y == 6
    assert state.z == 7
    assert state.yaw_rate == 2
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test'

    # set_yaw(nan) should change back to yaw mode
    res = set_yaw(yaw=nan)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_NAVIGATE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.yaw == 0
    assert state.yaw_frame_id == 'map'

    # test set_position
    res = set_position(x=nan, y=nan, z=13, yaw=nan, frame_id='test2')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_POSITION
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 5
    assert state.y == 6
    assert state.z == 13
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test2'
    assert state.yaw_frame_id == 'map'

    # set_altitude should not change the mode
    res = set_altitude(z=3, frame_id='test')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_POSITION
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 5
    assert state.y == 6
    assert state.z == 3
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test'
    assert state.yaw_frame_id == 'map'

    # set_yaw should not change the main mode
    res = set_yaw(yaw=1, frame_id='test2')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_POSITION
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.x == 5
    assert state.y == 6
    assert state.z == 3
    assert state.yaw == 1
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'test'
    assert state.yaw_frame_id == 'test2'

    # test set_velocity
    res = set_velocity(vx=1, frame_id='body')
    state = get_state(node)
    assert state.mode == State.MODE_VELOCITY
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.vx == 1
    assert state.vy == 0
    assert state.vz == 0
    assert state.yaw == 0
    assert state.xy_frame_id == 'map'
    assert state.z_frame_id == 'map'
    assert state.yaw_frame_id == 'map'

    # set_altitude should not work in velocity mode
    res = set_altitude(z=3, frame_id='test')
    assert res.success == False
    assert res.message.startswith('Altitude cannot be set in')

    # test set_attitude
    res = set_attitude(roll=0.1, pitch=0.2, yaw=0.3, thrust=0.5)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_ATTITUDE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.roll == approx(0.1)
    assert state.pitch == approx(0.2)
    assert state.yaw == approx(0.3)
    assert state.thrust == approx(0.5)
    assert state.yaw_frame_id == 'map'
    msg = _wait_for_message(node, PoseStamped, '/mavros/setpoint_attitude/attitude', timeout=3)
    # Tait-Bryan ZYX angle (rzyx) converted to quaternion
    assert msg.pose.orientation.x == approx(0.0342708)
    assert msg.pose.orientation.y == approx(0.10602051)
    assert msg.pose.orientation.z == approx(0.14357218)
    assert msg.pose.orientation.w == approx(0.98334744)
    msg = _wait_for_message(node, mavros_msgs.msg.Thrust, '/mavros/setpoint_attitude/thrust', timeout=3)
    assert msg.thrust == approx(0.5)

    # set_yaw should work in attitude mode
    res = set_yaw(yaw=0.7, frame_id='test2')
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_ATTITUDE
    assert state.yaw_mode == State.YAW_MODE_YAW
    assert state.roll == approx(0.1)
    assert state.pitch == approx(0.2)
    assert state.yaw == approx(0.7)
    assert state.thrust == approx(0.5)
    assert state.yaw_frame_id == 'test2'

    # set_yaw_rate should not work in attitude mode
    res = set_yaw_rate(yaw_rate=0.3)
    assert res.success == False
    assert res.message.startswith('Yaw rate cannot be set in')

    # test set_rates
    res = set_rates(roll_rate=nan, pitch_rate=nan, yaw_rate=0.3, thrust=0.6)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_RATES
    assert state.yaw_mode == State.YAW_MODE_YAW_RATE
    assert state.roll_rate == approx(0)
    assert state.pitch_rate == approx(0)
    assert state.yaw_rate == approx(0.3)
    assert state.thrust == approx(0.6)
    msg = _wait_for_message(node, mavros_msgs.msg.AttitudeTarget, '/mavros/setpoint_raw/attitude', timeout=3)
    assert msg.thrust == approx(0.6)

    res = set_rates(roll_rate=0.3, pitch_rate=0.2, yaw_rate=0.1, thrust=0.4)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_RATES
    assert state.yaw_mode == State.YAW_MODE_YAW_RATE
    assert state.roll_rate == approx(0.3)
    assert state.pitch_rate == approx(0.2)
    assert state.yaw_rate == approx(0.1)
    assert state.thrust == approx(0.4)

    res = set_rates(roll_rate=nan, pitch_rate=nan, yaw_rate=nan, thrust=0.3)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_RATES
    assert state.yaw_mode == State.YAW_MODE_YAW_RATE
    assert state.roll_rate == approx(0.3)
    assert state.pitch_rate == approx(0.2)
    assert state.yaw_rate == approx(0.1)
    assert state.thrust == approx(0.3)
    msg = _wait_for_message(node, mavros_msgs.msg.AttitudeTarget, '/mavros/setpoint_raw/attitude', timeout=3)
    assert msg.type_mask == mavros_msgs.msg.AttitudeTarget.IGNORE_ATTITUDE
    assert msg.body_rate.x == approx(0.3)
    assert msg.body_rate.y == approx(0.2)
    assert msg.body_rate.z == approx(0.1)

    # set_yaw_rate should work in rates mode
    res = set_yaw_rate(yaw_rate=0.4)
    assert res.success == True
    state = get_state(node)
    assert state.mode == State.MODE_RATES
    assert state.yaw_mode == State.YAW_MODE_YAW_RATE
    assert state.roll_rate == approx(0.3)
    assert state.pitch_rate == approx(0.2)
    assert state.yaw_rate == approx(0.4)
    assert state.thrust == approx(0.3)

    res = set_rates(roll_rate=inf)
    assert res.success == False
    assert res.message == 'roll_rate argument cannot be Inf'

    # test land service
    res = land()
    assert res.success == True
    assert state_msg.mode == 'AUTO.LAND'
