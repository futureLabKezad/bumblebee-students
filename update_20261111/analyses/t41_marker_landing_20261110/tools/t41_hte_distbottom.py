#!/usr/bin/env python3
"""T41 (READ ONLY): per s10 run — is hover_thrust_estimate in the ULog at all (HTE runs only after dist_bottom > 1.0 m,
MulticopterHoverThrustEstimator.cpp:130-134), max vehicle_local_position.dist_bottom, max range, max truth height.
Usage: t41_hte_distbottom.py RUNS_DIR"""
import glob, json, os, sys
import numpy as np
from pyulog import ULog

R = sys.argv[1]
for r in sorted(os.listdir(R)):
    if not r.startswith('s10_'):
        continue
    f = sorted(glob.glob(os.path.join(R, r, 'rootfs/log/*/*.ulg')), key=os.path.getsize)[-1]
    u = ULog(f, ['vehicle_local_position', 'vehicle_local_position_groundtruth', 'distance_sensor', 'hover_thrust_estimate'])
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    lp, gt = D['vehicle_local_position'], D['vehicle_local_position_groundtruth']
    h = -gt['z'] - np.median(-gt['z'][:50])
    he = D.get('hover_thrust_estimate')
    print(json.dumps({'run': r, 'script_height_m': json.load(open(os.path.join(R, r, 'run_options.json'))).get('script_height_m'),
                      'dist_bottom_max': round(float(lp['dist_bottom'].max()), 3), 'n_dist_bottom_gt_1': int((lp['dist_bottom'] > 1.0).sum()),
                      'range_max': round(float(D['distance_sensor']['current_distance'].max()), 3) if 'distance_sensor' in D else None,
                      'truth_h_max': round(float(h.max()), 3), 'hte_msgs': 0 if he is None else len(he['timestamp']),
                      'hte_valid_share': None if he is None else round(float(he['valid'].mean()), 2)}))
