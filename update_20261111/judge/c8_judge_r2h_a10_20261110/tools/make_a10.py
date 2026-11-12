#!/usr/bin/env python3
"""make_a10.py - T44 (10.11.2026): C8 package revision A10 = A9 (/work/c8_judge_r2g_a9_20261110, pins 4b46f4d4; review:
accepted with notes) with the image FINAL r2h (/work/fixed_image_r2h_20261110) byte for byte instead of r2g.
What changes, and only this:
 - candidate/parameters/vpe_fix.py = the r2h vpe_fix (flight_profile.py and aruco_detect.py: same bytes in r2g and r2h);
 - chat 1 variant B (T44, 18:29): vpe_fix publishes as on the drone. executor/vpe_diagnostic_entry.py no longer installs
   the freshness opt-in (its mixin published only the newest pose and dropped the r2h B2 medoid; no judge reads its
   output); candidate/parameters/vpe_freshness_optin.py stays the A9 file, not loaded. The gate diagnostic (observation
   only; the judge reads its VPE_GATE_DIAG_START line) and the profile opt-in (parameter service; the judge reads its
   journal) stay;
 - the two loaded places that pin the vpe_fix sha (3b8a93d4 since r2e): candidate/parameters/vpe_profile_optin.py and
   executor/vpe_gate_diagnostic_p1.py TARGET_SHA256; vpe_diagnostic_entry.py pins the new helper sha;
 - run.sh: product sums of the r2h install, r2h drone.py; sitl_setup PROFILE_SOURCE path (same bytes); own paths, launcher
   version, pins A10, tests (paths; a9_checks.py is replaced by a10_checks.py = the A9 -> A10 difference).
Judge (1ab83ca4), legacy copy, expectations, airframe 4070 v2, run_sim.snapshot.sh, profile order: as in A9.
VARIANT is the composition choice of chat 1 (T44): 'B' = no freshness opt-in (vpe_fix as on the drone).
Usage: python3 -I make_a10.py   (refuses to overwrite)
"""
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# name: (value, MAVLink param type) in flight_real_params_4070.json -- UNCHANGED from A9 (tools/make_a9.py; the
# expectation files are byte-copies of A9's; the A8 tests read the values from this builder; a10_checks compares)
EXPECT_4070 = {
    'BAT1_SOURCE': (0, 6),   # approved drone set, owner 09.11 «да» (4061: 1)
    'SDLOG_MODE': (1, 6),    # log from boot, owner 10.11 «В» (new name)
    'EKF2_OF_QMIN': (50, 6), # A9: flow quality minimum, owner 10.11 (T33, smooth landing; 20EC: 1) (new name)
}

VARIANT = 'B'
WORK = Path('/work')
SRC = WORK / 'c8_judge_r2g_a9_20261110'
DST = WORK / 'c8_judge_r2h_a10_20261110'
OLD, NEW = 'c8_judge_r2g_a9_20261110', 'c8_judge_r2h_a10_20261110'
IMG_OLD, IMG_NEW = 'fixed_image_r2g_20261110', 'fixed_image_r2h_20261110'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2g_a9_01.json'
PINS_SRC_SHA = '4b46f4d421c7b311d1de18e6ec2f8dc81ee65bc095a8540b380077c8740c05f6'
PINS_NAME = 'frozen_inputs_c8_r2h_a10_01.json'
JUDGE_SHA = '1ab83ca41f435250d523cb6697f6cda0331f8e2db6d6a9fd6051c9495924c27d'
R2G, R2H = WORK / IMG_OLD, WORK / IMG_NEW
R2H_MANIFEST_SHA = sys.argv[1] if len(sys.argv) > 1 else None      # the reviewed final r2h MANIFEST_SHA256.txt
R2G_VPE = '3b8a93d4d08983694186766b0259fa6fa6b4167079c4078cf402a908d02e9725'
R2G_DRONE = '068e6eb44ab01ad8807337b0c50d4f47c543d554cc3c09323d9043e39e2d3661'
R2H_DRONE = 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c'
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py', 'tests/a6_apply_order.py', 'tests/a7_vision_launch.py', 'tests/a8_checks.py',
        'tests/a8_judge_effect.py', 'tests/a8_judge_on_a7_run.py', 'tests/a9_logger_restart.py']
