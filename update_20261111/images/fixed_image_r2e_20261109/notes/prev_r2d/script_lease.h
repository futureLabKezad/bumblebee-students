// T25 (r2d, 09.11.2026): script lease watchdog decision for simple_offboard. No ROS: unit-tested by
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
