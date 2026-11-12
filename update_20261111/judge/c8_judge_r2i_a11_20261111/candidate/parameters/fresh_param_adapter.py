"""Raw frame adapter for an EXISTING MAVROS router bridge, no socket ownership.

Injected bridge must flush/drain old frames before request, serialize PARAM
traffic and enforce its deadline. PARAM has no nonce; see INTERFACE.md.

restore_fast_01: resend=True (ProfileTransaction's reads and writes: prepare, apply, allow-flight and restore; the default
path used by the supervisor's independent scans is unchanged) sends the same request again when no reply arrives within
RESEND_WINDOWS_S[k] of send k; the last send waits until the absolute deadline, so a lost reply never gets less time than
before. A reply received after the FIRST send of the call is accepted and returned at once. PARAM_VALUE has no nonce: after
a call that needed an extra send, the NEXT resend-mode call first drops all frames until STRAY_WAIT_S after that last send
(bounded by its own deadline), so a late duplicate is never taken as its reply. A duplicate later than that is the residual
risk; the restore's two final full scans come after it. The number of sends of a failed call is attached to the exception
(attribute 'sends').
"""
from dataclasses import dataclass
import math
import threading
import time
from deadline_lock import locked

RESEND_WINDOWS_S = (0.5, 1.0)
STRAY_WAIT_S = 2.0


@dataclass(frozen=True)
class WireSample:
    name: str
    value: float
    mav_param_type: int
    sysid: int
    compid: int
    received: float
    sends: int = 1


class FreshParamAdapter:
    def __init__(self, bridge, clock=time.monotonic):
        self.bridge, self.clock = bridge, clock
        self.lock = threading.RLock()
        self.last_write_sends = 1
        self.strays_until = float('-inf')   # late replies to our extra sends may arrive until then

    @property
    def supports_resend(self):
        return hasattr(self.bridge, 'set_real32_resend')

    def state(self, deadline):
        return self.bridge.state(deadline)

    def write(self, name, value, deadline, resend=False):
        with locked(self.lock, deadline, self.clock):
            if resend:
                self._drop_strays(deadline)
                self.last_write_sends = 0
                try:
                    result, self.last_write_sends, last_sent = self.bridge.set_real32_resend(
                        name, value, deadline, RESEND_WINDOWS_S)
                except BaseException as error:
                    self.last_write_sends = getattr(error, 'sends', None)
                    if (self.last_write_sends or 0) > 1:
                        self.strays_until = max(self.strays_until, self.clock()+STRAY_WAIT_S)
                    raise
                if self.last_write_sends > 1:
                    self.strays_until = max(self.strays_until, last_sent+STRAY_WAIT_S)
            else:
                result=self.bridge.set_real32(name, value, deadline)
            if self.clock()>=deadline: raise TimeoutError('write deadline')
            return result

    def read_fresh(self, name, deadline, resend=False):
        if resend:
            return self._read_resend(name, deadline)
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

    def _drop_strays(self, deadline):
        """Before a request: drop frames until strays_until (late replies to earlier extra sends), never past deadline."""
        until = min(deadline, self.strays_until)
        while self.clock() < until:
            try:
                self.bridge.next_frame(until)
            except TimeoutError:
                break
        if self.clock() >= deadline:
            raise TimeoutError('deadline while dropping late duplicates')

    def _read_resend(self, name, deadline):
        with locked(self.lock, deadline, self.clock):
            if self.clock() >= deadline:
                raise TimeoutError('deadline before read')
            self._drop_strays(deadline)
            self.bridge.drain(deadline)
            first = None
            sends = 0
            try:
                for k in range(len(RESEND_WINDOWS_S)+1):
                    started = self.clock()
                    sent = self.bridge.request_read(name, 1, 1, -1, deadline)
                    sends += 1
                    if (type(sent) not in (int,float) or not math.isfinite(sent) or
                            not started<=sent<=self.clock() or self.clock()>=deadline):
                        raise RuntimeError('invalid READ publication time')
                    first = sent if first is None else first
                    final = k == len(RESEND_WINDOWS_S)
                    until = deadline if final else min(deadline, sent+RESEND_WINDOWS_S[k])
                    while self.clock() < until:
                        try:
                            frame = self.bridge.next_frame(until)
                        except TimeoutError:
                            if final: raise
                            break
                        if self.clock()>=deadline: raise TimeoutError('read deadline')
                        if (frame.message_id != 22 or not frame.framing_ok or
                            frame.sysid != 1 or frame.compid != 1 or frame.name != name or
                            not first <= frame.received <= self.clock()):
                            continue
                        if (frame.mav_param_type != 9 or type(frame.value) is not float or
                                not math.isfinite(frame.value)):
                            raise ValueError('invalid PARAM_VALUE type/value')
                        if sends > 1:
                            self.strays_until = max(self.strays_until, sent+STRAY_WAIT_S)
                        return WireSample(name, frame.value, 9, 1, 1, frame.received, sends)
                    if self.clock() >= deadline:
                        raise TimeoutError('PARAM_VALUE deadline')
                raise TimeoutError('PARAM_VALUE deadline')
            except BaseException as error:
                if sends > 1:
                    self.strays_until = max(self.strays_until, self.clock()+STRAY_WAIT_S)
                try:
                    error.sends = sends
                except AttributeError:
                    pass
                raise
