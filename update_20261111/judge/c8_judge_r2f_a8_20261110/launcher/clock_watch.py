#!/usr/bin/env python3
"""No ROS: every 10 ms compares CLOCK_REALTIME with CLOCK_MONOTONIC and logs any step of their offset > 50 ms.

Each realtime reading is bracketed by two monotonic readings; a sample whose bracket is wider than 5 ms (the process
was preempted between the reads) is skipped, so load cannot produce a fake step. First line: 'start'.
"""
import sys
import time

BRACKET = 0.005
STEP = 0.05


def offset():
    while True:
        m0 = time.monotonic()
        t = time.time()
        m1 = time.monotonic()
        if m1 - m0 <= BRACKET:
            return t - (m0 + m1) / 2


log = open(sys.argv[1], 'a', buffering=1)
prev = offset()
log.write(f'{time.monotonic():.6f},start,offset={prev:.6f}\n')
while True:
    time.sleep(0.01)
    off = offset()
    if abs(off - prev) > STEP:
        log.write(f'{time.monotonic():.6f},realtime_step,{off - prev:+.3f},wall={time.time():.3f}\n')
    prev = off
