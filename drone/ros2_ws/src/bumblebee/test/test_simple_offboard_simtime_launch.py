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

"""Launch test: the real simple_offboard binary under use_sim_time (Gazebo sim).

Gazebo runs at ~25% of real time with the GUI open and PX4 SITL in lockstep with
it (bumblebee_sim.launch.py sets use_sim_time for every node). Navigate speed, the
arm settle hold and the FCU state watchdog must follow /clock there, not the wall
clock. A fake /clock at 0.25x real time drives simple_offboard and a fake MAVROS
that publishes State once per simulated second, like PX4's heartbeat.

    colcon test --packages-select bumblebee     (registered in CMakeLists.txt)
    launch_test test/test_simple_offboard_simtime_launch.py

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
    from rclpy.parameter import Parameter
    from rosgraph_msgs.msg import Clock
    from std_srvs.srv import Trigger

    from bumblebee import srv
except ImportError as e:  # plain `python -m unittest discover` without ROS (drone-tests CI job)
    raise unittest.SkipTest(f'needs ROS 2 Jazzy and the built bumblebee package: {e}')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_mavros  # noqa: E402

nan = math.nan

# Simulated seconds per wall second (Gazebo with the GUI open)
RTF = 0.25
SIM_START = 1000.0

# Set by generate_test_description(): the tests only make sense under launch_test
_LAUNCHED = False


@pytest.mark.launch_test
def generate_test_description():
    global _LAUNCHED
    _LAUNCHED = True
    # As in test_simple_offboard_launch.py, plus use_sim_time
    simple_offboard = launch_ros.actions.Node(
        package='bumblebee',
        executable='simple_offboard',
        name='simple_offboard',
        output='screen',
        parameters=[{
            'use_sim_time': True,
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


def navigate_request(x=nan, y=nan, z=nan, frame_id='map', speed=0.5, auto_arm=False):
    r = srv.Navigate.Request()
    r.x, r.y, r.z, r.yaw, r.speed = x, y, z, nan, speed
    r.frame_id, r.auto_arm = frame_id, auto_arm
    return r


class TestSimTime(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _LAUNCHED:
            raise unittest.SkipTest('run with launch_test or colcon test')
        rclpy.init()
        # /clock first, so the nodes below never see time 0 for long
        cls.sim = SIM_START
        cls.sim_lock = threading.Lock()
        cls.clock_node = rclpy.create_node('fake_clock')
        cls.clock_pub = cls.clock_node.create_publisher(Clock, '/clock', 10)
        cls.clock_running = True
        cls.clock_thread = threading.Thread(target=cls._run_clock, daemon=True)
        cls.clock_thread.start()
        sim_time = [Parameter('use_sim_time', Parameter.Type.BOOL, True)]
        cls.fake = fake_mavros.FakeMavros(state_period=1.0, parameter_overrides=sim_time)
        cls.node = rclpy.create_node('simple_offboard_simtime_test')
        cls.clients = {'navigate': cls.node.create_client(srv.Navigate, '/navigate'),
                       'release': cls.node.create_client(Trigger, '/release')}
        cls.executor = SingleThreadedExecutor()
        cls.executor.add_node(cls.fake)
        cls.executor.add_node(cls.node)
        cls.spin_thread = threading.Thread(target=cls.executor.spin, daemon=True)
        cls.spin_thread.start()
        for name, client in cls.clients.items():
            assert client.wait_for_service(timeout_sec=30.0), f'simple_offboard has no /{name}'

    @classmethod
    def tearDownClass(cls):
        cls.clock_running = False
        cls.clock_thread.join(timeout=5.0)
        cls.executor.shutdown()
        cls.spin_thread.join(timeout=5.0)
        cls.fake.destroy_node()
        cls.node.destroy_node()
        cls.clock_node.destroy_node()
        rclpy.shutdown()

    @classmethod
    def _run_clock(cls):
        last = time.monotonic()
        while cls.clock_running:
            time.sleep(0.01)
            now = time.monotonic()
            with cls.sim_lock:
                cls.sim += (now - last) * RTF
                sim = cls.sim
            last = now
            msg = Clock()
            msg.clock.sec = int(sim)
            msg.clock.nanosec = int((sim % 1) * 1e9)
            cls.clock_pub.publish(msg)

    def setUp(self):
        self.fake.reset()
        self.assertTrue(self.call('release', Trigger.Request()).success)
        self.wait_sim(0.5)
        with self.fake.lock:
            self.fake.clear()

    # helpers

    def sim_now(self):
        with self.sim_lock:
            return self.sim

    def wait_sim(self, seconds):
        end = self.sim_now() + seconds
        while self.sim_now() < end:
            time.sleep(0.01)

    def call(self, name, request, timeout=30.0):
        future = self.clients[name].call_async(request)
        deadline = time.monotonic() + timeout
        while not future.done():
            if time.monotonic() > deadline:
                self.fail(f'no service response in {timeout} s')
            time.sleep(0.01)
        return future.result()

    def test_01_navigate_speed_in_sim_seconds(self, proc_output, simple_offboard):
        """speed is m per simulated second, and 1 Hz (sim) heartbeats keep the stream."""
        self.fake.set_state(armed=True, mode='OFFBOARD', pose=(0.0, 0.0, 1.0))
        self.wait_sim(0.5)
        called = time.monotonic()
        res = self.call('navigate', navigate_request(4.0, 0.0, 1.0, speed=0.5))
        self.assertTrue(res.success, res.message)
        time.sleep(7.0)   # 1.75 s simulated; State arrives every 4 s of wall time
        sp = self.fake.snapshot('setpoints')
        window = [s for s in sp if called + 2.0 <= s[0] <= called + 6.0]
        self.assertGreater(len(window), 90, 'setpoint stream stopped')   # 30 Hz wall
        self.assertGreater(sp[-1][0], called + 6.5, 'setpoint stream stopped')
        (_, x1, _, _, stamp1), (_, x2, _, _, stamp2) = window[0], window[-1]
        speed = (x2 - x1) / ((stamp2 - stamp1) * 1e-9)
        self.assertAlmostEqual(speed, 0.5, delta=0.1,
                               msg=f'{speed:.3f} m per simulated second, requested 0.5')
        self.assertLess(sp[-1][1], 1.2, 'setpoint ahead of the simulated speed')
        for _, _, y, z, _ in sp:
            self.assertLess(abs(y), 0.01)
            self.assertLess(abs(z - 1.0), 0.01)
        self.assertEqual(sum(io.text.decode(errors='replace').count('No FCU state')
                             for io in proc_output[simple_offboard]), 0)

    def test_02_arm_settle_in_sim_seconds(self):
        """auto_arm takeoff holds the start for arm_settle_time (1.5 s) of simulated time."""
        self.fake.set_state(pose=(0.0, 0.0, 0.0))
        self.wait_sim(0.5)
        res = self.call('navigate', navigate_request(z=1.0, frame_id='body', auto_arm=True))
        armed_sim = self.sim_now()
        self.assertTrue(res.success, res.message)
        self.assertTrue(self.fake.snapshot('armed'))
        self.wait_sim(2.5)   # 10 s of wall time
        sp = self.fake.snapshot('setpoints')
        settling = [z for _, _, _, z, stamp in sp if stamp * 1e-9 < armed_sim + 1.3]
        self.assertGreater(len(settling), 100)   # 1.3 s simulated = 5.2 s wall at 30 Hz
        self.assertLess(max(settling), 0.03, 'climb started during arm_settle_time')
        self.assertGreater(sp[-1][3], 0.3, 'no climb after arm_settle_time')
        self.assertLess(sp[-1][3], 0.65, 'climbing faster than 0.5 m per simulated second')


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _LAUNCHED:
            raise unittest.SkipTest('run with launch_test or colcon test')

    def test_exit_code(self, proc_info):
        launch_testing.asserts.assertExitCodes(proc_info)
