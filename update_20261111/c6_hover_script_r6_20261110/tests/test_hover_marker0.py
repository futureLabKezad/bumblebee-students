#!/usr/bin/env python3
"""Tests for hover_marker0.py r6 (variant B, settle before fly_to, vision = new vpe_fix poses, move low then climb) without ROS, a simulator or a drone (09.11.2026).

A fake `drone` module records every call. Time is a fake clock (65 s hover runs
instantly). Ctrl+C is a real SIGINT raised inside the fake call of the chosen stage;
the fake enable_safe_interrupt() installs the same kind of handler as drone.py
(sets should_land). Run: python3 -I tests/test_hover_marker0.py -v
"""
import io
import math
import os
import re
import runpy
import signal
import sys
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), 'hover_marker0.py')

PREFLIGHT = ['check_flight_profile', 'require_aruco', 'wait_yaw_lock',
             'wait_position_stable', 'require_vpe_link', 'print_pos_fresh']
FLIGHT = ['takeoff', 'fly_to', 'fly_to', 'safe_land']   # r6: move low, then climb
# Calls that command the drone. None of them may happen before takeoff.
COMMANDS = {'takeoff', 'fly_to', 'safe_land', 'navigate', 'navigate_wait', 'hover',
            'move', 'land', 'arming', 'set_mode', 'set_param', 'apply_flight_profile'}


class Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


