#!/usr/bin/env python3
"""A11 static checks: the A10 -> A11 difference is exactly the image r2i (+ texts and paths).
Judge, legacy copy, expectations, run_sim.snapshot.sh, the freshness file and every other executor/candidate file are
byte-identical to A10 edition 2; candidate vpe_fix = the r2i file; the two loaded vpe_fix pins differ from A10 in exactly
their sha line and name the r2i sha; vpe_diagnostic_entry differs in exactly the helper sha line; pins = A10 keys
renamed with every sha correct; r2i MANIFEST verified and pinned; product sums pass on the r2i install and fail on r2h.
Run: python -B -I tests/a11_checks.py (analysis venv)"""
import ast
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

D = Path('/work/c8_judge_r2i_a11_20261111')
A10 = Path('/work/c8_judge_r2h_a10_20261110')
R2I = Path('/work/fixed_image_r2i_20261111')
R2H = Path('/work/fixed_image_r2h_20261110')
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
J = lambda p: json.loads(Path(p).read_text())
VH, VI = h(R2H / 'src/bumblebee/src/python/vpe_fix.py'), h(R2I / 'src/bumblebee/src/python/vpe_fix.py')
assert VH.startswith('66d806ba') and VI.startswith('f0dc7c18')


def expect(path):
    return [ast.literal_eval(n.value) for n in ast.parse(Path(path).read_text()).body
            if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'EXPECT_4070' for t in n.targets)][0]


def changed_lines(rel):
    d = [l for l in difflib.unified_diff((A10 / rel).read_text().splitlines(), (D / rel).read_text().splitlines(), lineterm='', n=0)
         if l[:1] in '+-' and not l.startswith(('+++', '---'))]
    return [l for l in d if l.startswith('-')], [l for l in d if l.startswith('+')]


assert expect(D / 'tools/make_a11.py') == expect(A10 / 'tools/make_a10.py')
for rel in ('verify_flight_c8.py', 'legacy/verify_package1b_gates_c8.py', 'expect/flight_real_params_4070.json',
            'expect/rc_real_params_4070.json', 'expect/flight_real_params_4061.json', 'expect/rc_real_params_4061.json',
            'executor/run_sim.snapshot.sh', 'candidate/parameters/vpe_freshness_optin.py'):
    assert h(D / rel) == h(A10 / rel), rel
# candidate
cand = sorted(str(p.relative_to(A10)) for p in (A10 / 'candidate').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A10)))
assert cand == ['candidate/README.md', 'candidate/manifest.json', 'candidate/parameters/vpe_fix.py',
                'candidate/parameters/vpe_profile_optin.py'], cand
assert h(D / 'candidate/parameters/vpe_fix.py') == VI
for c, i in (('parameters/flight_profile.py', 'src/bumblebee/examples/flight_profile.py'),
             ('vision/aruco_detect.py', 'src/bumblebee/src/python/aruco_detect.py')):
    assert h(D / 'candidate' / c) == h(R2I / i) == h(R2H / i) == h(A10 / 'candidate' / c), c
for rel in ('candidate/parameters/vpe_profile_optin.py', 'executor/vpe_gate_diagnostic_p1.py'):
    minus, plus = changed_lines(rel)
    assert len(minus) == len(plus) == 1 and VH in minus[0] and VI in plus[0], (rel, minus, plus)
    assert plus[0].split(VI)[0] == minus[0].split(VH)[0].replace('-', '+', 1), rel
    assert VH not in (D / rel).read_text(), rel
