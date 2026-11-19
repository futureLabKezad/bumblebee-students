"""Shared bench for the round-2 H2 tests (copied from round 1 tests_h2/test_h2_unknown_outcome.py, Bench unchanged
except: modules are loaded by the caller, a write log with the reason of each call, and an in-air write count).

The REAL VpeFix class (stubbed ROS from tests_existing/offline_suite/rosstub.py, never spun). Only the lowest MAVROS
call, _param_set_once, is replaced by a fake MAVROS + PX4 model; _param_set_with_retry, _handle_set_param,
_on_parameter_event, state_callback, the revert paths and the TTL path are the file's own code.
"""
import contextlib
import importlib.util
import io
import os
import struct
import sys
import threading
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tests_existing', 'offline_suite'))
import rosstub  # noqa: E402
rosstub.install()
from rosstub import _Msg  # noqa: E402

NS = 1_000_000_000
T0 = 1793344392.0          # session 1, T5a step 2 (epoch s of the drone log)
NAME = 'MPC_TKO_SPEED'
NOT_SENT = 'service /mavros/mavros/set not available'
TIMEOUT = 'future timeout after 6.0s'
BEHAVIOURS = ('ok', 'ok_noevent', 'timeout_applied', 'timeout_event', 'timeout', 'crash_applied', 'crash',
              'mavros_false', 'not_sent')


def f32(v):
    return struct.unpack('f', struct.pack('f', float(v)))[0]


ORIG = f32(0.8)
REQ = 0.3
N_PARAMS = 1107


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FastEvent:
    """threading.Event for vpe_fix under the bench: wait() never sleeps (the 0.3 s pause between the two
    ParamSetV2 attempts; the fake MAVROS answers at once). Round 1 slept for real; the fake clock never moved."""
    def __init__(self):
        self._flag = False

    def set(self):
        self._flag = True

    def is_set(self):
        return self._flag

    def wait(self, timeout=None):
        return self._flag


_THREADING = SimpleNamespace(Lock=threading.Lock, Event=_FastEvent)