class FakeDrone:
    """Builds a module object named 'drone' with the public API the script uses."""

    def __init__(self, clock, **cfg):
        self.clock = clock
        self.calls = []
        self.cfg = dict(profile=(10, 10, []), aruco_ok=True, yaw_ok=True, stable_ok=True,
                        vpe_ok=True, start=(0.02, -0.03, 0.01), takeoff_ok=True, fly_ok=True,
                        land_ok=True, sigint_at=None, sigint_hover_tick=None,
                        fcu=None, markers=None, old_image=False, profile_raises=False, no_vpa=False,
                        # r4 settle phase (after takeoff, before fly_to): drone z - target z per check
                        settle_dz=lambda n: min(-0.12 + 0.01 * n, 0.0), settle_raises=None,
                        sigint_settle_tick=None, settle_fcu=None, settle_markers=None,
                        # r5: vision = a NEW vpe_fix pose arrives on a watch tick when markers(n) > 0;
                        # poses also arrive during takeoff/fly_to unless switched off; no pose at all: never_pose
                        pose_in_takeoff=True, pose_in_fly=True, never_pose=False, raw_markers=2,
                        takeoff_pose_age=0.0, takeoff_s=8.0,
                        # r6: second fly_to (climb over marker 0) and the settle after it
                        climb_ok=True, pose_in_climb=True, climb_dz=lambda n: min(-0.06 + 0.01 * n, 0.0),
                        climb_markers=None, climb_fcu=None, sigint_climb_tick=None)
        self.cfg.update(cfg)
        self.hover_ticks = 0
        self.settle_ticks = 0
        self.settle_checks = 0
        self.hovering = False      # armed in the air (after takeoff)
        self.at_marker = False     # r6: both fly_to done (climb settle, then hover)
        self.flys = 0              # r6: fly_to calls so far
        self.climb_ticks = 0
        self.climb_checks = 0
        m = types.ModuleType('drone')
        m.should_land = False
        # r5: the raw count is fixed (cfg raw_markers) and must not drive the watchdog
        m._aruco_markers_used = self.cfg['raw_markers']
        m._markers_used_age = lambda: 0.1
        self.last_pose_t = None
        if not self.cfg['no_vpa']:
            m.vision_pose_age = self.vision_pose_age
        self.m = m
        names = ['get_fcu_status', 'enable_safe_interrupt', 'check_flight_profile',
                 'require_aruco', 'wait_yaw_lock', 'wait_position_stable', 'require_vpe_link',
                 'print_pos_fresh', 'takeoff', 'fly_to', 'safe_land', 'get_pos', '_shutdown',
                 'apply_flight_profile', 'set_param', 'navigate', 'navigate_wait', 'hover',
                 'move', 'land', 'arming', 'set_mode']
        for n in names:
            if n == 'check_flight_profile' and self.cfg['old_image']:
                continue
            setattr(m, n, self._wrap(n))

    def vision_pose_age(self):
        if self.last_pose_t is None:
            return float('inf')
        return self.clock.t - self.last_pose_t

    def _pose(self):
        if not self.cfg['never_pose']:
            self.last_pose_t = self.clock.t

    def _wrap(self, name):
        def f(*a, **k):
            self.calls.append((name, a, k, self.m.should_land))
            return getattr(self, 'do_' + name, self.do_default)(name, *a, **k)
        return f

    def _sigint(self, stage):
        if self.cfg['sigint_at'] == stage:
            signal.raise_signal(signal.SIGINT)

    # --- fakes ---------------------------------------------------------------------
    def do_default(self, name, *a, **k):
        if name in ('apply_flight_profile', 'set_param', 'navigate', 'navigate_wait', 'hover',
                    'move', 'land', 'arming', 'set_mode'):
            raise AssertionError('script must not call drone.%s' % name)
        return None

    def do_enable_safe_interrupt(self, name):
        def handler(sig, frame):
            self.m.should_land = True
        signal.signal(signal.SIGINT, handler)

    def do_get_fcu_status(self, name, *a, **k):
        if self.hovering and not self.at_marker:
            self.settle_ticks += 1
            if self.cfg['sigint_settle_tick'] == self.settle_ticks:
                signal.raise_signal(signal.SIGINT)
            if self.cfg['settle_markers'] is None or self.cfg['settle_markers'](self.settle_ticks) > 0:
                self._pose()
            if self.cfg['settle_fcu'] is not None:
                return self.cfg['settle_fcu'](self.settle_ticks)
        if self.hovering and self.at_marker and '=== HOVER' not in sys.stdout.getvalue():
            # r6: settle after the climb (the script has not started the hover yet)
            self.climb_ticks += 1
            if self.cfg['sigint_climb_tick'] == self.climb_ticks:
                signal.raise_signal(signal.SIGINT)
            if self.cfg['climb_markers'] is None or self.cfg['climb_markers'](self.climb_ticks) > 0:
                self._pose()
            if self.cfg['climb_fcu'] is not None:
                return self.cfg['climb_fcu'](self.climb_ticks)
        elif self.hovering and self.at_marker:
            self.hover_ticks += 1
            if self.cfg['sigint_hover_tick'] == self.hover_ticks:
                signal.raise_signal(signal.SIGINT)
            if self.cfg['markers'] is None or self.cfg['markers'](self.hover_ticks) > 0:
                self._pose()
            if self.cfg['fcu'] is not None:
                return self.cfg['fcu'](self.hover_ticks)
        return {'connected': True, 'armed': self.hovering, 'mode': 'OFFBOARD' if self.hovering else 'STABILIZED',
                'cell': float('nan'), 'ok': True}

    def do_check_flight_profile(self, name, profile):
        assert profile == 'INDOOR_ARUCO_SLOW'
        self._sigint(name)
        if self.cfg['profile_raises']:
            raise RuntimeError('GetParameters failed')
        return self.cfg['profile']

    def do_require_aruco(self, name, **k):
        self._sigint(name)
        if not self.cfg['aruco_ok']:
            raise RuntimeError('require_aruco: need >=1 markers, got 0')
        return [0]

    def do_wait_yaw_lock(self, name, **k):
        self._sigint(name)
        return self.cfg['yaw_ok']

    def do_wait_position_stable(self, name, **k):
        self._sigint(name)
        return self.cfg['stable_ok']

    def do_require_vpe_link(self, name, **k):
        self._sigint(name)
        if not self.cfg['vpe_ok']:
            raise RuntimeError('vpe link below 8 Hz')

    def do_print_pos_fresh(self, name, *a, **k):
        self._sigint(name)
        self._pose()
        if self.cfg['start'] is None:
            return None
        x, y, z = self.cfg['start']
        return types.SimpleNamespace(x=x, y=y, z=z, armed=False, mode='STABILIZED')

    def do_takeoff(self, name, **k):
        self._sigint(name)
        self.clock.sleep(self.cfg['takeoff_s'])
        if self.cfg['pose_in_takeoff']:
            self._pose()
            if self.last_pose_t is not None:
                self.last_pose_t -= self.cfg['takeoff_pose_age']   # last pose that long before takeoff() returns
        ok = self.cfg['takeoff_ok'] and not self.m.should_land
        self.hovering = ok
        return ok

    def do_fly_to(self, name, **k):
        self.flys += 1
        self._sigint(name if self.flys == 1 else 'fly_to_climb')
        self.clock.sleep(3.0)
        if self.flys == 1:
            if self.cfg['pose_in_fly']:
                self._pose()
            return self.cfg['fly_ok'] and not self.m.should_land
        if self.cfg['pose_in_climb']:
            self._pose()
        ok = self.cfg['climb_ok'] and not self.m.should_land
        self.at_marker = ok
        return ok

    def do_get_pos(self, name, *a, **k):
        if k.get('frame_id') == 'navigate_target' and self.at_marker:
            self.climb_checks += 1     # r6: settle after the climb
            return (0.0, 0.0, self.cfg['climb_dz'](self.climb_checks))
        if k.get('frame_id') == 'navigate_target':
            self.settle_checks += 1
            if self.cfg['settle_raises'] is not None and self.cfg['settle_raises'](self.settle_checks):
                raise RuntimeError('Service get_telemetry timed out')
            return (0.0, 0.0, self.cfg['settle_dz'](self.settle_checks))
        return (0.01, 0.02, 1.0)

    def do_safe_land(self, name, **k):
        self.hovering = False
        self._sigint(name)
        return self.cfg['land_ok']


def run(**cfg):
    clock = Clock()
    fd = FakeDrone(clock, **cfg)
    old = signal.getsignal(signal.SIGINT)
    out = io.StringIO()
    code = None
    try:
        with mock.patch.dict(sys.modules, {'drone': fd.m}), \
                mock.patch.object(time, 'monotonic', clock.monotonic), \
                mock.patch.object(time, 'sleep', clock.sleep), \
                redirect_stdout(out):
            try:
                runpy.run_path(SCRIPT, run_name='__main__')
            except SystemExit as e:
                code = e.code
    finally:
        signal.signal(signal.SIGINT, old)
    names = [c[0] for c in fd.calls if c[0] not in ('get_fcu_status', 'get_pos')]
    return code, names, fd, out.getvalue()


