"""r2f T35 (no ROS): vision watchdogs count only NEW poses vpe_fix published on /mavros/mavros/pose_cov.

Uses the package's own fake vehicle (src/bumblebee/test/test_drone_flight_guards.py: FakeFCU, virtual clock).
"False frame" = what r2e's /aruco_detect/markers_used callback did on a value >= 1 (false detection that vpe_fix
rejected): _aruco_markers_used = 1 and _aruco_markers_pos_time = now, with no vpe_fix publication.
Controls run the same scenario on r2e's drone.py to show each test tells r2e and r2f apart.
Run: python3 -B test/test_r2f.py -v   (from the r2f folder)
"""
import ast
import importlib.util
import math
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EX = ROOT / 'src/bumblebee/examples'
R2E_DRONE = Path('/work/fixed_image_r2e_20261109/src/bumblebee/examples/drone.py')

_spec = importlib.util.spec_from_file_location('guards_r2f', ROOT / 'src/bumblebee/test/test_drone_flight_guards.py')
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)
R2F_DRONE = Path(G.DRONE_PY)
assert R2F_DRONE == EX / 'drone.py', R2F_DRONE


def pose(x, y=0.0, z=1.0):
    return types.SimpleNamespace(pose=types.SimpleNamespace(pose=types.SimpleNamespace(
        position=types.SimpleNamespace(x=x, y=y, z=z),
        orientation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0))))


class Base(G.GuardTestBase):
    drone_py = R2F_DRONE

    def setUp(self):
        self._old = G.DRONE_PY
        G.DRONE_PY = str(self.drone_py)

    def tearDown(self):
        G.DRONE_PY = self._old

    def flying(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.land_t = []
        orig = fcu.set_mode

        def set_mode(req):
            if req.custom_mode == 'AUTO.LAND':
                self.land_t.append(self.clock.now)
            return orig(req)
        d._set_mode_client = G.FakeClient('/mavros/set_mode', set_mode)
        return d, fcu

    def false_frames(self, d):
        """r2e's markers_used callback on a false detection, every clock step (~10 Hz in navigate_wait)."""
        def cb(_dt):
            d._aruco_markers_used = 1
            d._aruco_markers_used_time = self.clock.now
            d._aruco_markers_pos_time = self.clock.now
        self.clock.on_advance.append(cb)


class VisionWatchdogR2F(Base):

    def test_false_frames_do_not_extend_vision(self):
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))                 # last real pose now
        t_pose = self.clock.now
        self.false_frames(d)
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))   # 16 s leg at 0.5 m/s
        self.assertIn('Vision lost', self.text())
        self.assertIn('no new vpe_fix pose', self.text())
        self.assertEqual(len(self.land_t), 1)
        self.assertGreater(self.land_t[0] - t_pose, 6.0)
        self.assertLessEqual(self.land_t[0] - t_pose, 6.5 + 1e-6)   # fly_to limit 6 s + one 0.5 s loop step
        self.assertTrue(d._vision_abort)

    def test_new_poses_extend_vision(self):
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(fcu.pos[0], fcu.pos[1], fcu.pos[2])))
        self.assertTrue(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertNotIn('Vision lost', self.text())
        self.assertEqual(self.land_t, [])
        self.assertLess(d.vision_pose_age(), 0.2)

    def test_repeated_same_pose_does_not_extend(self):
        """vpe_fix repeats the last accepted pose for up to 0.5 s with a new stamp: not new vision."""
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))
        t_pose = self.clock.now
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(0.0)))
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertIn('Vision lost', self.text())
        self.assertGreater(self.land_t[0] - t_pose, 6.0)
        self.assertLessEqual(self.land_t[0] - t_pose, 6.5 + 1e-6)

    def test_vpe_fix_silent_trips(self):
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertIn('Vision lost', self.text())
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])

    def test_vision_pose_age(self):
        d, fcu = self.flying()
        self.assertEqual(d.vision_pose_age(), math.inf)
        d._on_vpe_pose(pose(0.1))
        self.assertEqual(d.vision_pose_age(), 0.0)
        self.clock.sleep(0.7)
        d._on_vpe_pose(pose(0.1))                 # repeat: age keeps growing
        self.assertAlmostEqual(d.vision_pose_age(), 0.7)
        d._on_vpe_pose(pose(0.1, 0.0, 1.0001))    # any change of the pose is new
        self.assertEqual(d.vision_pose_age(), 0.0)

    def test_no_pose_before_takeoff_inactive_and_warns(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        self.false_frames(d)                      # raw frames alone never activate the r2f watchdog
        self.assertTrue(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('takeoff: no vpe_fix pose seen yet -- vision watchdog inactive until the first one', self.text())
        self.assertNotIn('Vision lost', self.text())

    def test_no_warning_when_pose_seen(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        d._on_vpe_pose(pose(0.0, 0.0, 0.0))
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(fcu.pos[0], fcu.pos[1], fcu.pos[2])))
        self.assertTrue(self.run_quiet(d.takeoff, 1.0))
        self.assertNotIn('no vpe_fix pose seen yet', self.text())

    def test_safe_land_false_frames_mean_straight_land(self):
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))
        self.clock.sleep(3.5)                     # no new pose for 3.5 s
        d._aruco_markers_used, d._aruco_markers_pos_time = 1, self.clock.now   # a fresh false frame
        self.assertTrue(self.run_quiet(d.safe_land, x=0.5, y=0.5))
        self.assertIn('safe_land: vision unhealthy -> straight land', self.text())
        self.assertNotIn('Precision approach', self.text())

    def test_safe_land_fresh_pose_keeps_precision_approach(self):
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(fcu.pos[0], fcu.pos[1], fcu.pos[2])))
        self.run_quiet(d.safe_land, x=0.5, y=0.5)
        self.assertIn('Precision approach to (0.50, 0.50)', self.text())
        self.assertNotIn('vision unhealthy', self.text())


