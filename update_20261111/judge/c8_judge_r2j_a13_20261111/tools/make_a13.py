#!/usr/bin/env python3
"""make_a13.py - T55 of chat 1 (11.11.2026): C8 package revision A13 = A12 (/work/c8_judge_r2j_a12_20261111, SHA256SUMS.txt
cb2f46e2, pins 697408e7; review: MUST-FIX = A12 pins the old model_v1 / airframe 4070 while its camera TF follows the
reference) + the Simulator's T52 model and set:
  model  /work/t52_model_ref_20261111/models/model_v2/bumblebee (model.sdf 1618e853; meshes and model.config = model_v1 bytes)
  set    airframe 4074_gz_bumblebee_t52_ref_dims (61237522) = 4070 v2 (0224deec, still pinned) + the 10 sensor positions
What changes, and only this (the judge logic, the S tests and the criteria do not):
 - verify_flight_c8.py: a new identity row c8_4074 (autostart 4074, the same 18 names, the same expect/*_4070.json: no
   EKF2_*_POS / EKF2_MIN_RNG name is judged, sitl_setup never writes them); c8_4070 and the others unchanged;
 - candidate/parameters/vpe_profile_optin.py: the SITL airframe check 4070 -> 4074 (it refuses any other airframe);
 - launcher v40: defaults C8_AIRFRAME 4074, C8_MODEL model_v2; pins A13: + the 4074 airframe, model_v1 -> model_v2 keys,
   c8_target airframe / chain / model / judge identity; tests follow; a12_checks.py -> a13_checks.py.
The image stays r2j. sim_only_4074.json (the C2 list of the Simulator) is not read by the judge or the runner: not pinned.
Usage: python3 -I make_a13.py   (refuses to overwrite)
"""
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

# UNCHANGED from A12 .. A9 (the A8 tests read the values from this builder)
EXPECT_4070 = {
    'BAT1_SOURCE': (0, 6),   # approved drone set, owner 09.11 «да» (4061: 1)
    'SDLOG_MODE': (1, 6),    # log from boot, owner 10.11 «В» (new name)
    'EKF2_OF_QMIN': (50, 6), # A9: flow quality minimum, owner 10.11 (T33, smooth landing; 20EC: 1) (new name)
}

WORK = Path('/work')
SRC = WORK / 'c8_judge_r2j_a12_20261111'
DST = WORK / 'c8_judge_r2j_a13_20261111'
OLD, NEW = 'c8_judge_r2j_a12_20261111', 'c8_judge_r2j_a13_20261111'
A12_SUMS = 'cb2f46e24d51b8019669b8dc774c3efb6dcc26c1fa41606487e455a7785411a6'
PINS_SRC = SRC / 'pins/frozen_inputs_c8_r2j_a12_01.json'
PINS_SRC_SHA = '697408e77fe390decf45a404b9d1d218ee61ea41d18cb258df217ae3b8724708'
PINS_NAME = 'frozen_inputs_c8_r2j_a13_01.json'
JUDGE_SHA = '1ab83ca41f435250d523cb6697f6cda0331f8e2db6d6a9fd6051c9495924c27d'
AFDIR = 'goal_step5b_20261109/px4_etc/init.d-posix/airframes/'
AF4074, AF4074_SHA = AFDIR + '4074_gz_bumblebee_t52_ref_dims', '6123752230c2226602e3c0276cb33e7e329af7b18a40e5756f708b5f16ba4920'
AF4070, AF4070_SHA = AFDIR + '4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50', '0224deec06a3a4fee076b2bc24d8cd1cd1650f3d270da057f94afa057698339e'
M1, M2 = 'goal_t22_flow_20261109/model_v1/bumblebee/', 't52_model_ref_20261111/models/model_v2/bumblebee/'
M2_SDF_SHA = '1618e85388ead0e0fc89102e51ea34dc3ee98e4917d9ee2a65e276bba77ac4bc'
COPY = ['verify_flight_c8.py', 'legacy', 'expect', 'candidate', 'executor', 'launcher/host_run_wsl_c8_r2e_b.sh',
        'launcher/clock_watch.py', 'launcher/viewer_wslg.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py',
        'tests/ledger_check.py', 'tests/a6_apply_order.py', 'tests/a7_vision_launch.py', 'tests/a8_checks.py',
        'tests/a8_judge_effect.py', 'tests/a8_judge_on_a7_run.py', 'tests/a9_logger_restart.py', 'tests/a10_vpe_as_drone.py']
