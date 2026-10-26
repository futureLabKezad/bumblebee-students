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

"""Two requests of the app stream to the flight stream (COORDINATION.md):

- drone.py led_blink / led_strobe flash at most 3 times per second, whatever
  freq asks (photosensitive children), and led_strobe defaults to 2.5 Hz;
- MAVROS offers MAVLink only on 127.0.0.1:5760 (owner decision 21.10.2026),
  in both copies of mavros_params.yaml.

drone.py is loaded without hardware (smbus2 is optional) and runs on a fake
clock; set_led is replaced by a recorder.
"""
import importlib.util
import os
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(PKG, '..', '..', '..', '..'))
DRONE_PY = os.path.join(PKG, 'examples', 'drone.py')


def load_drone():
    spec = importlib.util.spec_from_file_location('drone_under_test', DRONE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class BlinkLimit(unittest.TestCase):
    def setUp(self):
        self.drone = load_drone()
        self.clock = FakeClock()
        self.writes = []
        for name, fake in (('monotonic', self.clock.monotonic), ('sleep', self.clock.sleep)):
            patcher = mock.patch.object(self.drone.time, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.drone.set_led = lambda strip, led, r, g, b: self.writes.append((self.clock.t, (r, g, b) != (0, 0, 0)))

    def flashes_per_second(self, fn, duration=4.0, **kw):
        fn(255, 0, 0, duration=duration, manage_control=False, **kw)
        lit = [on for _, on in self.writes]
        starts = sum(1 for a, b in zip([False] + lit, lit) if b and not a)
        return starts / duration

    def test_blink_never_faster_than_three_per_second(self):
        for freq in (1.0, 2.5, 3.0, 4.0, 8.0, 20.0):
            with self.subTest(freq=freq):
                self.writes.clear()
                self.clock.t = 0.0
                rate = self.flashes_per_second(self.drone.led_blink, freq=freq)
                self.assertLessEqual(rate, self.drone.MAX_FLASH_HZ + 0.25)
                self.assertGreater(rate, 0)

    def test_strobe_defaults_to_two_and_a_half(self):
        rate = self.flashes_per_second(self.drone.led_strobe)
        self.assertAlmostEqual(rate, 2.5, delta=0.3)

    def test_the_limit_is_three(self):
        self.assertEqual(self.drone.MAX_FLASH_HZ, 3.0)


class MavlinkOnlyOnTheDrone(unittest.TestCase):
    def test_both_mavros_params_listen_on_loopback(self):
        for rel in ('drone/system/mavros_params.yaml', 'drone/ros2_ws/src/bumblebee/config/mavros_params.yaml'):
            with self.subTest(file=rel):
                with open(os.path.join(REPO, rel)) as f:
                    lines = [line.split('#')[0].strip() for line in f]
                urls = [line.split(':', 1)[1].strip() for line in lines if line.startswith('gcs_url:')]
                self.assertEqual(urls, ['tcp-l://127.0.0.1:5760'])


if __name__ == '__main__':
    unittest.main()
