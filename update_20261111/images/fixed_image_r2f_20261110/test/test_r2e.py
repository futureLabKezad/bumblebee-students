"""r2e tests without ROS: review fixes in drone.py (lease survives publish errors) and flight_marker.py (a missed
waypoint ends the mission). The simple_offboard side is test/test_script_lease.cpp (plain g++).
Run: python3 -m unittest discover -s test -p 'test_r2e.py'   (from fixed_image_r2e_20261109)
"""
import ast
import importlib.util
import os
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, 'src', 'bumblebee', 'examples')


def load():
    spec = importlib.util.spec_from_file_location('drone_r2e_under_test', os.path.join(EX, 'drone.py'))
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    d._initialized = True
    return d


class FlakyPub:
    def __init__(self, fails):
        self.fails = fails
        self.calls = 0
        self.ok = 0
        self.lock = threading.Lock()

    def publish(self, msg):
        with self.lock:
            self.calls += 1
            if self.calls <= self.fails:
                raise RuntimeError('publisher\'s context is invalid')
            self.ok += 1


class LeasePublishErrorTest(unittest.TestCase):

    def test_lease_survives_publish_errors(self):
        d = load()
        d.LEASE_PERIOD_S = 0.03
        d.Bool = type('Bool', (), {'data': False})
        pub = FlakyPub(fails=3)
        d._node = types.SimpleNamespace(create_publisher=lambda typ, topic, depth: pub)
        try:
            d._start_script_lease()
            time.sleep(0.4)
            self.assertTrue(d._lease_thread.is_alive())
            self.assertGreaterEqual(pub.ok, 4)          # kept publishing after the 3 errors
        finally:
            d._stop_script_lease()
        self.assertFalse(d._lease_thread.is_alive())


class MarkerExampleTest(unittest.TestCase):

    def test_every_fly_to_result_is_checked(self):
        path = os.path.join(EX, 'flight', 'flight_marker.py')
        with open(path, encoding='utf-8') as f:
            src = f.read()
        tree = ast.parse(src)
        checked = 0
        calls = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'fly_to':
                calls += 1
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp) \
                    and isinstance(node.test.op, ast.Not) and isinstance(node.test.operand, ast.Call) \
                    and getattr(node.test.operand.func, 'attr', None) == 'fly_to':
                self.assertIsInstance(node.body[0], ast.Raise)
                self.assertEqual(node.body[0].exc.func.id, 'SystemExit')
                checked += 1
        self.assertEqual(calls, 3)
        self.assertEqual(checked, 3)
        # the raise happens inside the try whose finally lands
        self.assertIn('finally:\n    drone.safe_land(x=0, y=0, precision_speed=0.1)', src)


if __name__ == '__main__':
    unittest.main()
