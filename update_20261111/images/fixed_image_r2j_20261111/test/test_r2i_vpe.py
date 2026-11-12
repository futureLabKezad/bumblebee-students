#!/usr/bin/env python3
"""r2i (T46, owner 11.11 «Зрение при посадке», no ROS): vpe_fix publishes in AUTO.LAND on the same vision condition
as in OFFBOARD (B1/B2 of r2h); every other armed mode stays silent. The REAL VpeFix class on the offline bench, driven
by the event simulation of test/test_r2h_vpe.py (24 Hz detector, 30 Hz publish timer, 1 Hz /mavros/state).
Every AUTO.LAND scenario runs on r2i and, as the control, on r2h's vpe_fix (/work/fixed_image_r2h_20261110): r2h
stays silent in AUTO.LAND (T45: no vision after LAND).
Run: python3 -B test/test_r2i_vpe.py -v   (from the r2i folder)
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_r2h_vpe as base  # noqa: E402  (its R2H is this folder's vpe_fix: r2i)

B = base.B
Sim = base.Sim
R2I = base.R2H
R2I_VPE = base.R2H_VPE
assert 'fixed_image_r2j_' in str(R2I_VPE), R2I_VPE
R2H_VPE = Path('/work/fixed_image_r2h_20261110/src/bumblebee/src/python/vpe_fix.py')
R2H = B.load(str(R2H_VPE), 'vpe_fix_r2h_control_t46')
FRAME = base.FRAME
MARK = lambda t: (2, (0.0, 0.0, 1.0))


def modes(*steps):
    """steps: (from_s, connected, armed, mode) in time order; the last one with from_s <= t applies"""
    def st(t):
        cur = None
        for a, c, ar, m in steps:
            if t >= a - 1e-9:
                cur = (c, ar, m)
        return cur
    return st


def gaps(ts):
    return max((b - a for a, b in zip(ts, ts[1:])), default=0.0)


class AutoLand(unittest.TestCase):
    def test_offboard_to_auto_land_keeps_publishing(self):
        """OFFBOARD until 3 s, AUTO.LAND after (the script's own /land or a PX4 failsafe land), markers seen:
        r2i publishes on without a gap; control r2h stops at the AUTO.LAND State."""
        st = modes((0, True, True, 'OFFBOARD'), (3, True, True, 'AUTO.LAND'))
        s = Sim(R2I, MARK, state=st)
        s.run(8.0)
        ts = [t for t, _ in s.sent(after=2.0)]
        self.assertGreater(ts[-1], 7.9)
        self.assertLess(gaps(ts), 0.05)
        self.assertEqual(s.node._evaluate_gate(), (True, 'AUTO.LAND + vision_ok'))   # publish stays True: no log line
        c = Sim(R2H, MARK, state=st)
        c.run(8.0)
        self.assertEqual(c.sent(after=3.0 + 0.05), [])
        self.assertIn('armed in manual (no publish)', ' '.join(m for _, _, m in c.node.logs))

    def test_auto_land_from_the_start_publishes(self):
        st = modes((0, True, True, 'AUTO.LAND'))
        s = Sim(R2I, MARK, state=st)
        s.run(4.0)
        self.assertGreater(len(s.sent(after=1.0)), 3.0 * 30 * 0.9)
        c = Sim(R2H, MARK, state=st)
        c.run(4.0)
        self.assertEqual(c.sent(after=0.05), [])

    def test_auto_land_vision_bad_suspends_as_in_offboard(self):
        """markers stop at 4 s (empty frames): the gate closes as in OFFBOARD (>= 1 marker within 1.5 s, B1, + 0.5 s)"""
        det = lambda t: (2, (0.0, 0.0, 1.0)) if t < 4.0 else (0, None)
        when = {}
        for mode in ('OFFBOARD', 'AUTO.LAND'):
            s = Sim(R2I, det, state=modes((0, True, True, mode)))
            s.run(8.0)
            self.assertFalse(s.node.vpe_active, mode)
            self.assertEqual(s.sent(after=4.0 + 0.5 + 0.05), [], mode)       # nothing older than 0.5 s
            closes = [((t - s.t0) / 1e9, m) for t, _, m in s.node.logs if 'vision_bad (publish suspended)' in m]
            self.assertTrue(closes and closes[-1][1].startswith('vpe_fix: %s + vision_bad' % mode), (mode, closes))
            self.assertLessEqual(closes[-1][0], 4.0 + 1.5 + 0.5 + 2 * FRAME, mode)
            when[mode] = closes[-1][0]
        self.assertEqual(when['OFFBOARD'], when['AUTO.LAND'])

    def test_manual_and_other_auto_modes_never_publish(self):
        """armed in STAB, ALTCTL, POSCTL (pilot) or other AUTO modes: silent, as r2h"""
        for mode in ('STABILIZED', 'ALTCTL', 'POSCTL', 'AUTO.LOITER', 'AUTO.RTL', 'AUTO.TAKEOFF', 'ACRO'):
            for mod in (R2I, R2H):
                s = Sim(mod, MARK, state=modes((0, True, True, 'OFFBOARD'), (3, True, True, mode)))
                s.run(6.0)
                self.assertEqual(s.sent(after=3.0 + 0.05), [], mode)
                self.assertFalse(s.node.vpe_active, mode)

    def test_auto_land_to_posctl_closes_at_once(self):
        """the pilot takes over during the landing: the POSCTL State closes the gate at once (P1b)"""
        st = modes((0, True, True, 'OFFBOARD'), (2, True, True, 'AUTO.LAND'), (5, True, True, 'POSCTL'))
        s = Sim(R2I, MARK, state=st)
        s.run(8.0)
        self.assertGreater(len([t for t, _ in s.sent(after=2.0) if t < 5.0]), 80)
        self.assertEqual(s.sent(after=5.0 + 0.05), [])

    def test_auto_land_fcu_state_unknown_closes(self):
        """P1 kept in AUTO.LAND: connected=False closes at once; no State for > 4.5 s closes"""
        s = Sim(R2I, MARK, state=modes((0, True, True, 'AUTO.LAND'), (3, False, False, '')))
        s.run(6.0)
        self.assertEqual(s.sent(after=3.0 + 0.05), [])
        st2 = lambda t: (True, True, 'AUTO.LAND') if t < 2.0 else None
        s2 = Sim(R2I, MARK, state=st2)
        s2.run(9.0)
        self.assertEqual(s2.sent(after=2.0 - 0.01 + 4.5 + 0.15), [])

    def test_disarm_after_landing_is_the_warm_up(self):
        s = Sim(R2I, MARK, state=modes((0, True, True, 'AUTO.LAND'), (3, True, False, 'AUTO.LAND')))
        s.run(5.0)
        self.assertTrue(s.node.vpe_active)
        self.assertIn('disarmed (warm-up)', ' '.join(m for _, _, m in s.node.logs))

    def test_b2_reentry_in_auto_land(self):
        """r2h B2 works in AUTO.LAND too: after a pause the first samples are the medoid"""
        xs = [0.0, 0.01, 0.06]
        det = base.B2Reentry.det_with_pause(xs)
        s = Sim(R2I, det, state=modes((0, True, True, 'AUTO.LAND')))
        s.run(5.0)
        after = s.sent(after=det.back[0])
        t1 = after[0][0]
        hold = [m.pose.pose.position.x for t, m in after if t < t1 + 0.5 - 1e-6]
        self.assertTrue(hold and all(abs(x - 0.01) < 1e-9 for x in hold), hold)


if __name__ == '__main__':
    unittest.main()
