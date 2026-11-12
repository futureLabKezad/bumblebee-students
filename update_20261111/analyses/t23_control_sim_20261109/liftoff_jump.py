#!/usr/bin/env python3
"""liftoff_jump.py - T23 control (Claude «Симулятор», 09.11.2026). Reads files only.
Height jump of the EKF at lift-off, against Gazebo ground truth (same definition as РАЗБОР_T23.md §2):
  d(t) = (EKF height - its median on the ground) - (gt height - its median on the ground)
  ground = 2.0 .. 0.2 s before in_air (vehicle_land_detected.landed 1 -> 0);
  jump = max |d| in 1.5 s after in_air (sign kept), plus terrain state shift and the EKF2_MIN_RNG value.
Usage: python3 -I liftoff_jump.py RUN [RUN ...]
"""
import glob, json, os, sys
import numpy as np
from pyulog import ULog


def T(u, n):
    return next((d.data for d in u.data_list if d.name == n and d.multi_id == 0), None)


for run in sys.argv[1:]:
    for f in sorted(glob.glob(os.path.join(run, 'rootfs/log/*/*.ulg'))):
        u = ULog(f)
        ld, lp, gt = T(u, 'vehicle_land_detected'), T(u, 'vehicle_local_position'), T(u, 'vehicle_local_position_groundtruth')
        if ld is None or gt is None:
            continue
        tl = ld['timestamp'] / 1e6
        up = np.where(ld['landed'][:-1].astype(bool) & ~ld['landed'][1:].astype(bool))[0]
        if not len(up):
            continue
        ta = float(tl[up[0] + 1])
        t1, t2 = lp['timestamp'] / 1e6, gt['timestamp'] / 1e6
        ekf = -lp['z']; tru = np.interp(t1, t2, -gt['z'])
        g = (t1 >= ta - 2.0) & (t1 <= ta - 0.2)
        d = (ekf - np.median(ekf[g])) - (tru - np.median(tru[g]))
        w = (t1 >= ta) & (t1 <= ta + 1.5)
        i = np.argmax(np.abs(d[w]))
        out = {'run': os.path.basename(run), 'ulog': os.path.basename(f), 'in_air_s': round(ta, 2),
               'jump_m': round(float(d[w][i]), 3), 'dist_bottom_ground': round(float(np.median(lp['dist_bottom'][g])), 3),
               'EKF2_MIN_RNG': u.initial_parameters.get('EKF2_MIN_RNG')}
        es = T(u, 'estimator_states')
        if es is not None and 'states[24]' in es:
            te = es['timestamp'] / 1e6
            out['terrain_shift_m'] = round(float(np.interp(ta + 1.0, te, es['states[24]']) - np.interp(ta - 0.5, te, es['states[24]'])), 3)
        print(json.dumps(out, ensure_ascii=False))
        break
