#!/usr/bin/env python3
"""A10 offline check (ROS sourced, no node started): class composition of the VPE entry of THIS package
(executor/vpe_diagnostic_entry.py, variant B of chat 1, T44). Replaces the flight_trial_07 / combined_04 check of the
freshness order (A9 and older: see /work/c8_judge_r2g_a9_20261110/executor/tests/test_entry_order.py), review A10 S4.
1) the A10 order (diagnostic wrapper on the r2h VpeFix, then the profile class) composes; NodeClass MRO = ProfileVpe ->
   VpeFix -> Node; _evaluate_gate resolves to the diagnostic wrapper; no FreshnessMixin; ProfileVpe defines no pose-path
   method; the loaded vpe_fix is the one the diagnostic pins (TARGET_SHA256 = r2h).
2) control: the freshness opt-in kept in the candidate (A9 file, pin = r2g vpe_fix) refuses the r2h vpe_fix, so it cannot
   be active by accident.
Each case runs in a fresh interpreter (module state). Run with ROS sourced (as tests/test_c8_b2.sh d2_*)."""
import json
import subprocess
import sys

D = '/work/c8_judge_r2j_a12_20261111'
COMMON = f'''
import hashlib, importlib.util, sys, json
from pathlib import Path
sys.path.insert(0, {D + '/candidate/parameters'!r})
helper = Path({D + '/executor/vpe_gate_diagnostic_p1.py'!r})
spec = importlib.util.spec_from_file_location('gate_diagnostic', helper)
diagnostic = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostic)
import vpe_fix, vpe_profile_optin
c33 = vpe_fix.VpeFix
'''
GOOD = COMMON + '''
POSE = {'aruco_map_callback', 'publish_timer', 'markers_used_callback', 'markers_callback', 'yaw_locked_callback',
        '_reentry_pose', '_medoid', '_maybe_reseed', '_single_marker_fresh', '_multi_marker_fresh', '_apply_gate',
        '_evaluate_gate', '_gate_tick', 'state_callback', 'get_clock'}
vpe_fix.VpeFix._evaluate_gate = diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
Node = vpe_profile_optin.make_node_class(vpe_fix.VpeFix)
mro = [c.__name__ for c in Node.__mro__]
own = {k for k, v in Node.__dict__.items() if callable(v) or isinstance(v, staticmethod)}
print(json.dumps({'mro': mro, 'same_class': vpe_fix.VpeFix is c33,
  'gate_is_wrapper': Node._evaluate_gate is vpe_fix.VpeFix.__dict__['_evaluate_gate'] and hasattr(Node._evaluate_gate, '__wrapped__'),
  'sha_is_target': hashlib.sha256(Path(vpe_fix.__file__).read_bytes()).hexdigest() == diagnostic.TARGET_SHA256,
  'mixin_in_mro': 'FreshnessMixin' in mro, 'profile_pose_overrides': sorted(own & POSE)}))
'''
BAD = COMMON + '''
import vpe_freshness_optin
try:
    vpe_freshness_optin.install(vpe_fix, enabled=True); print(json.dumps({'refused': None}))
except ValueError as e:
    print(json.dumps({'refused': str(e)}))
'''
ok = True
for name, code in (('a10_order', GOOD), ('freshness_refuses_r2h_control', BAD)):
    r = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
    out = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-800:]
    print(name, out)
    try:
        d = json.loads(out)
    except ValueError:
        d = {}
    if name == 'a10_order':
        good = (d.get('mro', [])[:2] == ['ProfileVpe', 'VpeFix'] and d.get('same_class') and d.get('gate_is_wrapper')
                and d.get('sha_is_target') and d.get('mixin_in_mro') is False and d.get('profile_pose_overrides') == [])
    else:
        good = d.get('refused') == 'c33 VPE source PIN mismatch'
    print('PASS' if good else 'FAIL', name)
    ok &= bool(good)
print('ALL OK' if ok else 'FAILED')
sys.exit(0 if ok else 1)
