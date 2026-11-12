#!/usr/bin/env python3
"""A9 static checks: the A8 -> A9 difference is exactly image r2g + the M1 logger restart (+ texts).
Judge, legacy copy, expectations and every candidate file are byte-identical to A8; EXPECT_4070 is the same; the
candidate manifest differs only in texts; run_sim.snapshot.sh only in the logger block; pins = A8 keys renamed with
every sha correct; r2g MANIFEST verified and pinned; product sums pass on the r2g install and fail on r2f.
Run: python -B -I tests/a9_checks.py (analysis venv)"""
import ast
import difflib
import hashlib
import json
import subprocess
from pathlib import Path

D = Path('/work/c8_judge_r2g_a9_20261110')
A8 = Path('/work/c8_judge_r2f_a8_20261110')
R2G = Path('/work/fixed_image_r2g_20261110')
R2F = Path('/work/fixed_image_r2f_20261110')
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
J = lambda p: json.loads(Path(p).read_text())


def expect(path):
    return [ast.literal_eval(n.value) for n in ast.parse(Path(path).read_text()).body
            if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'EXPECT_4070' for t in n.targets)][0]


E9, E8 = expect(D / 'tools/make_a9.py'), expect(A8 / 'tools/make_a8.py')
assert E9 == dict(E8, EKF2_OF_QMIN=(50, 6)), E9          # A9: + EKF2_OF_QMIN 50 (owner 10.11); MPC_LAND_CRWL not added
for rel in ('legacy/verify_package1b_gates_c8.py', 'expect/rc_real_params_4070.json',
            'expect/flight_real_params_4061.json', 'expect/rc_real_params_4061.json'):
    assert h(D / rel) == h(A8 / rel), rel
f8, f9 = J(A8 / 'expect/flight_real_params_4070.json'), J(D / 'expect/flight_real_params_4070.json')
assert {k: v for k, v in f9['parameters'].items() if k != 'EKF2_OF_QMIN'} == f8['parameters'] and 'EKF2_OF_QMIN' not in f8['parameters']
assert f9['parameters']['EKF2_OF_QMIN'] == {'value': 50, 'type': 6}
assert {k: v for k, v in f9.items() if k != 'parameters'} == {k: v for k, v in f8.items() if k != 'parameters'}
# judge: only the sha of the c8_4070 flight expectation changes (data)
d = [l for l in difflib.unified_diff((A8 / 'verify_flight_c8.py').read_text().splitlines(),
                                     (D / 'verify_flight_c8.py').read_text().splitlines(), lineterm='', n=0)
     if l[:1] in '+-' and not l.startswith(('+++', '---'))]
assert len(d) == 2 and d[0] == "-        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '%s')," % h(A8 / 'expect/flight_real_params_4070.json') \
    and d[1] == "+        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '%s')," % h(D / 'expect/flight_real_params_4070.json'), d
# a new name can be set only by the airframe: sitl_setup never writes it (not in the 20EC files, not in the profile)
import importlib.util
s2 = importlib.util.spec_from_file_location('ss', D / 'executor/sitl_setup.py'); ss = importlib.util.module_from_spec(s2); s2.loader.exec_module(ss)
for name in E9:
    if name in ss.KEEP_AIRFRAME:
        continue
    for f in ('/work/sim/ros_stack/flight_real_params.json', '/work/sim/ros_stack/rc_real_params.json', str(D / 'candidate/parameters/flight_profile.py')):
        assert name not in Path(f).read_text(), (name, f)
for p in (A8 / 'candidate').rglob('*'):
    if p.is_file() and p.name not in ('manifest.json', 'README.md'):
        assert h(p) == h(D / p.relative_to(A8)), p
