#!/usr/bin/env python3
"""make_r2h.py - r2h CANDIDATE = r2g + three changes (task T43 of chat 1, 10.11.2026). Not handed out, not for the
drone: only for the Simulator's control runs (not counted). Onto the drone only after the owner's «да».

vpe_fix.py
  B1  the VPE gate: one marker is "fresh" when /aruco_detect/markers_used was >= 1 within the last 1.5 s
      (_QUALITY_SINGLE_TIMEOUT, unchanged) and yaw is locked -- not "the LAST markers_used message is >= 1".
      The gate is re-evaluated on every markers_used message and on every change of yaw_locked, not only at the
      1 Hz tick (which stays as a backstop). T42: near the floor the detector blinks (an empty frame publishes
      markers_used 0), so the 1 Hz check closed the gate for whole seconds (1-7 s) although a marker was seen
      0.1 s earlier; every pause > 0.4 s made PX4 reset the EKF xy onto ONE vision sample.
  B2  re-entry after a pause: when vpe_fix has not published for > 0.3 s (_REENTRY_GAP; PX4 stops EV fusion after
      0.4 s), it publishes again only once 3 accepted poses not older than _POSE_TIMEOUT are at hand (or, with a
      slow detector, once the oldest fresh pose is 0.3 s old: review M1), and for the first 0.5 s (_REENTRY_HOLD)
      it publishes the medoid of the fresh poses at hand (an actual sample, orientation included), then the
      latest pose as before. A reseed restarts the pose history (review S2). PX4 resets onto the 2nd sample after a pause; the medoid removes the single-frame
      noise part of that reset (T42: ~0.035 m of the ~0.11 m resets). Why B2 too: raw detection near the floor
      is absent for 0.7-1.4 s at a time (aruco SEARCHING spans), longer than _POSE_TIMEOUT + 0.4 s, so pauses
      and resets remain at low height even with B1.
drone.py
  W   navigate_wait waits 0.5 s per loop as before, but looks at the vision watchdog every 0.1 s and ends the wait
      as soon as the silence passes vision_timeout; the loop then runs its checks in their order (disarm, pilot,
      vision...). The silence is measured on simple_offboard's hold clock (the ROS clock under use_sim_time, else
      monotonic), like _hold_now(). Limits unchanged (6.0 s fly_to/move, 25 s takeoff, 3 s safe_land).
      vision_pose_age() (the scripts' signal) is unchanged: it stays on time.monotonic().
Not changed: limits, constants of the gate (1.0 / 1.5 / 0.5 s), P1 state logic, the pose guards, scripts.
Usage: python3 -I make_r2h.py R2H_DIR   (the files there must be r2g's)
"""
import hashlib
import os
import sys

R2G = {
    'src/bumblebee/examples/drone.py': '068e6eb44ab01ad8',
    'src/bumblebee/src/python/vpe_fix.py': '3b8a93d4d0898369',
}

