#!/usr/bin/python3
"""param_events_probe.py - goal step 5b (Claude, 09.11.2026). SIMULATOR ONLY. Read-only measurement for F3.

F3 = the flight profile is sometimes applied only partly, because vpe_fix's PX4-parameter cache (filled only from
/parameter_events, vpe_fix.py:277-300, 383-405) misses some parameters. This probe measures, in the same run:
  A) every /parameter_events message from node /mavros/mavros, with a deep queue (KEEP_LAST 5000, RELIABLE);
  B) the same topic with the QoS vpe_fix uses (KEEP_LAST 200, RELIABLE) - a twin subscription; its callback is
     fast, so it shows the loss a queue of 200 gives to a FAST consumer (vpe_fix's own consumer is slower);
  C) how many parameters MAVROS holds at the end: /mavros/mavros/list_parameters (read-only service call);
and, for the watched names (the profile parameters), when each was first seen in A and B.
It publishes nothing, writes no parameter, calls no service except list_parameters.
Stops when RUN/stop_probe exists (or after --max-s), then writes RUN/param_events_probe.json (refuses to overwrite).
Usage: python3 param_events_probe.py RUN_DIR [--max-s N] [--watch NAME ...]
"""
import json
import os
import re
import sys
import time

import rclpy
from rcl_interfaces.msg import ParameterEvent
from rcl_interfaces.srv import ListParameters
from rclpy.node import Node
from rclpy.qos import QoSHistoryPolicy, QoSProfile, ReliabilityPolicy

MAVROS_NODE = '/mavros/mavros'
PX4_NAME = re.compile(r'^[A-Z][A-Z0-9_]*$')


class Probe(Node):
    def __init__(self, watch):
        super().__init__('bb_probe_param_events')
        self.t0 = time.monotonic()
        self.watch = set(watch)
        self.stats = {}
        for key, depth in (('A_depth5000', 5000), ('B_depth200', 200)):
            self.stats[key] = {'messages': 0, 'mavros_messages': 0, 'new': 0, 'changed': 0, 'deleted': 0,
                               'names': set(), 'arrivals': [], 'watch_first_s': {}, 'watch_count': {}}
            qos = QoSProfile(depth=depth, history=QoSHistoryPolicy.KEEP_LAST,
                             reliability=ReliabilityPolicy.RELIABLE)
            self.create_subscription(ParameterEvent, '/parameter_events',
                                     lambda msg, k=key: self.on_event(k, msg), qos)

    def on_event(self, key, msg):
        s = self.stats[key]
        s['messages'] += 1
        if msg.node != MAVROS_NODE:
            return
        now = round(time.monotonic() - self.t0, 3)
        s['mavros_messages'] += 1
        s['arrivals'].append(now)
        s['new'] += len(msg.new_parameters)
        s['changed'] += len(msg.changed_parameters)
        s['deleted'] += len(msg.deleted_parameters)
        for p in list(msg.new_parameters) + list(msg.changed_parameters):
            if PX4_NAME.match(p.name):
                s['names'].add(p.name)
            if p.name in self.watch:
                s['watch_first_s'].setdefault(p.name, now)
                s['watch_count'][p.name] = s['watch_count'].get(p.name, 0) + 1


def bursts(arr, gap=1.0):
    out, start, prev, n = [], None, None, 0
    for a in arr:
        if start is None:
            start, prev, n = a, a, 1
            continue
        if a - prev > gap:
            out.append({'from_s': start, 'to_s': prev, 'messages': n})
            start, n = a, 0
        prev = a
        n += 1
    if start is not None:
        out.append({'from_s': start, 'to_s': prev, 'messages': n})
    return out


def main():
    run_dir = sys.argv[1]
    args = sys.argv[2:]
    max_s = float(args[args.index('--max-s') + 1]) if '--max-s' in args else 1800
    watch = args[args.index('--watch') + 1:] if '--watch' in args else []
    out = os.path.join(run_dir, 'param_events_probe.json')
    if os.path.exists(out):
        sys.exit('refusing to overwrite ' + out)
    rclpy.init()
    node = Probe(watch)
    stop = os.path.join(run_dir, 'stop_probe')
    while rclpy.ok() and not os.path.exists(stop) and time.monotonic() - node.t0 < max_s:
        rclpy.spin_once(node, timeout_sec=0.05)
    # C) what MAVROS holds now
    held = None
    cli = node.create_client(ListParameters, MAVROS_NODE + '/list_parameters')
    if cli.wait_for_service(timeout_sec=5.0):
        fut = cli.call_async(ListParameters.Request(prefixes=[], depth=0))
        end = time.monotonic() + 10.0
        while not fut.done() and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
        if fut.done() and fut.result() is not None:
            names = list(fut.result().result.names)
            held = {'all_names': len(names), 'px4_like_names': sum(1 for n in names if PX4_NAME.match(n)),
                    'px4_names_sorted_sha_hint': len(set(n for n in names if PX4_NAME.match(n)))}
            held_set = set(n for n in names if PX4_NAME.match(n))
        else:
            held_set = None
    else:
        held_set = None
    res = {'t_end_s': round(time.monotonic() - node.t0, 1), 'mavros_held': held, 'watch': sorted(watch)}
    for key, s in node.stats.items():
        r = {k: v for k, v in s.items() if k not in ('names', 'arrivals')}
        r['distinct_px4_names'] = len(s['names'])
        r['bursts_gap1s'] = bursts(s['arrivals'])
        r['max_messages_in_100ms'] = 0
        arr = s['arrivals']
        j = 0
        for i in range(len(arr)):
            while arr[i] - arr[j] > 0.1:
                j += 1
            r['max_messages_in_100ms'] = max(r['max_messages_in_100ms'], i - j + 1)
        r['watch_never_seen'] = sorted(set(watch) - set(s['watch_first_s']))
        if held_set is not None:
            r['held_by_mavros_but_never_seen'] = len(held_set - s['names'])
            r['held_by_mavros_but_never_seen_examples'] = sorted(held_set - s['names'])[:40]
        res[key] = r
    with open(out, 'x', encoding='utf-8') as f:
        json.dump(res, f, indent=1)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
