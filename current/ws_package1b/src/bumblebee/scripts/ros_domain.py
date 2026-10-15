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
"""Pick this drone's ROS_DOMAIN_ID and print it.

Every drone runs the same ROS graph (/mavros/..., /simple_offboard/...). On a
shared Wi-Fi, drones in the same DDS domain see each other's topics and
services -- an arming call meant for one can reach another. So each drone gets
its own domain (1-101; 0 stays the ROS default for laptops):

  * the one remembered for this drone (state file, bound to its wlan0 MAC), else
  * one derived from the MAC, and with --browse
  * a free one if another drone on the Wi-Fi already advertises the same domain
    in its Bonjour record (_bumblebee._tcp TXT ros_domain=..). The drone that
    notices the clash moves -- usually the one that just joined (a drone that
    has been running all along may be flying); set_identity.sh re-runs this
    every minute, so a clash missed once is found on the next pass. Free
    domains are probed in a MAC-seeded order, so two drones moving at the same
    moment do not land on the same new domain.

The choice is remembered, so a drone keeps its domain from boot to boot.
Called by set_identity.sh (root): without --browse at boot, with --browse from
the NetworkManager hook once Wi-Fi is up and from the minute timer; with
--keep N when a move has to wait (PX4 not confirmed disarmed), so the next pass
starts from the domain the flight stack really runs on. avahi-utils is not installed, so the
browse is a one-shot mDNS query (RFC 6762 legacy unicast) answered by the
other drones' avahi daemons.

Usage: ros_domain.py --mac 88:a2:9e:57:20:ec --id 20EC --state FILE [--browse | --keep N]
"""
import argparse
import os
import random
import socket
import struct
import sys
import time

FIRST, LAST = 1, 101            # ROS 2 domains whose ports never collide on Linux
SERVICE = '_bumblebee._tcp.local'
MDNS_ADDR = ('224.0.0.251', 5353)
TYPE_PTR, TYPE_TXT = 12, 16


def log(msg):
    print('ros_domain: ' + msg, file=sys.stderr, flush=True)


def preferred(mac):
    """Domain derived from the MAC (stable, spread over FIRST..LAST)."""
    digits = mac.replace(':', '').lower()
    return FIRST + int(digits[-6:] or '0', 16) % (LAST - FIRST + 1)


def read_state(path, mac):
    """Remembered domain if the file belongs to this drone ('<domain> <mac>')."""
    try:
        with open(path) as f:
            parts = f.read().split()
        domain, owner = int(parts[0]), parts[1].lower()
    except (OSError, ValueError, IndexError):
        return None
    if owner != mac.lower() or not FIRST <= domain <= LAST:
        return None
    return domain


def write_state(path, domain, mac):
    if read_state(path, mac) == domain:
        return
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write('%d %s\n' % (domain, mac.lower()))
    os.replace(tmp, path)


def probe_step(mac):
    """Per-drone step through the domains. The span (101) is prime, so every
    step 1..100 visits all of them, and different drones visit them in
    different orders."""
    digits = mac.replace(':', '').lower()
    return 1 + int(digits or '0', 16) % (LAST - FIRST)


def choose(current, my_id, others, mac=''):
    """Keep `current` unless another drone advertises it; then the first domain
    nobody advertises, in this drone's own probe order. `others` maps drone
    id -> advertised domain (our own id is ignored)."""
    taken = {d for i, d in others.items() if i != my_id}
    if current not in taken:
        return current
    span, step = LAST - FIRST + 1, probe_step(mac)
    for k in range(1, span):
        d = FIRST + (current - FIRST + k * step) % span
        if d not in taken:
            return d
    return current


# ---- minimal mDNS client ------------------------------------------------------

def encode_name(name):
    out = b''
    for label in name.rstrip('.').split('.'):
        raw = label.encode()
        out += bytes([len(raw)]) + raw
    return out + b'\x00'


def build_query(qid, names, qtype):
    head = struct.pack('!HHHHHH', qid, 0, len(names), 0, 0, 0)
    return head + b''.join(encode_name(n) + struct.pack('!HH', qtype, 1) for n in names)


