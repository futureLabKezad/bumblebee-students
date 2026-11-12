// r2i T46 (S9): fcuLinkSilentNs() without ROS, against the r2h rule (silence = now - last State) as the control.
// Build and run (from the r2i folder):
//   g++ -std=c++17 -Wall -Wextra -Werror -I src/bumblebee/src/cpp test/test_state_link.cpp -o /tmp/tsl && /tmp/tsl
// Model: FCU HEARTBEATs (and so MAVROS States) every 1 s at a phase; local_position every 1/30 s; the watchdog
// (publishSetpoint) ticks every 1/30 s; threshold state_watchdog_timeout 4.5 s (unchanged).
// What r2i promises (1 Hz HEARTBEATs make 4.0-5.0 s a phase-dependent band, whatever the rule):
//   - it never stops before the loss has really lasted 4.5 s;
//   - a HEARTBEAT-only gap of <= 4.0 s never stops, of >= 5.0 s always stops before it ends;
//   - when the whole link goes (the fast stream too), it stops 4.5 s after the loss began (to one fast sample).
#include "state_link.h"
#include <cstdio>

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::printf("FAIL line %d: %s\n", __LINE__, #cond); ++failures; } } while (0)

static const int64_t S = 1000000000LL;
static const int64_t MS = 1000000LL;
static const int64_t TH = 4500 * MS;            // state_watchdog_timeout (unchanged)
static const int64_t P = S;                     // HEARTBEAT period
static const int64_t TICK = S / 30;
static const int64_t FAST = S / 30;

struct Run {
    int64_t phase;              // HEARTBEATs at phase + k s
    int64_t drop_a, drop_b;     // HEARTBEATs in [drop_a, drop_b) are dropped (S9 proxy); -1: none
    int64_t link_a, link_b;     // everything (HEARTBEATs and the fast stream) is lost in [link_a, link_b); -1: none
    bool no_fast = false;       // no fast stream at all (fallback)
    bool lost_hb(int64_t t) const {
        return (drop_a >= 0 && t >= drop_a && t < drop_b) || (link_a >= 0 && t >= link_a && t < link_b);
    }
    int64_t last_hb(int64_t now) const {            // the last State received at or before now
        int64_t k = (now - phase) / S;
        for (int64_t t = phase + k * S; t > 0; t -= S)
            if (t <= now && !lost_hb(t)) return t;
        return 0;
    }
    int64_t last_fast(int64_t now) const {
        if (no_fast) return 0;
        int64_t t = now - now % FAST;
        while (link_a >= 0 && t >= link_a && t < link_b) t -= FAST;
        return t;
    }
    // first tick in [a, b] at which the rule fires; -1 = none
    int64_t fire(int64_t a, int64_t b, bool old_rule) const {
        for (int64_t t = a - a % TICK; t <= b; t += TICK) {
            int64_t sr = last_hb(t);
            int64_t silent = old_rule ? t - sr : fcuLinkSilentNs(t, sr, last_fast(t), P);
            if (silent > TH) return t;
        }
        return -1;
    }
};

int main() {
    // 1. C8 A10 heartbeat_13 exactly (proxy record, PX4 sim time): HEARTBEATs at k + 0.436 s
    {
        Run r{436 * MS, 63344 * MS, 66844 * MS, -1, -1};
        CHECK(r.last_hb(66900 * MS) == 62436 * MS);                 // 4 dropped: 63.436 .. 66.436
        CHECK(r.fire(62500 * MS, 67500 * MS, false) == -1);         // r2i: the short gap does not stop the flight
        int64_t old = r.fire(62500 * MS, 67500 * MS, true);
        CHECK(old > 0 && old < 67436 * MS);                         // control: r2h stopped it (as in the run)
        Run l{436 * MS, 69464 * MS, 74464 * MS, -1, -1};             // the long gap of the same run
        int64_t f = l.fire(69500 * MS, 76000 * MS, false);
        CHECK(f > 0 && f < 75436 * MS);                             // r2i stops before the HEARTBEAT returns
        CHECK(f - 69464 * MS >= TH);                                // and only after >= 4.5 s of real loss
        std::printf("heartbeat_13: short r2i none, r2h %.3f s; long r2i %.3f s (%.3f s after the drop began)\n",
                    old / 1e9, f / 1e9, (f - 69464 * MS) / 1e9);
    }
    // 2. S9 HEARTBEAT-only gaps at every phase (step 7 ms)
    int old_short_fires = 0, n = 0;
    for (int64_t ph = 0; ph < S; ph += 7 * MS, ++n) {
        int64_t a = 50 * S + 300 * MS;
        Run s{ph, a, a + 3500 * MS, -1, -1};
        CHECK(s.fire(a - S, a + 6 * S, false) == -1);               // a 3.5 s gap never stops (r2i)
        if (s.fire(a - S, a + 6 * S, true) > 0) ++old_short_fires;
        Run l{ph, a, a + 5000 * MS, -1, -1};
        int64_t f = l.fire(a - S, a + 8 * S, false);
        int64_t back = a + 5000 * MS;                               // the first HEARTBEAT after the gap is >= back
        while (l.lost_hb(back) || (back - ph) % S != 0) back += MS;
        CHECK(f > 0 && f < back);                                   // a 5.0 s gap always stops before it ends
        CHECK(f - a >= TH);                                         // never before 4.5 s of real loss
        Run m{ph, a, a + 4000 * MS, -1, -1};                        // 4.0 s: at most 4 HEARTBEATs lost, never stops
        CHECK(m.fire(a - S, a + 7 * S, false) == -1);
        Run b{ph, a, a + 4400 * MS, -1, -1};                        // 4.0-5.0 s: depends on the phase (1 Hz evidence),
        int64_t fb = b.fire(a - S, a + 7 * S, false);              // but never before 4.5 s of real loss
        CHECK(fb == -1 || fb - a >= TH);
    }
    CHECK(old_short_fires > n / 3);                                 // control: r2h stops on a share of the phases
    std::printf("S9 phases: %d, r2h stopped the 3.5 s gap in %d of them, r2i in none\n", n, old_short_fires);
    // 3. Real link loss / MAVROS kill (HEARTBEATs AND the fast stream stop at L), every phase
    int64_t worst_old = 0, worst_new = 0;
    for (int64_t ph = 0; ph < S; ph += 7 * MS) {
        int64_t L = 80 * S + 123 * MS;
        Run k{ph, -1, -1, L, L + 60 * S};
        int64_t f = k.fire(L - S, L + 7 * S, false), o = k.fire(L - S, L + 7 * S, true);
        CHECK(f > 0 && f - L > TH - FAST && f - L <= TH + FAST + TICK);   // r2i: 4.5 s after the loss, to a sample
        CHECK(f < L + 5 * S);                                             // before a MAVROS respawned after 5 s
        CHECK(o > 0 && o - L <= TH + TICK);
        if (f - L > worst_new) worst_new = f - L;
        if (o - L > worst_old) worst_old = o - L;
        Run q{ph, -1, -1, L, L + 4000 * MS};                              // a 4.0 s total loss: no stop (r2i)
        CHECK(q.fire(L - S, L + 7 * S, false) == -1);
        Run w{ph, -1, -1, L, L + 4400 * MS};                              // 4.4 s: never before 4.5 s of loss
        int64_t fw = w.fire(L - S, L + 7 * S, false);
        CHECK(fw == -1 || fw - L >= TH);
    }
    std::printf("link loss: stop after the loss began r2i <= %.3f s, r2h <= %.3f s\n", worst_new / 1e9, worst_old / 1e9);
    // 4. Fallbacks: no fast sample yet -> as r2h; no valid State -> now - 0
    CHECK(fcuLinkSilentNs(10 * S, 5 * S, 0, P) == 5 * S);
    CHECK(fcuLinkSilentNs(10 * S, 0, 9 * S, P) == 10 * S);
    CHECK(fcuLinkSilentNs(10 * S, 5 * S, 9 * S, 0) == 5 * S);
    CHECK(fcuLinkSilentNs(10 * S, 5 * S, 9 * S, P) == 4 * S);           // fast running: from the next HEARTBEAT due
    CHECK(fcuLinkSilentNs(10 * S, 5 * S, 5 * S + 300 * MS, P) == 4700 * MS);   // fast stopped 0.3 s after the State
    CHECK(fcuLinkSilentNs(10 * S, 5 * S, 4 * S, P) == 5 * S);           // fast stopped earlier: from the State
    if (failures) { std::printf("test_state_link: %d FAILED\n", failures); return 1; }
    std::printf("test_state_link: all cases OK\n");
    return 0;
}
