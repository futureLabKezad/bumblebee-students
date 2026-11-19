class _Stamp:
    def __init__(self, sec=0, nanosec=0):
        self.sec = sec
        self.nanosec = nanosec
class _Header:
    def __init__(self, stamp=None):
        self.stamp = stamp or _Stamp()
class Marker:
    def __init__(self, id=0):
        self.id = id
class MarkerArray:
    def __init__(self, markers=None, stamp=None):
        self.header = _Header(stamp)
        self.markers = markers or []