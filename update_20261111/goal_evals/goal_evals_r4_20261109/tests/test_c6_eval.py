#!/usr/bin/env python3
"""Synthetic tests for c6_eval.py: a clean hover passes, every kind of failure is caught, limits are inclusive
exactly as the approved numbers say. No Gazebo, no ULog. Run: python3 -I -B tests/test_c6_eval.py -v"""
import io
import math
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import c6_eval as E  # noqa: E402

VALID = {'valid': True, 'invalid_reasons': [], 'rtf_min': 1.0, 'clock_ok': True}


def flight(land_at=80.0, hover_h=1.0, disarm=True, nav_switch=None, fs_at=None, kill=False):
    """Clean C6 flight: arm 1 s, climb 2-7 s, hover at hover_h over marker 0 until land_at, descend, disarm."""
    t = np.arange(0.0, 100.0, 0.02)
    h = np.interp(t, [0, 2, 7, land_at, land_at + 8, 100], [0, 0, hover_h, hover_h, 0, 0])
    xy = np.zeros((len(t), 2)) + 0.02 * np.column_stack([np.sin(t), np.cos(t)])
    et = np.arange(0.0, 100.0, 0.01)
    exyz = np.column_stack([np.interp(et, t, xy[:, 0]), np.interp(et, t, xy[:, 1]), np.interp(et, t, h)])
    nav_t = [0.0, 1.0, land_at]
    nav = [15, 14, 18]
    if nav_switch is not None:
        nav_t.insert(2, nav_switch[0])
        nav.insert(2, nav_switch[1])
    arm_t = np.array([0.0, 1.0] + ([land_at + 10] if disarm else []))
    armed = np.array([False, True] + ([False] if disarm else []))
    st_t = np.array(nav_t)
    fail = np.zeros(len(nav_t), bool)
    if fs_at is not None:
        st_t = np.append(st_t, fs_at)
        nav = nav + [nav[-1]]
        fail = np.append(fail, True)
        o = np.argsort(st_t)
        st_t, nav, fail = st_t[o], np.array(nav)[o], fail[o]
    return {'t': t, 'xy': xy, 'z': h + 0.32, 'ekf_t': et, 'ekf_xyz': exyz,
            'ekf_xy_reset': np.zeros(len(et), int), 'ekf_delta_xy': np.zeros(len(et)),
            'ekf_z_reset': np.zeros(len(et), int), 'ekf_delta_z': np.zeros(len(et)),
            'st_t': st_t, 'nav': np.array(nav), 'failsafe': fail,
            'arm_t': arm_t, 'armed': armed,
            'land_t': np.array([0.0, 2.5, land_at + 8.5]), 'landed': np.array([True, False, True]), 'kill': kill}


def judge(d, validity=VALID, emerg=(), sha_ok=True):
    res, v = E.evaluate(d, emerg=None if emerg is None else list(emerg))
    v['script_matches_versions'] = sha_ok      # r3: set by main() from G.script_source
    word, failed, lines = E.verdict(v, validity)
    return word, failed, res


def bump(d, t0, t1, dx=0.0, dz=0.0, ramp=2.0):
    """add a smooth (slow, not a jump) offset between t0 and t1 to truth (and EKF alike)."""
    f = lambda tt: np.interp(tt, [t0 - ramp, t0, t1, t1 + ramp], [0, 1, 1, 0])  # noqa: E731
    d['xy'][:, 0] += dx * f(d['t'])
    d['z'] += dz * f(d['t'])
    d['ekf_xyz'][:, 0] += dx * f(d['ekf_t'])
    d['ekf_xyz'][:, 2] += dz * f(d['ekf_t'])
    return d


class Clean(unittest.TestCase):
    def test_clean_hover_passes(self):
        word, failed, res = judge(flight())
        self.assertEqual(word, 'PASS', failed)
        self.assertGreaterEqual(res['window']['len_s'], 60.0)
        self.assertEqual(res['offset_share_le_10cm'], 1.0)
        self.assertEqual(res['settling_s'], 0.0)
        self.assertIn('nav_state 18', res['window']['ends_because'])

    def test_window_starts_at_end_of_climb(self):
        res, v = E.evaluate(flight())
        # h reaches 0.90 at 2 + 5*0.9 = 6.5 s
        self.assertAlmostEqual(res['window']['from_s'], 6.5, delta=0.03)
        self.assertAlmostEqual(res['window']['to_s'], 80.0, delta=0.03)

    def test_missing_line_is_not_a_pass(self):
        word, failed, lines = E.verdict({'took_off': True}, VALID)
        self.assertEqual(word, 'FAIL')
        self.assertIn('not evaluated: hover_60s', failed)

    def test_invalid_run_fails(self):
        word, failed, _ = judge(flight(), dict(VALID, valid=False))
        self.assertEqual(failed, ['run_valid'])


