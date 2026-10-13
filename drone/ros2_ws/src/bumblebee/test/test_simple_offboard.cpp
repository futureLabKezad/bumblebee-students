// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Unit tests for the navigate segment math in simple_offboard.cpp (spec S1, A1):
// progress runs on a monotonic clock, is clamped to [0, 1], and the setpoint
// always lies on the segment start -> target.
//
// The node is a single file, so the test compiles that very file without its
// main(); nothing here starts ROS.

#define SIMPLE_OFFBOARD_NO_MAIN
#include "simple_offboard.cpp"

#include <limits>

#include <gtest/gtest.h>

namespace {

constexpr int64_t kSec = 1000000000LL;
// A real ROS/epoch stamp (Oct 2025) in nanoseconds: the order of magnitude that
// broke the old code when serve() published with Time(0)
constexpr int64_t kEpoch = 1760000000LL * kSec + 123456789LL;

Point point(double x, double y, double z) {
    Point p;
    p.x = x;
    p.y = y;
    p.z = z;
    return p;
}

// Distance from p to the segment a -> b
double distanceToSegment(const Point& p, const Point& a, const Point& b) {
    double dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    double len2 = dx * dx + dy * dy + dz * dz;
    double t = len2 > 0 ? ((p.x - a.x) * dx + (p.y - a.y) * dy + (p.z - a.z) * dz) / len2 : 0;
    t = std::clamp(t, 0.0, 1.0);
    double ex = a.x + dx * t - p.x, ey = a.y + dy * t - p.y, ez = a.z + dz * t - p.z;
    return std::sqrt(ex * ex + ey * ey + ez * ez);
}

void expectPointEq(const Point& actual, const Point& expected) {
    EXPECT_DOUBLE_EQ(actual.x, expected.x);
    EXPECT_DOUBLE_EQ(actual.y, expected.y);
    EXPECT_DOUBLE_EQ(actual.z, expected.z);
}

}  // namespace

TEST(NavigateProgress, RealEpochStampsKeepPrecision) {
    // 1 m at 0.5 m/s: 0.25 s in = 12.5 %, 1 ms resolution survives epoch-sized values
    EXPECT_NEAR(navigateProgress(1.0, 0.5, kEpoch, kEpoch + kSec / 4), 0.125, 1e-12);
    EXPECT_NEAR(navigateProgress(1.0, 0.5, kEpoch, kEpoch + kSec / 1000), 0.0005, 1e-12);
    EXPECT_NEAR(navigateProgress(2.0, 0.5, kEpoch, kEpoch + 2 * kSec), 0.5, 1e-12);
    EXPECT_DOUBLE_EQ(navigateProgress(1.0, 0.5, kEpoch, kEpoch), 0.0);
}

TEST(NavigateProgress, OldTimeZeroLurchIsGone) {
    // The A1 bug: start stamped with a real epoch time, "now" = Time(0) from
    // serve() -> elapsed ~ -1.76e9 s -> the setpoint went ~1e8 m behind the start.
    EXPECT_DOUBLE_EQ(navigateProgress(1.0, 0.5, kEpoch, 0), 0.0);
    Point start = point(1, 2, 0.1), target = point(1, 2, 1.1);
    expectPointEq(navigateSetpoint(start, target, 0.5, kEpoch, 0), start);
    // and the reverse (start = Time(0), now = epoch) stops at the target, never beyond
    EXPECT_DOUBLE_EQ(navigateProgress(1.0, 0.5, 0, kEpoch), 1.0);
    expectPointEq(navigateSetpoint(start, target, 0.5, 0, kEpoch), target);
}

TEST(NavigateProgress, ClockStepBackHoldsStart) {
    Point start = point(0, 0, 1), target = point(3, -4, 1);
    for (int64_t step : {kSec / 100, kSec, 3600 * kSec, int64_t(400) * 24 * 3600 * kSec}) {
        EXPECT_DOUBLE_EQ(navigateProgress(5.0, 0.5, kEpoch, kEpoch - step), 0.0) << step;
        expectPointEq(navigateSetpoint(start, target, 0.5, kEpoch, kEpoch - step), start);
    }
}

