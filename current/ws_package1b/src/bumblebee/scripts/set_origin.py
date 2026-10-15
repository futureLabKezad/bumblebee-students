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
set_origin.py -- send SET_GPS_GLOBAL_ORIGIN to PX4 via pymavlink.

PX4 without GPS has no global origin, causing pos_horiz_abs=false and
preventing arming. This sends the origin via MAVROS GCS TCP bridge.

Usage: python3 set_origin.py [--host 127.0.0.1] [--port 5760]
"""

import argparse
import time
from pymavlink import mavutil


def main():
    parser = argparse.ArgumentParser(description='Send SET_GPS_GLOBAL_ORIGIN to PX4')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5760)
    parser.add_argument('--lat', type=float, default=25.2048, help='Latitude (deg)')
    parser.add_argument('--lon', type=float, default=55.2708, help='Longitude (deg)')
    parser.add_argument('--alt', type=float, default=5.0, help='Altitude MSL (m)')
    args = parser.parse_args()

    conn_str = f'tcp:{args.host}:{args.port}'
    print(f'Connecting to {conn_str}...')
    mav = mavutil.mavlink_connection(conn_str, source_system=255, source_component=190)

    print('Waiting for heartbeat...')
    mav.wait_heartbeat(timeout=10)
    print(f'Heartbeat from system {mav.target_system}, component {mav.target_component}')

    lat_e7 = int(args.lat * 1e7)
    lon_e7 = int(args.lon * 1e7)
    alt_mm = int(args.alt * 1000)

    # Send SET_GPS_GLOBAL_ORIGIN
    for i in range(5):
        mav.mav.set_gps_global_origin_send(
            mav.target_system,  # target_system
            lat_e7,             # latitude (degE7)
            lon_e7,             # longitude (degE7)
            alt_mm,             # altitude (mm MSL)
        )
        print(f'  Sent SET_GPS_GLOBAL_ORIGIN #{i+1}: lat={args.lat}, lon={args.lon}, alt={args.alt}m')
        time.sleep(0.5)

    # Also send SET_HOME_POSITION for good measure
    for i in range(3):
        mav.mav.command_long_send(
            mav.target_system,
            mav.target_component,
            179,  # MAV_CMD_DO_SET_HOME
            0,    # confirmation
            0,    # use specified position (not current)
            0, 0, 0,  # unused
            args.lat,  # latitude
            args.lon,  # longitude
            args.alt,  # altitude
        )
        print(f'  Sent MAV_CMD_DO_SET_HOME #{i+1}')
        time.sleep(0.5)

    # Wait for GPS_GLOBAL_ORIGIN response
    print('Waiting for GPS_GLOBAL_ORIGIN response...')
    start = time.time()
    while time.time() - start < 5:
        msg = mav.recv_match(type=['GPS_GLOBAL_ORIGIN', 'COMMAND_ACK', 'STATUSTEXT'],
                             blocking=True, timeout=1)
        if msg:
            mtype = msg.get_type()
            if mtype == 'GPS_GLOBAL_ORIGIN':
                print(f'  GPS_GLOBAL_ORIGIN: lat={msg.latitude/1e7}, lon={msg.longitude/1e7}, alt={msg.altitude/1000}m')
            elif mtype == 'COMMAND_ACK':
                print(f'  COMMAND_ACK: cmd={msg.command}, result={msg.result}')
            elif mtype == 'STATUSTEXT':
                print(f'  STATUSTEXT: {msg.text}')

    mav.close()
    print('Done.')


if __name__ == '__main__':
    main()
