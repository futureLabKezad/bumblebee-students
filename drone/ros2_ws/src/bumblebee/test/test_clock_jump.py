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

"""Tests for scripts/fcu_armed.py and scripts/clock_jump.sh.

    python3 -m unittest test/test_clock_jump.py
"""
import importlib.util
import os
import shutil
import socket
import stat
import struct
import subprocess
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), 'scripts')
spec = importlib.util.spec_from_file_location('fcu_armed', os.path.join(SCRIPTS, 'fcu_armed.py'))
fa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fa)
x25 = fa.fcu_detect.x25


def heartbeat(base_mode, sysid=1, compid=1, mav_type=2, autopilot=12):
    payload = struct.pack('<IBBBBB', 0, mav_type, autopilot, base_mode, 3, 3)
    payload = payload.rstrip(b'\x00') or b'\x00'          # MAVLink v2 trims trailing zeros
    hdr = bytes([0xFD, len(payload), 0, 0, 7, sysid, compid, 0, 0, 0])
    crc = x25(hdr[1:] + payload + bytes([50]))
    return hdr + payload + struct.pack('<H', crc)


def attitude():
    payload = bytes(28)
    hdr = bytes([0xFD, len(payload), 0, 0, 1, 1, 1, 30, 0, 0])
    crc = x25(hdr[1:] + payload + bytes([39]))
    return hdr + payload + struct.pack('<H', crc)


class Heartbeats(unittest.TestCase):
    def test_autopilot_states(self):
        self.assertEqual(fa.autopilot_heartbeats(heartbeat(29)), [29])            # 20EC on the desk
        self.assertEqual(fa.autopilot_heartbeats(attitude() + heartbeat(29 | 0x80)), [29 | 0x80])

    def test_mavros_own_heartbeat_is_ignored(self):
        # relayed on tcp 5760 with base_mode 192 (looks armed): not the autopilot
        mavros = heartbeat(192, compid=191, mav_type=18, autopilot=8)
        self.assertEqual(fa.autopilot_heartbeats(mavros + heartbeat(29)), [29])
        self.assertEqual(fa.autopilot_heartbeats(mavros), [])

    def test_corrupt_frame_is_ignored(self):
        bad = bytearray(heartbeat(29 | 0x80))
        bad[-1] ^= 0xFF
        self.assertEqual(fa.autopilot_heartbeats(bytes(bad)), [])


class FakeGcsPort:
    """Stands in for MAVROS's tcp 5760: sends `stream` to each client."""

    def __init__(self, stream):
        self.srv = socket.socket()
        self.srv.bind(('127.0.0.1', 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.stream = stream
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        try:
            c, _ = self.srv.accept()
            c.sendall(self.stream)
            threading.Event().wait(1.5)
            c.close()
        except OSError:
            pass


class State(unittest.TestCase):
    def test_disarmed_armed_unknown(self):
        self.assertEqual(fa.state(port=FakeGcsPort(attitude() + heartbeat(29)).port, seconds=1), 'disarmed')
        self.assertEqual(fa.state(port=FakeGcsPort(heartbeat(29 | 0x80)).port, seconds=1), 'armed')
        self.assertEqual(fa.state(port=FakeGcsPort(attitude() * 5).port, seconds=1), 'unknown')

    def test_nothing_listening_is_unknown(self):
        s = socket.socket()
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
        s.close()
        self.assertEqual(fa.state(port=port, seconds=0.5), 'unknown')


class ClockJump(unittest.TestCase):
    """clock_jump.sh with systemctl/pgrep and fcu_armed.py stubbed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.bin = os.path.join(d, 'bin')
        self.scripts = os.path.join(d, 'scripts')
        os.mkdir(self.bin)
        os.mkdir(self.scripts)
        shutil.copy(os.path.join(SCRIPTS, 'clock_jump.sh'), self.scripts)
        with open(os.path.join(self.scripts, 'fcu_armed.py'), 'w') as f:
            f.write('import os\nprint(os.environ.get("FAKE_FCU", "unknown"))\n')
        stubs = {
            'systemctl': '#!/bin/bash\necho "$*" >> "$D/systemctl.log"\n',
            'pgrep': '#!/bin/bash\n[ -n "$FAKE_MAVROS" ]\n',
        }
        for name, body in stubs.items():
            p = os.path.join(self.bin, name)
            with open(p, 'w') as f:
                f.write(body)
            os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.tmp.cleanup()

    def run_jump(self, **env):
        e = dict(os.environ, D=self.tmp.name, PATH=self.bin + os.pathsep + os.environ['PATH'], **env)
        r = subprocess.run(['bash', os.path.join(self.scripts, 'clock_jump.sh')], env=e,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        try:
            with open(os.path.join(self.tmp.name, 'systemctl.log')) as f:
                return r.stdout, f.read().splitlines()
        except FileNotFoundError:
            return r.stdout, []

    def test_disarmed_restarts_everything(self):
        out, calls = self.run_jump(FAKE_MAVROS='1', FAKE_FCU='disarmed')
        self.assertIn('--no-block try-restart notify-manager wifi-manager', calls)
        self.assertIn('--no-block try-restart bumblebee', calls)

    def test_armed_or_unknown_leaves_the_flight_stack_alone(self):
        for fcu in ('armed', 'unknown', ''):
            out, calls = self.run_jump(FAKE_MAVROS='1', FAKE_FCU=fcu)
            self.assertNotIn('--no-block try-restart bumblebee', calls, fcu)
            self.assertIn('NOT restarted', out)
            os.remove(os.path.join(self.tmp.name, 'systemctl.log'))

    def test_stack_not_running_yet_only_restarts_the_helpers(self):
        out, calls = self.run_jump(FAKE_FCU='disarmed')
        self.assertEqual(calls, ['--no-block try-restart notify-manager wifi-manager'])


if __name__ == '__main__':
    unittest.main()
