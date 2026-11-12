"""r2d tests without ROS: F7 (arrival with settle_speed, the marker examples) and T25 (drone.py script lease).

The simple_offboard side of T25 is test/test_script_lease.cpp (plain g++).
Run: python3 -m unittest discover -s test -p 'test_r2d.py'   (from fixed_image_r2d_20261109)
"""
import ast
import importlib.util
import math
import os
import threading
import time as _time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, 'src', 'bumblebee', 'examples')
DRONE_PY = os.path.join(EX, 'drone.py')
NAN = float('nan')


def load():
    spec = importlib.util.spec_from_file_location('drone_r2d_under_test', DRONE_PY)
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    d._initialized = True
    d._fcu_mode_state = lambda wait=0.0: (True, True, 'OFFBOARD')
    return d


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Log:
    def __init__(self):
        self.lines = []

    def warn(self, m):
        self.lines.append(m)

    error = info = warning = warn


def rig(d, samples, settle_speed, tolerance=0.12, timeout=60.0):
    """navigate_wait over scripted (dist, vx, vy) samples; returns (result, samples used)."""
    clock = FakeClock()
    log = Log()
    d.time = clock
    d.rclpy = types.SimpleNamespace(ok=lambda: True)
    d.should_land = False
    d._aruco_markers_pos_time = None
    d._telem_staleness = lambda frame: 1.0          # > 0.2: jump guards skipped, < 5: not stale
    d._node = types.SimpleNamespace(get_logger=lambda: log)
    d.navigate = lambda **kw: types.SimpleNamespace(success=True, message='')
    used = [0]

    def sample():
        i = min(used[0], len(samples) - 1)
        return samples[i]

    def telem_target(frame_id):
        dist = sample()[0]
        return types.SimpleNamespace(x=dist, y=0.0, z=0.0)

    def telem_map(frame_id='map'):
        s = sample()
        used[0] += 1
        return types.SimpleNamespace(x=0.0, y=0.0, z=1.0, vx=s[1], vy=s[2], armed=True)

    d.get_telemetry = telem_target
    d._get_telemetry_robust = telem_map
    r = d.navigate_wait(x=0.0, y=0.7, z=1.0, frame_id='map', tolerance=tolerance,
                        settle_speed=settle_speed, timeout=timeout, phase='T')
    return r, used[0]


class F7ArrivalTest(unittest.TestCase):

    def setUp(self):
        self.d = load()

    def test_default_is_old_arrival(self):
        r, n = rig(self.d, [(0.30, 0.1, 0), (0.24, 0.1, 0), (0.20, 0.1, 0)], None, tolerance=0.25)
        self.assertTrue(r)
        self.assertEqual(n, 2)                      # first sample under 0.25, moving or not

    def test_two_settled_samples_needed(self):
        r, n = rig(self.d, [(0.20, 0.10, 0), (0.11, 0.08, 0), (0.10, 0.04, 0), (0.09, 0.03, 0)], 0.05)
        self.assertTrue(r)
        self.assertEqual(n, 4)

    def test_fast_sample_resets(self):
        r, n = rig(self.d, [(0.10, 0.04, 0), (0.10, 0.0, 0.07), (0.10, 0.04, 0), (0.10, 0.03, 0.01)], 0.05)
        self.assertTrue(r)
        self.assertEqual(n, 4)

    def test_leaving_tolerance_resets(self):
        r, n = rig(self.d, [(0.10, 0.01, 0), (0.13, 0.01, 0), (0.10, 0.01, 0), (0.10, 0.01, 0)], 0.05)
        self.assertTrue(r)
        self.assertEqual(n, 4)

    def test_nan_speed_never_settles(self):
        r, n = rig(self.d, [(0.05, NAN, NAN)], 0.05, timeout=5.0)
        self.assertFalse(r)                         # timed out, never counted
        self.assertGreater(n, 5)

    def test_outside_tolerance_never_arrives(self):
        r, n = rig(self.d, [(0.13, 0.0, 0.0)], 0.05, timeout=5.0)
        self.assertFalse(r)

    def test_fly_to_passes_settle_speed(self):
        got = []
        self.d.navigate_wait = lambda **kw: got.append(kw) or True
        self.d.fly_to(0, 0.7, 1.5, speed=0.1, tolerance=0.12, settle_speed=0.05)
        self.d.fly_to(0, 0.7, 1.5)
        self.assertEqual(got[0]['settle_speed'], 0.05)
        self.assertEqual(got[0]['tolerance'], 0.12)
        self.assertIsNone(got[1]['settle_speed'])   # other callers: old arrival
        self.assertEqual(got[1]['tolerance'], 0.2)


