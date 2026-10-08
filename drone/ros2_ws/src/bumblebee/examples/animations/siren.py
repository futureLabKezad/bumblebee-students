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

"""siren — show: police-style red/blue flasher + two-tone wail on the buzzer."""
import _show
from _show import drone

LEFT = (drone.LED_1, drone.LED_2, drone.LED_5)
RIGHT = (drone.LED_3, drone.LED_4, drone.LED_6)
RED = (220, 0, 0)
BLUE = (0, 0, 220)
WAIL = 'MNT100L4O5AO6DO5AO6D'  # hi-lo two-tone, 2.4 s
FLIP_S = 0.25


def frame(t):
    if int(t / FLIP_S) % 2 == 0:
        _show.paint(LEFT, RED)
        _show.paint(RIGHT, BLUE)
    else:
        _show.paint(LEFT, BLUE)
        _show.paint(RIGHT, RED)


_show.run(frame, WAIL, fps=10, gap=0.1)
