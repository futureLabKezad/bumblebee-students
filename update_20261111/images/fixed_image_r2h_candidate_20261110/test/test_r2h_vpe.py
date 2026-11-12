#!/usr/bin/env python3
"""r2h B1/B2 (no ROS): the REAL vpe_fix.VpeFix class on the offline bench (rosstub, never spun), driven by a small
event simulation: the node's own timers (30 Hz publish, 1 Hz gate tick, 0.1 s state watchdog) fire when due, the
detector sends /aruco_detect/markers_used (and an accepted /aruco_map/pose when a marker is used) at 24 Hz, MAVROS
/mavros/state at 1 Hz. ROS time active (SITL-like), so the P1 state ages run on the bench clock.
Every scenario runs on r2h and, as a control, on r2g's vpe_fix (3b8a93d4).
Run: python3 -B test/test_r2h_vpe.py -v   (from the r2h folder)
"""
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'src/bumblebee/test/vpe_fix_h2_r2/tests_r2'))
import bench as B  # noqa: E402
import rosstub  # noqa: E402

R2H_VPE = ROOT / 'src/bumblebee/src/python/vpe_fix.py'
R2G_VPE = Path('/work/fixed_image_r2g_20261110/src/bumblebee/src/python/vpe_fix.py')
assert 'fixed_image_r2h_candidate_20261110' in str(R2H_VPE), R2H_VPE
R2H = B.load(str(R2H_VPE), 'vpe_fix_r2h')
R2G = B.load(str(R2G_VPE), 'vpe_fix_r2g_control')
NS = B.NS
FRAME = 1.0 / 24.0


def pose_msg(x, y=0.0, z=1.0):
    m = rosstub.PoseWithCovarianceStamped()
    m.pose.pose.position.x, m.pose.pose.position.y, m.pose.pose.position.z = x, y, z
    return m


class Sim:
    """detector(t) -> (markers_used, (x, y, z) or None) for a frame at t s after the start; state(t) -> (connected,
    armed, mode) or None (no State that second)."""

    def __init__(self, mod, detector, state=lambda t: (True, True, 'OFFBOARD'), yaw_locked=True, frame=FRAME):
        self.frame = frame
        self.b = B.boot(mod)
        self.clk = self.b.clock
        self.clk.ros_time_is_active = True
        self.node = self.b.node
        self.node.yaw_locked_callback(rosstub._Simple(yaw_locked))
        self.detector, self.state = detector, state
        self.t0 = self.clk.t_ns
        for tm in self.node.timers:                    # timers count from the start of the scenario
            tm.next_due_ns = self.t0 + int(round(tm.period * NS))
        self.next_frame = self.t0
        self.next_state = self.t0
        self.frames = []

    def t(self):
        return (self.clk.t_ns - self.t0) / NS

    def run(self, seconds):
        end = self.t0 + int(seconds * NS) if not self.frames else self.clk.t_ns + int(seconds * NS)
        while True:
            due = [tm.next_due_ns for tm in self.node.timers if not tm.cancelled]
            nxt = min(due + [self.next_frame, self.next_state])
            if nxt > end:
                self.clk.t_ns = end
                return
            self.clk.t_ns = nxt
            for tm in list(self.node.timers):          # timers first, in creation order
                if not tm.cancelled and tm.next_due_ns == nxt:
                    tm.cb()
                    tm.next_due_ns += int(round(tm.period * NS))
            if self.next_state == nxt:
                s = self.state(self.t())
                if s is not None:
                    self.b.state(*s)
                self.next_state += NS
            if self.next_frame == nxt:
                n, p = self.detector(self.t())
                if n >= 1 and p is not None:
                    self.node.aruco_map_callback(pose_msg(*p))
                self.node.markers_used_callback(rosstub._Simple(n))
                self.frames.append((self.t(), n))
                self.next_frame += int(round(self.frame * NS))

    def sent(self, after=0.0):
        return [((t - self.t0) / NS, m) for t, m in self.node.vpe_pub.sent if (t - self.t0) / NS >= after]

    def pauses(self, after=0.0, until=None):
        ts = [t for t, _ in self.sent(after) if until is None or t <= until]
        return [(a, b - a) for a, b in zip(ts, ts[1:]) if b - a > 0.4]


