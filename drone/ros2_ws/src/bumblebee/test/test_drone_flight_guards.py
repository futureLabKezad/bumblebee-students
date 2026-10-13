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

"""Tests for the flight guards in examples/drone.py (flight package 1, D1-D3).

D1  takeoff() refuses when the FCU state is unknown or the vehicle is armed and
    not in OFFBOARD; the STABILIZED pre-switch happens only on the ground.
D2  pilot wins: no drone.py path (navigate_wait guards, fly_to/move, hover,
    safe_land, set_mode) changes the mode of an armed vehicle outside OFFBOARD;
    safe_land in AUTO.LAND (e.g. after a guard abort) sends nothing but still
    watches the descent.
D3  arming() only disarms, only when landed; the below-floor guard is measured
    from the height at arm and lands instead of disarming; the arming client
    uses the real MAVROS 2.14 service name.

ROS is faked: drone.py is loaded from the source file with fake service
clients, a fake /mavros/state feed and a virtual clock (time.sleep advances it
and steps the fake vehicle), so no rclpy is needed and nothing real is armed:

    python3 -m unittest discover -s drone/ros2_ws/src/bumblebee/test \
        -p 'test_drone_flight_guards.py'
"""
import contextlib
import importlib.util
import io
import math
import os
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DRONE_PY = os.path.join(os.path.dirname(HERE), 'examples', 'drone.py')
# Repo-root copy (absent inside a colcon workspace).
ROOT_DRONE_PY = os.path.normpath(os.path.join(HERE, '..', '..', '..', '..', '..',
                                              'examples', 'drone.py'))


