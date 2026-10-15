"""Policy hook for the existing loopback fault proxy. No sockets or ROS.
A file handshake supplies fail-closed ARM inhibition and one PARAM source.
"""
import hashlib
import json
import math
import os
import time
from pathlib import Path

WRITER = (245, 190)
MODE_SOURCE = (1, 191)
RC_SOURCE = (255, 190)
CONTROL_SOURCES = {MODE_SOURCE, RC_SOURCE}
OFFBOARD = 6 << 16
NEUTRAL_RC = (1499,1500,1000,1497,1000,1000,1500,1000) + (1500,)*8 + (0,0)
RC_MAP = json.loads(Path(__file__).with_name('rc_expected09.json').read_text())
# Values are pinned in local mavros_msgs/msg/CommandCode.msg.
SAFETY_COMMANDS = {20, 21, 23, 85}  # RTL, LAND, LAND_LOCAL, VTOL_LAND
LAUNCH_COMMANDS = {22, 24, 84, 300}  # TAKEOFF, VTOL_TAKEOFF, MISSION_START
MANUAL_INPUTS = {'MANUAL_CONTROL','RC_CHANNELS_OVERRIDE','HIL_RC_INPUTS_RAW'}
PARAM_TRAFFIC = {'PARAM_SET','PARAM_EXT_SET','PARAM_REQUEST_READ',
                 'PARAM_REQUEST_LIST','PARAM_EXT_REQUEST_READ','PARAM_EXT_REQUEST_LIST'}

def atomic_json(path, doc):
    path=Path(path); tmp=path.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(doc,f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path)

