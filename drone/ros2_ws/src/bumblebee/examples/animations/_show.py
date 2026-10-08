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

"""Shared LED runner for "shows" (party, siren, alarm, victory).

A show script defines frame(t) (paint the LEDs for time t, seconds since
start) and calls run(frame). Like the plain animations it only drives the
LEDs over I2C; the show's buzzer melody is replayed by wifi_manager.py (see
SHOWS there), which already owns a ROS node. Started and stopped (SIGTERM) by
POST /api/led/animation.
"""
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone  # noqa: E402

_running = True


def _stop(*_):
    global _running
    _running = False


def run(frame, fps=10):
    """Loop frame(t) at `fps` until SIGTERM/SIGINT."""
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    drone.led_take_control()
    try:
        t0 = time.time()
        while _running:
            now = time.time()
            frame(now - t0)
            time.sleep(max(0.0, 1.0 / fps - (time.time() - now)))
    finally:
        try:
            drone.led_off()
        except OSError:
            pass
        drone.led_release_control()


def paint(strips, rgb):
    for s in strips:
        drone.set_led(s, drone.LED_ALL, *rgb)


def fill(rgb):
    drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *rgb)
