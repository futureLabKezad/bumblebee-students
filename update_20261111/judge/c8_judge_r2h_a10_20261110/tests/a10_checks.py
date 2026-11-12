#!/usr/bin/env python3
"""A10 static checks: the A9 -> A10 difference is exactly the image FINAL r2h + variant B (no freshness opt-in) (+ texts).
Judge, legacy copy, expectations, run_sim.snapshot.sh, the freshness file and every other executor/candidate file are
byte-identical to A9; candidate vpe_fix = the r2h file; the loaded vpe_fix pins (profile opt-in, gate diagnostic) differ
from A9 in exactly their sha line and name the r2h sha; vpe_diagnostic_entry = the A9 statements minus the three
freshness statements, with the new helper sha; pins = A9 keys renamed with every sha correct; r2h MANIFEST verified and pinned; product sums pass on the r2h
install and fail on r2g. Run: python -B -I tests/a10_checks.py (analysis venv)"""
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

D = Path('/work/c8_judge_r2h_a10_20261110')
A9 = Path('/work/c8_judge_r2g_a9_20261110')
R2H = Path('/work/fixed_image_r2h_20261110')
R2G = Path('/work/fixed_image_r2g_20261110')
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
J = lambda p: json.loads(Path(p).read_text())
VG, VH = h(R2G / 'src/bumblebee/src/python/vpe_fix.py'), h(R2H / 'src/bumblebee/src/python/vpe_fix.py')
assert VG.startswith('3b8a93d4') and VG != VH


def changed_lines(rel):
    d = [l for l in difflib.unified_diff((A9 / rel).read_text().splitlines(), (D / rel).read_text().splitlines(), lineterm='', n=0)
         if l[:1] in '+-' and not l.startswith(('+++', '---'))]
    return [l for l in d if l.startswith('-')], [l for l in d if l.startswith('+')]


import ast as _ast
def _expect(path):
    return [_ast.literal_eval(n.value) for n in _ast.parse(Path(path).read_text()).body
            if isinstance(n, _ast.Assign) and any(getattr(x, 'id', None) == 'EXPECT_4070' for x in n.targets)][0]
assert _expect(D / 'tools/make_a10.py') == _expect(A9 / 'tools/make_a9.py')          # expectations unchanged
for rel in ('verify_flight_c8.py', 'legacy/verify_package1b_gates_c8.py', 'expect/flight_real_params_4070.json',
            'expect/rc_real_params_4070.json', 'expect/flight_real_params_4061.json', 'expect/rc_real_params_4061.json',
            'executor/run_sim.snapshot.sh'):
    assert h(D / rel) == h(A9 / rel), rel
# candidate
cand = sorted(str(p.relative_to(A9)) for p in (A9 / 'candidate').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A9)))
assert cand == ['candidate/README.md', 'candidate/manifest.json', 'candidate/parameters/vpe_fix.py',
                'candidate/parameters/vpe_profile_optin.py'], cand
assert h(D / 'candidate/parameters/vpe_freshness_optin.py') == h(A9 / 'candidate/parameters/vpe_freshness_optin.py')   # kept, not loaded
assert h(D / 'candidate/parameters/vpe_fix.py') == VH
for c, i in (('parameters/flight_profile.py', 'src/bumblebee/examples/flight_profile.py'),
             ('vision/aruco_detect.py', 'src/bumblebee/src/python/aruco_detect.py')):
    assert h(D / 'candidate' / c) == h(R2H / i) == h(R2G / i) == h(A9 / 'candidate' / c), c
for rel in ('candidate/parameters/vpe_profile_optin.py', 'executor/vpe_gate_diagnostic_p1.py'):
    minus, plus = changed_lines(rel)
    assert len(minus) == len(plus) == 1 and VG in minus[0] and VH in plus[0] and VH not in minus[0], (rel, minus, plus)
    assert plus[0].split(VH)[0] == minus[0].split(VG)[0].replace('-', '+', 1), rel          # the same statement, other sha
    assert VG not in (D / rel).read_text(), rel
import ast
s = (D / 'executor/vpe_diagnostic_entry.py').read_text()
assert h(D / 'executor/vpe_gate_diagnostic_p1.py') in s and h(A9 / 'executor/vpe_gate_diagnostic_p1.py') not in s
assert 'vpe_freshness_optin' not in s and 'install(' not in s
old = [ast.dump(n) for n in ast.parse((A9 / 'executor/vpe_diagnostic_entry.py').read_text().replace(
    h(A9 / 'executor/vpe_gate_diagnostic_p1.py'), h(D / 'executor/vpe_gate_diagnostic_p1.py'))).body]
