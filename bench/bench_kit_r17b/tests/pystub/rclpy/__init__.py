import time
from .node import FakeNode

_nodes = []


def init(*a, **k):
    pass


def shutdown(*a, **k):
    pass


def create_node(name):
    n = FakeNode(name)
    _nodes.append(n)
    return n


def spin_once(node, timeout_sec=0.1):
    node.spin_once(timeout_sec)


def spin_until_future_complete(node, fut, timeout_sec=None):
    return None
