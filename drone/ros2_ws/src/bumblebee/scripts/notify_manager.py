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

"""
notify_manager.py -- State-driven LED + buzzer notifications for Bumblebee.

Single owner of the LED strips (replaces led_default.py). A priority state
machine maps the drone's current condition to an LED animation and, on state
entry, a buzzer tune (PX4 FCU via MAVROS /mavros/play_tune).

States (highest priority first):
  ERROR        FCU link was up and dropped     red pulse 2.5/s,      -- light only (below)
                                               never fully dark
  LOW_BATTERY  cell 2.0..3.6 V for >= 1 s      slow red blink 1/s    alarm (repeat)
  ARUCO_LOCK   fresh markers + yaw locked      green pulse           -- silent in flight
  ARUCO_SEARCH markers seen < 3 s ago          amber pulse           --
  HOTSPOT      WiFi in bumblebee-hotspot AP    cyan breathing        rising "hotspot ready"
  CONNECTING   WiFi not connected (debounced)  amber rotating ring   long "connecting" (repeat)
  IDLE         WiFi connected to a network     rainbow body          "ding"

Nothing here flashes more than 3 times per second (photosensitive children):
ERROR alternates bright and dim red 2.5 times per second and LOW_BATTERY
blinks once per second, so the two alarms also look different.

Sound. The buzzer is on the flight controller and tunes reach it through
MAVROS, so every tune is guarded on telemetry.connected and the early-boot
states (~20-25 s) are LED-only. For the same reason the FC-lost alarm (ERROR)
is LIGHT ONLY on the drone: the link it reports lost is the only way to the
buzzer. The GCS laptop app sounds that alarm instead (it sees connected=false
in /mavros/state). Sound is handled every loop iteration, whatever the LED lock.

LED lock. Other scripts take the LEDs with /tmp/led_busy (same contract as the
old led_default.py): GCS colours and animations (wifi_manager.py,
examples/animations/) and student or flight scripts (drone.led_take_control()).
While a live owner holds it the normal states are not drawn, except:
  * ERROR and LOW_BATTERY are drawn over the lock. Meanwhile /tmp/led_alarm
    (holding this process's PID) tells the owners to stop writing; the
    examples/animations scripts do (see _show.py). When the alarm clears the
    owner gets the LEDs back: the GCS colour from /tmp/led_user_color is
    repainted if it is newer than the lock, otherwise the LEDs are blanked once
    and the owner repaints them itself.
  * A stale lock is ignored and removed: one holding the PID of a process that
    is gone (the animations write their PID), or one without a PID that has
    stayed unchanged for LEGACY_LOCK_MAX_S. That age is counted on the
    monotonic clock, so the wall-clock jump after boot does not age a lock.

Runs as systemd service notify-manager.service. For a manual demo / check:
    python3 notify_manager.py --selftest
"""

import os
import sys
import json
import math
import time
import signal
import threading
import subprocess

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

LOCK_FILE = '/tmp/led_busy'
# Present while ERROR / LOW_BATTERY is drawn over a lock owner. Holds our PID,
# so a crashed notify_manager cannot leave the owners dark for good.
ALARM_FILE = '/tmp/led_alarm'
# The colour /api/led/color set last, JSON {"r": R, "g": G, "b": B} (written by
# wifi_manager). Repainted when an alarm ends, if it is newer than the lock.
USER_COLOR_FILE = '/tmp/led_user_color'
ALARM_STATES = ('ERROR', 'LOW_BATTERY')
# A lock without an owner PID (drone.led_take_control(), wifi_manager's
# colour) counts as stale after this long unchanged. A GCS colour may well stay
# for a whole lesson, hence an hour; a new colour restarts the count.
LEGACY_LOCK_MAX_S = 3600.0
# A lock whose owner PID is gone is dropped only after this long, so a lock
# being rewritten is never judged on a single read.
STALE_GRACE_S = 1.0

