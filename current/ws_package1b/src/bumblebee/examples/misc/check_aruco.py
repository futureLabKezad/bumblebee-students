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

import rclpy
from rclpy.node import Node
from aruco_pose.msg import MarkerArray


class ArucoWatcher(Node):
    def __init__(self):
        super().__init__('check_aruco')
        self.last_ids = []
        self.create_subscription(MarkerArray, '/aruco_detect/markers', self.cb, 1)

    def cb(self, msg):
        ids = [m.id for m in msg.markers]
        if ids != self.last_ids:
            if ids:
                print('Markers VISIBLE:', ids)
            else:
                print('No markers in frame')
            self.last_ids = ids


rclpy.init()
node = ArucoWatcher()
print('Watching camera... point it at ArUco markers')
print('Press Ctrl+C to stop')
rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
