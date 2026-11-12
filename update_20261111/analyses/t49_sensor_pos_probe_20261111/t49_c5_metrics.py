#!/usr/bin/env python3
"""t49_c5_metrics.py (Claude «Симулятор», 11.11.2026, T49). READ ONLY. Per flight.py run (С5), from the run's ULog:
  dist_bottom_max   - max vehicle_local_position.dist_bottom (valid) while armed;
  hte_valid         - hover_thrust_estimate.valid ever true while armed (+ first time, s after arm; last hover_thrust);
  ekf_jump_liftoff  - liftoff = first Gazebo truth height > 0.05 m above the arm height; e = EKF height (-z) - truth height;
                      jump = max |e(t) - e(liftoff - 0.5 s)| for t in [liftoff - 0.5, liftoff + 3] s; plus EKF z resets
                      (z_reset_counter changes, delta_z) in that window. (Definition fixed here; T23 wording «скачок высоты EKF при отрыве».)
Height / motors off: from the С5 evaluator output (c5_eval r5, file given). Usage: python3 -I t49_c5_metrics.py RUN [...]"""
import glob, json, os, sys
import numpy as np
from pyulog import ULog
for run in sys.argv[1:]:
    tag = os.path.basename(run.rstrip('/'))
    ul = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')))[-1]
    u = ULog(ul, ['vehicle_local_position', 'vehicle_local_position_groundtruth', 'actuator_armed', 'hover_thrust_estimate'])
    d = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    aa = d['actuator_armed']; ta = aa['timestamp'] / 1e6; arm = aa['armed'].astype(bool)
    t_arm = ta[np.argmax(arm)]; offs = np.where(arm[:-1] & ~arm[1:])[0]; t_dis = ta[offs[-1] + 1] if len(offs) else ta[-1]
    lp = d['vehicle_local_position']; tl = lp['timestamp'] / 1e6; m = (tl >= t_arm) & (tl <= t_dis)
    db = lp['dist_bottom'][m & lp['dist_bottom_valid'].astype(bool)]
    g = d['vehicle_local_position_groundtruth']; tg = g['timestamp'] / 1e6
    z0g = float(np.interp(t_arm, tg, g['z'])); hg = -(g['z'] - z0g)
    lift = tg[(tg > t_arm) & (hg > 0.05)]
    res = {'run': tag, 'dist_bottom_max_m': round(float(db.max()), 3) if len(db) else None}
    h = d.get('hover_thrust_estimate')
    if h is not None:
        th = h['timestamp'] / 1e6; mh = (th >= t_arm) & (th <= t_dis); v = h['valid'].astype(bool) & mh
        res['hte_valid'] = bool(v.any()); res['hte_first_valid_s_after_arm'] = round(float(th[v][0] - t_arm), 1) if v.any() else None
        res['hte_last'] = round(float(h['hover_thrust'][mh][-1]), 3) if mh.any() else None
    if len(lift):
        tL = lift[0]; w = (tl >= tL - 0.5) & (tl <= tL + 3.0)
        e = (-lp['z']) - np.interp(tl, tg, hg)
        e0 = float(np.interp(tL - 0.5, tl, e))
        res['liftoff_s_after_arm'] = round(float(tL - t_arm), 2)
        res['ekf_jump_liftoff_m'] = round(float(np.max(np.abs(e[w] - e0))), 3) if w.any() else None
        zr = lp['z_reset_counter'][w]; dz = lp['delta_z'][w]
        res['z_resets_in_window'] = int(len(np.unique(zr)) - 1) if w.any() else None
        res['z_reset_delta_m'] = [round(float(x), 3) for x in dz[np.r_[False, np.diff(zr) != 0]]] if w.sum() > 1 else []
    print(json.dumps(res))
