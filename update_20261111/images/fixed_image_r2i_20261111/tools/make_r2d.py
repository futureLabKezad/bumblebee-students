#!/usr/bin/env python3
"""make_r2d.py - r2 revision d = r2c + F7 + T25 (Claude, 09.11.2026).

F7 (waypoint arrival): the marker examples counted a point at 0.25 m, the same number as the С7 limit; Gazebo
  measured 0.21-0.26 at the switch. navigate_wait/fly_to get an optional settle_speed (default None = old
  behaviour): a point counts after 2 successive samples within tolerance with horizontal speed < settle_speed.
  flight_marker.py and flight_marker_loop.py: tolerance 0.25 -> 0.12, settle_speed 0.05. Criteria untouched.
T25 (script dies alone, Gazebo k1_r2c_4059_kill_hover): OFFBOARD held, simple_offboard kept streaming, the drone
  hovered. Script lease: drone.py sends True on /simple_offboard/script_lease every 0.5 s from its first flight
  command; simple_offboard lands with its own /land when the lease is silent > script_lease_timeout (2 s) while
  armed in OFFBOARD. Engaged only by a lease seen while armed in OFFBOARD; a pilot / PX4 failsafe mode change
  disengages it for that arm cycle (pilot wins). Decision in src/cpp/script_lease.h (no ROS, unit-tested).
Usage: python3 -I make_r2d.py R2D_DIR   (the files there must be r2c's)
"""
import hashlib
import os
import sys

R2C = {
    'src/bumblebee/examples/drone.py': 'ac823ae535416f39',
    'src/bumblebee/examples/flight/flight_marker.py': '902d36a7f04f2957',
    'src/bumblebee/examples/flight/flight_marker_loop.py': 'cade97b5fc96706e',
    'src/bumblebee/src/cpp/simple_offboard.cpp': '85328f0dfd6616d9',
    'src/bumblebee/CMakeLists.txt': '5bea3f52d2e03507',
}