class DryRun(unittest.TestCase):
    def test_full_flight_order_and_args(self):
        code, names, fd, out = run()
        self.assertEqual(code, 0, out)
        self.assertEqual(names, ['enable_safe_interrupt'] + PREFLIGHT + FLIGHT + ['_shutdown'])
        first = [c[0] for c in fd.calls][:2]
        self.assertEqual(first, ['get_fcu_status', 'enable_safe_interrupt'],
                         'node first, then the Ctrl+C handler')
        k = {c[0]: c[2] for c in fd.calls}
        self.assertEqual(k['takeoff']['height'], 0.75)   # r6: below the C6 band
        # r3: flies to map (0, 0) = marker 0 centre slowly, and lands there
        # r6: first at START z + 0.75, then straight up to START z + 1.0
        f1, f2 = [c[2] for c in fd.calls if c[0] == 'fly_to']
        self.assertEqual((f1['x'], f1['y']), (0.0, 0.0))
        self.assertAlmostEqual(f1['z'], 0.01 + 0.75, places=9)
        self.assertEqual((f1['speed'], f1['tolerance'], f1['settle_speed']), (0.1, 0.12, 0.05))
        self.assertEqual((f2['x'], f2['y']), (0.0, 0.0))
        self.assertAlmostEqual(f2['z'], 0.01 + 1.0, places=9)
        self.assertEqual((f2['speed'], f2['tolerance'], f2['settle_speed']), (0.1, 0.12, 0.05))
        self.assertEqual((k['safe_land']['x'], k['safe_land']['y']), (0.0, 0.0))
        self.assertEqual((k['safe_land']['precision_speed'], k['safe_land']['precision_tolerance']),
                         (0.1, 0.18))
        hov = out.index('=== HOVER 65s')
        self.assertLess(out.index('Hover point = marker 0 centre'), hov)
        # r4: settle between takeoff and fly_to; reads only, in the navigate_target frame
        allc = [c[0] for c in fd.calls]
        i_t, i_f = allc.index('takeoff'), allc.index('fly_to')
        between = fd.calls[i_t + 1:i_f]
        self.assertTrue(between and all(c[0] in ('get_fcu_status', 'get_pos') for c in between), between)
        frames = [c[2].get('frame_id') for c in between if c[0] == 'get_pos']
        # height checks in navigate_target; the 1 Hz [SETTLE] print reads map (default frame)
        self.assertEqual(frames.count('navigate_target'), fd.settle_checks)
        self.assertTrue(set(frames) <= {'navigate_target', None}, frames)
        # dz: -0.11, -0.10, ... -> below <= 0.03 from check 9 on; 3 in a row -> fly_to after check 11
        self.assertEqual(fd.settle_checks, 11)
        self.assertIn('=== SETTLE END waited=', out)
        self.assertIn('reason=height reached ===', out)
        self.assertLess(out.index('reason=height reached'), hov)
        # r6: second settle (after the climb), also before the hover: dz -0.05.. -> fly on after check 5
        self.assertEqual(fd.climb_checks, 5)
        self.assertEqual(out.count('reason=height reached ==='), 2)
        self.assertLess(out.index('below the takeoff height'), out.index('below the hover height'))
        self.assertLess(out.rindex('reason=height reached'), hov)
        self.assertIn('r6 order: takeoff to z 0.76 (START z + 0.75 m), move to marker 0 there, climb to z 1.01', out)
        m = re.search(r'HOVER END held=([\d.]+)s reason=full time', out)
        self.assertTrue(m, out)
        self.assertGreaterEqual(float(m.group(1)), 65.0)
        self.assertLess(float(m.group(1)), 65.5)
        self.assertIn('C6 HOVER RESULT: OK', out)
        self.assertIn('=== HOVER 65s over marker 0 START ===', out)
        self.assertGreaterEqual(out.count('[HOVER] t='), 59)

    def test_landing_not_confirmed_is_not_ok(self):
        code, names, fd, out = run(land_ok=False)
        self.assertEqual(code, 4)
        self.assertIn('C6 HOVER RESULT: CUT', out)


class Profile(unittest.TestCase):
    def assertNoFlight(self, names):
        self.assertFalse(COMMANDS & set(names), names)

    def test_mismatch_refuses(self):
        code, names, fd, out = run(profile=(6, 10, ['MPC_XY_P: PX4 0.4, profile 0.25']))
        self.assertEqual(code, 3)
        self.assertIn('only 6/10 PX4 params match', out)
        self.assertIn('MPC_XY_P', out)
        self.assertNoFlight(names)
        self.assertNotIn('require_aruco', names)

    def test_check_raises_refuses(self):
        code, names, fd, out = run(profile_raises=True)
        self.assertEqual(code, 3)
        self.assertNoFlight(names)

    def test_old_image_without_check_refuses_and_never_writes(self):
        code, names, fd, out = run(old_image=True)
        self.assertEqual(code, 3)
        self.assertIn('no check_flight_profile', out)
        self.assertNoFlight(names)   # apply_flight_profile (writes in port-rc3) never called


