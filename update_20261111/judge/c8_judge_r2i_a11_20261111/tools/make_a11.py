#!/usr/bin/env python3
"""make_a11.py - T46 addendum of chat 1 (11.11.2026): C8 package revision A11 = A10 edition 2
(/work/c8_judge_r2h_a10_20261110, SHA256SUMS.txt 4f44222b, pins 9ec805e7; reviews: accepted with notes) with the image
r2i (/work/fixed_image_r2i_20261111, SHA256SUMS 38daf429, MANIFEST 855f9f93) byte for byte instead of r2h.
What changes, and only this:
 - candidate/parameters/vpe_fix.py = the r2i vpe_fix (vision in AUTO.LAND); flight_profile.py and aruco_detect.py: the
   same bytes in r2h and r2i (checked);
 - the two loaded vpe_fix pins (vpe_profile_optin.py, executor/vpe_gate_diagnostic_p1.py TARGET_SHA256) = the r2i sha;
   vpe_diagnostic_entry.py pins the new helper sha;
 - run.sh: product sums of the r2i install (the r2i simple_offboard binary carries the S9 change); drone.py sha unchanged
   (r2i drone.py = r2h bytes); sitl_setup PROFILE_SOURCE path; own paths, launcher v38, pins A11, tests (paths;
   a10_checks.py is replaced by a11_checks.py = the A10 -> A11 difference); executor/tests/test_entry_order.py paths.
Judge (1ab83ca4), legacy copy, expectations, airframe 4070 v2, run_sim.snapshot.sh, the S scenarios, variant B
(no freshness opt-in): as in A10. The S9 change lives in the image (simple_offboard), not in the test.
Usage: python3 -I make_a11.py   (refuses to overwrite)
"""
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# UNCHANGED from A10 / A9 (the A8 tests read the values from this builder; a11_checks compares)
EXPECT_4070 = {
    'BAT1_SOURCE': (0, 6),   # approved drone set, owner 09.11 «да» (4061: 1)
    'SDLOG_MODE': (1, 6),    # log from boot, owner 10.11 «В» (new name)
    'EKF2_OF_QMIN': (50, 6), # A9: flow quality minimum, owner 10.11 (T33, smooth landing; 20EC: 1) (new name)
}

WORK = Path('/work')
SRC = WORK / 'c8_judge_r2h_a10_20261110'
DST = WORK / 'c8_judge_r2i_a11_20261111'
OLD, NEW = 'c8_judge_r2h_a10_20261110', 'c8_judge_r2i_a11_20261111'
IMG_OLD, IMG_NEW = 'fixed_image_r2h_20261110', 'fixed_image_r2i_20261111'
R2H, R2I = WORK / IMG_OLD, WORK / IMG_NEW
A10_SUMS = '4f44222becddab42f9a733a1bcd7a8b96e6fd0004bfafc3391f195a59cc9b3ef'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2h_a10_01.json'
PINS_SRC_SHA = '9ec805e7360beca7646c4a7d337ff7056e8776ae11862537b9b9fb6145544358'
PINS_NAME = 'frozen_inputs_c8_r2i_a11_01.json'
JUDGE_SHA = '1ab83ca41f435250d523cb6697f6cda0331f8e2db6d6a9fd6051c9495924c27d'
R2I_SUMS = '38daf42986a93e361128fc05fc8d05315320e8cff6fca4d2bbd63381a22d0204'
R2I_MANIFEST_SHA = '855f9f93e2166d8cde1156f6f010728210919882337e30fade4d7ba63f58412b'
R2H_MANIFEST_SHA = '548bd2616b639482c7a13824477040cf2c19a84bff1510af8f540419e8153f1c'
R2H_VPE = '66d806baf5ef6884bdc7e1636289e90dd55964f8f69ed0ffa13be2e23f5e6958'
R2I_VPE = 'f0dc7c18f2fa24ffd7c9baffd92e8f3dd723c0521c27eedb4eeef408faa8642d'
DRONE = 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c'   # r2h = r2i
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py', 'tests/a6_apply_order.py', 'tests/a7_vision_launch.py', 'tests/a8_checks.py',
        'tests/a8_judge_effect.py', 'tests/a8_judge_on_a7_run.py', 'tests/a9_logger_restart.py', 'tests/a10_vpe_as_drone.py']
