#!/usr/bin/env python3
"""A6 test (T32): apply order of the INDOOR_ARUCO profile on the airframe 4061 baseline.
Model: the candidate's KnownCapsModel (sitl_profile_closure_candidate.py) = PX4's committed clamps
(MulticopterPositionControl.cpp:215-280: CRUISE/VEL_MANUAL <= XY_VEL_MAX, MAN_BACK/SIDE <= VEL_MANUAL,
Z_V_AUTO_UP/DN <= Z_VEL_MAX_UP/DN). Baseline: the real 4061 values read by the failed run INT_flight_C8b_kill_01
(flight_result.json independent_before), read-only.
Checks: (1) the A6 supervisor applies in restore_order (text check); (2) the old dict order reproduces the run failure
(MPC_XY_CRUISE ends at 0.25, not 0.3); (3) the A6 order reaches every profile value; (4) the transaction restore order
(parents first) returns the full 18-name baseline from the applied state; (5) inside the profile only the pair
MPC_XY_VEL_MAX -> MPC_XY_CRUISE has both ends.
Run: python3 -B -I a6_apply_order.py"""
import json
import sys
from pathlib import Path

D = Path('/work/c8_judge_r2j_a13_20261111')
sys.path.insert(0, str(D / 'candidate/parameters'))
from sitl_profile_closure_candidate import (CLAMP_EDGES, KnownCapsModel, closure_names,  # noqa: E402
                                            profile_values, restore_order)

profile = profile_values()
names = closure_names(profile)
run = json.loads(Path('/work/sim/runs/INT_flight_C8b_kill_01/flight_result.json').read_text())
baseline = {k: float(v['value']) for k, v in run['independent_before'].items()}
assert set(baseline) == set(names), sorted(set(baseline) ^ set(names))
assert baseline['MPC_XY_VEL_MAX'] == 0.25 and abs(baseline['MPC_XY_CRUISE'] - 0.2) < 1e-6

src = (D / 'executor/supervisor.py').read_text()
assert 'for name in restore_order(tuple(profile)):' in src and 'value=profile[name]' in src
assert 'for name,value in profile_values().items():\n        req=SetParam' not in src

old = KnownCapsModel(baseline)
for n, v in profile.items():
    old.write(n, v)
assert abs(old.values['MPC_XY_CRUISE'] - 0.25) < 1e-6, old.values['MPC_XY_CRUISE']

order = restore_order(tuple(profile))
new = KnownCapsModel(baseline)
for n in order:
    new.write(n, profile[n])
bad = {n: (new.values[n], profile[n]) for n in profile if abs(new.values[n] - profile[n]) > 1e-6}
assert not bad, bad
side = {n: (baseline[n], new.values[n]) for n in names if n not in profile and abs(new.values[n] - baseline[n]) > 1e-6}

for n in restore_order(names):
    new.write(n, baseline[n])
diff = {n: (new.values[n], baseline[n]) for n in names if abs(new.values[n] - baseline[n]) > 1e-6}
assert not diff, diff

pairs = [(p, c) for p, c in CLAMP_EDGES if p in profile and c in profile]
assert pairs == [('MPC_XY_VEL_MAX', 'MPC_XY_CRUISE')], pairs
assert order.index('MPC_XY_VEL_MAX') < order.index('MPC_XY_CRUISE')
print('ok; apply order:', list(order))
print('non-profile closure values changed while applied (restored after):', side)
