"""Private ROS transport checks for all six types and consumer failure/resume; no MAVLink."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid

FILTER = Path(__file__).resolve().parents[1] / 'src/python/setpoint_freshness.py'


def cdr_padding_offsets(payload, message_type):
    """Alignment bytes of the observed little-endian CDR encoding, not ROS fields."""
    if payload[:4] != bytes.fromhex('00010000'):
        raise AssertionError('Unexpected CDR encoding in padding diagnostic')
    string_length = struct.unpack_from('<I', payload, 12)[0]
    offset = 16+string_length  # Header Time(8), string length(4), string incl. terminator
    padding = []
    def align(boundary):
        nonlocal offset
        next_offset = 4+((offset-4+boundary-1)//boundary)*boundary
        padding.extend(range(offset,next_offset))
        offset = next_offset
    if message_type == 'PositionTarget':
        offset += 1  # coordinate_frame, uint8
        align(2); offset += 2  # type_mask, uint16
        align(8)  # position starts with float64
    elif message_type == 'AttitudeTarget':
        offset += 1  # type_mask, uint8
        align(8)  # quaternion starts with float64
    elif message_type in ('PoseStamped', 'TwistStamped'):
        align(8)  # pose / linear vector starts with float64
    elif message_type == 'Thrust':
        align(4)  # thrust, float32
    else:
        raise AssertionError('Unknown message type')
    return padding


def payload_equal(expected, actual, message_type, decoder):
    # Compare every typed ROS field after CDR float32 canonicalization. Padding
    # is not a field, but message framing and length must still match exactly.
    return (len(expected) == len(actual) and expected[:4] == actual[:4] and
            decoder(expected,message_type) == decoder(actual,message_type))


def test_ros_filter_transport():
    env = dict(os.environ, ROS_DOMAIN_ID='91', ROS_LOCALHOST_ONLY='1',
               ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               FASTDDS_BUILTIN_TRANSPORTS='UDPv4', RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
    p = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker'],
                       env=env, capture_output=True, text=True, timeout=135)
    print(p.stdout)
    assert p.returncode == 0, p.stdout+p.stderr


def worker():
    assert os.environ.get('ROS_DOMAIN_ID') == '91' and os.environ.get('ROS_LOCALHOST_ONLY') == '1'
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.serialization import serialize_message, deserialize_message
    from rosidl_runtime_py.convert import message_to_ordereddict
    from geometry_msgs.msg import PoseStamped, TwistStamped
    from mavros_msgs.msg import PositionTarget, AttitudeTarget, Thrust
    from rosgraph_msgs.msg import Clock
    from test_safety import guard_graph
    guard_graph()
    spec = importlib.util.spec_from_file_location('filter_policy', FILTER)
    policy = importlib.util.module_from_spec(spec); spec.loader.exec_module(policy)
    types = dict(PoseStamped=PoseStamped, TwistStamped=TwistStamped, PositionTarget=PositionTarget,
                 AttitudeTarget=AttitudeTarget, Thrust=Thrust)
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = rclpy.create_node('freshness_transport_test_'+uuid.uuid4().hex[:8])
    namespace = '/bb_test_'+uuid.uuid4().hex[:12]
    private = namespace+'/setpoint_freshness_test'
    received = {key: [] for key, _, _, _ in policy.CHANNELS}
    data_lock = threading.Lock()
    # A forwarded private sentinel proves the worker processed a nonzero ROS
    # clock; graph discovery alone cannot order volatile /clock callbacks.
    startup_probe_frame = 'startup_clock_probe_'+uuid.uuid4().hex
    startup_probe_received = threading.Event()
    startup_probe_receipts = []
    publishers = {}
    output_remappings = []
    for key, typ, _, mavros_topic in policy.CHANNELS:
        publishers[key] = node.create_publisher(types[typ], private+'/input/'+key, 1)
        def callback_for(channel):
            def callback(message):
                if channel == 'position' and message.header.frame_id == startup_probe_frame:
                    # Exact sentinel isolation also excludes delayed warmups
                    # after readiness from every original payload/count check.
                    with data_lock:
                        startup_probe_receipts.append(dict(wall=time.monotonic(),
                            stamp_ns=message.header.stamp.sec*1000000000+message.header.stamp.nanosec))
                    startup_probe_received.set()
                    return
                with data_lock:
                    received[channel].append(bytes(serialize_message(message)))
            return callback
        # Exercise the candidate's exact six distinct MAVROS suffixes, in a
        # private namespace, so mixed-type aliases cannot hide in this test.
        output = namespace+mavros_topic
        node.create_subscription(types[typ], output, callback_for(key), qos_profile_sensor_data)
        output_remappings += ['-r', '~/output/'+key+':='+output]
    clock_publisher = node.create_publisher(Clock, '/clock', 1)
    wall_start = time.monotonic()
    def ros_ns():
        return int((10.+.2*(time.monotonic()-wall_start))*1e9)
    def clock_tick():
        msg = Clock(); ns = ros_ns()
        msg.clock.sec, msg.clock.nanosec = divmod(ns, 1000000000)
        clock_publisher.publish(msg)
    clock_timer = node.create_timer(.02, clock_tick)
    executor = SingleThreadedExecutor(); executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True); thread.start()
    process = subprocess.Popen([sys.executable, str(FILTER), '--ros-args', '-r', '__ns:='+namespace,
                                '-r', '__node:=setpoint_freshness_test', '-p', 'use_sim_time:=true',
                                *output_remappings],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    rows = []
    def wait_for(predicate, timeout, label):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError('filter exited: '+process.stdout.read())
            time.sleep(.01)
        assert predicate(), label
    def counts():
        with data_lock:
            return {k: len(v) for k, v in received.items()}
    def clear():
        with data_lock:
            for values in received.values():
                values.clear()
    def message(key, stamped):
        typ = next(typ for k,typ,_,_ in policy.CHANNELS if k == key)
        msg = types[typ](); msg.header.frame_id = 'keep_payload_'+key
        msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(stamped, 1000000000)
        if typ == 'PoseStamped':
            msg.pose.position.x = 1.25; msg.pose.position.y = -2.5; msg.pose.orientation.w = 1.
        elif typ == 'TwistStamped':
            msg.twist.linear.x = .7; msg.twist.angular.z = -.3
        elif typ == 'PositionTarget':
            msg.coordinate_frame = 1; msg.type_mask = 255; msg.position.z = 1.2; msg.yaw = .4
        elif typ == 'AttitudeTarget':
            msg.type_mask = 4; msg.orientation.w = 1.; msg.body_rate.z = .3; msg.thrust = .2
        else:
            msg.thrust = .33
        return msg
    def fresh_round():
        for key in publishers:
            publishers[key].publish(message(key, ros_ns()))
    try:
        wait_for(lambda: all(p.get_subscription_count() == 1 for p in publishers.values()), 20, 'six private inputs not connected')
        startup_last_probe = [None]
        def startup_clock_ready():
            if startup_probe_received.is_set():
                return True
            now = time.monotonic()
            if startup_last_probe[0] is None or now-startup_last_probe[0] >= .05:
                probe = message('position', ros_ns())
                probe.header.frame_id = startup_probe_frame
                publishers['position'].publish(probe)
                startup_last_probe[0] = now
            return startup_probe_received.is_set()
        wait_for(startup_clock_ready, 5, 'worker did not forward a fresh clock-readiness sentinel')
        with data_lock:
            startup_receipts = list(startup_probe_receipts)
        print(json.dumps({'case': 'worker_clock_readiness', 'sentinel_frame': startup_probe_frame,
                          'received': startup_receipts}), flush=True)
        expected = {}
        for key in publishers:
            msg = message(key, ros_ns()); expected[key] = bytes(serialize_message(msg))
            publishers[key].publish(msg)
        wait_for(lambda: all(counts()[k] == 1 for k in publishers), 5, 'fresh commands not delivered')
        with data_lock:
            snapshot = {key: list(values) for key, values in received.items()}
        diagnostics = []
        for key, wanted in expected.items():
            typ = next(typ for k,typ,_,_ in policy.CHANNELS if k == key)
            expected_msg = deserialize_message(wanted, types[typ])
            for actual in snapshot[key]:
                actual_msg = deserialize_message(actual, types[typ])
                diagnostics.append({
                    'channel': key, 'type': typ,
                    'expected_hex': wanted.hex(), 'received_hex': actual.hex(),
                    'expected_length': len(wanted), 'received_length': len(actual),
                    'byte_diff_offsets': [i for i,(a,b) in enumerate(zip(wanted,actual)) if a != b],
                    'expected_fields': message_to_ordereddict(expected_msg),
                    'received_fields': message_to_ordereddict(actual_msg),
                    'semantic_equal': expected_msg == actual_msg,
                    'schema_padding_offsets': cdr_padding_offsets(wanted, typ),
                })
        print(json.dumps({'case': 'payload_diagnostic', 'rows': diagnostics}), flush=True)
        assert all(len(snapshot[k]) == 1 and payload_equal(v, snapshot[k][0],
                   types[next(typ for key,typ,_,_ in policy.CHANNELS if key == k)], deserialize_message)
                   for k,v in expected.items()), 'decoded payload/header changed'
        assert all(set(row['byte_diff_offsets']).issubset(row['schema_padding_offsets'])
                   for row in diagnostics), 'byte differences outside proven CDR alignment padding'
        # Strict negative controls: changing any header or payload must fail the
        # equality criterion. Test real serialized ROS messages for every type.
        negative_controls = []
        for key, wanted in expected.items():
            typ = next(typ for k,typ,_,_ in policy.CHANNELS if k == key)
            for changed in ('header_stamp', 'header_frame_id', 'payload'):
                altered = deserialize_message(wanted, types[typ])
                if changed == 'header_stamp':
                    ns = altered.header.stamp.sec*1000000000+altered.header.stamp.nanosec+1
                    altered.header.stamp.sec, altered.header.stamp.nanosec = divmod(ns,1000000000)
                elif changed == 'header_frame_id':
                    altered.header.frame_id = 'X'+altered.header.frame_id[1:]  # same CDR length, different field
                elif typ == 'PoseStamped':
                    altered.pose.position.x += 1.
                elif typ == 'PositionTarget':
                    altered.position.z += 1.
                elif typ == 'AttitudeTarget':
                    altered.thrust += 1.
                elif typ == 'TwistStamped':
                    altered.twist.linear.x += 1.
                else:
                    altered.thrust += 1.
                assert not payload_equal(wanted, bytes(serialize_message(altered)), types[typ],
                                         deserialize_message), (key, changed, 'mutation not detected')
                negative_controls.append({'channel': key, 'changed': changed, 'rejected': True})
        print(json.dumps({'case': 'payload_negative_controls', 'rows': negative_controls}), flush=True)
        rows.append({'case': 'all_six_unchanged', 'counts': counts()})
        clear()
        for offset in (-700000000, 5000000000):
            for key in publishers:
                publishers[key].publish(message(key, ros_ns()+offset))
            time.sleep(.35)
            assert sum(counts().values()) == 0, ('stale/future leaked', offset, counts())
        for key in publishers:
            publishers[key].publish(message(key, 0))
        time.sleep(.2)
        assert sum(counts().values()) == 0, 'zero stamps leaked'
        rows.append({'case': 'stale_future_zero_dropped', 'counts': counts()})
        # Short process pause: current fresh data remains usable after recovery.
        process.send_signal(signal.SIGSTOP); time.sleep(.1); process.send_signal(signal.SIGCONT)
        fresh_round()
        wait_for(lambda: all(counts()[k] >= 1 for k in publishers), 5, 'short pause broke fresh traffic')
        rows.append({'case': 'short_pause_fresh_control', 'counts': counts()})
        time.sleep(.1); clear()
        # Paused consumer, old queued messages, advancing /clock at RTF=0.2.
        # At 1.2 wall s the sim age is only 0.24 s: the resume watermark must
        # reject them even though the ordinary age threshold would allow them.
        process.send_signal(signal.SIGSTOP)
        queued_stamp = ros_ns()
        for key in publishers:
            publishers[key].publish(message(key, queued_stamp))
        time.sleep(1.2)
        process.send_signal(signal.SIGCONT)
        time.sleep(.7)
        assert sum(counts().values()) == 0, ('queued input leaked after consumer resume', counts())
        rows.append({'case': 'consumer_resume_queue_dropped', 'counts': counts(), 'rtf': .2})
        # A late queued command can have a stamp newer than the latest queued
        # clock while both still look fresh. Recovery must require DDS clock
        # publication after actual resume detection, not merely DDS age<1 s.
        process.send_signal(signal.SIGSTOP)
        time.sleep(1.08)
        clock_timer.cancel()
        late_stamp = ros_ns()
        queued_clock = Clock()
        queued_clock.clock.sec, queued_clock.clock.nanosec = divmod(late_stamp-20000000, 1000000000)
        clock_publisher.publish(queued_clock)
        for key in publishers:
            publishers[key].publish(message(key, late_stamp))
        time.sleep(.12)
        process.send_signal(signal.SIGCONT)
        time.sleep(.3)
        assert sum(counts().values()) == 0, ('late queue leaked using pre-resume clock', counts())
        clock_timer.reset()
        time.sleep(.4)
        assert sum(counts().values()) == 0, ('late queue leaked after new clock recovery', counts())
        rows.append({'case': 'late_queue_recent_pre_resume_clock_dropped', 'counts': counts(), 'rtf': .2})
        # Separate publisher control after recovery; no old data is altered/replayed.
        for _ in range(30):
            fresh_round(); time.sleep(1/30)
        wait_for(lambda: all(counts()[k] >= 10 for k in publishers), 5, '30 Hz fresh control lost')
        rows.append({'case': 'fresh_30hz_after_resume', 'counts': counts()})
        # Filter failure must end every output, without generating ARM/MODE.
        process.kill(); process.wait(timeout=5)
        time.sleep(.2); clear()
        for _ in range(15):
            fresh_round(); time.sleep(1/30)
        assert sum(counts().values()) == 0, ('failed filter still outputs', counts())
        rows.append({'case': 'filter_failure_ends_stream', 'counts': counts()})
        print(json.dumps({'pass': True, 'rows': rows, 'private_namespace': namespace}), flush=True)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGCONT); process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        print(process.stdout.read()); process.stdout.close()
        executor.shutdown(); thread.join(timeout=5); node.destroy_node(); rclpy.shutdown()


if __name__ == '__main__':
    worker() if '--worker' in sys.argv else test_ros_filter_transport()
