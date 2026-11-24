#!/usr/bin/env python3
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Flight studio (GCS 1.4, 24.11.2026): command help, «how to fix», the pre-flight review,
the motion profile, the page script, and that the drone part of the page is the one of 1.3.0."""
import glob
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

WEB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WEB)
import build_html  # noqa: E402
from bbflight import apidoc, bbmap, codecheck, coverage, fakedrone, hints, preflight, simrun, webapi  # noqa: E402


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


MAP = bbmap.from_map_txt(read(os.path.join(WEB, 'testdata', 'map_final.txt')), name='field_real')
MAP_JSON = bbmap.to_json(MAP)


def studio(src, cfg='{"time_budget_s": 300}'):
    return json.loads(webapi.studio(src, MAP_JSON, 'gazebo', cfg))


def codes(r, level=None):
    return [f['code'] for f in r['preflight']['findings'] if level is None or f['level'] == level]


PROLOGUE = "import drone\ndrone.require_map('field_real')\n"


class CommandHelp(unittest.TestCase):
    def test_every_student_command_has_help_and_nothing_else(self):
        self.assertEqual(apidoc.missing(), ([], []))

    def test_signatures_name_the_real_parameters(self):
        """Every parameter named in the help exists in the simulated drone (same names as the drone module)."""
        fd = fakedrone.FakeDrone(MAP, coverage.camera('gazebo'))
        for c in apidoc.docs():
            if c['group'] == 'lights' or c['name'] == 'should_land':
                continue
            real = set(inspect.signature(getattr(fd, c['name'])).parameters)
            m = re.match(r'\w+\((.*?)\)', c['sig'])
            named = [a.split('=')[0].strip() for a in m.group(1).split(',') if a.strip()]
            for a in named:
                self.assertIn(a, real, '%s: %s is not a parameter' % (c['name'], a))

    def test_snippets_pass_the_code_check(self):
        for c in apidoc.docs():
            src = 'import drone\nx = drone.%s\n' % c['snippet']
            self.assertTrue(codecheck.check(src)['ok'], c['snippet'])

    def test_groups_cover_all(self):
        groups = {g for g, _t in apidoc.GROUPS}
        self.assertTrue(all(c['group'] in groups for c in apidoc.docs()))


class HowToFix(unittest.TestCase):
    BAD = [
        'import os\n', 'from drone import *\n', 'import drone\ndrone._x()\n', 'import drone\ndrone.set_param("A", 1)\n',
        'import drone\ndrone.arming(True)\n', 'import drone\nd = drone\n', 'x = (1).__class__\n', 'open("f")\n',
        'try:\n    pass\nexcept:\n    pass\n', 's = "__x"\n', 'import drone\ndrone.flyto(1, 2)\n', 'if True\n    pass\n',
    ]

    def test_every_code_error_gets_advice(self):
        for src in self.BAD:
            r = json.loads(webapi.check_code_hints(src))
            self.assertTrue(r['errors'], src)
            for e in r['errors']:
                self.assertTrue(e['fix'], 'no advice for %r (%s)' % (e['text'], src))

    def test_close_command_name_is_suggested(self):
        self.assertIn('drone.fly_to?', hints.fix_for('drone.flyto is not in the list of commands for students'))
        self.assertIn('drone.takeoff?', hints.fix_for('drone.takeof is not in the list of commands for students'))

    def test_warnings_get_advice(self):
        r = json.loads(webapi.check_code_hints('import drone\ndrone.takeoff(0.9)\nwhile True:\n    pass\n'))
        self.assertTrue(r['warnings'])
        self.assertTrue(all(w['fix'] for w in r['warnings']))

    def test_guard_messages_get_advice(self):
        for text in ['guard: takeoff to 2.00 m is outside the tested 0.5-1.3 m; command refused',
                     'guard: speed 0.50 m/s is outside the tested 0-0.10; command refused',
                     'guard: point (9.00, 9.00) is outside the field; command refused',
                     'fly to: the drone is not in the air; command refused',
                     'no marker in view for 6 s; the vision guard lands the drone',
                     'flight time over the budget of 300 s; the time guard lands the drone',
                     'the program ended with the drone in the air; the runner on the drone lands it',
                     'error: NameError: name \'x\' is not defined']:
            self.assertTrue(hints.fix_for(text), text)


class Review(unittest.TestCase):
    def test_example_is_flyable_with_notes(self):
        r = studio(read(os.path.join(WEB, 'examples', 'flight_marker_student.py')))
        self.assertTrue(r['ran'])
        self.assertIn(r['preflight']['verdict'], ('ready', 'check'))
        self.assertNotIn('error', [f['level'] for f in r['preflight']['findings']])
        st = r['preflight']['stats']
        self.assertIn('23.0 V by PX4', st['battery'])
        self.assertIn('20 V by a multimeter', st['battery'])
        self.assertAlmostEqual(st['max_height_m'], 0.9, places=2)
        self.assertAlmostEqual(st['rangefinder_m'], 0.9 + preflight.RNG_ON_FLOOR, places=2)

    def test_low_takeoff_warns_about_the_px4_1m_threshold(self):
        r = studio(PROLOGUE + 'drone.takeoff(height=0.6)\ndrone.hover(2)\ndrone.land()\n')
        self.assertIn('HTE', codes(r, 'warn'))
        r = studio(PROLOGUE + 'drone.takeoff(height=0.9)\ndrone.hover(2)\ndrone.land()\n')
        self.assertNotIn('HTE', codes(r))

    def test_refused_command_is_an_error_with_line_and_fix(self):
        r = studio(PROLOGUE + 'drone.takeoff(height=0.9)\ndrone.fly_to(0, 1, speed=0.5)\ndrone.land()\n')
        f = [f for f in r['preflight']['findings'] if f['level'] == 'error']
        self.assertTrue(f)
        self.assertEqual(f[0]['line'], 4)
        self.assertIn('0.10', f[0]['fix'])
        self.assertEqual(r['preflight']['verdict'], 'not_ready')

    def test_command_before_takeoff(self):
        r = studio(PROLOGUE + 'drone.fly_to(0, 1)\ndrone.takeoff(height=0.9)\ndrone.land()\n')
        f = [f for f in r['preflight']['findings'] if 'not in the air' in f['title']]
        self.assertTrue(f and f[0]['line'] == 3 and 'Take off first' in f[0]['fix'])

    def test_no_require_map_is_a_warning(self):
        r = studio('import drone\ndrone.takeoff(height=0.9)\ndrone.fly_to(0, 1)\ndrone.land()\n')
        self.assertIn('MAP_NAME', codes(r, 'warn'))

    def test_close_to_the_edge(self):
        x0, y0, x1, y1 = bbmap.bounds(MAP, 0.0)
        src = PROLOGUE + 'drone.takeoff(height=0.9)\ndrone.fly_to(%.3f, 0.5)\ndrone.land()\n' % (x1 + 0.25)
        r = studio(src)
        self.assertIn('EDGE', codes(r, 'warn'))
        self.assertIn('OUTSIDE_MARKERS', codes(r))

    def test_blind_stretch_is_reported_before_the_guard(self):
        x0, y0, x1, y1 = bbmap.bounds(MAP, 0.0)
        src = PROLOGUE + 'drone.takeoff(height=0.5)\ndrone.fly_to(%.3f, %.3f)\ndrone.land()\n' % (x1 + 0.28, y1 + 0.28)
        r = studio(src)
        blind = [f for f in r['preflight']['findings'] if f['code'] == 'BLIND']
        self.assertTrue(blind, codes(r))                                     # review 24.11, m1: BLIND itself
        guard = [f for f in r['preflight']['findings'] if 'vision guard lands' in f['title']]
        if guard:
            self.assertLess(blind[0]['t'], guard[0]['t'])                    # reported before the guard lands it

    def test_no_number_from_gazebo_is_sold_as_a_drone_fact(self):
        """review 24.11, K2: the T41 times are Gazebo's, and the model never declares a flight safe."""
        r = studio(PROLOGUE + 'drone.takeoff(height=0.6)\ndrone.fly_to(0, 1)\ndrone.fly_to(0, 0)\ndrone.land()\n')
        text = ' '.join(f['why'] + ' ' + f['fix'] for f in r['preflight']['findings'])
        self.assertIn('in Gazebo (test T41)', text)
        self.assertNotIn('this is safe', text.lower())

    def test_height_advice_matches_the_message(self):
        """review 24.11, M5: map z in the simulation, height above the floor on the drone."""
        self.assertIn('0.30 to 1.20', hints.fix_for('guard: height z=1.25 is outside the tested 0.30-1.20; command refused'))
        self.assertIn('0.41–1.31', hints.fix_for('height above the floor 1.40 m is outside the tested 0.41–1.31'))

    def test_budget_advice_does_not_say_raise_it(self):
        self.assertNotIn('raise', hints.fix_for('flight time over the budget of 300 s; the time guard lands the drone'))

    def test_time_close_to_the_budget(self):
        r = studio(PROLOGUE + 'drone.takeoff(height=0.9)\ndrone.hover(50)\ndrone.land()\n', '{"time_budget_s": 70}')
        self.assertIn('TIME', codes(r, 'warn'))

    def test_code_errors_stop_before_flying(self):
        r = studio('import os\n')
        self.assertFalse(r['ran'])
        self.assertEqual(r['preflight']['verdict'], 'not_ready')
        self.assertTrue(all(f['fix'] for f in r['preflight']['findings'] if f['level'] == 'error'))

    def test_result_is_plain_json(self):
        r = webapi.studio(read(os.path.join(WEB, 'examples', 'corner_18_student.py')), MAP_JSON, 'drone', '{}')
        self.assertNotIn('NaN', r)
        self.assertNotIn('Infinity', r)


