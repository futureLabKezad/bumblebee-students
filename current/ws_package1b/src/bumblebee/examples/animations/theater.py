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

"""theater — chase pattern (every 3rd pixel lit) cycling around all strips."""
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

STEP_MS = 120
NUM_LEDS = 11
STRIPS = (drone.LED_1, drone.LED_2, drone.LED_3,
          drone.LED_4, drone.LED_5, drone.LED_6)
COLOR = (245, 200, 66)  # match dashboard accent

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

drone.led_take_control()
try:
    offset = 0
    while _running:
        for s in STRIPS:
            for i in range(NUM_LEDS):
                if (i + offset) % 3 == 0:
                    drone.set_led(s, i, *COLOR)
                else:
                    drone.set_led(s, i, 0, 0, 0)
        time.sleep(STEP_MS / 1000.0)
        offset = (offset + 1) % 3
finally:
    try:
        drone.led_off()
    except OSError:
        pass
    drone.led_release_control()
