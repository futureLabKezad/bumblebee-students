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

"""Off-drone tests for scripts/wifi_manager.py (the GCS REST API).

nmcli is replaced by a fake, so these run on any machine with tornado and
bcrypt installed:  python3 -m unittest test/test_wifi_manager.py
"""
import importlib.util
import json
import logging
import os
import tempfile
import threading
import time
import unittest

import tornado.gen
from tornado.testing import AsyncHTTPTestCase

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)

# wifi_manager configures file logging under /var/log at import; a handler on
# the root logger turns that basicConfig() into a no-op.
logging.getLogger().addHandler(logging.NullHandler())

_spec = importlib.util.spec_from_file_location(
    'wifi_manager', os.path.join(PKG, 'scripts', 'wifi_manager.py'))
wm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wm)


class FakeNmcli:
    """Records calls; answers the few read queries the handlers make."""

    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()
        self.connections = ['netplan-wlan0-Y', 'Home WiFi', 'Lab:5G', 'Bad Net', wm.HOTSPOT_CONN]
        self.priorities = {'netplan-wlan0-Y': 10, 'Home WiFi': 12, 'Lab:5G': 0, 'Bad Net': 5, wm.HOTSPOT_CONN: 0}
        self.wlan0 = ('connected', wm.HOTSPOT_CONN)

    def __call__(self, *args, timeout=15):
        if args[:1] == ('-w',):          # nmcli -w <secs> ...: record the command itself
            args = args[2:]
        with self.lock:
            self.calls.append(args)
        if args[:2] == ('-g', 'connection.uuid'):
            return 'uuid-' + args[-1]
        if args[:3] == ('con', 'up', 'Bad Net'):
            raise RuntimeError('Error: Connection activation failed: Secrets were required')
        if args[:4] == ('-t', '-f', 'NAME', 'con'):
            # nmcli -t escapes ':' and '\\' inside values
            return '\n'.join(c.replace('\\', '\\\\').replace(':', '\\:') for c in self.connections)
        if args[:4] == ('-t', '-f', 'NAME,TYPE', 'con'):
            return '\n'.join(c.replace(':', '\\:') + ':802-11-wireless' for c in self.connections)
        if args[:4] == ('-t', '-f', 'TYPE,AUTOCONNECT-PRIORITY', 'con'):
            return '\n'.join('802-11-wireless:%d' % p for p in self.priorities.values())
        if args[:4] == ('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device'):
            return 'wlan0:%s:%s\neth0:unavailable:' % self.wlan0
        if args[:4] == ('-t', '-f', 'IP4.ADDRESS', 'device'):
            return 'IP4.ADDRESS[1]:10.42.0.1/24'
        if 'IN-USE,SSID,SIGNAL,SECURITY,FREQ' in args:
            return '*:Lab\\:5G:80:WPA2:2437 MHz\n:Home WiFi:55:WPA2:5180 MHz'
        if 'list' in args:
            return '*:77:Bumblebee-ABCD'
        return ''

    def called(self, *prefix):
        with self.lock:
            return [c for c in self.calls if c[:len(prefix)] == prefix]


