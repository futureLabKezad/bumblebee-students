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

"""Tests for drone/tools/install_on_drone.sh, the update bundle's installer.

The real bundle is built with make_bundle.sh and installed into a fake root
(BB_ROOT), the way the installer is meant to be tested: no sudo, systemctl is
echoed. pgrep (the "package update running" check) and systemctl (called by
rollback.sh) are replaced by small scripts on PATH.
Runs anywhere bash is available:  python3 -m unittest test/test_install_on_drone.py
"""
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRONE = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
TOOLS = os.path.join(DRONE, 'tools')
APT_CONF = '/etc/apt/apt.conf.d/99-bumblebee-no-auto-upgrades'
WANTS = '/etc/systemd/system/timers.target.wants'
TIMERS = {'apt-daily.timer': '/usr/lib/systemd/system/apt-daily.timer',
          'apt-daily-upgrade.timer': '/usr/lib/systemd/system/apt-daily-upgrade.timer'}


def write_exe(path, body):
    with open(path, 'w') as f:
        f.write('#!/bin/sh\n' + body + '\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)


class InstallOnDrone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tgz = os.path.join(cls.tmp.name, 'bundle.tgz')
        subprocess.run(['bash', os.path.join(TOOLS, 'make_bundle.sh'), tgz, '9.9.9-test'],
                       check=True, capture_output=True)
        cls.bundle = os.path.join(cls.tmp.name, 'x')
        with tarfile.open(tgz) as t:
            t.extractall(cls.bundle)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory()
        d = self.case.name
        self.root = os.path.join(d, 'root')
        for sub in ('etc', 'home/lb', 'sys/class/net/wlan0', WANTS.lstrip('/')):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        self.put('/etc/environment', 'ROS_DOMAIN_ID=26\n')
        self.put('/etc/bumblebee_version', 'Bumblebee 1.0.1\n')
        self.put('/sys/class/net/wlan0/address', 'd8:3a:dd:12:20:ec\n')
        self.bin = os.path.join(d, 'bin')
        os.makedirs(self.bin)
        write_exe(os.path.join(self.bin, 'systemctl'), 'echo "(fake) systemctl $*"')
        self.not_busy = os.path.join(d, 'pgrep-idle')
        write_exe(self.not_busy, 'exit 1')
        self.busy = os.path.join(d, 'pgrep-busy')
        write_exe(self.busy, 'echo 4242; exit 0')

    def tearDown(self):
        self.case.cleanup()

    def path(self, p):
        return os.path.join(self.root, p.lstrip('/'))

    def put(self, p, text):
        with open(self.path(p), 'w') as f:
            f.write(text)

    def link_apt_timers(self):
        for name, target in TIMERS.items():
            os.symlink(target, self.path(os.path.join(WANTS, name)))

    def install(self, pgrep):
        env = dict(os.environ, BB_ROOT=self.root, BB_PGREP=pgrep,
                   PATH=self.bin + os.pathsep + os.environ['PATH'])
        return subprocess.run(['bash', os.path.join(self.bundle, 'bb-update', 'install_on_drone.sh')],
                              env=env, capture_output=True, text=True)

    def rollback(self):
        backups = os.path.join(self.root, 'home/lb/.bumblebee-update')
        (ts,) = os.listdir(backups)
        script = os.path.join(backups, ts, 'rollback.sh')
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ['PATH'])
        out = subprocess.run(['bash', script], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        with open(script) as f:
            return f.read(), out.stdout

    # -- automatic Ubuntu updates (bench, 26.10.2026) ------------------------

    def test_auto_updates_are_switched_off_and_rollback_switches_them_on(self):
        self.link_apt_timers()
        out = self.install(self.not_busy)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        with open(self.path(APT_CONF)) as f:
            conf = f.read()
        for key in ('Update-Package-Lists', 'Download-Upgradeable-Packages',
                    'AutocleanInterval', 'Unattended-Upgrade'):
            self.assertIn('APT::Periodic::%s "0";' % key, conf)
        for name in TIMERS:
            self.assertFalse(os.path.lexists(self.path(os.path.join(WANTS, name))), name + ' still enabled')
            self.assertIn('disabled %s (Ubuntu automatic updates)' % name, out.stdout)
        self.assertIn('systemctl stop apt-daily.timer apt-daily-upgrade.timer', out.stdout)

        script, ran = self.rollback()
        self.assertIn('systemctl start apt-daily.timer apt-daily-upgrade.timer', script)
        self.assertIn('(fake) systemctl start apt-daily.timer apt-daily-upgrade.timer', ran)
        self.assertFalse(os.path.lexists(self.path(APT_CONF)), 'rollback removes the apt switch-off')
        for name, target in TIMERS.items():
            link = self.path(os.path.join(WANTS, name))
            self.assertTrue(os.path.islink(link), name + ' not restored')
            self.assertEqual(os.readlink(link), target)
        with open(self.path('/etc/bumblebee_version')) as f:
            self.assertEqual(f.read(), 'Bumblebee 1.0.1\n')

    def test_timers_already_off_stay_off_after_rollback(self):
        out = self.install(self.not_busy)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn('Ubuntu automatic updates', out.stdout)
        self.assertNotIn('systemctl stop apt-daily', out.stdout)
        script, _ = self.rollback()
        self.assertNotIn('apt-daily', script)
        for name in TIMERS:
            self.assertFalse(os.path.lexists(self.path(os.path.join(WANTS, name))))

    def test_refuses_while_a_package_update_runs_and_changes_nothing(self):
        self.link_apt_timers()
        out = self.install(self.busy)
        self.assertEqual(out.returncode, 1)
        self.assertIn('an Ubuntu package update is running', out.stdout)
        self.assertIn('do not switch the drone off', out.stdout)
        self.assertFalse(os.path.lexists(self.path(APT_CONF)))
        self.assertFalse(os.path.exists(self.path('/home/lb/.bumblebee-update')), 'no backup: nothing started')
        for name in TIMERS:
            self.assertTrue(os.path.islink(self.path(os.path.join(WANTS, name))))
        with open(self.path('/etc/bumblebee_version')) as f:
            self.assertEqual(f.read(), 'Bumblebee 1.0.1\n')

    def test_version_stamp_names_the_bundle(self):
        out = self.install(self.not_busy)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        with open(self.path('/etc/bumblebee_version')) as f:
            lines = f.read().splitlines()
        self.assertTrue(lines[0].startswith('Bumblebee 9.9.9-test (repo '), lines[0])
        self.assertEqual(lines[1], 'before: Bumblebee 1.0.1')


if __name__ == '__main__':
    unittest.main()