class Offsets(unittest.TestCase):
    def test_share_below_95(self):
        # 0.15 m away for ~6 s of ~73 s (8 %): share 92 %
        word, failed, res = judge(bump(flight(), 30, 36, dx=0.15, ramp=0.5))
        self.assertIn('share_10cm_ge_95pct', failed)
        self.assertNotIn('offset_max_le_20cm', failed)

    def test_share_95_ok(self):
        # ~2.5 s of ~73 s outside: ~97 %
        word, failed, res = judge(bump(flight(), 30, 32, dx=0.15, ramp=0.5))
        self.assertNotIn('share_10cm_ge_95pct', failed)
        self.assertGreater(res['offset_share_le_10cm'], 0.95)

    def test_max_above_20cm(self):
        word, failed, res = judge(bump(flight(), 30, 30.5, dx=0.23, ramp=1.5))
        self.assertIn('offset_max_le_20cm', failed)
        self.assertNotIn('no_jump_b_truth', failed)   # slow drift, not a jump

    def test_limits_inclusive(self):
        d = flight()
        d['xy'][:] = [0.0, 0.0]
        d['xy'][(d['t'] > 20) & (d['t'] < 21)] = [0.0999, 0.0]
        word, failed, res = judge(d)
        self.assertEqual(res['offset_share_le_10cm'], 1.0)
        d = flight()
        d['xy'][:] = [0.0, 0.0]
        d['xy'][(d['t'] > 20) & (d['t'] < 21)] = [0.1001, 0.0]
        word, failed, res = judge(d)
        self.assertLess(res['offset_share_le_10cm'], 1.0)

    def test_offset_is_from_marker0_not_takeoff_point(self):
        d = flight()
        d['xy'] += [0.12, 0.0]           # steady 12 cm from marker 0 (e.g. took off 12 cm beside it)
        word, failed, res = judge(d)
        self.assertIn('share_10cm_ge_95pct', failed)


class Height(unittest.TestCase):
    def test_height_err_above_10cm(self):
        word, failed, res = judge(bump(flight(), 40, 42, dz=0.12, ramp=1.5))
        self.assertIn('height_err_le_10cm', failed)

    def test_height_inside(self):
        word, failed, res = judge(bump(flight(), 40, 42, dz=0.09, ramp=1.5))
        self.assertEqual(word, 'PASS', failed)

    def test_never_reaches_height(self):
        word, failed, res = judge(flight(hover_h=0.85))
        self.assertIn('hover_window_found', failed)
        self.assertEqual(word, 'FAIL')

    def test_overshoot_hover_too_high(self):
        # passes 0.9 on the way up (window starts there), then hovers at 1.25
        word, failed, res = judge(flight(hover_h=1.25))
        self.assertIn('height_err_le_10cm', failed)


