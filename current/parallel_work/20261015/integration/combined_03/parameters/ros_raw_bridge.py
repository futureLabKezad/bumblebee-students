"""Executable bridge for MAVROS 2.14 /uas1 raw topics; no UDP sockets.
ROS/pymavlink imports occur only in constructor. Spin node on another thread.
"""
from collections import deque
import json
import math
from pathlib import Path
import threading
import time
from types import SimpleNamespace as NS
import uuid
from deadline_lock import locked
from proxy_profile_policy import WRITER, atomic_json

class RosRawBridge:
    def __init__(self,node,guard_directory,expected_fcu_endpoint,clock=time.monotonic,
                 codec=None,message_type=None,qos=None,callback_group=None):
        self.node,self.clock=node,clock
        self.directory=Path(guard_directory)
        self.endpoint=expected_fcu_endpoint
        if not self.endpoint.startswith('ep:'):
            raise ValueError('router FCU endpoint must be independently identified')
        self.cv=threading.Condition(threading.RLock())
        self.frames=deque(maxlen=2048)
        self.heartbeat=None
        self.armed_observations=0
        self.fault=None
        self.epoch=None
        self.heartbeat_request_lock=threading.Lock()
        self.last_heartbeat_request_sent=None
        if codec is None:
            from pymavlink import mavutil
            from mavros import mavlink as convert
            from mavros_msgs.msg import Mavlink
            from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
            if not mavutil.mavlink20():
                raise RuntimeError('start with MAVLINK20=1 before importing pymavlink')
            codec=PymavlinkCodec(mavutil,convert)
            message_type=Mavlink
            qos=QoSProfile(depth=1000,reliability=ReliabilityPolicy.BEST_EFFORT,
                durability=DurabilityPolicy.VOLATILE)
        self.codec=codec
        self.publisher=node.create_publisher(message_type,'/uas1/mavlink_sink',qos)
        self.subscription=node.create_subscription(message_type,'/uas1/mavlink_source',
            self.on_message,qos,callback_group=callback_group)
    def on_message(self,msg):
        received=self.clock()
        # Only a separately identified FCU endpoint, valid framing and source 1/1.
        if (msg.framing_status!=1 or msg.sysid!=1 or msg.compid!=1 or
                msg.header.frame_id!=self.endpoint):
            return
        try:
            parsed=self.codec.decode(msg)
            if parsed is None or parsed.get_type()=='BAD_DATA': return
            if parsed.get_srcSystem()!=1 or parsed.get_srcComponent()!=1: return
            kind=parsed.get_type()
            with self.cv:
                if kind=='HEARTBEAT' and parsed.autopilot==12:
                    if parsed.base_mode & 128:
                        self.armed_observations=getattr(self,'armed_observations',0)+1
                    self.heartbeat=NS(armed=bool(parsed.base_mode & 128),connected=True,
                        sysid=1,compid=1,received=received)
                if kind=='PARAM_VALUE':
                    name=parsed.param_id
                    if isinstance(name,bytes): name=name.decode('ascii')
                    name=name.rstrip('\x00')
                    if len(self.frames)==self.frames.maxlen:
                        self.fault='raw_queue_overflow'
                    self.frames.append(NS(message_id=22,framing_ok=True,sysid=1,compid=1,
                        name=name,received=received,mav_param_type=int(parsed.param_type),
                        value=float(parsed.param_value)))
                self.cv.notify_all()
        except Exception as error:
            self.fault='raw_decode:'+str(error)
    def _status(self,deadline):
        if self.clock()>=deadline: raise TimeoutError('guard_deadline')
        d=json.loads((self.directory/'status.json').read_text())
        if (not 0 <= self.clock()-d['received'] <= .5 or d['fault'] is not None or
                tuple(d['writer'])!=WRITER):
            raise RuntimeError('proxy guard unavailable or conflicted')
        if d['mode']=='inhibit' and d.get('arm_pending') is not False:
            raise RuntimeError('previous ARM outcome unresolved')
        if self.epoch is None: self.epoch=d['epoch']
        if self.epoch!=d['epoch']: raise RuntimeError('proxy restarted')
        if self.fault: raise RuntimeError(self.fault)
        return d
    def set_mode(self,mode,deadline):
        if mode not in ('inhibit','flight'): raise ValueError('invalid policy mode')
        token=uuid.uuid4().hex
        atomic_json(self.directory/'control.json',dict(mode=mode,token=token))
        while self.clock()<deadline:
            d=self._status(deadline)
            if d['token']==token and d['mode']==mode:
                if self.clock()>=deadline: raise TimeoutError('proxy acknowledgment deadline')
                return True
            # Event wait permits callbacks; bounded by the same absolute deadline.
            threading.Event().wait(min(.02,max(0,deadline-self.clock())))
        raise TimeoutError('proxy mode acknowledgment')
    def _request_heartbeat(self,deadline,max_age=1.0):
        # Separate data-only path: _send() would recurse through state().
        # Reserve rate slots at actual publish, including ambiguous failures.
        with locked(self.heartbeat_request_lock,deadline,self.clock):
            status=self._status(deadline)
            if status['mode']!='inhibit': raise RuntimeError('heartbeat request requires inhibition')
            with locked(self.cv,deadline,self.clock):
                hb=self.heartbeat
                if hb is None or hb.armed is not False:
                    raise RuntimeError('heartbeat request requires previous disarmed observation')
                proxy_hb=status.get('heartbeat')
                if proxy_hb is not None and proxy_hb.get('armed') is True:
                    raise RuntimeError('proxy reports armed')
                if (proxy_hb is not None and
                        0<=self.clock()-hb.received<=max_age and
                        0<=self.clock()-proxy_hb['received']<=max_age):
                    return None  # Another waiter already obtained real fresh data.
            now=self.clock()
            last=self.last_heartbeat_request_sent
            if last is not None and now-last<.5: return None
            encoded=self.codec.encode(self.codec.heartbeat_request_message())
            status=self._status(deadline)
            with locked(self.cv,deadline,self.clock):
                if self.heartbeat is None or self.heartbeat.armed is not False:
                    raise RuntimeError('armed before heartbeat request')
            if status['mode']!='inhibit': raise RuntimeError('heartbeat request requires inhibition')
            if (status.get('heartbeat') or {}).get('armed') is True:
                raise RuntimeError('proxy reports armed')
            sent=self.clock()
            if sent>=deadline: raise TimeoutError('heartbeat request deadline')
            self.last_heartbeat_request_sent=sent
            self.publisher.publish(encoded)
            if self.clock()>=deadline: raise TimeoutError('deadline after heartbeat request publish')
            return sent

    def state(self,deadline,max_age=1.0):
        """Wait only for stale disarmed observations, never extend deadline.

        Missing first raw HEARTBEAT remains an immediate readiness refusal.
        Proxy status is revalidated at least every 20 ms while waiting.
        """
        if type(max_age) not in (int,float) or not 0<max_age<=1.0:
            raise ValueError('state freshness window cannot exceed one second')
        with locked(self.cv,deadline,self.clock):
            initial_armed_count=getattr(self,'armed_observations',0)
        while self.clock()<deadline:
            status=self._status(deadline)
            with locked(self.cv,deadline,self.clock):
                count=getattr(self,'armed_observations',0)
                if count!=initial_armed_count:
                    raise RuntimeError('armed observed while awaiting fresh heartbeat')
                hb=self.heartbeat
                if hb is None:
                    return NS(armed=None,connected=False,sysid=None,compid=None,received=None,
                        reason='awaiting_first_heartbeat')
                # Armed never waits for a later disarmed message.
                if hb.armed is True:
                    return hb
                if (hb.armed is not False or hb.connected is not True or
                        hb.sysid!=1 or hb.compid!=1 or
                        type(hb.received) not in (int,float) or not math.isfinite(hb.received) or
                        hb.received>self.clock()):
                    raise RuntimeError('invalid raw heartbeat state')
                proxy_hb=status.get('heartbeat')
                proxy_fresh=False
                if proxy_hb is not None:
                    if proxy_hb.get('armed') is True:
                        raise RuntimeError('proxy reports armed')
                    stamp=proxy_hb.get('received')
                    if (proxy_hb.get('armed') is not False or proxy_hb.get('connected') is not True or
                            proxy_hb.get('sysid')!=1 or proxy_hb.get('compid')!=1 or
                            type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp>self.clock()):
                        raise RuntimeError('invalid proxy heartbeat state')
                    proxy_fresh=0<=self.clock()-stamp<=max_age
                if proxy_fresh and 0<=self.clock()-hb.received<=max_age:
                    return hb
            requested=self._request_heartbeat(deadline,max_age)
            if requested is not None:
                continue
            with locked(self.cv,deadline,self.clock):
                remaining=deadline-self.clock()
                if remaining<=0: break
                self.cv.wait(timeout=min(.02,remaining))
        raise TimeoutError('fresh disarmed heartbeat deadline')
    def drain(self,deadline):
        with locked(self.cv,deadline,self.clock): self.frames.clear()
    def next_frame(self,deadline):
        with locked(self.cv,deadline,self.clock):
            while not self.frames:
                remaining=deadline-self.clock()
                if remaining<=0: raise TimeoutError('raw receive deadline')
                self.cv.wait(timeout=remaining)
            return self.frames.popleft()
    def _send(self,message,deadline,writing=False):
        # An extra conservative 50 ms headroom for SET, never a wider window.
        # The proxy still independently enforces its original 1.0 s condition.
        state=self.state(deadline,max_age=.95 if writing else 1.0)
        if state.armed is not False or state.connected is not True:
            raise RuntimeError('unsafe parameter state')
        d=self._status(deadline)
        if d['mode']!='inhibit': raise RuntimeError('parameter access requires inhibition')
        encoded=self.codec.encode(message)
        sent=self.clock()  # Actual publication boundary, after all waits/encoding.
        if sent>=deadline: raise TimeoutError('send deadline')
        self.publisher.publish(encoded)
        if self.clock()>=deadline: raise TimeoutError('deadline after publish')
        return sent
    def request_read(self,name,sysid,compid,index,deadline):
        if (sysid,compid,index)!=(1,1,-1): raise ValueError('wrong read target')
        return self._send(self.codec.read_message(name),deadline)
    def set_real32(self,name,value,deadline):
        state=self.state(deadline,max_age=.95)
        if state.armed is not False or not 0<=self.clock()-state.received<=1.:
            raise RuntimeError('unsafe write state')
        self.drain(deadline)
        started=self.clock()
        sent=self._send(self.codec.set_message(name,value),deadline,writing=True)
        if (type(sent) not in (int,float) or not math.isfinite(sent) or
                not started<=sent<=self.clock() or self.clock()>=deadline):
            raise RuntimeError('invalid SET publication time')
        while self.clock()<deadline:
            s=self.next_frame(deadline)
            now=self.clock()
            if now>=deadline: raise TimeoutError('SET acknowledgment deadline')
            if (s.name==name and s.mav_param_type==9 and sent<=s.received<=now and
                    math.isclose(s.value,value,abs_tol=1e-6,rel_tol=1e-6)):
                return True
        return False

