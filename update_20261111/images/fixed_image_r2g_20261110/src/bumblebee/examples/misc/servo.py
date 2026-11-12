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
servo.py -- RC channel 9 controls servo up/down.
  Button pressed  (CH9 > 1500 us, ~1900 us) -> servo UP   (255)
  Button released (CH9 < 1500 us, ~1100 us) -> servo DOWN (0)

Note: MAVROS 2.x publishes RC on /mavros/mavros/in (not /mavros/rc/in)
"""
import sys
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

import rclpy
from rclpy.node import Node
from mavros_msgs.msg import RCIn

CH9_IDX    = 8    # channel 9 is index 8 (0-based)
THRESHOLD  = 1500 # us midpoint
SERVO_UP   = 255
SERVO_DOWN = 0
SERVO_CENTER = 128


class ServoRC(Node):
    def __init__(self):
        super().__init__('servo_rc')
        self._last = None
        self.sub = self.create_subscription(
            RCIn, '/mavros/mavros/in', self._cb, 10)
        self.get_logger().info(
            'ServoRC ready -- CH9 button: pressed=UP(255), released=DOWN(0)')

    def _cb(self, msg):
        if len(msg.channels) <= CH9_IDX:
            return
        ch9 = msg.channels[CH9_IDX]
        pressed = ch9 > THRESHOLD
        state = 'up' if pressed else 'down'
        if state == self._last:
            return
        angle = SERVO_UP if pressed else SERVO_DOWN
        drone.set_servo_angle(angle)
        self.get_logger().info(
            f'Servo: {state} (CH9={ch9}us, angle={angle})')
        self._last = state


def main():
    rclpy.init()
    node = ServoRC()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        drone.set_servo_angle(SERVO_CENTER)
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
