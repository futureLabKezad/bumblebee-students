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

"""WiFi Manager — Tornado REST API on 0.0.0.0:8765 (used directly by the GCS app)."""

import json
import logging
import os
import re
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
# Touched before every API-driven Wi-Fi switch. wifi_watchdog.sh and the NM
# dispatcher hold off their hotspot fallback while it is fresh, so they don't
# abort a join that is still authenticating / getting DHCP.
WIFI_SWITCH_MARKER = '/tmp/bumblebee-wifi-switch'
# Delay before a connection-changing nmcli call, so the HTTP reply reaches the
# GCS before the drone drops the link the GCS is talking over.
SWITCH_DELAY_S = 1.5
# Present while the GCS asked for hotspot mode: wifi_watchdog.sh then stops
# probing for known networks (which would switch the drone back to client).
HOTSPOT_PIN_MARKER = '/tmp/bumblebee-hotspot-pinned'
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


def nmcli(*args):
    """Run nmcli, return stdout. Raises RuntimeError on non-zero exit."""
    result = subprocess.run(
        ['nmcli'] + list(args),
        capture_output=True, text=True, timeout=15,
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


def _nmcli_after_reply(*args):
    """Run a link-changing nmcli command after the current reply is sent.

    `nmcli con up/down` on wlan0 tears down the network the GCS is connected
    through, so it must not run before the response is flushed.
    """
    _mark_wifi_switch()

    def worker():
        time.sleep(SWITCH_DELAY_S)
        try:
            nmcli(*args)
            logging.info('nmcli %s: ok', ' '.join(args))
        except Exception:
            logging.exception('nmcli %s failed', ' '.join(args))

    threading.Thread(target=worker, daemon=True).start()


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


def _fcu_safe_for_tune():
    """True only with a fresh FCU state saying disarmed. Unknown counts as
    armed: a show's melody must never cover PX4's own warnings in flight."""
    try:
        st = _drone.get_fcu_status()
        return bool(st.get('ok')) and not st.get('armed')
    except Exception:
        return False


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
        self.finish(json.dumps({'error': msg}))

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
                ssid = conn
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

    return {'mode': mode, 'ssid': ssid, 'ip': ip, 'signal': signal}


class StatusHandler(BaseHandler):
    async def get(self):
        try:
            self.finish(json.dumps(await _blocking(_wifi_status)))
        except Exception as e:
            logging.exception('status error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


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
                parts = line.split(':')
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
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


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
                if name == 'bumblebee-hotspot':
                    continue
                networks.append({'name': name})
            self.finish(json.dumps(networks))
        except Exception as e:
            logging.exception('networks error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class SaveNetworkHandler(BaseHandler):
    def post(self):
        if not self.require_auth():
            return
        body = json.loads(self.request.body)
        ssid = body.get('ssid', '').strip()
        password = body.get('password', '').strip()
        if not ssid:
            self.set_status(400)
            self.finish(json.dumps({'error': 'ssid required'}))
            return
        try:
            if ssid in _con_names():
                if password:
                    nmcli('con', 'modify', ssid, 'wifi-sec.psk', password)
            else:
                if password:
                    nmcli('con', 'add', 'type', 'wifi',
                          'con-name', ssid, 'ssid', ssid,
                          'wifi-sec.key-mgmt', 'wpa-psk',
                          'wifi-sec.psk', password)
                else:
                    nmcli('con', 'add', 'type', 'wifi',
                          'con-name', ssid, 'ssid', ssid)
            nmcli('con', 'modify', ssid,
                  'connection.autoconnect', 'yes',
                  'connection.autoconnect-priority', _next_wifi_priority())
            self.finish(json.dumps({'ok': True}))
        except Exception as e:
            logging.exception('save error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class ApplyNowHandler(BaseHandler):
    def post(self):
        if not self.require_auth():
            return
        body = json.loads(self.request.body)
        ssid = body.get('ssid', '').strip()
        if not ssid:
            self.set_status(400)
            self.finish(json.dumps({'error': 'ssid required'}))
            return
        try:
            known = _con_names()
        except Exception as e:
            logging.exception('apply-now error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))
            return
        if ssid not in known:
            self.set_status(404)
            self.finish(json.dumps({'error': 'unknown network: ' + ssid}))
            return
        try:
            os.remove(HOTSPOT_PIN_MARKER)   # a client network was chosen
        except OSError:
            pass
        # Reply first: bringing the connection up drops the hotspot the GCS is
        # talking through, so a reply sent afterwards never arrives.
        _nmcli_after_reply('con', 'up', ssid)
        logging.info('apply-now: switching to %s', ssid)
        self.finish(json.dumps({'ok': True}))


class ApplyBootHandler(BaseHandler):
    def post(self):
        if not self.require_auth():
            return
        body = json.loads(self.request.body)
        ssid = body.get('ssid', '').strip()
        if not ssid:
            self.set_status(400)
            self.finish(json.dumps({'error': 'ssid required'}))
            return
        try:
            nmcli('con', 'modify', ssid,
                  'connection.autoconnect', 'yes',
                  'connection.autoconnect-priority', _next_wifi_priority())
            self.finish(json.dumps({'ok': True, 'note': 'will connect on next boot'}))
        except Exception as e:
            logging.exception('apply-boot error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class DeleteNetworkHandler(BaseHandler):
    def delete(self):
        if not self.require_auth():
            return
        body = json.loads(self.request.body)
        ssid = body.get('ssid', '').strip()
        if not ssid:
            self.set_status(400)
            self.finish(json.dumps({'error': 'ssid required'}))
            return
        if ssid == HOTSPOT_CONN:
            # Without it the drone has no fallback AP and cannot be provisioned.
            self.set_status(403)
            self.finish(json.dumps({'error': 'the hotspot profile cannot be deleted'}))
            return
        try:
            nmcli('con', 'delete', ssid)
            self.finish(json.dumps({'ok': True}))
        except Exception as e:
            logging.exception('delete error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


def _current_mode():
    raw = nmcli('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device', 'status')
    for line in raw.splitlines():
        parts = line.split(':')
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
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))

    def post(self):
        if not self.require_auth():
            return
        body = json.loads(self.request.body)
        target = (body.get('mode') or '').strip().lower()
        if target not in ('hotspot', 'client'):
            self.set_status(400)
            self.finish(json.dumps({'error': "mode must be 'hotspot' or 'client'"}))
            return
        # Both directions drop the link the GCS is using, so reply first and
        # switch right after (see _nmcli_after_reply).
        try:
            if target == 'hotspot':
                open(HOTSPOT_PIN_MARKER, 'w').close()
                ssid = _hotspot_ssid()
                if ssid:
                    nmcli('connection', 'modify', HOTSPOT_CONN, 'wifi.ssid', ssid)
                _nmcli_after_reply('connection', 'up', HOTSPOT_CONN)
                logging.info('switching to hotspot mode')
            else:
                try:
                    os.remove(HOTSPOT_PIN_MARKER)
                except OSError:
                    pass
                if _current_mode() == 'hotspot':
                    # wifi_watchdog will pick a visible known network.
                    _nmcli_after_reply('connection', 'down', HOTSPOT_CONN)
                logging.info('switching to client mode (watchdog will reconnect)')
            self.finish(json.dumps({'ok': True, 'mode': target}))
        except Exception as e:
            logging.exception('mode set error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class LedColorHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.set_status(503)
            self.finish(json.dumps({'error': 'led unavailable'}))
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
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class LedAnimationHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.set_status(503)
            self.finish(json.dumps({'error': 'led unavailable'}))
            return
        try:
            body = json.loads(self.request.body)
        except Exception:
            body = {}
        name = str(body.get('name', '')).strip().lower()
        if name not in ANIMATIONS:
            self.set_status(400)
            self.finish(json.dumps({'error': 'unknown animation', 'available': sorted(ANIMATIONS)}))
            return
        script = os.path.join(ANIM_DIR, name + '.py')
        if not os.path.isfile(script):
            self.set_status(500)
            self.finish(json.dumps({'error': 'script missing: ' + script}))
            return
        global _anim_proc
        _stop_anim()
        try:
            _anim_proc = subprocess.Popen(['python3', script])
            _anim_proc._name = name
            if name in SHOWS:
                _start_show_tune(name, _show_gen)
            self.finish(json.dumps({'ok': True, 'name': name, 'pid': _anim_proc.pid}))
        except Exception as e:
            logging.exception('led animation spawn')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class LedStatusHandler(BaseHandler):
    def get(self):
        running = _anim_proc is not None and _anim_proc.poll() is None
        self.finish(json.dumps({
            'led_ok': _LED_OK,
            'animation': None if not running else getattr(_anim_proc, '_name', None),
            'pid': _anim_proc.pid if running else None,
            'busy': os.path.exists(LED_BUSY),
        }))


class LedResetHandler(BaseHandler):
    def post(self):
        _stop_anim()
        try:
            os.remove(LED_BUSY)
        except OSError:
            pass
        self.finish(json.dumps({'ok': True}))


class SoundsPlayHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.set_status(503)
            self.finish(json.dumps({'error': 'drone unavailable'}))
            return
        try:
            body = json.loads(self.request.body)
        except Exception:
            self.set_status(400)
            self.finish(json.dumps({'error': 'bad json'}))
            return
        tune = str(body.get('tune', '')).strip()
        fmt = str(body.get('format', 'QBASIC')).strip().upper()
        if not tune:
            self.set_status(400)
            self.finish(json.dumps({'error': 'empty tune'}))
            return
        if fmt not in ('QBASIC', 'MML'):
            self.set_status(400)
            self.finish(json.dumps({'error': 'bad format'}))
            return
        try:
            _drone.play_tune(tune, fmt)
            self.finish(json.dumps({'ok': True}))
        except Exception as e:
            logging.exception('sound play error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


class SoundsTtsHandler(BaseHandler):
    def post(self):
        if not _LED_OK:
            self.set_status(503)
            self.finish(json.dumps({'error': 'drone bus unavailable'}))
            return
        if not _TTS_OK or _tts_to_tune is None:
            self.set_status(503)
            self.finish(json.dumps({'error': 'espeak-ng not installed'}))
            return
        try:
            body = json.loads(self.request.body or b'{}')
        except ValueError:
            self.set_status(400)
            self.finish(json.dumps({'error': 'bad json'}))
            return
        text = str(body.get('text', '')).strip()
        lang = str(body.get('lang', 'en')).strip().lower()
        if not text:
            self.set_status(400)
            self.finish(json.dumps({'error': 'text required'}))
            return
        try:
            tune, phonemes = _tts_to_tune(text, lang=lang)
            _drone.play_tune(tune, 'QBASIC')
            self.finish(json.dumps({'ok': True, 'tune': tune, 'phonemes': phonemes}))
        except ValueError as ve:
            self.set_status(400)
            self.finish(json.dumps({'error': str(ve)}))
        except Exception as e:
            logging.exception('tts error')
            self.set_status(500)
            self.finish(json.dumps({'error': str(e)}))


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
        (r'/api/sounds/play',     SoundsPlayHandler),
        (r'/api/sounds/tts',      SoundsTtsHandler),
    ])


if __name__ == '__main__':
    app = make_app()
    app.listen(8765, address='0.0.0.0')
    logging.info('wifi-manager started on 0.0.0.0:8765')
    tornado.ioloop.IOLoop.current().start()
