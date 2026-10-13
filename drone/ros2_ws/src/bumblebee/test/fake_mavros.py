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

"""Fake MAVROS + PX4 for the simple_offboard launch test.

Publishes what simple_offboard reads from MAVROS (state, local pose), offers the
set_mode and arming services and records every setpoint simple_offboard sends.
It models only the PX4 behaviour the safety tests need: OFFBOARD is accepted only
while setpoints stream, and arming can be made to succeed, fail, or succeed late.
Pure ROS topics and services: no MAVLink, no FCU, nothing reaches a motor.
"""

import threading
import time

from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import AttitudeTarget, PositionTarget, State, Thrust
from mavros_msgs.srv import CommandBool, SetMode
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

# Names as simple_offboard sees them on the drone (remaps of bumblebee.launch.py)
STATE = '/mavros/state'
POSE = '/mavros/mavros/pose'
SET_MODE = '/mavros/set_mode'
ARMING = '/mavros/mavros/arming'
SETPOINT_POSITION = '/mavros/mavros/local'
# Setpoint topics of the disabled velocity/attitude/rates paths
OTHER_SETPOINTS = {
    '/mavros/setpoint_raw/local': PositionTarget,
    '/mavros/setpoint_raw/attitude': AttitudeTarget,
    '/mavros/setpoint_attitude/attitude': PoseStamped,
    '/mavros/mavros/cmd_vel': TwistStamped,
    '/mavros/mavros/thrust': Thrust,
}
# PX4 refuses OFFBOARD unless setpoints arrived this recently
OFFBOARD_SIGNAL_TIMEOUT = 0.5

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)


class FakeMavros(Node):
    """Fake FCU state + MAVROS services; all fields are guarded by self.lock."""

    def __init__(self, state_period=0.2, parameter_overrides=None, **state):
        """state_period: State publish period on the node clock (MAVROS: 1 s heartbeat).
        parameter_overrides: e.g. use_sim_time. state: the first published state."""
        super().__init__('fake_mavros', parameter_overrides=parameter_overrides or [])
        self.lock = threading.Lock()
        self.state_pub = self.create_publisher(State, STATE, LATCHED)
        self.pose_pub = self.create_publisher(PoseStamped, POSE, 10)
        self.create_service(SetMode, SET_MODE, self._set_mode)
        self.create_service(CommandBool, ARMING, self._arming)
        self.create_subscription(PoseStamped, SETPOINT_POSITION, self._setpoint, 100)
        for topic, msg_type in OTHER_SETPOINTS.items():
            self.create_subscription(msg_type, topic,
                                     lambda msg, topic=topic: self._other_setpoint(topic), 100)
        self._arm_timer = None
        self.reset(**state)
        # MAVROS publishes state on every heartbeat (1 Hz) and on change; 5 Hz by default
        self.create_timer(state_period, self.publish_state)
        self.create_timer(1 / 30, self._publish_pose)

    def reset(self, **state):
        """Back to a connected, disarmed vehicle in POSCTL; clear all records."""
        with self.lock:
            if self._arm_timer:
                self._arm_timer.cancel()
            self._arm_timer = None
            self.connected = True
            self.armed = False
            self.mode = 'POSCTL'
            self.state_age = 0.0     # backdate state stamps by this (stale = unknown state)
            self.publish_states = True   # False: no State at all (heartbeats lost)
            self.pose = (0.0, 0.0, 0.0)
            self.arming = 'ok'       # 'ok', 'never' (PX4 rejects) or 'late' (arms after arm_delay)
            self.arm_delay = 1.0
            self.accept_offboard = True
            self.last_setpoint = 0.0
            self.clear()
        self.set_state(**state)

    def clear(self):
        """Forget recorded setpoints and requests (caller may hold self.lock)."""
        self.setpoints = []          # (monotonic receive time, x, y, z, header stamp ns)
        self.other_setpoints = []    # topics of disabled-path setpoints received
        self.mode_requests = []
        self.arming_requests = []

    def set_state(self, **state):
        with self.lock:
            for key, value in state.items():
                if not hasattr(self, key):
                    raise AttributeError(key)
                setattr(self, key, value)
        self.publish_state()

    def snapshot(self, name):
        with self.lock:
            value = getattr(self, name)
            return list(value) if isinstance(value, list) else value

    def publish_state(self):
        msg = State()
        with self.lock:
            if not self.publish_states:
                return
            stamp = self.get_clock().now() - Duration(seconds=self.state_age)
            msg.header.stamp = stamp.to_msg()
            msg.connected = self.connected
            msg.armed = self.armed
            msg.guided = True
            msg.mode = self.mode
            msg.system_status = 4 if self.armed else 3  # MAV_STATE_ACTIVE / STANDBY
        self.state_pub.publish(msg)

    def _publish_pose(self):
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        with self.lock:
            msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = self.pose
        msg.pose.orientation.w = 1.0
        self.pose_pub.publish(msg)

    def _setpoint(self, msg):
        stamp_ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        p = msg.pose.position
        with self.lock:
            self.last_setpoint = time.monotonic()
            self.setpoints.append((self.last_setpoint, p.x, p.y, p.z, stamp_ns))

    def _other_setpoint(self, topic):
        with self.lock:
            self.other_setpoints.append(topic)

    def _set_mode(self, request, response):
        with self.lock:
            mode = request.custom_mode
            self.mode_requests.append(mode)
            streaming = time.monotonic() - self.last_setpoint < OFFBOARD_SIGNAL_TIMEOUT
            if mode != 'OFFBOARD' or (self.accept_offboard and streaming):
                self.mode = mode
        response.mode_sent = True    # MAVROS: sent; PX4 may still refuse
        self.publish_state()
        return response

    def _arming(self, request, response):
        with self.lock:
            self.arming_requests.append(request.value)
            if not request.value:
                self.armed = False
                accepted = True
            elif self.arming == 'ok':
                self.armed = True
                accepted = True
            elif self.arming == 'late':
                # ACK now, the armed state arrives arm_delay later
                accepted = True
                if not self._arm_timer:
                    self._arm_timer = threading.Timer(self.arm_delay, self._arm_late)
                    self._arm_timer.start()
            else:
                accepted = False
        response.success = accepted
        response.result = 0 if accepted else 1   # MAV_RESULT_ACCEPTED / TEMPORARILY_REJECTED
        self.publish_state()
        return response

    def _arm_late(self):
        with self.lock:
            self.armed = True
            self._arm_timer = None
        self.publish_state()
