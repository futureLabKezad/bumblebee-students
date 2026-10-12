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

"""Tests for scripts/ros_watchdog.py.

    python3 -m unittest test/test_ros_watchdog.py
"""
import importlib.util
import json
import os
import socket
import struct
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'ros_watchdog', os.path.join(os.path.dirname(HERE), 'scripts', 'ros_watchdog.py'))
wdm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wdm)

G, F, B = wdm.GRACE_S, wdm.FAIL_S, wdm.BACKOFF_S


class Decisions(unittest.TestCase):
    def test_startup_is_never_judged(self):
        wd = wdm.Watchdog(0)
        self.assertEqual(wd.step(500, None, False, 'disarmed'), 'ok')       # stack not running
        self.assertEqual(wd.step(600, G - 1, False, 'disarmed'), 'ok')      # just started

    def test_restart_after_fail_window_when_disarmed(self):
        wd = wdm.Watchdog(0)
        self.assertEqual(wd.step(100, G + 100, True, 'unknown'), 'ok')
        self.assertEqual(wd.step(100 + F - 1, G + 200, False, 'disarmed'), 'wait')
        self.assertEqual(wd.step(100 + F + 1, G + 200, False, 'disarmed'), 'restart')

    def test_never_restarts_when_armed_or_unknown(self):
        for fcu in ('armed', 'unknown'):
            wd = wdm.Watchdog(0)
            self.assertEqual(wd.step(1000, G + 1000, False, fcu), 'wait', fcu)
            self.assertEqual(wd.step(5000, G + 5000, False, fcu), 'wait', fcu)

    def test_backoff_between_restarts(self):
        wd = wdm.Watchdog(0)
        self.assertEqual(wd.step(F + 1, G + 100, False, 'disarmed'), 'restart')
        t = F + 1
        # the restarted stack is past its grace period but still broken
        self.assertEqual(wd.step(t + F + 1, G + 100, False, 'disarmed'), 'wait')
        self.assertEqual(wd.step(t + B + 1, G + 100, False, 'disarmed'), 'restart')

    def test_gives_up_after_max_restarts(self):
        wd = wdm.Watchdog(0)
        t, results = 0, []
        for _ in range(wdm.MAX_RESTARTS + 2):
            t += B + F + 10
            results.append(wd.step(t, G + t, False, 'disarmed'))
        self.assertEqual(results.count('restart'), wdm.MAX_RESTARTS)
        self.assertEqual(results[-1], 'give_up')

    def test_recovery_resets_the_fail_window(self):
        wd = wdm.Watchdog(0)
        wd.step(F - 5, G + 100, False, 'disarmed')
        wd.step(F, G + 100, True, 'unknown')
        self.assertEqual(wd.step(F + 10, G + 100, False, 'disarmed'), 'wait')


class FakeRosbridge:
    """Minimal websocket server: answers the handshake, then publishes
    /mavros/state once the client subscribes (or stays silent)."""

    def __init__(self, deliver):
        self.deliver = deliver
        self.srv = socket.socket()
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            c, _ = self.srv.accept()
            buf = b''
            while b'\r\n\r\n' not in buf:
                buf += c.recv(4096)
            c.sendall(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n'
                      b'Connection: Upgrade\r\nSec-WebSocket-Accept: x\r\n\r\n')
            c.recv(4096)                                   # the subscribe frame
            if self.deliver:
                p = json.dumps({'op': 'publish', 'topic': '/mavros/state',
                                'msg': {'connected': True, 'armed': False}}).encode()
                c.sendall(bytes([0x81, 126]) + struct.pack('>H', len(p)) + p
                          if len(p) >= 126 else bytes([0x81, len(p)]) + p)
            threading.Event().wait(2)
            c.close()
        except OSError:
            pass


class Probe(unittest.TestCase):
    def test_state_arrives(self):
        self.assertTrue(wdm.state_arrives('127.0.0.1', FakeRosbridge(True).port, timeout=1.5))

    def test_silent_rosbridge(self):
        self.assertFalse(wdm.state_arrives('127.0.0.1', FakeRosbridge(False).port, timeout=1.0))

    def test_nothing_listening(self):
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        self.assertFalse(wdm.state_arrives('127.0.0.1', port, timeout=0.5))


if __name__ == '__main__':
    unittest.main()