IMAGE_COPIES = {'candidate/parameters/flight_profile.py': 'src/bumblebee/examples/flight_profile.py',
                'candidate/parameters/vpe_fix.py': 'src/bumblebee/src/python/vpe_fix.py',
                'candidate/vision/aruco_detect.py': 'src/bumblebee/src/python/aruco_detect.py'}
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


def product_list(a9_list):
    """the r2g install held 17 Python byte-code caches (__pycache__/*.pyc); the r2h install has none (the image test
    scripts remove __pycache__). Caches only: the A10 list is the A9 list without them, same order."""
    inst = R2H / 'install'
    now_list = sorted('./' + str(p.relative_to(inst)) for p in inst.rglob('*') if p.is_file())
    a10_list = [n for n in a9_list if '/__pycache__/' not in n]
    if len(a9_list) - len(a10_list) != 17 or sorted(a10_list) != now_list:
        sys.exit('STOP: r2h install file list differs from the A9 product list: %s' % sorted(set(a10_list) ^ set(now_list))[:10])
    return a10_list


def main():
    product_list([l[66:] for l in (SRC / 'executor/PRODUCT_SHA256SUMS.txt').read_text().splitlines()])   # before any write
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if VARIANT != 'B':
        sys.exit('STOP: only variant B (chat 1, 18:29) is implemented')
    if sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA:
        sys.exit('STOP: A9 changed')
    if R2H_MANIFEST_SHA is None or sha(R2H / 'MANIFEST_SHA256.txt') != R2H_MANIFEST_SHA:
        sys.exit('STOP: give the reviewed r2h MANIFEST sha; the folder has %s' % sha(R2H / 'MANIFEST_SHA256.txt'))
    for f in ('MANIFEST_SHA256.txt', 'SHA256SUMS'):
        subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2H, check=True)
    if sha(R2H / 'src/bumblebee/examples/drone.py') != R2H_DRONE or sha(R2G / 'src/bumblebee/examples/drone.py') != R2G_DRONE:
        sys.exit('STOP: drone.py r2h / r2g')
    if sha(R2G / 'src/bumblebee/src/python/vpe_fix.py') != R2G_VPE:
        sys.exit('STOP: r2g vpe_fix')
    R2H_VPE = sha(R2H / 'src/bumblebee/src/python/vpe_fix.py')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins A9: ' + name)
    for c, i in IMAGE_COPIES.items():
        if sha(SRC / c) != sha(R2G / i):
            sys.exit('STOP: A9 candidate copy differs from r2g: ' + c)
        if c != 'candidate/parameters/vpe_fix.py' and sha(R2G / i) != sha(R2H / i):
            sys.exit('STOP: %s differs between r2g and r2h' % i)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A10 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()

    # 1. candidate: the r2h vpe_fix, and the vpe_fix pins of the composition
    shutil.copy2(R2H / IMAGE_COPIES['candidate/parameters/vpe_fix.py'], DST / 'candidate/parameters/vpe_fix.py')
    R.append(('candidate/parameters/vpe_fix.py', 'A10: copy of the final r2h vpe_fix (%s).' % R2H_VPE[:8]))
    # variant B: vpe_freshness_optin.py stays the A9 file (not loaded any more; its PIN_C33 is the r2g sha)
    edit('candidate/parameters/vpe_profile_optin.py', [
        ("    if hashlib.sha256(original.read_bytes()).hexdigest()!='%s':  # c8-r2e-b: r2e vpe_fix\n" % R2G_VPE,
         "    if hashlib.sha256(original.read_bytes()).hexdigest()!='%s':  # A10: r2h vpe_fix (c8-r2e-b..A9: r2e = r2g)\n" % R2H_VPE, 1,
         'A10: the profile opt-in pins the r2h vpe_fix.')])
    edit('executor/vpe_gate_diagnostic_p1.py', [
        ("TARGET_SHA256 = '%s'  # c8-r2e-b (D2): r2e vpe_fix\n" % R2G_VPE,
         "TARGET_SHA256 = '%s'  # A10: r2h vpe_fix (c8-r2e-b (D2)..A9: r2e = r2g)\n" % R2H_VPE, 1,
         'A10: the gate diagnostic pins the r2h vpe_fix.')])
    old_helper, old_fresh = sha(SRC / 'executor/vpe_gate_diagnostic_p1.py'), sha(SRC / 'candidate/parameters/vpe_freshness_optin.py')
    new_helper = sha(DST / 'executor/vpe_gate_diagnostic_p1.py')
    edit('executor/vpe_diagnostic_entry.py', [
        ("hexdigest()=='%s'  # c8-r2e-b: vpe_gate_diagnostic_p1.py with the r2e TARGET_SHA256" % old_helper,
         "hexdigest()=='%s'  # A10: vpe_gate_diagnostic_p1.py with the r2h TARGET_SHA256" % new_helper, 1,
         'A10: entry pins the new diagnostic helper.'),
        ("# flight_trial_07 / combined_04 (handover §8 п.5): VPE freshness on the pinned CLEAN c33 VpeFix first (install() verifies\n"
         "# the c33 file SHA, method bodies and constants), then the diagnostic wrapper on the resulting FreshVpe class.\n"
         "# vpe_profile_optin.main() re-imports vpe_fix.VpeFix -> NodeClass = parameters(FreshVpe) (FreshBase order).\n"
         "import vpe_freshness_optin\n"
         "assert hashlib.sha256(Path(vpe_freshness_optin.__file__).read_bytes()).hexdigest()=='%s'  # combined_c8_r2e\n"
         "vpe_freshness_optin.install(vpe_fix,enabled=True)\n" % old_fresh,
         "# A10 (T44, chat 1 variant B, 10.11.2026): NO freshness opt-in. vpe_fix publishes as on the drone (aruco.launch.py runs\n"
         "# vpe_fix.py itself; the freshness mixin published only the newest pose and dropped the r2h B2 medoid). What stays:\n"
         "# the gate diagnostic below (observation only, same result) and the profile opt-in class (parameter service only).\n"
         "# vpe_profile_optin.main() re-imports vpe_fix.VpeFix -> NodeClass = parameters(VpeFix).\n", 1,
         'A10 (variant B): the freshness opt-in is not installed (vpe_fix as on the drone).'),
    ])

    # 2. candidate manifest
    mp = DST / 'candidate/manifest.json'
    mt = mp.read_text()
    m = json.loads(mt)
    if dump(m, 1) != mt:
        sys.exit('STOP: manifest format')
    m['scope'] = edit_text(m['scope'], 'candidate/manifest.json:scope', [
        ('combined_c8_r2g (A9, T39 10.11.2026; A8: r2f; T28: r2e): combined_13 + fixed image r2g parts',
         'combined_c8_r2h (A10, T44 10.11.2026; A9: r2g; A8: r2f; T28: r2e): combined_13 + fixed image r2h (final) parts', 1, 'Scope text.')])
    for k in IMAGE_COPIES:
        kk = k[len('candidate/'):]
        m['origins'][kk] = edit_text(m['origins'][kk], 'candidate/manifest.json:origins:' + kk,
                                     [(IMG_OLD, IMG_NEW, 1, 'Origin r2g -> r2h.')])
    m['origins']['parameters/vpe_profile_optin.py'] += '; A10: pinned vpe_fix sha = r2h'
    m['origins']['parameters/vpe_freshness_optin.py'] += '; A10: NOT loaded (variant B: vpe_fix as on the drone), file as A9'
    R.append(('candidate/manifest.json:origins', 'A10 notes (profile pin r2h; freshness not loaded).'))
    for kk in ('parameters/vpe_fix.py', 'parameters/vpe_profile_optin.py'):
        m['files'][kk] = sha(DST / 'candidate' / kk)
        R.append(('candidate/manifest.json:files:' + kk, 'A10: new sha.'))
    if {k for k in m['files'] if m['files'][k] != json.loads(mt)['files'][k]} != {
            'parameters/vpe_fix.py', 'parameters/vpe_profile_optin.py'}:
        sys.exit('STOP: manifest files')
    for k, v in m['files'].items():
        if sha(DST / 'candidate' / k) != v:
            sys.exit('STOP: manifest sha ' + k)
    mp.write_text(dump(m, 1))
    with open(DST / 'candidate/README.md', 'a') as h:
        h.write('A10 (T44, 10.11.2026): image FINAL r2h: vpe_fix.py = r2h (%s); the vpe_fix pin of vpe_profile_optin.py = r2h; '
                'vpe_freshness_optin.py is kept as in A9 but NOT loaded (chat 1 variant B: vpe_fix publishes as on the drone); '
                'flight_profile.py and aruco_detect.py byte-identical in r2g and r2h; the rest as A9.\n' % R2H_VPE[:8])
    R.append(('candidate/README.md', 'One line appended.'))

    # 3. executor
    inst = R2H / 'install'
    a9_list = [l[66:] for l in (SRC / 'executor/PRODUCT_SHA256SUMS.txt').read_text().splitlines()]
    a10_list = product_list(a9_list)
    (DST / 'executor/PRODUCT_SHA256SUMS.txt').write_text(''.join('%s  %s\n' % (sha(inst / n[2:]), n) for n in a10_list))
    R.append(('executor/PRODUCT_SHA256SUMS.txt', 'Regenerated from the r2h install (%d paths = the A9 %d without the 17 '
                                                 '__pycache__ files, same order).' % (len(a10_list), len(a9_list))))
    psha, old_psha = sha(DST / 'executor/PRODUCT_SHA256SUMS.txt'), sha(SRC / 'executor/PRODUCT_SHA256SUMS.txt')
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # A9: this copy (A8 + image r2g + logger restart for SDLOG_MODE 1, ../DIFF_a9.md)' % OLD,
         'OWN=/work/%s/executor  # A10: this copy (A9 + image final r2h, ../DIFF_a10.md)' % NEW, 1, 'Own folder.'),
        ('(c8 A9: fixed image r2g, /work/fixed_image_r2g_20261110/install, MANIFEST_SHA256.txt 3d503cef)',
         '(c8 A10: fixed image r2h, /work/fixed_image_r2h_20261110/install, MANIFEST_SHA256.txt %s)' % R2H_MANIFEST_SHA[:8], 1, 'Comment.'),
        ('echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % old_psha, 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % psha, 1,
         'A10: product sums of the r2h install.'),
        ('# c8: product parameter (A9: r2g), pinned above', '# c8: product parameter (A10: r2h), pinned above', 1, 'Comment.'),
        ('# c8: product src is a parameter; the sha is r2g drone.py (A9).', '# c8: product src is a parameter; the sha is r2h drone.py (A10).', 1, 'Comment.'),
        ('echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % R2G_DRONE, 'echo "%s  $C8_PRODUCT_SRC/examples/drone.py"' % R2H_DRONE, 1,
         'A10: r2h drone.py.'),
    ])
    edit('executor/sitl_setup.py', [
        ("PROFILE_SOURCE = Path('/work/fixed_image_r2g_20261110/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3); A9: r2g (same bytes)",
         "PROFILE_SOURCE = Path('/work/fixed_image_r2h_20261110/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3); A10: r2h (same bytes)",
         1, 'A10: profile path r2h (byte-identical file).')])
    edit('executor/vision_c8.launch.py', [(OLD + '/candidate', NEW + '/candidate', 2, 'A10: own candidate path (header + location check).')])

    # 4. launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v36-c8-r2g-a9 (A9, T39 10.11.2026: runner = %s/executor, image r2g, airframe 4070; A8 v35 (not handed out), A7 v34, A6 v33, b v32)' % OLD,
         'launcher v37-c8-r2h-a10 (A10, T44 10.11.2026: runner = %s/executor, image final r2h, airframe 4070; A9 v36, A8 v35 (not handed out), A7 v34, A6 v33, b v32)' % NEW,
         1, 'Header.'),
        ('host_run_wsl_c8_r2e_b.sh v36-c8-r2g-a9; no real drone, no ssh', 'host_run_wsl_c8_r2e_b.sh v37-c8-r2h-a10; no real drone, no ssh', 1, 'First line.'),
        ('no TRIAL argument in v36-c8-r2g-a9', 'no TRIAL argument in v37-c8-r2h-a10', 1, 'Refusal text.'),
        ('RUNNER=$WORK/%s/executor/run.sh   # A9: the only runner of this launcher' % OLD,
         'RUNNER=$WORK/%s/executor/run.sh   # A10: the only runner of this launcher' % NEW, 1, 'Runner.'),
        ('SDLOG_MODE 1, image r2g, T22', 'SDLOG_MODE 1, image r2h, T22', 1, 'Comment.'),
        ('C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2g_20261110/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2g_20261110/src/bumblebee}',
         'C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2h_20261110/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2h_20261110/src/bumblebee}',
         1, 'A10: default image r2h.'),
        ("    runner = '%s/executor/run.sh'  # A9: the fixed runner" % OLD, "    runner = '%s/executor/run.sh'  # A10: the fixed runner" % NEW, 1, 'Pins runner.'),
        ('host_run_wsl_c8_r2e_b.sh v36-c8-r2g-a9" > "$SIDE/launcher.log"', 'host_run_wsl_c8_r2e_b.sh v37-c8-r2h-a10" > "$SIDE/launcher.log"', 1, 'Banner.'),
        ("'trial': '%s/executor'," % OLD, "'trial': '%s/executor'," % NEW, 1, 'host_check runner.'),
    ])

    # 5. tests: paths, then the A10 cases
    for t in ('tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py', 'tests/a6_apply_order.py',
              'tests/a7_vision_launch.py', 'tests/a8_checks.py', 'tests/a8_judge_effect.py', 'tests/a8_judge_on_a7_run.py',
              'tests/a9_logger_restart.py'):
        txt = (DST / t).read_text()
        n1, n2, n3 = txt.count(OLD), txt.count(IMG_OLD), txt.count('tools/make_a9.py')
        txt = txt.replace(OLD, NEW).replace(IMG_OLD, IMG_NEW).replace('tools/make_a9.py', 'tools/make_a10.py')
        (DST / t).write_text(txt)
        R.append((t, 'Paths -> A10 (%d), image -> r2h (%d), builder -> make_a10.py (%d).' % (n1, n2, n3)))
    edit('tests/test_c8_b2.sh', [
        ('$D/pins/frozen_inputs_c8_r2g_a9_01.json', '$D/pins/' + PINS_NAME, 2, 'Tests use pins A10.'),
        ("diagnostic.TARGET_SHA256 == '%s'" % R2G_VPE, "diagnostic.TARGET_SHA256 == '%s'" % R2H_VPE, 1,
         'd2: the composition pins the r2h vpe_fix.'),
        ("# 6. D2: VPE composition with the r2e vpe_fix (ROS sourced, no node started): freshness + diagnostic wrapper + opt-in class\n",
         "# 6. D2: VPE composition with the r2h vpe_fix (ROS sourced, no node started): diagnostic wrapper + opt-in class, NO freshness (A10, variant B)\n",
         1, 'd2 comment.'),
        ("import vpe_freshness_optin, vpe_profile_optin\n"
         "c33 = vpe_fix.VpeFix\n"
         "vpe_freshness_optin.install(vpe_fix, enabled=True)\n",
         "import vpe_profile_optin\n"
         "c33 = vpe_fix.VpeFix\n", 1, 'd2: composition without freshness (as the A10 entry).'),
        ("assert 'FreshnessMixin' in mro and issubclass(vpe_fix.VpeFix, c33) and Node._freshness_pose_timeout_ns == 500000000, mro\n",
         "assert 'FreshnessMixin' not in mro and vpe_fix.VpeFix is c33 and Node.__mro__[1] is c33 and not hasattr(Node, '_freshness_pose_timeout_ns'), mro   # A10: as on the drone\n",
         1, 'd2: no freshness in the node class.'),
        ("# 7. vpe_diagnostic_entry pins = the new helper and the candidate freshness file\n",
         "# 7. vpe_diagnostic_entry pins = the new helper; it never loads the freshness opt-in (A10, variant B)\n", 1, 'd2_entry comment.'),
        ("assert h('$D/executor/vpe_gate_diagnostic_p1.py') in s and h('$D/candidate/parameters/vpe_freshness_optin.py') in s\n",
         "assert h('$D/executor/vpe_gate_diagnostic_p1.py') in s and 'vpe_freshness_optin' not in s and 'install(' not in s\n", 1,
         'd2_entry: helper pinned, freshness not loaded.'),
        ("t a9_logger_restart python3 -B -I $D/tests/a9_logger_restart.py $O\n",
         "t a9_logger_restart python3 -B -I $D/tests/a9_logger_restart.py $O\n"
         "# A10 (variant B): the vision pose goes out as on the drone (offline bench, the real classes, as the A10 entry composes them)\n"
         "t a10_vpe_as_drone python3 -B -I $D/tests/a10_vpe_as_drone.py\n", 1, 'a10_vpe_as_drone added.'),
        ('/work/c8_judge_r2f_a8_20261110/pins/frozen_inputs_c8_r2f_a8_01.json', '/work/%s/pins/frozen_inputs_c8_r2g_a9_01.json' % OLD, 1,
         'Control: the A9 pins are refused by the A10 launcher.'),
        ('# A9: the A8 -> A9 difference is exactly image r2g + M1 (judge, expectations, candidate files unchanged)\n'
         't a9_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a9_checks.py\n',
         '# A10: the A9 -> A10 difference is exactly the image final r2h (judge, expectations, run_sim unchanged)\n'
         't a10_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a10_checks.py\n', 1, 'a9_checks -> a10_checks.'),
    ])
    edit('tests/a8_checks.py', [
        ("    assert h(D / 'candidate' / c) == h(R2F / i) == h(A7 / 'candidate' / c), c\n",
         "    assert h(D / 'candidate' / c) == h(R2F / i), c   # A10: image copies = r2h bytes\n"
         "    assert h(R2F / i) == h(A7 / 'candidate' / c) or c == 'parameters/vpe_fix.py', c   # A10: only vpe_fix changed since A7\n",
         1, 'A10: candidate image copies = r2h; vpe_fix differs from A7 on purpose.'),
        ("norm = lambda l: l[1:].replace('4061', 'X').replace('4070', 'X').replace('  # A8: airframe X', '')\n"
         "assert [norm(l) for l in d if l.startswith('-')] == [norm(l) for l in d if l.startswith('+')] and len(d) == 4, d\n",
         "norm = lambda l: l[1:].replace('4061', 'X').replace('4070', 'X').replace('  # A8: airframe X', '') \\\n"
         "    .replace('%s', 'V').replace('%s', 'V').replace('  # A10: r2h vpe_fix (c8-r2e-b..A9: r2e = r2g)', '  # c8-r2e-b: r2e vpe_fix')   # A10\n"
         "assert [norm(l) for l in d if l.startswith('-')] == [norm(l) for l in d if l.startswith('+')] and len(d) == 6, d   # A10: + the vpe_fix pin line\n"
         % (R2G_VPE, R2H_VPE), 1, 'A10: vpe_profile_optin differs from A7 by the airframe check and the vpe_fix pin.'),
        ("assert set(ma) == set(mb) and [k for k in ma if ma[k] != mb[k]] == ['parameters/vpe_profile_optin.py']\n",
         "assert set(ma) == set(mb) and {k for k in ma if ma[k] != mb[k]} == {'parameters/vpe_profile_optin.py', 'parameters/vpe_fix.py'}   # A10: + r2h vpe_fix\n",
         1, 'A10: manifest files differ from A7 also in vpe_fix.'),
        ("pins = J(D / 'pins/frozen_inputs_c8_r2g_a9_01.json')", "pins = J(D / 'pins/%s')" % PINS_NAME, 1, 'Pins A10.'),
        ("assert acc == [[h(D / 'pins/frozen_inputs_c8_r2g_a9_01.json'), str(D / 'pins/frozen_inputs_c8_r2g_a9_01.json')]], acc",
         "assert acc == [[h(D / 'pins/%s'), str(D / 'pins/%s')]], acc" % (PINS_NAME, PINS_NAME), 1, 'Accepted pins A10.'),
        ("    '3d503cef2e2187c38c1a3dd2a71eb205d12216d38dedfca4eb0ad546fec76779'   # A9: r2g",
         "    '%s'   # A10: final r2h" % R2H_MANIFEST_SHA, 1, 'A10: the reviewed r2h MANIFEST.'),
    ])
    for f in ('a10_checks.py', 'a10_vpe_as_drone.py'):
        shutil.copy2(Path(__file__).with_name(f), DST / 'tests' / f)
        R.append(('tests/' + f, 'New test (A10).'))

    # 6. pins A10
    new = json.loads(json.dumps(old_pins))
    changed = set()
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1).replace(IMG_OLD + '/', IMG_NEW + '/', 1)
            h2 = R2H_DRONE if nn == '@run/drone.py' else sha(WORK / nn)
            if h2 != h:
                changed.add(nn)
            g[nn] = h2
        new[group] = g
    for k, v in old_pins['run_files'].items():
        p = DST / 'executor' / k if (DST / 'executor' / k).exists() else R2H / 'src/bumblebee/examples' / k
        new['run_files'][k] = sha(p)
        if new['run_files'][k] != v:
            changed.add('run_files:' + k)
    allowed = {NEW + '/executor/run.sh', NEW + '/executor/sitl_setup.py', NEW + '/executor/PRODUCT_SHA256SUMS.txt',
               NEW + '/executor/vision_c8.launch.py', NEW + '/executor/vpe_gate_diagnostic_p1.py', NEW + '/executor/vpe_diagnostic_entry.py',
               NEW + '/candidate/parameters/vpe_fix.py',
               NEW + '/candidate/parameters/vpe_profile_optin.py', '@run/drone.py',
               IMG_NEW + '/src/bumblebee/examples/drone.py', IMG_NEW + '/src/bumblebee/src/python/vpe_fix.py',
               IMG_NEW + '/install/bumblebee/lib/bumblebee/simple_offboard', IMG_NEW + '/MANIFEST_SHA256.txt', IMG_NEW + '/image_manifest_r2.tsv',
               'run_files:run.sh', 'run_files:sitl_setup.py', 'run_files:drone.py', 'run_files:vision_c8.launch.py',
               'run_files:vpe_gate_diagnostic_p1.py', 'run_files:vpe_diagnostic_entry.py'}
    if not changed <= allowed:
        sys.exit('STOP: unexpected changes: %s' % sorted(changed - allowed))
    R.append(('pins/' + PINS_NAME, 'Changed entries: %s' % sorted(changed)))
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    new['combined_manifest_sha256'] = sha(DST / 'candidate/manifest.json')
    new['combined_files'] = json.loads((DST / 'candidate/manifest.json').read_text())['files']
    new['sdk_drone_py'].update(source=str(R2H / 'src/bumblebee/examples/drone.py'), sha256=R2H_DRONE,
                               product_tag='fixed image r2h final (MANIFEST_SHA256.txt %s)' % R2H_MANIFEST_SHA[:8], by=NEW + '/tools/make_a10.py')
    new['c8_target'].update(product_install=str(R2H / 'install'), product_src=str(R2H / 'src/bumblebee'),
                            combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4070',
                            a10='image final r2h byte for byte (vpe_fix B1/B2, drone.py W) (T44)')
    P = DST / 'pins' / PINS_NAME
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v37-c8-r2h-a10 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# %s = pins A9 (4b46f4d4) renamed + image final r2h (tools/make_a10.py)\n'
                '%s  %s\n' % (NEW, PINS_NAME, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a10.py')

    # 7. DIFF_a10.md against A9
    out = ['# DIFF A9 -> A10 (generated by tools/make_a10.py)\n']
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
    with open(DST / 'DIFF_a10.md', 'x') as h:
        h.write(''.join(out))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge_same': sha(DST / 'verify_flight_c8.py') == JUDGE_SHA,
                      'manifest': new['combined_manifest_sha256'], 'product_sums': psha, 'changed': sorted(changed), 'edits': len(R)}))


if __name__ == '__main__':
    main()
