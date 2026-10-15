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
ros_mjpeg_server.py — MJPEG HTTP streaming server for ROS2 image topics.

Replaces web_video_server when it cannot be installed.
Serves MJPEG streams on port 8080 compatible with the GCS dashboard.

URL format:
  http://host:8080/stream?topic=/camera/image_raw[&quality=60&fps=5&width=320&height=240]

Query parameters (all optional, taken from the FIRST active client of a topic):
  quality  JPEG quality 1..100          (default 60)
  fps      max encoded frames per second (default 5; 0 = uncapped)
  width    max output width in px        (default 320; 0 = no downscale)
  height   accepted but ignored — aspect ratio is preserved from width

Handles both raw RGB images and YUYV images from v4l2_camera + libcamerify.
YUYV topics are identified by topic name containing 'yuv' and the step-5 tile
pattern is corrected the same way camera_fix.py does it.

Performance notes (the Pi 5 is CPU-bound — aruco_detect pins ~2 cores):
  * Topics are subscribed lazily, only when a browser actually opens the stream.
  * The expensive cvtColor/resize/imencode work is skipped entirely while no
    client is watching a topic (encode-on-demand via a per-topic client count).
  * Each topic is throttled to its requested fps and downscaled to its
    requested width before JPEG encoding, so the dashboard gets exactly the
    lightweight stream it asks for instead of full-res 15 Hz.
  * All image subscriptions use BEST_EFFORT, which is QoS-compatible with both
    RELIABLE and BEST_EFFORT publishers (a RELIABLE subscriber is not).

Usage (standalone):
  python3 ros_mjpeg_server.py

Usage (from launch):
  ros2 run bumblebee ros_mjpeg_server.py
"""

import threading
import time
import urllib.parse
import io
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Each client connection gets its own thread."""
    daemon_threads = True

import numpy as np
import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSHistoryPolicy
from sensor_msgs.msg import Image

PORT = 8080

# Defaults applied when a client omits the query parameter.
DEFAULT_QUALITY = 60
DEFAULT_FPS = 5.0
DEFAULT_WIDTH = 320


# -------------------------------------------------------------------
# Per-topic state: latest JPEG, client refcount, and stream parameters.
# Clients poll the frame store via condition variable.
# -------------------------------------------------------------------
class FrameStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._jpeg: bytes | None = None
        self._seq: int = 0

    def put(self, jpeg: bytes):
        with self._cond:
            self._jpeg = jpeg
            self._seq += 1
            self._cond.notify_all()

    def get(self, last_seq: int, timeout: float = 2.0):
        """Block until a new frame arrives (seq > last_seq), return (jpeg, seq)."""
        with self._cond:
            deadline = time.monotonic() + timeout
            while self._seq <= last_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, self._seq
                self._cond.wait(remaining)
            return self._jpeg, self._seq


class TopicState:
    """Frame store + viewer count + stream params for one image topic."""
    def __init__(self):
        self.store = FrameStore()
        self.lock = threading.Lock()
        self.clients = 0
        self.last_encode = 0.0
        # Stream params; locked in from the first client of the topic.
        self.quality = DEFAULT_QUALITY
        self.fps = DEFAULT_FPS
        self.width = DEFAULT_WIDTH


# topic -> TopicState
_topics: dict[str, TopicState] = {}
_topics_lock = threading.Lock()


def get_topic(topic: str) -> TopicState:
    with _topics_lock:
        st = _topics.get(topic)
        if st is None:
            st = TopicState()
            _topics[topic] = st
        return st


