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

"""Safety rules of scripts/wifi_manager.py, off-drone (nmcli and drone.py faked).

  - "unknown = armed": Wi-Fi and sound changes need a fresh, linked, disarmed
    flight controller (one exception: Wi-Fi provisioning on the setup hotspot);
  - Safe Remove of the network in use (confirm, reply first, delete after);
  - a new password is tried in a pending profile before it replaces a working one;
  - a stale join failure never raises the hotspot over a newer connection;
  - the setup hotspot cannot be changed through the API, whatever names it;
  - no reply and no log line carries a Wi-Fi password;
  - GET /api/info; every error carries a stable "code";
  - the drone's own pages (www/) explain the refusals.

Run with the rest:  python -m unittest discover -s test -p 'test_*.py'
"""
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import bcrypt
import tornado.gen
from tornado.testing import AsyncHTTPTestCase

import test_wifi_manager as base   # loads scripts/wifi_manager.py once, as base.wm

wm = base.wm
FakeDrone = base.FakeDrone
REAL_NMCLI = wm.nmcli       # the subprocess wrapper, before any test swaps in a fake
_MISSING = object()

# Module globals a test may replace; all restored in tearDown.
PATCHED = ('nmcli', 'WIFI_SWITCH_MARKER', 'SWITCH_DELAY_S', 'HOTSPOT_PIN_MARKER',
           'WIFI_FAILED_LOG', '_hotspot_ssid', 'LAST_ERROR_FILE', '_drone', '_LED_OK',
           '_TTS_OK', '_tts_to_tune', 'PENDING_TTL_S', 'VERSION_FILE',
           'AVAHI_SERVICE_FILE', 'STACK_DOMAIN_FILE', 'PROC_DIR', 'CONFIG_PATH')

CHANGING = (('con', 'add'), ('con', 'clone'), ('con', 'modify'), ('con', 'delete'),
            ('con', 'up'), ('connection', 'up'), ('connection', 'down'),
            ('connection', 'modify'))


def _esc(name):
    return name.replace('\\', '\\\\').replace(':', '\\:')


