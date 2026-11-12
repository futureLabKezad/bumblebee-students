#!/usr/bin/env python3
"""rc_hold.py - goal step 5 (Claude, 06.11.2026). SIMULATOR ONLY.

Talks only to the local PX4 SITL GCS link (udpin 127.0.0.1:14550). For a scenario run it:
  1. reads every PX4 parameter (list + by-name reads for drone names not listed) -> RUN/params_sitl.json (for C2);
  2. then, until RUN/stop_rc exists (or --max-s), sends what the pilot's transmitter and a ground station send:
     RC_CHANNELS_OVERRIDE 25 Hz with the old harness values (flight_trial_33/rc_emulator.py: [1499,1500,1000,1497,
     1000,1000,1500,1000] + 1500 x 8; throttle 1499 while armed, 1000 otherwise) and a GCS HEARTBEAT at 1 Hz;
  3. logs mode/armed changes and STATUSTEXT to RUN/events.jsonl.
It sends no command, no setpoint and no parameter write.
rc_hold2 (09.11, Claude, stand 5B ed.5): copy of step-5 rc_hold.py + pilot take-over: when RUN/pilot_pos appears, the
mode switch CH6 (RC_MAP_FLTMODE 6 on 20EC) goes from 1000 (slot 1 STAB) to 1999 (RC6_MAX, slot 6 = POSCTL, COM_FLTMODE6 2):
what a pilot does to take the drone from the script. Logged once as event pilot_pos.
Usage: python3 -I rc_hold2.py RUN_DIR DRONE.params [--max-s N]
"""
import json
import os
import struct
import sys
import time

from pymavlink import mavutil

CONN = 'udpin:127.0.0.1:14550'
BASE = [1499, 1500, 1000, 1497, 1000, 1000, 1500, 1000] + [1500] * 8


def main():
    run_dir, drone_path = sys.argv[1:3]
    args = sys.argv[3:]
    max_s = float(args[args.index('--max-s') + 1]) if '--max-s' in args else 900
    drone = []
    for line in open(drone_path, encoding='utf-8'):
        if not line.startswith('#') and line.strip():
            parts = line.rstrip('\n').split('\t')
            if parts[1] == '1':
                drone.append(parts[2])
    ev = open(os.path.join(run_dir, 'events.jsonl'), 'a', encoding='utf-8')
    t0 = time.monotonic()

    def log(kind, **kw):
        ev.write(json.dumps({'t': round(time.monotonic() - t0, 3), 'kind': kind, **kw}, ensure_ascii=False) + '\n')
        ev.flush()

    m = mavutil.mavlink_connection(CONN, source_system=255, source_component=190)
    if m.wait_heartbeat(timeout=60) is None:
        sys.exit('no heartbeat from SITL')
    ts, tc = m.target_system, 1
    state = {'armed': False, 'mode': None}
    params = {}
    last_rc = last_hb = 0.0

    def tick():
        nonlocal last_rc, last_hb
        now = time.monotonic()
        if now - last_rc >= 0.04:
            ch = list(BASE)
            ch[2] = 1499 if state['armed'] else 1000
            if os.path.exists(os.path.join(run_dir, 'pilot_pos')):   # rc_hold2: pilot takes Position
                ch[5] = 1999
                if not state.get('pilot_pos'):
                    state['pilot_pos'] = True
                    log('pilot_pos', ch6=1999)
            m.mav.rc_channels_override_send(ts, tc, *ch, 0, 0)
            last_rc = now
        if now - last_hb >= 1.0:
            m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            last_hb = now

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            tick()
            msg = m.recv_match(blocking=True, timeout=0.02)
            if msg is None:
                continue
            t = msg.get_type()
            if t == 'HEARTBEAT' and msg.get_srcSystem() == ts and msg.get_srcComponent() == 1:
                armed = bool(msg.base_mode & 128)
                mode = f'{(msg.custom_mode >> 16) & 0xFF}.{(msg.custom_mode >> 24) & 0xFF}'
                if armed != state['armed'] or mode != state['mode']:
                    log('state', armed=armed, mode=mode)
                state['armed'], state['mode'] = armed, mode
            elif t == 'STATUSTEXT':
                log('statustext', severity=msg.severity, text=msg.text)
            elif t == 'PARAM_VALUE':
                v = msg.param_value
                if msg.param_type in (1, 2, 3, 4, 5, 6):
                    v = struct.unpack('<i', struct.pack('<f', v))[0]
                params[msg.param_id] = {'value': v, 'type': msg.param_type, 'index': msg.param_index,
                                        'count': msg.param_count}

    log('connected', target=[ts, tc])
    pump(1)
    m.mav.param_request_list_send(ts, 1)
    last_n, quiet = -1, 0
    while quiet < 6:
        pump(0.5)
        quiet = quiet + 1 if len(params) == last_n else 0
        last_n = len(params)
    count = max((p['count'] for p in params.values()), default=0)
    have = {p['index'] for p in params.values()}
    for i in range(count):
        if i not in have:
            m.mav.param_request_read_send(ts, 1, b'', i)
            pump(0.05)
    listed = set(params)
    for name in drone:
        if name not in params:
            m.mav.param_request_read_send(ts, 1, name.encode(), -1)
            pump(0.03)
    pump(2)
    with open(os.path.join(run_dir, 'params_sitl.json'), 'x', encoding='utf-8') as f:
        json.dump({'count_reported': count, 'listed': len(listed),
                   'read_by_name': sorted(n for n in params if n not in listed), 'params': params}, f, indent=1,
                  sort_keys=True)
    log('params', count=count, listed=len(listed))
    open(os.path.join(run_dir, 'rc_ready'), 'w').close()
    stop = os.path.join(run_dir, 'stop_rc')
    while not os.path.exists(stop) and time.monotonic() - t0 < max_s:
        pump(0.5)
    log('rc_end', armed=state['armed'])


if __name__ == '__main__':
    main()
