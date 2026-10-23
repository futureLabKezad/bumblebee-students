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

Query parameters (all optional; each request is clamped to these limits):
  quality  JPEG quality 10..90             (default 60)
  fps      max encoded frames/s 1..15      (default 5;   0 = the cap, 15)
  width    max output width in px 80..640  (default 320; 0 = the cap, 640)
  height   accepted but ignored — aspect ratio is preserved from width

THE SHARED-PARAMETER RULE
  A topic is encoded once and every viewer of it gets the same JPEGs, so
  quality/fps/width are shared per topic. They are the HIGHEST value of each
  parameter among the viewers connected right now (each request clamped as
  above first), recomputed whenever a viewer joins or leaves:
    * nobody gets less than they asked for, within the limits;
    * nobody can push the drone past 640 px / 15 fps / quality 90, whatever
      the URL says (fps=0&width=0 used to mean full size at the camera rate);
    * when the most demanding viewer leaves, the stream drops back to what
      the remaining viewers asked for (it used to stay with whatever the
      FIRST viewer of the topic had asked, for as long as anyone watched).
  The GCS apps ask quality=60&fps=12&width=320 (PiP 50/3/160), www/gcs.html
  60/5/320; all inside the limits, so they get exactly what they ask.

Handles both raw RGB images and YUYV images from v4l2_camera + libcamerify.
YUYV topics are identified by topic name containing 'yuv' and the step-5 tile
pattern is corrected the same way camera_fix.py does it.

Performance notes (the Pi 5 is CPU-bound — aruco_detect pins ~2 cores):
  * Topics are subscribed lazily, only when a browser actually opens the stream.
  * A topic's subscription is destroyed once it has had no viewer for 10 s,
    so publishers that only render while someone subscribes (aruco_detect's
    640x480 debug image, ~0.9 MB per frame, and its map image) stop again,
    and raw camera frames are no longer received just to be dropped; the
    next viewer subscribes anew. This runs from a timer of the node, i.e. in the executor
    thread, so destroy_subscription never races the executor.
  * The expensive cvtColor/resize/imencode work is skipped entirely while no
    client is watching a topic (encode-on-demand via a per-topic client count).
  * Each topic is throttled to its shared fps and downscaled to its shared
    width before JPEG encoding, so the dashboard gets the lightweight stream
    it asks for instead of full-res 15 Hz.
  * A viewer whose socket accepts no data for 10 s is dropped (socket timeout
    on the handler, plus TCP_USER_TIMEOUT on Linux for a laptop that vanished
    while only keep-alives are sent), instead of being counted as watching
    for up to ~15 min of TCP retransmissions.
  * A new viewer's first frame is never older than 2 s: a leftover frame
    (say, the ArUco debug image of the last flight) is not shown as live.
  * All image subscriptions use BEST_EFFORT, which is QoS-compatible with both
    RELIABLE and BEST_EFFORT publishers (a RELIABLE subscriber is not).

Usage (standalone):
  python3 ros_mjpeg_server.py

Usage (from launch):
  ros2 run bumblebee ros_mjpeg_server.py
