#!/usr/bin/env python3
"""Loopback-only, SITL-guarded MAVLink recorder and bounded fault injection."""
import argparse
import json
import os
import select
import socket
import struct
import time
from proxy_profile_policy import ProxyProfilePolicy
from param_set_audit import param_set_record, forward_outbound
from pathlib import Path

os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

p = argparse.ArgumentParser()
p.add_argument('--out', required=True)
p.add_argument('--profile-guard', required=True)
p.add_argument('--ack-delay', type=float, default=0.)
a = p.parse_args()
out = Path(a.out)
guard = ProxyProfilePolicy(a.profile_guard)
assert str(out).startswith('/work/sim/runs/') and 0 <= a.ack_delay <= 4
assert not Path('/etc/bumblebee').exists() and not Path('/etc/bumblebee_version').exists()
# The runner checked SIM_GZ_EN independently before opening this proxy.
assert json.loads((out / 'rc_ready.json').read_text())['parameters']['COM_OBL_RC_ACT']['after'] in (0, 4)
up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
down = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
up.bind(('127.0.0.1', 14540))
down.bind(('127.0.0.1', 14680))
parsers = [mavutil.mavlink.MAVLink(None), mavutil.mavlink.MAVLink(None)]
for parser in parsers:
    parser.robust_parsing = True
start = time.monotonic()
px4_sim = None
px4_clock_wall = None
px4_clock_source = None
last_clock_report_wall = 0.
delayed = []
control_observation = {}
delay_next_ack = False
f = (out / 'mavlink_proxy.jsonl').open('w')

def record(kind, **kw):
    f.write(json.dumps({'wall': time.monotonic(), 'elapsed': time.monotonic()-start,
                        'kind': kind, 'px4_sim': px4_sim, **kw}) + '\n')
    f.flush()


def update_px4_clock(msg, kind):
    """PX4 boot time, never host UNIX time or a TIMESYNC echo."""
    global px4_sim, px4_clock_wall, px4_clock_source, last_clock_report_wall
    clock_messages = {'LOCAL_POSITION_NED', 'ATTITUDE', 'ATTITUDE_QUATERNION',
                      'GLOBAL_POSITION_INT', 'SYSTEM_TIME'}
    if (msg is None or kind not in clock_messages or msg.get_srcSystem() != 1
            or msg.get_srcComponent() != 1):
        return
    sim = msg.time_boot_ms / 1000.
    if px4_sim is not None and sim < px4_sim:
        return
    px4_sim, px4_clock_wall, px4_clock_source = sim, time.monotonic(), kind
    if px4_clock_wall - last_clock_report_wall >= .1:
        payload = {'px4_sim': px4_sim, 'wall': px4_clock_wall,
                   'source_message': kind, 'source_system': 1, 'source_component': 1}
        temporary = out / 'proxy_clock.tmp'
        temporary.write_text(json.dumps(payload))
        temporary.replace(out / 'proxy_clock.json')
        last_clock_report_wall = px4_clock_wall

def frames(data):
    """MAVROS/PX4 datagrams may contain several complete MAVLink frames."""
    i = 0
    while i < len(data):
        magic = data[i]
        if magic == 0xFD and i+10 <= len(data):
            n = 12+data[i+1]+(13 if data[i+2] & 1 else 0)
        elif magic == 0xFE and i+6 <= len(data):
            n = 8+data[i+1]
        else:
            yield data[i:]
            return
        if i+n > len(data):
            yield data[i:]
            return
        yield data[i:i+n]
        i += n

record('started', ack_delay=a.ack_delay, schema=2,
       forwarded_setpoint_payload=True, forwarded_setpoint_source=True,
       px4_clock_basis='PX4 source 1/1 time_boot_ms messages',
       recorded_packet_types=['COMMAND_LONG','COMMAND_INT','COMMAND_ACK','SET_MODE',
                              'SET_POSITION_TARGET_LOCAL_NED','SET_ATTITUDE_TARGET','HEARTBEAT'])