class Motion(unittest.TestCase):
    def test_fractions_go_from_0_to_1_without_going_back(self):
        for d, T, v in [(1.0, 16.6, 0.1), (0.05, 7.1, 0.1), (2.0, 26.6, 0.1), (0.9, 6.0, 0.15), (1.0, 10.0, None)]:
            steps = int(round(T / 0.1))
            f = fakedrone.leg_fractions(d, steps * 0.1, v, 0.1, steps)
            self.assertEqual(f[0], 0.0)
            self.assertAlmostEqual(f[-1], 1.0)
            self.assertTrue(all(b >= a - 1e-12 for a, b in zip(f, f[1:])))

    def test_never_faster_than_the_command_or_px4(self):
        """In the trace the drone is never faster than the guard speed (0.10 + rounding) horizontally,
        nor than the PX4 profile vertically."""
        r = simrun.run(read(os.path.join(WEB, 'examples', 'flight_marker_loop_student.py')), MAP, coverage.camera('gazebo'))
        tr = r['trace']
        for a, b in zip(tr, tr[1:]):
            dt = b[0] - a[0]
            if dt <= 0:
                continue
            vxy = math.hypot(b[1] - a[1], b[2] - a[2]) / dt
            vz = (b[3] - a[3]) / dt
            self.assertLessEqual(vxy, 0.10 * 1.06 + 1e-6, 'at %.1f s' % b[0])
            self.assertLessEqual(vz, fakedrone.PX4_PROFILE['up_mps'] + 1e-6)
            self.assertGreaterEqual(vz, -fakedrone.PX4_PROFILE['down_mps'] - 1e-6)

    def test_leg_times_did_not_change(self):
        """The fitted times of 1.3 stay: the profile only changes where the drone is inside a leg."""
        for ex, total in (('flight_marker_student.py', 86.6), ('flight_marker_loop_student.py', 187.8), ('corner_18_student.py', 62.6)):
            r = simrun.run(read(os.path.join(WEB, 'examples', ex)), MAP, coverage.camera('gazebo'))
            self.assertAlmostEqual(r['duration_s'], total, delta=0.11, msg=ex)


