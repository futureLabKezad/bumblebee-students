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
  ERROR        FCU link was up and dropped        red strobe          TUNE_ERROR
  LOW_BATTERY  cell voltage 2.0..3.6 V            fast red blink      alarm (repeat)
  ARUCO_LOCK   fresh markers + yaw locked         green pulse         -- silent in flight
  ARUCO_SEARCH markers seen < 3 s ago             amber pulse         --
  HOTSPOT      WiFi in bumblebee-hotspot AP mode  cyan breathing      rising "hotspot ready"
  CONNECTING   WiFi not connected (debounced)     amber rotating ring long "connecting" (repeat)
  IDLE         WiFi connected to a network        rainbow body        "ding"

The buzzer needs MAVROS connected to the FCU (~20-25 s after boot), so every
tune is guarded on telemetry.connected; early-boot states are LED-only.

Yields LED control to other scripts via /tmp/led_busy (same contract as the
old led_default.py): while the lock file exists the render loop pauses so the
web UI animations and flight scripts can take over. Sound is independent of the
LED lock.

Runs as systemd service notify-manager.service. For a manual demo / check:
    python3 notify_manager.py --selftest
"""

import os
import sys
import math
import time
import signal
import threading
import subprocess

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

LOCK_FILE = '/tmp/led_busy'

# --- buzzer tunes (QBASIC notation, <= 230 chars) --------------------------
TUNE_CONNECTING = 'MFT120L8O4CDEFGAB>CL4P8'   # long rising run, ~1.4 s
TUNE_HOTSPOT    = 'MFT160L8O4GO5CEG'          # rising "ready" arpeggio
TUNE_LOWBATT    = 'MFT200L8O5GEC'             # urgent descending triad
# drone.TUNE_ERROR  -> descending error motif
# drone.TUNE_NOTIFY -> two-tone ding-dong (connected)

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
    # 2. LOW_BATTERY -- a real cell reading in the danger band.
    if ok and cell == cell and 2.0 < cell < 3.6:
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
        if entered:
            _guarded_play(drone.TUNE_ERROR, 'error', 3.0)
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
        c = _s(RED) if int(t * 8) % 2 == 0 else (0, 0, 0)     # ~8 Hz strobe
        drone.set_led(drone.STRIP_ALL, drone.LED_ALL, *c)
    elif state == 'LOW_BATTERY':
        c = _s(RED) if int(t * 4) % 2 == 0 else (0, 0, 0)     # ~4 Hz blink
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


# --- lifecycle --------------------------------------------------------------
def _shutdown(signum, frame):
    _stop.set()
    try:
        drone.led_off()
    except Exception:
        pass
    os._exit(0)


def main_loop():
    prev = None
    while not _stop.is_set():
        # Yield to other LED scripts (web UI animations, flight scripts).
        if os.path.exists(LOCK_FILE):
            _conn_pos_reset()
            time.sleep(0.2)
            continue
        state = resolve_state()
        handle_sound(state, prev)
        try:
            render(state)
        except Exception:
            pass
        prev = state
        time.sleep(0.05)


def _conn_pos_reset():
    global _conn_pos
    _conn_pos = -1


def selftest():
    """Cycle through every state (LED + sound) for a quick demo / verification."""
    # Prime telemetry once so the buzzer guard (connected check) passes and
    # the play_tune publisher / ROS node get initialized before the demo.
    try:
        t = drone.get_telemetry(frame_id='map')
        _telem['connected'] = bool(t.connected)
        _telem['ok'] = True
    except Exception:
        pass
    drone.led_take_control()   # pause the running default/notify service
    seq = ['CONNECTING', 'HOTSPOT', 'IDLE', 'ARUCO_SEARCH',
           'ARUCO_LOCK', 'LOW_BATTERY', 'ERROR']
    try:
        for st in seq:
            print('selftest:', st, flush=True)
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
    drone.led_off()
    if '--selftest' in sys.argv:
        selftest()
        return
    threading.Thread(target=_telem_poller, name='telem', daemon=True).start()
    threading.Thread(target=_wifi_poller, name='wifi', daemon=True).start()
    print('notify_manager: started', flush=True)
    main_loop()


if __name__ == '__main__':
    main()
