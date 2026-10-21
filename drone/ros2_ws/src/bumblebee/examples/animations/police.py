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

"""police — red/blue swapping across the body until SIGTERM.

At most 3 flashes per second (photosensitive children): the sides swap red
and blue every 0.2 s (2.5 per second per colour) with no dark phase in
between. Timed from the clock, so slow I2C writes cannot speed it up.
"""
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone
import _show  # noqa: E402

FLIP_S = 0.2
POLL_S = 0.02
LEFT = (drone.LED_1, drone.LED_2, drone.LED_5)
RIGHT = (drone.LED_3, drone.LED_4, drone.LED_6)
RED = (220, 0, 0)
BLUE = (0, 0, 220)

_running = True


def _stop(*_):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)


def paint(strips, color):
    for s in strips:
        drone.set_led(s, drone.LED_ALL, *color)


_show.take_control()
try:
    t0 = time.monotonic()
    shown = None
    while _running:
        phase = int((time.monotonic() - t0) / FLIP_S) % 2
        if phase != shown:
            if phase == 0:
                paint(LEFT, RED)
                paint(RIGHT, BLUE)
            else:
                paint(LEFT, BLUE)
                paint(RIGHT, RED)
            shown = phase
        time.sleep(POLL_S)
finally:
    _show.release_control()
