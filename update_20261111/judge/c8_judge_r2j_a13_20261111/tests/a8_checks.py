#!/usr/bin/env python3
"""A8 static checks (no Gazebo, no PX4, no node). Run: python -B -I tests/a8_checks.py (analysis venv: the judge imports).
1) identity c8_4070: airframe 4070, the c8_4061 names, its own pinned expectation files; a changed file is refused;
2) expectations: rc = the 4061 file; flight = the 4061 file + EXPECT_4070 exactly (read from tools/make_a13.py);
   every EXPECT_4070 value = a 'param set-default' line of airframe 4070, which sources the unchanged 4061 file;
   sitl_setup keeps BAT1_SOURCE from the airframe and never writes SDLOG_MODE (not in the 20EC files or the profile);
3) the judge differs from A7 only by the c8_4070 comment and table row (no logic line);
4) candidate: image copies = r2f bytes; vpe_profile_optin.py differs from A7 only in the airframe check; manifest files
   differ only in that sha; 5) pins: every entry matches the files now, A7 keys renamed + 3 new keys;
6) product: r2f MANIFEST verifies and is pinned; run.sh pins the product sums of r2f; the r2e install fails them.
"""
import ast
import difflib
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

D = Path('/work/c8_judge_r2j_a13_20261111')
A7 = Path('/work/c8_judge_r2e_a7_20261110')
R2F = Path('/work/fixed_image_r2j_20261111')
R2E = Path('/work/fixed_image_r2e_20261109')
AF = Path('/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes')
AF4070 = AF / '4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50'   # A9: the Simulator's 4070 with EKF2_OF_QMIN 50
AF4061 = AF / '4061_gz_bumblebee_candidate_4060_disarm_rcl_obl'
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
J = lambda p: json.loads(Path(p).read_text())

src = (D / 'tools/make_a13.py').read_text()
EXPECT = [ast.literal_eval(n.value) for n in ast.parse(src).body
          if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'EXPECT_4070' for t in n.targets)][0]
assert EXPECT['BAT1_SOURCE'] == (0, 6) and EXPECT['SDLOG_MODE'] == (1, 6), EXPECT   # the two owner decisions

# 1. identity
s = importlib.util.spec_from_file_location('vj', D / 'verify_flight_c8.py'); vj = importlib.util.module_from_spec(s); s.loader.exec_module(vj)
I = vj.IDENTITIES
assert sorted(I) == ['c8_4061', 'c8_4070', 'c8_4074', 'rel3_4030'], sorted(I)   # A13: + c8_4074
assert I['c8_4070']['autostart'] == 4070 and I['c8_4070']['names'] == I['c8_4061']['names'] and len(I['c8_4070']['names']) == 18
rp = I['c8_4070']['real_params']
assert {k: (str(p), x) for k, (p, x) in rp.items()} == {
    'flight_real_params.json': (str(D / 'expect/flight_real_params_4070.json'), h(D / 'expect/flight_real_params_4070.json')),
    'rc_real_params.json': (str(D / 'expect/rc_real_params_4070.json'), h(D / 'expect/rc_real_params_4070.json'))}
vj.use_identity('c8_4070'); m = vj.load_legacy(); assert m.AUTOSTART == 4070 and m.REAL_PARAMS['flight_real_params.json'].endswith('_4070.json')
vj.use_identity('c8_4061'); m = vj.load_legacy(); assert m.AUTOSTART == 4061 and m.REAL_PARAMS['flight_real_params.json'].endswith('_4061.json')
p, x = I['c8_4070']['real_params']['flight_real_params.json']
I['c8_4070']['real_params']['flight_real_params.json'] = (p, '0' * 64)
vj.use_identity('c8_4070')
try:
    vj.load_legacy(); sys.exit('FAIL: a wrong expectation sha was accepted')
except ValueError:
    pass

# 2. expectations and the airframe
assert h(D / 'expect/rc_real_params_4070.json') == h(A7 / 'expect/rc_real_params_4061.json')
a, b = J(A7 / 'expect/flight_real_params_4061.json'), J(D / 'expect/flight_real_params_4070.json')
assert {k: v for k, v in a.items() if k != 'parameters'} == {k: v for k, v in b.items() if k != 'parameters'}
diff = {k: (a['parameters'].get(k), b['parameters'].get(k)) for k in set(a['parameters']) | set(b['parameters'])
        if a['parameters'].get(k) != b['parameters'].get(k)}
