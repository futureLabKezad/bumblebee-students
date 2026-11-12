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
"""Watch that the drone's ROS graph still delivers data; restart it if not.

On drone 20EC the ROS 2 nodes started at power-on sometimes stop delivering
data to each other a minute or two later (rosbridge -- i.e. the GCS app --
gets no telemetry, rosapi calls time out, camera_fix sees no frames, while
MAVROS itself keeps talking to the flight controller). It never recovers on
its own; restarting the stack does, and it then stays healthy. This watchdog
makes that automatic:

  every CHECK_S seconds, subscribe to /mavros/state through the local
  rosbridge (exactly the path the app uses). /mavros/state is published on
  every flight-controller heartbeat (1 Hz). If nothing arrives for FAIL_S while
  PX4's own heartbeat is present on MAVROS's GCS port (so the flight controller
  link is fine and the fault is on the ROS side), restart the ROS services --
  only when that heartbeat says disarmed, never when armed or unknown, and at
  most once per BACKOFF_S.

Runs as root (it restarts system units); everything it reads is read-only.
"""
import base64
import json
import logging
import os
import socket
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fcu_armed  # noqa: E402  (same directory)

HOST = os.environ.get('BB_ROSBRIDGE_HOST', '127.0.0.1')
PORT = int(os.environ.get('BB_ROSBRIDGE_PORT', '9090'))
CHECK_S = float(os.environ.get('BB_WD_CHECK_S', '10'))
FAIL_S = float(os.environ.get('BB_WD_FAIL_S', '30'))
GRACE_S = float(os.environ.get('BB_WD_GRACE_S', '60'))      # after a (re)start of the stack
BACKOFF_S = float(os.environ.get('BB_WD_BACKOFF_S', '600'))
# A restart that does not help will not help the next time either: stop after
# a few per boot instead of restarting the flight stack forever.
MAX_RESTARTS = int(os.environ.get('BB_WD_MAX_RESTARTS', '3'))
UNITS = ['bumblebee', 'notify-manager', 'wifi-manager']

log = logging.getLogger('ros_watchdog')


def ws_messages(buf):
    """Split complete server->client websocket text frames off buf (unmasked).
    Returns (list of payload bytes, rest of buf)."""
    out = []
    while len(buf) >= 2:
        n, off = buf[1] & 0x7F, 2
        if n == 126:
            if len(buf) < 4:
                break
            n, off = struct.unpack('>H', buf[2:4])[0], 4
        elif n == 127:
            if len(buf) < 10:
                break
            n, off = struct.unpack('>Q', buf[2:10])[0], 10
        if len(buf) < off + n:
            break
        if buf[0] & 0x0F == 1:                         # text frame
            out.append(buf[off:off + n])
        buf = buf[off + n:]
    return out, buf


def is_state(payload):
    # rosbridge escapes '/' in JSON ("\/mavros\/state"): decode, never grep.
    try:
        msg = json.loads(payload)
    except ValueError:
        return False
    return isinstance(msg, dict) and msg.get('op') == 'publish' and msg.get('topic') == '/mavros/state'


def state_arrives(host=HOST, port=PORT, timeout=4.0):
    """True if /mavros/state comes through rosbridge within `timeout`."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return False
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        s.sendall(('GET / HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                   'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (host, port, key)).encode())
        buf, end = b'', time.monotonic() + timeout
        while b'\r\n\r\n' not in buf:
            if time.monotonic() > end:
                return False
            chunk = s.recv(4096)
            if not chunk:
                return False
            buf += chunk
        buf = buf.split(b'\r\n\r\n', 1)[1]
        p = json.dumps({'op': 'subscribe', 'topic': '/mavros/state',
                        'type': 'mavros_msgs/msg/State'}).encode()
        mask = os.urandom(4)
        hdr = bytes([0x81, 0x80 | len(p)]) if len(p) < 126 else bytes([0x81, 0xFE]) + struct.pack('>H', len(p))
        s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(p)))
        while True:
            frames, buf = ws_messages(buf)
            if any(is_state(f) for f in frames):
                return True
            left = end - time.monotonic()
            if left <= 0:
                return False
            s.settimeout(left)
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                return False
            if not chunk:
                return False
            buf += chunk
    except OSError:
        return False
    finally:
        s.close()


def unit_age(unit):
    """Seconds since `unit` entered its active state, or None if not active."""
    try:
        out = subprocess.run(['systemctl', 'show', '-p', 'ActiveState', '-p',
                              'ActiveEnterTimestampMonotonic', unit],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    props = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
    if props.get('ActiveState') != 'active':
        return None
    since = int(props.get('ActiveEnterTimestampMonotonic', '0') or 0) / 1e6
    return time.clock_gettime(time.CLOCK_MONOTONIC) - since if since else None


class Watchdog:
    """Decision logic, separated from I/O so it can be tested."""

    def __init__(self, now):
        self.last_ok = now
        self.last_restart = -1e9
        self.restarts = 0

    def step(self, now, stack_age, healthy, fcu):
        """Return 'restart', 'wait' or 'ok'. fcu: armed / disarmed / unknown."""
        if stack_age is None or stack_age < GRACE_S:
            self.last_ok = now                      # starting up: nothing to judge yet
            return 'ok'
        if healthy:
            self.last_ok = now
            return 'ok'
        if now - self.last_ok < FAIL_S:
            return 'wait'
        if fcu == 'unknown':
            # no flight-controller link either: not the fault we fix here
            return 'wait'
        if fcu != 'disarmed' or now - self.last_restart < BACKOFF_S:
            return 'wait'
        if self.restarts >= MAX_RESTARTS:
            return 'give_up'
        self.restarts += 1
        self.last_restart = now
        self.last_ok = now
        return 'restart'


def main():
    logging.basicConfig(level=logging.INFO, format='ros_watchdog: %(message)s')
    wd = Watchdog(time.monotonic())
    warned = False
    while True:
        now = time.monotonic()
        age = unit_age('bumblebee')
        healthy = state_arrives() if age is not None and age >= GRACE_S else True
        fcu = 'unknown' if healthy else fcu_armed.state()
        decision = wd.step(now, age, healthy, fcu)
        if decision == 'restart':
            log.warning('no /mavros/state through rosbridge for %.0f s while the flight '
                        'controller is linked and disarmed: restarting %s', FAIL_S, ' '.join(UNITS))
            subprocess.run(['systemctl', '--no-block', 'restart'] + UNITS, check=False)
            warned = False
        elif decision == 'wait' and not healthy and fcu == 'armed' and not warned:
            log.warning('ROS graph stopped delivering data while ARMED: not restarting; land first')
            warned = True
        elif decision == 'give_up' and not warned:
            log.warning('ROS graph still not delivering data after %d restarts: giving up '
                        'until the next boot', MAX_RESTARTS)
            warned = True
        elif decision == 'ok':
            warned = False
        time.sleep(CHECK_S)


if __name__ == '__main__':
    main()