# ---------------------------------------------------------------- drone.py
DRONE = [
    # F7: navigate_wait signature
    ("""def navigate_wait(x=0.0, y=0.0, z=0.0, yaw=float('nan'), speed=0.5, frame_id='body',
                  tolerance=0.2, auto_arm=False, phase='FLIGHT', timeout=60.0,
                  tolerance_adaptive=False, vision_timeout=6.0):
""",
     """def navigate_wait(x=0.0, y=0.0, z=0.0, yaw=float('nan'), speed=0.5, frame_id='body',
                  tolerance=0.2, auto_arm=False, phase='FLIGHT', timeout=60.0,
                  tolerance_adaptive=False, vision_timeout=6.0, settle_speed=None):
""", 1),
    ("""    otherwise the passed-in `tolerance` is kept.
    \"\"\"
    global _vision_abort
""",
     """    otherwise the passed-in `tolerance` is kept.

    settle_speed (F7, r2d; default None = arrive at the first sample within
    tolerance, as before): also require the horizontal speed below
    settle_speed m/s on 2 successive samples within tolerance, so the point
    counts only once the drone has nearly stopped there.
    \"\"\"
    global _vision_abort
""", 1),
    ("""    last_t = None      # wall time of previous sample
""",
     """    last_t = None      # wall time of previous sample
    settled = 0        # F7: successive samples within tolerance below settle_speed
""", 1),
    ("""        if dist < tolerance:
            return True
        if time.time() > deadline:
            _node.get_logger().warn('Navigate timed out after %.0fs (dist=%.2f)' % (timeout, dist))
""",
     """        if dist < tolerance:
            if settle_speed is None:
                return True
            # F7 (r2d): count the point only once the drone has nearly stopped
            # there; a NaN speed compares False and does not count
            v_xy = math.hypot(t.vx, t.vy)
            settled = settled + 1 if v_xy < settle_speed else 0
            if settled >= 2:
                return True
        else:
            settled = 0
        if time.time() > deadline:
            _node.get_logger().warn('Navigate timed out after %.0fs (dist=%.2f)' % (timeout, dist))
""", 1),
    # F7: fly_to passes settle_speed through
    ("""def fly_to(x, y, z=1.0, speed=0.5, tolerance=0.2, tolerance_adaptive=False):
    \"\"\"Fly to absolute map coordinates (x, y, z).\"\"\"
    _init()
    print('=== FLY TO (%.2f, %.2f, %.2f) ===' % (x, y, z))
    return navigate_wait(x=x, y=y, z=z, speed=speed, frame_id='map', phase='FLY_TO',
                         tolerance=tolerance, tolerance_adaptive=tolerance_adaptive)
""",
     """def fly_to(x, y, z=1.0, speed=0.5, tolerance=0.2, tolerance_adaptive=False,
           settle_speed=None):
    \"\"\"Fly to absolute map coordinates (x, y, z).

    settle_speed (F7, r2d): see navigate_wait; None keeps the old arrival.
    \"\"\"
    _init()
    print('=== FLY TO (%.2f, %.2f, %.2f) ===' % (x, y, z))
    return navigate_wait(x=x, y=y, z=z, speed=speed, frame_id='map', phase='FLY_TO',
                         tolerance=tolerance, tolerance_adaptive=tolerance_adaptive,
                         settle_speed=settle_speed)
""", 1),
    # T25: the lease starts with the first flight command
    ("""def navigate(**kwargs):
    global _arm_ref_z, _auto_arm_ok_t
    _init()
    req = srv.Navigate.Request()
""",
     """def navigate(**kwargs):
    global _arm_ref_z, _auto_arm_ok_t
    _init()
    _start_script_lease()   # T25: simple_offboard lands if this process dies
    req = srv.Navigate.Request()
""", 1),
    # T25: the lease stops with the script
    ("""    _stop_detector_wake()   # F1: no wakes after the script ends
""",
     """    _stop_detector_wake()   # F1: no wakes after the script ends
    _stop_script_lease()    # T25: armed in OFFBOARD after this -> simple_offboard lands
""", 1),
    # T25: lease thread, next to the detector wake
    ("""def check_aruco(timeout=10, min_markers=1):
""",
     """# T25 (r2d, 09.11.2026): script lease. A flight script that died alone
# (SIGKILL, OOM, a crash of python itself) left the drone in OFFBOARD:
# simple_offboard kept streaming the last setpoint and the drone hovered
# (Gazebo k1_r2c_4059_kill_hover). From the first flight command on, this
# thread sends True on LEASE_TOPIC every LEASE_PERIOD_S. simple_offboard lands
# with its own /land when the lease is silent for script_lease_timeout (2 s)
# while armed in OFFBOARD; it never acts in another mode (the pilot's switch
# wins). Ctrl+C keeps the process, and so the lease, alive: safe_land runs as
# before. The lease ends with the process or in _shutdown().
LEASE_TOPIC = '/simple_offboard/script_lease'
LEASE_PERIOD_S = 0.5
_lease_lock = threading.Lock()
_lease_thread = None
_lease_stop = None


def _start_script_lease():
    \"\"\"Start the lease once. Idempotent; never raises.\"\"\"
    global _lease_thread, _lease_stop
    try:
        with _lease_lock:
            if _lease_thread is not None and _lease_thread.is_alive():
                return
            pub = _node.create_publisher(Bool, LEASE_TOPIC, 10)
            stop = threading.Event()

            def run():
                msg = Bool()
                msg.data = True
                try:
                    while not stop.is_set():
                        pub.publish(msg)
                        stop.wait(LEASE_PERIOD_S)
                except Exception:
                    pass

            _lease_stop = stop
            _lease_thread = threading.Thread(target=run, name='script-lease', daemon=True)
            _lease_thread.start()
    except Exception as e:
        print('  WARN  script lease not started: %s' % e)


def _stop_script_lease():
    stop = _lease_stop
    if stop is not None:
        stop.set()
    t = _lease_thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=1.0)


def check_aruco(timeout=10, min_markers=1):
""", 1),
]

LOOP = [
    ("""        if not drone.fly_to(x=wx, y=wy, z=cruise_z, speed=0.1, tolerance=0.25):
""",
     """        # F7 (r2d): 0.12 m and nearly stopped -- a margin under the 0.25 m of C7
        if not drone.fly_to(x=wx, y=wy, z=cruise_z, speed=0.1, tolerance=0.12, settle_speed=0.05):
""", 1),
    ("""        drone.fly_to(x=0.0, y=0.0, z=cruise_z, speed=0.1, tolerance=0.25)
""",
     """        drone.fly_to(x=0.0, y=0.0, z=cruise_z, speed=0.1, tolerance=0.12, settle_speed=0.05)
""", 1),
]

