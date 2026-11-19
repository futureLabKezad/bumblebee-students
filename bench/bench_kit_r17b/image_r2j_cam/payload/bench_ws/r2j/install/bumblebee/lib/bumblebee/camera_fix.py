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

Full-row read (2026-10-28, camera_fullrow_01): the "5-row tile pattern" is a
line-pitch mismatch. The ISP writes each sensor row with a pitch of
source_pitch bytes (1600 for 640 px YUYV: 1280 image bytes + 320 zero bytes),
but the message has step = 2 * width (1280) and height * step bytes. Output
row 5k is sensor row 4k (5 * 1280 == 4 * 1600); rows in between straddle two
sensor rows and the zero padding (the rotating 160-px zero band). The legacy
path therefore keeps 1 of every 4 sensor rows. The full-row path reads every
sensor row at its true pitch and resamples it onto the SAME output geometry as
the legacy path (output row o <- sensor row (o - (period-1)/2) * 2W/pitch,
linear), so the existing calibration (K, D) stays valid. It runs only when the
buffer matches that layout (size, pitch/period, all padding bytes zero);
otherwise the legacy path runs unchanged. full_rows:=false forces legacy.

Subscribe to: <camera>/image_raw_yuv  (yuv422_yuy2)
Publish to:   <camera>/image_raw      (mono8)
"""

import math
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
STATS_SEC = 30.0  # one stats line (full-row / legacy frame counts) per period


def full_row_layout(raw, height, width, step, pitch, period):
    """(n_rows, '') if raw holds sensor rows at `pitch` with zero padding, else (0, reason).

    raw: 1-D uint8 message data. n_rows = complete sensor rows in raw.
    """
    w2 = 2 * width
    if step <= 0 or raw.size != height * step:
        return 0, 'size %d != height %d * step %d' % (raw.size, height, step)
    # The legacy every-Nth-row path is exact only for this pitch; the
    # calibration was made on its output, so the geometry must match it.
    if not (pitch > w2 and pitch * (period - 1) == period * w2):
        return 0, 'pitch %d does not match row_period %d at width %d' % (pitch, period, width)
    n_rows = (raw.size - w2) // pitch + 1
    s_max = (height - 1 - (period - 1) / 2.0) * (period - 1) / period
    if math.ceil(s_max) > n_rows - 1:
        return 0, 'only %d sensor rows for %d output rows' % (n_rows, height)
    n_pad = raw.size // pitch
    pad = np.lib.stride_tricks.as_strided(
        raw[w2:], shape=(n_pad, pitch - w2), strides=(pitch, 1), writeable=False)
    if pad.any():
        return 0, 'padding bytes are not zero (not the padded PiSP layout)'
    return n_rows, ''


def sensor_rows(raw, width, pitch, n_rows):
    """(n_rows, 2*width) view of the YUYV bytes of every sensor row (no copy)."""
    return np.lib.stride_tricks.as_strided(
        raw, shape=(n_rows, 2 * width), strides=(pitch, 1), writeable=False)


def full_row_plan(height, width, pitch, period, n_rows):
    """Output row o <- sensor row s = (o - (period-1)/2) * 2W/pitch (linear), clamped to the rows present.

    Exact integer arithmetic: s = num / den. Rows are grouped by their weight (5 groups for 640 px / 1600 B):
    [(output_rows, sensor_row_a, sensor_row_b, weight_b)].
    """
    o = np.arange(height, dtype=np.int64)
    num = (2 * o - (period - 1)) * (2 * width)
    den = 2 * pitch
    num = np.clip(num, 0, (n_rows - 1) * den)
    i0 = num // den
    rem = num % den
    i1 = np.minimum(i0 + 1, n_rows - 1)
    plan = []
    for r in np.unique(rem):
        rows = np.nonzero(rem == r)[0]
        plan.append((rows, i0[rows], i1[rows], float(r) / den))
    return plan


def full_row_gray(raw, height, width, pitch, n_rows, plan):
    """mono8 (height, width) image from every sensor row, in the legacy output geometry."""
    y = np.ascontiguousarray(sensor_rows(raw, width, pitch, n_rows)[:, 0::2])   # Y of every sensor row
    out = np.empty((height, width), np.uint8)
    for rows, a, b, w in plan:
        out[rows] = y[a] if w == 0.0 else cv2.addWeighted(y[a], 1.0 - w, y[b], w, 0.0)
    return out


class CameraFix(Node):
    def __init__(self):
        super().__init__('camera_fix')
        self.declare_parameter('input_topic', 'image_raw_yuv')
        self.declare_parameter('output_topic', 'image_raw')
        self.declare_parameter('row_period', 5)  # every Nth row is valid
        self.declare_parameter('full_rows', True)  # read every sensor row (see module doc)
        self.declare_parameter('source_pitch', 1600)  # bytes per sensor row as the ISP writes it

        self.in_topic = self.get_parameter('input_topic').value
        self.out_topic = self.get_parameter('output_topic').value
        self.period = self.get_parameter('row_period').value
        self.full_rows = bool(self.get_parameter('full_rows').value)
        self.source_pitch = int(self.get_parameter('source_pitch').value)
        self._fr_key = None
        self._fr_plan = None
        self._n_full = 0
        self._n_legacy = 0

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
        self.create_timer(STATS_SEC, self._stats)

        self.get_logger().info(
            f'camera_fix: {self.in_topic} -> {self.out_topic} (period={self.period}, '
            f'full_rows={self.full_rows}, source_pitch={self.source_pitch})')

    def _info_cb(self, msg):
        self.last_info = msg

    def _stats(self):
        self.get_logger().info(
            'camera_fix stats %.0fs: full-row frames %d, legacy frames %d'
            % (STATS_SEC, self._n_full, self._n_legacy))
        self._n_full = 0
        self._n_legacy = 0

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

        gray = None
        if self.full_rows:
            try:
                n_rows, why = full_row_layout(raw, H, W, step, self.source_pitch, self.period)
                if n_rows:
                    key = (H, W, self.source_pitch, self.period, n_rows)
                    if key != self._fr_key:
                        self._fr_plan = full_row_plan(H, W, self.source_pitch, self.period, n_rows)
                        self._fr_key = key
                        self.get_logger().info(
                            'camera_fix: full-row read: %d sensor rows at pitch %d -> %dx%d'
                            % (n_rows, self.source_pitch, W, H))
                    gray = full_row_gray(raw, H, W, self.source_pitch, n_rows, self._fr_plan)
                    self._n_full += 1
                else:
                    self.get_logger().warn(
                        f'full-row read not possible ({why}); legacy every-{self.period}th-row path',
                        throttle_duration_sec=10)
            except Exception as e:
                gray = None
                self.get_logger().error(f'camera_fix full-row error: {e}', throttle_duration_sec=2)
        if gray is None:
            self._n_legacy += 1
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
