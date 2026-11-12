#!/usr/bin/env python3
"""make_c8_exec_b.py - T28 (09.11.2026): C8 executor revision b for airframe 4061 / image r2e (owner: variant B).
Built on /work/c8_executor_20261109 (executor_r2e, launcher v31-c8-r2e), which stays untouched. Output: N (new folder):
  candidate/   combined_c8_r2e = combined_13 + the r2e image parts (D2/D3) + honest identity (D7) + 4061 RC contract (D1)
  executor/    executor_r2e + no rollback of the 4061 values (D1), r2e profile (13 names), r2e VPE pins, identity record
  launcher/    host_run_wsl_c8_r2e_b.sh (v32-c8-r2e-b) + its own ACCEPTED_PINS_b.txt
  pins/        frozen_inputs_c8_r2e_b_01.json (same format; judge = the C8 judge copy of this folder)
  DIFF_exec_b.md  every changed line with its reason
Never overwrites. Every source is checked by sha before use.
Usage: python3 -I make_c8_exec_b.py N
"""
import difflib
import hashlib
import json
import shutil
import sys
from pathlib import Path

WORK = Path('/work')
OLD = WORK / 'c8_executor_20261109'
EXO, LAO = OLD / 'executor_r2e', OLD / 'launcher/host_run_wsl_c8_r2e.sh'
C13 = WORK / 'parallel_work/20261015/integration/combined_13'
R2E = WORK / 'fixed_image_r2e_20261109'
PX4_ETC = WORK / 'goal_step5b_20261109/px4_etc'
MODEL = WORK / 'goal_t22_flow_20261109/model_v1/bumblebee'
PLUGIN = WORK / 'goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so'
SRC_SHA = {
    OLD / 'SHA256SUMS.txt': None,  # informational
    C13 / 'manifest.json': 'ab20df8862fd298ef5ec0656e70fe0221314c1ac01b07d1d68fd60c3fcfc3b9b',
    R2E / 'MANIFEST_SHA256.txt': 'd3e043c2',
    R2E / 'src/bumblebee/examples/flight_profile.py': '5b8e2a12a91445a1aba867fc22d84a8fd884a50ebd835da008a31c737633695b',
    R2E / 'src/bumblebee/src/python/vpe_fix.py': '3b8a93d4d08983694186766b0259fa6fa6b4167079c4078cf402a908d02e9725',
    R2E / 'src/bumblebee/src/python/aruco_detect.py': '66f061ecc14445de5901cee8d4dfcd59be98fcaa697b97cbf939a89bd0be9bd3',
    R2E / 'src/bumblebee/examples/drone.py': '855f4cc4ad511a59b679092f3c587ce5689684edd53e3a0abbb72bd2226ac9ad',
}
OLD_PINS = OLD / 'pins/frozen_inputs_c8_r2e_01.json'
OLD_PINS_SHA = 'b9d5fe71'
VPE_OLD, VPE_NEW = '7f107882a52a6819add53352a6feee4d18d117822a5cbdb39e8ca82e37f1fd09', SRC_SHA[R2E / 'src/bumblebee/src/python/vpe_fix.py']
PROF_OLD, PROF_NEW = 'ce5263e73a61162984272e4a2a3ea8cdb2eabc90c46075d7badaa4cc9b5a56ae', SRC_SHA[R2E / 'src/bumblebee/examples/flight_profile.py']
KEEP = ('NAV_RCL_ACT', 'COM_RCL_EXCEPT', 'COM_DISARM_LAND')   # D1: airframe 4061 values stay (3 / 0 / 0.5)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rel(p):
    return str(Path(p).relative_to(WORK))


N = Path(sys.argv[1]).resolve()
R = []   # (relpath in N, original path, reason)


def check_sources():
    for p, s in SRC_SHA.items():
        if s and not sha(p).startswith(s):
            sys.exit('STOP: %s changed (%s)' % (p, sha(p)[:16]))
    if not sha(OLD_PINS).startswith(OLD_PINS_SHA):
        sys.exit('STOP: old pins changed')
    for name, s in json.loads((C13 / 'manifest.json').read_text())['files'].items():
        if sha(C13 / name) != s:
            sys.exit('STOP: combined_13 file changed: ' + name)


