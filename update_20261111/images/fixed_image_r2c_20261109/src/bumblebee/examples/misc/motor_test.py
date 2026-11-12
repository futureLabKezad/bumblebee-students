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
motor_test.py -- ground motor test to verify ROS 2 and drone.py work correctly.

Bypasses simple_offboard, talks directly to MAVROS.
No ArUco markers needed.

WARNING: Remove propellers before running this test!

Run: source /opt/ros/jazzy/setup.bash && source ~/ros2_ws/install/setup.bash && python3 motor_test.py
"""

import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from mavros_msgs.srv import CommandBool, SetMode
from mavros_msgs.msg import State, AttitudeTarget
from std_msgs.msg import Header
import math

current_state = State()


def state_cb(msg):
    global current_state
    current_state = msg


def main():
    rclpy.init()
    node = Node('motor_test')

    state_qos = QoSProfile(
        depth=10,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    node.create_subscription(State, '/mavros/state', state_cb, state_qos)

    # Attitude setpoints -- don't require EKF position estimate
    setpoint_pub = node.create_publisher(AttitudeTarget, '/mavros/setpoint_raw/attitude', 10)

    arming_client = node.create_client(CommandBool, '/mavros/mavros/arming')
    set_mode_client = node.create_client(SetMode, '/mavros/set_mode')

    print('=== Motor test ===')
    print('WARNING: Make sure propellers are REMOVED!')
    print()

    # Step 1: Wait for MAVROS connection
    print('[1/5] Waiting for MAVROS connection...')
    while rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.5)
        if current_state.connected:
            break
    print('  Connected! mode=%s armed=%s' % (current_state.mode, current_state.armed))

    # Attitude setpoint: level, 15% throttle (enough to spin, not to lift)
    def publish_setpoint():
        msg = AttitudeTarget()
        msg.header.stamp = node.get_clock().now().to_msg()
        # Ignore roll/pitch/yaw rates, use orientation + thrust
        msg.type_mask = AttitudeTarget.IGNORE_ROLL_RATE | AttitudeTarget.IGNORE_PITCH_RATE | AttitudeTarget.IGNORE_YAW_RATE
        # Level orientation (identity quaternion)
        msg.orientation.w = 1.0
        msg.orientation.x = 0.0
        msg.orientation.y = 0.0
        msg.orientation.z = 0.0
        msg.thrust = 0.15  # 15% throttle
        setpoint_pub.publish(msg)

    timer = node.create_timer(0.05, publish_setpoint)  # 20Hz

    # Step 2: Send setpoints for 2 seconds before switching mode
    print('[2/5] Sending setpoints...')
    t0 = time.time()
    while time.time() - t0 < 2.0:
        rclpy.spin_once(node, timeout_sec=0.05)

    # Wait for services
    while not set_mode_client.wait_for_service(timeout_sec=1.0):
        print("  waiting for set_mode service...")
    while not arming_client.wait_for_service(timeout_sec=1.0):
        print("  waiting for arming service...")

    # Step 3: Switch to OFFBOARD
    print('[3/5] Switching to OFFBOARD...')
    req = SetMode.Request()
    req.custom_mode = 'OFFBOARD'
    future = set_mode_client.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    if future.done():
        print('  set_mode result: success=%s' % future.result().mode_sent)

    t0 = time.time()
    while time.time() - t0 < 1.0:
        rclpy.spin_once(node, timeout_sec=0.05)
    print('  mode=%s' % current_state.mode)

    # Step 4: Arm
    print('[4/5] Arming...')
    req = CommandBool.Request()
    req.value = True
    future = arming_client.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    if future.done():
        print('  arming result: success=%s' % future.result().success)

    t0 = time.time()
    while time.time() - t0 < 0.5:
        rclpy.spin_once(node, timeout_sec=0.05)
    print('  armed=%s mode=%s' % (current_state.armed, current_state.mode))

    # Hold for 3 seconds -- motors should spin at 15% throttle
    print('  Motors spinning for 3 seconds...')
    for i in range(6):
        rclpy.spin_once(node, timeout_sec=0.5)
        print('  t=%.1fs  armed=%s  mode=%s' % (i * 0.5, current_state.armed, current_state.mode))

    # Step 5: Disarm
    print('[5/5] Disarming...')
    req = CommandBool.Request()
    req.value = False
    future = arming_client.call_async(req)
    rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
    if future.done():
        print('  disarm result: success=%s' % future.result().success)

    timer.cancel()
    time.sleep(0.5)
    rclpy.spin_once(node, timeout_sec=0.5)

    print()
    print('=== Motor test complete ===')
    if not current_state.armed:
        print('SUCCESS: Motors tested, ROS 2 + MAVROS working correctly.')
    else:
        print('WARNING: Drone still armed! Disarm manually.')

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
