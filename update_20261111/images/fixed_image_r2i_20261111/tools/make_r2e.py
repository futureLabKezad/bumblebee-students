#!/usr/bin/env python3
"""make_r2e.py - r2 revision e = r2d + fixes from the independent review of r2d (Claude, 09.11.2026).

Review: /work/review_r2d_20261109/REVIEW_r2d.md.
MUST-FIX 1: after a stall of simple_offboard itself (1.5-3 s) the lease tick ran before the queued State that reported
  PX4's offboard-loss failsafe, saw the cached "armed in OFFBOARD" (still fresh, state_timeout 3 s) and sent AUTO.LAND
  over the failsafe (proven by the reviewer's probe). Fix in script_lease.h: land only on a State received after the
  lease became overdue AND after the watchdog has ticked regularly for 1 s (a tick gap > 0.5 s = this node stalled;
  the queued lease and State messages drain first).
SHOULD 2: a script killed inside navigate(auto_arm) before the armed report arrived was never engaged. Fix: an
  auto_arm request while the lease is fresh engages the arm it starts (first armed tick in OFFBOARD within 15 s).
SHOULD 3: drone.py's lease thread ended for good on the first publish error. Fix: log once, keep going.
SHOULD 4: script_lease_timeout must be 0 (off) or within [1, 30] s (the lease period is 0.5 s).
SHOULD 5: flight_marker.py ignored fly_to's result. Fix: a missed waypoint ends the mission (finally: safe_land).
Usage: python3 -I make_r2e.py R2E_DIR   (the files there must be r2d's)
"""
import hashlib
import os
import sys

R2D = {
    'src/bumblebee/examples/drone.py': '319e25ac4b2fb3a1',
    'src/bumblebee/examples/flight/flight_marker.py': '03c14ca5904aaf44',
    'src/bumblebee/src/cpp/simple_offboard.cpp': '23c282a78bdfb8c5',
    'src/bumblebee/src/cpp/script_lease.h': '2c5ca72422ec45f3',
}

DRONE = [
    ("""            def run():
                msg = Bool()
                msg.data = True
                try:
                    while not stop.is_set():
                        pub.publish(msg)
                        stop.wait(LEASE_PERIOD_S)
                except Exception:
                    pass
""",
     """            def run():
                msg = Bool()
                msg.data = True
                warned = False
                while not stop.is_set():
                    # r2e: a failed publish must not end the lease for good
                    # (simple_offboard would land a healthy flight 2 s later)
                    try:
                        pub.publish(msg)
                    except Exception as e:
                        if not warned:
                            print('  WARN  script lease publish failed (retrying): %s' % e)
                            warned = True
                    stop.wait(LEASE_PERIOD_S)
""", 1),
]

MARKER = [
    ("""    drone.fly_to(x=0, y=1.4, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05)
""",
     """    if not drone.fly_to(x=0, y=1.4, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05):
        raise SystemExit('waypoint above marker 2 not reached')   # r2e: finally -> safe_land
""", 1),
    ("""    drone.fly_to(x=0, y=0.7, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05)
""",
     """    if not drone.fly_to(x=0, y=0.7, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05):
        raise SystemExit('waypoint above marker 1 not reached')
""", 1),
    ("""    drone.fly_to(x=0, y=0, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05)
""",
     """    if not drone.fly_to(x=0, y=0, z=cruise_z, speed=0.10, tolerance=0.12, settle_speed=0.05):
        raise SystemExit('waypoint above marker 0 not reached')
""", 1),
]

SO = [
    ("""        if (!std::isfinite(lease_timeout) || lease_timeout < 0.0 || lease_timeout > 30.0)
            throw std::invalid_argument("script_lease_timeout must be within [0, 30] s");
""",
     """        if (!std::isfinite(lease_timeout) || lease_timeout < 0.0 || lease_timeout > 30.0 ||
            (lease_timeout > 0.0 && lease_timeout < 1.0))
            throw std::invalid_argument("script_lease_timeout must be 0 (off) or within [1, 30] s");
""", 1),
    ("""                if (auto_arm) {
                    serve_land_seq_ = land_seq_.load(); checkArmCancel();
""",
     """                if (auto_arm) {
                    // T25 (r2e): an auto_arm request while the script's lease is fresh engages the arm it starts,
                    // even if the script dies before PX4 reports armed
                    if (script_lease_timeout_ns_ > 0) {
                        const int64_t lease_now = steadyNs(), lease_rx = lease_rx_ns_.load();
                        if (lease_rx != 0 && lease_now - lease_rx <= script_lease_timeout_ns_)
                            lease_arm_req_ns_ = lease_now;
                    }
                    serve_land_seq_ = land_seq_.load(); checkArmCancel();
""", 1),
    ("""    std::atomic<int64_t> lease_rx_ns_{0};
""",
     """    std::atomic<int64_t> lease_rx_ns_{0};
    std::atomic<int64_t> lease_arm_req_ns_{0};  // r2e: steadyNs() of the last auto_arm request with a fresh lease
""", 1),
    ("""        const auto s = fcuState();
        const int64_t now = steadyNs();
        const int64_t rx = lease_rx_ns_.load();
        if (!scriptLeaseLandDue(lease_, s.connected && stateFresh(), s.armed, s.mode == "OFFBOARD",
                                rx, now, script_lease_timeout_ns_, kScriptLeaseRetryNs))
            return;
""",
     """        mavros_msgs::msg::State s;
        int64_t state_rx = 0;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            s = state_;
            state_rx = state_rx_steady_ns_;  // r2e: receipt of that State, steady clock like the lease
        }
        const int64_t now = steadyNs();
        const int64_t rx = lease_rx_ns_.load();
        if (!scriptLeaseLandDue(lease_, s.connected && stateFresh(), s.armed, s.mode == "OFFBOARD",
                                rx, state_rx, lease_arm_req_ns_.load(), now, script_lease_timeout_ns_,
                                kScriptLeaseRetryNs))
            return;
""", 1),
]