def edit(f, orig, edits):
    """f: path in N (already copied from orig). edits: (old, new, count, reason)."""
    t = (N / f).read_text()
    for old, new, n, why in edits:
        c = t.count(old)
        if c != n:
            sys.exit('STOP: %s anchor %r: %d matches (want %d)' % (f, old[:80], c, n))
        t = t.replace(old, new)
        R.append((f, orig, why))
    (N / f).write_text(t)


def put(dst, src):
    d = N / dst
    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        sys.exit('STOP: exists ' + str(d))
    shutil.copy2(src, d)


# ------------------------------------------------------------------ 1) candidate combined_c8_r2e
def build_candidate():
    man13 = json.loads((C13 / 'manifest.json').read_text())
    for name in man13['files']:
        put('candidate/' + name, C13 / name)
    replaced = {
        'parameters/flight_profile.py': R2E / 'src/bumblebee/examples/flight_profile.py',
        'parameters/vpe_fix.py': R2E / 'src/bumblebee/src/python/vpe_fix.py',
        'vision/aruco_detect.py': R2E / 'src/bumblebee/src/python/aruco_detect.py',
    }
    for name, src in replaced.items():
        (N / 'candidate' / name).unlink()   # our own fresh copy of combined_13, replaced by the r2e file
        put('candidate/' + name, src)
        R.append(('candidate/' + name, C13 / name, 'D2/D3: whole file replaced by the r2e image file %s (sha %s).' % (rel(src), sha(src)[:8])))
    P = 'candidate/parameters/'
    edit(P + 'sitl_profile_closure_candidate.py', C13 / 'parameters/sitl_profile_closure_candidate.py', [
        ("PROFILE_SHA256 = '%s'" % PROF_OLD, "PROFILE_SHA256 = '%s'  # c8-r2e-b: r2e flight_profile.py" % PROF_NEW, 1,
         'D3: pinned profile = the r2e flight_profile.py.'),
        ("    if len(profile) != 14 or any(", "    if len(profile) != 13 or any(", 1,
         'D3: r2e INDOOR_ARUCO has 13 names (COM_SPOOLUP_TIME is the drone\'s own value); the closure adds the same 5 children = 18.'),
        ("        raise ValueError('Expected 14 finite profile floats')", "        raise ValueError('Expected 13 finite profile floats')", 1,
         'D3: message follows the count.'),
        ("    return dict(status='model_all_19_restored',", "    return dict(status='model_all_18_restored',", 1,
         'D3: status label follows the closure size (18); no reader of this label exists (grep: judge, executor).'),
    ])
    edit(P + 'vpe_freshness_optin.py', C13 / 'parameters/vpe_freshness_optin.py', [
        ("PIN_C33 = '%s'" % VPE_OLD, "PIN_C33 = '%s'  # c8-r2e-b: r2e vpe_fix (name kept)" % VPE_NEW, 1,
         'D2: pinned VPE = r2e vpe_fix.py (as combined_13 did for P1: only the pinned sha). Methods and constants are still checked.'),
    ])
    edit(P + 'vpe_profile_optin.py', C13 / 'parameters/vpe_profile_optin.py', [
        ("    required=['sitl_4030','sim_gz_en_1','all_fcu_paths_guarded','no_hardware',\n",
         "    # c8-r2e-b (D7): the airframe is checked from PX4's own SYS_AUTOSTART (sitl_setup.py reads it; supervisor copies it)\n"
         "    if audit.get('sitl_autostart')!=4061 or audit.get('sitl_autostart_source')!='rc_ready.json:sys_autostart':\n"
         "        raise RuntimeError('SITL airframe is not 4061')\n"
         "    required=['sim_gz_en_1','all_fcu_paths_guarded','no_hardware',\n", 1,
         'D7: honest identity: the literal label sitl_4030 is replaced by the SYS_AUTOSTART value PX4 reported (must be 4061).'),
        ("!='%s':" % VPE_OLD, "!='%s':  # c8-r2e-b: r2e vpe_fix" % VPE_NEW, 1,
         'D2: pinned VPE = r2e vpe_fix.py.'),
    ])
    rc = json.loads((C13 / 'parameters/rc_expected09.json').read_text())
    assert rc['NAV_RCL_ACT'] == 0.0 and rc['COM_RCL_EXCEPT'] == 4.0
    t = (N / P / 'rc_expected09.json').read_text()
    t2 = t.replace('"COM_RCL_EXCEPT": 4.0,', '"COM_RCL_EXCEPT": 0.0,').replace('"NAV_RCL_ACT": 0.0,', '"NAV_RCL_ACT": 3.0,')
    assert t2.count('"COM_RCL_EXCEPT": 0.0,') == 1 and t2.count('"NAV_RCL_ACT": 3.0,') == 1
    (N / P / 'rc_expected09.json').write_text(t2)
    R.append(('candidate/parameters/rc_expected09.json', C13 / 'parameters/rc_expected09.json',
              'D1: the RC contract asserts the airframe 4061 values (NAV_RCL_ACT 3, COM_RCL_EXCEPT 0) that now stay in PX4.'))
    files = {name: sha(N / 'candidate' / name) for name in man13['files']}
    man = {
        'scope': 'combined_c8_r2e (T28, 09.11.2026): combined_13 + fixed image r2e parts for C8 on airframe 4061. SIMULATOR ONLY.',
        'files': files,
        'origins': dict(man13.get('origins', {}), **{n: rel(s) for n, s in replaced.items()}),
        'flight_accepted': False,
        'changed_from_combined_13': sorted(n for n in files if files[n] != man13['files'][n]),
    }
    with open(N / 'candidate/manifest.json', 'x') as h:
        h.write(json.dumps(man, indent=1) + '\n')
    with open(N / 'candidate/README.md', 'x') as h:
        h.write('# combined_c8_r2e (T28, 09.11.2026). ТОЛЬКО СИМУЛЯТОР. flight_accepted=false\n'
                'combined_13 + r2e: flight_profile.py (13 names), vpe_fix.py (3b8a93d4), aruco_detect.py (66f061ec); pins of the\n'
                'closure (profile sha, 13), freshness and profile opt-in (vpe sha), honest airframe check (D7), RC contract 4061 (D1).\n'
                'Changed files: manifest.json changed_from_combined_13; every line: ../DIFF_exec_b.md.\n')
    return man


