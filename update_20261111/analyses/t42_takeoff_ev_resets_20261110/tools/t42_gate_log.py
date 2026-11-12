#!/usr/bin/env python3
"""T42 (READ ONLY): vpe_fix gate and aruco_detect events from ros.log (ROS wall stamps), per run, armed phase.
For each run: the vpe_fix gate switches (publish True/False with the reason), closed spans while armed+OFFBOARD,
the aruco_detect SEARCHING/NORMAL flips and single-marker frame pixel sizes in the same span, and the stamps of the
gate checks (tick phase). Usage: t42_gate_log.py RUN_DIR [...] -> one JSON line per run."""
import json, os, re, sys

RX = re.compile(r'\[(?:INFO|WARN|ERROR)\] \[(\d+\.\d+)\] \[(\w+)\]: (.*)$')

for run in sys.argv[1:]:
    ev = []
    with open(os.path.join(run, 'ros.log'), errors='replace') as f:
        for line in f:
            m = RX.search(line)
            if m:
                ev.append((float(m.group(1)), m.group(2), m.group(3).strip()))
    gate = [(t, msg) for t, n, msg in ev if n == 'vpe_publisher' and '-> publish=' in msg]
    arm_t = next((t for t, msg in gate if 'OFFBOARD' in msg or 'armed in manual' in msg), None)
    end_t = next((t for t, msg in gate if t > (arm_t or 0) and 'disarmed (warm-up)' in msg), None)
    closed, t_close = [], None
    for t, msg in gate:
        if arm_t is None or t < arm_t or (end_t and t >= end_t):
            continue
        if msg.endswith('publish=False') and t_close is None:
            t_close = (t, msg.split(' -> ')[0])
        elif msg.endswith('publish=True') and t_close is not None:
            closed.append({'from': round(t_close[0] - arm_t, 2), 'to': round(t - arm_t, 2), 'len': round(t - t_close[0], 2), 'why': t_close[1]})
            t_close = None
    if t_close is not None:
        closed.append({'from': round(t_close[0] - arm_t, 2), 'to': None, 'why': t_close[1]})
    # tick phase of the gate switches after the first one (1 Hz _gate_tick -> same fractional second)
    ph = sorted(round((t - arm_t) % 1.0, 2) for t, msg in gate if arm_t and t > arm_t + 0.05 and (not end_t or t < end_t))
    search = [(round(t - arm_t, 2), msg.split('->')[1].strip()[:9]) for t, n, msg in ev
              if n == 'aruco_detect' and 'searching profile' in msg and arm_t and arm_t - 1 <= t <= arm_t + 25]
    single = [(round(t - arm_t, 2), int(re.search(r'pixel=(\d+)', msg).group(1)), re.search(r'err=([\d.]+)', msg).group(1))
              for t, n, msg in ev if n == 'aruco_detect' and 'single-marker frame' in msg and arm_t and arm_t - 1 <= t <= arm_t + 25]
    rej = {}
    for t, n, msg in ev:
        if n == 'vpe_publisher' and 'rejected pose' in msg and arm_t and arm_t <= t <= arm_t + 25:
            k = msg.split('rejected pose ')[1].split()[0]
            rej[k] = rej.get(k, 0) + 1
    print(json.dumps({'run': os.path.basename(run.rstrip('/')), 'gate_first_offboard_wall': arm_t,
                      'closed_while_armed': closed, 'switch_phase_s': ph, 'aruco_search_flips_first25s': len(search),
                      'aruco_search': search[:30], 'single_marker_frames': single[:20], 'vpe_rejects_first25s': rej}))
