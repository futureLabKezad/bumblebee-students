#!/usr/bin/env python3
"""A10 (T44, chat 1 variant B): the vision pose leaves vpe_fix as on the drone. No ROS, no PX4, no Gazebo.
Offline bench of the final r2h image (rosstub; the REAL VpeFix class). Poses carry real header stamps (30 ms latency).
1) static: executor/vpe_diagnostic_entry.py never loads the freshness opt-in; the profile opt-in class (vpe_profile_optin
   make_node_class) overrides no pose-path method; the gate diagnostic only wraps _evaluate_gate;
2) composed as the A10 entry (candidate vpe_fix + the gate diagnostic on _evaluate_gate): a pause, then poses with 1 cm
   noise, 20 seeds: 16 of 16 samples in the 0.5 s after the first, no gap > 1/30 s + 1 ms; and the samples are exactly
   the plain vpe_fix ones (the diagnostic changes nothing);
3) control, A9 composition (+ freshness, its PIN set in memory to the file under test; no file edited): r2h loses samples
   after the pause (the reason for variant B);
4) control, A9 on r2g: r2g + freshness sends exactly what r2g sends (so the A9 runs on r2g are not affected).
Run: python3 -B -I tests/a10_vpe_as_drone.py"""
import ast
import hashlib
import importlib.util
import random
import sys
from pathlib import Path

D = Path('/work/c8_judge_r2j_a13_20261111')
A9 = Path('/work/c8_judge_r2g_a9_20261110')
IMG = Path('/work/fixed_image_r2j_20261111')
sys.path.insert(0, str(IMG / 'src/bumblebee/test/vpe_fix_h2_r2/tests_r2'))
import bench as B  # noqa: E402
import rosstub  # noqa: E402

NS = B.NS
FRAME = 1.0 / 24.0
CAND_VPE = D / 'candidate/parameters/vpe_fix.py'
R2G_VPE = Path('/work/fixed_image_r2g_20261110/src/bumblebee/src/python/vpe_fix.py')
FRESH = A9 / 'candidate/parameters/vpe_freshness_optin.py'
POSE_PATH = {'aruco_map_callback', 'publish_timer', 'markers_used_callback', 'markers_callback', 'yaw_locked_callback',
             '_reentry_pose', '_medoid', '_maybe_reseed', '_single_marker_fresh', '_multi_marker_fresh', '_apply_gate',
             '_evaluate_gate', '_gate_tick', 'state_callback', 'get_clock'}
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
N = [0]

# 1. static
entry = ast.parse((D / 'executor/vpe_diagnostic_entry.py').read_text())
names = {a.name for n in ast.walk(entry) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
assert 'vpe_freshness_optin' not in names and 'vpe_freshness_optin' not in ast.dump(entry), names
assert h(CAND_VPE) == h(IMG / 'src/bumblebee/src/python/vpe_fix.py')
prof = ast.parse((D / 'candidate/parameters/vpe_profile_optin.py').read_text())
mk = [n for n in prof.body if isinstance(n, ast.FunctionDef) and n.name == 'make_node_class'][0]
cls = [n for n in ast.walk(mk) if isinstance(n, ast.ClassDef)]
assert len(cls) == 1
over = {m.name for m in cls[0].body if isinstance(m, ast.FunctionDef)}
assert over and not over & POSE_PATH, over & POSE_PATH
wraps = [ast.unparse(n) for n in ast.walk(entry) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) for t in n.targets)]
assert wraps == ['vpe_fix.VpeFix._evaluate_gate = diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)'], wraps
print('static ok: no freshness in the entry; profile class overrides', sorted(over), '; one wrapper (_evaluate_gate)')


def variant(path, diag=False, fresh=False):
    N[0] += 1
    mod = B.load(str(path), 'a10_vpe_%d' % N[0])
    if fresh:
        spec = importlib.util.spec_from_file_location('a10_fresh_%d' % N[0], FRESH)
        fo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fo)
        fo.PIN_C33 = h(path)                     # control only: the A9 composition on this file
        fo.install(mod, enabled=True)
    if diag:
        spec = importlib.util.spec_from_file_location('a10_diag_%d' % N[0], D / 'executor/vpe_gate_diagnostic_p1.py')
        dg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dg)
        mod.VpeFix._evaluate_gate = dg.diagnostic_wrapper(mod.VpeFix._evaluate_gate)
    return mod


