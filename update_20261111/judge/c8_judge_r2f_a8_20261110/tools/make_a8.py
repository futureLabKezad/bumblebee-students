#!/usr/bin/env python3
"""make_a8.py - T38 (10.11.2026): C8 package revision A8 = A7 (/work/c8_judge_r2e_a7_20261110, pins 12a05438)
with the reviewed image r2f (/work/fixed_image_r2f_20261110, MANIFEST_SHA256.txt 2feb53fb, review: accepted, no MUST-FIX)
and the final Gazebo set airframe 4070 of the Simulator (= 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1, file sha 0bca708f).
Changes (nothing else; DIFF_a8.md lists every line):
 - image r2e -> r2f: run.sh product pins (PRODUCT_SHA256SUMS.txt regenerated from the r2f install, drone.py sha),
   sitl_setup.py profile path (flight_profile.py is byte-identical in r2f), launcher defaults, pins.
   Candidate image copies (flight_profile.py, vpe_fix.py, aruco_detect.py) are byte-identical in r2f: unchanged.
 - airframe 4061 -> 4070: launcher default C8_AIRFRAME, the SITL harness opt-in check (candidate/parameters/
   vpe_profile_optin.py: not an image file, SITL only), judge identity c8_4070 (one new table row: data, no logic).
 - expectations of real_parameters_before_arm for c8_4070 = the 4061 files + EXPECT_4070 below.
 - judge logic, legacy copy, profile order, camera launch (path only), executor logic: as in A7.
A future approved setting (e.g. T33 flow: EKF2_OF_QMIN, MPC_LAND_CRWL) = ONE new line in EXPECT_4070, the matching line
in the Simulator's airframe 4070 and its new sha in AF4070_SHA; tests/a8_checks.py reads EXPECT_4070 from this file.
Usage: python3 -I make_a8.py   (refuses to overwrite)
"""
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# name: (value, MAVLink param type: 6 = INT32, 9 = REAL32) in flight_real_params_4070.json; each line = one decision
EXPECT_4070 = {
    'BAT1_SOURCE': (0, 6),   # approved drone set, owner 09.11 «да» (4061: 1)
    'SDLOG_MODE': (1, 6),    # log from boot, owner 10.11 «В» (new name)
}

WORK = Path('/work')
SRC = WORK / 'c8_judge_r2e_a7_20261110'
DST = WORK / 'c8_judge_r2f_a8_20261110'
OLD, NEW = 'c8_judge_r2e_a7_20261110', 'c8_judge_r2f_a8_20261110'
IMG_OLD, IMG_NEW = 'fixed_image_r2e_20261109', 'fixed_image_r2f_20261110'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2e_a7_01.json'
PINS_SRC_SHA = '12a0543824841ee023ff7d97bd26c053331b3e50bfd999b5063fa2f50a73e73f'
PINS_NAME = 'frozen_inputs_c8_r2f_a8_01.json'
JUDGE_SHA = 'c37579351b295a36a1d34af3fb49522877a0d0220a3a84e0505585adf09551bd'
R2F = WORK / IMG_NEW
R2F_MANIFEST_SHA = '2feb53fb5420695afe23492a47bda012dd7031141b601d2f85a3cb3bbc1b9691'
R2F_DRONE_SHA = '94f9dfee2f6114c014d7fe9cadc0b1a92fdc03e93ba510b63cb87d1e7af6851a'
R2E_DRONE_SHA = '855f4cc4ad511a59b679092f3c587ce5689684edd53e3a0abbb72bd2226ac9ad'
AFDIR = 'goal_step5b_20261109/px4_etc/init.d-posix/airframes'
AF4070 = AFDIR + '/4070_gz_bumblebee_final_4061_bat0_sdlog1'
AF4070_SHA = '0bca708fbe25b1731e94de159fb74d62aaf0015d66d6311ea0f48ddcfc73fa29'
AF4061 = AFDIR + '/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl'
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py', 'tests/a6_apply_order.py', 'tests/a7_vision_launch.py']
R = []


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def edit_text(t, rel, edits):
    for old, new, n, why in edits:
        c = t.count(old)
        if c != n:
            sys.exit('STOP: %s anchor %r: %d matches (want %d)' % (rel, old[:70], c, n))
        t = t.replace(old, new)
        R.append((rel, why))
    return t


