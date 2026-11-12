// r2e T25: scriptLeaseLandDue() without ROS. Build and run (from fixed_image_r2e_20261109):
//   g++ -std=c++17 -Wall -Wextra -Werror -I src/bumblebee/src/cpp test/test_script_lease.cpp -o /tmp/tsl && /tmp/tsl
// Model: the watchdog ticks every 0.2 s; MAVROS State arrives once a second (on whole seconds) unless stated.
#include "script_lease.h"
#include <cstdio>
#include <initializer_list>

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); ++failures; } } while (0)

static const int64_t S = 1000000000LL;      // 1 s
static const int64_t T = 2 * S;             // script_lease_timeout 2 s
static const int64_t R = kScriptLeaseRetryNs;
static const int64_t TICK = S / 5;

struct Sim {
    ScriptLease l;
    bool state_ok = true, armed = false, offboard = false;
    bool state_flow = true;                  // State messages arrive (1 Hz)
    int64_t rx = 0, state_rx = 0, arm_req = 0;
    bool tick(int64_t now, int64_t timeout = T) {
        if (state_flow) state_rx = now - now % S;
        return scriptLeaseLandDue(l, state_ok, armed, offboard, rx, state_rx, arm_req, now, timeout, R);
    }
    // ticks every 0.2 s from a to b; returns the first due time, -1 = none
    int64_t run(int64_t a, int64_t b, int64_t timeout = T) {
        for (int64_t t = a; t <= b; t += TICK)
            if (tick(t, timeout)) return t;
        return -1;
    }
    // a flight with a live script from a to b (lease every 0.5 s)
    void live(int64_t a, int64_t b) {
        for (int64_t t = a; t <= b; t += TICK) {
            if (t % (S / 2) < TICK) rx = t - t % (S / 2);
            CHECK(!tick(t));
        }
    }
};