# --- flash rates: at most 3 flashes per second --------------------------------
ERROR_HZ = 2.5          # bright/dim red alternations per second
ERROR_FLOOR = 0.15      # dim-phase brightness: a pulse, never fully dark
LOW_BATT_HZ = 1.0       # full on/off blinks per second
LOW_BATT_ENTER_S = 1.0  # cell must read low this long before the alarm...
LOW_BATT_HOLD_S = 5.0   # ...which then stays this long after the last low reading

# --- buzzer tunes (QBASIC notation, <= 230 chars) --------------------------
TUNE_CONNECTING = 'MFT120L8O4CDEFGAB>CL4P8'   # long rising run, ~1.4 s
TUNE_HOTSPOT    = 'MFT160L8O4GO5CEG'          # rising "ready" arpeggio
TUNE_LOWBATT    = 'MFT200L8O5GEC'             # urgent descending triad
# drone.TUNE_NOTIFY -> two-tone ding-dong (connected)
# drone.TUNE_ERROR is deliberately unused: ERROR is light-only (see handle_sound).

# --- colors / brightness ----------------------------------------------------
DIM = 0.45            # extra scale on top of the hardware ~25% cap
AMBER = (255, 120, 0)
TRAIL = (120, 50, 0)  # dim amber trail for the connecting ring
CYAN  = (0, 180, 200)
GREEN = (0, 210, 50)
RED   = (255, 0, 0)
REAR  = (100, 0, 0)   # static rear color in idle
FRONT = (0, 100, 0)   # static front color in idle


def _s(c):
    """Scale a color tuple by the global DIM factor."""
    return (int(c[0] * DIM), int(c[1] * DIM), int(c[2] * DIM))


def _sb(c, b):
    """Scale a color by DIM and an extra brightness factor b in [0, 1]."""
    return (int(c[0] * DIM * b), int(c[1] * DIM * b), int(c[2] * DIM * b))


# Approximate ring order of the 6 strips around the airframe, used for the
# rotating "connecting" beacon: front-L -> body-L -> rear-L -> rear-R -> body-R
# -> front-R.
RING = [drone.LED_2, drone.LED_4, drone.LED_1, drone.LED_3, drone.LED_5, drone.LED_6]

# --- shared state -----------------------------------------------------------
_stop = threading.Event()
_telem_lock = threading.Lock()
_telem = {'connected': False, 'mode': '', 'cell': float('nan'), 'ok': False}
_wifi_lock = threading.Lock()
_wifi = {'state': 'unknown', 't': 0.0}
_seen_fcu = False         # have we ever seen FCU connected (enables ERROR)
_last_conn_t = 0.0        # monotonic time FCU was last connected
_last_play = {}           # tune key -> last monotonic play time
_low_since = None         # start of the current run of low cell readings
_low_last = None          # time of the last low cell reading
_low_active = False       # LOW_BATTERY latched (debounced)


