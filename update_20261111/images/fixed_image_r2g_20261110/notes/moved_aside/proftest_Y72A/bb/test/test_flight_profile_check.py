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

"""Tests for the read-only flight-profile check (param_profile_fix_01, 09.11.2026).

P1  check_flight_profile() never writes: the vpe_fix gate client is never called.
P2  every value equal (PX4 float32 rounding included) -> matched == total.
P3  one value differs or cannot be read -> matched < total, named in problems,
    no exception (the scripts then refuse to fly).
P4  finding F3: names MAVROS does not have yet are read again after
    ParamPull(force_pull=True), up to 3 rounds; then fail-closed.
P5  the profiles hold no COM_SPOOLUP_TIME; all three examples check
    INDOOR_ARUCO_SLOW, refuse to fly on a mismatch and write nothing.
P6  the false "nothing is persisted" texts are gone.
P7  on the 20EC parameter file (04.11, component 1) exactly the 4 values of the
    owner card differ from INDOOR_ARUCO_SLOW; MPC_JERK_MAX and MPC_TKO_SPEED
    (unused in OFFBOARD, they shape manual Altitude) are not checked.

ROS is faked: drone.py is loaded from ../examples/drone.py with fake MAVROS
service clients and a virtual clock, so no rclpy is needed and nothing is
written anywhere:

    python3 -m unittest discover -s src/bumblebee/test -p 'test_flight_profile_check.py'
"""
import contextlib
import importlib.util
import inspect
import io
import os
import runpy
import struct
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(os.path.dirname(HERE), 'examples')
DRONE_PY = os.path.join(EXAMPLES, 'drone.py')
PROFILE_PY = os.path.join(EXAMPLES, 'flight_profile.py')
SCRIPTS = [os.path.join(EXAMPLES, 'flight', n) for n in ('flight.py', 'flight_marker.py', 'flight_marker_loop.py')]
PARAMS_20EC = '/work/pc_inventory_20261019/incident_motors_20261104/params_20261104_1145.params'
CARD = {'MPC_XY_P': (0.45, 0.25), 'MPC_XY_VEL_P_ACC': (1.6, 1.2), 'MPC_XY_VEL_I_ACC': (0.3, 0.1),
        'MPC_XY_VEL_D_ACC': (0.08, 0.05)}

if EXAMPLES not in sys.path:
    sys.path.insert(0, EXAMPLES)


def f32(x):
    """The value as PX4 stores it (float32), as MAVROS hands it back."""
    return struct.unpack('<f', struct.pack('<f', float(x)))[0]


def _bag(**defaults):
    return lambda: types.SimpleNamespace(**defaults)


GET_PARAMETERS = types.SimpleNamespace(Request=_bag(names=[]), Response=_bag(values=[]))
PARAM_PULL = types.SimpleNamespace(Request=_bag(force_pull=False), Response=_bag(success=True, param_received=0))


class FakeFuture:
    def __init__(self, value):
        self.value = value

    def done(self):
        return True

    def result(self):
        return self.value

    def add_done_callback(self, cb):
        cb(self)


class FakeClient:
    def __init__(self, name, handler, available=True):
        self.srv_name = name
        self.handler = handler
        self.available = available

    def wait_for_service(self, timeout_sec=None):
        return self.available

    def call(self, req, timeout_sec=None):
        return self.handler(req)

    def call_async(self, req):
        return FakeFuture(self.handler(req))


class FakeTime:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return 1.79e9 + self.now

    def sleep(self, dt):
        self.now += max(float(dt), 0.0)


class FakeLogger:
    def _log(self, msg):
        pass

    warn = warning = error = info = debug = _log


class FakeNode:
    def get_logger(self):
        return FakeLogger()


class FakeMavrosParams:
    """PX4 parameters as MAVROS holds them. hidden[name] = pulls before MAVROS has the name."""

    def __init__(self, table, hidden=None):
        self.table = dict(table)
        self.hidden = dict(hidden or {})
        self.pulls = 0
        self.gets = 0

    def get(self, req):
        self.gets += 1
        values = []
        for name in req.names:
            if name in self.table and self.hidden.get(name, 0) <= self.pulls:
                v = self.table[name]
                if isinstance(v, int) and not isinstance(v, bool):
                    values.append(types.SimpleNamespace(type=2, integer_value=v, double_value=0.0, bool_value=False))
                else:
                    values.append(types.SimpleNamespace(type=3, double_value=f32(v), integer_value=0, bool_value=False))
            else:
                values.append(types.SimpleNamespace(type=0, double_value=0.0, integer_value=0, bool_value=False))
        return types.SimpleNamespace(values=values)

    def pull(self, req):
        self.pulls += 1
        return types.SimpleNamespace(success=True, param_received=len(self.table))


