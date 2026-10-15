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

"""fire — flickering orange/red per-pixel until SIGTERM."""
import random
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

FPS = 15
FRAME = 1.0 / FPS
NUM_LEDS = 11
STRIPS = (drone.LED_1, drone.LED_2, drone.LED_3,
          drone.LED_4, drone.LED_5, drone.LED_6)

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def flicker():
    intensity = random.random()
    r = int(180 + 75 * intensity)
    g = int(30 + 70 * intensity * random.random())
    b = int(5 * random.random())
    return r, g, b


drone.led_take_control()
try:
    while _running:
        for s in STRIPS:
            for i in range(NUM_LEDS):
                drone.set_led(s, i, *flicker())
        time.sleep(FRAME)
finally:
    try:
        drone.led_off()
    except OSError:
        pass
    drone.led_release_control()