class Preflight(unittest.TestCase):
    def check(self, code_expected, text, **cfg):
        code, names, fd, out = run(**cfg)
        self.assertEqual(code, code_expected, out)
        self.assertIn(text, out)
        self.assertFalse(COMMANDS & set(names), names)

    def test_no_markers_f1(self):
        self.check(1, 'detector sleeps until arming', aruco_ok=False)

    def test_no_yaw_lock(self):
        self.check(1, 'yaw_world not locked', yaw_ok=False)

    def test_not_stable(self):
        self.check(1, 'position never converged', stable_ok=False)

    def test_no_vpe(self):
        self.check(1, 'vpe link below 8 Hz', vpe_ok=False)

    def test_start_nan(self):
        self.check(1, 'START position NaN', start=(float('nan'), 0.0, 0.0))

    def test_start_y_nan(self):
        self.check(1, 'START position NaN', start=(0.0, float('nan'), 0.0))

    def test_start_z_nan(self):
        self.check(1, 'START position NaN', start=(0.0, 0.0, float('nan')))

    def test_start_none(self):
        code, names, fd, out = run(start=None)
        self.assertEqual(code, 1, out)
        self.assertFalse(COMMANDS & set(names), names)

    def test_variant_a_map_frame_refuses(self):
        """Gazebo s04 (4035, variant A): on marker 0 the EKF map read (0.00, 1.53). r3 refuses:
        fly_to(0, 0) would take the drone 1.5 m away."""
        self.check(1, 'is 1.53 m from marker 0 (limit 0.50)', start=(0.0, 1.53, -0.05))

    def test_start_offset_limit(self):
        code, names, fd, out = run(start=(0.30, -0.39, 0.0))     # 0.492 m: flies
        self.assertEqual(code, 0, out)
        self.check(1, 'map is not the marker frame', start=(-0.31, 0.40, 0.0))   # 0.506 m
        self.check(1, 'map is not the marker frame', start=(0.0, -0.51, 0.0))

    def test_s9_c6_04_start(self):
        """Variant B run s9_c6_04: START (-0.05, -0.05, z -0.31). Hover z = 0.69, as takeoff's target."""
        code, names, fd, out = run(start=(-0.05, -0.05, -0.31))
        self.assertEqual(code, 0, out)
        f1, f = [c[2] for c in fd.calls if c[0] == 'fly_to']
        self.assertAlmostEqual(f1['z'], 0.44, places=9)   # r6: START z + 0.75
        self.assertAlmostEqual(f['z'], 0.69, places=9)
        self.assertEqual((f['x'], f['y']), (0.0, 0.0))
        self.assertIn('z 0.69 (START z + 1.0 m); START (-0.05, -0.05) is 0.07 m off', out)


class CtrlC(unittest.TestCase):
    def test_before_takeoff_never_flies(self):
        for stage in PREFLIGHT:
            with self.subTest(stage=stage):
                code, names, fd, out = run(sigint_at=stage)
                self.assertEqual(code, 1, out)
                self.assertIn('Ctrl+C before takeoff', out)
                self.assertFalse(COMMANDS & set(names), names)
                self.assertEqual(names[-1], '_shutdown')

    def test_in_flight_lands(self):
        code, names, fd, out = run(sigint_at='takeoff')
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'safe_land'])
        land = [c for c in fd.calls if c[0] == 'safe_land'][0]
        self.assertTrue(land[3], 'should_land already set when safe_land starts')
        self.assertIn('reason=Ctrl+C', out)
        self.assertNotIn('HOVER 60s', out)

    def test_during_fly_to_lands(self):
        code, names, fd, out = run(sigint_at='fly_to')
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'fly_to', 'safe_land'])
        land = [c for c in fd.calls if c[0] == 'safe_land'][0]
        self.assertTrue(land[3], 'should_land already set when safe_land starts')
        self.assertIn('reason=Ctrl+C', out)
        self.assertNotIn('=== HOVER 65s', out)

    def test_during_hover_lands_at_once(self):
        code, names, fd, out = run(sigint_hover_tick=50)
        self.assertEqual(code, 4)
        self.assertIn('reason=Ctrl+C', out)
        held = float(re.search(r'HOVER END held=([\d.]+)s', out).group(1))
        self.assertLess(held, 6.0)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'fly_to', 'fly_to', 'safe_land'])

    def test_during_landing_landing_goes_on(self):
        code, names, fd, out = run(sigint_at='safe_land')
        self.assertEqual(names.count('safe_land'), 1)
        self.assertEqual(code, 4)   # Ctrl+C is recorded; landing itself was not repeated
        self.assertIn('reason=Ctrl+C during landing', out)


