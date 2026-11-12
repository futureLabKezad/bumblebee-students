#!/usr/bin/env python3
"""make_r2f.py - r2 revision f = r2e + exactly two fixes (owner 10.11.2026 ~09:15, card T35/T34, variant 1).

Draft: /work/t35_image_findings_20261110/drafts/R2F_DRAFT.md (edition 2, after the T35 review).
T35: the vision watchdogs counted raw /aruco_detect/markers_used frames, including false detections that vpe_fix
  rejected, so each false frame postponed the vision-loss landing by up to 6 s (Gazebo: 11 and 18 s instead of <=7 s).
  Fix: "vision present" = a NEW pose that vpe_fix actually published on /mavros/mavros/pose_cov (a repeat of the
  same pose, which vpe_fix sends for up to 0.5 s, does not count). Public drone.vision_pose_age().
  Places: drone.navigate_wait watchdog, drone.safe_land precision-approach check, flight.py hover watchdog,
  flight_marker.py hover_vw, flight_marker_loop.py hover. Not changed: preflight gates on the ground (raw counts),
  wait_quorum, notify_manager LEDs.
T34: simple_offboard.handleState() clears nav_from_sp_flag_ for every State not yet in OFFBOARD, so the first
  navigate after an auto_arm takeoff could start from local_position_ instead of the setpoint (setpoint ~0.1 m lower).
  Fix: set nav_from_sp_flag_ again after a successful offboardAndArm() of a navigate request.
Package test test_drone_flight_guards.py: the 6 places that trip the vision watchdog now set _vpe_pose_time.
Usage: python3 -I make_r2f.py R2F_DIR   (the files there must be r2e's)
"""
import hashlib
import os
import sys

R2E = {
    'src/bumblebee/examples/drone.py': '855f4cc4ad511a59',
    'src/bumblebee/examples/flight/flight.py': 'f6886aa7622d1184',
    'src/bumblebee/examples/flight/flight_marker.py': '76e4ea4f09f09441',
    'src/bumblebee/examples/flight/flight_marker_loop.py': '805486e087d670b8',
    'src/bumblebee/src/cpp/simple_offboard.cpp': '75bf193be38acaf6',
    'src/bumblebee/test/test_drone_flight_guards.py': '7fc0b121c8ac9f55',
}

DRONE = [
    ("""_aruco_markers_pos_time  = None
""",
     """_aruco_markers_pos_time  = None
# r2f (T35): vision watchdogs count only NEW poses vpe_fix actually published on /mavros/mavros/pose_cov.
# Raw markers_used frames that vpe_fix rejected (false detections) no longer extend vision.
_vpe_pose_time = None   # time.monotonic() of the last NEW vpe_fix pose
_vpe_pose_last = None   # (x, y, z, qx, qy, qz, qw) of that pose; vpe_fix repeats it for up to 0.5 s, a repeat does not count
""", 1),
    ("""    _node.create_subscription(Bool,  '/aruco_detect/yaw_locked',   _on_yaw_locked,   10)
""",
     """    _node.create_subscription(Bool,  '/aruco_detect/yaw_locked',   _on_yaw_locked,   10)

    # r2f (T35): new poses vpe_fix published (vision_pose_age()). BEST_EFFORT like require_vpe_link.
    from geometry_msgs.msg import PoseWithCovarianceStamped as _PWCS_vpe
    _vpe_qos = QoSProfile(
        depth=10,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE)
    _node.create_subscription(_PWCS_vpe, '/mavros/mavros/pose_cov', _on_vpe_pose, _vpe_qos)
""", 1),
    ("""def _markers_pos_age():
    \"\"\"Seconds since aruco_detect last reported >=1 usable marker; +inf if never.\"\"\"
    if _aruco_markers_pos_time is None:
        return float('inf')
    return time.monotonic() - _aruco_markers_pos_time
""",
     """def _markers_pos_age():
    \"\"\"Seconds since aruco_detect last reported >=1 usable marker; +inf if never.\"\"\"
    if _aruco_markers_pos_time is None:
        return float('inf')
    return time.monotonic() - _aruco_markers_pos_time


def _on_vpe_pose(msg):
    \"\"\"r2f (T35): /mavros/mavros/pose_cov callback; only a pose different from the last one counts.\"\"\"
    global _vpe_pose_time, _vpe_pose_last
    p, o = msg.pose.pose.position, msg.pose.pose.orientation
    key = (p.x, p.y, p.z, o.x, o.y, o.z, o.w)
    if key != _vpe_pose_last:
        _vpe_pose_last = key
        _vpe_pose_time = time.monotonic()


def vision_pose_age():
    \"\"\"Seconds since vpe_fix last published a NEW vision pose on /mavros/mavros/pose_cov; +inf if never.

    r2f (T35): this is "vision present" for the flight watchdogs (navigate_wait, safe_land, the example scripts).
    Raw /aruco_detect/markers_used frames do not count: vpe_fix rejects false detections, this age does not see
    them. A repeat of the same pose (vpe_fix repeats the last accepted pose for up to 0.5 s) does not count.
    \"\"\"
    if _vpe_pose_time is None:
        return float('inf')
    return time.monotonic() - _vpe_pose_time
""", 1),
    ("""        if t.armed and _aruco_markers_pos_time is not None \\
                and _markers_pos_age() > vision_timeout:
            _vision_abort = True
            _node.get_logger().error(
                'Vision lost for %.1fs (markers_used=0, limit %.1fs) -- EKF '
                'is coasting, landing'
                % (_markers_pos_age(), vision_timeout))
""",
     """        # r2f (T35): vision = a NEW pose vpe_fix published (vision_pose_age()); raw markers_used frames that
        # vpe_fix rejected (false detections) no longer extend it. Active from the first vpe_fix pose.
        if t.armed and _vpe_pose_time is not None \\
                and vision_pose_age() > vision_timeout:
            _vision_abort = True
            _node.get_logger().error(
                'Vision lost for %.1fs (no new vpe_fix pose, limit %.1fs) -- EKF '
                'is coasting, landing'
                % (vision_pose_age(), vision_timeout))
""", 1),
    ("""    print('=== TAKEOFF to %.1fm ===' % height)
""",
     """    if _vpe_pose_time is None:
        # r2f (T35): the vision watchdog starts at the first vpe_fix pose; say so instead of staying silent
        _node.get_logger().warn('takeoff: no vpe_fix pose seen yet -- vision watchdog inactive until the first one')
    print('=== TAKEOFF to %.1fm ===' % height)
""", 1),
    ("""    if x is not None and (_vision_abort or
                          (_aruco_markers_pos_time is not None
                           and _markers_pos_age() > 3.0)):
""",
     """    # r2f (T35): "silent" = no new vpe_fix pose for >3 s (raw detector frames no longer count)
    if x is not None and (_vision_abort or
                          (_vpe_pose_time is not None
                           and vision_pose_age() > 3.0)):
""", 1),
]

