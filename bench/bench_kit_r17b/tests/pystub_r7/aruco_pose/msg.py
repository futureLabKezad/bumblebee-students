# pystub_r7/aruco_pose/msg.py - ТОЛЬКО ДЛЯ ТЕСТОВ (поля как в aruco_pose/msg/Marker.msg: id, c1..c4 типа Point2D)
class Point2D:
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y


class Marker:
    def __init__(self, id=0, c1=None, c2=None, c3=None, c4=None):
        self.id = id
        self.c1 = c1 or Point2D()
        self.c2 = c2 or Point2D()
        self.c3 = c3 or Point2D()
        self.c4 = c4 or Point2D()


class MarkerArray:
    def __init__(self, markers=None):
        self.markers = markers or []