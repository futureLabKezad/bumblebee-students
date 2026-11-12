"""r2h W (no ROS): navigate_wait looks at the vision watchdog every 0.1 s (was: once per 0.5 s loop), on simple_offboard's
hold clock (ROS clock under use_sim_time, else monotonic).

1. Every r2g test (test/test_r2g.py, which re-runs every r2f test) on r2h's drone.py: test_r2g's folder check is
   retargeted to this folder, nothing else in it changes. Its bounds "limit + one 0.5 s loop" still hold.
2. New W tests: landing at limit + <= 0.1 s (fly_to 6 s, takeoff 25 s, after a pose stream stops); controls on r2g
   (up to + 0.5 s); the hold clock (sim time when active, monotonic when not or when the ROS clock reads 0, a change of
   clock kind falls back to monotonic, a negative age is +inf); vision_pose_age() stays monotonic; the loop step and
   the other checks are unchanged (source).
Run: python3 -B test/test_r2h.py -v   (from the r2h folder)
"""
import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_src = (HERE / 'test_r2g.py').read_text()
_old = "assert 'fixed_image_r2g_20261110' in str(R2G_DRONE), R2G_DRONE"
assert _src.count(_old) == 1
_src = _src.replace(_old, "assert 'fixed_image_r2i_20261111' in str(R2G_DRONE), R2G_DRONE   # r2h: retargeted")
R2G_TESTS = types.ModuleType('test_r2g_on_r2h')
R2G_TESTS.__file__ = str(HERE / 'test_r2g.py')
sys.modules['test_r2g_on_r2h'] = R2G_TESTS
exec(compile(_src, str(HERE / 'test_r2g.py'), 'exec'), R2G_TESTS.__dict__)
T = R2G_TESTS.T
G = T.G
pose = T.pose
R2H_DRONE = R2G_TESTS.R2G_DRONE
R2G_DRONE = Path('/work/fixed_image_r2g_20261110/src/bumblebee/examples/drone.py')

# 1. every r2g test on r2h
for _name in dir(R2G_TESTS):
    _obj = getattr(R2G_TESTS, _name)
    if isinstance(_obj, type) and issubclass(_obj, unittest.TestCase) and _obj.__module__ == 'test_r2g_on_r2h':
        globals()['R2G_' + _name] = _obj


def sim_clock(d, sim):
    d._node.get_clock = lambda: types.SimpleNamespace(
        ros_time_is_active=sim['active'], now=lambda: types.SimpleNamespace(nanoseconds=int(sim['t'] * 1e9)))


class WLimits(T.Base):
    drone_py = R2H_DRONE

    def test_fly_to_lands_within_0p1_s_of_the_limit_after_the_last_pose(self):
        d, fcu = self.flying()
        d._on_vpe_pose(pose(0.0))
        t_pose = self.clock.now
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertIn('Vision lost', self.text())
        self.assertEqual(len(self.land_t), 1)
        self.assertGreater(self.land_t[0] - t_pose, 6.0)
        self.assertLessEqual(self.land_t[0] - t_pose, 6.1 + 1e-6)

    def test_flying_without_any_pose_lands_within_0p1_s(self):
        d, fcu = self.flying()
        arm = d._vision_arm_t
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertGreater(self.land_t[0] - arm, 6.0)
        self.assertLessEqual(self.land_t[0] - arm, 6.1 + 1e-6)

    def test_pose_stream_that_stops_mid_leg(self):
        """new poses every clock step for 3 s, then none: landing 6.0..6.1 s after the last pose, at any phase of the
        0.5 s loop (start offsets 0.0..0.45 s)"""
        for off in (0.0, 0.1, 0.25, 0.45):
            with self.subTest(offset=off):
                d, fcu = self.flying()
                self.clock.sleep(off)
                start = self.clock.now
                last = {'t': None}

                def cb(_dt, d=d, fcu=fcu, start=start, last=last):
                    if self.clock.now - start < 3.0:
                        d._on_vpe_pose(pose(fcu.pos[0] + 1e-4 * self.clock.now, fcu.pos[1], fcu.pos[2]))
                        last['t'] = self.clock.now
                self.clock.on_advance.append(cb)
                self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
                gap = self.land_t[0] - last['t']
                self.assertGreater(gap, 6.0)
                self.assertLessEqual(gap, 6.1 + 1e-6)

    def test_takeoff_without_any_pose_lands_within_0p1_s_of_25(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        self.land_t = []
        orig = fcu.set_mode

        def set_mode(req):
            if req.custom_mode == 'AUTO.LAND':
                self.land_t.append(self.clock.now)
            return orig(req)
        d._set_mode_client = G.FakeClient('/mavros/set_mode', set_mode)
        self.assertFalse(self.run_quiet(d.takeoff, 20.0, speed=0.4))
        self.assertGreater(self.land_t[0] - d._vision_arm_t, 25.0)
        self.assertLessEqual(self.land_t[0] - d._vision_arm_t, 25.1 + 1e-6)

    def test_with_poses_the_flight_is_unchanged(self):
        d, fcu = self.flying()
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(fcu.pos[0], fcu.pos[1], fcu.pos[2])))
        self.assertTrue(self.run_quiet(d.fly_to, 2.0, 0.0, 1.0))
        self.assertNotIn('Vision lost', self.text())
        self.assertEqual(self.land_t, [])


