#!/usr/bin/env python3
"""T42 (READ ONLY): what the EV error in flight follows. For one run: EV observation vs truth in the steady frame
(as t42_vision_bias.py), after the arm and truth height >= 0.3 m. Checks
  (1) time lag: the truth shift tau (0..0.4 s) that minimises the median error (EV stamped later than the picture);
  (2) tilt: least squares of the error on (roll, pitch) in the map frame, R^2 and the slope in m/rad;
  (3) vector medians of the error in height bands.
Usage: t42_vision_cause.py RUN_DIR [...] -> JSON lines."""
import glob, json, os, sys
import numpy as np
from pyulog import ULog

TOPICS = ['vehicle_status', 'vehicle_local_position_groundtruth', 'estimator_aid_src_ev_pos', 'vehicle_attitude_groundtruth', 'vehicle_attitude']

for run in sys.argv[1:]:
    f = sorted(glob.glob(run + '/rootfs/log/*/*.ulg'), key=os.path.getsize)[-1]
    u = ULog(f, TOPICS, disable_str_exceptions=True)
    t0 = np.int64(u.start_timestamp)
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    s = lambda d, k='timestamp': (d[k].astype(np.int64) - t0) / 1e6
    st = D['vehicle_status']; ts = s(st); armed = st['arming_state'] == 2
    t_arm = ts[np.argmax(armed)]
    gt, ev = D['vehicle_local_position_groundtruth'], D['estimator_aid_src_ev_pos']
    att = D.get('vehicle_attitude_groundtruth', D['vehicle_attitude'])
    tg, te, ta = s(gt), s(ev, 'timestamp_sample'), s(att)
    h0 = -np.interp(t_arm, tg, gt['z'])

    def err(tau):
        gx, gy = np.interp(te - tau, tg, gt['x']), np.interp(te - tau, tg, gt['y'])
        return np.c_[ev['observation[0]'] - gx, ev['observation[1]'] - gy]
    h = -np.interp(te, tg, gt['z']) - h0
    after = te > t_arm
    steady = after & (h >= 0.85)
    if steady.sum() < 50:
        print(json.dumps({'run': os.path.basename(run.rstrip('/')), 'skip': 'no steady part'}))
        continue
    sel = after & (h >= 0.3)
    lag = []
    for tau in np.arange(0, 0.41, 0.02):
        e = err(tau); off = np.median(e[steady], axis=0)
        lag.append((round(float(tau), 2), float(np.median(np.linalg.norm(e[sel] - off, axis=1)))))
    best = min(lag, key=lambda x: x[1])
    e = err(0.0); off = np.median(e[steady], axis=0); E = e - off
    q = np.c_[[np.interp(te, ta, att['q[%d]' % i]) for i in range(4)]].T
    w, x, y, z = q.T
    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1, 1))
    A = np.c_[roll[sel], pitch[sel], np.ones(sel.sum())]
    r2, coef = [], []
    for k in range(2):
        c, *_ = np.linalg.lstsq(A, E[sel, k], rcond=None)
        res = E[sel, k] - A @ c
        r2.append(round(float(1 - res.var() / E[sel, k].var()), 2)); coef.append([round(float(v), 3) for v in c[:2]])
    bands = {}
    for lo, hi in ((0.3, 0.45), (0.45, 0.7), (0.7, 0.85), (0.85, 2)):
        m = after & (h >= lo) & (h < hi)
        if m.any():
            bands['%.2f-%.2f' % (lo, hi)] = [round(float(v), 3) for v in np.median(E[m], axis=0)]
    print(json.dumps({'run': os.path.basename(run.rstrip('/')), 'attitude_topic': 'vehicle_attitude_groundtruth' if 'vehicle_attitude_groundtruth' in D else 'vehicle_attitude',
                      'lag_best_s': best[0], 'err_median_lag0': round(lag[0][1], 3), 'err_median_best': round(best[1], 3),
                      'tilt_R2_xy': r2, 'tilt_slope_m_per_rad_x[roll,pitch]_y[roll,pitch]': coef,
                      'roll_pitch_p95_deg': [round(float(np.degrees(np.percentile(np.abs(roll[sel]), 95))), 1), round(float(np.degrees(np.percentile(np.abs(pitch[sel]), 95))), 1)],
                      'err_vec_median_by_height': bands}))