class ControlR2E(Base):
    """The same scenarios on r2e: false frames DO extend vision there (the T35 finding)."""
    drone_py = R2E_DRONE

    def test_r2e_false_frames_extend_vision(self):
        d, fcu = self.flying()
        d._aruco_markers_pos_time = self.clock.now
        self.false_frames(d)
        self.assertTrue(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertNotIn('Vision lost', self.text())
        self.assertFalse(hasattr(d, 'vision_pose_age'))

    def test_r2e_safe_land_trusts_false_frames(self):
        d, fcu = self.flying()
        d._aruco_markers_pos_time = self.clock.now
        self.clock.sleep(3.5)
        d._aruco_markers_pos_time = self.clock.now
        self.run_quiet(d.safe_land, x=0.5, y=0.5)
        self.assertIn('Precision approach', self.text())


def hover_vw_from(path, fake_drone, clock):
    """flight_marker.hover_vw compiled alone (the script flies on import) against a fake drone and clock."""
    tree = ast.parse(path.read_text())
    fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'hover_vw']
    assert len(fn) == 1
    ns = {'drone': fake_drone, 'time': clock}
    exec(compile(ast.Module(body=fn, type_ignores=[]), str(path), 'exec'), ns)
    return ns['hover_vw']


class Scripts(unittest.TestCase):

    def fake(self, age_fn):
        clock = G.FakeTime()
        clock.time = lambda: clock.now
        fd = types.SimpleNamespace(should_land=False, hover=lambda s: clock.sleep(s),
                                   vision_pose_age=lambda: age_fn(clock),
                                   _aruco_markers_used=3, _markers_used_age=lambda: 0.0)   # raw frames look healthy
        return fd, clock

    def test_hover_vw_aborts_on_no_new_pose_despite_raw_frames(self):
        fd, clock = self.fake(lambda c: math.inf)
        hv = hover_vw_from(EX / 'flight/flight_marker.py', fd, clock)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(hv(10.0, silent_limit=2.0))

    def test_hover_vw_ok_with_new_poses(self):
        fd, clock = self.fake(lambda c: 0.1)
        hv = hover_vw_from(EX / 'flight/flight_marker.py', fd, clock)
        self.assertTrue(hv(3.0, silent_limit=2.0))

    def test_hover_watchdogs_use_vision_pose_age(self):
        """flight.py and flight_marker_loop.py hover loops are top-level code: their condition line is checked."""
        f = (EX / 'flight/flight.py').read_text()
        self.assertIn('        if drone.vision_pose_age() > 1.0:\n', f)
        self.assertNotIn('drone._aruco_markers_used == 0', f)
        loop = (EX / 'flight/flight_marker_loop.py').read_text()
        self.assertIn('            if drone.vision_pose_age() > 1.0:   # r2f (T35): new vpe_fix poses only\n', loop)
        self.assertNotIn('drone._aruco_markers_used == 0', loop)
        marker = (EX / 'flight/flight_marker.py').read_text()
        self.assertNotIn('drone._aruco_markers_used == 0', marker)
        self.assertIn('mu = drone._aruco_markers_used', marker)   # wait_quorum (on the ground) unchanged

    def test_init_subscribes_pose_cov_best_effort(self):
        """_init() with faked ROS (as the package's ArmingD3 test): /mavros/mavros/pose_cov -> _on_vpe_pose."""
        d = G.load_drone()
        subs = {}

        class Node:
            def __init__(self, name):
                pass

            def create_client(self, srv_type, name):
                return G.FakeClient(name, None)

            def create_subscription(self, msg_type, topic, cb, qos):
                subs[topic] = (msg_type, cb, qos)

        ex = types.SimpleNamespace(add_node=lambda n: None, spin=lambda: None, shutdown=lambda timeout_sec=None: None)
        d._ros2_import = lambda: None
        d.rclpy = types.SimpleNamespace(init=lambda **kw: None, ok=lambda: False,
                                        executors=types.SimpleNamespace(MultiThreadedExecutor=lambda: ex,
                                                                        SingleThreadedExecutor=lambda: ex))
        d.Node = Node
        d.atexit = types.SimpleNamespace(register=lambda fn: None)
        d.srv = types.SimpleNamespace(GetTelemetry='GetTelemetry', Navigate='Navigate', SetParam='SetParam')
        d.Trigger, d.CommandBool, d.SetMode, d.ParamPull = 'Trigger', 'CommandBool', 'SetMode', 'ParamPull'
        d.Int32, d.Bool, d.State, d.BatteryState = 'Int32', 'Bool', 'State', 'BatteryState'
        d.PoseWithCovarianceStamped = 'PWCS'
        d.QoSProfile = lambda **kw: kw
        d.ReliabilityPolicy = types.SimpleNamespace(RELIABLE=1, BEST_EFFORT=2)
        d.DurabilityPolicy = types.SimpleNamespace(TRANSIENT_LOCAL=1, VOLATILE=2)
        d._init()
        msg_type, cb, qos = subs['/mavros/mavros/pose_cov']
        self.assertEqual(msg_type, 'PWCS')
        self.assertIs(cb, d._on_vpe_pose)
        self.assertEqual(qos, dict(depth=10, reliability=2, durability=2))
        self.assertIn('/aruco_detect/markers_used', subs)   # raw stream still read (preflight, LEDs)

    def test_drone_py_watchdogs_no_longer_read_raw_marker_time(self):
        src = R2F_DRONE.read_text()
        nw = src[src.index('def navigate_wait('):src.index('def takeoff(')]
        sl = src[src.index('def safe_land('):]
        sl = sl[:sl.index('\ndef ', 1)]
        for body in (nw, sl):
            self.assertNotIn('_aruco_markers_pos_time', body)
            self.assertNotIn('_markers_pos_age()', body)
            self.assertIn('vision_pose_age()', body)
        init = src[src.index('def _on_markers_used('):src.index('def _on_battery(')]
        self.assertIn("_node.create_subscription(PoseWithCovarianceStamped, '/mavros/mavros/pose_cov', _on_vpe_pose, "
                      "_vpe_qos)", init)
        self.assertIn('reliability=ReliabilityPolicy.BEST_EFFORT', init)


if __name__ == '__main__':
    unittest.main()