class InFlight(unittest.TestCase):
    def test_pilot_takes_over(self):
        fcu = lambda n: {'ok': True, 'connected': True, 'armed': True, 'cell': 0.0,  # noqa: E731
                         'mode': 'POSCTL' if n >= 20 else 'OFFBOARD'}
        code, names, fd, out = run(fcu=fcu)
        self.assertEqual(code, 4)
        self.assertIn('pilot/failsafe has control (mode=POSCTL)', out)
        # nothing re-sent after the takeover except safe_land (which itself sends nothing then)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'fly_to', 'fly_to', 'safe_land'])

    def test_disarm_during_hover(self):
        fcu = lambda n: {'ok': True, 'connected': True, 'armed': n < 10, 'mode': 'OFFBOARD', 'cell': 0.0}  # noqa: E731
        code, names, fd, out = run(fcu=fcu)
        self.assertEqual(code, 4)
        self.assertIn('reason=disarmed', out)

    def test_fcu_state_unknown(self):
        fcu = lambda n: {'ok': n < 10, 'connected': n < 10, 'armed': True, 'mode': 'OFFBOARD', 'cell': 0.0}  # noqa: E731
        code, names, fd, out = run(fcu=fcu)
        self.assertEqual(code, 4)
        held = float(re.search(r'HOVER END held=([\d.]+)s', out).group(1))
        self.assertIn('FCU state unknown', out)
        self.assertLess(held, 5.0)

    def test_vision_silent_lands(self):
        code, names, fd, out = run(markers=lambda n: 0 if n >= 100 else 2)
        self.assertEqual(code, 4)
        self.assertIn('vision silent >3s', out)
        held = float(re.search(r'HOVER END held=([\d.]+)s', out).group(1))
        self.assertTrue(12.8 < held < 14.0, held)

    def test_short_vision_gap_tolerated(self):
        code, names, fd, out = run(markers=lambda n: 0 if 100 <= n < 120 else 2)
        self.assertEqual(code, 0, out)

    def test_takeoff_fails_no_hover(self):
        code, names, fd, out = run(takeoff_ok=False)
        self.assertEqual(code, 4)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'safe_land'])
        self.assertNotIn('HOVER 60s', out)
        self.assertIn('takeoff not completed', out)

    def test_fly_to_fails_no_hover(self):
        """fly_to False (timeout, guard, pilot): no hover; safe_land (it sends nothing if the pilot has it)."""
        code, names, fd, out = run(fly_ok=False)
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'fly_to', 'safe_land'])
        self.assertNotIn('=== HOVER 65s', out)
        self.assertIn('reason=marker 0 centre not reached (fcu ok=True armed=True mode=OFFBOARD)', out)
        self.assertIn('C6 HOVER RESULT: CUT', out)


class Settle(unittest.TestCase):
    """r4: after takeoff wait until the estimate is <= 0.03 m below the takeoff target (3 checks in a row)."""

    def cut(self, text, **cfg):
        code, names, fd, out = run(**cfg)
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'safe_land'])
        self.assertNotIn('=== HOVER 65s', out)
        self.assertIn(text, out)
        return code, names, fd, out

    def test_s9_c6r3_03_never_settles_times_out(self):
        code, names, fd, out = self.cut('reason=takeoff height not reached in 15s', settle_dz=lambda n: -0.08)
        waited = float(re.search(r'SETTLE END waited=([\d.]+)s', out).group(1))
        self.assertTrue(15.0 <= waited < 15.2, waited)
        self.assertIn('C6 HOVER RESULT: CUT', out)

    def test_boundary_exactly_3cm_counts(self):
        code, names, fd, out = run(settle_dz=lambda n: -0.03)
        self.assertEqual(code, 0, out)
        self.assertEqual(fd.settle_checks, 3)

    def test_just_below_3cm_does_not_count(self):
        self.cut('takeoff height not reached', settle_dz=lambda n: -0.031)

    def test_above_target_counts(self):
        code, names, fd, out = run(settle_dz=lambda n: 0.04)
        self.assertEqual(code, 0, out)
        self.assertEqual(fd.settle_checks, 3)

    def test_needs_three_in_a_row(self):
        # -0.02, -0.02, -0.05, ... never 3 in a row -> timeout
        self.cut('takeoff height not reached', settle_dz=lambda n: -0.05 if n % 3 == 0 else -0.02)
        # 2 bad then good from check 3 on -> fly_to after check 5
        code, names, fd, out = run(settle_dz=lambda n: -0.2 if n <= 2 else -0.01)
        self.assertEqual(code, 0, out)
        self.assertEqual(fd.settle_checks, 5)

    def test_nan_and_read_errors_do_not_count(self):
        self.cut('takeoff height not reached', settle_dz=lambda n: float('nan'))
        self.cut('takeoff height not reached', settle_dz=lambda n: -0.01, settle_raises=lambda n: n % 2 == 0)
        code, names, fd, out = run(settle_dz=lambda n: -0.01, settle_raises=lambda n: n <= 4)
        self.assertEqual(code, 0, out)
        self.assertEqual(fd.settle_checks, 7)

    def test_pilot_takes_over_during_settle(self):
        fcu = lambda n: {'ok': True, 'connected': True, 'armed': True, 'cell': 0.0,  # noqa: E731
                         'mode': 'POSCTL' if n >= 3 else 'OFFBOARD'}
        self.cut('reason=pilot/failsafe has control (mode=POSCTL)', settle_fcu=fcu, settle_dz=lambda n: -0.1)

    def test_disarm_during_settle(self):
        fcu = lambda n: {'ok': True, 'connected': True, 'armed': n < 3, 'mode': 'OFFBOARD', 'cell': 0.0}  # noqa: E731
        self.cut('reason=disarmed', settle_fcu=fcu, settle_dz=lambda n: -0.1)

    def test_fcu_unknown_during_settle(self):
        fcu = lambda n: {'ok': n < 3, 'connected': n < 3, 'armed': True, 'mode': 'OFFBOARD', 'cell': 0.0}  # noqa: E731
        self.cut('FCU state unknown >3s', settle_fcu=fcu, settle_dz=lambda n: -0.1)

    def test_vision_silent_during_settle(self):
        # r6 A: first settle limit is 25 s from the takeoff; here the settle times out first (8 + 15 s)
        self.cut('takeoff height not reached in 15s', settle_markers=lambda n: 0, settle_dz=lambda n: -0.1)

    def test_safety_checked_before_height(self):
        # pilot takes over on the very check where the height is reached: the takeover wins
        fcu = lambda n: {'ok': True, 'connected': True, 'armed': True, 'cell': 0.0,  # noqa: E731
                         'mode': 'POSCTL' if n >= 3 else 'OFFBOARD'}
        self.cut('reason=pilot/failsafe has control (mode=POSCTL)', settle_fcu=fcu, settle_dz=lambda n: 0.0)

    def test_ctrl_c_during_settle_lands(self):
        code, names, fd, out = self.cut('reason=Ctrl+C', sigint_settle_tick=4, settle_dz=lambda n: -0.1)
        land = [c for c in fd.calls if c[0] == 'safe_land'][0]
        self.assertTrue(land[3], 'should_land already set when safe_land starts')