def hue_to_rgb(h):
    """Convert hue (0-359 degrees) to (r, g, b) at full saturation/value."""
    h = h % 360
    sector = int(h // 60)
    frac = (h % 60) / 60.0
    tbl = [
        (255, int(255 * frac), 0),
        (int(255 * (1 - frac)), 255, 0),
        (0, 255, int(255 * frac)),
        (0, int(255 * (1 - frac)), 255),
        (int(255 * frac), 0, 255),
        (255, 0, int(255 * (1 - frac))),
    ]
    return tbl[sector]


# --- background pollers -----------------------------------------------------
def _telem_poller():
    """Track FCU connection / mode / cell voltage from cheap topic subscriptions.

    Uses drone.get_fcu_status() (cached /mavros/state + /mavros/battery), NOT the
    heavy /get_telemetry service. The old service-based poll did TF lookups and
    stalled under CPU load; a stall was caught here as connected=False and
    surfaced as a false ERROR -> red strobe while the FCU was actually fine.
    Now ERROR reflects the real State.connected flag, and a transient read error
    keeps the last-known status instead of faking a disconnect.
    """
    global _seen_fcu, _last_conn_t
    while not _stop.is_set():
        try:
            s = drone.get_fcu_status()
            with _telem_lock:
                _telem['connected'] = bool(s['connected'])
                _telem['mode'] = str(s['mode'])
                _telem['cell'] = float(s['cell'])
                _telem['ok'] = bool(s['ok'])
            if s['connected']:
                _seen_fcu = True
                _last_conn_t = time.monotonic()
        except Exception:
            # Do NOT flip connected=False on a transient hiccup -- that was the
            # false-ERROR (red) bug. Keep the last-known status.
            pass
        _stop.wait(0.5)


def _classify_wifi():
    """Return one of: 'hotspot', 'connected', 'connecting', 'unknown'."""
    try:
        out = subprocess.run(
            ['nmcli', '-t', '-f', 'DEVICE,STATE,CONNECTION', 'device', 'status'],
            capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return 'unknown'
    for line in out.splitlines():
        parts = line.split(':')
        if len(parts) < 3:
            continue
        dev, state, conn = parts[0], parts[1], parts[2]
        if not dev.startswith('wlan'):
            continue
        if 'hotspot' in conn.lower():
            return 'hotspot'
        if state == 'connected':
            return 'connected'
        return 'connecting'
    return 'connecting'


def _wifi_poller():
    while not _stop.is_set():
        st = _classify_wifi()
        with _wifi_lock:
            if st != _wifi['state']:
                _wifi['state'] = st
                _wifi['t'] = time.monotonic()
        _stop.wait(2.0)


# --- state machine ----------------------------------------------------------
def _low_battery(low, now):
    """Debounced LOW_BATTERY. It is drawn over the user's LEDs, so it must not
    flap on a voltage sag or fire on a single bad reading."""
    global _low_since, _low_last, _low_active
    if low:
        _low_last = now
        if _low_since is None:
            _low_since = now
        if now - _low_since >= LOW_BATT_ENTER_S:
            _low_active = True
    else:
        _low_since = None
        if _low_active and now - _low_last >= LOW_BATT_HOLD_S:
            _low_active = False
    return _low_active


def resolve_state():
    now = time.monotonic()
    with _telem_lock:
        connected = _telem['connected']
        cell = _telem['cell']
        ok = _telem['ok']
    with _wifi_lock:
        wifi = _wifi['state']
        wifi_age = now - _wifi['t']

    # 1. ERROR -- FCU link was up and dropped for > 2 s (debounced).
    if _seen_fcu and not connected and (now - _last_conn_t) > 2.0:
        return 'ERROR'
    # 2. LOW_BATTERY -- a real cell reading in the danger band (debounced).
    if _low_battery(bool(ok and cell == cell and 2.0 < cell < 3.6), now):
        return 'LOW_BATTERY'
    # 3/4. ArUco -- only meaningful while markers are fresh (i.e. in flight).
    try:
        pos_age = drone._markers_pos_age()
        locked = bool(drone._aruco_yaw_locked)
    except Exception:
        pos_age, locked = float('inf'), False
    if pos_age < 1.5 and locked:
        return 'ARUCO_LOCK'
    if pos_age < 3.0:
        return 'ARUCO_SEARCH'
    # 5/6/7. WiFi-derived states.
    if wifi == 'hotspot':
        return 'HOTSPOT'
    if wifi == 'connected':
        return 'IDLE'
    # connecting / disconnected / unknown -> CONNECTING, with a short grace
    # window to avoid flicker on brief blips.
    if wifi_age < 2.0:
        return 'IDLE'
    return 'CONNECTING'


# --- buzzer -----------------------------------------------------------------
def _guarded_play(tune, key, min_interval):
    """Play a tune if the FCU is connected and we have not played `key` recently."""
    now = time.monotonic()
    if now - _last_play.get(key, -1e9) < min_interval:
        return
    with _telem_lock:
        connected = _telem['connected']
    if not connected:
        return
    try:
        drone.play_tune(tune)
        _last_play[key] = now
    except Exception:
        pass


def handle_sound(state, prev):
    entered = (state != prev)
    if state == 'ERROR':
        # Light only, on purpose. The buzzer is on the FC and a tune reaches it
        # through MAVROS -- over the very link ERROR reports lost -- so no tune
        # can sound here (the old TUNE_ERROR call was always dropped by the
        # connected guard). The GCS laptop app sounds the FC-lost alarm. When
        # the link is back, IDLE / HOTSPOT / CONNECTING chime as usual.
        pass
    elif state == 'LOW_BATTERY':
        _guarded_play(TUNE_LOWBATT, 'lowbatt', 10.0)      # repeats while low
    elif state == 'HOTSPOT':
        if entered:
            _guarded_play(TUNE_HOTSPOT, 'hotspot', 5.0)
    elif state == 'CONNECTING':
        _guarded_play(TUNE_CONNECTING, 'connecting', 8.0)  # repeats while connecting
    elif state == 'IDLE':
        if entered and prev not in (None, 'IDLE', 'ARUCO_LOCK', 'ARUCO_SEARCH'):
            _guarded_play(drone.TUNE_NOTIFY, 'connected', 3.0)
    # ARUCO_* stay silent on purpose.


# --- LED rendering ----------------------------------------------------------
_idle_hue = 0
_conn_pos = -1


def _render_idle():
    global _idle_hue
    r, g, b = hue_to_rgb(_idle_hue)
    r, g, b = int(r * 0.4), int(g * 0.4), int(b * 0.4)
    drone.set_led(drone.LED_5, drone.LED_ALL, r, g, b)   # left long strip
    drone.set_led(drone.LED_4, drone.LED_ALL, r, g, b)   # right long strip
    drone.set_led(drone.LED_1, drone.LED_ALL, *REAR)
    drone.set_led(drone.LED_3, drone.LED_ALL, *REAR)
    drone.set_led(drone.LED_2, drone.LED_ALL, *FRONT)
    drone.set_led(drone.LED_6, drone.LED_ALL, *FRONT)
    _idle_hue = (_idle_hue + 6) % 360


def _render_connecting(t):
    """Rotating amber beacon across the 6-strip ring (looks like 'scanning')."""
    global _conn_pos
    n = len(RING)
    pos = int(t * 6) % n
    if pos == _conn_pos:
        return
    _conn_pos = pos
    for i, strip in enumerate(RING):
        if i == pos:
            drone.set_led(strip, drone.LED_ALL, *_s(AMBER))
        elif i == (pos - 1) % n:
            drone.set_led(strip, drone.LED_ALL, *_s(TRAIL))
        else:
            drone.set_led(strip, drone.LED_ALL, 0, 0, 0)


def render(state):
    t = time.monotonic()
    if state == 'ERROR':
        # 2.5 bright/dim alternations per second (limit: 3), never fully dark.
        bright = int(t * ERROR_HZ * 2) % 2 == 0
        c = _s(RED) if bright else _sb(RED, ERROR_FLOOR)
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *c)
    elif state == 'LOW_BATTERY':
        # A slow full blink, once per second: clearly not the ERROR pulse.
        c = _s(RED) if int(t * LOW_BATT_HZ * 2) % 2 == 0 else (0, 0, 0)
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *c)
    elif state == 'HOTSPOT':
        b = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * 2.2))     # slow breathing
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *_sb(CYAN, b))
    elif state == 'ARUCO_LOCK':
        b = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(t * 4.0))
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *_sb(GREEN, b))
    elif state == 'ARUCO_SEARCH':
        b = 0.20 + 0.80 * (0.5 + 0.5 * math.sin(t * 6.0))     # quick pulse
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *_sb(AMBER, b))
    elif state == 'CONNECTING':
        _render_connecting(t)
    else:  # IDLE
        _render_idle()


