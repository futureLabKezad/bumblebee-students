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

"""Mock Bumblebee drone for testing the GCS app without hardware.

Unlike gcs/windows/tools/SimDrone, this runs the drone's *real* REST backend
(drone/.../scripts/wifi_manager.py) and metrics server (sys_metrics.py), with
only the hardware faked: nmcli, the I2C LEDs and the PX4 buzzer. On macOS it
also advertises the _bumblebee._tcp Bonjour service like set_identity.sh.

    pip install tornado bcrypt
    python3 gcs/tools/mock_drone.py            # Ctrl-C to stop

Ports: 8765 REST API, 8888 metrics, 9090 rosbridge (telemetry stub).
Every LED / buzzer / nmcli action is printed to stdout.

Flight-controller states, for testing what the apps show and what the drone
refuses (the real wifi_manager.py reads the same fake state):

    --fcu disarmed   FC linked, disarmed (default)
    --fcu armed      FC linked, armed in OFFBOARD
    --fcu stale      /mavros/state stops arriving (last known state kept)
    --fcu lost       MAVROS reports connected=false (FC cable out)
    --telemetry freeze   rosbridge stays open but publishes nothing
    --battery low        12 %, 20.4 V

Change them while running, from the same machine only:

    curl 'http://127.0.0.1:8799/mock/set?fcu=armed&battery=low'
    curl  http://127.0.0.1:8799/mock/state

A silent link drop (drone switched off, out of Wi-Fi range) is not a state:
pause the whole process with `kill -STOP <pid>` and resume with `kill -CONT`.
Use --host 127.0.0.1 to keep the mock off the classroom network.
"""
import argparse
import importlib.util
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import tornado.ioloop
import tornado.web
import tornado.websocket

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PKG = os.path.join(REPO, 'drone', 'ros2_ws', 'src', 'bumblebee')
NAME = 'Bumblebee-Mock'
HWID = 'M0CK'


def say(*a):
    print('[mock-drone]', *a, flush=True)


# ---- fake flight-controller state, shared by REST and rosbridge -------------
CHOICES = {
    'fcu': ('disarmed', 'armed', 'stale', 'lost'),
    'telemetry': ('normal', 'freeze'),
    'battery': ('ok', 'low'),
}
STATE = {'fcu': 'disarmed', 'telemetry': 'normal', 'battery': 'ok', 'last_armed': False}


def set_state(**changes):
    """Validate and apply; returns an error string or None."""
    for key, value in changes.items():
        if key not in CHOICES or value not in CHOICES[key]:
            return 'bad %s=%s (choose %s)' % (key, value, '|'.join(CHOICES.get(key, ())))
    for key, value in changes.items():
        if key == 'fcu' and value in ('disarmed', 'armed'):
            STATE['last_armed'] = value == 'armed'
        STATE[key] = value
    say('state', {k: STATE[k] for k in CHOICES})
    return None


def fcu_status(max_age=3.0):
    """Same shape and meaning as drone.get_fcu_status() on the real drone."""
    fcu = STATE['fcu']
    if fcu == 'stale':   # no fresh State: not ok, not connected, last armed flag
        return {'connected': False, 'armed': STATE['last_armed'], 'mode': '', 'cell': float('nan'), 'ok': False}
    if fcu == 'lost':    # fresh State from MAVROS saying the FC link is down
        return {'connected': False, 'armed': False, 'mode': '', 'cell': float('nan'), 'ok': True}
    armed = fcu == 'armed'
    return {'connected': True, 'armed': armed, 'mode': 'OFFBOARD' if armed else 'POSCTL',
            'cell': 3.4 if STATE['battery'] == 'low' else 4.0, 'ok': True}


class ControlHandler(tornado.web.RequestHandler):
    def get(self, what):
        if what == 'set':
            err = set_state(**{k: self.get_argument(k) for k in self.request.arguments})
            if err:
                self.set_status(400)
                self.finish({'error': err})
                return
        self.finish({k: STATE[k] for k in CHOICES})


