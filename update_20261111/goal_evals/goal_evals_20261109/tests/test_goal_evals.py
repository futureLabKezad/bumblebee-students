#!/usr/bin/env python3
"""Synthetic tests for c5_eval.py, c7_eval.py and goal_common.py: a clean flight passes, every kind of failure
is caught, limits are inclusive exactly as the approved numbers say. No Gazebo, no ULog.
Run: python3 -I -B tests/test_goal_evals.py -v"""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import goal_common as G  # noqa: E402
import c5_eval as C5  # noqa: E402
import c7_eval as C7  # noqa: E402

VALID = {'valid': True}


def status(times_navs, arm_off_at=None, fs_at=None, took_over_at=None):
    """vehicle_status arrays; arming ARMED from 0 until arm_off_at."""
    st_t = np.arange(0.0, 120.0, 0.5)
    nav = np.full(len(st_t), 14)
    for t0, n in times_navs:
        nav[st_t >= t0] = n
    arming = np.where((arm_off_at is None) | (st_t < (arm_off_at if arm_off_at is not None else 1e9)), 2, 1)
    fs = np.zeros(len(st_t), bool)
    if fs_at is not None:
        fs[st_t >= fs_at] = True
    uto = np.zeros(len(st_t), bool)
    if took_over_at is not None:
        uto[st_t >= took_over_at] = True
    return {'st_t': st_t, 'nav': nav, 'arming_state': arming, 'failsafe': fs, 'user_took_over': uto}


# ---------------------------------------------------------------- C5
def c5_flight(H=0.8, land_at=30.0, touch_at=None, off_delay=2.0, hover_dev=0.0, dev_at=(15.0, 15.5)):
    t = np.arange(0.0, 60.0, 0.02)
    touch_at = touch_at if touch_at is not None else land_at + H / 0.3
    h = np.interp(t, [0, 2, 5, land_at, touch_at, 60], [0, 0, H, H, 0, 0])
    h = h + hover_dev * ((t >= dev_at[0]) & (t < dev_at[1]))
    vz = np.gradient(h, t)
    d = {'t': t, 'xy': np.zeros((len(t), 2)), 'z': h + 0.3, 'vz_up': vz, 'kill': False}
    d.update(status([(land_at, 18)], arm_off_at=touch_at + off_delay))
    return d


def c5_judge(d, H=0.8, code=0):
    res, v = C5.evaluate(d, H, code)
    v['run_valid'] = True
    v['script_height_known'] = True
    word, failed = G.verdict(v, C5.NEED)
    return word, failed, res