def read_name(msg, off):
    """(name, offset after it) with DNS compression pointers followed."""
    labels, jumped, end = [], False, off
    for _ in range(128):                       # bound against pointer loops
        n = msg[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            if not jumped:
                end = off + 2
            off = ((n & 0x3F) << 8) | msg[off + 1]
            jumped = True
            continue
        labels.append(msg[off + 1:off + 1 + n].decode('utf-8', 'replace'))
        off += 1 + n
    else:
        raise ValueError('name too long')
    return '.'.join(labels), (end if jumped else off)


def parse_records(msg):
    """[(name, type, rdata_offset, rdlength)] of every record in a response."""
    _, flags, qd, an, ns, ar = struct.unpack('!HHHHHH', msg[:12])
    off = 12
    for _ in range(qd):
        _, off = read_name(msg, off)
        off += 4
    out = []
    for _ in range(an + ns + ar):
        name, off = read_name(msg, off)
        rtype, _, _, rdlen = struct.unpack('!HHIH', msg[off:off + 10])
        off += 10
        out.append((name, rtype, off, rdlen))
        off += rdlen
    return out


def txt_dict(msg, off, rdlen):
    out, end = {}, off + rdlen
    while off < end:
        n = msg[off]
        item = msg[off + 1:off + 1 + n].decode('utf-8', 'replace')
        off += 1 + n
        key, _, value = item.partition('=')
        if key:
            out[key] = value
    return out


def mdns_ask(sock, names, qtype, seconds):
    """Send a legacy-unicast mDNS query (three times: multicast over Wi-Fi gets
    lost); collect PTR targets and TXT dicts."""
    qid = random.randrange(1, 0xFFFF)
    query = build_query(qid, names, qtype)
    start = time.monotonic()
    resend = [start + seconds * f for f in (0.0, 0.3, 0.6)]
    ptrs, txts = set(), {}
    end = start + seconds
    while True:
        now = time.monotonic()
        while resend and resend[0] <= now:
            resend.pop(0)
            try:
                sock.sendto(query, MDNS_ADDR)
            except OSError:
                pass
        left = end - now
        if left <= 0:
            break
        sock.settimeout(min(left, resend[0] - now) if resend else left)
        try:
            msg, _ = sock.recvfrom(9000)
        except socket.timeout:
            continue
        except OSError:
            break
        try:
            if struct.unpack('!H', msg[:2])[0] != qid:
                continue
            for name, rtype, off, rdlen in parse_records(msg):
                if rtype == TYPE_PTR and name.lower() == SERVICE:
                    ptrs.add(read_name(msg, off)[0])
                elif rtype == TYPE_TXT:
                    txts[name] = txt_dict(msg, off, rdlen)
        except (ValueError, IndexError, struct.error):
            continue
    return ptrs, txts


def browse(seconds=1.5):
    """Drone id -> advertised ROS domain, for every drone answering on the LAN."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sock.bind(('', 0))                     # not 5353: answered by unicast
        instances, txts = mdns_ask(sock, [SERVICE], TYPE_PTR, seconds)
        missing = sorted(i for i in instances if i not in txts)
        if missing:
            _, more = mdns_ask(sock, missing, TYPE_TXT, seconds)
            txts.update(more)
    finally:
        sock.close()
    found = {}
    for txt in txts.values():
        try:
            found[txt['id'].upper()] = int(txt['ros_domain'])
        except (KeyError, ValueError):
            continue
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--mac', required=True)
    ap.add_argument('--id', required=True, help='drone id (last 4 hex of the MAC)')
    ap.add_argument('--state', required=True)
    ap.add_argument('--browse', action='store_true', help='avoid domains other drones use')
    ap.add_argument('--keep', type=int, metavar='N',
                    help='the flight stack stays on N for now: remember N')
    a = ap.parse_args(argv)

    mac, my_id = a.mac.strip().lower(), a.id.strip().upper()
    if a.keep is not None:
        if FIRST <= a.keep <= LAST:
            try:
                write_state(a.state, a.keep, mac)
            except OSError as e:
                log('cannot remember domain %d: %s' % (a.keep, e))
        print(a.keep)
        return 0
    domain = read_state(a.state, mac) or preferred(mac)
    if a.browse:
        try:
            others = browse()
        except OSError as e:
            log('browse failed (%s), keeping %d' % (e, domain))
            others = {}
        new = choose(domain, my_id, others, mac)
        if new != domain:
            rivals = sorted(i for i, d in others.items() if d == domain and i != my_id)
            log('domain %d is also used by %s; this drone moves to %d' % (domain, ', '.join(rivals), new))
            domain = new
    try:
        write_state(a.state, domain, mac)
    except OSError as e:
        log('cannot remember domain %d: %s' % (domain, e))
    print(domain)
    return 0


if __name__ == '__main__':
    sys.exit(main())