def fly_to_calls(path):
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'fly_to':
            calls.append({k.arg: ast.literal_eval(k.value) for k in node.keywords
                          if k.arg in ('tolerance', 'settle_speed', 'speed')})
    return calls


class F7ExamplesTest(unittest.TestCase):

    def test_marker_examples(self):
        for name, n in (('flight_marker.py', 3), ('flight_marker_loop.py', 2)):
            with self.subTest(example=name):
                calls = fly_to_calls(os.path.join(EX, 'flight', name))
                self.assertEqual(len(calls), n)
                for c in calls:
                    self.assertEqual(c.get('tolerance'), 0.12)
                    self.assertEqual(c.get('settle_speed'), 0.05)
                    self.assertLessEqual(c['tolerance'], 0.25 / 2)   # a margin under the 0.25 m of C7


class FakePub:
    def __init__(self, topic):
        self.topic = topic
        self.times = []
        self.lock = threading.Lock()

    def publish(self, msg):
        assert msg.data is True
        with self.lock:
            self.times.append(_time.monotonic())


class LeaseTest(unittest.TestCase):

    def setUp(self):
        d = self.d = load()
        d.LEASE_PERIOD_S = 0.05
        d.Bool = type('Bool', (), {'data': False})
        self.pubs = []

        def create_publisher(typ, topic, depth):
            p = FakePub(topic)
            self.pubs.append(p)
            return p
        d._node = types.SimpleNamespace(create_publisher=create_publisher, get_logger=lambda: Log(),
                                        destroy_node=lambda: None)
        d.srv = types.SimpleNamespace(Navigate=types.SimpleNamespace(Request=lambda: types.SimpleNamespace()))
        d._call = lambda client, req, timeout=5.0, wait=None: types.SimpleNamespace(success=True, message='')

    def tearDown(self):
        self.d._stop_script_lease()

    def test_no_lease_without_flight_command(self):
        self.d.get_telemetry = lambda **kw: None
        self.assertIsNone(self.d._lease_thread)
        self.assertEqual(self.pubs, [])

    def test_navigate_starts_one_lease(self):
        self.d.navigate(x=0.0, y=0.0, z=1.0, frame_id='map', auto_arm=False)
        self.d.navigate(x=0.0, y=0.7, z=1.0, frame_id='map', auto_arm=False)
        _time.sleep(0.4)
        self.assertEqual(len(self.pubs), 1)
        p = self.pubs[0]
        self.assertEqual(p.topic, '/simple_offboard/script_lease')
        self.assertGreaterEqual(len(p.times), 5)
        gaps = [b - a for a, b in zip(p.times, p.times[1:])]
        self.assertLess(max(gaps), 0.05 * 4)
        self.assertTrue(self.d._lease_thread.daemon)  # never keeps a finished script alive (F4)

    def test_real_period_is_well_under_timeout(self):
        d = load()
        self.assertEqual(d.LEASE_TOPIC, '/simple_offboard/script_lease')
        self.assertLessEqual(d.LEASE_PERIOD_S * 3, 2.0)  # 3 periods fit in script_lease_timeout 2 s

    def test_stop_ends_publishing(self):
        self.d.navigate(x=0.0, y=0.0, z=1.0, frame_id='map', auto_arm=False)
        _time.sleep(0.15)
        self.d._stop_script_lease()
        self.assertFalse(self.d._lease_thread.is_alive())
        n = len(self.pubs[0].times)
        _time.sleep(0.2)
        self.assertEqual(len(self.pubs[0].times), n)

    def test_shutdown_stops_lease(self):
        d = self.d
        d.navigate(x=0.0, y=0.0, z=1.0, frame_id='map', auto_arm=False)
        _time.sleep(0.1)
        d._executor = None
        d._spin_thread = None
        d.rclpy = types.SimpleNamespace(ok=lambda: False)
        d._shutdown()
        self.assertFalse(d._lease_thread.is_alive())

    def test_publisher_failure_does_not_stop_navigate(self):
        def boom(*a):
            raise RuntimeError('no publisher')
        self.d._node.create_publisher = boom
        res = self.d.navigate(x=0.0, y=0.0, z=1.0, frame_id='map', auto_arm=False)
        self.assertTrue(res.success)
        self.assertIsNone(self.d._lease_thread)


if __name__ == '__main__':
    unittest.main()