# ------------------------------------------------------------------ 2) executor
def build_executor():
    for p in sorted(EXO.rglob('*')):
        if p.is_file():
            put('executor/' + str(p.relative_to(EXO)), p)
    E = 'executor/'
    OWN_OLD, OWN_NEW = '/work/c8_executor_20261109/executor_r2e', '/work/c8_judge_r2e_20261109/executor'
    edit(E + 'run.sh', EXO / 'run.sh', [
        ('OWN=%s  # c8: this copy (flight_trial_24 + target set as parameters, DIFF_r2e.md)' % OWN_OLD,
         'OWN=%s  # c8-r2e-b: this copy (c8 executor_r2e + revision b, ../DIFF_exec_b.md)' % OWN_NEW, 1,
         'Own folder is the new copy (c8_executor_20261109 stays untouched).'),
        ('# c8: product src is a parameter; the sha is r2e drone.py. flight_profile.py stays the ws_package1b copy (14 names; README decision D3)\n',
         '# c8: product src is a parameter; the sha is r2e drone.py. c8-r2e-b (D3): flight_profile.py is the r2e copy (13 names), sha checked\n', 1,
         'D3: comment.'),
        ('cp "$C8_PRODUCT_SRC/examples/drone.py" /work/ws_package1b/src/bumblebee/examples/flight_profile.py "$OUT/"\n',
         'echo "%s  $C8_PRODUCT_SRC/examples/flight_profile.py" | sha256sum -c --quiet - || { echo \'Refusing: product flight_profile.py differs from the sha in run.sh\' >&2; exit 2; }\n'
         'cp "$C8_PRODUCT_SRC/examples/drone.py" "$C8_PRODUCT_SRC/examples/flight_profile.py" "$OUT/"  # c8-r2e-b (D3)\n' % PROF_NEW, 1,
         'D3: the run uses the r2e flight_profile.py (same file as the candidate copy), pinned by sha.'),
    ])
    edit(E + 'sitl_setup.py', EXO / 'sitl_setup.py', [
        ("PROFILE_SOURCE = Path('/work/ws_package1b/src/bumblebee/examples/flight_profile.py')\nPROFILE_COUNT = 14\n",
         "PROFILE_SOURCE = Path('/work/fixed_image_r2e_20261109/src/bumblebee/examples/flight_profile.py')  # c8-r2e-b (D3)\n"
         "PROFILE_COUNT = 13  # c8-r2e-b (D3): r2e INDOOR_ARUCO (no COM_SPOOLUP_TIME)\n"
         "# c8-r2e-b (D1): airframe 4061 values that this setup no longer overwrites with the 20EC files (rc/flight_real_params)\n"
         "KEEP_AIRFRAME = ('NAV_RCL_ACT', 'COM_RCL_EXCEPT', 'COM_DISARM_LAND')\n", 1,
         'D3: r2e profile and its count; D1: names kept at the airframe values.'),
        ("        raise ValueError('INDOOR_ARUCO must contain exactly 14 parameters')",
         "        raise ValueError('INDOOR_ARUCO must contain exactly %d parameters' % PROFILE_COUNT)", 1, 'D3: message follows the count.'),
        ("        raise RuntimeError('Incomplete 14-parameter baseline before rc_ready')",
         "        raise RuntimeError('Incomplete %d-parameter baseline before rc_ready' % PROFILE_COUNT)", 1, 'D3: message follows the count.'),
        ("            report['profile_restore_status'] = 'all_14_confirmed'",
         "            report['profile_restore_status'] = 'all_%d_confirmed' % PROFILE_COUNT", 1,
         'D3: label follows the count (its only reader is dead code in gate.py, `if False:`).'),
        ("        assert pump.read('SYS_AUTOSTART', expected_type=6)[0] == args.expected_autostart, 'Wrong airframe'\n",
         "        autostart = pump.read('SYS_AUTOSTART', expected_type=6)[0]\n"
         "        assert autostart == args.expected_autostart, 'Wrong airframe'\n"
         "        report['sys_autostart'] = autostart  # c8-r2e-b (D7): PX4's own value, copied into audit.json by supervisor.py\n", 1,
         'D7: record the SYS_AUTOSTART value PX4 reported.'),
        ("        params['COM_OBL_RC_ACT'] = dict(value=args.obl, type=6)\n",
         "        params['COM_OBL_RC_ACT'] = dict(value=args.obl, type=6)\n"
         "        report['kept_airframe_values'] = {k: params.pop(k)['value'] for k in KEEP_AIRFRAME if k in params}  # c8-r2e-b (D1)\n", 1,
         'D1: NAV_RCL_ACT, COM_RCL_EXCEPT, COM_DISARM_LAND are not written; the 20EC file values that were skipped are recorded.'),
    ])
    edit(E + 'supervisor.py', EXO / 'supervisor.py', [
        ("    audit={'sitl_4030':True,'sim_gz_en_1':True,",
         "    ready=json.loads((a.out/'rc_ready.json').read_text())  # c8-r2e-b (D7): PX4's own SYS_AUTOSTART from sitl_setup.py\n"
         "    audit={'sitl_autostart':ready['sys_autostart'],'sitl_autostart_source':'rc_ready.json:sys_autostart','sim_gz_en_1':True,", 1,
         'D7: honest identity in audit.json (the literal sitl_4030=True is gone).'),
        ("    report['profile_restored']=True;event('all_19_restored',count=19)",
         "    report['profile_restored']=True;event('all_19_restored',count=len(report['independent_before']))  # c8-r2e-b: real count (18)", 1,
         'D3: the event records the real number of restored values (event name kept).'),
    ])
    new_diag = None
    edit(E + 'vpe_gate_diagnostic_p1.py', EXO / 'vpe_gate_diagnostic_p1.py', [
        ("TARGET_SHA256 = '%s'  # flight_trial_10: P1+P1b candidate" % VPE_OLD,
         "TARGET_SHA256 = '%s'  # c8-r2e-b (D2): r2e vpe_fix" % VPE_NEW, 1,
         'D2: the diagnostic wrapper accepts the r2e vpe_fix (vpe_diagnostic_entry.py compares the imported vpe_fix with it).'),
    ])
    new_diag = sha(N / E / 'vpe_gate_diagnostic_p1.py')
    fresh_new = sha(N / 'candidate/parameters/vpe_freshness_optin.py')
    edit(E + 'vpe_diagnostic_entry.py', EXO / 'vpe_diagnostic_entry.py', [
        ("=='fad42acbd29aecf37d5f0ebb73e9734fcd0af2f4a893b6ef5f54bb5281e42aa1'",
         "=='%s'  # c8-r2e-b: vpe_gate_diagnostic_p1.py with the r2e TARGET_SHA256" % new_diag, 1,
         'D2: pin of the changed diagnostic helper.'),
        ("=='e6422f282633ae9e9fc4ed93824e3c6c05d6a562876c6bfc05ec486572910f20'  # combined_13",
         "=='%s'  # combined_c8_r2e" % fresh_new, 1,
         'D2: pin of the candidate freshness opt-in (r2e vpe sha).'),
    ])
    for f in ('README.md',):
        pass