assert set(diff) == set(EXPECT) and all(diff[k][1] == {'value': v, 'type': t} for k, (v, t) in EXPECT.items()), diff
af = AF4070.read_text().splitlines()
assert '. ${R}etc/init.d-posix/airframes/' + AF4061.name in af
sets = {l.split()[2]: l.split()[3] for l in af if l.startswith('param set-default ')}
assert set(sets) == set(EXPECT), sets
for k, (v, t) in EXPECT.items():
    assert float(sets[k]) == float(v), (k, sets[k], v)
pins = J(D / 'pins/frozen_inputs_c8_r2j_a13_01.json')
assert pins['repo_files']['goal_step5b_20261109/px4_etc/init.d-posix/airframes/' + AF4070.name] == h(AF4070)
assert pins['repo_files']['goal_step5b_20261109/px4_etc/init.d-posix/airframes/' + AF4061.name] == h(AF4061)
s2 = importlib.util.spec_from_file_location('ss', D / 'executor/sitl_setup.py'); ss = importlib.util.module_from_spec(s2); s2.loader.exec_module(ss)
assert 'BAT1_SOURCE' in ss.KEEP_AIRFRAME
for f in ('/work/sim/ros_stack/flight_real_params.json', '/work/sim/ros_stack/rc_real_params.json'):
    t = Path(f).read_text()
    assert 'SDLOG_MODE' not in t, f
assert 'SDLOG_MODE' not in (D / 'candidate/parameters/flight_profile.py').read_text()

# 3. judge: one row
d = [l for l in difflib.unified_diff((A7 / 'verify_flight_c8.py').read_text().splitlines(),
                                     (D / 'verify_flight_c8.py').read_text().replace('#  c8_4074:   A13 (T55, 11.11.2026): airframe 4074 of the Simulator (T52) = 4070 v2 + the 10 sensor positions of the\n#             20EC reference; the same 18 names and the same expect/*_4070.json (no EKF2_*_POS / MIN_RNG is judged).\n', '').replace("    'c8_4074': dict(autostart=4074, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={\n        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '9e471a6e3fcad40958fab2eaa040713479759ef815581ebeb9761590634900d1'),\n        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),\n", '').splitlines(), lineterm='', n=0)   # A13 row: a13_checks
     if l[:1] in '+-' and not l.startswith(('+++', '---'))]
assert not [l for l in d if l.startswith('-')], d
added = [l[1:] for l in d]
assert len(added) == 5 and added[0].startswith('#  c8_4070:') and added[1].startswith('#  ') \
    and added[2].startswith("    'c8_4070': dict(autostart=4070, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={") \
    and added[3].startswith("        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '") \
    and added[4].startswith("        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '"), added
assert h(D / 'legacy/verify_package1b_gates_c8.py') == h(A7 / 'legacy/verify_package1b_gates_c8.py') == pins['legacy_verifier_sha256']

# 4. candidate
for c, i in (('parameters/flight_profile.py', 'src/bumblebee/examples/flight_profile.py'),
             ('parameters/vpe_fix.py', 'src/bumblebee/src/python/vpe_fix.py'), ('vision/aruco_detect.py', 'src/bumblebee/src/python/aruco_detect.py')):
    assert h(D / 'candidate' / c) == h(R2F / i), c   # A10/A11: image copies = image bytes (A11: r2i)
    assert h(R2F / i) == h(A7 / 'candidate' / c) or c == 'parameters/vpe_fix.py', c   # A10: only vpe_fix changed since A7
d = [l for l in difflib.unified_diff((A7 / 'candidate/parameters/vpe_profile_optin.py').read_text().splitlines(),
                                     (D / 'candidate/parameters/vpe_profile_optin.py').read_text().splitlines(), lineterm='', n=0)
     if l[:1] in '+-' and not l.startswith(('+++', '---'))]
norm = lambda l: l[1:].replace('4061', 'X').replace('4070', 'X').replace('4074', 'X').replace('  # A8: airframe X; A13: X', '').replace('  # A8: airframe X', '') \
    .replace('3b8a93d4d08983694186766b0259fa6fa6b4167079c4078cf402a908d02e9725', 'V').replace('66d806baf5ef6884bdc7e1636289e90dd55964f8f69ed0ffa13be2e23f5e6958', 'V').replace('  # A10: r2h vpe_fix (c8-r2e-b..A9: r2e = r2g)', '  # c8-r2e-b: r2e vpe_fix') \
    .replace('f0dc7c18f2fa24ffd7c9baffd92e8f3dd723c0521c27eedb4eeef408faa8642d', 'V').replace('  # A11: r2i vpe_fix (c8-r2e-b..A9: r2e = r2g; A10: r2h)', '  # c8-r2e-b: r2e vpe_fix')   # A10, A11
