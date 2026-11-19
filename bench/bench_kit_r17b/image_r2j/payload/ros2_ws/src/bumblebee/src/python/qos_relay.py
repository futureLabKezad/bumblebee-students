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
qos_relay.py -- Re-publishes BEST_EFFORT MAVROS topics as RELIABLE for rosbridge.

MAVROS sensor topics use BEST_EFFORT QoS. rosbridge subscribes with RELIABLE,
causing QoS incompatibility and no data flowing to the GCS dashboard.
This node bridges the gap.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped, TwistStamped
from sensor_msgs.msg import Imu

SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

TOPICS = [
    ('/mavros/mavros/pose',           PoseStamped,  '/mavros/mavros/pose_reliable'),
    ('/mavros/mavros/velocity_local', TwistStamped, '/mavros/mavros/velocity_local_reliable'),
    ('/mavros/mavros/data',           Imu,          '/mavros/mavros/data_reliable'),
]


class QosRelay(Node):
    def __init__(self):
        super().__init__('qos_relay')
        self._pubs = []
        for src, msg_type, dst in TOPICS:
            pub = self.create_publisher(msg_type, dst, RELIABLE_QOS)
            self._pubs.append(pub)
            self.create_subscription(
                msg_type, src,
                lambda msg, p=pub: p.publish(msg),
                SENSOR_QOS,
            )
        self.get_logger().info('QoS relay started for %d topics' % len(TOPICS))


def main():
    rclpy.init()
    node = QosRelay()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
