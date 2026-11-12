#!/usr/bin/env python3
"""T42 (READ ONLY): where the EV pose is off. Vision error = EV observation - truth (horizontal), with the constant
map-vs-Gazebo frame offset taken as the median over the steady part of the flight (truth height >= 0.85 m above the
arm height, EV fused). Reports per run: vision error on the ground before the arm (last 2 s) and at the arm,
in bands of truth height during the climb, and the hover spread (p95); also the EKF-truth error at the same points
with the same offset (EKF frame = EV frame). Usage: t42_vision_bias.py RUN_DIR [...] -> JSON lines."""
import glob, json, os, sys
import numpy as np
from pyulog import ULog

TOPICS = ['vehicle_status', 'vehicle_local_position', 'vehicle_local_position_groundtruth', 'estimator_aid_src_ev_pos',
          'vehicle_attitude', 'vehicle_land_detected']

for run in sys.argv[1:]:
    f = sorted(glob.glob(run + '/rootfs/log/*/*.ulg'), key=os.path.getsize)[-1]
    u = ULog(f, TOPICS, disable_str_exceptions=True)
    t0 = np.int64(u.start_timestamp)
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    s = lambda d, k='timestamp': (d[k].astype(np.int64) - t0) / 1e6
    st = D['vehicle_status']; ts = s(st); armed = st['arming_state'] == 2
    t_arm = ts[np.argmax(armed)]
    gt, lp, ev = D['vehicle_local_position_groundtruth'], D['vehicle_local_position'], D['estimator_aid_src_ev_pos']
    tg, tl, te = s(gt), s(lp), s(ev, 'timestamp_sample')
    h0 = -np.interp(t_arm, tg, gt['z'])
    gx, gy, gz = (np.interp(te, tg, gt[k]) for k in ('x', 'y', 'z'))
    h = -gz - h0
    exy = np.c_[ev['observation[0]'] - gx, ev['observation[1]'] - gy]
    lx, ly = np.interp(te, tl, lp['x']), np.interp(te, tl, lp['y'])
    kxy = np.c_[lx - gx, ly - gy]
    after = te > t_arm
    steady = after & (h >= 0.85)
    if steady.sum() < 50:
        print(json.dumps({'run': os.path.basename(run), 'skip': 'no steady part'}))
        continue
    off = np.median(exy[steady], axis=0)
    ve = np.linalg.norm(exy - off, axis=1)
    ke = np.linalg.norm(kxy - off, axis=1)
    pre = (te > t_arm - 2.0) & (te <= t_arm)
    out = {'run': os.path.basename(run.rstrip('/')), 'arm': round(float(t_arm), 2),
           'vision_err_ground_pre_arm_median': round(float(np.median(ve[pre])), 3) if pre.any() else None,
           'vision_err_ground_vec': [round(float(v), 3) for v in np.median(exy[pre] - off, axis=0)] if pre.any() else None,
           'hover_vision_err_p95': round(float(np.percentile(ve[steady], 95)), 3),
           'hover_ekf_err_p95': round(float(np.percentile(ke[steady], 95)), 3)}
    bands = {}
    for lo, hi in ((0.02, 0.25), (0.25, 0.45), (0.45, 0.7), (0.7, 0.85)):
        m = after & (h >= lo) & (h < hi) & (te < t_arm + 25)
        if m.any():
            bands['%.2f-%.2f' % (lo, hi)] = {'n': int(m.sum()), 'vision_err_median': round(float(np.median(ve[m])), 3),
                                             'vision_err_max': round(float(ve[m].max()), 3)}
    out['climb_bands'] = bands
    # EKF error just before the first in-air resume vs vision error there
    print(json.dumps(out))
