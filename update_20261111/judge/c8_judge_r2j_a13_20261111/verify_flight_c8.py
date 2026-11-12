#!/usr/bin/env python3
"""Host-only, fail-closed review of one saved combined SITL scenario.

C8 COPY (T28, 09.11.2026, owner variant B) of flight_verification_03/verify_flight.py (sha d7f96939).
Changed only: expected airframe, profile names and (c8_4061, owner 09.11 variant A) the pinned expectation files of
real_parameters_before_arm come from the fixed IDENTITIES table (--identity, required); reports are written only into
this folder's reviews/; the legacy verifier is this folder's copy (legacy/).
'rel3_4030' = the accepted judge's values (bit-for-bit proof on rel3: tools/compare_rel3.py).
"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent   # /work (the accepted judge: HERE.parents[3] of flight_verification_03 = /work)
LEGACY = HERE / 'legacy/verify_package1b_gates_c8.py'
LEGACY_SHA = '8bcef313758277da8c9bc05ec25f0b2f5c618d0e65704a0e1ac98f4553d0360e'
NAMES_REL3 = set('COM_DISARM_PRFLT COM_SPOOLUP_TIME MPC_ACC_HOR MPC_JERK_MAX MPC_LAND_SPEED MPC_TKO_SPEED MPC_VEL_MANUAL MPC_VEL_MAN_BACK MPC_VEL_MAN_SIDE MPC_XY_CRUISE MPC_XY_P MPC_XY_VEL_D_ACC MPC_XY_VEL_I_ACC MPC_XY_VEL_MAX MPC_XY_VEL_P_ACC MPC_Z_VEL_MAX_DN MPC_Z_VEL_MAX_UP MPC_Z_V_AUTO_DN MPC_Z_V_AUTO_UP'.split())
# C8 identity table (fixed; no free values on the command line).
#  rel3_4030: the accepted judge (airframe 4030, 19 names = combined_13 profile 14 + closure 5).
#  c8_4061:   airframe 4061 (candidate set 09.11), image r2e: its flight_profile.py DEFAULT has 13 names
#             (no COM_SPOOLUP_TIME: the drone's own value), + the same closure 5 = 18 names.
#             real_parameters_before_arm expects expect/*_4061.json (owner 09.11 «да», variant A): the sim/ros_stack
#             files with only the 5 values of 4061 (NAV_RCL_ACT 3, COM_RCL_EXCEPT 0, COM_DISARM_LAND 0.5,
#             COM_SPOOLUP_TIME 1.0, BAT1_SOURCE 1; A5); pinned here by sha.
#  c8_4070:   A8 (T38, 10.11.2026): airframe 4070 of the Simulator = 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1, image r2f;
#             the same 18 names; expect/*_4070.json = the 4061 files + those 2 values (tools/make_a8.py EXPECT_4070).
#  c8_4074:   A13 (T55, 11.11.2026): airframe 4074 of the Simulator (T52) = 4070 v2 + the 10 sensor positions of the
#             20EC reference; the same 18 names and the same expect/*_4070.json (no EKF2_*_POS / MIN_RNG is judged).
IDENTITIES = {
    'rel3_4030': dict(autostart=4030, names=frozenset(NAMES_REL3), real_params=None),
    'c8_4061': dict(autostart=4061, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={
        'flight_real_params.json': (HERE / 'expect/flight_real_params_4061.json', '5c00730133462a0b831ddf82dedeb43dc66ab2f98c629d8044aadf8b344d6444'),
        'rc_real_params.json': (HERE / 'expect/rc_real_params_4061.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),
    'c8_4070': dict(autostart=4070, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={
        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '9e471a6e3fcad40958fab2eaa040713479759ef815581ebeb9761590634900d1'),
        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),
    'c8_4074': dict(autostart=4074, names=frozenset(NAMES_REL3 - {'COM_SPOOLUP_TIME'}), real_params={
        'flight_real_params.json': (HERE / 'expect/flight_real_params_4070.json', '9e471a6e3fcad40958fab2eaa040713479759ef815581ebeb9761590634900d1'),
        'rc_real_params.json': (HERE / 'expect/rc_real_params_4070.json', '99002dc26d073659b2ba567b8d6c67122bb710b896c8c05499b9e65bcc0c1d9c')}),
}
IDENTITY = None
NAMES = None


def use_identity(key):
    global IDENTITY, NAMES
    IDENTITY = key
    NAMES = set(IDENTITIES[key]['names'])
# flight_verification_03: the owner's field candidate (sheets 30x42) is pinned here because the frozen pins do not list it.
FIELD_SUMS = ROOT / 'parallel_work/20261015/integration/field_measurements_01/SHA256SUMS.json'
FIELD_SUMS_SHA = '49229a96c2681a3d98238233a477cdf97180c48e7f5a592b3dace617d9314c51'
FIELD_MARK = 'field_measurements_01/generated'
SCENARIOS = {'land':'S8', 'kill':'S2', 'freeze':'S3', 'mavros_restart':'S4',
             'pilot':'S5', 'cancel_before':'S6', 'ack_cancel':'S7',
             'cancel':'after_arm_cancel', 'heartbeat':'S9', 'preflight':'preflight'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def verdict(items):
    states = [x['status'] for x in items]
    return 'failed' if 'failed' in states else 'unknown' if not states or 'unknown' in states else 'pass'


def item(status='unknown', reason='', **evidence):
    return dict(status=status, reason=reason, evidence=evidence)


def condition(value, reason='', **evidence):
    return item('pass' if value is True else 'failed' if value is False else 'unknown', reason, **evidence)


def read_json(path, errors, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        errors.append(dict(file=str(path), error=str(exc)))
        return default


def load_legacy():
    if digest(LEGACY) != LEGACY_SHA:
        raise ValueError('Existing passive verifier changed; independent review must be renewed')
    spec = importlib.util.spec_from_file_location('flight_verification_legacy', LEGACY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.AUTOSTART = IDENTITIES[IDENTITY]['autostart']   # C8 copy: identity values passed to the legacy copy
    real = IDENTITIES[IDENTITY]['real_params']
    if real is not None:
        for name, (path, sha) in real.items():
            if not path.is_file() or digest(path) != sha:
                raise ValueError('Pinned real-parameter expectation changed: ' + str(path))
        module.REAL_PARAMS = {name: str(path) for name, (path, sha) in real.items()}
    return module


def provenance(run, manifest_path, pins, errors):
    checks = {}
    expected = pins.get('combined_manifest_sha256')
    checks['accepted_manifest'] = condition(
        digest(manifest_path) == expected if manifest_path.is_file() and expected else None,
        'Expected SHA comes from the separately frozen trusted pins, not from the run')
    copied = run / 'combined_manifest.json'
    checks['run_manifest'] = condition(digest(copied) == expected if copied.is_file() and expected else None)
    manifest = read_json(manifest_path, errors, {})
    files = manifest.get('files', {})
    bad, missing = [], []
    for name, sha in files.items():
        path = (manifest_path.parent / name).resolve()
        if not path.is_relative_to(manifest_path.parent.resolve()):
            bad.append(name)
        elif not path.is_file():
            missing.append(name)
        elif digest(path) != sha or pins.get('combined_files', {}).get(name) != sha:
            bad.append(name)
    checks['combined_sources'] = item('failed' if bad else 'unknown' if missing or not files or files != pins.get('combined_files') else 'pass',
        'Accepted candidate files are checked independently of its saved run ledger', mismatched=bad, missing=missing)
    for group, base in (('repo_files', ROOT), ('run_files', run)):
        bad, missing = [], []
        for name, sha in pins.get(group, {}).items():
            path = (base / name).resolve()
            if not path.is_relative_to(base.resolve()):
                bad.append(name)
            elif not path.is_file():
                missing.append(name)
            elif digest(path) != sha:
                bad.append(name)
        checks[group] = item('failed' if bad else 'unknown' if missing or not pins.get(group) else 'pass',
            'Run copies and current frozen sources must agree with the trusted pre-run snapshot', mismatched=bad, missing=missing)
    ledger = run / 'flight_source.sha256'
    seen, bad = set(), []
    if ledger.is_file():
        for line in ledger.read_text().splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})\s+\*?(.+)', line)
            if not match:
                bad.append(line); continue
            sha, name = match.groups()
            if '/sim/runs/' in name:
                key = '@run/' + Path(name).name
            elif name.startswith('/work/'):
                key = name[6:]
            else:
                key = name
            if key in seen or pins.get('ledger_files', {}).get(key) != sha:
                bad.append(key)
            seen.add(key)
    missing = sorted(set(pins.get('ledger_files', {})) - seen)
    checks['pre_run_source_ledger'] = item('failed' if bad else 'unknown' if missing or not seen else 'pass',
        'A recorded source ledger is provenance evidence, not proof of every process memory page', mismatched=bad, missing=missing)
    run_sh = run / 'run.sh'
    if run_sh.is_file() and FIELD_MARK in run_sh.read_text(errors='replace'):
        checks['field_files'] = field_check(run, errors)
    return dict(status=verdict(checks.values()), checks=checks)


def field_check(run, errors):
    # flight_verification_03: the run's field_files.sha256 must equal the pinned owner field list (generated/ part).
    if not FIELD_SUMS.is_file() or digest(FIELD_SUMS) != FIELD_SUMS_SHA:
        return item('failed', 'Pinned field reference changed or missing', reference=str(FIELD_SUMS))
    ref = read_json(FIELD_SUMS, errors, {}).get('files', {})
    expected = {k.split('generated/', 1)[1]: v for k, v in ref.items() if k.startswith('generated/')}
    recorded, bad_lines = {}, []
    path = run / 'field_files.sha256'
    if not path.is_file():
        return item('failed', 'Field run without field_files.sha256', expected_files=len(expected))
    for line in path.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})\s+\*?\./(.+)', line)
        if not match:
            bad_lines.append(line); continue
        recorded[match.group(2)] = match.group(1)
    differ = sorted(n for n in set(expected) | set(recorded) if expected.get(n) != recorded.get(n))
    return condition(bool(expected) and not differ and not bad_lines,
        'Field files of the run equal the pinned owner field (field_measurements_01/SHA256SUMS.json generated/)',
        files=len(recorded), expected=len(expected), differ=differ[:20], bad_lines=bad_lines[:5])


def read_packets(run, errors):
    rows, broken = [], False
    try:
        for number, line in enumerate((run/'mavlink_proxy.jsonl').read_text().splitlines(), 1):
            if line.strip():
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError('Non-object proxy record')
                    rows.append(value)
                except ValueError as exc:
                    broken = True; errors.append(dict(proxy_line=number, error=str(exc)))
    except OSError as exc:
        errors.append(dict(file='mavlink_proxy.jsonl', error=str(exc)))
    started = next((r for r in rows if r.get('kind') == 'started'), {})
    complete = bool(rows and started and rows[-1].get('kind') == 'stopped' and not broken
                    and {'SET_POSITION_TARGET_LOCAL_NED','SET_ATTITUDE_TARGET'} <= set(started.get('recorded_packet_types',[])))
    return rows, complete


def fcu_heartbeat(row):
    return (row.get('kind') == 'heartbeat_forwarded' and row.get('source_system') == 1
            and row.get('source_component') == 1 and row.get('autopilot') == 12 and finite(row.get('wall')))


def main_mode(row):
    value = row.get('custom_mode')
    return (value >> 16) & 255 if type(value) is int else None


def profile_review(flight, journal, packets, complete=None):
    # flight_verification_03: verify() passes the real proxy completeness; complete=None (direct calls in old tests)
    # evaluates the given packets as they are.
    checks = {}
    phases = ['independent_before', 'independent_after', 'independent_stable']
    baseline = journal.get('baseline', {})
    checks['journal_restored'] = condition(journal.get('status') == 'restored' and journal.get('pending') is None
        if journal else None, journal_status=journal.get('status'))
    checks['journal_names'] = condition(set(baseline) == NAMES and all(finite(v) for v in baseline.values()) if baseline else None, expected_count=len(NAMES), actual_count=len(baseline))
    details = {}; intervals = {}
    for phase in phases:
        samples = flight.get(phase)
        if not isinstance(samples, dict):
            checks[phase] = item(reason='Independent complete wire scan is missing'); continue
        bad = []; received = []
        for name in NAMES:
            sample = samples.get(name)
            if not isinstance(sample, dict):
                bad.append(dict(name=name, error='missing')); continue
            value, stamp = sample.get('value'), sample.get('received')
            if (sample.get('source') != [1, 1] or sample.get('type') != 9 or not finite(value)
                    or not finite(stamp) or name not in baseline or value != baseline[name]):
                bad.append(dict(name=name, sample=sample, journal_baseline=baseline.get(name)))
            if finite(stamp):
                received.append(stamp)
        if received:
            intervals[phase] = [min(received), max(received)]
        checks[phase] = condition(not bad and set(samples) == NAMES,
            'Exact names, float values, REAL32 type and FCU source 1/1; no tolerance silently broadens equality', bad=bad,
            unexpected=sorted(set(samples)-NAMES), received_interval=intervals.get(phase))
        details[phase] = samples
    for key in ['expected', 'final_readback']:
        values = journal.get(key)
        checks['journal_'+key] = condition(set(values) == NAMES and values == baseline if isinstance(values, dict) else None)
    before, after, stable = [intervals.get(p) for p in phases]
    states = flight.get('states', [])
    ignored = [r for r in states if not isinstance(r, dict) or r.get('armed') not in (True, False) or not finite(r.get('wall'))]
    armed = [r['wall'] for r in states if r.get('armed') is True and finite(r.get('wall'))]
    disarmed = [r['wall'] for r in states if r.get('armed') is False and armed and finite(r.get('wall')) and r['wall'] > min(armed)]
    applied = flight.get('independent_applied', {})
    applied_times = [s.get('received') for s in applied.values() if isinstance(s, dict)]
    start = flight.get('started_wall'); end = flight.get('finished_wall')
    timing = None
    if before and after and stable and finite(start) and finite(end) and applied_times and all(finite(v) for v in applied_times):
        timing = (start <= before[0] <= before[1] < min(applied_times) <= max(applied_times) < after[0]
                  and after[1] < stable[0] <= stable[1] <= end)
        if armed:
            # flight_verification_02 (19.10.2026): 01 required max(disarmed) < after[0], but the supervisor records MAVROS
            # State (1 Hz) until the end, so disarmed States always arrive during/after the 'after' scan and no armed run
            # could pass (INT_flight_pc_land_01). Intent: restoration starts only after the vehicle disarmed and stayed
            # disarmed. Now: a disarm after the LAST armed State, before the 'after' scan; no armed State at/after it.
            last_armed = max(armed)
            disarm_after_last = [w for w in disarmed if w > last_armed]
            timing = (timing and before[1] < min(armed) and bool(disarm_after_last)
                      and min(disarm_after_last) < after[0] and last_armed < after[0])
    checks['scan_order'] = condition(timing, 'Before/apply/after/stable are distinct chronological scans; armed flights require post-disarm restoration', intervals=intervals,
        ignored_state_rows=len(ignored), ignored_state_examples=ignored[:5])
    hb_armed = [r['wall'] for r in packets if fcu_heartbeat(r) and r.get('armed') is True]
    if armed or hb_armed:
        # flight_verification_03 (S4): MAVROS State can be missing while MAVROS restarts, so re-arming is also searched in
        # the source-identified FCU heartbeats: an armed FCU heartbeat needs an armed State, and no armed FCU heartbeat may
        # follow the first disarmed State after the last armed State (until the end of the record).
        last = max(armed) if armed else None
        d0 = min((w for w in disarmed if last is not None and w > last), default=None)
        rearm = [w for w in hb_armed if d0 is not None and w > d0]
        value = None if complete is False else (bool(armed) and d0 is not None and not rearm)
        checks['no_armed_fcu_heartbeat_after_disarm'] = condition(value,
            'No source-identified armed FCU heartbeat after the first disarm that follows the last armed State; '
            'unknown when the proxy record is incomplete', first_disarm_state=d0, armed_heartbeats=len(hb_armed),
            armed_heartbeats_after_disarm=rearm[:10], armed_states=len(armed), proxy_complete=complete)
    hb = [r for r in packets if fcu_heartbeat(r) and after and stable and after[1] < r['wall'] < stable[0]]
    unique = sorted(set(r['wall'] for r in hb))
    checks['three_stability_heartbeats'] = condition(len(unique) >= 3 and all(r.get('armed') is False for r in hb) if after and stable else None,
        'Three source-identified disarmed FCU heartbeats must separate after and stable scans', count=len(unique))
    checks['final_connected_disarmed'] = condition(states[-1].get('connected') is True and states[-1].get('armed') is False if states else None)
    checks['profile_restored_flag'] = condition(flight.get('profile_restored') if type(flight.get('profile_restored')) is bool else None)
    return dict(status=verdict(checks.values()), checks=checks, independent_scans=details,
        limits=['PARAM has no nonce and reads are not an atomic snapshot.', 'Only these %d known dependencies are covered.' % len(NAMES)])


def scenario_measurements(scenario, events, packets, complete, log, old, criteria):
    checks = {}; measurements = {}
    def first(kind):
        return next((r for r in events if r.get('kind') == kind), None)
    def old_check(name):
        return old.get('checks', {}).get(name, item(reason='Existing verifier check unavailable'))
    status = log.rows('vehicle_status') if log else None
    if scenario == 'freeze':
        fault, before, resume = first('injected_signal'), first('sigcont_before'), first('sigcont')
        valid = bool(fault and before and resume and fault.get('signal') == 'freeze'
                     and fault.get('pid') == before.get('pid') == resume.get('pid')
                     and all(finite(r.get('sim')) and finite(r.get('wall')) for r in (fault,before,resume))
                     and fault['wall'] < before['wall'] <= resume['wall']
                     and fault['sim'] <= before['sim'] <= resume['sim'])
        duration = before['sim']-fault['sim'] if valid else None
        after_duration = resume['sim']-fault['sim'] if valid else None
        tolerance = criteria.get('s3_stop_tolerance_sim_s', .05)
        checks['stop_two_sim_seconds'] = condition(abs(duration-2.) <= tolerance and abs(after_duration-2.) <= tolerance if duration is not None else None,
            'Recorded pre-signal boundaries; not an OS scheduler trace', measured_sim_s=duration,
            after_signal_measured_sim_s=after_duration,tolerance_sim_s=tolerance, fault=fault, before=before, resume=resume)
        checks['no_armed_offboard_return'] = old_check('offboard_no_armed_reentry')
    elif scenario == 'pilot':
        modes = [r for r in packets if fcu_heartbeat(r) and r.get('armed') is True and main_mode(r) == 3]
        takeover = modes[0] if modes else None
        cleanup = next((r for r in events if r.get('kind') == 'external_mode_sent' and r.get('mode') == 'AUTO.LAND'), None)
        refused = first('pilot_command_refusal')
        checks['posctl_source_heartbeat'] = condition(True if takeover else None, first=takeover)
        checks['sdk_refused'] = condition(refused.get('success') is False if refused else None, response=refused)
        end = cleanup.get('wall') if cleanup else None
        if takeover and finite(end) and end > takeover['wall'] and complete:
            sp = [r for r in packets if r.get('kind') == 'setpoint_forwarded' and finite(r.get('wall'))
                  and takeover['wall'] < r['wall'] < end]
            timed = finite(takeover.get('px4_sim')) and all(finite(r.get('px4_sim')) for r in sp)
            late = [r for r in sp if r.get('px4_sim', -math.inf) > takeover.get('px4_sim', math.inf)+.1]
            checks['targets_stop_after_posctl_heartbeat'] = condition(not late if timed else None,
                'No target later than 0.1 PX4 simulation seconds after the first identified POSCTL heartbeat',
                late_count=len(late), examples=late[:10], observed_until_cleanup_wall=end)
            returns = [r for r in packets if fcu_heartbeat(r) and r.get('armed') is True and main_mode(r) == 6
                       and takeover['wall'] < r['wall'] < end]
            checks['no_offboard_heartbeat_reentry'] = condition(not returns, reentries=returns)
        else:
            checks['targets_stop_after_posctl_heartbeat'] = item(reason='Complete proxy and explicit cleanup boundary required')
            checks['no_offboard_heartbeat_reentry'] = item(reason='Complete observed POSCTL interval required')
        # Heartbeats alone cannot exclude a brief return between reports.
        checks['no_ulog_armed_reentry'] = item(reason='Aligned ULog and POSCTL/cleanup brackets required')
        checks['stop_within_heartbeat_plus_point_one'] = item(reason='Aligned POSCTL transition and complete target timing required')
        if status and takeover and finite(end) and old_check('ulog_gazebo_sim_clock_alignment')['status'] == 'pass':
            pos = next((r for r in status if r.get('arming_state') == 2 and r.get('nav_state') == 2), None)
            cleanup_sim = cleanup.get('sim')
            if pos and finite(cleanup_sim) and old_check('px4_boot_gazebo_clock_alignment')['status'] == 'pass':
                returns = [r for r in status if pos['timestamp'] < r['timestamp'] < cleanup_sim*1e6
                           and r.get('arming_state') == 2 and r.get('nav_state') == 14]
                checks['no_ulog_armed_reentry'] = condition(not returns, reentries=returns)
                targets = [r for r in packets if r.get('kind') == 'setpoint_forwarded'
                           and finite(r.get('px4_sim')) and pos['timestamp']/1e6 <= r['px4_sim'] < cleanup_sim]
                last = max((r['px4_sim'] for r in targets),default=pos['timestamp']/1e6)
                checks['stop_within_heartbeat_plus_point_one'] = condition(last-pos['timestamp']/1e6 <= 1.1 if complete else None,
                    'Actual PX4 POSCTL transition to final forwarded target, one 1 Hz heartbeat plus 0.1 seconds',
                    delay_sim_s=last-pos['timestamp']/1e6)
    elif scenario == 'land':
        for name in ['physical_takeoff','land_actual_disarm','landing_disarm_within_3s']:
            checks[name] = old_check(name)
        returned = first('safe_land_return')
        disarm = old_check('land_actual_disarm').get('evidence', {}).get('disarm_sim_s')
        checks['safe_land_true_after_disarm'] = condition(
            returned.get('success') is True and returned['sim'] >= disarm if returned and finite(disarm) and finite(returned.get('sim')) else None,
            'Order of the saved return event and actual PX4 DISARM; not a client-side nanosecond trace', returned=returned, disarm_sim_s=disarm)
        contact = old_check('landing_disarm_within_3s').get('evidence', {}).get('landed_sim_s')
        land = old_check('land_actual_disarm').get('evidence', {}).get('land_sim_s')
        gt = log.rows('vehicle_local_position_groundtruth') if log else None
        speeds = [r['vz'] for r in (gt or []) if finite(r.get('vz')) and finite(contact) and finite(land)
                  and land+.2 <= r['timestamp']/1e6 <= contact-.2]
        if speeds:
            ordered = sorted(speeds); median = ordered[len(ordered)//2]
            measurements['s8_descent'] = dict(samples=len(speeds), median_down_mps=median,
                min_down_mps=min(speeds), max_down_mps=max(speeds), window_sim_s=[land+.2,contact-.2])
            tolerance = criteria.get('s8_descent_abs_tolerance_mps')
            checks['descent_near_point_four'] = condition(abs(median-.4) <= tolerance if finite(tolerance) else None,
                'The original word approximately has no numeric tolerance; only explicit reviewed criteria can supply it',
                tolerance_mps=tolerance, **measurements['s8_descent'])
        else:
            checks['descent_near_point_four'] = item(reason='Physical GT velocity during the descent is unavailable')
        checks['offboard_disarmed_after_landing'] = condition(any(r.get('arming_state') != 2 and r.get('nav_state') == 14
            and r['timestamp']/1e6 >= disarm for r in status) if status and finite(disarm) else None)
        checks['next_physical_takeoff'] = item(reason='A second ARM and independently confirmed physical rise are required; current one-flight runner does not supply this gate')
    elif scenario == 'heartbeat':
        checks['shared_clock_acceptance'] = item(reason='Current runner explicitly excludes S9; wall/simulation timeout mismatch is unresolved')
    return dict(checks=checks, status=verdict(checks.values()), measurements=measurements)


def verify(run, expected_manifest, pins, origin=None, criteria=None):
    errors = []; criteria = criteria or {}
    flight = read_json(run/'flight_result.json', errors, {}) or {}
    gate = read_json(run/'gate_result.json', errors, {}) or {}
    journal = read_json(run/'guard_final/profile_journal.json', errors, {}) or {}
    packets, complete = read_packets(run, errors)
    legacy = None
    try:
        legacy = load_legacy()
        legacy_result = legacy.verify(run, origin)
    except Exception as exc:
        errors.append(dict(existing_verifier_error=str(exc)))
        legacy_result = {}
    try:
        log = legacy.Log(run/'flight.ulg') if legacy and (run/'flight.ulg').is_file() else None
    except Exception as exc:
        errors.append(dict(ulog_error=str(exc))); log = None
    scenario = flight.get('scenario', gate.get('scenario'))
    core = legacy_result.get('full_cancel_acceptance' if scenario in ('cancel','ack_cancel') else 'independent_acceptance', {})
    measured = scenario_measurements(scenario, gate.get('events') or read_json(run/'gate_events.json', errors, []) or [],
                                     packets, complete, log, legacy_result, criteria)
    profile = profile_review(flight, journal, packets, complete)
    prov = provenance(run, expected_manifest, pins, errors)
    prerequisites = {
        'raw_gate_result': condition(gate.get('pass') if type(gate.get('pass')) is bool else None),
        'success_before_cleanup': condition(flight.get('success_before_cleanup') if type(flight.get('success_before_cleanup')) is bool else None),
        'independent_profile19': item(profile['status']), 'frozen_provenance': item(prov['status']),
        'complete_proxy': condition(complete if packets else None),
        'fresh_single_ulog': item(reason='Fresh single ULog copy status required'),
        'scenario_identity': condition(flight.get('scenario') == gate.get('scenario') if flight and gate else None),
    }
    copied = read_json(run/'ulog_copy_status.json', errors, {}) or {}
    prerequisites['fresh_single_ulog'] = condition(copied.get('fresh_log_count') == 1 and copied.get('copied') is True if copied else None)
    if scenario == 'preflight':
        prerequisites.pop('raw_gate_result'); prerequisites.pop('scenario_identity')
        no_arm = not any(r.get('kind') == 'arm_forwarded' for r in packets)
        no_arm = no_arm and not any(r.get('armed') is True for r in packets if fcu_heartbeat(r))
        prerequisites['no_arm_preflight'] = condition(no_arm if complete else None)
        commands = legacy_result.get('ulog_command_counts',{})
        prerequisites['no_arm_preflight_ulog'] = condition(
            not legacy_result.get('arming_intervals') and commands.get('external_arm') == 0 and not log.u.dropouts
            if log and commands.get('dataset_present') is True else None)
        scenario_checks = dict(prerequisites)
    else:
        scenario_checks = dict(prerequisites, existing_core=item(core.get('status','unknown')))
        scenario_checks.update(measured['checks'])
        if scenario == 'pilot':
            # There is no legacy complete S5 required-check table.
            scenario_checks.pop('existing_core')
            for name in ['px4_version','candidate4030','real_parameters_before_arm','simulation_only_parameters','physical_takeoff','rc_valid_while_armed']:
                scenario_checks[name] = legacy_result.get('checks',{}).get(name,item())
        if scenario in ('land','heartbeat'):
            scenario_checks['full_scenario_coverage'] = item(reason='S8 needs a second takeoff; S9 has no eligible shared-clock flight gate')
    s1 = legacy_result.get('checks',{}).get('s1_first_target_true_offset',item())
    return dict(schema=1, run=str(run), scenario=scenario, scenario_gate=SCENARIOS.get(scenario,'unknown'),
        scenario_status=verdict(scenario_checks.values()), scenario_checks=scenario_checks,
        raw_gate_result=gate.get('pass'), success_before_cleanup=flight.get('success_before_cleanup'),
        profile_restored_flag=flight.get('profile_restored'), profile19=profile,
        provenance=prov, existing_core=core, supplementary=measured,
        s1=dict(status='unknown', physical_target_check=s1,
                scope='No complete S1 verdict: single MODE/accepted ARM and text evidence also require review'),
        legacy_full_report=legacy_result, errors=errors,
        strict_original_vision_acceptance=False, deployment_accepted=False,
        limits=['One saved combined candidate scenario; no hardware or publication acceptance.',
                'Missing evidence remains unknown. Cleanup success cannot promote an earlier failure.',
                'Values are independent wire scans but PARAM has no nonce or atomic snapshot.',
                'Source ledgers and immutable copies establish recorded inputs, not every runtime memory page.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--expected-manifest', type=Path, required=True)
    parser.add_argument('--frozen-pins', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--origin-evidence', type=Path)
    parser.add_argument('--criteria', type=Path)
    parser.add_argument('--identity', required=True, choices=sorted(IDENTITIES))
    args = parser.parse_args()
    use_identity(args.identity)
    out = args.out.resolve()
    if not out.is_relative_to(HERE / 'reviews') or out.exists():
        raise SystemExit('Write a new report only inside c8_judge_r2e_20261109/reviews')
    origin = None
    if args.origin_evidence:
        data = json.loads(args.origin_evidence.read_text())
        values = data.get('enu_origin_ned')
        if data.get('verified') is not True or not data.get('method') or not data.get('evidence_sha256'):
            raise SystemExit('Origin requires a reviewed method and hashed independent evidence')
        for name, sha in data['evidence_sha256'].items():
            if digest(Path(name)) != sha:
                raise SystemExit('Origin evidence SHA mismatch')
        if not isinstance(values,list) or len(values)!=3 or not all(finite(v) for v in values):
            raise SystemExit('Origin requires three finite N/E/D values')
        origin = values
    pins = json.loads(args.frozen_pins.read_text())
    criteria = json.loads(args.criteria.read_text()) if args.criteria else {}
    for key,value in criteria.items():
        if key not in ('s3_stop_tolerance_sim_s','s8_descent_abs_tolerance_mps') or not finite(value) or value < 0:
            raise SystemExit('Unsupported criteria')
        if key == 's3_stop_tolerance_sim_s' and value > .05:
            raise SystemExit('S3 timing tolerance cannot be broadened beyond 0.05 simulation seconds')
    report = verify(args.run.resolve(),args.expected_manifest.resolve(),pins,origin,criteria)
    report['review_input_sha256'] = dict(frozen_pins=digest(args.frozen_pins), verifier=digest(Path(__file__)),
        expected_manifest=digest(args.expected_manifest), criteria=digest(args.criteria) if args.criteria else None,
        origin_evidence=digest(args.origin_evidence) if args.origin_evidence else None)
    report['judge_identity'] = dict(identity=IDENTITY, autostart=IDENTITIES[IDENTITY]['autostart'],
                                    names=sorted(NAMES), legacy=str(LEGACY),
                                    real_params=({n: [str(p), s] for n, (p, s) in IDENTITIES[IDENTITY]['real_params'].items()}
                                                 if IDENTITIES[IDENTITY]['real_params'] else None))
    report['evidence_sha256'] = {str(p.relative_to(args.run)):digest(p) for p in args.run.rglob('*')
        if p.is_file() and p.name in ('flight_result.json','gate_result.json','gate_events.json','profile_journal.json',
            'combined_manifest.json','flight_source.sha256','flight.ulg','groundtruth.json','mavlink_proxy.jsonl','ulog_copy_status.json')}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(report=str(out),scenario=report['scenario'],status=report['scenario_status'],
        raw=report['raw_gate_result'],core=report['existing_core'].get('status'),profile19=report['profile19']['status'])))
    raise SystemExit(0 if report['scenario_status']=='pass' else 1 if report['scenario_status']=='failed' else 2)


if __name__ == '__main__':
    main()
