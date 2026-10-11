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
"""Find the baud rate the flight controller speaks MAVLink at, before MAVROS
opens the port, and print the MAVROS fcu_url to use.

PX4's TELEM baud (SER_TEL1_BAUD) is not the same on every drone -- the repo's
own parameter snapshots differ (921600 in px4_v0_0_1, 115200 in px4_v0_0_2) --
and a fixed fcu_url then leaves MAVROS reading garbage: no telemetry, no
buzzer, no flight. This listens on the UART at a few rates and picks the one
where valid MAVLink frames (checked by CRC) arrive.

Read-only: it never writes to the port, so it cannot send the flight
controller anything. It does nothing while another process (e.g. a running
MAVROS) has the port open. The last rate that worked is remembered and tried
first, and is also the fallback when the flight controller is silent (off, or
still booting), so a drone that worked once keeps working.

Usage (start_bumblebee.sh): BB_FCU_URL=$(fcu_detect.py) -- always prints a URL.
Exit status: 0 found, 3 no MAVLink heard (fallback printed), 2 not a serial URL
or no device (configured URL printed).
"""
import argparse
import os
import re
import select
import sys
import termios
import time

DEFAULT_PARAMS = '/home/lb/mavros_params.yaml'
DEFAULT_CACHE = '/home/lb/.bumblebee/fcu_url'
# After the configured and the remembered rate: PX4 defaults and common choices.
COMMON_BAUDS = [921600, 115200, 57600, 460800, 230400, 500000, 1500000, 38400, 19200, 9600]

# msgid -> CRC_EXTRA of messages PX4 streams by default. HEARTBEAT alone is
# enough (1 Hz); the others make detection faster on a busy link. A wrong entry
# could only make frames not count, never make garbage count.
CRC_EXTRA = {0: 50, 1: 124, 2: 137, 22: 220, 24: 24, 30: 39, 31: 246, 32: 185,
             33: 104, 36: 222, 65: 118, 74: 20, 77: 143, 83: 22, 85: 140,
             105: 93, 111: 34, 141: 47, 147: 154, 230: 163, 241: 90, 242: 104,
             245: 130, 253: 83}


def log(msg):
    print('fcu_detect: ' + msg, file=sys.stderr, flush=True)


def x25(data, crc=0xFFFF):
    """MAVLink checksum (CRC-16/MCRF4XX)."""
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


def count_frames(buf):
    """(valid MAVLink v1/v2 frames, heartbeats among them) found in buf."""
    ok = hb = 0
    i, n = 0, len(buf)
    while i < n:
        stx = buf[i]
        if stx == 0xFD and i + 12 <= n:
            ln, incompat = buf[i + 1], buf[i + 2]
            msgid = buf[i + 7] | (buf[i + 8] << 8) | (buf[i + 9] << 16)
            if msgid in CRC_EXTRA and i + 12 + ln <= n:
                crc = x25(bytes(buf[i + 1:i + 10 + ln]) + bytes([CRC_EXTRA[msgid]]))
                if crc == buf[i + 10 + ln] | (buf[i + 11 + ln] << 8):
                    ok += 1
                    hb += msgid == 0
                    i += 12 + ln + (13 if incompat & 1 else 0)
                    continue
        elif stx == 0xFE and i + 8 <= n:
            ln, msgid = buf[i + 1], buf[i + 5]
            if msgid in CRC_EXTRA and i + 8 + ln <= n:
                crc = x25(bytes(buf[i + 1:i + 6 + ln]) + bytes([CRC_EXTRA[msgid]]))
                if crc == buf[i + 6 + ln] | (buf[i + 7 + ln] << 8):
                    ok += 1
                    hb += msgid == 0
                    i += 8 + ln
                    continue
        i += 1
    return ok, hb


def looks_like_mavlink(buf):
    ok, hb = count_frames(buf)
    return hb >= 1 or ok >= 3


def parse_serial_url(url):
    """'/dev/ttyAMA0:115200' or 'serial:///dev/ttyAMA0:115200' -> (dev, baud);
    None for anything else (udp://, tcp://, ...)."""
    m = re.fullmatch(r'(?:serial://)?(/dev/[^:?]+):(\d+)', (url or '').strip())
    return (m.group(1), int(m.group(2))) if m else None


def configured_url(params_path):
    try:
        with open(params_path) as f:
            m = re.search(r'^\s*fcu_url:\s*["\']?([^"\'\s#]+)', f.read(), re.M)
            return m.group(1) if m else None
    except OSError:
        return None