new = [ast.dump(n) for n in ast.parse(s).body]
removed = [x for x in old if x not in new]
assert [x for x in old if x in new] == new and len(removed) == 3 and all('vpe_freshness_optin' in x for x in removed), removed
ma, mb = J(A9 / 'candidate/manifest.json'), J(D / 'candidate/manifest.json')
assert set(ma) == set(mb) and set(ma['files']) == set(mb['files'])
assert {k for k in ma['files'] if ma['files'][k] != mb['files'][k]} == {'parameters/vpe_fix.py', 'parameters/vpe_profile_optin.py'}
assert all(h(D / 'candidate' / k) == v for k, v in mb['files'].items())
assert ma['changed_from_combined_13'] == mb['changed_from_combined_13'] and ma['flight_accepted'] == mb['flight_accepted'] is False
# executor: only these files differ from A9
diffs = sorted(str(p.relative_to(A9)) for p in (A9 / 'executor').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A9)))
assert diffs == ['executor/PRODUCT_SHA256SUMS.txt', 'executor/run.sh', 'executor/sitl_setup.py',
                 'executor/tests/test_entry_order.log', 'executor/tests/test_entry_order.py',   # ed.2 (review A10 S4): A10 composition
                 'executor/vision_c8.launch.py', 'executor/vpe_diagnostic_entry.py', 'executor/vpe_gate_diagnostic_p1.py'], diffs
_log = (D / 'executor/tests/test_entry_order.log').read_text()
assert 'ALL OK' in _log and 'PASS a10_order' in _log and 'PASS freshness_refuses_r2h_control' in _log, _log
minus, plus = changed_lines('executor/sitl_setup.py')
assert len(minus) == len(plus) == 1 and 'fixed_image_r2h_20261110' in plus[0], plus
# image r2h
for f in ('MANIFEST_SHA256.txt', 'SHA256SUMS'):
    subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2H, check=True)
pins = J(D / 'pins/frozen_inputs_c8_r2h_a10_01.json')
assert pins['repo_files']['fixed_image_r2h_20261110/MANIFEST_SHA256.txt'] == h(R2H / 'MANIFEST_SHA256.txt')
assert pins['sdk_drone_py']['sha256'] == h(R2H / 'src/bumblebee/examples/drone.py') == pins['ledger_files']['@run/drone.py']
run = (D / 'executor/run.sh').read_text()
assert 'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % h(R2H / 'src/bumblebee/examples/drone.py') in run
assert 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % h(D / 'executor/PRODUCT_SHA256SUMS.txt') in run
ok = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2H / 'install', capture_output=True)
bad = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2G / 'install', capture_output=True)
assert ok.returncode == 0 and bad.returncode != 0
# installed vpe_fix of the product = the candidate copy (the run uses the candidate copy; both are r2h)
assert h(R2H / 'install/bumblebee/lib/bumblebee/vpe_fix.py') == VH
# pins: A9 keys renamed, every sha correct, nothing left of A9 / r2g
p9 = J(A9 / 'pins/frozen_inputs_c8_r2g_a9_01.json')
ren = lambda k: k.replace('c8_judge_r2g_a9_20261110/', 'c8_judge_r2h_a10_20261110/').replace('fixed_image_r2g_20261110/', 'fixed_image_r2h_20261110/')
for g in ('repo_files', 'ledger_files'):
    assert set(pins[g]) == {ren(k) for k in p9[g]}, g
    for k, v in pins[g].items():
        assert v == (h(R2H / 'src/bumblebee/examples/drone.py') if k == '@run/drone.py' else h(Path('/work') / k)), k
    assert not [k for k in pins[g] if 'r2g_a9' in k or 'fixed_image_r2g' in k]
assert set(pins['run_files']) == set(p9['run_files'])
for k, v in pins['run_files'].items():
    p = D / 'executor' / k if (D / 'executor' / k).exists() else R2H / 'src/bumblebee/examples' / k
    assert h(p) == v, k
assert pins['c8_target']['airframe_chain'] == p9['c8_target']['airframe_chain']
assert pins['legacy_verifier_sha256'] == p9['legacy_verifier_sha256']
assert pins['combined_files'] == mb['files'] and pins['combined_manifest_sha256'] == h(D / 'candidate/manifest.json')
launcher = (D / 'launcher/host_run_wsl_c8_r2e_b.sh').read_text()
assert 'C8_AIRFRAME=${C8_AIRFRAME:-4070};' in launcher and '/work/fixed_image_r2h_20261110/install}' in launcher
assert 'fixed_image_r2g' not in launcher and 'r2g_a9' not in launcher
print('a10 ok: judge/expectations/run_sim = A9; candidate vpe_fix = r2h, two loaded vpe pins = r2h sha only; entry = A9 minus freshness; image r2h pinned; pins renamed')
