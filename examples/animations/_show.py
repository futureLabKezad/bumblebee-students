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

"""Shared LED runner for "shows" (party, siren, alarm, victory), plus the LED
lock helpers every script in this folder uses.

A show script defines frame(t) (paint the LEDs for time t, seconds since
start) and calls run(frame). Like the plain animations it only drives the
LEDs over I2C; the show's buzzer melody is replayed by wifi_manager.py (see
SHOWS there), which already owns a ROS node. Started and stopped (SIGTERM) by
POST /api/led/animation.

take_control() / release_control() wrap drone.led_take_control() /
led_release_control() for notify_manager.py's safety alarms:
  * our PID goes into /tmp/led_busy, so notify_manager can tell when this
    process is gone and the lock is stale;
  * while notify_manager draws ERROR / LOW_BATTERY over us it raises
    /tmp/led_alarm (holding its PID); our LED writes are skipped until the
    flag is gone, then the animation simply carries on.

Flash rule for everything in this folder: at most 3 flashes per second
(photosensitive children). test/test_notify_manager.py measures it.
"""
import os
import signal
import sys
import time

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone  # noqa: E402

LOCK_FILE = getattr(drone, '_LED_BUSY_FILE', '/tmp/led_busy')
ALARM_FILE = getattr(drone, '_LED_ALARM_FILE', '/tmp/led_alarm')  # notify_manager.ALARM_FILE

_running = True


def _stop(*_):
    global _running
    _running = False


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError, ValueError):
        return False
    try:
        with open('/proc/%d/stat' % pid) as f:
            return f.read().rsplit(')', 1)[1].split()[0] not in ('Z', 'X')
    except (OSError, IndexError):
        return True


_alarm = {'key': None, 't': 0.0, 'active': False}


def alarm_active():
    """True while notify_manager draws a safety alarm over the LEDs.

    A flag whose PID is not running (notify_manager crashed) is ignored.
    """
    try:
        st = os.stat(ALARM_FILE)
    except OSError:
        return False
    key = (st.st_ino, st.st_mtime_ns)
    now = time.monotonic()
    if key != _alarm['key'] or now - _alarm['t'] > 1.0:
        try:
            with open(ALARM_FILE) as f:
                text = f.read(32).strip()
            active = not text.isdigit() or _pid_alive(int(text))
        except (OSError, ValueError):
            active = True
        _alarm.update(key=key, t=now, active=active)
    return _alarm['active']


def _gate_led_writes():
    """Make every drone.set_led() in this process (led_off() too) skip while the
    alarm flag is up."""
    raw = drone.set_led
    if getattr(raw, '_alarm_gated', False):
        return

    def set_led(*args, **kwargs):
        if alarm_active():
            return None
        return raw(*args, **kwargs)
    set_led._alarm_gated = True
    drone.set_led = set_led


def _stamp_lock():
    """Write our PID into the lock led_take_control() has just created."""
    try:
        fd = os.open(LOCK_FILE, os.O_WRONLY | os.O_TRUNC)   # never creates it
    except OSError:
        return
    try:
        os.write(fd, b'%d\n' % os.getpid())
    except OSError:
        pass
    finally:
        os.close(fd)


def take_control():
    """drone.led_take_control(), plus the PID stamp and the alarm gate above."""
    _gate_led_writes()
    drone.led_take_control()
    _stamp_lock()


def release_control():
    """Blank the LEDs (unless an alarm is showing) and release the lock."""
    try:
        drone.led_off()
    except Exception:          # a failed blank must not keep the lock taken
        pass
    finally:
        drone.led_release_control()


def run(frame, fps=10):
    """Loop frame(t) at `fps` until SIGTERM/SIGINT."""
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    take_control()
    try:
        t0 = time.time()
        while _running:
            now = time.time()
            frame(now - t0)
            time.sleep(max(0.0, 1.0 / fps - (time.time() - now)))
    finally:
        release_control()


def paint(strips, rgb):
    for s in strips:
        drone.set_led(s, drone.LED_ALL, *rgb)


def fill(rgb):
    drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *rgb)