class Bench:
    """A VpeFix node, a PX4 parameter table (the truth) and a fake MAVROS.

    plan: one behaviour per ParamSetV2 attempt (the next attempt takes the next one; empty -> 'ok' while MAVROS is
    alive, else 'not_sent'):
      ok               PX4 applies, MAVROS publishes the changed event, (True, 'ok')
      ok_noevent       PX4 applies, the changed event is lost, (True, 'ok')
      timeout_applied  PX4 applies, the event is lost, (False, future timeout)
      timeout_event    PX4 applies, MAVROS publishes the event during the call, the answer is lost (future timeout)
      timeout          PX4 unchanged, (False, future timeout)
      crash_applied    PX4 applies, MAVROS dies before the event, (False, future timeout)
      crash            MAVROS dies before sending, PX4 unchanged, (False, future timeout)
      mavros_false     PX4 unchanged, (False, 'MAVROS returned success=False')
      not_sent         (False, service not available): no request
    """

    def __init__(self, mod, t0=T0):
        self.mod = mod
        clock = rosstub.FakeClock()
        clock.t_ns = int(t0 * NS)
        clock.ros_time_is_active = False      # drone: steady clock for state ages, system time for stamps
        self.clock = clock
        rosstub.Node.CLOCK = clock
        try:
            self.node = mod.VpeFix()
        finally:
            rosstub.Node.CLOCK = None
        self.node._param_set_once = self._param_set_once
        mod.threading = _THREADING      # test speed only: the 0.3 s pause between attempts does not sleep
        self.px4 = {'P%04d' % i: float(i) for i in range(N_PARAMS - 1)}
        self.px4[NAME] = ORIG
        self.alive = True
        self.plan = []
        self.writes = []          # (t, armed at the call, name, value, behaviour)
        self.extra_log = []       # (t_ns, raw line) of other processes, for the replay log

    # ------------------------------------------------------------ time, MAVROS, PX4
    def step(self, s):
        self.clock.t_ns += int(s * NS)

    def _param_set_once(self, name, value, ptype, timeout=6.0):
        b = self.plan.pop(0) if self.plan else ('ok' if self.alive else 'not_sent')
        self.writes.append((self.clock.t_ns / NS, self.node.armed, name, value, b))
        if b == 'not_sent':
            return False, NOT_SENT
        if b in ('ok', 'ok_noevent', 'timeout_applied', 'timeout_event', 'crash_applied'):
            self.px4[name] = f32(value)
        if b == 'ok_noevent':
            return True, 'ok'
        if b == 'timeout_event':              # the PX4 value reached the cache, the service answer was lost
            self.event([name], changed=True)
        if b in ('crash', 'crash_applied'):
            self.alive = False
            self.extra_log.append((self.clock.t_ns, "[mavros_node-1] terminate called after throwing an instance of "
                                                    "'std::future_error'"))
            self.extra_log.append((self.clock.t_ns, '[mavros_node-1]   what():  std::future_error: Promise already '
                                                    'satisfied'))
        if b == 'ok':
            self.event([name], changed=True)
            return True, 'ok'
        self.step(timeout)
        if b == 'mavros_false':
            return False, 'MAVROS returned success=False'
        return False, TIMEOUT

    def event(self, names, changed=False, values=None):
        ps = [_Msg(name=n, value=_Msg(type=3, integer_value=0,
                                       double_value=(values or self.px4)[n])) for n in names]
        msg = _Msg(node='/mavros/mavros', new_parameters=[] if changed else ps,
                   changed_parameters=ps if changed else [], deleted_parameters=[])
        self.node._on_parameter_event(msg)

    def pull(self, batch=50):
        """a (re)started MAVROS reads every PX4 parameter: new_parameters events in batches"""
        names = sorted(self.px4)
        for i in range(0, len(names), batch):
            self.event(names[i:i + batch])
            self.step(0.05)

    def respawn(self):
        self.state(False, False, '')          # MAVROS sys_status placeholder at its start
        self.step(0.7)
        self.alive = True
        self.state(True, self.node.armed, 'CMODE(458752)')
        self.pull()

    # ------------------------------------------------------------ vpe_fix inputs
    def state(self, connected, armed, mode):
        ns = self.clock.ros_ns() - 2_000_000
        self.node.state_callback(rosstub.State(connected=connected, armed=armed, mode=mode, stamp_ns=ns))

    def set(self, value, name=NAME, ttl=0.0, persistent=False, ptype=1):
        req = _Msg(param_id=name, value=value, ptype=ptype, ttl_sec=ttl, persistent=persistent)
        return self.node._handle_set_param(req, _Msg())

    def revert_all(self):
        return self.node._handle_revert_all(None, _Msg())

    def arm(self, mode='STABILIZED'):
        self.state(True, True, mode)
        self.step(1.0)

    def disarm(self, mode='STABILIZED'):
        self.state(True, False, mode)
        self.step(1.0)

    def arm_disarm(self, mode='STABILIZED'):
        self.arm(mode)
        self.disarm(mode)

    def fire_ttl(self):
        timers = [t for t in self.node.timers if getattr(t.cb, '__name__', '') == '_fire' and not t.cancelled]
        for t in timers:
            t.cb()
        return len(timers)

    # ------------------------------------------------------------ checks
    def lines(self, text=''):
        return [m for _, _, m in self.node.logs if text in m]

    def writes_while_armed(self):
        return [w for w in self.writes if w[1]]

    def entry(self, name=NAME):
        return self.node._overrides.get(name)

    def drone_log(self, path):
        rows = [(t, '[vpe_fix.py-20] [%s %.9f] [vpe_publisher]: %s' % (lvl, t / NS, m))
                for t, lvl, m in self.node.logs] + list(self.extra_log)
        rows.sort(key=lambda r: r[0])
        with open(path, 'w') as f:
            for _, r in rows:
                f.write(r + '\n')
        return path


def run_eval(mod, path):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = mod.cmd_pairs(path)
    return rc, buf.getvalue()


def boot(mod):
    b = Bench(mod)
    b.pull()                                   # cache HOT through the real event path
    assert b.node._cache_hot
    b.state(True, False, 'STABILIZED')
    b.step(1.0)
    return b
