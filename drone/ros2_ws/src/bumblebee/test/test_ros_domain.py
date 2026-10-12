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

"""Tests for scripts/ros_domain.py (per-drone ROS_DOMAIN_ID).

    python3 -m unittest test/test_ros_domain.py
"""
import contextlib
import importlib.util
import io
import os
import socket
import struct
import tempfile
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'ros_domain', os.path.join(os.path.dirname(HERE), 'scripts', 'ros_domain.py'))
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)

MAC = '88:a2:9e:57:20:ec'


def txt_rdata(items):
    return b''.join(bytes([len(s)]) + s.encode() for s in items)


def response(qid, question_name, qtype, records):
    """DNS response echoing the question; records = [(name|None, type, rdata)],
    name None = compression pointer to the question name (offset 12)."""
    msg = struct.pack('!HHHHHH', qid, 0x8400, 1, len(records), 0, 0)
    msg += rd.encode_name(question_name) + struct.pack('!HH', qtype, 1)
    for name, rtype, rdata in records:
        msg += (b'\xc0\x0c' if name is None else rd.encode_name(name))
        msg += struct.pack('!HHIH', rtype, 1, 10, len(rdata)) + rdata
    return msg


class FakeDrones:
    """Answers legacy-unicast mDNS queries like avahi on other drones would."""

    def __init__(self, drones):
        self.drones = drones          # id -> domain
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', 0))
        self.addr = self.sock.getsockname()
        self.stop = False
        self.t = threading.Thread(target=self.run, daemon=True)
        self.t.start()

    def inst(self, i):
        return 'bumblebee-%s.%s' % (i.lower(), rd.SERVICE)

    def run(self):
        self.sock.settimeout(0.1)
        while not self.stop:
            try:
                msg, peer = self.sock.recvfrom(9000)
            except socket.timeout:
                continue
            qid, _, qd = struct.unpack('!HHH', msg[:6])
            name, off = rd.read_name(msg, 12)
            qtype = struct.unpack('!H', msg[off:off + 2])[0]
            if qtype == rd.TYPE_PTR:
                # PTR answers only -- the client must ask for TXT itself
                recs = [(None, rd.TYPE_PTR, rd.encode_name(self.inst(i))) for i in self.drones]
                self.sock.sendto(response(qid, name, qtype, recs), peer)
            elif qtype == rd.TYPE_TXT:
                off = 12
                for _ in range(qd):
                    qname, off = rd.read_name(msg, off)
                    off += 4
                    for i, d in self.drones.items():
                        if qname == self.inst(i):
                            rec = [(None, rd.TYPE_TXT, txt_rdata(['name=Bumblebee-' + i, 'id=' + i, 'ros_domain=%d' % d]))]
                            self.sock.sendto(response(qid, qname, qtype, rec), peer)

    def close(self):
        self.stop = True
        self.t.join()
        self.sock.close()


