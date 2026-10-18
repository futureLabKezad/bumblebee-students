#!/usr/bin/env python3
"""Passive Gazebo /stats recorder (SIM ONLY, sends nothing): sim time vs wall time.

Writes one JSON line per message to --out and prints a summary of 5 s wall windows:
RTF = delta sim_time / delta monotonic wall. System python3 (gz python bindings)."""
import argparse, json, threading, time
from gz.msgs10.world_stats_pb2 import WorldStatistics
from gz.transport13 import Node
ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--seconds', type=float, required=True)
ap.add_argument('--label', required=True); a = ap.parse_args()
rows, lock = [], threading.Lock()
def cb(msg):
    with lock:
        rows.append((time.monotonic(), msg.sim_time.sec + msg.sim_time.nsec * 1e-9, msg.real_time_factor, msg.paused))
node = Node(); assert node.subscribe(WorldStatistics, '/stats', cb), 'cannot subscribe /stats'
t0 = time.monotonic(); time.sleep(a.seconds)
with lock: data = list(rows)
with open(a.out, 'a') as f:
    for w, s, r, p in data: f.write(json.dumps({'label': a.label, 'wall': w, 'sim': s, 'gz_rtf': r, 'paused': p}) + '\n')
wins = []
if data:
    i = 0
    while True:
        j = i
        while j < len(data) and data[j][0] - data[i][0] < 5.0: j += 1
        if j >= len(data): break
        wins.append((data[j][1] - data[i][1]) / (data[j][0] - data[i][0])); i = j
total = (data[-1][1] - data[0][1]) / (data[-1][0] - data[0][0]) if len(data) > 1 else None
print(json.dumps({'label': a.label, 'messages': len(data), 'rtf_total': total,
                  'rtf_5s_min': min(wins) if wins else None, 'rtf_5s_max': max(wins) if wins else None,
                  'windows': [round(x, 3) for x in wins]}))