class StatefulNmcli:
    """A small NetworkManager: saved profiles, wlan0 and the routers in range.

    `router` maps an SSID in range to the password that works (None: open).
    `con up` succeeds only with that password; a failed join leaves wlan0 as
    `after_fail` (default: disconnected), like NM after an activation failure.
    A newer `con up` cancels one still in progress (its nmcli fails, wlan0 is
    left to the newer one), as NetworkManager does.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.calls = []
        self.profiles = []
        self.n = 0
        self.activation = 0
        self.router = {}
        self.delay = {}            # ssid -> seconds `con up` takes
        self.late_join = set()     # ssids whose `con up` reports failure but connects anyway
        self.fail_delete = set()   # refs whose `con delete` fails
        self.after_fail = None
        self.add(wm.HOTSPOT_CONN, 'Bumblebee-ABCD', '12345678')
        self.wlan0 = ('connected', wm.HOTSPOT_CONN)

    def add(self, name, ssid, psk=None, prio=0, autoconnect='yes'):
        self.n += 1
        p = {'uuid': 'uuid-%04d' % self.n, 'name': name, 'ssid': ssid, 'psk': psk,
             'autoconnect': autoconnect, 'priority': prio, 'num': self.n}
        self.profiles.append(p)
        return p

    @staticmethod
    def refs(p):
        """Every way nmcli lets a command name this profile: its name, UUID,
        D-Bus path (or just the number at its end) and keyfile name."""
        path = '/org/freedesktop/NetworkManager/Settings/%d' % p['num']
        keyfile = '/etc/NetworkManager/system-connections/%s.nmconnection' % p['name']
        return (p['uuid'], p['name'], path, str(p['num']), keyfile)

    def find_all(self, ref):
        return [p for p in self.profiles if ref in self.refs(p)]

    def find(self, ref):
        for p in self.profiles:
            if p['uuid'] == ref:
                return p
        for p in self.profiles:
            if ref in self.refs(p):
                return p
        return None

    def named(self, name):
        with self.lock:
            return [p for p in self.profiles if p['name'] == name]

    def called(self, *prefix):
        with self.lock:
            return [c for c in self.calls if c[:len(prefix)] == prefix]

    def changes(self):
        with self.lock:
            return [c for c in self.calls if c[:2] in CHANGING]

    def _apply(self, p, pairs):
        for key, value in zip(pairs[0::2], pairs[1::2]):
            if key == 'connection.id':
                if self.wlan0[1] == p['name']:
                    self.wlan0 = (self.wlan0[0], value)
                p['name'] = value
            elif key == 'wifi-sec.psk':
                p['psk'] = value
            elif key == 'connection.autoconnect':
                p['autoconnect'] = value
            elif key == 'connection.autoconnect-priority':
                p['priority'] = int(value)
            elif key in ('wifi.ssid', 'ssid'):
                p['ssid'] = value

    def __call__(self, *args, timeout=15):
        if args[:1] == ('-w',):
            args = args[2:]
        with self.lock:
            self.calls.append(args)
            a = list(args)
            if a[:4] == ['-t', '-f', 'NAME', 'con']:
                return '\n'.join(_esc(p['name']) for p in self.profiles)
            if a[:4] == ['-t', '-f', 'NAME,TYPE', 'con']:
                return '\n'.join(_esc(p['name']) + ':802-11-wireless' for p in self.profiles)
            if a[:4] == ['-t', '-f', 'UUID,NAME', 'con']:
                return '\n'.join(p['uuid'] + ':' + _esc(p['name']) for p in self.profiles)
            if a[:4] == ['-t', '-f', 'TYPE,AUTOCONNECT-PRIORITY', 'con']:
                return '\n'.join('802-11-wireless:%d' % p['priority'] for p in self.profiles)
            if a[:2] == ['-g', 'connection.uuid']:
                found = self.find_all(a[-1])      # nmcli shows every profile the ref names
                if not found:
                    raise RuntimeError('Error: %s - no such connection profile.' % a[-1])
                return '\n'.join(p['uuid'] for p in found)
            if a[:2] == ['-g', '802-11-wireless.ssid']:
                p = self.find(a[-1])
                if p is None:
                    raise RuntimeError('Error: %s - no such connection profile.' % a[-1])
                return p['ssid'] or ''
            if a[:4] == ['-t', '-f', 'DEVICE,STATE,CONNECTION', 'device']:
                return 'wlan0:%s:%s\neth0:unavailable:' % (self.wlan0[0], _esc(self.wlan0[1]))
            if a[:4] == ['-t', '-f', 'IP4.ADDRESS', 'device']:
                return 'IP4.ADDRESS[1]:10.42.0.1/24'
            if 'IN-USE,SSID,SIGNAL,SECURITY,FREQ' in a:
                return '*:Home WiFi:55:WPA2:5180 MHz'
            if 'list' in a:
                return '*:77:Bumblebee-ABCD'
            if a[:2] == ['con', 'add']:
                kv = dict(zip(a[2::2], a[3::2]))
                p = self.add(kv['con-name'], kv['ssid'], kv.get('wifi-sec.psk'))
                self._apply(p, [k for pair in kv.items() for k in pair
                                if pair[0].startswith('connection.')])
                return "Connection '%s' (%s) successfully added." % (p['name'], p['uuid'])
            if a[:2] == ['con', 'clone']:
                src = self.find(a[2])
                if src is None:
                    raise RuntimeError('Error: unknown connection %s' % a[2])
                p = self.add(a[3], src['ssid'], src['psk'], src['priority'], src['autoconnect'])
                return '%s (%s) cloned as %s (%s).' % (src['name'], src['uuid'], p['name'], p['uuid'])
            if a[:2] in (['con', 'modify'], ['connection', 'modify']):
                p = self.find(a[2])
                if p is None:
                    raise RuntimeError('Error: unknown connection %s' % a[2])
                self._apply(p, a[3:])
                return ''
            if a[:2] == ['con', 'delete']:
                if a[2] in self.fail_delete:
                    raise RuntimeError('Error: Connection deletion failed: Insufficient privileges')
                p = self.find(a[2])
                if p is None:
                    raise RuntimeError('Error: unknown connection %s' % a[2])
                self.profiles.remove(p)
                if self.wlan0[1] == p['name']:
                    self.wlan0 = ('disconnected', '')
                return ''
            if a[:2] == ['connection', 'down']:
                self.wlan0 = ('disconnected', '')
                return ''
            if a[:2] not in (['con', 'up'], ['connection', 'up']):
                return ''
            p = self.find(a[2])
            if p is None:
                raise RuntimeError('Error: unknown connection %s' % a[2])
            name, ssid, psk = p['name'], p['ssid'], p['psk']
            self.activation += 1
            mine = self.activation
            self.wlan0 = ('connecting (preparing)', name)
        time.sleep(self.delay.get(ssid, 0))     # a join takes time; others may run meanwhile
        with self.lock:
            if self.activation != mine:         # a newer `con up` took wlan0 over
                raise RuntimeError('Error: Connection activation failed: '
                                   'The device was disconnected by the user')
            if name == wm.HOTSPOT_CONN:
                self.wlan0 = ('connected', name)
                return ''
            if ssid in self.late_join:          # NM got there after nmcli gave up
                self.wlan0 = ('connected', name)
                raise RuntimeError('Error: Timeout expired (40 seconds)')
            if ssid in self.router and self.router[ssid] == psk:
                self.wlan0 = ('connected', name)
                return ''
            self.wlan0 = self.after_fail or ('disconnected', '')
            raise RuntimeError('Error: Connection activation failed: Secrets were required, '
                               'but not provided.')


class SafetyCase(AsyncHTTPTestCase):
    """Shared setup: StatefulNmcli, a disarmed fresh FC, temp marker files."""

    def setUp(self):
        self.saved = {k: getattr(wm, k, _MISSING) for k in PATCHED}
        self.threads_before = set(threading.enumerate())
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.fake = StatefulNmcli()
        self.drone = FakeDrone()
        wm.nmcli = self.fake
        wm._drone, wm._LED_OK = self.drone, True
        wm.WIFI_SWITCH_MARKER = os.path.join(t, 'switch')
        wm.HOTSPOT_PIN_MARKER = os.path.join(t, 'pinned')
        wm.WIFI_FAILED_LOG = os.path.join(t, 'failed')
        wm.LAST_ERROR_FILE = os.path.join(t, 'last-error.json')
        wm._hotspot_ssid = lambda: 'Bumblebee-ABCD'
        wm.SWITCH_DELAY_S = 0.2
        wm._TTS_OK, wm._tts_to_tune = True, lambda text, lang='en': ('MFT120L8C', 'k')
        wm.VERSION_FILE = os.path.join(t, 'bumblebee_version')
        wm.AVAHI_SERVICE_FILE = os.path.join(t, 'bumblebee.service')
        wm.STACK_DOMAIN_FILE = os.path.join(t, 'stack-domain')
        wm.PROC_DIR = os.path.join(t, 'proc')
        for name in ('_pending',):
            if hasattr(wm, name):
                getattr(wm, name).clear()
        wm._fcu_last_linked_armed = None
        super().setUp()

    def tearDown(self):
        # let switch workers of this test finish before the next test swaps nmcli
        deadline = time.time() + 5
        while time.time() < deadline and any(
                th.is_alive() and th.name == 'wifi-switch'
                for th in set(threading.enumerate()) - self.threads_before):
            time.sleep(0.02)
        super().tearDown()
        for k, v in self.saved.items():
            if v is _MISSING:
                if hasattr(wm, k):
                    delattr(wm, k)
            else:
                setattr(wm, k, v)
        self.tmp.cleanup()

    def get_app(self):
        return wm.make_app()

    def call(self, method, path, body=None):
        if body is None and method == 'GET':
            resp = self.fetch(path)
        else:
            resp = self.fetch(path, method=method, allow_nonstandard_methods=True,
                              body=body if isinstance(body, (bytes, str)) else json.dumps(body or {}))
        try:
            data = json.loads(resp.body)
        except ValueError:
            data = None
        return resp.code, data

    def wait_for(self, pred, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if pred():
                return True
            time.sleep(0.02)
        return bool(pred())

    def run_loop(self, seconds):
        """Let IOLoop timers (call_later) fire; wait_for() blocks the loop."""
        self.io_loop.run_sync(lambda: tornado.gen.sleep(seconds))

    def last_error(self):
        try:
            with open(wm.LAST_ERROR_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def assertError(self, result, status, code):
        got_status, body = result
        self.assertEqual(got_status, status, body)
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get('code'), code, body)
        self.assertIsInstance(body.get('error'), str)
        self.assertTrue(body['error'])


# The seven endpoints the "unknown = armed" rule guards, with valid bodies.
GUARDED = [
    ('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'newpass12'}),
    ('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'}),
    ('POST', '/api/wifi/apply-boot', {'ssid': 'Home WiFi'}),
    ('POST', '/api/wifi/mode', {'mode': 'hotspot'}),
    ('DELETE', '/api/wifi/network', {'ssid': 'Home WiFi'}),
    ('POST', '/api/sounds/play', {'tune': 'MFT120L8C'}),
    ('POST', '/api/sounds/tts', {'text': 'hello'}),
]
PROVISIONING = ('/api/wifi/save', '/api/wifi/apply-now', '/api/wifi/apply-boot')


class FcuGuardTest(SafetyCase):
    def setUp(self):
        super().setUp()
        self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        self.fake.router['Home WiFi'] = 'goodpass1'

    def on_client(self):
        self.fake.wlan0 = ('connected', 'Home WiFi')

    def assertNothingChanged(self):
        time.sleep(wm.SWITCH_DELAY_S + 0.2)
        self.assertEqual(self.fake.changes(), [])
        self.assertEqual(self.drone.tunes, [])

    def test_armed_refuses_every_change(self):
        self.on_client()
        self.drone.armed = True
        for method, path, body in GUARDED:
            self.assertError(self.call(method, path, body), 409, 'armed')
        self.assertNothingChanged()

    def test_armed_refuses_on_the_hotspot_too(self):
        self.drone.armed = True              # wlan0 is on the setup hotspot
        for method, path, body in GUARDED:
            self.assertError(self.call(method, path, body), 409, 'armed')
        self.assertNothingChanged()

    def test_stale_state_with_armed_flag_counts_as_armed(self):
        self.drone.fresh, self.drone.armed = False, True
        for method, path, body in GUARDED:
            self.assertError(self.call(method, path, body), 409, 'armed')
        self.assertNothingChanged()

    def test_unknown_refuses_every_change_on_a_client_network(self):
        self.on_client()
        self.drone.fresh = False
        for method, path, body in GUARDED:
            self.assertError(self.call(method, path, body), 503, 'fc_unknown')
        self.assertNothingChanged()

    def test_link_lost_is_unknown(self):
        self.on_client()
        self.drone.linked = False             # MAVROS: connected=false
        for method, path, body in GUARDED:
            self.assertError(self.call(method, path, body), 503, 'fc_unknown')
        self.assertNothingChanged()

    def test_no_drone_module_is_unknown(self):
        self.on_client()
        wm._LED_OK = False                   # drone.py did not import
        for path in PROVISIONING:
            self.assertError(self.call('POST', path, {'ssid': 'Home WiFi'}), 503, 'fc_unknown')
        self.assertError(self.call('POST', '/api/wifi/mode', {'mode': 'hotspot'}), 503, 'fc_unknown')
        self.assertNothingChanged()

    def test_unknown_on_setup_hotspot_allows_provisioning_only(self):
        self.drone.fresh = False             # bench: FC unpowered; wlan0 on the hotspot
        for method, path, body in GUARDED:
            if path in PROVISIONING:
                continue
            self.assertError(self.call(method, path, body), 503, 'fc_unknown')
        self.assertEqual(self.fake.changes(), [])
        code, _ = self.call('POST', '/api/wifi/save', {'ssid': 'Classroom', 'password': 'classpass1'})
        self.assertEqual(code, 200)
        self.fake.router['Classroom'] = 'classpass1'
        code, body = self.call('POST', '/api/wifi/apply-now', {'ssid': 'Classroom'})
        self.assertEqual((code, body), (200, {'ok': True}))
        self.assertTrue(self.wait_for(lambda: self.fake.named('Classroom')))
        self.assertEqual(self.fake.wlan0, ('connected', 'Classroom'))
        self.fake.wlan0 = ('connected', wm.HOTSPOT_CONN)
        code, _ = self.call('POST', '/api/wifi/apply-boot', {'ssid': 'Classroom'})
        self.assertEqual(code, 200)

    def test_link_lost_while_armed_counts_as_armed(self):
        self.drone.armed = True              # flying, linked
        self.assertError(self.call('POST', '/api/sounds/play', {'tune': 'C'}), 409, 'armed')
        # the FC link drops: MAVROS then says connected=false, armed=false
        self.drone.armed, self.drone.linked = False, False
        for path in PROVISIONING:            # no hotspot exception for a drone that may fly
            self.assertError(self.call('POST', path, {'ssid': 'Home WiFi'}), 409, 'armed')
        self.assertNothingChanged()
        # a fresh linked disarmed state clears it
        self.drone.linked = True
        self.assertEqual(self.call('POST', '/api/sounds/play', {'tune': 'C'})[0], 200)

    def test_disarmed_sounds_play(self):
        self.assertEqual(self.call('POST', '/api/sounds/play', {'tune': 'MFT120L8C'})[0], 200)
        code, body = self.call('POST', '/api/sounds/tts', {'text': 'hi'})
        self.assertEqual(code, 200)
        self.assertEqual(body['tune'], 'MFT120L8C')
        self.assertEqual(self.drone.tunes, ['MFT120L8C', 'MFT120L8C'])

    def test_switch_is_checked_again_right_before_it_runs(self):
        code, _ = self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.assertEqual(code, 200)
        self.drone.armed = True              # armed within the reply-first delay
        time.sleep(wm.SWITCH_DELAY_S + 0.4)
        self.assertEqual(self.fake.called('con', 'up'), [])
        self.assertEqual(self.fake.called('connection', 'up'), [])
        self.assertEqual(self.last_error()['reason'], 'armed')

    def test_mode_switch_is_checked_again_right_before_it_runs(self):
        self.on_client()
        self.assertEqual(self.call('POST', '/api/wifi/mode', {'mode': 'hotspot'})[0], 200)
        self.drone.fresh = False
        time.sleep(wm.SWITCH_DELAY_S + 0.4)
        self.assertEqual(self.fake.called('connection', 'up'), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))


class SafeRemoveTest(SafetyCase):
    def setUp(self):
        super().setUp()
        self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        self.fake.add('Cafe', 'Cafe', None)
        self.fake.wlan0 = ('connected', 'Home WiFi')

    def test_active_network_needs_confirmation(self):
        self.assertError(self.call('DELETE', '/api/wifi/network', {'ssid': 'Home WiFi'}),
                         409, 'active_network')
        self.assertError(self.call('DELETE', '/api/wifi/network',
                                   {'ssid': 'Home WiFi', 'confirm_active': 'yes'}),
                         409, 'active_network')
        self.run_loop(wm.SWITCH_DELAY_S + 0.3)
        self.assertEqual(self.fake.called('con', 'delete'), [])
        self.assertEqual(len(self.fake.named('Home WiFi')), 1)

    def test_confirmed_delete_replies_first_then_deletes(self):
        code, body = self.call('DELETE', '/api/wifi/network',
                               {'ssid': 'Home WiFi', 'confirm_active': True})
        self.assertEqual(code, 200)
        self.assertTrue(body['ok'])
        self.assertEqual(self.fake.called('con', 'delete'), [], 'deleted before the reply')
        self.run_loop(wm.SWITCH_DELAY_S + 0.3)
        self.assertTrue(self.wait_for(lambda: self.fake.called('con', 'delete')))
        self.assertEqual(self.fake.named('Home WiFi'), [])
        # no switch marker: wifi_watchdog.sh should react to the loss at once
        self.assertFalse(os.path.exists(wm.WIFI_SWITCH_MARKER))

    def test_other_network_is_deleted_at_once(self):
        code, body = self.call('DELETE', '/api/wifi/network', {'ssid': 'Cafe'})
        self.assertEqual((code, body), (200, {'ok': True}))
        self.assertEqual(self.fake.named('Cafe'), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))

    def test_delete_also_drops_a_pending_change(self):
        self.call('POST', '/api/wifi/save', {'ssid': 'Cafe', 'password': 'cafepass1'})
        self.assertEqual(self.call('DELETE', '/api/wifi/network', {'ssid': 'Cafe'})[0], 200)
        self.assertEqual(self.fake.named('Cafe'), [])
        self.assertEqual(self.fake.named('Cafe.bb-pending'), [])

    def test_active_network_named_by_its_uuid_needs_confirmation_too(self):
        [home] = self.fake.named('Home WiFi')
        for ref in (home['uuid'], '/org/freedesktop/NetworkManager/Settings/%d' % home['num']):
            self.assertError(self.call('DELETE', '/api/wifi/network', {'ssid': ref}),
                             409, 'active_network')
        self.run_loop(wm.SWITCH_DELAY_S + 0.3)
        self.assertEqual(self.fake.called('con', 'delete'), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))

    def test_failed_delete_is_reported_even_with_a_pending_change(self):
        self.call('POST', '/api/wifi/save', {'ssid': 'Cafe', 'password': 'cafepass1'})
        self.fake.fail_delete.add('Cafe')
        self.assertError(self.call('DELETE', '/api/wifi/network', {'ssid': 'Cafe'}),
                         500, 'nmcli_failed')
        self.assertEqual(len(self.fake.named('Cafe')), 1)


class PendingPasswordTest(SafetyCase):
    """A typo in a new password must not overwrite the working one."""

    def setUp(self):
        super().setUp()
        self.home = self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        self.fake.router['Home WiFi'] = 'goodpass1'

    def pending(self):
        with self.fake.lock:
            return [p for p in self.fake.profiles if p['name'].endswith('.bb-pending')]

    def test_save_does_not_touch_the_working_profile(self):
        code, body = self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'typo-pass'})
        self.assertEqual(code, 200)
        self.assertTrue(body['ok'])
        self.assertEqual(self.home['psk'], 'goodpass1')
        self.assertEqual(self.fake.called('con', 'modify', 'Home WiFi'), [])
        [p] = self.pending()
        self.assertEqual((p['ssid'], p['psk'], p['autoconnect']), ('Home WiFi', 'typo-pass', 'no'))
        names = [n['name'] for n in json.loads(self.fetch('/api/wifi/networks').body)]
        self.assertEqual(names, ['Home WiFi'])

    def test_wrong_password_keeps_the_working_one(self):
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'typo-pass'})
        self.assertEqual(self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})[0], 200)
        self.assertTrue(self.wait_for(lambda: self.fake.wlan0 == ('connected', wm.HOTSPOT_CONN)
                                      and self.fake.called('connection', 'up', wm.HOTSPOT_CONN)))
        self.assertTrue(self.wait_for(lambda: not self.pending()))
        self.assertEqual(self.fake.named('Home WiFi'), [self.home])
        self.assertEqual(self.home['psk'], 'goodpass1')
        self.assertEqual(self.home['autoconnect'], 'yes')
        try:
            with open(wm.WIFI_FAILED_LOG) as f:
                failed = f.read()
        except OSError:
            failed = ''
        self.assertNotIn(self.home['uuid'], failed, 'the working profile was put in back-off')
        err = self.last_error()
        self.assertEqual((err['ssid'], err['reason']), ('Home WiFi', 'wrong_password'))

    def test_right_password_replaces_the_old_profile(self):
        self.fake.router['Home WiFi'] = 'newpass12'      # the router's password changed
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'newpass12'})
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.assertTrue(self.wait_for(lambda: not self.pending() and self.fake.named('Home WiFi')
                                      and self.fake.named('Home WiFi')[0] is not self.home))
        [p] = self.fake.named('Home WiFi')
        self.assertEqual((p['psk'], p['autoconnect'], p['priority']), ('newpass12', 'yes', 13))
        self.assertNotIn(self.home, self.fake.profiles)
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))
        self.assertIsNone(self.last_error())
        self.assertEqual(self.fake.called('connection', 'up', wm.HOTSPOT_CONN), [])

    def test_proven_password_is_kept_even_if_the_old_profile_cannot_be_deleted(self):
        # e.g. a read-only profile: the one that just joined must still become
        # the network the drone joins after a reboot, ahead of the old one
        self.fake.router['Home WiFi'] = 'newpass12'
        self.fake.fail_delete.add(self.home['uuid'])
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'newpass12'})
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.assertTrue(self.wait_for(lambda: not self.pending()))
        [new] = [p for p in self.fake.named('Home WiFi') if p is not self.home]
        self.assertEqual((new['psk'], new['autoconnect'], new['priority']), ('newpass12', 'yes', 13))
        self.assertEqual(self.home['autoconnect'], 'no')
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))

    def test_new_network_with_wrong_password_leaves_nothing_behind(self):
        self.fake.router['Classroom'] = 'classpass1'
        self.call('POST', '/api/wifi/save', {'ssid': 'Classroom', 'password': 'classpass0'})
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Classroom'})
        self.assertTrue(self.wait_for(lambda: self.fake.called('connection', 'up', wm.HOTSPOT_CONN)))
        self.assertTrue(self.wait_for(lambda: not self.pending()))
        self.assertEqual(self.fake.named('Classroom'), [])
        err = self.last_error()
        self.assertEqual((err['ssid'], err['reason']), ('Classroom', 'wrong_password'))

    def test_new_network_with_right_password_is_kept_on_top(self):
        self.fake.router['Classroom'] = 'classpass1'
        self.call('POST', '/api/wifi/save', {'ssid': 'Classroom', 'password': 'classpass1'})
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Classroom'})
        self.assertTrue(self.wait_for(lambda: self.fake.named('Classroom') and not self.pending()))
        [p] = self.fake.named('Classroom')
        self.assertEqual((p['ssid'], p['psk'], p['autoconnect'], p['priority']),
                         ('Classroom', 'classpass1', 'yes', 13))
        names = [n['name'] for n in json.loads(self.fetch('/api/wifi/networks').body)]
        self.assertIn('Classroom', names)

    def test_apply_boot_stores_the_password_without_switching(self):
        self.fake.wlan0 = ('connected', 'Home WiFi')
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'newpass12'})
        code, body = self.call('POST', '/api/wifi/apply-boot', {'ssid': 'Home WiFi'})
        self.assertEqual((code, body), (200, {'ok': True, 'note': 'will connect on next boot'}))
        self.assertEqual(self.fake.named('Home WiFi'), [self.home], 'the profile in use was replaced')
        self.assertEqual((self.home['psk'], self.home['priority']), ('newpass12', 13))
        self.assertEqual(self.pending(), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))
        time.sleep(wm.SWITCH_DELAY_S + 0.2)
        self.assertEqual(self.fake.called('con', 'up'), [])

    def test_apply_boot_of_a_new_network(self):
        self.call('POST', '/api/wifi/save', {'ssid': 'Classroom', 'password': 'classpass1'})
        self.assertEqual(self.call('POST', '/api/wifi/apply-boot', {'ssid': 'Classroom'})[0], 200)
        [p] = self.fake.named('Classroom')
        self.assertEqual((p['psk'], p['autoconnect'], p['priority']), ('classpass1', 'yes', 13))
        self.assertEqual(self.pending(), [])

    def test_apply_boot_never_deletes_a_pending_profile_that_joined(self):
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'newpass12'})
        with wm._wifi_lock:                  # an apply-now took it and wlan0 joined it,
            rec = wm._pending['Home WiFi']    # its worker has not promoted it yet
            rec['gen'] = wm._bump_switch_gen()
        self.fake.wlan0 = ('connected', 'Home WiFi.bb-pending')
        self.assertEqual(self.call('POST', '/api/wifi/apply-boot', {'ssid': 'Home WiFi'})[0], 200)
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'), 'the link in use was deleted')
        [p] = self.fake.named('Home WiFi')
        self.assertEqual(p['psk'], 'newpass12')
        self.assertEqual(self.pending(), [])

    def test_save_without_password_only_raises_priority(self):
        code, body = self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': ''})
        self.assertEqual((code, body), (200, {'ok': True}))
        self.assertEqual(self.pending(), [])
        self.assertEqual((self.home['psk'], self.home['priority']), ('goodpass1', 13))

    def test_saving_again_replaces_the_pending_profile(self):
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'first-try'})
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'second-try'})
        [p] = self.pending()
        self.assertEqual(p['psk'], 'second-try')

    def test_unused_pending_profile_expires(self):
        wm.PENDING_TTL_S = 0.3
        self.call('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': 'typo-pass'})
        self.assertEqual(len(self.pending()), 1)
        self.run_loop(0.6)
        self.assertTrue(self.wait_for(lambda: not self.pending()))
        self.assertEqual(self.fake.named('Home WiFi'), [self.home])
        self.assertEqual(self.home['psk'], 'goodpass1')

    def test_status_names_the_network_not_the_pending_profile(self):
        self.fake.add('Home WiFi.bb-pending', 'Home WiFi', 'x')
        self.fake.wlan0 = ('connected', 'Home WiFi.bb-pending')
        self.assertEqual(json.loads(self.fetch('/api/wifi/status').body)['ssid'], 'Home WiFi')

    def test_start_up_settles_pending_profiles_left_behind(self):
        joined = self.fake.add('Home WiFi.bb-pending', 'Home WiFi', 'newpass12')
        stray = self.fake.add('Cafe.bb-pending', 'Cafe', 'x')
        self.fake.wlan0 = ('connected', 'Home WiFi.bb-pending')   # restarted mid-promotion
        wm._recover_pending()
        self.assertEqual(self.fake.named('Home WiFi'), [joined])
        self.assertNotIn(self.home, self.fake.profiles)
        self.assertNotIn(stray, self.fake.profiles)
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))


class JoinRaceTest(SafetyCase):
    """Double Apply / a slow join must not raise the hotspot over a good link."""

    def setUp(self):
        super().setUp()
        self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        self.fake.add('Bad Net', 'Bad Net', 'wrong')
        self.fake.router.update({'Home WiFi': 'goodpass1', 'Bad Net': 'right'})

    def test_stale_failure_does_not_raise_the_hotspot(self):
        self.fake.delay['Bad Net'] = 0.8
        self.assertEqual(self.call('POST', '/api/wifi/apply-now', {'ssid': 'Bad Net'})[0], 200)
        time.sleep(wm.SWITCH_DELAY_S + 0.2)         # its join is under way
        self.assertTrue(self.fake.called('con', 'up', 'Bad Net'))
        self.assertEqual(self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})[0], 200)
        self.assertTrue(self.wait_for(lambda: self.fake.called('con', 'up', 'Home WiFi')))
        time.sleep(1.0)                             # the first join fails after the second joined
        self.assertEqual(self.fake.called('connection', 'up', wm.HOTSPOT_CONN), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))
        self.assertIsNone(self.last_error())

    def test_double_apply_switches_once(self):
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})
        self.assertTrue(self.wait_for(lambda: self.fake.called('con', 'up', 'Home WiFi')))
        time.sleep(wm.SWITCH_DELAY_S + 0.3)
        self.assertEqual(len(self.fake.called('con', 'up', 'Home WiFi')), 1)

    def test_failure_with_wlan0_back_on_a_client_network_keeps_it(self):
        self.fake.after_fail = ('connected', 'Home WiFi')   # NM fell back on its own
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Bad Net'})
        self.assertTrue(self.wait_for(lambda: self.last_error() is not None))
        time.sleep(0.2)
        self.assertEqual(self.fake.called('connection', 'up', wm.HOTSPOT_CONN), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Home WiFi'))
        self.assertEqual(self.last_error()['ssid'], 'Bad Net')

    def test_failure_report_but_connected_to_the_target_is_success(self):
        self.fake.router['Classroom'] = 'classpass1'
        self.fake.late_join.add('Classroom')
        self.call('POST', '/api/wifi/save', {'ssid': 'Classroom', 'password': 'classpass1'})
        self.call('POST', '/api/wifi/apply-now', {'ssid': 'Classroom'})
        self.assertTrue(self.wait_for(lambda: self.fake.called('con', 'up')))
        time.sleep(0.4)                              # the failure handler has run
        self.assertEqual(self.fake.called('connection', 'up', wm.HOTSPOT_CONN), [])
        self.assertEqual(self.fake.wlan0, ('connected', 'Classroom'))
        [p] = self.fake.named('Classroom')
        self.assertEqual((p['autoconnect'], p['priority']), ('yes', 13))
        self.assertIsNone(self.last_error())


class ProtectedNetworkTest(SafetyCase):
    NAMES = (wm.HOTSPOT_CONN, 'Bumblebee-ABCD', 'BUMBLEBEE-1F2E', 'bumblebee-x')

    def test_setup_hotspot_cannot_be_changed(self):
        self.fake.wlan0 = ('connected', 'Home WiFi')
        for name in self.NAMES:
            for method, path, body in (
                    ('POST', '/api/wifi/save', {'ssid': name, 'password': 'x' * 8}),
                    ('POST', '/api/wifi/apply-now', {'ssid': name}),
                    ('POST', '/api/wifi/apply-boot', {'ssid': name}),
                    ('DELETE', '/api/wifi/network', {'ssid': name, 'confirm_active': True})):
                self.assertError(self.call(method, path, body), 409, 'protected_network')
        time.sleep(wm.SWITCH_DELAY_S + 0.2)
        self.assertEqual(self.fake.changes(), [])
        self.assertEqual(self.fake.find(wm.HOTSPOT_CONN)['psk'], '12345678')

    def changes_refused(self, refs):
        for ref in refs:
            for method, path, body in (
                    ('POST', '/api/wifi/save', {'ssid': ref, 'password': 'x' * 8}),
                    ('POST', '/api/wifi/save', {'ssid': ref, 'password': ''}),
                    ('POST', '/api/wifi/apply-now', {'ssid': ref}),
                    ('POST', '/api/wifi/apply-boot', {'ssid': ref}),
                    ('DELETE', '/api/wifi/network', {'ssid': ref}),
                    ('DELETE', '/api/wifi/network', {'ssid': ref, 'confirm_active': True})):
                self.assertError(self.call(method, path, body), 409, 'protected_network')
        time.sleep(wm.SWITCH_DELAY_S + 0.2)
        self.assertEqual(self.fake.changes(), [])

    def test_hotspot_named_any_way_nmcli_accepts_is_protected(self):
        # nmcli takes a UUID, a D-Bus path (or its number) or a keyfile name
        # wherever it takes a profile name: `con delete <hotspot uuid>` must
        # not get past a guard that only compares names.
        self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        self.fake.wlan0 = ('connected', 'Home WiFi')
        hotspot = self.fake.find(wm.HOTSPOT_CONN)
        before = dict(hotspot)
        self.changes_refused(self.fake.refs(hotspot))
        self.assertIn(hotspot, self.fake.profiles)
        self.assertEqual(hotspot, before)

    def test_profile_of_a_bumblebee_ssid_is_protected_under_any_name(self):
        other = self.fake.add('Lab drone', 'Bumblebee-1F2E', '12345678')
        before = dict(other)
        self.changes_refused(('Lab drone', other['uuid']))
        self.assertEqual(other, before)

    def test_ordinary_profiles_by_uuid_still_work(self):
        cafe = self.fake.add('Cafe', 'Cafe', None, prio=3)
        self.assertEqual(self.call('POST', '/api/wifi/apply-boot', {'ssid': cafe['uuid']})[0], 200)
        self.assertEqual(cafe['priority'], 10)
        self.assertEqual(self.call('DELETE', '/api/wifi/network', {'ssid': cafe['uuid']}),
                         (200, {'ok': True}))
        self.assertNotIn(cafe, self.fake.profiles)


class InfoTest(SafetyCase):
    def write(self, path, text):
        with open(path, 'w') as f:
            f.write(text)

    def test_info_contract(self):
        self.write(wm.VERSION_FILE, 'Bumblebee 1.0.2-rc (repo abc123), built 2026-10-21\n'
                                    'update 1.0.2-rc installed 2026-10-22\n')
        self.write(wm.AVAHI_SERVICE_FILE,
                   '<service>\n    <txt-record>name=Lab-3</txt-record>\n'
                   '    <txt-record>id=ABCD</txt-record>\n</service>\n')
        os.makedirs(os.path.join(wm.PROC_DIR, '4321'))
        self.write(wm.STACK_DOMAIN_FILE, '17 4321\n')
        code, body = self.call('GET', '/api/info')
        self.assertEqual(code, 200)
        self.assertEqual(body, {'name': 'Lab-3', 'id': 'ABCD',
                                'version': 'Bumblebee 1.0.2-rc (repo abc123), built 2026-10-21',
                                'ros_domain': 17, 'contract': 1})

    def test_info_without_identity_files(self):
        old = os.environ.pop('ROS_DOMAIN_ID', None)
        try:
            body = self.call('GET', '/api/info')[1]
            self.assertEqual(body, {'name': 'Bumblebee-ABCD', 'id': 'ABCD', 'version': 'unknown',
                                    'ros_domain': None, 'contract': 1})
            os.environ['ROS_DOMAIN_ID'] = '5'
            self.assertEqual(self.call('GET', '/api/info')[1]['ros_domain'], 5)
        finally:
            os.environ.pop('ROS_DOMAIN_ID', None)
            if old is not None:
                os.environ['ROS_DOMAIN_ID'] = old

    def test_domain_of_a_stopped_stack_is_ignored(self):
        os.makedirs(wm.PROC_DIR)
        self.write(wm.STACK_DOMAIN_FILE, '17 4321\n')     # pid 4321 is gone
        os.environ['ROS_DOMAIN_ID'] = '9'
        try:
            self.assertEqual(self.call('GET', '/api/info')[1]['ros_domain'], 9)
        finally:
            os.environ.pop('ROS_DOMAIN_ID', None)


class ErrorCodeTest(SafetyCase):
    def test_wifi_errors_carry_codes(self):
        self.assertError(self.call('POST', '/api/wifi/save', b'not json'), 400, 'bad_json')
        self.assertError(self.call('POST', '/api/wifi/save', {'password': 'x'}), 400, 'ssid_required')
        self.assertError(self.call('POST', '/api/wifi/apply-now', {}), 400, 'ssid_required')
        self.assertError(self.call('POST', '/api/wifi/apply-boot', [1, 2]), 400, 'bad_json')
        self.assertError(self.call('DELETE', '/api/wifi/network', {}), 400, 'ssid_required')
        self.assertError(self.call('POST', '/api/wifi/apply-now', {'ssid': 'Nope'}), 404, 'unknown_network')
        self.assertError(self.call('POST', '/api/wifi/mode', {'mode': 'x'}), 400, 'bad_mode')

    def test_nmcli_failure_has_a_code(self):
        def broken(*args, timeout=15):
            raise RuntimeError('Error: NetworkManager is not running.')
        wm.nmcli = broken
        self.assertError(self.call('POST', '/api/wifi/apply-boot', {'ssid': 'Home WiFi'}),
                         500, 'nmcli_failed')
        self.assertError(self.call('GET', '/api/wifi/status'), 500, 'nmcli_failed')
        self.assertError(self.call('GET', '/api/wifi/networks'), 500, 'nmcli_failed')

    def test_sound_and_led_errors_carry_codes(self):
        self.assertError(self.call('POST', '/api/sounds/play', {'tune': ''}), 400, 'empty_tune')
        self.assertError(self.call('POST', '/api/sounds/play', {'tune': 'C', 'format': 'X'}), 400, 'bad_format')
        self.assertError(self.call('POST', '/api/sounds/play', b'{'), 400, 'bad_json')
        self.assertError(self.call('POST', '/api/sounds/tts', {'text': ''}), 400, 'text_required')
        wm._TTS_OK = False
        self.assertError(self.call('POST', '/api/sounds/tts', {'text': 'hi'}), 503, 'tts_unavailable')
        result = self.call('POST', '/api/led/animation', {'name': 'nope'})
        self.assertError(result, 400, 'unknown_animation')
        self.assertIn('rainbow', result[1]['available'])
        wm._LED_OK = False
        self.assertError(self.call('POST', '/api/sounds/play', {'tune': 'C'}), 503, 'drone_unavailable')
        self.assertError(self.call('POST', '/api/led/animation', {'name': 'rainbow'}), 503, 'led_unavailable')

    def test_led_color_and_login_errors_carry_codes(self):
        self.assertError(self.call('POST', '/api/led/color', b'{'), 400, 'bad_json')
        self.assertError(self.call('POST', '/api/led/color', {'r': 'red'}), 400, 'bad_color')
        wm.CONFIG_PATH = os.path.join(self.tmp.name, 'config.json')
        with open(wm.CONFIG_PATH, 'w') as f:
            json.dump({'pin_hash': bcrypt.hashpw(b'1234', bcrypt.gensalt(4)).decode()}, f)
        self.assertError(self.call('POST', '/api/auth/login', {'pin': '0000'}), 401, 'invalid_pin')
        self.assertError(self.call('POST', '/api/auth/login', b'pin'), 400, 'bad_json')
        self.assertEqual(self.call('POST', '/api/auth/login', {'pin': '1234'}), (200, {'ok': True}))
        wm._LED_OK = False
        self.assertError(self.call('POST', '/api/led/color', {'r': 1}), 503, 'led_unavailable')

    def test_password_length_is_checked_before_nmcli(self):
        self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        for ssid in ('Home WiFi', 'Classroom'):
            for password in ('short', 'x' * 64, 'y' * 70):
                self.assertError(self.call('POST', '/api/wifi/save',
                                           {'ssid': ssid, 'password': password}),
                                 400, 'bad_password_length')
        self.assertEqual(self.fake.changes(), [])
        # 8..63 characters, or exactly 64 hex digits (a raw WPA key)
        for password in ('8chars!!', 'z' * 63, 'ab' * 32):
            self.assertEqual(self.call('POST', '/api/wifi/save',
                                       {'ssid': 'Home WiFi', 'password': password})[0], 200)


class _Capture(logging.Handler):
    """Every log record, traceback included, formatted as the log file gets it."""

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []
        self.formatter_ = logging.Formatter('%(levelname)s %(name)s %(message)s')

    def emit(self, record):
        self.lines.append(self.formatter_.format(record))


class SecretTest(SafetyCase):
    """No reply and no log line may carry a Wi-Fi password, nmcli's own
    failures included: a timed-out subprocess quotes its whole command line,
    and nmcli may quote a value it rejects. The real nmcli() wrapper runs here,
    over a fake subprocess.run that hands everything else to StatefulNmcli."""

    SECRET = 'Pa55-w0rd!x'

    def setUp(self):
        super().setUp()
        self.home = self.fake.add('Home WiFi', 'Home WiFi', 'goodpass1', prio=12)
        self.fake.router['Home WiFi'] = 'goodpass1'
        self.fake.wlan0 = ('connected', 'Home WiFi')
        self.on_secret = None        # 'timeout' | 'echo': what a command carrying SECRET does
        self.on_join = None          # stderr of a failing `con up`
        wm.nmcli = REAL_NMCLI
        patcher = mock.patch.object(wm.subprocess, 'run', self.run_nmcli)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.log = _Capture()
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        self.addCleanup(root.removeHandler, self.log)
        root.addHandler(self.log)
        root.setLevel(logging.DEBUG)

    def run_nmcli(self, cmd, **kw):
        args = tuple(cmd[1:])
        if self.on_secret and any(self.SECRET in a for a in args):
            if self.on_secret == 'timeout':
                raise subprocess.TimeoutExpired(cmd, kw.get('timeout'))
            return subprocess.CompletedProcess(
                cmd, 2, '', "Error: failed to modify 802-11-wireless-security.psk: "
                            "'%s' is not a valid PSK.\n" % self.SECRET)
        if self.on_join and ('con', 'up') in (args[:2], args[2:4]):
            return subprocess.CompletedProcess(cmd, 4, '', self.on_join + '\n')
        try:
            out = self.fake(*args)
        except RuntimeError as e:
            return subprocess.CompletedProcess(cmd, 10, '', str(e) + '\n')
        return subprocess.CompletedProcess(cmd, 0, (out or '') + '\n', '')

    def send(self, method, path, body):
        resp = self.fetch(path, method=method, allow_nonstandard_methods=True, body=json.dumps(body))
        return resp.code, resp.body.decode()

    def assertNoSecret(self, *texts):
        self.assertTrue(self.log.lines)
        for text in texts + tuple(self.log.lines):
            self.assertNotIn(self.SECRET, text)

    def test_timed_out_save_does_not_echo_the_password(self):
        self.on_secret = 'timeout'
        code, raw = self.send('POST', '/api/wifi/save', {'ssid': 'Home WiFi', 'password': self.SECRET})
        self.assertEqual(code, 504, raw)
        self.assertEqual(json.loads(raw)['code'], 'nmcli_timeout')
        self.assertNoSecret(raw)
        # the command is logged, without the password
        self.assertTrue([line for line in self.log.lines
                         if 'timed out' in line and 'wifi-sec.psk' in line], self.log.lines)
        # nothing half-done is left: the working profile as it was, no pending copy
        self.assertEqual(self.home['psk'], 'goodpass1')
        self.assertEqual(self.fake.named('Home WiFi.bb-pending'), [])

    def test_timed_out_save_of_a_new_network_does_not_echo_the_password(self):
        self.on_secret = 'timeout'
        code, raw = self.send('POST', '/api/wifi/save', {'ssid': 'Classroom', 'password': self.SECRET})
        self.assertEqual((code, json.loads(raw)['code']), (504, 'nmcli_timeout'), raw)
        self.assertNoSecret(raw)

    def test_nmcli_error_quoting_the_password_is_not_echoed(self):
        self.on_secret = 'echo'
        for ssid in ('Home WiFi', 'Classroom'):
            code, raw = self.send('POST', '/api/wifi/save', {'ssid': ssid, 'password': self.SECRET})
            self.assertEqual((code, json.loads(raw)['code']), (500, 'nmcli_failed'), raw)
            self.assertNoSecret(raw)
        # the log keeps the rest of nmcli's message
        self.assertTrue([line for line in self.log.lines if 'is not a valid PSK' in line])

    def test_timed_out_apply_boot_does_not_echo_the_password(self):
        self.assertEqual(self.send('POST', '/api/wifi/save',
                                   {'ssid': 'Home WiFi', 'password': self.SECRET})[0], 200)
        self.on_secret = 'timeout'
        code, raw = self.send('POST', '/api/wifi/apply-boot', {'ssid': 'Home WiFi'})
        self.assertEqual((code, json.loads(raw)['code']), (504, 'nmcli_timeout'), raw)
        self.assertNoSecret(raw)

    def test_failed_join_does_not_show_the_password(self):
        self.assertEqual(self.send('POST', '/api/wifi/save',
                                   {'ssid': 'Home WiFi', 'password': self.SECRET})[0], 200)
        self.on_join = 'Error: Connection activation failed: psk %s was rejected' % self.SECRET
        self.assertEqual(self.send('POST', '/api/wifi/apply-now', {'ssid': 'Home WiFi'})[0], 200)
        self.assertTrue(self.wait_for(lambda: self.last_error() is not None))
        status = self.fetch('/api/wifi/status').body.decode()
        self.assertEqual(json.loads(status)['last_error']['reason'], 'wrong_password')
        self.assertNoSecret(status)


class WebPagesTest(unittest.TestCase):
    """The drone's own pages (www/) call this API directly: every refusal it
    can send them has a clear text there, and Safe Remove is confirmed. They
    also work with a drone that sends no "code" (they show its "error")."""

    WWW = os.path.join(base.PKG, 'www')

    def page(self, name):
        with open(os.path.join(self.WWW, name), encoding='utf-8') as f:
            return f.read()

    def assertExplains(self, name, codes):
        html = self.page(name)
        for code in codes:
            self.assertIn("case '%s':" % code, html, '%s has no text for %s' % (name, code))

    def test_wifi_page(self):
        self.assertExplains('wifi.html', (
            'armed', 'fc_unknown', 'active_network', 'protected_network', 'nmcli_failed',
            'nmcli_timeout', 'unknown_network', 'bad_password_length', 'ssid_required'))
        self.assertIn('confirm_active: true', self.page('wifi.html'))

    def test_led_page(self):
        self.assertExplains('led.html', (
            'armed', 'fc_unknown', 'drone_unavailable', 'led_unavailable', 'tts_unavailable'))

    def test_gcs_page(self):
        self.assertExplains('gcs.html', ('led_unavailable', 'led_failed'))

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_inline_scripts_parse(self):
        for name in ('wifi.html', 'led.html', 'gcs.html'):
            scripts = re.findall(r'<script>(.*?)</script>', self.page(name), re.S)
            self.assertTrue(scripts, name)
            for script in scripts:
                with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
                    f.write(script)
                try:
                    res = subprocess.run(['node', '--check', f.name], capture_output=True, text=True)
                finally:
                    os.remove(f.name)
                self.assertEqual(res.returncode, 0, '%s: %s' % (name, res.stderr))
