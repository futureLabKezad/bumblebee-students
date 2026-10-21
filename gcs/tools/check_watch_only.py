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

"""Check that the GCS apps only watch the drone.

Bumblebee GCS (Mac and Windows) must never fly the drone: no arming, no mode
changes, no setpoints, no PX4 parameter writes. Today this holds because the
apps only *subscribe* over rosbridge and call a fixed set of drone REST
endpoints (Wi-Fi, lights, sounds). This script makes that a CI rule instead of
a code comment.

    python3 gcs/tools/check_watch_only.py          # exit 1 on any violation

Rules, applied to gcs/macos/Sources and gcs/windows/src:
  1. rosbridge: the only ops the apps may send are subscribe and unsubscribe.
  2. No flight-control names (MAVROS command/param/setpoint services, the
     simple_offboard services, MAVLink ports).
  3. REST: every "/api/..." path must be in ALLOWED_API. A new endpoint is a
     deliberate change to this list, reviewed like any other.
A line can opt out of rule 2 with a trailing "watch-only: allow <reason>"
comment; use it only for text that names these things without calling them.
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SOURCES = ['gcs/macos/Sources', 'gcs/windows/src']
EXTENSIONS = ('.swift', '.cs')

ALLOWED_OPS = {'subscribe', 'unsubscribe'}

ALLOWED_API = {
    '/api/auth/login', '/api/auth/logout',
    '/api/wifi/status', '/api/wifi/scan', '/api/wifi/networks', '/api/wifi/save',
    '/api/wifi/apply-now', '/api/wifi/apply-boot', '/api/wifi/network', '/api/wifi/mode',
    '/api/led/color', '/api/led/animation', '/api/led/status', '/api/led/reset',
    '/api/fcu/status',
    '/api/sounds/play', '/api/sounds/tts',
}

# Names that only appear when something commands the flight controller.
FORBIDDEN = [
    (re.compile(r'/mavros(/mavros)?/(cmd|param|setpoint|set_mode|mission|rc/override)', re.I), 'MAVROS command, parameter or setpoint topic/service'),
    (re.compile(r'\b(cmd/arming|set_mode|setpoint_(raw|position|velocity|attitude|accel))\b', re.I), 'arming, mode or setpoint name'),
    (re.compile(r'\b(CommandBool|CommandLong|CommandTOL|SetMode|ParamSet|ParamPush|OverrideRCIn)\b'), 'MAVROS service type'),
    (re.compile(r'\bcall_service\b|\b"?advertise"?\s*[:=]'), 'rosbridge service call or publisher'),
    (re.compile(r'"/(navigate|navigate_global|set_position|set_velocity|set_attitude|set_rates|land|release)"'), 'simple_offboard service'),
    (re.compile(r'\b(14550|14540|14557|5760)\b'), 'MAVLink port'),
]

OP_PATTERNS = [
    re.compile(r'\\?"op\\?"\s*:\s*\\?"(\w+)'),     # ["op": "subscribe"], {"op":"x"}, escaped JSON
    re.compile(r'\bop\s*=\s*"(\w+)"'),              # C#: new { op = "subscribe" }
]
API_LITERAL = re.compile(r'"(/api/[A-Za-z0-9_./-]*)"')
API_DYNAMIC = re.compile(r'"(/api/[A-Za-z0-9_./-]*)(\\\(|\{)')   # Swift \(x) or C# $"{x}"
ALLOW_MARK = 'watch-only: allow'


def source_files(root):
    for rel in SOURCES:
        base = os.path.join(root, rel)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ('bin', 'obj', '.build')]
            for name in sorted(filenames):
                if name.endswith(EXTENSIONS):
                    yield os.path.join(dirpath, name)


def strip_comment(line):
    """Drop a // comment that is not inside a string literal."""
    in_str = False
    i = 0
    while i < len(line) - 1:
        c = line[i]
        if c == '\\' and in_str:
            i += 2
            continue
        if c == '"':
            in_str = not in_str
        elif not in_str and line[i:i + 2] == '//':
            return line[:i]
        i += 1
    return line


def check_text(path, text):
    problems = []
    in_block = False
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw
        if in_block:
            end = line.find('*/')
            if end < 0:
                continue
            line, in_block = line[end + 2:], False
        start = line.find('/*')
        if start >= 0 and line.find('*/', start) < 0 and '"' not in line[:start]:
            line, in_block = line[:start], True
        allowed = ALLOW_MARK in raw
        code = strip_comment(line)
        for rx in OP_PATTERNS:
            for m in rx.finditer(code):
                if m.group(1) not in ALLOWED_OPS:
                    problems.append((path, n, 'rosbridge op "%s" (only %s allowed)' % (m.group(1), ', '.join(sorted(ALLOWED_OPS)))))
        if not allowed:
            for rx, why in FORBIDDEN:
                m = rx.search(code)
                if m:
                    problems.append((path, n, '%s: %s' % (why, m.group(0))))
        for m in API_LITERAL.finditer(code):
            if m.group(1) not in ALLOWED_API:
                problems.append((path, n, 'REST path %s is not in ALLOWED_API' % m.group(1)))
        for m in API_DYNAMIC.finditer(code):
            problems.append((path, n, 'REST path built at run time (%s...): spell it out and add it to ALLOWED_API' % m.group(1)))
    return problems


def main(argv):
    root = argv[1] if len(argv) > 1 else ROOT
    problems, count = [], 0
    for path in source_files(root):
        count += 1
        with open(path, encoding='utf-8') as f:
            problems += check_text(os.path.relpath(path, root), f.read())
    if count == 0:
        print('check_watch_only: no app sources found under %s' % root, file=sys.stderr)
        return 2
    for path, n, what in problems:
        print('%s:%d: %s' % (path, n, what))
    print('check_watch_only: %d files, %d problems' % (count, len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
