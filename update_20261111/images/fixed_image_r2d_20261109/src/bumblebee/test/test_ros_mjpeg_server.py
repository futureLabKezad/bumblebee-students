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

"""Tests for src/ros_mjpeg_server.py, without ROS.

rclpy, sensor_msgs, cv2 and numpy are replaced by fakes in sys.modules only
while the server module is imported; the real modules (if any) are put back
right after, so other tests are not affected.

    python3 -m unittest discover -s test -p 'test_ros_mjpeg_server.py'
"""
import importlib.util
import os
import socket
import sys
import threading
import time
import types
import unittest
import urllib.parse
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), 'src', 'ros_mjpeg_server.py')

APP = dict(quality=60, fps=12, width=320)        # Mac/Windows GCS CameraView
WEB = dict(quality=60, fps=5, width=320)         # www/gcs.html main camera
PIP = dict(quality=50, fps=3, width=160)         # ArUco map picture-in-picture
STUDENT = dict(quality=100, fps=0, width=0)      # "give me everything"


# ---------------------------------------------------------------- fakes
class FakeLogger:
    def __init__(self):
        self.lines = []

    def _log(self, msg, **_kw):
        self.lines.append(str(msg))

    info = warn = warning = error = debug = _log


class FakeSub:
    def __init__(self, topic, cb):
        self.topic, self.cb, self.destroyed = topic, cb, False


class FakeTimer:
    def __init__(self, period, cb):
        self.period, self.callback = period, cb


class FakeNode:
    """Stands in for rclpy.node.Node and records what the server asks of ROS."""
    fail_next_subscribe = False

    def __init__(self, name, *a, **kw):
        self.node_name = name
        self.created, self.destroyed, self.timers = [], [], []
        self._logger = FakeLogger()

    def create_subscription(self, msg_type, topic, cb, qos):
        if self.fail_next_subscribe:
            self.fail_next_subscribe = False
            raise RuntimeError('rcl: subscription create failed')
        sub = FakeSub(topic, cb)
        self.created.append(sub)
        return sub

    def destroy_subscription(self, sub):
        sub.destroyed = True
        self.destroyed.append(sub)
        return True

    def create_timer(self, period, cb, *a, **kw):
        t = FakeTimer(period, cb)
        self.timers.append(t)
        return t

    def get_logger(self):
        return self._logger

    def destroy_node(self):
        pass


