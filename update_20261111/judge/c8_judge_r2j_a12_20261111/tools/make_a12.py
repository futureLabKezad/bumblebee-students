#!/usr/bin/env python3
"""make_a12.py - T53 of chat 1 (11.11.2026): C8 package revision A12 = A11 (/work/c8_judge_r2i_a11_20261111, SHA256SUMS.txt
30a5b675, pins f6de13cf; review: accepted with notes) with the image r2j (/work/fixed_image_r2j_20261111) instead of r2i.
r2j = r2i + the camera translations of the 20EC reference (ЭТАЛОН_РАЗМЕРОВ_20EC.md); vpe_fix, flight_profile.py,
aruco_detect.py, drone.py: r2i's bytes, so the candidate files and the vpe_fix pins do not change.
What changes:
 - run.sh: product sums of the r2j install (launch files, rebuilt binaries); sitl_setup PROFILE_SOURCE path; own paths;
   launcher v39; pins A12; tests (paths; a11_checks.py -> a12_checks.py);
 - executor/vision_c8.launch.py: the runner publishes its OWN down-camera TF (it does not use the image launch): its
   translation (0.05, 0, -0.07) -> (0.081, 0, -0.034) per the reference, the angles unchanged, so the C8 runs use the same
   camera geometry as r2j and as the Simulator's model (T52). tests/a7_vision_launch.py allows exactly that one line.
Judge (1ab83ca4), legacy copy, expectations, airframe 4070 v2, run_sim.snapshot.sh, the S scenarios, variant B: as A11.
Usage: python3 -I make_a12.py   (refuses to overwrite)
"""
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# UNCHANGED from A11 / A10 / A9 (the A8 tests read the values from this builder; a12_checks compares)
EXPECT_4070 = {
    'BAT1_SOURCE': (0, 6),   # approved drone set, owner 09.11 «да» (4061: 1)
    'SDLOG_MODE': (1, 6),    # log from boot, owner 10.11 «В» (new name)
    'EKF2_OF_QMIN': (50, 6), # A9: flow quality minimum, owner 10.11 (T33, smooth landing; 20EC: 1) (new name)
}

