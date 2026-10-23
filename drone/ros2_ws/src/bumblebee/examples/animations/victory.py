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

"""victory — show: golden chase around the ring (+ fanfare, played by wifi_manager)."""
import os
import sys

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone  # noqa: E402
# _show.py, the shared LED helper: next to this script, or else the copy
# installed beside drone.py (examples/animations/) for a script copied alone.
# sim-run (runpy.run_path) does not put this script's folder on sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(drone.__file__)), 'animations'))
import _show  # noqa: E402

GOLD = (245, 200, 66)
DIM = (40, 28, 6)
STEP_S = 0.2   # each strip lights every 3 steps: 1.7 flashes/s (limit 3)


def frame(t):
    lead = int(t / STEP_S) % len(drone.LED_RING)
    for k, strip in enumerate(drone.LED_RING):
        rgb = GOLD if k in (lead, (lead + 3) % len(drone.LED_RING)) else DIM
        drone.set_led(strip, drone.LED_ALL, *rgb)


_show.run(frame, fps=10)