# ---- fake hardware: drone.py (LEDs over I2C, PX4 buzzer) --------------------
FAKE_DRONE = '''
import sys
LED_1, LED_2, LED_3, LED_4, LED_5, LED_6 = 0, 5, 1, 3, 2, 4
LED_ALL = STRIP_ALL = 255
LED_RING = [LED_2, LED_4, LED_1, LED_3, LED_5, LED_6]
TUNE_MARIO = 'MFT200L8O5EEP8EP8CEP8GP8P4<GP4'
TUNE_WARN = 'MFT200L16O5AP16AP16A'
TUNE_VICTORY = 'MFT180L8O5CEGO6CL4C'
_last = None
def set_led(s, l, r, g, b):
    global _last
    if (r, g, b) != _last:
        print('[mock-drone] LED strip=%d led=%d rgb=(%d,%d,%d)' % (s, l, r, g, b), flush=True)
        _last = (r, g, b)
def led_off(): print('[mock-drone] LED off', flush=True)
def led_take_control(): pass
def led_release_control(): pass
def play_tune(tune, format='QBASIC'):
    print('[mock-drone] BUZZER %s %s' % (format, tune), flush=True)
def get_fcu_status(max_age=3.0):
    return {'connected': True, 'armed': False, 'mode': 'POSCTL', 'cell': 4.0, 'ok': True}
'''


class FakeNmcli:
    """Just enough NetworkManager to drive the GCS Wi-Fi screens."""

    def __init__(self):
        self.connections = ['netplan-wlan0-Classroom', 'bumblebee-hotspot']
        self.active = 'netplan-wlan0-Classroom'

    def __call__(self, *args):
        say('nmcli', ' '.join(args))
        if args[:4] == ('-t', '-f', 'NAME', 'con'):
            return '\n'.join(self.connections)
        if args[:4] == ('-t', '-f', 'NAME,TYPE', 'con'):
            return '\n'.join(c + ':802-11-wireless' for c in self.connections)
        if args[:4] == ('-t', '-f', 'DEVICE,STATE,CONNECTION', 'device'):
            return 'wlan0:connected:%s' % self.active
        if args[:4] == ('-t', '-f', 'IP4.ADDRESS', 'device'):
            return 'IP4.ADDRESS[1]:192.168.1.50/24'
        if 'IN-USE,SSID,SIGNAL,SECURITY,FREQ' in args:
            return '*:Classroom:80:WPA2:2437 MHz\n:Office:55:WPA2:5180 MHz'
        if 'list' in args:
            return '*:80:Classroom'
        if args[:2] == ('con', 'add'):
            self.connections.insert(0, args[args.index('con-name') + 1])
        if args[:2] in (('con', 'up'), ('connection', 'up')):
            self.active = args[2]
        return ''


# ---- rosbridge stub on :9090 ------------------------------------------------
def telemetry(topic, t):
    if topic == '/mavros/state':
        fcu = STATE['fcu']
        if fcu == 'stale':
            return None
        if fcu == 'lost':
            return {'connected': False, 'armed': False, 'mode': ''}
        return {'connected': True, 'armed': fcu == 'armed', 'mode': 'OFFBOARD' if fcu == 'armed' else 'POSCTL'}
    if topic == '/mavros/battery':
        if STATE['battery'] == 'low':
            return {'voltage': 20.4, 'percentage': 0.12}
        return {'voltage': 24.1, 'percentage': 0.83}
    if topic == '/mavros/mavros/pose':
        yaw = 0.3 * t
        return {'pose': {'position': {'x': math.cos(t / 4), 'y': math.sin(t / 4), 'z': 1.0},
                         'orientation': {'x': 0, 'y': 0, 'z': math.sin(yaw / 2), 'w': math.cos(yaw / 2)}}}
    if topic == '/mavros/mavros/velocity_local':
        return {'twist': {'linear': {'x': -math.sin(t / 4) / 4, 'y': math.cos(t / 4) / 4, 'z': 0}}}
    if topic == '/mavros/mavros/data':
        return {'angular_velocity': {'x': 0.01, 'y': 0.0, 'z': 0.3},
                'linear_acceleration': {'x': 0.0, 'y': 0.0, 'z': 9.81}}
    return None