int main() {
    {   // 1. k1: script flying in OFFBOARD, killed after its lease at 10.0 -> due at the first State after 12.0 (13.0)
        Sim s; s.armed = true; s.offboard = true;
        s.live(0, 10 * S);
        int64_t due = s.run(10 * S + TICK, 20 * S);
        CHECK(due == 13 * S);
        CHECK(!s.tick(due + S / 2));                 // no retry before 1 s
        CHECK(s.tick(due + S));                      // /land failed and still OFFBOARD: retry
    }
    {   // 2. no State after the lease went overdue: never (the cached State may be old)
        Sim s; s.armed = true; s.offboard = true;
        s.live(0, 10 * S);
        s.state_flow = false;                        // state_ok stays true (fresh within state_timeout)
        CHECK(s.run(10 * S + TICK, 20 * S) == -1);
        s.state_flow = true;
        CHECK(s.run(20 * S, 22 * S) == 20 * S);
    }
    {   // 3. a script without a lease (old scripts, other tools): never
        Sim s; s.armed = true; s.offboard = true;
        CHECK(s.run(0, 60 * S) == -1);
    }
    {   // 4. a lease seen only before arming (drone.py preflight, then another tool flies): never
        Sim s; s.rx = 1 * S; CHECK(!s.tick(1 * S));
        s.armed = true; s.offboard = true;
        CHECK(s.run(10 * S, 60 * S) == -1);
    }
    {   // 5. killed right after arming: the last lease 0.4 s before the first armed tick still engages
        Sim s; s.offboard = true; s.rx = 9 * S + 6 * S / 10; CHECK(s.run(8 * S, 9 * S + 8 * S / 10) == -1);
        s.armed = true;
        int64_t due = s.run(10 * S, 20 * S);
        CHECK(due == 12 * S);                        // overdue at 11.6, first State after it at 12.0
    }
    {   // 6. pilot wins: pilot switches to POSCTL, the script dies -> never; back to OFFBOARD -> still never
        Sim s; s.armed = true; s.offboard = true;
        s.live(0, 5 * S);
        s.offboard = false;
        CHECK(s.run(5 * S + TICK, 30 * S) == -1);
        s.offboard = true;
        CHECK(s.run(30 * S, 60 * S) == -1);
        s.rx = 61 * S;
        CHECK(s.run(61 * S, 70 * S) == -1);
    }
    {   // 7. our own AUTO.LAND (or a PX4 failsafe) then disarm, re-arm without a lease: never
        Sim s; s.armed = true; s.offboard = true; s.live(0, 1 * S);
        s.offboard = false; CHECK(s.run(2 * S, 10 * S) == -1);
        s.armed = false; CHECK(!s.tick(11 * S));
        s.armed = true; s.offboard = true;
        CHECK(s.run(12 * S, 40 * S) == -1);
    }
    {   // 8. after a disarm a new arm cycle with a lease engages again
        Sim s; s.armed = true; s.offboard = true; s.live(0, 1 * S);
        s.offboard = false; CHECK(!s.tick(2 * S));
        s.armed = false; CHECK(!s.tick(3 * S));
        s.armed = true; s.offboard = true; s.live(4 * S, 6 * S);
        int64_t due = s.run(6 * S + TICK, 12 * S);
        CHECK(due == 9 * S);                         // lease 6.0, overdue 8.0, State 9.0
    }
    {   // 9. FCU state unknown: never acts, and keeps the engagement for when the state is back
        Sim s; s.armed = true; s.offboard = true; s.live(0, 1 * S);
        s.state_ok = false; CHECK(s.run(1 * S + TICK, 10 * S) == -1);
        s.state_ok = true; CHECK(s.run(10 * S, 11 * S) == 10 * S);
    }
    {   // 10. disarmed (landed, Ctrl+C path finished): never, whatever the lease
        Sim s; s.rx = 1 * S;
        CHECK(s.run(0, 30 * S) == -1);
    }
    {   // 11. timeout 0 = off
        Sim s; s.armed = true; s.offboard = true; s.rx = 1 * S;
        CHECK(s.run(1 * S, 30 * S, 0) == -1);
    }
    {   // 12. a receipt stamped after now (other thread) counts as fresh
        Sim s; s.armed = true; s.offboard = true; s.rx = 5 * S + 1000;
        CHECK(!s.tick(5 * S));
        CHECK(s.l.engaged);
    }
    {   // 13. lease steady during a whole flight with 1.4 s gaps (slow Pi): never
        Sim s; s.armed = true; s.offboard = true;
        bool any = false;
        for (int64_t t = 0; t <= 60 * S; t += TICK) {
            if (t % (7 * S / 5) == 0) s.rx = t;
            any = any || s.tick(t);
        }
        CHECK(!any);
    }
    {   // 14. MUST-FIX 1: simple_offboard itself stalls 2 s (SIGSTOP), script alive. At resume the tick may run
        //     before the queued lease and with an old "armed in OFFBOARD" State processed late: never land
        for (int64_t stall : {S + S / 2, 18 * S / 10, 2 * S, 23 * S / 10, 26 * S / 10, 3 * S}) {
            Sim s; s.armed = true; s.offboard = true;
            s.live(0, 10 * S);                       // last lease 10.0, last tick 10.0
            const int64_t back = 10 * S + stall;
            s.state_rx = back;                       // the old State processed at resume (receipt time = now)
            s.state_flow = false;
            CHECK(!s.tick(back));                    // first tick after the stall: lease still 10.0
            s.rx = back + S / 20;                    // the queued lease drains 50 ms later
            s.state_flow = true;
            bool any = false;
            for (int64_t t = back + TICK; t <= back + 10 * S; t += TICK) {
                if (t % (S / 2) < TICK) s.rx = t - t % (S / 2);
                any = any || s.tick(t);
            }
            CHECK(!any);
        }
    }
    {   // 15. same stall, but PX4 went into its offboard-loss failsafe meanwhile: the State says POSCTL -> never
        Sim s; s.armed = true; s.offboard = true;
        s.live(0, 10 * S);
        s.offboard = false;
        s.state_rx = 12 * S;
        CHECK(s.run(12 * S, 30 * S) == -1);
    }
    {   // 16. the script dies after the stall: still lands (after the 1 s of regular ticks and a new State)
        Sim s; s.armed = true; s.offboard = true;
        s.live(0, 10 * S);
        CHECK(!s.tick(12 * S));                      // stall 10 -> 12, script died at 10.0 meanwhile
        int64_t due = s.run(12 * S + TICK, 20 * S);
        CHECK(due == 13 * S);                        // regular since 12.0, State 13.0 > overdue 12.0
    }
    {   // 17. SHOULD 2: killed inside navigate(auto_arm), the armed report comes 3 s later: still lands
        Sim s; s.offboard = true; s.live(0, 5 * S);  // disarmed, lease live until 5.0
        s.arm_req = 5 * S;                           // auto_arm request with a fresh lease, script killed at 5.0
        CHECK(s.run(5 * S + TICK, 8 * S - TICK) == -1);
        s.armed = true;                              // PX4 reports armed at 8.0
        int64_t due = s.run(8 * S, 20 * S);
        CHECK(due == 8 * S);                         // overdue 7.0, State 8.0
    }
    {   // 18. an old auto_arm request (> 15 s) does not engage a later arm
        Sim s; s.offboard = true; s.arm_req = 1 * S;
        CHECK(s.run(1 * S, 20 * S) == -1);
        s.armed = true;
        CHECK(s.run(20 * S, 40 * S) == -1);
    }
    {   // 19. an auto_arm request engages only the first armed tick, and only in OFFBOARD
        Sim s; s.arm_req = 5 * S; s.offboard = false; CHECK(s.run(5 * S, 6 * S) == -1);
        s.armed = true;                              // the pilot armed in POSCTL
        CHECK(s.run(6 * S, 8 * S) == -1);
        s.offboard = true;                           // later switches to OFFBOARD with no script
        CHECK(s.run(8 * S, 30 * S) == -1);
    }
    if (failures) { std::printf("%d FAILED\n", failures); return 1; }
    std::printf("test_script_lease: 19 cases OK\n");
    return 0;
}
