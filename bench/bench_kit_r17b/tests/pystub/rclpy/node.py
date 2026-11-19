import os, sys, time
from std_msgs.msg import Bool, Int32
from mavros_msgs.msg import State, StatusText
from sensor_msgs.msg import BatteryState
from aruco_pose.msg import MarkerArray, Marker, _Stamp
from rcl_interfaces.srv import ParameterValue

FAKE_PARAMS = {'BAT1_SOURCE': (2, 0), 'BAT1_N_CELLS': (2, 4), 'BAT1_V_EMPTY': (3, 3.5), 'BAT1_V_CHARGED': (3, 4.05),
               'BAT1_V_DIV': (3, 18.1), 'BAT_LOW_THR': (3, 0.15), 'BAT_CRIT_THR': (3, 0.07), 'BAT_EMERGEN_THR': (3, 0.05),
               'COM_LOW_BAT_ACT': (2, 0)}   # BAT1_A_PER_V и CBRK_SUPPLY_CHK намеренно нет: «not_in_MAVROS_table»


class _Clock:
    def now(self):
        class T:
            pass
        t = T()
        t.nanoseconds = int(time.time() * 1e9)
        return t


class _Pub:
    def __init__(self, node, cls, topic):
        self.node = node; self.cls = cls; self.topic = topic; self.count = 0

    def publish(self, msg):
        self.count += 1
        self.node.published.append((self.topic, getattr(msg, 'data', None)))


class _Future:
    def __init__(self, result):
        self._r = result

    def done(self):
        return True

    def result(self):
        return self._r


class _Resp:
    pass


class _Client:
    def __init__(self, node, cls, name):
        self.node = node; self.cls = cls; self.name = name

    def wait_for_service(self, timeout_sec=1.0):
        return os.environ.get('BB_STUB_SCENARIO', 'ok') != 'nosvc'

    def call_async(self, req):
        r = _Resp()
        r.values = []
        for n in req.names:
            t, v = FAKE_PARAMS.get(n, (0, 0))
            if t == 2:
                r.values.append(ParameterValue(type=2, integer_value=v))
            elif t == 3:
                r.values.append(ParameterValue(type=3, double_value=v))
            else:
                r.values.append(ParameterValue(type=0))
        self.node.service_calls.append((self.name, list(req.names)))
        return _Future(r)


class FakeNode:
    def __init__(self, name):
        self.name = name
        self.subs = []; self.pubs = []; self.timers = []; self.published = []; self.service_calls = []
        self.first = True
        self.scn = os.environ.get('BB_STUB_SCENARIO', 'ok')
        self.t_mark = time.monotonic(); self.t_cam = time.monotonic(); self.t_yuv = time.monotonic(); self.t_used = time.monotonic(); self.t_bat = time.monotonic()
        self.n_used = 0; self.warned = False; self.t0 = time.monotonic()

    def create_subscription(self, cls, topic, cb, qos, raw=False):
        self.subs.append((cls, topic, cb, raw))

    def create_publisher(self, cls, topic, qos):
        p = _Pub(self, cls, topic)
        self.pubs.append(p)
        return p

    def create_client(self, cls, name):
        return _Client(self, cls, name)

    def create_timer(self, period, cb):
        self.timers.append([period, cb, time.monotonic()])

    def get_clock(self):
        return _Clock()

    def get_topic_names_and_types(self):
        return [('/mavros/state', ['mavros_msgs/msg/State']),
                ('/mavros/mavros/pose_cov', ['geometry_msgs/msg/PoseWithCovarianceStamped']),
                ('/mavros/battery', ['sensor_msgs/msg/BatteryState']),
                ('/mavros/statustext/recv', ['mavros_msgs/msg/StatusText']),
                ('/main_camera/image_raw_yuv', ['sensor_msgs/msg/Image']),
                ('/aruco_detect/markers_used', ['std_msgs/msg/Int32']),
                ('/other', ['std_msgs/msg/String'])]

    def get_service_names_and_types(self):
        return [('/mavros/mavros/get_parameters', ['rcl_interfaces/srv/GetParameters']), ('/other/get_parameters', ['rcl_interfaces/srv/GetParameters'])]

    def spin_once(self, timeout_sec=0.1):
        time.sleep(min(timeout_sec, 0.05))
        now = time.monotonic()
        scn = self.scn
        if scn != 'nostate':
            st = {'ok': (True, False, 'MANUAL'), 'armed': (True, True, 'STABILIZED'), 'disconnected': (False, False, 'MANUAL'), 'vib_armed': (True, True, 'STABILIZED')}.get(scn, (True, False, 'MANUAL'))
            if self.first:
                self.first = False
                for cls, topic, cb, raw in self.subs:
                    if cls is State:
                        cb(State(*st))
            for cls, topic, cb, raw in self.subs:
                if cls is MarkerArray and scn in ('ok', 'vib_armed'):
                    while now - self.t_mark >= 0.05:
                        self.t_mark += 0.05
                        ns = time.time_ns() - 50_000_000
                        cb(MarkerArray([Marker(0)], _Stamp(ns // 10 ** 9, ns % 10 ** 9)))
                if cls is Int32 and topic.endswith('markers_used') and scn in ('ok', 'vib_armed'):
                    while now - self.t_used >= 0.05:
                        self.t_used += 0.05
                        self.n_used += 1
                        # первые 1,5 с шлёт 1, потом ~1 с нули, потом снова 1: даёт один пропуск «значение >= 1» больше 0,4 с и 1,0 с
                        age = self.t_used - self.t0
                        cb(Int32(0 if 1.5 <= age < 2.6 else 1))
                if raw and topic.endswith('image_raw') and scn in ('ok', 'vib_armed'):
                    while now - self.t_cam >= 1.0 / 24.0:
                        self.t_cam += 1.0 / 24.0
                        cb(b'x')
                if raw and topic.endswith('image_raw_yuv') and scn in ('ok', 'vib_armed'):
                    while now - self.t_yuv >= 1.0 / 24.0:
                        self.t_yuv += 1.0 / 24.0
                        cb(b'y')
                if cls is BatteryState and scn in ('ok', 'bat_warn'):
                    while now - self.t_bat >= 0.2:
                        self.t_bat += 0.2
                        cb(BatteryState(voltage=16.2, percentage=0.95, current=0.5, present=True, cell_voltage=[4.05, 4.05, 4.05, 4.05]))
                if cls is StatusText and scn == 'bat_warn' and not self.warned and now - self.t0 > 0.3:
                    self.warned = True
                    cb(StatusText(4, 'Low battery'))
        for t in self.timers:
            if now - t[2] >= t[0]:
                t[2] += t[0]
                t[1]()


Node = FakeNode
