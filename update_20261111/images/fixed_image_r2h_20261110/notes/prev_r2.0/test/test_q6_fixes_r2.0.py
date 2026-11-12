"""Tests for the question-6 draft fixes (image_bugs_q6_20261109, 09.11.2026). No ROS, no simulator.

F4  control experiment with real Python: a non-daemon thread + atexit hook hangs; threading._register_atexit exits.
    drone.py registers _shutdown that way.
F1  aruco_detect._detect_full_rate honours /aruco_detect/wake for 5 s (methods taken from the source with ast);
    drone.check_aruco() publishes the wake while it waits and destroys the publisher.
F2  drone.set_aruco_map(): same map -> OK and nothing written / no subprocess; different or unreadable -> RuntimeError.
E1  flight.py takes off to 0.8 m.   E2  flight_marker_loop.py waypoints 13/12/11 sit on its own map (x=-0.72).
Run: python3 -m unittest discover -s test -p 'test_q6_fixes.py'   (from the folder image_bugs_q6_20261109)
"""
import ast
import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(os.path.dirname(HERE), 'src', 'bumblebee')
EX = os.path.join(PKG, 'examples')
DRONE_PY = os.path.join(EX, 'drone.py')
DETECT_PY = os.path.join(PKG, 'src', 'python', 'aruco_detect.py')
IMAGE_MAP = '/work/sim/worlds/aruco_map/map.input.txt'


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def load_drone():
    spec = importlib.util.spec_from_file_location('drone_q6_under_test', DRONE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._initialized = True
    return mod


class F4ShutdownTest(unittest.TestCase):
    PROG = textwrap.dedent('''
        import threading, atexit
        ev = threading.Event()
        threading.Thread(target=ev.wait, daemon=False).start()
        def stop(): ev.set()
        {hook}(stop)
        print('main done')
    ''')

    def run_prog(self, hook):
        return subprocess.run([sys.executable, '-I', '-c', self.PROG.format(hook=hook)],
                              capture_output=True, text=True, timeout=10 if 'threading' in hook else 3)

    def test_control_atexit_hangs(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_prog('atexit.register')

    def test_register_atexit_exits(self):
        r = self.run_prog('threading._register_atexit')
        self.assertEqual(r.returncode, 0)
        self.assertIn('main done', r.stdout)

    def test_drone_registers_before_thread_join(self):
        t = read(DRONE_PY)
        i = t.index('_spin_thread.start()')
        self.assertIn('threading._register_atexit(_shutdown)', t[i:i + 600])
        self.assertIn('daemon=False', t)   # unchanged: the fix does not rely on a daemon thread


class F1WakeTest(unittest.TestCase):

    def methods(self):
        tree = ast.parse(read(DETECT_PY))
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
                   and any(isinstance(f, ast.FunctionDef) and f.name == '_detect_full_rate' for f in n.body))
        body = [n for n in cls.body if (isinstance(n, ast.FunctionDef) and n.name in ('_detect_full_rate', '_wake_cb'))
                or (isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'WAKE_HOLD_S')]
        mod = ast.Module(body=[ast.ClassDef(name='D', bases=[], keywords=[], body=body, decorator_list=[])],
                         type_ignores=[])
        clock = types.SimpleNamespace(now=100.0)
        ns = {'time': types.SimpleNamespace(monotonic=lambda: clock.now)}
        exec(compile(ast.fix_missing_locations(mod), DETECT_PY, 'exec'), ns)
        return ns['D'], clock

    def make(self, gate=True, armed=False, mode='POSCTL'):
        D, clock = self.methods()
        d = D()
        d.gate_by_flight_state, d.full_rate_when_armed = gate, True
        d._fcu_armed, d._fcu_mode, d._wake_until = armed, mode, 0.0
        return d, clock

    def test_sleeps_when_disarmed_without_wake(self):
        d, _ = self.make()
        self.assertFalse(d._detect_full_rate())

    def test_wake_holds_5s(self):
        d, clock = self.make()
        d._wake_cb(types.SimpleNamespace(data=True))
        self.assertTrue(d._detect_full_rate())
        clock.now += 4.9
        self.assertTrue(d._detect_full_rate())
        clock.now += 0.2
        self.assertFalse(d._detect_full_rate())

    def test_false_wake_does_nothing(self):
        d, _ = self.make()
        d._wake_cb(types.SimpleNamespace(data=False))
        self.assertFalse(d._detect_full_rate())

    def test_armed_and_gate_off_unchanged(self):
        self.assertTrue(self.make(armed=True)[0]._detect_full_rate())
        self.assertTrue(self.make(mode='OFFBOARD')[0]._detect_full_rate())
        self.assertTrue(self.make(gate=False)[0]._detect_full_rate())

    def test_wake_subscription_in_gate_block(self):
        t = read(DETECT_PY)
        self.assertIn("self.create_subscription(Bool, '/aruco_detect/wake', self._wake_cb, 10)", t)
        self.assertIn('import time', t)

    def test_check_aruco_publishes_wake(self):
        d = load_drone()
        subs, pubs, destroyed = {}, [], []

        class Pub:
            def __init__(self):
                self.sent = []

            def publish(self, m):
                self.sent.append(m.data)

        class Node:
            def create_subscription(self, typ, topic, cb, qos):
                subs[topic] = cb
                return topic

            def create_publisher(self, typ, topic, qos):
                p = Pub()
                pubs.append((topic, p))
                return p

            def destroy_subscription(self, s):
                destroyed.append(s)

            def destroy_publisher(self, p):
                destroyed.append(p)

        clock = types.SimpleNamespace(t=0.0, sleeps=0)

        def sleep(dt):
            clock.t += dt
            clock.sleeps += 1
            if clock.sleeps == 3:
                subs['/aruco_detect/markers'](types.SimpleNamespace(markers=[types.SimpleNamespace(id=0)]))
        d._node = Node()
        d.Bool = lambda: types.SimpleNamespace(data=False)
        d.MarkerArray = object
        d.rclpy = types.SimpleNamespace(ok=lambda: True)
        d.time = types.SimpleNamespace(time=lambda: clock.t, sleep=sleep, monotonic=lambda: clock.t)
        with contextlib.redirect_stdout(io.StringIO()):
            ids = d.check_aruco(timeout=10, min_markers=1)
        self.assertEqual(ids, [0])
        self.assertEqual(pubs[0][0], '/aruco_detect/wake')
        self.assertEqual(pubs[0][1].sent, [True, True, True])
        self.assertIn(pubs[0][1], destroyed)


class F2MapTest(unittest.TestCase):

    def setUp(self):
        self.d = load_drone()
        self.tmp = tempfile.mkdtemp(prefix='q6map_')
        self.d.MAP_FILE = os.path.join(self.tmp, 'map.txt')
        with open(self.d.MAP_FILE, 'w') as f:
            f.write(read(IMAGE_MAP))
        self.d._node = types.SimpleNamespace(get_logger=lambda: types.SimpleNamespace(error=print))
        self.d.subprocess = types.SimpleNamespace(run=self.fail_run)

    def fail_run(self, *a, **k):
        raise AssertionError('set_aruco_map must not run subprocesses (pkill / ros2 lifecycle)')

    def loop_markers(self):
        tree = ast.parse(read(os.path.join(EX, 'flight', 'flight_marker_loop.py')))
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and getattr(n.func, 'attr', '') == 'set_aruco_map')
        return ast.literal_eval(call.args[0])

    def test_same_map_ok_and_file_untouched(self):
        before = read(self.d.MAP_FILE)
        mtime = os.stat(self.d.MAP_FILE).st_mtime_ns
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.d.set_aruco_map(self.loop_markers())
        self.assertIn('Map check OK: 20 markers', out.getvalue())
        self.assertEqual(read(self.d.MAP_FILE), before)
        self.assertEqual(os.stat(self.d.MAP_FILE).st_mtime_ns, mtime)

    def test_map_file_argument(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.d.set_aruco_map(map_file=IMAGE_MAP)

    def test_different_map_refuses(self):
        m = self.loop_markers()
        m[11] = dict(m[11], x=-1.0)
        with self.assertRaises(RuntimeError) as e:
            self.d.set_aruco_map(m)
        self.assertIn('id 11', str(e.exception))

    def test_missing_marker_refuses(self):
        with self.assertRaises(RuntimeError):
            self.d.set_aruco_map(self.loop_markers()[:-1])

    def test_unreadable_loaded_map_refuses(self):
        self.d.MAP_FILE = os.path.join(self.tmp, 'absent.txt')
        with self.assertRaises(RuntimeError):
            self.d.set_aruco_map(self.loop_markers())


class ExamplesTest(unittest.TestCase):

    def test_scripts_parse(self):
        for n in ('flight.py', 'flight_marker.py', 'flight_marker_loop.py'):
            ast.parse(read(os.path.join(EX, 'flight', n)))
        ast.parse(read(DRONE_PY))
        ast.parse(read(DETECT_PY))

    def test_e1_flight_height_matches_docstring(self):
        t = read(os.path.join(EX, 'flight', 'flight.py'))
        self.assertIn('takeoff to 0.8m', t)
        self.assertIn('drone.takeoff(height=0.8, speed=0.4)', t)

    def test_e2_loop_waypoints_on_its_map(self):
        t = read(os.path.join(EX, 'flight', 'flight_marker_loop.py'))
        tree = ast.parse(t)
        wp = next(ast.literal_eval(n.value) for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'WAYPOINTS')
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                    and getattr(n.func, 'attr', '') == 'set_aruco_map')
        mp = {m['id']: (m['x'], m['y']) for m in ast.literal_eval(call.args[0])}
        for mid, idx in ((13, 4), (12, 5), (11, 6)):
            self.assertAlmostEqual(wp[idx][0], mp[mid][0], places=3)
            self.assertLess(abs(wp[idx][1] - mp[mid][1]), 0.035)   # y kept as in the script: 1-3 cm off the map


if __name__ == '__main__':
    unittest.main()
