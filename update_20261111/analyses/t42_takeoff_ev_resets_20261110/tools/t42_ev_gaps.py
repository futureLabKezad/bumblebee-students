#!/usr/bin/env python3
"""T42 (READ ONLY): EV pauses while armed and the EKF horizontal resets they cause, per run.
For every armed period of the flight ULog:
  - EV samples = estimator_aid_src_ev_pos (one per EV sample; timestamp_sample, observation); a pause = spacing > GAP_S;
  - for each pause: start/end (s from ULog start, and s from the arm), length, truth height above the arm height,
    flow fused share and cs_ev_pos during the pause, EKF-truth horizontal drift over the pause,
    the xy reset at the resume (reset counter change within RESUME_WIN after the first sample) and its size,
    the vision error vs truth at the resume (both relative to the arm);
  - the largest EKF moves in < 0.2 s (as a34_c6jump.py) above MOVE_MIN, with the nearest reset.
Truth = vehicle_local_position_groundtruth; all horizontal errors are taken relative to their value at the arm
(EKF/EV frame and Gazebo frame differ by a constant). Output: one JSON line per run.
Usage: t42_ev_gaps.py RUN_DIR [...]"""
import glob, json, os, sys
import numpy as np
from pyulog import ULog

GAP_S = 0.25
RESUME_WIN = 1.0
MOVE_MIN = 0.08
TOPICS = ['vehicle_status', 'vehicle_land_detected', 'vehicle_local_position', 'vehicle_local_position_groundtruth',
          'estimator_status_flags', 'estimator_aid_src_optical_flow', 'estimator_aid_src_ev_pos']


def flight_ulog(run):
    fs = sorted(glob.glob(run + '/rootfs/log/*/*.ulg'), key=os.path.getsize)
    return fs[-1]


def moves_lt(t, P, dt, thr):
    """all windows (j..i, t[i]-t[j] < dt) whose displacement > thr, merged by end time"""
    out, j = [], 0
    for i in range(len(t)):
        while t[i] - t[j] >= dt:
            j += 1
        if j < i:
            d = np.linalg.norm(P[j:i] - P[i], axis=1)
            k = int(np.argmax(d))
            if d[k] > thr:
                if out and t[i] - out[-1][1] < 0.3:
                    if d[k] > out[-1][2]:
                        out[-1] = (float(t[j + k]), float(t[i]), float(d[k]))
                else:
                    out.append((float(t[j + k]), float(t[i]), float(d[k])))
    return out


