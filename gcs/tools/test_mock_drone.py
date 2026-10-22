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

"""Tests for the mock drone's flight-controller states.

    python3 gcs/tools/test_mock_drone.py

The state logic is tested everywhere. The end-to-end test (real wifi_manager.py
behind the mock, rosbridge stub, control API) needs tornado and bcrypt and
free ports 8765/8888/9090/8799; it is skipped when tornado is missing,
unless MOCK_E2E_REQUIRED=1 (CI), where a skip becomes a failure.
"""
import json
import os
import socket
import subprocess
import sys
import time
import types
import unittest
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import tornado  # noqa: F401
    HAVE_TORNADO = True
except ImportError:
    HAVE_TORNADO = False
    # Enough of tornado for mock_drone to import; only the pure logic is used.
    t = types.ModuleType('tornado')
    for sub in ('ioloop', 'web', 'websocket'):
        m = types.ModuleType('tornado.' + sub)
        setattr(t, sub, m)
        sys.modules['tornado.' + sub] = m
    t.web.RequestHandler = object
    t.websocket.WebSocketHandler = object
    sys.modules['tornado'] = t

import mock_drone as md  # noqa: E402


class States(unittest.TestCase):
    def setUp(self):
        md.set_state(fcu='disarmed', telemetry='normal', battery='ok')

    def test_disarmed(self):
        st = md.fcu_status()
        self.assertTrue(st['connected'] and st['ok'])
        self.assertFalse(st['armed'])
        self.assertEqual(md.telemetry('/mavros/state', 0), {'connected': True, 'armed': False, 'mode': 'POSCTL'})

    def test_armed(self):
        md.set_state(fcu='armed')
        st = md.fcu_status()
        self.assertTrue(st['armed'] and st['connected'])
        self.assertEqual(md.telemetry('/mavros/state', 0)['mode'], 'OFFBOARD')

    def test_stale_keeps_last_armed_and_stops_state(self):
        md.set_state(fcu='armed')
        md.set_state(fcu='stale')
        st = md.fcu_status()
        self.assertFalse(st['ok'] or st['connected'])
        self.assertTrue(st['armed'], 'stale must keep the last known armed flag, like drone.py')
        self.assertIsNone(md.telemetry('/mavros/state', 0))

    def test_lost(self):
        md.set_state(fcu='lost')
        st = md.fcu_status()
        self.assertTrue(st['ok'])
        self.assertFalse(st['connected'] or st['armed'])
        self.assertEqual(md.telemetry('/mavros/state', 0), {'connected': False, 'armed': False, 'mode': ''})

    def test_low_battery(self):
        md.set_state(battery='low')
        self.assertEqual(md.telemetry('/mavros/battery', 0)['percentage'], 0.12)

    def test_bad_values_are_refused(self):
        self.assertIsNotNone(md.set_state(fcu='flying'))
        self.assertIsNotNone(md.set_state(color='red'))
        self.assertEqual(md.STATE['fcu'], 'disarmed', 'a refused change must not apply')


def _free(port):
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) != 0


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


# CI sets MOCK_E2E_REQUIRED=1 so these tests can never be skipped silently there.
REQUIRED = os.environ.get('MOCK_E2E_REQUIRED') == '1'


