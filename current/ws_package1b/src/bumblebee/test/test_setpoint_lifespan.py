"""Isolated DDS expiry diagnostic: real PoseStamped writer, SIGSTOP/CONT, no flight services.

Run separately after sourcing ROS Jazzy:
    python3 test/test_setpoint_lifespan.py

The reader keeps MAVROS 2.14's SensorDataQoS (including default infinite lifespan).
A failure is evidence that writer-only lifespan cannot protect a sample already
accepted into the reader's history; do not change the reader to make this pass.
The production C++ helper's exact QoS is checked by the corresponding gtest.
"""
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent


def test_dds_lifespan_with_sensor_reader():
    env = dict(os.environ, ROS_DOMAIN_ID='90', ROS_LOCALHOST_ONLY='1',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               FASTDDS_BUILTIN_TRANSPORTS='UDPv4', RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
                            env=env, capture_output=True, text=True, timeout=70)
    print(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr


def read_event(process, kind, timeout=10.0):
    deadline = time.monotonic() + timeout
    seen = []
    while time.monotonic() < deadline:
        ready, _, _ = select.select([process.stdout], [], [], min(.1, deadline-time.monotonic()))
        if not ready:
            if process.poll() is not None:
                break
            continue
        line = process.stdout.readline()
        if not line:
            break
        seen.append(line.rstrip())
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get('kind') == kind:
            return message
    raise AssertionError('No %s from writer: %s' % (kind, seen))


def wait_stopped(process):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        pid, status = os.waitpid(process.pid, os.WUNTRACED | os.WNOHANG)
        if pid:
            assert os.WIFSTOPPED(status), 'writer terminated instead of SIGSTOP'
            return
        time.sleep(.005)
    raise AssertionError('writer did not stop')


def worker():
    assert os.environ.get('ROS_DOMAIN_ID') == '90'
    assert os.environ.get('ROS_LOCALHOST_ONLY') == '1'
    assert os.environ.get('RMW_IMPLEMENTATION') == 'rmw_fastrtps_cpp'
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import qos_profile_sensor_data
    from test_safety import guard_graph
    guard_graph()
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    rows = []
    try:
        for kind, pause in [('short_pause_control', .1), ('expired_queue', 1.2), ('continuous_control', 0.)]:
            topic = '/bb_lifespan_test_' + uuid.uuid4().hex + '/setpoint'
            node = rclpy.create_node('lifespan_reader_' + uuid.uuid4().hex[:8])
            samples = []
            def received(message, info):
                source_ns = int(getattr(info, 'source_timestamp', 0))
                samples.append({'token': message.pose.position.x,
                                'wall': time.monotonic(),
                                'dds_source_ns': source_ns,
                                'dds_age_s': (time.time_ns()-source_ns)*1e-9 if source_ns else None,
                                'ros_header_sec': message.header.stamp.sec})
            subscription = node.create_subscription(PoseStamped, topic, received, qos_profile_sensor_data)
            executor = SingleThreadedExecutor()
            executor.add_node(node)
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--writer', topic],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1)
            try:
                read_event(process, 'ready')
                process.stdin.write('fresh\n'); process.stdin.flush()
                deadline = time.monotonic()+3
                while not samples and time.monotonic() < deadline:
                    executor.spin_once(timeout_sec=.01)
                assert any(s['token'] == 1. for s in samples), 'fresh control sample did not arrive'
                samples.clear()
                if pause:
                    # Do not spin this executor until after the pause: this exposes
                    # data already buffered by DDS, not an application callback copy.
                    process.stdin.write('stop_after_publish\n'); process.stdin.flush()
                    written = read_event(process, 'stopping')
                    wait_stopped(process)
                    time.sleep(pause)
                    resumed = time.monotonic()
                    process.send_signal(signal.SIGCONT)
                    read_event(process, 'resumed')
                    deadline = time.monotonic()+.8
                    while time.monotonic() < deadline:
                        executor.spin_once(timeout_sec=.01)
                    row = {'case': kind, 'pause_wall_s': pause, 'written': written,
                           'sigcont_wall': resumed, 'samples_after_resume': samples,
                           'old_sample_delivered': any(s['token'] == 101. for s in samples)}
                else:
                    process.stdin.write('continuous\n'); process.stdin.flush()
                    deadline = time.monotonic()+1.5
                    while time.monotonic() < deadline:
                        executor.spin_once(timeout_sec=.01)
                    row = {'case': kind, 'samples': samples, 'received_count': len(samples)}
                rows.append(row)
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGCONT)
                    process.stdin.write('exit\n'); process.stdin.flush()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=3)
                process.stdin.close(); process.stdout.close()
                executor.remove_node(node); executor.shutdown()
                node.destroy_subscription(subscription); node.destroy_node()
        print(json.dumps({'rmw': 'rmw_fastrtps_cpp', 'reader': 'unchanged SensorDataQoS',
                          'writer_lifespan_s': .5, 'rows': rows}), flush=True)
        assert rows[0]['old_sample_delivered'], 'short-pause control must show the queue is usable'
        assert not rows[1]['old_sample_delivered'], 'expired sample delivered: writer-only lifespan is insufficient for this reader queue'
        assert rows[2]['received_count'] >= 10, 'continuous 30 Hz control not established'
    finally:
        rclpy.shutdown()


def writer(topic):
    assert topic.startswith('/bb_lifespan_test_') and topic.endswith('/setpoint')
    assert os.environ.get('ROS_DOMAIN_ID') == '90' and os.environ.get('ROS_LOCALHOST_ONLY') == '1'
    from test_safety import validate_environment
    validate_environment()
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from rclpy.duration import Duration
    from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy
    from rclpy.signals import SignalHandlerOptions
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('lifespan_writer_' + uuid.uuid4().hex[:8])
    qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                     reliability=ReliabilityPolicy.RELIABLE,
                     durability=DurabilityPolicy.VOLATILE, lifespan=Duration(seconds=.5))
    publisher = node.create_publisher(PoseStamped, topic, qos)
    deadline = time.monotonic()+10
    while publisher.get_subscription_count() != 1 and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=.02)
    assert publisher.get_subscription_count() == 1, 'no private SensorDataQoS reader'
    print(json.dumps({'kind': 'ready', 'pid': os.getpid()}), flush=True)
    def publish(token):
        message = PoseStamped()
        message.header.stamp.sec = 0  # intentionally fixed; DDS expiry is independent
        message.pose.position.x = token
        publisher.publish(message)
    try:
        for command in sys.stdin:
            command = command.strip()
            if command == 'fresh':
                publish(1.)
            elif command == 'stop_after_publish':
                publish(101.)
                print(json.dumps({'kind': 'stopping', 'wall': time.monotonic(), 'token': 101.}), flush=True)
                os.kill(os.getpid(), signal.SIGSTOP)
                print(json.dumps({'kind': 'resumed', 'wall': time.monotonic()}), flush=True)
            elif command == 'continuous':
                start = time.monotonic()
                for i in range(30):
                    publish(200.+i)
                    time.sleep(max(0., start+(i+1)/30-time.monotonic()))
            elif command == 'exit':
                break
            else:
                raise AssertionError('unexpected command')
    finally:
        node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == '--worker':
        worker()
    elif len(sys.argv) == 3 and sys.argv[1] == '--writer':
        writer(sys.argv[2])
    else:
        test_dds_lifespan_with_sensor_reader()
