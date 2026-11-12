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
    # the script's /land: an external DO_SET_MODE AUTO/LAND 16 ms before each AUTO.LAND entry
    land_t = [t0 - 0.016 for t0, n in times_navs if n == 18]
    return {'st_t': st_t, 'nav': nav, 'arming_state': arming, 'failsafe': fs, 'user_took_over': uto,
            'ff_t': st_t.copy(), 'ff': {}, 'cmd_ext_logged': True,
            'cmd_t': np.array(land_t), 'cmd': np.full(len(land_t), 176), 'cmd_p2': np.full(len(land_t), 4.0),
            'cmd_p3': np.full(len(land_t), 6.0), 'cmd_ext': np.ones(len(land_t), bool)}


LOG_OK = 'x\n=== LANDING ===\n'


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


def c5_judge(d, H=0.8, code=0, src='', log=LOG_OK):
    res, v = C5.evaluate(d, H, code, None, src, log)
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
        # contact (h <= 0.01) at 32.005 s; disarm recorded on the 35.0 s status sample: 2.995 s
        d = c5_flight(touch_at=32.03, off_delay=2.97)
        self.assertNotIn('motors_off_le_3s', c5_judge(d)[1])
        d = c5_flight(touch_at=32.03, off_delay=3.5)
        self.assertIn('motors_off_le_3s', c5_judge(d)[1])

    def test_touchdown_is_contact_not_5cm(self):
        # PX4-like slow final phase: 0.8 -> 0.06 m at 0.4 m/s, then 0.06 -> 0 at 0.05 m/s; contact at 33.05 s
        d = c5_flight()
        t = d['t']
        h = np.interp(t, [0, 2, 5, 30.0, 31.85, 33.05, 60], [0, 0, 0.8, 0.8, 0.06, 0.0, 0.0])
        d['z'], d['vz_up'] = h + 0.3, np.gradient(h, t)
        res, v = C5.evaluate(d, 0.8, 0, None, '', LOG_OK)
        self.assertAlmostEqual(res['touchdown_s'], 33.05 - 0.01 / 0.05, delta=0.05)

    def test_touchdown_first_contact_of_a_bounce(self):
        # fast contact at 32.0 s (0.4 m/s down), bounce to 0.05 m, rests from 33.0 s: touchdown = 32.0 s
        d = c5_flight()
        t = d['t']
        h = np.interp(t, [0, 2, 5, 30.0, 32.0, 32.5, 33.0, 60], [0, 0, 0.8, 0.8, 0.0, 0.05, 0.0, 0.0])
        d['z'], d['vz_up'] = h + 0.3, np.gradient(h, t)
        res, v = C5.evaluate(d, 0.8, 0, None, '', LOG_OK)
        self.assertAlmostEqual(res['touchdown_s'], 32.0 - 0.01 / 0.4, delta=0.03)

    def test_failsafe_flags(self):
        def with_ff(flag, on_from, on_at_start=False):
            d = c5_flight()
            d['ff_t'] = np.arange(0.0, 60.0, 0.5)
            a = d['ff_t'] >= on_from
            if on_at_start:
                a[:] = True
            d['ff'] = {flag: a, 'home_position_invalid': np.ones(len(a), bool)}
            return d
        self.assertIn('no_emergency', c5_judge(with_ff('battery_warning', 20.0))[1])
        self.assertIn('no_emergency', c5_judge(with_ff('battery_warning', 31.0))[1])   # after /land, still armed
        self.assertIn('no_emergency', c5_judge(with_ff('offboard_control_signal_lost', 20.0))[1])  # before land
        self.assertNotIn('no_emergency', c5_judge(with_ff('offboard_control_signal_lost', 31.0))[1])  # after /land
        self.assertNotIn('no_emergency', c5_judge(with_ff('global_position_invalid', 0, True))[1])  # on from start
        self.assertIn('no_emergency', c5_judge(with_ff('offboard_control_signal_lost', 31.0), log='x\n')[1])
        d = with_ff('global_position_invalid', 0, True)     # on at start, off at 10 s, on again at 20 s
        a = d['ff']['global_position_invalid']
        a[(d['ff_t'] >= 10) & (d['ff_t'] < 20)] = False
        self.assertIn('no_emergency', c5_judge(d)[1])

    def test_hold(self):
        """r3: Hold is the script's only with '=== HOLD ===' in script.log AND an external DO_SET_MODE AUTO/LOITER
        (176, 4, 3) within 2 s before; the text of the source file does not count."""
        def hold_flight(cmd_dt=0.02, p3=3.0, ext=True):
            d = c5_flight()
            d['nav'][(d['st_t'] >= 20) & (d['st_t'] < 21)] = 4
            d['cmd_t'] = np.r_[d['cmd_t'], 20.0 - cmd_dt]
            d['cmd'] = np.r_[d['cmd'], 176]
            d['cmd_p2'] = np.r_[d['cmd_p2'], 4.0]
            d['cmd_p3'] = np.r_[d['cmd_p3'], p3]
            d['cmd_ext'] = np.r_[d['cmd_ext'], ext]
            return d
        log_hold = 'x\n=== HOLD ===\n' + LOG_OK
        self.assertNotIn('no_emergency', c5_judge(hold_flight(), log=log_hold)[1])
        self.assertIn('no_emergency', c5_judge(hold_flight())[1])                        # no request line
        self.assertIn('no_emergency', c5_judge(hold_flight(), src="drone.set_mode('AUTO.LOITER')\n")[1])
        self.assertIn('no_emergency', c5_judge(hold_flight(cmd_dt=2.5), log=log_hold)[1])  # command too early
        self.assertIn('no_emergency', c5_judge(hold_flight(p3=6.0), log=log_hold)[1])      # not a LOITER command
        self.assertIn('no_emergency', c5_judge(hold_flight(ext=False), log=log_hold)[1])   # PX4-internal

    def test_guard_landing_is_emergency(self):
        """r3 (chat 1): a drone.py guard landing fails C5 even though safe_land printed '=== LANDING ==='."""
        for line in ('[ERROR] [1.0] [flight]: Position jump 0.50m in 0.10s (5.0 m/s) -- EKF likely diverged, landing',
                     '[ERROR] [1.0] [flight]: Vision lost for 6.5s (markers_used=0, limit 6.0s) -- EKF is coasting, '
                     'landing',
                     '[ERROR] [1.0] [flight]: Telemetry stale for 5.2s (NaN position) -- landing',
                     '[ERROR] [1.0] [flight]: EKF z=-0.80 is 0.80 m below the height at arm (0.00) -- EKF diverged, '
                     'landing',
                     '[ERROR] [1.0] [flight]: Altitude overshoot: z=1.50 > target 0.80 +0.6 -- runaway climb, landing',
                     '[INFO] [1.0] [flight]: Guard /land: landing (AUTO.LAND)'):
            with self.subTest(line=line[:40]):
                word, failed, res = c5_judge(c5_flight(), log='x\n' + line + '\n=== LANDING ===\n')
                self.assertIn('no_emergency', failed)
                self.assertTrue(any('drone.py emergency landing' in e for e in res['emergencies']))
        self.assertIn('no_emergency', c5_judge(c5_flight(), log=None)[1])          # no script.log
        d = c5_flight()
        d['nav'][:] = 14                            # no AUTO.LAND at all: the missing log alone must fail
        self.assertTrue(any('script.log missing' in e for e in G.emergencies(d, 0, None, '', None)))
        self.assertEqual(G.emergencies(d, 0, None, '', LOG_OK), [])

    def test_missing_data_not_evaluated(self):
        """r3: no failsafe_flags topic / no from_external field = not evaluated = fail."""
        d = c5_flight()
        d['ff_t'], d['ff'] = None, {}
        word, failed, res = c5_judge(d)
        self.assertIn('no_emergency', failed)
        self.assertTrue(any('failsafe_flags not in ULog' in e for e in res['emergencies']))
        d = c5_flight()
        d['cmd_ext_logged'] = False
        self.assertIn('no_emergency', c5_judge(d)[1])

    def test_landing_command_kind(self):
        d = c5_flight()
        d['cmd_ext'][:] = False                     # the land command came from inside PX4
        self.assertIn('no_emergency', c5_judge(d)[1])
        d = c5_flight()
        d['cmd_p3'][:] = 3.0                        # DO_SET_MODE AUTO/LOITER is not a landing request
        self.assertIn('no_emergency', c5_judge(d)[1])

    def test_window_start_edge(self):
        # band (|h-0.8| <= 0.10) entered at the 4.64 s sample; 0.16 m off at 4.66-4.68 s (the 2 samples after it)
        self.assertIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.25, dev_at=(4.7, 4.9)))[1])
        self.assertIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.25, dev_at=(4.655, 4.695)))[1])

    def test_window_end_edge(self):
        # AUTO.LAND (left OFFBOARD) at 30.0 s; 0.12 m off at 29.6-29.95 s: inside the window
        self.assertIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.12, dev_at=(29.6, 29.95)))[1])
        # r4: only the last 3 samples before the switch (29.94-29.98 s)
        self.assertIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.12, dev_at=(29.935, 29.995)))[1])
        # the same just after the switch is outside the window
        self.assertNotIn('height_within_0p10', c5_judge(c5_flight(hover_dev=0.12, dev_at=(30.05, 30.3)))[1])

    def test_land_not_requested(self):
        d = c5_flight()
        d['cmd_t'] = np.array([])                       # PX4 switched to AUTO.LAND by itself
        for k in ('cmd', 'cmd_p2', 'cmd_p3', 'cmd_ext'):
            d[k] = np.array([])
        word, failed, res = c5_judge(d)
        self.assertIn('no_emergency', failed)
        self.assertTrue(any('not requested' in e for e in res['emergencies']))
        self.assertIn('no_emergency', c5_judge(c5_flight(), log='no landing line\n')[1])
        d = c5_flight()
        d['cmd_t'] = d['cmd_t'] - 2.5                   # a command too long before the switch
        self.assertIn('no_emergency', c5_judge(d)[1])

    def test_stand_ended_exit(self):
        word, failed, res = c5_judge(c5_flight(), code=143)
        self.assertIn('no_emergency', failed)
        self.assertTrue(any('ended by the stand' in e for e in res['emergencies']))

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


