# pystub_r7/rclpy/node.py - ТОЛЬКО ДЛЯ ТЕСТОВ. Поддельный узел: отдаёт /mavros/state и /aruco_detect/markers по сценарию BB_R7_SCN.
import os, time
from mavros_msgs.msg import State


class _Info:
    def __init__(self, node_name):
        self.node_name = node_name


def _mk(i, x0):
    from aruco_pose.msg import Marker, Point2D
    return Marker(id=i, c1=Point2D(x0 + 230.0, 399.0), c2=Point2D(x0 + 3.0, 402.0), c3=Point2D(x0 + 1.0, 109.0), c4=Point2D(x0 + 228.0, 104.0))


class Node:
    def __init__(self, name, log):
        self.name = name
        self._log = log
        self._subs = {}
        self._n = 0
        self.scn = os.environ.get('BB_R7_SCN', 'asleep')

    def create_subscription(self, cls, topic, cb, qos, **kw):
        self._log('SUB ' + topic)
        self._subs[topic] = cb
        return object()

    def create_publisher(self, cls, topic, qos=None, **kw):
        self._log('PUB ' + topic)
        return object()

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
        if self.scn.startswith('awake'):
            out.append(_Info('aruco_detect'))
        return out

    def _spin(self, timeout):
        time.sleep(min(timeout, 0.05))
        self._n += 1
        s = self.scn
        cb = self._subs.get('/mavros/state')
        if cb and s != 'nostate':
            armed = (s == 'armed') or (s == 'armed_during' and self._n > 20)
            cb(State(connected=(s != 'noconn'), armed=armed, mode='POSCTL'))
        mcb = self._subs.get('/aruco_detect/markers')
        if mcb and s in ('awake_ok', 'awake_false', 'armed_during'):
            arr = [_mk(0, 236.0)]
            if s == 'awake_false' and self._n % 4 == 0:
                arr = [_mk(38, 236.0)]
            if self._n % 7 == 0:
                arr = []
            from aruco_pose.msg import MarkerArray
            mcb(MarkerArray(markers=arr))