TEST(NavigateProgress, ClockStepForwardStopsAtTarget) {
    Point start = point(0, 0, 1), target = point(3, -4, 1);
    for (int64_t step : {10 * kSec, 3600 * kSec, int64_t(400) * 24 * 3600 * kSec}) {
        EXPECT_DOUBLE_EQ(navigateProgress(5.0, 0.5, kEpoch, kEpoch + step), 1.0) << step;
        expectPointEq(navigateSetpoint(start, target, 0.5, kEpoch, kEpoch + step), target);
    }
}

TEST(NavigateProgress, ZeroDistanceIsComplete) {
    Point here = point(0.3, -0.2, 0.9);
    EXPECT_DOUBLE_EQ(navigateProgress(0.0, 0.5, kEpoch, kEpoch), 1.0);
    EXPECT_DOUBLE_EQ(navigateProgress(0.0, 0.0, kEpoch, kEpoch - kSec), 1.0);
    for (int64_t now : {kEpoch - kSec, kEpoch, kEpoch + kSec, int64_t(0)}) {
        Point sp = navigateSetpoint(here, here, 0.5, kEpoch, now);
        EXPECT_TRUE(std::isfinite(sp.x) && std::isfinite(sp.y) && std::isfinite(sp.z));
        expectPointEq(sp, here);
    }
}

TEST(NavigateProgress, InvalidSpeedHoldsStart) {
    Point start = point(0, 0, 0), target = point(1, 0, 0);
    const double inf = std::numeric_limits<double>::infinity();
    for (double speed : {0.0, -0.5, std::nan(""), inf}) {
        EXPECT_DOUBLE_EQ(navigateProgress(1.0, speed, kEpoch, kEpoch + 10 * kSec), 0.0) << speed;
        expectPointEq(navigateSetpoint(start, target, speed, kEpoch, kEpoch + 10 * kSec), start);
    }
}

TEST(NavigateProgress, ClampedAndOnSegment) {
    Point start = point(-1, 2, 0.5), target = point(2, -2, 1.5);
    double length = std::sqrt(9.0 + 16.0 + 1.0);
    const double speed = 0.7;
    double previous = -1;
    // From 5 s before the start to 5 s after the end, every 10 ms
    int64_t end_ns = static_cast<int64_t>(length / speed * kSec);
    for (int64_t t = -5 * kSec; t <= end_ns + 5 * kSec; t += kSec / 100) {
        double p = navigateProgress(length, speed, kEpoch, kEpoch + t);
        ASSERT_GE(p, 0.0);
        ASSERT_LE(p, 1.0);
        ASSERT_GE(p, previous);  // monotonic in time
        previous = p;
        Point sp = navigateSetpoint(start, target, speed, kEpoch, kEpoch + t);
        ASSERT_LT(distanceToSegment(sp, start, target), 1e-9) << t;
        if (t > 0 && t < end_ns) {
            // moves at the requested speed
            double moved = std::sqrt(std::pow(sp.x - start.x, 2) + std::pow(sp.y - start.y, 2) +
                                     std::pow(sp.z - start.z, 2));
            ASSERT_NEAR(moved, speed * t * 1e-9, 1e-9) << t;
        }
    }
    EXPECT_DOUBLE_EQ(previous, 1.0);
}

TEST(NavigateProgress, MidpointAndExactTarget) {
    Point start = point(0, 0, 1), target = point(2, 0, 1);
    expectPointEq(navigateSetpoint(start, target, 0.5, kEpoch, kEpoch + 2 * kSec), point(1, 0, 1));
    // At and past the end the target comes back bit-exact (no rounding drift)
    Point odd_start = point(0.1, 0.2, 0.3), odd_target = point(0.7, -0.11, 1.3);
    Point at_end = navigateSetpoint(odd_start, odd_target, 0.5, kEpoch, kEpoch + 100 * kSec);
    EXPECT_EQ(at_end.x, odd_target.x);
    EXPECT_EQ(at_end.y, odd_target.y);
    EXPECT_EQ(at_end.z, odd_target.z);
}

TEST(SteadyClock, IsMonotonic) {
    int64_t previous = steadyNs();
    for (int i = 0; i < 1000; i++) {
        int64_t t = steadyNs();
        ASSERT_GE(t, previous);
        previous = t;
    }
}
