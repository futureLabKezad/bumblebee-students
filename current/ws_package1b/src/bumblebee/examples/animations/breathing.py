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

"""breathing — white sin-pulse on all strips until SIGTERM."""
import math
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

PERIOD = 3.0
FPS = 25
FRAME = 1.0 / FPS

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

drone.led_take_control()
try:
    t0 = time.time()
    while _running:
        t = time.time() - t0
        v = 0.5 * (1.0 - math.cos(2 * math.pi * t / PERIOD))
        c = int(v * 255)
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, c, c, c)
        time.sleep(FRAME)
finally:
    try:
        drone.led_off()
    except OSError:
        pass
    drone.led_release_control()
