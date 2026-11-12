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
led_strip.py -- LED strip animation demo for Bumblebee drone.

Animations on 6 strips via I2C (ATtiny slave 0x30):
  - Running fire (blue) on LED_3 and LED_6 every 100 ms
  - Police blinker (red/blue) on LED_1,2,4,5 every 500 ms

Run (no ROS2 required):
    python3 led_strip.py

Strip indices (ATtiny PA-pin numbers):
  LED_1=0  LED_2=5  LED_3=1  LED_4=3  LED_5=2  LED_6=4
"""

import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

STRIP_LEN = 11    # pixels per long strip (indices 0-10)
T_FAST    = 0.10  # running fire step interval, seconds
T_BLINK   = 0.50  # blinker toggle interval, seconds
T_RUN     = 30.0  # total demo duration, seconds

run_pos     = 0
blink_state = False
t_fast      = time.time()
t_blink     = time.time()

print('=== LED Strip Demo ===')
drone.led_take_control()   # pause led_default.py

deadline = time.time() + T_RUN

try:
    while time.time() < deadline:
        now = time.time()

        # Running fire on LED_3 (strip=1) and LED_6 (strip=4)
        if now - t_fast >= T_FAST:
            t_fast = now
            prev_pos = (run_pos - 1) % STRIP_LEN

            drone.set_led(drone.LED_3, prev_pos, 0, 0, 0)
            drone.set_led(drone.LED_6, prev_pos, 0, 0, 0)
            drone.set_led(drone.LED_3, run_pos,  0, 0, 100)
            drone.set_led(drone.LED_6, run_pos,  0, 0, 100)

            run_pos = (run_pos + 1) % STRIP_LEN

        # Blinker: LED_1,4 red / LED_2,5 blue (alternating)
        if now - t_blink >= T_BLINK:
            t_blink = now
            blink_state = not blink_state

            if blink_state:
                drone.set_led(drone.LED_1, drone.LED_ALL, 100, 0, 0)
                drone.set_led(drone.LED_4, drone.LED_ALL, 100, 0, 0)
                drone.set_led(drone.LED_2, drone.LED_ALL, 0, 0, 0)
                drone.set_led(drone.LED_5, drone.LED_ALL, 0, 0, 0)
            else:
                drone.set_led(drone.LED_1, drone.LED_ALL, 0, 0, 0)
                drone.set_led(drone.LED_4, drone.LED_ALL, 0, 0, 0)
                drone.set_led(drone.LED_2, drone.LED_ALL, 0, 0, 100)
                drone.set_led(drone.LED_5, drone.LED_ALL, 0, 0, 100)

except KeyboardInterrupt:
    print('\nInterrupted.')

finally:
    drone.led_off()
    drone.led_release_control()   # resume led_default.py
    print('LEDs off, default pattern restored.')
