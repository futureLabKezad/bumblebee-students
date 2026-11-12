"""r2f T35 with real ROS: the real drone.py (r2f) subscribes to /mavros/mavros/pose_cov and vision_pose_age() follows
NEW poses from a publisher with vpe_fix's QoS (create_publisher(..., 1) = RELIABLE, VOLATILE, depth 1).
A raw /aruco_detect/markers_used = 1 stream alone does not move vision_pose_age(). No FCU, no flight command:
drone._init() only. Localhost only, every name under the private /bb_test_* namespace (guard_graph()).
Run (jazzy + ws_sitl + mavros bp02 + r2f install sourced, ROS_DOMAIN_ID set): python3 test/test_r2f_vpe_sub_ros.py
"""
import importlib.util
import math
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'src/bumblebee/test'))
SDK = ROOT / 'src/bumblebee/examples/drone.py'


def main():
    from test_safety import TEST_NS, topic, guard_graph
    guard_graph()
    names = ['/get_telemetry', '/navigate', '/land', '/mavros/mavros/arming', '/mavros/set_mode',
             '/vpe_fix/set_param', '/mavros/mavros/pull', '/mavros/mavros/get_parameters',
             '/aruco_detect/markers_used', '/aruco_detect/yaw_locked', '/aruco_detect/wake', '/mavros/state',
             '/mavros/battery', '/mavros/mavros/pose_cov', '/tf', '/tf_static', '/clock']
    sys.argv[1:] = ['--ros-args', '-r', '__ns:=' + TEST_NS]
    for n in names:
        sys.argv += ['-r', n + ':=' + topic(n)]
    spec = importlib.util.spec_from_file_location('r2f_sdk', SDK)
    drone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drone)
    drone._init()
    import rclpy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from std_msgs.msg import Int32
    pub_node = rclpy.create_node('r2f_vpe_pub', namespace=TEST_NS)
    pose_pub = pub_node.create_publisher(PoseWithCovarianceStamped, topic('/mavros/mavros/pose_cov'), 1)
    mu_pub = pub_node.create_publisher(Int32, topic('/aruco_detect/markers_used'), 10)

    def pose(x):
        m = PoseWithCovarianceStamped()
        m.header.frame_id = 'map'
        m.pose.pose.position.x, m.pose.pose.position.z, m.pose.pose.orientation.w = x, 1.0, 1.0
        return m

    def wait_match(pub):
        end = time.monotonic() + 10.
        while pub.get_subscription_count() < 1:
            assert time.monotonic() < end, 'no subscriber on ' + pub.topic_name
            time.sleep(.05)

    try:
        wait_match(pose_pub)
        wait_match(mu_pub)
        assert drone.vision_pose_age() == math.inf
        # 1) raw markers_used = 1 at 6 Hz for 2 s, no pose: vision_pose_age stays +inf
        for _ in range(12):
            mu_pub.publish(Int32(data=1))
            time.sleep(1 / 6)
        assert drone._aruco_markers_used == 1, drone._aruco_markers_used   # the raw stream did arrive
        assert drone.vision_pose_age() == math.inf, drone.vision_pose_age()
        # 2) new poses at 30 Hz for 1 s: age stays small
        for i in range(30):
            pose_pub.publish(pose(0.001 * i))
            time.sleep(1 / 30)
        age_new = drone.vision_pose_age()
        assert age_new < 0.2, age_new
        # 3) the same pose repeated for 1 s (vpe_fix's 0.5 s repeat, longer): age grows
        same = pose(0.5)
        pose_pub.publish(same)
        time.sleep(0.2)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 1.0:
            pose_pub.publish(same)
            time.sleep(1 / 30)
        age_rep = drone.vision_pose_age()
        assert age_rep > 1.0, age_rep
        print('R2F_VPE_SUB_ROS_PASS age_after_new=%.3f age_after_1s_repeats=%.3f' % (age_new, age_rep))
    finally:
        pub_node.destroy_node()
        drone._shutdown()


if __name__ == '__main__':
    main()
