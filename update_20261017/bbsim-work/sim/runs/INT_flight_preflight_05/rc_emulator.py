#!/usr/bin/env python3
"""Neutral virtual RC/GCS through the profile proxy, independent of MAVROS."""
import argparse
import json
import os
from pathlib import Path
import socket
import time
os.environ['MAVLINK20'] = '1'
from pymavlink import mavutil

p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--guard',type=Path,required=True);a=p.parse_args()
assert str(a.out).startswith('/work/sim/runs/INT_flight_')
assert not any(Path(x).exists() for x in ('/etc/bumblebee','/etc/bumblebee_version','/dev/px4'))
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0))
encoder=mavutil.mavlink.MAVLink(None,srcSystem=255,srcComponent=190)
channels=[1499,1500,1000,1497,1000,1000,1500,1000]+[1500]*8
report={'destination':['127.0.0.1',14680],'source':[255,190],
        'local_endpoint':sock.getsockname(),'heartbeat_count':0,'rc_count':0,
        'max_hb_gap':0.,'max_rc_gap':0.,'parameter_commands':0,'arm_commands':0}
last_hb=last_rc=last_save=None;start=time.monotonic()
def send(msg):
    frame=msg.pack(encoder);encoder.seq=(encoder.seq+1)%256
    sock.sendto(frame,('127.0.0.1',14680))
def save():
    tmp=a.out/'rc_emulator.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(a.out/'rc_emulator.json')
try:
    while time.monotonic()-start<900 and not (a.out/'rc_stop').exists():
        now=time.monotonic()
        if last_hb is None or now-last_hb>=1.:
            send(mavutil.mavlink.MAVLink_heartbeat_message(6,8,0,0,4,3))
            report['heartbeat_count']+=1
            if last_hb is not None:report['max_hb_gap']=max(report['max_hb_gap'],now-last_hb)
            last_hb=now
        status=json.loads((a.guard/'status.json').read_text())
        if 0<=now-status['received']<.5 and (last_rc is None or now-last_rc>=.05):
            hb=status.get('heartbeat')
            if hb:
                channels[2]=1499 if hb['armed'] else 1000
                send(mavutil.mavlink.MAVLink_rc_channels_override_message(1,1,*channels))
                report['rc_count']+=1;report['channels']=list(channels)
                if last_rc is not None:report['max_rc_gap']=max(report['max_rc_gap'],now-last_rc)
                last_rc=now
        if last_save is None or now-last_save>=1.:
            report['last_wall']=now;save();last_save=now
        time.sleep(.01)
finally:
    save();sock.close()
