# pystub_r7/rclpy/qos.py - ТОЛЬКО ДЛЯ ТЕСТОВ
class QoSReliabilityPolicy:
    RELIABLE = 1
    BEST_EFFORT = 2


class QoSProfile:
    def __init__(self, depth=10, reliability=None, **kw):
        self.depth = depth
        self.reliability = reliability