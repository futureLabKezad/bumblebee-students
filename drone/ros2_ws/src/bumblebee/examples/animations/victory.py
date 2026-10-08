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
import _show
from _show import drone

GOLD = (245, 200, 66)
DIM = (40, 28, 6)
STEP_S = 0.12


def frame(t):
    lead = int(t / STEP_S) % len(drone.LED_RING)
    for k, strip in enumerate(drone.LED_RING):
        rgb = GOLD if k in (lead, (lead + 3) % len(drone.LED_RING)) else DIM
        drone.set_led(strip, drone.LED_ALL, *rgb)


_show.run(frame, fps=10)