class Jumps(unittest.TestCase):
    def test_a_xy_reset_big(self):
        d = flight()
        k = np.searchsorted(d['ekf_t'], 30.0)
        d['ekf_xy_reset'][k:] = 1
        d['ekf_delta_xy'][k] = 0.15
        word, failed, res = judge(d)
        self.assertIn('no_jump_a_ekf', failed)
        self.assertEqual(res['jump_a_ekf_resets'][0]['axis'], 'xy')

    def test_a_xy_reset_small_ok(self):
        d = flight()
        k = np.searchsorted(d['ekf_t'], 30.0)
        d['ekf_xy_reset'][k:] = 1
        d['ekf_delta_xy'][k] = 0.05
        self.assertEqual(judge(d)[0], 'PASS')

    def test_a_reset_outside_window_ok(self):
        d = flight()
        k = np.searchsorted(d['ekf_t'], 3.0)    # during the climb
        d['ekf_xy_reset'][k:] = 1
        d['ekf_delta_xy'][k] = 0.5
        self.assertEqual(judge(d)[0], 'PASS')

    def test_a_z_reset_big(self):
        d = flight()
        k = np.searchsorted(d['ekf_t'], 30.0)
        d['ekf_z_reset'][k:] = 1
        d['ekf_delta_z'][k] = 0.2
        self.assertIn('no_jump_a_ekf', judge(d)[1])

    def test_a_estimate_step(self):
        d = flight()
        d['ekf_xyz'][d['ekf_t'] >= 30.0, 1] += 0.11
        word, failed, res = judge(d)
        self.assertIn('no_jump_a_ekf', failed)
        self.assertNotIn('no_jump_b_truth', failed)

    def test_a_estimate_fast_ramp(self):
        # 0.12 m in 0.15 s, no single big step between neighbours (0.008 m per sample)
        d = flight()
        d['ekf_xyz'][:, 1] += np.interp(d['ekf_t'], [30.0, 30.15], [0.0, 0.12])
        self.assertIn('no_jump_a_ekf', judge(d)[1])

    def test_a_estimate_slow_ramp_ok(self):
        d = flight()
        d['ekf_xyz'][:, 1] += np.interp(d['ekf_t'], [30.0, 31.0], [0.0, 0.12])   # 0.12 m in 1 s
        self.assertNotIn('no_jump_a_ekf', judge(d)[1])

    def test_b_truth_jump(self):
        d = flight()
        d['xy'][:, 1] += np.interp(d['t'], [30.0, 30.4, 30.8], [0.0, 0.11, 0.0])
        word, failed, res = judge(d)
        self.assertIn('no_jump_b_truth', failed)
        self.assertNotIn('no_jump_a_ekf', failed)

    def test_b_truth_slow_ok(self):
        d = flight()
        d['xy'][:, 1] += np.interp(d['t'], [30.0, 31.0, 32.0], [0.0, 0.09, 0.0])
        self.assertNotIn('no_jump_b_truth', judge(d)[1])

    def test_b_vertical_counts(self):
        d = flight()
        d['z'] += np.interp(d['t'], [30.0, 30.3, 30.6], [0.0, 0.11, 0.0])
        self.assertIn('no_jump_b_truth', judge(d)[1])


class Window(unittest.TestCase):
    def test_short_hover(self):
        word, failed, res = judge(flight(land_at=60.0))
        self.assertIn('hover_60s', failed)

    def test_pilot_takeover_ends_window(self):
        word, failed, res = judge(flight(nav_switch=(40.0, 2)))
        self.assertIn('hover_60s', failed)
        self.assertIn('nav_state 2', res['window']['ends_because'])

    def test_settling_reported_not_forgiven(self):
        d = flight()
        d['xy'][:, 0] += np.interp(d['t'], [6.5, 12.0, 14.0], [0.15, 0.15, 0.0])
        word, failed, res = judge(d)
        self.assertGreater(res['settling_s'], 5.0)
        self.assertIn('share_10cm_ge_95pct', failed)    # the slow start still counts


class Landing(unittest.TestCase):
    def test_no_disarm(self):
        self.assertIn('landed_and_disarmed_after_hover', judge(flight(disarm=False))[1])

    def test_emergency_list_fails(self):
        self.assertIn('no_emergency', judge(flight(), emerg=['nav_state DESCEND at 50.00 s'])[1])

    def test_emergency_not_evaluated_fails(self):
        word, failed, _ = judge(flight(), emerg=None)
        self.assertEqual(word, 'FAIL')
        self.assertIn('not evaluated: no_emergency', failed)

    def test_shared_list_with_c5_c7(self):
        """r2: C6 uses goal_common.emergencies, the same function as c5_eval.py and c7_eval.py."""
        src = open(os.path.join(os.path.dirname(HERE), 'c6_eval.py'), encoding='utf-8').read()
        self.assertIn('G.emergencies(dc, code, how, src, G.read_script_log(run))', src)
        self.assertNotIn("v['no_failsafe']", src)
        for f in ('c5_eval.py', 'c7_eval.py'):
            self.assertIn('G.emergencies(d, code, how, script_src, script_log)',
                          open(os.path.join(os.path.dirname(HERE), f), encoding='utf-8').read())

    def test_script_sha_must_match(self):
        """r3: the run's script must be the one in versions.txt, as in C5 and C7."""
        word, failed, _ = judge(flight(), sha_ok=False)
        self.assertEqual(word, 'FAIL')
        self.assertIn('script_matches_versions', failed)
        word, failed, lines = E.verdict({k: True for k in ('took_off', 'hover_window_found', 'hover_60s',
                                                           'share_10cm_ge_95pct', 'offset_max_le_20cm',
                                                           'height_err_le_10cm', 'no_jump_a_ekf', 'no_jump_b_truth',
                                                           'landed_and_disarmed_after_hover', 'no_emergency')}, VALID)
        self.assertIn('not evaluated: script_matches_versions', failed)