def run_one(run):
    f = flight_ulog(run)
    u = ULog(f, TOPICS, disable_str_exceptions=True)
    t0 = np.int64(u.start_timestamp)
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    s = lambda d, k='timestamp': (d[k].astype(np.int64) - t0) / 1e6
    st = D['vehicle_status']; ts = s(st); armed = st['arming_state'] == 2
    lp, gt = D['vehicle_local_position'], D['vehicle_local_position_groundtruth']
    tl, tg = s(lp), s(gt)
    fl, of, evp = D['estimator_status_flags'], D['estimator_aid_src_optical_flow'], D['estimator_aid_src_ev_pos']
    tf, to_, te = s(fl), s(of), s(evp)
    vo, tv = evp, s(evp, 'timestamp_sample')
    ld = D['vehicle_land_detected']; tld = s(ld)
    xy = lambda k, T, d, a='x', b='y': np.array([np.interp(k, T, d[a]), np.interp(k, T, d[b])])
    ekf_err = lambda k: xy(k, tl, lp) - xy(k, tg, gt)
    ev_err = lambda k: xy(k, tv, vo, 'observation[0]', 'observation[1]') - xy(k, tg, gt)
    h_truth = lambda k: -np.interp(k, tg, gt['z'])
    res = {'run': os.path.basename(run.rstrip('/')), 'ulog': f, 'arms': []}
    # armed periods
    edges = np.flatnonzero(np.diff(armed.astype(int))) + 1
    starts = [i for i in edges if armed[i]]
    if armed[0]:
        starts = [0] + starts
    for i0 in starts:
        t_arm = ts[i0]
        after = np.flatnonzero((ts > t_arm) & ~armed)
        t_dis = ts[after[0]] if len(after) else ts[-1]
        lo = np.flatnonzero((tld > t_arm) & (ld['landed'] == 0))
        t_to = float(tld[lo[0]]) if len(lo) else None
        nav = st['nav_state'][(ts >= t_arm) & (ts <= t_dis)]; tn = ts[(ts >= t_arm) & (ts <= t_dis)]
        off = np.flatnonzero(nav == 14)
        t_off = float(tn[off[0]]) if len(off) else None
        e0, v0, h0 = ekf_err(t_arm), ev_err(t_arm), h_truth(t_arm)
        sel = (tv >= t_arm - 1.0) & (tv <= t_dis)
        tvs = tv[sel]
        gaps = []
        # pause at the start of the armed period (no sample since t_arm) counts too
        prev = tvs[tvs <= t_arm]
        cand = list(zip(tvs[:-1], tvs[1:]))
        for a, b in cand:
            if b - a > GAP_S and b > t_arm:
                gaps.append((float(a), float(b)))
        rc = lp['xy_reset_counter'].astype(int); ch = np.flatnonzero(np.diff(rc) != 0) + 1
        resets = [(float(tl[i]), float(np.hypot(lp['delta_xy[0]'][i], lp['delta_xy[1]'][i])),
                   [round(float(lp['delta_xy[0]'][i]), 3), round(float(lp['delta_xy[1]'][i]), 3)]) for i in ch
                  if t_arm - 1 <= tl[i] <= t_dis + 1]
        G = []
        for a, b in gaps:
            m_of = (to_ >= a) & (to_ <= b); m_fl = (tf >= a) & (tf <= b)
            r = [x for x in resets if b - 0.05 <= x[0] <= b + RESUME_WIN]
            d_drift = ekf_err(b) - ekf_err(a)
            G.append({
                'from': round(a, 2), 'to': round(b, 2), 'len': round(b - a, 2),
                'to_from_arm': round(b - t_arm, 2),
                'h_truth_end': round(float(h_truth(b) - h0), 3),
                'in_air': bool(t_to is not None and b > t_to),
                'of_fused': round(float(np.mean(of['fused'][m_of])), 2) if m_of.any() else None,
                'ev_pos_flag_end': bool(fl['cs_ev_pos'][m_fl][-1]) if m_fl.any() else None,
                'ekf_drift_over_gap': round(float(np.hypot(*d_drift)), 3),
                'ekf_err_at_resume': round(float(np.hypot(*(ekf_err(b) - e0))), 3),
                'ev_err_at_resume': round(float(np.hypot(*(ev_err(b + 0.01) - v0))), 3),
                'reset': [(round(x[0], 2), round(x[1], 3), x[2]) for x in r],
                # reset = EV - EKF at the resume = vision part - EKF drift part (both relative to the arm)
                'ekf_drift_vec': [round(float(v), 3) for v in (ekf_err(b) - e0)],
                'ev_err_vec': [round(float(v), 3) for v in (ev_err(b + 0.01) - v0)],
                'ev_minus_ekf_vec': [round(float(v), 3) for v in (xy(b + 0.01, tv, vo, 'observation[0]', 'observation[1]') - xy(b + 0.01, tl, lp))],
            })
        # big moves in < 0.2 s while armed
        m = (tl >= t_arm) & (tl <= t_dis)
        P = np.c_[lp['x'][m], lp['y'][m], lp['z'][m]]
        mv = moves_lt(tl[m], P, 0.2, MOVE_MIN)
        MV = []
        for a, b, d in mv:
            near = [x for x in resets if a - 0.05 <= x[0] <= b + 0.05]
            evs = (te >= a - 0.3) & (te <= b)
            MV.append({'from': round(a, 2), 'to': round(b, 2), 'move': round(d, 3), 'h_truth': round(float(h_truth(b) - h0), 3),
                       'reset_in_move': [(round(x[0], 2), round(x[1], 3)) for x in near],
                       'ev_innov_max': round(float(np.max(np.hypot(evp['innovation[0]'][evs], evp['innovation[1]'][evs]))), 3) if evs.any() else None})
        res['arms'].append({'arm': round(float(t_arm), 2), 'disarm': round(float(t_dis), 2),
                            'takeoff': round(t_to, 2) if t_to else None, 'offboard': round(t_off, 2) if t_off else None,
                            'gaps': G, 'resets_gt_0p05': [(round(x[0], 2), round(x[1], 3)) for x in resets if x[1] > 0.05],
                            'moves_gt_0p08_lt_0p2s': MV})
    return res


for run in sys.argv[1:]:
    print(json.dumps(run_one(run)))
    sys.stdout.flush()
