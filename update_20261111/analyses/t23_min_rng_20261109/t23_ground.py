#!/usr/bin/env python3
"""T23: what the EKF gets from the range finder on the ground and at the landed 1->0 transition.
Read-only. Run: python3 -I -B t23_ground.py RUN_DIR"""
import glob
import json
import os
import sys

import numpy as np
from pyulog import ULog

run = sys.argv[1]
ulg = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')))[-1]
pp = json.load(open(os.path.join(run, 'params_sitl.json')))['params']
for k in ('EKF2_MIN_RNG', 'EKF2_HGT_REF', 'EKF2_RNG_CTRL', 'EKF2_EV_CTRL', 'EKF2_BARO_CTRL', 'EKF2_RNG_POS_Z',
          'EKF2_IMU_POS_Z', 'EKF2_RNG_QLTY_T', 'EKF2_RNG_A_HMAX', 'EKF2_RNG_FOG', 'EKF2_TERR_NOISE', 'EKF2_RNG_NOISE'):
    print(k, pp.get(k, {}).get('value'))
u = ULog(ulg)
T = {}
for d in u.data_list:
    T.setdefault(d.name, d)
t0 = u.start_timestamp


def g(name, field):
    d = T.get(name)
    if d is None or field not in d.data:
        return None, None
    return (d.data['timestamp'] - t0) / 1e6, d.data[field]


lt, landed = g('vehicle_land_detected', 'landed')
at, arm = g('vehicle_status', 'arming_state')
t_arm = at[np.argmax(arm == 2)]
i = np.where((lt > t_arm) & (landed == 0))[0][0]
t_un = lt[i]
print('ulog', ulg)
print('armed at %.2f  landed->0 at %.2f' % (t_arm, t_un))

ds_t, ds = g('distance_sensor', 'current_distance')
_, dmin = g('distance_sensor', 'min_distance')
_, dq = g('distance_sensor', 'signal_quality')
print('distance_sensor min_distance', np.unique(dmin)[:5], 'quality', np.unique(dq)[:5])
pre = (ds_t > t_un - 5) & (ds_t < t_un)
print('range on ground (5 s before): mean %.3f min %.3f max %.3f std %.4f' % (
    ds[pre].mean(), ds[pre].min(), ds[pre].max(), ds[pre].std()))

flags = T.get('estimator_status_flags')
ft = (flags.data['timestamp'] - t0) / 1e6
for f in ('cs_rng_hgt', 'cs_rng_terrain', 'cs_rng_kin_consistent', 'cs_rng_fault', 'cs_in_air', 'cs_ev_hgt',
          'cs_baro_hgt', 'cs_opt_flow_terrain', 'cs_rng_stuck', 'fs_bad_rng'):
    if f in flags.data:
        v = flags.data[f]
        ch = np.where(np.diff(v.astype(int)) != 0)[0]
        print('%-22s start=%d changes=%s' % (f, v[0], ['%.2f->%d' % (ft[c + 1], v[c + 1]) for c in ch[:8]]))

ra = T.get('estimator_aid_src_rng_hgt')
if ra is not None:
    rt = (ra.data['timestamp'] - t0) / 1e6
    for lo, hi in ((t_un - 3, t_un - 0.5), (t_un - 0.5, t_un + 2.0)):
        w = (rt > lo) & (rt < hi)
        idx = np.where(w)[0][::max(1, w.sum() // 12)]
        for k in idx:
            print('rng_aid t=%.2f obs=%.3f innov=%+.3f fused=%d rej=%d' % (
                rt[k], ra.data['observation'][k], ra.data['innovation'][k], ra.data['fused'][k],
                ra.data['innovation_rejected'][k]))

lp_t, z = g('vehicle_local_position', 'z')
_, dist_b = g('vehicle_local_position', 'dist_bottom')
gt_t, gz = g('vehicle_local_position_groundtruth', 'z')
st = T.get('estimator_states')
for tt in np.arange(t_un - 2, t_un + 2.6, 0.25):
    k = np.searchsorted(lp_t, tt)
    kg = np.searchsorted(gt_t, tt)
    kd = np.searchsorted(ds_t, tt)
    terr = ''
    if st is not None:
        s_t = (st.data['timestamp'] - t0) / 1e6
        ks = min(np.searchsorted(s_t, tt), len(s_t) - 1)
        # state 24 is terrain in 1.16 (pos 7..9, terrain index 24)
        terr = 'state24=%.3f state9=%.3f' % (st.data['states[24]'][ks], st.data['states[9]'][ks])
    print('t=%.2f ekf_z=%.3f truth_z=%.3f dist_bottom=%.3f range=%.3f %s' % (
        tt, z[min(k, len(z) - 1)], gz[min(kg, len(gz) - 1)], dist_b[min(k, len(z) - 1)], ds[min(kd, len(ds) - 1)], terr))
