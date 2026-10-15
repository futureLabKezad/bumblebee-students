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

"""ArUco detection metrics recorder.

CLI observer that subscribes to the camera + aruco_detect topics for a fixed
duration, then appends a single row of aggregate metrics to a CSV.

Designed to be invoked manually by the operator with different --label values
to compare detection robustness across conditions (angles, lighting) before
and after changes to camera_fix / aruco_detect.

Usage:
    source /opt/ros/jazzy/setup.bash
    source /home/lb/ros2_ws/install/setup.bash
    python3 aruco_metrics_record.py --label baseline --duration 60
    python3 aruco_metrics_record.py --label after-A --duration 60
    python3 aruco_metrics_record.py --label 45deg-backlight --duration 60

CSV columns:
    timestamp_iso, label, duration_s,
    hz_image, hz_markers,
    mean_markers_used, frac_seen, mean_n_markers,
    pose_x_std, pose_y_std, pose_z_std,
    yaw_locked_frac, cov_z_mean
"""

import argparse
import csv
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Image
from std_msgs.msg import Int32, Bool
from geometry_msgs.msg import PoseWithCovarianceStamped
from aruco_pose.msg import MarkerArray


CSV_HEADER = [
    'timestamp_iso',
    'label',
    'duration_s',
    'hz_image',
    'hz_markers',
    'mean_markers_used',
    'frac_seen',
    'mean_n_markers',
    'pose_x_std',
    'pose_y_std',
    'pose_z_std',
    'yaw_locked_frac',
    'cov_z_mean',
]


def reliable_qos(depth: int = 10) -> QoSProfile:
    return QoSProfile(
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
        history=HistoryPolicy.KEEP_LAST,
        depth=depth,
    )


class MetricsRecorder(Node):
    def __init__(self, label: str, duration: float):
        super().__init__('aruco_metrics_recorder')
        self.label = label
        self.duration = float(duration)
        self.t_start = time.monotonic()

        # Raw timestamps of incoming messages (monotonic seconds).
        self.image_stamps = []
        self.markers_stamps = []

        # Per-message data.
        self.markers_used_samples = []       # list[int]
        self.n_markers_samples = []          # list[int]  (length of MarkerArray.markers)
        self.pose_x = []
        self.pose_y = []
        self.pose_z = []
        self.cov_z_samples = []              # diagonal element [14] of covariance
        self.yaw_locked_samples = []         # list[bool]

        qos = reliable_qos(10)

        self.sub_image = self.create_subscription(
            Image, '/main_camera/image_raw', self.on_image, qos)
        self.sub_markers = self.create_subscription(
            MarkerArray, '/aruco_detect/markers', self.on_markers, qos)
        self.sub_used = self.create_subscription(
            Int32, '/aruco_detect/markers_used', self.on_markers_used, qos)
        self.sub_yaw = self.create_subscription(
            Bool, '/aruco_detect/yaw_locked', self.on_yaw_locked, qos)
        self.sub_pose = self.create_subscription(
            PoseWithCovarianceStamped, '/aruco_map/pose', self.on_map_pose, qos)

        # Periodic live status (every 10 s).
        self.last_status_t = self.t_start
        self.create_timer(1.0, self.tick)

        self.get_logger().info(
            f"Recording metrics: label='{label}' duration={duration:.1f}s")

    # ----- callbacks -----

    def on_image(self, _msg: Image):
        self.image_stamps.append(time.monotonic())

    def on_markers(self, msg: MarkerArray):
        self.markers_stamps.append(time.monotonic())
        self.n_markers_samples.append(len(msg.markers))

    def on_markers_used(self, msg: Int32):
        self.markers_used_samples.append(int(msg.data))

    def on_yaw_locked(self, msg: Bool):
        self.yaw_locked_samples.append(bool(msg.data))

    def on_map_pose(self, msg: PoseWithCovarianceStamped):
        p = msg.pose.pose.position
        self.pose_x.append(p.x)
        self.pose_y.append(p.y)
        self.pose_z.append(p.z)
        cov = msg.pose.covariance
        # covariance is a flat 36-element list, diagonal [0,7,14,21,28,35].
        # Index 14 is Z dispersion (σz²).
        if len(cov) >= 15:
            self.cov_z_samples.append(float(cov[14]))

    # ----- periodic status -----

    def tick(self):
        now = time.monotonic()
        elapsed = now - self.t_start
        if elapsed - (self.last_status_t - self.t_start) >= 10.0:
            hz_img = self._hz(self.image_stamps)
            hz_mk = self._hz(self.markers_stamps)
            mu_used = self._mean(self.markers_used_samples)
            frac_seen = self._frac_seen()
            self.get_logger().info(
                f"[T+{elapsed:5.1f}s] hz_img={hz_img:5.1f} hz_mk={hz_mk:5.1f} "
                f"mu_used={mu_used:4.2f} frac_seen={frac_seen:4.2f}"
            )
            self.last_status_t = now

        if elapsed >= self.duration:
            self.get_logger().info("Duration reached, finalizing.")
            # signal main loop to stop
            raise SystemExit(0)

    # ----- helpers -----

    @staticmethod
    def _hz(stamps):
        if len(stamps) < 2:
            return 0.0
        dt = stamps[-1] - stamps[0]
        if dt <= 0.0:
            return 0.0
        return (len(stamps) - 1) / dt

    @staticmethod
    def _mean(xs):
        if not xs:
            return 0.0
        return sum(xs) / len(xs)

    @staticmethod
    def _std(xs):
        n = len(xs)
        if n < 2:
            return 0.0
        m = sum(xs) / n
        var = sum((x - m) ** 2 for x in xs) / (n - 1)
        if var < 0.0:
            return 0.0
        return math.sqrt(var)

    def _frac_seen(self):
        if not self.markers_used_samples:
            return 0.0
        seen = sum(1 for v in self.markers_used_samples if v >= 1)
        return seen / len(self.markers_used_samples)

    def _yaw_locked_frac(self):
        if not self.yaw_locked_samples:
            return 0.0
        locked = sum(1 for v in self.yaw_locked_samples if v)
        return locked / len(self.yaw_locked_samples)

    # ----- final metrics -----

    def compute_row(self):
        return {
            'timestamp_iso': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'label': self.label,
            'duration_s': f"{self.duration:.1f}",
            'hz_image': f"{self._hz(self.image_stamps):.3f}",
            'hz_markers': f"{self._hz(self.markers_stamps):.3f}",
            'mean_markers_used': f"{self._mean(self.markers_used_samples):.3f}",
            'frac_seen': f"{self._frac_seen():.3f}",
            'mean_n_markers': f"{self._mean(self.n_markers_samples):.3f}",
            'pose_x_std': f"{self._std(self.pose_x):.4f}",
            'pose_y_std': f"{self._std(self.pose_y):.4f}",
            'pose_z_std': f"{self._std(self.pose_z):.4f}",
            'yaw_locked_frac': f"{self._yaw_locked_frac():.3f}",
            'cov_z_mean': f"{self._mean(self.cov_z_samples):.4f}",
        }