# -------------------------------------------------------------------
# ROS2 node: subscribes to image topics on demand
# -------------------------------------------------------------------
class MjpegNode(Node):
    def __init__(self):
        super().__init__('ros_mjpeg_server')
        self._subs: dict[str, object] = {}
        self._subs_lock = threading.Lock()

        # BEST_EFFORT is compatible with both RELIABLE and BEST_EFFORT
        # publishers, so it works for raw camera topics (best-effort) and
        # processed topics like aruco debug (reliable) alike.
        self._qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.get_logger().info(f'MJPEG server ready on port {PORT} (lazy subscribe, encode-on-demand)')

    def add_client(self, topic: str, quality: int, fps: float, width: int) -> TopicState:
        """Register a viewer. Subscribes lazily on the first client and locks
        in the stream params from that client."""
        st = get_topic(topic)
        with st.lock:
            if st.clients == 0:
                st.quality = quality
                st.fps = fps
                st.width = width
            st.clients += 1
        with self._subs_lock:
            if topic not in self._subs:
                self._do_subscribe(topic, st)
        return st

    def remove_client(self, topic: str):
        st = get_topic(topic)
        with st.lock:
            if st.clients > 0:
                st.clients -= 1
        # Subscription is kept alive (destroying it from this thread while the
        # executor spins is racy); _image_cb early-returns while clients == 0,
        # so no JPEG encoding happens for topics nobody is watching.

    def _do_subscribe(self, topic: str, st: TopicState):
        """Create a subscription for topic (caller holds _subs_lock)."""
        sub = self.create_subscription(
            Image, topic,
            lambda msg, t=topic, s=st: self._image_cb(msg, t, s),
            self._qos,
        )
        self._subs[topic] = sub
        self.get_logger().info(f'MJPEG server: subscribed to {topic}')

    def _image_cb(self, msg: Image, topic: str, st: TopicState):
        # Encode-on-demand + fps cap: bail out before any heavy work.
        now = time.monotonic()
        with st.lock:
            if st.clients <= 0:
                return
            min_interval = (1.0 / st.fps) if st.fps > 0 else 0.0
            if min_interval and (now - st.last_encode) < min_interval:
                return
            st.last_encode = now
            quality = st.quality
            width = st.width
        try:
            jpeg = self._to_jpeg(msg, width, quality)
        except Exception as e:
            self.get_logger().error(f'Image convert error on {topic}: {e}', throttle_duration_sec=5)
            return
        st.store.put(jpeg)

    def _to_jpeg(self, msg: Image, target_width: int, quality: int) -> bytes:
        H, W, step = msg.height, msg.width, msg.step
        raw = np.frombuffer(bytes(msg.data), dtype=np.uint8)

        if msg.encoding in ('yuv422_yuy2', 'yuyv4:2:2', 'YUYV'):
            # PiSP ISP tile fix: every 5th row is a valid YUYV row
            rows = raw.reshape(H, step)
            valid = rows[0::5]
            yuyv = valid.reshape(-1, W, 2)
            bgr = cv2.cvtColor(yuyv, cv2.COLOR_YUV2BGR_YUYV)
            if bgr.shape[0] != H:
                bgr = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_LINEAR)
        elif msg.encoding == 'rgb8':
            rgb = raw.reshape(H, W, 3)
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        elif msg.encoding == 'bgr8':
            bgr = raw.reshape(H, W, 3)
        elif msg.encoding in ('mono8', '8UC1'):
            gray = raw.reshape(H, W)
            bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        else:
            raise ValueError(f'Unsupported encoding: {msg.encoding}')

        # Downscale to the requested width (keeps aspect ratio). Only shrinks.
        if target_width and bgr.shape[1] > target_width:
            scale = target_width / float(bgr.shape[1])
            new_h = max(1, int(round(bgr.shape[0] * scale)))
            bgr = cv2.resize(bgr, (target_width, new_h), interpolation=cv2.INTER_AREA)

        ok, buf = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if not ok:
            raise ValueError('JPEG encode failed')
        return bytes(buf)


_node: MjpegNode | None = None


# -------------------------------------------------------------------
# HTTP handler
# -------------------------------------------------------------------
def _int_param(params: dict, key: str, default: int) -> int:
    try:
        return int(params[key][0])
    except (KeyError, ValueError, IndexError):
        return default


def _float_param(params: dict, key: str, default: float) -> float:
    try:
        return float(params[key][0])
    except (KeyError, ValueError, IndexError):
        return default


class MjpegHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress per-request logging

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        topic_list = params.get('topic', [])

        if parsed.path != '/stream' or not topic_list:
            self.send_error(400, 'Use /stream?topic=/camera/image_raw')
            return

        topic = topic_list[0]
        if _node is None:
            self.send_error(503, 'ROS node not ready')
            return

        quality = max(1, min(100, _int_param(params, 'quality', DEFAULT_QUALITY)))
        fps = max(0.0, _float_param(params, 'fps', DEFAULT_FPS))
        width = max(0, _int_param(params, 'width', DEFAULT_WIDTH))

        st = _node.add_client(topic, quality, fps, width)

        self.send_response(200)
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        seq = 0
        try:
            while True:
                jpeg, seq = st.store.get(seq, timeout=5.0)
                if jpeg is None:
                    # No frame within timeout — send a keep-alive boundary
                    self.wfile.write(b'--frame\r\n\r\n')
                    self.wfile.flush()
                    continue
                self.wfile.write(
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n'
                    b'Content-Length: ' + str(len(jpeg)).encode() + b'\r\n'
                    b'\r\n' + jpeg + b'\r\n'
                )
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass
        finally:
            _node.remove_client(topic)


def main():
    global _node
    rclpy.init()
    _node = MjpegNode()

    # Spin ROS node in a background thread
    ros_thread = threading.Thread(target=rclpy.spin, args=(_node,), daemon=True)
    ros_thread.start()

    server = ThreadedHTTPServer(('0.0.0.0', PORT), MjpegHandler)
    _node.get_logger().info(f'Listening on :{PORT}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        _node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
