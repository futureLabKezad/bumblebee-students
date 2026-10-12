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

"""Tests for scripts/fcu_detect.py (MAVLink baud detection).

    python3 -m unittest test/test_fcu_detect.py
"""
import contextlib
import importlib.util
import io
import os
import random
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'fcu_detect', os.path.join(os.path.dirname(HERE), 'scripts', 'fcu_detect.py'))
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)


def heartbeat_v2(seq=0, sysid=1, signed=False):
    payload = bytes([0, 0, 0, 0, 2, 12, 81, 3, 3])
    hdr = bytes([0xFD, len(payload), 1 if signed else 0, 0, seq, sysid, 1, 0, 0, 0])
    crc = fd.x25(hdr[1:] + payload + bytes([50]))
    return hdr + payload + bytes([crc & 0xFF, crc >> 8]) + (bytes(13) if signed else b'')


def attitude_v1(seq=0):
    payload = bytes(28)
    hdr = bytes([0xFE, len(payload), seq, 1, 1, 30])
    crc = fd.x25(hdr[1:] + payload + bytes([39]))
    return hdr + payload + bytes([crc & 0xFF, crc >> 8])


def garbage(n, seed=1):
    rnd = random.Random(seed)
    return bytes(rnd.randrange(256) for _ in range(n))


class Frames(unittest.TestCase):
    def test_checksum_matches_reference(self):
        self.assertEqual(fd.x25(b'123456789'), 0x6F91)   # CRC-16/MCRF4XX check value

    def test_counts_v2_v1_and_signed_frames_in_noise(self):
        buf = garbage(300) + heartbeat_v2(1) + garbage(50, 2) + attitude_v1() + heartbeat_v2(2, signed=True)
        self.assertEqual(fd.count_frames(buf), (3, 2))

    def test_noise_is_not_mavlink(self):
        # Wrong-baud reads look like this; 64 KB of noise must never pass.
        for seed in range(5):
            self.assertFalse(fd.looks_like_mavlink(garbage(65536, seed)))

    def test_truncated_frame_is_ignored(self):
        self.assertEqual(fd.count_frames(heartbeat_v2()[:-1]), (0, 0))


class Urls(unittest.TestCase):
    def test_parse_serial_urls(self):
        self.assertEqual(fd.parse_serial_url('/dev/ttyAMA0:115200'), ('/dev/ttyAMA0', 115200))
        self.assertEqual(fd.parse_serial_url('serial:///dev/ttyACM0:57600'), ('/dev/ttyACM0', 57600))
        self.assertIsNone(fd.parse_serial_url('udp://:14540@127.0.0.1:14557'))
        self.assertIsNone(fd.parse_serial_url(''))

    def test_configured_url_from_params(self):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
            f.write('mavros:\n  ros__parameters:\n    fcu_url: /dev/ttyAMA0:115200\n'
                    '    gcs_url: tcp-l://0.0.0.0:5760\n')
        try:
            self.assertEqual(fd.configured_url(f.name), '/dev/ttyAMA0:115200')
        finally:
            os.unlink(f.name)

    def test_candidates_try_remembered_then_configured_first(self):
        c = fd.candidates(921600, 115200)
        self.assertEqual(c[:2], [921600, 115200])
        self.assertEqual(len(c), len(set(c)))
        self.assertEqual(fd.candidates(None, 115200)[0], 115200)


class Detect(unittest.TestCase):
    def fake_fc(self, true_baud, unsupported=()):
        calls = []

        def listen(baud, seconds):
            calls.append(baud)
            if baud in unsupported:
                return None
            if baud == true_baud:
                return garbage(40) + b''.join(heartbeat_v2(i) for i in range(3))
            return garbage(2000, baud)
        return listen, calls

    def test_finds_the_rate_the_flight_controller_uses(self):
        listen, calls = self.fake_fc(921600)
        self.assertEqual(fd.detect(listen, fd.candidates(None, 115200), 1.0, 1), 921600)
        self.assertEqual(calls[:2], [115200, 921600])

    def test_silent_line_stops_the_search(self):
        calls = []

        def listen(baud, seconds):
            calls.append(baud)
            return b''
        self.assertIsNone(fd.detect(listen, fd.candidates(None, 115200), 1.0, 2))
        self.assertEqual(len(calls), 1)

    def test_unsupported_rate_is_skipped_not_taken_for_silence(self):
        listen, calls = self.fake_fc(57600, unsupported=(921600,))
        self.assertEqual(fd.detect(listen, [921600, 115200, 57600], 1.0, 1), 57600)

    def test_no_mavlink_anywhere(self):
        listen, _ = self.fake_fc(None)
        self.assertIsNone(fd.detect(listen, fd.candidates(None, 115200), 1.0, 1))


class Main(unittest.TestCase):
    """End to end on a pseudo-terminal standing in for the UART."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.params = os.path.join(self.tmp.name, 'mavros_params.yaml')
        self.cache = os.path.join(self.tmp.name, 'cache', 'fcu_url')

    def tearDown(self):
        self.tmp.cleanup()

    def write_params(self, url):
        with open(self.params, 'w') as f:
            f.write('mavros:\n  ros__parameters:\n    fcu_url: %s\n' % url)

    def run_main(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = fd.main(['--params', self.params, '--cache', self.cache, '--window', '0.4', *extra])
        return rc, out.getvalue().strip()

    def test_missing_device_prints_configured_url(self):
        self.write_params('/dev/nonexistent-uart:115200')
        self.assertEqual(self.run_main(), (2, '/dev/nonexistent-uart:115200'))

    def test_non_serial_url_is_passed_through(self):
        self.write_params('udp://:14540@127.0.0.1:14557')
        self.assertEqual(self.run_main(), (2, 'udp://:14540@127.0.0.1:14557'))

    def test_detects_on_a_live_port_and_remembers_it(self):
        master, slave = os.openpty()
        dev = os.ttyname(slave)
        self.write_params('%s:115200' % dev)
        stop = threading.Event()

        def flight_controller():
            seq = 0
            while not stop.is_set():
                os.write(master, heartbeat_v2(seq % 256) + attitude_v1(seq % 256))
                seq += 1
                time.sleep(0.05)
        t = threading.Thread(target=flight_controller, daemon=True)
        t.start()
        try:
            rc, url = self.run_main()
        finally:
            stop.set()
            t.join()
            os.close(master)
            os.close(slave)
        self.assertEqual((rc, url), (0, '%s:115200' % dev))
        with open(self.cache) as f:
            self.assertEqual(f.read().strip(), url)

    def test_silent_port_falls_back_to_the_remembered_rate(self):
        master, slave = os.openpty()
        dev = os.ttyname(slave)
        self.write_params('%s:115200' % dev)
        os.makedirs(os.path.dirname(self.cache))
        with open(self.cache, 'w') as f:
            f.write('%s:921600\n' % dev)
        try:
            rc, url = self.run_main()
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual((rc, url), (3, '%s:921600' % dev))


if __name__ == '__main__':
    unittest.main()
