class QoSReliabilityPolicy:
    RELIABLE = 1
    BEST_EFFORT = 2
class QoSHistoryPolicy:
    KEEP_LAST = 1
class QoSProfile:
    def __init__(self, depth=10, reliability=None, history=None):
        self.depth = depth
        self.reliability = reliability
        self.history = history