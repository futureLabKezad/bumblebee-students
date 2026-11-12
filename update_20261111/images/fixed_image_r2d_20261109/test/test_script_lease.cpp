// r2d T25: scriptLeaseLandDue() without ROS. Build and run (from fixed_image_r2d_20261109):
//   g++ -std=c++17 -Wall -Wextra -Werror -I src/bumblebee/src/cpp test/test_script_lease.cpp -o /tmp/tsl && /tmp/tsl
#include "script_lease.h"
#include <cstdio>
#include <cstdlib>

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); ++failures; } } while (0)

static const int64_t S = 1000000000LL;      // 1 s
static const int64_t T = 2 * S;             // script_lease_timeout 2 s
static const int64_t R = kScriptLeaseRetryNs;

struct Sim {
    ScriptLease l;
    bool state_ok = true, armed = false, offboard = false;
    int64_t rx = 0;                          // last lease receipt, 0 = never
    bool tick(int64_t now, int64_t timeout = T) {
        return scriptLeaseLandDue(l, state_ok, armed, offboard, rx, now, timeout, R);
    }
    // ticks every 0.2 s from a to b (inclusive of a); returns the first due time, -1 = none
    int64_t run(int64_t a, int64_t b, int64_t timeout = T) {
        for (int64_t t = a; t <= b; t += S / 5)
            if (tick(t, timeout)) return t;
        return -1;
    }
};

int main() {
    {   // 1. the k1 case: script flying in OFFBOARD, killed at 10 s -> due just after 12 s, then every 1 s
        Sim s; s.armed = true; s.offboard = true;
        for (int64_t t = 0; t <= 10 * S; t += S / 2) { s.rx = t; CHECK(!s.tick(t)); }
        int64_t due = s.run(10 * S + S / 5, 20 * S);
        CHECK(due > 12 * S && due <= 12 * S + S / 5);
        CHECK(!s.tick(due + S / 2));                 // no retry before 1 s
        CHECK(s.tick(due + S));                      // /land failed and still OFFBOARD: retry
    }
    {   // 2. exactly the timeout is not late yet
        Sim s; s.armed = true; s.offboard = true; s.rx = 5 * S;
        CHECK(!s.tick(5 * S));
        CHECK(!s.tick(7 * S));
        CHECK(s.tick(7 * S + 1));
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
        Sim s; s.offboard = true; s.rx = 9 * S + 6 * S / 10; CHECK(!s.tick(9 * S + 8 * S / 10));
        s.armed = true;
        int64_t due = s.run(10 * S, 20 * S);
        CHECK(due > s.rx + T && due <= s.rx + T + S / 5);
    }
    {   // 6. pilot wins: pilot switches to POSCTL, the script dies -> never; back to OFFBOARD -> still never
        Sim s; s.armed = true; s.offboard = true;
        for (int64_t t = 0; t <= 5 * S; t += S / 2) { s.rx = t; CHECK(!s.tick(t)); }
        s.offboard = false;                          // pilot took over
        CHECK(s.run(5 * S + S / 5, 30 * S) == -1);
        s.offboard = true;                           // pilot back in OFFBOARD, script dead: as before r2d
        CHECK(s.run(30 * S, 60 * S) == -1);
        s.rx = 61 * S;                               // even a lease again in this arm cycle: stays off
        CHECK(s.run(61 * S, 70 * S) == -1);
    }
    {   // 7. our own AUTO.LAND (or a PX4 failsafe) then disarm, re-arm without a lease: never
        Sim s; s.armed = true; s.offboard = true; s.rx = 1 * S; CHECK(!s.tick(1 * S));
        s.offboard = false; CHECK(s.run(2 * S, 10 * S) == -1);
        s.armed = false; CHECK(!s.tick(11 * S));
        s.armed = true; s.offboard = true;
        CHECK(s.run(12 * S, 40 * S) == -1);
    }
    {   // 8. after a disarm a new arm cycle with a lease engages again
        Sim s; s.armed = true; s.offboard = true; s.rx = 1 * S; CHECK(!s.tick(1 * S));
        s.offboard = false; CHECK(!s.tick(2 * S));
        s.armed = false; CHECK(!s.tick(3 * S));
        s.armed = true; s.offboard = true; s.rx = 4 * S; CHECK(!s.tick(4 * S));
        int64_t due = s.run(4 * S + S / 5, 10 * S);
        CHECK(due > 6 * S && due <= 6 * S + S / 5);
    }
    {   // 9. FCU state unknown: never acts, and keeps the engagement for when the state is back
        Sim s; s.armed = true; s.offboard = true; s.rx = 1 * S; CHECK(!s.tick(1 * S));
        s.state_ok = false; CHECK(s.run(2 * S, 10 * S) == -1);
        s.state_ok = true; CHECK(s.tick(10 * S + S / 5));
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
        for (int64_t t = 0; t <= 60 * S; t += S / 5) {
            if (t % (7 * S / 5) == 0) s.rx = t;
            any = any || s.tick(t);
        }
        CHECK(!any);
    }
    if (failures) { std::printf("%d FAILED\n", failures); return 1; }
    std::printf("test_script_lease: 13 cases OK\n");
    return 0;
}
