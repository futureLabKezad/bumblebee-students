# pystub_r8/rclpy/node.py - ТОЛЬКО ДЛЯ ТЕСТОВ. Поддельный узел: /mavros/state, детектор (/aruco_detect/markers, /aruco_map/pose) и EKF по сценарию BB_R8_SCN.
# Детектор r2j «просыпается» только после сигнала в /aruco_detect/wake и спит через 5 с после последнего; в сценарии rc3 сигнал не слушает (как aruco_detect.py 7eb7bdf3).
# BB_R8_POSE=x,y - поза base_link по меткам (по умолчанию 0,0); BB_R8_RESEED=x,y,z - один раз дописать в BB_TEST_LOG строку vpe_fix RESEEDED после первого wake.
import os, time
from mavros_msgs.msg import State


class _Info:
    def __init__(self, node_name):
        self.node_name = node_name


class _Pub:
    def __init__(self, node, topic):
        self.node, self.topic = node, topic

    def publish(self, msg):
        self.node._log('PUBLISH %s data=%s' % (self.topic, getattr(msg, 'data', '?')))
        if self.topic == '/aruco_detect/wake' and getattr(msg, 'data', False):
            self.node._wake_t = time.monotonic()
            self.node._wakes += 1


class _Timer:
    def __init__(self, period, cb):
        self.period, self.cb, self.next = period, cb, time.monotonic() + period
        self.alive = True


def _mk(i, x0):
    from aruco_pose.msg import Marker, Point2D
    return Marker(id=i, c1=Point2D(x0 + 230.0, 399.0), c2=Point2D(x0 + 3.0, 402.0), c3=Point2D(x0 + 1.0, 109.0), c4=Point2D(x0 + 228.0, 104.0))


class Node:
    def __init__(self, name, log):
        self.name = name
        self._log = log
        self._subs = {}
        self._timers = []
        self._n = 0
        self._wake_t = None
        self._wakes = 0
        self._reseeded = False
        self.scn = os.environ.get('BB_R8_SCN', 'r2j_ok')

    def create_subscription(self, cls, topic, cb, qos, **kw):
        self._log('SUB ' + topic)
        self._subs[topic] = cb
        return object()

    def create_publisher(self, cls, topic, qos=None, **kw):
        self._log('PUB ' + topic)
        return _Pub(self, topic)

    def create_timer(self, period, cb):
        self._log('TIMER %.1f' % period)
        t = _Timer(period, cb)
        self._timers.append(t)
        return t

    def destroy_timer(self, t):
        self._log('DESTROY_TIMER')
        t.alive = False

    def create_client(self, *a, **kw):
        self._log('CLIENT')
        return object()

    def destroy_node(self):
        self._log('DESTROY')

    def get_publishers_info_by_topic(self, topic):
        return [_Info('aruco_detect')] if topic == '/aruco_detect/markers' else []

    def get_subscriptions_info_by_topic(self, topic):
        if topic != '/main_camera/image_raw':
            return []
        out = [_Info('optical_flow')]
        if self._awake():
            out.append(_Info('aruco_detect'))
        return out

    def _awake(self):
        return self.scn != 'rc3' and self._wake_t is not None and time.monotonic() - self._wake_t < 5.0

    def _spin(self, timeout):
        time.sleep(min(timeout, 0.05))
        self._n += 1
        now = time.monotonic()
        for t in self._timers:
            if t.alive and now >= t.next:
                t.next += t.period
                t.cb()
        s = self.scn
        cb = self._subs.get('/mavros/state')
        if cb and s != 'nostate':
            armed = (s == 'armed') or (s == 'armed_during' and self._wakes >= 2)
            cb(State(connected=(s != 'noconn'), armed=armed, mode='POSCTL'))
        ecb = self._subs.get('/mavros/local_position/pose')
        if ecb:
            from geometry_msgs.msg import PoseStamped
            ecb(PoseStamped(0.01, 0.0, -0.01))
        if not self._awake():
            return
        if os.environ.get('BB_R8_RESEED') and not self._reseeded and os.environ.get('BB_TEST_LOG'):
            self._reseeded = True
            with open(os.environ['BB_TEST_LOG'], 'a') as f:
                f.write('[vpe_fix.py-7] [WARN] [1794000001.100] [vpe_fix]: vpe_fix: gate RESEEDED (xy-jump) age=1.20s new_xyz=(%s)\n' % os.environ['BB_R8_RESEED'])
        mcb = self._subs.get('/aruco_detect/markers')
        if mcb:
            arr = [_mk(0, 236.0)]
            if s == 'false5' and self._n % 4 == 0:
                arr = [_mk(5, 236.0)]
            if s == 'false38' and self._n % 4 == 0:
                arr = [_mk(38, 236.0)]
            if self._n % 7 == 0:
                arr = []
            from aruco_pose.msg import MarkerArray
            mcb(MarkerArray(markers=arr))
        pcb = self._subs.get('/aruco_map/pose')
        if pcb and self._n % 3 == 0:
            from geometry_msgs.msg import PoseWithCovarianceStamped
            x, y = [float(v) for v in os.environ.get('BB_R8_POSE', '0,0').split(',')]
            pcb(PoseWithCovarianceStamped(x, y, -0.22))
