"""Guards and private names for fake flight tests; never uses MAVLink."""
from pathlib import Path
import time
import uuid

TEST_NS='/bb_test_'+uuid.uuid4().hex[:12]

def validate_environment(markers=('/etc/bumblebee_version','/etc/bumblebee'),nodes=(),state_publishers=0):
    if any(Path(p).exists() for p in markers):
        raise RuntimeError('Flight tests refuse to run on a Bumblebee drone')
    if any(name in ('mavros','simple_offboard') for name,ns in nodes) or state_publishers:
        raise RuntimeError('Flight tests refuse a ROS domain with a live vehicle; choose an unused ROS_DOMAIN_ID')

def guard_graph(seconds=3):
    validate_environment()
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.signals import SignalHandlerOptions
    ctx=Context();rclpy.init(context=ctx,signal_handler_options=SignalHandlerOptions.NO)
    node=rclpy.create_node('flight_test_guard_'+uuid.uuid4().hex[:8],context=ctx)
    executor=SingleThreadedExecutor(context=ctx);executor.add_node(node)
    try:
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            executor.spin_once(timeout_sec=.1)
            validate_environment(nodes=node.get_node_names_and_namespaces(),state_publishers=node.count_publishers('/mavros/state'))
    finally:
        executor.remove_node(node);executor.shutdown();node.destroy_node();ctx.shutdown()

def topic(name):
    return TEST_NS+'/'+name.lstrip('/')