class C5Tests(unittest.TestCase):
    def test_clean_passes(self):
        word, failed, res = c5_judge(c5_flight())
        self.assertEqual(word, 'PASS', failed)
        self.assertAlmostEqual(res['motors_off_after_touchdown_s'], 2.0, delta=0.51)

    def test_height_max_not_mean(self):
        word, failed, res = c5_judge(c5_flight(hover_dev=0.12))   # 0.5 s out of band, mean still fine
        self.assertIn('height_within_0p10', failed)
        self.assertLess(abs(res['height_mean_m'] - 0.8), 0.01)

    def test_height_limit_inclusive(self):
        self.assertNotIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.0999))[1])
        self.assertIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.1001))[1])

    def test_wrong_script_height(self):
        word, failed, res = c5_judge(c5_flight(H=0.8), H=1.5)
        self.assertIn('height_window_found', failed)

    def test_motors_off_limit(self):
        # status sampled every 0.5 s: delay measured on the status sample (never earlier than the truth)
        d = c5_flight(touch_at=32.0, off_delay=3.0)
        self.assertNotIn('motors_off_le_3s', c5_judge(d)[1])
        d = c5_flight(touch_at=32.0, off_delay=3.5)
        self.assertIn('motors_off_le_3s', c5_judge(d)[1])

    def test_touchdown_is_contact_not_5cm(self):
        # PX4-like slow final phase: 0.8 -> 0.06 m at 0.4 m/s, then 0.06 -> 0 at 0.05 m/s; contact at 33.05 s
        d = c5_flight()
        t = d['t']
        h = np.interp(t, [0, 2, 5, 30.0, 31.85, 33.05, 60], [0, 0, 0.8, 0.8, 0.06, 0.0, 0.0])
        d['z'], d['vz_up'] = h + 0.3, np.gradient(h, t)
        res, v = C5.evaluate(d, 0.8)
        self.assertAlmostEqual(res['touchdown_s'], 33.05 - 0.01 / 0.05, delta=0.05)

    def test_no_motors_off(self):
        d = c5_flight()
        d['arming_state'][:] = 2
        self.assertIn('motors_off_found', c5_judge(d)[1])

    def test_no_touchdown(self):
        d = c5_flight()
        d['z'] = np.maximum(d['z'], 0.3 + 0.2 * (d['t'] > 10))
        self.assertIn('touchdown_found', c5_judge(d)[1])

    def test_emergencies(self):
        cases = {'failsafe': dict(fs_at=20.0), 'took over': dict(took_over_at=20.0)}
        for name, kw in cases.items():
            with self.subTest(name):
                d = c5_flight()
                d.update(status([(30.0, 18)], arm_off_at=d['st_t'][-1] if False else 34.67, **kw))
                self.assertIn('no_emergency', c5_judge(d)[1])
        for nav in (5, 12, 13):
            with self.subTest(nav=nav):
                d = c5_flight()
                d['nav'][(d['st_t'] >= 20) & (d['st_t'] < 21)] = nav
                self.assertIn('no_emergency', c5_judge(d)[1])
        d = c5_flight()
        d['kill'] = True
        self.assertIn('no_emergency', c5_judge(d)[1])
        self.assertIn('no_emergency', c5_judge(c5_flight(), code=3)[1])
        self.assertIn('no_emergency', c5_judge(c5_flight(), code=None)[1])

    def test_never_armed(self):
        d = c5_flight()
        d['arming_state'][:] = 1
        word, failed, _ = c5_judge(d)
        self.assertIn('took_off', failed)

    def test_script_height_from_code(self):
        self.assertEqual(C5.script_height('import drone\ndrone.takeoff(height=0.8, speed=0.4)\n'), 0.8)
        self.assertEqual(C5.script_height('drone.takeoff(1.5)\n'), 1.5)
        self.assertEqual(C5.script_height('drone.takeoff(speed=0.4)\n'), 1.0)
        for bad in ('h = 1\ndrone.takeoff(height=h)\n', 'x = 1\n', 'drone.takeoff(0.8)\ndrone.takeoff(0.8)\n'):
            with self.assertRaises(ValueError):
                C5.script_height(bad)


# ---------------------------------------------------------------- C7
ROUTE = [(0.0, 1.4, 0.25), (0.0, 0.7, 0.25), (0.0, 0.0, 0.25)]
OFFSET = np.array([0.3, 1.53])   # the EKF frame is not the marker map (variant A)


