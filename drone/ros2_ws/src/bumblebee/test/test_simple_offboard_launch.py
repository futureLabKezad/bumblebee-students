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

"""Launch test: the real simple_offboard binary against a fake MAVROS.

Checks the safety behaviour of flight package 1 (spec S1-S5): no setpoint lurch
at the start of a navigate, refusal while the pilot or a PX4 failsafe has control
or while the FCU state is unknown, the disabled velocity/attitude/rates/yaw-rate
paths, the stream stopping when PX4 leaves OFFBOARD by itself (also when only a
gap in the FCU state shows it, as after a MAVROS restart, but not on a few lost
heartbeats), and /land cancelling an auto_arm in progress or still queued.
Simulation time: test_simple_offboard_simtime_launch.py.

    colcon test --packages-select bumblebee     (registered in CMakeLists.txt)
    launch_test test/test_simple_offboard_launch.py

Everything is local ROS topics and services (fake_mavros.py): no MAVLink, no FCU.
"""

import math
import os
import sys
import threading
import time
import unittest

try:
    import launch
    import launch_ros.actions
    import launch_testing
    import launch_testing.actions
    import launch_testing.asserts
    import pytest
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from std_srvs.srv import Trigger

    from bumblebee import srv
except ImportError as e:  # plain `python -m unittest discover` without ROS (drone-tests CI job)
    raise unittest.SkipTest(f'needs ROS 2 Jazzy and the built bumblebee package: {e}')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_mavros  # noqa: E402

nan = math.nan

# simple_offboard's arm_hold_after_land default: auto_arm is refused this long after /land
ARM_HOLD_AFTER_LAND = 3.0

# Set by generate_test_description(): the tests only make sense under launch_test
_LAUNCHED = False


@pytest.mark.launch_test
def generate_test_description():
    global _LAUNCHED
    _LAUNCHED = True
    # Parameters and remaps as in launch/bumblebee.launch.py
    simple_offboard = launch_ros.actions.Node(
        package='bumblebee',
        executable='simple_offboard',
        name='simple_offboard',
        output='screen',
        parameters=[{
            'reference_frames.main_camera_optical': 'map',
            'terrain_frame_mode': 'range',
            'arming_timeout': 15.0,
            'setpoint_smooth_alpha': 0.5,
        }],
        remappings=[
            ('/mavros/local_position/pose', '/mavros/mavros/pose'),
            ('/mavros/local_position/velocity_body', '/mavros/mavros/velocity_body'),
            ('/mavros/cmd/arming', '/mavros/mavros/arming'),
            ('/mavros/setpoint_position/local', '/mavros/mavros/local'),
            ('/mavros/setpoint_attitude/cmd_vel', '/mavros/mavros/cmd_vel'),
            ('/mavros/setpoint_attitude/thrust', '/mavros/mavros/thrust'),
        ],
    )
    return (launch.LaunchDescription([simple_offboard, launch_testing.actions.ReadyToTest()]),
            {'simple_offboard': simple_offboard})


SERVICES = {
    'get_telemetry': srv.GetTelemetry,
    'navigate': srv.Navigate,
    'navigate_global': srv.NavigateGlobal,
    'set_position': srv.SetPosition,
    'set_velocity': srv.SetVelocity,
    'set_attitude': srv.SetAttitude,
    'set_rates': srv.SetRates,
    'set_yaw_rate': srv.SetYawRate,
    'land': Trigger,
    'release': Trigger,
}


def navigate_request(x=nan, y=nan, z=nan, frame_id='map', speed=0.5, auto_arm=False):
    r = srv.Navigate.Request()
    r.x, r.y, r.z, r.yaw, r.speed = x, y, z, nan, speed
    r.frame_id, r.auto_arm = frame_id, auto_arm
    return r


