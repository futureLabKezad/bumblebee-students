#!/usr/bin/env python3
"""T41 (READ ONLY): why ground_contact comes late after touchdown. Recomputes the PX4 v1.16.1 MC land detector
ground-contact conditions (MulticopterLandDetector.cpp:159-250) from the ULog around the final touchdown:
  low_thr   thrust setpoint (|z|) <= THR_MIN + (hover - THR_MIN) * 0.6 (0.3 without a valid hover-thrust estimate)
  in_desc   trajectory_setpoint vz >= 1.1 * LNDMC_Z_VEL_MAX
  no_vz     |vz| < LNDMC_Z_VEL_MAX (x2.5 once landed)   (or |z_deriv| < it)
  no_vxy    |vxy| <= LNDMC_XY_VEL_MAX
  rng_ok    dist_bottom_valid (factor 1 hysteresis; invalid -> x3, LandDetector.cpp:130-135)
Touchdown = first sample after the last armed truth height > 0.01 m with height <= 0.01 m (as the Simulator's
land_phase_info.py), truth from vehicle_local_position_groundtruth, height relative to the median of the first 1 s.
Prints per run the first time each condition holds after touchdown, ground_contact / maybe_landed / landed / disarm,
and a 0.25 s table from td-0.5 to td+4. Usage: t41_ground_contact.py RUN [...]"""
import glob, json, os, sys
import numpy as np
from pyulog import ULog

TOPICS = ['vehicle_status', 'vehicle_local_position', 'vehicle_local_position_groundtruth', 'vehicle_land_detected',
          'trajectory_setpoint', 'vehicle_thrust_setpoint', 'hover_thrust_estimate', 'distance_sensor']
for run in sys.argv[1:]:
    P = json.load(open(os.path.join(run, 'params_sitl.json')))['params']
    p = lambda k: float(P[k]['value'])
    f = sorted(glob.glob(run + '/rootfs/log/*/*.ulg'), key=os.path.getsize)[-1]
    u = ULog(f, TOPICS, disable_str_exceptions=True)
    t0 = np.int64(u.start_timestamp)
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    s = lambda d: (d['timestamp'].astype(np.int64) - t0) / 1e6
    st, lp, gt, ld = D['vehicle_status'], D['vehicle_local_position'], D['vehicle_local_position_groundtruth'], D['vehicle_land_detected']
    ts, tl, tg, tld = s(st), s(lp), s(gt), s(ld)
    armed_g = np.interp(tg, ts, (st['arming_state'] == 2).astype(float)) > 0.5
    h = -gt['z'] - np.median(-gt['z'][tg <= tg[0] + 1.0])
    up = np.flatnonzero(armed_g & (h > 0.01))
    td = float(tg[np.flatnonzero((np.arange(len(tg)) > up[-1]) & (h <= 0.01))[0]])
    dis = ts[np.flatnonzero((ts > td) & (st['arming_state'] != 2))[0]]
    sp, th, he = D['trajectory_setpoint'], D['vehicle_thrust_setpoint'], D.get('hover_thrust_estimate')
    tsp, tth = s(sp), s(th)
    zmax = p('LNDMC_Z_VEL_MAX')
    grid = np.arange(td - 0.5, td + 4.01, 0.05)
    def last(T, v, k):
        i = np.searchsorted(T, k, side='right') - 1
        return v[i] if i >= 0 else np.nan
    hov = []
    for k in grid:
        if he is not None and len(he['timestamp']):
            th_ = he['hover_thrust']; ok = he['valid']; i = np.searchsorted(s(he), k, side='right') - 1
            hov.append((float(th_[i]), bool(ok[i])) if i >= 0 else (p('MPC_THR_HOVER'), False))
        else:
            hov.append((p('MPC_THR_HOVER'), False))
    rows = []
    for j, k in enumerate(grid):
        thr = abs(last(tth, th['xyz[2]'], k))
        hv, hv_ok = hov[j]
        lim = p('MPC_THR_MIN') + (hv - p('MPC_THR_MIN')) * (0.6 if hv_ok else 0.3)
        vz, zd = last(tl, lp['vz'], k), last(tl, lp['z_deriv'], k)
        vxy = np.hypot(last(tl, lp['vx'], k), last(tl, lp['vy'], k))
        spvz = last(tsp, sp['velocity[2]'], k)
        c = dict(t=round(k - td, 2), thr=round(float(thr), 3), lim=round(float(lim), 3), hov=round(float(hv), 3), low_thr=bool(thr <= lim),
                 spvz=round(float(spvz), 3), in_desc=bool(np.isfinite(spvz) and spvz >= 1.1 * zmax),
                 vz=round(float(vz), 3), no_vz=bool(abs(vz) < zmax or abs(zd) < zmax), vxy=round(float(vxy), 3),
                 no_vxy=bool(vxy <= p('LNDMC_XY_VEL_MAX')), rng_ok=bool(last(tl, lp['dist_bottom_valid'], k)),
                 dist_bottom=round(float(last(tl, lp['dist_bottom'], k)), 3), est_z=round(float(last(tl, lp['z'], k)), 3),
                 gc=bool(last(tld, ld['ground_contact'], k)), ml=bool(last(tld, ld['maybe_landed'], k)), la=bool(last(tld, ld['landed'], k)),
                 nav=int(last(ts, st['nav_state'], k)))
        rows.append(c)
    first = {}
    for key in ('low_thr', 'in_desc', 'no_vz', 'no_vxy', 'rng_ok', 'gc', 'ml', 'la'):
        hit = [r['t'] for r in rows if r['t'] >= 0 and r[key]]
        first[key] = hit[0] if hit else None
    allc = [r['t'] for r in rows if r['t'] >= 0 and r['low_thr'] and r['in_desc'] and r['no_vz'] and r['no_vxy']]
    print(json.dumps({'run': os.path.basename(run.rstrip('/')), 'touchdown': round(td, 3), 'disarm_after_td': round(float(dis - td), 3),
                      'first_true_after_td': first, 'all_four_after_td': allc[0] if allc else None}))
    for r in rows[::5]:
        print('   ', json.dumps(r))
