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

"""WiFi Manager — Tornado REST API on 0.0.0.0:8765 (used directly by the GCS app).

Safety rules, each in one place:
  - _fcu_refusal: Wi-Fi changes and sounds need a fresh, linked, disarmed
    flight controller ("unknown = armed"); one exception keeps first-time
    setup on the drone's own hotspot working;
  - _save_network: a new password is tried in a pending profile before it
    replaces a profile that works;
  - _switch_gen / _join_failed: only the newest Wi-Fi request acts on a failed
    join, and the hotspot is never raised over a link that is up;
  - _is_protected: the setup hotspot cannot be changed through the API;
  - SHOW_MAX_S: animations stop by themselves;
  - every error reply is {"error": text, "code": stable snake_case string}.
"""

import json
import logging
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta

import bcrypt
import shutil
import tornado.ioloop
import tornado.web

CONFIG_PATH = '/etc/wifi-manager/config.json'
LOG_PATH = '/var/log/wifi-manager-api.log'
HOTSPOT_CONN = 'bumblebee-hotspot'

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
try:
    import drone as _drone
    _LED_OK = True
except Exception as _e:
    logging.warning('drone.py import failed, LED endpoints disabled: %s', _e)
    _LED_OK = False

sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/scripts')
try:
    from tts_buzzer import tts_to_tune as _tts_to_tune
    _TTS_OK = shutil.which('espeak-ng') is not None
except Exception as _te:
    logging.warning('tts_buzzer import failed: %s', _te)
    _TTS_OK = False
    _tts_to_tune = None
LED_BUSY = '/tmp/led_busy'
ANIM_DIR = '/home/lb/ros2_ws/src/bumblebee/examples/animations'
# Shows = an LED script from ANIM_DIR plus a buzzer melody that this process
# replays (it already owns a ROS node via drone.py, so the LED script stays
# I2C-only like the other animations). name -> (drone.py tune constant or
# literal QBASIC tune, seconds of silence between repeats).
SHOWS = {
    'party':   ('TUNE_MARIO', 0.6),
    'siren':   ('MNT100L4O5AO6DO5AO6D', 0.1),   # hi-lo two-tone wail
    'alarm':   ('TUNE_WARN', 0.5),
    'victory': ('TUNE_VICTORY', 1.5),
}
ANIMATIONS = {'breathing', 'rainbow', 'police', 'strobe', 'fire', 'theater',
              'rainbow_theater'} | set(SHOWS)
# Every animation and show started through /api/led/animation stops by itself
# after this long (a forgotten siren must not run all lesson; the GCS can
# start it again). /api/led/status reports the seconds left.
SHOW_MAX_S = 120
# Touched before every API-driven Wi-Fi switch. wifi_watchdog.sh and the NM
# dispatcher hold off their hotspot fallback while it is fresh, so they don't
# abort a join that is still authenticating / getting DHCP.
WIFI_SWITCH_MARKER = '/tmp/bumblebee-wifi-switch'
# Delay before a connection-changing nmcli call, so the HTTP reply reaches the
# GCS before the drone drops the link the GCS is talking over.
SWITCH_DELAY_S = 1.5
# How long a GCS-requested join may take before we give up and bring the
# hotspot back (auth + DHCP on a slow hotspot can take ~20 s).
JOIN_TIMEOUT_S = 40
# Networks whose GCS-requested join just failed ("uuid epoch" lines);
# wifi_watchdog.sh backs off from them like from its own failed probes.
WIFI_FAILED_LOG = '/tmp/bumblebee-wifi-failed'
# Present while the GCS asked for hotspot mode: wifi_watchdog.sh then stops
# probing for known networks (which would switch the drone back to client).
HOTSPOT_PIN_MARKER = '/tmp/bumblebee-hotspot-pinned'
# New credentials wait in a profile "<name>.bb-pending" until a join proved
# them (see _save_network); never listed to the GCS as a saved network.
PENDING_SUFFIX = '.bb-pending'
# A pending profile that no apply-now / apply-boot asked for is dropped after this.
PENDING_TTL_S = 120
# GET /api/info
VERSION_FILE = '/etc/bumblebee_version'                       # first line: the image
AVAHI_SERVICE_FILE = '/etc/avahi/services/bumblebee.service'  # TXT name= (set_identity.sh)
STACK_DOMAIN_FILE = '/run/bumblebee-stack/domain'             # "<domain> <pid>" (start_bumblebee.sh)
PROC_DIR = '/proc'
API_CONTRACT = 1    # bumped only when this API changes incompatibly
_anim_proc = None  # subprocess.Popen | None
_show_gen = 0      # bumped on every animation stop/start; ends a show's tune loop


def _stop_anim():
    global _anim_proc, _show_gen
    _show_gen += 1
    if _anim_proc is not None and _anim_proc.poll() is None:
        try:
            _anim_proc.terminate()
            _anim_proc.wait(timeout=1.5)
        except subprocess.TimeoutExpired:
            _anim_proc.kill()
            try:
                _anim_proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
        except Exception:
            logging.exception('stop_anim error')
    _anim_proc = None


def _expire_anim(gen):
    """SHOW_MAX_S after an animation started: stop it if it is still the one
    running (gen unchanged), and give the LEDs back to notify_manager, as
    POST /api/led/reset does."""
    if gen != _show_gen or _anim_proc is None:
        return
    name = getattr(_anim_proc, '_name', '?')
    _stop_anim()
    try:
        os.remove(LED_BUSY)
    except OSError:
        pass
    logging.info('animation %s stopped after its %s s limit', name, SHOW_MAX_S)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)