# --- LED lock (/tmp/led_busy) and alarm flag (/tmp/led_alarm) ----------------
def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _ident(path):
    """Identity of the current version of a file, or None if it is absent."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_size)


def _read_pid(path):
    """Owner PID written in a lock / flag file, or None (empty: owner unknown)."""
    try:
        with open(path) as f:
            text = f.read(32).strip()
    except OSError:
        return None
    if not text or any(ch not in '0123456789' for ch in text):
        return None
    pid = int(text)
    return pid if pid > 0 else None


def _pid_alive(pid):
    """True while process `pid` runs; an exited, not yet reaped one counts as gone."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass                                   # runs, as another user
    except (OSError, OverflowError, ValueError):
        return False
    try:
        with open('/proc/%d/stat' % pid) as f:
            state = f.read().rsplit(')', 1)[1].split()[0]
        return state not in ('Z', 'X')
    except (OSError, IndexError):
        return True                            # no /proc: kill() said it runs


_lock_seen = {'key': None, 't': 0.0, 'dead_t': None, 'logged': None}


def lock_status():
    """'free', 'held' or 'stale' (ignored, and removed) for LOCK_FILE."""
    ident = _ident(LOCK_FILE)
    if ident is None:
        _lock_seen['key'] = None
        return 'free'
    now = time.monotonic()
    pid = _read_pid(LOCK_FILE)
    key = (ident, pid, _ident(USER_COLOR_FILE))
    if key != _lock_seen['key']:
        # A new or rewritten lock, or a new GCS colour: its age starts now.
        _lock_seen.update(key=key, t=now, dead_t=None)
    if pid is not None:
        if _pid_alive(pid):
            _lock_seen['dead_t'] = None
            return 'held'
        if _lock_seen['dead_t'] is None:
            _lock_seen['dead_t'] = now
        if now - _lock_seen['dead_t'] < STALE_GRACE_S:
            return 'held'
        why = 'its owner (pid %d) is gone' % pid
    else:
        if now - _lock_seen['t'] <= LEGACY_LOCK_MAX_S:
            return 'held'
        why = 'it names no owner and has not changed for %d s' % LEGACY_LOCK_MAX_S
    return 'stale' if _drop_stale_lock(ident, why) else 'held'