VPE = [
    # constants
    ("""_GATE_HYSTERESIS = 0.5
""",
     """_GATE_HYSTERESIS = 0.5

# r2h (B2): re-entry after a publish pause. PX4 EKF2 stops EV fusion after 0.4 s without a sample and on the
# return resets its xy onto ONE sample (ev_pos_control.cpp startEvPosFusion); the first samples after a pause are
# the medoid of the last _REENTRY_N accepted poses (none older than _POSE_TIMEOUT), for _REENTRY_HOLD seconds.
_REENTRY_GAP  = 0.3
_REENTRY_N    = 3
_REENTRY_HOLD = 0.5
# review M1: a slow detector (e.g. ~6 Hz, or empty frames) may not give _REENTRY_N poses within _POSE_TIMEOUT; then
# the wait ends once the oldest fresh pose is _REENTRY_MAX_WAIT old and the medoid is taken of the poses at hand.
_REENTRY_MAX_WAIT = 0.3
""", 1),
    # state in __init__
    ("""        self.markers_used = 0
        self.markers_used_time = None
        self.markers_used_multi_time = None
        self.yaw_locked = False
""",
     """        self.markers_used = 0
        self.markers_used_time = None
        self.markers_used_multi_time = None
        # r2h (B1): last time markers_used was >= 1 (an empty frame publishes 0 and must not end "fresh")
        self.markers_pos_time = None
        self.yaw_locked = False
        # r2h (B2): accepted poses (receipt time, pose) and the re-entry state after a publish pause
        self._recent_poses = deque(maxlen=_REENTRY_N)
        self._last_publish_time = None
        self._reentry_wait = False
        self._reentry_until = None
""", 1),
    # B1 freshness
    ("""    def _single_marker_fresh(self):
        if self.markers_used_time is None or not self.yaw_locked or self.markers_used < 1:
            return False
        age = (self.get_clock().now() - self.markers_used_time).nanoseconds / 1e9
        return age <= _QUALITY_SINGLE_TIMEOUT
""",
     """    def _single_marker_fresh(self):
        # r2h (B1): >= 1 marker within the last _QUALITY_SINGLE_TIMEOUT, not "the last message was >= 1"
        if self.markers_pos_time is None or not self.yaw_locked:
            return False
        age = (self.get_clock().now() - self.markers_pos_time).nanoseconds / 1e9
        return age <= _QUALITY_SINGLE_TIMEOUT
""", 1),
    # B2: remember accepted poses
    ("""        self.last_pose = msg.pose.pose
        self.last_pose_time = now
        self._consec_rejects = 0
""",
     """        self.last_pose = msg.pose.pose
        self.last_pose_time = now
        self._recent_poses.append((now, msg.pose.pose))   # r2h (B2)
        self._consec_rejects = 0
""", 1),
    # B1 every message
    ("""    def markers_used_callback(self, msg):
        self.markers_used = int(msg.data)
        self.markers_used_time = self.get_clock().now()
        if self.markers_used >= 2:
            self.markers_used_multi_time = self.markers_used_time

    def yaw_locked_callback(self, msg):
        self.yaw_locked = bool(msg.data)
""",
     """    def markers_used_callback(self, msg):
        self.markers_used = int(msg.data)
        self.markers_used_time = self.get_clock().now()
        if self.markers_used >= 2:
            self.markers_used_multi_time = self.markers_used_time
        if self.markers_used >= 1:
            self.markers_pos_time = self.markers_used_time   # r2h (B1)
        # r2h (B1): decide on every detector frame, not only at the 1 Hz tick
        self._apply_gate()

    def yaw_locked_callback(self, msg):
        locked = bool(msg.data)
        changed = locked != self.yaw_locked
        self.yaw_locked = locked
        if changed:
            self._apply_gate()   # r2h (B1)
""", 1),
    # B2 helper before publish_timer
    ("""    def publish_timer(self):
""",
     """    def _reentry_pose(self, now):
        \"\"\"r2h (B2): the pose to publish now, or None to stay silent.

        After more than _REENTRY_GAP s without a publish (or before the first one): wait until _REENTRY_N accepted
        poses not older than _POSE_TIMEOUT are at hand, or until the oldest of them is _REENTRY_MAX_WAIT old (a slow
        detector, review M1); then for _REENTRY_HOLD s publish the medoid of the fresh poses at hand (1.._REENTRY_N;
        one missing frame does not silence it, review S1); else the latest pose, as before.\"\"\"
        last = self._last_publish_time
        gap = None if last is None else (now - last).nanoseconds / 1e9
        if self._reentry_until is not None and now.nanoseconds >= self._reentry_until:
            self._reentry_until = None
        if self._reentry_until is None and not self._reentry_wait and (gap is None or gap > _REENTRY_GAP):
            self._reentry_wait = True
            self.get_logger().info(
                'vpe_fix: resume after %s without a publish: waiting for %d fresh poses (medoid)'
                % ('start' if gap is None else '%.2fs' % gap, _REENTRY_N))
        if not self._reentry_wait and self._reentry_until is None:
            return self.last_pose
        fresh = [(t, p) for (t, p) in self._recent_poses
                 if (now - t).nanoseconds / 1e9 <= _POSE_TIMEOUT]
        if not fresh:
            return None
        if self._reentry_wait:
            waited = (now - fresh[0][0]).nanoseconds / 1e9
            if len(fresh) < _REENTRY_N and waited < _REENTRY_MAX_WAIT:
                return None
            self._reentry_wait = False
            self._reentry_until = now.nanoseconds + int(_REENTRY_HOLD * 1e9)
        return self._medoid([p for (_t, p) in fresh])

    def publish_timer(self):
""", 1),
    ("""        out = PoseWithCovarianceStamped()
        out.header.stamp = self.get_clock().now().to_msg()
        out.header.frame_id = 'map'
        out.pose.pose = self.last_pose
""",
     """        # r2h (B2): after a pause, the medoid of the last fresh poses first
        now = self.get_clock().now()
        pose = self._reentry_pose(now)
        if pose is None:
            return
        out = PoseWithCovarianceStamped()
        out.header.stamp = now.to_msg()
        out.header.frame_id = 'map'
        out.pose.pose = pose
""", 1),
    # review S2: a reseed restarts the pose history (the medoid never mixes poses from before it)
    ("""        self._consec_rejects = 0
        self._reseed_candidates.clear()
        self.get_logger().warn(
""",
     """        self._consec_rejects = 0
        self._reseed_candidates.clear()
        self._recent_poses.clear()               # r2h (B2, review S2)
        self._recent_poses.append((now, seed))
        self.get_logger().warn(
""", 1),
    ("""        self.vpe_pub.publish(out)
        self.published += 1
""",
     """        self.vpe_pub.publish(out)
        self._last_publish_time = now   # r2h (B2)
        self.published += 1
""", 1),
]