class Files(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='c6eval_')

    def tearDown(self):
        shutil.rmtree(self.d)

    def write_world(self, rot, shift):
        c, s = math.cos(rot), math.sin(rot)
        mp = {0: (0.0, 0.0), 1: (0.0, 0.73), 2: (0.0, 1.42), 11: (-0.72, 0.73)}
        inc = []
        lines = ['# id\tlength\tx\ty\tz\trot_z\trot_y\trot_x']
        for i, (x, y) in mp.items():
            # world = R^-1 (map - shift)
            wx, wy = x - shift[0], y - shift[1]
            wx, wy = c * wx + s * wy, -s * wx + c * wy
            inc.append('<include><uri>model://aruco_%d</uri><pose>%r %r 0.004 0 0 0</pose></include>' % (i, wx, wy))
            lines.append('%d\t0.29\t%.3f\t%.3f\t-0.320\t1.571\t0\t0' % (i, x, y))
        open(os.path.join(self.d, 'world.sdf'), 'w').write('<sdf>' + '\n'.join(inc) + '</sdf>')
        open(os.path.join(self.d, 'map.txt'), 'w').write('\n'.join(lines) + '\n')

    def test_world_to_map_rotation_and_shift(self):
        self.write_world(0.7, (0.3, -0.2))
        T = E.world_to_map(os.path.join(self.d, 'world.sdf'), os.path.join(self.d, 'map.txt'))
        self.assertLess(T['max_residual_m'], 1e-3)
        self.assertAlmostEqual(math.atan2(T['R'][1, 0], T['R'][0, 0]), 0.7, places=3)

    def test_main_no_ulog_fails_and_never_overwrites(self):
        self.write_world(0.0, (0.0, 0.0))
        open(os.path.join(self.d, 'rtf.txt'), 'w').write('real_time_factor: 1.0\n')
        open(os.path.join(self.d, 'clock_check.txt'), 'w').write('{"ok": true}\n')
        open(os.path.join(self.d, 'script.log'), 'w').write('PREFLIGHT FAIL: x\n')
        argv = [self.d, '--map', os.path.join(self.d, 'map.txt')]
        with redirect_stdout(io.StringIO()) as out:
            code = E.main(argv)
        self.assertEqual(code, 1)
        self.assertIn('C6 FAIL', out.getvalue())
        self.assertIn('never armed', out.getvalue())
        self.assertIn("'script_matches_versions': False", out.getvalue())   # no versions.txt here
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(E.main(argv), 2)
        self.assertIn('refusing to overwrite', out.getvalue())

    def test_main_script_sha_checked(self):
        self.write_world(0.0, (0.0, 0.0))
        s = os.path.join(self.d, 'hover.py')
        open(s, 'w').write('drone.takeoff(height=1.0)\n')
        import goal_common as GC
        open(os.path.join(self.d, 'versions.txt'), 'w').write('script %s %s\n' % (s, GC.sha256(s)))
        argv = [self.d, '--map', os.path.join(self.d, 'map.txt'), '--out', os.path.join(self.d, 'o1')]
        with redirect_stdout(io.StringIO()) as out:
            E.main(argv)
        self.assertIn("'script_matches_versions': True", out.getvalue())
        open(s, 'w').write('drone.takeoff(height=1.5)\n')       # file changed after the run
        argv[-1] = os.path.join(self.d, 'o2')
        with redirect_stdout(io.StringIO()) as out:
            E.main(argv)
        self.assertIn("'script_matches_versions': False", out.getvalue())

    def test_numbers_are_the_approved_ones(self):
        self.assertEqual(E.C6, {'height_m': 1.0, 'height_tol_m': 0.10, 'hover_s': 60.0, 'offset_10cm_m': 0.10,
                                'share_min': 0.95, 'offset_max_m': 0.20, 'jump_m': 0.10, 'jump_ekf_dt_s': 0.2,
                                'jump_truth_dt_s': 0.5})
        self.assertEqual(E.RTF_MIN, 0.20)


if __name__ == '__main__':
    unittest.main()