# ------------------------------------------------------------------ 3) launcher
def build_launcher():
    put('launcher/host_run_wsl_c8_r2e_b.sh', LAO)
    for f in ('clock_watch.py', 'viewer_wslg.sh'):
        put('launcher/' + f, OLD / 'launcher' / f)
    L = 'launcher/host_run_wsl_c8_r2e_b.sh'
    edit(L, LAO, [
        ('# host_run_wsl_c8_r2e.sh = launcher v31-c8-r2e (Claude, 09.11.2026): copy of flight_trial_04_wsl_v29/host_run_wsl.sh for the C8 executor\n'
         '#   /work/c8_executor_20261109/executor_r2e (flight_trial_24 + target set as parameters). Every change: ../DIFF_r2e.md.\n',
         '# host_run_wsl_c8_r2e_b.sh = launcher v32-c8-r2e-b (Claude, T28 09.11.2026): copy of c8_executor_20261109/launcher/host_run_wsl_c8_r2e.sh\n'
         '#   for the C8 executor revision b /work/c8_judge_r2e_20261109/executor. Changes: ../DIFF_exec_b.md (v31 changes: c8_executor_20261109/DIFF_r2e.md).\n', 1,
         'Header: new version and runner.'),
        ('#   bash host_run_wsl_c8_r2e.sh TAG SCENARIO [VIEW]', '#   bash host_run_wsl_c8_r2e_b.sh TAG SCENARIO [VIEW]', 1, 'Usage line.'),
        ('echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e.sh v31-c8-r2e; no real drone, no ssh"',
         'echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v32-c8-r2e-b; no real drone, no ssh"', 1,
         'First printed line: ТОЛЬКО СИМУЛЯТОР + version.'),
        ('no TRIAL argument in v31-c8-r2e', 'no TRIAL argument in v32-c8-r2e-b', 1, 'Version in a refusal.'),
        ('RUNNER=$WORK/c8_executor_20261109/executor_r2e/run.sh   # c8: the only runner of this launcher',
         'RUNNER=$WORK/c8_judge_r2e_20261109/executor/run.sh   # c8-r2e-b: the only runner of this launcher', 1, 'Runner = revision b.'),
        ('ACCEPTED_PINS=$HERE/ACCEPTED_PINS_r2e.txt   # c8-r2e: own accepted-pins list of this launcher version',
         'ACCEPTED_PINS=$HERE/ACCEPTED_PINS_b.txt   # c8-r2e-b: own accepted-pins list of this launcher version', 1,
         'Own accepted-pins list (v31 list untouched).'),
        ("    runner = 'c8_executor_20261109/executor_r2e/run.sh'  # c8: the fixed runner",
         "    runner = 'c8_judge_r2e_20261109/executor/run.sh'  # c8-r2e-b: the fixed runner", 1, 'Pins must cover this runner.'),
        ('echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e.sh v31-c8-r2e" > "$SIDE/launcher.log"',
         'echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v32-c8-r2e-b" > "$SIDE/launcher.log"', 1, 'launcher.log banner.'),
        ("'trial': 'c8_executor_20261109/executor_r2e',", "'trial': 'c8_judge_r2e_20261109/executor',", 1, 'host_check names the real runner.'),
    ])


