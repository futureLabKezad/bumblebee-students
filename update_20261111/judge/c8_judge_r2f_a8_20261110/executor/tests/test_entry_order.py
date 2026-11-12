#!/usr/bin/env python3
"""flight_trial_07 offline check (ROS sourced, no node started): class composition of the VPE entry with combined_04.
1) the 07 order (freshness on clean c33, then diagnostic wrapper) composes; NodeClass MRO = parameters -> FreshVpe ->
   FreshnessMixin -> c33 VpeFix; _evaluate_gate resolves to the diagnostic wrapper; freshness pose timeout 0.5 s.
2) control: the 06 order (wrapper first) makes install() refuse ('loaded c33 method was modified').
Each case runs in a fresh interpreter (module state)."""
import subprocess, sys, json
C04 = '/work/parallel_work/20261015/integration/combined_09/parameters'
COMMON = f'''
import hashlib, importlib.util, sys, json
from pathlib import Path
sys.path.insert(0, {C04!r})
helper = Path('/work/sim/ros_stack/vpe_gate_diagnostic.py')
spec = importlib.util.spec_from_file_location('gate_diagnostic', helper)
diagnostic = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostic)
import vpe_fix, vpe_freshness_optin, vpe_profile_optin
c33 = vpe_fix.VpeFix
'''
GOOD = COMMON + '''
vpe_freshness_optin.install(vpe_fix, enabled=True)
vpe_fix.VpeFix._evaluate_gate = diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
Node = vpe_profile_optin.make_node_class(vpe_fix.VpeFix)
mro = [c.__name__ for c in Node.__mro__]
print(json.dumps({'mro': mro, 'fresh_is_sub_of_c33': issubclass(vpe_fix.VpeFix, c33),
  'c33_gate_untouched': '_evaluate_gate' in c33.__dict__ and c33.__dict__['_evaluate_gate'] is not vpe_fix.VpeFix.__dict__.get('_evaluate_gate'),
  'gate_is_wrapper': Node._evaluate_gate is vpe_fix.VpeFix.__dict__['_evaluate_gate'],
  'pose_timeout_ns': Node._freshness_pose_timeout_ns,
  'mixin_in_mro': 'FreshnessMixin' in mro}))
'''
BAD = COMMON + '''
vpe_fix.VpeFix._evaluate_gate = diagnostic.diagnostic_wrapper(vpe_fix.VpeFix._evaluate_gate)
try:
    vpe_freshness_optin.install(vpe_fix, enabled=True); print(json.dumps({'refused': None}))
except ValueError as e:
    print(json.dumps({'refused': str(e)}))
'''
ok = True
for name, code in (('07_order', GOOD), ('06_order_control', BAD)):
    r = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
    out = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-800:]
    print(name, out)
    if name == '07_order':
        d = json.loads(out)
        good = (d['mixin_in_mro'] and d['fresh_is_sub_of_c33'] and d['gate_is_wrapper'] and d['pose_timeout_ns'] == 500_000_000
                and d['mro'].index('FreshVpe') < d['mro'].index('FreshnessMixin') < d['mro'].index('VpeFix'))
        print('PASS' if good else 'FAIL', name); ok &= good
    else:
        good = 'loaded c33 method was modified: _evaluate_gate' in out
        print('PASS' if good else 'FAIL', name); ok &= good
print('ALL OK' if ok else 'FAILED')
sys.exit(0 if ok else 1)
