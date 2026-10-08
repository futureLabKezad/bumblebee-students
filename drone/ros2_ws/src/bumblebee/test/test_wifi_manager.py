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
        self.connections = ['netplan-wlan0-Y', 'Home WiFi', wm.HOTSPOT_CONN]
        self.wlan0 = ('connected', wm.HOTSPOT_CONN)

    def __call__(self, *args):
        with self.lock:
            self.calls.append(args)
        if args[:4] == ('-t', '-f', 'NAME', 'con'):
            return '\n'.join(self.connections)
        if args[:4] == ('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device'):
            return 'wlan0:%s:%s\neth0:unavailable:' % self.wlan0
        if args[:4] == ('-t', '-f', 'IP4.ADDRESS', 'device'):
            return 'IP4.ADDRESS[1]:10.42.0.1/24'
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
        self._orig = (wm.nmcli, wm.WIFI_SWITCH_MARKER, wm.SWITCH_DELAY_S)
        wm.nmcli = self.fake
        wm.WIFI_SWITCH_MARKER = os.path.join(self.tmp.name, 'switch')
        wm.SWITCH_DELAY_S = 0.2
        super().setUp()

    def tearDown(self):
        super().tearDown()
        wm.nmcli, wm.WIFI_SWITCH_MARKER, wm.SWITCH_DELAY_S = self._orig
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
                          'ip': '10.42.0.1', 'signal': 77})
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