def c7_flight(route=ROUTE, point_bias=None, land_bias=(0.0, 0.0), extra_stop=False, skip_reach=None,
              retarget=None, stop_before=None, truth_bias_at=None, land_bias_first_s=None):
    """Marker-map truth path: takeoff at marker 0 to 0.7 m, legs at 0.1 m/s, 6 s holds, land at the last point.
    r3 options: retarget=[(k, dx)] - 3 s into the hold of point k the setpoint is re-aimed dx m sideways (hover());
    stop_before=(k, dist) - a 2 s stop on the leg to point k, dist m before it;
    truth_bias_at=(t0, t1, dx) - truth moved dx sideways between t0 and t1;
    land_bias_first_s=s - land_bias only for s seconds after motors off, then back on the point."""
    knots_t, knots_xy = [0.0, 8.0], [(0.0, 0.0), (0.0, 0.0)]
    hold_t = []          # (point reached by the setpoint, setpoint leaves the point) per route point
    tt = 8.0
    for n, (x, y, _tol) in enumerate(route):
        px, py = knots_xy[-1]
        L = float(np.hypot(x - px, y - py))
        if extra_stop and len(knots_t) == 2:
            mx, my = (px + x) / 2, (py + y) / 2
            knots_t += [tt + L / 2 / 0.1, tt + L / 2 / 0.1 + 3.0]
            knots_xy += [(mx, my), (mx, my)]
            tt += 3.0
        if stop_before is not None and stop_before[0] == n:
            f = (L - stop_before[1]) / L
            sx, sy = px + f * (x - px), py + f * (y - py)
            knots_t += [tt + (L - stop_before[1]) / 0.1, tt + (L - stop_before[1]) / 0.1 + 2.0]
            knots_xy += [(sx, sy), (sx, sy)]
            tt += 2.0
        tt += L / 0.1
        knots_t += [tt, tt + 6.0]
        knots_xy += [(x, y), (x, y)]
        hold_t.append((tt, tt + 6.0))
        tt += 6.0
    t_land = tt
    sp_t = np.arange(0.0, t_land + 15, 0.2)
    kx = np.array(knots_xy)
    spx, spy = np.interp(sp_t, knots_t, kx[:, 0]), np.interp(sp_t, knots_t, kx[:, 1])
    for k, dx in (retarget or []):
        a, b = hold_t[k]
        spx[(sp_t >= a + 3.0) & (sp_t <= b + 1e-9)] += dx
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
    if truth_bias_at is not None:
        t0, t1, dx = truth_bias_at
        xy[(t >= t0) & (t <= t1), 0] += dx
    after = t >= t_land + 3
    if land_bias_first_s is not None:            # motors off on the 0.5 s status grid at >= t_land + 5
        after = after & (t <= np.ceil((t_land + 5) * 2) / 2 + land_bias_first_s)
    xy[after] += np.array(land_bias)
    d = {'t': t, 'xy': xy, 'z': h + 0.3, 'vz_up': np.gradient(h, t), 'ekf_t': ekf_t, 'ekf_xyz': E,
         'sp_t': sp_t, 'sp_xyz': np.column_stack([spx + OFFSET[0], spy + OFFSET[1], np.full(len(sp_t), 0.7)]),
         'kill': False, '_hold_t': hold_t, '_sp_step': 0.2}
    d.update(status([(t_land, 18)], arm_off_at=t_land + 5))
    return d


