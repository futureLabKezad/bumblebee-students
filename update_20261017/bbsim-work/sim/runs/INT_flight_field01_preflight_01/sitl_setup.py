#!/usr/bin/env python3
"""SITL RC/GCS emulator plus read-only, complete flight-profile readback.

Existing simulator setup PARAM_SET operations are retained. Profile observation
adds PARAM_REQUEST_READ only; it never restores or otherwise writes the profile.
"""
import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import time

PROFILE_SOURCE = Path('/work/ws_package1b/src/bumblebee/examples/flight_profile.py')
PROFILE_COUNT = 14
PROFILE_WINDOW = 30.0
MATCH_TOLERANCE = 0.001
CHANNELS = [1499, 1500, 1000, 1497, 1000, 1000, 1500, 1000] + [1500]*8


def profile_manifest(path=PROFILE_SOURCE):
    source = Path(path).read_bytes()
    values = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'INDOOR_ARUCO'
                      for target in node.targets)]
    if len(values) != 1:
        raise ValueError('Expected one literal INDOOR_ARUCO profile')
    profile = ast.literal_eval(values[0])
    if not isinstance(profile, dict) or len(profile) != PROFILE_COUNT:
        raise ValueError('INDOOR_ARUCO must contain exactly 14 parameters')
    for name, value in profile.items():
        if not isinstance(name, str) or not 1 <= len(name) <= 16:
            raise ValueError('Invalid profile parameter name')
        if type(value) is not float or not math.isfinite(value):
            raise ValueError('Expected finite float profile value: '+name)
    return dict(source=str(path), source_sha256=hashlib.sha256(source).hexdigest(),
                names=list(profile), count=len(profile), profile_values=profile,
                observation_only=True, expected_mav_param_type=9,
                readback_window_wall_s=PROFILE_WINDOW)


def parameter_name(value):
    if isinstance(value, bytes):
        value = value.split(b'\0', 1)[0].decode('ascii')
    if not isinstance(value, str):
        raise ValueError('Invalid PARAM_VALUE name representation')
    return value.split('\0', 1)[0]


def decode_parameter(message, encoding):
    typ = int(message.param_type)
    raw = float(message.param_value)
    if typ == 6:
        if encoding == 'cast':
            if not math.isfinite(raw) or not raw.is_integer() or not -(2**31) <= raw < 2**31:
                raise ValueError('Invalid cast INT32 PARAM_VALUE')
            return int(raw)
        if encoding != 'bytewise':
            raise ValueError('INT32 encoding is not established')
        # Valid INT32 bits can be NaN as wire floats; validate decoded values.
        return struct.unpack('<i', struct.pack('<f', raw))[0]
    if typ != 9 or not math.isfinite(raw):
        raise ValueError('Unsupported or non-finite PARAM_VALUE')
    return raw


def parameter_matches(message, key, expected_type, system=1, component=1):
    return (message.get_type() == 'PARAM_VALUE'
            and message.get_srcSystem() == system and message.get_srcComponent() == component
            and parameter_name(message.param_id) == key
            and (expected_type is None or int(message.param_type) == expected_type))


def matches_baseline(sample, baseline):
    return (sample['type'] == baseline['type'] and math.isfinite(sample['value'])
            and math.isfinite(baseline['value'])
            and abs(sample['value']-baseline['value']) < MATCH_TOLERANCE)