class ProxyProfilePolicy:
    def __init__(self, directory, clock=time.monotonic):
        self.directory=Path(directory); self.clock=clock
        self.last_heartbeat=None
        self.last_fcu_sequence=None
        self.last_rejection=None
        self.fault=None
        self.arm_pending=False
        self.observed_armed=False
        self.arm_pending_reasons=[]
        self.epoch=os.urandom(16).hex()
        # Immutable startup evidence, supplied after independent read-only audit.
        self.rc_contract=None
        try:
            contract=json.loads((self.directory/'rc_contract.json').read_text())
            if (isinstance(contract,dict) and contract.get('parameters')==RC_MAP and
                    contract.get('all_rc_related_parameters_audited') is True and
                    contract.get('independently_verified') is True and
                    isinstance(contract.get('evidence_sha256'),str) and
                    len(contract['evidence_sha256'])==64 and
                    all(c in '0123456789abcdef' for c in contract['evidence_sha256']) and
                    self._rc_evidence_valid(contract)):
                self.rc_contract=contract
        except (OSError,ValueError): pass
    @staticmethod
    def _rc_evidence_valid(contract):
        try:
            data=Path(contract['ready_path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=contract['evidence_sha256']: return False
            samples=json.loads(data)['parameters']
            for name,value in RC_MAP.items():
                sample=samples[name]
                actual=sample['after']
                if type(actual) not in (int,float) or actual!=value: return False
                if sample.get('source',[1,1])!=[1,1]: return False
                if sample.get('wire_type',sample.get('type')) not in (6,9): return False
            return True
        except (OSError,ValueError,KeyError,TypeError): return False

    def mode(self):
        try:
            d=json.loads((self.directory/'control.json').read_text())
            if d.get('mode') in ('inhibit','flight') and type(d.get('token')) is str:
                return d
        except (OSError,ValueError): pass
        return {'mode':'inhibit','token':None}
    def tick(self):
        d=self.mode()
        atomic_json(self.directory/'status.json',dict(mode=d['mode'],token=d['token'],
            received=self.clock(),epoch=self.epoch,fault=self.fault,
            writer=list(WRITER),heartbeat=self.last_heartbeat,arm_pending=self.arm_pending,
            arm_pending_reasons=self.arm_pending_reasons,
            arm_resolution='unknown' if self.arm_pending else 'no_pending_attempt'))
    def _pending(self,reason):
        # A pre-request armed observation cannot resolve a new attempt.
        self.arm_pending=True
        self.observed_armed=False
        if reason not in self.arm_pending_reasons:
            self.arm_pending_reasons.append(reason)

    def _control_target(self,msg,kind):
        source=(msg.get_srcSystem(),msg.get_srcComponent())
        if source not in CONTROL_SOURCES: return False
        if kind in MANUAL_INPUTS and source!=RC_SOURCE: return False
        if kind=='SET_MODE' and source!=MODE_SOURCE: return False
        if getattr(msg,'target_system',None)!=1: return False
        return kind=='SET_MODE' or getattr(msg,'target_component',None)==1

    def _safe_offboard(self,msg,kind):
        if kind=='SET_MODE':
            return type(msg.base_mode) is int and msg.base_mode==1 and getattr(msg,'custom_mode',None)==OFFBOARD
        return (kind=='COMMAND_LONG' and
                (msg.get_srcSystem(),msg.get_srcComponent())==MODE_SOURCE and
                msg.param1==1 and getattr(msg,'param2',None)==6 and
                getattr(msg,'param3',None)==0 and
                all(getattr(msg,'param'+str(i),None)==0 for i in range(4,8)))

    def _inhibit_offboard(self,msg,kind,mode):
        return (mode=='inhibit' and self.fault is None and
                self._safe_offboard(msg,kind) and not self.arm_pending and
                self.last_heartbeat is not None and not self.last_heartbeat['armed'] and
                0<=self.clock()-self.last_heartbeat['received']<=1.)

    def _neutral_rc(self,msg):
        if self.rc_contract is None or msg.get_type()!='RC_CHANNELS_OVERRIDE': return False
        values=tuple(getattr(msg,'chan'+str(i)+'_raw',None) for i in range(1,19))
        if any(type(v) is not int for v in values): return False
        if values==NEUTRAL_RC: return True
        armed_values=list(NEUTRAL_RC);armed_values[2]=1499
        return (values==tuple(armed_values) and self.last_heartbeat is not None and
                self.last_heartbeat['armed'] and
                0<=self.clock()-self.last_heartbeat['received']<=1.)

    def accept(self,msg,inbound):
        self.last_rejection=None
        kind=msg.get_type() if msg is not None else 'UNPARSED'
        if inbound:
            if msg is None or kind in ('UNPARSED','BAD_DATA'):
                self.last_rejection='malformed_inbound'
                return False
            # Other queues may deliver PARAM/ACK/sensors out of sequence.
            # Keep a forward sequence anchor, but only reject stale FCU state.
            if (msg.get_srcSystem(),msg.get_srcComponent())==(1,1):
                sequence=msg.get_seq()
                valid=type(sequence) is int and 0<=sequence<=255
                delta=None if self.last_fcu_sequence is None or not valid else (sequence-self.last_fcu_sequence)%256
                forward=valid and (delta is None or 0<delta<128)
                is_state=(kind=='HEARTBEAT' and msg.autopilot==12)
                if is_state and not forward:
                    self.last_rejection=('invalid_heartbeat_sequence' if not valid
                                         else 'non_forward_heartbeat_sequence')
                    return False
                if forward: self.last_fcu_sequence=sequence
            if (kind=='HEARTBEAT' and (msg.get_srcSystem(),msg.get_srcComponent())==(1,1)
                    and msg.autopilot==12):
                armed=bool(msg.base_mode & 128)
                if armed: self.observed_armed=True
                if not armed and self.observed_armed:
                    self.arm_pending=False; self.observed_armed=False
                    self.arm_pending_reasons=[]
                self.last_heartbeat=dict(armed=armed,received=self.clock(),
                    sysid=1,compid=1,connected=True)
            return True
        if kind in ('UNPARSED','BAD_DATA'):
            self.fault='unparsed_outbound'; return False
        mode=self.mode()['mode']  # One decision uses one mode snapshot.
        if kind in PARAM_TRAFFIC:
            if self.fault is not None:
                return False
            if (msg.get_srcSystem(),msg.get_srcComponent())!=WRITER:
                # MAVROS' passive startup pull is blocked but does not poison lease.
                if kind not in ('PARAM_REQUEST_LIST','PARAM_REQUEST_READ'):
                    self.fault='foreign_parameter_writer'
                return False
            if kind not in ('PARAM_REQUEST_READ','PARAM_SET'):
                self.fault='unsupported_parameter_protocol'; return False
            if (getattr(msg,'target_system',None)!=1 or
                    getattr(msg,'target_component',None)!=1): return False
            if kind=='PARAM_SET' and (mode!='inhibit' or
                    self.arm_pending or self.last_heartbeat is None or self.last_heartbeat['armed'] or
                    not 0 <= self.clock()-self.last_heartbeat['received'] <= 1.):
                self.fault='write_without_disarmed_inhibition'; return False
        command_control=(kind in ('COMMAND_LONG','COMMAND_INT') and
                         msg.command in (SAFETY_COMMANDS | LAUNCH_COMMANDS | {176,400,245,246}))
        if command_control or kind=='SET_MODE' or kind in MANUAL_INPUTS:
            if not self._control_target(msg,kind): return False
        if kind in ('COMMAND_LONG','COMMAND_INT') and msg.command==512:
            if ((msg.get_srcSystem(),msg.get_srcComponent())!=WRITER or
                    getattr(msg,'target_system',None)!=1 or
                    getattr(msg,'target_component',None)!=1): return False
        if kind in ('COMMAND_LONG','COMMAND_INT'):
            # Emergency landing and explicit disarm have priority over faults.
            if msg.command in SAFETY_COMMANDS:
                return True
            if msg.command==400 and msg.param1==0:
                return True
            if msg.command in (245,246):
                self.fault='storage_or_reboot_command'; return False
            if msg.command==400:
                if not math.isfinite(msg.param1) or msg.param1<=.5:
                    self.fault='invalid_arm_disarm_request'; return False
                permitted=mode=='flight' and self.fault is None
                if permitted: self._pending(kind+':400')
                return permitted
            if msg.command==176:
                # Only exact unarmed OFFBOARD is exempt from a new ARM attempt.
                if not math.isfinite(msg.param1) or not 0<=msg.param1<=255 or int(msg.param1)!=msg.param1:
                    self.fault='invalid_base_mode'; return False
                # No mode change is admitted during a parameter transaction.
                if mode!='flight': return self._inhibit_offboard(msg,kind,mode)
                if self.fault is not None: return False
                # Pinned Commander DO_SET_MODE only changes navigation state.
                if not self._safe_offboard(msg,kind): self._pending(kind+':176')
                return True
            if msg.command in LAUNCH_COMMANDS:
                permitted=mode=='flight' and self.fault is None
                if permitted: self._pending(kind+':'+str(msg.command))
                return permitted
        if kind=='SET_MODE':
            if type(msg.base_mode) is not int or not 0<=msg.base_mode<=255:
                self.fault='invalid_base_mode'; return False
            if mode!='flight': return self._inhibit_offboard(msg,kind,mode)
            if self.fault is not None: return False
            if not self._safe_offboard(msg,kind): self._pending('SET_MODE')
            return True
        if kind in MANUAL_INPUTS:
            # Non-neutral or unqualified input is never forwarded, even armed.
            # Inhibit drops it without a pending attempt: no command reached FCU.
            if mode!='flight' or self.fault is not None: return False
            return self._neutral_rc(msg)

        return True
