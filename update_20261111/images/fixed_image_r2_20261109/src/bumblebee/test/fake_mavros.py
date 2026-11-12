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
The default remains a fast command fake. faithful=True adds a limited command
model for PX4 1.16.1 / MAVROS 2.14: heartbeat-only reports, mode/ARM denials,
offboard loss, optional descent and auto-disarm. It is not a dynamics simulator.
Pure ROS topics and services: no MAVLink, no FCU, nothing reaches a motor.
"""

import threading
import time
import math

from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import AttitudeTarget, PositionTarget, State, Thrust, StatusText
from mavros_msgs.srv import CommandBool, SetMode
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
from rclpy.duration import Duration
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

from test_safety import TEST_NS, topic as test_topic, guard_graph
from fake_px4_model import Px4Model

# Names as simple_offboard sees them on the drone (remaps of bumblebee.launch.py)
STATE = test_topic('/mavros/state')
POSE = test_topic('/mavros/mavros/pose')
SET_MODE = test_topic('/mavros/set_mode')
ARMING = test_topic('/mavros/mavros/arming')
SETPOINT_POSITION = test_topic('/mavros/mavros/local')
# Setpoint topics of the disabled velocity/attitude/rates paths
OTHER_SETPOINTS = {
    test_topic('/mavros/setpoint_raw/local'): PositionTarget,
    test_topic('/mavros/setpoint_raw/attitude'): AttitudeTarget,
    test_topic('/mavros/setpoint_attitude/attitude'): PoseStamped,
    test_topic('/mavros/mavros/cmd_vel'): TwistStamped,
    test_topic('/mavros/mavros/thrust'): Thrust,
}
# Legacy fast-fake stream threshold. The faithful model uses configurable
# COM_OF_LOSS_T and accepts OFFBOARD while disarmed without a stream.
OFFBOARD_SIGNAL_TIMEOUT = 0.5

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)


class FakeMavros(Node):
    """Fake FCU state + MAVROS services; all fields are guarded by self.lock."""

    def __init__(self, state_period=None, parameter_overrides=None,
                 faithful=False, heartbeat_only=None, **state):
        """state_period: State publish period on the node clock (MAVROS: 1 s heartbeat).
        parameter_overrides: e.g. use_sim_time. state: the first published state."""
        guard_graph()
        super().__init__('fake_mavros', namespace=TEST_NS, parameter_overrides=parameter_overrides or [],
                         cli_args=['--ros-args','-r','/tf:='+test_topic('/tf'),'-r','/tf_static:='+test_topic('/tf_static'),'-r','/clock:='+test_topic('/clock')])
        self.lock = threading.Lock()
        self.faithful = faithful
        self.heartbeat_only = faithful if heartbeat_only is None else heartbeat_only
        self._px4 = None
        self._report_arm_hidden = False
        self.state_pub = self.create_publisher(State, STATE, LATCHED)
        self.pose_pub = self.create_publisher(PoseStamped, POSE, 10)
        self.velocity_pub = self.create_publisher(TwistStamped, test_topic('/mavros/local_position/velocity_body'), 10)
        self.statustext_pub = self.create_publisher(StatusText, test_topic('/mavros/statustext/recv'), 10)
        self.tf_pub = TransformBroadcaster(self)
        self.command_group = MutuallyExclusiveCallbackGroup()
        self.create_service(SetMode, SET_MODE, self._set_mode, callback_group=self.command_group)
        self.create_service(CommandBool, ARMING, self._arming, callback_group=self.command_group)
        self.create_subscription(PoseStamped, SETPOINT_POSITION, self._setpoint, 100)
        for topic, msg_type in OTHER_SETPOINTS.items():
            self.create_subscription(msg_type, topic,
                                     lambda msg, topic=topic: self._other_setpoint(topic), 100)
        self._arm_timer = None
        self.reset(**state)
        # MAVROS State follows heartbeats. Only the legacy fast fake also emits
        # immediate reports on changes; faithful tests default to exactly 1 Hz.
        if state_period is None:
            state_period = 1.0 if faithful else 0.2
        self.create_timer(state_period, self._heartbeat)
        self.create_timer(1 / 30, self._publish_pose)

    def reset(self, **state):
        """Back to a connected, disarmed vehicle in POSCTL; clear all records."""
        with self.lock:
            if self._arm_timer:
                self._arm_timer.cancel()
            self._arm_timer = None
            self.connected = True
            self.armed = False
            self.true_armed = False
            self.true_mode = 'POSCTL'
            self.intended_mode = 'POSCTL'
            self._report_arm_hidden = False
            self.publish_fcu_tf = True
            self.ack_delay = 0.0
            self.ack_timeout = 5.0
            self.deny_disarm = False
            self.mode_reply_delay = 0.0
            self.mode_drop = False
            self.mode = 'POSCTL'
            self.state_age = 0.0     # backdate state stamps by this (stale = unknown state)
            self.publish_states = True   # False: no State at all (heartbeats lost)
            self.pose = (0.0, 0.0, 0.0)
            self.arming = 'ok'       # 'late' delays the report, not execution of ARM
            self.arm_delay = 1.0
            self.accept_offboard = True
            self.last_setpoint = -math.inf
            self.dynamics = False
            self.floor_z = 0.0
            self.of_loss_t = 1.0
            self.obl_rc_act = 0
            self.resume_offboard = False
            self.preflight_disarm_s = 30.0
            self.land_disarm_s = 2.0
            self.land_speed = 0.5
            self.statustext = []
            self.command_events = []
            self._px4 = Px4Model(now=time.monotonic()) if self.faithful else None
            self.clear()
        self.set_state(**state)

    def clear(self):
        """Forget recorded setpoints and requests (caller may hold self.lock)."""
        self.setpoints = []          # (monotonic receive time, x, y, z, header stamp ns)
        self.other_setpoints = []    # topics of disabled-path setpoints received
        self.mode_requests = []
        self.arming_requests = []
        self.state_publications = []

    def set_state(self, **state):
        with self.lock:
            reported_mode, reported_armed = self.mode, self.armed
            for key, value in state.items():
                if not hasattr(self, key):
                    raise AttributeError(key)
                setattr(self, key, value)
                if key == 'armed': self.true_armed = value
            if self._px4:
                m = self._px4
                for key in ('connected', 'pose', 'floor_z', 'dynamics', 'of_loss_t',
                            'obl_rc_act', 'resume_offboard', 'preflight_disarm_s',
                            'land_disarm_s', 'land_speed', 'last_setpoint'):
                    setattr(m, key, getattr(self, key))
                if 'pose' in state:
                    m.target = tuple(state['pose'])
                if 'mode' in state:
                    m.pilot_mode(time.monotonic(), state['mode'])
                if 'armed' in state:
                    m.armed = state['armed']
                    m.arm_time = time.monotonic() if m.armed else None
                    m.ever_airborne = m.armed and m.pose[2] > m.floor_z + 0.1
                self._model_snapshot_locked()
                if self.heartbeat_only:
                    self.mode, self.armed = reported_mode, reported_armed
        self.publish_state()

    def snapshot(self, name):
        with self.lock:
            value = getattr(self, name)
            return list(value) if isinstance(value, list) else value

    def _model_snapshot_locked(self):
        m = self._px4
        self.true_armed, self.true_mode = m.armed, m.mode
        self.intended_mode, self.pose = m.intended_mode, m.pose
        self.command_events = list(m.events)

    def _heartbeat(self):
        if self._px4:
            with self.lock:
                self._px4.connected = self.connected
                self._px4.tick(time.monotonic())
                self._model_snapshot_locked()
                _, armed, mode = self._px4.heartbeat()
                self.armed = False if self._report_arm_hidden else armed
                self.mode = mode
        self.publish_state(heartbeat=True)

    def publish_state(self, heartbeat=False):
        if self.heartbeat_only and not heartbeat:
            return
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
            self.state_publications.append((time.monotonic(), msg.connected,
                                            msg.armed, msg.mode))
        self.state_pub.publish(msg)

    def _publish_pose(self):
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        with self.lock:
            if self._px4:
                self._px4.tick(time.monotonic())
                self._model_snapshot_locked()
            msg.pose.position.x, msg.pose.position.y, msg.pose.position.z = self.pose
            vz = self._px4.vz if self._px4 else 0.0
        msg.pose.orientation.w = 1.0
        self.pose_pub.publish(msg)
        if self.publish_fcu_tf:
            transform = TransformStamped()
            transform.header = msg.header
            transform.child_frame_id = 'base_link'
            transform.transform.translation.x = msg.pose.position.x
            transform.transform.translation.y = msg.pose.position.y
            transform.transform.translation.z = msg.pose.position.z
            transform.transform.rotation = msg.pose.orientation
            self.tf_pub.sendTransform(transform)
        if self.faithful:
            velocity = TwistStamped()
            velocity.header.stamp = msg.header.stamp
            velocity.header.frame_id = 'base_link'
            velocity.twist.linear.z = vz
            self.velocity_pub.publish(velocity)

    def _setpoint(self, msg):
        stamp_ns = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        p = msg.pose.position
        with self.lock:
            self.last_setpoint = time.monotonic()
            self.setpoints.append((self.last_setpoint, p.x, p.y, p.z, stamp_ns))
            if self._px4:
                self._px4.setpoint(self.last_setpoint, (p.x, p.y, p.z))
                self._model_snapshot_locked()

    def _other_setpoint(self, topic):
        with self.lock:
            self.other_setpoints.append(topic)

    def _set_mode(self, request, response):
        with self.lock:
            mode = request.custom_mode
            self.mode_requests.append(mode)
            streaming = time.monotonic() - self.last_setpoint < OFFBOARD_SIGNAL_TIMEOUT
            if self._px4:
                self._px4.command_mode(time.monotonic(), mode, self.accept_offboard)
                self._model_snapshot_locked()
            elif mode != 'OFFBOARD' or (self.accept_offboard and streaming):
                self.mode = mode
        self._publish_denials()
        if self.mode_reply_delay: time.sleep(self.mode_reply_delay)
        response.mode_sent = not self.mode_drop    # MAVROS: sent; PX4 may still refuse
        self.publish_state()
        return response

    def _arming(self, request, response):
        with self.lock:
            self.arming_requests.append(request.value)
            if self._px4:
                accepted = self._px4.command_arm(time.monotonic(), request.value,
                    deny_disarm=self.deny_disarm, deny_arm=self.arming == 'never')
                if request.value and accepted:
                    self._report_arm_hidden = self.arming in ('late', 'accept_no_report')
                    if self.arming == 'late' and not self._arm_timer:
                        self._arm_timer = threading.Timer(self.arm_delay, self._arm_late)
                        self._arm_timer.start()
                elif not request.value and accepted:
                    self._report_arm_hidden = False
                    if self._arm_timer: self._arm_timer.cancel()
                    self._arm_timer = None
                self._model_snapshot_locked()
            elif not request.value:
                accepted = not self.deny_disarm and self.pose[2] <= 0.1
                if accepted:
                    self.true_armed = False
                    self.armed = False
                    if self._arm_timer: self._arm_timer.cancel()
                    self._arm_timer = None
            elif self.arming in ('ok', 'late', 'noack', 'accept_no_report'):
                self.true_armed = True
                accepted = True
                if self.arming in ('late', 'accept_no_report'):
                    self.armed = False
                    if self.arming == 'late' and not self._arm_timer:
                        self._arm_timer = threading.Timer(self.arm_delay, self._arm_late)
                        self._arm_timer.start()
                else:
                    self.armed = True
            else:
                accepted = False
            noack = request.value and self.arming == 'noack'
            delay = self.ack_timeout if noack else self.ack_delay
        self._publish_denials()
        self.publish_state()
        if delay: time.sleep(delay)
        response.success = False if noack else accepted
        response.result = 0 if (noack or accepted) else 1
        return response

    def _arm_late(self):
        with self.lock:
            if self._px4:
                self._report_arm_hidden = False
            else:
                self.armed = self.true_armed
            self._arm_timer = None
        self.publish_state()

    def _publish_denials(self):
        pending = []
        with self.lock:
            if self._px4:
                pending = self._px4.statustext[len(self.statustext):]
                self.statustext.extend(pending)
        for _, text in pending:
            msg = StatusText()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.severity = 4
            msg.text = text
            self.statustext_pub.publish(msg)

    def destroy_node(self):
        # A delayed report may otherwise survive the test's ROS context teardown.
        with self.lock:
            if self._arm_timer:
                self._arm_timer.cancel()
                self._arm_timer = None
        return super().destroy_node()
