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
    'systemctl': '#!/bin/bash\necho "$*" >> "$D/systemctl.log"\n',
    'chown': '#!/bin/bash\ntrue\n',
}


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
        self.env = dict(os.environ, D=self.d, PATH=bindir + os.pathsep + os.environ['PATH'],
                        BB_NAME_FILE=self.p('drone_name'), BB_MAC_FILE=self.p('drone_name.mac'),
                        BB_SERVICE_FILE=self.p('bumblebee.service'), BB_WLAN_ADDRESS=self.p('addr'))

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

    def run_script(self, ip):
        env = dict(self.env, FAKE_IP=ip or '')
        r = subprocess.run(['bash', SCRIPT], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def avahi_calls(self):
        log = self.read('systemctl.log') or ''
        return [line for line in log.splitlines() if 'avahi' in line]

    def test_legacy_name_without_binding_is_kept(self):
        self.write('drone_name', 'bumblebee-4')
        self.run_script('172.20.10.7')
        self.assertEqual(self.read('hostname'), 'bumblebee-4')
        self.assertIsNone(self.read('drone_name.mac'))

    def test_cloned_card_rederives_name(self):
        self.write('drone_name', 'bumblebee-4')
        self.write('drone_name.mac', 'aa:bb:cc:dd:ee:ff')
        self.run_script('172.20.10.7')
        self.assertEqual(self.read('drone_name'), 'bumblebee-7')
        self.assertEqual(self.read('drone_name.mac'), MAC)
        self.assertEqual(self.read('hostname'), 'bumblebee-7')

    def test_no_client_ip_leaves_things_alone(self):
        self.run_script('10.42.0.1')
        self.assertIsNone(self.read('drone_name'))
        self.assertIsNone(self.read('bumblebee.service'))

    def test_service_record_has_name_and_id(self):
        self.run_script('172.20.10.9')
        svc = self.read('bumblebee.service')
        self.assertIn('<txt-record>name=Bumblebee-9</txt-record>', svc)
        self.assertIn('<txt-record>id=ABCD</txt-record>', svc)

    def test_rerun_does_not_poke_avahi(self):
        self.run_script('172.20.10.9')
        first = len(self.avahi_calls())
        self.assertGreaterEqual(first, 1)
        self.run_script('172.20.10.9')    # e.g. a DHCP renewal
        self.assertEqual(len(self.avahi_calls()), first)


if __name__ == '__main__':
    unittest.main()
