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

"""
led_default.py -- Default LED pattern for Bumblebee drone.

Runs continuously as a systemd service:
  - LED_1, LED_3 (side strips)  : flowing rainbow stream across 4 pixels
  - LED_2, LED_6 (front)        : solid green

Each of the 4 pixels on a strip holds a different hue (90 deg apart).
Every frame the base hue advances, making colours flow like a stream.

Yields to other LED scripts via lock file /tmp/led_busy:
  - When /tmp/led_busy exists   : pauses and waits
  - When /tmp/led_busy removed  : resumes immediately

Start/stop is managed by led-default.service.
Do not run directly unless testing.
"""

import sys
import os
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

LOCK_FILE  = '/tmp/led_busy'

NUM_LEDS   = 4      # number of pixels in the strip
# Hue advances 90 deg per step so the running pixel visits each rainbow colour
HUE_STEP   = 90 // NUM_LEDS   # degrees per pixel step
FRAME_TIME = 0.15   # seconds between steps -> full pass ~0.6 s
BRIGHTNESS = 0.4    # 0.0 – 1.0 scale factor to avoid blinding

FRONT_COLOR = (0, 100, 0)   # front LEDs: solid green


def hue_to_rgb(h):
    """Convert hue (0-359 degrees) to (r, g, b) at full saturation/value."""
    h = h % 360
    sector = h // 60
    frac   = (h % 60) / 60.0
    tbl = [
        (255, int(255 * frac),       0),
        (int(255 * (1 - frac)), 255, 0),
        (0, 255, int(255 * frac)),
        (0, int(255 * (1 - frac)), 255),
        (int(255 * frac),       0, 255),
        (255, 0, int(255 * (1 - frac))),
    ]
    return tbl[sector]


def set_static():
    """Paint front LEDs with static colors on startup."""
    drone.set_led(drone.LED_2, drone.LED_ALL, *FRONT_COLOR)
    drone.set_led(drone.LED_6, drone.LED_ALL, *FRONT_COLOR)


hue = 0
pos = 0          # index of the currently lit pixel (0 … NUM_LEDS-1)
_initialized = False

print('led_default: started')

try:
    while True:
        # Yield to other LED scripts
        if os.path.exists(LOCK_FILE):
            _initialized = False  # re-init when we resume
            time.sleep(0.2)
            continue

        if not _initialized:
            try:
                drone.led_off()
                set_static()
                _initialized = True
            except OSError:
                time.sleep(1.0)
                continue

        # Chase effect: one pixel runs along the strip with a changing rainbow colour.
        # Turn off the previous pixel, light up the current one.
        prev_pos = (pos - 1) % NUM_LEDS
        drone.set_led(drone.LED_1, prev_pos, 0, 0, 0)
        drone.set_led(drone.LED_3, prev_pos, 0, 0, 0)

        r, g, b = hue_to_rgb(hue)
        r = int(r * BRIGHTNESS)
        g = int(g * BRIGHTNESS)
        b = int(b * BRIGHTNESS)
        drone.set_led(drone.LED_1, pos, r, g, b)
        drone.set_led(drone.LED_3, pos, r, g, b)

        # Front LEDs stay fixed
        drone.set_led(drone.LED_2, drone.LED_ALL, *FRONT_COLOR)
        drone.set_led(drone.LED_6, drone.LED_ALL, *FRONT_COLOR)

        pos = (pos + 1) % NUM_LEDS
        hue = (hue + HUE_STEP) % 360
        time.sleep(FRAME_TIME)

except KeyboardInterrupt:
    pass

finally:
    drone.led_off()
    print('led_default: stopped')