WORK = Path('/work')
SRC = WORK / 'c8_judge_r2i_a11_20261111'
DST = WORK / 'c8_judge_r2j_a12_20261111'
OLD, NEW = 'c8_judge_r2i_a11_20261111', 'c8_judge_r2j_a12_20261111'
IMG_OLD, IMG_NEW = 'fixed_image_r2i_20261111', 'fixed_image_r2j_20261111'
R2I, R2J = WORK / IMG_OLD, WORK / IMG_NEW
A11_SUMS = '30a5b67516febbb3b13d28fae65d0fa88c77419611d508704cf14d2f41585a3f'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2i_a11_01.json'
PINS_SRC_SHA = 'f6de13cfc365b6815041bf38e9176f771ac3f8d28e9c5bdfeddfdb970e2badeb'
PINS_NAME = 'frozen_inputs_c8_r2j_a12_01.json'
JUDGE_SHA = '1ab83ca41f435250d523cb6697f6cda0331f8e2db6d6a9fd6051c9495924c27d'
R2J_SUMS = '14fbcf74d847605c927181245f23e5c598c551a24249991070770ea49bf26094'
R2J_MANIFEST_SHA = 'b0899329ed73769a4a9afa4842c448b14e0f00c05d0d0a11dd6523c258563ee4'
R2I_MANIFEST_SHA = '855f9f93e2166d8cde1156f6f010728210919882337e30fade4d7ba63f58412b'
DRONE = 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c'
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
TF_OLD = "            '--x', '0.05', '--y', '0', '--z', '-0.07', '--yaw', '-1.5707963',\n"
TF_NEW = ("            '--x', '0.081', '--y', '0', '--z', '-0.034', '--yaw', '-1.5707963',   "
          "# A12 (T53): translation per ЭТАЛОН_РАЗМЕРОВ_20EC (= r2j launch)\n")
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
    a11 = [l[66:] for l in (SRC / 'executor/PRODUCT_SHA256SUMS.txt').read_text().splitlines()]
    inst = R2J / 'install'
    now = sorted('./' + str(p.relative_to(inst)) for p in inst.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    if sorted(a11) != now:
        sys.exit('STOP: r2j install file list differs from A11: %s' % sorted(set(a11) ^ set(now))[:10])
    return a11


def main():
    a11_list = product_list()
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(SRC / 'SHA256SUMS.txt') != A11_SUMS or sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA:
        sys.exit('STOP: A11 is not the reviewed one')
    subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS.txt'], cwd=SRC, check=True)
    if sha(R2J / 'SHA256SUMS') != R2J_SUMS or sha(R2J / 'MANIFEST_SHA256.txt') != R2J_MANIFEST_SHA:
        sys.exit('STOP: r2j sums')
    for f in ('SHA256SUMS', 'MANIFEST_SHA256.txt'):
        subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=R2J, check=True)
    for c, i in IMAGE_COPIES.items():
        if sha(SRC / c) != sha(R2J / i) or sha(R2I / i) != sha(R2J / i):
            sys.exit('STOP: candidate copy differs from r2j: ' + c)
    if sha(R2J / 'src/bumblebee/examples/drone.py') != DRONE:
        sys.exit('STOP: drone.py')
    old_pins = json.loads(PINS_SRC.read_text())
    for group in ('repo_files', 'ledger_files'):
        for name, h in old_pins[group].items():
            if not name.startswith('@run/') and sha(WORK / name) != h:
                sys.exit('STOP: source file changed since pins A11: ' + name)
    if (SRC / 'executor/vision_c8.launch.py').read_text().count(TF_OLD) != 1:
        sys.exit('STOP: vision_c8 TF anchor')
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A12 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()
    for rel in RENAME:
        p = DST / rel
        t = p.read_text()
        n1, n2, n3 = t.count(OLD), t.count(IMG_OLD), t.count('tools/make_a11.py')
        p.write_text(t.replace(OLD, NEW).replace(IMG_OLD, IMG_NEW).replace('tools/make_a11.py', 'tools/make_a12.py'))
        R.append((rel, 'Paths -> A12 (%d), image -> r2j (%d), builder -> make_a12.py (%d).' % (n1, n2, n3)))

    # candidate: the same files; texts only
    mp = DST / 'candidate/manifest.json'
    mt = mp.read_text()
    m = json.loads(mt)
    if dump(m, 1) != mt:
        sys.exit('STOP: manifest format')
    m['scope'] = edit_text(m['scope'], 'candidate/manifest.json:scope', [
        ('combined_c8_r2i (A11, T46 11.11.2026; A10: r2h;', 'combined_c8_r2j (A12, T53 11.11.2026; A11: r2i; A10: r2h;', 1, 'Scope.'),
        ('fixed image r2i parts', 'fixed image r2j parts', 1, 'Scope.')])
    for k in IMAGE_COPIES:
        kk = k[len('candidate/'):]
        m['origins'][kk] = edit_text(m['origins'][kk], 'candidate/manifest.json:origins:' + kk,
                                     [(IMG_OLD, IMG_NEW, 1, 'Origin r2i -> r2j (same bytes).')])
    if m['files'] != json.loads(mt)['files']:
        sys.exit('STOP: manifest files must not change')
    mp.write_text(dump(m, 1))
    with open(DST / 'candidate/README.md', 'a') as h:
        h.write('A12 (T53, 11.11.2026): image r2j (camera translations of the 20EC reference); the candidate files are the '
                'r2i bytes; the rest as A11.\n')
    R.append(('candidate/README.md', 'One line appended.'))

    # executor
    inst = R2J / 'install'
    (DST / 'executor/PRODUCT_SHA256SUMS.txt').write_text(''.join('%s  %s\n' % (sha(inst / n[2:]), n) for n in a11_list))
    R.append(('executor/PRODUCT_SHA256SUMS.txt', 'Regenerated from the r2j install (the same %d paths, same order).' % len(a11_list)))
    psha, old_psha = sha(DST / 'executor/PRODUCT_SHA256SUMS.txt'), sha(SRC / 'executor/PRODUCT_SHA256SUMS.txt')
    edit('executor/run.sh', [
        ('OWN=/work/%s/executor  # A11: this copy (A10 + image r2i, ../DIFF_a11.md)' % NEW,
         'OWN=/work/%s/executor  # A12: this copy (A11 + image r2j + camera TF of the reference, ../DIFF_a12.md)' % NEW, 1, 'Own folder.'),
        ('(c8 A11: fixed image r2i, /work/%s/install, MANIFEST_SHA256.txt %s)' % (IMG_NEW, R2I_MANIFEST_SHA[:8]),
         '(c8 A12: fixed image r2j, /work/%s/install, MANIFEST_SHA256.txt %s)' % (IMG_NEW, R2J_MANIFEST_SHA[:8]), 1, 'Comment.'),
        ('echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % old_psha, 'echo "%s  $OWN/PRODUCT_SHA256SUMS.txt"' % psha, 1,
         'A12: product sums of the r2j install.'),
        ('# c8: product parameter (A11: r2i), pinned above', '# c8: product parameter (A12: r2j), pinned above', 1, 'Comment.'),
        ('# c8: product src is a parameter; the sha is r2i drone.py (A11; the r2h bytes).',
         '# c8: product src is a parameter; the sha is r2j drone.py (A12; the r2h bytes).', 1, 'Comment.'),
    ])
    edit('executor/sitl_setup.py', [('# c8-r2e-b (D3); A11: r2i (same bytes)', '# c8-r2e-b (D3); A12: r2j (same bytes)', 1, 'Comment.')])
    edit('executor/vision_c8.launch.py', [(TF_OLD, TF_NEW, 1, 'A12 (T53): down-camera TF translation per the 20EC reference.')])

    # launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v38-c8-r2i-a11 (A11, T46 11.11.2026: runner = %s/executor, image r2i, airframe 4070; A10 v37,' % NEW,
         'launcher v39-c8-r2j-a12 (A12, T53 11.11.2026: runner = %s/executor, image r2j, airframe 4070; A11 v38, A10 v37,' % NEW,
         1, 'Header.'),
        ('v38-c8-r2i-a11', 'v39-c8-r2j-a12', 3, 'Version strings.'),
        ('RUNNER=$WORK/%s/executor/run.sh   # A11: the only runner of this launcher' % NEW,
         'RUNNER=$WORK/%s/executor/run.sh   # A12: the only runner of this launcher' % NEW, 1, 'Runner.'),
        ('SDLOG_MODE 1, image r2i, T22', 'SDLOG_MODE 1, image r2j, T22', 1, 'Comment.'),
        ("    runner = '%s/executor/run.sh'  # A11: the fixed runner" % NEW, "    runner = '%s/executor/run.sh'  # A12: the fixed runner" % NEW,
         1, 'Pins runner.'),
    ])

    # tests
    edit('tests/test_c8_b2.sh', [
        ('$D/pins/frozen_inputs_c8_r2i_a11_01.json', '$D/pins/' + PINS_NAME, 2, 'Tests use pins A12.'),
        ('# 6. D2: VPE composition with the r2i vpe_fix', '# 6. D2: VPE composition with the r2j (= r2i) vpe_fix', 1, 'd2 comment.'),
        ('/work/c8_judge_r2h_a10_20261110/pins/frozen_inputs_c8_r2h_a10_01.json', '/work/%s/pins/frozen_inputs_c8_r2i_a11_01.json' % OLD, 1,
         'Control: the A11 pins are refused by the A12 launcher.'),
        ('# A11: the A10 -> A11 difference is exactly the image r2i (judge, expectations, run_sim unchanged)\n'
         't a11_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a11_checks.py\n',
         '# A12: the A11 -> A12 difference is exactly the image r2j + the reference camera TF of the runner\n'
         't a12_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a12_checks.py\n', 1, 'a11_checks -> a12_checks.'),
    ])
    edit('tests/a8_checks.py', [
        ("    '%s'   # A11: r2i" % R2I_MANIFEST_SHA, "    '%s'   # A12: r2j" % R2J_MANIFEST_SHA, 1, 'A12: the r2j MANIFEST.'),
        ("pins = J(D / 'pins/frozen_inputs_c8_r2i_a11_01.json')", "pins = J(D / 'pins/%s')" % PINS_NAME, 1, 'Pins A12.'),
        ("assert acc == [[h(D / 'pins/frozen_inputs_c8_r2i_a11_01.json'), str(D / 'pins/frozen_inputs_c8_r2i_a11_01.json')]], acc",
         "assert acc == [[h(D / 'pins/%s'), str(D / 'pins/%s')]], acc" % (PINS_NAME, PINS_NAME), 1, 'Accepted pins A12.'),
    ])
    edit('tests/a7_vision_launch.py', [
        ("                   \"-        raise RuntimeError('Separate integration candidate required')\"], removed\n",
         "                   \"-        raise RuntimeError('Separate integration candidate required')\",\n"
         "                   %r], removed   # A12: the camera TF line\n" % ('-' + TF_OLD.rstrip('\n')), 1, 'A12: the TF line removed.'),
        ("assert len(added) == 7, added\n", "assert len(added) == 8, added   # A12: + the camera TF line\n", 1, 'A12: 8 added lines.'),
        ("                     \"+        raise RuntimeError('C8 package candidate required')\"], added[5:]\n",
         "                     \"+        raise RuntimeError('C8 package candidate required')\",\n"
         "                     %r], added[5:]   # A12\n" % ('+' + TF_NEW.rstrip('\n')), 1, 'A12: the TF line added.'),
    ])
    shutil.copy2(Path(__file__).with_name('a12_checks.py'), DST / 'tests/a12_checks.py')
    R.append(('tests/a12_checks.py', 'New test (A12).'))

    # pins A12
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
        p = DST / 'executor' / k if (DST / 'executor' / k).exists() else R2J / 'src/bumblebee/examples' / k
        new['run_files'][k] = sha(p)
        if new['run_files'][k] != v:
            changed.add('run_files:' + k)
    allowed = {NEW + '/executor/run.sh', NEW + '/executor/sitl_setup.py', NEW + '/executor/PRODUCT_SHA256SUMS.txt',
               NEW + '/executor/vision_c8.launch.py', IMG_NEW + '/install/bumblebee/lib/bumblebee/simple_offboard',
               IMG_NEW + '/MANIFEST_SHA256.txt', IMG_NEW + '/image_manifest_r2.tsv',
               'run_files:run.sh', 'run_files:sitl_setup.py', 'run_files:vision_c8.launch.py'}
    if not changed <= allowed:
        sys.exit('STOP: unexpected changes: %s' % sorted(changed - allowed))
    R.append(('pins/' + PINS_NAME, 'Changed entries: %s' % sorted(changed)))
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    new['combined_manifest_sha256'] = sha(DST / 'candidate/manifest.json')
    new['combined_files'] = json.loads((DST / 'candidate/manifest.json').read_text())['files']
    new['sdk_drone_py'].update(source=str(R2J / 'src/bumblebee/examples/drone.py'), sha256=DRONE,
                               product_tag='fixed image r2j (MANIFEST_SHA256.txt %s)' % R2J_MANIFEST_SHA[:8], by=NEW + '/tools/make_a12.py')
    new['c8_target'].update(product_install=str(R2J / 'install'), product_src=str(R2J / 'src/bumblebee'),
                            combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4070',
                            a12='image r2j (camera translations of the 20EC reference) + the runner camera TF (T53)')
    P = DST / 'pins' / PINS_NAME
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v39-c8-r2j-a12 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# %s = pins A11 (f6de13cf) renamed + image r2j + runner camera TF (tools/make_a12.py)\n'
                '%s  %s\n' % (NEW, PINS_NAME, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a12.py')
    out = ['# DIFF A11 -> A12 (generated by tools/make_a12.py)\n']
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
    with open(DST / 'DIFF_a12.md', 'x') as h:
        h.write(''.join(out))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge_same': sha(DST / 'verify_flight_c8.py') == JUDGE_SHA,
                      'manifest': new['combined_manifest_sha256'], 'product_sums': psha, 'changed': sorted(changed), 'edits': len(R)}))


if __name__ == '__main__':
    main()