# ------------------------------------------------------------------ 4) pins
def chain(af):
    d = PX4_ETC / 'init.d-posix/airframes'
    f = [x for x in d.iterdir() if x.name.startswith(af + '_')]
    assert len(f) == 1
    f = f[0]; res = []
    for _ in range(20):
        res.append(f)
        nxt = [l.split('airframes/', 1)[1].split()[0] for l in f.read_text().splitlines() if l.startswith('. ${R}etc/init.d-posix/airframes/')]
        if not nxt:
            break
        f = d / nxt[0]
    return res


def build_pins(man):
    EX, CA = N / 'executor', N / 'candidate'
    exe_py = sorted(EX.glob('*.py'))
    assert len(exe_py) == 12
    repo = {}
    for p in exe_py + [EX / 'run.sh', EX / 'run_sim.snapshot.sh', EX / 'MAVROS_BP02_SHA256SUMS.txt', EX / 'PRODUCT_SHA256SUMS.txt']:
        repo[rel(p)] = sha(p)
    for p in [R2E / 'src/bumblebee/examples/flight_profile.py', WORK / 'ws_package1b/setpoint_freshness_sitl_reference.json',
              R2E / 'src/bumblebee/examples/drone.py', R2E / 'src/bumblebee/src/cpp/simple_offboard.cpp',
              R2E / 'install/bumblebee/lib/bumblebee/simple_offboard', R2E / 'src/bumblebee/src/python/setpoint_freshness.py',
              R2E / 'src/bumblebee/src/python/vpe_fix.py', R2E / 'src/bumblebee/src/python/aruco_detect.py',
              R2E / 'src/bumblebee/launch/mavros_scoped_config.py', R2E / 'MANIFEST_SHA256.txt', R2E / 'image_manifest_r2.tsv',
              WORK / 'parallel_work/20261015/integration/combined_trial_tools/start_mavros.py',
              WORK / 'parallel_work/20261015/integration/combined_trial_tools/vision.launch.py',
              WORK / 'sim/ros_stack/pipeline_probe.py', WORK / 'sim/ros_stack/rc_real_params.json', WORK / 'sim/ros_stack/flight_real_params.json',
              N / 'legacy/verify_package1b_gates_c8.py', N / 'verify_flight_c8.py',
              PLUGIN] + chain('4061') + sorted(x for x in MODEL.rglob('*') if x.is_file()):
        repo[rel(p)] = sha(p)
    for name in man['files']:
        repo[rel(CA / name)] = sha(CA / name)
    run_files = {p.name: sha(p) for p in exe_py}
    run_files['run.sh'] = sha(EX / 'run.sh'); run_files['run_sim.snapshot.sh'] = sha(EX / 'run_sim.snapshot.sh')
    run_files['drone.py'] = SRC_SHA[R2E / 'src/bumblebee/examples/drone.py']
    run_files['flight_profile.py'] = PROF_NEW
    ledger = {rel(p): sha(p) for p in exe_py}
    ledger[rel(EX / 'run.sh')] = sha(EX / 'run.sh')
    for p in sorted((CA / 'parameters').glob('*.py')) + sorted((CA / 'parameters').glob('*.json')) + [CA / 'vision/aruco_detect.py',
              R2E / 'install/bumblebee/lib/bumblebee/simple_offboard', R2E / 'src/bumblebee/src/python/setpoint_freshness.py']:
        ledger[rel(p)] = sha(p)
    ledger['@run/drone.py'] = SRC_SHA[R2E / 'src/bumblebee/examples/drone.py']
    assert len(ledger) == 31, len(ledger)
    old = json.loads(OLD_PINS.read_text())
    pins = {
        'schema': 1,
        'scope': old['scope'],
        'expected_manifest': str(CA / 'manifest.json'),
        'combined_manifest_sha256': sha(CA / 'manifest.json'),
        'combined_files': man['files'],
        'repo_files': repo, 'run_files': run_files, 'ledger_files': ledger,
        'legacy_verifier_sha256': sha(N / 'legacy/verify_package1b_gates_c8.py'),
        'sdk_drone_py': dict(old['sdk_drone_py'], by='c8_judge_r2e_20261109/tools/make_c8_exec_b.py'),
        'c8_target': dict(old['c8_target'], combined_candidate=str(CA), executor=str(EX),
                          launcher=str(N / 'launcher/host_run_wsl_c8_r2e_b.sh'),
                          judge=str(N / 'verify_flight_c8.py') + ' --identity c8_4061',
                          note='informational; verify_flight_c8.py and the launcher read only the keys above it'),
    }
    P = N / 'pins/frozen_inputs_c8_r2e_b_01.json'
    P.parent.mkdir(exist_ok=True)
    with open(P, 'x') as h:
        h.write(json.dumps(pins, indent=1) + '\n')
    with open(N / 'launcher/ACCEPTED_PINS_b.txt', 'x') as h:
        h.write('# ACCEPTED_PINS_b.txt of launcher v32-c8-r2e-b (host_run_wsl_c8_r2e_b.sh reads only this list)\n'
                '# frozen_inputs_c8_r2e_b_01.json: combined_c8_r2e + executor revision b + airframe 4061 chain + r2e + T22 model_v1/plugin_v1 + MAVROS bp02 + C8 judge copy\n'
                '%s  %s\n' % (sha(P), P))
    return P, pins