def c7_judge(d, route=ROUTE, flown='same', code=0, log=LOG_OK):
    flown = [p[:2] for p in route] if flown == 'same' else flown
    res, v = C7.evaluate(d, route, flown, (0.0, 0.0), code, None, '', log)
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

    def test_no_rounding_before_compare(self):
        """r3: 0.2504 m point error and 0.1504 m landing are fails (r2 rounded them to 0.250 / 0.150)."""
        word, failed, res = c7_judge(c7_flight(point_bias=(1, (0.2504, 0.0))))
        self.assertIn('points_within_0p25', failed)
        self.assertIn('landing_within_0p15', c7_judge(c7_flight(land_bias=(0.1504, 0.0)))[1])

    def test_retarget_hold_at_point_ok(self):
        """r3: hover() re-aims the setpoint 6 cm at a reached point: an extra hold, not a route point."""
        word, failed, res = c7_judge(c7_flight(retarget=[(0, 0.06), (2, 0.06)]))
        self.assertEqual(word, 'PASS', failed)
        self.assertEqual(len(res['holds']), 6)

    def test_retarget_beyond_tolerance_fails(self):
        # 0.30 m away from the point (fly_to tolerance 0.25): not a re-target at the point
        self.assertIn('holds_match_route', c7_judge(c7_flight(retarget=[(1, 0.30)]))[1])

    def test_stop_on_a_leg_fails(self):
        # a 2 s stop 0.2 m before point 2 on the leg (not at a reached point): the holds cannot be read as the route
        self.assertIn('holds_match_route', c7_judge(c7_flight(stop_before=(1, 0.2)))[1])

    def test_error_at_the_moment_of_the_next_command(self):
        """Truth off the point only from 0.15 s before the setpoint moves on (the first moved sample ends the window)."""
        d = c7_flight()
        b = d['_hold_t'][1][1]                       # setpoint leaves point 2 after this time
        b_first_moved = (np.floor(b / 0.2 + 1e-6) + 1) * 0.2
        d2 = c7_flight(truth_bias_at=(b_first_moved - 0.15, b_first_moved + 0.05, 0.30))
        word, failed, res = c7_judge(d2)
        self.assertIn('points_within_0p25', failed)
        self.assertGreater(res['points'][1]['err_at_next_command_m'], 0.25)
        # re-target holds at the point do not end the point early: bias at the end of the re-target hold counts
        d3 = c7_flight(retarget=[(1, 0.06)], truth_bias_at=(b_first_moved - 0.15, b_first_moved + 0.05, 0.30))
        self.assertIn('points_within_0p25', c7_judge(d3)[1])

    def test_error_right_after_arrival(self):
        d = c7_flight()
        a = d['_hold_t'][1][0]                       # setpoint reaches point 2 (arrival is about here)
        self.assertIn('points_within_0p25', c7_judge(c7_flight(truth_bias_at=(a + 0.3, a + 1.0, 0.30)))[1])
        # r4: only the first 0.2 s after the arrival itself (arrival time of the clean flight, same EKF)
        t_arr = c7_judge(d)[2]['points'][1]['arrival_s']
        self.assertIn('points_within_0p25', c7_judge(c7_flight(truth_bias_at=(t_arr - 0.005, t_arr + 0.2, 0.30)))[1])

    def test_clean_log_lines_are_not_aborts(self):
        """r4: lines of a normal flight (drone.py / scripts) must not match the abort or guard patterns."""
        clean = ('x\n=== FLY TO (0.0, 0.7, 1.3) ===\nHovering 1.5s...\n[HOVER] t=12 x=0.01 y=0.02 z=1.00 markers=4\n'
                 'HOVER END held=65.0s reason=full time\nC6 HOVER RESULT: OK held=65.0s reason=full time landed=True\n'
                 'safe_land: precision XY=NaN -> straight land (no precision approach)\n'
                 '[LAND] z=0.05 vz=-0.10 armed=True\nLanded and disarmed.\n'
                 '[INFO] [1.0] [flight]: /land: landing (AUTO.LAND)\n=== LANDING ===\n')
        self.assertEqual(G.emergencies(c5_flight(), 0, None, '', clean), [])

    def test_script_own_abort_landing_is_emergency(self):
        """r4 (review of r3): the scripts' own emergency landings / aborts fail, even with '=== LANDING ==='."""
        for line in ('VISION SILENT >3s during hover -- safe_land',                    # flight.py
                     'flight_marker: vision silent >3.0s -- aborting',                  # flight_marker.py
                     'flight_marker_loop: vision silent >3.0s -- emergency land',       # flight_marker_loop.py
                     'Waypoint (0.00, 1.40) failed -- aborting mission',                 # flight_marker_loop.py
                     'HOVER END held=12.0s reason=vision silent >3s'):                   # hover_marker0.py
            with self.subTest(line=line[:30]):
                word, failed, res = c5_judge(c5_flight(), log='x\n' + line + '\n=== LANDING ===\n')
                self.assertIn('no_emergency', failed)
                self.assertTrue(any('script emergency landing / abort' in e for e in res['emergencies']))
                self.assertIn('no_emergency', c7_judge(c7_flight(), log='x\n' + line + '\n=== LANDING ===\n')[1])

    def test_landing_mean_over_first_second(self):
        self.assertIn('landing_within_0p15', c7_judge(c7_flight(land_bias=(0.16, 0.0), land_bias_first_s=1.05))[1])

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