def flight_requests(auto_arm):
    """Requests that would start OFFBOARD control (navigate, navigate_global, set_position)."""
    ng = srv.NavigateGlobal.Request()
    ng.lat, ng.lon, ng.z, ng.yaw, ng.speed, ng.auto_arm = 55.7, 37.6, 1.0, nan, 0.5, auto_arm
    sp = srv.SetPosition.Request()
    sp.x, sp.y, sp.z, sp.yaw, sp.frame_id, sp.auto_arm = 0.0, 0.0, 1.0, nan, 'body', auto_arm
    return [('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=auto_arm)),
            ('navigate_global', ng), ('set_position', sp)]


def disabled_requests(auto_arm):
    """The control paths that make PX4 leave OFFBOARD after ~1 s (A8)."""
    sv = srv.SetVelocity.Request()
    sv.vx, sv.vy, sv.vz, sv.yaw, sv.frame_id, sv.auto_arm = 0.5, 0.0, 0.0, nan, 'body', auto_arm
    sa = srv.SetAttitude.Request()
    sa.roll, sa.pitch, sa.yaw, sa.thrust, sa.frame_id, sa.auto_arm = 0.0, 0.1, 0.0, 0.5, 'body', auto_arm
    sr = srv.SetRates.Request()
    sr.roll_rate, sr.pitch_rate, sr.yaw_rate, sr.thrust, sr.auto_arm = 0.0, 0.0, 0.5, 0.5, auto_arm
    sy = srv.SetYawRate.Request()
    sy.yaw_rate = 0.5
    return [('set_velocity', sv), ('set_attitude', sa), ('set_rates', sr), ('set_yaw_rate', sy)]


class TestSimpleOffboard(unittest.TestCase):

    land_answered = -math.inf   # monotonic time of the last /land response

    @classmethod
    def setUpClass(cls):
        if not _LAUNCHED:
            raise unittest.SkipTest('run with launch_test or colcon test')
        rclpy.init()
        cls.fake = fake_mavros.FakeMavros()
        cls.node = rclpy.create_node('simple_offboard_test')
        cls.clients = {name: cls.node.create_client(srv_type, '/' + name)
                       for name, srv_type in SERVICES.items()}
        cls.executor = SingleThreadedExecutor()
        cls.executor.add_node(cls.fake)
        cls.executor.add_node(cls.node)
        cls.spin_thread = threading.Thread(target=cls.executor.spin, daemon=True)
        cls.spin_thread.start()
        for name, client in cls.clients.items():
            assert client.wait_for_service(timeout_sec=30.0), f'simple_offboard has no /{name}'

    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown()
        cls.spin_thread.join(timeout=5.0)
        cls.fake.destroy_node()
        cls.node.destroy_node()
        rclpy.shutdown()

    def setUp(self):
        # Connected, disarmed, POSCTL, no stream: simple_offboard back at its baseline
        # and past the auto_arm hold of an earlier test's /land
        hold_left = ARM_HOLD_AFTER_LAND + 0.2 - (time.monotonic() - self.land_answered)
        if hold_left > 0:
            time.sleep(hold_left)
        self.fake.reset()
        self.assertTrue(self.call('release', Trigger.Request()).success)
        time.sleep(0.4)
        with self.fake.lock:
            self.fake.clear()

    # helpers

    def call_async(self, name, request):
        return self.clients[name].call_async(request)

    def wait_future(self, future, timeout=20.0):
        deadline = time.monotonic() + timeout
        while not future.done():
            if time.monotonic() > deadline:
                self.fail(f'no service response in {timeout} s')
            time.sleep(0.01)
        return future.result()

    def call(self, name, request, timeout=20.0):
        result = self.wait_future(self.call_async(name, request), timeout)
        if name == 'land':
            type(self).land_answered = time.monotonic()
        return result

    def wait_until(self, predicate, timeout, what):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                self.fail(f'timed out waiting for {what}')
            time.sleep(0.01)

    def fly(self, pose=(0.0, 0.0, 1.0)):
        """Pretend to hover in OFFBOARD with a navigate stream at pose."""
        self.fake.set_state(armed=True, mode='OFFBOARD', pose=pose)
        time.sleep(0.4)
        x, y, z = pose
        res = self.call('navigate', navigate_request(x, y, z))
        self.assertTrue(res.success, res.message)
        time.sleep(0.4)
        self.assertGreater(len(self.fake.snapshot('setpoints')), 5, 'no setpoint stream')

    def clear_and_wait(self, seconds):
        """Records of the next `seconds` only."""
        with self.fake.lock:
            self.fake.clear()
        time.sleep(seconds)

    def assertNear(self, setpoint, expected, delta, what):
        _, x, y, z, _ = setpoint
        distance = math.dist((x, y, z), expected)
        self.assertLess(distance, delta, f'{what}: ({x:.3f}, {y:.3f}, {z:.3f}) is {distance:.3g} m '
                        f'from {expected}')

    def log_count(self, proc_output, process, text):
        return sum(io.text.decode(errors='replace').count(text) for io in proc_output[process])

    # S1: no setpoint lurch, monotonic progress on the segment

    def test_01_takeoff_holds_start_then_climbs(self):
        """auto_arm takeoff: starts at the drone, held through arm settle, then climbs."""
        self.fake.set_state(pose=(0.5, -0.3, 0.0))
        time.sleep(0.4)
        res = self.call('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        armed_at = time.monotonic()
        self.assertTrue(res.success, res.message)
        self.assertEqual(self.fake.snapshot('mode_requests'), ['OFFBOARD'])
        self.assertTrue(self.fake.snapshot('armed'))
        time.sleep(3.5)
        sp = self.fake.snapshot('setpoints')
        self.assertGreater(len(sp), 60)
        self.assertNear(sp[0], (0.5, -0.3, 0.0), 0.02, 'first setpoint')
        for _, x, y, z, _ in sp:
            self.assertAlmostEqual(x, 0.5, delta=0.01)
            self.assertAlmostEqual(y, -0.3, delta=0.01)
            self.assertTrue(-0.01 <= z <= 1.01, f'z={z} is off the segment')
        settling = [z for t, _, _, z, _ in sp if t < armed_at + 1.2]
        self.assertLess(max(settling), 0.03, 'climb started during arm_settle_time')
        self.assertGreater(sp[-1][3], 0.4, 'no climb after arm_settle_time')
        steps = [abs(b[3] - a[3]) for a, b in zip(sp, sp[1:])]
        self.assertLess(max(steps), 0.05, 'setpoint jumped')  # 0.5 m/s at 30 Hz ~ 0.017 m

    def test_02_mid_flight_navigate_has_no_lurch(self):
        """The A1 bug: the first setpoint after a navigate went ~1e8 m behind the start."""
        self.fake.set_state(armed=True, mode='OFFBOARD', pose=(0.0, 0.0, 1.0))
        time.sleep(0.4)
        started = time.monotonic()
        res = self.call('navigate', navigate_request(1.0, 0.0, 1.0, speed=0.5))
        self.assertTrue(res.success, res.message)
        time.sleep(1.0)
        sp = self.fake.snapshot('setpoints')
        self.assertGreater(len(sp), 20)
        self.assertNear(sp[0], (0.0, 0.0, 1.0), 0.03, 'first setpoint')
        previous_x = -0.01
        for t, x, y, z, _ in sp:
            self.assertLess(abs(y), 0.01)
            self.assertLess(abs(z - 1.0), 0.01)
            self.assertGreaterEqual(x, previous_x - 1e-6, 'setpoint moved backwards')
            self.assertLessEqual(x, 0.5 * (t - started) + 0.03, 'setpoint ahead of the speed')
            previous_x = x
        self.assertGreater(sp[-1][1], 0.25, 'setpoint does not move')

    # S2: the pilot (or a PX4 failsafe) wins, unknown state is refused

    def test_03_refused_when_pilot_or_failsafe_has_control(self):
        for mode in ('POSCTL', 'ALTCTL', 'STABILIZED', 'AUTO.LAND', 'AUTO.RTL'):
            self.fake.set_state(armed=True, mode=mode, pose=(0.0, 0.0, 1.0))
            time.sleep(0.4)
            for auto_arm in (True, False):
                for name, request in flight_requests(auto_arm):
                    res = self.call(name, request)
                    self.assertFalse(res.success, f'{name} accepted when armed in {mode}')
                    self.assertIn('pilot', res.message, name)
                    self.assertIn(mode, res.message, name)
        time.sleep(0.5)
        self.assertEqual(self.fake.snapshot('mode_requests'), [])
        self.assertEqual(self.fake.snapshot('arming_requests'), [])
        self.assertEqual(self.fake.snapshot('setpoints'), [])

    def test_04_refused_when_state_unknown(self):
        self.fake.set_state(state_age=10.0)   # MAVROS state stale for 10 s
        time.sleep(0.4)
        for name, request in flight_requests(auto_arm=True):
            res = self.call(name, request)
            self.assertFalse(res.success, name)
            self.assertIn('State timeout', res.message, name)
        self.fake.set_state(state_age=0.0, connected=False)
        time.sleep(0.4)
        for name, request in flight_requests(auto_arm=True):
            res = self.call(name, request)
            self.assertFalse(res.success, name)
            self.assertIn('No connection', res.message, name)
        time.sleep(0.5)
        self.assertEqual(self.fake.snapshot('mode_requests'), [])
        self.assertEqual(self.fake.snapshot('arming_requests'), [])
        self.assertEqual(self.fake.snapshot('setpoints'), [])

    # S3: dead control paths rejected before any state change

    def test_05_disabled_control_paths(self):
        # On the ground, auto_arm through these paths must not touch the FCU at all
        for name, request in disabled_requests(auto_arm=True):
            res = self.call(name, request)
            self.assertFalse(res.success, name)
            self.assertIn('disabled', res.message, name)
        time.sleep(0.3)
        self.assertEqual(self.fake.snapshot('mode_requests'), [])
        self.assertEqual(self.fake.snapshot('arming_requests'), [])
        self.assertEqual(self.fake.snapshot('setpoints'), [])
        # In flight they must leave the running navigate stream exactly as it was
        self.fly((0.2, 0.1, 1.0))
        with self.fake.lock:
            self.fake.clear()
        for name, request in disabled_requests(auto_arm=False):
            res = self.call(name, request)
            self.assertFalse(res.success, name)
            self.assertIn('disabled', res.message, name)
        time.sleep(0.5)
        sp = self.fake.snapshot('setpoints')
        self.assertGreater(len(sp), 10, 'navigate stream stopped')
        for setpoint in sp:
            self.assertNear(setpoint, (0.2, 0.1, 1.0), 0.01, 'navigate setpoint')
        self.assertEqual(self.fake.snapshot('other_setpoints'), [])
        self.assertEqual(self.fake.snapshot('mode_requests'), [])
        self.assertEqual(self.fake.snapshot('arming_requests'), [])

    # S4: PX4 leaving OFFBOARD by itself stops the stream

    def test_06_leaving_offboard_stops_stream(self, proc_output, simple_offboard):
        self.fly()
        res = self.call('navigate', navigate_request(1.0, 0.0, 1.0))
        self.assertTrue(res.success, res.message)
        self.fake.set_state(mode='POSCTL')   # the pilot flips the RC mode switch
        time.sleep(0.3)
        self.clear_and_wait(1.0)
        self.assertEqual(self.fake.snapshot('setpoints'), [], 'still streaming after a takeover')
        proc_output.assertWaitFor('PX4 left OFFBOARD for POSCTL', process=simple_offboard, timeout=5)
        # The stream does not come back by itself (e.g. a MAVROS restart reporting
        # OFFBOARD again), and the script cannot take over from the pilot
        self.fake.set_state(mode='OFFBOARD')
        time.sleep(0.2)
        self.fake.set_state(mode='POSCTL')
        self.clear_and_wait(1.0)
        self.assertEqual(self.fake.snapshot('setpoints'), [])
        res = self.call('navigate', navigate_request(0.0, 0.0, 1.0, auto_arm=True))
        self.assertFalse(res.success)
        self.assertIn('pilot', res.message)
        self.assertEqual(self.fake.snapshot('mode_requests'), [])

    def test_07_failsafe_land_stops_stream(self):
        """A PX4 failsafe switching to AUTO.LAND is not our /land: the stream stops too."""
        self.fly()
        self.fake.set_state(mode='AUTO.LAND')
        time.sleep(0.3)
        self.clear_and_wait(1.0)
        self.assertEqual(self.fake.snapshot('setpoints'), [])

    # S5: /land cancels auto_arm and lands

    def test_08_land_cancels_auto_arm(self):
        """Ctrl+C during takeoff (arming never succeeds): no motor start, AUTO.LAND."""
        self.fake.set_state(arming='never')
        time.sleep(0.3)
        navigate = self.call_async('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        self.wait_until(lambda: self.fake.snapshot('arming_requests'), 5.0, 'an arming request')
        time.sleep(0.3)
        started = time.monotonic()
        land = self.call('land', Trigger.Request(), timeout=10.0)
        land_time = time.monotonic() - started
        nav = self.wait_future(navigate, 5.0)
        self.assertTrue(land.success, land.message)
        self.assertLess(land_time, 3.0)
        self.assertFalse(nav.success)
        self.assertIn('cancel', nav.message.lower())
        self.assertEqual(self.fake.snapshot('mode'), 'AUTO.LAND')
        self.assertEqual(self.fake.snapshot('mode_requests'), ['OFFBOARD', 'AUTO.LAND'])
        time.sleep(0.2)
        self.clear_and_wait(2.5)   # simple_offboard retried arming every 2 s before
        self.assertEqual(self.fake.snapshot('arming_requests'), [], 'still arming after /land')
        self.assertEqual(self.fake.snapshot('setpoints'), [])
        self.assertFalse(self.fake.snapshot('armed'))

    def test_09_land_cancels_late_arming(self):
        """Arming ACKed but the armed state arrives late: cancelled, AUTO.LAND, no new stream."""
        self.fake.set_state(arming='late', arm_delay=1.5)
        time.sleep(0.3)
        navigate = self.call_async('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        self.wait_until(lambda: self.fake.snapshot('arming_requests'), 5.0, 'an arming request')
        time.sleep(0.2)
        land = self.call('land', Trigger.Request(), timeout=10.0)
        nav = self.wait_future(navigate, 5.0)
        self.assertTrue(land.success, land.message)
        self.assertFalse(nav.success)
        self.assertIn('cancel', nav.message.lower())
        self.wait_until(lambda: self.fake.snapshot('armed'), 5.0, 'the late arm')
        self.clear_and_wait(2.5)
        self.assertEqual(self.fake.snapshot('mode'), 'AUTO.LAND')   # PX4 lands and disarms
        self.assertEqual(self.fake.snapshot('setpoints'), [])
        self.assertEqual(self.fake.snapshot('mode_requests'), [])
        self.assertEqual(self.fake.snapshot('arming_requests'), [])

    def test_10_land_cancels_offboard_wait(self):
        """PX4 refuses OFFBOARD: /land cancels the wait at once; nothing to land on the ground."""
        self.fake.set_state(accept_offboard=False)
        time.sleep(0.3)
        navigate = self.call_async('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        self.wait_until(lambda: 'OFFBOARD' in self.fake.snapshot('mode_requests'), 5.0,
                        'the OFFBOARD request')
        time.sleep(0.2)
        started = time.monotonic()
        land = self.call('land', Trigger.Request(), timeout=10.0)
        nav = self.wait_future(navigate, 5.0)
        self.assertLess(time.monotonic() - started, 2.0, 'not cancelled (OFFBOARD timeout is 3 s)')
        self.assertFalse(nav.success)
        self.assertIn('cancel', nav.message.lower())
        self.assertFalse(land.success)   # still disarmed in POSCTL: land_only_in_offboard
        self.assertIn('not in OFFBOARD', land.message)
        self.clear_and_wait(1.0)
        self.assertEqual(self.fake.snapshot('arming_requests'), [])
        self.assertEqual(self.fake.snapshot('setpoints'), [])

    def test_11_land_in_flight(self, proc_output, simple_offboard):
        """Normal /land: AUTO.LAND, stream stops, not reported as a pilot takeover."""
        self.fly()
        takeovers = self.log_count(proc_output, simple_offboard, 'PX4 left OFFBOARD')
        land = self.call('land', Trigger.Request(), timeout=10.0)
        self.assertTrue(land.success, land.message)
        self.assertEqual(self.fake.snapshot('mode'), 'AUTO.LAND')
        time.sleep(0.2)
        self.clear_and_wait(1.0)
        self.assertEqual(self.fake.snapshot('setpoints'), [])
        self.assertEqual(self.log_count(proc_output, simple_offboard, 'PX4 left OFFBOARD'), takeovers)

    def test_12_land_cancels_queued_auto_arm(self):
        """/land while a navigate(auto_arm) still waits in the service queue: no motor start.

        get_telemetry on a missing frame holds the services callback group for
        telemetry_transform_timeout (0.5 s), the navigate sent next waits behind it, and
        /land (own callback group) runs and fails at once, still disarmed in POSCTL.
        """
        telemetry_request = srv.GetTelemetry.Request()
        telemetry_request.frame_id = 'no_such_frame'
        telemetry = self.call_async('get_telemetry', telemetry_request)
        time.sleep(0.05)
        navigate = self.call_async('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        time.sleep(0.05)
        land = self.call('land', Trigger.Request(), timeout=10.0)
        self.assertFalse(navigate.done(), 'the navigate was not queued behind get_telemetry')
        self.assertFalse(land.success)
        self.assertIn('not in OFFBOARD', land.message)
        nav = self.wait_future(navigate, 5.0)
        self.wait_future(telemetry, 5.0)
        self.assertFalse(nav.success, 'queued auto_arm ran after /land')
        self.assertIn('cancel', nav.message.lower())
        self.assertIn('land requested', nav.message)
        time.sleep(0.5)
        self.assertEqual(self.fake.snapshot('mode_requests'), [])
        self.assertEqual(self.fake.snapshot('arming_requests'), [])
        self.assertEqual(self.fake.snapshot('setpoints'), [])
        self.assertFalse(self.fake.snapshot('armed'))
        # The hold is bounded: a takeoff asked for after it arms as usual
        time.sleep(max(0.0, ARM_HOLD_AFTER_LAND + 0.2 - (time.monotonic() - self.land_answered)))
        res = self.call('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        self.assertTrue(res.success, res.message)
        self.assertEqual(self.fake.snapshot('arming_requests'), [True])

    # S4: MAVROS restart or FCU link loss, where no exit from OFFBOARD is ever seen

    def test_13_mavros_restart_stops_stream(self, proc_output, simple_offboard):
        """MAVROS dies mid-flight and launch respawns it: the old target must not reach it.

        PX4 left OFFBOARD during the outage (COM_OF_LOSS_T) and goes back to it as soon
        as setpoints arrive again, so the new MAVROS may first report OFFBOARD. Runs
        last: it replaces the shared fake MAVROS.
        """
        self.fly()
        res = self.call('navigate', navigate_request(2.0, 0.0, 1.0))
        self.assertTrue(res.success, res.message)
        # Lost heartbeats must not stop the stream: MAVROS reports State at 1 Hz, so
        # two lost ones and a late third leave 3.05 s or more without State, past
        # state_timeout (3 s). Here 3.1-3.3 s (the fake's last State before the gap
        # is up to 0.2 s old).
        self.fake.set_state(publish_states=False)
        self.clear_and_wait(3.1)
        self.fake.set_state(publish_states=True)
        self.assertGreater(len(self.fake.snapshot('setpoints')), 70, 'stream stopped on lost heartbeats')
        time.sleep(0.5)
        self.assertEqual(self.log_count(proc_output, simple_offboard, 'No FCU state'), 0)
        # MAVROS crashes, launch respawns it 5 s later (respawn_delay in bumblebee.launch.py)
        old = self.fake
        self.executor.remove_node(old)
        old.destroy_node()
        time.sleep(5.5)
        new = fake_mavros.FakeMavros(armed=True, mode='OFFBOARD', pose=(0.6, 0.0, 1.0))
        type(self).fake = new
        self.executor.add_node(new)
        time.sleep(1.5)
        self.assertEqual(new.snapshot('setpoints'), [], 'the stale target reached the respawned MAVROS')
        proc_output.assertWaitFor('No FCU state', process=simple_offboard, timeout=5)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _LAUNCHED:
            raise unittest.SkipTest('run with launch_test or colcon test')

    def test_exit_code(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info)
