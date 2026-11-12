#!/usr/bin/env python3
"""t52_checks.py (Claude «Симулятор», 11.11.2026, T52). READ ONLY. Per run (ULog):
 standing (before the first arm): median distance_sensor.current_distance (raw rangefinder) and vehicle_local_position.dist_bottom;
 innovations: estimator_aid_src_optical_flow (innovation[0..1], test_ratio[0..1]) and estimator_aid_src_rng_hgt (innovation,
 test_ratio), split into HOVER (armed, truth h > 0.8 m, |yaw rate| < 5 deg/s) and TURN (armed, truth h > 0.8 m, |yaw rate| > 10 deg/s):
 mean and RMS innovation, mean test_ratio, samples. «Not worse» = RMS innovation and mean test_ratio not larger than on 4070 v2.
Usage: python3 -I t52_checks.py RUN [...]"""
import glob, json, os, sys
import numpy as np
from pyulog import ULog
for run in sys.argv[1:]:
    ul = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')))[-1]
    u = ULog(ul, ['distance_sensor', 'vehicle_local_position', 'actuator_armed', 'vehicle_local_position_groundtruth',
                  'vehicle_angular_velocity', 'estimator_aid_src_optical_flow', 'estimator_aid_src_rng_hgt'])
    d = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    T = lambda a: a['timestamp'] / 1e6
    aa = d['actuator_armed']; arm = aa['armed'].astype(bool); t_arm = T(aa)[np.argmax(arm)]
    res = {'run': os.path.basename(run.rstrip('/'))}
    ds = d.get('distance_sensor'); lp = d['vehicle_local_position']
    if ds is not None:
        m = T(ds) < t_arm - 0.5; res['stand_raw_range_m'] = round(float(np.median(ds['current_distance'][m])), 4) if m.any() else None
    m = (T(lp) < t_arm - 0.5) & lp['dist_bottom_valid'].astype(bool)
    res['stand_dist_bottom_m'] = round(float(np.median(lp['dist_bottom'][m])), 4) if m.any() else None
    g = d['vehicle_local_position_groundtruth']; z0 = float(np.interp(t_arm, T(g), g['z']))
    av = d['vehicle_angular_velocity']
    def phase(t):
        h = -(np.interp(t, T(g), g['z']) - z0); yr = np.degrees(np.abs(np.interp(t, T(av), av['xyz[2]'])))
        armed = np.interp(t, T(aa), aa['armed'].astype(float)) > 0.5
        return armed & (h > 0.8) & (yr < 5), armed & (h > 0.8) & (yr > 10)
    for name, key, n in (('flow', 'estimator_aid_src_optical_flow', 2), ('range', 'estimator_aid_src_rng_hgt', 1)):
        a = d.get(key)
        if a is None:
            continue
        t = T(a); hov, turn = phase(t)
        for ph, m in (('hover', hov), ('turn', turn)):
            if not m.any():
                res['%s_%s' % (name, ph)] = None; continue
            if n == 2:
                inn = np.stack([a['innovation[0]'][m], a['innovation[1]'][m]], 1); tr = np.stack([a['test_ratio[0]'][m], a['test_ratio[1]'][m]], 1)
                res['%s_%s' % (name, ph)] = {'n': int(m.sum()), 'inn_mean': [round(float(x), 4) for x in inn.mean(0)],
                                             'inn_rms': [round(float(x), 4) for x in np.sqrt((inn ** 2).mean(0))],
                                             'test_ratio_mean': [round(float(x), 3) for x in tr.mean(0)]}
            else:
                inn = a['innovation'][m]; tr = a['test_ratio'][m]
                res['%s_%s' % (name, ph)] = {'n': int(m.sum()), 'inn_mean': round(float(inn.mean()), 4),
                                             'inn_rms': round(float(np.sqrt((inn ** 2).mean())), 4), 'test_ratio_mean': round(float(tr.mean()), 3)}
    print(json.dumps(res))
