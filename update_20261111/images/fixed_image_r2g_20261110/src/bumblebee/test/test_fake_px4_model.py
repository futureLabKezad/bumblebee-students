"""Table-driven tests of the bounded command model; no ROS or flight."""
import unittest
from fake_px4_model import Px4Model


class TestPx4Model(unittest.TestCase):
    def test_ground_offboard_without_stream(self):
        m = Px4Model()
        self.assertTrue(m.command_mode(1., 'OFFBOARD'))
        self.assertEqual(m.intended_mode, 'OFFBOARD')
        self.assertFalse(m.command_arm(1., True))
        self.assertIn('setpoint', m.statustext[-1][1])

    def test_arm_denial_table(self):
        for mode in ['AUTO.LAND', 'AUTO.RTL', 'AUTO.DESCEND', 'DESCEND']:
            with self.subTest(mode=mode):
                m = Px4Model(mode=mode)
                m.setpoint(1., (0., 0., 0.))
                self.assertFalse(m.command_arm(1., True))
                self.assertFalse(m.armed)
                self.assertTrue(m.statustext)

    def test_arm_setpoint_freshness_boundary(self):
        for age, accepted in [(0., True), (.999, True), (1., False), (1.01, False)]:
            with self.subTest(age=age):
                m = Px4Model(mode='OFFBOARD')
                m.setpoint(1., (0., 0., 0.))
                self.assertEqual(m.command_arm(1. + age, True), accepted)

    def test_nonforced_disarm_ground_only(self):
        for z, accepted in [(.6, True), (.65, True), (.71, False), (1.2, False)]:
            with self.subTest(z=z):
                m = Px4Model(armed=True, pose=(0., 0., z), floor_z=.6)
                self.assertEqual(m.command_arm(1., False), accepted)
                self.assertEqual(m.armed, not accepted)
        m = Px4Model(armed=True)
        self.assertFalse(m.command_arm(1., False, deny_disarm=True))

    def test_offboard_loss_action_table(self):
        for action, mode in [(0, 'POSCTL'), (4, 'AUTO.LAND')]:
            with self.subTest(action=action):
                m = Px4Model(mode='OFFBOARD', armed=True, obl_rc_act=action)
                m.setpoint(1., (0., 0., 1.))
                m.tick(1.999)
                self.assertEqual(m.mode, 'OFFBOARD')
                m.tick(2.)
                self.assertEqual(m.mode, mode)
                self.assertEqual(m.intended_mode, 'OFFBOARD')

    def test_retained_intention_can_resume_both_fallbacks(self):
        for action, fallback in [(0, 'POSCTL'), (4, 'AUTO.LAND')]:
            with self.subTest(action=action):
                m = Px4Model(mode='OFFBOARD', armed=True, obl_rc_act=action,
                             resume_offboard=True)
                m.setpoint(1., (0., 0., 1.))
                m.tick(2.)
                self.assertEqual(m.mode, fallback)
                self.assertEqual(m.intended_mode, 'OFFBOARD')
                m.setpoint(2.01, (0., 0., 1.))
                self.assertEqual(m.mode, 'OFFBOARD')
                self.assertTrue(m.armed)
                self.assertFalse(m.offboard_fallback)
                m.tick(3.01)
                self.assertEqual(m.mode, fallback)
                self.assertFalse(any(kind == 'arm' for _, kind, _ in m.events))

    def test_explicit_pilot_or_land_command_prevents_resume(self):
        for mode, method in [('ALTCTL', 'pilot_mode'),
                             ('AUTO.LAND', 'pilot_mode'),
                             ('AUTO.LAND', 'command_mode')]:
            with self.subTest(mode=mode, method=method):
                m = Px4Model(mode='OFFBOARD', armed=True, obl_rc_act=4,
                             resume_offboard=True)
                m.setpoint(1., (0., 0., 1.))
                m.tick(2.)
                getattr(m, method)(2.1, mode)
                m.setpoint(2.2, (0., 0., 1.))
                self.assertEqual(m.mode, mode)
                self.assertEqual(m.intended_mode, mode)
                self.assertFalse(m.offboard_fallback)

    def test_resume_remains_opt_in(self):
        for action, fallback in [(0, 'POSCTL'), (4, 'AUTO.LAND')]:
            with self.subTest(action=action):
                m = Px4Model(mode='OFFBOARD', armed=True, obl_rc_act=action)
                m.setpoint(1., (0., 0., 1.))
                m.tick(2.)
                m.setpoint(2.01, (0., 0., 1.))
                self.assertEqual(m.mode, fallback)

    def test_resume_cannot_rearm_after_landing_disarm(self):
        m = Px4Model(mode='OFFBOARD', armed=True, obl_rc_act=4,
                     resume_offboard=True, dynamics=True)
        m.setpoint(0., (0., 0., 0.))
        m.tick(1.)
        m.tick(3.)
        self.assertFalse(m.armed)
        self.assertEqual(m.events[-1][2], 'auto_disarm_land')
        m.setpoint(3.01, (0., 0., 1.))
        self.assertEqual(m.mode, 'OFFBOARD')
        self.assertFalse(m.armed)
        self.assertFalse(any(kind == 'arm' for _, kind, _ in m.events))

    def test_descent_and_two_seconds_touchdown_disarm(self):
        m = Px4Model(mode='AUTO.LAND', armed=True, pose=(0., 0., 1.), dynamics=True)
        m.tick(1.)
        self.assertEqual(m.pose[2], .5)
        m.tick(2.)
        self.assertEqual(m.pose[2], 0.)
        self.assertTrue(m.armed)
        m.tick(3.999)
        self.assertTrue(m.armed)
        m.tick(4.)
        self.assertFalse(m.armed)
        self.assertEqual(m.events[-1][2], 'auto_disarm_land')

    def test_thirty_second_preflight_auto_disarm(self):
        m = Px4Model(dynamics=True)
        self.assertTrue(m.command_arm(0., True))
        m.tick(29.999)
        self.assertTrue(m.armed)
        m.tick(30.)
        self.assertFalse(m.armed)
        self.assertEqual(m.events[-1][2], 'auto_disarm_preflight')

    def test_airborne_is_not_preflight_disarmed(self):
        m = Px4Model(armed=True, pose=(0., 0., 1.), dynamics=True)
        m.tick(31.)
        self.assertTrue(m.armed)

    def test_disconnection_is_unknown_not_disarm(self):
        m = Px4Model(mode='OFFBOARD', armed=True)
        m.connected = False
        self.assertEqual(m.heartbeat(), (False, False, ''))
        self.assertTrue(m.armed)
        m.connected = True
        self.assertEqual(m.heartbeat(), (True, True, 'OFFBOARD'))

    def test_rejected_inflight_offboard_preserves_pilot_mode(self):
        m = Px4Model(mode='POSCTL', armed=True)
        self.assertFalse(m.command_mode(1., 'OFFBOARD'))
        self.assertEqual(m.mode, 'POSCTL')
        self.assertEqual(m.intended_mode, 'POSCTL')


if __name__ == '__main__':
    unittest.main()