class VisionR5(unittest.TestCase):
    """r5: vision = new vpe_fix pose (vision_pose_age <= 1 s); cut when absent > 3 s, i.e. age > 4 s;
    silence counted at the latest from the takeoff (S4)."""

    def held(self, out):
        return float(re.search(r'HOVER END held=([\d.]+)s', out).group(1))

    def test_raw_markers_zero_but_poses_flow_no_cut(self):
        # raw count 0 the whole flight, new vpe_fix poses keep coming -> no cut
        code, names, fd, out = run(raw_markers=0)
        self.assertEqual(code, 0, out)

    def test_raw_markers_present_but_no_new_pose_cuts(self):
        # false markers keep the raw count up (fake _aruco_markers_used = 2 always), but no new pose from tick 100
        code, names, fd, out = run(markers=lambda n: 0 if n >= 100 else 2)
        self.assertEqual(code, 4, out)
        self.assertIn('vision silent >3s (no new vpe_fix pose for 4.', out)
        self.assertTrue(13.9 <= self.held(out) <= 14.2, self.held(out))

    def test_gap_3_8s_tolerated_4_2s_cut(self):
        code, names, fd, out = run(markers=lambda n: 0 if 100 <= n < 138 else 2)
        self.assertEqual(code, 0, out)
        code, names, fd, out = run(markers=lambda n: 0 if 100 <= n < 143 else 2)
        self.assertEqual(code, 4, out)
        self.assertIn('vision silent >3s', out)

    def test_never_a_pose_counts_from_takeoff(self):
        # S4 + r6 A: no pose at all -> the first settle never ends (height alone is not enough), no fly_to
        code, names, fd, out = run(never_pose=True)
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'safe_land'])
        # review 10.11: height there after 15 s, no pose -> waits on until 25 s from the takeoff, then the watchdog
        self.assertIn('height reached, waiting for a new vpe_fix pose (until 25s after the takeoff)', out)
        self.assertIn('reason=vision silent >24s (no new vpe_fix pose for 25.', out)
        waited = float(re.search(r'SETTLE END waited=([\d.]+)s', out).group(1))
        self.assertTrue(17.0 <= waited < 17.2, waited)
        # with a long takeoff the 25 s limit (counted from the takeoff) cuts first
        code, names, fd, out = run(never_pose=True, takeoff_s=20.0)
        self.assertEqual(code, 4, out)
        self.assertNotIn('fly_to', names)
        self.assertIn('vision silent >24s (no new vpe_fix pose for 25.', out)
        waited = float(re.search(r'SETTLE END waited=([\d.]+)s', out).group(1))
        self.assertTrue(5.0 <= waited < 5.2, waited)

    def test_vision_back_late_in_the_climb(self):
        # r6 A: takeoff() to 0.75 m returns at ~0.60 m, vision comes back at 0.64-0.73 m (Gazebo);
        # last pose 6.5 s old at the first settle check, back after 2 s -> no cut, fly_to only after it is back
        code, names, fd, out = run(takeoff_pose_age=6.5, settle_markers=lambda n: 0 if n <= 20 else 2)
        self.assertEqual(code, 0, out)
        self.assertGreaterEqual(fd.settle_checks, 21)
        self.assertIn('below the takeoff height and a new vpe_fix pose', out)

    def test_height_reached_but_no_pose_waits(self):
        # r6 A: height reached at check 11, pose only from tick 30 -> fly_to after tick 30, not at check 11
        code, names, fd, out = run(settle_markers=lambda n: 0 if n < 30 else 2, takeoff_pose_age=1.0)
        self.assertEqual(code, 0, out)
        self.assertEqual(fd.settle_checks, 30)

    def test_old_pose_does_not_end_first_settle(self):
        # r6 A: last pose at settle tick 1; the height is there from check 13 on, the pose is then 1.2 s old
        # (VISION_AGE_S 1.0) -> the first settle never ends
        code, names, fd, out = run(settle_markers=lambda n: 1 if n == 1 else 0,
                                   settle_dz=lambda n: -0.1 if n <= 12 else 0.0)
        self.assertEqual(code, 4, out)
        self.assertNotIn('fly_to', names)
        # last pose at settle tick 1 (8 s after the takeoff): at 25.5 s it is 17.5 s old -> fallback reason
        self.assertIn('reason=vision silent >1s at 25s after the takeoff (no new vpe_fix pose for 17.', out)

    def test_vision_back_after_15s_flies_on(self):
        # review 10.11: no pose for 16 s of the settle (24 s since the takeoff, < 25 s), then back -> flies on
        code, names, fd, out = run(settle_markers=lambda n: 0 if n <= 160 else 2)
        self.assertEqual(code, 0, out)
        self.assertEqual(names.count('fly_to'), 2)
        waited = float(re.search(r'SETTLE END waited=([\d.]+)s', out).group(1))
        self.assertTrue(16.0 <= waited < 16.3, waited)

    def test_height_lost_while_waiting_for_vision(self):
        # height there in the first 15 s, then lost while vision is back -> no fly_to, own reason
        code, names, fd, out = run(settle_markers=lambda n: 0 if n <= 150 else 2, takeoff_pose_age=2.0,
                                   settle_dz=lambda n: 0.0 if n <= 150 else -0.1)
        self.assertEqual(code, 4, out)
        self.assertNotIn('fly_to', names)
        self.assertIn('reason=takeoff height not held until vision came back', out)

    def test_lost_during_climb_not_reset_at_settle(self):
        # r6 A: last pose before takeoff, none since -> the first settle never ends; with a 20 s takeoff the
        # 25 s limit counted from the takeoff cuts 5 s into the settle (not 25 s after the settle start)
        code, names, fd, out = run(pose_in_takeoff=False, settle_markers=lambda n: 0, takeoff_s=20.0)
        self.assertEqual(code, 4, out)
        self.assertNotIn('fly_to', names)
        self.assertIn('vision silent >24s', out)
        waited = float(re.search(r'SETTLE END waited=([\d.]+)s', out).group(1))
        self.assertLess(waited, 5.2)

    def test_lost_during_fly_to_not_reset_at_climb_settle(self):
        # r6: last pose at the takeoff settle end, none during the two 3 s fly_to -> cut at the climb settle start
        code, names, fd, out = run(pose_in_fly=False, pose_in_climb=False, climb_markers=lambda n: 0)
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'fly_to', 'fly_to', 'safe_land'])
        self.assertIn('vision silent >3s (no new vpe_fix pose for 6.', out)
        self.assertNotIn('=== HOVER 65s', out)

    def test_lost_in_climb_settle_not_reset_at_hover(self):
        # r6: last pose when the climb fly_to returns, none in the climb settle (0.4 s) or the hover
        # -> cut when 4 s have passed in all, ~3.6 s into the hover (not 4 s)
        code, names, fd, out = run(climb_markers=lambda n: 0, markers=lambda n: 0)
        self.assertEqual(code, 4, out)
        self.assertIn('vision silent >3s', out)
        self.assertTrue(3.4 < self.held(out) < 3.8, self.held(out))

    def test_image_before_r2f_refuses_before_arming(self):
        code, names, fd, out = run(no_vpa=True)
        self.assertEqual(code, 1, out)
        self.assertIn('no vision_pose_age (image before r2f)', out)
        self.assertFalse(COMMANDS & set(names), names)
        self.assertNotIn('check_flight_profile', names)

    def test_watchdog_does_not_read_raw_count(self):
        src = open(SCRIPT, encoding='utf-8').read()
        code = '\n'.join(l.split('#')[0] for l in src.splitlines())
        for bad in ('_aruco_markers_used', '_markers_used_age', '_markers_pos_age'):
            self.assertNotIn(bad, code, bad)
        self.assertIn('drone.vision_pose_age()', code)


