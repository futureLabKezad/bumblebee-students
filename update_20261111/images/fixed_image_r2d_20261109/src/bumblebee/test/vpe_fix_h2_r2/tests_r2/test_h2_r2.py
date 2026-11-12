#!/usr/bin/env python3
"""H2 round 2: tests of the candidate after the review (30.10.2026).

Env:
  H2_TARGET    round-2 candidate vpe_fix.py
  H2_CONTROL   original vpe_fix.py 7f107882
  H2_EVAL      folder with the round-2 H3 evaluator s1_eval.py and original/s1_eval.py
  H2_OUT       folder for replay logs
  H2_REAL_S1   folder with the real session-1 logs (optional)

Review findings covered here:
  HIGH  no cache value or /parameter_events update ever drops an unconfirmed override (tests r2*, r3b, r4d, r7);
        the guarantee "after the disarm edge, revert_all or TTL PX4 ends at the original, or the evaluator says STOP"
        is checked over a matrix of every pair of MAVROS behaviours x later events x ends (test_r10_*)
  LOW   no TTL for an unconfirmed entry in the air, no write of its original while armed (tests r8*; the write count
        against 7f107882 is in test_in_air_writes.py)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench as B  # noqa: E402
from bench import NAME, ORIG, REQ, TIMEOUT, NOT_SENT, boot, run_eval, f32  # noqa: E402

TARGET = B.load(os.environ['H2_TARGET'], 'vpe_fix_r2_candidate')
CONTROL = B.load(os.environ['H2_CONTROL'], 'vpe_fix_r2_control')
EVAL_NEW = B.load(os.path.join(os.environ['H2_EVAL'], 's1_eval.py'), 's1_eval_r2')
EVAL_OLD = B.load(os.path.join(os.environ['H2_EVAL'], 'original', 's1_eval.py'), 's1_eval_r2_original')
OUT = os.environ['H2_OUT']
REAL = os.environ.get('H2_REAL_S1')
os.makedirs(OUT, exist_ok=True)

RESTORED_U = 'vpe_fix gate: restored MPC_TKO_SPEED=0.8 (%s); was unconfirmed'


class Candidate(unittest.TestCase):
    MOD = TARGET

    def setUp(self):
        self.b = boot(self.MOD)

    def assert_orig(self):
        self.assertAlmostEqual(self.b.px4[NAME], ORIG, places=6)

    def eval_rc(self, tag):
        log = self.b.drone_log(os.path.join(OUT, 'r2_%s.log' % tag))
        return run_eval(EVAL_NEW, log)

    # ------------------------------------------------------------ 1 (round 1 test_1, 1b, 1c)
    def test_r1_timeout_applied_in_air_event_does_not_confirm_restored_on_disarm(self):
        b = self.b
        b.arm('OFFBOARD')                      # in flight: a profile write, allowed while armed as before
        b.plan = ['timeout_applied', 'timeout']
        r = b.set(REQ, ttl=5.0)
        self.assertEqual((r.success, r.message), (False, TIMEOUT))
        e = b.entry()
        self.assertTrue(e is not None and e.unconfirmed)
        self.assertAlmostEqual(e.original, ORIG, places=6)
        self.assertEqual(b.lines('set MPC_TKO_SPEED=0.3 failed, outcome unknown'),
                         ['vpe_fix gate: set MPC_TKO_SPEED=0.3 failed, outcome unknown (future timeout after 6.0s); '
                          'override kept UNCONFIRMED (orig=0.8): restored on disarm, revert_all or TTL, never while '
                          'armed'])
        self.assertEqual(b.fire_ttl(), 0, 'no TTL for an unconfirmed entry in the air')
        n = len(b.writes)
        b.step(5.0)
        b.event([NAME], changed=True)          # PX4 shows 0.3: information only
        self.assertTrue(b.entry() is e and e.unconfirmed)
        self.assertEqual(b.lines('confirmed'), [])
        self.assertEqual(len(b.writes), n)
        b.disarm('OFFBOARD')
        self.assert_orig()
        self.assertIsNone(b.entry())
        self.assertEqual(b.lines('restored MPC_TKO_SPEED'), [RESTORED_U % 'disarmed'])
        self.assertEqual([(w[2], w[4]) for w in b.writes_while_armed()],
                         [(NAME, 'timeout_applied'), (NAME, 'timeout')])

    def test_r1b_mavros_success_false_is_unknown_too(self):
        b = self.b
        b.plan = ['mavros_false', 'timeout_applied']
        self.assertFalse(b.set(REQ).success)
        self.assertTrue(b.entry().unconfirmed)
        b.arm_disarm()
        self.assert_orig()
        self.assertEqual(b.lines('restored MPC_TKO_SPEED'), [RESTORED_U % 'disarmed'])

    def test_r1c_value_seen_during_the_call_still_unconfirmed(self):
        b = self.b
        b.plan = ['timeout_event', 'timeout']
        b.set(REQ)
        self.assertTrue(b.entry().unconfirmed)
        b.arm_disarm()
        self.assert_orig()

    # ------------------------------------------------------------ 2 (round 1 test_2..2e)
    def test_r2_original_seen_after_failure_never_drops(self):
        """HIGH: the round-1 'dropped' path is gone; one harmless write of the original on disarm"""
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        b.step(2.0)
        b.event([NAME], changed=True)          # PX4 value read after the failure: the original
        self.assertTrue(b.entry() is not None and b.entry().unconfirmed)
        self.assertEqual(b.lines('dropped'), [])
        n = len(b.writes)
        b.arm_disarm()
        self.assertEqual([(w[2], round(w[3], 3), w[1]) for w in b.writes[n:]], [(NAME, 0.8, False)])
        self.assert_orig()

    def test_r2b_noop_on_old_cache_value_never_drops_and_logs(self):
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        r = b.set(float(ORIG))
        self.assertTrue(r.success and r.message.startswith('noop'))
        self.assertTrue(b.entry().unconfirmed)
        self.assertEqual(b.lines('kept UNCONFIRMED (orig=0.8, requested 0.3)'),
                         ['vpe_fix gate: noop MPC_TKO_SPEED=0.8, override with unknown write outcome kept UNCONFIRMED '
                          '(orig=0.8, requested 0.3): restored on disarm, revert_all or TTL'])
        b.arm_disarm()
        self.assertEqual([(w[2], round(w[3], 3), w[4]) for w in b.writes[-1:]], [(NAME, 0.8, 'ok')])
        self.assert_orig()

    def test_r2c_third_value_kept_and_restored(self):
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        b.px4[NAME] = f32(0.5)
        b.event([NAME], changed=True)
        self.assertTrue(b.entry().unconfirmed)
        b.arm_disarm()
        self.assert_orig()

    def test_r2d_not_sent_dropped_as_before(self):
        b = self.b
        b.plan = ['not_sent', 'not_sent']
        r = b.set(REQ)
        self.assertEqual((r.success, r.message), (False, NOT_SENT))
        self.assertIsNone(b.entry())
        self.assertEqual(len(b.lines('set MPC_TKO_SPEED=0.3 failed, not sent')), 1)

    def test_r2e_sent_then_service_gone_is_unknown(self):
        b = self.b
        b.plan = ['timeout_applied', 'not_sent']
        r = b.set(REQ)
        self.assertEqual(r.message, '%s (attempt 1: %s)' % (NOT_SENT, TIMEOUT))
        self.assertTrue(b.entry().unconfirmed)

    # ------------------------------------------------------------ 3 (round 1 test_3, 3b)
    def test_r3_mavros_restart_applied_stays_unconfirmed(self):
        b = self.b
        b.plan = ['crash_applied']
        b.set(REQ)
        b.step(40.0)
        b.respawn()
        self.assertTrue(b.entry().unconfirmed)
        self.assertEqual(b.lines('vpe_fix gate: restored'), [], 'connected=False is never a disarm')
        b.arm_disarm()
        self.assert_orig()

    def test_r3b_mavros_restart_not_applied_never_drops(self):
        b = self.b
        b.plan = ['crash']
        b.set(REQ)
        b.step(40.0)
        b.respawn()                            # the pull shows the original
        self.assertTrue(b.entry() is not None and b.entry().unconfirmed)
        n = len(b.writes)
        b.arm_disarm()
        self.assertEqual(len(b.writes), n + 1, 'one harmless write of the original on the ground')
        self.assertFalse(b.writes[-1][1])
        self.assert_orig()

    # ------------------------------------------------------------ 4 (round 1 test_4..4h)
    def test_r4_revert_all_restores_unconfirmed(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ)
        r = b.revert_all()
        self.assertEqual((r.success, r.message), (True, 'reverted 1 override(s) point-precise'))
        self.assert_orig()
        self.assertEqual(b.lines('restored MPC_TKO_SPEED'), [RESTORED_U % 'explicit_revert_all'])

    def test_r4b_revert_all_unconfirmed_px4_unchanged_is_harmless(self):
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        b.revert_all()
        self.assert_orig()
        self.assertIsNone(b.entry())

    def test_r4c_ttl_on_ground_restores_unconfirmed(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ, ttl=5.0)
        self.assertEqual(b.fire_ttl(), 1)
        self.assert_orig()
        self.assertEqual(b.lines('restored MPC_TKO_SPEED'), [RESTORED_U % 'ttl_expired'])

    def test_r4d_event_never_cancels_ttl(self):
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ, ttl=5.0)
        b.event([NAME], changed=True)
        self.assertIsNotNone(b.entry())
        self.assertEqual(b.fire_ttl(), 1)
        self.assertIsNone(b.entry())
        self.assert_orig()

    def test_r4e_persistent_unconfirmed_kept_on_disarm_restored_by_revert_all(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ, persistent=True)
        b.arm_disarm()
        self.assertAlmostEqual(b.px4[NAME], REQ, places=6)
        b.revert_all()
        self.assert_orig()

    def test_r4f_shutdown_revert_on_ground_restores_unconfirmed(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ)
        b.node._revert_all(reason='shutdown')
        self.assert_orig()

    def test_r4g_later_successful_write_is_an_ordinary_override(self):
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        r = b.set(REQ)
        self.assertTrue(r.success)
        self.assertEqual(r.original_value, ORIG)
        self.assertFalse(b.entry().unconfirmed)
        b.arm_disarm()
        self.assert_orig()

    def test_r4h_success_after_unknown_never_dropped_by_a_late_old_value(self):
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        b.plan = ['ok_noevent']
        self.assertTrue(b.set(REQ).success)
        b.event([NAME], values={NAME: ORIG})
        self.assertIsNotNone(b.entry())
        b.arm_disarm()
        self.assert_orig()

    # ------------------------------------------------------------ 5 safety rules kept (round 1 test_5)
    def test_r5_ev_ctrl_guard_and_first_write_wins_kept(self):
        b = self.b
        b.px4['EKF2_EV_CTRL'] = 15.0
        b.event(['EKF2_EV_CTRL'])
        b.arm('OFFBOARD')
        r = b.set(0.0, name='EKF2_EV_CTRL', ptype=0)
        self.assertFalse(r.success)
        self.assertIn('refused', r.message)
        self.assertEqual([w for w in b.writes if w[2] == 'EKF2_EV_CTRL'], [])
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ)
        r = b.set(0.5)
        self.assertTrue(r.success)
        self.assertAlmostEqual(r.original_value, ORIG, places=6)
        b.disarm('OFFBOARD')
        self.assert_orig()

    # ------------------------------------------------------------ 6 replay of 30.10 (round 1 test_6)
    @staticmethod
    def replay(mod, end):
        b = boot(mod)
        b.plan = ['crash_applied', 'timeout']
        r1 = b.set(REQ)
        b.step(40.0)
        b.respawn()
        b.step(5.0)
        r2 = b.set(REQ)
        if end == 'disarm':
            b.arm_disarm()
        elif end == 'revert_all':
            b.revert_all()
        return b, r1, r2

    def test_r6_replay_30_10(self):
        for end in ('stop', 'disarm', 'revert_all'):
            with self.subTest(end=end):
                b, r1, r2 = self.replay(self.MOD, end)
                self.assertEqual((r1.success, r1.message), (False, TIMEOUT))
                self.assertEqual((r2.success, r2.message), (True, 'noop: already 0.3'))
                self.assertEqual(len(b.lines('noop MPC_TKO_SPEED=0.3, override with unknown write outcome kept')), 1)
                log = b.drone_log(os.path.join(OUT, 'replay_r2_%s.log' % end))
                rc, out = run_eval(EVAL_NEW, log)
                with open(log + '.eval_r2.txt', 'w') as f:
                    f.write('rc=%d\n%s' % (rc, out))
                if end == 'stop':
                    self.assertAlmostEqual(b.px4[NAME], REQ, places=6)
                    self.assertTrue(b.entry() is not None and b.entry().unconfirmed)
                    self.assertEqual(rc, 1, out)
                    self.assertIn('ИСХОД ЗАПИСИ НЕ ИЗВЕСТЕН', out)
                else:
                    self.assertAlmostEqual(b.px4[NAME], ORIG, places=6)
                    self.assertIsNone(b.entry())
                    self.assertEqual(rc, 0, out)

    # ------------------------------------------------------------ 7 the review probe (stale event, then the truth)
    def test_r7_review_probe_stale_original_then_real_value(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ)
        b.step(1.0)
        b.event([NAME], values={NAME: ORIG})   # a read made BEFORE the write, processed after the failure
        b.step(0.1)
        b.event([NAME], changed=True)          # PX4 truth = 0.3
        self.assertTrue(b.entry() is not None and b.entry().unconfirmed)
        b.arm_disarm()
        self.assert_orig()
        rc, out = self.eval_rc('probe')
        self.assertEqual(rc, 0, out)

    # ------------------------------------------------------------ 8 armed (LOW)
    def test_r8_unknown_in_air_no_ttl_restored_on_disarm(self):
        b = self.b
        b.arm('OFFBOARD')
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ, ttl=2.0)
        self.assertIsNone(b.entry().ttl_timer)
        self.assertEqual(b.fire_ttl(), 0)
        self.assertEqual(len(b.writes), 2)
        b.disarm('OFFBOARD')
        self.assert_orig()
        self.assertEqual([w[4] for w in b.writes_while_armed()], ['timeout_applied', 'timeout'])

    def test_r8b_ttl_due_in_air_held_until_disarm(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ, ttl=5.0)                    # on the ground: TTL armed
        b.arm('OFFBOARD')
        n = len(b.writes)
        self.assertEqual(b.fire_ttl(), 1)      # TTL due in the air
        self.assertEqual(len(b.writes), n, 'no write while armed')
        self.assertEqual(b.lines('held'), ['vpe_fix gate: restore of MPC_TKO_SPEED=0.8 (ttl_expired) held: write '
                                           'outcome unknown and FCU armed, restored on disarm'])
        self.assertEqual(b.fire_ttl(), 0, 'the timer is cancelled once held')
        self.assertTrue(b.entry().unconfirmed)
        rc, out = self.eval_rc('ttl_held')
        self.assertEqual(rc, 1, out)           # until the disarm: STOP
        b.disarm('OFFBOARD')
        self.assert_orig()
        self.assertEqual(b.lines('restored MPC_TKO_SPEED'), [RESTORED_U % 'disarmed'])
        rc, out = self.eval_rc('ttl_held_disarmed')
        self.assertEqual(rc, 0, out)

    def test_r8c_revert_all_in_air_held_until_disarm(self):
        b = self.b
        b.arm('OFFBOARD')
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ)
        n = len(b.writes)
        b.revert_all()
        self.assertEqual(len(b.writes), n)
        self.assertAlmostEqual(b.px4[NAME], REQ, places=6)
        self.assertEqual(len(b.lines('restore of MPC_TKO_SPEED=0.8 (explicit_revert_all) held')), 1)
        rc, out = self.eval_rc('revert_held')
        self.assertEqual(rc, 1, out)
        b.disarm('OFFBOARD')
        self.assert_orig()

    def test_r8d_shutdown_in_air_held(self):
        b = self.b
        b.arm('OFFBOARD')
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ)
        n = len(b.writes)
        b.node._revert_all(reason='shutdown')
        self.assertEqual(len(b.writes), n)
        rc, out = self.eval_rc('shutdown_held')
        self.assertEqual(rc, 1, out)
        self.assertIn('ИСХОД ЗАПИСИ НЕ ИЗВЕСТЕН', out)

    def test_r8e_ordinary_override_ttl_in_air_unchanged(self):
        """a successful write keeps the 7f107882 TTL behaviour, also after an unknown outcome"""
        b = self.b
        b.plan = ['timeout', 'timeout']
        b.set(REQ)
        b.arm('OFFBOARD')
        b.plan = ['ok']
        self.assertTrue(b.set(0.4, ttl=3.0).success)
        self.assertFalse(b.entry().unconfirmed)
        self.assertEqual(b.fire_ttl(), 1)
        self.assertEqual([(round(w[3], 3), w[1]) for w in b.writes[-1:]], [(0.8, True)])
        self.assert_orig()

    def test_r8f_fcu_state_unknown_after_armed_counts_as_armed(self):
        b = self.b
        b.plan = ['timeout_applied', 'timeout']
        b.set(REQ, ttl=5.0)
        b.arm('OFFBOARD')
        b.state(False, False, '')              # MAVROS placeholder: never a disarm, last armed kept
        n = len(b.writes)
        b.fire_ttl()
        b.revert_all()
        self.assertEqual(len(b.writes), n)
        b.state(True, False, 'AUTO.LAND')      # reconnect after landing: the disarm edge
        self.assert_orig()

    # ------------------------------------------------------------ 9 the "not sent" string coupling
    def test_r9_param_set_once_not_sent_string_is_the_constant(self):
        """_param_set_once (unchanged 7f107882 code) returns the literal; the H2 branch compares with the constant"""
        node = self.b.node
        ok, msg = type(node)._param_set_once(node, NAME, REQ, 1, timeout=0.0)   # FakeClient: service never there
        self.assertEqual((ok, msg), (False, self.MOD._SET_NOT_SENT))

    # ------------------------------------------------------------ 11 a disarm edge during the call
    def test_r11_disarm_restore_during_the_call_then_unknown_kept_again(self):
        """the disarm edge restores the entry between attempt 1 and 2; attempt 2 lands with an unknown outcome:
        the entry is put back, the evaluator says STOP until a later restore, revert_all brings the original"""
        b = self.b
        b.arm('OFFBOARD')
        fake, done = b.node._param_set_once, []

        def once(name, value, ptype, timeout=6.0):
            res = fake(name, value, ptype, timeout)
            if not done:
                done.append(1)
                b.plan.insert(0, 'ok')         # the restore of the disarm edge
                b.state(True, False, 'OFFBOARD')
            return res
        b.node._param_set_once = once
        b.plan = ['timeout_applied', 'timeout_applied']
        b.set(REQ)
        self.assertAlmostEqual(b.px4[NAME], REQ, places=6)
        self.assertTrue(b.entry() is not None and b.entry().unconfirmed)
        rc, out = self.eval_rc('race')
        self.assertEqual(rc, 1, out)
        b.revert_all()
        self.assert_orig()
        rc, out = self.eval_rc('race_reverted')
        self.assertEqual(rc, 0, out)

    # ------------------------------------------------------------ 10 the guarantee over a matrix
    def test_r10_guarantee_matrix(self):
        """every pair of MAVROS behaviours for the two attempts x later events x end: PX4 at the original, or the
        evaluator says STOP (never a silent wrong value); and with MAVROS alive at the end PX4 is at the original.
        Ends: disarm (arm, disarm), revert_all on the ground, TTL due on the ground, stop (nothing: the 30.10 end)."""
        bad, n = [], 0
        for p1 in B.BEHAVIOURS:
            for p2 in B.BEHAVIOURS:
                if p1 in ('ok', 'ok_noevent') and p2 != 'ok':
                    continue                   # attempt 2 not used
                for ev in ('none', 'stale_orig', 'real', 'respawn', 'noop'):
                    for end in ('disarm', 'revert_all', 'ttl', 'stop'):
                        n += 1
                        b, rc, out = run_case(self.MOD, p1, p2, ev, end)
                        at_orig = abs(b.px4[NAME] - ORIG) < 1e-6
                        if not (at_orig or rc == 1):
                            bad.append((p1, p2, ev, end, round(b.px4[NAME], 3), rc))
                        if end != 'stop' and b.alive and not at_orig:
                            bad.append(('alive-not-restored', p1, p2, ev, end))
                        if at_orig and end != 'stop' and rc not in (0, 1):
                            bad.append(('rc', p1, p2, ev, end, rc))
        self.assertEqual(bad, [], '; '.join(map(str, bad)))
        self.assertGreater(n, 400)


def run_case(mod, p1, p2, ev, end):
    b = boot(mod)
    b.plan = [p1, p2]
    ttl = 5.0 if end == 'ttl' else 0.0
    b.set(REQ, ttl=ttl)
    b.plan = []
    b.step(1.0)
    if ev == 'stale_orig':
        b.event([NAME], values={NAME: ORIG})
    elif ev == 'real':
        b.event([NAME], changed=True)
    elif ev == 'respawn':
        b.step(40.0)
        b.respawn()
    elif ev == 'noop':
        b.alive = True
        b.event([NAME], changed=True)
        b.set(REQ, ttl=ttl)                    # the kit repeats the same request (a write if PX4 did not take it)
    if end == 'disarm':
        b.arm_disarm()
    elif end == 'revert_all':
        b.revert_all()
    elif end == 'ttl':
        b.fire_ttl()
    log = b.drone_log(os.path.join(OUT, 'matrix_last.log'))
    rc, out = run_eval(EVAL_NEW, log)
    return b, rc, out


class Control(unittest.TestCase):
    """the same inputs on the original 7f107882: the tests above are not vacuous"""

    def test_original_replay_silently_leaves_0_3(self):
        b, r1, r2 = Candidate.replay(CONTROL, 'disarm')
        self.assertAlmostEqual(b.px4[NAME], REQ, places=6)
        log = b.drone_log(os.path.join(OUT, 'replay_original_disarm.log'))
        rc_old, _ = run_eval(EVAL_OLD, log)
        rc_new, out_new = run_eval(EVAL_NEW, log)
        self.assertEqual(rc_old, 0, 'the old pairs check misses it (finding Н3)')
        self.assertEqual(rc_new, 1, out_new)

    def test_original_breaks_the_guarantee_matrix(self):
        bad = 0
        for p1, p2 in (('timeout_applied', 'timeout'), ('crash_applied', 'not_sent'), ('timeout_event', 'timeout')):
            for ev in ('none', 'real', 'respawn'):
                b, rc, out = run_case(CONTROL, p1, p2, ev, 'disarm')
                if not (abs(b.px4[NAME] - ORIG) < 1e-6):
                    bad += 1
        self.assertEqual(bad, 9, 'PX4 left at 0.3 after the disarm in every one of these cases on 7f107882')


@unittest.skipUnless(REAL, 'H2_REAL_S1 not set')
class RealLogs(unittest.TestCase):
    def test_real_logs_still_stop(self):
        for fn in ('w1_watch_2718616360.log', 'step08_t5a_apply_1117417889.log'):
            with self.subTest(log=fn):
                path = os.path.join(REAL, fn)
                rc_old, _ = run_eval(EVAL_OLD, path)
                rc_new, out_new = run_eval(EVAL_NEW, path)
                self.assertEqual(rc_old, 0)
                self.assertEqual(rc_new, 1, out_new)
                self.assertIn('ИСХОД ЗАПИСИ НЕ ИЗВЕСТЕН', out_new)
                self.assertIn('MPC_TKO_SPEED', out_new)


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, descriptions=False))