FLIGHT = [
    ("""        m_age = drone._markers_used_age()
        if drone._aruco_markers_used == 0 or m_age > 1.0:
""",
     """        # r2f (T35): silent = no NEW vpe_fix pose for >1 s (raw detector frames no longer count)
        if drone.vision_pose_age() > 1.0:
""", 1),
]

MARKER = [
    ("""    Returns False if /aruco_detect/markers_used stayed at 0 (or stale >1s)
    for longer than silent_limit -- caller should abort the mission and
""",
     """    Returns False if vpe_fix published no NEW pose (drone.vision_pose_age() > 1 s, r2f)
    for longer than silent_limit -- caller should abort the mission and
""", 1),
    ("""        if drone._aruco_markers_used == 0 or drone._markers_used_age() > 1.0:
""",
     """        if drone.vision_pose_age() > 1.0:   # r2f (T35): new vpe_fix poses only
""", 1),
]

LOOP = [
    ("""            if drone._aruco_markers_used == 0 or drone._markers_used_age() > 1.0:
""",
     """            if drone.vision_pose_age() > 1.0:   # r2f (T35): new vpe_fix poses only
""", 1),
]

SO = [
    ("""                if (setpoint_type_ == NONE)
                    throw std::runtime_error("Setpoint stream stopped while arming, not flying");
                arm_complete_ns_ = monotonicNs();
""",
     """                if (setpoint_type_ == NONE)
                    throw std::runtime_error("Setpoint stream stopped while arming, not flying");
                arm_complete_ns_ = monotonicNs();
                // r2f (T34): handleState() cleared nav_from_sp_flag_ on every State not yet in OFFBOARD
                // while arming; set it again so the next navigate starts from the setpoint
                if (setpoint_type_ == NAVIGATE || setpoint_type_ == NAVIGATE_GLOBAL) nav_from_sp_flag_ = true;
""", 1),
]

GUARDS = [
    ("d._aruco_markers_pos_time = self.clock.now - ", "d._vpe_pose_time = self.clock.now - ", 6),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def patch(root, rel, edits):
    path = os.path.join(root, rel)
    data = open(path, 'rb').read()
    if not sha(data).startswith(R2E[rel]):
        sys.exit('STOP: %s is not r2e (%s)' % (rel, sha(data)[:16]))
    t = data.decode('utf-8')
    for old, new, n in edits:
        if t.count(old) != n:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
        t = t.replace(old, new)
    out = t.encode('utf-8')
    open(path, 'wb').write(out)
    print('r2f %s %s' % (rel, sha(out)))


def main():
    root = sys.argv[1]
    for rel in R2E:   # all inputs checked before the first write
        h = sha(open(os.path.join(root, rel), 'rb').read())
        if not h.startswith(R2E[rel]):
            sys.exit('STOP: %s is not r2e (%s)' % (rel, h[:16]))
    patch(root, 'src/bumblebee/examples/drone.py', DRONE)
    patch(root, 'src/bumblebee/examples/flight/flight.py', FLIGHT)
    patch(root, 'src/bumblebee/examples/flight/flight_marker.py', MARKER)
    patch(root, 'src/bumblebee/examples/flight/flight_marker_loop.py', LOOP)
    patch(root, 'src/bumblebee/src/cpp/simple_offboard.cpp', SO)
    patch(root, 'src/bumblebee/test/test_drone_flight_guards.py', GUARDS)


if __name__ == '__main__':
    main()
