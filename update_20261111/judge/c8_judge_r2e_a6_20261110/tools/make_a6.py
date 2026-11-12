#!/usr/bin/env python3
"""make_a6.py - T32 (10.11.2026): C8 package revision A6 = /work/c8_judge_r2e_20261109 (build 2, pins 02, 40d67c1c)
+ one fix in the package executor: the INDOOR_ARUCO profile is applied parents-before-children (restore_order of the
candidate closure), so MPC_XY_VEL_MAX is raised before MPC_XY_CRUISE. On airframe 4061 (MPC_XY_VEL_MAX 0.25) the old
dict order wrote MPC_XY_CRUISE 0.3 first and PX4 committed it down to 0.25 (MulticopterPositionControl.cpp:215-217)
-> supervisor assert -> every C8 scenario failed before take-off (/work/c8_rel3_run_20261110/RUN_LOG.md).
Unchanged: image r2e, the judge copy (verify_flight_c8.py, legacy, expect/ byte-identical), the candidate, the profile
values, the expectations. Restore order was already parents-first (profile_transaction.restore uses restore_order).
Only path changes besides that: the new folder name in executor/run.sh, the launcher, tests; new pins + accepted list.
Usage: python3 -I make_a6.py   (refuses to overwrite)
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

WORK = Path('/work')
SRC = WORK / 'c8_judge_r2e_20261109'
DST = WORK / 'c8_judge_r2e_a6_20261110'
OLD, NEW = 'c8_judge_r2e_20261109', 'c8_judge_r2e_a6_20261110'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2e_b_02.json'
PINS_SRC_SHA = '40d67c1cc4250c8ac626c4f0cb052f0106bacaf11facb8491d2f528a15eb9ab5'
JUDGE_SHA = 'c37579351b295a36a1d34af3fb49522877a0d0220a3a84e0505585adf09551bd'
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py']
R = []   # (file, reason)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def edit(rel, edits):
    p = DST / rel
    t = p.read_text()
    for old, new, n, why in edits:
        c = t.count(old)
        if c != n:
            sys.exit('STOP: %s anchor %r: %d matches (want %d)' % (rel, old[:70], c, n))
        t = t.replace(old, new)
        R.append((rel, why))
    p.write_text(t)


def main():
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA:
        sys.exit('STOP: source package changed')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins 02: ' + name)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A6 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()

    # 1. the fix: apply order parents-before-children
    edit('executor/supervisor.py', [
        ('from sitl_profile_closure_candidate import closure_names,profile_values\n',
         'from sitl_profile_closure_candidate import closure_names,profile_values,restore_order  # A6: restore_order for the apply order\n', 1,
         'A6: import the candidate closure order (parents before children).'),
        ("    for name,value in profile_values().items():\n"
         "        req=SetParam.Request();req.param_id=name;req.ptype=1;req.value=value;req.ttl_sec=0.;req.persistent=False\n",
         "    profile=profile_values()\n"
         "    # A6 (T32, 10.11): parents before children (MPC_XY_VEL_MAX before MPC_XY_CRUISE). In dict order PX4 committed\n"
         "    # MPC_XY_CRUISE 0.3 down to the old MPC_XY_VEL_MAX 0.25 of airframe 4061 (MulticopterPositionControl.cpp:215-217).\n"
         "    for name in restore_order(tuple(profile)):\n"
         "        value=profile[name]\n"
         "        req=SetParam.Request();req.param_id=name;req.ptype=1;req.value=value;req.ttl_sec=0.;req.persistent=False\n", 1,
         'A6: apply the profile parents-before-children; same names and values, only the order changes.'),
    ])
    # 2. paths
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # c8-r2e-b: this copy (c8 executor_r2e + revision b, ../DIFF_exec_b.md)' % OLD,
         'OWN=/work/%s/executor  # A6: this copy (revision b + apply order, ../DIFF_a6.md)' % NEW, 1, 'Own folder is the new copy.'),
    ])
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('# host_run_wsl_c8_r2e_b.sh = launcher v32-c8-r2e-b', '# host_run_wsl_c8_r2e_b.sh = launcher v33-c8-r2e-a6 (A6, T32 10.11.2026: runner = %s/executor; was v32-c8-r2e-b)' % NEW, 1,
         'Header: version and runner.'),
        ('ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v32-c8-r2e-b; no real drone, no ssh',
         'ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6; no real drone, no ssh', 1, 'First printed line: version.'),
        ('no TRIAL argument in v32-c8-r2e-b', 'no TRIAL argument in v33-c8-r2e-a6', 1, 'Version in a refusal.'),
        ('RUNNER=$WORK/%s/executor/run.sh   # c8-r2e-b: the only runner of this launcher' % OLD,
         'RUNNER=$WORK/%s/executor/run.sh   # A6: the only runner of this launcher' % NEW, 1, 'Runner = A6.'),
        ("    runner = '%s/executor/run.sh'  # c8-r2e-b: the fixed runner" % OLD,
         "    runner = '%s/executor/run.sh'  # A6: the fixed runner" % NEW, 1, 'Pins must cover this runner.'),
        ('ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v32-c8-r2e-b',
         'ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6', 1, 'launcher.log banner.'),
        ("'trial': '%s/executor'," % OLD, "'trial': '%s/executor'," % NEW, 1, 'host_check names the real runner.'),
    ])
    for t in ('tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py'):
        txt = (DST / t).read_text()
        n = txt.count('/work/' + OLD)
        if n < 1:
            sys.exit('STOP: no path in ' + t)
        (DST / t).write_text(txt.replace('/work/' + OLD, '/work/' + NEW))
        R.append((t, 'Test paths -> the A6 folder (%d places).' % n))
    edit('tests/test_c8_b2.sh', [
        ('frozen_inputs_c8_r2e_b_02.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"\n# control: the old v31 pins',
         'frozen_inputs_c8_r2e_a6_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"\n# control: the old v31 pins', 1, 'Pre-check uses pins A6.'),
        ('t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_b_02.json',
         't ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_a6_01.json', 1, 'Ledger test uses pins A6.'),
        ('$D/_aside_build1/pins/frozen_inputs_c8_r2e_b_01.json', '/work/%s/pins/frozen_inputs_c8_r2e_b_02.json' % OLD, 1,
         'Control: the previous pins (02 of build 2) are refused by the A6 launcher.'),
        ('--out $D/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json --identity rel3_4030',
         '--out $D/reviews/OVERWRITE_GUARD.json --identity rel3_4030', 1,
         'Overwrite refusal is tested on a guard file in the A6 reviews folder.'),
        ("open('$D/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json')",
         "open('/work/%s/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json')" % OLD, 1,
         'The rel3 proof of the identical judge (sha c3757935) stays in the build-2 folder.'),
        ('echo "RESULT pass=$PASS fail=$FAIL (logs $O)"',
         '# A6: apply order on the 4061 baseline (candidate KnownCapsModel = the PX4 committed clamps): new order reaches every\n'
         '# profile value; the old dict order reproduces the run failure (MPC_XY_CRUISE 0.25); the restore returns the baseline.\n'
         't a6_apply_order python3 -B -I $D/tests/a6_apply_order.py\n'
         'echo "RESULT pass=$PASS fail=$FAIL (logs $O)"', 1, 'A6 test added.'),
    ])
    shutil.copy2(Path(__file__).with_name('a6_apply_order.py'), DST / 'tests/a6_apply_order.py')
    R.append(('tests/a6_apply_order.py', 'New test (A6).'))

    # 3. pins A6: pins 02 with the folder prefix renamed; every unchanged file must keep its sha
    new = json.loads(json.dumps(old_pins))
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1) if name.startswith(OLD + '/') else name
            if not nn.startswith('@run/'):
                h2 = sha(WORK / nn)
                if h2 != h and nn not in (NEW + '/executor/supervisor.py', NEW + '/executor/run.sh'):
                    sys.exit('STOP: unexpected change ' + nn)
                h = h2
            g[nn] = h
        new[group] = g
    for f in ('supervisor.py', 'run.sh'):
        new['run_files'][f] = sha(DST / 'executor' / f)
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    assert new['combined_manifest_sha256'] == sha(DST / 'candidate/manifest.json')
    new['sdk_drone_py']['by'] = NEW + '/tools/make_a6.py'
    new['c8_target'].update(combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4061',
                            a6='apply order parents-before-children (T32)')
    changed = sorted(k for g in ('repo_files', 'ledger_files', 'run_files') for k in new[g]
                     if old_pins[g].get(k.replace(NEW + '/', OLD + '/', 1)) != new[g][k])
    P = DST / 'pins/frozen_inputs_c8_r2e_a6_01.json'
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v33-c8-r2e-a6 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# frozen_inputs_c8_r2e_a6_01.json = pins 02 (40d67c1c) with the folder renamed + supervisor.py/run.sh of A6\n'
                '%s  %s\n' % (NEW, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a6.py')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'changed_entries': changed,
                      'judge_sha_same': sha(DST / 'verify_flight_c8.py') == JUDGE_SHA, 'edits': len(R)}))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
