// r2i (T46, 11.11.2026, S9 heartbeat): how long the FCU link has been silent, for the state watchdog of
// simple_offboard (publishSetpoint). No ROS: unit-tested by test/test_state_link.cpp of the r2i folder with plain g++.
//
// MAVROS publishes /mavros/state once per FCU HEARTBEAT (1 Hz). r2h counted the silence from the last State, so a
// loss was overestimated by up to one heartbeat period: a 3.5 s HEARTBEAT gap that swallowed 4 heartbeats gave 5.0 s
// without State and stopped the flight (C8 A10 heartbeat_13, proven from its proxy record).
// The loss began after the last State and no later than the next HEARTBEAT was due (state_rx + period). A fast FCU
// stream (local_position, ~30 Hz) tells which:
//   - it stopped inside that interval (MAVROS died, the UART link dropped): the loss began when it stopped;
//   - it is still running (only HEARTBEATs are missing): the loss began when the next HEARTBEAT was due.
// Without a valid State (state_rx <= 0) or without any fast sample yet (fast_rx <= 0): as r2h, from state_rx.
#pragma once
#include <cstdint>

inline int64_t fcuLinkSilentNs(int64_t now, int64_t state_rx, int64_t fast_rx, int64_t period) {
    if (state_rx <= 0 || fast_rx <= 0 || period <= 0) return now - state_rx;
    int64_t start = fast_rx;
    if (start < state_rx) start = state_rx;                     // stopped before the last State: no earlier than it
    if (start > state_rx + period) start = state_rx + period;   // still running: from the next HEARTBEAT due
    return now - start;
}
