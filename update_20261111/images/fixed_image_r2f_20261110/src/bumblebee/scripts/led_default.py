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
  - LED_4, LED_5 (long strips)  : rainbow cycle
  - LED_1, LED_3 (rear)         : solid red
  - LED_2, LED_6 (front)        : solid green

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

# Rainbow step: degrees to advance per animation frame
HUE_STEP   = 6      # degrees per frame (360 / HUE_STEP = 60 frames per full cycle)
FRAME_TIME = 0.05   # seconds per frame -> full cycle ~3 seconds

# Rear and front brightness (0-255)
REAR_COLOR  = (100, 0, 0)   # red
FRONT_COLOR = (0, 100, 0)   # green


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
    """Paint all 4 corner point LEDs with static colors on startup."""
    drone.set_led(drone.LED_1, drone.LED_ALL, *REAR_COLOR)
    drone.set_led(drone.LED_5, drone.LED_ALL, *REAR_COLOR)
    drone.set_led(drone.LED_2, drone.LED_ALL, *FRONT_COLOR)
    drone.set_led(drone.LED_6, drone.LED_ALL, *FRONT_COLOR)

hue = 0

print('led_default: started')
drone.led_off()
set_static()

try:
    while True:
        # Yield to other LED scripts
        if os.path.exists(LOCK_FILE):
            time.sleep(0.2)
            continue

        # Rainbow frame on the long body strip
        r, g, b = hue_to_rgb(hue)
        # Scale brightness down to avoid blinding (max ~40% of 255)
        r = int(r * 0.4)
        g = int(g * 0.4)
        b = int(b * 0.4)

        drone.set_led(drone.LED_5, drone.LED_ALL, r, g, b)   # left long strip
        drone.set_led(drone.LED_4, drone.LED_ALL, r, g, b)   # right long strip

        # 4 corner point LEDs stay fixed
        drone.set_led(drone.LED_1, drone.LED_ALL, *REAR_COLOR)   # rear  = red
        drone.set_led(drone.LED_3, drone.LED_ALL, *REAR_COLOR)   # rear  = red
        drone.set_led(drone.LED_2, drone.LED_ALL, *FRONT_COLOR)  # front = green
        drone.set_led(drone.LED_6, drone.LED_ALL, *FRONT_COLOR)  # front = green

        hue = (hue + HUE_STEP) % 360
        time.sleep(FRAME_TIME)

except KeyboardInterrupt:
    pass

finally:
    drone.led_off()
    print('led_default: stopped')
