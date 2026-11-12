#!/usr/bin/env python3
"""make_r2g.py - r2 revision g = r2f + one fix S4 (owner 10.11.2026 «да», task T39 of chat 1).

S4 (review of r2f): the vision watchdog started only at the first vpe_fix pose. If vpe_fix never published, it stayed
off for the whole flight (takeoff only warned); r2e had armed it at the first raw marker frame.
Fix: "no vision" is counted from the arm when no vpe_fix pose has come yet. The arm = the first /mavros/state that
drone.py sees armed (connected) in this flight; cleared on the disarm edge like the other per-flight state. Same
limits as before (takeoff 25 s, fly_to/move 6 s, safe_land 3 s); with poses everything is as in r2f.
Why the arm and not the takeoff call: the watchdog acts only while armed; the arm edge is already tracked in
_on_fcu_state (disarm edge) and covers every way of arming (auto_arm, pilot, a script started on an armed vehicle),
while takeoff() is not called before every navigate_wait; the takeoff limit (25 s) was sized for "arming + a slow
climb" (T30: vision gaps near the floor at spin-up), so counting from the arm keeps its meaning.
Not changed: drone.vision_pose_age() (the scripts' "vision present", hover r5), the pose callback, limits, scripts.
Usage: python3 -I make_r2g.py R2G_DIR   (the files there must be r2f's)
"""
import hashlib
import os
import sys

R2F = {
    'src/bumblebee/examples/drone.py': '94f9dfee2f6114c0',
}

DRONE = [
    ("""_vpe_pose_last = None   # (x, y, z, qx, qy, qz, qw) of that pose; vpe_fix repeats it for up to 0.5 s, a repeat does not count
""",
     """_vpe_pose_last = None   # (x, y, z, qx, qy, qz, qw) of that pose; vpe_fix repeats it for up to 0.5 s, a repeat does not count
# r2g (S4): time.monotonic() when drone.py first saw this flight armed (/mavros/state); cleared on the disarm edge.
# Until the first vpe_fix pose, the watchdogs count "no vision" from it.
_vision_arm_t = None
""", 1),
    ("""    global _fcu_state_msg, _fcu_state_time, _arm_ref_z, _own_auto_land, _auto_arm_ok_t
    prev = _fcu_state_msg
""",
     """    global _fcu_state_msg, _fcu_state_time, _arm_ref_z, _own_auto_land, _auto_arm_ok_t
    global _vision_arm_t
    prev = _fcu_state_msg
""", 1),
    ("""        _arm_ref_z = None
        _own_auto_land = False
        _auto_arm_ok_t = None
""",
     """        _arm_ref_z = None
        _own_auto_land = False
        _auto_arm_ok_t = None
        _vision_arm_t = None   # r2g (S4)
    # r2g (S4): the first armed State of this flight starts the no-vision count (until the first vpe_fix pose)
    if msg.connected and msg.armed and _vision_arm_t is None:
        _vision_arm_t = time.monotonic()
""", 1),
    ("""    if _vpe_pose_time is None:
        return float('inf')
    return time.monotonic() - _vpe_pose_time
""",
     """    if _vpe_pose_time is None:
        return float('inf')
    return time.monotonic() - _vpe_pose_time


def _vision_silence_age():
    \"\"\"r2g (S4): seconds without vision for the flight watchdogs (navigate_wait, safe_land).

    Since the last new vpe_fix pose; if none has come yet, since drone.py saw this flight armed. None while
    neither is known (disarmed and no pose yet): no watchdog. vision_pose_age() is unchanged.
    \"\"\"
    if _vpe_pose_time is not None:
        return time.monotonic() - _vpe_pose_time
    if _vision_arm_t is not None:
        return time.monotonic() - _vision_arm_t
    return None
""", 1),
    ("""        # vpe_fix rejected (false detections) no longer extend it. Active from the first vpe_fix pose.
        if t.armed and _vpe_pose_time is not None \\
                and vision_pose_age() > vision_timeout:
            _vision_abort = True
            _node.get_logger().error(
                'Vision lost for %.1fs (no new vpe_fix pose, limit %.1fs) -- EKF '
                'is coasting, landing'
                % (vision_pose_age(), vision_timeout))
""",
     """        # vpe_fix rejected (false detections) no longer extend it.
        # r2g (S4): with no vpe_fix pose yet, "no vision" counts from the arm (_vision_silence_age()).
        silence = _vision_silence_age()
        if t.armed and silence is not None and silence > vision_timeout:
            _vision_abort = True
            _node.get_logger().error(
                'Vision lost for %.1fs (no new vpe_fix pose%s, limit %.1fs) -- EKF '
                'is coasting, landing'
                % (silence, '' if _vpe_pose_time is not None else ' since the arm', vision_timeout))
""", 1),
    ("""    if _vpe_pose_time is None:
        # r2f (T35): the vision watchdog starts at the first vpe_fix pose; say so instead of staying silent
        _node.get_logger().warn('takeoff: no vpe_fix pose seen yet -- vision watchdog inactive until the first one')
""",
     """    if _vpe_pose_time is None:
        # r2g (S4): no pose yet -- the watchdog counts from the arm and lands after vision_timeout without one
        _node.get_logger().warn('takeoff: no vpe_fix pose seen yet -- landing if none arrives within %.1fs of the arm'
                                % vision_timeout)
""", 1),
    ("""    if x is not None and (_vision_abort or
                          (_vpe_pose_time is not None
                           and vision_pose_age() > 3.0)):
""",
     """    # r2g (S4): with no pose yet, counted from the arm
    silence = _vision_silence_age()
    if x is not None and (_vision_abort or
                          (silence is not None and silence > 3.0)):
""", 1),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    root = sys.argv[1]
    for rel in R2F:
        h = sha(open(os.path.join(root, rel), 'rb').read())
        if not h.startswith(R2F[rel]):
            sys.exit('STOP: %s is not r2f (%s)' % (rel, h[:16]))
    rel = 'src/bumblebee/examples/drone.py'
    path = os.path.join(root, rel)
    t = open(path, 'rb').read().decode('utf-8')
    for old, new, n in DRONE:
        if t.count(old) != n:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
        t = t.replace(old, new)
    out = t.encode('utf-8')
    open(path, 'wb').write(out)
    print('r2g %s %s' % (rel, sha(out)))


if __name__ == '__main__':
    main()