def load_drone():
    spec = importlib.util.spec_from_file_location('drone_profile_under_test', DRONE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_profiles():
    spec = importlib.util.spec_from_file_location('flight_profile_under_test', PROFILE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PROFILES


class ProfileCheckTest(unittest.TestCase):

    def setUp(self):
        self.profile = dict(load_profiles()['INDOOR_ARUCO_SLOW'])
        self.d = load_drone()

    def wire(self, table, hidden=None, get_available=True):
        d = self.d
        d._initialized = True
        d._node = FakeNode()
        d.time = FakeTime()
        d.GetParameters = GET_PARAMETERS
        d.ParamPull = PARAM_PULL
        self.px4 = FakeMavrosParams(table, hidden)
        self.gate_calls = []
        d._param_get_client = FakeClient('/mavros/mavros/get_parameters', self.px4.get, get_available)
        d._param_pull_client = FakeClient('/mavros/mavros/pull', self.px4.pull)
        d._gate_param_client = FakeClient(
            '/vpe_fix/set_param',
            lambda req: self.gate_calls.append(req) or types.SimpleNamespace(success=True, message=''))
        d.srv = types.SimpleNamespace(SetParam=types.SimpleNamespace(
            Request=_bag(param_id='', value=0.0, ptype=0, ttl_sec=0.0, persistent=False),
            Response=_bag(success=True, message='')))

    def check(self, name='INDOOR_ARUCO_SLOW'):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            res = self.d.check_flight_profile(name)
        self.output = out.getvalue()
        return res

    # P1, P2
    def test_all_match_no_writes(self):
        self.wire(self.profile)
        matched, total, problems = self.check()
        self.assertEqual((matched, total, problems), (len(self.profile), len(self.profile), []))
        self.assertEqual(self.px4.pulls, 0)
        self.assertEqual(self.gate_calls, [])
        self.assertIn('nothing is written', self.output)

    # P3
    def test_one_mismatch_is_named(self):
        table = dict(self.profile, MPC_XY_P=0.45)
        self.wire(table)
        matched, total, problems = self.check()
        self.assertEqual(matched, total - 1)
        self.assertEqual(len(problems), 1)
        self.assertIn('MPC_XY_P: PX4 0.45, profile 0.25', problems[0])
        self.assertEqual(self.gate_calls, [])

    def test_integer_typed_value_matches(self):
        table = dict(self.profile, COM_DISARM_PRFLT=30)
        self.wire(table)
        matched, total, _ = self.check()
        self.assertEqual(matched, total)

    # P4
    def test_f3_missing_until_one_pull(self):
        hidden = {n: 1 for n in ('MPC_XY_P', 'MPC_XY_VEL_P_ACC', 'MPC_XY_VEL_I_ACC', 'MPC_XY_VEL_D_ACC')}
        self.wire(self.profile, hidden)
        matched, total, problems = self.check()
        self.assertEqual((matched, problems), (total, []))
        self.assertEqual(self.px4.pulls, 1)
        self.assertEqual(self.gate_calls, [])

    def test_missing_forever_fails_closed(self):
        self.wire(self.profile, {'MPC_XY_P': 99})
        matched, total, problems = self.check()
        self.assertEqual(matched, total - 1)
        self.assertEqual(problems, ['MPC_XY_P: not read from PX4'])
        self.assertEqual(self.px4.pulls, 3)
        self.assertEqual(self.gate_calls, [])

    def test_service_unavailable_fails_closed(self):
        self.wire(self.profile, get_available=False)
        matched, total, problems = self.check()
        self.assertEqual(matched, 0)
        self.assertEqual(len(problems), total)
        self.assertEqual(self.gate_calls, [])

    def test_apply_flight_profile_only_checks(self):
        self.wire(self.profile)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            n = self.d.apply_flight_profile('INDOOR_ARUCO_SLOW')
        self.assertEqual(n, len(self.profile))
        self.assertIn('no longer writes', out.getvalue())
        self.assertEqual(self.gate_calls, [])

    def test_unknown_profile_raises(self):
        self.wire(self.profile)
        with self.assertRaises(ValueError):
            self.check('NO_SUCH_PROFILE')

    def test_check_code_has_no_write_path(self):
        for fn in (self.d.check_flight_profile, self.d.read_px4_params, self.d.apply_flight_profile):
            src = inspect.getsource(fn)
            for bad in ('set_param(', '_gate_param_client', 'ParamSetV2', 'SetParam'):
                self.assertNotIn(bad, src, '%s uses %s' % (fn.__name__, bad))


class StaticTest(unittest.TestCase):

    # P5
    def test_no_spoolup_in_profiles(self):
        for name, prof in load_profiles().items():
            self.assertNotIn('COM_SPOOLUP_TIME', prof, name)

    def test_slow_has_no_manual_only_params(self):
        prof = load_profiles()['INDOOR_ARUCO_SLOW']
        for name in ('MPC_JERK_MAX', 'MPC_TKO_SPEED'):
            self.assertNotIn(name, prof)

    def test_examples_check_slow_profile_and_refuse(self):
        for path in SCRIPTS:
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
            self.assertIn('check_flight_profile(', text, path)
            self.assertIn('INDOOR_ARUCO_SLOW', text, path)
            self.assertNotIn('apply_flight_profile(', text, path)
            self.assertNotIn('set_param(', text, path)
            self.assertIn('sys.exit(3)', text, path)

    def _run_script(self, path, result):
        """Run an example with a fake `drone`: check_flight_profile returns `result`; any other drone call
        except enable_safe_interrupt/_shutdown stops the run (Reached) so nothing else happens."""
        calls = []

        class Reached(Exception):
            pass

        fake = types.ModuleType('drone')

        def attr(name):
            def fn(*a, **k):
                calls.append(name)
                if name == 'check_flight_profile':
                    if isinstance(result, Exception):
                        raise result
                    return result
                if name in ('enable_safe_interrupt', '_shutdown'):
                    return None
                raise Reached(name)
            return fn
        fake.__getattr__ = attr
        saved = sys.modules.get('drone')
        sys.modules['drone'] = fake
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    runpy.run_path(path, run_name='__main__')
                    outcome = 'finished'
                except SystemExit as e:
                    outcome = 'exit %s' % e.code
                except Reached as e:
                    outcome = 'reached %s' % e.args[0]
        finally:
            if saved is None:
                sys.modules.pop('drone', None)
            else:
                sys.modules['drone'] = saved
        return outcome, calls

    # P5: the check runs first and a mismatch exits before any flight call
    def test_scripts_refuse_before_any_flight_call(self):
        for path in SCRIPTS:
            for result in ((9, 10, ['X: PX4 1, profile 2']), (0, 10, ['X: not read from PX4']),
                           RuntimeError('boom')):
                outcome, calls = self._run_script(path, result)
                self.assertEqual(outcome, 'exit 3', '%s %r' % (path, result))
                self.assertEqual([c for c in calls if c not in ('enable_safe_interrupt', '_shutdown')],
                                 ['check_flight_profile'], path)
                self.assertIn('_shutdown', calls, path)

    def test_scripts_continue_when_all_match(self):
        for path in SCRIPTS:
            outcome, calls = self._run_script(path, (10, 10, []))
            self.assertTrue(outcome.startswith('reached '), '%s: %s' % (path, outcome))
            self.assertEqual(calls[:2], ['enable_safe_interrupt', 'check_flight_profile'], path)

    # P6
    def test_false_persistence_texts_gone(self):
        for path in [DRONE_PY, PROFILE_PY] + SCRIPTS:
            with open(path, encoding='utf-8') as fh:
                text = fh.read()
            for bad in ('nothing is intentionally persisted', 'Nothing is persisted to PX4 EEPROM',
                        'nothing is persisted', 'PX4 EEPROM stays untouched', '\'"\'"\''):
                self.assertNotIn(bad, text, '%s: %r' % (path, bad))

    # P7
    @unittest.skipUnless(os.path.exists(PARAMS_20EC), '20EC parameter file not on this machine')
    def test_20ec_differences_are_the_owner_card(self):
        drone = {}
        with open(PARAMS_20EC, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                p = line.rstrip('\n').split('\t')
                if len(p) >= 4 and p[1] == '1':
                    drone[p[2]] = float(p[3])
        prof = load_profiles()['INDOOR_ARUCO_SLOW']
        diff = {n: (drone.get(n), v) for n, v in prof.items()
                if n not in drone or abs(drone[n] - v) > 1e-4 * max(1.0, abs(v))}
        self.assertEqual(set(diff), set(CARD))
        for n, (old, new) in CARD.items():
            self.assertAlmostEqual(diff[n][0], old, places=5)
            self.assertAlmostEqual(diff[n][1], new, places=5)


if __name__ == '__main__':
    unittest.main()