def _fake_modules():
    def mod(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        return m

    qos = mod('rclpy.qos',
              QoSProfile=lambda **kw: types.SimpleNamespace(**kw),
              QoSReliabilityPolicy=types.SimpleNamespace(BEST_EFFORT='best_effort', RELIABLE='reliable'),
              QoSHistoryPolicy=types.SimpleNamespace(KEEP_LAST='keep_last'))
    node = mod('rclpy.node', Node=FakeNode)
    rclpy = mod('rclpy', node=node, qos=qos,
                init=lambda *a, **k: None, spin=lambda *a, **k: None, shutdown=lambda *a, **k: None)
    msg = mod('sensor_msgs.msg', Image=type('Image', (), {}))
    return {
        'numpy': mod('numpy'),
        'cv2': mod('cv2'),
        'rclpy': rclpy,
        'rclpy.node': node,
        'rclpy.qos': qos,
        'sensor_msgs': mod('sensor_msgs', msg=msg),
        'sensor_msgs.msg': msg,
    }


def load_server():
    """A fresh copy of the server module (its own topic table) built on the fakes."""
    fakes = _fake_modules()
    saved = {name: sys.modules.get(name) for name in fakes}
    sys.modules.update(fakes)
    try:
        spec = importlib.util.spec_from_file_location('ros_mjpeg_server_under_test', SRC)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        for name, old in saved.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return m


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.m = load_server()
        self.clock = FakeClock()
        # the server reads "now" through ros_mjpeg_server._clock
        patcher = mock.patch.object(self.m, '_clock', self.clock, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.node = self.m.MjpegNode()
        self.m._node = self.node
        self.encoded = []      # (width, quality) of every JPEG the node encoded

        def fake_to_jpeg(msg, width, quality):
            self.encoded.append((width, quality))
            return b'\xff\xd8jpeg%d\xff\xd9' % len(self.encoded)
        self.node._to_jpeg = fake_to_jpeg

    def sweep(self):
        """Run the node's own timer callback, as the rclpy executor would."""
        self.assertEqual(len(self.node.timers), 1)
        self.node.timers[0].callback()

    def params(self, topic):
        st = self.m.get_topic(topic)
        return st.quality, st.fps, st.width


# ------------------------------------------------- 1. idle subscriptions
class IdleSubscriptionRelease(ServerTest):
    TOPIC = '/aruco_detect/debug'

    def test_sweep_timer_lives_in_the_node(self):
        # create_timer => the callback runs in the executor thread that spins
        # the node, so destroy_subscription never races the executor.
        self.assertEqual(len(self.node.timers), 1)
        self.assertLessEqual(self.node.timers[0].period, 1.0)

    def test_released_10s_after_the_last_viewer_leaves(self):
        self.node.add_client(self.TOPIC, **APP)
        self.node.add_client(self.TOPIC, **PIP)
        self.assertEqual(len(self.node.created), 1)

        self.node.remove_client(self.TOPIC, **APP)
        self.clock.t += 60
        self.sweep()                                # one viewer is still there
        self.assertEqual(self.node.destroyed, [])

        self.node.remove_client(self.TOPIC, **PIP)  # last viewer gone at t0
        self.clock.t += 9.9
        self.sweep()
        self.assertEqual(self.node.destroyed, [])
        self.clock.t += 0.1                          # t0 + 10 s
        self.sweep()
        self.assertEqual(self.node.destroyed, [self.node.created[0]])
        self.clock.t += 30
        self.sweep()                                 # destroyed exactly once
        self.assertEqual(len(self.node.destroyed), 1)

    def test_next_viewer_subscribes_again_and_gets_frames(self):
        self.node.add_client(self.TOPIC, **APP)
        self.node.remove_client(self.TOPIC, **APP)
        self.clock.t += 10
        self.sweep()
        self.assertTrue(self.node.created[0].destroyed)

        st = self.node.add_client(self.TOPIC, **APP)
        self.assertEqual(len(self.node.created), 2)
        fresh = self.node.created[1]
        self.assertEqual(fresh.topic, self.TOPIC)
        self.assertFalse(fresh.destroyed)
        fresh.cb(object())                            # a message on the new subscription
        jpeg, _ = st.store.get(st.store.start_seq(), timeout=0.5)
        self.assertIsNotNone(jpeg)

    def test_viewer_back_within_10s_keeps_the_subscription(self):
        self.node.add_client(self.TOPIC, **APP)
        self.node.remove_client(self.TOPIC, **APP)
        self.clock.t += 9
        self.node.add_client(self.TOPIC, **APP)       # e.g. Bottom -> ArUco -> Bottom
        self.clock.t += 120
        self.sweep()
        self.assertEqual(self.node.destroyed, [])
        self.assertEqual(len(self.node.created), 1)

        self.node.remove_client(self.TOPIC, **APP)    # idle clock restarts here
        self.clock.t += 9.9
        self.sweep()
        self.assertEqual(self.node.destroyed, [])
        self.clock.t += 0.1
        self.sweep()
        self.assertEqual(len(self.node.destroyed), 1)

    def test_watched_topic_is_never_released(self):
        self.node.add_client(self.TOPIC, **APP)
        self.clock.t += 24 * 3600
        self.sweep()
        self.assertEqual(self.node.destroyed, [])

    def test_only_idle_topics_are_released(self):
        self.node.add_client('/main_camera/image_raw', **APP)
        self.node.add_client(self.TOPIC, **APP)
        self.node.remove_client(self.TOPIC, **APP)
        self.clock.t += 10
        self.sweep()
        self.assertEqual([s.topic for s in self.node.destroyed], [self.TOPIC])

    def test_failed_subscribe_does_not_leave_a_phantom_viewer(self):
        self.node.fail_next_subscribe = True
        with self.assertRaises(RuntimeError):
            self.node.add_client(self.TOPIC, **APP)
        self.assertEqual(self.m.get_topic(self.TOPIC).clients, 0)
        st = self.node.add_client(self.TOPIC, **APP)  # next try works normally
        self.assertEqual(st.clients, 1)
        self.node.remove_client(self.TOPIC, **APP)
        self.clock.t += 10
        self.sweep()
        self.assertEqual(len(self.node.destroyed), 1)

    def test_new_viewer_does_not_get_a_stale_frame(self):
        # A frame left from an earlier viewer (e.g. ArUco debug from the last
        # flight) must not be shown to a new viewer as if it were live.
        st = self.node.add_client(self.TOPIC, **APP)
        self.node.created[0].cb(object())
        self.assertEqual(len(self.encoded), 1)
        jpeg, _ = st.store.get(st.store.start_seq(), timeout=0.2)
        self.assertIsNotNone(jpeg)                   # fresh frame: served at once
        self.node.remove_client(self.TOPIC, **APP)
        self.clock.t += 30
        self.sweep()
        st = self.node.add_client(self.TOPIC, **APP)
        jpeg, _ = st.store.get(st.store.start_seq(), timeout=0.2)
        self.assertIsNone(jpeg)                      # stale frame: not served


# ------------------------------------------------------ 3. parameter caps
class ParameterCaps(ServerTest):
    TOPIC = '/main_camera/image_raw'

    def parse(self, query):
        return self.m._requested_params(urllib.parse.parse_qs(query))

    def test_url_defaults_unchanged(self):
        self.assertEqual(self.parse('topic=/x'), (60, 5.0, 320))

    def test_app_and_web_requests_pass_through_unchanged(self):
        self.assertEqual(self.parse('topic=/x&type=mjpeg&quality=60&fps=12&width=320&height=240'), (60, 12.0, 320))
        self.assertEqual(self.parse('topic=/x&type=mjpeg&quality=50&fps=3&width=160&height=120'), (50, 3.0, 160))
        self.assertEqual(self.parse('topic=/x&type=mjpeg&quality=60&fps=5&width=320&height=240'), (60, 5.0, 320))

    def test_requests_are_capped(self):
        self.assertEqual(self.parse('topic=/x&quality=100&fps=0&width=0'), (90, 15.0, 640))
        self.assertEqual(self.parse('topic=/x&quality=100&fps=1000&width=4000'), (90, 15.0, 640))
        self.assertEqual(self.parse('topic=/x&quality=-5&fps=-3&width=-1'), (10, 15.0, 640))
        self.assertEqual(self.parse('topic=/x&quality=0&fps=0.01&width=8'), (10, 1.0, 80))
        self.assertEqual(self.parse('topic=/x&fps=inf'), (60, 15.0, 320))
        self.assertEqual(self.parse('topic=/x&fps=nan&width=abc&quality=x'), (60, 5.0, 320))

    def test_node_caps_direct_callers_too(self):
        self.node.add_client(self.TOPIC, **STUDENT)
        self.assertEqual(self.params(self.TOPIC), (90, 15.0, 640))

    def test_shared_params_follow_the_viewers_present(self):
        # Highest request wins (so nobody gets less than asked, within caps)
        # and it is recomputed whenever a viewer joins or leaves.
        self.node.add_client(self.TOPIC, **WEB)
        self.assertEqual(self.params(self.TOPIC), (60, 5.0, 320))
        self.node.add_client(self.TOPIC, **APP)
        self.assertEqual(self.params(self.TOPIC), (60, 12.0, 320))
        self.node.add_client(self.TOPIC, **STUDENT)
        self.assertEqual(self.params(self.TOPIC), (90, 15.0, 640))
        self.node.remove_client(self.TOPIC, **STUDENT)
        self.assertEqual(self.params(self.TOPIC), (60, 12.0, 320))
        self.node.remove_client(self.TOPIC, **APP)
        self.assertEqual(self.params(self.TOPIC), (60, 5.0, 320))

    def test_first_viewer_does_not_lock_params(self):
        self.node.add_client(self.TOPIC, **STUDENT)   # student script opened it first
        self.node.add_client(self.TOPIC, **APP)
        self.node.remove_client(self.TOPIC, **STUDENT)
        self.assertEqual(self.params(self.TOPIC), (60, 12.0, 320))

    def test_fps0_width0_viewer_cannot_push_encoding_past_the_cap(self):
        self.node.add_client(self.TOPIC, **APP)
        self.node.add_client(self.TOPIC, **STUDENT)
        cb = self.node.created[0].cb
        for _ in range(200):                           # a 100 Hz camera for 2 s
            cb(object())
            self.clock.t += 0.01
        self.assertLessEqual(len(self.encoded), 2 * 15 + 1)
        self.assertGreaterEqual(len(self.encoded), 2 * 15 - 2)
        self.assertTrue(all(w <= 640 and q <= 90 for w, q in self.encoded))


# ---------------------------------------------------- 2. dead-client timeout
class DeadClientTimeout(ServerTest):
    TOPIC = '/second_camera/image_raw'

    def test_handler_has_10s_socket_timeout(self):
        # StreamRequestHandler.setup() turns this into settimeout() on the
        # client socket; without it (None) a stuck send blocks for ~15 min.
        self.assertEqual(self.m.MjpegHandler.timeout, 10)
        self.assertEqual(self.m.CLIENT_TIMEOUT_S, 10)

    def test_tcp_user_timeout_is_set_where_the_os_has_it(self):
        calls = []

        class Sock:
            def setsockopt(self, *args):
                calls.append(args)

        linux_socket = types.SimpleNamespace(IPPROTO_TCP=socket.IPPROTO_TCP, TCP_USER_TIMEOUT=18,
                                             timeout=socket.timeout)
        with mock.patch.object(self.m, 'socket', linux_socket):
            self.assertTrue(self.m._set_tcp_user_timeout(Sock(), 10))
        self.assertEqual(calls, [(socket.IPPROTO_TCP, 18, 10000)])

        calls.clear()
        mac_socket = types.SimpleNamespace(IPPROTO_TCP=socket.IPPROTO_TCP, timeout=socket.timeout)
        with mock.patch.object(self.m, 'socket', mac_socket):
            self.assertFalse(self.m._set_tcp_user_timeout(Sock(), 10))
        self.assertEqual(calls, [])

        class Refusing:
            def setsockopt(self, *args):
                raise OSError(92, 'Protocol not available')
        with mock.patch.object(self.m, 'socket', linux_socket):
            self.assertFalse(self.m._set_tcp_user_timeout(Refusing(), 10))

    @unittest.skipUnless(hasattr(socket, 'TCP_USER_TIMEOUT'), 'TCP_USER_TIMEOUT is Linux-only')
    def test_tcp_user_timeout_on_a_real_socket(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(s.close)
        self.assertTrue(self.m._set_tcp_user_timeout(s, 10))
        self.assertEqual(s.getsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT), 10000)

    # -- end to end over loopback, with the 10 s shortened to 0.5 s
    def start_server(self):
        patcher = mock.patch.object(self.m.MjpegHandler, 'timeout', 0.5)
        patcher.start()
        self.addCleanup(patcher.stop)
        server = self.m.ThreadedHTTPServer(('127.0.0.1', 0), self.m.MjpegHandler)
        threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server.server_address[1]

    def start_camera(self, frame_size):
        """Keep publishing big frames into the topic until the test ends."""
        st = self.m.get_topic(self.TOPIC)
        stop = threading.Event()
        frame = b'\xff\xd8' + b'x' * frame_size + b'\xff\xd9'

        def run():
            while not stop.is_set():
                st.store.put(frame)
                stop.wait(0.01)
        threading.Thread(target=run, daemon=True).start()
        self.addCleanup(stop.set)
        return st

    def connect(self, port, rcvbuf=None):
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if rcvbuf:
            c.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
        c.connect(('127.0.0.1', port))
        self.addCleanup(c.close)
        c.sendall(('GET /stream?topic=%s&fps=15 HTTP/1.0\r\n\r\n' % self.TOPIC).encode())
        return c

    def wait_for(self, cond, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cond():
                return True
            time.sleep(0.02)
        return cond()

    def test_client_that_stops_reading_is_dropped(self):
        port = self.start_server()
        st = self.start_camera(256 * 1024)
        self.connect(port, rcvbuf=4096)                # ...and never read a byte
        self.assertTrue(self.wait_for(lambda: st.clients == 1, 5), 'viewer never registered')
        self.assertTrue(self.wait_for(lambda: st.clients == 0, 10),
                        'a client that accepts no data must be dropped after the handler timeout')
        log = '\n'.join(self.node.get_logger().lines)
        self.assertIn('clients=0', log)
        self.assertIn('timeout', log)
        # and its subscription is released 10 s later like any other
        self.clock.t += 10
        self.sweep()
        self.assertEqual(len(self.node.destroyed), 1)

    def test_client_gone_before_the_headers_is_not_counted(self):
        port = self.start_server()
        st = self.m.get_topic(self.TOPIC)

        def peer_gone(handler):
            raise BrokenPipeError(32, 'Broken pipe')
        with mock.patch.object(self.m.MjpegHandler, 'end_headers', peer_gone):
            self.connect(port)
            self.assertTrue(self.wait_for(lambda: len(self.node.created) == 1, 5), 'never subscribed')
            self.assertTrue(self.wait_for(lambda: st.clients == 0, 5),
                            'a viewer whose headers could not be sent stays counted forever')

    def test_client_that_keeps_reading_stays(self):
        port = self.start_server()
        st = self.start_camera(64 * 1024)
        c = self.connect(port)
        got = bytearray()
        deadline = time.monotonic() + 1.5              # 3x the shortened timeout
        c.settimeout(0.5)
        while time.monotonic() < deadline:
            try:
                chunk = c.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            got += chunk
        self.assertEqual(st.clients, 1)
        self.assertTrue(got.startswith(b'HTTP/1.0 200'), bytes(got[:40]))
        self.assertIn(b'--frame\r\nContent-Type: image/jpeg\r\n', got)
        c.close()
        self.assertTrue(self.wait_for(lambda: st.clients == 0, 5))


if __name__ == '__main__':
    unittest.main()