class Rosbridge(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        self.topics = set()
        self.t0 = time.time()
        self.timer = tornado.ioloop.PeriodicCallback(self.tick, 200)
        self.timer.start()
        say('rosbridge client connected')

    def on_message(self, message):
        msg = json.loads(message)
        if msg.get('op') == 'subscribe':
            self.topics.add(msg['topic'])

    def tick(self):
        if STATE['telemetry'] == 'freeze':
            return
        t = time.time() - self.t0
        for topic in list(self.topics):
            m = telemetry(topic, t)
            if m is not None:
                self.write_message(json.dumps({'op': 'publish', 'topic': topic, 'msg': m}))

    def on_close(self):
        self.timer.stop()
        say('rosbridge client disconnected')


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Mock Bumblebee drone for GCS testing.')
    p.add_argument('--host', default='0.0.0.0',
                   help='address for the drone ports (default 0.0.0.0, so the apps can scan for it)')
    p.add_argument('--control-port', type=int, default=8799,
                   help='port of the /mock/* control API, always on 127.0.0.1')
    for key, values in CHOICES.items():
        p.add_argument('--' + key, choices=values, default=STATE[key])
    return p.parse_args(argv)


def main():
    args = parse_args()
    set_state(fcu=args.fcu, telemetry=args.telemetry, battery=args.battery)
    tmp = tempfile.mkdtemp(prefix='mock-drone-')
    with open(os.path.join(tmp, 'drone.py'), 'w') as f:
        f.write(FAKE_DRONE)
    sys.path.insert(0, tmp)
    os.environ['PYTHONPATH'] = tmp + os.pathsep + os.environ.get('PYTHONPATH', '')

    # The real REST backend, with nmcli and hardware faked.
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logging.getLogger().setLevel(logging.INFO)
    spec = importlib.util.spec_from_file_location(
        'wifi_manager', os.path.join(PKG, 'scripts', 'wifi_manager.py'))
    wm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wm)
    import drone as fake_drone
    fake_drone.get_fcu_status = fcu_status
    wm.nmcli = FakeNmcli()
    wm._drone, wm._LED_OK = fake_drone, True
    wm.ANIM_DIR = os.path.join(PKG, 'examples', 'animations')
    wm.WIFI_SWITCH_MARKER = os.path.join(tmp, 'wifi-switch')
    wm._hotspot_ssid = lambda: 'Bumblebee-' + HWID
    wm.make_app().listen(8765, address=args.host)

    tornado.web.Application([(r'/', Rosbridge)]).listen(9090, address=args.host)
    tornado.web.Application([(r'/mock/(state|set)', ControlHandler)]).listen(
        args.control_port, address='127.0.0.1')

    procs = [subprocess.Popen([sys.executable, os.path.join(PKG, 'scripts', 'sys_metrics.py')])]
    if shutil.which('dns-sd') and args.host not in ('127.0.0.1', 'localhost'):
        procs.append(subprocess.Popen(
            ['dns-sd', '-R', NAME.lower(), '_bumblebee._tcp', 'local', '9090',
             'name=' + NAME, 'rosbridge=9090', 'mjpeg=8080', 'metrics=8888',
             'api=8765', 'id=' + HWID], stdout=subprocess.DEVNULL))
    say('up on %s: REST :8765 (real wifi_manager.py), metrics :8888, rosbridge :9090; control 127.0.0.1:%d' % (args.host, args.control_port))
    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