def _drop_stale_lock(ident, why):
    """Remove a stale lock, so the next /api/led/color creates a fresh one.
    Returns False if the lock was rewritten meanwhile (judge it again)."""
    if _ident(LOCK_FILE) != ident:
        return False
    try:
        os.remove(LOCK_FILE)
        what = 'removed'
    except FileNotFoundError:
        return True
    except OSError as e:
        what = 'ignored (cannot remove it: %s)' % e
    if _lock_seen['logged'] != ident:
        _lock_seen['logged'] = ident
        print('notify_manager: stale %s %s: %s' % (LOCK_FILE, what, why), flush=True)
    return True


def _stamp_lock():
    """Write our PID into the lock drone.led_take_control() has just created,
    so a crash of this process does not leave a lock nobody releases."""
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


_alarm_flag_on = False


def _raise_alarm_flag():
    global _alarm_flag_on
    if not _alarm_flag_on or not os.path.exists(ALARM_FILE):
        tmp = '%s.%d' % (ALARM_FILE, os.getpid())
        try:
            with open(tmp, 'w') as f:
                f.write('%d\n' % os.getpid())
            os.replace(tmp, ALARM_FILE)     # atomic: never read half-written
        except OSError:
            _remove(tmp)
    _alarm_flag_on = True


def _lower_alarm_flag():
    global _alarm_flag_on
    if _alarm_flag_on:
        _remove(ALARM_FILE)
        _alarm_flag_on = False


def _user_color():
    """The GCS colour to give back after an alarm, or None.

    Only if wifi_manager wrote it after the lock was taken; a newer lock belongs
    to an animation or a script, which repaints by itself.
    """
    try:
        if os.stat(USER_COLOR_FILE).st_mtime_ns < os.stat(LOCK_FILE).st_mtime_ns:
            return None
        with open(USER_COLOR_FILE) as f:
            value = json.loads(f.read(256))
        if isinstance(value, dict):
            value = [value.get('r'), value.get('g'), value.get('b')]
        rgb = [int(x) for x in value]
    except (OSError, ValueError, TypeError):
        return None
    if len(rgb) != 3:
        return None
    return tuple(max(0, min(255, x)) for x in rgb)


