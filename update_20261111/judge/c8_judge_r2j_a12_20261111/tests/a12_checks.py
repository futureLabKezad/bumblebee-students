#!/usr/bin/env python3
"""A12 static checks: the A11 -> A12 difference is exactly the image r2j + the runner's camera TF of the 20EC reference
(+ texts and paths). Judge, legacy copy, expectations, run_sim.snapshot.sh, gate.py and every candidate file are A11's
bytes; vision_c8.launch.py differs in exactly the TF translation line ((0.05, 0, -0.07) -> (0.081, 0, -0.034), angles
unchanged); pins = A11 keys renamed with every sha correct; r2j MANIFEST verified and pinned; product sums pass on the
r2j install and fail on r2i. Run: python -B -I tests/a12_checks.py (analysis venv)"""
import ast
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

D = Path('/work/c8_judge_r2j_a12_20261111')
A11 = Path('/work/c8_judge_r2i_a11_20261111')
R2J = Path('/work/fixed_image_r2j_20261111')
R2I = Path('/work/fixed_image_r2i_20261111')
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
J = lambda p: json.loads(Path(p).read_text())


def expect(path):
    return [ast.literal_eval(n.value) for n in ast.parse(Path(path).read_text()).body
            if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'EXPECT_4070' for t in n.targets)][0]


def changed_lines(rel):
    d = [l for l in difflib.unified_diff((A11 / rel).read_text().splitlines(), (D / rel).read_text().splitlines(), lineterm='', n=0)
         if l[:1] in '+-' and not l.startswith(('+++', '---'))]
    return [l for l in d if l.startswith('-')], [l for l in d if l.startswith('+')]


assert expect(D / 'tools/make_a12.py') == expect(A11 / 'tools/make_a11.py')
for rel in ('verify_flight_c8.py', 'legacy/verify_package1b_gates_c8.py', 'expect/flight_real_params_4070.json',
            'expect/rc_real_params_4070.json', 'expect/flight_real_params_4061.json', 'expect/rc_real_params_4061.json',
            'executor/run_sim.snapshot.sh', 'executor/gate.py', 'executor/vpe_gate_diagnostic_p1.py', 'executor/vpe_diagnostic_entry.py'):
    assert h(D / rel) == h(A11 / rel), rel
cand = sorted(str(p.relative_to(A11)) for p in (A11 / 'candidate').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A11)))
assert cand == ['candidate/README.md', 'candidate/manifest.json'], cand
ma, mb = J(A11 / 'candidate/manifest.json'), J(D / 'candidate/manifest.json')
assert ma['files'] == mb['files'] and set(ma) == set(mb)
for c, i in (('parameters/flight_profile.py', 'src/bumblebee/examples/flight_profile.py'),
             ('parameters/vpe_fix.py', 'src/bumblebee/src/python/vpe_fix.py'), ('vision/aruco_detect.py', 'src/bumblebee/src/python/aruco_detect.py')):
    assert h(D / 'candidate' / c) == h(R2J / i) == h(R2I / i), c
diffs = sorted(str(p.relative_to(A11)) for p in (A11 / 'executor').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A11)))
assert diffs == ['executor/PRODUCT_SHA256SUMS.txt', 'executor/run.sh', 'executor/sitl_setup.py',
                 'executor/tests/test_entry_order.py', 'executor/vision_c8.launch.py'], diffs
# the runner camera TF: only the translation line, reference numbers, angles unchanged
minus, plus = changed_lines('executor/vision_c8.launch.py')
tf = [l for l in minus if "'--x'" in l], [l for l in plus if "'--x'" in l]
assert tf[0] == ["-            '--x', '0.05', '--y', '0', '--z', '-0.07', '--yaw', '-1.5707963',"], minus
assert len(tf[1]) == 1 and tf[1][0].startswith("+            '--x', '0.081', '--y', '0', '--z', '-0.034', '--yaw', '-1.5707963',"), plus
assert [l for l in minus if l not in tf[0]] and all('c8_judge_r2i_a11' in l for l in minus if l not in tf[0])
assert "'--pitch', '0', '--roll', '3.1415926'" in (D / 'executor/vision_c8.launch.py').read_text()
img = (R2J / 'src/bumblebee/launch/bumblebee.launch.py').read_text()
assert "['0.081', '0', '-0.034', '-1.5707963', '0', '3.1415926'," in img          # the same TF as the image launch
minus, plus = changed_lines('executor/sitl_setup.py')
assert len(minus) == len(plus) == 1 and 'fixed_image_r2j_20261111' in plus[0], plus
for f in ('MANIFEST_SHA256.txt', 'SHA256SUMS'):
    subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2J, check=True)
pins = J(D / 'pins/frozen_inputs_c8_r2j_a12_01.json')
assert pins['repo_files']['fixed_image_r2j_20261111/MANIFEST_SHA256.txt'] == h(R2J / 'MANIFEST_SHA256.txt')
assert pins['sdk_drone_py']['sha256'] == h(R2J / 'src/bumblebee/examples/drone.py') == pins['ledger_files']['@run/drone.py']
run = (D / 'executor/run.sh').read_text()
assert 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % h(D / 'executor/PRODUCT_SHA256SUMS.txt') in run
ok = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2J / 'install', capture_output=True)
bad = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2I / 'install', capture_output=True)
assert ok.returncode == 0 and bad.returncode != 0
p11 = J(A11 / 'pins/frozen_inputs_c8_r2i_a11_01.json')
ren = lambda k: k.replace('c8_judge_r2i_a11_20261111/', 'c8_judge_r2j_a12_20261111/').replace('fixed_image_r2i_20261111/', 'fixed_image_r2j_20261111/')
for g in ('repo_files', 'ledger_files'):
    assert set(pins[g]) == {ren(k) for k in p11[g]}, g
    for k, v in pins[g].items():
        assert v == (h(R2J / 'src/bumblebee/examples/drone.py') if k == '@run/drone.py' else h(Path('/work') / k)), k
    assert not [k for k in pins[g] if 'r2i_a11' in k or 'fixed_image_r2i' in k]
assert set(pins['run_files']) == set(p11['run_files'])
for k, v in pins['run_files'].items():
    p = D / 'executor' / k if (D / 'executor' / k).exists() else R2J / 'src/bumblebee/examples' / k
    assert h(p) == v, k
assert pins['c8_target']['airframe_chain'] == p11['c8_target']['airframe_chain']
assert pins['legacy_verifier_sha256'] == p11['legacy_verifier_sha256']
assert pins['combined_files'] == mb['files'] and pins['combined_manifest_sha256'] == h(D / 'candidate/manifest.json')
launcher = (D / 'launcher/host_run_wsl_c8_r2e_b.sh').read_text()
assert '/work/fixed_image_r2j_20261111/install}' in launcher and 'fixed_image_r2i' not in launcher and 'v39-c8-r2j-a12' in launcher
print('a12 ok: judge/expectations/run_sim/gate/candidate = A11; runner camera TF = the reference (angles unchanged); '
      'image r2j pinned; product sums r2j; pins renamed')
