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

"""Tests for scripts/set_identity.sh with ip/hostnamectl/systemctl stubbed.

    python3 -m unittest test/test_set_identity.py
"""
import os
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), 'scripts', 'set_identity.sh')
MAC = 'd8:3a:dd:12:ab:cd'

STUBS = {
    'ip': '#!/bin/bash\n[ -n "$FAKE_IP" ] && echo "3: wlan0 inet $FAKE_IP/28 brd x scope global wlan0"\n',
    'hostnamectl': '#!/bin/bash\nif [ "$1" = "--static" ]; then cat "$D/hostname" 2>/dev/null; '
                   'else echo "$2" > "$D/hostname"; fi\n',
    # is-active: avahi runs unless $D/avahi-down exists, any other unit X only if
    # $D/active.X exists; `show -p MainPID --value X` prints $D/pid.X (or 0)
    'systemctl': '#!/bin/bash\n'
                 'if [ "$1" = is-active ]; then case "${@: -1}" in\n'
                 '  avahi-daemon) [ ! -e "$D/avahi-down" ] ;;\n'
                 '  *) [ -e "$D/active.${@: -1}" ] ;; esac; exit; fi\n'
                 'if [ "$1" = show ]; then cat "$D/pid.${@: -1}" 2>/dev/null || echo 0; exit 0; fi\n'
                 'echo "$*" >> "$D/systemctl.log"\n',
    # MAVROS process present only if $D/mavros-up exists
    'pgrep': '#!/bin/bash\n[ -e "$D/mavros-up" ]\n',
    'chown': '#!/bin/bash\ntrue\n',
}


# Stand-in for fcu_armed.py: PX4's heartbeat says $FAKE_FCU.
FCU_ARMED_STUB = 'import os\nprint(os.environ.get("FAKE_FCU", "unknown"))\n'

# Stand-in for ros_domain.py: records its arguments, answers $FAKE_DOMAIN.
ROS_DOMAIN_STUB = '''import os, sys
with open(os.path.join(os.environ['D'], 'ros_domain.log'), 'a') as f:
    f.write(' '.join(sys.argv[1:]) + '\\n')
print(os.environ.get('FAKE_DOMAIN', '37'))
'''


class SetIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        bindir = os.path.join(self.d, 'bin')
        os.mkdir(bindir)
        for name, body in STUBS.items():
            p = os.path.join(bindir, name)
            with open(p, 'w') as f:
                f.write(body)
            os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        self.p = lambda name: os.path.join(self.d, name)
        with open(self.p('addr'), 'w') as f:
            f.write(MAC + '\n')
        with open(self.p('ros_domain_stub.py'), 'w') as f:
            f.write(ROS_DOMAIN_STUB)
        with open(self.p('fcu_armed_stub.py'), 'w') as f:
            f.write(FCU_ARMED_STUB)
        self.env = dict(os.environ, D=self.d, PATH=bindir + os.pathsep + os.environ['PATH'],
                        BB_NAME_FILE=self.p('drone_name'), BB_MAC_FILE=self.p('drone_name.mac'),
                        BB_SERVICE_FILE=self.p('bumblebee.service'), BB_WLAN_ADDRESS=self.p('addr'),
                        BB_ROS_STATE=self.p('ros_domain'), BB_ROS_ENV=self.p('ros.env'),
                        BB_ROS_DOMAIN_PY=self.p('ros_domain_stub.py'), BB_BROWSE_DELAY='0',
                        BB_FCU_ARMED_PY=self.p('fcu_armed_stub.py'), BB_PROC=self.p('proc'),
                        BB_ETC_ENVIRONMENT=self.p('environment'), BB_IDENTITY_LOCK=self.p('lock'))

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        with open(self.p(name), 'w') as f:
            f.write(text + '\n')

    def read(self, name):
        try:
            with open(self.p(name)) as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    def run_script(self, ip, **extra):
        env = dict(self.env, FAKE_IP=ip or '', **extra)
        r = subprocess.run(['bash', SCRIPT], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def avahi_calls(self):
        log = self.read('systemctl.log') or ''
        return [line for line in log.splitlines() if 'avahi' in line and 'is-active' not in line]

    def test_name_comes_from_mac_without_network(self):
        self.run_script('10.42.0.1')            # hotspot mode, first boot
        self.assertEqual(self.read('hostname'), 'bumblebee-abcd')
        svc = self.read('bumblebee.service')
        self.assertIn('<txt-record>name=Bumblebee-ABCD</txt-record>', svc)
        self.assertIn('<txt-record>id=ABCD</txt-record>', svc)
        self.assertIsNone(self.read('drone_name'))

    def test_name_does_not_follow_the_ip(self):
        self.run_script('172.20.10.7')
        self.run_script('192.168.1.192')
        self.assertEqual(self.read('hostname'), 'bumblebee-abcd')

    def test_ip_derived_name_is_retired(self):
        self.write('drone_name', 'bumblebee-4')  # baked into the V1.0.0-beta image
        self.run_script('172.20.10.7')
        self.assertEqual(self.read('hostname'), 'bumblebee-abcd')
        self.assertIsNone(self.read('drone_name'))

    def test_custom_name_is_kept_and_bound(self):
        self.write('drone_name', 'Falcon')
        self.run_script('172.20.10.7')
        self.assertEqual(self.read('hostname'), 'falcon')
        self.assertIn('<txt-record>name=Falcon</txt-record>', self.read('bumblebee.service'))
        self.assertEqual(self.read('drone_name.mac'), MAC)

    def test_custom_name_of_another_drone_is_ignored(self):
        self.write('drone_name', 'falcon')
        self.write('drone_name.mac', 'aa:bb:cc:dd:ee:ff')
        self.run_script('172.20.10.7')
        self.assertEqual(self.read('hostname'), 'bumblebee-abcd')
        self.assertEqual(self.read('drone_name'), 'falcon')   # left for its own drone

    def test_invalid_custom_name_is_ignored(self):
        self.write('drone_name', 'my_drone!')
        self.run_script('172.20.10.7')
        self.assertEqual(self.read('hostname'), 'bumblebee-abcd')

    def test_custom_name_equal_to_default_displays_like_it(self):
        self.write('drone_name', 'bumblebee-abcd')
        self.run_script('172.20.10.7')
        self.assertIn('<txt-record>name=Bumblebee-ABCD</txt-record>', self.read('bumblebee.service'))

    def test_no_mac_leaves_things_alone(self):
        with open(self.p('addr'), 'w') as f:
            f.write('')
        self.run_script('172.20.10.7')
        self.assertIsNone(self.read('hostname'))
        self.assertIsNone(self.read('bumblebee.service'))

    def test_avahi_is_never_waited_for(self):
        # Run inside bumblebee-identity.service, which avahi is ordered after:
        # a blocking restart would wait for the service itself forever.
        self.run_script('172.20.10.9')
        calls = self.avahi_calls()
        self.assertTrue(calls)
        for line in calls:
            self.assertIn('--no-block', line)

    def test_avahi_not_running_yet_is_left_alone(self):
        open(self.p('avahi-down'), 'w').close()   # boot: avahi starts after us
        self.run_script('172.20.10.9')
        self.assertEqual(self.avahi_calls(), [])
        self.assertEqual(self.read('hostname'), 'bumblebee-abcd')

    # ---- per-drone ROS 2 domain ----

    def ros_env(self):
        return self.read('ros.env') or ''

    def restarts(self):
        log = self.read('systemctl.log') or ''
        return [line for line in log.splitlines() if 'restart' in line and 'avahi' not in line]

    def unit(self, name, pid, domain=None):
        """Pretend systemd unit `name` runs main PID `pid` with ROS_DOMAIN_ID=domain."""
        open(self.p('active.' + name), 'w').close()
        self.write('pid.' + name, str(pid))
        os.makedirs(self.p('proc/%d' % pid), exist_ok=True)
        env = ['PATH=/usr/bin'] + (['ROS_DOMAIN_ID=%s' % domain] if domain is not None else [])
        with open(self.p('proc/%d/environ' % pid), 'w') as f:
            f.write('\0'.join(env) + '\0')

    def stack(self, domain):
        self.unit('bumblebee', 100, domain)
        open(self.p('mavros-up'), 'w').close()

    def test_domain_written_and_advertised(self):
        self.run_script('192.168.1.5', FAKE_DOMAIN='37')
        self.assertIn('ROS_DOMAIN_ID=37', self.ros_env().splitlines())
        self.assertIn('FASTDDS_BUILTIN_TRANSPORTS=UDPv4', self.ros_env().splitlines())
        self.assertIn('<txt-record>ros_domain=37</txt-record>', self.read('bumblebee.service'))
        self.assertIn('ROS_DOMAIN_ID=37', self.read('environment').splitlines())

    def test_other_drones_are_looked_at_only_on_a_client_wifi(self):
        self.run_script('10.42.0.1')               # own hotspot
        self.run_script('192.168.1.5')             # shared Wi-Fi
        calls = self.read('ros_domain.log').splitlines()
        self.assertNotIn('--browse', calls[0])
        self.assertIn('--browse', calls[1])
        self.assertIn('--id ABCD', calls[1])

    def test_boot_applies_a_new_domain_without_restarts(self):
        self.write('ros.env', 'ROS_DOMAIN_ID=12')
        self.run_script('', FAKE_DOMAIN='37')      # nothing running yet
        self.assertIn('ROS_DOMAIN_ID=37', self.ros_env())
        self.assertEqual(self.restarts(), [])

    def test_stack_moves_only_on_px4_disarmed(self):
        self.write('ros.env', 'ROS_DOMAIN_ID=12')
        self.stack(12)
        self.run_script('192.168.1.5', FAKE_DOMAIN='37', FAKE_FCU='disarmed')
        self.assertIn('ROS_DOMAIN_ID=37', self.ros_env())
        self.assertEqual(self.restarts(), ['--no-block try-restart bumblebee wifi-manager notify-manager'])

    def test_armed_or_unknown_keeps_everything_on_the_running_domain(self):
        for fcu in ('armed', 'unknown'):
            self.write('ros.env', 'ROS_DOMAIN_ID=12')
            self.stack(12)
            self.unit('wifi-manager', 200, 12)
            self.run_script('192.168.1.5', FAKE_DOMAIN='37', FAKE_FCU=fcu)
            self.assertIn('ROS_DOMAIN_ID=12', self.ros_env(), fcu)
            self.assertIn('<txt-record>ros_domain=12</txt-record>', self.read('bumblebee.service'), fcu)
            self.assertIn('ROS_DOMAIN_ID=12', self.read('environment'), fcu)
            self.assertEqual(self.restarts(), [], fcu)

    def test_helpers_follow_when_the_stack_is_not_running(self):
        self.write('ros.env', 'ROS_DOMAIN_ID=12')
        self.unit('wifi-manager', 200, 12)         # started at boot on the old domain
        self.unit('notify-manager', 300, 37)       # already right
        self.run_script('192.168.1.5', FAKE_DOMAIN='37')
        self.assertEqual(self.restarts(), ['--no-block try-restart wifi-manager'])

    def test_stack_started_before_domains_counts_as_domain_0(self):
        self.stack(None)                           # updated from rc3: no ROS_DOMAIN_ID at all
        self.run_script('192.168.1.5', FAKE_DOMAIN='37', FAKE_FCU='disarmed')
        self.assertIn('--no-block try-restart bumblebee wifi-manager notify-manager', self.restarts())

    def test_etc_environment_keeps_exactly_one_domain_line(self):
        self.write('environment', 'PATH="/usr/bin"\nFASTDDS_BUILTIN_TRANSPORTS=UDPv4\nROS_DOMAIN_ID=5')
        self.run_script('192.168.1.5', FAKE_DOMAIN='37')
        lines = self.read('environment').splitlines()
        self.assertEqual([l for l in lines if l.startswith('ROS_DOMAIN_ID=')], ['ROS_DOMAIN_ID=37'])
        self.assertIn('PATH="/usr/bin"', lines)
        self.assertIn('FASTDDS_BUILTIN_TRANSPORTS=UDPv4', lines)

    def test_rerun_does_not_poke_avahi(self):
        self.run_script('172.20.10.9')
        first = len(self.avahi_calls())
        self.assertGreaterEqual(first, 1)
        self.run_script('172.20.10.9')    # e.g. a DHCP renewal
        self.assertEqual(len(self.avahi_calls()), first)


if __name__ == '__main__':
    unittest.main()