def edit(rel, edits):
    p = DST / rel
    p.write_text(edit_text(p.read_text(), rel, edits))


def dump(obj, indent):
    return json.dumps(obj, indent=indent, ensure_ascii=False) + '\n'


def main():
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA:
        sys.exit('STOP: A7 changed')
    if sha(R2F / 'MANIFEST_SHA256.txt') != R2F_MANIFEST_SHA or sha(R2F / 'src/bumblebee/examples/drone.py') != R2F_DRONE_SHA:
        sys.exit('STOP: r2f is not the reviewed one')
    subprocess.run(['sha256sum', '-c', '--quiet', 'MANIFEST_SHA256.txt'], cwd=R2F, check=True)
    if sha(WORK / AF4070) != AF4070_SHA:
        sys.exit('STOP: airframe 4070 is not the one this build pins')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins A7: ' + name)
    # the image files the candidate carries are byte-identical in r2f
    same = {'candidate/parameters/flight_profile.py': 'src/bumblebee/examples/flight_profile.py',
            'candidate/parameters/vpe_fix.py': 'src/bumblebee/src/python/vpe_fix.py',
            'candidate/vision/aruco_detect.py': 'src/bumblebee/src/python/aruco_detect.py'}
    for c, i in same.items():
        if sha(SRC / c) != sha(R2F / i):
            sys.exit('STOP: candidate copy differs from r2f: ' + c)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A8 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()

    # 1. expectations c8_4070 = the 4061 files + EXPECT_4070 (types kept for names that exist)
    fl = json.loads((SRC / 'expect/flight_real_params_4061.json').read_text())
    for name, (value, ptype) in EXPECT_4070.items():
        cur = fl['parameters'].get(name)
        if cur is not None and cur['type'] != ptype:
            sys.exit('STOP: type of %s differs from the 4061 file' % name)
        fl['parameters'][name] = {'value': value, 'type': ptype}
    with open(DST / 'expect/flight_real_params_4070.json', 'x') as h:
        h.write(dump(fl, 2))
    shutil.copy2(SRC / 'expect/rc_real_params_4061.json', DST / 'expect/rc_real_params_4070.json')
    R.append(('expect/flight_real_params_4070.json', 'New: 4061 file + %s.' % sorted(EXPECT_4070)))
    R.append(('expect/rc_real_params_4070.json', 'New: copy of rc_real_params_4061.json (no RC change in 4070).'))
    fsha, rsha = sha(DST / 'expect/flight_real_params_4070.json'), sha(DST / 'expect/rc_real_params_4070.json')

    # 2. judge: one identity row (data); logic unchanged
    edit('verify_flight_c8.py', [
        ("#             COM_SPOOLUP_TIME 1.0, BAT1_SOURCE 1; A5); pinned here by sha.\n",
         "#             COM_SPOOLUP_TIME 1.0, BAT1_SOURCE 1; A5); pinned here by sha.\n"
         "#  c8_4070:   A8 (T38, 10.11.2026): airframe 4070 of the Simulator = 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1, image r2f;\n"
         "#             the same 18 names; expect/*_4070.json = the 4061 files + those 2 values (tools/make_a8.py EXPECT_4070).\n", 1,
         'Comment of the new identity.'),
        ("        'rc_real_params.json': (HERE / 'expect/rc_real_params_4061.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),\n}\n",
         "        'rc_real_params.json': (HERE / 'expect/rc_real_params_4061.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),\n"
         "    'c8_4070': dict(autostart=4070, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={\n"
         "        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '%s'),\n"
         "        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '%s')}),\n}\n" % (fsha, rsha), 1,
         'A8: identity c8_4070 (one table row, no logic change).'),
    ])

    # 3. candidate: the SITL harness airframe check 4061 -> 4070 (not an image file); manifest sha + text
    edit('candidate/parameters/vpe_profile_optin.py', [
        ("    if audit.get('sitl_autostart')!=4061 or audit.get('sitl_autostart_source')!='rc_ready.json:sys_autostart':\n"
         "        raise RuntimeError('SITL airframe is not 4061')\n",
         "    if audit.get('sitl_autostart')!=4070 or audit.get('sitl_autostart_source')!='rc_ready.json:sys_autostart':  # A8: airframe 4070\n"
         "        raise RuntimeError('SITL airframe is not 4070')\n", 1, 'A8: SITL harness airframe check 4061 -> 4070.'),
    ])
    mp = DST / 'candidate/manifest.json'
    mt = mp.read_text()
    m = json.loads(mt)
    if dump(m, 1) != mt:
        sys.exit('STOP: manifest format')
    m['scope'] = edit_text(m['scope'], 'candidate/manifest.json:scope', [
        ('combined_c8_r2e (T28, 09.11.2026): combined_13 + fixed image r2e parts for C8 on airframe 4061.',
         'combined_c8_r2f (A8, T38 10.11.2026; was combined_c8_r2e, T28): combined_13 + fixed image r2f parts for C8 on airframe 4070.', 1,
         'Scope text.')])
    m['files']['parameters/vpe_profile_optin.py'] = sha(DST / 'candidate/parameters/vpe_profile_optin.py')
    for k in ('parameters/flight_profile.py', 'parameters/vpe_fix.py', 'vision/aruco_detect.py'):
        m['origins'][k] = edit_text(m['origins'][k], 'candidate/manifest.json:origins:' + k,
                                    [(IMG_OLD, IMG_NEW, 1, 'Origin r2e -> r2f (byte-identical file).')])
    m['origins']['parameters/vpe_profile_optin.py'] += '; A8: SITL airframe check 4070'
    R.append(('candidate/manifest.json', 'files: vpe_profile_optin.py sha; origins text.'))
    mp.write_text(dump(m, 1))
    with open(DST / 'candidate/README.md', 'a') as h:
        h.write('A8 (T38, 10.11.2026): image r2f (the three image copies above are byte-identical in r2f), airframe 4070 '
                '(vpe_profile_optin.py checks 4070). README.md is not a pinned candidate file.\n')
    R.append(('candidate/README.md', 'One line appended.'))

    # 4. executor
    inst = R2F / 'install'
    a7_list = [l[66:] for l in (SRC / 'executor/PRODUCT_SHA256SUMS.txt').read_text().splitlines()]
    now_list = sorted('./' + str(p.relative_to(inst)) for p in inst.rglob('*') if p.is_file())
    if sorted(a7_list) != now_list:
        sys.exit('STOP: r2f install file list differs from the A7 product list')
    (DST / 'executor/PRODUCT_SHA256SUMS.txt').write_text(''.join('%s  %s\n' % (sha(inst / n[2:]), n) for n in a7_list))
    R.append(('executor/PRODUCT_SHA256SUMS.txt', 'Regenerated from the r2f install (same %d paths, same order).' % len(a7_list)))
    psha = sha(DST / 'executor/PRODUCT_SHA256SUMS.txt')
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # A7: this copy (A6 + own camera launch file, ../DIFF_a7.md)' % OLD,
         'OWN=/work/%s/executor  # A8: this copy (A7 + image r2f + airframe 4070, ../DIFF_a8.md)' % NEW, 1, 'Own folder.'),
        ('(c8: fixed image r2e, /work/fixed_image_r2e_20261109/install, MANIFEST_SHA256.txt d3e043c2)',
         '(c8 A8: fixed image r2f, /work/fixed_image_r2f_20261110/install, MANIFEST_SHA256.txt 2feb53fb)', 1, 'Comment.'),
        ('echo "544f3179194b2fa14e16ff6add053e607ff14b0045d70b469ea61502642fd6ad  $OWN/PRODUCT_SHA256SUMS.txt"',
         'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % psha, 1, 'A8: product sums of the r2f install.'),
        ('# c8: product parameter (r2e), pinned above', '# c8: product parameter (A8: r2f), pinned above', 1, 'Comment.'),
        ('# c8: product src is a parameter; the sha is r2e drone.py.', '# c8: product src is a parameter; the sha is r2f drone.py (A8).', 1, 'Comment.'),
        ('echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % R2E_DRONE_SHA,
         'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % R2F_DRONE_SHA, 1, 'A8: r2f drone.py.'),
    ])
    edit('executor/sitl_setup.py', [
        ("PROFILE_SOURCE = Path('/work/fixed_image_r2e_20261109/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3)",
         "PROFILE_SOURCE = Path('/work/fixed_image_r2f_20261110/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3); A8: r2f (same bytes)",
         1, 'A8: profile path r2f (byte-identical file).'),
    ])
    edit('executor/vision_c8.launch.py', [('c8_judge_r2e_a7_20261110/candidate', NEW + '/candidate', 2,
                                           'A8: own candidate path (header + location check).')])

    # 5. launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v34-c8-r2e-a7 (A7, 10.11.2026: runner = %s/executor; A6 was v33, b was v32)' % OLD,
         'launcher v35-c8-r2f-a8 (A8, T38 10.11.2026: runner = %s/executor, image r2f, airframe 4070; A7 was v34, A6 v33, b v32)' % NEW,
         1, 'Header.'),
        ('host_run_wsl_c8_r2e_b.sh v34-c8-r2e-a7; no real drone, no ssh', 'host_run_wsl_c8_r2e_b.sh v35-c8-r2f-a8; no real drone, no ssh', 1, 'First line.'),
        ('no TRIAL argument in v34-c8-r2e-a7', 'no TRIAL argument in v35-c8-r2f-a8', 1, 'Refusal text.'),
        ('RUNNER=$WORK/%s/executor/run.sh   # A7: the only runner of this launcher' % OLD,
         'RUNNER=$WORK/%s/executor/run.sh   # A8: the only runner of this launcher' % NEW, 1, 'Runner.'),
        ('# ---- c8: target set (defaults = C8 set of 09.11: airframe 4061, image r2e, T22 model_v1 + plugin_v1, MAVROS bp02)',
         '# ---- c8: target set (defaults = C8 set A8 of 10.11: airframe 4070 = 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1, image r2f, T22 model_v1 + plugin_v1, MAVROS bp02)',
         1, 'Comment.'),
        ('C8_AIRFRAME=${C8_AIRFRAME:-4061};', 'C8_AIRFRAME=${C8_AIRFRAME:-4070};', 1, 'A8: default airframe 4070.'),
        ('C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2e_20261109/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2e_20261109/src/bumblebee}',
         'C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2f_20261110/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2f_20261110/src/bumblebee}',
         1, 'A8: default image r2f.'),
        ("    runner = '%s/executor/run.sh'  # A7: the fixed runner" % OLD, "    runner = '%s/executor/run.sh'  # A8: the fixed runner" % NEW, 1, 'Pins runner.'),
        ('host_run_wsl_c8_r2e_b.sh v34-c8-r2e-a7" > "$SIDE/launcher.log"', 'host_run_wsl_c8_r2e_b.sh v35-c8-r2f-a8" > "$SIDE/launcher.log"', 1, 'Banner.'),
        ("'trial': '%s/executor'," % OLD, "'trial': '%s/executor'," % NEW, 1, 'host_check runner.'),
    ])

    # 6. tests: paths, then the A8 cases
    for t in ('tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py', 'tests/a6_apply_order.py', 'tests/a7_vision_launch.py'):
        txt = (DST / t).read_text()
        n1, n2 = txt.count('/work/' + OLD), txt.count(IMG_OLD)
        txt = txt.replace('/work/' + OLD, '/work/' + NEW).replace(IMG_OLD, IMG_NEW)
        (DST / t).write_text(txt)
        R.append((t, 'Paths -> A8 (%d) and image -> r2f (%d).' % (n1, n2)))
    edit('tests/test_c8_b2.sh', [
        ('$D/pins/frozen_inputs_c8_r2e_a7_01.json', '$D/pins/' + PINS_NAME, 2, 'Tests use pins A8.'),
        ('env C8_AF_FILE=/work/%s \\\n  C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf \\\n' % AF4061,
         'env C8_AF_FILE=/work/%s \\\n  C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf \\\n' % AF4070, 1,
         'Launcher pre-check with the default airframe 4070.'),
        ('/work/c8_judge_r2e_a6_20261110/pins/frozen_inputs_c8_r2e_a6_01.json', '/work/%s/pins/frozen_inputs_c8_r2e_a7_01.json' % OLD, 1,
         'Control: the A7 pins are refused by the A8 launcher.'),
        ("grep -qx 'SITL airframe is not 4061'", "grep -qx 'SITL airframe is not 4070'", 2, 'D7: the opt-in now names 4070.'),
        ('t d7_optin_4061_reaches_route_check bash -c "python3 -B -I $O/optin_case.py \'{\\"sitl_autostart\\":4061,',
         't d7_optin_refuses_4061 bash -c "python3 -B -I $O/optin_case.py \'{\\"sitl_autostart\\":4061,\\"sitl_autostart_source\\":\\"rc_ready.json:sys_autostart\\"}\' $O | grep -qx \'SITL airframe is not 4070\'"\n'
         't d7_optin_4070_reaches_route_check bash -c "python3 -B -I $O/optin_case.py \'{\\"sitl_autostart\\":4070,', 1,
         'D7: 4061 refused, 4070 reaches the route check.'),
        ('echo "RESULT pass=$PASS fail=$FAIL (logs $O)"',
         '# A8: identity c8_4070, expectations = 4061 + EXPECT_4070 = airframe 4070, judge diff = one row, candidate/pins/product r2f\n'
         't a8_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a8_checks.py\n'
         '# A8: c8_4070 on the rel3 kill run: as c8_4061 plus the EXPECT_4070 names (judge really reads the 4070 files)\n'
         't judge_c8_4070_effect bash -c "$J --identity c8_4070 --out $D/reviews/tests_$(basename $O)/kill_as_c8_4070.json >/dev/null; '
         '/work/analysis/layout/.venv/bin/python -B -I $D/tests/a8_judge_effect.py $D/reviews/tests_$(basename $O)/kill_as_c8_4061.json $D/reviews/tests_$(basename $O)/kill_as_c8_4070.json"\n'
         '# A8: on a real 4061 run of A7: c8_4061 = A7 verdict; c8_4070 fails only on autostart + BAT1_SOURCE / SDLOG_MODE\n'
         't a8_judge_on_a7_run python3 -B -I $D/tests/a8_judge_on_a7_run.py $D/reviews/tests_$(basename $O)\n'
         'echo "RESULT pass=$PASS fail=$FAIL (logs $O)"', 1, 'A8 tests added.'),
    ])
    edit('tests/a7_vision_launch.py', [
        ("for other in (Path('/work/c8_judge_r2e_a6_20261110/candidate'),",
         "for other in (Path('/work/c8_judge_r2e_a6_20261110/candidate'), Path('/work/%s/candidate'),  # A8: A7 refused too\n              " % OLD,
         1, 'A8: the A7 candidate is refused too.'),
    ])
    for f in ('a8_checks.py', 'a8_judge_effect.py', 'a8_judge_on_a7_run.py'):
        shutil.copy2(Path(__file__).with_name(f), DST / 'tests' / f)
        R.append(('tests/' + f, 'New test (A8).'))

    # 7. pins A8
    new = json.loads(json.dumps(old_pins))
    changed = set()
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1).replace(IMG_OLD + '/', IMG_NEW + '/', 1)
            if nn == '@run/drone.py':
                h2 = R2F_DRONE_SHA
            else:
                h2 = sha(WORK / nn)
            if h2 != h:
                changed.add(nn)
            g[nn] = h2
        new[group] = g
    for k in (AF4070, NEW + '/expect/flight_real_params_4070.json', NEW + '/expect/rc_real_params_4070.json'):
        new['repo_files'][k] = sha(WORK / k)
    for k, v in old_pins['run_files'].items():
        p = DST / 'executor' / k if (DST / 'executor' / k).exists() else R2F / 'src/bumblebee/examples' / k
        new['run_files'][k] = sha(p)
        if new['run_files'][k] != v:
            changed.add('run_files:' + k)
    allowed = {NEW + '/verify_flight_c8.py', NEW + '/executor/run.sh', NEW + '/executor/sitl_setup.py',
               NEW + '/executor/PRODUCT_SHA256SUMS.txt', NEW + '/executor/vision_c8.launch.py',
               NEW + '/candidate/parameters/vpe_profile_optin.py', '@run/drone.py',
               IMG_NEW + '/src/bumblebee/examples/drone.py', IMG_NEW + '/src/bumblebee/src/cpp/simple_offboard.cpp',
               IMG_NEW + '/install/bumblebee/lib/bumblebee/simple_offboard', IMG_NEW + '/MANIFEST_SHA256.txt',
               IMG_NEW + '/image_manifest_r2.tsv',
               'run_files:run.sh', 'run_files:sitl_setup.py', 'run_files:drone.py', 'run_files:vision_c8.launch.py'}
    if not changed <= allowed:
        sys.exit('STOP: unexpected changes: %s' % sorted(changed - allowed))
    R.append(('pins/' + PINS_NAME, 'Changed entries: %s' % sorted(changed)))
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    new['combined_manifest_sha256'] = sha(DST / 'candidate/manifest.json')
    new['combined_files'] = json.loads((DST / 'candidate/manifest.json').read_text())['files']
    new['sdk_drone_py'].update(source=str(R2F / 'src/bumblebee/examples/drone.py'), sha256=R2F_DRONE_SHA,
                               product_tag='fixed image r2f (MANIFEST_SHA256.txt 2feb53fb)', by=NEW + '/tools/make_a8.py')
    new['c8_target'].update(airframe=4070, airframe_chain=[Path(AF4070).name] + old_pins['c8_target']['airframe_chain'],
                            product_install=str(R2F / 'install'), product_src=str(R2F / 'src/bumblebee'),
                            combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4070',
                            a8='image r2f + airframe 4070 (BAT1_SOURCE 0, SDLOG_MODE 1), identity c8_4070 (T38)')
    P = DST / 'pins' / PINS_NAME
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v35-c8-r2f-a8 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# %s = pins A7 (12a05438) renamed + image r2f + airframe 4070 + identity c8_4070 files (tools/make_a8.py)\n'
                '%s  %s\n' % (NEW, PINS_NAME, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a8.py')

    # 8. DIFF_a8.md: every changed line against A7 (new files listed)
    out = ['# DIFF A7 -> A8 (generated by tools/make_a8.py)\n']
    for p in sorted(DST.rglob('*')):
        rel = p.relative_to(DST)
        if not p.is_file() or rel.parts[0] in ('reviews', 'tools') or rel.name == 'build_edits.json':
            continue
        q = SRC / rel
        if not q.exists():
            out.append('\n## NEW %s (sha %s)\n' % (rel, sha(p)[:8]))
            continue
        if sha(p) == sha(q):
            continue
        try:
            a, b = q.read_text().splitlines(), p.read_text().splitlines()
        except UnicodeDecodeError:
            out.append('\n## BINARY CHANGED %s\n' % rel)
            continue
        d = list(difflib.unified_diff(a, b, str(q), str(p), lineterm='', n=0))
        if len(d) > 400:
            out.append('\n## %s: %d diff lines (regenerated file), first 6:\n```\n%s\n```\n' % (rel, len(d), '\n'.join(d[:8])))
        else:
            out.append('\n## %s\n```diff\n%s\n```\n' % (rel, '\n'.join(d)))
    with open(DST / 'DIFF_a8.md', 'x') as h:
        h.write(''.join(out))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge': sha(DST / 'verify_flight_c8.py'),
                      'manifest': new['combined_manifest_sha256'], 'product_sums': psha,
                      'expect_4070': [fsha, rsha], 'changed': sorted(changed), 'edits': len(R)}))


if __name__ == '__main__':
    main()
