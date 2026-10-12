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
"""Print whether the flight controller is armed: armed / disarmed / unknown.

Reads PX4's own HEARTBEAT from MAVROS's GCS port (tcp 5760) instead of ROS,
because it is asked exactly when ROS may not be trusted -- right after the
system clock jumped (see clock_jump.sh). Read-only: sends nothing.

Only the autopilot's heartbeat counts (component 1, a real autopilot type):
MAVROS's own heartbeat (component 191, onboard controller) is relayed on the
same port with flags that look armed.

Exit status: 0 disarmed, 1 armed, 2 unknown (no autopilot heartbeat heard).
"""
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fcu_detect  # noqa: E402  (same directory: MAVLink checksum)

MAV_COMP_ID_AUTOPILOT1 = 1
MAV_AUTOPILOT_INVALID = 8
MAV_TYPE_GCS, MAV_TYPE_ONBOARD_CONTROLLER = 6, 18
MAV_MODE_FLAG_SAFETY_ARMED = 0x80
HEARTBEAT_CRC_EXTRA = 50


def autopilot_heartbeats(buf):
    """base_mode of every CRC-valid MAVLink v2 HEARTBEAT from an autopilot."""
    out, i, n = [], 0, len(buf)
    while True:
        i = buf.find(b'\xfd', i)
        if i < 0 or i + 12 > n:
            return out
        ln, incompat = buf[i + 1], buf[i + 2]
        end = i + 12 + ln
        if buf[i + 7:i + 10] != b'\x00\x00\x00' or end > n:
            i += 1
            continue
        crc = fcu_detect.x25(bytes(buf[i + 1:i + 10 + ln]) + bytes([HEARTBEAT_CRC_EXTRA]))
        if crc != buf[end - 2] | (buf[end - 1] << 8):
            i += 1
            continue
        payload = bytes(buf[i + 10:i + 10 + ln]) + bytes(9)     # v2 trims trailing zeros
        compid = buf[i + 6]
        mav_type, autopilot, base_mode = payload[4], payload[5], payload[6]
        if (compid == MAV_COMP_ID_AUTOPILOT1 and autopilot != MAV_AUTOPILOT_INVALID
                and mav_type not in (MAV_TYPE_GCS, MAV_TYPE_ONBOARD_CONTROLLER)):
            out.append(base_mode)
        i = end + (13 if incompat & 1 else 0)


def state(host='127.0.0.1', port=5760, seconds=3.0):
    """'armed' / 'disarmed' from the latest autopilot heartbeat, else 'unknown'."""
    try:
        s = socket.create_connection((host, port), timeout=1.0)
    except OSError:
        return 'unknown'
    buf, end = bytearray(), time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            try:
                chunk = s.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            buf += chunk
            beats = autopilot_heartbeats(buf)
            if beats:
                return 'armed' if beats[-1] & MAV_MODE_FLAG_SAFETY_ARMED else 'disarmed'
    except OSError:
        pass
    finally:
        s.close()
    return 'unknown'


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    host = argv[0] if argv else '127.0.0.1'
    result = state(host)
    print(result)
    return {'disarmed': 0, 'armed': 1}.get(result, 2)


if __name__ == '__main__':
    sys.exit(main())