def write_diff():
    out = ['# DIFF_exec_b — C8 executor revision b vs its originals (generated by tools/make_c8_exec_b.py)\n\n',
           'Originals: c8_executor_20261109/executor_r2e, launcher/host_run_wsl_c8_r2e.sh, combined_13. Every other copied file is '
           'byte-identical (SHA256SUMS.txt). New files: candidate/manifest.json, candidate/README.md, pins/, launcher/ACCEPTED_PINS_b.txt.\n\n',
           '## Replacements and reasons\n\n| # | file | reason |\n|---|---|---|\n']
    for i, (f, orig, why) in enumerate(R, 1):
        out.append('| %d | %s | %s |\n' % (i, f, why.replace('|', '/')))
    out.append('\n## Unified diffs (every changed line)\n')
    seen = []
    for f, orig, _ in R:
        if f in seen:
            continue
        seen.append(f)
        try:
            a, b = Path(orig).read_text().splitlines(True), (N / f).read_text().splitlines(True)
        except UnicodeDecodeError:
            continue
        if len(a) > 3000:
            out.append('\n### %s\n\nwhole file replaced (sha %s -> %s)\n' % (f, sha(orig)[:8], sha(N / f)[:8]))
            continue
        d = difflib.unified_diff(a, b, fromfile=str(orig), tofile=str(N / f))
        out.append('\n### %s\n\n```diff\n%s```\n' % (f, ''.join(d)))
    with open(N / 'DIFF_exec_b.md', 'x') as h:
        h.writelines(out)


def main():
    check_sources()
    if any((N / d).exists() for d in ('candidate', 'executor', 'launcher', 'pins', 'DIFF_exec_b.md')):
        sys.exit('STOP: refusing to overwrite')
    man = build_candidate()
    build_executor()
    build_launcher()
    P, pins = build_pins(man)
    write_diff()
    print(json.dumps({'replacements': len(R), 'candidate_manifest': sha(N / 'candidate/manifest.json'), 'pins': str(P),
                      'pins_sha': sha(P), 'repo_files': len(pins['repo_files']), 'run_files': len(pins['run_files']),
                      'ledger_files': len(pins['ledger_files'])}))


if __name__ == '__main__':
    main()