class Sim:
    def __init__(self, mod, detector, latency=0.03):
        self.latency = latency
        self.b = B.boot(mod)
        self.clk = self.b.clock
        self.clk.ros_time_is_active = True
        self.node = self.b.node
        self.node.yaw_locked_callback(rosstub._Simple(True))
        self.detector = detector
        self.t0 = self.clk.t_ns
        for tm in self.node.timers:
            tm.next_due_ns = self.t0 + int(round(tm.period * NS))
        self.next_frame = self.next_state = self.t0

    def msg(self, x):
        m = rosstub.PoseWithCovarianceStamped()
        m.pose.pose.position.x, m.pose.pose.position.y, m.pose.pose.position.z = x, 0.0, 1.0
        sec, nsec = divmod(self.clk.ros_ns() - int(self.latency * NS), NS)
        m.header.stamp = rosstub.SimpleNamespace(sec=int(sec), nanosec=int(nsec))
        return m

    def run(self, seconds):
        end = self.t0 + int(seconds * NS)
        while True:
            nxt = min([tm.next_due_ns for tm in self.node.timers if not tm.cancelled] + [self.next_frame, self.next_state])
            if nxt > end:
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
                n, x = self.detector((nxt - self.t0) / NS)
                if n:
                    self.node.aruco_map_callback(self.msg(x))
                self.node.markers_used_callback(rosstub._Simple(n))
                self.next_frame += int(round(FRAME * NS))

    def sent(self):
        pub = self.node.vpe_pub
        pub = getattr(pub, 'wrapped', pub)
        return [((t - self.t0) / NS, round(m.pose.pose.position.x, 9)) for t, m in pub.sent]


def det_noisy(seed):
    rnd = random.Random(seed)
    back = []

    def det(t):
        if 2.1 <= t < 3.1:
            return 0, None
        if t >= 3.1:
            back.append(t)
        return 2, rnd.gauss(0.0, 0.01)
    det.back = back
    return det


def after_pause(mod, seed):
    det = det_noisy(seed)
    s = Sim(mod, det)
    s.run(5.0)
    out = s.sent()
    ts = [t for t, _ in out if t >= det.back[0]]
    hold = [t for t in ts if t < ts[0] + 0.5 - 1e-9]
    gap = max(b - a for a, b in zip(ts, ts[1:]) if a < ts[0] + 0.6)
    return [(t, x) for t, x in out if t >= det.back[0]], len(hold), gap, len(out)


lost, whole = [], []
for seed in range(20):
    out, n, gap, _ = after_pause(variant(CAND_VPE, diag=True), seed)
    assert n == 16 and gap <= 1 / 30 + 0.001, (seed, n, gap)
    plain, _, _, _ = after_pause(variant(CAND_VPE), seed)
    assert out == plain, seed                                            # the diagnostic changes no sample
    _, cn, cgap, _ = after_pause(variant(CAND_VPE, diag=True, fresh=True), seed)
    lost.append((cn, round(cgap, 3)))
    g, _, _, ng = after_pause(variant(R2G_VPE), seed)
    gf, _, _, ngf = after_pause(variant(R2G_VPE, fresh=True), seed)
    assert g == gf, seed                                  # A9 on r2g: after the pause freshness changes no sample
    whole.append(ng - ngf)                                # whole run: freshness may end the pause start earlier (stamp age)
assert min(n for n, _ in lost) < 16 and max(g for _, g in lost) > 0.4, lost
print('A10 composition: 20/20 seeds 16 of 16 after the pause, gap <= 1/30 s, = plain vpe_fix; '
      'control A9 composition on r2h: min %d of 16, max gap %.2f s; r2g + freshness = r2g after the pause (20/20); '
      'whole run r2g minus r2g+freshness samples: %s' % (min(n for n, _ in lost), max(g for _, g in lost), sorted(set(whole))))
