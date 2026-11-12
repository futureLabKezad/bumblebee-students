#!/usr/bin/env python3
"""Reject stale/future flight commands before unchanged MAVROS; no ARM/MODE clients."""
import time
from functools import partial

MAX_AGE_NS = 500000000
MAX_FUTURE_NS = 100000000
WALL_RESUME_NS = 1000000000
CHANNELS = (
    ('position', 'PoseStamped', '/mavros/setpoint_position/local', '/mavros/setpoint_position/local'),
    ('position_raw', 'PositionTarget', '/mavros/setpoint_raw/local', '/mavros/setpoint_raw/local'),
    ('attitude', 'PoseStamped', '/mavros/setpoint_attitude/attitude', '/mavros/setpoint_attitude/attitude'),
    ('attitude_raw', 'AttitudeTarget', '/mavros/setpoint_raw/attitude', '/mavros/setpoint_raw/attitude'),
    ('rates', 'TwistStamped', '/mavros/setpoint_attitude/cmd_vel', '/mavros/setpoint_attitude/cmd_vel'),
    ('thrust', 'Thrust', '/mavros/setpoint_attitude/thrust', '/mavros/setpoint_attitude/thrust'),
)


def stamp_ns(stamp):
    if not (0 <= stamp.nanosec < 1000000000):
        return None
    return stamp.sec*1000000000 + stamp.nanosec


def dds_source_timestamp(info):
    # Jazzy rclpy returns a dict, not an object with source_timestamp attributes.
    value = info.get('source_timestamp', 0) if isinstance(info, dict) else getattr(info, 'source_timestamp', 0)
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def command_rejection(now_ns, stamped_ns, resume_floor_ns=0):
    if now_ns <= 0:
        return 'clock_unknown'
    if stamped_ns is None or stamped_ns <= 0:
        return 'stamp_unknown'
    if resume_floor_ns and stamped_ns <= resume_floor_ns:
        return 'queued_before_filter_resume'
    age = now_ns-stamped_ns
    if age > MAX_AGE_NS:
        return 'stale'
    if age < -MAX_FUTURE_NS:
        return 'future'
    return None


class ClockResumeGuard:
    """Pure wall-dispatch guard; after a sim-time process stall require a live clock.

    A received /clock must be written recently in DDS wall time, received after
    the detected stall, and reflected by the Node ROS clock before forwarding.
    A stamp watermark rejects all pre-recovery queued inputs, even when their
    sim age is still <0.5 s at a low RTF. Live wall ticks with paused /clock do
    not create a resume gate. No control command is issued by this guard.
    """
    def __init__(self):
        self.last_wall_ns = None
        self.need_clock = False
        self.resume_detected_wall_ns = 0
        self.resume_detected_system_ns = 0
        self.clock_candidate_ns = None
        self.resume_floor_ns = 0

    def observe(self, wall_ns, ros_ns, use_sim_time, system_wall_ns=None):
        if self.last_wall_ns is not None and (wall_ns < self.last_wall_ns or
                                               wall_ns-self.last_wall_ns > WALL_RESUME_NS):
            if use_sim_time:
                self.need_clock = True
                self.resume_detected_wall_ns = wall_ns
                # DDS source timestamps use system time, not monotonic time.
                # Never recover from a recently written /clock queued before
                # the process actually resumed. Unknown system time fails closed.
                self.resume_detected_system_ns = system_wall_ns or 0
                self.clock_candidate_ns = None
        self.last_wall_ns = wall_ns
        if self.need_clock:
            if self.clock_candidate_ns is None or ros_ns < self.clock_candidate_ns:
                return 'clock_after_resume_required'
            self.resume_floor_ns = self.clock_candidate_ns
            self.need_clock = False
        return None

    def receive_clock(self, clock_ns, received_wall_ns, dds_source_wall_ns, system_wall_ns):
        if not self.need_clock or received_wall_ns < self.resume_detected_wall_ns or clock_ns <= 0:
            return False
        if dds_source_wall_ns <= 0:
            return False
        if self.resume_detected_system_ns <= 0 or dds_source_wall_ns < self.resume_detected_system_ns:
            return False
        age = system_wall_ns-dds_source_wall_ns
        if age > WALL_RESUME_NS or age < -MAX_FUTURE_NS:
            return False
        self.clock_candidate_ns = clock_ns
        return True