RENAME = ['executor/run.sh', 'executor/sitl_setup.py', 'executor/vision_c8.launch.py', 'executor/tests/test_entry_order.py',
          'launcher/host_run_wsl_c8_r2e_b.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py',
          'tests/a6_apply_order.py', 'tests/a7_vision_launch.py', 'tests/a8_checks.py', 'tests/a8_judge_effect.py',
          'tests/a8_judge_on_a7_run.py', 'tests/a9_logger_restart.py', 'tests/a10_vpe_as_drone.py']
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


def product_list():
    a10 = [l[66:] for l in (SRC / 'executor/PRODUCT_SHA256SUMS.txt').read_text().splitlines()]
    inst = R2I / 'install'
    # Python byte-code caches are not product files: the image ROS tests leave __pycache__ in the r2i install (outside its
    # sums); the A10 list has none (A10 dropped the 17 the r2g install held)
    now = sorted('./' + str(p.relative_to(inst)) for p in inst.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    if sorted(a10) != now:
        sys.exit('STOP: r2i install file list differs from A10: %s' % sorted(set(a10) ^ set(now))[:10])
    return a10


def main():
    a10_list = product_list()                          # before any write
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(SRC / 'SHA256SUMS.txt') != A10_SUMS or sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA:
        sys.exit('STOP: A10 is not the reviewed edition 2')
    subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS.txt'], cwd=SRC, check=True)
    if sha(R2I / 'SHA256SUMS') != R2I_SUMS or sha(R2I / 'MANIFEST_SHA256.txt') != R2I_MANIFEST_SHA:
        sys.exit('STOP: r2i is not the one handed to chat 1')
    for f in ('SHA256SUMS', 'MANIFEST_SHA256.txt'):
        subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2I, check=True)
    if sha(R2I / IMAGE_COPIES['candidate/parameters/vpe_fix.py']) != R2I_VPE or sha(R2I / 'src/bumblebee/examples/drone.py') != DRONE:
        sys.exit('STOP: r2i vpe_fix / drone.py')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins A10: ' + name)
    for c, i in IMAGE_COPIES.items():
        if sha(SRC / c) != sha(R2H / i):
            sys.exit('STOP: A10 candidate copy differs from r2h: ' + c)
        if c != 'candidate/parameters/vpe_fix.py' and sha(R2H / i) != sha(R2I / i):
            sys.exit('STOP: %s differs between r2h and r2i' % i)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A11 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()

    # paths A10 -> A11, r2h -> r2i (named files only)
    for rel in RENAME:
        p = DST / rel
        t = p.read_text()
        n1, n2 = t.count(OLD), t.count(IMG_OLD)
        n3 = t.count('tools/make_a10.py')
        p.write_text(t.replace(OLD, NEW).replace(IMG_OLD, IMG_NEW).replace('tools/make_a10.py', 'tools/make_a11.py'))
        R.append((rel, 'Paths -> A11 (%d), image -> r2i (%d), builder -> make_a11.py (%d).' % (n1, n2, n3)))

    # 1. candidate
    shutil.copy2(R2I / IMAGE_COPIES['candidate/parameters/vpe_fix.py'], DST / 'candidate/parameters/vpe_fix.py')
    R.append(('candidate/parameters/vpe_fix.py', 'A11: copy of the r2i vpe_fix (%s).' % R2I_VPE[:8]))
    edit('candidate/parameters/vpe_profile_optin.py', [
        ("!='%s':  # A10: r2h vpe_fix (c8-r2e-b..A9: r2e = r2g)\n" % R2H_VPE,
         "!='%s':  # A11: r2i vpe_fix (c8-r2e-b..A9: r2e = r2g; A10: r2h)\n" % R2I_VPE, 1, 'A11: the profile opt-in pins the r2i vpe_fix.')])
    edit('executor/vpe_gate_diagnostic_p1.py', [
        ("TARGET_SHA256 = '%s'  # A10: r2h vpe_fix (c8-r2e-b (D2)..A9: r2e = r2g)\n" % R2H_VPE,
         "TARGET_SHA256 = '%s'  # A11: r2i vpe_fix (c8-r2e-b (D2)..A9: r2e = r2g; A10: r2h)\n" % R2I_VPE, 1,
         'A11: the gate diagnostic pins the r2i vpe_fix.')])
    old_helper, new_helper = sha(SRC / 'executor/vpe_gate_diagnostic_p1.py'), sha(DST / 'executor/vpe_gate_diagnostic_p1.py')
    edit('executor/vpe_diagnostic_entry.py', [
        ("hexdigest()=='%s'  # A10: vpe_gate_diagnostic_p1.py with the r2h TARGET_SHA256" % old_helper,
         "hexdigest()=='%s'  # A11: vpe_gate_diagnostic_p1.py with the r2i TARGET_SHA256" % new_helper, 1,
         'A11: entry pins the new diagnostic helper.')])
    mp = DST / 'candidate/manifest.json'
    mt = mp.read_text()
    m = json.loads(mt)
    if dump(m, 1) != mt:
        sys.exit('STOP: manifest format')
    m['scope'] = edit_text(m['scope'], 'candidate/manifest.json:scope', [
        ('combined_c8_r2h (A10, T44 10.11.2026; A9: r2g; A8: r2f; T28: r2e): combined_13 + fixed image r2h (final) parts',
         'combined_c8_r2i (A11, T46 11.11.2026; A10: r2h; A9: r2g; A8: r2f; T28: r2e): combined_13 + fixed image r2i parts', 1, 'Scope text.')])
    for k in IMAGE_COPIES:
        kk = k[len('candidate/'):]
        m['origins'][kk] = edit_text(m['origins'][kk], 'candidate/manifest.json:origins:' + kk,
                                     [(IMG_OLD, IMG_NEW, 1, 'Origin r2h -> r2i.')])
    m['origins']['parameters/vpe_profile_optin.py'] = edit_text(
        m['origins']['parameters/vpe_profile_optin.py'], 'candidate/manifest.json:origins:vpe_profile_optin',
        [('; A10: pinned vpe_fix sha = r2h', '; A11: pinned vpe_fix sha = r2i (A10: r2h)', 1, 'A11 note.')])
    for kk in ('parameters/vpe_fix.py', 'parameters/vpe_profile_optin.py'):
        m['files'][kk] = sha(DST / 'candidate' / kk)
    if {k for k in m['files'] if m['files'][k] != json.loads(mt)['files'][k]} != {'parameters/vpe_fix.py', 'parameters/vpe_profile_optin.py'}:
        sys.exit('STOP: manifest files')
    for k, v in m['files'].items():
        if sha(DST / 'candidate' / k) != v:
            sys.exit('STOP: manifest sha ' + k)
    mp.write_text(dump(m, 1))
    R.append(('candidate/manifest.json:files', 'A11: vpe_fix and vpe_profile_optin shas.'))
    with open(DST / 'candidate/README.md', 'a') as h:
        h.write('A11 (T46, 11.11.2026): image r2i: vpe_fix.py = r2i (%s, vision in AUTO.LAND); the vpe_fix pin of '
                'vpe_profile_optin.py = r2i; the rest as A10 (variant B: no freshness opt-in).\n' % R2I_VPE[:8])
    R.append(('candidate/README.md', 'One line appended.'))

    # 2. executor
    inst = R2I / 'install'
    (DST / 'executor/PRODUCT_SHA256SUMS.txt').write_text(''.join('%s  %s\n' % (sha(inst / n[2:]), n) for n in a10_list))
    R.append(('executor/PRODUCT_SHA256SUMS.txt', 'Regenerated from the r2i install (the same %d paths, same order).' % len(a10_list)))
    psha, old_psha = sha(DST / 'executor/PRODUCT_SHA256SUMS.txt'), sha(SRC / 'executor/PRODUCT_SHA256SUMS.txt')
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # A10: this copy (A9 + image final r2h, ../DIFF_a10.md)' % NEW,
         'OWN=/work/%s/executor  # A11: this copy (A10 + image r2i, ../DIFF_a11.md)' % NEW, 1, 'Own folder.'),
        ('(c8 A10: fixed image r2h, /work/%s/install, MANIFEST_SHA256.txt %s)' % (IMG_NEW, R2H_MANIFEST_SHA[:8]),
         '(c8 A11: fixed image r2i, /work/%s/install, MANIFEST_SHA256.txt %s)' % (IMG_NEW, R2I_MANIFEST_SHA[:8]), 1, 'Comment.'),
        ('echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % old_psha, 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % psha, 1,
         'A11: product sums of the r2i install.'),
        ('# c8: product parameter (A10: r2h), pinned above', '# c8: product parameter (A11: r2i), pinned above', 1, 'Comment.'),
        ('# c8: product src is a parameter; the sha is r2h drone.py (A10).',
         '# c8: product src is a parameter; the sha is r2i drone.py (A11; the r2h bytes).', 1, 'Comment.'),
    ])
    edit('executor/sitl_setup.py', [('# c8-r2e-b (D3); A10: r2h (same bytes)', '# c8-r2e-b (D3); A11: r2i (same bytes)', 1,
                                     'A11: profile path r2i (byte-identical file).')])

    # 3. launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v37-c8-r2h-a10 (A10, T44 10.11.2026: runner = %s/executor, image final r2h, airframe 4070; A9 v36,' % NEW,
         'launcher v38-c8-r2i-a11 (A11, T46 11.11.2026: runner = %s/executor, image r2i, airframe 4070; A10 v37, A9 v36,' % NEW,
         1, 'Header.'),
        ('v37-c8-r2h-a10', 'v38-c8-r2i-a11', 3, 'Version strings (first line, refusal, banner).'),
        ('RUNNER=$WORK/%s/executor/run.sh   # A10: the only runner of this launcher' % NEW,
         'RUNNER=$WORK/%s/executor/run.sh   # A11: the only runner of this launcher' % NEW, 1, 'Runner.'),
        ('SDLOG_MODE 1, image r2h, T22', 'SDLOG_MODE 1, image r2i, T22', 1, 'Comment.'),
        ("    runner = '%s/executor/run.sh'  # A10: the fixed runner" % NEW, "    runner = '%s/executor/run.sh'  # A11: the fixed runner" % NEW,
         1, 'Pins runner.'),
    ])

    # 4. tests
    edit('tests/test_c8_b2.sh', [
        ('$D/pins/frozen_inputs_c8_r2h_a10_01.json', '$D/pins/' + PINS_NAME, 2, 'Tests use pins A11.'),
        ("diagnostic.TARGET_SHA256 == '%s'" % R2H_VPE, "diagnostic.TARGET_SHA256 == '%s'" % R2I_VPE, 1, 'd2: r2i vpe_fix.'),
        ('# 6. D2: VPE composition with the r2h vpe_fix', '# 6. D2: VPE composition with the r2i vpe_fix', 1, 'd2 comment.'),
        ('/work/c8_judge_r2g_a9_20261110/pins/frozen_inputs_c8_r2g_a9_01.json', '/work/%s/pins/frozen_inputs_c8_r2h_a10_01.json' % OLD, 1,
         'Control: the A10 pins are refused by the A11 launcher.'),
        ('# A10: the A9 -> A10 difference is exactly the image final r2h (judge, expectations, run_sim unchanged)\n'
         't a10_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a10_checks.py\n',
         '# A11: the A10 -> A11 difference is exactly the image r2i (judge, expectations, run_sim unchanged)\n'
         't a11_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a11_checks.py\n', 1, 'a10_checks -> a11_checks.'),
    ])
    edit('tests/a8_checks.py', [
        ("    assert h(D / 'candidate' / c) == h(R2F / i), c   # A10: image copies = r2h bytes\n",
         "    assert h(D / 'candidate' / c) == h(R2F / i), c   # A10/A11: image copies = image bytes (A11: r2i)\n", 1, 'Comment.'),
        (".replace('  # A10: r2h vpe_fix (c8-r2e-b..A9: r2e = r2g)', '  # c8-r2e-b: r2e vpe_fix')   # A10\n",
         ".replace('  # A10: r2h vpe_fix (c8-r2e-b..A9: r2e = r2g)', '  # c8-r2e-b: r2e vpe_fix') \\\n"
         "    .replace('%s', 'V').replace('  # A11: r2i vpe_fix (c8-r2e-b..A9: r2e = r2g; A10: r2h)', '  # c8-r2e-b: r2e vpe_fix')   # A10, A11\n" % R2I_VPE,
         1, 'A11: vpe_profile_optin pins the r2i sha.'),
        ("    '%s'   # A10: final r2h" % R2H_MANIFEST_SHA, "    '%s'   # A11: r2i" % R2I_MANIFEST_SHA, 1, 'A11: the r2i MANIFEST.'),
        ("pins = J(D / 'pins/frozen_inputs_c8_r2h_a10_01.json')", "pins = J(D / 'pins/%s')" % PINS_NAME, 1, 'Pins A11.'),
        ("assert acc == [[h(D / 'pins/frozen_inputs_c8_r2h_a10_01.json'), str(D / 'pins/frozen_inputs_c8_r2h_a10_01.json')]], acc",
         "assert acc == [[h(D / 'pins/%s'), str(D / 'pins/%s')]], acc" % (PINS_NAME, PINS_NAME), 1, 'Accepted pins A11.'),
    ])
    for f in ('a11_checks.py',):
        shutil.copy2(Path(__file__).with_name(f), DST / 'tests' / f)
        R.append(('tests/' + f, 'New test (A11).'))

    # 5. pins A11
    new = json.loads(json.dumps(old_pins))
    changed = set()
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1).replace(IMG_OLD + '/', IMG_NEW + '/', 1)
            h2 = DRONE if nn == '@run/drone.py' else sha(WORK / nn)
            if h2 != h:
                changed.add(nn)
            g[nn] = h2
        new[group] = g
    for k, v in old_pins['run_files'].items():
        p = DST / 'executor' / k if (DST / 'executor' / k).exists() else R2I / 'src/bumblebee/examples' / k
        new['run_files'][k] = sha(p)
        if new['run_files'][k] != v:
            changed.add('run_files:' + k)
    allowed = {NEW + '/executor/run.sh', NEW + '/executor/sitl_setup.py', NEW + '/executor/PRODUCT_SHA256SUMS.txt',
               NEW + '/executor/vision_c8.launch.py', NEW + '/executor/vpe_gate_diagnostic_p1.py', NEW + '/executor/vpe_diagnostic_entry.py',
               NEW + '/candidate/parameters/vpe_fix.py', NEW + '/candidate/parameters/vpe_profile_optin.py',
               IMG_NEW + '/src/bumblebee/src/python/vpe_fix.py', IMG_NEW + '/src/bumblebee/src/cpp/simple_offboard.cpp',
               IMG_NEW + '/install/bumblebee/lib/bumblebee/simple_offboard', IMG_NEW + '/MANIFEST_SHA256.txt', IMG_NEW + '/image_manifest_r2.tsv',
               'run_files:run.sh', 'run_files:sitl_setup.py', 'run_files:vision_c8.launch.py',
               'run_files:vpe_gate_diagnostic_p1.py', 'run_files:vpe_diagnostic_entry.py'}
    if not changed <= allowed:
        sys.exit('STOP: unexpected changes: %s' % sorted(changed - allowed))
    R.append(('pins/' + PINS_NAME, 'Changed entries: %s' % sorted(changed)))
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    new['combined_manifest_sha256'] = sha(DST / 'candidate/manifest.json')
    new['combined_files'] = json.loads((DST / 'candidate/manifest.json').read_text())['files']
    new['sdk_drone_py'].update(source=str(R2I / 'src/bumblebee/examples/drone.py'), sha256=DRONE,
                               product_tag='fixed image r2i (MANIFEST_SHA256.txt %s)' % R2I_MANIFEST_SHA[:8], by=NEW + '/tools/make_a11.py')
    new['c8_target'].update(product_install=str(R2I / 'install'), product_src=str(R2I / 'src/bumblebee'),
                            combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4070',
                            a11='image r2i byte for byte (vpe_fix vision in AUTO.LAND, simple_offboard S9 link silence, '
                                'flight_marker 0.9 m) (T46)')
    P = DST / 'pins' / PINS_NAME
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v38-c8-r2i-a11 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# %s = pins A10 (9ec805e7) renamed + image r2i (tools/make_a11.py)\n'
                '%s  %s\n' % (NEW, PINS_NAME, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a11.py')

    # 6. DIFF_a11.md against A10
    out = ['# DIFF A10 -> A11 (generated by tools/make_a11.py)\n']
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
    with open(DST / 'DIFF_a11.md', 'x') as h:
        h.write(''.join(out))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge_same': sha(DST / 'verify_flight_c8.py') == JUDGE_SHA,
                      'manifest': new['combined_manifest_sha256'], 'product_sums': psha, 'changed': sorted(changed), 'edits': len(R)}))


if __name__ == '__main__':
    main()