class SameLimitsAsTheDrone(unittest.TestCase):
    """The simulation refuses what the drone refuses. testdata/bb_mission_0.2.0_guards.py is a byte copy of
    bb_mission 0.2.0 guards.py (the mission server package is not in this repository). With BB_MISSION_GUARDS
    pointing at the package's file, the copy is also checked against it. Never skipped (review 24.11, M7)."""
    COPY = os.path.join(WEB, 'testdata', 'bb_mission_0.2.0_guards.py')
    GUARDS = os.environ.get('BB_MISSION_GUARDS', '')
    # SHA256 of guards.py in the bb_mission 0.2.0 package (drone_pkg_bb_mission_20261123). Byte for byte:
    # .gitattributes keeps testdata/ out of line-ending conversion (review 2, 24.11, S2 and m7).
    PACKAGE_SHA256 = '97407d3cc74686dd9c31000f0597ba50c07306b622f97290386548f3afdf77fc'

    def test_copy_is_pinned_to_the_package_hash(self):
        import hashlib
        with open(self.COPY, 'rb') as f:
            data = f.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.PACKAGE_SHA256,
                         'testdata copy is not the bb_mission 0.2.0 guards.py (%d bytes, %d CR)' % (len(data), data.count(b'\r')))

    def test_copy_is_the_package_file(self):
        if not self.GUARDS:
            return                                   # CI: only the copy is there; checked against the package on the PC
        with open(self.GUARDS, 'rb') as a, open(self.COPY, 'rb') as b:
            self.assertEqual(a.read(), b.read(), 'testdata copy differs from %s' % self.GUARDS)

    def test_numbers_match_bb_mission_guards(self):
        ns = {}
        exec(compile(read(self.COPY), 'guards.py', 'exec'), ns)
        lim, d = ns['LIMITS'], fakedrone.DEFAULTS
        for k in ('takeoff_min', 'takeoff_max', 'climb_speed_max', 'speed_max', 'field_margin', 'time_budget_s',
                  'vision_timeout_s', 'quorum_timeout_s'):
            self.assertEqual(lim[k], d[k], k)
        # heights: the drone counts from the takeoff floor, the simulation in map z with the floor at z_rest
        self.assertAlmostEqual(lim['height_min'], d['z_min'] - d['z_rest'], places=6)
        self.assertAlmostEqual(lim['height_max'], d['z_max'] - d['z_rest'], places=6)


