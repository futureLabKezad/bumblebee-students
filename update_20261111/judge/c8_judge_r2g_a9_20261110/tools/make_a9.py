#!/usr/bin/env python3
"""make_a9.py - T39 (10.11.2026): C8 package revision A9 = A8 (/work/c8_judge_r2f_a8_20261110, pins 65d0f719; review:
REJECT, not handed out) + image r2g (/work/fixed_image_r2g_20261110 = r2f + S4) + the fixes of the A8 review:
 M1  executor/run_sim.snapshot.sh: in px4_first the logger was stopped and restarted only for SDLOG_MODE 0, so on airframe
     4070 (SDLOG_MODE 1) nothing after the PX4 startup was logged. Now the restart uses the rc.logging arguments of the
     airframe's mode (1: -e); the boot log closed by the stop is moved to $OUT/boot_log_before_restart (not deleted) so run.sh
     copies exactly one fresh ULog (the judge requires fresh_log_count == 1). Other modes: refused.
 S1  tests/a8_judge_on_a7_run.py: every EXPECT_4070 name must be among the judged values.
 S2  README: what a new setting really takes (a new package revision; the expectation is still one line).
Judge (5b2d6106), legacy copy, expectations, candidate files, profile order, camera launch logic: as in A8.
EXPECT_4070 lives here (the expectation files are rebuilt from A7's 4061 files and must equal A8's).
Usage: python3 -I make_a9.py   (refuses to overwrite)
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
    'EKF2_OF_QMIN': (50, 6), # A9: flow quality minimum, owner 10.11 (T33, smooth landing; 20EC: 1) (new name)
}

WORK = Path('/work')
A7 = WORK / 'c8_judge_r2e_a7_20261110'
SRC = WORK / 'c8_judge_r2f_a8_20261110'
DST = WORK / 'c8_judge_r2g_a9_20261110'
OLD, NEW = 'c8_judge_r2f_a8_20261110', 'c8_judge_r2g_a9_20261110'
IMG_OLD, IMG_NEW = 'fixed_image_r2f_20261110', 'fixed_image_r2g_20261110'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2f_a8_01.json'
PINS_SRC_SHA = '65d0f719c6a10c49874f5a323527d5dbb812e1577924a38ca04adcb50ae5f900'
PINS_NAME = 'frozen_inputs_c8_r2g_a9_01.json'
JUDGE_SHA = '5b2d6106a224eb4cd33f56d274fb6592f246673842d006a8ab074d0a00ea172f'
R2G = WORK / IMG_NEW
R2G_MANIFEST_SHA = '3d503cef2e2187c38c1a3dd2a71eb205d12216d38dedfca4eb0ad546fec76779'
R2G_DRONE_SHA = '068e6eb44ab01ad8807337b0c50d4f47c543d554cc3c09323d9043e39e2d3661'
R2F_DRONE_SHA = '94f9dfee2f6114c014d7fe9cadc0b1a92fdc03e93ba510b63cb87d1e7af6851a'
AFDIR = 'goal_step5b_20261109/px4_etc/init.d-posix/airframes'
AF4070 = AFDIR + '/4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50'   # A9: the Simulator's 4070 v2 (+ EKF2_OF_QMIN 50)
AF4070_SHA = '0224deec06a3a4fee076b2bc24d8cd1cd1650f3d270da057f94afa057698339e'
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py', 'tests/a6_apply_order.py', 'tests/a7_vision_launch.py', 'tests/a8_checks.py',
        'tests/a8_judge_effect.py', 'tests/a8_judge_on_a7_run.py']
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
        sys.exit('STOP: A8 changed')
    if sha(R2G / 'MANIFEST_SHA256.txt') != R2G_MANIFEST_SHA or sha(R2G / 'src/bumblebee/examples/drone.py') != R2G_DRONE_SHA:
        sys.exit('STOP: r2g is not the reviewed one')
    subprocess.run(['sha256sum', '-c', '--quiet', 'MANIFEST_SHA256.txt'], cwd=R2G, check=True)
    if sha(WORK / AF4070) != AF4070_SHA:
        sys.exit('STOP: airframe 4070 is not the one this build pins')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if name.startswith(AFDIR + '/4070_'):
                continue   # 4070 v1 was moved aside by the Simulator; replaced below by v2
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins A8: ' + name)
    for c, i in {'candidate/parameters/flight_profile.py': 'src/bumblebee/examples/flight_profile.py',
                 'candidate/parameters/vpe_fix.py': 'src/bumblebee/src/python/vpe_fix.py',
                 'candidate/vision/aruco_detect.py': 'src/bumblebee/src/python/aruco_detect.py'}.items():
        if sha(SRC / c) != sha(R2G / i):
            sys.exit('STOP: candidate copy differs from r2g: ' + c)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A9 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()

    # 1. expectations: rebuilt from A7's 4061 files + EXPECT_4070, must equal A8's (single source of the values)
    fl = json.loads((A7 / 'expect/flight_real_params_4061.json').read_text())
    for name, (value, ptype) in EXPECT_4070.items():
        cur = fl['parameters'].get(name)
        if cur is not None and cur['type'] != ptype:
            sys.exit('STOP: type of %s differs from the 4061 file' % name)
        fl['parameters'][name] = {'value': value, 'type': ptype}
    old_fsha = sha(SRC / 'expect/flight_real_params_4070.json')
    (DST / 'expect/flight_real_params_4070.json').write_text(dump(fl, 2))
    fsha = sha(DST / 'expect/flight_real_params_4070.json')
    R.append(('expect/flight_real_params_4070.json', 'Rebuilt: 4061 file + %s (A9 adds EKF2_OF_QMIN 50).' % sorted(EXPECT_4070)))
    # the judge pins the expectation by sha: the c8_4070 row gets the new sha (data; no logic line changes)
    edit('verify_flight_c8.py', [
        ("        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '%s'),\n" % old_fsha,
         "        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '%s'),\n" % fsha, 1,
         'A9: c8_4070 flight expectation sha (EKF2_OF_QMIN 50 added; the values are EXPECT_4070 of tools/make_a9.py).'),
    ])

    # 2. candidate manifest: origins r2f -> r2g (files byte-identical, the file shas do not change)
    mp = DST / 'candidate/manifest.json'
    mt = mp.read_text()
    m = json.loads(mt)
    if dump(m, 1) != mt:
        sys.exit('STOP: manifest format')
    m['scope'] = edit_text(m['scope'], 'candidate/manifest.json:scope', [
        ('combined_c8_r2f (A8, T38 10.11.2026; was combined_c8_r2e, T28): combined_13 + fixed image r2f parts',
         'combined_c8_r2g (A9, T39 10.11.2026; A8: r2f; T28: r2e): combined_13 + fixed image r2g parts', 1, 'Scope text.')])
    for k in ('parameters/flight_profile.py', 'parameters/vpe_fix.py', 'vision/aruco_detect.py'):
        m['origins'][k] = edit_text(m['origins'][k], 'candidate/manifest.json:origins:' + k,
                                    [(IMG_OLD, IMG_NEW, 1, 'Origin r2f -> r2g (byte-identical file).')])
    mp.write_text(dump(m, 1))
    with open(DST / 'candidate/README.md', 'a') as h:
        h.write('A9 (T39, 10.11.2026): image r2g (the three image copies are byte-identical in r2g); the rest as A8.\n')
    R.append(('candidate/README.md', 'One line appended.'))

    # 3. executor
    inst = R2G / 'install'
    a8_list = [l[66:] for l in (SRC / 'executor/PRODUCT_SHA256SUMS.txt').read_text().splitlines()]
    now_list = sorted('./' + str(p.relative_to(inst)) for p in inst.rglob('*') if p.is_file())
    if sorted(a8_list) != now_list:
        sys.exit('STOP: r2g install file list differs from the A8 product list')
    (DST / 'executor/PRODUCT_SHA256SUMS.txt').write_text(''.join('%s  %s\n' % (sha(inst / n[2:]), n) for n in a8_list))
    R.append(('executor/PRODUCT_SHA256SUMS.txt', 'Regenerated from the r2g install (same %d paths, same order).' % len(a8_list)))
    psha = sha(DST / 'executor/PRODUCT_SHA256SUMS.txt')
    old_psha = sha(SRC / 'executor/PRODUCT_SHA256SUMS.txt')
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # A8: this copy (A7 + image r2f + airframe 4070, ../DIFF_a8.md)' % OLD,
         'OWN=/work/%s/executor  # A9: this copy (A8 + image r2g + logger restart for SDLOG_MODE 1, ../DIFF_a9.md)' % NEW, 1, 'Own folder.'),
        ('(c8 A8: fixed image r2f, /work/fixed_image_r2f_20261110/install, MANIFEST_SHA256.txt 2feb53fb)',
         '(c8 A9: fixed image r2g, /work/fixed_image_r2g_20261110/install, MANIFEST_SHA256.txt %s)' % R2G_MANIFEST_SHA[:8], 1, 'Comment.'),
        ('echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % old_psha, 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % psha, 1,
         'A9: product sums of the r2g install.'),
        ('# c8: product parameter (A8: r2f), pinned above', '# c8: product parameter (A9: r2g), pinned above', 1, 'Comment.'),
        ('# c8: product src is a parameter; the sha is r2f drone.py (A8).', '# c8: product src is a parameter; the sha is r2g drone.py (A9).', 1, 'Comment.'),
        ('echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % R2F_DRONE_SHA,
         'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % R2G_DRONE_SHA, 1, 'A9: r2g drone.py.'),
    ])
    edit('executor/sitl_setup.py', [
        ("PROFILE_SOURCE = Path('/work/fixed_image_r2f_20261110/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3); A8: r2f (same bytes)",
         "PROFILE_SOURCE = Path('/work/fixed_image_r2g_20261110/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3); A9: r2g (same bytes)",
         1, 'A9: profile path r2g (byte-identical file).'),
    ])
    edit('executor/vision_c8.launch.py', [(OLD + '/candidate', NEW + '/candidate', 2, 'A9: own candidate path (header + location check).')])
    edit('executor/run_sim.snapshot.sh', [
        ("  $B/bin/px4-logger stop; sleep 1\n"
         "  if [ \"$($B/bin/px4-param show -q SDLOG_MODE)\" = 0 ]; then $B/bin/px4-logger start -b 1000 -t; fi\n"
         "  echo \"c8: logger restarted (px4_first)\"\n",
         "  $B/bin/px4-logger stop; sleep 1\n"
         "  # A9 (M1 of the A8 review): restart with the arguments rc.logging uses for the airframe's SDLOG_MODE. Mode 1\n"
         "  # (log from boot, airframe 4070) adds -e; its boot log, closed by the stop, is moved out of the run rootfs (kept in\n"
         "  # $OUT/boot_log_before_restart) so run.sh copies exactly one fresh ULog: the restarted one (before setup and arm).\n"
         "  SDLOG=$($B/bin/px4-param show -q SDLOG_MODE)\n"
         "  case \"$SDLOG\" in\n"
         "    0) $B/bin/px4-logger start -b 1000 -t ;;\n"
         "    1) mkdir -p \"$OUT/boot_log_before_restart\"\n"
         "       if [ -d \"$OUT/rootfs/log\" ]; then find \"$OUT/rootfs/log\" -name '*.ulg' -exec mv -n {} \"$OUT/boot_log_before_restart/\" \\; ; fi\n"
         "       $B/bin/px4-logger start -b 1000 -t -e ;;\n"
         "    *) echo \"c8: SDLOG_MODE $SDLOG is not supported by this runner (0 or 1)\" >&2; exit 2 ;;\n"
         "  esac\n"
         "  echo \"c8: logger restarted (px4_first, SDLOG_MODE $SDLOG)\"\n", 1,
         'A9 (M1): logger restart for SDLOG_MODE 1 (-e), boot log moved aside; other modes refused.'),
    ])

    # 4. launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v35-c8-r2f-a8 (A8, T38 10.11.2026: runner = %s/executor, image r2f, airframe 4070; A7 was v34, A6 v33, b v32)' % OLD,
         'launcher v36-c8-r2g-a9 (A9, T39 10.11.2026: runner = %s/executor, image r2g, airframe 4070; A8 v35 (not handed out), A7 v34, A6 v33, b v32)' % NEW,
         1, 'Header.'),
        ('host_run_wsl_c8_r2e_b.sh v35-c8-r2f-a8; no real drone, no ssh', 'host_run_wsl_c8_r2e_b.sh v36-c8-r2g-a9; no real drone, no ssh', 1, 'First line.'),
        ('no TRIAL argument in v35-c8-r2f-a8', 'no TRIAL argument in v36-c8-r2g-a9', 1, 'Refusal text.'),
        ('RUNNER=$WORK/%s/executor/run.sh   # A8: the only runner of this launcher' % OLD,
         'RUNNER=$WORK/%s/executor/run.sh   # A9: the only runner of this launcher' % NEW, 1, 'Runner.'),
        ('SDLOG_MODE 1, image r2f, T22', 'SDLOG_MODE 1, image r2g, T22', 1, 'Comment.'),
        ('C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2f_20261110/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2f_20261110/src/bumblebee}',
         'C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2g_20261110/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2g_20261110/src/bumblebee}',
         1, 'A9: default image r2g.'),
        ("    runner = '%s/executor/run.sh'  # A8: the fixed runner" % OLD, "    runner = '%s/executor/run.sh'  # A9: the fixed runner" % NEW, 1, 'Pins runner.'),
        ('host_run_wsl_c8_r2e_b.sh v35-c8-r2f-a8" > "$SIDE/launcher.log"', 'host_run_wsl_c8_r2e_b.sh v36-c8-r2g-a9" > "$SIDE/launcher.log"', 1, 'Banner.'),
        ("'trial': '%s/executor'," % OLD, "'trial': '%s/executor'," % NEW, 1, 'host_check runner.'),
    ])

    # 5. tests: paths (A8 -> A9, r2f -> r2g, builder name), then the A9 cases
    for t in ('tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py', 'tests/a6_apply_order.py',
              'tests/a7_vision_launch.py', 'tests/a8_checks.py', 'tests/a8_judge_effect.py', 'tests/a8_judge_on_a7_run.py'):
        txt = (DST / t).read_text()
        n1, n2, n3 = txt.count(OLD), txt.count(IMG_OLD), txt.count('tools/make_a8.py')
        txt = txt.replace(OLD, NEW).replace(IMG_OLD, IMG_NEW).replace('tools/make_a8.py', 'tools/make_a9.py')
        (DST / t).write_text(txt)
        R.append((t, 'Paths -> A9 (%d), image -> r2g (%d), builder -> make_a9.py (%d).' % (n1, n2, n3)))
    edit('tests/test_c8_b2.sh', [
        ('$D/pins/frozen_inputs_c8_r2f_a8_01.json', '$D/pins/' + PINS_NAME, 2, 'Tests use pins A9.'),
        ('env C8_AF_FILE=/work/%s/4070_gz_bumblebee_final_4061_bat0_sdlog1 \\\n' % AFDIR, 'env C8_AF_FILE=/work/%s \\\n' % AF4070, 1,
         'Launcher pre-check with airframe 4070 v2.'),
        ('/work/c8_judge_r2e_a7_20261110/pins/frozen_inputs_c8_r2e_a7_01.json', '/work/%s/pins/frozen_inputs_c8_r2f_a8_01.json' % OLD, 1,
         'Control: the A8 pins are refused by the A9 launcher.'),
        ('echo "RESULT pass=$PASS fail=$FAIL (logs $O)"',
         '# A9 (M1): the logger restart block of run_sim.snapshot.sh with fake px4 tools: SDLOG_MODE 0 / 1 / 2; control = the A8 block\n'
         't a9_logger_restart python3 -B -I $D/tests/a9_logger_restart.py $O\n'
         '# A9: the A8 -> A9 difference is exactly image r2g + M1 (judge, expectations, candidate files unchanged)\n'
         't a9_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a9_checks.py\n'
         'echo "RESULT pass=$PASS fail=$FAIL (logs $O)"', 1, 'A9 tests added.'),
    ])
    edit('tests/a8_checks.py', [
        ("assert pins['repo_files']['fixed_image_r2g_20261110/MANIFEST_SHA256.txt'] == h(R2F / 'MANIFEST_SHA256.txt') == \\\n"
         "    '2feb53fb5420695afe23492a47bda012dd7031141b601d2f85a3cb3bbc1b9691'",
         "assert pins['repo_files']['fixed_image_r2g_20261110/MANIFEST_SHA256.txt'] == h(R2F / 'MANIFEST_SHA256.txt') == \\\n"
         "    '%s'   # A9: r2g" % R2G_MANIFEST_SHA, 1, 'A9: the reviewed r2g MANIFEST.'),
        ("pins = J(D / 'pins/frozen_inputs_c8_r2f_a8_01.json')", "pins = J(D / 'pins/%s')" % PINS_NAME, 1, 'Pins A9.'),
        ("acc = [l.split() for l in (D / 'launcher/ACCEPTED_PINS_b.txt').read_text().splitlines() if l and not l.startswith('#')]\n"
         "assert acc == [[h(D / 'pins/frozen_inputs_c8_r2f_a8_01.json'), str(D / 'pins/frozen_inputs_c8_r2f_a8_01.json')]], acc",
         "acc = [l.split() for l in (D / 'launcher/ACCEPTED_PINS_b.txt').read_text().splitlines() if l and not l.startswith('#')]\n"
         "assert acc == [[h(D / 'pins/%s'), str(D / 'pins/%s')]], acc" % (PINS_NAME, PINS_NAME), 1, 'Accepted pins A9.'),
        ("ren = lambda k: k.replace('c8_judge_r2e_a7_20261110/', 'c8_judge_r2g_a9_20261110/').replace('fixed_image_r2e_20261109/', 'fixed_image_r2g_20261110/')",
         "ren = lambda k: k.replace('c8_judge_r2e_a7_20261110/', 'c8_judge_r2g_a9_20261110/').replace('fixed_image_r2e_20261109/', 'fixed_image_r2g_20261110/')  # A9",
         1, 'Key mapping A7 -> A9 (checked: the path replacement already gives it).'),
    ])
    a8_af = "AF4070 = AF / '4070_gz_bumblebee_final_4061_bat0_sdlog1'"
    if Path(AF4070).name != '4070_gz_bumblebee_final_4061_bat0_sdlog1':
        edit('tests/a8_checks.py', [(a8_af, "AF4070 = AF / '%s'   # A9: the Simulator's 4070 with EKF2_OF_QMIN 50" % Path(AF4070).name,
                                     1, 'A9: airframe 4070 file name.')])
    edit('tests/a8_judge_on_a7_run.py', [
        ("mm = lc['real_parameters_before_arm']['evidence']['mismatches']\n",
         "mm = lc['real_parameters_before_arm']['evidence']['mismatches']\n"
         "# A9 (S1 of the A8 review): every EXPECT_4070 name must really be judged (not only the ones that differ here)\n"
         "assert set(EXPECT) <= set(lc['real_parameters_before_arm']['evidence']['values']), sorted(EXPECT)\n", 1,
         'A9 (S1): all EXPECT_4070 names must be judged.'),
    ])
    for f in ('a9_logger_restart.py', 'a9_checks.py'):
        shutil.copy2(Path(__file__).with_name(f), DST / 'tests' / f)
        R.append(('tests/' + f, 'New test (A9).'))

    # 6. pins A9
    new = json.loads(json.dumps(old_pins))
    changed = set()
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1).replace(IMG_OLD + '/', IMG_NEW + '/', 1)
            if nn.startswith(AFDIR + '/4070_'):
                g[nn] = h          # removed below (v1 moved aside), v2 added
                continue
            h2 = R2G_DRONE_SHA if nn == '@run/drone.py' else sha(WORK / nn)
            if h2 != h:
                changed.add(nn)
            g[nn] = h2
        new[group] = g
    for k, v in old_pins['run_files'].items():
        p = DST / 'executor' / k if (DST / 'executor' / k).exists() else R2G / 'src/bumblebee/examples' / k
        new['run_files'][k] = sha(p)
        if new['run_files'][k] != v:
            changed.add('run_files:' + k)
    # airframe 4070 of the Simulator with EKF2_OF_QMIN 50 (the A8 entry is replaced if the file name changed)
    old_af = [k for k in new['repo_files'] if k.startswith(AFDIR + '/4070_')]
    if len(old_af) != 1:
        sys.exit('STOP: A8 pins have %d airframe 4070 entries' % len(old_af))
    del new['repo_files'][old_af[0]]
    new['repo_files'][AF4070] = AF4070_SHA
    changed.add(AF4070)
    new['c8_target']['airframe_chain'] = [Path(AF4070).name] + [n for n in old_pins['c8_target']['airframe_chain'] if not n.startswith('4070_')]
    allowed = {NEW + '/executor/run.sh', NEW + '/verify_flight_c8.py', NEW + '/expect/flight_real_params_4070.json', AF4070, NEW + '/executor/run_sim.snapshot.sh', NEW + '/executor/sitl_setup.py',
               NEW + '/executor/PRODUCT_SHA256SUMS.txt', NEW + '/executor/vision_c8.launch.py', '@run/drone.py',
               IMG_NEW + '/src/bumblebee/examples/drone.py', IMG_NEW + '/install/bumblebee/lib/bumblebee/simple_offboard',
               IMG_NEW + '/MANIFEST_SHA256.txt', IMG_NEW + '/image_manifest_r2.tsv',
               'run_files:run.sh', 'run_files:run_sim.snapshot.sh', 'run_files:sitl_setup.py', 'run_files:drone.py',
               'run_files:vision_c8.launch.py'}
    if not changed <= allowed:
        sys.exit('STOP: unexpected changes: %s' % sorted(changed - allowed))
    R.append(('pins/' + PINS_NAME, 'Changed entries: %s' % sorted(changed)))
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    new['combined_manifest_sha256'] = sha(DST / 'candidate/manifest.json')
    if new['combined_files'] != json.loads((DST / 'candidate/manifest.json').read_text())['files']:
        sys.exit('STOP: candidate files changed')
    new['sdk_drone_py'].update(source=str(R2G / 'src/bumblebee/examples/drone.py'), sha256=R2G_DRONE_SHA,
                               product_tag='fixed image r2g (MANIFEST_SHA256.txt %s)' % R2G_MANIFEST_SHA[:8], by=NEW + '/tools/make_a9.py')
    new['c8_target'].update(product_install=str(R2G / 'install'), product_src=str(R2G / 'src/bumblebee'),
                            combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4070',
                            a9='image r2g (S4) + logger restart for SDLOG_MODE 1 (M1 of the A8 review) (T39)')
    P = DST / 'pins' / PINS_NAME
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v36-c8-r2g-a9 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# %s = pins A8 (65d0f719) renamed + image r2g + run_sim.snapshot.sh M1 (tools/make_a9.py)\n'
                '%s  %s\n' % (NEW, PINS_NAME, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a9.py')

    # 7. DIFF_a9.md against A8
    out = ['# DIFF A8 -> A9 (generated by tools/make_a9.py)\n']
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
        a, b = q.read_text().splitlines(), p.read_text().splitlines()
        d = list(difflib.unified_diff(a, b, str(q), str(p), lineterm='', n=0))
        if len(d) > 400:
            out.append('\n## %s: %d diff lines (regenerated file), first 8:\n```\n%s\n```\n' % (rel, len(d), '\n'.join(d[:8])))
        else:
            out.append('\n## %s\n```diff\n%s\n```\n' % (rel, '\n'.join(d)))
    with open(DST / 'DIFF_a9.md', 'x') as h:
        h.write(''.join(out))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge_same': sha(DST / 'verify_flight_c8.py') == JUDGE_SHA,
                      'manifest': new['combined_manifest_sha256'], 'product_sums': psha, 'changed': sorted(changed), 'edits': len(R)}))


if __name__ == '__main__':
    main()
