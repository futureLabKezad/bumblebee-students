"""r2b: the detector stays awake for the whole preflight and no wake is sent after arming or after the script ends.

Real threads, time scaled 1/20: WAKE_PERIOD_S 2 s -> 0.1 s, detector hold WAKE_HOLD_S 5 s -> 0.25 s. The preflight is
replayed in the order and length of examples/flight/flight.py: require_aruco ~3 s, wait_yaw_lock up to 20 s,
wait_position_stable >= 3 s, require_vpe_link 2 s, takeoff's vision wait, then arming. No ROS.
Run: python3 -m unittest discover -s test -p 'test_r2b_wake.py'   (from fixed_image_r2_20261109)
"""
import importlib.util
import os
import threading
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRONE_PY = os.path.join(os.path.dirname(HERE), 'src', 'bumblebee', 'examples', 'drone.py')
SCALE = 20.0
HOLD = 5.0 / SCALE


class Rec:
    def __init__(self):
        self.times = []
        self.destroyed = 0
        self.lock = threading.Lock()

    def create_publisher(self, typ, topic, qos):
        assert topic == '/aruco_detect/wake'
        rec = self

        class Pub:
            def publish(self, m):
                assert m.data is True
                with rec.lock:
                    rec.times.append(time.monotonic())
        return Pub()

    def destroy_publisher(self, p):
        self.destroyed += 1


def load():
    spec = importlib.util.spec_from_file_location('drone_r2b_under_test', DRONE_PY)
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    d._initialized = True
    d.Bool = lambda: types.SimpleNamespace(data=False)
    d._fcu_state_msg = types.SimpleNamespace(armed=False)
    d.WAKE_PERIOD_S = 2.0 / SCALE
    d.WAKE_MAX_S = 180.0 / SCALE
    return d


class WakeTimelineTest(unittest.TestCase):

    def setUp(self):
        self.d = load()
        self.rec = Rec()
        self.d._node = self.rec

    def tearDown(self):
        self.d._stop_detector_wake()

    def assert_awake(self, t0, t1):
        ts = [t for t in self.rec.times if t <= t1]
        self.assertTrue(ts and ts[0] - t0 <= HOLD, 'first wake too late')
        gaps = [b - a for a, b in zip(ts, ts[1:])] + [t1 - ts[-1]]
        self.assertLessEqual(max(gaps), HOLD, 'detector would fall asleep (gap %.3f s scaled)' % max(gaps))

    def test_flight_py_preflight_then_arm(self):
        d = self.d
        t0 = time.monotonic()
        for step_s in (3.0, 20.0, 3.0, 2.0, 4.0):   # aruco, yaw lock, stable, vpe link, takeoff vision wait
            d._keep_detector_awake()
            time.sleep(step_s / SCALE)
        t_arm = time.monotonic()
        d._fcu_state_msg = types.SimpleNamespace(armed=True)
        self.assert_awake(t0, t_arm)
        time.sleep(3 * d.WAKE_PERIOD_S)
        late = [t for t in self.rec.times if t > t_arm + d.WAKE_PERIOD_S + 0.05]
        self.assertEqual(late, [], 'wakes continued after arming')
        self.assertFalse(d._wake_thread.is_alive())
        self.assertEqual(self.rec.destroyed, 1)

    def test_one_thread_only(self):
        for _ in range(5):
            self.d._keep_detector_awake()
        names = [t.name for t in threading.enumerate() if t.name == 'aruco-wake']
        self.assertEqual(len(names), 1)

    def test_no_wake_after_script_end(self):
        d = self.d
        d._keep_detector_awake()
        time.sleep(0.3)
        d._stop_detector_wake()            # what _shutdown() does
        n = len(self.rec.times)
        time.sleep(0.4)
        self.assertEqual(len(self.rec.times), n)
        self.assertFalse(d._wake_thread.is_alive())

    def test_timeout_without_arming(self):
        d = self.d
        d.WAKE_MAX_S = 0.3
        d._keep_detector_awake()
        time.sleep(0.6)
        self.assertFalse(d._wake_thread.is_alive())

    def test_thread_is_daemon_and_shutdown_stops_it(self):
        self.d._keep_detector_awake()
        self.assertTrue(self.d._wake_thread.daemon)
        with open(DRONE_PY, encoding="utf-8") as f:
            src = f.read()
        i = src.index('def _shutdown():')
        self.assertIn('_stop_detector_wake()', src[i:i + 1200])
        for fn in ('check_aruco', 'wait_yaw_lock', 'require_vpe_link', 'wait_position_stable', 'takeoff'):
            j = src.index('\ndef %s(' % fn)
            self.assertIn('_keep_detector_awake()', src[j:j + 2500], fn)


if __name__ == '__main__':
    unittest.main()


class MapFileLinesTest(unittest.TestCase):
    """Review T15 must-fix 3: a short, bad or repeated map line is a RuntimeError, not IndexError/ValueError."""

    def check(self, body):
        import tempfile
        d = load()
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(body)
        try:
            return d._read_map_file(f.name)
        finally:
            os.remove(f.name)

    def test_good_map(self):
        rows = self.check("# id length x y z rot_z\n0 0.19 0 0 -0.32 1.571 0 0\n4 0.29 -0.72 -0.73 -0.32 -1.571 0 0\n")
        self.assertEqual(rows[4], (0.29, -0.72, -0.73, -1.571))

    def test_bad_lines(self):
        for body in ("0 0.19 0\n", "0 0.19 zero 0\n", "x 0.19 0 0\n", "0 0.19 0 0\n0 0.29 1 1\n", "# only comment\n"):
            with self.assertRaises(RuntimeError, msg=repr(body)):
                self.check(body)

    def test_image_map_reads(self):
        m = "/work/ws_sitl/install/aruco_pose/share/aruco_pose/map/map.txt"
        if not os.path.exists(m):
            self.skipTest("no stand map")
        self.assertEqual(len(load()._read_map_file(m)), 20)