minus, plus = changed_lines('executor/vpe_diagnostic_entry.py')
assert len(minus) == len(plus) == 1, (minus, plus)
s = (D / 'executor/vpe_diagnostic_entry.py').read_text()
assert h(D / 'executor/vpe_gate_diagnostic_p1.py') in s and 'vpe_freshness_optin' not in s and 'install(' not in s
ma, mb = J(A10 / 'candidate/manifest.json'), J(D / 'candidate/manifest.json')
assert set(ma) == set(mb) and set(ma['files']) == set(mb['files'])
assert {k for k in ma['files'] if ma['files'][k] != mb['files'][k]} == {'parameters/vpe_fix.py', 'parameters/vpe_profile_optin.py'}
assert all(h(D / 'candidate' / k) == v for k, v in mb['files'].items())
assert ma['changed_from_combined_13'] == mb['changed_from_combined_13'] and mb['flight_accepted'] is False
# executor: only these files differ from A10
diffs = sorted(str(p.relative_to(A10)) for p in (A10 / 'executor').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A10)))
assert diffs == ['executor/PRODUCT_SHA256SUMS.txt', 'executor/run.sh', 'executor/sitl_setup.py',
                 'executor/tests/test_entry_order.py',   # paths only; its log is the same text (rerun on A11)
                 'executor/vision_c8.launch.py', 'executor/vpe_diagnostic_entry.py', 'executor/vpe_gate_diagnostic_p1.py'], diffs
minus, plus = changed_lines('executor/sitl_setup.py')
assert len(minus) == len(plus) == 1 and 'fixed_image_r2i_20261111' in plus[0], plus
_log = (D / 'executor/tests/test_entry_order.log').read_text()
assert 'ALL OK' in _log and 'PASS a10_order' in _log and 'PASS freshness_refuses_r2h_control' in _log, _log
# image r2i
for f in ('MANIFEST_SHA256.txt', 'SHA256SUMS'):
    subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2I, check=True)
pins = J(D / 'pins/frozen_inputs_c8_r2i_a11_01.json')
assert pins['repo_files']['fixed_image_r2i_20261111/MANIFEST_SHA256.txt'] == h(R2I / 'MANIFEST_SHA256.txt')
assert pins['sdk_drone_py']['sha256'] == h(R2I / 'src/bumblebee/examples/drone.py') == pins['ledger_files']['@run/drone.py']
run = (D / 'executor/run.sh').read_text()
assert 'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % h(R2I / 'src/bumblebee/examples/drone.py') in run
assert 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % h(D / 'executor/PRODUCT_SHA256SUMS.txt') in run
ok = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2I / 'install', capture_output=True)
bad = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2H / 'install', capture_output=True)
assert ok.returncode == 0 and bad.returncode != 0
assert h(R2I / 'install/bumblebee/lib/bumblebee/vpe_fix.py') == VI
# pins: A10 keys renamed, every sha correct, nothing left of A10 / r2h
p10 = J(A10 / 'pins/frozen_inputs_c8_r2h_a10_01.json')
ren = lambda k: k.replace('c8_judge_r2h_a10_20261110/', 'c8_judge_r2i_a11_20261111/').replace('fixed_image_r2h_20261110/', 'fixed_image_r2i_20261111/')
for g in ('repo_files', 'ledger_files'):
    assert set(pins[g]) == {ren(k) for k in p10[g]}, g
    for k, v in pins[g].items():
        assert v == (h(R2I / 'src/bumblebee/examples/drone.py') if k == '@run/drone.py' else h(Path('/work') / k)), k
    assert not [k for k in pins[g] if 'r2h_a10' in k or 'fixed_image_r2h' in k]
assert set(pins['run_files']) == set(p10['run_files'])
for k, v in pins['run_files'].items():
    p = D / 'executor' / k if (D / 'executor' / k).exists() else R2I / 'src/bumblebee/examples' / k
    assert h(p) == v, k
assert pins['c8_target']['airframe_chain'] == p10['c8_target']['airframe_chain']
assert pins['legacy_verifier_sha256'] == p10['legacy_verifier_sha256']
assert pins['combined_files'] == mb['files'] and pins['combined_manifest_sha256'] == h(D / 'candidate/manifest.json')
launcher = (D / 'launcher/host_run_wsl_c8_r2e_b.sh').read_text()
assert 'C8_AIRFRAME=${C8_AIRFRAME:-4070};' in launcher and '/work/fixed_image_r2i_20261111/install}' in launcher
assert 'fixed_image_r2h' not in launcher and 'r2h_a10' not in launcher and 'v38-c8-r2i-a11' in launcher
print('a11 ok: judge/expectations/run_sim/freshness = A10; candidate vpe_fix = r2i, two loaded vpe pins = r2i sha only; '
      'image r2i pinned; product sums r2i; pins renamed')
