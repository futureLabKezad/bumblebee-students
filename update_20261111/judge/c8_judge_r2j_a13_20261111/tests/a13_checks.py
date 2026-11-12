#!/usr/bin/env python3
"""A13 static checks: the A12 -> A13 difference is exactly airframe 4074 + model_v2 of T52 (+ texts and paths).
Judge: exactly one new identity row c8_4074 (autostart 4074, the c8_4070 names and expectation files) and its comment;
legacy, expectations, run_sim, gate.py, vision_c8 (camera TF), sitl_setup and the other candidate files: A12's bytes;
the opt-in accepts only airframe 4074; pins = A12 keys (model_v1 -> model_v2) + the 4074 airframe, every sha correct;
model_v2 differs from model_v1 only in model.sdf, whose camera / IMU / flow poses are the reference; 4074 sources 4070 v2
and sets exactly the 10 reference values. Run: python -B -I tests/a13_checks.py (analysis venv)"""
import difflib
import hashlib
import importlib.util
import json
import re
from pathlib import Path

D = Path('/work/c8_judge_r2j_a13_20261111')
A12 = Path('/work/c8_judge_r2j_a12_20261111')
W = Path('/work')
AFD = 'goal_step5b_20261109/px4_etc/init.d-posix/airframes/'
AF4074, AF4070 = AFD + '4074_gz_bumblebee_t52_ref_dims', AFD + '4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50'
M1, M2 = 'goal_t22_flow_20261109/model_v1/bumblebee/', 't52_model_ref_20261111/models/model_v2/bumblebee/'
h = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
J = lambda p: json.loads(Path(p).read_text())
REF10 = {'EKF2_IMU_POS_X': -0.059, 'EKF2_IMU_POS_Y': 0.007, 'EKF2_IMU_POS_Z': -0.016, 'EKF2_RNG_POS_X': 0.082,
         'EKF2_RNG_POS_Y': -0.028, 'EKF2_RNG_POS_Z': 0.034, 'EKF2_OF_POS_X': 0.082, 'EKF2_OF_POS_Y': -0.028,
         'EKF2_OF_POS_Z': 0.034, 'EKF2_MIN_RNG': 0.23}          # ЭТАЛОН_РАЗМЕРОВ_20EC.md §3.1 (PX4 axes)


def changed_lines(rel):
    d = [l for l in difflib.unified_diff((A12 / rel).read_text().splitlines(), (D / rel).read_text().splitlines(), lineterm='', n=0)
         if l[:1] in '+-' and not l.startswith(('+++', '---'))]
    return [l for l in d if l.startswith('-')], [l for l in d if l.startswith('+')]


for rel in ('legacy/verify_package1b_gates_c8.py', 'expect/flight_real_params_4070.json', 'expect/rc_real_params_4070.json',
            'expect/flight_real_params_4061.json', 'expect/rc_real_params_4061.json', 'executor/run_sim.snapshot.sh',
            'executor/gate.py', 'executor/sitl_setup.py', 'executor/vpe_diagnostic_entry.py', 'executor/vpe_gate_diagnostic_p1.py',
            'executor/PRODUCT_SHA256SUMS.txt', 'candidate/parameters/vpe_fix.py', 'candidate/parameters/flight_profile.py',
            'candidate/vision/aruco_detect.py', 'candidate/parameters/vpe_freshness_optin.py'):
    assert h(D / rel) == h(A12 / rel), rel
# judge: only the c8_4074 row and its comment are added; c8_4074 = c8_4070 but autostart 4074
minus, plus = changed_lines('verify_flight_c8.py')
assert minus == [] and len(plus) == 5, (minus, plus)
s = importlib.util.spec_from_file_location('vj', D / 'verify_flight_c8.py'); vj = importlib.util.module_from_spec(s); s.loader.exec_module(vj)
I = vj.IDENTITIES
assert sorted(I) == ['c8_4061', 'c8_4070', 'c8_4074', 'rel3_4030']
assert I['c8_4074']['autostart'] == 4074 and I['c8_4074']['names'] == I['c8_4070']['names'] and len(I['c8_4074']['names']) == 18
assert I['c8_4074']['real_params'] == I['c8_4070']['real_params']
vj.use_identity('c8_4074'); m = vj.load_legacy(); assert m.AUTOSTART == 4074 and m.REAL_PARAMS['flight_real_params.json'].endswith('_4070.json')
judged = set(json.loads((D / 'expect/flight_real_params_4070.json').read_text())['parameters']) | \
    set(json.loads((D / 'expect/rc_real_params_4070.json').read_text())['parameters'])
