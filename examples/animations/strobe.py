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

"""strobe — white flash on all LEDs until SIGTERM.

At most 3 flashes per second (photosensitive children): 150 ms on + 250 ms
off, plus the I2C writes, is about 2.4 flashes/s, at 40 % white.
"""
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone
import _show  # noqa: E402

ON_MS = 150
OFF_MS = 250
LEVEL = 100   # of 255: <= 40 % white

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

_show.take_control()
try:
    while _running:
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, LEVEL, LEVEL, LEVEL)
        time.sleep(ON_MS / 1000.0)
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, 0, 0, 0)
        time.sleep(OFF_MS / 1000.0)
finally:
    _show.release_control()
