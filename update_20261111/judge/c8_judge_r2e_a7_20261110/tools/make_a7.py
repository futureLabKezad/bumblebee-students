#!/usr/bin/env python3
"""make_a7.py - T32 follow-up (10.11.2026): C8 package revision A7 = A6 (/work/c8_judge_r2e_a6_20261110, pins d61b25d7)
+ own camera launch file. A6 run INT_flight_C8a6_kill_01 failed before take-off: executor/run.sh:112 launched the shared
/work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py, which accepts a candidate only under
.../integration/combined_* (vision.launch.py:16-19) -> «Separate integration candidate required» (camera_stack.log).
A7: executor/vision_c8.launch.py = that file byte-for-byte except the candidate-location check, which now requires
exactly this package's candidate; the detector-sha-vs-manifest check stays. run.sh launches it. Nothing else changes:
image r2e, judge copy, expectations, candidate, profile values and the A6 apply order are the same.
Usage: python3 -I make_a7.py   (refuses to overwrite)
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

WORK = Path('/work')
SRC = WORK / 'c8_judge_r2e_a6_20261110'
DST = WORK / 'c8_judge_r2e_a7_20261110'
OLD, NEW = 'c8_judge_r2e_a6_20261110', 'c8_judge_r2e_a7_20261110'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2e_a6_01.json'
PINS_SRC_SHA = 'd61b25d70ca7201532da7039484e0cedd50c85b12babfb26f0a7be2ddc72197a'
JUDGE_SHA = 'c37579351b295a36a1d34af3fb49522877a0d0220a3a84e0505585adf09551bd'
VISION_SRC = WORK / 'parallel_work/20261015/integration/combined_trial_tools/vision.launch.py'
VISION_SRC_SHA = 'c9fe8ba65b2321ca7f9823ac3ea6ccfc845f2bf44c3372ce6d9a76aeead7d92a'
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py', 'tests/a6_apply_order.py']
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


def main():
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA or sha(VISION_SRC) != VISION_SRC_SHA:
        sys.exit('STOP: source changed')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins A6: ' + name)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A7 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()

    # 1. own camera launch file
    v = VISION_SRC.read_text()
    v = edit_text(v, 'executor/vision_c8.launch.py', [
        ('"""Ground camera chain for a separately frozen integration candidate."""\n',
         '"""Ground camera chain for a separately frozen integration candidate.\n\n'
         'C8 A7 copy (10.11.2026) of combined_trial_tools/vision.launch.py (sha c9fe8ba6): only the candidate-location\n'
         'check differs. It requires exactly the C8 package candidate %s/candidate (the shared file accepts\n'
         'only .../integration/combined_*). The detector-vs-manifest sha check is unchanged."""\n' % NEW, 1,
         'Header: what this copy is.'),
        ("    parent = Path('/work/parallel_work/20261015/integration')\n"
         "    if not root.is_relative_to(parent) or not root.name.startswith('combined_'):\n"
         "        raise RuntimeError('Separate integration candidate required')\n",
         "    if root != Path('/work/%s/candidate'):   # C8 A7: only this package's frozen candidate\n"
         "        raise RuntimeError('C8 package candidate required')\n" % NEW, 1,
         'A7: the candidate must be exactly this package candidate (was: only .../integration/combined_*).'),
    ])
    with open(DST / 'executor/vision_c8.launch.py', 'x') as h:
        h.write(v)
    R.append(('executor/vision_c8.launch.py', 'New file (A7).'))
    # 2. run.sh
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # A6: this copy (revision b + apply order, ../DIFF_a6.md)' % OLD,
         'OWN=/work/%s/executor  # A7: this copy (A6 + own camera launch file, ../DIFF_a7.md)' % NEW, 1, 'Own folder.'),
        ('setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch /work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py > "$OUT/camera_stack.log"',
         'setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch "$OWN/vision_c8.launch.py" > "$OUT/camera_stack.log"', 1,
         'A7: launch the package copy of the camera chain (the shared one refuses a candidate outside .../integration/combined_*).'),
    ])
    # 3. launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v33-c8-r2e-a6 (A6, T32 10.11.2026: runner = %s/executor; was v32-c8-r2e-b)' % OLD,
         'launcher v34-c8-r2e-a7 (A7, 10.11.2026: runner = %s/executor; A6 was v33, b was v32)' % NEW, 1, 'Header.'),
        ('host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6; no real drone, no ssh', 'host_run_wsl_c8_r2e_b.sh v34-c8-r2e-a7; no real drone, no ssh', 1, 'First line.'),
        ('no TRIAL argument in v33-c8-r2e-a6', 'no TRIAL argument in v34-c8-r2e-a7', 1, 'Refusal text.'),
        ('RUNNER=$WORK/%s/executor/run.sh   # A6: the only runner of this launcher' % OLD,
         'RUNNER=$WORK/%s/executor/run.sh   # A7: the only runner of this launcher' % NEW, 1, 'Runner.'),
        ("    runner = '%s/executor/run.sh'  # A6: the fixed runner" % OLD, "    runner = '%s/executor/run.sh'  # A7: the fixed runner" % NEW, 1, 'Pins runner.'),
        ('host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6" > "$SIDE/launcher.log"', 'host_run_wsl_c8_r2e_b.sh v34-c8-r2e-a7" > "$SIDE/launcher.log"', 1, 'Banner.'),
        ("'trial': '%s/executor'," % OLD, "'trial': '%s/executor'," % NEW, 1, 'host_check runner.'),
    ])
    # 4. tests
    for t in ('tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py', 'tests/a6_apply_order.py'):
        txt = (DST / t).read_text()
        n = txt.count('/work/' + OLD)
        (DST / t).write_text(txt.replace('/work/' + OLD, '/work/' + NEW))
        R.append((t, 'Test paths -> A7 (%d places).' % n))
    edit('tests/test_c8_b2.sh', [
        ('frozen_inputs_c8_r2e_a6_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"\n# control: the old v31 pins',
         'frozen_inputs_c8_r2e_a7_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"\n# control: the old v31 pins', 1, 'Pre-check uses pins A7.'),
        ('t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_a6_01.json',
         't ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_a7_01.json', 1, 'Ledger test uses pins A7.'),
        ('/work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_02.json', '/work/%s/pins/frozen_inputs_c8_r2e_a6_01.json' % OLD, 1,
         'Control: the A6 pins are refused by the A7 launcher.'),
        ('echo "RESULT pass=$PASS fail=$FAIL (logs $O)"',
         '# A7: the package camera launch accepts exactly this candidate, refuses others and a changed detector (ROS sourced, no node started)\n'
         't a7_vision_launch bash -c "set +u; source /opt/ros/jazzy/setup.bash; source /work/ws_sitl/install/setup.bash; set -u; python3 -B $D/tests/a7_vision_launch.py"\n'
         'echo "RESULT pass=$PASS fail=$FAIL (logs $O)"', 1, 'A7 test added.'),
    ])
    shutil.copy2(Path(__file__).with_name('a7_vision_launch.py'), DST / 'tests/a7_vision_launch.py')
    R.append(('tests/a7_vision_launch.py', 'New test (A7).'))
    # 5. ledger_check.py: the run.sh ledger line is unchanged; its glob "$OWN"/*.py now includes vision_c8.launch.py (automatic)

    # 6. pins A7
    new = json.loads(json.dumps(old_pins))
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1) if name.startswith(OLD + '/') else name
            if not nn.startswith('@run/'):
                h2 = sha(WORK / nn)
                if h2 != h and nn != NEW + '/executor/run.sh':
                    sys.exit('STOP: unexpected change ' + nn)
                h = h2
            g[nn] = h
        new[group] = g
    vk = NEW + '/executor/vision_c8.launch.py'
    new['repo_files'][vk] = sha(DST / 'executor/vision_c8.launch.py')
    new['ledger_files'][vk] = sha(DST / 'executor/vision_c8.launch.py')
    new['run_files']['run.sh'] = sha(DST / 'executor/run.sh')
    new['run_files']['vision_c8.launch.py'] = sha(DST / 'executor/vision_c8.launch.py')
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    assert new['combined_manifest_sha256'] == sha(DST / 'candidate/manifest.json')
    new['sdk_drone_py']['by'] = NEW + '/tools/make_a7.py'
    new['c8_target'].update(combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4061',
                            a7='own camera launch file (vision_c8.launch.py) for the package candidate')
    P = DST / 'pins/frozen_inputs_c8_r2e_a7_01.json'
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v34-c8-r2e-a7 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# frozen_inputs_c8_r2e_a7_01.json = pins A6 (d61b25d7) renamed + run.sh and vision_c8.launch.py of A7\n'
                '%s  %s\n' % (NEW, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a7.py')
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge_sha_same': sha(DST / 'verify_flight_c8.py') == JUDGE_SHA,
                      'vision_c8': sha(DST / 'executor/vision_c8.launch.py'), 'edits': len(R)}))


if __name__ == '__main__':
    main()