def _give_back():
    """An alarm drawn over the lock is over: hand the LEDs back to the owner."""
    rgb = _user_color()
    try:
        if rgb is None:
            drone.led_off()        # leave no red behind; the owner repaints
        else:
            drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *rgb)
    except Exception:
        pass


# --- main loop --------------------------------------------------------------
_shown = None     # the state we drew last; None while the lock owner has the LEDs


def _draw(state):
    global _shown
    if state != _shown:
        _conn_pos_reset()          # the connecting ring repaints only on change
    _shown = state
    try:
        render(state)
    except Exception:
        pass


def step(prev):
    """One loop iteration: resolve the state, sound, then draw or yield."""
    global _shown
    state = resolve_state()
    handle_sound(state, prev)      # the buzzer never depends on the LED lock
    lock = lock_status()
    if state in ALARM_STATES:
        _raise_alarm_flag()
        if lock == 'held' and _shown not in ALARM_STATES:
            print('notify_manager: %s drawn over %s; the owner gets the LEDs back '
                  'when it clears' % (state, LOCK_FILE), flush=True)
        _draw(state)
    elif lock == 'held':
        if _shown in ALARM_STATES:
            _give_back()
        _lower_alarm_flag()
        _shown = None
        _conn_pos_reset()
    else:
        _lower_alarm_flag()
        _draw(state)
    return state


# --- lifecycle --------------------------------------------------------------
def _shutdown(signum, frame):
    _stop.set()
    try:
        if _shown in ALARM_STATES and lock_status() == 'held':
            _give_back()
        elif _shown is not None:   # never blank LEDs a lock owner is showing
            drone.led_off()
    except Exception:
        pass
    _lower_alarm_flag()
    os._exit(0)


def main_loop():
    prev = None
    while not _stop.is_set():
        prev = step(prev)
        time.sleep(0.05)


def _conn_pos_reset():
    global _conn_pos
    _conn_pos = -1


def selftest():
    """Cycle through every state (LED + sound) for a quick demo / verification.

    ERROR stays silent here, as on a real FC loss: its tune could never reach
    the buzzer (see handle_sound), so the selftest does not pretend it does.
    """
    # Prime telemetry once so the buzzer guard (connected check) passes and
    # the play_tune publisher / ROS node get initialized before the demo.
    try:
        t = drone.get_telemetry(frame_id='map')
        _telem['connected'] = bool(t.connected)
        _telem['ok'] = True
    except Exception:
        pass
    drone.led_take_control()   # pause the running default/notify service
    _stamp_lock()
    seq = ['CONNECTING', 'HOTSPOT', 'IDLE', 'ARUCO_SEARCH',
           'ARUCO_LOCK', 'LOW_BATTERY', 'ERROR']
    try:
        for st in seq:
            note = ' (light only: the GCS app sounds this alarm)' if st == 'ERROR' else ''
            print('selftest:', st + note, flush=True)
            handle_sound(st, None)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 3.0:
                render(st)
                time.sleep(0.05)
            drone.led_off()
            time.sleep(0.3)
    finally:
        drone.led_off()
        drone.led_release_control()
        _stop.set()
        os._exit(0)


def main():
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    if '--selftest' in sys.argv:
        drone.led_off()
        selftest()
        return
    _remove(ALARM_FILE)            # left by a crashed instance: owners would stay dark
    if lock_status() != 'held':    # a restart (clock_jump.sh) keeps the owner's LEDs
        drone.led_off()
    threading.Thread(target=_telem_poller, name='telem', daemon=True).start()
    threading.Thread(target=_wifi_poller, name='wifi', daemon=True).start()
    print('notify_manager: started', flush=True)
    main_loop()


if __name__ == '__main__':
    main()
