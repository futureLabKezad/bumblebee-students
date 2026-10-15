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

"""police — alternating red/blue flasher across the body until SIGTERM."""
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

ON_MS = 80
OFF_MS = 40
LEFT = (drone.LED_1, drone.LED_2, drone.LED_5)
RIGHT = (drone.LED_3, drone.LED_4, drone.LED_6)
RED = (220, 0, 0)
BLUE = (0, 0, 220)
BLACK = (0, 0, 0)

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def paint(strips, color):
    for s in strips:
        drone.set_led(s, drone.LED_ALL, *color)


def blackout():
    drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *BLACK)


drone.led_take_control()
try:
    phase = 0
    while _running:
        if phase == 0:
            paint(LEFT, RED)
            paint(RIGHT, BLUE)
        elif phase == 1:
            blackout()
        elif phase == 2:
            paint(LEFT, BLUE)
            paint(RIGHT, RED)
        else:
            blackout()
        delay = ON_MS if phase % 2 == 0 else OFF_MS
        time.sleep(delay / 1000.0)
        phase = (phase + 1) % 4
finally:
    try:
        drone.led_off()
    except OSError:
        pass
    drone.led_release_control()