MARKER = [
    ("""    drone.fly_to(x=0, y=1.4, z=cruise_z, speed=0.10, tolerance=0.25)
""",
     """    # F7 (r2d): 0.12 m and nearly stopped -- a margin under the 0.25 m of C7
    drone.fly_to(x=0, y=1.4, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05)
""", 1),
    ("""    drone.fly_to(x=0, y=0.7, z=cruise_z, speed=0.10, tolerance=0.25)
""",
     """    drone.fly_to(x=0, y=0.7, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05)
""", 1),
    ("""    drone.fly_to(x=0, y=0, z=cruise_z, speed=0.10, tolerance=0.25)
""",
     """    drone.fly_to(x=0, y=0, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05)
""", 1),
]

SO = [
    ("""#include <std_srvs/srv/trigger.hpp>
""",
     """#include <std_srvs/srv/trigger.hpp>
#include <std_msgs/msg/bool.hpp>
#include "script_lease.h"
""", 1),
    ("""        setpoint_smooth_alpha_ = declare_parameter("setpoint_smooth_alpha", 0.3);
""",
     """        setpoint_smooth_alpha_ = declare_parameter("setpoint_smooth_alpha", 0.3);
        // T25 (r2d): land when the flight script's lease (drone.py, every 0.5 s) is silent this long while armed in
        // OFFBOARD; 0 = off. Engaged only by a lease seen while armed in OFFBOARD (scripts without one: as before)
        const double lease_timeout = declare_parameter("script_lease_timeout", 2.0);
        if (!std::isfinite(lease_timeout) || lease_timeout < 0.0 || lease_timeout > 30.0)
            throw std::invalid_argument("script_lease_timeout must be within [0, 30] s");
        script_lease_timeout_ns_ = static_cast<int64_t>(lease_timeout * 1e9);
""", 1),
    ("""        setpoint_timer_->cancel();

        position_msg_.header.frame_id = local_frame_;
""",
     """        setpoint_timer_->cancel();

        // T25 (r2d): script lease. Receipt on the concurrent group; the watchdog in the land group, so it never
        // overlaps a /land call and calls the same land()
        if (script_lease_timeout_ns_ > 0) {
            lease_sub_ = create_subscription<std_msgs::msg::Bool>("~/script_lease", rclcpp::QoS(10),
                [this](const std_msgs::msg::Bool::SharedPtr) { lease_rx_ns_ = steadyNs(); }, sub_opts);
            lease_timer_ = create_wall_timer(std::chrono::milliseconds(200),
                [this]() { scriptLeaseTick(); }, cb_grp_land_);
        }

        position_msg_.header.frame_id = local_frame_;
""", 1),
    ("""    std::atomic<bool> landing_{false};
""",
     """    std::atomic<bool> landing_{false};
    // T25 (r2d) script lease: steadyNs() of the last lease (any thread); watchdog state (lease timer only)
    std::atomic<int64_t> lease_rx_ns_{0};
    ScriptLease lease_;
    int64_t script_lease_timeout_ns_ = 0;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr lease_sub_;
    rclcpp::TimerBase::SharedPtr lease_timer_;
""", 1),
    ("""    void release(const std_srvs::srv::Trigger::Request::SharedPtr,
""",
     """    // T25 (r2d): the flight script stopped sending its lease while we fly it in OFFBOARD -> our own /land
    void scriptLeaseTick() {
        const auto s = fcuState();
        const int64_t now = steadyNs();
        const int64_t rx = lease_rx_ns_.load();
        if (!scriptLeaseLandDue(lease_, s.connected && stateFresh(), s.armed, s.mode == "OFFBOARD",
                                rx, now, script_lease_timeout_ns_, kScriptLeaseRetryNs))
            return;
        RCLCPP_ERROR(get_logger(), "Script lease silent for %.1f s while armed in OFFBOARD: the flight script "
                     "stopped -- landing", (now - rx) / 1e9);
        auto req = std::make_shared<std_srvs::srv::Trigger::Request>();
        auto res = std::make_shared<std_srvs::srv::Trigger::Response>();
        land(req, res);
        if (res->success)
            RCLCPP_WARN(get_logger(), "Script lease landing started %s", res->message.c_str());
        else
            RCLCPP_ERROR(get_logger(), "Script lease landing failed: %s (retry in 1 s)", res->message.c_str());
    }

    void release(const std_srvs::srv::Trigger::Request::SharedPtr,
""", 1),
]

