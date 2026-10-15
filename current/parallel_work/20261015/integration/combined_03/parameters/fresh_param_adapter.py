"""Raw frame adapter for an EXISTING MAVROS router bridge, no socket ownership.

Injected bridge must flush/drain old frames before request, serialize PARAM
traffic and enforce its deadline. PARAM has no nonce; see INTERFACE.md.
"""
from dataclasses import dataclass
import math
import threading
import time
from deadline_lock import locked


@dataclass(frozen=True)
class WireSample:
    name: str
    value: float
    mav_param_type: int
    sysid: int
    compid: int
    received: float


class FreshParamAdapter:
    def __init__(self, bridge, clock=time.monotonic):
        self.bridge, self.clock = bridge, clock
        self.lock = threading.RLock()

    def state(self, deadline):
        return self.bridge.state(deadline)

    def write(self, name, value, deadline):
        with locked(self.lock, deadline, self.clock):
            result=self.bridge.set_real32(name, value, deadline)
            if self.clock()>=deadline: raise TimeoutError('write deadline')
            return result

    def read_fresh(self, name, deadline):
        with locked(self.lock, deadline, self.clock):
            if self.clock() >= deadline:
                raise TimeoutError('deadline before read')
            # A bridge hook on the existing router sends PARAM_REQUEST_READ
            # target 1/1, param_index=-1, param_id=name (all 16 bytes encoded).
            self.bridge.drain(deadline)
            started = self.clock()
            sent = self.bridge.request_read(name, 1, 1, -1, deadline)
            if (type(sent) not in (int,float) or not math.isfinite(sent) or
                    not started<=sent<=self.clock() or self.clock()>=deadline):
                raise RuntimeError('invalid READ publication time')
            while self.clock() < deadline:
                frame = self.bridge.next_frame(deadline)
                if self.clock()>=deadline: raise TimeoutError('read deadline')
                if (frame.message_id != 22 or not frame.framing_ok or
                    frame.sysid != 1 or frame.compid != 1 or frame.name != name or
                    not sent <= frame.received <= self.clock()):
                    continue
                if (frame.mav_param_type != 9 or type(frame.value) is not float or
                        not math.isfinite(frame.value)):
                    raise ValueError('invalid PARAM_VALUE type/value')
                return WireSample(name, frame.value, 9, 1, 1, frame.received)
            raise TimeoutError('PARAM_VALUE deadline')