class OrderR6(unittest.TestCase):
    """r6 (chat 1, 10.11; T40): the move to marker 0 is done at 0.75 m, below the C6 band; then the climb
    to 1.0 m over the centre and a second settle; the hover starts only after that."""

    def no_hover(self, text, **cfg):
        code, names, fd, out = run(**cfg)
        self.assertEqual(code, 4, out)
        self.assertEqual([n for n in names if n in COMMANDS], ['takeoff', 'fly_to', 'fly_to', 'safe_land'])
        self.assertNotIn('=== HOVER 65s', out)
        self.assertIn(text, out)
        self.assertIn('C6 HOVER RESULT: CUT', out)
        return code, names, fd, out

    def test_nothing_sent_between_the_moves(self):
        code, names, fd, out = run()
        allc = [c[0] for c in fd.calls]
        i1 = allc.index('fly_to')
        i2 = allc.index('fly_to', i1 + 1)
        self.assertEqual(i2, i1 + 1, fd.calls[i1:i2 + 1])
        # between the climb and the hover only reads; height checks in navigate_target
        after = [c for c in fd.calls[i2 + 1:] if c[0] != 'safe_land' and c[0] != '_shutdown']
        self.assertTrue(all(c[0] in ('get_fcu_status', 'get_pos') for c in after), after)

    def test_climb_fails_no_hover(self):
        self.no_hover('reason=hover height over marker 0 not reached (fcu ok=True armed=True mode=OFFBOARD)',
                      climb_ok=False)

    def test_climb_settle_times_out_no_hover(self):
        code, names, fd, out = self.no_hover('reason=hover height not reached in 15s', climb_dz=lambda n: -0.08)
        waited = [float(w) for w in re.findall(r'SETTLE END waited=([\d.]+)s', out)]
        self.assertEqual(len(waited), 2)
        self.assertTrue(15.0 <= waited[1] < 15.2, waited)

    def test_pilot_takes_over_in_climb_settle(self):
        fcu = lambda n: {'ok': True, 'connected': True, 'armed': True, 'cell': 0.0,  # noqa: E731
                         'mode': 'POSCTL' if n >= 2 else 'OFFBOARD'}
        self.no_hover('reason=pilot/failsafe has control (mode=POSCTL)', climb_fcu=fcu, climb_dz=lambda n: -0.1)

    def test_vision_silent_in_climb_settle(self):
        self.no_hover('vision silent >3s', pose_in_climb=False, climb_markers=lambda n: 0, climb_dz=lambda n: -0.1)

    def test_ctrl_c_during_climb_lands(self):
        code, names, fd, out = self.no_hover('reason=Ctrl+C', sigint_at='fly_to_climb')
        land = [c for c in fd.calls if c[0] == 'safe_land'][0]
        self.assertTrue(land[3], 'should_land already set when safe_land starts')

    def test_ctrl_c_in_climb_settle_lands(self):
        code, names, fd, out = self.no_hover('reason=Ctrl+C', sigint_climb_tick=2, climb_dz=lambda n: -0.1)
        land = [c for c in fd.calls if c[0] == 'safe_land'][0]
        self.assertTrue(land[3], 'should_land already set when safe_land starts')

    def test_low_height_below_band_with_overshoot_margin(self):
        # C6 band starts at 0.90; max takeoff overshoot in 27 Gazebo runs +0.053 m; vision >= 95 % from 0.70 m
        src = open(SCRIPT, encoding='utf-8').read()
        low = float(re.search(r'^LOW_H = ([\d.]+) ', src, re.M).group(1))
        self.assertLessEqual(low + 0.053, 0.90 - 0.09)
        self.assertGreaterEqual(low, 0.70)


