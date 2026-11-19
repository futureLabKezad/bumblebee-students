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

TEST(ArmReply, AckTimeoutIsUnknown) {
    EXPECT_EQ(classifyArmReply(false, false, 0), ArmReply::UNKNOWN);
    EXPECT_EQ(classifyArmReply(true, false, 0), ArmReply::UNKNOWN);
    EXPECT_EQ(classifyArmReply(true, true, 0), ArmReply::ACCEPTED);
    EXPECT_EQ(classifyArmReply(true, false, 1), ArmReply::REJECTED);
}
TEST(ArmSend, RequiresFreshHeartbeatAndKnownRejection) {
    mavros_msgs::msg::State state;
    state.connected = true; state.mode = "OFFBOARD"; state.armed = false;
    EXPECT_TRUE(armSendAllowed(state, 10*kSec, 10*kSec, ArmReply::REJECTED, 7*kSec, 9*kSec));
    EXPECT_FALSE(armSendAllowed(state, 9*kSec, 10*kSec, ArmReply::REJECTED, 7*kSec, 8*kSec));
    EXPECT_FALSE(armSendAllowed(state, 10*kSec, 10*kSec, ArmReply::UNKNOWN, 7*kSec, 9*kSec));
    EXPECT_FALSE(armSendAllowed(state, 10*kSec, 10*kSec, ArmReply::ACCEPTED, 7*kSec, 9*kSec));
    EXPECT_FALSE(armSendAllowed(state, 10*kSec, 10*kSec, ArmReply::REJECTED, 7*kSec, 10*kSec));
    state.armed = true;
    EXPECT_FALSE(armSendAllowed(state, 10*kSec, 10*kSec, ArmReply::REJECTED, 7*kSec, 9*kSec));
}
TEST(Disarm, DoesNotTakeControlFromPilot) {
    mavros_msgs::msg::State state; state.armed = true; state.mode = "POSCTL";
    EXPECT_FALSE(disarmAllowed(state));
    state.mode = "OFFBOARD"; EXPECT_TRUE(disarmAllowed(state));
    state.armed = false; state.mode = "POSCTL"; EXPECT_TRUE(disarmAllowed(state));
}

TEST(FlightRun, IdleAndResetBoundaries) {
    EXPECT_EQ(flightRunStart(10, 100, 500000100), 10);
    EXPECT_EQ(flightRunStart(10, 100, 500000101), 500000101);
    EXPECT_EQ(flightRunStart(10, 100, 99), 99);
}
TEST(FlightRun, QueuedArmAfterLand) {
    EXPECT_TRUE(queuedArmBlocked(9000000000, 1000000000, 4000000000));
    EXPECT_FALSE(queuedArmBlocked(9000000000, 4500000000, 4000000000));
    EXPECT_FALSE(queuedArmBlocked(9000000000, 1000000000, 0));
    EXPECT_FALSE(queuedArmBlocked(1000000000, 1000000000, 4000000000));
}


TEST(SetpointResume, GapBoundaryAndClockReset) {
    EXPECT_FALSE(setpointResumeBlocked(true, true, 10*kSec, 10*kSec));
    EXPECT_FALSE(setpointResumeBlocked(true, true, 10*kSec, 11*kSec));
    EXPECT_TRUE(setpointResumeBlocked(true, true, 10*kSec, 11*kSec + 1));
    EXPECT_TRUE(setpointResumeBlocked(true, true, 10*kSec, 10*kSec - 1));
}

TEST(SetpointResume, InactiveInitialAndDisarmedDoNotBlock) {
    EXPECT_FALSE(setpointResumeBlocked(false, true, 10*kSec, 20*kSec));
    EXPECT_FALSE(setpointResumeBlocked(true, true, 0, 20*kSec));
    EXPECT_FALSE(setpointResumeBlocked(true, false, 10*kSec, 20*kSec));
    // Armed and an unresolved ARM use the same guarded=true path.
    EXPECT_TRUE(setpointResumeBlocked(true, true, 10*kSec, 20*kSec));
}

