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

"""Simulation tests for scripts/wifi_watchdog.sh.

The real script runs against a fake `nmcli` / `ip` backed by a JSON state file
(a tiny NetworkManager model), with all intervals shortened. Runs anywhere
bash is available:  python3 -m unittest test/test_wifi_watchdog.py
"""
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHDOG = os.path.join(os.path.dirname(HERE), 'scripts', 'wifi_watchdog.sh')
HOTSPOT = 'bumblebee-hotspot'

FAKE_NMCLI = r'''#!/usr/bin/env python3
import json, os, sys, time
STATE = os.environ['FAKE_STATE']
with open(STATE) as f:
    st = json.load(f)

def save():
    with open(STATE + '.tmp', 'w') as f:
        json.dump(st, f)
    os.replace(STATE + '.tmp', STATE)

def esc(v):
    return v.replace('\\', '\\\\').replace(':', '\\:')

def find(key):
    for c in st['cons']:
        if key in (c['uuid'], c['name']):
            return c
    return None

args = sys.argv[1:]
# NetworkManager acting on its own (e.g. boot autoconnect) at a given time
auto = st.get('nm_auto')
if auto and time.time() >= auto['at'] and not auto.get('done'):
    st['conn'], st['state'] = auto['conn'], 'connected'
    auto['done'] = True
st['calls'].append(args)
if args[:1] == ['-w']:
    args = args[2:]
t = args[:2] == ['-t', '-f'] and args[2]
out = []
rc = 0
if t == 'DEVICE,CONNECTION':
    out = ['wlan0:' + esc(st['conn'])]
elif t == 'DEVICE,STATE':
    out = ['wlan0:' + st['state']]
elif t == 'UUID,NAME':
    out = ['%s:%s' % (c['uuid'], esc(c['name'])) for c in st['cons']]
elif t == 'UUID,TYPE,NAME':
    out = ['%s:802-11-wireless:%s' % (c['uuid'], esc(c['name'])) for c in st['cons']]
elif t == 'UUID,TYPE,AUTOCONNECT,NAME':
    out = ['%s:802-11-wireless:%s:%s' % (c['uuid'], c.get('auto', 'yes'), esc(c['name'])) for c in st['cons']]
elif t == 'UUID,TYPE,AUTOCONNECT-PRIORITY,TIMESTAMP,NAME':
    out = ['%s:802-11-wireless:%d:%d:%s' % (c['uuid'], c['prio'], c['ts'], esc(c['name'])) for c in st['cons']]
elif t == 'SSID' and 'list' in args:
    out = [esc(s) for s in st['visible']]
elif t == '802-11-wireless.ssid':
    # `con show <id>` is multiline output: values are NOT escaped
    out = ['802-11-wireless.ssid:' + find(args[-1])['ssid']]
elif args[:2] == ['-g', '802-11-wireless.hidden']:
    out = [find(args[-1]).get('hidden', 'no')]
elif args[:2] == ['-g', '802-11-wireless.ssid']:
    out = [esc(find(args[-1])['ssid'])]   # -g escapes like -t tabular
elif args[:2] == ['-g', 'connection.id']:
    out = [find(args[-1])['name']]
elif args[:3] == ['dev', 'wifi', 'rescan']:
    pass
elif args[:2] == ['connection', 'modify']:
    c = find(args[2])
    if 'wifi.ssid' in args:
        c['ssid'] = args[args.index('wifi.ssid') + 1]
    if 'connection.autoconnect' in args:
        c['auto'] = args[args.index('connection.autoconnect') + 1]
elif args[:2] == ['connection', 'down']:
    if find(args[2])['name'] == st['conn']:
        st['conn'], st['state'] = '', 'disconnected'
elif args[:2] == ['connection', 'up']:
    c = find(args[2])
    if c['name'] == 'bumblebee-hotspot':
        st['conn'], st['state'] = c['name'], 'connected'
        st['hotspot_ups'].append(c['ssid'])
    elif c.get('fail_first', 0) > 0:          # transient failure (busy AP)
        c['fail_first'] -= 1
        st['conn'], st['state'] = '', 'disconnected'
        rc = 4
        out = ['Error: Connection activation failed: The Wi-Fi network could not be found.']
    elif (c['ssid'] in st['visible'] or c.get('hidden') == 'yes') and c.get('psk_ok', True):
        st['conn'], st['state'] = c['name'], 'connected'
        c['ts'] = int(time.time())
    else:
        st['conn'], st['state'] = '', 'disconnected'
        rc = 4
        out = ['Error: Connection activation failed: Secrets were required, but not provided.'
               if c['ssid'] in st['visible'] else
               'Error: Connection activation failed: The Wi-Fi network could not be found.']
save()
print('\n'.join(out))
sys.exit(rc)
'''