def save_report(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
    temporary.replace(path)


class TelemetryPump:
    """One receive path; waiting for parameters never blocks RC/heartbeat work."""
    def __init__(self, connection, system, mavutil, report, out, throttle,
                 clock=time.monotonic, sleep=time.sleep):
        self.m = connection
        self.system = system
        self.mavutil = mavutil
        self.report = report
        self.out = out
        self.throttle = throttle
        self.clock = clock
        self.sleep = sleep
        self.encoding = None
        self.rc_enabled = False
        self.last_hb = self.last_rc = None
        self.armed_seen = False
        self.disarm_wall = None
        self.rearmed_after_disarm = False
        self.current_armed = None
        self.request_index = 0
        self.last_pump_idle = False
        report['keepalive'] = dict(heartbeat_send_count=0, rc_send_count=0,
            max_heartbeat_gap_wall_s=0.0, max_rc_gap_wall_s=0.0)
        report['parameter_read_protocol'] = dict(rejected_count=0, rejected_last=[],
            correlation='source/component/name/type and receipt after local request; PARAM protocol has no nonce')

    def keepalive(self):
        now = self.clock()
        stats = self.report['keepalive']
        if self.last_hb is None or now-self.last_hb >= 1.0:
            self.m.mav.heartbeat_send(self.mavutil.mavlink.MAV_TYPE_GCS,
                self.mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
                self.mavutil.mavlink.MAV_STATE_ACTIVE)
            if self.last_hb is not None:
                stats['max_heartbeat_gap_wall_s'] = max(stats['max_heartbeat_gap_wall_s'], now-self.last_hb)
            self.last_hb = now
            stats['heartbeat_send_count'] += 1
        if self.rc_enabled and (self.last_rc is None or now-self.last_rc >= 0.05):
            self.m.mav.rc_channels_override_send(self.system, 1, *self.report['channels'])
            if self.last_rc is not None:
                stats['max_rc_gap_wall_s'] = max(stats['max_rc_gap_wall_s'], now-self.last_rc)
            self.last_rc = now
            stats['rc_send_count'] += 1

    def observe(self, message):
        now = self.clock()
        kind = message.get_type()
        if message.get_srcSystem() != self.system or message.get_srcComponent() != 1:
            return
        if kind == 'HEARTBEAT' and message.autopilot == self.mavutil.mavlink.MAV_AUTOPILOT_PX4:
            armed = bool(message.base_mode & self.mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            self.current_armed = armed
            self.report['states'].append(dict(wall=now, armed=armed,
                mode=self.mavutil.mode_string_v10(message), source_system=self.system, source_component=1))
            if armed:
                self.report['channels'][2] = self.throttle
                self.armed_seen = True
                if self.disarm_wall is not None:
                    self.rearmed_after_disarm = True
                    self.report['profile_restore_all_confirmed'] = False
                    self.report['profile_restore_status'] = 'rearmed'
                    self.report['profile_restore_invalidated_wall'] = now
            elif self.armed_seen and self.disarm_wall is None:
                self.disarm_wall = now
                self.report['actual_px4_arm_to_disarm_wall'] = now
        elif kind == 'RC_CHANNELS':
            self.report['pass_rc'] = message.chancount >= 16
        elif kind == 'SYS_STATUS':
            bit = self.mavutil.mavlink.MAV_SYS_STATUS_SENSOR_RC_RECEIVER
            self.report['rc_receiver_healthy'] = bool(message.onboard_control_sensors_present & bit
                and message.onboard_control_sensors_health & bit)
            self.report['prearm_ok'] = bool(message.onboard_control_sensors_health & 0x10000000)

    def pump(self):
        self.keepalive()
        messages = []
        self.last_pump_idle = False
        for index in range(64):
            message = self.m.recv_match(blocking=False)
            if message is None:
                self.last_pump_idle = True
                break
            if index % 16 == 0:
                self.keepalive()
            self.observe(message)
            if message.get_type() == 'PARAM_VALUE':
                messages.append(message)
        return messages

    def read_sample(self, key, expected_type=None, timeout=10.0, deadline=None):
        # Drain queued responses before this read. PARAM_VALUE has no nonce;
        # do not claim stronger network correlation than the protocol provides.
        drain_deadline = self.clock()+0.2
        if deadline is not None:
            drain_deadline = min(drain_deadline, deadline)
        while True:
            self.pump()
            if self.last_pump_idle:
                break
            if self.clock() >= drain_deadline:
                raise TimeoutError('Parameter receive queue did not drain: '+key)
            self.sleep(0.001)
        request_wall = self.clock()
        stop = request_wall+timeout if deadline is None else min(deadline, request_wall+timeout)
        if request_wall >= stop:
            raise TimeoutError('Parameter read deadline: '+key)
        self.request_index += 1
        index = self.request_index
        self.m.mav.param_request_read_send(self.system, 1, key.encode(), -1)
        while self.clock() < stop:
            if (self.out/'rc_stop').exists():
                raise InterruptedError('Observer stop requested')
            for message in self.pump():
                try:
                    if not parameter_matches(message, key, expected_type, self.system, 1):
                        continue
                    if key == 'SIM_GZ_EN' and self.encoding is None:
                        if int(message.param_type) != 6:
                            raise ValueError('SIM_GZ_EN must be INT32')
                        self.encoding = 'cast' if message.param_value == 1 else 'bytewise'
                    value = decode_parameter(message, self.encoding)
                    return dict(value=value, type=int(message.param_type), request_wall=request_wall,
                        wall=self.clock(), local_request_index=index, source_system=self.system,
                        source_component=1, wire_float_bits=struct.pack('<f', float(message.param_value)).hex())
                except (ValueError, OverflowError, struct.error) as error:
                    protocol = self.report['parameter_read_protocol']
                    protocol['rejected_count'] += 1
                    protocol['rejected_last'].append(dict(wall=self.clock(), key=key, reason=str(error)))
                    del protocol['rejected_last'][:-32]
            self.sleep(min(0.01, max(0.0, stop-self.clock())))
        raise TimeoutError('No parameter '+key)

    def read(self, key, expected_type=None):
        sample = self.read_sample(key, expected_type=expected_type)
        return sample['value'], sample['type']


def capture_baseline(pump, report, manifest):
    start = pump.clock()
    deadline = start+PROFILE_WINDOW
    baseline = {}
    report.update(profile_manifest=manifest, profile_baseline=baseline,
        profile_baseline_started_wall=start, profile_baseline_deadline_wall=deadline,
        profile_baseline_all_confirmed=False, profile_restore_samples=[],
        profile_restore_confirmed=False, profile_restore_all_confirmed=False,
        profile_restore_parameters={}, profile_restore_status='awaiting_actual_arm_disarm')
    while len(baseline) < manifest['count'] and pump.clock() < deadline:
        for name in manifest['names']:
            if name in baseline or pump.clock() >= deadline:
                continue
            try:
                baseline[name] = pump.read_sample(name, expected_type=9, timeout=0.5, deadline=deadline)
            except TimeoutError:
                pass
            if pump.current_armed or pump.armed_seen:
                raise RuntimeError('PX4 armed before profile baseline/rc_ready')
    report['profile_baseline_completed_wall'] = pump.clock()
    report['profile_baseline_all_confirmed'] = len(baseline) == manifest['count']
    if not report['profile_baseline_all_confirmed']:
        raise RuntimeError('Incomplete 14-parameter baseline before rc_ready')
    report['profile_baseline_MPC_XY_VEL_MAX'] = baseline['MPC_XY_VEL_MAX']['value']
    report['profile_restore_parameters'] = {name:dict(baseline=baseline[name], confirmed=False,
        attempts=0, samples=[]) for name in manifest['names']}


def collect_restoration(pump, report):
    """Read only after a source PX4 ARM->DISARM; hard total 30 wall seconds."""
    start = pump.clock()
    if (pump.disarm_wall is None or not pump.armed_seen or pump.current_armed is not False
            or start-pump.disarm_wall < 1.0):
        raise RuntimeError('Readback requires actual PX4 ARM->DISARM plus one wall second')
    deadline = pump.disarm_wall+1.0+PROFILE_WINDOW
    report.update(profile_restore_started_wall=start, profile_restore_deadline_wall=deadline,
                  profile_restore_status='reading', profile_restore_all_confirmed=False)
    while pump.clock() < deadline and not pump.rearmed_after_disarm:
        complete_sweep = True
        for name in report['profile_manifest']['names']:
            item = report['profile_restore_parameters'][name]
            item['confirmed'] = False
            if pump.clock() >= deadline or pump.rearmed_after_disarm:
                complete_sweep = False
                break
            item['attempts'] += 1
            try:
                sample = pump.read_sample(name, expected_type=item['baseline']['type'],
                                          timeout=0.5, deadline=deadline)
            except TimeoutError as error:
                item['last_error'] = str(error)
                complete_sweep = False
                continue
            sample['confirmed'] = matches_baseline(sample, item['baseline'])
            item['samples'].append(sample)
            item['last_sample'] = sample
            item['confirmed'] = sample['confirmed']
            item['confirmed_wall'] = sample['wall'] if sample['confirmed'] else None
            if name == 'MPC_XY_VEL_MAX':
                # Preserve legacy XY-only fields and their meaning.
                report['profile_restore_samples'].append(dict(wall=sample['wall'], value=sample['value']))
                report['profile_restore_confirmed'] = sample['confirmed']
        if (complete_sweep and all(item['confirmed'] for item in report['profile_restore_parameters'].values())
                and pump.current_armed is False and not pump.rearmed_after_disarm):
            report['profile_restore_all_confirmed'] = True
            report['profile_restore_status'] = 'all_14_confirmed'
            break
        save_report(pump.out/'rc_observer.json', report)
        pump.sleep(min(0.05, max(0.0, deadline-pump.clock())))
    report['profile_restore_completed_wall'] = pump.clock()
    if not report['profile_restore_all_confirmed']:
        report['profile_restore_status'] = 'rearmed' if pump.rearmed_after_disarm else 'deadline_expired'
    save_report(pump.out/'rc_observer.json', report)


def main():
    os.environ['MAVLINK20'] = '1'
    from pymavlink import mavutil
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--obl', type=int, choices=[0, 4], required=True)
    parser.add_argument('--throttle', type=int, choices=[1000, 1499], default=1499)
    parser.add_argument('--real-flight-params')
    parser.add_argument('--guard',type=Path,required=True)
    parser.add_argument('--rc-expected',type=Path,required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    assert out.is_relative_to(Path('/work/sim/runs'))
    assert not any(Path(name).exists() for name in ('/etc/bumblebee_version', '/etc/bumblebee', '/dev/px4'))
    connection = mavutil.mavlink_connection('udpin:127.0.0.1:14550', source_system=255, source_component=190)
    report = dict(parameters={}, channels=list(CHANNELS), states=[], pass_rc=False,
                  rc_receiver_healthy=False, hover_throttle=args.throttle)
    try:
        hb = connection.wait_heartbeat(timeout=20)
        assert hb and hb.autopilot == mavutil.mavlink.MAV_AUTOPILOT_PX4
        system = connection.target_system
        assert system == 1 and hb.get_srcSystem() == 1 and hb.get_srcComponent() == 1
        assert not (hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED), 'Must start disarmed'
        pump = TelemetryPump(connection, system, mavutil, report, out, args.throttle)
        pump.observe(hb)
        assert pump.read('SIM_GZ_EN', expected_type=6)[0] == 1, 'Not Gazebo SITL'
        assert pump.read('SYS_AUTOSTART', expected_type=6)[0] == 4030, 'Wrong airframe'
        params = json.loads(Path('/work/sim/ros_stack/rc_real_params.json').read_text())['parameters']
        if args.real_flight_params:
            extra = json.loads(Path(args.real_flight_params).read_text())
            params.update(extra['parameters'])
            params.update(extra['sim_only'])
        params['COM_OBL_RC_ACT'] = dict(value=args.obl, type=6)
        # Existing SITL setup writes only. No profile-baseline or restore writes.
        for key, item in params.items():
            old, typ = pump.read(key, expected_type=item['type'])
            target = item['value']
            assert typ == item['type'], key
            report['parameters'][key] = dict(before=old, after=target, type=typ)
            if old != target:
                value = (struct.unpack('<f', struct.pack('<i', int(target)))[0]
                         if typ == 6 and pump.encoding == 'bytewise' else float(target))
                connection.mav.param_set_send(system, 1, key.encode(), value, typ)
                actual, actual_type = pump.read(key, expected_type=typ)
                assert actual_type == typ and abs(actual-target) < MATCH_TOLERANCE, (key, actual, target)
        expected=json.loads(args.rc_expected.read_text())
        report['rc_audit_sweeps']=[]
        for sweep in range(2):
            samples={}
            for name,value in expected.items():
                sample=pump.read_sample(name,expected_type=report['parameters'][name]['type'])
                assert sample['value']==value,(name,sample['value'],value)
                samples[name]=sample
                report['parameters'][name].update(after=sample['value'],source=[sample['source_system'],sample['source_component']],wire_type=sample['type'])
            report['rc_audit_sweeps'].append(samples)
        # This process exits before the guarded route is opened. No RC/ARM/MODE.
        report['setup_only'] = True
        report['rc_enabled'] = False
        report['completed_wall'] = time.monotonic()
        save_report(out/'rc_ready.json', report)
        contract={'parameters':expected,'all_rc_related_parameters_audited':True,'independently_verified':True,
            'evidence_sha256':hashlib.sha256((out/'rc_ready.json').read_bytes()).hexdigest(),'ready_path':str(out/'rc_ready.json')}
        save_report(args.guard/'rc_contract.json',contract)
    except InterruptedError:
        report['observer_stopped_during_read'] = True
    except BaseException as error:
        report['observer_error'] = dict(type=type(error).__name__, message=str(error), wall=time.monotonic())
        raise
    finally:
        save_report(out/'rc_observer.json', report)
        connection.close()


if __name__ == '__main__':
    main()