"""

import errno
import math
import socket
import threading
import time
import urllib.parse
import io
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple


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

# Limits every viewer's request is clamped to (see THE SHARED-PARAMETER RULE).
MIN_QUALITY, MAX_QUALITY = 10, 90
MIN_FPS, MAX_FPS = 1.0, 15.0
MIN_WIDTH, MAX_WIDTH = 80, 640

SUB_IDLE_RELEASE_S = 10.0   # destroy a topic's subscription after this long without viewers
SUB_SWEEP_PERIOD_S = 1.0    # how often the node looks for such subscriptions
CLIENT_TIMEOUT_S = 10       # drop a viewer whose socket accepts no data for this long
STALE_FRAME_S = 2.0         # a new viewer's first frame must be younger than this

# One clock for the idle / frame-age / fps bookkeeping (the tests replace it).
_clock = time.monotonic


def clamp_request(quality, fps, width) -> Tuple[int, float, int]:
    """Clamp one viewer's request to the server limits.

    0 or a negative fps/width (the old "uncapped" / "no downscale") means the
    cap; a value that is not a number means the default.
    """
    try:
        quality = int(quality)
    except (TypeError, ValueError, OverflowError):
        quality = DEFAULT_QUALITY
    quality = max(MIN_QUALITY, min(MAX_QUALITY, quality))

    try:
        fps = float(fps)
    except (TypeError, ValueError, OverflowError):
        fps = DEFAULT_FPS
    if math.isnan(fps):
        fps = DEFAULT_FPS
    elif fps <= 0:
        fps = MAX_FPS
    fps = max(MIN_FPS, min(MAX_FPS, fps))

    try:
        width = int(width)
    except (TypeError, ValueError, OverflowError):
        width = DEFAULT_WIDTH
    if width <= 0:
        width = MAX_WIDTH
    width = max(MIN_WIDTH, min(MAX_WIDTH, width))
    return quality, fps, width


# -------------------------------------------------------------------
# Per-topic state: latest JPEG, client refcount, and stream parameters.
# Clients poll the frame store via condition variable.
# -------------------------------------------------------------------
class FrameStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._jpeg: Optional[bytes] = None
        self._seq: int = 0
        self._stamp = 0.0           # _clock() of the latest put()

    def put(self, jpeg: bytes):
        with self._cond:
            self._jpeg = jpeg
            self._seq += 1
            self._stamp = _clock()
            self._cond.notify_all()

    def start_seq(self, max_age: float = STALE_FRAME_S) -> int:
        """The seq a new viewer should start from (pass it to get()).

        The latest frame is handed out at once only if it is younger than
        max_age; an older one (left from a previous viewer, the publisher has
        stopped since) is skipped and the viewer waits for a new frame.
        """
        with self._cond:
            if self._jpeg is not None and _clock() - self._stamp <= max_age:
                return self._seq - 1
            return self._seq

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
    """Frame store + viewers + shared stream params for one image topic.
    Fields other than store are guarded by lock."""
    def __init__(self):
        self.store = FrameStore()
        self.lock = threading.Lock()
        # One clamped (quality, fps, width) request per connected viewer.
        self.requests: List[Tuple[int, float, int]] = []
        self.idle_since: Optional[float] = None   # _clock() when the last viewer left
        self.last_encode = 0.0
        # Shared stream params: per-field maximum of requests (see the rule
        # at the top of the file); unchanged while there are no viewers.
        self.quality = DEFAULT_QUALITY
        self.fps = DEFAULT_FPS
        self.width = DEFAULT_WIDTH

    @property
    def clients(self) -> int:
        return len(self.requests)

    def recompute(self):
        """Re-derive the shared params from the viewers present (hold lock)."""
        if self.requests:
            self.quality = max(r[0] for r in self.requests)
            self.fps = max(r[1] for r in self.requests)
            self.width = max(r[2] for r in self.requests)


# topic -> TopicState
_topics: Dict[str, TopicState] = {}
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
        self._subs: Dict[str, object] = {}
        self._subs_lock = threading.Lock()   # order: _subs_lock, then a TopicState.lock

        # BEST_EFFORT is compatible with both RELIABLE and BEST_EFFORT
        # publishers, so it works for raw camera topics (best-effort) and
        # processed topics like aruco debug (reliable) alike.
        self._qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=1,
        )

        # HTTP threads only ever create subscriptions; destroying them while
        # the executor spins would race it, so idle ones are destroyed by this
        # timer, whose callback runs in the executor thread itself.
        self._sweep_timer = self.create_timer(SUB_SWEEP_PERIOD_S, self._release_idle_subscriptions)

        self.get_logger().info(
            f'MJPEG server ready on port {PORT} (lazy subscribe, encode-on-demand, '
            f'idle release {SUB_IDLE_RELEASE_S:g} s, client timeout {CLIENT_TIMEOUT_S} s)')

    def add_client(self, topic: str, quality: int, fps: float, width: int) -> TopicState:
        """Register a viewer: clamp its request, recompute the topic's shared
        params and subscribe if the topic has no subscription (any more)."""
        req = clamp_request(quality, fps, width)
        st = get_topic(topic)
        with st.lock:
            st.requests.append(req)
            st.idle_since = None
            st.recompute()
        try:
            with self._subs_lock:
                if topic not in self._subs:
                    self._do_subscribe(topic, st)
        except Exception:
            self._forget(st, req)     # no phantom viewer if subscribing failed
            raise
        with st.lock:
            n, q, f, w = st.clients, st.quality, st.fps, st.width
        self.get_logger().info(f'MJPEG viewer + {topic}: clients={n}, sending {w}px {f:g}fps q{q}')
        return st

    def remove_client(self, topic: str, quality: int, fps: float, width: int, reason: str = 'closed'):
        """Unregister the viewer that was added with these params. The
        subscription stays until the topic has been idle SUB_IDLE_RELEASE_S."""
        st = get_topic(topic)
        n = self._forget(st, clamp_request(quality, fps, width))
        if n is not None:
            self.get_logger().info(f'MJPEG viewer - {topic} ({reason}): clients={n}')

    @staticmethod
    def _forget(st: TopicState, req) -> Optional[int]:
        """Drop one viewer's request; returns the viewers left (None if absent)."""
        with st.lock:
            try:
                st.requests.remove(req)
            except ValueError:
                return None
            if not st.requests:
                st.idle_since = _clock()
            st.recompute()
            return st.clients

    def _release_idle_subscriptions(self):
        """Timer callback (executor thread): destroy the subscription of every
        topic that has had no viewer for SUB_IDLE_RELEASE_S seconds."""
        now = _clock()
        released = []
        with self._subs_lock:
            for topic, sub in list(self._subs.items()):
                st = get_topic(topic)
                with st.lock:
                    if st.clients:
                        continue
                    if st.idle_since is None:
                        st.idle_since = now
                    if now - st.idle_since < SUB_IDLE_RELEASE_S:
                        continue
                # A viewer arriving from here on finds the topic missing in
                # _subs (it waits for _subs_lock) and subscribes again.
                del self._subs[topic]
                try:
                    self.destroy_subscription(sub)
                except Exception as e:
                    self.get_logger().error(f'MJPEG server: destroy_subscription({topic}) failed: {e}')
                released.append(topic)
        for topic in released:
            self.get_logger().info(
                f'MJPEG server: released {topic} (no viewers for {SUB_IDLE_RELEASE_S:g} s)')
        return released

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
        now = _clock()
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


