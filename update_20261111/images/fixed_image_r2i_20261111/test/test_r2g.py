"""r2g S4 (no ROS): with no vpe_fix pose yet, the vision watchdog counts "no vision" from the arm.

Re-runs every r2f test (test/test_r2f.py) on r2g's drone.py; two r2f tests describe the r2f behaviour that S4 changes
on purpose and are replaced here (takeoff warning text; safe_land/navigate_wait now read _vision_silence_age()).
New S4 tests: no pose ever -> landing at arm + limit (takeoff 25 s, fly_to 6 s, safe_land straight after 3 s);
a late first pose takes over; the disarm clears the arm reference; normal flight with poses unchanged; false frames
still do not extend vision; vision_pose_age() unchanged. Controls on r2f: no pose ever -> no landing (the S4 finding).
Run: python3 -B test/test_r2g.py -v   (from the r2g folder)
"""
import importlib.util
import math
import types
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('test_r2f_base', HERE / 'test_r2f.py')
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
G = T.G
R2G_DRONE = T.R2F_DRONE          # test_r2f resolves drone.py of this folder (r2g)
R2F_DRONE = Path('/work/fixed_image_r2f_20261110/src/bumblebee/examples/drone.py')
assert 'fixed_image_r2g_20261110' in str(R2G_DRONE), R2G_DRONE
pose = T.pose


