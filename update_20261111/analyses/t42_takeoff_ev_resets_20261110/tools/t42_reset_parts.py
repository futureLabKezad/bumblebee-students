#!/usr/bin/env python3
"""T42 (READ ONLY): split every in-air EKF xy reset at an EV resume into three parts (vectors, truth frame):
  reset = EV(sample used) - EKF(before)
        = [EV(sample) - local EV bias]            single-sample noise (PX4 resets to ONE sample)
        + [local EV bias - EV bias at the arm]    vision bias change, ground -> this height
        - [EKF error now - EKF error at the arm]  EKF drift on flow during the pause
local EV bias = median(EV - truth) over the 1.5 s after the resume; EV bias at the arm = median over the 2 s before
the arm. The sample used = the EV sample nearest before the reset stamp (time_last_fuse of the aid source).
Usage: t42_reset_parts.py out/ev_gaps.jsonl -> JSON lines + a summary on stdout."""
import json, sys
import numpy as np
from pyulog import ULog

TOPICS = ['vehicle_local_position', 'vehicle_local_position_groundtruth', 'estimator_aid_src_ev_pos']
allp = []
for line in open(sys.argv[1]):
    d = json.loads(line)
    u = ULog(d['ulog'], TOPICS, disable_str_exceptions=True)
    t0 = np.int64(u.start_timestamp)
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    s = lambda x, k='timestamp': (x[k].astype(np.int64) - t0) / 1e6
    lp, gt, ev = D['vehicle_local_position'], D['vehicle_local_position_groundtruth'], D['estimator_aid_src_ev_pos']
    tl, tg, te = s(lp), s(gt), s(ev, 'timestamp_sample')
    E = np.c_[ev['observation[0]'] - np.interp(te, tg, gt['x']), ev['observation[1]'] - np.interp(te, tg, gt['y'])]
    K = lambda k: np.array([np.interp(k, tl, lp['x']) - np.interp(k, tg, gt['x']), np.interp(k, tl, lp['y']) - np.interp(k, tg, gt['y'])])
    for a in d['arms']:
        arm = a['arm']
        pre = (te > arm - 2) & (te <= arm)
        if not pre.any():
            continue
        b_arm = np.median(E[pre], axis=0); k_arm = K(arm)
        for g in a['gaps']:
            if not g['in_air'] or g['len'] <= 0.4 or not g['reset']:
                continue
            tr, size, vec = g['reset'][0]
            # EV sample used: the last sample whose fusion-time (timestamp) is <= the reset publish time
            tpub = s(ev)
            idx = np.flatnonzero(tpub <= tr + 1e-3)
            if not len(idx):
                continue
            i = idx[-1]
            loc = (te > te[i]) & (te <= te[i] + 1.5)
            if loc.sum() < 5:
                continue
            b_loc = np.median(E[loc], axis=0)
            noise = E[i] - b_loc
            bias = b_loc - b_arm
            drift = K(tr - 0.25) - k_arm
            pred = noise + bias - drift
            p = {'run': d['run'], 't': tr, 'h': g['h_truth_end'], 'reset': size,
                 'pred': round(float(np.hypot(*pred)), 3), 'noise': round(float(np.hypot(*noise)), 3),
                 'bias_change': round(float(np.hypot(*bias)), 3), 'drift': round(float(np.hypot(*drift)), 3),
                 'along': [round(float(np.dot(v, np.array(vec)) / max(size, 1e-6)), 3) for v in (noise, bias, -drift)]}
            allp.append(p)
            print(json.dumps(p))
P = allp
R = np.array([p['reset'] for p in P]); A = np.array([p['along'] for p in P]); pr = np.array([p['pred'] for p in P])
print('# n %d, reset median %.3f; |reset - predicted| median %.3f' % (len(P), np.median(R), np.median(np.abs(R - pr))))
for name, k in (('single-sample noise', 0), ('vision bias change', 1), ('EKF drift', 2)):
    print('# along the reset, %s: median %.3f m, in resets > 0.08 m: median %.3f m' % (name, np.median(A[:, k]), np.median(A[R > 0.08, k])))