DRONE = [
    ("""_vision_arm_t = None
_aruco_yaw_locked        = False
""",
     """_vision_arm_t = None
# r2h (W): the same two moments as watchdog stamps on simple_offboard's hold clock (_wd_stamp()); vision_pose_age()
# keeps time.monotonic(). The vision watchdog is looked at every _VISION_WD_PERIOD s inside navigate_wait's wait.
_vpe_pose_wd = None
_vision_arm_wd = None
_VISION_WD_PERIOD = 0.1
_aruco_yaw_locked        = False
""", 1),
    ("""    global _vision_arm_t
    prev = _fcu_state_msg
""",
     """    global _vision_arm_t, _vision_arm_wd
    prev = _fcu_state_msg
""", 1),
    ("""        _vision_arm_t = None   # r2g (S4)
    # r2g (S4): the first armed State of this flight starts the no-vision count (until the first vpe_fix pose)
    if msg.connected and msg.armed and _vision_arm_t is None:
        _vision_arm_t = time.monotonic()
""",
     """        _vision_arm_t = None   # r2g (S4)
        _vision_arm_wd = None  # r2h (W)
    # r2g (S4): the first armed State of this flight starts the no-vision count (until the first vpe_fix pose)
    if msg.connected and msg.armed and _vision_arm_t is None:
        _vision_arm_wd = _wd_stamp()            # r2h (W): one reading for both clocks
        _vision_arm_t = _vision_arm_wd[2]
""", 1),
    ("""    global _vpe_pose_time, _vpe_pose_last
    p, o = msg.pose.pose.position, msg.pose.pose.orientation
    key = (p.x, p.y, p.z, o.x, o.y, o.z, o.w)
    if key != _vpe_pose_last:
        _vpe_pose_last = key
        _vpe_pose_time = time.monotonic()
""",
     """    global _vpe_pose_time, _vpe_pose_last, _vpe_pose_wd
    p, o = msg.pose.pose.position, msg.pose.pose.orientation
    key = (p.x, p.y, p.z, o.x, o.y, o.z, o.w)
    if key != _vpe_pose_last:
        _vpe_pose_last = key
        _vpe_pose_wd = _wd_stamp()              # r2h (W): one reading for both clocks
        _vpe_pose_time = _vpe_pose_wd[2]
""", 1),
    ("""def _vision_silence_age():
    \"\"\"r2g (S4): seconds without vision for the flight watchdogs (navigate_wait, safe_land).

    Since the last new vpe_fix pose; if none has come yet, since drone.py saw this flight armed. None while
    neither is known (disarmed and no pose yet): no watchdog. vision_pose_age() is unchanged.
    \"\"\"
    if _vpe_pose_time is not None:
        return time.monotonic() - _vpe_pose_time
    if _vision_arm_t is not None:
        return time.monotonic() - _vision_arm_t
    return None
""",
     """def _wd_stamp():
    \"\"\"r2h (W): a vision-watchdog stamp (sim, hold-clock seconds, monotonic seconds).

    The hold clock is simple_offboard's (_hold_now()): the ROS clock under use_sim_time (SITL), else monotonic.
    A ROS clock that reads 0 (no /clock yet) counts as monotonic.\"\"\"
    m = time.monotonic()
    try:
        clock = _node.get_clock()
        if clock.ros_time_is_active:
            t = clock.now().nanoseconds * 1e-9
            if t > 0.0:
                return (True, t, m)
    except Exception:
        pass
    return (False, m, m)


def _wd_age(stamp):
    \"\"\"r2h (W): seconds since a _wd_stamp() on the same kind of clock (monotonic if the kind changed in between);
    a negative age (the clock went back) is +inf, so the watchdog fails toward landing.\"\"\"
    now = _wd_stamp()
    age = now[1] - stamp[1] if now[0] == stamp[0] else now[2] - stamp[2]
    return age if age >= 0.0 else float('inf')


def _vision_silence_age():
    \"\"\"r2g (S4): seconds without vision for the flight watchdogs (navigate_wait, safe_land).

    Since the last new vpe_fix pose; if none has come yet, since drone.py saw this flight armed. None while
    neither is known (disarmed and no pose yet): no watchdog. vision_pose_age() is unchanged.
    r2h (W): measured on simple_offboard's hold clock (_wd_stamp(), _wd_since()).
    \"\"\"
    if _vpe_pose_time is not None:
        return _wd_since(_vpe_pose_time, _vpe_pose_wd)
    if _vision_arm_t is not None:
        return _wd_since(_vision_arm_t, _vision_arm_wd)
    return None


def _wd_since(mono_t, stamp):
    \"\"\"r2h (W): the moment is mono_t (time.monotonic(), as in r2g); its hold-clock stamp is used only when it was
    taken at that same moment (else -- e.g. the moment was set by other code -- monotonic, exactly as r2g).\"\"\"
    if stamp is None or stamp[2] != mono_t:
        return time.monotonic() - mono_t
    return _wd_age(stamp)


def _wait_watching_vision(seconds, vision_timeout):
    \"\"\"r2h (W): sleep `seconds` in slices of _VISION_WD_PERIOD; return early once the vision silence passes
    vision_timeout (or should_land is set), so the caller's loop runs its checks at once.\"\"\"
    end = time.monotonic() + seconds
    while not should_land:
        left = end - time.monotonic()
        if left <= 0.0:
            return
        time.sleep(min(_VISION_WD_PERIOD, left))
        silence = _vision_silence_age()
        if silence is not None and silence > vision_timeout:
            return
""", 1),
    ("""        if time.time() > deadline:
            _node.get_logger().warn('Navigate timed out after %.0fs (dist=%.2f)' % (timeout, dist))
            return False
        time.sleep(0.5)
    return False
""",
     """        if time.time() > deadline:
            _node.get_logger().warn('Navigate timed out after %.0fs (dist=%.2f)' % (timeout, dist))
            return False
        # r2h (W): the same 0.5 s step, the vision watchdog looked at every 0.1 s
        _wait_watching_vision(0.5, vision_timeout)
    return False
""", 1),
]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def apply(root, rel, edits):
    path = os.path.join(root, rel)
    t = open(path, 'rb').read().decode('utf-8')
    for old, new, n in edits:
        if t.count(old) != n:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
        t = t.replace(old, new)
    out = t.encode('utf-8')
    open(path, 'wb').write(out)
    print('r2h %s %s' % (rel, sha(out)))


def main():
    root = sys.argv[1]
    for rel in R2G:
        h = sha(open(os.path.join(root, rel), 'rb').read())
        if not h.startswith(R2G[rel]):
            sys.exit('STOP: %s is not r2g (%s)' % (rel, h[:16]))
    apply(root, 'src/bumblebee/src/python/vpe_fix.py', VPE)
    apply(root, 'src/bumblebee/examples/drone.py', DRONE)


if __name__ == '__main__':
    main()
