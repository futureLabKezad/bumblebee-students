#!/usr/bin/env python3
"""H2 round 2, review LOW: the candidate adds no PX4 write while armed compared with the original 7f107882.

Every scenario runs twice, on 7f107882 and on the candidate, with the same inputs; the fake MAVROS records every
ParamSetV2 attempt with the armed flag vpe_fix had at the call. Writes while armed: candidate <= original, in every
scenario. Scenarios: the script of every H2 test (round 1 and round 2, without their assertions) and a matrix of
every pair of MAVROS behaviours for the two attempts x armed before/after the request x what happens in the air.
Env: H2_TARGET, H2_CONTROL, H2_OUT (the table goes to H2_OUT/in_air_writes.txt).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bench as B  # noqa: E402
from bench import NAME, ORIG, REQ, boot, f32  # noqa: E402

TARGET = B.load(os.environ['H2_TARGET'], 'vpe_fix_air_candidate')
CONTROL = B.load(os.environ['H2_CONTROL'], 'vpe_fix_air_control')
OUT = os.environ['H2_OUT']
os.makedirs(OUT, exist_ok=True)


# ------------------------------------------------------------ the scripts of the H2 tests (no assertions)
def s_timeout_in_air_event_disarm(b):            # round 1 test_1, round 2 r1
    b.arm('OFFBOARD'); b.plan = ['timeout_applied', 'timeout']; b.set(REQ, ttl=5.0); b.fire_ttl()
    b.step(5.0); b.event([NAME], changed=True); b.disarm('OFFBOARD')


def s_mavros_false(b):                           # 1b
    b.plan = ['mavros_false', 'timeout_applied']; b.set(REQ); b.arm_disarm()


def s_timeout_event(b):                          # 1c
    b.plan = ['timeout_event', 'timeout']; b.set(REQ); b.arm_disarm()


def s_original_seen(b):                          # 2
    b.plan = ['timeout', 'timeout']; b.set(REQ); b.step(2.0); b.event([NAME], changed=True); b.arm_disarm()


def s_noop_old_cache(b):                         # 2b
    b.plan = ['timeout', 'timeout']; b.set(REQ); b.set(float(ORIG)); b.arm_disarm()


def s_third_value(b):                            # 2c
    b.plan = ['timeout', 'timeout']; b.set(REQ); b.px4[NAME] = f32(0.5); b.event([NAME], changed=True)
    b.arm_disarm()


def s_not_sent(b):                               # 2d
    b.plan = ['not_sent', 'not_sent']; b.set(REQ); b.arm_disarm()


def s_sent_then_gone(b):                         # 2e
    b.plan = ['timeout_applied', 'not_sent']; b.set(REQ); b.arm_disarm()


def s_restart_applied(b):                        # 3
    b.plan = ['crash_applied']; b.set(REQ); b.step(40.0); b.respawn(); b.arm_disarm()


def s_restart_not_applied(b):                    # 3b
    b.plan = ['crash']; b.set(REQ); b.step(40.0); b.respawn(); b.arm_disarm()


def s_revert_all(b):                             # 4, 4b
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ); b.revert_all(); b.arm_disarm()


def s_ttl_ground(b):                             # 4c, 4d
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ, ttl=5.0); b.event([NAME], changed=True); b.fire_ttl()
    b.arm_disarm()


def s_persistent(b):                             # 4e
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ, persistent=True); b.arm_disarm(); b.revert_all()


def s_shutdown_ground(b):                        # 4f
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ); b.node._revert_all(reason='shutdown')


def s_later_success(b):                          # 4g
    b.plan = ['timeout', 'timeout']; b.set(REQ); b.set(REQ); b.arm_disarm()


def s_success_late_old_value(b):                 # 4h
    b.plan = ['timeout', 'timeout']; b.set(REQ); b.plan = ['ok_noevent']; b.set(REQ)
    b.event([NAME], values={NAME: ORIG}); b.arm_disarm()


def s_ev_ctrl_first_write(b):                    # 5
    b.px4['EKF2_EV_CTRL'] = 15.0; b.event(['EKF2_EV_CTRL']); b.arm('OFFBOARD')
    b.set(0.0, name='EKF2_EV_CTRL', ptype=0); b.plan = ['timeout_applied', 'timeout']; b.set(REQ); b.set(0.5)
    b.disarm('OFFBOARD')


def s_replay(end):                               # 6
    def f(b):
        b.plan = ['crash_applied', 'timeout']; b.set(REQ); b.step(40.0); b.respawn(); b.step(5.0); b.set(REQ)
        if end == 'disarm':
            b.arm_disarm()
        elif end == 'revert_all':
            b.revert_all()
        elif end == 'armed_then_disarm':
            b.arm(); b.revert_all(); b.fire_ttl(); b.disarm()
    return f


def s_probe(b):                                  # 7 (review probe)
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ); b.step(1.0); b.event([NAME], values={NAME: ORIG})
    b.step(0.1); b.event([NAME], changed=True); b.arm_disarm()


def s_in_air_no_ttl(b):                          # 8
    b.arm('OFFBOARD'); b.plan = ['timeout_applied', 'timeout']; b.set(REQ, ttl=2.0); b.fire_ttl()
    b.disarm('OFFBOARD')


def s_ttl_due_in_air(b):                         # 8b
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ, ttl=5.0); b.arm('OFFBOARD'); b.fire_ttl(); b.fire_ttl()
    b.disarm('OFFBOARD')


def s_revert_all_in_air(b):                      # 8c
    b.arm('OFFBOARD'); b.plan = ['timeout_applied', 'timeout']; b.set(REQ); b.revert_all(); b.disarm('OFFBOARD')


def s_shutdown_in_air(b):                        # 8d
    b.arm('OFFBOARD'); b.plan = ['timeout_applied', 'timeout']; b.set(REQ); b.node._revert_all(reason='shutdown')


def s_ordinary_ttl_in_air(b):                    # 8e
    b.plan = ['timeout', 'timeout']; b.set(REQ); b.arm('OFFBOARD'); b.plan = ['ok']; b.set(0.4, ttl=3.0)
    b.fire_ttl(); b.disarm('OFFBOARD')


def s_fcu_unknown_in_air(b):                     # 8f
    b.plan = ['timeout_applied', 'timeout']; b.set(REQ, ttl=5.0); b.arm('OFFBOARD'); b.state(False, False, '')
    b.fire_ttl(); b.revert_all(); b.state(True, False, 'AUTO.LAND')


NAMED = [(f.__name__, f) for f in (s_timeout_in_air_event_disarm, s_mavros_false, s_timeout_event, s_original_seen,
                                   s_noop_old_cache, s_third_value, s_not_sent, s_sent_then_gone, s_restart_applied,
                                   s_restart_not_applied, s_revert_all, s_ttl_ground, s_persistent, s_shutdown_ground,
                                   s_later_success, s_success_late_old_value, s_ev_ctrl_first_write, s_probe,
                                   s_in_air_no_ttl, s_ttl_due_in_air, s_revert_all_in_air, s_shutdown_in_air,
                                   s_ordinary_ttl_in_air, s_fcu_unknown_in_air)]
NAMED += [('s_replay_%s' % e, s_replay(e)) for e in ('stop', 'disarm', 'revert_all', 'armed_then_disarm')]


def matrix_case(p1, p2, arm_at, air):
    def f(b):
        if arm_at == 'before_set':
            b.arm('OFFBOARD')
        b.plan = [p1, p2]
        b.set(REQ, ttl=4.0)
        b.plan = []
        if arm_at == 'after_set':
            b.arm('OFFBOARD')
        if air == 'ttl':
            b.fire_ttl()
        elif air == 'revert_all':
            b.revert_all()
        elif air == 'shutdown':
            b.node._revert_all(reason='shutdown')
        elif air == 'event':
            b.event([NAME], changed=True)
        elif air == 'stale_event':
            b.event([NAME], values={NAME: ORIG})
        elif air == 'respawn':
            b.step(40.0)
            b.respawn()
        elif air == 'noop':
            b.alive = True
            b.event([NAME], changed=True)
            b.set(REQ, ttl=4.0)
            b.fire_ttl()
        elif air == 'second_write_ttl':
            b.alive = True
            b.set(0.4, ttl=4.0)
            b.fire_ttl()
        b.fire_ttl()
        b.disarm('OFFBOARD')
        b.fire_ttl()
    return f


MATRIX = []
for p1 in B.BEHAVIOURS:
    for p2 in B.BEHAVIOURS:
        if p1 in ('ok', 'ok_noevent') and p2 != 'ok':
            continue
        for arm_at in ('before_set', 'after_set'):
            for air in ('none', 'ttl', 'revert_all', 'shutdown', 'event', 'stale_event', 'respawn', 'noop',
                        'second_write_ttl'):
                MATRIX.append(('m_%s_%s_%s_%s' % (p1, p2, arm_at, air), matrix_case(p1, p2, arm_at, air)))


def in_air(mod, script):
    b = boot(mod)
    script(b)
    return len(b.writes_while_armed()), len(b.writes), b


class InAirWrites(unittest.TestCase):
    def test_no_extra_write_while_armed(self):
        rows, worse, fewer = [], [], []
        for name, script in NAMED + MATRIX:
            o, o_all, _ = in_air(CONTROL, script)
            c, c_all, bc = in_air(TARGET, script)
            rows.append('%-60s original=%d candidate=%d   (all writes: original=%d candidate=%d)'
                        % (name, o, c, o_all, c_all))
            if c > o:
                worse.append(name)
            elif c < o:
                fewer.append(name)
        with open(os.path.join(OUT, 'in_air_writes.txt'), 'w') as f:
            f.write('writes while armed per scenario (7f107882 vs round-2 candidate)\n')
            f.write('\n'.join(rows) + '\n')
            f.write('scenarios: %d (named %d, matrix %d); candidate more: %d; candidate fewer: %d %s\n'
                    % (len(rows), len(NAMED), len(MATRIX), len(worse), len(fewer), fewer))
        self.assertEqual(worse, [])
        self.assertEqual(len(rows), len(NAMED) + len(MATRIX))
        self.assertGreater(len(MATRIX), 1000)


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, descriptions=False))
