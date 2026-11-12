#!/usr/bin/env python3
"""t45_table.py (Claude «Симулятор», 11.11.2026). READ ONLY. T45: during the slow descent after floor_near_off, per 0.1 m of
height above the takeoff point:
  - from script_ts.log (wall stamps): [VIS] markers_used / vision_age (0.2 s, read-only monitor) matched to the height of the
    latest [FLY_TO] line (estimate z minus START z; 0.5 s);
  - from the ULog (sim time): EV samples fused (estimator_aid_src_ev_pos timestamp_sample) per s, binned by Gazebo truth height.
Also: height where markers_used first stays 0 for >= 1 s, and the script's end lines. Usage: python3 -I t45_table.py RUN [...]"""
import glob, os, re, sys
import numpy as np
from pyulog import ULog

for run in sys.argv[1:]:
    tag = os.path.basename(run.rstrip('/'))
    L = open(os.path.join(run, 'script_ts.log'), errors='replace').read().splitlines()
    start_z = None; t_desc = None; z_last = None; rows = []; ends = []
    for l in L:
        p = l.split(' ', 2)
        if len(p) < 3:
            continue
        try:
            w = float(p[0])
        except ValueError:
            continue
        txt = p[2]
        m = re.search(r'START.*?z[=: ]+(-?[\d.]+)', txt)
        if start_z is None and txt.startswith('START') and m:
            start_z = float(m.group(1))
        if 'T45 DESCENT START' in txt:
            t_desc = w
            m2 = re.search(r'to z (-?[\d.]+)', txt)
            low = float(m2.group(1)) if m2 else None
        m = re.search(r'\[FLY_TO\].*? z=(-?[\d.]+)', txt)
        if m and t_desc is not None:
            z_last = float(m.group(1))
        m = re.search(r'\[VIS\] markers_used=(\d+) vision_age=([\d.infa]+)', txt)
        if m and t_desc is not None and z_last is not None:
            rows.append((w, z_last, int(m.group(1)), float(m.group(2))))
        if any(k in txt for k in ('Vision lost', 'T45 DESCENT END', 'HOVER RESULT', 'not reached', 'LANDING')):
            ends.append('%.1f %s' % (w - (t_desc or w), txt[:90]))
    print('== %s  (START z from log: %s; low target %s)' % (tag, start_z, locals().get('low')))
    if start_z is None and rows:
        start_z = (locals().get('low') or 0.2) - 0.2
    if rows:
        A = np.array(rows)
        h = A[:, 1] - start_z
        print('  height  n  markers_used median/min/max  share(age<=0.5 s)')
        for b in np.arange(1.0, 0.1, -0.1):
            m = (h <= b + 0.05) & (h > b - 0.05)
            if m.any():
                print('  %.1f m  %3d  %4.1f / %d / %d   %.2f' % (b, m.sum(), np.median(A[m, 2]), A[m, 2].min(), A[m, 2].max(),
                                                           float((A[m, 3] <= 0.5).mean())))
        z0 = np.where(A[:, 2] == 0)[0]
        first_zero = None
        for i in z0:
            j = (A[:, 0] >= A[i, 0]) & (A[:, 0] <= A[i, 0] + 1.0)
            if (A[j, 2] == 0).all() and (A[j, 0].max() - A[i, 0]) >= 0.8:
                first_zero = (round(A[i, 0] - t_desc, 1), round(float(h[i]), 2)); break
        print('  markers_used 0 for >=1 s first at (s after descent start, height):', first_zero)
    ul = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')))
    if ul:
        u = ULog(ul[-1], ['estimator_aid_src_ev_pos', 'vehicle_local_position_groundtruth'])
        d = {x.name: x.data for x in u.data_list if x.multi_id == 0}
        g = d['vehicle_local_position_groundtruth']; tg = g['timestamp'] / 1e6; hz = -(g['z'] - g['z'][0])
        ev = d['estimator_aid_src_ev_pos']; te = ev['timestamp_sample'] / 1e6
        he = np.interp(te, tg, hz)
        # descent window: last time truth height was > 0.9 before the final descent, to touchdown
        top = np.where(hz > 0.9)[0]
        t0 = tg[top[-1]] if len(top) else tg[0]
        print('  ULog EV samples per s by truth height (after the last time above 0.9 m, t %.1f s):' % t0)
        for b in np.arange(0.9, 0.0, -0.1):
            mt = (tg >= t0) & (hz <= b + 0.05) & (hz > b - 0.05)
            if mt.sum() > 2:
                dur = mt.sum() * float(np.median(np.diff(tg)))
                ne = int(((te >= t0) & (he <= b + 0.05) & (he > b - 0.05)).sum())
                print('   %.1f m  %.1f s  EV %d  -> %.1f /s (logged subset)' % (b, dur, ne, ne / dur if dur else 0))
    print('  ends:', ends[:6])
