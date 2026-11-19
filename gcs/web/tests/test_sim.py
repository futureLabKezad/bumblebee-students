"""Tests for codecheck (layer 1), fakedrone and simrun (step 4)."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from bbflight import bbmap, codecheck, coverage, simrun  # noqa: E402

with open(os.path.join(ROOT, 'testdata', 'map_final.txt'), encoding='utf-8') as f:
    MP = bbmap.from_map_txt(f.read(), name='field_real')


def example(name):
    with open(os.path.join(ROOT, 'examples', name), encoding='utf-8') as f:
        return f.read()


def errs(src):
    return [e['text'] for e in codecheck.check(src)['errors']]


class CodeCheck(unittest.TestCase):
    def test_examples_pass(self):
        for n in ('flight_marker_student.py', 'flight_marker_loop_student.py', 'corner_18_student.py'):
            r = codecheck.check(example(n))
            self.assertTrue(r['ok'], (n, r['errors']))
            self.assertEqual(r['warnings'], [], n)

    def test_old_image_scripts_are_rejected(self):
        # the drone image's own examples use sys (and private drone names): not student programs
        p = os.path.join(ROOT, '..', '..', 'drone', 'ros2_ws', 'src', 'bumblebee', 'examples', 'flight', 'flight_marker.py')
        if not os.path.exists(p):
            self.skipTest('the repository example is not next to gcs/web')
        with open(p, encoding='utf-8') as f:
            e = errs(f.read())
        self.assertTrue(any('sys' in x for x in e), e)

    def test_forbidden(self):
        cases = {
            'import os': 'os',
            'import subprocess': 'subprocess',
            'import drone\ndrone.set_param("MPC_XY_VEL_MAX", 5)': 'set_param',
            'import drone\ndrone.arming(True)': 'arming',
            'import drone\ndrone.set_mode("OFFBOARD")': 'set_mode',
            'import drone\ndrone.navigate(x=1)': 'navigate',
            'import drone\ndrone.apply_flight_profile()': 'apply_flight_profile',
            'import drone\ndrone._init()': '_init',
            'open("/etc/passwd")': 'open',
            'eval("1")': 'eval',
            'exec("x=1")': 'exec',
            '__import__("os")': '__import__',
            'getattr(1, "real")': 'getattr',
            '().__class__.__bases__': '__class__',
            'from drone import *': 'import *',
            'from drone import set_param': 'set_param',
            'import drone as d\nd.set_param("X", 1)': 'set_param',
            'import drone\ndrone = 5': 'drone',
            'import drone\ndrone.teleport(1)': 'teleport',
            # review 17.11 item 1: match class patterns read any attribute
            'import drone\nmatch drone.takeoff:\n    case object(__self__=fd):\n        pass\n': 'match',
            'import drone\nmatch drone.takeoff:\n    case object(cfg=c):\n        pass\n': 'match',
            '"{0.__self__.cfg}".format(1)': '__',
            '"{0._x}".format(1)': '{x._y}',
            'g = {}\ng["__builtins__"]': '__',
            # item 4: drone as a value / replaced attributes
            'import drone\nm = drone\nm.set_param("X", 5)': 'as a value',
            'import drone\n[drone][0].set_mode("OFFBOARD")': 'as a value',
            'import drone\n(lambda d: d.navigate(x=5))(drone)': 'as a value',
            'import drone\ndef f(d):\n    d.set_param("X", 1)\nf(drone)': 'as a value',
            'import drone\nmatch drone:\n    case _:\n        pass\n': 'as a value',
            'import drone\ndrone.land = drone.hover': 'cannot be changed',
            'import drone\ndel drone.land': 'cannot be changed',
            # bare except / BaseException would swallow the guard landing
            'import drone\ntry:\n    drone.hover(1)\nexcept:\n    pass\n': 'except',
            'import drone\ntry:\n    drone.hover(1)\nexcept BaseException:\n    pass\n': 'BaseException',
            'import drone\ntry:\n    drone.hover(1)\nexcept (ValueError, BaseException):\n    pass\n': 'BaseException',
        }
        for src, word in cases.items():
            e = errs(src)
            self.assertTrue(e, src)
            self.assertTrue(any(word in x for x in e), (src, e))

    def test_syntax_error_has_line(self):
        r = codecheck.check('import drone\n\ndrone.takeoff(0.9\n')
        self.assertFalse(r['ok'])
        self.assertGreaterEqual(r['errors'][0]['line'], 3)

    def test_name_main_allowed(self):
        self.assertEqual(errs('import drone\nif __name__ == "__main__":\n    drone.hover(1)\n'), [])

    def test_normal_programs_still_pass(self):
        ok = ('import drone\ntry:\n    drone.hover(1)\nexcept Exception as e:\n    print(e)\n'
              'class A:\n    pass\n'
              'x, y = drone.marker_xy(2)\nprint(f"{x:.2f}")\n')
        self.assertEqual(errs(ok), [])

    def test_warnings(self):
        w = [x['text'] for x in codecheck.check('import drone\ndrone.takeoff(0.9)\n')['warnings']]
        self.assertTrue(any('no landing' in x for x in w), w)
        w = [x['text'] for x in codecheck.check('import drone\nwhile True:\n    x = 1\n')['warnings']]
        self.assertTrue(any('while True' in x for x in w), w)


def run(src, **kw):
    return simrun.run(src, MP, coverage.camera('gazebo'), **kw)


class Simulation(unittest.TestCase):
    def script_s(self, r):
        to = next(l['t'] for l in r['log'] if l['text'].startswith('=== TAKEOFF'))
        return r['duration_s'] - to

    def test_flight_marker_route_and_time_FIT(self):
        r = run(example('flight_marker_student.py'))
        self.assertTrue(r['ok'], r['events'])
        flown = [l['text'] for l in r['log'] if l['text'].startswith('=== FLY TO MARKER')]
        pts = [tuple(float(v) for v in re.findall(r'-?\d+\.\d+', t)[:2]) for t in flown]
        # the r2j/scripts_final route: (0.09, 1.95) -> (0.06, 0.97) -> (0.00, 0.00), two decimals as drone.py prints
        self.assertEqual([(round(x, 2), round(y, 2)) for x, y in pts], [(0.09, 1.95), (0.06, 0.97), (0.0, 0.0)])
        # the time model is FITTED on these 19 runs (median 83.2 s): this only shows the fit, it is not a check
        self.assertLess(abs(self.script_s(r) - 83.2) / 83.2, 0.05, self.script_s(r))
        self.assertFalse(r['landed_by_guard'])

    def test_loop_route_and_time_CHECK(self):
        # NOT used in the fit: 20 Gazebo runs fB_c7loop, takeoff -> script end median 168.2 s (160.5..173.5)
        r = run(example('flight_marker_loop_student.py'))
        self.assertTrue(r['ok'], r['events'])
        flown = [l['text'] for l in r['log'] if l['text'].startswith('=== FLY TO (')]
        pts = [tuple(round(float(v), 2) for v in re.findall(r'-?\d+\.\d+', t)[:2]) for t in flown]
        want = [(0.06, 0.97), (0.09, 1.95), (0.02, 2.92), (-0.59, 2.95), (-1.19, 2.93), (-1.23, 1.93),
                (-1.23, 0.95), (-0.58, 0.95), (0.06, 0.97), (0.0, 0.0)]     # the r2j loop WAYPOINTS + home
        self.assertEqual(pts, want)
        err = (self.script_s(r) - 168.2) / 168.2
        self.assertLess(abs(err), 0.15, self.script_s(r))   # 17.11: +9.8 % (the model is slower: conservative)

    def test_corner_18_shows_red_zone(self):
        r = run(example('corner_18_student.py'))
        self.assertTrue(any('red zone' in e['text'] for e in r['events']), r['events'])

    def test_takeoff_too_high_is_refused(self):
        r = run('import drone\ndrone.takeoff(2.0)\ndrone.land()\n')
        self.assertTrue(any('takeoff to 2.00' in e['text'] for e in r['events']))
        self.assertFalse(r['ok'])

    def test_out_of_field_refused(self):
        r = run('import drone\ndrone.takeoff(0.9)\ndrone.fly_to(5.0, 0.0, speed=0.1)\ndrone.land()\n')
        e = [x for x in r['events'] if 'outside the field' in x['text']]
        self.assertTrue(e)
        self.assertEqual(e[0]['line'], 3)

    def test_speed_above_tested_is_refused(self):
        # plan R1: outside the tested range the guard REFUSES (tested 0.10 m/s)
        r = run('import drone\ndrone.takeoff(0.9)\nok1 = drone.fly_to(0.0, 0.5, speed=0.2)\n'
                'ok2 = drone.fly_to(0.0, 0.5, speed=0.1)\nprint(ok1, ok2)\ndrone.land()\n')
        self.assertTrue(any(e['level'] == 'error' and 'speed 0.20' in e['text'] and e['line'] == 3 for e in r['events']))
        self.assertIn('False True', [l['text'] for l in r['log']])

    def test_nan_speed_refused(self):
        r = run('import drone\ndrone.takeoff(0.9)\ndrone.fly_to(0.0, 0.5, speed=float("nan"))\ndrone.land()\n')
        self.assertTrue(any('speed nan' in e['text'] for e in r['events']), r['events'])

    def test_guard_landing_cannot_be_caught(self):
        # review 17.11 item 2: "except Exception" around a hover over the budget, then a new takeoff
        src = ('import drone\ndrone.takeoff(0.9)\ntry:\n    drone.hover(400)\nexcept Exception as e:\n    print("caught", e)\n'
               'drone.takeoff(0.9)\ndrone.hover(600)\ndrone.land()\n')
        r = run(src, time_budget_s=300)
        self.assertTrue(r['landed_by_guard'])
        self.assertLess(r['duration_s'], 320)
        self.assertEqual(sum(1 for e in r['events'] if 'arming and takeoff' in e['text']), 1)
        self.assertNotIn('caught', ' '.join(l['text'] for l in r['log']))

    def test_durations_must_be_finite_and_positive(self):
        for bad in ('-60', 'float("nan")', '1e9'):
            r = run('import drone\ndrone.takeoff(0.9)\ndrone.hover(%s)\ndrone.land()\n' % bad)
            self.assertTrue(any(e['level'] == 'error' and e['line'] == 3 for e in r['events']), (bad, r['events']))
            ts = [p[0] for p in r['trace']]
            self.assertEqual(ts, sorted(ts), bad)                 # the clock never goes back
        r = run('import drone\ndrone.wait_position_stable(stable_secs=-60)\n')
        self.assertFalse(r['ok'])
        self.assertGreaterEqual(r['duration_s'], 0)

    def test_safe_land_approach_speed_limited(self):
        r = run('import drone\ndrone.takeoff(0.9)\ndrone.fly_to(0.0, 0.8, speed=0.1)\ndrone.safe_land(0.7, 0.0, precision_speed=5)\n')
        tr = r['trace']
        vmax = max(((tr[k][1] - tr[k - 1][1]) ** 2 + (tr[k][2] - tr[k - 1][2]) ** 2) ** 0.5 / max(1e-6, tr[k][0] - tr[k - 1][0])
                   for k in range(1, len(tr)))
        self.assertLess(vmax, 0.11)
        self.assertTrue(any('limited' in e['text'] for e in r['events']))

    def test_start_pose_and_move_like_gazebo(self):
        # Gazebo spawn: (-0.111, 0.003), heading -1.5 deg; move(x=...) is forward
        r = run('import drone\nprint(*[round(v, 3) for v in drone.get_pos()])\n')
        x, y, z = (float(v) for v in r['log'][-1]['text'].split())
        self.assertAlmostEqual(x, -0.111, places=2)
        self.assertAlmostEqual(y, 0.003, places=2)
        r = run('import drone\ndrone.takeoff(0.9)\ndrone.move(x=0.5)\nprint(*[round(v, 2) for v in drone.get_pos()])\ndrone.land()\n')
        x, y, z = (float(v) for v in r['log'][-1]['text'].split())
        self.assertGreater(x, 0.35)
        self.assertLess(abs(y), 0.05)

    def test_require_map_empty_name_refused(self):
        mp = dict(MP, name='')
        r = simrun.run('import drone\ndrone.require_map("")\n', mp, coverage.camera('gazebo'))
        self.assertFalse(r['ok'])

    def test_class_definition_runs(self):
        r = run('import drone\nclass A:\n    pass\nprint(type(A()).__name__ if False else "ok")\n')
        self.assertFalse(r['check']['ok'])        # "__name__" attribute access is refused by layer 1
        r = run('import drone\nclass A:\n    x = 1\nprint(A.x)\n')
        self.assertTrue(r['ok'], r['events'])
        self.assertEqual(r['log'][-1]['text'], '1')

    def test_no_landing_runner_lands(self):
        r = run('import drone\ndrone.takeoff(0.9)\ndrone.hover(2)\n')
        self.assertTrue(any('in the air' in e['text'] for e in r['events']))
        self.assertEqual(r['trace'][-1][5], 0)       # disarmed at the end

    def test_infinite_loop_stops(self):
        r = run('import drone\nwhile True:\n    pass\n', line_limit=20000)
        self.assertTrue(r['ran'])
        self.assertTrue(any('endless' in e['text'] for e in r['events']))

    def test_sleep_loop_stops_by_budget(self):
        r = run('import drone, time\ndrone.takeoff(0.9)\nwhile True:\n    time.sleep(1)\n', time_budget_s=60)
        self.assertTrue(r['landed_by_guard'])
        self.assertTrue(any('budget' in e['text'] for e in r['events']))

    def test_unknown_marker_is_error_with_line(self):
        r = run('import drone\ndrone.takeoff(0.9)\ndrone.fly_to_marker(42)\ndrone.land()\n')
        e = [x for x in r['events'] if 'marker 42' in x['text']]
        self.assertTrue(e)
        self.assertEqual(e[0]['line'], 3)

    def test_wrong_map_stops(self):
        r = run('import drone\ndrone.require_map("other_field")\ndrone.takeoff(0.9)\n')
        self.assertFalse(r['ok'])
        self.assertEqual(r['trace'][-1][5], 0)

    def test_student_exception_reported(self):
        r = run('import drone\ndrone.takeoff(0.9)\nx = 1 / 0\n')
        self.assertTrue(any('ZeroDivisionError' in e['text'] and e['line'] == 3 for e in r['events']))
        self.assertEqual(r['trace'][-1][5], 0)

    def test_runtime_import_blocked(self):
        # codecheck rejects it; even if it ran, the importer refuses
        r = run('import os\n')
        self.assertFalse(r['ran'])

    def test_virtual_clock(self):
        r = run('import drone, time\nt = time.time()\ntime.sleep(100)\nprint(round(time.time() - t))\n')
        self.assertEqual(r['log'][-1]['text'], '100')

    def test_result_is_json(self):
        json.dumps(run(example('flight_marker_student.py')))


class WebApi(unittest.TestCase):
    def setUp(self):
        from bbflight import webapi
        self.api = webapi
        self.mj = bbmap.to_json(MP)

    def test_no_nan_in_results(self):
        out = self.api.simulate('import drone\ndrone.takeoff(0.9)\ndrone.hover(float("nan"))\n', self.mj)
        self.assertNotIn('NaN', out)
        json.loads(out)

    def test_grid_refuses_maps_with_errors_and_huge_fields(self):
        bad = json.loads(self.mj)
        bad['markers'][3]['x'] = 2900.0
        self.assertIn('error', json.loads(self.api.grid(json.dumps(bad), 0.75)))
        far = json.loads(self.mj)
        far['markers'][3]['x'] = 40.0
        self.assertIn('error', json.loads(self.api.grid(json.dumps(far), 0.75)))
        ok = json.loads(self.api.grid(self.mj, 0.75))
        self.assertNotIn('error', ok)

    def test_map_from_txt_keeps_file_problems(self):
        out = json.loads(self.api.map_from_txt('0 0.19 0 0 -0.32 1.57 0 0\n1 0.29 0 0.97\n', 'f'))
        self.assertTrue(any('8 columns' in e for e in out['_check']['errors']))

    def test_simulate_refuses_map_with_errors(self):
        bad = json.loads(self.mj)
        bad['markers'][1]['id'] = 0
        self.assertIn('error', json.loads(self.api.simulate('import drone\n', json.dumps(bad))))


if __name__ == '__main__':
    unittest.main()