class WControlR2G(T.Base):
    """The same on r2g: the check waits for the 0.5 s loop step."""
    drone_py = R2G_DRONE

    def test_r2g_lands_up_to_0p5_s_after_the_limit(self):
        worst = 0.0
        for off in (0.0, 0.1, 0.25, 0.45):
            d, fcu = self.flying()
            self.clock.sleep(off)
            start = self.clock.now
            last = {'t': None}

            def cb(_dt, d=d, fcu=fcu, start=start, last=last):
                if self.clock.now - start < 3.0:
                    d._on_vpe_pose(pose(fcu.pos[0] + 1e-4 * self.clock.now, fcu.pos[1], fcu.pos[2]))
                    last['t'] = self.clock.now
            self.clock.on_advance.append(cb)
            self.run_quiet(d.fly_to, 8.0, 0.0, 1.0)
            worst = max(worst, self.land_t[0] - last['t'])
            self.clock.on_advance.remove(cb)
        self.assertGreater(worst, 6.1 + 1e-6)
        self.assertLessEqual(worst, 6.5 + 1e-6)


class WClock(T.Base):
    drone_py = R2H_DRONE

    def test_silence_follows_the_sim_clock_when_active(self):
        d, fcu = self.flying()
        sim = {'active': True, 't': 100.0}
        sim_clock(d, sim)
        d._on_vpe_pose(pose(0.3))
        self.clock.now += 4.0          # wall 4 s ...
        sim['t'] += 2.0                # ... sim 2 s (RTF 0.5)
        self.assertAlmostEqual(d._vision_silence_age(), 2.0)
        self.assertAlmostEqual(d.vision_pose_age(), 4.0)    # the scripts' signal stays monotonic

    def test_monotonic_when_not_active_or_clock_reads_zero(self):
        for active, t in ((False, 100.0), (True, 0.0)):
            with self.subTest(active=active, t=t):
                d, fcu = self.flying()
                sim = {'active': active, 't': t}
                sim_clock(d, sim)
                d._on_vpe_pose(pose(0.4 + t))
                self.clock.now += 3.0
                self.assertAlmostEqual(d._vision_silence_age(), 3.0)

    def test_change_of_clock_kind_falls_back_to_monotonic(self):
        d, fcu = self.flying()
        sim = {'active': True, 't': 0.0}            # use_sim_time, /clock not started: monotonic stamp
        sim_clock(d, sim)
        d._on_vpe_pose(pose(0.5))
        self.clock.now += 1.5
        sim['t'] = 500.0                            # /clock starts
        self.assertAlmostEqual(d._vision_silence_age(), 1.5)

    def test_negative_age_is_inf(self):
        d, fcu = self.flying()
        sim = {'active': True, 't': 100.0}
        sim_clock(d, sim)
        d._on_vpe_pose(pose(0.6))
        sim['t'] = 90.0                             # the sim clock went back (a restarted Gazebo)
        self.assertEqual(d._vision_silence_age(), math.inf)

    def test_arm_reference_on_the_hold_clock_and_cleared_on_disarm(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        sim = {'active': True, 't': 50.0}
        sim_clock(d, sim)
        d._on_fcu_state(types.SimpleNamespace(connected=True, armed=True, mode='OFFBOARD'))
        self.assertEqual(d._vision_arm_wd[:2], (True, 50.0))
        sim['t'] += 1.0
        self.assertAlmostEqual(d._vision_silence_age(), 1.0)
        d._on_fcu_state(types.SimpleNamespace(connected=True, armed=False, mode='OFFBOARD'))
        self.assertIsNone(d._vision_arm_wd)
        self.assertIsNone(d._vision_arm_t)


class WSource(unittest.TestCase):
    def test_navigate_wait_step_and_checks(self):
        src = R2H_DRONE.read_text()
        nw = src[src.index('def navigate_wait('):src.index('def takeoff(')]
        self.assertIn('_wait_watching_vision(0.5, vision_timeout)', nw)
        self.assertNotIn('time.sleep(0.5)', nw)
        old = R2G_DRONE.read_text()
        onw = old[old.index('def navigate_wait('):old.index('def takeoff(')]
        self.assertEqual(onw.replace('        time.sleep(0.5)\n', ''),
                         nw.replace('        # r2h (W): the same 0.5 s step, the vision watchdog looked at every 0.1 s\n'
                                    '        _wait_watching_vision(0.5, vision_timeout)\n', ''))
        self.assertIn('_VISION_WD_PERIOD = 0.1', src)
        for lim in ('vision_timeout=6.0', 'vision_timeout=25.0', 'silence > 3.0'):
            self.assertEqual(src.count(lim), old.count(lim), lim)


if __name__ == '__main__':
    unittest.main()
