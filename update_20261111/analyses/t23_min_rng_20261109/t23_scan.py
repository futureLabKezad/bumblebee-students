#!/usr/bin/env python3
"""T23: for every run folder given, EKF2_MIN_RNG / HGT_REF and the EKF height jump at the in_air 0->1 edge
(EKF z change minus truth z change over 1.5 s, while the vehicle is still on the ground) plus the EKF HAGL
observation just before. Read-only. Run: python3 -I -B t23_scan.py RUN_DIR..."""
import glob
import json
import os
import sys

import numpy as np
from pyulog import ULog

print('%-28s %7s %3s %3s %8s %8s %8s %8s' % ('run', 'MIN_RNG', 'HR', 'EV', 'obs_gnd', 'jump', 'pred', 'terr_d'))
for run in sys.argv[1:]:
    name = os.path.basename(run.rstrip('/'))
    ulgs = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')))
    try:
        pp = json.load(open(os.path.join(run, 'params_sitl.json')))['params']
    except Exception:
        print('%-28s no params' % name)
        continue
    if not ulgs:
        print('%-28s no ulog' % name)
        continue
    try:
        u = ULog(ulgs[-1], ['estimator_status_flags', 'vehicle_local_position', 'vehicle_local_position_groundtruth',
                            'estimator_aid_src_rng_hgt', 'estimator_states'])
    except Exception as e:
        print('%-28s ulog error %s' % (name, e))
        continue
    T = {d.name: d for d in u.data_list}
    t0 = u.start_timestamp
    f = T['estimator_status_flags']
    ft = (f.data['timestamp'] - t0) / 1e6
    ia = f.data['cs_in_air']
    e = np.where(np.diff(ia.astype(int)) == 1)[0]
    if not len(e):
        print('%-28s never in air' % name)
        continue
    te = ft[e[0] + 1]
    lp = T['vehicle_local_position']
    lt = (lp.data['timestamp'] - t0) / 1e6
    gt = T['vehicle_local_position_groundtruth']
    gtt = (gt.data['timestamp'] - t0) / 1e6
    ra = T['estimator_aid_src_rng_hgt']
    rt = (ra.data['timestamp'] - t0) / 1e6
    st = T['estimator_states']
    stt = (st.data['timestamp'] - t0) / 1e6

    def at(tt, ts, v):
        return v[min(np.searchsorted(ts, tt), len(v) - 1)]

    w = (rt > te - 1.0) & (rt < te)
    obs = float(np.mean(ra.data['observation'][w]))
    a, b = te - 0.1, te + 1.5
    dz_ekf = at(a, lt, lp.data['z']) - at(b, lt, lp.data['z'])
    dz_true = at(a, gtt, gt.data['z']) - at(b, gtt, gt.data['z'])
    mr = pp['EKF2_MIN_RNG']['value']
    terr_d = at(b, stt, st.data['states[24]']) - at(a, stt, st.data['states[24]'])
    print('%-28s %7.3f %3d %3d %8.3f %+8.3f %+8.3f %+8.3f' % (
        name, mr, pp['EKF2_HGT_REF']['value'], pp['EKF2_EV_CTRL']['value'], obs, dz_ekf - dz_true, obs - mr, terr_d))