_node: Optional[MjpegNode] = None


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


def _requested_params(params: dict) -> Tuple[int, float, int]:
    """(quality, fps, width) one viewer asked for in the URL, clamped."""
    return clamp_request(_int_param(params, 'quality', DEFAULT_QUALITY),
                         _float_param(params, 'fps', DEFAULT_FPS),
                         _int_param(params, 'width', DEFAULT_WIDTH))


def _set_tcp_user_timeout(sock, seconds: float) -> bool:
    """Linux: abort the connection once sent data stays unacknowledged for
    `seconds` (the laptop was closed or left the Wi-Fi), instead of after the
    ~15 min of retransmissions of tcp_retries2. False where the OS lacks it."""
    opt = getattr(socket, 'TCP_USER_TIMEOUT', None)
    if opt is None:
        return False
    try:
        sock.setsockopt(socket.IPPROTO_TCP, opt, int(seconds * 1000))
    except OSError:
        return False
    return True


def _is_timeout(e: BaseException) -> bool:
    return isinstance(e, socket.timeout) or getattr(e, 'errno', None) == errno.ETIMEDOUT


class MjpegHandler(BaseHTTPRequestHandler):
    # StreamRequestHandler.setup() applies this with settimeout(): a send
    # that cannot progress for 10 s (client stopped reading, or vanished and
    # the buffers are full) raises socket.timeout and the viewer is dropped.
    timeout = CLIENT_TIMEOUT_S

    def setup(self):
        super().setup()
        # While a topic sends only keep-alives the tiny writes never fill the
        # buffers, so the socket timeout alone would not notice a vanished
        # client; with TCP_USER_TIMEOUT the next write fails with ETIMEDOUT.
        _set_tcp_user_timeout(self.connection, CLIENT_TIMEOUT_S)

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
        node = _node
        if node is None:
            self.send_error(503, 'ROS node not ready')
            return

        quality, fps, width = _requested_params(params)
        st = node.add_client(topic, quality, fps, width)

        reason = 'closed'
        try:
            # Inside the try: a client gone before the headers must not stay
            # counted as a viewer.
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            seq = st.store.start_seq()
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
        except OSError as e:     # socket.timeout, BrokenPipe, ConnectionReset, ETIMEDOUT...
            reason = 'timeout' if _is_timeout(e) else 'closed'
        except Exception as e:
            reason = f'error: {e!r}'
        finally:
            node.remove_client(topic, quality, fps, width, reason=reason)


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