def blink(on=0.4, off=0.3, x=0.0):
    """near-floor detector: one marker for `on` s, then empty frames for `off` s (markers_used 0)"""
    def det(t):
        return (1, (x, 0.0, 0.3)) if (t % (on + off)) < on else (0, None)
    return det


class B1Gate(unittest.TestCase):
    def test_blinking_single_marker_keeps_the_gate_open(self):
        """T42: one marker seen 0.4 s, missed 0.3 s (empty frames). r2h: no publish pause > 0.4 s; r2g (control):
        the 1 Hz check closes the gate for whole seconds."""
        s = Sim(R2H, blink())
        s.run(20.0)
        self.assertEqual(s.pauses(after=1.0), [])
        self.assertGreater(len(s.sent(after=1.0)), 20 * 30 * 0.5)
        c = Sim(R2G, blink())
        c.run(20.0)
        long_pauses = [d for _, d in c.pauses(after=1.0) if d >= 0.9]
        self.assertTrue(long_pauses, c.pauses(after=1.0))

    def test_gate_opens_on_the_first_frame_not_at_the_tick(self):
        """markers come back at t=2.3 s: r2h opens on that frame (+ <= one 30 Hz tick), r2g waits for the 1 Hz tick."""
        det = lambda t: (0, None) if t < 2.3 else (2, (0.0, 0.0, 1.0))
        s = Sim(R2H, det)
        s.run(4.0)
        first = s.sent(after=1.0)[0][0]
        self.assertLess(first - 2.3, 0.15)            # opening + B2 needs 3 fresh poses (3 frames = 0.125 s)
        c = Sim(R2G, det)
        c.run(4.0)
        self.assertGreaterEqual(c.sent(after=1.0)[0][0], 3.0 - 1e-6)

    def test_gate_still_closes_when_markers_stay_away(self):
        """markers stop at t=3 s (empty frames continue): the gate closes after 1.5 s + 0.5 s hysteresis (+1 frame)"""
        det = lambda t: (1, (0.0, 0.0, 1.0)) if t < 3.0 else (0, None)
        s = Sim(R2H, det)
        s.run(8.0)
        closes = [(t, m) for t, lvl, m in [((tt - s.t0) / NS, lvl, m) for tt, lvl, m in s.node.logs]
                  if 'vision_bad (publish suspended)' in m]
        self.assertTrue(closes)
        last_marker = 3.0 - FRAME                          # the last frame with a marker (frames every 1/24 s)
        self.assertGreaterEqual(closes[-1][0], last_marker + 1.5 + 0.5 - FRAME - 1e-6)
        self.assertLessEqual(closes[-1][0], 3.0 + 1.5 + 0.5 + 2 * FRAME)
        self.assertFalse(s.node.vpe_active)
        self.assertEqual(s.sent(after=3.0 + 0.5 + 0.05), [])   # no pose older than 0.5 s is ever sent

    def test_single_marker_without_yaw_lock_stays_closed(self):
        s = Sim(R2H, lambda t: (1, (0.0, 0.0, 1.0)), yaw_locked=False)
        s.run(5.0)
        self.assertEqual(s.sent(after=0.6), [])

    def test_unknown_fcu_state_closes_whatever_the_markers(self):
        """P1 kept: connected=False closes at once and a marker frame does not reopen; no State for > 4.5 s closes"""
        st = lambda t: (True, True, 'OFFBOARD') if t < 3.0 else (False, False, '')
        s = Sim(R2H, lambda t: (2, (0.0, 0.0, 1.0)), state=st)
        s.run(6.0)
        self.assertFalse(s.node.vpe_active)
        self.assertEqual(s.sent(after=3.0 + 0.05), [])
        st2 = lambda t: (True, True, 'OFFBOARD') if t < 2.0 else None
        s2 = Sim(R2H, lambda t: (2, (0.0, 0.0, 1.0)), state=st2)
        s2.run(9.0)
        self.assertEqual(s2.sent(after=2.0 - 0.01 + 4.5 + 0.15), [])

    def test_armed_in_manual_never_publishes(self):
        s = Sim(R2H, lambda t: (2, (0.0, 0.0, 1.0)), state=lambda t: (True, True, 'POSCTL'))
        s.run(4.0)
        self.assertEqual(s.sent(after=0.05), [])

    def test_disarmed_warm_up_unchanged(self):
        s = Sim(R2H, lambda t: (0, None) if t < 1.0 else (1, (0.0, 0.0, -0.08)), state=lambda t: (True, False, 'STABILIZED'))
        s.run(3.0)
        self.assertTrue(s.node.vpe_active)
        self.assertGreater(len(s.sent()), 30)