RENAME = ['executor/run.sh', 'executor/vision_c8.launch.py', 'executor/tests/test_entry_order.py',
          'launcher/host_run_wsl_c8_r2e_b.sh', 'tests/test_c8_b2.sh', 'tests/d1_check.py', 'tests/ledger_check.py',
          'tests/a6_apply_order.py', 'tests/a7_vision_launch.py', 'tests/a8_checks.py', 'tests/a8_judge_effect.py',
          'tests/a8_judge_on_a7_run.py', 'tests/a9_logger_restart.py', 'tests/a10_vpe_as_drone.py']
JUDGE_COMMENT = ("#  c8_4074:   A13 (T55, 11.11.2026): airframe 4074 of the Simulator (T52) = 4070 v2 + the 10 sensor positions of the\n"
                 "#             20EC reference; the same 18 names and the same expect/*_4070.json (no EKF2_*_POS / MIN_RNG is judged).\n")
JUDGE_ROW = ("    'c8_4074': dict(autostart=4074, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={\n"
             "        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '9e471a6e3fcad40958fab2eaa040713479759ef815581ebeb9761590634900d1'),\n"
             "        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),\n")
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
    if sha(SRC / 'SHA256SUMS.txt') != A12_SUMS or sha(PINS_SRC) != PINS_SRC_SHA or sha(SRC / 'verify_flight_c8.py') != JUDGE_SHA:
        sys.exit('STOP: A12 is not the reviewed one')
    subprocess.run(['sha256sum', '-c', '--quiet', 'SHA256SUMS.txt'], cwd=SRC, check=True)
    if sha(WORK / AF4074) != AF4074_SHA or sha(WORK / AF4070) != AF4070_SHA or sha(WORK / M2 / 'model.sdf') != M2_SDF_SHA:
        sys.exit('STOP: T52 files are not the ones chat 1 checked')
    if '. ${R}etc/init.d-posix/airframes/' + Path(AF4070).name not in (WORK / AF4074).read_text().splitlines():
        sys.exit('STOP: 4074 does not source 4070 v2')
    old_pins = json.loads(PINS_SRC.read_text())
    m1 = sorted(k for k in old_pins['repo_files'] if k.startswith(M1))
    if sorted(k[len(M1):] for k in m1) != sorted(str(p.relative_to(WORK / M2)) for p in (WORK / M2).rglob('*') if p.is_file()):
        sys.exit('STOP: model_v2 file list differs from the pinned model_v1 list')
    for k in m1:
        if k != M1 + 'model.sdf' and sha(WORK / k) != sha(WORK / M2 / k[len(M1):]):
            sys.exit('STOP: model_v2 %s differs from model_v1' % k)
    DST.mkdir()
    for c in COPY:
        s, d = SRC / c, DST / c
        d.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if s.is_dir() else shutil.copy2)(s, d)
    (DST / 'reviews').mkdir()
    (DST / 'reviews/OVERWRITE_GUARD.json').write_text('{"note": "A13 test: the judge must refuse to overwrite this file"}\n')
    (DST / 'pins').mkdir()
    for rel in RENAME:
        p = DST / rel
        t = p.read_text()
        n1, n3 = t.count(OLD), t.count('tools/make_a12.py')
        p.write_text(t.replace(OLD, NEW).replace('tools/make_a12.py', 'tools/make_a13.py'))
        R.append((rel, 'Paths -> A13 (%d), builder -> make_a13.py (%d).' % (n1, n3)))

    # judge: one identity row (data), c8_4074
    edit('verify_flight_c8.py', [
        ("#             the same 18 names; expect/*_4070.json = the 4061 files + those 2 values (tools/make_a8.py EXPECT_4070).\n",
         "#             the same 18 names; expect/*_4070.json = the 4061 files + those 2 values (tools/make_a8.py EXPECT_4070).\n"
         + JUDGE_COMMENT, 1, 'A13: identity comment.'),
        ("        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),\n}\n",
         "        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),\n"
         + JUDGE_ROW + "}\n", 1, 'A13: identity c8_4074.')])
    # candidate: the opt-in airframe check
    edit('candidate/parameters/vpe_profile_optin.py', [
        ("    if audit.get('sitl_autostart')!=4070 or audit.get('sitl_autostart_source')!='rc_ready.json:sys_autostart':  # A8: airframe 4070\n"
         "        raise RuntimeError('SITL airframe is not 4070')\n",
         "    if audit.get('sitl_autostart')!=4074 or audit.get('sitl_autostart_source')!='rc_ready.json:sys_autostart':  # A8: airframe 4070; A13: 4074\n"
         "        raise RuntimeError('SITL airframe is not 4074')\n", 1, 'A13: the opt-in accepts only airframe 4074.')])
    mp = DST / 'candidate/manifest.json'
    mt = mp.read_text()
    m = json.loads(mt)
    m['scope'] = edit_text(m['scope'], 'candidate/manifest.json:scope', [
        ('combined_c8_r2j (A12, T53 11.11.2026;', 'combined_c8_r2j (A13, T55 11.11.2026; A12: airframe 4070;', 1, 'Scope.'),
        ('for C8 on airframe 4070.', 'for C8 on airframe 4074.', 1, 'Scope.')])
    m['origins']['parameters/vpe_profile_optin.py'] += '; A13: SITL airframe check 4074'
    m['files']['parameters/vpe_profile_optin.py'] = sha(DST / 'candidate/parameters/vpe_profile_optin.py')
    if {k for k in m['files'] if m['files'][k] != json.loads(mt)['files'][k]} != {'parameters/vpe_profile_optin.py'}:
        sys.exit('STOP: manifest files')
    mp.write_text(dump(m, 1))
    R.append(('candidate/manifest.json', 'A13: vpe_profile_optin sha and texts.'))
    with open(DST / 'candidate/README.md', 'a') as h:
        h.write('A13 (T55, 11.11.2026): airframe 4074 (T52): vpe_profile_optin.py accepts only SITL airframe 4074; the rest as A12.\n')
    # executor: comment only
    edit('executor/run.sh', [('OWN=/work/%s/executor  # A12: this copy (A11 + image r2j + camera TF of the reference, ../DIFF_a12.md)' % NEW,
                              'OWN=/work/%s/executor  # A13: this copy (A12 + airframe 4074 and model_v2 of T52 in the pins, ../DIFF_a13.md)' % NEW,
                              1, 'Own folder.')])
    # launcher
    edit('launcher/host_run_wsl_c8_r2e_b.sh', [
        ('launcher v39-c8-r2j-a12 (A12, T53 11.11.2026: runner = %s/executor, image r2j, airframe 4070; A11 v38,' % NEW,
         'launcher v40-c8-r2j-a13 (A13, T55 11.11.2026: runner = %s/executor, image r2j, airframe 4074, model_v2; A12 v39, A11 v38,' % NEW,
         1, 'Header.'),
        ('v39-c8-r2j-a12', 'v40-c8-r2j-a13', 3, 'Version strings.'),
        ('# A12: the only runner of this launcher', '# A13: the only runner of this launcher', 1, 'Runner.'),
        ("  # A12: the fixed runner", "  # A13: the fixed runner", 1, 'Pins runner.'),
        ('# ---- c8: target set (defaults = C8 set A8 of 10.11: airframe 4070 = 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1, image r2j, T22 model_v1 + plugin_v1, MAVROS bp02)',
         '# ---- c8: target set (defaults = C8 set A13 of 11.11: airframe 4074 = 4070 v2 + the 10 sensor positions of the reference (T52), image r2j, T52 model_v2 + T22 plugin_v1, MAVROS bp02)',
         1, 'Comment.'),
        ('C8_AIRFRAME=${C8_AIRFRAME:-4070};', 'C8_AIRFRAME=${C8_AIRFRAME:-4074};', 1, 'A13: default airframe 4074.'),
        ('C8_MODEL=${C8_MODEL:-/work/goal_t22_flow_20261109/model_v1/bumblebee};', 'C8_MODEL=${C8_MODEL:-/work/t52_model_ref_20261111/models/model_v2/bumblebee};',
         1, 'A13: default model_v2.'),
    ])
    # tests
    edit('tests/test_c8_b2.sh', [
        ('$D/pins/frozen_inputs_c8_r2j_a12_01.json', '$D/pins/' + PINS_NAME, 2, 'Tests use pins A13.'),
        ('env C8_AF_FILE=/work/%s \\\n  C8_MODEL_SDF=/work/%smodel.sdf \\\n' % (AF4070, M1),
         'env C8_AF_FILE=/work/%s \\\n  C8_MODEL_SDF=/work/%smodel.sdf \\\n' % (AF4074, M2), 1, 'Launcher pre-check: airframe 4074, model_v2.'),
        ("grep -qx 'SITL airframe is not 4070'", "grep -qx 'SITL airframe is not 4074'", 3, 'd7: refusal text 4074.'),
        ("t d7_optin_4070_reaches_route_check bash -c \"python3 -B -I $O/optin_case.py '{\\\"sitl_autostart\\\":4070,",
         "t d7_optin_refuses_4070 bash -c \"python3 -B -I $O/optin_case.py '{\\\"sitl_autostart\\\":4070,\\\"sitl_autostart_source\\\":\\\"rc_ready.json:sys_autostart\\\"}' $O | grep -qx 'SITL airframe is not 4074'\"\n"
         "t d7_optin_4074_reaches_route_check bash -c \"python3 -B -I $O/optin_case.py '{\\\"sitl_autostart\\\":4074,", 1,
         'd7: 4070 refused, 4074 reaches the route check.'),
        ('/work/c8_judge_r2i_a11_20261111/pins/frozen_inputs_c8_r2i_a11_01.json', '/work/%s/pins/frozen_inputs_c8_r2j_a12_01.json' % OLD, 1,
         'Control: the A12 pins are refused by the A13 launcher.'),
        ('# A12: the A11 -> A12 difference is exactly the image r2j + the reference camera TF of the runner\n'
         't a12_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a12_checks.py\n',
         '# A13: the A12 -> A13 difference is exactly airframe 4074 + model_v2 (identity row, opt-in check, pins)\n'
         't a13_checks /work/analysis/layout/.venv/bin/python -B -I $D/tests/a13_checks.py\n', 1, 'a12_checks -> a13_checks.'),
    ])
    edit('tests/a8_checks.py', [
        ("assert sorted(I) == ['c8_4061', 'c8_4070', 'rel3_4030'], sorted(I)", "assert sorted(I) == ['c8_4061', 'c8_4070', 'c8_4074', 'rel3_4030'], sorted(I)   # A13: + c8_4074",
         1, 'A13: identities.'),
        ("                                     (D / 'verify_flight_c8.py').read_text().splitlines(), lineterm='', n=0)\n"
         "     if l[:1] in '+-' and not l.startswith(('+++', '---'))]\nassert not [l for l in d if l.startswith('-')], d\n",
         "                                     (D / 'verify_flight_c8.py').read_text().replace(%r, '').replace(%r, '').splitlines(), lineterm='', n=0)   # A13 row: a13_checks\n"
         "     if l[:1] in '+-' and not l.startswith(('+++', '---'))]\nassert not [l for l in d if l.startswith('-')], d\n" % (JUDGE_COMMENT, JUDGE_ROW),
         1, 'A13: the A8 judge check ignores the c8_4074 lines (checked by a13_checks).'),
        (".replace('  # A8: airframe X', '')", ".replace('4074', 'X').replace('  # A8: airframe X; A13: X', '').replace('  # A8: airframe X', '')", 1,
         'A13: opt-in airframe 4074 normalised like 4061/4070.'),
        ("pins = J(D / 'pins/frozen_inputs_c8_r2j_a12_01.json')", "pins = J(D / 'pins/%s')" % PINS_NAME, 1, 'Pins A13.'),
        ("assert acc == [[h(D / 'pins/frozen_inputs_c8_r2j_a12_01.json'), str(D / 'pins/frozen_inputs_c8_r2j_a12_01.json')]], acc",
         "assert acc == [[h(D / 'pins/%s'), str(D / 'pins/%s')]], acc" % (PINS_NAME, PINS_NAME), 1, 'Accepted pins A13.'),
        (".replace('fixed_image_r2e_20261109/', 'fixed_image_r2j_20261111/')  # A9",
         ".replace('fixed_image_r2e_20261109/', 'fixed_image_r2j_20261111/').replace(%r, %r)  # A9, A13: model_v2" % (M1, M2), 1,
         'A13: model_v1 keys -> model_v2.'),
        ("    'goal_step5b_20261109/px4_etc/init.d-posix/airframes/' + AF4070.name,\n",
         "    'goal_step5b_20261109/px4_etc/init.d-posix/airframes/' + AF4070.name, %r,   # A13: + 4074\n" % AF4074, 1, 'A13: + airframe 4074.'),
        ("'C8_AIRFRAME=${C8_AIRFRAME:-4070};' in launcher", "'C8_AIRFRAME=${C8_AIRFRAME:-4074};' in launcher", 1, 'A13: default airframe.'),
    ])
    shutil.copy2(Path(__file__).with_name('a13_checks.py'), DST / 'tests/a13_checks.py')
    R.append(('tests/a13_checks.py', 'New test (A13).'))

    # pins
    new = json.loads(json.dumps(old_pins))
    changed = set()
    for group in ('repo_files', 'ledger_files'):
        g = {}
        for name, h in old_pins[group].items():
            nn = name.replace(OLD + '/', NEW + '/', 1).replace(M1, M2, 1)
            h2 = h if nn == '@run/drone.py' else sha(WORK / nn)
            if h2 != h:
                changed.add(nn)
            g[nn] = h2
        if group == 'repo_files':
            g[AF4074] = AF4074_SHA
            changed.add(AF4074)
        new[group] = g
    for k, v in old_pins['run_files'].items():
        p = DST / 'executor' / k if (DST / 'executor' / k).exists() else WORK / 'fixed_image_r2j_20261111/src/bumblebee/examples' / k
        new['run_files'][k] = sha(p)
        if new['run_files'][k] != v:
            changed.add('run_files:' + k)
    allowed = {NEW + '/executor/run.sh', NEW + '/verify_flight_c8.py', NEW + '/candidate/parameters/vpe_profile_optin.py',
               NEW + '/executor/vision_c8.launch.py', 'run_files:vision_c8.launch.py',   # its candidate path check (A13 folder)
               M2 + 'model.sdf', AF4074, 'run_files:run.sh'}
    if not changed <= allowed:
        sys.exit('STOP: unexpected changes: %s' % sorted(changed - allowed))
    R.append(('pins/' + PINS_NAME, 'Changed entries: %s' % sorted(changed)))
    new['expected_manifest'] = str(DST / 'candidate/manifest.json')
    new['combined_manifest_sha256'] = sha(DST / 'candidate/manifest.json')
    new['combined_files'] = json.loads((DST / 'candidate/manifest.json').read_text())['files']
    new['sdk_drone_py']['by'] = NEW + '/tools/make_a13.py'
    new['c8_target'].update(airframe=4074, airframe_chain=[Path(AF4074).name] + old_pins['c8_target']['airframe_chain'],
                            model=str(WORK / M2).rstrip('/'), combined_candidate=str(DST / 'candidate'), executor=str(DST / 'executor'),
                            launcher=str(DST / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                            judge=str(DST / 'verify_flight_c8.py') + ' --identity c8_4074',
                            a13='airframe 4074 + model_v2 of T52 (the 20EC reference dimensions), identity c8_4074 (T55)')
    P = DST / 'pins' / PINS_NAME
    with open(P, 'x') as h:
        h.write(json.dumps(new, indent=1) + '\n')
    with open(DST / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v40-c8-r2j-a13 (host_run_wsl_c8_r2e_b.sh of %s reads only this list)\n'
                '# %s = pins A12 (697408e7) renamed + airframe 4074 + model_v2 (tools/make_a13.py)\n'
                '%s  %s\n' % (NEW, PINS_NAME, sha(P), P))
    (DST / 'tools').mkdir()
    shutil.copy2(__file__, DST / 'tools/make_a13.py')
    out = ['# DIFF A12 -> A13 (generated by tools/make_a13.py)\n']
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
        out.append('\n## %s\n```diff\n%s\n```\n' % (rel, '\n'.join(d[:400])))
    with open(DST / 'DIFF_a13.md', 'x') as h:
        h.write(''.join(out))
    with open(DST / 'build_edits.json', 'x') as h:
        h.write(json.dumps(R, indent=1, ensure_ascii=False) + '\n')
    print(json.dumps({'pins': str(P), 'pins_sha': sha(P), 'judge': sha(DST / 'verify_flight_c8.py'),
                      'manifest': new['combined_manifest_sha256'], 'changed': sorted(changed), 'edits': len(R)}))


if __name__ == '__main__':
    main()