CMAKE = [
    ("""ament_target_dependencies(simple_offboard
  rclcpp tf2 tf2_ros tf2_geometry_msgs
  std_srvs geometry_msgs sensor_msgs mavros_msgs)
""",
     """ament_target_dependencies(simple_offboard
  rclcpp tf2 tf2_ros tf2_geometry_msgs
  std_srvs std_msgs geometry_msgs sensor_msgs mavros_msgs)
""", 1),
]

LEASE_H = r'''// T25 (r2d, 09.11.2026): script lease watchdog decision for simple_offboard. No ROS: unit-tested by
// test/test_script_lease.cpp of the r2d folder with plain g++.
//
// drone.py sends a lease every 0.5 s from its first flight command. The watchdog lands (simple_offboard's own
// /land) when the lease is older than timeout while the vehicle is armed in OFFBOARD and the lease was seen fresh
// while armed in OFFBOARD in this arm cycle. Pilot wins: armed in any other mode (pilot switch, PX4 failsafe, our
// own AUTO.LAND) disengages it until the next disarm, so switching back to OFFBOARD later behaves as before r2d.
#pragma once
#include <cstdint>

constexpr int64_t kScriptLeaseRetryNs = 1000000000LL;  // a failed /land is retried after 1 s

struct ScriptLease {
    bool engaged = false;      // a fresh lease was seen while armed in OFFBOARD (this arm cycle)
    bool stepped_back = false; // armed outside OFFBOARD after engaging: off until disarmed
    int64_t last_try_ns = 0;   // last landing attempt, 0 = none
};

// One watchdog tick. state_ok: FCU state connected and fresh (an unknown state never acts).
// lease_rx_ns: receipt time of the last lease, 0 = never. True = land now.
inline bool scriptLeaseLandDue(ScriptLease& l, bool state_ok, bool armed, bool offboard,
                               int64_t lease_rx_ns, int64_t now_ns, int64_t timeout_ns, int64_t retry_ns) {
    if (timeout_ns <= 0 || !state_ok) return false;
    if (!armed) { l = ScriptLease(); return false; }
    if (!offboard) {
        if (l.engaged) l.stepped_back = true;
        l.engaged = false;
        return false;
    }
    if (l.stepped_back) return false;
    // A receipt after now (another thread) is fresh too
    const bool fresh = lease_rx_ns != 0 && now_ns - lease_rx_ns <= timeout_ns;
    if (fresh) { l.engaged = true; return false; }
    if (!l.engaged) return false;
    if (l.last_try_ns != 0 && now_ns - l.last_try_ns < retry_ns) return false;
    l.last_try_ns = now_ns;
    return true;
}
'''


def sha(b):
    return hashlib.sha256(b).hexdigest()


def patch(root, rel, edits):
    path = os.path.join(root, rel)
    data = open(path, 'rb').read()
    if not sha(data).startswith(R2C[rel]):
        sys.exit('STOP: %s is not r2c (%s)' % (rel, sha(data)[:16]))
    t = data.decode('utf-8')
    for old, new, n in edits:
        if t.count(old) != n:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
        t = t.replace(old, new)
    out = t.encode('utf-8')
    open(path, 'wb').write(out)
    print('r2d %s %s' % (rel, sha(out)))


def main():
    root = sys.argv[1]
    h = os.path.join(root, 'src/bumblebee/src/cpp/script_lease.h')
    if os.path.exists(h):
        sys.exit('STOP: %s exists' % h)
    patch(root, 'src/bumblebee/examples/drone.py', DRONE)
    patch(root, 'src/bumblebee/examples/flight/flight_marker_loop.py', LOOP)
    patch(root, 'src/bumblebee/examples/flight/flight_marker.py', MARKER)
    patch(root, 'src/bumblebee/src/cpp/simple_offboard.cpp', SO)
    patch(root, 'src/bumblebee/CMakeLists.txt', CMAKE)
    with open(h, 'xb') as f:
        f.write(LEASE_H.encode('utf-8'))
    print('r2d src/bumblebee/src/cpp/script_lease.h %s' % sha(LEASE_H.encode('utf-8')))


if __name__ == '__main__':
    main()
