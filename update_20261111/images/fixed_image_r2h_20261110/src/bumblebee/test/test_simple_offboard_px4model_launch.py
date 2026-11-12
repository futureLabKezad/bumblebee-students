"""Real C++ controller with the opt-in bounded PX4 command model.

Every service, topic and TF uses a random private namespace. There is no MAVLink.
These checks exercise ROS contracts and do not count as real PX4 SITL gates.
"""
import math
import json
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
    from rclpy.executors import MultiThreadedExecutor
    from bumblebee import srv
    from bumblebee.msg import State as ControllerState
    from mavros_msgs.msg import State as MavrosState
    from std_srvs.srv import Trigger
except ImportError as exc:
    raise unittest.SkipTest(f'ROS Jazzy and a built package required: {exc}')

sys.path.insert(0, os.path.dirname(__file__))
from fake_mavros import FakeMavros, LATCHED
from test_safety import TEST_NS, topic, guard_graph
from executor_support import CooperativeExecutor as MultiThreadedExecutor

LAUNCHED = False


@pytest.mark.launch_test
def generate_test_description():
    global LAUNCHED
    guard_graph()
    LAUNCHED = True
    controller = launch_ros.actions.Node(
        package='bumblebee', executable='simple_offboard',
        name='simple_offboard_tested', namespace=TEST_NS, output='screen',
        parameters=[{'arming_timeout': 15.0, 'use_sim_time': False,
                     'state_watchdog_timeout': 4.5}],
        remappings=[('/tf', topic('/tf')), ('/tf_static', topic('/tf_static')),
                    (topic('/mavros/local_position/pose'), topic('/mavros/mavros/pose')),
                    (topic('/mavros/cmd/arming'), topic('/mavros/mavros/arming')),
                    (topic('/mavros/setpoint_position/local'), topic('/mavros/mavros/local'))])
    return launch.LaunchDescription([controller, launch_testing.actions.ReadyToTest()]), {'controller': controller}