assert not judged & set(REF10), judged & set(REF10)            # no sensor-position name is judged: the same files hold
# opt-in: 4074 only
minus, plus = changed_lines('candidate/parameters/vpe_profile_optin.py')
norm13 = lambda l: l.replace('4070', 'X').replace('4074', 'X').replace('; A13: X', '')
assert [norm13(l) for l in minus] == [norm13(l).replace('+', '-', 1) for l in plus] \
    and len(minus) == 2, (minus, plus)
ma, mb = J(A12 / 'candidate/manifest.json'), J(D / 'candidate/manifest.json')
assert {k for k in ma['files'] if ma['files'][k] != mb['files'][k]} == {'parameters/vpe_profile_optin.py'}
assert all(h(D / 'candidate' / k) == v for k, v in mb['files'].items())
# airframe 4074 and model_v2
af = (W / AF4074).read_text().splitlines()
assert '. ${R}etc/init.d-posix/airframes/' + Path(AF4070).name in af
sets = {l.split()[2]: float(l.split()[3]) for l in af if l.startswith('param set-default ')}
assert sets == REF10, sets
sdf = (W / M2 / 'model.sdf').read_text()
for frag in ('0.081 0 -0.034', '-0.059 -0.007 0.016', '0.082 0.028 -0.034'):
    assert frag in sdf, frag
assert '0.05 0 -0.07' not in sdf
for p in (W / M2).rglob('*'):
    if p.is_file() and p.name != 'model.sdf':
        assert h(p) == h(W / M1 / p.relative_to(W / M2)), p
# pins
pins, p12 = J(D / 'pins/frozen_inputs_c8_r2j_a13_01.json'), J(A12 / 'pins/frozen_inputs_c8_r2j_a12_01.json')
ren = lambda k: k.replace('c8_judge_r2j_a12_20261111/', 'c8_judge_r2j_a13_20261111/').replace(M1, M2)
assert set(pins['repo_files']) == {ren(k) for k in p12['repo_files']} | {AF4074}
assert set(pins['ledger_files']) == {ren(k) for k in p12['ledger_files']}
for g in ('repo_files', 'ledger_files'):
    for k, v in pins[g].items():
        assert v == (p12['ledger_files']['@run/drone.py'] if k == '@run/drone.py' else h(W / k)), k
assert pins['repo_files'][AF4070] == h(W / AF4070) and not [k for k in pins['repo_files'] if M1 in k or 'r2j_a12' in k]
assert pins['c8_target']['airframe'] == 4074 and pins['c8_target']['airframe_chain'] == [Path(AF4074).name] + p12['c8_target']['airframe_chain']
assert pins['c8_target']['model'] == str(W / M2).rstrip('/') and pins['c8_target']['judge'].endswith('--identity c8_4074')
assert pins['combined_files'] == mb['files'] and pins['combined_manifest_sha256'] == h(D / 'candidate/manifest.json')
assert pins['legacy_verifier_sha256'] == p12['legacy_verifier_sha256']
launcher = (D / 'launcher/host_run_wsl_c8_r2e_b.sh').read_text()
assert 'C8_AIRFRAME=${C8_AIRFRAME:-4074};' in launcher and 'C8_MODEL=${C8_MODEL:-/work/%s};' % M2.rstrip('/') in launcher
assert 'v40-c8-r2j-a13' in launcher and 'r2j_a12' not in launcher and 'model_v1' not in launcher.split('C8_MODEL=')[1].split('\n')[0]
assert re.search(r"'--x', '0.081', '--y', '0', '--z', '-0.034'", (D / 'executor/vision_c8.launch.py').read_text())
print('a13 ok: one identity row c8_4074 (= c8_4070, autostart 4074), opt-in 4074, airframe 4074 = 4070 v2 + 10 reference values, '
      'model_v2 = model_v1 + reference poses, pins renamed + 4074; judge logic, expectations, S tests unchanged')
