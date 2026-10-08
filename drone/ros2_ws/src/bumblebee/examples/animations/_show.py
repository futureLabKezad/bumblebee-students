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

"""Shared runner for "shows": an LED pattern plus a looping PX4 buzzer melody.

A show script defines frame(t) (paint the LEDs for time t, seconds since
start) and calls run(frame, tune). Started and stopped (SIGTERM) by
wifi_manager.py via POST /api/led/animation, like the plain animations.
The buzzer is best-effort: if MAVROS is down the LEDs still run.
"""
import re
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone  # noqa: E402

_TOKEN = re.compile(r'M[FBNLS]|[TLONP]\d+|[A-G][#+-]?\d*\.*|[<>]', re.I)


def tune_seconds(tune):
    """Play length of a QBASIC (PX4 PLAY_TUNE) string, in seconds."""
    tempo, length, total = 120, 4, 0.0
    for tok in _TOKEN.findall(tune.upper()):
        head = tok[0]
        if tok.startswith('M') and len(tok) == 2 or head in '<>' or head == 'O':
            continue
        if head == 'T':
            tempo = int(tok[1:])
            continue
        if head == 'L':
            length = int(tok[1:])
            continue
        dots = tok.count('.')
        digits = re.sub(r'\D', '', tok)
        if head == 'P':
            n = int(digits)
        elif head == 'N':
            n = length
        else:
            n = int(digits) if digits else length
        d = (240.0 / tempo) / n
        total += d * (2 - 0.5 ** dots)
    return total


_running = True


def _stop(*_):
    global _running
    _running = False


def _play(tune):
    try:
        drone.play_tune(tune)
    except Exception as exc:  # buzzer is optional (no MAVROS / plugin off)
        print('show: buzzer unavailable: %s' % exc, file=sys.stderr)


def run(frame, tune, fps=10, gap=0.4):
    """Loop frame(t) at `fps` and replay `tune` with `gap` s of silence between."""
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    period = tune_seconds(tune) + gap
    drone.led_take_control()
    try:
        t0 = time.time()
        next_tune = t0
        while _running:
            now = time.time()
            if now >= next_tune:
                _play(tune)
                next_tune = now + period
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