def append_csv(path: str, row: dict):
    new_file = not os.path.exists(path)
    with open(path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new_file:
            w.writeheader()
        w.writerow(row)


def parse_args():
    ap = argparse.ArgumentParser(description="ArUco detection metrics recorder")
    ap.add_argument('--label', required=True,
                    help="Run label (e.g. baseline, after-A, 45deg-backlight)")
    ap.add_argument('--duration', type=float, default=60.0,
                    help="Recording duration in seconds (default: 60)")
    ap.add_argument('--csv', default='/tmp/aruco_metrics.csv',
                    help="Output CSV path (default: /tmp/aruco_metrics.csv)")
    return ap.parse_args()


def main():
    args = parse_args()

    rclpy.init()
    node = MetricsRecorder(args.label, args.duration)

    # Graceful Ctrl+C handling: rclpy.spin() will raise KeyboardInterrupt.
    interrupted = False
    try:
        try:
            rclpy.spin(node)
        except SystemExit:
            # Duration reached, fired from inside tick().
            pass
        except KeyboardInterrupt:
            interrupted = True
            node.get_logger().info("Ctrl+C received, finalizing early.")
    finally:
        row = node.compute_row()
        try:
            append_csv(args.csv, row)
            node.get_logger().info(
                f"Wrote row to {args.csv}: hz_image={row['hz_image']} "
                f"hz_markers={row['hz_markers']} mean_markers_used={row['mean_markers_used']} "
                f"frac_seen={row['frac_seen']} pose_z_std={row['pose_z_std']} "
                f"cov_z_mean={row['cov_z_mean']}"
            )
        except Exception as e:
            node.get_logger().error(f"Failed to write CSV: {e}")

        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass

    sys.exit(130 if interrupted else 0)


if __name__ == '__main__':
    main()