class PymavlinkCodec:
    def __init__(self,mavutil,convert):
        self.mavutil,self.convert=mavutil,convert
        self.encoder=mavutil.mavlink.MAVLink(None,srcSystem=WRITER[0],srcComponent=WRITER[1])
        self.decoder=mavutil.mavlink.MAVLink(None)
    def decode(self,message):
        return self.decoder.parse_char(self.convert.convert_to_bytes(message))
    def encode(self,message):
        message.pack(self.encoder)
        result=self.convert.convert_to_rosmsg(message)
        self.encoder.seq=(self.encoder.seq+1)%256
        return result
    @staticmethod
    def name_bytes(name):
        data=name.encode('ascii')
        if not 0<len(data)<=16 or b'\0' in data: raise ValueError('invalid param name')
        return data
    def read_message(self,name):
        return self.mavutil.mavlink.MAVLink_param_request_read_message(1,1,self.name_bytes(name),-1)
    def heartbeat_request_message(self):
        # REQUEST_MESSAGE(HEARTBEAT), not SET_MESSAGE_INTERVAL or ARM.
        return self.mavutil.mavlink.MAVLink_command_long_message(
            1,1,512,0,0.,0.,0.,0.,0.,0.,0.)
    def set_message(self,name,value):
        if type(value) is not float or not math.isfinite(value): raise ValueError('REAL32 required')
        return self.mavutil.mavlink.MAVLink_param_set_message(1,1,self.name_bytes(name),value,9)
