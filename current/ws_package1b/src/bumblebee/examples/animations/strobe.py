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

"""strobe — fast white flash on all LEDs until SIGTERM."""
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

ON_MS = 50
OFF_MS = 80

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

drone.led_take_control()
try:
    while _running:
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, 255, 255, 255)
        time.sleep(ON_MS / 1000.0)
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, 0, 0, 0)
        time.sleep(OFF_MS / 1000.0)
finally:
    try:
        drone.led_off()
    except OSError:
        pass
    drone.led_release_control()