@unittest.skipUnless(HAVE_TORNADO or REQUIRED, 'tornado not installed')
class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_TORNADO:
            raise RuntimeError('MOCK_E2E_REQUIRED=1 but tornado is not installed')
        busy = [p for p in (8765, 8888, 9090, 8799) if not _free(p)]
        if busy:
            if REQUIRED:
                raise RuntimeError('ports in use: %s' % busy)
            raise unittest.SkipTest('ports in use: %s' % busy)
        cls.proc = subprocess.Popen([sys.executable, os.path.join(HERE, 'mock_drone.py'), '--host', '127.0.0.1'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 15
        while time.time() < deadline:
            if not _free(8765) and not _free(8799) and not _free(9090):
                return
            time.sleep(0.2)
        cls.proc.kill()
        raise RuntimeError('mock drone did not start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)

    def test_real_backend_sees_each_state(self):
        expect = {'disarmed': (True, False), 'armed': (True, True), 'stale': (False, True), 'lost': (False, False)}
        _get('http://127.0.0.1:8799/mock/set?fcu=disarmed')
        for fcu, (connected, armed) in expect.items():
            _get('http://127.0.0.1:8799/mock/set?fcu=' + fcu)
            st = _get('http://127.0.0.1:8765/api/fcu/status')
            self.assertEqual((st['connected'], st['armed']), (connected, armed), fcu)

    def test_bad_control_value_is_400(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            _get('http://127.0.0.1:8799/mock/set?fcu=flying')
        self.assertEqual(e.exception.code, 400)

    @staticmethod
    def _post(path, body):
        req = urllib.request.Request('http://127.0.0.1:8765' + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_real_backend_refuses_like_the_drone(self):
        # wifi_manager.py's "unknown = armed" rule, driven by the mock's FC state
        silent = {'tune': 'MFT255L64P64'}
        _get('http://127.0.0.1:8799/mock/set?fcu=armed')
        code, body = self._post('/api/sounds/play', silent)
        self.assertEqual((code, body['code']), (409, 'armed'))
        # disarmed for a while, then the FC link drops: that is "unknown", not
        # "armed", because the backend polls the FC state every second as on
        # the drone (a link lost while still armed would stay "armed")
        _get('http://127.0.0.1:8799/mock/set?fcu=disarmed')
        time.sleep(1.5)
        _get('http://127.0.0.1:8799/mock/set?fcu=lost')
        code, body = self._post('/api/sounds/play', silent)
        self.assertEqual((code, body['code']), (503, 'fc_unknown'))
        _get('http://127.0.0.1:8799/mock/set?fcu=disarmed')
        self.assertEqual(self._post('/api/sounds/play', silent), (200, {'ok': True}))

    def test_freeze_stops_rosbridge_publications(self):
        import datetime
        from tornado import gen
        from tornado.ioloop import IOLoop
        from tornado.websocket import websocket_connect

        async def count(seconds):
            ws = await websocket_connect('ws://127.0.0.1:9090/')
            ws.write_message(json.dumps({'op': 'subscribe', 'topic': '/mavros/state'}))
            n, end = 0, time.monotonic() + seconds
            pending = None
            while time.monotonic() < end:
                pending = pending or ws.read_message()
                try:
                    msg = await gen.with_timeout(datetime.timedelta(seconds=0.3), pending)
                    pending = None
                except gen.TimeoutError:
                    continue
                if msg:
                    n += 1
            ws.close()
            return n

        _get('http://127.0.0.1:8799/mock/set?fcu=disarmed&telemetry=normal')
        self.assertGreater(IOLoop.current().run_sync(lambda: count(1.5)), 0)
        _get('http://127.0.0.1:8799/mock/set?telemetry=freeze')
        self.assertEqual(IOLoop.current().run_sync(lambda: count(1.5)), 0)
        _get('http://127.0.0.1:8799/mock/set?telemetry=normal')



@unittest.skipUnless(HAVE_TORNADO or REQUIRED, 'tornado not installed')
class Shutdown(unittest.TestCase):
    def test_sigterm_also_stops_the_metrics_server(self):
        if not HAVE_TORNADO:
            raise RuntimeError('MOCK_E2E_REQUIRED=1 but tornado is not installed')
        if not all(_free(p) for p in (8765, 8888, 9090, 8799)):
            self.skipTest('ports in use') if not REQUIRED else self.fail('ports in use')
        proc = subprocess.Popen([sys.executable, os.path.join(HERE, 'mock_drone.py'), '--host', '127.0.0.1'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 15
            while _free(8888) and time.time() < deadline:
                time.sleep(0.2)
            self.assertFalse(_free(8888), 'metrics server did not start')
        finally:
            proc.terminate()
            proc.wait(timeout=10)
        deadline = time.time() + 5
        while not _free(8888) and time.time() < deadline:
            time.sleep(0.2)
        self.assertTrue(_free(8888), 'sys_metrics.py kept running after the mock was stopped')


if __name__ == '__main__':
    unittest.main()