FAKE_SS = r'''#!/usr/bin/env python3
import json, os
with open(os.environ['FAKE_STATE']) as f:
    st = json.load(f)
for n in st.get('tcp', []):     # "Recv-Q Send-Q Local:Port Peer:Port"
    print(n)
'''


def con(name, uuid, ssid=None, prio=0, ts=0, psk_ok=True):
    return {'name': name, 'uuid': uuid, 'ssid': ssid or name, 'prio': prio, 'ts': ts, 'psk_ok': psk_ok}


class WatchdogSim(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        for name, body in (('nmcli', FAKE_NMCLI), ('ss', FAKE_SS)):
            p = os.path.join(d, name)
            with open(p, 'w') as f:
                f.write(body.replace('/usr/bin/env python3', sys.executable, 1))
            os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        with open(os.path.join(d, 'addr'), 'w') as f:
            f.write('d8:3a:dd:12:ab:cd\n')
        self.state_path = os.path.join(d, 'state.json')
        self.env = dict(os.environ,
                        PATH=d + os.pathsep + os.environ['PATH'],
                        FAKE_STATE=self.state_path,
                        BB_CHECK_INTERVAL='0.2', BB_RECONNECT_INTERVAL='2', BB_SCAN_WAIT='0.2',
                        BB_JOIN_TIMEOUT='5', BB_PROBE_BACKOFF='30', BB_SWITCH_GRACE='3',
                        BB_API_SWITCH_MARKER=os.path.join(d, 'api-switch'),
                        BB_API_FAILED_LOG=os.path.join(d, 'api-failed'),
                        BB_RECONNECT_DEADLINE='60', BB_TRY_TIMEOUT='5',
                        BB_PROBE_MARKER=os.path.join(d, 'probe'),
                        BB_HOTSPOT_PIN_MARKER=os.path.join(d, 'pinned'),
                        BB_WLAN_ADDRESS=os.path.join(d, 'addr'),
                        BB_LOG=os.path.join(d, 'log'))

    def tearDown(self):
        self.tmp.cleanup()

    def run_watchdog(self, state, seconds):
        state.setdefault('calls', [])
        state.setdefault('hotspot_ups', [])
        with open(self.state_path, 'w') as f:
            json.dump(state, f)
        p = subprocess.Popen(['bash', WATCHDOG], env=self.env, start_new_session=True)
        time.sleep(seconds)
        os.killpg(p.pid, signal.SIGTERM)
        p.wait()
        with open(self.state_path) as f:
            return json.load(f)

    def ups(self, st, key):
        return [c for c in st['calls'] if 'up' in c and c[-1] == key]

    def hotspot(self, ssid='Bumblebee-1234'):
        return con(HOTSPOT, 'hs-uuid', ssid=ssid)

    # -- boot / fallback ----------------------------------------------------

    def test_no_known_network_raises_stable_hotspot(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': [], 'conn': '', 'state': 'disconnected'}, 3)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual(st['hotspot_ups'][0], 'Bumblebee-ABCD')   # last 4 of the MAC

    def test_reconnects_to_visible_known_network(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 2)
        self.assertEqual(st['conn'], 'Home')
        self.assertEqual(st['hotspot_ups'], [])

    # -- review finding: probe with a bad password must not lose the hotspot --

    def test_failed_probe_restores_hotspot_and_backs_off(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home', psk_ok=False)],
                                'visible': ['Home'], 'conn': HOTSPOT, 'state': 'connected'}, 9)
        self.assertEqual(st['conn'], HOTSPOT, 'hotspot not restored after a failed join')
        self.assertEqual(len(self.ups(st, 'u-home')), 1, 'failed network re-probed inside the backoff')
        # re-raised right after the failure, not after a full reconnect loop
        self.assertGreaterEqual(len(st['hotspot_ups']), 1)

    def test_probe_switches_to_good_network(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': HOTSPOT, 'state': 'connected'}, 8)
        self.assertEqual(st['conn'], 'Home')

    # -- review finding: GCS-requested hotspot mode must stick ---------------

    def test_pinned_hotspot_is_not_probed(self):
        open(self.env['BB_HOTSPOT_PIN_MARKER'], 'w').close()
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': HOTSPOT, 'state': 'connected'}, 5)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual(self.ups(st, 'u-home'), [])

    def test_active_hotspot_client_is_not_kicked(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': HOTSPOT, 'state': 'connected',
                                'tcp': ['0 0 10.42.0.1:9090 10.42.0.23:51234']}, 5)
        self.assertEqual(st['conn'], HOTSPOT)

    def test_hands_off_after_api_switch(self):
        with open(self.env['BB_API_SWITCH_MARKER'], 'w') as f:
            f.write(str(int(time.time())))
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': [], 'conn': '', 'state': 'connecting (configuring)'}, 2)
        self.assertEqual([c for c in st['calls'] if 'up' in c], [])

    def test_hotspot_client_without_gcs_session_does_not_block_probe(self):
        # a phone joined to the hotspot, but no GCS connection is open
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': HOTSPOT, 'state': 'connected',
                                'tcp': ['0 0 192.168.1.50:22 192.168.1.7:50000']}, 8)
        self.assertEqual(st['conn'], 'Home')

    # -- second review: failed GCS-requested switch ----------------------------

    def test_failed_gcs_switch_brings_hotspot_back_after_grace(self):
        with open(self.env['BB_API_SWITCH_MARKER'], 'w') as f:
            f.write(str(int(time.time())))
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home', psk_ok=False)],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 5)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual(self.ups(st, 'u-home'), [], 'retried the network that just failed')

    def test_network_failed_by_gcs_is_not_retried(self):
        with open(self.env['BB_API_FAILED_LOG'], 'w') as f:
            f.write('u-home %d\n' % int(time.time()))
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 3)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual(self.ups(st, 'u-home'), [])

    # -- fast hotspot when no known network is around -------------------------

    def test_saved_network_out_of_range_gives_hotspot_fast(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': [], 'conn': '', 'state': 'disconnected'}, 2.5)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual(self.ups(st, 'u-home'), [], 'tried a network that is not in range')

    def test_hidden_network_is_still_tried(self):
        hidden = con('Lab', 'u-lab')
        hidden['hidden'] = 'yes'
        st = self.run_watchdog({'cons': [self.hotspot(), hidden],
                                'visible': [], 'conn': '', 'state': 'disconnected'}, 2.5)
        self.assertEqual(st['conn'], 'Lab')

    def test_does_not_interrupt_networkmanager_joining(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': '', 'state': 'connecting (configuring)'}, 2)
        self.assertEqual([c for c in st['calls'] if 'up' in c], [])

    def test_autoconnect_only_rewritten_when_off(self):
        cons = [self.hotspot(), con('Home', 'u-home'), con('Lab', 'u-lab')]
        cons[2]['auto'] = 'no'
        st = self.run_watchdog({'cons': cons, 'visible': ['Home'], 'conn': 'Home', 'state': 'connected'}, 2)
        modified = [c[2] for c in st['calls'] if c[:2] == ['connection', 'modify']]
        self.assertEqual(sorted(set(modified)), ['u-lab'])

    # -- third review: don't fight NetworkManager, hidden networks, retries ----

    def test_no_join_on_top_of_nm_autoconnect(self):
        self.env.update(BB_SCAN_WAIT='1')
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected',
                                'nm_auto': {'conn': 'Home', 'at': time.time() + 0.6}}, 3)
        self.assertEqual(st['conn'], 'Home')
        self.assertEqual(self.ups(st, 'u-home'), [], 'restarted a join NM had already done')
        self.assertEqual(st['hotspot_ups'], [])

    def test_hidden_profile_does_not_pull_drone_off_hotspot(self):
        hidden = con('Lab', 'u-lab')
        hidden['hidden'] = 'yes'
        st = self.run_watchdog({'cons': [self.hotspot(), hidden],
                                'visible': [], 'conn': HOTSPOT, 'state': 'connected'}, 6)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual([c for c in st['calls'] if c[:2] == ['connection', 'down']], [])

    def test_wrong_password_is_not_retried(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home', psk_ok=False)],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 3)
        self.assertEqual(len(self.ups(st, 'u-home')), 1)
        self.assertEqual(st['conn'], HOTSPOT)

    def test_transient_failure_is_retried_once(self):
        flaky = con('Home', 'u-home')
        flaky['fail_first'] = 1
        st = self.run_watchdog({'cons': [self.hotspot(), flaky],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 3)
        self.assertEqual(st['conn'], 'Home')
        self.assertEqual(len(self.ups(st, 'u-home')), 2)

    def test_visible_network_tried_before_hidden(self):
        hidden = con('Lab', 'u-lab', prio=50)
        hidden['hidden'] = 'yes'
        st = self.run_watchdog({'cons': [self.hotspot(), hidden, con('Home', 'u-home')],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 3)
        self.assertEqual(st['conn'], 'Home')
        self.assertEqual(self.ups(st, 'u-lab'), [])

    # -- review findings: profile choice -----------------------------------

    def test_prefers_visible_then_priority_over_stale_lab_profile(self):
        cons = [self.hotspot(),
                con('Y', 'u-y', prio=10, ts=1782900000),          # image's lab network, out of range
                con('Classroom', 'u-new', prio=11, ts=0)]          # just provisioned by the GCS
        st = self.run_watchdog({'cons': cons, 'visible': ['Classroom'],
                                'conn': '', 'state': 'disconnected'}, 2)
        self.assertEqual(st['conn'], 'Classroom')
        self.assertEqual(self.ups(st, 'u-y'), [])

    def test_profile_name_with_colon(self):
        st = self.run_watchdog({'cons': [self.hotspot(), con('Lab:5G', 'u-lab')],
                                'visible': ['Lab:5G'], 'conn': HOTSPOT, 'state': 'connected'}, 8)
        self.assertEqual(st['conn'], 'Lab:5G')

    # -- pending profiles of wifi_manager.py (<name>.bb-pending) --------------

    def pending(self, name, uuid):
        c = con(name + '.bb-pending', uuid, ssid=name)
        c['auto'] = 'no'                 # as wifi_manager.py creates it
        return c

    def test_pending_profile_is_never_joined(self):
        # the saved Home profile has the old (wrong) password; the untested
        # new one waits in Home.bb-pending: only the GCS's apply-now joins it
        st = self.run_watchdog({'cons': [self.hotspot(), con('Home', 'u-home', psk_ok=False),
                                         self.pending('Home', 'u-pend')],
                                'visible': ['Home'], 'conn': '', 'state': 'disconnected'}, 3)
        self.assertEqual(self.ups(st, 'u-pend'), [])
        self.assertEqual(len(self.ups(st, 'u-home')), 1)
        self.assertEqual(st['conn'], HOTSPOT)

    def test_pending_profile_keeps_autoconnect_off(self):
        cons = [self.hotspot(), con('Home', 'u-home'), con('Lab', 'u-lab'), self.pending('Lab', 'u-pend')]
        cons[2]['auto'] = 'no'
        st = self.run_watchdog({'cons': cons, 'visible': ['Home'], 'conn': 'Home', 'state': 'connected'}, 2)
        modified = [c[2] for c in st['calls'] if c[:2] == ['connection', 'modify']]
        self.assertEqual(sorted(set(modified)), ['u-lab'])

    def test_only_a_pending_profile_counts_as_none_saved(self):
        # first Add drone on a fresh drone: the new network exists only as a
        # pending profile; the hotspot comes up at once, without scan rounds
        st = self.run_watchdog({'cons': [self.hotspot(), self.pending('Classroom', 'u-pend')],
                                'visible': ['Classroom'], 'conn': '', 'state': 'disconnected'}, 2)
        self.assertEqual(st['conn'], HOTSPOT)
        self.assertEqual(self.ups(st, 'u-pend'), [])
        calls = st['calls']
        first_up = next(i for i, c in enumerate(calls) if c[:2] == ['connection', 'up'] and c[-1] == HOTSPOT)
        self.assertNotIn(['dev', 'wifi', 'rescan'], calls[:first_up], 'scanned before raising the hotspot')

    def test_pending_suffix_after_a_colon_in_the_name(self):
        st = self.run_watchdog({'cons': [self.hotspot(), self.pending('Lab:5G', 'u-pend')],
                                'visible': ['Lab:5G'], 'conn': '', 'state': 'disconnected'}, 2)
        self.assertEqual(self.ups(st, 'u-pend'), [])
        self.assertEqual(st['conn'], HOTSPOT)


if __name__ == '__main__':
    unittest.main()
