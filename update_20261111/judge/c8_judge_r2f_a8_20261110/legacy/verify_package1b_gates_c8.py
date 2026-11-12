#!/usr/bin/env python3
"""Read local SITL artifacts and report pass/failed/unknown without commanding ROS.

C8 COPY (T28, 09.11.2026, owner variant B): copy of analysis/exp_scripts/verify_package1b_gates.py (sha 1f6e2b0b).
Only changes: the expected SYS_AUTOSTART of the 'candidate4030' check is the module value AUTOSTART, and (owner 09.11,
variant A) the expectation files of 'real_parameters_before_arm' are the module value REAL_PARAMS when set; both are set by
the C8 judge copy (verify_flight_c8.py) from its fixed identity table (it checks the sha of the files). With the defaults
(4030, None) this file behaves exactly as the original. The check id stays 'candidate4030' (historical name).

Example (host):
  analysis/layout/.venv/bin/python -I analysis/exp_scripts/verify_package1b_gates.py \
    sim/runs/TAG --out sim/runs/TAG/passive_verification.json

No simulation, sockets, subprocesses, parameter changes, or hardware access.
Missing data never become a successful check. --enu-origin-ned explicitly supplies
the NED coordinates of Gazebo's world ENU origin; absent that, physical S1 target
comparison is unknown. ULog estimated position/target comparison is also reported.
"""
import argparse
import bisect
import hashlib
import json
import lzma
import math
import re
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / 'analysis/codex_python'))
PX4_COMMIT = '94cb2012792b2ae89f0b147cfee53ee31ae550be'
AUTOSTART = 4030   # C8 copy: set by verify_flight_c8.py from its identity table (4030 = the accepted judge)
REAL_PARAMS = None  # C8 copy: {file name: pinned path} for c8_4061; None = the original lookup (run copy, else sim/ros_stack)
PX4_STATUS_SOURCE = 'https://raw.githubusercontent.com/PX4/PX4-Autopilot/v1.16.1/msg/versioned/VehicleStatus.msg'
PX4_POSITION_SOURCE = 'https://raw.githubusercontent.com/PX4/PX4-Autopilot/v1.16.1/msg/versioned/VehicleLocalPosition.msg'
# Commander casts its internal events enum into latest_disarming_reason. That
# enum differs from constants in versioned VehicleStatus.msg on the pinned build.
# Prefer metadata_events embedded in the ULog; do not guess the shifted values.
REASONS = {0: 'transition_to_standby', 1: 'stick_gesture', 2: 'rc_switch',
           3: 'command_internal', 4: 'command_external', 5: 'mission_start'}
SP_TYPES = {'SET_POSITION_TARGET_LOCAL_NED', 'SET_ATTITUDE_TARGET'}
TOPICS = ['vehicle_status', 'vehicle_command', 'vehicle_command_ack',
          'manual_control_setpoint', 'failsafe_flags', 'vehicle_local_position',
          'vehicle_local_position_groundtruth', 'trajectory_setpoint', 'vehicle_land_detected']


def scalar(value):
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    return scalar(value)