# In-memory sessions: {token: expiry_datetime}
SESSIONS = {}
SESSION_TTL = timedelta(hours=24)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def nmcli(*args, timeout=15):
    """Run nmcli, return stdout. Raises RuntimeError on non-zero exit."""
    result = subprocess.run(
        ['nmcli'] + list(args),
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _mark_wifi_switch():
    try:
        with open(WIFI_SWITCH_MARKER, 'w') as f:
            f.write(str(int(time.time())))
    except OSError:
        logging.exception('cannot write %s', WIFI_SWITCH_MARKER)


def _clear_switch_marker():
    try:
        os.remove(WIFI_SWITCH_MARKER)
    except OSError:
        pass


# Serialises what the handlers and the join workers do to pending profiles,
# and bumps of the switch generation.
_wifi_lock = threading.RLock()
# Bumped by every request that changes the Wi-Fi link (apply-now, mode, a
# confirmed delete of the network in use) or replaces a pending change. A join
# worker acts only while its generation is still the newest: a stale one never
# switches, and its failure never raises the hotspot over a newer connection.
_switch_gen = 0
# name -> pending record of a saved but not yet proven profile, see _save_network
_pending = {}


def _bump_switch_gen():
    global _switch_gen
    with _wifi_lock:
        _switch_gen += 1
        return _switch_gen


def _run_handler(fn, *args):
    if fn is None:
        return
    try:
        fn(*args)
    except Exception:
        logging.exception('switch handler')


def _nmcli_after_reply(*args, on_fail=None, on_ok=None, on_skip=None, gen=None, action=None):
    """Run a link-changing nmcli command after the current reply is sent.

    `nmcli con up/down` on wlan0 tears down the network the GCS is connected
    through, so it must not run before the response is flushed. Right before
    it runs, the request is checked again: `gen` must still be the newest
    switch generation (else a newer Wi-Fi request superseded it), and the
    flight-controller rule for `action` (see _fcu_refusal) must still allow
    it. If not, on_skip(reason) runs instead, reason being 'superseded' or the
    refusal code. on_fail(exc) runs if the command fails or times out, on_ok()
    if it succeeds.
    """
    _mark_wifi_switch()

    def worker():
        time.sleep(SWITCH_DELAY_S)
        why = None
        if gen is not None and gen != _switch_gen:
            why = 'superseded'
        elif action is not None:
            refusal = _fcu_refusal(action)
            if refusal is not None:
                why = refusal[1]
        if why is not None:
            logging.warning('nmcli %s not run: %s', ' '.join(args), why)
            if why != 'superseded':
                _clear_switch_marker()       # nothing is switching after all
            _run_handler(on_skip, why)
            return
        try:
            nmcli('-w', str(JOIN_TIMEOUT_S), *args, timeout=JOIN_TIMEOUT_S + 10)
        except Exception as exc:
            logging.exception('nmcli %s failed', ' '.join(args))
            _run_handler(on_fail, exc)
            return
        logging.info('nmcli %s: ok', ' '.join(args))
        _run_handler(on_ok)

    threading.Thread(target=worker, daemon=True, name='wifi-switch').start()


def _in_background(loop, fn, *args):
    """Run a blocking call (nmcli) on the IOLoop's executor, logging failures.
    Used from IOLoop timers (call_later)."""
    def run():
        try:
            fn(*args)
        except Exception:
            logging.exception('%s failed', getattr(fn, '__name__', 'background call'))
    loop.run_in_executor(None, run)


# Why the last GCS-requested join failed; reported in /api/wifi/status so the
# GCS can tell the user (read over the hotspot the drone falls back to).
LAST_ERROR_FILE = '/tmp/bumblebee-wifi-last-error.json'


def _join_reason(exc):
    """Map an nmcli failure to a short reason code for the GCS."""
    text = str(exc).lower()
    if isinstance(exc, subprocess.TimeoutExpired) or 'timeout' in text or 'timed out' in text:
        return 'timeout'
    if 'secrets were required' in text or 'no secrets' in text or 'psk' in text or '802.1x' in text:
        return 'wrong_password'
    if 'no network with ssid' in text or 'ssid-not-found' in text or 'not found' in text:
        return 'not_found'
    if 'ip configuration' in text or 'dhcp' in text:
        return 'no_ip'
    return 'failed'


def _write_last_error(name, reason, message=''):
    try:
        with open(LAST_ERROR_FILE, 'w') as f:
            json.dump({'ssid': name, 'reason': reason, 'message': message[-300:],
                       'time': int(time.time())}, f)
    except OSError:
        logging.exception('cannot record join error')


def _wlan0():
    """(state, connection name) of wlan0, as NetworkManager reports it now."""
    raw = nmcli('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device', 'status')
    for line in raw.splitlines():
        parts = _nm_fields(line)
        if parts[0] == 'wlan0':
            state = parts[1] if len(parts) > 1 else ''
            conn = parts[2] if len(parts) > 2 else ''
            return state, ('' if conn == '--' else conn)
    return '', ''


def _wlan0_or_none():
    """_wlan0(), or (None, None) when it cannot be read."""
    try:
        return _wlan0()
    except Exception:
        logging.exception('cannot read the wlan0 state')
        return None, None


def _join_failed(name, exc=None, rec=None, gen=None):
    """A GCS-requested join of `name` failed (wrong password, out of range, no
    DHCP, or a newer join took wlan0 over); rec is its pending profile, if it
    tried one, gen the switch generation of its request.

    - wlan0 connected to the very profile it tried (NetworkManager finished
      after nmcli gave up): that is a success after all.
    - A pending profile is deleted; the profile it would have replaced stays
      exactly as it was and is not put in back-off.
    - Only the newest request acts further: it records why for the GCS
      (last_error in /api/wifi/status), tells wifi_watchdog.sh not to retry a
      saved profile that failed, and brings the hotspot straight back so the
      GCS can reach the drone again -- unless wlan0 is connected right now (to
      the hotspot already, or back on another client network).
    """
    tried = rec['pending'] if rec is not None else name
    state, conn = _wlan0_or_none()
    if state == 'connected' and conn == tried:
        logging.info('join of %s reported a failure, but wlan0 is connected to it', name)
        if rec is not None:
            _promote_pending(rec)
        return
    if rec is not None and rec.get('gen') == gen:
        _discard_pending(rec)
    if gen is not None and gen != _switch_gen:
        logging.info('join of %s failed after a newer Wi-Fi request; that one decides', name)
        return
    _write_last_error(name, _join_reason(exc) if exc else 'failed', str(exc) if exc else '')
    if rec is None:
        try:
            con_uuid = nmcli('-g', 'connection.uuid', 'con', 'show', name).strip()
            with open(WIFI_FAILED_LOG, 'a') as f:
                f.write('%s %d\n' % (con_uuid, int(time.time())))
        except Exception:
            logging.exception('cannot record failed join of %s', name)
    _clear_switch_marker()               # nothing deliberate is pending any more
    state, conn = _wlan0_or_none()       # again: deleting the pending profile may change it
    if state == 'connected' and conn:
        logging.info('join of %s failed; wlan0 is on %s, hotspot not raised', name, conn)
        return
    ssid = _hotspot_ssid()
    if ssid:
        nmcli('connection', 'modify', HOTSPOT_CONN, 'wifi.ssid', ssid)
    nmcli('connection', 'up', HOTSPOT_CONN, timeout=30)
    logging.info('join of %s failed, hotspot back up', name)


def _con_uuid(ref):
    """UUID of a saved connection, '' if it cannot be read."""
    try:
        out = nmcli('-g', 'connection.uuid', 'con', 'show', ref).strip()
    except Exception:
        logging.exception('cannot read the uuid of %s', ref)
        return ''
    return out.splitlines()[0].strip() if out else ''


def _save_network(name, password):
    """POST /api/wifi/save. New credentials never overwrite a profile that works.

    They go into a pending profile "<name>.bb-pending": a clone of the
    existing profile with the new password, or a new profile. Autoconnect
    leaves it alone (autoconnect off, lowest priority). apply-now then joins
    that one: only a join that succeeds replaces the old profile
    (_promote_pending); a failed one deletes it (_join_failed), so a typo
    cannot cut the drone off its classroom network. apply-boot cannot test
    anything and stores it as before (_store_pending_for_boot). Nobody asking
    within PENDING_TTL_S drops it. Without a password, an existing profile
    only becomes the preferred one, as before.

    Returns the pending record, or None when nothing is pending.
    """
    with _wifi_lock:
        names = _con_names()
        if name in names and not password:
            nmcli('con', 'modify', name,
                  'connection.autoconnect', 'yes',
                  'connection.autoconnect-priority', _next_wifi_priority())
            return None
        pname = name + PENDING_SUFFIX
        old = _pending.get(name)
        if old is not None or pname in names:
            # replaces an earlier pending change: a join still trying it is stale now
            _bump_switch_gen()
            if old is not None:
                _discard_pending(old)
            else:
                nmcli('con', 'delete', pname)
        quiet = ('connection.autoconnect', 'no', 'connection.autoconnect-priority', '0')
        if name in names:
            nmcli('con', 'clone', name, pname)
            try:
                nmcli('con', 'modify', pname, 'wifi-sec.psk', password, *quiet)
            except Exception:
                _delete_quietly(pname)
                raise
        elif password:
            nmcli('con', 'add', 'type', 'wifi', 'con-name', pname, 'ssid', name,
                  'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.psk', password, *quiet)
        else:
            nmcli('con', 'add', 'type', 'wifi', 'con-name', pname, 'ssid', name, *quiet)
        rec = {'name': name, 'pending': pname, 'uuid': _con_uuid(pname),
               'password': password, 'gen': None}
        _pending[name] = rec
        logging.info('save: new settings for %s wait in %s', name, pname)
        return rec


def _delete_quietly(ref):
    try:
        nmcli('con', 'delete', ref)
    except Exception:
        logging.exception('cannot delete %s', ref)


def _promote_pending(rec):
    """The pending profile joined, so its password works: it becomes the network.

    The old profile of that name is deleted first (it is not the one in use:
    the pending one is) and the pending one renamed after it, so a restart in
    between leaves something _recover_pending() finishes.
    """
    with _wifi_lock:
        if rec.get('final'):
            return
        rec['final'] = True
        if _pending.get(rec['name']) is rec:
            del _pending[rec['name']]
        prio = _next_wifi_priority()
        for con_uuid, con_name in _con_list():
            if con_name == rec['name'] and con_uuid != rec['uuid']:
                nmcli('con', 'delete', con_uuid)
        nmcli('con', 'modify', rec['uuid'] or rec['pending'],
              'connection.id', rec['name'],
              'connection.autoconnect', 'yes',
              'connection.autoconnect-priority', prio)
        logging.info('new settings for %s worked and are saved', rec['name'])


def _discard_pending(rec):
    """Drop a pending profile that did not (or will not) join. The profile it
    would have replaced is left exactly as it was."""
    with _wifi_lock:
        if rec.get('final'):
            return
        rec['final'] = True
        if _pending.get(rec['name']) is rec:
            del _pending[rec['name']]
        _delete_quietly(rec['uuid'] or rec['pending'])
        logging.info('new settings for %s dropped; the saved profile is unchanged', rec['name'])


def _store_pending_for_boot(rec):
    """apply-boot: nothing can be tested now, so the pending settings are stored
    as they are (as before 1.0.2). An existing profile keeps its identity (it
    may be the link in use right now) and takes the new password; a new
    network's pending profile is renamed."""
    with _wifi_lock:
        if rec.get('gen') is not None:   # an apply-now took it: proven, or stale now
            state, conn = _wlan0_or_none()
            if state == 'connected' and conn == rec['pending']:
                _promote_pending(rec)    # it joined: never delete the link in use
                return
            _bump_switch_gen()
        prio = _next_wifi_priority()
        if rec['name'] in _con_names():
            settings = ('connection.autoconnect', 'yes', 'connection.autoconnect-priority', prio)
            if rec['password']:
                settings = ('wifi-sec.psk', rec['password']) + settings
            nmcli('con', 'modify', rec['name'], *settings)
            _discard_pending(rec)
            return
        nmcli('con', 'modify', rec['uuid'] or rec['pending'],
              'connection.id', rec['name'],
              'connection.autoconnect', 'yes',
              'connection.autoconnect-priority', prio)
        rec['final'] = True
        if _pending.get(rec['name']) is rec:
            del _pending[rec['name']]


def _pending_expired(rec):
    """PENDING_TTL_S after save: a pending profile nobody applied is dropped
    (or kept, if NetworkManager joined it meanwhile)."""
    with _wifi_lock:
        if rec.get('final') or rec.get('gen') is not None:
            return
        state, conn = _wlan0_or_none()
        if state == 'connected' and conn == rec['pending']:
            _promote_pending(rec)
        else:
            _discard_pending(rec)


def _recover_pending(loop=None):
    """At start-up, settle pending profiles a previous run left behind.

    wifi-manager can be restarted right after a join (set_identity.sh moves it
    to a new ROS domain), between the join and _promote_pending. A pending
    profile wlan0 is connected to has proved its password and is promoted; one
    still joining is looked at again later; any other is deleted.
    """
    state, conn = _wlan0()
    retry = False
    for con_uuid, con_name in _con_list():
        if not con_name.endswith(PENDING_SUFFIX):
            continue
        rec = {'name': con_name[:-len(PENDING_SUFFIX)], 'pending': con_name,
               'uuid': con_uuid, 'password': '', 'gen': None}
        if conn == con_name and state == 'connected':
            _promote_pending(rec)
        elif conn == con_name:
            retry = True
        else:
            _discard_pending(rec)
    if retry and loop is not None:
        loop.add_callback(loop.call_later, JOIN_TIMEOUT_S,
                          _in_background, loop, _recover_pending, loop)


def _delete_network(name):
    """Delete a saved profile (and a pending change of it)."""
    with _wifi_lock:
        rec = _pending.get(name)
        if rec is not None:
            _discard_pending(rec)
        try:
            nmcli('con', 'delete', name)
        except Exception:
            if rec is None or name in _con_names():
                raise                # else only the pending profile existed: done


def _delete_after_reply(name):
    """Confirmed DELETE of the network in use, run after the reply went out.
    No switch marker: wifi_watchdog.sh should look for another known network
    (or raise the hotspot) at once."""
    refusal = _fcu_refusal('link')
    if refusal is not None:
        logging.warning('delete of %s not done: %s', name, refusal[1])
        return
    _delete_network(name)
    logging.info('deleted %s, the network in use', name)


def _is_protected(name):
    """The setup hotspot profile (bumblebee-hotspot, SSID Bumblebee-<id>), any
    other drone's hotspot (Bumblebee-*) and our own pending profiles: not to be
    saved over, joined, changed or deleted through the API."""
    n = name.strip().lower()
    return n == HOTSPOT_CONN or n.startswith('bumblebee-') or n.endswith(PENDING_SUFFIX)


def _hwid():
    """Short hardware id (last 4 hex digits of the wlan0 MAC), as advertised in
    the Bonjour TXT record and used in the hotspot SSID."""
    ssid = _hotspot_ssid()
    return ssid[len('Bumblebee-'):] if ssid else ''


def _hotspot_ssid():
    """Stable hotspot SSID: Bumblebee-<last 4 hex digits of the wlan0 MAC>."""
    try:
        with open('/sys/class/net/wlan0/address') as f:
            mac = f.read().strip().replace(':', '')
        if len(mac) >= 4:
            return 'Bumblebee-' + mac[-4:].upper()
    except OSError:
        pass
    return None


def _nm_unescape(value):
    """Undo nmcli terse-mode escaping of ':' and '\\' in a single field."""
    out, i = [], 0
    while i < len(value):
        if value[i] == '\\' and i + 1 < len(value):
            i += 1
        out.append(value[i])
        i += 1
    return ''.join(out)


def _nm_fields(line):
    """Split one nmcli -t line into unescaped fields ('\\:' is not a separator)."""
    fields, cur, i = [], [], 0
    while i < len(line):
        ch = line[i]
        if ch == '\\' and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if ch == ':':
            fields.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    fields.append(''.join(cur))
    return fields


def _con_names():
    """Names of all saved NetworkManager connections (unescaped)."""
    return [_nm_unescape(n) for n in nmcli('-t', '-f', 'NAME', 'con', 'show').splitlines()]


def _con_list():
    """(uuid, name) of every saved NetworkManager connection. UUIDs never
    contain ':', names may (escaped by nmcli -t)."""
    out = []
    for line in nmcli('-t', '-f', 'UUID,NAME', 'con', 'show').splitlines():
        con_uuid, sep, name = line.partition(':')
        if sep:
            out.append((con_uuid, _nm_unescape(name)))
    return out


def _next_wifi_priority():
    """One above every saved Wi-Fi profile, so the network the GCS provisioned
    last wins both NM autoconnect and wifi_watchdog.sh's retry order."""
    best = 9
    for line in nmcli('-t', '-f', 'TYPE,AUTOCONNECT-PRIORITY', 'con', 'show').splitlines():
        kind, _, prio = line.partition(':')
        if kind == '802-11-wireless':
            try:
                best = max(best, int(prio))
            except ValueError:
                pass
    return str(min(best + 1, 999))


def _tune_seconds(tune):
    """Play length of a QBASIC (PX4 PLAY_TUNE) string, in seconds."""
    tempo, length, total = 120, 4, 0.0
    for tok in re.findall(r'M[FBNLS]|[TLONP]\d+|[A-G][#+-]?\d*\.*|[<>]', tune.upper()):
        head = tok[0]
        if (head == 'M' and len(tok) == 2) or head in '<>O':
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
        total += (240.0 / tempo) / n * (2 - 0.5 ** dots)
    return total


# What the last fresh state from a *linked* flight controller said about
# arming; None until one was seen. Needed because MAVROS publishes
# connected=false, armed=false once the FC link drops, even in flight.
_fcu_last_linked_armed = None


def _fcu_flight_state():
    """'disarmed', 'armed' or 'unknown', from drone.get_fcu_status() (cached
    topics, no service call). See _fcu_refusal for what each one allows."""
    global _fcu_last_linked_armed
    if not _LED_OK:
        return 'unknown'
    try:
        st = _drone.get_fcu_status()
    except Exception:
        return 'unknown'
    armed = bool(st.get('armed'))
    if st.get('connected'):          # fresh State from a linked FC
        _fcu_last_linked_armed = armed
        return 'armed' if armed else 'disarmed'
    if armed or _fcu_last_linked_armed:
        return 'armed'               # stale but last seen armed, or link lost while armed
    return 'unknown'


def _fcu_refusal(action):
    """The one "unknown = armed" policy for Wi-Fi changes and sounds.

    Returns None when `action` may run now, else (http_status, code, message).
    action: 'provision' (POST wifi/save, wifi/apply-now, wifi/apply-boot),
    'link' (POST wifi/mode, DELETE wifi/network) or 'sound' (POST
    sounds/play, sounds/tts).

    A change runs only while a fresh state from a linked flight controller
    says disarmed (drone.get_fcu_status(), as for the shows' melodies):
      - armed -> 409 "armed". Also counted as armed: a stale state whose last
        armed flag was set, and a link that dropped while the last linked
        state was armed (MAVROS then says armed=false). Armed always refuses.
      - anything else -> 503 "fc_unknown": no fresh state yet after boot, FC
        unpowered or unplugged, MAVROS down, drone.py not importable. The
        drone might be flying, so it is treated as armed.
    One exception keeps first-time setup ("Add drone") working on a bench,
    where the FC is often unpowered and its state therefore always unknown:
    'provision' is allowed with an unknown (not armed, see above) FC while
    wlan0 serves the drone's own setup hotspot (bumblebee-hotspot). Mode
    switches, deletes and sounds get no exception.

    Deferred link changes ask again right before they run (_nmcli_after_reply,
    _delete_after_reply), since the FC can arm in between.
    """
    state = _fcu_flight_state()
    if state == 'disarmed':
        return None
    what = 'sounds are' if action == 'sound' else 'Wi-Fi changes are'
    if state == 'armed':
        return (409, 'armed', 'the drone is armed: %s refused until it is disarmed' % what)
    if action == 'provision':
        try:
            if _current_mode() == 'hotspot':
                return None
        except Exception:
            logging.exception('cannot read the Wi-Fi mode')
    hint = '' if action == 'sound' else (
        '; or set up Wi-Fi while the drone shows its own Bumblebee-%s hotspot' % (_hwid() or 'XXXX'))
    return (503, 'fc_unknown',
            'flight controller state unknown (not linked, or no fresh state), so it counts as '
            'armed: %s refused. Check that the flight controller is powered and connected%s'
            % (what, hint))


def _fcu_safe_for_tune():
    """True only with a fresh FCU state saying disarmed. Unknown counts as
    armed: a show's melody must never cover PX4's own warnings in flight."""
    return _fcu_flight_state() == 'disarmed'


def _start_show_tune(name, gen):
    """Replay the show's melody until the show is stopped (gen changes).
    Silent while the drone is armed, so PX4's own warning tunes stay audible."""
    tune, gap = SHOWS[name]
    tune = getattr(_drone, tune, tune)
    period = _tune_seconds(tune) + gap
    loop = tornado.ioloop.IOLoop.current()
    try:
        # A brand-new DDS publisher drops its first message; create it with a
        # silent rest so the first real repeat is heard.
        _drone.play_tune('MFT255L64P64')
    except Exception:
        logging.exception('show %s: buzzer unavailable', name)
        return

    def tick():
        if gen != _show_gen or _anim_proc is None or _anim_proc.poll() is not None:
            return   # stopped, replaced, or the LED script exited
        if _fcu_safe_for_tune():
            try:
                _drone.play_tune(tune)
            except Exception:
                logging.exception('show %s: play_tune failed', name)
        loop.call_later(period, tick)

    loop.call_later(0.5, tick)


async def _blocking(fn, *args):
    """Run a blocking call (nmcli can take seconds) off the IOLoop thread."""
    return await tornado.ioloop.IOLoop.current().run_in_executor(None, fn, *args)


def is_authenticated(handler):
    token = handler.get_cookie('wm_session')
    if not token:
        return False
    expiry = SESSIONS.get(token)
    if not expiry or datetime.utcnow() > expiry:
        SESSIONS.pop(token, None)
        return False
    return True


class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json')

    def write_error(self, status_code, **kwargs):
        msg = kwargs.get('reason', 'error')
        code = {404: 'not_found', 405: 'method_not_allowed'}.get(
            status_code, 'internal_error' if status_code >= 500 else 'bad_request')
        self.finish(json.dumps({'error': msg, 'code': code}))

    def fail(self, status, code, error, **extra):
        """Error reply: {"error": text for people, "code": stable snake_case, ...}."""
        self.set_status(status)
        body = {'error': error, 'code': code}
        body.update(extra)
        self.finish(json.dumps(body))

    def json_body(self):
        """The request body as a JSON object, or None after a 400 bad_json reply."""
        try:
            body = json.loads(self.request.body or b'{}')
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self.fail(400, 'bad_json', 'bad json')
            return None
        return body

    def body_ssid(self, body):
        """body["ssid"] stripped, or None after a 400 ssid_required reply."""
        ssid = body.get('ssid', '')
        ssid = ssid.strip() if isinstance(ssid, str) else ''
        if not ssid:
            self.fail(400, 'ssid_required', 'ssid required')
            return None
        return ssid

    def refuse_protected(self, name):
        """409 protected_network for the setup hotspot (see _is_protected)."""
        if not _is_protected(name):
            return False
        self.fail(409, 'protected_network',
                  "'%s' is reserved for the drones' own setup hotspot "
                  "and cannot be saved, joined, changed or deleted here" % name)
        return True

    def refuse_unsafe(self, action):
        """409 armed / 503 fc_unknown unless _fcu_refusal(action) allows it."""
        refusal = _fcu_refusal(action)
        if refusal is None:
            return False
        logging.warning('%s %s refused: %s', self.request.method, self.request.path, refusal[1])
        self.fail(*refusal)
        return True

    def require_auth(self):
        if False:  # PIN auth removed by operator request
            self.set_status(401)
            self.finish(json.dumps({'error': 'unauthorized'}))
            return False
        return True


class AuthLoginHandler(BaseHandler):
    def post(self):
        body = json.loads(self.request.body)
        pin = str(body.get('pin', ''))
        cfg = load_config()
        if not bcrypt.checkpw(pin.encode(), cfg['pin_hash'].encode()):
            self.set_status(401)
            self.finish(json.dumps({'error': 'invalid PIN'}))
            return
        token = str(uuid.uuid4())
        SESSIONS[token] = datetime.utcnow() + SESSION_TTL
        self.set_cookie('wm_session', token, httponly=True, samesite='Strict')
        self.finish(json.dumps({'ok': True}))


class AuthLogoutHandler(BaseHandler):
    def post(self):
        token = self.get_cookie('wm_session')
        SESSIONS.pop(token, None)
        self.clear_cookie('wm_session')
        self.finish(json.dumps({'ok': True}))


def _wifi_status():
    raw = nmcli('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device', 'status')
    mode = 'unknown'
    ssid = ''
    ip = ''
    signal = 0
    for line in raw.splitlines():
        parts = _nm_fields(line)
        if parts[0] == 'wlan0':
            state = parts[1]
            conn = parts[2] if len(parts) > 2 else ''
            if state == 'connected':
                mode = 'hotspot' if conn == 'bumblebee-hotspot' else 'client'
                # while new settings are being proven, name the network, not the pending profile
                ssid = conn[:-len(PENDING_SUFFIX)] if conn.endswith(PENDING_SUFFIX) else conn
            else:
                mode = state
            break

    ip_raw = nmcli('-t', '-f', 'IP4.ADDRESS', 'device', 'show', 'wlan0')
    for line in ip_raw.splitlines():
        if line.startswith('IP4.ADDRESS'):
            ip = line.split(':')[-1].split('/')[0]
            break

    # --rescan no: the GCS polls this endpoint; an implicit rescan takes
    # seconds and stalls every other request.
    wifi_raw = nmcli('-t', '-f', 'IN-USE,SIGNAL,SSID', 'dev', 'wifi', 'list',
                     '--rescan', 'no')
    for line in wifi_raw.splitlines():
        parts = line.split(':')
        if parts[0] == '*' and len(parts) >= 3:
            try:
                signal = int(parts[1])
            except ValueError:
                pass
            break

    status = {'mode': mode, 'ssid': ssid, 'ip': ip, 'signal': signal, 'id': _hwid()}
    try:
        with open(LAST_ERROR_FILE) as f:
            status['last_error'] = json.load(f)
    except (OSError, ValueError):
        pass
    return status


class StatusHandler(BaseHandler):
    async def get(self):
        try:
            self.finish(json.dumps(await _blocking(_wifi_status)))
        except Exception as e:
            logging.exception('status error')
            self.fail(500, 'nmcli_failed', str(e))


def _band_for_freq(freq_mhz):
    if freq_mhz <= 0:
        return ''
    if freq_mhz < 3000:
        return '2.4'
    if 4900 <= freq_mhz < 5900:
        return '5'
    if freq_mhz >= 5900:
        return '6'
    return ''


def _scan_raw():
    try:
        nmcli('dev', 'wifi', 'rescan')
    except Exception:
        pass
    return nmcli('-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY,FREQ', 'dev', 'wifi', 'list')


class ScanHandler(BaseHandler):
    async def get(self):
        try:
            raw = await _blocking(_scan_raw)
            networks = []
            seen = set()
            for line in raw.splitlines():
                parts = _nm_fields(line)
                if len(parts) < 5:
                    continue
                in_use = parts[0] == '*'
                ssid = parts[1]
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                try:
                    signal = int(parts[2])
                except ValueError:
                    signal = 0
                # FREQ in terse mode can be "2437" or "2437 MHz"; take the leading int.
                freq = 0
                try:
                    freq = int(parts[4].strip().split()[0])
                except (ValueError, IndexError):
                    pass
                networks.append({
                    'ssid': ssid,
                    'signal': signal,
                    'security': parts[3],
                    'in_use': in_use,
                    'freq': freq,
                    'band': _band_for_freq(freq),
                })
            # Sort by band (5/6 GHz first), then by signal desc.
            band_rank = {'6': 0, '5': 1, '2.4': 2, '': 3}
            networks.sort(key=lambda n: (band_rank.get(n['band'], 9), -n['signal']))
            self.finish(json.dumps(networks))
        except Exception as e:
            logging.exception('scan error')
            self.fail(500, 'nmcli_failed', str(e))


class NetworksHandler(BaseHandler):
    def get(self):
        try:
            raw = nmcli('-t', '-f', 'NAME,TYPE', 'con', 'show')
            networks = []
            for line in raw.splitlines():
                parts = _nm_fields(line)
                if len(parts) < 2:
                    continue
                name, con_type = parts[0], parts[1]
                if con_type != '802-11-wireless':
                    continue
                if name == 'bumblebee-hotspot' or name.endswith(PENDING_SUFFIX):
                    continue
                networks.append({'name': name})
            self.finish(json.dumps(networks))
        except Exception as e:
            logging.exception('networks error')
            self.fail(500, 'nmcli_failed', str(e))


class SaveNetworkHandler(BaseHandler):
    """New credentials go into a pending profile (see _save_network)."""

    def post(self):
        if not self.require_auth():
            return
        body = self.json_body()
        if body is None:
            return
        ssid = self.body_ssid(body)
        if ssid is None:
            return
        password = body.get('password', '')
        password = password.strip() if isinstance(password, str) else ''
        if self.refuse_protected(ssid) or self.refuse_unsafe('provision'):
            return
        try:
            rec = _save_network(ssid, password)
        except Exception as e:
            logging.exception('save error')
            self.fail(500, 'nmcli_failed', str(e))
            return
        if rec is None:
            self.finish(json.dumps({'ok': True}))
            return
        loop = tornado.ioloop.IOLoop.current()
        loop.call_later(PENDING_TTL_S, _in_background, loop, _pending_expired, rec)
        # pending: tried by apply-now before it replaces anything
        self.finish(json.dumps({'ok': True, 'pending': True}))


class ApplyNowHandler(BaseHandler):
    def post(self):
        if not self.require_auth():
            return
        body = self.json_body()
        if body is None:
            return
        ssid = self.body_ssid(body)
        if ssid is None:
            return
        if self.refuse_protected(ssid) or self.refuse_unsafe('provision'):
            return
        try:
            known = _con_names()
        except Exception as e:
            logging.exception('apply-now error')
            self.fail(500, 'nmcli_failed', str(e))
            return
        with _wifi_lock:
            rec = _pending.get(ssid)        # new settings saved for it: join with those
            if rec is None and ssid not in known:
                self.fail(404, 'unknown_network', 'unknown network: ' + ssid)
                return
            gen = _bump_switch_gen()
            if rec is not None:
                rec['gen'] = gen
        for f in (HOTSPOT_PIN_MARKER, LAST_ERROR_FILE):  # a client network was chosen;
            try:                                       # forget the previous failure
                os.remove(f)
            except OSError:
                pass

        def skipped(why):
            if rec is not None and rec.get('gen') == gen:
                _discard_pending(rec)
            if why != 'superseded':
                _write_last_error(ssid, why, 'not switched: ' + why)

        # Reply first: bringing the connection up drops the hotspot the GCS is
        # talking through, so a reply sent afterwards never arrives.
        _nmcli_after_reply('con', 'up', (rec['uuid'] or rec['pending']) if rec else ssid,
                           gen=gen, action='provision',
                           on_ok=(lambda: _promote_pending(rec)) if rec else None,
                           on_fail=lambda exc: _join_failed(ssid, exc, rec=rec, gen=gen),
                           on_skip=skipped)
        logging.info('apply-now: switching to %s%s', ssid, ' (new settings)' if rec else '')
        self.finish(json.dumps({'ok': True}))


class ApplyBootHandler(BaseHandler):
    def post(self):
        if not self.require_auth():
            return
        body = self.json_body()
        if body is None:
            return
        ssid = self.body_ssid(body)
        if ssid is None:
            return
        if self.refuse_protected(ssid) or self.refuse_unsafe('provision'):
            return
        try:
            with _wifi_lock:
                rec = _pending.get(ssid)
                if rec is not None:
                    _store_pending_for_boot(rec)
                else:
                    nmcli('con', 'modify', ssid,
                          'connection.autoconnect', 'yes',
                          'connection.autoconnect-priority', _next_wifi_priority())
            self.finish(json.dumps({'ok': True, 'note': 'will connect on next boot'}))
        except Exception as e:
            logging.exception('apply-boot error')
            self.fail(500, 'nmcli_failed', str(e))


class DeleteNetworkHandler(BaseHandler):
    """Safe Remove: the network in use is deleted only with confirm_active:
    true, and then only after the reply, which would not arrive otherwise."""

    def delete(self):
        if not self.require_auth():
            return
        body = self.json_body()
        if body is None:
            return
        ssid = self.body_ssid(body)
        if ssid is None:
            return
        # Without the hotspot the drone has no fallback AP and cannot be provisioned.
        if self.refuse_protected(ssid) or self.refuse_unsafe('link'):
            return
        state, conn = _wlan0_or_none()
        in_use = conn is None or conn in (ssid, ssid + PENDING_SUFFIX)
        if in_use and body.get('confirm_active') is not True:
            # GCS 1.1.0 shows this text as is and cannot confirm: say what to do
            self.fail(409, 'active_network',
                      ("'%s' is the network the drone is using right now" if conn is not None else
                       "cannot tell whether '%s' is the network the drone is using right now") % ssid
                      + ': removing it disconnects the drone (it then joins another saved network '
                        'or shows its own hotspot). Move the drone to another network first, or '
                        'confirm the removal (confirm_active) in a newer GCS.')
            return
        if in_use:
            _bump_switch_gen()          # a join still under way must not raise the hotspot now
            loop = tornado.ioloop.IOLoop.current()
            loop.call_later(SWITCH_DELAY_S, _in_background, loop, _delete_after_reply, ssid)
            logging.info('delete: removing %s, the network in use, after the reply', ssid)
            self.finish(json.dumps({'ok': True, 'deferred': True}))
            return
        try:
            _delete_network(ssid)
            self.finish(json.dumps({'ok': True}))
        except Exception as e:
            logging.exception('delete error')
            self.fail(500, 'nmcli_failed', str(e))


def _current_mode():
    raw = nmcli('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device', 'status')
    for line in raw.splitlines():
        parts = _nm_fields(line)
        if parts[0] == 'wlan0' and len(parts) >= 3:
            if parts[1] == 'connected':
                return 'hotspot' if parts[2] == HOTSPOT_CONN else 'client'
            return parts[1]
    return 'unknown'


class ModeHandler(BaseHandler):
    def get(self):
        try:
            self.finish(json.dumps({'mode': _current_mode()}))
        except Exception as e:
            logging.exception('mode get error')
            self.fail(500, 'nmcli_failed', str(e))

    def post(self):
        if not self.require_auth():
            return
        body = self.json_body()
        if body is None:
            return
        target = body.get('mode') or ''
        target = target.strip().lower() if isinstance(target, str) else ''
        if target not in ('hotspot', 'client'):
            self.fail(400, 'bad_mode', "mode must be 'hotspot' or 'client'")
            return
        if self.refuse_unsafe('link'):
            return
        gen = _bump_switch_gen()

        def unpin(why):
            if why != 'superseded':      # refused at the last moment: not pinned after all
                try:
                    os.remove(HOTSPOT_PIN_MARKER)
                except OSError:
                    pass

        # Both directions drop the link the GCS is using, so reply first and
        # switch right after (see _nmcli_after_reply).
        try:
            if target == 'hotspot':
                open(HOTSPOT_PIN_MARKER, 'w').close()
                ssid = _hotspot_ssid()
                if ssid:
                    nmcli('connection', 'modify', HOTSPOT_CONN, 'wifi.ssid', ssid)
                _nmcli_after_reply('connection', 'up', HOTSPOT_CONN,
                                   gen=gen, action='link', on_skip=unpin)
                logging.info('switching to hotspot mode')
            else:
                try:
                    os.remove(HOTSPOT_PIN_MARKER)
                except OSError:
                    pass
                if _current_mode() == 'hotspot':
                    # wifi_watchdog will pick a visible known network.
                    _nmcli_after_reply('connection', 'down', HOTSPOT_CONN, gen=gen, action='link')
                logging.info('switching to client mode (watchdog will reconnect)')
            self.finish(json.dumps({'ok': True, 'mode': target}))
        except Exception as e:
            logging.exception('mode set error')
            self.fail(500, 'nmcli_failed', str(e))


class LedColorHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.fail(503, 'led_unavailable', 'led unavailable')
            return
        body = json.loads(self.request.body)
        r = max(0, min(255, int(body.get('r', 0))))
        g = max(0, min(255, int(body.get('g', 0))))
        b = max(0, min(255, int(body.get('b', 0))))
        anim_was_running = _anim_proc is not None and _anim_proc.poll() is None
        _stop_anim()
        first = not os.path.exists(LED_BUSY)
        if first or anim_was_running:
            open(LED_BUSY, 'w').close()
            time.sleep(0.22)
        try:
            _drone.set_led(_drone.STRIP_ALL, _drone.LED_ALL, r, g, b)
            self.finish(json.dumps({'ok': True}))
        except Exception as e:
            logging.exception('led color error')
            self.fail(500, 'led_failed', str(e))


class LedAnimationHandler(BaseHandler):
    """Starts an animation or show; it stops by itself after SHOW_MAX_S."""

    def post(self):
        if not _LED_OK:
            self.fail(503, 'led_unavailable', 'led unavailable')
            return
        try:
            body = json.loads(self.request.body)
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        name = str(body.get('name', '')).strip().lower()
        if name not in ANIMATIONS:
            self.fail(400, 'unknown_animation', 'unknown animation', available=sorted(ANIMATIONS))
            return
        script = os.path.join(ANIM_DIR, name + '.py')
        if not os.path.isfile(script):
            self.fail(500, 'script_missing', 'script missing: ' + script)
            return
        global _anim_proc
        _stop_anim()
        try:
            limit = SHOW_MAX_S
            _anim_proc = subprocess.Popen(['python3', script])
            _anim_proc._name = name
            _anim_proc._deadline = time.monotonic() + limit
            gen = _show_gen
            if name in SHOWS:
                _start_show_tune(name, gen)
            tornado.ioloop.IOLoop.current().call_later(limit, _expire_anim, gen)
            self.finish(json.dumps({'ok': True, 'name': name, 'pid': _anim_proc.pid,
                                    'max_s': limit}))
        except Exception as e:
            logging.exception('led animation spawn')
            self.fail(500, 'spawn_failed', str(e))


class LedStatusHandler(BaseHandler):
    def get(self):
        running = _anim_proc is not None and _anim_proc.poll() is None
        remaining = None
        if running and getattr(_anim_proc, '_deadline', None) is not None:
            remaining = max(0, int(math.ceil(_anim_proc._deadline - time.monotonic())))
        self.finish(json.dumps({
            'led_ok': _LED_OK,
            'animation': None if not running else getattr(_anim_proc, '_name', None),
            'pid': _anim_proc.pid if running else None,
            'busy': os.path.exists(LED_BUSY),
            'remaining_s': remaining,     # until it stops by itself (SHOW_MAX_S)
        }))


class LedResetHandler(BaseHandler):
    def post(self):
        _stop_anim()
        try:
            os.remove(LED_BUSY)
        except OSError:
            pass
        self.finish(json.dumps({'ok': True}))


class FcuStatusHandler(BaseHandler):
    """Flight-controller link and arming state, read-only. set_identity.sh
    restarts the ROS services for a new ROS domain only when this says
    disarmed; unknown (no fresh state) must be treated as armed."""
    def get(self):
        if not _LED_OK:
            self.fail(503, 'drone_unavailable', 'drone unavailable')
            return
        try:
            st = _drone.get_fcu_status()
            # ok only with a fresh state from a *linked* flight controller:
            # MAVROS publishes connected=false, armed=false when the link drops
            self.finish(json.dumps({
                'ok': bool(st.get('connected')),
                'connected': bool(st.get('connected')),
                'armed': bool(st.get('armed')),
                'mode': str(st.get('mode') or ''),
            }))
        except Exception as e:
            logging.exception('fcu status error')
            self.fail(500, 'fcu_failed', str(e))


class SoundsPlayHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.fail(503, 'drone_unavailable', 'drone unavailable')
            return
        body = self.json_body()
        if body is None:
            return
        tune = str(body.get('tune', '')).strip()
        fmt = str(body.get('format', 'QBASIC')).strip().upper()
        if not tune:
            self.fail(400, 'empty_tune', 'empty tune')
            return
        if fmt not in ('QBASIC', 'MML'):
            self.fail(400, 'bad_format', 'bad format')
            return
        if self.refuse_unsafe('sound'):
            return
        try:
            _drone.play_tune(tune, fmt)
            self.finish(json.dumps({'ok': True}))
        except Exception as e:
            logging.exception('sound play error')
            self.fail(500, 'play_failed', str(e))


class SoundsTtsHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.fail(503, 'drone_unavailable', 'drone bus unavailable')
            return
        if not _TTS_OK or _tts_to_tune is None:
            self.fail(503, 'tts_unavailable', 'espeak-ng not installed')
            return
        body = self.json_body()
        if body is None:
            return
        text = str(body.get('text', '')).strip()
        lang = str(body.get('lang', 'en')).strip().lower()
        if not text:
            self.fail(400, 'text_required', 'text required')
            return
        if self.refuse_unsafe('sound'):
            return
        try:
            tune, phonemes = _tts_to_tune(text, lang=lang)
            _drone.play_tune(tune, 'QBASIC')
            self.finish(json.dumps({'ok': True, 'tune': tune, 'phonemes': phonemes}))
        except ValueError as ve:
            self.fail(400, 'bad_text', str(ve))
        except Exception as e:
            logging.exception('tts error')
            self.fail(500, 'tts_failed', str(e))


def _first_line(path):
    try:
        with open(path) as f:
            return f.readline().strip()
    except (OSError, ValueError):
        return ''


def _drone_name():
    """The name the drone advertises (Bonjour TXT name=, set_identity.sh)."""
    try:
        with open(AVAHI_SERVICE_FILE) as f:
            m = re.search(r'<txt-record>name=([^<]*)</txt-record>', f.read())
        if m and m.group(1).strip():
            return m.group(1).strip()
    except (OSError, ValueError):
        pass
    hwid = _hwid()
    return 'Bumblebee-' + hwid if hwid else socket.gethostname()


def _domain_or_none(text):
    try:
        domain = int(str(text).strip())
    except (TypeError, ValueError):
        return None
    return domain if 0 <= domain <= 232 else None


def _ros_domain():
    """ROS_DOMAIN_ID a laptop needs to see this drone's topics: the one the
    flight stack runs with (start_bumblebee.sh records "<domain> <pid>"), else
    the one this service was started with (/etc/bumblebee/ros.env via
    systemd); None if neither is known."""
    try:
        with open(STACK_DOMAIN_FILE) as f:
            fields = f.read().split()
        domain = _domain_or_none(fields[0]) if fields else None
        pid = fields[1] if len(fields) > 1 else ''
        gone = (pid.isdigit() and os.path.isdir(PROC_DIR)
                and not os.path.exists(os.path.join(PROC_DIR, pid)))
        if domain is not None and not gone:
            return domain
    except (OSError, ValueError):
        pass
    return _domain_or_none(os.environ.get('ROS_DOMAIN_ID'))


class InfoHandler(BaseHandler):
    """GET /api/info: who this drone is. Read-only; no auth, like /api/wifi/status.
    "contract" is the version of this API; it changes only incompatibly."""

    def get(self):
        try:
            info = {
                'name': _drone_name(),
                'id': _hwid(),
                'version': _first_line(VERSION_FILE) or 'unknown',
                'ros_domain': _ros_domain(),
                'contract': API_CONTRACT,
            }
        except Exception as e:
            logging.exception('info error')
            self.fail(500, 'info_failed', str(e))
            return
        self.finish(json.dumps(info))


def make_app():
    return tornado.web.Application([
        (r'/api/auth/login',      AuthLoginHandler),
        (r'/api/auth/logout',     AuthLogoutHandler),
        (r'/api/wifi/status',     StatusHandler),
        (r'/api/wifi/scan',       ScanHandler),
        (r'/api/wifi/networks',   NetworksHandler),
        (r'/api/wifi/save',       SaveNetworkHandler),
        (r'/api/wifi/apply-now',  ApplyNowHandler),
        (r'/api/wifi/apply-boot', ApplyBootHandler),
        (r'/api/wifi/network',    DeleteNetworkHandler),
        (r'/api/wifi/mode',       ModeHandler),
        (r'/api/led/color',       LedColorHandler),
        (r'/api/led/animation',   LedAnimationHandler),
        (r'/api/led/status',      LedStatusHandler),
        (r'/api/led/reset',       LedResetHandler),
        (r'/api/fcu/status',      FcuStatusHandler),
        (r'/api/sounds/play',     SoundsPlayHandler),
        (r'/api/sounds/tts',      SoundsTtsHandler),
        (r'/api/info',            InfoHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8765, address='0.0.0.0')
    logging.info('wifi-manager started on 0.0.0.0:8765')
    main_loop = tornado.ioloop.IOLoop.current()
    try:
        _recover_pending(main_loop)
    except Exception:
        logging.exception('settling pending Wi-Fi profiles failed')
    if _LED_OK:
        # Keeps _fcu_last_linked_armed current between requests, so a link
        # lost in flight still counts as armed (see _fcu_refusal). Read-only.
        tornado.ioloop.PeriodicCallback(_fcu_flight_state, 1000).start()
    main_loop.start()