def load_drone():
    """A fresh drone module (module-level state is per test)."""
    spec = importlib.util.spec_from_file_location('drone_under_test', DRONE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bag(**defaults):
    """Fake ROS message/request/response type: attribute bag with defaults."""
    return lambda: types.SimpleNamespace(**defaults)


def _srv_type(req, res):
    return types.SimpleNamespace(Request=_bag(**req), Response=_bag(**res))


NAN = float('nan')
NAVIGATE = _srv_type(dict(x=0.0, y=0.0, z=0.0, yaw=0.0, speed=0.0, frame_id='',
                          auto_arm=False),
                     dict(success=False, message=''))
GET_TELEMETRY = _srv_type(dict(frame_id=''), dict())
COMMAND_BOOL = _srv_type(dict(value=False), dict(success=False, result=0))
SET_MODE = _srv_type(dict(base_mode=0, custom_mode=''), dict(mode_sent=False))
TRIGGER = _srv_type(dict(), dict(success=False, message=''))


class FakeTime:
    """Virtual clock that replaces drone.time; sleep() steps the fake vehicle."""

    def __init__(self):
        self.now = 1000.0
        self.on_advance = []

    def monotonic(self):
        return self.now

    def time(self):
        return 1.79e9 + self.now

    def sleep(self, dt):
        dt = max(float(dt), 0.0)
        self.now += dt
        for cb in list(self.on_advance):
            cb(dt)


class FakeLogger:
    def __init__(self, sink):
        self.sink = sink

    def _log(self, msg):
        self.sink.append(str(msg))

    warn = warning = error = info = _log


class FakeNode:
    def __init__(self):
        self.log = []

    def get_logger(self):
        return FakeLogger(self.log)


class FakeClient:
    def __init__(self, name, handler):
        self.srv_name = name
        self.handler = handler

    def wait_for_service(self, timeout_sec=None):
        return True

    def call(self, req, timeout_sec=None):
        return self.handler(req)


class FakeFCU:
    """PX4 + MAVROS + simple_offboard as drone.py sees them through its clients.

    The vehicle follows the navigate target only while armed in OFFBOARD,
    descends in AUTO.LAND and disarms at the floor, and holds in any other
    mode. MAVROS republishes /mavros/state on every clock step (through the
    real drone._on_fcu_state callback) unless `publishing` is False.
    """

    def __init__(self, drone, clock, armed=False, mode='POSCTL', z=0.0, floor=None):
        self.d = drone
        self.clock = clock
        self.connected = True
        self.armed = armed
        self.mode = mode
        self.pos = [0.0, 0.0, z]
        self.vz = 0.0
        self.floor = z if floor is None else floor
        self.target = list(self.pos) if (armed and mode == 'OFFBOARD') else None
        self.speed = 0.5
        self.publishing = True        # MAVROS publishes /mavros/state
        self.telemetry_state = True   # simple_offboard's state is fresh
        self.land_result = None       # None: normal /land; else failure message
        self.calls = []               # (service, value)
        self.events = []              # [(virtual time, fn(fcu))]
        self.publish_state()
        clock.on_advance.append(self.step)

    # -- simulation --------------------------------------------------------
    def at(self, delay, fn):
        self.events.append((self.clock.now + delay, fn))

    def publish_state(self):
        self.d._on_fcu_state(types.SimpleNamespace(
            connected=self.connected, armed=self.armed, mode=self.mode))

    def step(self, dt):
        for ev in list(self.events):
            if self.clock.now >= ev[0]:
                self.events.remove(ev)
                ev[1](self)
        if self.armed and self.mode == 'OFFBOARD' and self.target is not None:
            d = [t - p for t, p in zip(self.target, self.pos)]
            dist = math.sqrt(sum(c * c for c in d))
            stepl = self.speed * dt
            if dist <= stepl or dist == 0.0:
                self.vz = 0.0
                self.pos = list(self.target)
            else:
                self.pos = [p + c / dist * stepl for p, c in zip(self.pos, d)]
                self.vz = d[2] / dist * self.speed
        elif self.armed and self.mode == 'AUTO.LAND':
            self.vz = -0.5
            self.pos[2] -= 0.5 * dt
            if self.pos[2] <= self.floor:
                self.pos[2] = self.floor
                self.vz = 0.0
                self.armed = False   # PX4 land detector + auto-disarm
        else:
            self.vz = 0.0
        if self.publishing:
            self.publish_state()

    # -- services ----------------------------------------------------------
    def get_telemetry(self, req):
        fresh = self.telemetry_state and self.connected
        frame = req.frame_id or 'map'
        if frame == 'navigate_target':
            if self.target is None:
                x = y = z = NAN
            else:
                x, y, z = [p - t for p, t in zip(self.pos, self.target)]
        else:
            x, y, z = self.pos
        return types.SimpleNamespace(
            frame_id=frame, connected=fresh, armed=self.armed if fresh else False,
            mode=self.mode if fresh else '', x=x, y=y, z=z, vx=0.0, vy=0.0, vz=self.vz)

    def navigate(self, req):
        self.calls.append(('navigate', (req.x, req.y, req.z, req.frame_id, req.auto_arm)))
        res = NAVIGATE.Response()
        if not (self.telemetry_state and self.connected):
            res.message = 'State timeout, check mavros settings'
            return res
        if self.armed and self.mode != 'OFFBOARD':   # serve() side of A4 (S2)
            res.message = 'Copter is armed and not in OFFBOARD'
            return res
        if req.auto_arm:
            self.mode = 'OFFBOARD'
            self.armed = True
        elif self.mode != 'OFFBOARD':
            res.message = 'Copter is not in OFFBOARD mode, use auto_arm?'
            return res
        elif not self.armed:
            res.message = 'Copter is not armed, use auto_arm?'
            return res
        goal = [req.x, req.y, req.z]
        if req.frame_id == 'body':
            goal = [p + g for p, g in zip(self.pos, goal)]
        self.target = goal
        self.speed = req.speed or 0.5
        self.publish_state()
        res.success = True
        return res

    def set_mode(self, req):
        self.calls.append(('set_mode', req.custom_mode))
        self.mode = req.custom_mode
        if self.mode != 'OFFBOARD':
            self.target = None
        self.publish_state()
        res = SET_MODE.Response()
        res.mode_sent = True
        return res

    def arming(self, req):
        self.calls.append(('arming', req.value))
        self.armed = bool(req.value)
        self.publish_state()
        res = COMMAND_BOOL.Response()
        res.success = True
        return res

    def land(self, req):
        self.calls.append(('land', None))
        res = TRIGGER.Response()
        if self.land_result is not None:
            res.message = self.land_result
            return res
        if self.mode != 'OFFBOARD':                # land_only_in_offboard
            res.message = 'Copter is not in OFFBOARD mode'
            return res
        self.mode = 'AUTO.LAND'
        self.target = None
        self.publish_state()
        res.success = True
        return res


class GuardTestBase(unittest.TestCase):
    """Builds drone.py around a FakeFCU; output is captured, not printed."""

    def make(self, **fcu_kw):
        d = load_drone()
        clock = FakeTime()
        d.time = clock
        d._initialized = True            # _init() returns at once
        d.rclpy = types.SimpleNamespace(ok=lambda: True)
        d.srv = types.SimpleNamespace(Navigate=NAVIGATE, GetTelemetry=GET_TELEMETRY)
        d.CommandBool = COMMAND_BOOL
        d.SetMode = SET_MODE
        d.Trigger = TRIGGER
        d._node = FakeNode()
        fcu = FakeFCU(d, clock, **fcu_kw)
        d._get_telemetry_client = FakeClient('/get_telemetry', fcu.get_telemetry)
        d._navigate_client = FakeClient('/navigate', fcu.navigate)
        d._land_client = FakeClient('/land', fcu.land)
        d._arming_client = FakeClient('/mavros/mavros/arming', fcu.arming)
        d._set_mode_client = FakeClient('/mavros/set_mode', fcu.set_mode)
        self.d, self.fcu, self.clock = d, fcu, clock
        self.out = io.StringIO()
        return d, fcu

    def run_quiet(self, fn, *args, **kwargs):
        with contextlib.redirect_stdout(self.out):
            return fn(*args, **kwargs)

    def text(self):
        return self.out.getvalue() + '\n' + '\n'.join(self.d._node.log)

    def calls(self, name):
        return [v for (n, v) in self.fcu.calls if n == name]

    def make_state_unknown(self):
        """MAVROS silent and simple_offboard's state timed out."""
        self.fcu.publishing = False
        self.fcu.telemetry_state = False
        self.d._fcu_state_time = self.clock.now - 10.0


class TakeoffD1(GuardTestBase):

    def test_refused_when_state_unknown(self):
        d, fcu = self.make(armed=False, mode='POSCTL')
        self.make_state_unknown()
        self.assertFalse(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('takeoff refused: FCU state unknown', self.text())
        self.assertEqual(fcu.calls, [])

    def test_refused_when_fcu_link_down(self):
        d, fcu = self.make(armed=False, mode='POSCTL')
        fcu.connected = False
        fcu.publish_state()
        self.assertFalse(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('FCU state unknown', self.text())
        self.assertEqual(fcu.calls, [])

    def test_refused_when_armed_in_pilot_mode(self):
        """Takeoff from the RC, then a script: not allowed (default)."""
        d, fcu = self.make(armed=True, mode='POSCTL', z=1.0, floor=0.0)
        self.assertFalse(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('takeoff refused: pilot/failsafe has control', self.text())
        self.assertEqual(fcu.calls, [])

    def test_retry_during_auto_land_never_switches_to_stabilized(self):
        """Audit A4: a retry after an AUTO.LAND abort used to set STABILIZED mid-air."""
        d, fcu = self.make(armed=True, mode='AUTO.LAND', z=1.2, floor=0.0)
        self.assertFalse(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('takeoff refused: pilot/failsafe has control', self.text())
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(self.calls('navigate'), [])

    def test_ground_takeoff_from_auto_land_keeps_stabilized_preswitch(self):
        d, fcu = self.make(armed=False, mode='AUTO.LAND', z=0.0)
        self.assertTrue(self.run_quiet(d.takeoff, 1.0))
        self.assertEqual(self.calls('set_mode'), ['STABILIZED'])
        self.assertEqual(self.calls('navigate'), [(0.0, 0.0, 1.0, 'map', True)])
        self.assertTrue(fcu.armed)
        self.assertEqual(fcu.mode, 'OFFBOARD')
        self.assertAlmostEqual(fcu.pos[2], 1.0, places=2)

    def test_ground_takeoff_from_posctl(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0)
        self.assertTrue(self.run_quiet(d.takeoff, 0.8))
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(len(self.calls('navigate')), 1)
        self.assertEqual(d._arm_ref_z, 0.0)

    def test_takeoff_while_flying_in_offboard_climbs_without_mode_change(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.assertTrue(self.run_quiet(d.takeoff, 0.5))
        self.assertEqual(self.calls('set_mode'), [])
        self.assertAlmostEqual(fcu.pos[2], 1.5, delta=0.15)   # takeoff tolerance
        self.assertIsNone(d._arm_ref_z)   # not armed by this call: no new floor

    def test_state_from_telemetry_when_state_cache_is_stale(self):
        """Second source: simple_offboard's /get_telemetry when /mavros/state is old."""
        d, fcu = self.make(armed=True, mode='POSCTL', z=1.0, floor=0.0)
        fcu.publishing = False
        d._fcu_state_time = self.clock.now - 10.0
        self.assertEqual(d._fcu_mode_state(), (True, True, 'POSCTL'))
        self.assertFalse(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('pilot/failsafe has control', self.text())


class PilotWinsD2(GuardTestBase):

    def test_fly_to_and_move_refused_in_pilot_mode(self):
        d, fcu = self.make(armed=True, mode='POSCTL', z=1.0, floor=0.0)
        self.assertFalse(self.run_quiet(d.fly_to, 1.0, 0.0, 1.0))
        self.assertFalse(self.run_quiet(d.move, x=0.5))
        self.assertIn('pilot/failsafe has control', self.text())
        self.assertEqual(fcu.calls, [])

    def test_fly_to_refused_when_state_unknown_without_retries(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.make_state_unknown()
        t0 = self.clock.now
        self.assertFalse(self.run_quiet(d.fly_to, 1.0, 0.0, 1.0))
        self.assertEqual(self.calls('navigate'), [])
        # One state wait, not navigate_wait's 5 "position" retries.
        self.assertLess(self.clock.now - t0, d._FCU_STATE_WAIT + 0.5)

    def test_takeover_mid_flight_stops_before_the_vision_guard(self):
        """The pilot flips to POSCTL; the vision watchdog would have fired AUTO.LAND."""
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        d._aruco_markers_pos_time = self.clock.now - 5.8   # trips 6 s limit next loop
        fcu.at(0.3, lambda f: setattr(f, 'mode', 'POSCTL'))
        self.assertFalse(self.run_quiet(d.fly_to, 3.0, 0.0, 1.0))
        self.assertIn('pilot/failsafe has control (armed, mode=POSCTL) -- FLY_TO stopped',
                      self.text())
        self.assertNotIn('Vision lost', self.text())
        self.assertFalse(d._vision_abort)
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(fcu.mode, 'POSCTL')

    def test_takeover_mid_flight_ends_navigate_wait_promptly(self):
        """No guard involved: the script stops instead of waiting out the 60 s timeout."""
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.at(1.0, lambda f: setattr(f, 'mode', 'POSCTL'))
        t0 = self.clock.now
        self.assertFalse(self.run_quiet(d.fly_to, 5.0, 0.0, 1.0))
        self.assertLess(self.clock.now - t0, 2.0)
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(len(self.calls('navigate')), 1)

    def test_vision_guard_still_lands_in_offboard(self):
        """Control for the test above: same flight, no takeover -> AUTO.LAND."""
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        d._aruco_markers_pos_time = self.clock.now - 5.8
        self.assertFalse(self.run_quiet(d.fly_to, 3.0, 0.0, 1.0))
        self.assertIn('Vision lost', self.text())
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])

    def test_guard_action_switches_only_from_offboard(self):
        for mode, armed, expect in (('OFFBOARD', True, ['AUTO.LAND']),
                                    ('POSCTL', True, []),
                                    ('AUTO.LAND', True, []),
                                    ('STABILIZED', True, []),
                                    ('OFFBOARD', False, [])):
            with self.subTest(mode=mode, armed=armed):
                d, fcu = self.make(armed=armed, mode=mode, z=1.0 if armed else 0.0, floor=0.0)
                self.run_quiet(d._land_if_offboard)
                self.assertEqual(self.calls('set_mode'), expect)
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.make_state_unknown()
        self.run_quiet(d._land_if_offboard)
        self.assertEqual(self.calls('set_mode'), [])

    def test_set_mode_refused_for_armed_vehicle_outside_offboard(self):
        d, fcu = self.make(armed=True, mode='POSCTL', z=1.0, floor=0.0)
        res = self.run_quiet(d.set_mode, 'AUTO.LAND')
        self.assertFalse(res.mode_sent)
        self.assertIn('pilot/failsafe has control', self.text())
        self.assertEqual(self.calls('set_mode'), [])

    def test_set_mode_allowed_on_ground_and_from_offboard(self):
        d, fcu = self.make(armed=False, mode='AUTO.LAND')
        self.assertTrue(self.run_quiet(d.set_mode, 'POSCTL').mode_sent)
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.assertTrue(self.run_quiet(d.set_mode, 'AUTO.LAND').mode_sent)
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])

    def test_set_mode_refused_when_state_unknown(self):
        d, fcu = self.make(armed=False, mode='POSCTL')
        self.make_state_unknown()
        self.assertFalse(self.run_quiet(d.set_mode, 'STABILIZED').mode_sent)
        self.assertEqual(fcu.calls, [])

    def test_hover_in_pilot_mode_sends_nothing_and_returns_at_once(self):
        d, fcu = self.make(armed=True, mode='POSCTL', z=1.0, floor=0.0)
        t0 = self.clock.now
        self.assertFalse(self.run_quiet(d.hover, 5.0))
        self.assertLess(self.clock.now - t0, 1.0)
        self.assertIn('pilot/failsafe has control (armed, mode=POSCTL) -- not hovering',
                      self.text())
        self.assertEqual(fcu.calls, [])

    def test_hover_stops_when_pilot_takes_over(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.at(1.0, lambda f: setattr(f, 'mode', 'POSCTL'))
        t0 = self.clock.now
        self.assertFalse(self.run_quiet(d.hover, 5.0))
        self.assertLess(self.clock.now - t0, 2.0)
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(len(self.calls('navigate')), 1)

    def test_hover_in_offboard_holds(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.assertTrue(self.run_quiet(d.hover, 2.0))
        self.assertEqual(self.calls('navigate'), [(0.0, 0.0, 1.0, 'map', False)])

    def test_safe_land_sends_nothing_when_pilot_or_failsafe_has_control(self):
        for mode in ('POSCTL', 'STABILIZED', 'AUTO.LOITER', 'AUTO.RTL'):
            with self.subTest(mode=mode):
                d, fcu = self.make(armed=True, mode=mode, z=1.0, floor=0.0)
                self.assertFalse(self.run_quiet(d.safe_land, x=0.0, y=0.0))
                self.assertIn('pilot/failsafe has control', self.text())
                self.assertEqual(fcu.calls, [])

    def test_safe_land_in_auto_land_sends_nothing_but_waits_for_touchdown(self):
        """A landing already in progress (failsafe or pilot here): watched, not commanded."""
        d, fcu = self.make(armed=True, mode='AUTO.LAND', z=1.0, floor=0.0)
        t0 = self.clock.now
        self.assertTrue(self.run_quiet(d.safe_land, x=0.0, y=0.0))
        self.assertEqual(fcu.calls, [])
        self.assertFalse(fcu.armed)
        self.assertGreater(self.clock.now - t0, 1.5)   # 1 m at 0.5 m/s: ended after touchdown
        self.assertIn('landing already in progress (AUTO.LAND)', self.text())
        self.assertIn('[LAND] z=', self.text())
        self.assertIn('Landed and disarmed.', self.text())
        self.assertNotIn('pilot/failsafe', self.text())

    def test_guard_abort_then_safe_land_watches_own_descent(self):
        """Example scripts: takeoff/fly_to abort on a guard, then safe_land in finally."""
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        d._aruco_markers_pos_time = self.clock.now - 5.8   # vision guard -> AUTO.LAND
        self.assertFalse(self.run_quiet(d.fly_to, 3.0, 0.0, 1.0))
        self.assertEqual(fcu.mode, 'AUTO.LAND')
        self.assertTrue(fcu.armed)
        # A retried takeoff is still refused, without blaming the pilot
        self.assertFalse(self.run_quiet(d.takeoff, 1.0))
        self.assertIn('takeoff refused: landing in progress (this script switched to '
                      'AUTO.LAND)', self.text())
        self.assertTrue(self.run_quiet(d.safe_land, x=0.0, y=0.0))
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])   # the guard's only
        self.assertEqual(self.calls('land'), [])
        self.assertEqual(len(self.calls('navigate')), 1)          # the fly_to's
        self.assertFalse(fcu.armed)
        self.assertIn('Landed and disarmed.', self.text())
        self.assertNotIn('pilot/failsafe', self.text())
        self.assertFalse(d._own_auto_land)                        # cleared on disarm

    def test_own_auto_land_mark_ends_when_the_pilot_takes_over(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.run_quiet(d._land_if_offboard)
        self.assertTrue(d._own_auto_land)
        fcu.mode = 'POSCTL'            # the pilot flips the RC mode switch
        fcu.publish_state()
        self.assertFalse(d._own_auto_land)
        fcu.mode = 'AUTO.LAND'         # and then chooses Land: the pilot's landing
        fcu.publish_state()
        self.assertIn('pilot/failsafe has control',
                      d._no_control_reason(*d._fcu_mode_state()))

    def test_safe_land_watches_when_land_failed_but_auto_land_came(self):
        """/land timed out, yet PX4 switched late: watch the descent, no fallback."""
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)

        def late_land(req):
            fcu.calls.append(('land', None))
            fcu.mode = 'AUTO.LAND'
            fcu.target = None
            fcu.publish_state()
            res = TRIGGER.Response()
            res.message = 'Land request timed out'
            return res
        d._land_client = FakeClient('/land', late_land)
        self.assertTrue(self.run_quiet(d.safe_land))
        self.assertEqual(self.calls('land'), [None])
        self.assertEqual(self.calls('set_mode'), [])
        self.assertFalse(fcu.armed)
        self.assertNotIn('pilot/failsafe', self.text())

    def test_safe_land_from_offboard(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        self.assertTrue(self.run_quiet(d.safe_land))
        self.assertEqual(self.calls('land'), [None])
        self.assertEqual(self.calls('set_mode'), [])
        self.assertFalse(fcu.armed)

    def test_safe_land_falls_back_to_auto_land_only_from_offboard(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.land_result = 'Busy'
        self.assertTrue(self.run_quiet(d.safe_land))
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])

    def test_safe_land_no_fallback_after_takeover_during_hover(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.at(0.5, lambda f: setattr(f, 'mode', 'POSCTL'))
        self.assertFalse(self.run_quiet(d.safe_land))
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(fcu.mode, 'POSCTL')

    def test_safe_land_stops_watching_when_pilot_takes_over_during_descent(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.at(2.5, lambda f: setattr(f, 'mode', 'POSCTL'))   # after hover + /land
        self.assertFalse(self.run_quiet(d.safe_land))         # no sys.exit(3)
        self.assertEqual(self.calls('land'), [None])
        self.assertEqual(self.calls('set_mode'), [])
        self.assertIn('stopped watching the descent', self.text())


class ArmingD3(GuardTestBase):

    def test_arming_service_name(self):
        """drone.py's own node gets no launch remaps: it must use the MAVROS 2.14 name."""
        d = load_drone()
        created = []
        subs = {}

        class Node:
            def __init__(self, name):
                pass

            def create_client(self, srv_type, name):
                created.append((srv_type, name))
                return FakeClient(name, None)

            def create_subscription(self, msg_type, topic, cb, qos):
                subs[topic] = cb

        executor = types.SimpleNamespace(add_node=lambda n: None, spin=lambda: None,
                                         shutdown=lambda timeout_sec=None: None)
        d._ros2_import = lambda: None
        d.rclpy = types.SimpleNamespace(
            init=lambda **kw: None, ok=lambda: False,
            executors=types.SimpleNamespace(MultiThreadedExecutor=lambda: executor))
        d.Node = Node
        d.atexit = types.SimpleNamespace(register=lambda fn: None)
        d.srv = types.SimpleNamespace(GetTelemetry='GetTelemetry', Navigate='Navigate',
                                      SetParam='SetParam')
        d.Trigger, d.CommandBool, d.SetMode, d.ParamPull = 'Trigger', 'CommandBool', 'SetMode', 'ParamPull'
        d.Int32, d.Bool, d.State, d.BatteryState = 'Int32', 'Bool', 'State', 'BatteryState'
        d.QoSProfile = lambda **kw: None
        d.ReliabilityPolicy = types.SimpleNamespace(RELIABLE=1, BEST_EFFORT=2)
        d.DurabilityPolicy = types.SimpleNamespace(TRANSIENT_LOCAL=1, VOLATILE=2)
        d._init()
        self.assertIn(('CommandBool', '/mavros/mavros/arming'), created)
        self.assertNotIn('/mavros/cmd/arming', [n for _, n in created])
        self.assertIs(subs['/mavros/state'], d._on_fcu_state)

    def test_arming_true_is_refused_even_on_the_ground(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0)
        res = self.run_quiet(d.arming, True)
        self.assertFalse(res.success)
        self.assertIn('arming refused', self.text())
        self.assertEqual(fcu.calls, [])
        self.assertFalse(fcu.armed)

    def test_disarm_refused_in_flight(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        res = self.run_quiet(d.arming, False)
        self.assertFalse(res.success)
        self.assertIn('not landed', self.text())
        self.assertEqual(self.calls('arming'), [])
        self.assertTrue(fcu.armed)

    def test_disarm_refused_near_floor_while_still_descending(self):
        d, fcu = self.make(armed=True, mode='AUTO.LAND', z=0.1, floor=0.0)
        fcu.vz = -0.4
        self.d.time.on_advance.remove(fcu.step)   # freeze the vehicle at z=0.1
        self.assertFalse(self.run_quiet(d.arming, False).success)
        self.assertEqual(self.calls('arming'), [])

    def test_disarm_refused_when_state_unknown(self):
        d, fcu = self.make(armed=True, mode='POSCTL', z=0.0)
        self.make_state_unknown()
        self.assertFalse(self.run_quiet(d.arming, False).success)
        self.assertEqual(self.calls('arming'), [])

    def test_disarm_on_the_ground(self):
        d, fcu = self.make(armed=True, mode='POSCTL', z=0.02, floor=0.0)
        res = self.run_quiet(d.arming, False)
        self.assertTrue(res.success)
        self.assertEqual(self.calls('arming'), [False])
        self.assertFalse(fcu.armed)

    def test_disarm_uses_height_recorded_at_arm(self):
        """Takeoff from a 0.4 m platform: landed back on it = on the ground."""
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.4)
        self.assertTrue(self.run_quiet(d.takeoff, 0.5))
        self.assertAlmostEqual(d._arm_ref_z, 0.4)
        fcu.target = None
        fcu.mode = 'POSCTL'          # e.g. landed by the pilot, still armed
        fcu.pos[2] = 0.43
        fcu.vz = 0.0
        fcu.publish_state()
        self.assertTrue(self.run_quiet(d.arming, False).success)
        self.assertEqual(self.calls('arming'), [False])

    def test_arm_height_cleared_on_disarm(self):
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.0)
        self.assertTrue(self.run_quiet(d.takeoff, 0.5))
        self.assertEqual(d._arm_ref_z, 0.0)
        self.assertTrue(self.run_quiet(d.safe_land))
        self.assertIsNone(d._arm_ref_z)

    def test_below_floor_guard_relative_to_arm_height_lands_not_disarms(self):
        """EKF z 0.55 m under the platform the drone took off from."""
        d, fcu = self.make(armed=False, mode='POSCTL', z=0.6)
        self.assertTrue(self.run_quiet(d.takeoff, 0.5))
        fcu.pos[2] = 0.05            # diverged estimate; absolute z is still > -0.5
        self.assertFalse(self.run_quiet(d.fly_to, 0.0, 0.0, 1.1))
        self.assertIn('below the height at arm', self.text())
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])
        self.assertEqual(self.calls('arming'), [])
        self.assertTrue(d._vision_abort)

    def test_below_floor_guard_without_arm_height_uses_zero(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.pos[2] = 0.05            # within 0.5 m of z=0: not a divergence
        fcu.target = [0.0, 0.0, 0.05]
        self.assertTrue(self.run_quiet(d.fly_to, 0.0, 0.0, 0.05))
        self.assertEqual(self.calls('set_mode'), [])
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        fcu.pos[2] = -0.6
        self.assertFalse(self.run_quiet(d.fly_to, 0.0, 0.0, 1.0))
        self.assertEqual(self.calls('set_mode'), ['AUTO.LAND'])
        self.assertEqual(self.calls('arming'), [])

    def test_below_floor_guard_never_switches_a_pilot_mode(self):
        d, fcu = self.make(armed=True, mode='OFFBOARD', z=1.0, floor=0.0)
        def takeover(f):
            f.mode = 'POSCTL'
            f.pos[2] = -0.8
        fcu.at(0.3, takeover)
        self.assertFalse(self.run_quiet(d.fly_to, 2.0, 0.0, 1.0))
        self.assertEqual(self.calls('set_mode'), [])
        self.assertEqual(self.calls('arming'), [])


@unittest.skipUnless(os.path.exists(ROOT_DRONE_PY), 'repo-root examples/drone.py not present')
class BothCopies(unittest.TestCase):

    def test_repo_root_copy_is_identical(self):
        with open(DRONE_PY, 'rb') as a, open(ROOT_DRONE_PY, 'rb') as b:
            self.assertEqual(a.read(), b.read(),
                             'examples/drone.py and drone/ros2_ws/src/bumblebee/'
                             'examples/drone.py must stay byte-identical')


if __name__ == '__main__':
    unittest.main()