ma, mb = J(A8 / 'candidate/manifest.json'), J(D / 'candidate/manifest.json')
assert ma['files'] == mb['files'] and set(ma) == set(mb)
assert [k for k in ma if ma[k] != mb[k]] == ['scope', 'origins'] or [k for k in ma if ma[k] != mb[k]] == ['origins', 'scope']
# run_sim.snapshot.sh: only the logger block
d = [l for l in difflib.unified_diff((A8 / 'executor/run_sim.snapshot.sh').read_text().splitlines(),
                                     (D / 'executor/run_sim.snapshot.sh').read_text().splitlines(), lineterm='', n=0)
     if l[:1] in '+-' and not l.startswith(('+++', '---'))]
assert [l for l in d if l.startswith('-')] == [
    '-  if [ "$($B/bin/px4-param show -q SDLOG_MODE)" = 0 ]; then $B/bin/px4-logger start -b 1000 -t; fi',
    '-  echo "c8: logger restarted (px4_first)"'], d
# executor: only these files differ from A8
diffs = sorted(str(p.relative_to(A8)) for p in (A8 / 'executor').rglob('*') if p.is_file() and h(p) != h(D / p.relative_to(A8)))
assert diffs == ['executor/PRODUCT_SHA256SUMS.txt', 'executor/run.sh', 'executor/run_sim.snapshot.sh',
                 'executor/sitl_setup.py', 'executor/vision_c8.launch.py'], diffs
# image r2g
subprocess.run(['sha256sum', '-c', '--quiet', 'MANIFEST_SHA256.txt'], cwd=R2G, check=True)
pins = J(D / 'pins/frozen_inputs_c8_r2g_a9_01.json')
assert pins['repo_files']['fixed_image_r2g_20261110/MANIFEST_SHA256.txt'] == h(R2G / 'MANIFEST_SHA256.txt')
assert pins['sdk_drone_py']['sha256'] == h(R2G / 'src/bumblebee/examples/drone.py') == pins['ledger_files']['@run/drone.py']
run = (D / 'executor/run.sh').read_text()
assert 'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % h(R2G / 'src/bumblebee/examples/drone.py') in run
assert 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % h(D / 'executor/PRODUCT_SHA256SUMS.txt') in run
ok = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2G / 'install', capture_output=True)
bad = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2F / 'install', capture_output=True)
assert ok.returncode == 0 and bad.returncode != 0
# pins: A8 keys renamed, every sha correct, nothing left of A8 / r2f
p8 = J(A8 / 'pins/frozen_inputs_c8_r2f_a8_01.json')
ren = lambda k: k.replace('c8_judge_r2f_a8_20261110/', 'c8_judge_r2g_a9_20261110/').replace('fixed_image_r2f_20261110/', 'fixed_image_r2g_20261110/')
AFP = 'goal_step5b_20261109/px4_etc/init.d-posix/airframes/4070_'
af9 = [k for k in pins['repo_files'] if k.startswith(AFP)]
assert len(af9) == 1 and pins['c8_target']['airframe_chain'][0] == Path(af9[0]).name
assert 'param set-default EKF2_OF_QMIN 50' in (Path('/work') / af9[0]).read_text().splitlines()
for g in ('repo_files', 'ledger_files'):
    assert {k for k in pins[g] if not k.startswith(AFP)} == {ren(k) for k in p8[g] if not k.startswith(AFP)}, g
    for k, v in pins[g].items():
        assert v == (h(R2G / 'src/bumblebee/examples/drone.py') if k == '@run/drone.py' else h(Path('/work') / k)), k
    assert not [k for k in pins[g] if 'r2f_a8' in k or 'fixed_image_r2f' in k]
assert set(pins['run_files']) == set(p8['run_files'])
assert pins['combined_files'] == mb['files'] and pins['combined_manifest_sha256'] == h(D / 'candidate/manifest.json')
launcher = (D / 'launcher/host_run_wsl_c8_r2e_b.sh').read_text()
assert 'C8_AIRFRAME=${C8_AIRFRAME:-4070};' in launcher and '/work/fixed_image_r2g_20261110/install}' in launcher
assert 'fixed_image_r2f' not in launcher and 'r2f_a8' not in launcher.replace('A8 v35 (not handed out)', '')
print('a9 ok: judge/expectations/candidate files = A8; image r2g pinned; run_sim only the logger block; pins renamed')