def create_filter():
    import rclpy
    from rclpy.node import Node
    from rclpy.clock import Clock
    from rclpy.clock_type import ClockType
    from rclpy.duration import Duration
    from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy, DurabilityPolicy, qos_profile_sensor_data
    from geometry_msgs.msg import PoseStamped, TwistStamped
    from mavros_msgs.msg import PositionTarget, AttitudeTarget, Thrust
    from rosgraph_msgs.msg import Clock as ClockMessage
    message_types = dict(PoseStamped=PoseStamped, TwistStamped=TwistStamped,
                         PositionTarget=PositionTarget, AttitudeTarget=AttitudeTarget, Thrust=Thrust)

    class SetpointFreshness(Node):
        def __init__(self):
            super().__init__('setpoint_freshness')
            self.guard = ClockResumeGuard()
            self.accepted = {key: 0 for key, _, _, _ in CHANNELS}
            self.rejected = {}
            self.last_warn_wall = 0
            # Compatible with SensorDataQoS position/raw and RELIABLE attitude readers.
            output_qos = QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=1,
                                    reliability=ReliabilityPolicy.RELIABLE,
                                    durability=DurabilityPolicy.VOLATILE, lifespan=Duration(seconds=.5))
            self.outputs = {key: self.create_publisher(message_types[typ], '~/output/'+key, output_qos)
                            for key, typ, _, _ in CHANNELS}
            self.inputs = [self.create_subscription(message_types[typ], '~/input/'+key,
                                                    partial(self.forward, key),
                                                    qos_profile_sensor_data)
                           for key, typ, _, _ in CHANNELS]
            self.clock_input = self.create_subscription(ClockMessage, '/clock', self.receive_clock,
                                                        qos_profile_sensor_data)
            self.wall_clock = Clock(clock_type=ClockType.STEADY_TIME)
            self.timer = self.create_timer(.05, self.tick, clock=self.wall_clock)
            self.get_logger().info('Flight-command filter active: age<=0.5 ROS s, future<=0.1 ROS s; no ARM/MODE clients')

        def uses_sim_time(self):
            return bool(self.get_parameter('use_sim_time').value)

        def observe(self):
            return self.guard.observe(time.monotonic_ns(), self.get_clock().now().nanoseconds,
                                      self.uses_sim_time(), time.time_ns())

        def tick(self):
            self.observe()

        def receive_clock(self, msg, info):
            self.observe()  # detect a stall even when /clock is the first callback after SIGCONT
            source_wall_ns = dds_source_timestamp(info)
            system_wall_ns = time.time_ns()
            if self.guard.receive_clock(stamp_ns(msg.clock) or 0, time.monotonic_ns(),
                                        source_wall_ns, system_wall_ns):
                self.get_logger().info('Post-pause /clock accepted: DDS age=%.3f wall s' %
                                       ((system_wall_ns-source_wall_ns)*1e-9))

        def forward(self, key, message):
            reason = self.observe()
            if reason is None:
                reason = command_rejection(self.get_clock().now().nanoseconds,
                                           stamp_ns(message.header.stamp), self.guard.resume_floor_ns)
            if reason is not None:
                self.rejected[reason] = self.rejected.get(reason, 0)+1
                wall = time.monotonic_ns()
                if wall-self.last_warn_wall > 2000000000:
                    self.last_warn_wall = wall
                    self.get_logger().warning('Dropped %s command: %s' % (key, reason))
                return
            self.outputs[key].publish(message)  # preserve every field and the original header
            self.accepted[key] += 1

    return SetpointFreshness()


def main():
    import rclpy
    rclpy.init()
    node = create_filter()
    try:
        rclpy.spin(node)  # single executor: guard state never crosses callback threads
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