def c7_flight(route=ROUTE, point_bias=None, land_bias=(0.0, 0.0), extra_stop=False, skip_reach=None):
    """Marker-map truth path: takeoff at marker 0 to 0.7 m, legs at 0.1 m/s, 6 s holds, land at the last point."""
    knots_t, knots_xy = [0.0, 8.0], [(0.0, 0.0), (0.0, 0.0)]
    tt = 8.0
    for (x, y, _tol) in route:
        px, py = knots_xy[-1]
        L = float(np.hypot(x - px, y - py))
        if extra_stop and len(knots_t) == 2:
            mx, my = (px + x) / 2, (py + y) / 2
            knots_t += [tt + L / 2 / 0.1, tt + L / 2 / 0.1 + 3.0]
            knots_xy += [(mx, my), (mx, my)]
            tt += 3.0
        tt += L / 0.1
        knots_t += [tt, tt + 6.0]
        knots_xy += [(x, y), (x, y)]
        tt += 6.0
    t_land = tt
    sp_t = np.arange(0.0, t_land + 15, 0.2)
    kx = np.array(knots_xy)
    spx, spy = np.interp(sp_t, knots_t, kx[:, 0]), np.interp(sp_t, knots_t, kx[:, 1])
    t = np.arange(0.0, t_land + 15, 0.02)
    tx, ty = np.interp(t - 0.5, knots_t, kx[:, 0]), np.interp(t - 0.5, knots_t, kx[:, 1])
    xy = np.column_stack([tx, ty])
    h = np.interp(t, [0, 1, 4, t_land, t_land + 3, 200], [0, 0, 0.7, 0.7, 0, 0])
    ekf_t = np.arange(0.0, t_land + 15, 0.01)
    E = np.column_stack([np.interp(ekf_t, t, xy[:, 0]), np.interp(ekf_t, t, xy[:, 1]), np.interp(ekf_t, t, h)])
    E[:, :2] += OFFSET
    if point_bias is not None:                     # truth off the point while the EKF believes it is there
        k, b = point_bias
        a = knots_t[2 + 2 * k] + 0.5
        sel = (t >= a) & (t <= a + 5.5)
        xy[sel] += b
    if skip_reach is not None:                     # EKF never within tolerance at point k
        a = knots_t[2 + 2 * skip_reach]
        sel = (ekf_t >= a - 0.5) & (ekf_t <= a + 6.5)
        E[sel, 0] += 0.4
    after = t >= t_land + 3
    xy[after] += np.array(land_bias)
    d = {'t': t, 'xy': xy, 'z': h + 0.3, 'vz_up': np.gradient(h, t), 'ekf_t': ekf_t, 'ekf_xyz': E,
         'sp_t': sp_t, 'sp_xyz': np.column_stack([spx + OFFSET[0], spy + OFFSET[1], np.full(len(sp_t), 0.7)]),
         'kill': False}
    d.update(status([(t_land, 18)], arm_off_at=t_land + 5))
    return d


def c7_judge(d, route=ROUTE, flown='same', code=0):
    flown = [p[:2] for p in route] if flown == 'same' else flown
    res, v = C7.evaluate(d, route, flown, (0.0, 0.0), code)
    v['run_valid'] = True
    v['route_from_code'] = True
    word, failed = G.verdict(v, C7.NEED)
    return word, failed, res