class TestControllerPx4Model(unittest.TestCase):
    land_answered = -math.inf

    @classmethod
    def setUpClass(cls):
        if not LAUNCHED:
            raise unittest.SkipTest('launch_test required')
        rclpy.init()
        cls.fake = FakeMavros(faithful=True)
        cls.node = rclpy.create_node('faithful_model_test')
        cls.observe_lock = threading.Lock()
        cls.heartbeat_receipts = []
        cls.controller_reports = []
        cls.node.create_subscription(MavrosState, topic('/mavros/state'),
                                     cls.observe_heartbeat, LATCHED)
        cls.node.create_subscription(ControllerState, topic('/state'),
                                     cls.observe_controller, LATCHED)
        cls.clients = {name: cls.node.create_client(kind, topic(name)) for name, kind in
                       [('navigate', srv.Navigate), ('get_telemetry', srv.GetTelemetry),
                        ('release', Trigger), ('land', Trigger)]}
        cls.executor = MultiThreadedExecutor(num_threads=4)
        cls.executor.add_node(cls.fake)
        cls.executor.add_node(cls.node)
        cls.thread = threading.Thread(target=cls.executor.spin, daemon=True)
        cls.thread.start()
        for client in cls.clients.values():
            assert client.wait_for_service(timeout_sec=20.)

    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown()
        cls.thread.join(timeout=5.)
        cls.fake.destroy_node()
        cls.node.destroy_node()
        rclpy.shutdown()

    def setUp(self):
        left = 3.3 - (time.monotonic() - self.land_answered)
        if left > 0:
            time.sleep(left)
        self.call('release', Trigger.Request())
        self.fake.reset()
        time.sleep(1.2)  # at least one real heartbeat; no immediate state report

    def until(self, predicate, timeout=10., what='condition'):
        end = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), end, 'timeout: ' + what)
            time.sleep(.01)

    def future(self, future, timeout=20.):
        self.until(future.done, timeout, 'service reply')
        return future.result()

    def call(self, name, req, timeout=20.):
        reply = self.future(self.clients[name].call_async(req), timeout)
        if name == 'land':
            type(self).land_answered = time.monotonic()
        return reply

    def nav(self, auto_arm=False, z=1.):
        req = srv.Navigate.Request()
        req.x = req.y = 0.
        req.z, req.yaw, req.speed = z, math.nan, .4
        req.frame_id, req.auto_arm = 'map', auto_arm
        return req

    @classmethod
    def observe_heartbeat(cls, msg):
        with cls.observe_lock:
            cls.heartbeat_receipts.append((time.monotonic(), msg.connected,
                                            msg.armed, msg.mode))

    @classmethod
    def observe_controller(cls, msg):
        with cls.observe_lock:
            cls.controller_reports.append((time.monotonic(), msg.mode))

    @classmethod
    def observed(cls, name):
        with cls.observe_lock:
            return list(getattr(cls, name))

    def drop_after_next_heartbeat(self):
        """Use a received heartbeat boundary, rather than the request time."""
        requested = time.monotonic()
        self.until(lambda: any(row[0] >= requested and row[1:] == (True, True, 'OFFBOARD')
                               for row in self.observed('heartbeat_receipts')),
                   2., 'known armed OFFBOARD heartbeat')
        self.fake.set_state(publish_states=False)
        # A queued observation can arrive just after suppression. It is an
        # actual heartbeat and must replace the older boundary, if present.
        time.sleep(.05)
        return self.observed('heartbeat_receipts')[-1][0]

    def wait_to(self, deadline):
        self.until(lambda: time.monotonic() >= deadline,
                   max(.1, deadline - time.monotonic() + .5), 'real-time boundary')

    def test_00_state_reports_only_follow_heartbeats(self):
        for i in range(10):
            self.fake.set_state(mode='ALTCTL' if i % 2 else 'POSCTL')
            time.sleep(.1)
        time.sleep(2.2)
        stamps = [row[0] for row in self.fake.snapshot('state_publications')]
        self.assertGreaterEqual(len(stamps), 3)
        for a, b in zip(stamps, stamps[1:]):
            self.assertGreater(b - a, .8, 'state-on-change bypassed heartbeat reporting')

    def test_01_legitimate_takeoff_with_heartbeat_only_reports(self):
        reply = self.call('navigate', self.nav(auto_arm=True))
        self.assertTrue(reply.success, reply.message)
        self.assertEqual(self.fake.snapshot('arming_requests'), [True])
        self.assertTrue(self.fake.snapshot('true_armed'))
        self.assertEqual(self.fake.snapshot('true_mode'), 'OFFBOARD')

    def test_02_cancel_before_arm_reaches_fake(self):
        self.fake.set_state(accept_offboard=False)
        pending = self.clients['navigate'].call_async(self.nav(auto_arm=True))
        self.until(lambda: 'OFFBOARD' in self.fake.snapshot('mode_requests'), what='OFFBOARD attempt')
        self.call('land', Trigger.Request())
        reply = self.future(pending)
        self.assertFalse(reply.success)
        self.assertIn('cancel', reply.message.lower())
        self.assertEqual(self.fake.snapshot('arming_requests'), [])
        self.assertFalse(self.fake.snapshot('true_armed'))

    def test_03_four_second_ack_then_land_settles_arm(self):
        self.fake.set_state(ack_delay=4., arming='late', arm_delay=5.)
        pending = self.clients['navigate'].call_async(self.nav(auto_arm=True))
        self.until(lambda: self.fake.snapshot('arming_requests'), what='ARM sent')
        start = time.monotonic()
        land = self.call('land', Trigger.Request(), timeout=16.)
        reply = self.future(pending)
        self.assertLess(time.monotonic() - start, 13.)
        self.assertTrue(land.success, land.message)
        self.assertFalse(reply.success)
        self.assertIn('cancel', reply.message.lower())
        self.assertEqual(self.fake.snapshot('arming_requests'), [True, False])
        self.assertFalse(self.fake.snapshot('true_armed'))
        self.assertTrue(any(e[1:] == ('disarm', 'external command')
                            for e in self.fake.snapshot('command_events')))

    def test_04_stream_loss_lands_in_bounded_model(self):
        self.fake.set_state(dynamics=True, obl_rc_act=4, of_loss_t=3.,
                            pose=(0., 0., .6), armed=True, mode='OFFBOARD',
                            last_setpoint=time.monotonic())
        time.sleep(1.1)
        reply = self.call('navigate', self.nav(z=.6))
        self.assertTrue(reply.success, reply.message)
        self.until(lambda: len(self.fake.snapshot('setpoints')) > 5, what='stream')
        self.fake.set_state(of_loss_t=1.)
        self.assertTrue(self.call('release', Trigger.Request()).success)
        self.until(lambda: self.fake.snapshot('true_mode') == 'AUTO.LAND', 3., 'loss mode')
        self.until(lambda: not self.fake.snapshot('true_armed'), 6., 'landing auto-disarm')
        self.assertEqual(self.fake.snapshot('pose')[2], 0.)
        self.assertNotIn('AUTO.LAND', self.fake.snapshot('mode_requests'))

    def test_05_disconnection_is_unknown_and_stream_does_not_resume(self):
        self.fake.set_state(armed=True, mode='OFFBOARD', obl_rc_act=4, of_loss_t=6.,
                            last_setpoint=time.monotonic())
        time.sleep(1.2)
        reply = self.call('navigate', self.nav(z=0.))
        self.assertTrue(reply.success, reply.message)
        self.fake.set_state(connected=False)
        time.sleep(4.2)
        req = srv.GetTelemetry.Request()
        req.frame_id = 'map'
        telem = self.call('get_telemetry', req)
        self.assertFalse(telem.connected)
        self.assertFalse(telem.armed)  # unknown report, true vehicle still armed
        self.assertTrue(self.fake.snapshot('true_armed'))
        before = len(self.fake.snapshot('setpoints'))
        self.fake.set_state(connected=True, mode='AUTO.LAND')
        time.sleep(1.5)
        self.assertEqual(len(self.fake.snapshot('setpoints')), before)
        self.assertEqual(self.fake.snapshot('true_mode'), 'AUTO.LAND')

    def test_06_realtime_short_and_long_heartbeat_gaps(self):
        """S9 timing contract with real C++ and private ROS; not a Gazebo gate.

        All clocks advance at real time. Heartbeats alone are suppressed;
        poses and setpoint reception continue. The controller watchdog is
        configured at its production default 4.5 s, PX4 model stream loss at
        1 s. Independent observer receipt times have a 50 ms DDS tolerance.
        """
        self.assertFalse(self.fake.get_parameter('use_sim_time').value)
        self.assertFalse(self.node.get_parameter('use_sim_time').value)
        self.fake.set_state(armed=True, mode='OFFBOARD', pose=(0., 0., .6),
                            dynamics=False, obl_rc_act=4, of_loss_t=3.,
                            resume_offboard=True, last_setpoint=time.monotonic())
        time.sleep(1.2)
        reply = self.call('navigate', self.nav(z=.6))
        self.assertTrue(reply.success, reply.message)
        self.until(lambda: len(self.fake.snapshot('setpoints')) > 5, what='active stream')
        self.fake.set_state(of_loss_t=1.)
        requests = (self.fake.snapshot('arming_requests'), self.fake.snapshot('mode_requests'))

        short_hb = self.drop_after_next_heartbeat()
        short_baseline = len(self.fake.snapshot('setpoints'))
        short_state_baseline = len(self.observed('heartbeat_receipts'))
        while time.monotonic() < short_hb + 3.5:
            self.assertTrue(self.fake.snapshot('true_armed'))
            self.assertEqual(self.fake.snapshot('true_mode'), 'OFFBOARD')
            self.assertLess(time.monotonic() - self.fake.snapshot('setpoints')[-1][0], .25,
                            'short heartbeat gap stopped the setpoint stream')
            time.sleep(.02)
        short_restored = time.monotonic()
        self.assertGreaterEqual(short_restored - short_hb, 3.5)
        self.assertLess(short_restored - short_hb, 3.65)
        self.assertEqual(len(self.observed('heartbeat_receipts')), short_state_baseline)
        self.assertGreater(len(self.fake.snapshot('setpoints')), short_baseline + 20)
        self.fake.set_state(publish_states=True)
        self.until(lambda: self.observed('heartbeat_receipts')[-1][0] >= short_restored,
                   1.2, 'short-gap heartbeat recovery')
        recovered_sp = len(self.fake.snapshot('setpoints'))
        time.sleep(.3)
        self.assertGreater(len(self.fake.snapshot('setpoints')), recovered_sp)
        self.assertEqual(self.fake.snapshot('true_mode'), 'OFFBOARD')
        self.assertEqual((self.fake.snapshot('arming_requests'), self.fake.snapshot('mode_requests')),
                         requests, 'heartbeat restoration issued a new ARM or mode command')

        long_hb = self.drop_after_next_heartbeat()
        long_state_baseline = len(self.observed('heartbeat_receipts'))
        # A visible MODE_NONE is emitted by the actual C++ stopStream, not by
        # an invented fake stop callback. While it is awaited heartbeats stay
        # suppressed, and the PX4 model still receives every setpoint.
        self.until(lambda: any(stamp >= long_hb and mode == ControllerState.MODE_NONE
                               for stamp, mode in self.observed('controller_reports')),
                   5.2, 'real C++ heartbeat watchdog stop')
        stopped = next(stamp for stamp, mode in self.observed('controller_reports')
                       if stamp >= long_hb and mode == ControllerState.MODE_NONE)
        self.assertGreaterEqual(stopped - long_hb, 4.45)
        self.assertLess(stopped - long_hb, 4.8)
        self.wait_to(long_hb + 5.)
        long_restored = time.monotonic()
        self.assertGreaterEqual(long_restored - long_hb, 5.)
        self.assertLess(long_restored - long_hb, 5.15)
        self.assertEqual(len(self.observed('heartbeat_receipts')), long_state_baseline)
        stopped_sp = self.fake.snapshot('setpoints')
        self.assertLessEqual(stopped_sp[-1][0] - long_hb, 4.65)
        self.fake.set_state(publish_states=True)
        self.until(lambda: self.fake.snapshot('true_mode') == 'AUTO.LAND', 1.6,
                   'model OFFBOARD loss after actual stream stop')
        loss = [stamp for stamp, kind, value in self.fake.snapshot('command_events')
                if stamp >= long_hb and kind == 'offboard_loss' and value == 'AUTO.LAND']
        self.assertTrue(loss)
        self.assertGreaterEqual(loss[0] - stopped_sp[-1][0], 1.)
        self.assertLess(loss[0] - stopped_sp[-1][0], 1.15)
        self.until(lambda: self.observed('heartbeat_receipts')[-1][0] >= long_restored,
                   1.2, 'long-gap heartbeat recovery')
        time.sleep(1.3)
        self.assertTrue(self.fake.snapshot('true_armed'))
        self.assertEqual(self.fake.snapshot('true_mode'), 'AUTO.LAND')
        self.assertEqual(len(self.fake.snapshot('setpoints')), len(stopped_sp),
                         'heartbeat restoration resumed an old setpoint stream')
        self.assertEqual((self.fake.snapshot('arming_requests'), self.fake.snapshot('mode_requests')),
                         requests, 'heartbeat gaps issued a new ARM or mode command')
        print('S9_REALTIME_TIMING ' + json.dumps({
            'clock': 'steady wall; use_sim_time=False',
            'gate_kind': 'real C++ / bounded fake ROS contract, not Gazebo acceptance',
            'short_suppression_seconds': short_restored - short_hb,
            'long_suppression_seconds': long_restored - long_hb,
            'watchdog_stop_observer_seconds': stopped - long_hb,
            'watchdog_observer_tolerance_seconds': .05,
            'offboard_loss_after_last_setpoint_seconds': loss[0] - stopped_sp[-1][0],
            'forwarded_setpoints_after_long_recovery':
                len(self.fake.snapshot('setpoints')) - len(stopped_sp),
            'additional_arm_requests': len(self.fake.snapshot('arming_requests')) - len(requests[0]),
            'additional_mode_requests': len(self.fake.snapshot('mode_requests')) - len(requests[1]),
        }, sort_keys=True), flush=True)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):
    def test_exit_codes(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info)
