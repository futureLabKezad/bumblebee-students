"""Real drone.py subprocess, real ROS and real C++ controller; private fake FCU.

Despite the historical file name this runs outside launch_testing, so its service
dispatch is measured independently. A /land proxy only records and forwards the
real Trigger request; no SDK function or client is replaced. No MAVLink exists.
"""
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

try:
    import rclpy
    from rclpy.callback_groups import ReentrantCallbackGroup
    from rclpy.executors import MultiThreadedExecutor
    from ament_index_python.packages import get_package_prefix
    from std_srvs.srv import Trigger
except ImportError as exc:
    raise unittest.SkipTest(f'ROS Jazzy and a built package required: {exc}')

from fake_mavros import FakeMavros
from test_safety import TEST_NS, topic, guard_graph
from executor_support import CooperativeExecutor as MultiThreadedExecutor


def test_real_sdk_sigint_protocol():
    env = dict(os.environ, ROS_DOMAIN_ID='88', ROS_LOCALHOST_ONLY='1',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               FASTDDS_BUILTIN_TRANSPORTS='UDPv4')
    result = subprocess.run([sys.executable, __file__, '--worker'], env=env,
                            text=True, capture_output=True, timeout=140.)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)


def sdk_child():
    # Inputs contain no arbitrary program to execute. Validate the source is the
    # package's actual SDK and every ROS remapping has a private destination.
    sdk = Path(sys.argv[sys.argv.index('--sdk-child') + 1]).resolve()
    safe = sys.argv[sys.argv.index('--sdk-child') + 2] == 'safe'
    assert sdk == (Path(__file__).resolve().parents[1] / 'examples/drone.py')
    remaps = [arg for arg in sys.argv if ':=' in arg]
    assert remaps and all(arg.split(':=', 1)[1].startswith('/bb_test_')
                          for arg in remaps)
    guard_graph()
    spec = importlib.util.spec_from_file_location('real_flight_sdk', sdk)
    drone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drone)
    if safe:
        drone.enable_safe_interrupt()
    try:
        result = drone.takeoff(height=.5, vision_timeout=20.)
        assert safe and result is False, 'SIGINT did not cancel the real takeoff'
        landed = drone.safe_land(timeout=12.)
        assert landed is True, 'safe_land did not confirm the disarmed ground state'
        print('SDK_CANCEL_PASS safe', flush=True)
    except KeyboardInterrupt:
        assert not safe, 'safe interrupt unexpectedly raised KeyboardInterrupt'
        print('SDK_CANCEL_PASS plain', flush=True)
    finally:
        drone._shutdown()


def worker():
    assert os.environ.get('ROS_LOCALHOST_ONLY') == '1'
    assert os.environ.get('ROS_DOMAIN_ID') == '88'
    guard_graph()
    rclpy.init()
    fake = FakeMavros(faithful=True)
    node = rclpy.create_node('real_sdk_cancel_observer')
    controller_land = node.create_client(Trigger, topic('/land'))
    observed = []
    proxy_group = ReentrantCallbackGroup()

    def forward_land(req, response):
        observed.append(time.monotonic())
        future = controller_land.call_async(req)
        end = time.monotonic() + 20.
        while not future.done() and time.monotonic() < end:
            time.sleep(.005)
        if not future.done():
            response.success, response.message = False, 'isolated test relay timed out'
        else:
            reply = future.result()
            response.success, response.message = reply.success, reply.message
        return response

    node.create_service(Trigger, topic('/observed_land'), forward_land,
                        callback_group=proxy_group)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(fake)
    executor.add_node(node)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()
    binary = str(Path(get_package_prefix('bumblebee')) / 'lib/bumblebee/simple_offboard')
    cpp_remaps = [('/tf', topic('/tf')), ('/tf_static', topic('/tf_static')),
                  (topic('/mavros/local_position/pose'), topic('/mavros/mavros/pose')),
                  (topic('/mavros/cmd/arming'), topic('/mavros/mavros/arming')),
                  (topic('/mavros/setpoint_position/local'), topic('/mavros/mavros/local'))]
    args = [binary, '--ros-args', '-r', '__ns:=' + TEST_NS,
            '-r', '__node:=simple_offboard_tested']
    for src, dst in cpp_remaps:
        args += ['-r', src + ':=' + dst]
    log = tempfile.TemporaryFile(mode='w+')
    cpp = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    child = None

    def until(predicate, timeout, what):
        end = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < end, 'timeout: ' + what
            assert cpp.poll() is None, 'controller exited unexpectedly'
            time.sleep(.005)

    try:
        assert controller_land.wait_for_service(timeout_sec=20.)
        rows = []
        for kind in ['safe', 'plain']:
            # Rejection makes the signal test independent of accidental arm-time
            # ordering. Separately assert that no new ARM follows the cancellation.
            fake.reset(arming='never', dynamics=True)
            time.sleep(1.2)
            observed.clear()
            sdk = Path(__file__).resolve().parents[1] / 'examples/drone.py'
            sdk_args = [sys.executable, __file__, '--sdk-child', str(sdk), kind,
                        '--ros-args', '-r', '__ns:=' + TEST_NS]
            names = ['/get_telemetry', '/navigate', '/land',
                     '/mavros/mavros/arming', '/mavros/set_mode',
                     '/vpe_fix/set_param', '/mavros/mavros/pull',
                     '/aruco_detect/markers_used', '/aruco_detect/yaw_locked',
                     '/mavros/state', '/mavros/battery', '/tf', '/tf_static', '/clock']
            for name in names:
                target = '/observed_land' if name == '/land' else name
                sdk_args += ['-r', name + ':=' + topic(target)]
            child = subprocess.Popen(sdk_args, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True)
            until(lambda: fake.snapshot('true_mode') == 'OFFBOARD' or child.poll() is not None,
                  30., 'SDK OFFBOARD request')
            assert child.poll() is None, child.communicate()[0]
            time.sleep(.5)
            signal_time = time.monotonic()
            os.kill(child.pid, signal.SIGINT)
            until(lambda: bool(observed) or child.poll() is not None, 3., '/land after SIGINT')
            assert observed, 'SDK exited or did not request /land after SIGINT'
            delay = observed[0] - signal_time
            assert delay < .5, ('SIGINT-to-/land request', delay)
            output, _ = child.communicate(timeout=35.)
            assert child.returncode == 0 and 'SDK_CANCEL_PASS ' + kind in output, output
            assert not fake.snapshot('true_armed')
            count = len(fake.snapshot('arming_requests'))
            time.sleep(2.2)
            assert len(fake.snapshot('arming_requests')) == count, 'ARM after cancellation'
            assert not fake.snapshot('setpoints') or time.monotonic() - fake.snapshot('setpoints')[-1][0] > 2.
            rows.append({'variant': kind, 'sigint_to_land_request_s': delay,
                         'arming_requests': fake.snapshot('arming_requests'),
                         'true_armed': fake.snapshot('true_armed'), 'output': output})
            child = None
            time.sleep(3.3)  # persistent cancel/arm hold of the real controller
        print(json.dumps(rows))
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.communicate(timeout=5.)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=5.)
        if cpp.poll() is None:
            cpp.send_signal(signal.SIGINT)
            try:
                cpp.wait(timeout=10.)
            except subprocess.TimeoutExpired:
                cpp.kill()
                cpp.wait(timeout=5.)
        log.seek(0)
        print(log.read())
        log.close()
        executor.shutdown()
        spin.join(timeout=5.)
        fake.destroy_node()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    if '--sdk-child' in sys.argv:
        sdk_child()
    else:
        assert '--worker' in sys.argv
        worker()