LEASE_H = r'''// T25 (r2d, 09.11.2026; r2e after the independent review): script lease watchdog decision for simple_offboard.
// No ROS: unit-tested by test/test_script_lease.cpp of the r2e folder with plain g++.
//
// drone.py sends a lease every 0.5 s from its first flight command. The watchdog lands (simple_offboard's own
// /land) when the lease is older than timeout while the vehicle is armed in OFFBOARD and the lease was seen fresh
// while armed in OFFBOARD in this arm cycle, or an auto_arm request came with a fresh lease. Pilot wins: armed in
// any other mode (pilot switch, PX4 failsafe, our own AUTO.LAND) disengages it until the next disarm.
// r2e: it acts only on a State received after the lease became overdue, and only after it has ticked regularly
// for 1 s: after a stall of this node the cached "armed in OFFBOARD" may be old (the reviewer's probe: a 1.8-2 s
// SIGSTOP made it land over PX4's offboard-loss failsafe), and queued lease and State messages must drain first.
#pragma once
#include <cstdint>

constexpr int64_t kScriptLeaseRetryNs = 1000000000LL;      // a failed /land is retried after 1 s
constexpr int64_t kScriptLeaseTickGapNs = 500000000LL;     // a longer gap between ticks: this node stalled
constexpr int64_t kScriptLeaseResumeNs = 1000000000LL;     // regular ticks needed before acting
constexpr int64_t kScriptLeaseArmWindowNs = 15000000000LL; // an auto_arm request engages an arm within this

struct ScriptLease {
    bool engaged = false;          // the lease belongs to this arm cycle
    bool stepped_back = false;     // armed outside OFFBOARD after engaging: off until disarmed
    bool armed_seen = false;       // this arm cycle has had a tick
    int64_t last_try_ns = 0;       // last landing attempt, 0 = none
    int64_t last_tick_ns = 0;      // previous tick, 0 = none
    int64_t regular_since_ns = 0;  // ticks no more than kScriptLeaseTickGapNs apart since then
};

// One watchdog tick. state_ok: FCU state connected and fresh (an unknown state never acts).
// lease_rx_ns: receipt of the last lease; state_rx_ns: receipt of the State that armed/offboard come from;
// arm_req_ns: last auto_arm request made while the lease was fresh. All steady clock, 0 = never. True = land now.
inline bool scriptLeaseLandDue(ScriptLease& l, bool state_ok, bool armed, bool offboard,
                               int64_t lease_rx_ns, int64_t state_rx_ns, int64_t arm_req_ns,
                               int64_t now_ns, int64_t timeout_ns, int64_t retry_ns) {
    if (l.last_tick_ns == 0 || now_ns - l.last_tick_ns > kScriptLeaseTickGapNs) l.regular_since_ns = now_ns;
    l.last_tick_ns = now_ns;
    if (timeout_ns <= 0 || !state_ok) return false;
    if (!armed) {
        l.engaged = l.stepped_back = l.armed_seen = false;
        l.last_try_ns = 0;
        return false;
    }
    const bool first_armed_tick = !l.armed_seen;
    l.armed_seen = true;
    if (!offboard) {
        if (l.engaged) l.stepped_back = true;
        l.engaged = false;
        return false;
    }
    if (l.stepped_back) return false;
    if (first_armed_tick && arm_req_ns != 0 && now_ns - arm_req_ns <= kScriptLeaseArmWindowNs) l.engaged = true;
    // A receipt after now (another thread) is fresh too
    const bool fresh = lease_rx_ns != 0 && now_ns - lease_rx_ns <= timeout_ns;
    if (fresh) { l.engaged = true; return false; }
    if (!l.engaged) return false;
    if (now_ns - l.regular_since_ns < kScriptLeaseResumeNs) return false;
    const int64_t base = lease_rx_ns > arm_req_ns ? lease_rx_ns : arm_req_ns;
    if (state_rx_ns <= base + timeout_ns || state_rx_ns < l.regular_since_ns) return false;
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
    if not sha(data).startswith(R2D[rel]):
        sys.exit('STOP: %s is not r2d (%s)' % (rel, sha(data)[:16]))
    t = data.decode('utf-8')
    for old, new, n in edits:
        if t.count(old) != n:
            sys.exit('STOP: %s anchor %r: %d matches' % (rel, old[:60], t.count(old)))
        t = t.replace(old, new)
    out = t.encode('utf-8')
    open(path, 'wb').write(out)
    print('r2e %s %s' % (rel, sha(out)))


def main():
    root = sys.argv[1]
    h = 'src/bumblebee/src/cpp/script_lease.h'
    if not sha(open(os.path.join(root, h), 'rb').read()).startswith(R2D[h]):
        sys.exit('STOP: script_lease.h is not r2d')
    patch(root, 'src/bumblebee/examples/drone.py', DRONE)
    patch(root, 'src/bumblebee/examples/flight/flight_marker.py', MARKER)
    patch(root, 'src/bumblebee/src/cpp/simple_offboard.cpp', SO)
    open(os.path.join(root, h), 'wb').write(LEASE_H.encode('utf-8'))
    print('r2e %s %s' % (h, sha(LEASE_H.encode('utf-8'))))


if __name__ == '__main__':
    main()