class Choice(unittest.TestCase):
    def test_preferred_is_stable_and_in_range(self):
        d = rd.preferred(MAC)
        self.assertEqual(d, rd.preferred(MAC.upper()))
        self.assertTrue(rd.FIRST <= d <= rd.LAST)
        self.assertNotEqual(d, 0)          # 0 stays the ROS default for laptops

    def test_no_rival_keeps_domain(self):
        self.assertEqual(rd.choose(37, '20EC', {'20EC': 37, '3009': 12}, MAC), 37)

    def test_the_drone_that_sees_the_clash_moves(self):
        # whatever the ids: the other drone may have been running (or flying) for ages
        self.assertNotEqual(rd.choose(37, '20EC', {'3009': 37}, MAC), 37)
        self.assertNotEqual(rd.choose(37, '3009', {'20EC': 37}, MAC), 37)

    def test_move_skips_taken_domains(self):
        taken = {'%04X' % i: d for i, d in enumerate(range(rd.FIRST, rd.LAST))}   # all but LAST
        self.assertEqual(rd.choose(rd.FIRST, 'FFFF', taken, MAC), rd.LAST)

    def test_simultaneous_movers_diverge(self):
        others = {'AAAA': 37}
        a = rd.choose(37, '1111', others, '88:a2:9e:57:20:ec')
        b = rd.choose(37, '2222', others, 'd8:3a:dd:12:ab:cd')
        self.assertNotEqual(a, 37)
        self.assertNotEqual(b, 37)
        self.assertNotEqual(a, b)

    def test_probe_order_visits_every_domain(self):
        for mac in (MAC, 'd8:3a:dd:12:ab:cd', '00:00:00:00:00:00'):
            step, span = rd.probe_step(mac), rd.LAST - rd.FIRST + 1
            seen = {rd.FIRST + (k * step) % span for k in range(span)}
            self.assertEqual(len(seen), span, mac)

    def test_keep_remembers_the_running_domain(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'ros_domain')
            rd.write_state(p, 54, MAC)                # a move picked earlier, deferred
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rd.main(['--mac', MAC, '--id', '20EC', '--state', p, '--keep', '17'])
            self.assertEqual(int(out.getvalue()), 17)
            self.assertEqual(rd.read_state(p, MAC), 17)
            with contextlib.redirect_stdout(io.StringIO()):
                rd.main(['--mac', MAC, '--id', '20EC', '--state', p, '--keep', '0'])   # out of range
            self.assertEqual(rd.read_state(p, MAC), 17)

    def test_state_is_bound_to_the_mac(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'sub', 'ros_domain')
            rd.write_state(p, 42, MAC)
            self.assertEqual(rd.read_state(p, MAC), 42)
            self.assertIsNone(rd.read_state(p, 'aa:bb:cc:dd:ee:ff'))   # card cloned to another drone


class Dns(unittest.TestCase):
    def test_compressed_names_and_txt(self):
        rec = [(None, rd.TYPE_TXT, txt_rdata(['id=20EC', 'ros_domain=37', 'flag']))]
        msg = response(7, 'bumblebee-20ec._bumblebee._tcp.local', rd.TYPE_TXT, rec)
        (name, rtype, off, rdlen), = rd.parse_records(msg)
        self.assertEqual((name, rtype), ('bumblebee-20ec._bumblebee._tcp.local', rd.TYPE_TXT))
        self.assertEqual(rd.txt_dict(msg, off, rdlen), {'id': '20EC', 'ros_domain': '37', 'flag': ''})

    def test_pointer_loop_is_rejected(self):
        msg = struct.pack('!HHHHHH', 1, 0, 0, 0, 0, 0) + b'\xc0\x0c'
        with self.assertRaises(ValueError):
            rd.read_name(msg, 12)


class Browse(unittest.TestCase):
    def setUp(self):
        self._addr = rd.MDNS_ADDR

    def tearDown(self):
        rd.MDNS_ADDR = self._addr

    def test_finds_other_drones_domains(self):
        fake = FakeDrones({'3009': 12, 'A1B2': 77})
        rd.MDNS_ADDR = fake.addr
        try:
            self.assertEqual(rd.browse(seconds=0.5), {'3009': 12, 'A1B2': 77})
        finally:
            fake.close()

    def test_main_moves_off_a_taken_domain_and_remembers(self):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, 'ros_domain')
            mine = rd.preferred(MAC)
            fake = FakeDrones({'0001': mine})          # a drone already uses our domain
            rd.MDNS_ADDR = fake.addr
            out = io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    rd.main(['--mac', MAC, '--id', '20EC', '--state', state, '--browse'])
            finally:
                fake.close()
            moved = int(out.getvalue())
            self.assertNotEqual(moved, mine)
            self.assertEqual(rd.read_state(state, MAC), moved)
            # later boots without a network keep it
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rd.main(['--mac', MAC, '--id', '20EC', '--state', state])
            self.assertEqual(int(out.getvalue()), moved)

    def test_no_answers_keeps_preferred(self):
        silent = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        silent.bind(('127.0.0.1', 0))
        rd.MDNS_ADDR = silent.getsockname()
        try:
            with tempfile.TemporaryDirectory() as d:
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    rd.main(['--mac', MAC, '--id', '20EC', '--state', os.path.join(d, 's'), '--browse'])
                self.assertEqual(int(out.getvalue()), rd.preferred(MAC))
        finally:
            silent.close()


if __name__ == '__main__':
    unittest.main()
