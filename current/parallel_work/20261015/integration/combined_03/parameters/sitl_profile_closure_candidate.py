#!/usr/bin/env python3
"""HOST-ONLY candidate policy/caps model. No ROS/MAVLink imports or live writes.

Not a launchable VPE replacement. Rules model only the six clamp edges root
verified in pinned PX4 MulticopterPositionControl.cpp lines 215-280. They do not
model the complete firmware, caches, timing or external parameter ownership.
"""
import ast
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().with_name('flight_profile.py')
PROFILE_SHA256 = 'ce5263e73a61162984272e4a2a3ea8cdb2eabc90c46075d7badaa4cc9b5a56ae'
# Parent must be restored before child. MPC_XY_CRUISE is already in profile14.
CLAMP_EDGES = (
    ('MPC_XY_VEL_MAX', 'MPC_XY_CRUISE'),
    ('MPC_XY_VEL_MAX', 'MPC_VEL_MANUAL'),
    ('MPC_VEL_MANUAL', 'MPC_VEL_MAN_BACK'),
    ('MPC_VEL_MANUAL', 'MPC_VEL_MAN_SIDE'),
    ('MPC_Z_VEL_MAX_UP', 'MPC_Z_V_AUTO_UP'),
    ('MPC_Z_VEL_MAX_DN', 'MPC_Z_V_AUTO_DN'),
)


def profile_values():
    source = PROFILE_PATH.read_bytes()
    if hashlib.sha256(source).hexdigest() != PROFILE_SHA256:
        raise ValueError('Pinned profile14 changed')
    assignments = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == 'INDOOR_ARUCO' for target in node.targets)]
    if len(assignments) != 1:
        raise ValueError('Expected one literal profile')
    profile = ast.literal_eval(assignments[0].value)
    if len(profile) != 14 or any(type(value) is not float or not math.isfinite(value)
                               for value in profile.values()):
        raise ValueError('Expected 14 finite profile floats')
    return profile


def closure_names(names):
    result = set(names)
    while True:
        expanded = result | {child for parent, child in CLAMP_EDGES if parent in result}
        if expanded == result:
            return tuple(sorted(result))
        result = expanded


def restore_order(names):
    pending = set(names)
    result = []
    while pending:
        ready = sorted(name for name in pending if not any(
            child == name and parent in pending for parent, child in CLAMP_EDGES))
        if not ready:
            raise ValueError('Cyclic restore dependency')
        for name in ready:
            pending.remove(name)
            result.append(name)
    return tuple(result)


@dataclass(frozen=True)
class Sample:
    value: float
    mav_param_type: int = 9  # REAL32. Not ROS ParameterType=3 or SetParam ptype=1.


def validate_samples(samples, names):
    if set(samples) != set(names):
        raise ValueError('Baseline is missing or contains unknown closure names')
    values = {}
    for name in names:
        sample = samples[name]
        if (not isinstance(sample, Sample) or sample.mav_param_type != 9
                or type(sample.value) is not float or not math.isfinite(sample.value)):
            raise ValueError('Unknown, non-finite or wrong-type baseline: '+name)
        values[name] = sample.value
    return values


def validate_constraints(values):
    for parent, child in CLAMP_EDGES:
        if parent in values and child in values and values[child] > values[parent]:
            raise ValueError('Baseline violates known cap: '+parent+' -> '+child)
    return values


def validate_baseline(samples, names):
    return validate_constraints(validate_samples(samples, names))


def validate_managed_request(name, value, ttl_sec=0.0, persistent=False):
    """Proposed initial opt-in scope; not installed in the original gate."""
    profile = profile_values()
    if (name not in profile or type(value) is not float or not math.isfinite(value)
            or value != profile[name]):
        raise ValueError('Outside the single approved profile transaction')
    if not math.isfinite(ttl_sec) or ttl_sec != 0 or persistent is not False:
        raise ValueError('TTL/persistent semantics are outside this bounded candidate')


class KnownCapsModel:
    """Immediate fixed-point model of these clamp rules only, never an FCU."""
    def __init__(self, values):
        self.values = dict(values)
        self.writes = []
        self.fail_write = None
        self.fail_read = None

    def write(self, name, value):
        if name == self.fail_write:
            return False
        self.writes.append((name, value))
        self.values[name] = float(value)
        for _ in range(len(CLAMP_EDGES)+1):
            previous = dict(self.values)
            for parent, child in CLAMP_EDGES:
                if parent in self.values and child in self.values and self.values[child] > self.values[parent]:
                    self.values[child] = self.values[parent]
            if previous == self.values:
                return True
        raise AssertionError('Known caps did not reach fixed point')

    def read(self, name):
        if name == self.fail_read:
            raise RuntimeError('Unknown readback')
        return Sample(self.values[name])


def legacy_apply_and_restore(model, profile, order='sorted'):
    journal = {}
    for name, value in profile.items():
        current = model.read(name).value
        if current != value:
            journal[name] = Sample(current)
            model.write(name, value)
    sequence = sorted(journal) if order == 'sorted' else restore_order(journal)
    for name in sequence:
        model.write(name, journal[name].value)
    return journal


def model_restore_closure(model, baseline, names):
    """Pure proof: retain full journal on any write/readback failure."""
    values = validate_baseline(baseline, names)  # No write on unknown baseline.
    journal = dict(baseline)  # Includes unchanged implicit dependents.
    for name in restore_order(names):
        if not model.write(name, values[name]):
            return dict(status='failed_write', success=False, journal=journal, name=name)
    try:
        readback = {name: model.read(name) for name in names}
        actual = validate_baseline(readback, names)
    except (RuntimeError, ValueError) as error:
        return dict(status='unknown_readback', success=False, journal=journal, error=str(error))
    changed = {name: dict(expected=values[name], actual=actual[name]) for name in names
               if abs(values[name]-actual[name]) >= 0.001}
    if changed:
        return dict(status='mismatch', success=False, journal=journal, changed=changed)
    return dict(status='model_all_19_restored', success=True, journal={}, readback=actual)


def illustrative_baseline():
    """Consistent synthetic fixture. It is not a snapshot of the real drone."""
    values = {name: value+0.2 for name, value in profile_values().items()}
    values.update(MPC_XY_CRUISE=5.0, MPC_XY_VEL_MAX=12.0,
        MPC_VEL_MANUAL=10.0, MPC_VEL_MAN_BACK=7.0, MPC_VEL_MAN_SIDE=6.0,
        MPC_Z_VEL_MAX_UP=3.0, MPC_Z_VEL_MAX_DN=2.25,
        MPC_Z_V_AUTO_UP=2.5, MPC_Z_V_AUTO_DN=1.5)
    return {name: Sample(float(value)) for name, value in values.items()}
