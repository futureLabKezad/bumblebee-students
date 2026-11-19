"""Minimal ROS stand-ins so the REAL vpe_fix.VpeFix class can be imported and driven offline (no ROS, no DDS).

Based on p1design/fc_continuity_4p5/tests/rosstub.py, extended for the final design:
  - FakeClock: ROS time = sim timeline + ros_offset_ns (an NTP step changes the offset); ros_time_is_active
    mirrors use_sim_time; a clock that has not started (no /clock) reports 0 via `stopped`.
  - State messages carry a real header stamp (set by the caller).
Timers are kept in creation order; the simulator fires timers before subscriptions at equal time and, among timers,
in creation order (rclpy executor order).
"""
import sys
import types
from types import SimpleNamespace


class Duration:
    def __init__(self, nanoseconds):
        self.nanoseconds = int(nanoseconds)


class Time:
    def __init__(self, nanoseconds=0, clock_type=None, seconds=None):
        if seconds is not None:
            nanoseconds = int(seconds * 1e9)
        self.nanoseconds = int(nanoseconds)
        self.clock_type = clock_type

    def __sub__(self, other):
        return Duration(self.nanoseconds - other.nanoseconds)

    def to_msg(self):
        return SimpleNamespace(sec=self.nanoseconds // 1_000_000_000,
                               nanosec=self.nanoseconds % 1_000_000_000)


class FakeClock:
    def __init__(self):
        self.t_ns = 0                 # simulation timeline
        self.ros_offset_ns = 0        # ROS time - timeline (NTP step on the drone, /clock start in SITL)
        self.ros_time_is_active = True
        self.stopped = False          # True: ROS time reads 0 (use_sim_time before the first /clock)

    def ros_ns(self):
        return 0 if self.stopped else self.t_ns + self.ros_offset_ns

    def now(self):
        return Time(self.ros_ns(), clock_type='ROS_TIME')


class Logger:
    def __init__(self, sink, clock):
        self.sink, self.clock = sink, clock

    def _log(self, level, msg):
        self.sink.append((self.clock.t_ns, level, msg))

    def info(self, msg):
        self._log('INFO', msg)

    def warn(self, msg):
        self._log('WARN', msg)

    warning = warn

    def error(self, msg):
        self._log('ERROR', msg)

    def debug(self, msg):
        self._log('DEBUG', msg)


class FakeTimer:
    def __init__(self, node, period, cb):
        self.period = float(period)
        self.cb = cb
        self.next_due_ns = node._clock.t_ns + int(round(self.period * 1e9))
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakePublisher:
    def __init__(self, node, topic):
        self.node, self.topic, self.sent = node, topic, []

    def publish(self, msg):
        self.sent.append((self.node._clock.t_ns, msg))


class FakeClient:
    def wait_for_service(self, timeout_sec=None):
        return False

    def call_async(self, req):
        raise RuntimeError('no MAVROS in offline tests')


class Node:
    CLOCK = None   # the simulator installs its clock here before constructing the node

    def __init__(self, name, *a, **k):
        self._clock = Node.CLOCK or FakeClock()
        self._name = name
        self.logs = []
        self._logger = Logger(self.logs, self._clock)
        self.timers = []
        self.subs = {}

    def get_clock(self):
        return self._clock

    def get_logger(self):
        return self._logger

    def create_publisher(self, typ, topic, qos):
        return FakePublisher(self, topic)

    def create_subscription(self, typ, topic, cb, qos, callback_group=None):
        self.subs[topic] = cb
        return SimpleNamespace(topic=topic)

    def create_timer(self, period, cb, callback_group=None):
        t = FakeTimer(self, period, cb)
        self.timers.append(t)
        return t

    def create_client(self, typ, name, callback_group=None):
        return FakeClient()

    def create_service(self, typ, name, cb, callback_group=None):
        return SimpleNamespace(name=name)

    def destroy_node(self):
        pass


class _Msg:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _header():
    return _Msg(stamp=SimpleNamespace(sec=0, nanosec=0), frame_id='')


class PoseWithCovarianceStamped(_Msg):
    def __init__(self):
        super().__init__(header=_header(),
                         pose=_Msg(pose=_Msg(position=_Msg(x=0.0, y=0.0, z=0.0),
                                             orientation=_Msg(x=0.0, y=0.0, z=0.0, w=1.0)),
                                   covariance=[0.0] * 36))


class State(_Msg):
    def __init__(self, connected=False, armed=False, mode='', stamp_ns=0):
        super().__init__(header=_header(), connected=connected, armed=armed, guided=False,
                         manual_input=False, mode=mode, system_status=0)
        sec, nsec = divmod(max(int(stamp_ns), 0), 1_000_000_000)
        self.header.stamp = SimpleNamespace(sec=sec, nanosec=nsec)


class _Simple(_Msg):
    def __init__(self, data=0):
        super().__init__(data=data)


class _SrvType:
    class Request(_Msg):
        pass

    class Response(_Msg):
        pass


def install():
    """Register the stand-in modules in sys.modules (idempotent)."""
    def mod(name, **attrs):
        m = sys.modules.get(name) or types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m
    rclpy = mod('rclpy', init=lambda *a, **k: None, shutdown=lambda *a, **k: None)
    rclpy.node = mod('rclpy.node', Node=Node)
    rclpy.callback_groups = mod('rclpy.callback_groups',
                                MutuallyExclusiveCallbackGroup=lambda: object(),
                                ReentrantCallbackGroup=lambda: object())
    rclpy.executors = mod('rclpy.executors', MultiThreadedExecutor=object)
    rclpy.qos = mod('rclpy.qos', QoSProfile=lambda **k: SimpleNamespace(**k),
                    ReliabilityPolicy=SimpleNamespace(RELIABLE='RELIABLE'),
                    DurabilityPolicy=SimpleNamespace(TRANSIENT_LOCAL='TRANSIENT_LOCAL'))
    mod('geometry_msgs')
    mod('geometry_msgs.msg', PoseWithCovarianceStamped=PoseWithCovarianceStamped)
    mod('mavros_msgs')
    mod('mavros_msgs.msg', State=State)
    mod('mavros_msgs.srv', ParamSetV2=_SrvType, ParamPull=_SrvType)
    mod('rcl_interfaces')
    mod('rcl_interfaces.msg', ParameterValue=_Msg,
        ParameterType=SimpleNamespace(PARAMETER_INTEGER=2, PARAMETER_DOUBLE=3),
        ParameterEvent=_Msg)
    mod('aruco_pose')
    mod('aruco_pose.msg', MarkerArray=_Msg)
    mod('std_msgs')
    mod('std_msgs.msg', Int32=_Simple, Bool=_Simple)
    mod('std_srvs')
    mod('std_srvs.srv', Trigger=_SrvType)
    mod('bumblebee')
    mod('bumblebee.srv', SetParam=_SrvType)