class R2FTestsOnR2G(T.VisionWatchdogR2F):
    """All r2f watchdog tests on r2g; one replaced (S4 changes it on purpose)."""

    def test_no_pose_before_takeoff_inactive_and_warns(self):
        # r2f: watchdog inactive + warning. r2g: the warning says it lands without a pose; a 2.5 s takeoff stays
        # well inside the 25 s limit, so it still succeeds; raw frames alone still do not count
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        self.false_frames(d)
        self.assertTrue(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('takeoff: no vpe_fix pose seen yet -- landing if none arrives within 25.0s of the arm', self.text())
        self.assertNotIn('Vision lost', self.text())


class ControlR2EOnR2G(T.ControlR2E):
    pass


class ScriptsOnR2G(T.Scripts):

    def test_drone_py_watchdogs_no_longer_read_raw_marker_time(self):
        src = R2G_DRONE.read_text()
        nw = src[src.index('def navigate_wait('):src.index('def takeoff(')]
        sl = src[src.index('def safe_land('):]
        sl = sl[:sl.index('\ndef ', 1)]
        for body in (nw, sl):
            self.assertNotIn('_aruco_markers_pos_time', body)
            self.assertNotIn('_markers_pos_age()', body)
            self.assertIn('silence = _vision_silence_age()', body)   # r2g: new vpe_fix poses, else since the arm
        init = src[src.index('def _on_markers_used('):src.index('def _on_battery(')]
        self.assertIn("_node.create_subscription(PoseWithCovarianceStamped, '/mavros/mavros/pose_cov', _on_vpe_pose, "
                      "_vpe_qos)", init)


class S4NoPoseEver(T.Base):
    drone_py = R2G_DRONE

    def test_takeoff_without_any_pose_lands_at_arm_plus_25s(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        self.assertIsNone(d._vision_arm_t)
        self.land_t = []
        orig = fcu.set_mode

        def set_mode(req):
            if req.custom_mode == 'AUTO.LAND':
                self.land_t.append(self.clock.now)
            return orig(req)
        d._set_mode_client = G.FakeClient('/mavros/set_mode', set_mode)
        self.false_frames(d)                                           # raw detector frames do not help
        self.assertFalse(self.run_quiet(d.takeoff, 20.0, speed=0.4))   # 50 s climb: the 25 s limit decides
        self.assertIn('no new vpe_fix pose since the arm, limit 25.0s', self.text())
        arm = d._vision_arm_t                                          # still armed (descending): kept
        self.assertIsNotNone(arm)
        self.assertEqual(len(self.land_t), 1)                          # in flight: AUTO.LAND (outside the ground hold)
        self.assertGreater(self.land_t[0] - arm, 25.0)
        self.assertLessEqual(self.land_t[0] - arm, 25.5 + 1e-6)        # + one 0.5 s loop
        self.assertTrue(d._vision_abort)

    def test_flying_without_any_pose_lands_after_the_fly_to_limit(self):
        d, fcu = self.flying()
        arm = d._vision_arm_t
        self.assertIsNotNone(arm)
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertIn('since the arm, limit 6.0s', self.text())
        self.assertGreater(self.land_t[0] - arm, 6.0)
        self.assertLessEqual(self.land_t[0] - arm, 6.5 + 1e-6)

    def test_late_first_pose_takes_over(self):
        """No pose for 4 s after the arm, then regular new poses: no landing, the age follows the poses."""
        d, fcu = self.flying()
        start = self.clock.now
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(fcu.pos[0], fcu.pos[1], fcu.pos[2]))
                                     if self.clock.now - start >= 4.0 else None)
        self.assertTrue(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertNotIn('Vision lost', self.text())
        self.assertLess(d._vision_silence_age(), 0.6)

    def test_false_frames_still_do_not_extend(self):
        d, fcu = self.flying()
        self.false_frames(d)
        self.assertFalse(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertIn('Vision lost', self.text())

    def test_safe_land_without_any_pose_is_straight_after_3s(self):
        d, fcu = self.flying()
        self.clock.sleep(3.5)
        self.assertTrue(self.run_quiet(d.safe_land, x=0.5, y=0.5))
        self.assertIn('safe_land: vision unhealthy -> straight land', self.text())
        self.assertNotIn('Precision approach', self.text())

    def test_disarm_clears_the_arm_reference(self):
        d, fcu = self.flying()
        self.assertIsNotNone(d._vision_arm_t)
        self.assertTrue(self.run_quiet(d.safe_land))
        self.assertFalse(fcu.armed)
        self.assertIsNone(d._vision_arm_t)
        self.assertIsNone(d._vision_silence_age())        # disarmed, no pose: no watchdog
        self.assertEqual(d.vision_pose_age(), math.inf)    # the scripts' signal is unchanged

    def test_link_loss_state_is_not_a_disarm(self):
        d, fcu = self.flying()
        arm = d._vision_arm_t
        fcu.publishing = False                 # (review SHOULD-1) time passes around the link loss: a reset would show
        self.clock.sleep(5.0)
        d._on_fcu_state(types.SimpleNamespace(connected=False, armed=False, mode=''))
        self.clock.sleep(5.0)
        d._on_fcu_state(types.SimpleNamespace(connected=True, armed=True, mode='OFFBOARD'))
        self.assertEqual(d._vision_arm_t, arm)
        self.assertGreaterEqual(d._vision_silence_age(), 10.0)

    def test_pose_before_arm_counts_as_in_r2f(self):
        """Poses on the ground before the arm (the normal case): the age runs from the last pose, as in r2f."""
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0, floor=0.0)
        d._on_vpe_pose(pose(0.0, 0.0, 0.0))
        self.clock.on_advance.append(lambda _dt: d._on_vpe_pose(pose(fcu.pos[0], fcu.pos[1], fcu.pos[2])))
        self.assertTrue(self.run_quiet(d.takeoff, 1.0))
        self.assertNotIn('no vpe_fix pose seen yet', self.text())
        self.assertNotIn('Vision lost', self.text())

    def test_vision_pose_age_unchanged(self):
        d, fcu = self.flying()
        self.assertEqual(d.vision_pose_age(), math.inf)    # armed, no pose: still +inf (scripts: silent)
        d._on_vpe_pose(pose(0.1))
        self.assertEqual(d.vision_pose_age(), 0.0)
        self.clock.sleep(0.7)
        self.assertAlmostEqual(d.vision_pose_age(), 0.7)
        self.assertAlmostEqual(d._vision_silence_age(), 0.7)


class S4ControlR2F(T.Base):
    """The same no-pose flights on r2f: the watchdog never fires (the S4 finding)."""
    drone_py = R2F_DRONE

    def test_r2f_flying_without_any_pose_never_lands(self):
        d, fcu = self.flying()
        self.assertTrue(self.run_quiet(d.fly_to, 8.0, 0.0, 1.0))
        self.assertNotIn('Vision lost', self.text())
        self.assertFalse(hasattr(d, '_vision_silence_age'))

    def test_r2f_safe_land_without_any_pose_flies_the_approach(self):
        d, fcu = self.flying()
        self.clock.sleep(3.5)
        self.run_quiet(d.safe_land, x=0.5, y=0.5)
        self.assertIn('Precision approach', self.text())


if __name__ == '__main__':
    unittest.main()
