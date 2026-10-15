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

"""party — show: rainbow spinning around the body (+ Mario theme, played by wifi_manager)."""
import colorsys

import _show
from _show import drone

SPIN_S = 1.5  # one revolution of the rainbow around the ring


def frame(t):
    for k, strip in enumerate(drone.LED_RING):
        hue = (t / SPIN_S + k / len(drone.LED_RING)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        drone.set_led(strip, drone.LED_ALL, int(r * 255), int(g * 255), int(b * 255))


_show.run(frame, fps=12)