class B2Reentry(unittest.TestCase):
    P0, P1 = 2.1, 3.1      # the gate stays open in both (1 Hz tick at 3.0 s: multi marker 0.92 s old), only the poses stop

    @classmethod
    def det_with_pause(cls, xs):
        """poses at x=0 until P0, nothing P0..P1 (markers_used 0), then the frames xs, then x=0.01"""
        back = []

        def det(t):
            if t < cls.P0:
                return 2, (0.0, 0.0, 1.0)
            if t < cls.P1:
                return 0, None
            back.append(t)
            k = len(back) - 1
            return 2, (xs[k] if k < len(xs) else 0.01, 0.0, 1.0)
        det.back = back
        return det
    def test_after_a_pause_the_first_samples_are_the_medoid_of_3(self):
        """after the pause the 3rd fresh pose is an outlier (+0.05): r2h sends nothing before 3 fresh poses, then the
        medoid (0.01) for 0.5 s; r2g (control) sends the first pose at once and the outlier next."""
        xs = [0.0, 0.01, 0.06]
        det = self.det_with_pause(xs)
        s = Sim(R2H, det)
        s.run(5.0)
        back = det.back[0]                                                   # the first frame after the pause
        before = [t for t, _ in s.sent(after=self.P0) if t < back]
        self.assertGreater(back - max(before), 0.4)                          # a real pause: PX4 would stop EV
        after = s.sent(after=back)
        t1 = after[0][0]
        self.assertGreaterEqual(t1, back + 2 * FRAME - 1e-6)                 # not before the 3rd fresh pose
        hold = [m.pose.pose.position.x for t, m in after if t < t1 + 0.5 - 1e-6]
        self.assertTrue(hold)
        self.assertTrue(all(abs(x - 0.01) < 1e-9 for x in hold), hold)       # medoid of (0, 0.01, 0.06)
        self.assertIn('resume after', ' '.join(m for _, _, m in s.node.logs))
        cdet = self.det_with_pause(xs)
        c = Sim(R2G, cdet)
        c.run(5.0)
        ca = c.sent(after=cdet.back[0])
        self.assertLess(ca[0][0], cdet.back[0] + FRAME)                      # r2g: the first pose at once
        self.assertIn(0.06, [m.pose.pose.position.x for _, m in ca[:6]])     # and the outlier among the first
    def test_after_the_hold_the_latest_pose_again(self):
        xs = [0.0, 0.01, 0.06]
        s = Sim(R2H, self.det_with_pause(xs))
        s.run(5.0)
        late = [m.pose.pose.position.x for t, m in s.sent(after=4.5)]
        self.assertTrue(late)
        self.assertTrue(all(abs(x - 0.01) < 1e-9 for x in late))           # the latest pose (x=0.01 after xs)

    def test_no_pause_no_medoid(self):
        """a continuous stream: after the start, every sample is the latest pose (B2 is idle)"""
        seq = {}

        def det(t):
            x = round(0.001 * int(t / FRAME), 6)
            seq[round(t, 6)] = x
            return 2, (x, 0.0, 1.0)
        s = Sim(R2H, det)
        s.run(6.0)
        xs = [m.pose.pose.position.x for _, m in s.sent(after=1.0)]
        self.assertEqual(xs, sorted(xs))                                     # monotonic: no held medoid lag pattern
        self.assertEqual(sum('resume after' in m for _, _, m in s.node.logs), 1)   # only the start

    def test_short_gap_below_0p3_is_not_a_pause(self):
        def det(t):
            if 2.0 <= t < 2.2:
                return 0, None
            return 2, (0.0, 0.0, 1.0)
        s = Sim(R2H, det)
        s.run(4.0)
        self.assertEqual(sum('resume after' in m for _, _, m in s.node.logs), 1)

