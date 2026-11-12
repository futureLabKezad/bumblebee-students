#!/usr/bin/env python3
"""PROBE (T44, read-only for every package): r2h vpe_fix composed with the C8 freshness opt-in
(c8_judge_r2g_a9_20261110/candidate/parameters/vpe_freshness_optin.py), as vpe_diagnostic_entry.py composes them.
Offline bench (rosstub), poses with real header stamps (latency 30 ms). PIN_C33 of the LOADED optin module is set to
the file under test (no file is edited). Prints, per variant: publishes after a pause, the first samples, the
freshness notes."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

F = Path('/work/fixed_image_r2h_20261110')
sys.path.insert(0, str(F / 'src/bumblebee/test/vpe_fix_h2_r2/tests_r2'))
import bench as B  # noqa: E402
import rosstub  # noqa: E402

NS = B.NS
FRAME = 1.0 / 24.0
OPTIN = Path('/work/c8_judge_r2g_a9_20261110/candidate/parameters/vpe_freshness_optin.py')
VPES = {'r2g': '/work/fixed_image_r2g_20261110/src/bumblebee/src/python/vpe_fix.py',
        'r2h': str(F / 'src/bumblebee/src/python/vpe_fix.py')}


def load_variant(name, fresh):
    mod = B.load(VPES[name], 'vpe_%s_%s' % (name, fresh))
    if fresh:
        spec = importlib.util.spec_from_file_location('optin_%s' % name, OPTIN)
        fo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fo)
        fo.PIN_C33 = hashlib.sha256(Path(VPES[name]).read_bytes()).hexdigest()   # probe only
        fo.install(mod, enabled=True)
    return mod


class Sim:
    def __init__(self, mod, detector, frame=FRAME, latency=0.03):
        self.frame, self.latency = frame, latency
        self.b = B.boot(mod)
        self.clk = self.b.clock
        self.clk.ros_time_is_active = True
        self.node = self.b.node
        self.node.yaw_locked_callback(rosstub._Simple(True))
        self.detector = detector
        self.t0 = self.clk.t_ns
        for tm in self.node.timers:
            tm.next_due_ns = self.t0 + int(round(tm.period * NS))
        self.next_frame = self.t0
        self.next_state = self.t0
        self.frames = []

    def t(self):
        return (self.clk.t_ns - self.t0) / NS

    def msg(self, x, y=0.0, z=1.0):
        m = rosstub.PoseWithCovarianceStamped()
        m.pose.pose.position.x, m.pose.pose.position.y, m.pose.pose.position.z = x, y, z
        sec, nsec = divmod(self.clk.ros_ns() - int(self.latency * NS), NS)
        m.header.stamp = rosstub.SimpleNamespace(sec=int(sec), nanosec=int(nsec))
        return m

    def run(self, seconds):
        end = self.t0 + int(seconds * NS)
        while True:
            due = [tm.next_due_ns for tm in self.node.timers if not tm.cancelled]
            nxt = min(due + [self.next_frame, self.next_state])
            if nxt > end:
                self.clk.t_ns = end
                return
            self.clk.t_ns = nxt
            for tm in list(self.node.timers):
                if not tm.cancelled and tm.next_due_ns == nxt:
                    tm.cb()
                    tm.next_due_ns += int(round(tm.period * NS))
            if self.next_state == nxt:
                self.b.state(True, True, 'OFFBOARD')
                self.next_state += NS
            if self.next_frame == nxt:
                n, p = self.detector(self.t())
                if n >= 1 and p is not None:
                    self.node.aruco_map_callback(self.msg(*p))
                self.node.markers_used_callback(rosstub._Simple(n))
                self.frames.append((self.t(), n))
                self.next_frame += int(round(self.frame * NS))

    def sent(self, after=0.0):
        pub = self.node.vpe_pub
        pub = getattr(pub, 'wrapped', pub)
        return [((t - self.t0) / NS, m) for t, m in pub.sent if (t - self.t0) / NS >= after]


def det_pause(xs, p0=2.1, p1=3.1):
    back = []

    def det(t):
        if t < p0:
            return 2, (0.0, 0.0, 1.0)
        if t < p1:
            return 0, None
        back.append(t)
        k = len(back) - 1
        return 2, (xs[k] if k < len(xs) else 0.01, 0.0, 1.0)
    det.back = back
    return det


def blink(on=0.4, off=0.3):
    return lambda t: (1, (0.0, 0.0, 0.3)) if (t % (on + off)) < on else (0, None)


import random


def det_noisy(seed, p0=2.1, p1=3.1, sd=0.01):
    rnd = random.Random(seed)
    back = []

    def det(t):
        if t < p0:
            return 2, (rnd.gauss(0.0, sd), 0.0, 1.0)
        if t < p1:
            return 0, None
        back.append(t)
        return 2, (rnd.gauss(0.0, sd), 0.0, 1.0)
    det.back = back
    return det


noisy = {}
for name in ('r2g', 'r2h'):
    for fresh in (False, True):
        key = '%s%s' % (name, '+freshness' if fresh else '')
        rows = []
        for seed in range(20):
            det = det_noisy(seed)
            s = Sim(load_variant(name, fresh), det)
            s.run(5.0)
            back = det.back[0]
            after = s.sent(after=back)
            ts = [t for t, _ in after]
            first = ts[0] - back
            hold = [t for t in ts if t < ts[0] + 0.5]
            gap = max(b - a for a, b in zip(ts, ts[1:]) if a < ts[0] + 0.6)
            rows.append((round(first, 3), len(hold), round(gap, 3)))
        noisy[key] = {'first_s_median': sorted(r[0] for r in rows)[10], 'first_s_max': max(r[0] for r in rows),
                      'sent_in_0.5s_after_first_min': min(r[1] for r in rows),
                      'sent_in_0.5s_after_first_median': sorted(r[1] for r in rows)[10],
                      'max_gap_first_0.6s_max': max(r[2] for r in rows)}
print('NOISY', json.dumps(noisy, indent=1))
out = {}
for name in ('r2g', 'r2h'):
    for fresh in (False, True):
        key = '%s%s' % (name, '+freshness' if fresh else '')
        mod = load_variant(name, fresh)
        det = det_pause([0.0, 0.01, 0.06])
        s = Sim(mod, det)
        s.run(5.0)
        back = det.back[0]
        after = s.sent(after=back)
        first = after[0][0] if after else None
        hold = [(round(t - back, 3), round(m.pose.pose.position.x, 3)) for t, m in after if t < back + 0.7]
        gaps = [round(b - a, 3) for (a, _), (b, _) in zip(after, after[1:]) if b - a > 0.1]
        notes = dict(getattr(s.node, '_freshness_counts', {}))
        sb = Sim(load_variant(name, fresh), blink())
        sb.run(20.0)
        ts = [t for t, _ in sb.sent(after=1.0)]
        bp = [round(b - a, 2) for a, b in zip(ts, ts[1:]) if b - a > 0.4]
        out[key] = {'pause_first_after_back_s': None if first is None else round(first - back, 3),
                    'pause_samples_first_0.7s': hold[:25], 'n_in_first_0.7s': len(hold), 'gaps_gt_0.1_after_back': gaps,
                    'freshness_notes': notes, 'blink_publishes': len(ts), 'blink_pauses_gt_0.4': bp[:20],
                    'blink_notes': dict(getattr(sb.node, '_freshness_counts', {}))}
print('PAUSE', json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'pause_samples_first_0.7s'} for k, v in out.items()}, indent=1))
print('FIRST3', json.dumps({k: v['pause_samples_first_0.7s'][:3] for k, v in out.items()}))