def read_cache(path):
    try:
        with open(path) as f:
            return f.read().strip() or None
    except OSError:
        return None


def write_cache(path, url):
    if read_cache(path) == url:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            f.write(url + '\n')
        os.replace(tmp, path)
    except OSError as e:
        log('cannot remember %s: %s' % (url, e))


def port_in_use(dev):
    """True if another process has dev open (e.g. MAVROS is already running)."""
    real = os.path.realpath(dev)
    try:
        pids = os.listdir('/proc')
    except OSError:
        return False
    for pid in pids:
        if not pid.isdigit() or int(pid) == os.getpid():
            continue
        fd_dir = '/proc/%s/fd' % pid
        try:
            for fd in os.listdir(fd_dir):
                try:
                    if os.path.realpath(os.path.join(fd_dir, fd)) == real:
                        return True
                except OSError:
                    pass
        except OSError:
            pass
    return False


class SerialListener:
    """Opens dev read-only; listen(baud, seconds) returns the bytes heard, or
    None if this system cannot set that rate."""

    def __init__(self, dev):
        self.fd = os.open(dev, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        self.orig = termios.tcgetattr(self.fd)

    def listen(self, baud, seconds):
        speed = getattr(termios, 'B%d' % baud, None)
        if speed is None:
            return None
        attr = termios.tcgetattr(self.fd)
        attr[0] = 0                                            # iflag: raw input
        attr[1] = 0                                            # oflag
        attr[2] = termios.CS8 | termios.CREAD | termios.CLOCAL  # 8N1, ignore modem lines
        attr[3] = 0                                            # lflag: no echo, no canon
        attr[4] = attr[5] = speed
        termios.tcsetattr(self.fd, termios.TCSANOW, attr)
        time.sleep(0.02)
        termios.tcflush(self.fd, termios.TCIFLUSH)              # drop bytes heard at the old rate
        buf = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            r, _, _ = select.select([self.fd], [], [], min(0.1, max(0.0, end - time.monotonic())))
            if r:
                try:
                    buf += os.read(self.fd, 65536)
                except (BlockingIOError, InterruptedError):
                    pass
        return bytes(buf)

    def close(self):
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.orig)
        finally:
            os.close(self.fd)


def candidates(first, *others):
    seen, out = set(), []
    for b in [first, *others, *COMMON_BAUDS]:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def detect(listen, bauds, window, rounds):
    """First baud whose window holds MAVLink, or None. A line that stays silent
    is silent at every rate (flight controller off or still booting), so the
    search stops there instead of trying the remaining rates."""
    for _ in range(rounds):
        for baud in bauds:
            heard = listen(baud, window)
            if heard is None:
                continue
            if not heard:
                return None
            if looks_like_mavlink(heard):
                return baud
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--params', default=DEFAULT_PARAMS)
    ap.add_argument('--cache', default=DEFAULT_CACHE)
    ap.add_argument('--window', type=float, default=1.2, help='seconds to listen per rate')
    ap.add_argument('--rounds', type=int, default=1)
    a = ap.parse_args(argv)

    conf = configured_url(a.params) or '/dev/ttyAMA0:115200'
    serial = parse_serial_url(conf)
    if not serial:
        print(conf)
        return 2
    dev, conf_baud = serial
    cached = read_cache(a.cache)
    cached_serial = parse_serial_url(cached)
    cached_baud = cached_serial[1] if cached_serial and cached_serial[0] == dev else None
    fallback = '%s:%d' % (dev, cached_baud or conf_baud)

    if not os.path.exists(dev):
        log('%s missing, using %s' % (dev, fallback))
        print(fallback)
        return 2
    if port_in_use(dev):
        log('%s is in use (MAVROS running?), not probing; using %s' % (dev, fallback))
        print(fallback)
        return 0

    try:
        port = SerialListener(dev)
    except OSError as e:
        log('cannot open %s (%s), using %s' % (dev, e, fallback))
        print(fallback)
        return 2
    try:
        baud = detect(port.listen, candidates(cached_baud, conf_baud), a.window, a.rounds)
    finally:
        port.close()

    if baud is None:
        log('no MAVLink on %s at any tested rate (flight controller off?), using %s'
            % (dev, fallback))
        print(fallback)
        return 3
    url = '%s:%d' % (dev, baud)
    if baud != conf_baud:
        log('flight controller talks at %d baud, not the configured %d; using %s'
            % (baud, conf_baud, url))
    else:
        log('flight controller found at %s' % url)
    write_cache(a.cache, url)
    print(url)
    return 0


if __name__ == '__main__':
    sys.exit(main())