class B2SlowDetector(unittest.TestCase):
    """review M1: the detector rate on the drone may be ~6 Hz (drone.py comment, not proven); the re-entry wait is
    bounded by _REENTRY_MAX_WAIT, so a slow detector is never silenced."""

    def test_4hz_all_good_frames_publish_continuously(self):
        s = Sim(R2H, lambda t: (2, (0.0, 0.0, 1.0)), frame=0.25)
        s.run(30.0)
        c = Sim(R2G, lambda t: (2, (0.0, 0.0, 1.0)), frame=0.25)
        c.run(30.0)
        self.assertEqual(s.pauses(after=1.0), [])
        self.assertGreater(len(s.sent()), 0.95 * len(c.sent()))
        self.assertLess(s.sent()[0][0], 0.25 + R2H._REENTRY_MAX_WAIT + 0.05)

    def test_6hz_every_3rd_frame_empty_publishes_continuously(self):
        k = {'n': 0}

        def det(t):
            k['n'] += 1
            return (0, None) if k['n'] % 3 == 0 else (1, (0.0, 0.0, 1.0))
        s = Sim(R2H, det, frame=1.0 / 6.0)
        s.run(30.0)
        k['n'] = 0
        c = Sim(R2G, det, frame=1.0 / 6.0)
        c.run(30.0)
        self.assertEqual(s.pauses(after=1.0), [])
        self.assertGreater(len(s.sent()), 0.95 * len(c.sent()))

    def test_6hz_after_a_pause_resumes_within_the_max_wait(self):
        def det(t):
            if 3.0 <= t < 4.5:
                return 0, None
            return 2, (0.0, 0.0, 1.0)
        s = Sim(R2H, det, frame=1.0 / 6.0)
        s.run(8.0)
        back = min(t for t, n in s.frames if t >= 4.5 and n > 0)
        first = min(t for t, _ in s.sent(after=back))
        self.assertLessEqual(first - back, R2H._REENTRY_MAX_WAIT + 1.0 / 30.0 + 1e-6)
        self.assertEqual(s.pauses(after=first), [])

    def test_a_frame_missing_during_the_hold_does_not_silence(self):
        """review S1: after a pause, one empty frame inside the 0.5 s medoid hold"""
        def det(t):
            if 2.1 <= t < 3.1:
                return 0, None
            if 3.4 <= t < 3.45:
                return 0, None
            return 2, (0.0, 0.0, 1.0)
        s = Sim(R2H, det)
        s.run(5.0)
        ts = [t for t, _ in s.sent(after=3.1)]
        self.assertTrue(ts)
        self.assertLess(max(b - a for a, b in zip(ts, ts[1:])), 0.1)


class B2Reseed(unittest.TestCase):
    def test_reseed_restarts_the_pose_history(self):
        """review S2: after a reseed the medoid can only use the seed and later poses"""
        b = B.boot(R2H)
        b.clock.ros_time_is_active = True
        n = b.node
        for i in range(5):
            n.aruco_map_callback(pose_msg(0.0))
            b.step(FRAME)
        self.assertEqual(len(n._recent_poses), 3)
        for i in range(20):                       # a consistent new position 0.5 m away: rejected, then reseeded
            n.aruco_map_callback(pose_msg(0.5))
            b.step(FRAME)
            if any('RESEEDED' in m for _, _, m in n.logs):
                break
        self.assertTrue(any('RESEEDED' in m for _, _, m in n.logs))
        self.assertEqual(len(n._recent_poses), 1)
        self.assertAlmostEqual(n._recent_poses[0][1].position.x, 0.5)


if __name__ == '__main__':
    unittest.main()