def read_json(path, errors, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        errors.append({'file': str(path), 'error': str(exc)})
        return default


def read_aruco_policy(run, errors):
    path = run / 'aruco_policy.json'
    metadata = read_json(path, errors)
    if metadata is not None and not isinstance(metadata, dict):
        errors.append({'file': str(path), 'error': 'ArUco policy must be a JSON object'})
        metadata = None
    declared = metadata.get('aruco_policy') if metadata else 'unknown'
    changed = metadata.get('policy_changed') if metadata else None
    candidate = declared == 'single_geometry_candidate' or changed is True
    original = declared == 'original' and changed is False
    wrapper = metadata.get('wrapper') if metadata else None
    snapshot = run / Path(wrapper).name if isinstance(wrapper, str) and wrapper else None
    actual = hashlib.sha256(snapshot.read_bytes()).hexdigest() if snapshot and snapshot.is_file() else None
    logged = metadata.get('wrapper_sha256') if metadata else None
    return {'source': 'aruco_policy.json' if metadata is not None else 'unknown',
            'metadata': metadata, 'aruco_policy': declared, 'policy_changed': changed,
            'classification': 'candidate' if candidate else 'original_declared' if original else 'unknown',
            'snapshot_file': snapshot.name if snapshot else None, 'snapshot_sha256': actual,
            'wrapper_sha_matches_snapshot': actual == logged if actual and logged else None}


def read_vision_policy(run, errors):
    """Provenance only: never adds a physical gate or upgrades its verdict."""
    path = run / 'vpe_policy.json'
    metadata = read_json(path, errors)
    if metadata is not None and not isinstance(metadata, dict):
        errors.append({'file': str(path), 'error': 'Vision policy must be a JSON object'})
        metadata = None
    declared = metadata.get('vpe_policy') if metadata else 'unknown'
    changed = metadata.get('policy_changed') if metadata else None
    aruco = read_aruco_policy(run, errors)
    vpe_candidate = declared == 'recent_single_candidate' or changed is True
    vpe_original = declared == 'original' and changed is False
    candidate = vpe_candidate or aruco['classification'] == 'candidate'
    original = vpe_original and aruco['classification'] == 'original_declared'
    if candidate:
        boundary = ('Candidate VPE and/or ArUco policy only; any passing scenario is conditional on those recorded policies '
                    'and is not acceptance of the original vision stack')
    elif original:
        boundary = ('Both original VPE and ArUco policies explicitly declared by run metadata; a scenario verdict alone '
                    'does not establish complete original-vision acceptance')
    else:
        boundary = ('Vision policy/source unknown; this scenario cannot establish acceptance '
                    'of the original vision stack')
    startups = []
    ros_log = run / 'ros.log'
    if ros_log.exists():
        with ros_log.open(errors='replace') as stream:
            for line in stream:
                for marker in ('VPE_RECENT_SINGLE_CANDIDATE_START', 'VPE_GATE_DIAG_START'):
                    if marker+' ' not in line:
                        continue
                    try:
                        row = json.loads(line.split(marker+' ', 1)[1])
                        if not isinstance(row, dict):
                            continue
                        filename = ('vpe_recent_single_candidate.py' if marker.startswith('VPE_RECENT')
                                    else 'vpe_gate_diagnostic.py')
                        snapshot = run / filename
                        actual = hashlib.sha256(snapshot.read_bytes()).hexdigest() if snapshot.exists() else None
                        logged = row.get('wrapper_sha256')
                        startups.append({'marker': marker, 'policy': row.get('policy'),
                            'policy_changed': row.get('policy_changed'),
                            'original_vpe_sha256': row.get('source_sha256'),
                            'logged_wrapper_sha256': logged, 'snapshot_file': filename,
                            'snapshot_sha256': actual,
                            'wrapper_sha_matches_snapshot': actual == logged if actual and logged else None})
                    except (OSError, ValueError) as exc:
                        errors.append({'file': str(ros_log), 'marker': marker, 'error': str(exc)})
    return {'source': 'vpe_policy.json + aruco_policy.json' if metadata is not None and aruco['metadata'] is not None else 'unknown',
            'vpe_source': 'vpe_policy.json' if metadata is not None else 'unknown',
            'metadata_file': str(path) if path.exists() else None,
            'metadata_sha256': hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            'metadata': metadata, 'vpe_policy': declared,
            'classification': 'candidate' if candidate else 'original_declared' if original else 'unknown',
            'vpe_policy_changed': changed, 'aruco_policy': aruco,
            'policy_changed': True if candidate else False if original else None,
            'wrapper_startup_evidence': startups,
            # Metadata naming "original" is not a complete vision-flight acceptance.
            'strict_original_vision_acceptance': False if candidate else 'unknown',
            'scope': boundary}


def freeze_setpoint_window(packets, fault, resume, stopped, recorder_complete,
                           advertised, old_end=None, resume_before=None):
    """Conservative S3 window, including the time before SIGCONT.

    The gate waits for AUTO.LAND before sending SIGCONT. The first identified
    PX4 armed AUTO.LAND heartbeat after the injected fault is therefore an
    earlier boundary; a future sigcont_before record is preferred for checking
    that ordering. The legacy post-signal event count is diagnostic only.
    """
    old_end_wall = old_end.get('wall') if old_end else None
    old_count = None
    if resume and number(resume.get('wall')) and number(old_end_wall):
        old_count = sum(r.get('kind') == 'setpoint_forwarded' and number(r.get('wall'))
                        and resume['wall'] < r['wall'] <= old_end_wall for r in packets)
    evidence = {'old_recorded_resume_boundary': {
        'start_wall': resume.get('wall') if resume else None, 'end_wall': old_end_wall,
        'forwarded_count': old_count, 'acceptance_eligible': False,
        'limitation': 'The legacy sigcont event is recorded after sending SIGCONT; a zero count can miss that gap or the later proxy tail'}}
    if not fault or not resume or not number(fault.get('wall')) or not number(resume.get('wall')):
        return dict(status='unknown', reason='Fault and SIGCONT records required', **evidence)
    if fault.get('signal') != 'freeze' or fault.get('pid') != resume.get('pid'):
        return dict(status='unknown', reason='The same recorded producer PID must receive the freeze and SIGCONT', **evidence)
    boundary = resume_before if resume_before else resume
    if resume_before and (resume_before.get('pid') != fault.get('pid') or not number(resume_before.get('wall'))):
        return dict(status='unknown', reason='Invalid pre-SIGCONT producer boundary', **evidence)
    px4_land = []
    for row in packets:
        mode = row.get('custom_mode')
        # Pinned MAVROS 2.14 px4_custom_mode.hpp: AUTO=4, AUTO_LAND=6.
        if (row.get('kind') in ('heartbeat', 'heartbeat_forwarded')
            and row.get('source_system') == 1 and row.get('source_component') == 1
            and row.get('autopilot') == 12 and row.get('armed') is True
            and isinstance(mode, int) and ((mode >> 16) & 255) == 4
            and ((mode >> 24) & 255) == 6 and number(row.get('wall'))
            and row['wall'] >= fault['wall']):
            px4_land.append(row)
    heartbeat = min(px4_land, key=lambda r: r['wall']) if px4_land else None
    if not heartbeat or heartbeat['wall'] >= boundary['wall']:
        return dict(status='unknown', reason='No source-identified armed AUTO.LAND heartbeat before SIGCONT',
                    first_px4_armed_land_heartbeat=heartbeat, **evidence)
    tail_end = stopped.get('wall') if stopped else None
    forwarded = [r for r in packets if r.get('kind') == 'setpoint_forwarded' and number(r.get('wall'))
                 and heartbeat['wall'] <= r['wall'] and (not number(tail_end) or r['wall'] <= tail_end)]
    evidence.update(window_start_wall=heartbeat['wall'], window_end_wall=tail_end,
                    first_px4_armed_land_heartbeat=heartbeat,
                    before_sigcont_record=resume_before, forwarded_count=len(forwarded),
                    forwarded_examples=forwarded[:20],
                    stop_to_recorded_resume_wall_s=resume['wall']-fault['wall'],
                    land_heartbeat_to_recorded_resume_wall_s=resume['wall']-heartbeat['wall'],
                    boundary_basis='First confirmed PX4 armed AUTO.LAND after the fault, through proxy stopped; includes the pre-SIGCONT period')
    complete = bool(recorder_complete and SP_TYPES <= set(advertised) and number(tail_end)
                    and tail_end >= resume['wall'])
    if not complete:
        return dict(status='unknown', reason='Complete advertised setpoint recording through proxy stopped is required', **evidence)
    return dict(status='failed' if forwarded else 'pass',
                reason='No grace interval: every forwarded target in the conservative LAND-to-proxy-stop S3 window counts',
                **evidence)


class Log:
    def __init__(self, path):
        from pyulog import ULog
        self.u = ULog(str(path), TOPICS)
        self.data = {d.name: d.data for d in self.u.data_list if d.multi_id == 0}
        self.reason_map = dict(REASONS)
        self.reason_map_source = 'unambiguous_common_values_only'
        try:
            metadata = json.loads(lzma.decompress(b''.join(self.u.msg_info_multiple_dict['metadata_events'][0])))
            for component in metadata['components'].values():
                enum = component.get('enums', {}).get('arm_disarm_reason_t')
                if enum:
                    self.reason_map = {int(k): v['name'] for k, v in enum['entries'].items()}
                    self.reason_map_source = 'embedded_metadata_events'
                    break
        except (KeyError, TypeError, ValueError, lzma.LZMAError):
            pass

    def rows(self, topic):
        data = self.data.get(topic)
        if data is None:
            return None
        return [{key: scalar(values[i]) for key, values in data.items()}
                for i in range(len(data['timestamp']))]

    def parameters_at(self, timestamp):
        values = dict(self.u.initial_parameters)
        # ULog initial values can be pre-run defaults; fold every earlier change.
        for stamp, name, value in sorted(self.u.changed_parameters, key=lambda x: x[0]):
            if stamp <= timestamp:
                values[name] = value
        return {k: scalar(v) for k, v in values.items()}


def verify(run, origin=None):
    errors, checks = [], {}
    result = {'run': str(run.resolve()), 'checks': checks, 'errors': errors}
    vision = read_vision_policy(run, errors)
    result['vision_policy'] = vision
    result['aruco_policy'] = vision['aruco_policy']
    result['strict_original_vision_acceptance'] = vision['strict_original_vision_acceptance']

    def check(name, status='unknown', reason='', **evidence):
        checks[name] = dict(status=status, reason=reason, evidence=clean(evidence))

    gate = read_json(run / 'gate_result.json', errors, {}) or {}
    events = gate.get('events') or read_json(run / 'gate_events.json', errors, []) or []
    scenario = gate.get('scenario')
    result['scenario'] = scenario
    result['offset_ms'] = gate.get('offset_ms')
    if isinstance(gate.get('pass'), bool):
        check('runner_completed', 'pass' if gate['pass'] else 'failed',
              'Runner assertion result, independently checked below', runner_pass=gate['pass'])
    else:
        check('runner_completed', reason='gate_result.json is missing or incomplete')

    proxy_path = run / 'mavlink_proxy.jsonl'
    packets, incomplete = [], False
    if proxy_path.exists():
        try:
            for line_number, line in enumerate(proxy_path.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if not isinstance(obj, dict):
                        raise ValueError('Proxy record is not an object')
                    packets.append(obj)
                except ValueError as exc:
                    incomplete = True
                    errors.append({'file': str(proxy_path), 'line': line_number, 'error': str(exc)})
        except OSError as exc:
            incomplete = True
            errors.append({'file': str(proxy_path), 'error': str(exc)})
    started = next((r for r in packets if r.get('kind') == 'started'), {})
    stopped = next((r for r in reversed(packets) if r.get('kind') == 'stopped'), {})
    advertised = set(started.get('recorded_packet_types') or [])
    recorder_complete = bool(started and stopped and not incomplete)
    result['proxy'] = {'records': len(packets), 'complete': recorder_complete,
                       'advertised_packet_types': sorted(advertised)}

    ulpath = run / 'flight.ulg'
    log = None
    if ulpath.exists():
        try:
            log = Log(ulpath)
        except Exception as exc:
            errors.append({'file': str(ulpath), 'error': str(exc)})
    status = log.rows('vehicle_status') if log else None
    commands = log.rows('vehicle_command') if log else None
    acks = log.rows('vehicle_command_ack') if log else None
    flags = log.rows('failsafe_flags') if log else None
    manual = log.rows('manual_control_setpoint') if log else None
    intervals = []
    if status:
        begin = None
        for i, row in enumerate(status):
            if row['arming_state'] == 2 and begin is None:
                begin = row['timestamp']
            if row['arming_state'] != 2 and begin is not None:
                reason = row.get('latest_disarming_reason')
                intervals.append({'arm_us': begin, 'disarm_us': row['timestamp'],
                                  'reason': reason, 'reason_name': log.reason_map.get(reason, 'unknown')})
                begin = None
        if begin is not None:
            intervals.append({'arm_us': begin, 'disarm_us': None, 'reason_name': 'not_observed'})
    result['arming_intervals'] = intervals
    arm_commands = [r for r in (commands or []) if r.get('command') == 400 and
                    r.get('param1', 0) > .5 and r.get('from_external')]
    disarm_commands = [r for r in (commands or []) if r.get('command') == 400 and
                       r.get('param1', 1) <= .5 and r.get('from_external')]
    result['ulog_command_counts'] = {'external_arm': len(arm_commands),
                                     'external_disarm': len(disarm_commands),
                                     'dataset_present': commands is not None}
    if log:
        commit = str(log.u.msg_info_dict.get('ver_sw', ''))
        check('px4_version', 'pass' if commit == PX4_COMMIT else 'failed',
              'Exact pinned PX4 source commit', actual=commit, expected=PX4_COMMIT)
        result['ulog'] = {'datasets': sorted(log.data),
                          'dropouts': len(log.u.dropouts), 'path': str(ulpath),
                          'disarm_reason_enum': log.reason_map, 'reason_enum_source': log.reason_map_source}
    else:
        check('px4_version', reason='Readable ULog is required')

    first_arm = intervals[0]['arm_us'] if intervals else (
        arm_commands[0]['timestamp'] if arm_commands else None)
    # Cancellation before ARM still has a meaningful snapshot: final logged values,
    # plus the independent ready report, but it is labelled "no actual ARM".
    snapshot_time = first_arm if first_arm is not None else (
        status[-1]['timestamp'] if status else None)
    params = log.parameters_at(snapshot_time) if log and snapshot_time is not None else {}
    result['parameter_snapshot'] = {'at_us': snapshot_time,
                                    'basis': 'before_first_arm' if first_arm is not None else 'no_arm_final_snapshot'}
    identity = {'SYS_AUTOSTART': AUTOSTART, 'SIM_GZ_EN': 1, 'COM_OBL_RC_ACT': 4}
    missing = [k for k in identity if not number(params.get(k))]
    mismatches = {k: {'actual': params.get(k), 'expected': v} for k, v in identity.items()
                  if number(params.get(k)) and abs(float(params[k]) - v) > .001}
    check('candidate4030', 'failed' if mismatches else 'unknown' if missing else 'pass',
          'ULog values after folding parameter changes', values={k: params.get(k) for k in identity},
          missing=missing, mismatches=mismatches)
    expected = {}
    sim_expected = {}
    sources = []
    for name in ['flight_real_params.json', 'rc_real_params.json']:
        if REAL_PARAMS is not None:
            # C8 copy (variant A): the identity's pinned expectation; a run copy cannot replace it
            path = Path(REAL_PARAMS[name])
        else:
            path = run / name
            if not path.exists():
                path = WORKSPACE / 'sim/ros_stack' / name
        obj = read_json(path, errors, {}) or {}
        expected.update({k: v['value'] for k, v in obj.get('parameters', {}).items()})
        sim_expected.update({k: v['value'] for k, v in obj.get('sim_only', {}).items()})
        sources.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()
                        if path.exists() else None, 'source': obj.get('source')})
    missing = [k for k in expected if not number(params.get(k))]
    mismatches = {k: {'actual': params[k], 'expected': v} for k, v in expected.items()
                  if number(params.get(k)) and abs(float(params[k]) - float(v)) > .001}
    check('real_parameters_before_arm', 'failed' if mismatches else 'unknown' if missing or not expected else 'pass',
          'Real commander/RC values, not ULog initial defaults alone',
          actual_arm_observed=first_arm is not None, expected_count=len(expected),
          values={k: params.get(k) for k in expected}, missing=missing,
          mismatches=mismatches, sources=sources)
    sim_missing = [k for k in sim_expected if not number(params.get(k))]
    sim_mismatches = {k: {'actual': params[k], 'expected': v} for k, v in sim_expected.items()
                      if number(params.get(k)) and abs(float(params[k]) - float(v)) > .001}
    check('simulation_only_parameters', 'failed' if sim_mismatches else 'unknown' if sim_missing or not sim_expected else 'pass',
          'Separate simulator-only values, not claimed as physical drone parameters',
          values={k: params.get(k) for k in sim_expected}, missing=sim_missing, mismatches=sim_mismatches)

    if not intervals:
        check('rc_valid_while_armed', reason='No armed interval observed; ground input is not an in-flight RC test')
    elif (not manual or not flags or not {'valid', 'data_source'} <= set(manual[0])
          or 'manual_control_signal_lost' not in flags[0]):
        check('rc_valid_while_armed', reason='manual_control_setpoint and failsafe_flags datasets required')
    else:
        def armed_at(stamp):
            return any(w['arm_us'] <= stamp <= (w['disarm_us'] or status[-1]['timestamp']) for w in intervals)
        mr = [r for r in manual if armed_at(r['timestamp'])]
        fr = [r for r in flags if armed_at(r['timestamp'])]
        sources_rc = sorted(set(r.get('data_source') for r in mr), key=str)
        bad_manual = sum(not r.get('valid') or r.get('data_source') != 1 for r in mr)
        bad_flags = sum(bool(r.get('manual_control_signal_lost')) for r in fr)
        ok = bool(mr and fr) and not bad_manual and not bad_flags
        check('rc_valid_while_armed', 'pass' if ok else 'failed' if mr and fr else 'unknown',
              'Actual RC source 1, valid manual input, no RC loss throughout logged armed intervals',
              samples=len(mr), flags_samples=len(fr), sources=sources_rc,
              invalid_manual_samples=bad_manual, lost_flag_samples=bad_flags)

    cancel = next((e for e in events if e.get('kind') in ('sigint_during_arm', 'sigint_before_navigate')), None)
    forwarded = [r for r in packets if r.get('kind') == 'arm_forwarded']
    if cancel and recorder_complete:
        before = [r for r in forwarded if r['wall'] <= cancel['wall']]
        after = [r for r in forwarded if r['wall'] > cancel['wall']]
        check('arm_sequence_at_cancel', 'pass', 'Counts are facts, not proof that an earlier ARM can be recalled',
              before_cancel=len(before), after_cancel=len(after), total=len(forwarded),
              ulog_received_external_arm_count=len(arm_commands), cancel_wall=cancel['wall'])
        check('no_additional_arm_after_cancel', 'pass' if not after else 'failed',
              'No new ARM forwarded after the recorded cancellation', after_cancel=len(after))
    else:
        check('arm_sequence_at_cancel', reason='Cancellation event and complete proxy recording required')
        check('no_additional_arm_after_cancel', reason='Cancellation event and complete proxy recording required')
    if scenario == 'cancel_before':
        known = commands is not None and log and not log.u.dropouts and recorder_complete
        fail = bool(arm_commands or forwarded or intervals)
        check('cancel_before_no_arm', 'failed' if fail else 'pass' if known else 'unknown',
              'No ARM at proxy, no received external ARM in ULog, no armed state',
              proxy_arm_count=len(forwarded), ulog_arm_count=len(arm_commands),
              armed_intervals=len(intervals))
    else:
        check('cancel_before_no_arm', reason='Not a cancel_before scenario')

    if scenario in ('cancel', 'ack_cancel'):
        if intervals and all(w['disarm_us'] is not None for w in intervals):
            valid = all(w.get('reason') == 4 for w in intervals)
            unforced = [r for r in disarm_commands if abs(r.get('param2') or 0.) < .001]
            check('cancel_external_nonforced_disarm',
                  'pass' if valid and unforced else 'failed',
                  'PX4 disarm reason must be command_external, not preflight auto-disarm',
                  intervals=intervals, nonforced_disarm_commands=unforced,
                  command_ack_400=[r for r in (acks or []) if r.get('command') == 400])
        else:
            check('cancel_external_nonforced_disarm', reason='Complete armed-to-disarmed transition and command dataset required')
    else:
        check('cancel_external_nonforced_disarm', reason='Not an after-ARM cancellation scenario')

    truth = read_json(run / 'groundtruth.json', errors, []) or []
    ground = next((e for e in events if e.get('kind') == 'ground_ready'), None)
    end_event = next((e for e in reversed(events) if e.get('kind') == 'disarmed'), None)
    cancel_end = next((e for e in reversed(events) if e.get('kind') == 'cancel_verified'), None)
    if not end_event and cancel_end:
        end_event = cancel_end
    if scenario in ('cancel_before', 'cancel', 'ack_cancel') and truth and ground and end_event:
        samples = [v for v in truth if ground['wall'] <= v.get('wall', -math.inf) <= end_event['wall']]
        if samples and 'truth_z' in ground:
            rise = max(v['z'] for v in samples) - ground['truth_z']
            check('cancel_true_rise_below_5cm', 'pass' if rise < .05 else 'failed',
                  'Measured Gazebo body ENU z, not estimated telemetry', max_rise_m=rise,
                  reference_z=ground['truth_z'], samples=len(samples),
                  measurement='maximum of recorded samples')
        else:
            check('cancel_true_rise_below_5cm', reason='True-position samples and explicit ground reference required')
    else:
        check('cancel_true_rise_below_5cm', reason='Cancellation ground/reference/end events and physical truth required')

    airborne = next((e for e in events if e.get('kind') == 'airborne'), None)
    airborne_scenarios = {'land', 'kill', 'freeze', 'mavros_restart', 'pilot', 'heartbeat'}
    if scenario in airborne_scenarios and ground and truth:
        window = [r for r in truth if ground['wall'] <= r.get('wall', -math.inf)
                  <= (airborne['wall'] if airborne else truth[-1]['wall'])]
        reference = ground.get('truth_z')
        if window and number(reference):
            rise = max(r['z'] for r in window) - reference
            event_rise = airborne.get('truth_z', reference) - reference if airborne else None
            injected = next((e for e in events if e.get('kind') == 'injected_signal'), None)
            preceding = [r for r in truth if injected and r.get('wall', math.inf) <= injected['wall']]
            at_fault_rise = preceding[-1]['z'] - reference if preceding else None
            at_fault_age = injected['wall'] - preceding[-1]['wall'] if preceding else None
            event_ok = bool(rise >= .35 and airborne and event_rise >= .35)
            fault_ok = not injected or (preceding and at_fault_rise >= .35 and at_fault_age < 1.)
            physical_status = 'failed' if not event_ok or (preceding and not fault_ok) else 'unknown' if injected and not preceding else 'pass'
            check('physical_takeoff', physical_status,
                  'At least 0.35 m physical Gazebo body rise at the airborne boundary, independent of estimated height',
                  maximum_rise_before_boundary_m=rise, physical_rise_at_airborne_event_m=event_rise,
                  reference_z=reference, airborne_event=airborne, samples=len(window),
                  physical_rise_at_fault_m=at_fault_rise, truth_age_at_fault_wall_s=at_fault_age)
        else:
            check('physical_takeoff', reason='Physical ground reference and valid truth samples required')
    else:
        check('physical_takeoff', reason='Not an airborne scenario, or physical truth/reference is missing')

    clock_aligned = False
    gt = log.rows('vehicle_local_position_groundtruth') if log else None
    if truth and gt:
        import numpy as np
        times = np.asarray([r['timestamp'] / 1e6 for r in gt])
        eligible = [r for r in truth if number(r.get('sim')) and times[0] <= r['sim'] <= times[-1]]
        moving = bool(eligible and max(r['z'] for r in eligible) - min(r['z'] for r in eligible) > .05)
        if eligible:
            sim = np.asarray([r['sim'] for r in eligible])
            observed = np.asarray([[r['y'], r['x'], -r['z']] for r in eligible])
            expected_gt = np.column_stack([np.interp(sim, times, [r[k] for r in gt]) for k in ['x', 'y', 'z']])
            residual = np.linalg.norm(observed - expected_gt, axis=1)
            clock_aligned = moving and float(np.max(residual)) < .01
            check('ulog_gazebo_sim_clock_alignment', 'pass' if clock_aligned else 'unknown',
                  'Moving physical Gazebo truth agrees with ULog groundtruth at the same simulation timestamps',
                  samples=len(eligible), moving_trajectory=moving,
                  maximum_position_residual_m=float(np.max(residual)),
                  median_position_residual_m=float(np.median(residual)))
        else:
            check('ulog_gazebo_sim_clock_alignment', reason='No overlapping groundtruth samples')
    else:
        check('ulog_gazebo_sim_clock_alignment', reason='Both timestamped physical truth datasets are required')

    # Schema 2 obtains boot time only from PX4 source 1/1. It can also align
    # stationary cancellation runs, where a constant position proves no clock.
    proxy_skew = None
    if truth and started.get('schema', 0) >= 2 and started.get('px4_clock_basis') == 'PX4 source 1/1 time_boot_ms messages':
        chronological = sorted((r for r in truth if number(r.get('wall')) and number(r.get('sim'))),
                               key=lambda r: r['wall'])
        wall_times = [r['wall'] for r in chronological]
        comparisons = []
        for packet in packets:
            if not number(packet.get('px4_sim')) or not number(packet.get('wall')):
                continue
            i = bisect.bisect_left(wall_times, packet['wall'])
            if 0 < i < len(wall_times) and 0 < wall_times[i] - wall_times[i - 1] <= .5:
                ratio = (packet['wall'] - wall_times[i - 1]) / (wall_times[i] - wall_times[i - 1])
                gazebo_sim = chronological[i - 1]['sim'] + ratio * (chronological[i]['sim'] - chronological[i - 1]['sim'])
                comparisons.append((packet['wall'], packet['px4_sim'], gazebo_sim,
                                    abs(packet['px4_sim'] - gazebo_sim)))
        if comparisons and len(comparisons) >= 8 and comparisons[-1][1] - comparisons[0][1] >= 1.:
            proxy_skew = max(row[3] for row in comparisons)
            aligned = proxy_skew < .15
            clock_aligned = clock_aligned or aligned
            check('px4_boot_gazebo_clock_alignment', 'pass' if aligned else 'unknown',
                  'Source-identified PX4 boot clock compared with timestamped Gazebo truth, including stationary runs',
                  samples=len(comparisons), maximum_observed_clock_skew_sim_s=proxy_skew,
                  px4_clock_source=started['px4_clock_basis'])
        else:
            check('px4_boot_gazebo_clock_alignment', reason='At least eight overlapping clock records spanning one simulation second required')
    else:
        check('px4_boot_gazebo_clock_alignment', reason='Schema 2 source-identified PX4 boot clock records and physical truth required')

    fault = next((e for e in events if e.get('kind') == 'injected_signal'), None)
    respawn = next((e for e in events if e.get('kind') == 'mavros_respawn'), None)
    resume = next((e for e in events if e.get('kind') == 'sigcont'), None)
    resume_before = next((e for e in events if e.get('kind') == 'sigcont_before'), None)
    heartbeats = [r for r in packets if r.get('kind') == 'heartbeat']
    first_land = None
    relevant_disarm = None
    if status and intervals:
        after = fault['sim'] * 1e6 if fault and clock_aligned else intervals[0]['arm_us']
        first_land = next((r for r in status if r['timestamp'] >= after and
                           r.get('arming_state') == 2 and r.get('nav_state') == 18), None)
        if first_land:
            relevant_disarm = next((w for w in intervals if w['arm_us'] <= first_land['timestamp']
                                   and w['disarm_us'] is not None and w['disarm_us'] >= first_land['timestamp']), None)
    if scenario in ('kill', 'freeze', 'mavros_restart') and fault and status and clock_aligned:
        reentries = [r for r in status if first_land and r['timestamp'] > first_land['timestamp']
                     and r.get('arming_state') == 2 and r.get('nav_state') == 14]
        ended = relevant_disarm is not None
        check('offboard_no_armed_reentry', 'failed' if reentries else 'pass' if first_land and ended and not log.u.dropouts else 'unknown',
              'Actual PX4 ULog state: armed LAND followed by DISARM; OFFBOARD after DISARM is allowed',
              first_land_sim_s=first_land['timestamp'] / 1e6 if first_land else None,
              disarm_sim_s=relevant_disarm['disarm_us'] / 1e6 if relevant_disarm else None,
              reentries=reentries, resume_event=resume, respawn_event=respawn,
              heartbeat_limitation='Old proxy heartbeats lack source identity, so armed=false is not treated as FCU DISARM')
    else:
        check('offboard_no_armed_reentry', reason='Fault event, aligned simulation clock and complete ULog state are required')

    if scenario in airborne_scenarios and first_land and relevant_disarm:
        landing_reason = relevant_disarm.get('reason_name') == 'auto_disarm_land'
        cleanup = any(e.get('kind') == 'explicit_cleanup_land' for e in events)
        check('land_actual_disarm', 'pass' if landing_reason and not cleanup else 'failed',
              'Physical airborne scenario reached armed AUTO.LAND and PX4 auto-disarmed by landing',
              land_sim_s=first_land['timestamp'] / 1e6,
              disarm_sim_s=relevant_disarm['disarm_us'] / 1e6,
              disarm_reason=relevant_disarm.get('reason'), disarm_reason_name=relevant_disarm.get('reason_name'),
              explicit_cleanup_land=cleanup)
        land_data = log.rows('vehicle_land_detected')
        transitions = [r for i, r in enumerate(land_data or []) if i > 0 and r.get('landed')
                       and not land_data[i - 1].get('landed') and first_land['timestamp'] <= r['timestamp'] <= relevant_disarm['disarm_us']]
        if transitions:
            delay = (relevant_disarm['disarm_us'] - transitions[-1]['timestamp']) / 1e6
            check('landing_disarm_within_3s', 'pass' if 0 <= delay <= 3. else 'failed',
                  'PX4 DISARM no later than three simulation seconds after land detector transition',
                  delay_sim_s=delay, landed_sim_s=transitions[-1]['timestamp'] / 1e6)
        else:
            check('landing_disarm_within_3s', reason='No logged landed false-to-true transition after LAND')
    else:
        check('land_actual_disarm', reason='Armed LAND, complete DISARM transition and embedded reason enum required')
        check('landing_disarm_within_3s', reason='Airborne LAND/DISARM and land detector datasets required')
    if scenario in ('kill', 'freeze', 'mavros_restart') and fault and clock_aligned and first_land:
        reaction = first_land['timestamp'] / 1e6 - fault['sim']
        loss_rows = [r for r in (flags or []) if r['timestamp'] / 1e6 >= fault['sim'] and r.get('offboard_control_signal_lost')]
        loss = loss_rows[0]['timestamp'] / 1e6 if loss_rows else None
        check('offboard_loss_reaction_within_1_5s', 'pass' if 0 <= reaction <= 1.5 else 'failed',
              'Injected stop/kill to actual armed AUTO.LAND, on validated simulation clock',
              injected_sim_s=fault['sim'], land_sim_s=first_land['timestamp'] / 1e6,
              reaction_sim_s=reaction, px4_loss_detected_sim_s=loss,
              loss_detection_to_land_sim_s=first_land['timestamp'] / 1e6 - loss if loss is not None else None)
    else:
        check('offboard_loss_reaction_within_1_5s', reason='Injected fault, validated simulation clock and armed LAND required')
    if not end_event and relevant_disarm and clock_aligned:
        disarm_sim = relevant_disarm['disarm_us'] / 1e6
        boundary_truth = next((r for r in truth if r['sim'] >= disarm_sim), None)
        if boundary_truth:
            end_event = {'kind': 'ulog_derived_disarm_boundary', 'sim': disarm_sim,
                         'wall': boundary_truth['wall']}
            result['derived_end_boundary'] = end_event
    boundary = respawn if scenario == 'mavros_restart' else resume if scenario == 'freeze' else None
    if scenario == 'freeze':
        window = freeze_setpoint_window(packets, fault, resume, stopped, recorder_complete,
                                        advertised, end_event, resume_before)
        old = window['old_recorded_resume_boundary']
        check('setpoints_after_old_recorded_resume_boundary',
              'failed' if old['forwarded_count'] else 'unknown',
              'Exact old count is diagnostic only and cannot establish a successful S3 zero-target result', **old)
        window_status, window_reason = window.pop('status'), window.pop('reason')
        check('setpoints_after_respawn_or_resume', window_status, window_reason, **window)
    elif boundary and end_event and recorder_complete and SP_TYPES <= advertised:
        sent_after = [r for r in packets if r.get('kind') == 'setpoint_forwarded'
                      and boundary['wall'] < r['wall'] <= end_event['wall']]
        after_grace = [r for r in sent_after if r['wall'] > boundary['wall'] + .3]
        check('setpoints_after_respawn_or_resume', 'pass' if not sent_after else 'failed',
              'All forwarded setpoints after the recorded boundary, with no excluded grace interval',
              count=len(sent_after), count_after_0_3s=len(after_grace),
              boundary_wall=boundary['wall'])
    else:
        check('setpoints_after_respawn_or_resume', reason='Recorded setpoint coverage and respawn/SIGCONT boundary required')

    held = [r for r in packets if r.get('kind') == 'held_arm_ack']
    released = [r for r in packets if r.get('kind') == 'released_arm_ack']
    if scenario == 'ack_cancel' and held and released:
        # Older recordings have release events without ids. At most one ACK is
        # pending; if the FIFO holds/releases counts agree their order is known.
        pairs = list(zip(held, released)) if len(held) == len(released) else []
        accepted_pairs = [(h, r) for h, r in pairs if h.get('result') == 0]
        delays = [r['wall'] - h['wall'] for h, r in accepted_pairs]
        ok = (bool(accepted_pairs) and all(abs(h.get('delay', 0.) - 4.) < .001 for h, _ in accepted_pairs)
              and all(d >= 3.9 for d in delays))
        check('ack_delay_four_seconds', 'pass' if ok else 'failed' if pairs else 'unknown',
              'Only ACCEPTED ARM ACK withholding counts; earlier REJECTED ACK is kept as separate evidence',
              accepted_wall_delays_s=delays, accepted_hold_count=len(accepted_pairs),
              held_count=len(held), released_count=len(released), results=[r.get('result') for r in held])
    else:
        check('ack_delay_four_seconds', reason='ack_cancel held/released ACK records required')
    land_reply = next((e for e in events if e.get('kind') == 'land_reply_received'), None)
    land_request = next((e for e in events if land_reply and e.get('kind') == 'land_request_sent'
                         and e.get('client_gid') == land_reply.get('client_gid')
                         and e.get('sequence_number') == land_reply.get('sequence_number')), None)
    introspection = next((e for e in events if e.get('kind') == 'land_introspection_enabled'), None)
    real_metadata = bool(land_reply and land_request and introspection
                         and land_reply.get('event_type') == 3 and land_request.get('event_type') == 0)
    steady_reply = bool(real_metadata
                        and number(land_reply.get('client_stamp_steady_wall'))
                        and number(land_request.get('client_stamp_steady_wall'))
                        and land_reply['client_stamp_steady_wall'] >= land_request['client_stamp_steady_wall']
                        and introspection.get('client_clock') == 'RCL_STEADY_TIME / Linux CLOCK_MONOTONIC'
                        and number(introspection.get('measured_max_clock_skew_wall_s'))
                        and introspection['measured_max_clock_skew_wall_s'] < .01)
    sim_reply = bool(real_metadata and number(land_reply.get('client_stamp_sim'))
                     and number(land_request.get('client_stamp_sim'))
                     and land_reply['client_stamp_sim'] >= land_request['client_stamp_sim']
                     and introspection.get('client_clock') == 'ROS simulation clock')
    real_reply = steady_reply or sim_reply
    check('land_reply_actual_client_event', 'pass' if real_reply else 'unknown',
          'Matching real ROS client REQUEST_SENT/RESPONSE_RECEIVED metadata, not navigate completion or observer wall time',
          request=land_request, reply=land_reply, introspection=introspection)
    if steady_reply:
        reply_wall = land_reply['client_stamp_steady_wall']
        disarm_sent = next((r for r in packets if r.get('kind') == 'packet'
                            and r.get('direction') == 'ros_to_px4' and r.get('command') == 400
                            and r.get('param1', 1.) <= .5 and abs(r.get('param2', 0.)) < .001
                            and (not cancel or r['wall'] >= cancel['wall'])), None)
        disarm_ack = next((r for r in packets if disarm_sent and r.get('kind') == 'packet'
                          and r.get('direction') == 'px4_to_ros' and r.get('command') == 400
                          and r.get('result') == 0 and r.get('source_system') == 1
                          and r.get('source_component') == 1 and r['wall'] >= disarm_sent['wall']), None)
        fcu_reports = [r for r in packets if r.get('kind') == 'heartbeat_forwarded'
                       and r.get('autopilot') == 12 and r.get('source_system') == 1
                       and r.get('source_component') == 1]
        disarmed = next((r for r in fcu_reports if disarm_ack and not r.get('armed')
                         and r['wall'] >= disarm_ack['wall']), None)
        confirmed_disarm = checks['cancel_external_nonforced_disarm']['status'] == 'pass'
        no_rearm = checks['no_additional_arm_after_cancel']['status'] == 'pass'
        bounded = bool(disarmed and disarmed['wall'] <= reply_wall + 2.)
        check('disarm_within_2s_of_land_reply',
              'pass' if bounded and confirmed_disarm and no_rearm and recorder_complete else 'unknown',
              'Actual steady-clock CLIENT RESPONSE_RECEIVED and source-identified DISARM report after accepted nonforced DISARM; a later report alone cannot prove a late actual DISARM',
              client_response_steady_wall=reply_wall,
              first_disarmed_heartbeat_wall=disarmed['wall'] if disarmed else None,
              report_minus_client_reply_wall_s=disarmed['wall'] - reply_wall if disarmed else None,
              actual_external_disarm_ulog_confirmed=confirmed_disarm, no_rearm_proved=no_rearm,
              disarm_command=disarm_sent, accepted_disarm_ack=disarm_ack,
              observer_callback_delay_wall_s=land_reply['wall'] - reply_wall,
              measured_instrumentation_clock_skew_wall_s=introspection['measured_max_clock_skew_wall_s'])
        check('disarm_within_2sim_s_of_land_reply', reason='Actual reply is measured with STEADY_TIME; event monitor_sim is approximate and is not reused as a client timestamp')
    elif sim_reply and clock_aligned and intervals:
        reply_sim = land_reply['client_stamp_sim']
        ended = [w for w in intervals if w['disarm_us'] is not None
                 and w['arm_us'] / 1e6 <= reply_sim]
        interval = ended[-1] if ended else None
        if interval:
            delta_sim = interval['disarm_us'] / 1e6 - reply_sim
            margin = proxy_skew if proxy_skew is not None else .01
            sim_status = 'pass' if delta_sim + margin <= 2. else 'failed' if delta_sim - margin > 2. else 'unknown'
            check('disarm_within_2sim_s_of_land_reply', sim_status,
                  'Actual PX4 ULog DISARM relative to SDK RESPONSE_RECEIVED on validated simulation clocks',
                  disarm_minus_reply_sim_s=delta_sim, measured_clock_skew_sim_s=margin,
                  disarmed_before_reply=delta_sim + margin <= 0., reply_sim_s=reply_sim,
                  disarm_sim_s=interval['disarm_us'] / 1e6)
            check('disarm_within_2s_of_land_reply', 'pass' if delta_sim + margin <= 0. else 'unknown',
                  'The wall-time deadline is proved when PX4 was already disarmed before the actual reply; positive simulation delay alone does not prove a wall-time bound',
                  disarm_minus_reply_sim_s=delta_sim, measured_clock_skew_sim_s=margin,
                  observer_wall_is_not_client_reply_wall=True)
        else:
            check('disarm_within_2sim_s_of_land_reply', reason='No complete actual ARM/DISARM interval for the real LAND reply')
            check('disarm_within_2s_of_land_reply', reason='No actual DISARM associated with the real LAND reply')
    elif real_reply:
        check('disarm_within_2sim_s_of_land_reply', reason='Validated PX4/Gazebo clock alignment and complete ARM/DISARM interval required')
        check('disarm_within_2s_of_land_reply', reason='Observer wall timestamp cannot establish the actual SDK response wall deadline')
    else:
        check('disarm_within_2sim_s_of_land_reply', reason='Matching actual LAND client service-event metadata required')
    legacy_reply = next((e for e in events if e.get('kind') == 'land_reply'), None)
    if not real_reply and legacy_reply and recorder_complete:
        fcu_heartbeats = [r for r in heartbeats if r.get('autopilot') == 12 and r.get('source_component') == 1]
        disarmed = next((r for r in fcu_heartbeats if r['wall'] >= legacy_reply['wall'] and not r.get('armed')), None)
        if disarmed:
            delta = disarmed['wall'] - legacy_reply['wall']
            check('disarm_within_2s_of_land_reply', 'pass' if delta <= 2. else 'failed',
                  'Independent disarmed heartbeat after explicit LAND service reply', wall_delay_s=delta)
        else:
            check('disarm_within_2s_of_land_reply', reason='No source-identified post-reply FCU disarmed heartbeat')
    elif not real_reply:
        check('disarm_within_2s_of_land_reply', reason='Actual land_reply_received or explicit legacy land_reply required; navigate_reply is not a LAND reply')

    if cancel:
        accepted_ack = next((r for r in packets if r.get('kind') == 'packet' and
                             r.get('direction') == 'px4_to_ros' and r.get('command') == 400
                             and r.get('result') == 0 and r['wall'] <= cancel['wall']), None)
        earlier = [r for r in forwarded if accepted_ack and r['wall'] <= accepted_ack['wall']]
        if earlier and number(gate.get('offset_ms')):
            offset = (cancel['wall'] - earlier[-1]['wall']) * 1000
            error = offset - gate['offset_ms']
            check('cancel_offset_observed', 'pass' if abs(error) <= 20. else 'failed',
                  'Actual SIGINT timing relative to the ARM that received ACCEPTED ACK',
                  requested_offset_ms=gate['offset_ms'], observed_offset_ms=offset, error_ms=error)
        elif scenario == 'cancel_before':
            check('cancel_offset_observed', reason='Cancellation before navigate has no accepted ARM boundary')
        else:
            check('cancel_offset_observed', reason='Accepted ARM ACK and recorded timing boundary required')
    else:
        check('cancel_offset_observed', reason='Not a cancellation scenario')

    # First packet of the controller stream, matched to the independent Gazebo
    # position. Origin must be supplied by verified frame metadata, never inferred.
    first = next((r for r in packets if r.get('kind') == 'packet' and r.get('direction') == 'ros_to_px4'
                  and r.get('mavpackettype') == 'SET_POSITION_TARGET_LOCAL_NED'), None)
    if first and truth and origin is not None and first.get('coordinate_frame') == 1 and not (first.get('type_mask', 0) & 7):
        positions = sorted(truth, key=lambda r: r['wall'])
        times = [r['wall'] for r in positions]
        i = bisect.bisect_left(times, first['wall'])
        if 0 < i < len(positions) and times[i] - times[i - 1] <= .25:
            fraction = (first['wall'] - times[i - 1]) / (times[i] - times[i - 1])
            actual = [positions[i - 1][key] + fraction * (positions[i][key] - positions[i - 1][key]) for key in ['x', 'y', 'z']]
            target = [first['y'] - origin[1], first['x'] - origin[0], origin[2] - first['z']]
            offset = math.dist(target, actual)
            check('s1_first_target_true_offset', 'pass' if offset < .05 else 'failed',
                  'Explicit NED/ENU origin and interpolated physical Gazebo position',
                  offset_m=offset, target_enu=target, actual_enu=actual, enu_origin_ned=origin,
                  first_packet_wall=first['wall'], truth_bracket_wall_s=times[i] - times[i - 1])
        else:
            check('s1_first_target_true_offset', reason='No close truth bracket around first setpoint packet')
    else:
        check('s1_first_target_true_offset', reason='Position packet, physical truth and explicit verified NED-to-world origin required')
    trajectory = log.rows('trajectory_setpoint') if log else None
    local = log.rows('vehicle_local_position') if log else None
    if trajectory and local:
        point = next((r for r in trajectory if all(r.get('position[%d]' % j) is not None for j in range(3))
                      and first_arm is not None and r['timestamp'] >= first_arm), None)
        previous = [r for r in local if point and r['timestamp'] <= point['timestamp']]
        if point and previous and point['timestamp'] - previous[-1]['timestamp'] <= 100000:
            current = previous[-1]
            offset = math.dist([point['position[%d]' % j] for j in range(3)], [current[k] for k in ['x', 'y', 'z']])
            check('s1_first_armed_trajectory_estimated_offset', 'pass' if offset < .05 else 'failed',
                  'ULog target versus estimated position in the same NED frame; not a physical-position proof',
                  offset_m=offset, at_us=point['timestamp'])
        else:
            check('s1_first_armed_trajectory_estimated_offset', reason='Fresh NED samples near first ARM required')
    else:
        check('s1_first_armed_trajectory_estimated_offset', reason='trajectory_setpoint and vehicle_local_position required')

    result['counts'] = {name: sum(c['status'] == name for c in checks.values()) for name in ['pass', 'failed', 'unknown']}
    result['status'] = 'failed' if result['counts']['failed'] else 'unknown' if result['counts']['unknown'] else 'pass'
    common = ['px4_version', 'candidate4030', 'real_parameters_before_arm', 'simulation_only_parameters']
    core = []
    gate_name = None
    if scenario == 'land':
        core = ['physical_takeoff', 'rc_valid_while_armed', 'land_actual_disarm', 'landing_disarm_within_3s']
        gate_name = 'normal_flight_and_land'
    elif scenario in ('kill', 'freeze', 'mavros_restart'):
        core = ['physical_takeoff', 'rc_valid_while_armed', 'land_actual_disarm',
                'landing_disarm_within_3s', 'offboard_no_armed_reentry', 'offboard_loss_reaction_within_1_5s']
        if scenario in ('freeze', 'mavros_restart'):
            core += ['setpoints_after_respawn_or_resume']
        gate_name = {'kill': 'S2', 'freeze': 'S3', 'mavros_restart': 'S4'}[scenario]
    elif scenario == 'cancel_before':
        core = ['cancel_before_no_arm', 'no_additional_arm_after_cancel', 'cancel_true_rise_below_5cm']
        gate_name = 'S6'
    elif scenario in ('cancel', 'ack_cancel'):
        core = ['rc_valid_while_armed', 'cancel_external_nonforced_disarm',
                'no_additional_arm_after_cancel', 'cancel_true_rise_below_5cm', 'cancel_offset_observed']
        if scenario == 'ack_cancel':
            core += ['ack_delay_four_seconds']
        gate_name = 'S7_core' if scenario == 'ack_cancel' else 'after_arm_cancel_core'
    if core:
        required = common + core
        statuses = [checks[name]['status'] for name in required]
        acceptance = 'failed' if 'failed' in statuses else 'unknown' if 'unknown' in statuses else 'pass'
        result['independent_acceptance'] = {
            'gate': gate_name, 'status': acceptance, 'required_checks': required,
            'raw_runner_result': gate.get('pass'),
            'raw_runner_result_was_not_modified': True,
            'scope': 'One recorded scenario, not a complete deployment authorization',
            'full_cancel_land_reply_bound_status': checks['disarm_within_2s_of_land_reply']['status'] if scenario in ('cancel', 'ack_cancel') else None,
            'other_checks_unknown': [name for name, item in checks.items() if item['status'] == 'unknown']}
        if scenario in ('cancel', 'ack_cancel'):
            full_required = required + ['land_reply_actual_client_event', 'disarm_within_2s_of_land_reply']
            full_statuses = [checks[name]['status'] for name in full_required]
            result['full_cancel_acceptance'] = {
                'gate': 'S7' if scenario == 'ack_cancel' else 'after_arm_cancel',
                'status': 'failed' if 'failed' in full_statuses else 'unknown' if 'unknown' in full_statuses else 'pass',
                'required_checks': full_required, 'raw_runner_result': gate.get('pass'),
                'scope': 'Full recorded cancellation scenario including the actual LAND response wall deadline'}
    else:
        result['independent_acceptance'] = {'status': 'unknown', 'reason': 'No complete required-check table for this scenario'}
    for key in ('independent_acceptance', 'full_cancel_acceptance'):
        if key in result:
            acceptance = result[key]
            acceptance['scope'] = acceptance.get('scope', 'One recorded scenario')+'; '+vision['scope']
            acceptance['vision_policy'] = vision
            acceptance['strict_original_vision_acceptance'] = vision['strict_original_vision_acceptance']
    result['deployment_gate'] = 'not_established_by_this_report_alone'
    result['enum_sources'] = [
        'Ulog metadata_events embedded arm_disarm_reason_t enum',
        'https://raw.githubusercontent.com/PX4/PX4-Autopilot/' + PX4_COMMIT + '/src/modules/commander/Commander.cpp',
        PX4_POSITION_SOURCE]
    return clean(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--out', type=Path, help='Write JSON here; otherwise stdout only')
    parser.add_argument('--enu-origin-ned', nargs=3, type=float, metavar=('N', 'E', 'D'))
    args = parser.parse_args()
    reports = [verify(run, args.enu_origin_ned) for run in args.runs]
    obj = reports[0] if len(reports) == 1 else reports
    output = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    if args.out:
        args.out.write_text(output)
        print(json.dumps({'output': str(args.out), 'runs': len(reports),
                          'statuses': [r['status'] for r in reports],
                          'gates': [r['independent_acceptance'].get('gate') for r in reports],
                          'gate_statuses': [r['independent_acceptance']['status'] for r in reports],
                          'vision_policies': [r['vision_policy']['classification'] for r in reports],
                          'strict_original_vision_acceptance': [r['strict_original_vision_acceptance'] for r in reports],
                          'vision_scope': [r['vision_policy']['scope'] for r in reports]}))
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
