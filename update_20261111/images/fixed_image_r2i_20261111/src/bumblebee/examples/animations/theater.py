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
import os
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone
# _show.py, the shared LED helper: next to this script, or else the copy
# installed beside drone.py (examples/animations/) for a script copied alone.
# sim-run (runpy.run_path) does not put this script's folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(drone.__file__)), 'animations'))
import _show  # noqa: E402

STEP_MS = 120  # a pixel lights every 3 steps: < 3 flashes/s even with instant writes
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

_show.take_control()
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
    _show.release_control()