TEST(SetpointResume, PausedRosClockAndLostHeartbeatsWithLiveWallTimer) {
    // Neither ROS time nor FCU State reception is an input to this guard.
    // /clock can remain paused and State silent for 3.5 s while wall ticks
    // continue at 30 Hz: their gaps stay below the 1 s publisher bound.
    int64_t last_tick = 10*kSec;
    for (int i = 1; i <= 105; ++i) {
        const int64_t tick = 10*kSec + i*(kSec/30);
        EXPECT_FALSE(setpointResumeBlocked(true, true, last_tick, tick));
        last_tick = tick;
    }
    // A process stall is different: a single gap over 1 s must stop it.
    EXPECT_TRUE(setpointResumeBlocked(true, true, last_tick, last_tick + kSec + 1));
}

TEST(SetpointResume, NewExplicitStreamStartDoesNotInheritOldGap) {
    // resetSetpoint clears the old checkpoint; an explicit accepted serve()
    // records a new one before enabling the timer.
    EXPECT_FALSE(setpointResumeBlocked(false, true, 0, 30*kSec));
    EXPECT_FALSE(setpointResumeBlocked(true, true, 30*kSec, 30*kSec + kSec/30));
}


TEST(SetpointResume, MultipleQueuedCommandsRequireStateAfterTheStop) {
    EXPECT_FALSE(publisherResumeStateAllowed(true, true, true, 10*kSec, 13*kSec));
    EXPECT_FALSE(publisherResumeStateAllowed(true, true, true, 13*kSec, 13*kSec));
    // A first refusal leaves the gate in place for the second queued request.
    EXPECT_FALSE(publisherResumeStateAllowed(true, true, true, 10*kSec, 13*kSec));
    EXPECT_TRUE(publisherResumeStateAllowed(true, true, true, 14*kSec, 13*kSec));
}

TEST(SetpointResume, FreshLandingPilotAndDisconnectedStatesCannotResume) {
    EXPECT_FALSE(publisherResumeStateAllowed(true, true, false, 14*kSec, 13*kSec));
    EXPECT_FALSE(publisherResumeStateAllowed(false, true, true, 14*kSec, 13*kSec));
    EXPECT_TRUE(publisherResumeStateAllowed(true, false, false, 14*kSec, 13*kSec));
    // Outside a post-stall resume, the existing checkState/checkPilot remains authoritative.
    EXPECT_TRUE(publisherResumeStateAllowed(true, true, true, 10*kSec, 0));
}

TEST(SetpointResume, CapturedTickExposesPauseBetweenFirstGuardAndCommit) {
    const int64_t previous_tick = 10*kSec - kSec/30;
    const int64_t captured_tick = 10*kSec;
    EXPECT_FALSE(setpointResumeBlocked(true, true, previous_tick, captured_tick));
    // SIGSTOP occurs after the first guard. Committing the captured value
    // keeps the pause visible even if ROS stamp capture runs after SIGCONT.
    const int64_t resumed_wall = 12*kSec;
    EXPECT_TRUE(setpointResumeBlocked(true, true, captured_tick, resumed_wall));
    // The rejected implementation refreshed the checkpoint after SIGCONT.
    EXPECT_FALSE(setpointResumeBlocked(true, true, resumed_wall, resumed_wall));
}

TEST(SetpointResume, FinalGuardDetectsPauseBeforeFreshRosStampCapture) {
    const int64_t committed_tick = 10*kSec;
    EXPECT_FALSE(setpointResumeBlocked(true, true, committed_tick, committed_tick + kSec/30));
    // A ROS stamp freshly obtained after the pause does not alter the steady
    // checkpoint; the common publish() guard must still stop old intent.
    const int64_t fresh_ros_stamp = kEpoch + 2*kSec;
    EXPECT_GT(fresh_ros_stamp, kEpoch);
    EXPECT_TRUE(setpointResumeBlocked(true, true, committed_tick, 12*kSec));
}

TEST(SetpointResume, StartingExplicitStreamCannotBypassFinalGuard) {
    // A new serve() has setpoint_type != NONE but its timer is still canceled.
    // The final common guard treats it as a starting stream, unlike the first
    // timer/serve guard. It uses the same pre-guard checkpoint under mutex_.
    const int64_t captured_tick = 10*kSec;
    EXPECT_FALSE(setpointResumeBlocked(false, true, captured_tick, 12*kSec));
    EXPECT_TRUE(setpointResumeBlocked(true, true, captured_tick, 12*kSec));
    EXPECT_FALSE(setpointResumeBlocked(true, true, captured_tick, 11*kSec));
    EXPECT_TRUE(setpointResumeBlocked(true, true, captured_tick, 11*kSec + 1));
}