class PageScript(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='bbstudio_')
        self.addCleanup(shutil.rmtree, self.d, True)

    def test_one_inline_script_with_all_parts_and_help(self):
        build_html.build(self.d)
        html = read(os.path.join(self.d, 'flight_embedded.html'))
        self.assertEqual(len(build_html.INLINE_SCRIPT.findall(html)), 1)
        for p in glob.glob(os.path.join(WEB, 'studio', '*.js')):
            self.assertIn('// ===== %s =====' % os.path.basename(p), html)
        m = re.search(r'<script id="apidocs" type="application/json">(.*?)</script>', html, re.S)
        docs = json.loads(m.group(1))
        self.assertEqual({c['name'] for c in docs['commands']}, codecheck.STUDENT_API)
        for key in ('/*__STUDIO_JS__*/', '/*__API_DOCS__*/', '/*__PY_FILES__*/'):
            self.assertNotIn(key, html)

    def test_ids_the_apps_and_the_window_test_use_are_there(self):
        tpl = read(os.path.join(WEB, 'flight_template.html'))
        for i in ('pystatus', 'btnsim', 'simbox', 'simkv', 'srvstate', 'sendmap', 'dronecheck', 'c_battery', 'c_rc', 'c_people',
                  'takeoff', 'takeoff2', 'dronemsgs', 'dronestop', 'liveevents', 'code', 'dltxt', 'srv', 'srvlabel', 'srvconnect'):
            self.assertEqual(tpl.count('id="%s"' % i), 1, i)

    def test_javascript_parses(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node is not installed')
        p = os.path.join(self.d, 'studio.js')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(build_html.studio_js())
        r = subprocess.run([node, '--check', p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class DronePartUnchanged(unittest.TestCase):
    """The drone block (connect, map, check, «Взлёт?», STOP, status) is the 1.3.0 code byte for byte,
    except the one marked line that also draws the live drone in 3D."""
    BASE = 'a42b870'

    def test_same_as_1_3_0(self):
        git = shutil.which('git')
        if not git:
            self.skipTest('git is not installed')
        r = subprocess.run([git, '-C', WEB, 'show', self.BASE + ':gcs/web/flight_template.html'], capture_output=True)
        # a shallow checkout lacks the commit: that must fail, not pass silently (review 24.11, M7; CI uses fetch-depth 0)
        self.assertEqual(r.returncode, 0, 'commit %s (GCS 1.3.0) is not in this checkout: fetch the full history' % self.BASE)
        old = r.stdout.decode('utf-8').split('\n')
        s = next(i for i, l in enumerate(old) if l.startswith('// ---------- drone: the mission server'))
        e = next(i for i, l in enumerate(old) if l.startswith('// ---------- start ----------'))
        want = '\n'.join(old[s:e]).rstrip() + '\n'
        got = read(os.path.join(WEB, 'studio', '60_drone.js')).split('\n', 1)[1]
        marked = '        if ((r.data.events || []).length) { draw(); render3d(); }      // 1.4: the live drone is also drawn in 3D\n'
        self.assertEqual(got.count(marked), 1)
        self.assertEqual(got.replace(marked, '        if ((r.data.events || []).length) draw();\n'), want)


if __name__ == '__main__':
    unittest.main()