class WifiManagerTest(AsyncHTTPTestCase):
    def setUp(self):
        self.fake = FakeNmcli()
        self.tmp = tempfile.TemporaryDirectory()
        self._orig = (wm.nmcli, wm.WIFI_SWITCH_MARKER, wm.SWITCH_DELAY_S, wm.HOTSPOT_PIN_MARKER,
                      wm.WIFI_FAILED_LOG, wm._hotspot_ssid)
        wm.WIFI_FAILED_LOG = os.path.join(self.tmp.name, 'failed')
        wm._hotspot_ssid = lambda: 'Bumblebee-ABCD'
        wm.nmcli = self.fake
        wm.WIFI_SWITCH_MARKER = os.path.join(self.tmp.name, 'switch')
        wm.HOTSPOT_PIN_MARKER = os.path.join(self.tmp.name, 'pinned')
        wm.SWITCH_DELAY_S = 0.2
        super().setUp()

    def tearDown(self):
        super().tearDown()
        (wm.nmcli, wm.WIFI_SWITCH_MARKER, wm.SWITCH_DELAY_S, wm.HOTSPOT_PIN_MARKER,
         wm.WIFI_FAILED_LOG, wm._hotspot_ssid) = self._orig
        self.tmp.cleanup()

    def get_app(self):
        return wm.make_app()

    def post(self, path, body, method='POST'):
        return self.fetch(path, method=method, body=json.dumps(body),
                          allow_nonstandard_methods=True)

    def wait_for(self, pred, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pred():
                return True
            time.sleep(0.02)
        return False

    # -- apply-now: the reply must not wait for the link change ------------

    def test_apply_now_replies_before_switching(self):
        resp = self.post('/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.assertEqual(resp.code, 200)
        self.assertEqual(json.loads(resp.body), {'ok': True})
        self.assertEqual(self.fake.called('con', 'up'), [],
                         'link switched before the reply was sent')
        self.assertTrue(os.path.exists(wm.WIFI_SWITCH_MARKER))
        self.assertTrue(self.wait_for(lambda: self.fake.called('con', 'up', 'Home WiFi')))

    def test_apply_now_profile_name_with_colon(self):
        resp = self.post('/api/wifi/apply-now', {'ssid': 'Lab:5G'})
        self.assertEqual(resp.code, 200)
        self.assertTrue(self.wait_for(lambda: self.fake.called('con', 'up', 'Lab:5G')))

    def test_networks_lists_unescaped_names(self):
        names = [n['name'] for n in json.loads(self.fetch('/api/wifi/networks').body)]
        self.assertIn('Lab:5G', names)
        self.assertNotIn(wm.HOTSPOT_CONN, names)

    def test_apply_now_clears_hotspot_pin(self):
        open(wm.HOTSPOT_PIN_MARKER, 'w').close()
        self.post('/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.assertFalse(os.path.exists(wm.HOTSPOT_PIN_MARKER))

    def test_save_gives_new_network_top_priority(self):
        resp = self.post('/api/wifi/save', {'ssid': 'Classroom', 'password': 'x' * 8})
        self.assertEqual(resp.code, 200)
        prio = [c for c in self.fake.calls if 'connection.autoconnect-priority' in c][-1]
        self.assertEqual(prio[-1], '13')   # one above the current max (12)

    def test_failed_join_brings_hotspot_back(self):
        resp = self.post('/api/wifi/apply-now', {'ssid': 'Bad Net'})
        self.assertEqual(resp.code, 200)
        self.assertTrue(self.wait_for(lambda: self.fake.called('connection', 'up', wm.HOTSPOT_CONN)))
        with open(wm.WIFI_FAILED_LOG) as f:
            self.assertTrue(f.read().startswith('uuid-Bad Net '))
        self.assertFalse(os.path.exists(wm.WIFI_SWITCH_MARKER))

    def test_scan_unescapes_ssids(self):
        nets = json.loads(self.fetch('/api/wifi/scan').body)
        self.assertEqual([n['ssid'] for n in nets][:1], ['Home WiFi'])   # 5 GHz first
        self.assertIn('Lab:5G', [n['ssid'] for n in nets])

    def test_apply_now_unknown_network(self):
        resp = self.post('/api/wifi/apply-now', {'ssid': 'Nope'})
        self.assertEqual(resp.code, 404)
        time.sleep(0.3)
        self.assertEqual(self.fake.called('con', 'up'), [])

    def test_apply_now_requires_ssid(self):
        self.assertEqual(self.post('/api/wifi/apply-now', {}).code, 400)

    # -- mode switch ---------------------------------------------------------

    def test_mode_hotspot_replies_then_switches(self):
        self.fake.wlan0 = ('connected', 'Home WiFi')
        resp = self.post('/api/wifi/mode', {'mode': 'hotspot'})
        self.assertEqual(resp.code, 200)
        self.assertEqual(json.loads(resp.body), {'ok': True, 'mode': 'hotspot'})
        self.assertTrue(self.wait_for(
            lambda: self.fake.called('connection', 'up', wm.HOTSPOT_CONN)))

    def test_hotspot_mode_is_pinned_until_client_mode(self):
        self.fake.wlan0 = ('connected', 'Home WiFi')
        self.post('/api/wifi/mode', {'mode': 'hotspot'})
        self.assertTrue(os.path.exists(wm.HOTSPOT_PIN_MARKER))
        self.fake.wlan0 = ('connected', wm.HOTSPOT_CONN)
        self.post('/api/wifi/mode', {'mode': 'client'})
        self.assertFalse(os.path.exists(wm.HOTSPOT_PIN_MARKER))

    def test_mode_client_from_hotspot(self):
        resp = self.post('/api/wifi/mode', {'mode': 'client'})
        self.assertEqual(resp.code, 200)
        self.assertTrue(self.wait_for(
            lambda: self.fake.called('connection', 'down', wm.HOTSPOT_CONN)))

    def test_mode_rejects_garbage(self):
        self.assertEqual(self.post('/api/wifi/mode', {'mode': 'x'}).code, 400)

    # -- status / misc -------------------------------------------------------

    def test_status_contract_and_no_rescan(self):
        resp = self.fetch('/api/wifi/status')
        self.assertEqual(resp.code, 200)
        self.assertEqual(json.loads(resp.body),
                         {'mode': 'hotspot', 'ssid': wm.HOTSPOT_CONN,
                          'ip': '10.42.0.1', 'signal': 77, 'id': 'ABCD'})
        wifi_list = [c for c in self.fake.calls if 'list' in c]
        self.assertTrue(wifi_list and all('--rescan' in c for c in wifi_list))

    def test_hotspot_profile_cannot_be_deleted(self):
        resp = self.post('/api/wifi/network', {'ssid': wm.HOTSPOT_CONN}, method='DELETE')
        self.assertEqual(resp.code, 403)
        self.assertEqual(self.fake.called('con', 'delete'), [])

    def test_delete_other_network(self):
        resp = self.post('/api/wifi/network', {'ssid': 'Home WiFi'}, method='DELETE')
        self.assertEqual(resp.code, 200)
        self.assertEqual(self.fake.called('con', 'delete'), [('con', 'delete', 'Home WiFi')])


class FakeDrone:
    TUNE_MARIO = 'MFT200L8O5EEP8EP8CEP8GP8P4<GP4'
    TUNE_WARN = 'MFT200L16O5AP16AP16A'
    TUNE_VICTORY = 'MFT180L8O5CEGO6CL4C'

    def __init__(self):
        self.tunes = []
        self.armed = False
        self.fresh = True

    def play_tune(self, tune, fmt='QBASIC'):
        self.tunes.append(tune)

    def get_fcu_status(self, max_age=3.0):
        return {'ok': self.fresh, 'armed': self.armed}

    def set_led(self, *a):
        pass


class ShowsTest(AsyncHTTPTestCase):
    """POST /api/led/animation for a show: LED script + tune loop in-process."""

    def setUp(self):
        self.drone = FakeDrone()
        self.tmp = tempfile.TemporaryDirectory()
        for name in wm.ANIMATIONS:   # LED scripts that just wait for SIGTERM
            with open(os.path.join(self.tmp.name, name + '.py'), 'w') as f:
                f.write('import time\nwhile True: time.sleep(1)\n')
        self._orig = (getattr(wm, '_drone', None), wm._LED_OK, wm.ANIM_DIR, wm.LED_BUSY)
        wm._drone, wm._LED_OK, wm.ANIM_DIR = self.drone, True, self.tmp.name
        wm.LED_BUSY = os.path.join(self.tmp.name, 'led_busy')
        super().setUp()

    def tearDown(self):
        wm._stop_anim()
        super().tearDown()
        wm._drone, wm._LED_OK, wm.ANIM_DIR, wm.LED_BUSY = self._orig
        self.tmp.cleanup()

    def get_app(self):
        return wm.make_app()

    def start(self, name):
        return self.fetch('/api/led/animation', method='POST', body=json.dumps({'name': name}))

    def test_show_repeats_its_tune_until_stopped(self):
        self.assertEqual(self.start('alarm').code, 200)      # 0.375 s tune + 0.5 s gap
        self.io_loop.run_sync(lambda: tornado.gen.sleep(2.4))
        real = [t for t in self.drone.tunes if t == FakeDrone.TUNE_WARN]
        self.assertGreaterEqual(len(real), 2)
        self.assertEqual(json.loads(self.fetch('/api/led/status').body)['animation'], 'alarm')
        self.fetch('/api/led/reset', method='POST', body='')
        n = len(self.drone.tunes)
        self.io_loop.run_sync(lambda: tornado.gen.sleep(1.2))
        self.assertEqual(len(self.drone.tunes), n, 'tune kept playing after the show stopped')

    def test_show_is_silent_while_armed(self):
        self.drone.armed = True
        self.start('siren')
        self.io_loop.run_sync(lambda: tornado.gen.sleep(1.0))
        self.assertNotIn('MNT100L4O5AO6DO5AO6D', self.drone.tunes)

    def test_show_is_silent_without_fresh_fcu_state(self):
        self.drone.fresh = False
        self.start('alarm')
        self.io_loop.run_sync(lambda: tornado.gen.sleep(1.5))
        self.assertNotIn(FakeDrone.TUNE_WARN, self.drone.tunes)

    def test_tune_stops_when_led_script_exits(self):
        with open(os.path.join(self.tmp.name, 'alarm.py'), 'w') as f:
            f.write('import time\ntime.sleep(0.3)\n')     # LED script dies early
        self.start('alarm')
        self.io_loop.run_sync(lambda: tornado.gen.sleep(2.5))
        self.assertLessEqual(len([t for t in self.drone.tunes if t == FakeDrone.TUNE_WARN]), 1)

    def test_plain_animation_plays_no_tune(self):
        self.start('rainbow')
        self.io_loop.run_sync(lambda: tornado.gen.sleep(1.0))
        self.assertEqual(self.drone.tunes, [])

    def test_tune_seconds(self):
        ts = wm._tune_seconds
        self.assertAlmostEqual(ts('T120L4C'), 0.5)
        self.assertAlmostEqual(ts('T120L4C.'), 0.75)
        self.assertAlmostEqual(ts('T60C8'), 0.5)
        self.assertAlmostEqual(ts('T120P2'), 1.0)
        self.assertAlmostEqual(ts('MNT100L4O5AO6DO5AO6D'), 2.4)


class AnimationsTest(unittest.TestCase):
    def test_every_animation_has_a_script(self):
        anim_dir = os.path.join(PKG, 'examples', 'animations')
        for name in sorted(wm.ANIMATIONS):
            self.assertTrue(os.path.isfile(os.path.join(anim_dir, name + '.py')), name)

    def test_gcs_names_are_known(self):
        # names the macOS GCS EntertainmentView sends
        for name in ('breathing', 'rainbow', 'police', 'strobe', 'fire', 'theater',
                     'rainbow_theater', 'party', 'siren', 'alarm', 'victory'):
            self.assertIn(name, wm.ANIMATIONS)


if __name__ == '__main__':
    unittest.main()