class Source(unittest.TestCase):
    """The script itself: no PX4 parameter writes, no direct mode/arming commands."""

    def test_no_forbidden_calls(self):
        src = open(SCRIPT, encoding='utf-8').read()
        code = '\n'.join(l.split('#')[0] for l in src.splitlines())
        for bad in ('set_param(', 'apply_flight_profile(', 'arming(', 'set_mode(', 'navigate(',
                    'navigate_wait(', 'drone.hover(', 'drone.land(', 'motor_test','subprocess', 'os.system',
                    'pkill', 'set_aruco_map('):
            self.assertNotIn(bad, code, bad)

    def test_api_matches_fixed_image(self):
        """Every drone.X(...) of the script exists in the fixed drone.py, with those keyword names."""
        import ast
        fixed = os.environ.get('BB_FIXED_DRONE',
                               '/work/fixed_image_r2f_20261110/src/bumblebee/examples/drone.py')
        if not os.path.exists(fixed):
            self.skipTest('fixed drone.py not found: ' + fixed)
        lib = ast.parse(open(fixed, encoding='utf-8').read())
        funcs = {n.name: n for n in lib.body if isinstance(n, ast.FunctionDef)}
        names = {t.id for n in lib.body if isinstance(n, ast.Assign) for t in n.targets
                 if isinstance(t, ast.Name)}
        used = 0
        for node in ast.walk(ast.parse(open(SCRIPT, encoding='utf-8').read())):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == 'drone':
                self.assertTrue(node.attr in funcs or node.attr in names, node.attr)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'drone':
                f = funcs[node.func.attr]
                params = [a.arg for a in f.args.args + f.args.kwonlyargs]
                for kw in node.keywords:
                    self.assertIn(kw.arg, params, '%s(%s=)' % (node.func.attr, kw.arg))
                self.assertLessEqual(len(node.args), len(params), node.func.attr)
                used += 1
        self.assertGreater(used, 10)

    def test_numbers(self):
        src = open(SCRIPT, encoding='utf-8').read()
        self.assertIn("HOVER_H = 1.0 ", src)
        self.assertIn('HOVER_S = 65.0 ', src)
        self.assertIn("PROFILE_NAME = 'INDOOR_ARUCO_SLOW'", src)
        for line in ('MARKER0_X = 0.0 ', 'MARKER0_Y = 0.0\n', 'MAX_START_OFFSET_M = 0.5 ',
                     'FLY_SPEED = 0.1 ', 'FLY_TOL = 0.12 ', 'FLY_SETTLE = 0.05 ',
                     'SETTLE_DZ = 0.03 ', 'SETTLE_SAMPLES = 3 ', 'SETTLE_TIMEOUT_S = 15.0 ',
                     'VISION_AGE_S = 1.0 ', 'VISION_SILENT_S = 3.0 ', 'LOW_H = 0.75 ', 'CLIMB_SPEED = 0.1 ',
                     'TAKEOFF_VISION_S = 25.0 '):
            self.assertIn(line, src)


if __name__ == '__main__':
    unittest.main()
