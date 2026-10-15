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

# Information: https://bumblebee.coex.tech/en/laser.html

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Range


class RangefinderNode(Node):
    def __init__(self):
        super().__init__('process_rangefinder')
        self.create_subscription(Range, 'rangefinder/range', self.range_callback, 1)

    def range_callback(self, msg):
        # Process data from the rangefinder
        print('Rangefinder distance:', msg.range)


rclpy.init()
node = RangefinderNode()
rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