(out / 'proxy_ready').touch()
try:
    while time.monotonic()-start < 900 and not (out / 'proxy_stop').exists():
        now = time.monotonic()
        guard.tick()
        for due, frame in list(delayed):
            if due <= now:
                down.sendto(frame, ('127.0.0.1', 14640))
                delayed.remove((due, frame))
                record('released_arm_ack')
        readable, _, _ = select.select([up, down], [], [], .02)
        for sock in readable:
            data, peer = sock.recvfrom(65535)
            assert peer[0] == '127.0.0.1'
            inbound = sock is up
            parser = parsers[0 if inbound else 1]
            for frame in frames(data):
                arm_sent = False
                msg = parser.parse_char(frame)
                kind = msg.get_type() if msg else 'UNPARSED'
                if not guard.accept(msg, inbound):
                    if not inbound and kind=='PARAM_SET':
                        record('param_set', **param_set_record(msg,False))
                    record('profile_policy_blocked', packet_type=kind,
                           direction='px4_to_ros' if inbound else 'ros_to_px4',
                           source_system=msg.get_srcSystem() if msg is not None else None,
                           source_component=msg.get_srcComponent() if msg is not None else None,
                           sequence=msg.get_seq() if msg is not None else None,
                           reason=guard.last_rejection or 'outbound_policy_rejected')
                    continue
                if inbound:
                    update_px4_clock(msg, kind)
                if kind in ('COMMAND_LONG', 'COMMAND_INT', 'COMMAND_ACK', 'SET_MODE',
                            'SET_POSITION_TARGET_LOCAL_NED', 'SET_ATTITUDE_TARGET'):
                    record('packet', direction='px4_to_ros' if inbound else 'ros_to_px4',
                           source_system=msg.get_srcSystem(), source_component=msg.get_srcComponent(),
                           sequence=msg.get_seq(), **msg.to_dict())
                if not inbound and kind == 'COMMAND_LONG' and msg.command == 400 and msg.param1 > .5:
                    delay_next_ack = True
                    arm_sent = True
                if inbound and kind == 'COMMAND_ACK' and msg.command == 400 and delay_next_ack:
                    delay_next_ack = False
                    if a.ack_delay:
                        delayed.append((now+a.ack_delay, frame))
                        record('held_arm_ack', delay=a.ack_delay, result=msg.result)
                        continue
                if inbound and kind == 'HEARTBEAT':
                    is_px4=msg.get_srcSystem()==1 and msg.get_srcComponent()==1 and msg.autopilot==12
                    record('heartbeat', armed=bool(msg.base_mode & 128), custom_mode=msg.custom_mode,
                           source_system=msg.get_srcSystem(),source_component=msg.get_srcComponent(),
                           autopilot=msg.autopilot,type=msg.type,is_px4=is_px4)
                    control = out / 'proxy_fault.json'
                    directive = json.loads(control.read_text()) if control.exists() else {}
                    sim_drop = (px4_sim is not None and
                                px4_sim < directive.get('drop_heartbeat_until_px4_sim', -1))
                    if is_px4 and (directive.get('drop_heartbeat',False) or sim_drop
                                   or now < directive.get('drop_heartbeat_until_wall', 0)):
                        record('dropped_heartbeat', phase=directive.get('phase'),
                               until_px4_sim=directive.get('drop_heartbeat_until_px4_sim'),
                               source_system=msg.get_srcSystem(), source_component=msg.get_srcComponent())
                        continue
                if inbound:
                    down.sendto(frame, ('127.0.0.1', 14640))
                    if kind == 'HEARTBEAT' and is_px4:
                        record('heartbeat_forwarded', armed=bool(msg.base_mode & 128),
                               custom_mode=msg.custom_mode, source_system=1,
                               source_component=1, autopilot=msg.autopilot, type=msg.type,
                               phase=directive.get('phase'))
                else:
                    forward_outbound(frame,msg,lambda raw: up.sendto(raw, ('127.0.0.1',14580)),record,control_observation)
                    if arm_sent:
                        record('arm_forwarded', source_system=msg.get_srcSystem(), source_component=msg.get_srcComponent())
                    if kind in ('SET_POSITION_TARGET_LOCAL_NED','SET_ATTITUDE_TARGET'):
                        record('setpoint_forwarded', packet_type=kind, direction='ros_to_px4',
                               source_system=msg.get_srcSystem(), source_component=msg.get_srcComponent(),
                               sequence=msg.get_seq(), **msg.to_dict())
finally:
    record('stopped')
    f.close()
    up.close()
    down.close()
