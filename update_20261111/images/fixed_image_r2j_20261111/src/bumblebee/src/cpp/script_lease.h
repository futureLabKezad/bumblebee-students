// T25 (r2d, 09.11.2026; r2e after the independent review): script lease watchdog decision for simple_offboard.
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
