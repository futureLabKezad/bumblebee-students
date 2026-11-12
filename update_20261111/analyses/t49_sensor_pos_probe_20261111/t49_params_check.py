#!/usr/bin/env python3
"""t49_params_check.py (Claude 11.11, review F1). READ ONLY. Did the variant's params really reach PX4? Reads RUN/params_sitl.json
(values read from the running SITL by the launcher). Exit 0 = all expected values within 1e-4, 1 = mismatch, 2 = file/param missing.
Usage: python3 -I t49_params_check.py RUN A|B"""
import json, os, sys
EXP = {'A': {'EKF2_RNG_POS_Z': 0.05, 'EKF2_OF_POS_Z': 0.05, 'EKF2_MIN_RNG': 0.23, 'EKF2_IMU_POS_Z': 0.0},
       'B': {'EKF2_RNG_POS_Z': 0.10, 'EKF2_OF_POS_Z': 0.10, 'EKF2_MIN_RNG': 0.28, 'EKF2_IMU_POS_Z': 0.0}}
run, v = sys.argv[1], sys.argv[2]
try:
    p = json.load(open(os.path.join(run, 'params_sitl.json')))['params']
except Exception as e:
    print('params: ERROR %s' % e); sys.exit(2)
got, bad = {}, []
for k, x in EXP[v].items():
    if k not in p:
        print('params: ERROR %s missing' % k); sys.exit(2)
    got[k] = round(float(p[k]['value']), 4)
    if abs(got[k] - x) > 1e-4:
        bad.append(k)
print('params %s: %s%s' % (v, got, ' MISMATCH %s' % bad if bad else ' ok'))
sys.exit(1 if bad else 0)