class C7Tests(unittest.TestCase):
    def test_clean_passes_with_offset_ekf_frame(self):
        word, failed, res = c7_judge(c7_flight())
        self.assertEqual(word, 'PASS', failed)
        self.assertEqual(len(res['points']), 3)
        self.assertLess(max(p['err_m'] for p in res['points']), 0.06)

    def test_point_error(self):
        word, failed, res = c7_judge(c7_flight(point_bias=(1, (0.26, 0.0))))
        self.assertIn('points_within_0p25', failed)
        self.assertGreater(res['points'][1]['err_max_wait_m'], 0.25)

    def test_point_limit_inclusive(self):
        self.assertNotIn('points_within_0p25', c7_judge(c7_flight(point_bias=(1, (0.24, 0.0))))[1])

    def test_landing(self):
        self.assertIn('landing_within_0p15', c7_judge(c7_flight(land_bias=(0.16, 0.0)))[1])
        self.assertNotIn('landing_within_0p15', c7_judge(c7_flight(land_bias=(0.14, 0.0)))[1])

    def test_flown_shorter_than_code(self):
        self.assertIn('route_flown_as_coded', c7_judge(c7_flight(), flown=[(0.0, 1.4)])[1])
        self.assertIn('route_flown_as_coded', c7_judge(c7_flight(), flown=None)[1])

    def test_extra_stop_cannot_match(self):
        word, failed, res = c7_judge(c7_flight(extra_stop=True))
        self.assertIn('holds_match_route', failed)
        self.assertEqual(word, 'FAIL')

    def test_setpoints_not_the_coded_route(self):
        # same number of stops, but the vehicle was sent to (0, 1.0) instead of (0, 1.4)
        d = c7_flight(route=[(0.0, 1.0, 0.25), (0.0, 0.7, 0.25), (0.0, 0.0, 0.25)])
        word, failed, res = c7_judge(d)
        self.assertIn('holds_match_route', failed)

    def test_point_not_reached(self):
        self.assertIn('all_points_reached', c7_judge(c7_flight(skip_reach=0))[1])

    def test_intervention(self):
        d = c7_flight()
        d['nav'][(d['st_t'] >= 20) & (d['st_t'] < 22)] = 2      # POSCTL by the pilot, then back
        self.assertIn('offboard_until_land', c7_judge(d)[1])

    def test_emergencies(self):
        d = c7_flight()
        d['failsafe'][d['st_t'] > 30] = True
        self.assertIn('no_emergency', c7_judge(d)[1])
        self.assertIn('no_emergency', c7_judge(c7_flight(), code=1)[1])

    def test_never_lands(self):
        d = c7_flight()
        d['nav'][:] = 14
        d['arming_state'][:] = 2
        word, failed, _ = c7_judge(d)
        self.assertIn('offboard_until_land', failed)
        self.assertIn('landing_found', failed)

    def test_route_patterns(self):
        src = ('import drone\nWP = [(0.0, 0.7), (-0.36, 2.1)]\ntry:\n    drone.takeoff(height=1.3)\n'
               '    for (a, b) in WP:\n        if not drone.fly_to(x=a, y=b, z=1, tolerance=0.25):\n            break\n'
               '    drone.fly_to(x=0, y=-0.0, z=1)\nfinally:\n    drone.safe_land(x=0, y=0)\n')
        self.assertEqual(C7.route_from_code(src), [(0.0, 0.7, 0.25), (-0.36, 2.1, 0.25), (0.0, 0.0, 0.2)])
        for bad in ('import drone\n', 'z=1\ndrone.fly_to(x=z, y=0)\n', 'while True:\n    drone.fly_to(x=0, y=0)\n',
                    'def f():\n    drone.fly_to(x=0, y=0)\n', 'for i in range(3):\n    drone.fly_to(x=i, y=0)\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                C7.route_from_code(bad)

    def test_route_of_the_image_examples(self):
        base = '/work/fixed_image_r2_20261109/src/bumblebee/examples/flight/'
        if not os.path.exists(base + 'flight_marker_loop.py'):
            self.skipTest('r2 image not found')
        loop = [p[:2] for p in C7.route_from_code(open(base + 'flight_marker_loop.py').read())]
        self.assertEqual(loop, [(0.0, 0.7), (0.0, 1.4), (0.0, 2.1), (-0.36, 2.1), (-0.72, 2.1), (-0.72, 1.4),
                                (-0.72, 0.7), (-0.36, 0.7), (0.0, 0.7), (0.0, 0.0)])
        fm = [p[:2] for p in C7.route_from_code(open(base + 'flight_marker.py').read())]
        self.assertEqual(fm, [(0.0, 1.4), (0.0, 0.7), (0.0, 0.0)])


class SeriesTests(unittest.TestCase):
    FP = {'script': 'a'}

    def rec(self, n, ok, script='flight_marker.py', fp=None):
        return {'run': 'r%d' % n, 'script': script, 'C7': 'PASS' if ok else 'FAIL', 'fingerprint': fp or self.FP}

    def test_ten_in_a_row_both(self):
        recs = [self.rec(i, True) for i in range(10)] + [self.rec(i, True, 'flight_marker_loop.py') for i in range(10)]
        s = C7.series(recs)
        self.assertTrue(s['C7_series_done'])

    def test_fail_resets(self):
        recs = [self.rec(i, True) for i in range(9)] + [self.rec(9, False)] + [self.rec(10, True)]
        s = C7.series(recs)
        self.assertEqual(s['per_script_in_a_row_now']['flight_marker.py'], 1)
        self.assertFalse(s['C7_series_done'])

    def test_change_restarts(self):
        recs = [self.rec(i, True) for i in range(9)] + [self.rec(9, True, fp={'script': 'b'})]
        s = C7.series(recs)
        self.assertEqual(s['per_script_in_a_row_now']['flight_marker.py'], 1)
        self.assertIn('changed', s['log'][-1]['note'])

    def test_only_one_script(self):
        s = C7.series([self.rec(i, True) for i in range(12)])
        self.assertFalse(s['C7_series_done'])

    def test_both_scripts_both_need_ten(self):
        recs = [self.rec(i, True) for i in range(10)] + [self.rec(i, True, 'flight_marker_loop.py') for i in range(5)]
        s = C7.series(recs)
        self.assertFalse(s['C7_series_done'])
        self.assertEqual(s['reached_10'], {'flight_marker.py': True, 'flight_marker_loop.py': False})


# ---------------------------------------------------------------- files
class FileTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='goalevals_')

    def tearDown(self):
        shutil.rmtree(self.d)

    def w(self, name, text):
        p = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, 'w').write(text)
        return p

    def test_script_exit(self):
        self.w('launcher.log', 'x\nscript exit 137 2026-11-06T16:13:21+04:00\n')
        self.assertEqual(G.script_exit(self.d)[0], 137)
        self.w('script_end.txt', '2026 ended by launcher: ... (F4)\n')
        self.assertIn('ended by launcher', G.script_exit(self.d)[1])

    def test_script_source_sha(self):
        s = self.w('scen/hover.py', 'drone.takeoff(height=0.8)\n')
        self.w('versions.txt', 'date x\nscript %s %s\n' % (s, G.sha256(s)))
        path, src, problem = G.script_source(self.d)
        self.assertIsNone(problem)
        self.w('scen/hover.py', 'drone.takeoff(height=1.0)\n')
        path, src, problem = G.script_source(self.d)
        self.assertIsNone(src)
        self.assertIn('differs', problem)

    def test_script_source_product(self):
        prod = os.path.join(self.d, 'prod')
        s = self.w('prod/src/bumblebee/examples/flight/flight.py', 'drone.takeoff(height=0.8)\n')
        self.w('snapshot/run_scenario2.sh', 'X=1\nPRODUCT=%s\n' % prod)
        self.w('versions.txt', 'script examples/flight/flight.py %s\n' % G.sha256(s))
        self.assertIsNone(G.script_source(self.d)[2])

    def test_fingerprint_ignores_date(self):
        self.w('versions.txt', 'date 1\nproduct p1\nabc' + '0' * 61 + '  tools/x.py\n')
        a = G.run_fingerprint(self.d)
        self.w('versions.txt', 'date 2\nproduct p1\nabc' + '0' * 61 + '  tools/x.py\n')
        self.assertEqual(a, G.run_fingerprint(self.d))
        self.w('versions.txt', 'date 2\nproduct p2\nabc' + '0' * 61 + '  tools/x.py\n')
        self.assertNotEqual(a, G.run_fingerprint(self.d))

    def test_main_no_ulog_and_no_overwrite(self):
        self.w('world.sdf', '<include><uri>model://aruco_0</uri><pose>0 0 0 0 0 0</pose></include>'
                            '<include><uri>model://aruco_1</uri><pose>0 0.73 0 0 0 0</pose></include>')
        m = self.w('map.txt', '0 0.19 0 0 -0.32 1.571 0 0\n1 0.29 0 0.73 -0.32 1.571 0 0\n')
        s = self.w('scen/f.py', 'drone.takeoff(height=0.8)\ndrone.fly_to(x=0, y=0.73)\n')
        self.w('versions.txt', 'script %s %s\n' % (s, G.sha256(s)))
        self.w('rtf.txt', 'real_time_factor: 1.0\n')
        self.w('clock_check.txt', '{"ok": true}\n')
        for mod, word in ((C5, 'C5 FAIL'), (C7, 'C7 FAIL')):
            with self.subTest(mod.__name__):
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(mod.main([self.d, '--map', m]), 1)
                self.assertIn(word, out.getvalue())
                self.assertIn('never armed', out.getvalue())
                with redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(mod.main([self.d, '--map', m]), 2)
                self.assertIn('refusing to overwrite', out.getvalue())

    def test_numbers(self):
        self.assertEqual((C5.C5['height_tol_m'], C5.C5['motors_off_s']), (0.10, 3.0))
        self.assertEqual((C7.C7['point_m'], C7.C7['landing_m'], C7.C7['in_a_row']), (0.25, 0.15, 10))
        self.assertEqual(G.RTF_MIN, 0.20)


if __name__ == '__main__':
    unittest.main()