assert [norm(l) for l in d if l.startswith('-')] == [norm(l) for l in d if l.startswith('+')] and len(d) == 6, d   # A10: + the vpe_fix pin line
ma, mb = J(A7 / 'candidate/manifest.json')['files'], J(D / 'candidate/manifest.json')['files']
assert set(ma) == set(mb) and {k for k in ma if ma[k] != mb[k]} == {'parameters/vpe_profile_optin.py', 'parameters/vpe_fix.py'}   # A10: + r2h vpe_fix
assert all(h(D / 'candidate' / k) == v for k, v in mb.items())
assert pins['combined_files'] == mb and pins['combined_manifest_sha256'] == h(D / 'candidate/manifest.json')

# 5. pins
p7 = J(A7 / 'pins/frozen_inputs_c8_r2e_a7_01.json')
ren = lambda k: k.replace('c8_judge_r2e_a7_20261110/', 'c8_judge_r2j_a13_20261111/').replace('fixed_image_r2e_20261109/', 'fixed_image_r2j_20261111/').replace('goal_t22_flow_20261109/model_v1/bumblebee/', 't52_model_ref_20261111/models/model_v2/bumblebee/')  # A9, A13: model_v2
assert set(pins['ledger_files']) == {ren(k) for k in p7['ledger_files']}
assert set(pins['repo_files']) == {ren(k) for k in p7['repo_files']} | {
    'goal_step5b_20261109/px4_etc/init.d-posix/airframes/' + AF4070.name, 'goal_step5b_20261109/px4_etc/init.d-posix/airframes/4074_gz_bumblebee_t52_ref_dims',   # A13: + 4074
    'c8_judge_r2j_a13_20261111/expect/flight_real_params_4070.json', 'c8_judge_r2j_a13_20261111/expect/rc_real_params_4070.json'}
for g in ('repo_files', 'ledger_files'):
    for k, v in pins[g].items():
        if k == '@run/drone.py':
            assert v == h(R2F / 'src/bumblebee/examples/drone.py')
        else:
            assert h(Path('/work') / k) == v, k
assert not [k for g in ('repo_files', 'ledger_files') for k in pins[g] if 'r2e_a7' in k or 'fixed_image_r2e' in k]
acc = [l.split() for l in (D / 'launcher/ACCEPTED_PINS_b.txt').read_text().splitlines() if l and not l.startswith('#')]
assert acc == [[h(D / 'pins/frozen_inputs_c8_r2j_a13_01.json'), str(D / 'pins/frozen_inputs_c8_r2j_a13_01.json')]], acc

# 6. product
subprocess.run(['sha256sum', '-c', '--quiet', 'MANIFEST_SHA256.txt'], cwd=R2F, check=True)
assert pins['repo_files']['fixed_image_r2j_20261111/MANIFEST_SHA256.txt'] == h(R2F / 'MANIFEST_SHA256.txt') == \
    'b0899329ed73769a4a9afa4842c448b14e0f00c05d0d0a11dd6523c258563ee4'   # A12: r2j
run = (D / 'executor/run.sh').read_text()
assert 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % h(D / 'executor/PRODUCT_SHA256SUMS.txt') in run
assert 'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % h(R2F / 'src/bumblebee/examples/drone.py') in run
ok = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2F / 'install', capture_output=True)
bad = subprocess.run(['sha256sum', '-c', '--quiet', str(D / 'executor/PRODUCT_SHA256SUMS.txt')], cwd=R2E / 'install', capture_output=True)
assert ok.returncode == 0 and bad.returncode != 0
launcher = (D / 'launcher/host_run_wsl_c8_r2e_b.sh').read_text()
assert 'C8_AIRFRAME=${C8_AIRFRAME:-4074};' in launcher and '/work/fixed_image_r2j_20261111/install}' in launcher
assert 'fixed_image_r2e' not in launcher and 'r2e_a7' not in launcher
print('a8 ok: identity c8_4070, expectations = 4061 + %s = airframe 4070, judge +1 row, candidate/pins/product r2f' % sorted(EXPECT))
