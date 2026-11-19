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
camera_fix.py — fixes YUYV images from v4l2_camera + libcamerify on RPi5 PiSP.

Problem: PiSP ISP writes YUYV output with a 5-row tile pattern:
  - Row N (N % 5 == 0): all columns valid YUYV data
  - Rows N+1..N+4: one 160-pixel tile-column is zeros (rotating pattern)
v4l2_camera reads the buffer with wrong stride assumption, producing green
scan lines.

Fast-path (Block A, 2026-06-17): extract Y plane only from every 5th row,
upscale by row-repeat (np.repeat) and publish mono8. ArUco detector pulls
gray anyway, so dropping the YUV→BGR→resize→RGB chain raises throughput
from ~8.6 Hz to ≥22 Hz on the Pi5 ISP.

Subscribe to: <camera>/image_raw_yuv  (yuv422_yuy2)
Publish to:   <camera>/image_raw      (mono8)
"""

import os
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy, qos_profile_sensor_data
from sensor_msgs.msg import Image, CameraInfo
import numpy as np
import cv2

WATCHDOG_SEC = 10.0  # exit (for launch respawn) if no frames for 2x this long
BOOT_GRACE_SEC = 20.0  # extra slack at startup while v4l2_camera comes up


class CameraFix(Node):
    def __init__(self):
        super().__init__('camera_fix')
        self.declare_parameter('input_topic', 'image_raw_yuv')
        self.declare_parameter('output_topic', 'image_raw')
        self.declare_parameter('row_period', 5)  # every Nth row is valid

        self.in_topic = self.get_parameter('input_topic').value
        self.out_topic = self.get_parameter('output_topic').value
        self.period = self.get_parameter('row_period').value

        self.sub_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )
        # Publish RELIABLE so image_transport CameraSubscriber (RELIABLE sub) can receive
        self.pub = self.create_publisher(Image, self.out_topic, 10)

        # Republish camera_info with same timestamp for image_transport sync
        # Subscribe to 'camera_info_raw' (v4l2 output), publish to 'camera_info' (for aruco/optical_flow)
        self.info_pub = self.create_publisher(CameraInfo, 'camera_info', 10)
        self.last_info = None
        self.create_subscription(CameraInfo, 'camera_info_raw', self._info_cb,
                                 QoSProfile(reliability=QoSReliabilityPolicy.BEST_EFFORT,
                                            history=QoSHistoryPolicy.KEEP_LAST, depth=1))

        # Create the image subscription ONCE. Destroying/recreating a
        # subscription from inside a timer callback while the executor spins
        # corrupts the rclpy wait-set: the new subscription matches the
        # publisher but its callback is never serviced (observed 2026-06-10,
        # camera dead for a whole boot). Never recreate in-process.
        self.sub = self.create_subscription(
            Image, self.in_topic, self.cb, self.sub_qos)
        self.last_frame = time.monotonic() + BOOT_GRACE_SEC
        self._watchdog_trips = 0

        self.create_timer(WATCHDOG_SEC, self._watchdog)

        self.get_logger().info(
            f'camera_fix: {self.in_topic} -> {self.out_topic} (period={self.period})')

    def _info_cb(self, msg):
        self.last_info = msg

    def _watchdog(self):
        if time.monotonic() - self.last_frame <= WATCHDOG_SEC:
            self._watchdog_trips = 0
            return
        self._watchdog_trips += 1
        if self._watchdog_trips == 1:
            self.get_logger().warn('No frames received for %.0fs' % WATCHDOG_SEC)
            return
        # A clean process restart reliably re-matches discovery; the launch
        # file runs this node with respawn=True.
        self.get_logger().error(
            'No frames for %.0fs — exiting so launch respawns a clean process'
            % (self._watchdog_trips * WATCHDOG_SEC))
        os._exit(1)

    def cb(self, msg):
        self.last_frame = time.monotonic()

        if msg.encoding != 'yuv422_yuy2':
            self.get_logger().warn(
                f'Expected yuv422_yuy2, got {msg.encoding}', throttle_duration_sec=5)
            return

        raw = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        H, W, step = msg.height, msg.width, msg.step

        try:
            rows = raw.reshape(H, step)
            valid = rows[0::self.period]          # (H/period, step)
            yuyv = valid.reshape(-1, W, 2)        # 2-channel YUYV
            # Y plane only (channel 0 of YUYV). Skip YUV→BGR→resize→RGB entirely:
            # ArUco detector consumes gray anyway, so colour is dead weight.
            y_small = yuyv[..., 0]                # (H/period, W) uint8
            # Row-repeat upscale ×period — same effect as INTER_NEAREST ×period
            # but ~10× cheaper (single O(N) numpy stride trick vs cv2 resize).
            gray = np.repeat(y_small, self.period, axis=0)
            if gray.shape[0] != H:
                gray = gray[:H, :]                # safety crop for non-divisible H
            gray = np.ascontiguousarray(gray)
        except Exception as e:
            self.get_logger().error(f'camera_fix error: {e}', throttle_duration_sec=2)
            return

        out = Image()
        out.header = msg.header
        out.height = H
        out.width = W
        out.encoding = 'mono8'
        out.step = W
        out.data = gray.tobytes()
        self.pub.publish(out)

        # Republish camera_info with matching timestamp for image_transport sync
        if self.last_info is not None:
            info = CameraInfo()
            info = self.last_info
            info.header.stamp = msg.header.stamp
            info.header.frame_id = msg.header.frame_id
            self.info_pub.publish(info)


def main(args=None):
    rclpy.init(args=args)
    node = CameraFix()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
