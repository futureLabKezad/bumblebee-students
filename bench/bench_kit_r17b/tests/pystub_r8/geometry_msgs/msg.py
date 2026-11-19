# pystub_r8/geometry_msgs/msg.py - ТОЛЬКО ДЛЯ ТЕСТОВ: поля, которые читает pi/r8_marker_wake.sh
class _V:
    def __init__(self, x=0.0, y=0.0, z=0.0, w=1.0):
        self.x, self.y, self.z, self.w = x, y, z, w


class _P:
    def __init__(self, x, y, z):
        self.position = _V(x, y, z)
        self.orientation = _V(0.0, 0.0, 0.7071068, 0.7071068)


class _PC:
    def __init__(self, x, y, z):
        self.pose = _P(x, y, z)


class PoseWithCovarianceStamped:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.pose = _PC(x, y, z)


class PoseStamped:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.pose = _P(x, y, z)
