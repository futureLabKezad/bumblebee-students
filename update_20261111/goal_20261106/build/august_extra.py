#!/usr/bin/env python3
"""august_extra.py - extra numbers for the August-logs report (Claude, 05.11.2026, goal step 2). READ ONLY.

Usage: python -I august_extra.py ULOG_DIR RAW_JSON OUT_TXT   (refuses to overwrite OUT_TXT)
1. optical-flow fusion in air before / after log 121 (from RAW_JSON of august_logs.py);
2. full parameter differences 112 -> 123 -> 147 and 144 -> 145 (calibration values summarised);
3. land-detector timing before every disarm by "auto disarm after landing" (logs 87-112) and raw range 1 Hz;
4. secondary steady-flight numbers for 147-148 (|vz| <= 0.3 m/s instead of 0.15 m/s; everything else as hover);
5. the PX4 v1.16.1 source lines that decide when optical flow may start (~/PX4-Autopilot, same commit as the drone).
"""
import glob
import json
import os
import subprocess
import sys

import numpy as np
from pyulog import ULog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import august_logs as A  # noqa: E402

ULOGS, RAW, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
if os.path.exists(OUT):
    print('STOP: refuse to overwrite ' + OUT)
    sys.exit(2)
lines = []
P = lines.append


def ulog(i, topics=None):
    return ULog(glob.glob(os.path.join(ULOGS, 'log_%d_*.ulg' % i))[0], topics)


# 1
raw = json.load(open(RAW))
P('== 1. Optical flow fused in air (cs_opt_flow), logs with >= 5 s in air')
for name, rng in (('logs 0-120', range(0, 121)), ('logs 121-148', range(121, 149))):
    rows = []
    for i in rng:
        r = raw.get(str(i), {})
        if r.get('in_air_s', 0) >= 5 and r.get('ekf_fusion_fraction', {}).get('basis') == 'in air':
            rows.append((i, r['ekf_fusion_fraction']['cs_opt_flow'], r.get('xy_valid_frac_in_air'),
                         r['params_initial'].get('EKF2_EV_CTRL'), r['params_initial'].get('EKF2_HGT_REF'),
                         r['params_initial'].get('EKF2_RNG_CTRL')))
    fr = [x[1] for x in rows]
    P('%s: %d logs; flow fused fraction min %.2f median %.2f max %.2f; logs with 0: %s' % (
        name, len(rows), min(fr), float(np.median(fr)), max(fr), [x[0] for x in rows if x[1] == 0]))
    P('   (log, flow, xy_valid, EV_CTRL, HGT_REF, RNG_CTRL): ' + ' '.join('(%d,%.2f,%s,%s,%s,%s)' % x for x in rows))

# 2
P('')
P('== 2. Parameter differences (CAL_* summarised; counters skipped)')
skip = ('COM_FLIGHT_UUID', 'LND_FLIGHT_T_', 'SYS_RESTART')
for pair in ((112, 123), (123, 147), (144, 145)):
    a, b = ulog(pair[0], ['vehicle_status']).initial_parameters, ulog(pair[1], ['vehicle_status']).initial_parameters
    diff = [(k, a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k) and not k.startswith(skip)]
    cal = [k for k, _, _ in diff if k.startswith('CAL_')]
    P('log %d -> %d: %d changed; calibration params changed: %d (%s)' % (pair[0], pair[1], len(diff), len(cal),
                                                                      ', '.join(sorted(set(k[:8] for k in cal)))))
    for k, va, vb in diff:
        if not k.startswith('CAL_'):
            P('   %-18s %s -> %s' % (k, va, vb))

# 3
P('')
P('== 3. Auto-disarm landings: seconds from land-detector stages to disarm; raw rangefinder (1 Hz) before disarm')
for i in (87, 88, 89, 95, 99, 104, 106, 112):
    u = ulog(i, ['vehicle_land_detected', 'actuator_armed', 'distance_sensor', 'vehicle_status'])
    D = {d.name: d.data for d in u.data_list if d.multi_id == 0}
    t0 = u.start_timestamp
    T = lambda a: (np.asarray(a, float) - t0) / 1e6  # noqa: E731
    aa = D['actuator_armed']
    ta = T(aa['timestamp'])
    arm = aa['armed'].astype(bool)
    dis = [ta[k] for k in range(1, len(ta)) if arm[k - 1] and not arm[k]]
    if not dis:
        P('log %d: no disarm' % i)
        continue
    td = dis[-1]
    ld = D['vehicle_land_detected']
    tl = T(ld['timestamp'])

    def last_rise(f):
        x = ld[f].astype(bool)
        r = [tl[k] for k in range(1, len(tl)) if x[k] and not x[k - 1] and tl[k] <= td + 0.01]
        return round(float(td - r[-1]), 2) if r else None
    ds = D['distance_sensor']
    tds = T(ds['timestamp'])
    near = ' '.join('%.1f:%.2f' % (a, b) for a, b in zip(tds, ds['current_distance']) if td - 16 <= a <= td)
    vs = D['vehicle_status']
    nav = [int(n) for a, n in zip(T(vs['timestamp']), vs['nav_state']) if a <= td][-1]
    P('log %d: disarm at %.2f s, mode %s; disarm minus ground_contact %s, maybe_landed %s, landed %s; range t:m %s' % (
        i, td, A.NAV.get(nav, nav), last_rise('ground_contact'), last_rise('maybe_landed'), last_rise('landed'), near))

# 4
P('')
P('== 4. Steady flight 147-148: in air, h(range) >= 0.5 m, |vz| <= 0.3 m/s, tilt <= 10 deg, runs >= 3 s')
for i in (147, 148):
    u = ulog(i, A.TOPICS)
    t0 = u.start_timestamp
    S = lambda a: (np.asarray(a, float) - t0) / 1e6  # noqa: E731
    T = lambda n: A.topic(u, n)  # noqa: E731
    lp = T('vehicle_local_position')
    tl = S(lp['timestamp'])
    vs = T('vehicle_status')
    ld = T('vehicle_land_detected')
    air = A.step_at(S(vs['timestamp']), vs['arming_state'] == 2, tl).astype(bool) & \
        ~A.step_at(S(ld['timestamp']), ld['landed'], tl).astype(bool)
    db = lp['dist_bottom'].astype(float)
    h = db - np.median(db[~air][:20])
    att = T('vehicle_attitude')
    ta = S(att['timestamp'])
    r, p = A.euler(att['q[0]'], att['q[1]'], att['q[2]'], att['q[3]'])
    tilt = np.degrees(np.interp(tl, ta, np.hypot(r, p)))
    w = A.runs(air & (h >= 0.5) & (np.abs(lp['vz']) <= 0.3) & (tilt <= 10), tl, 3.0)
    am = A.in_windows(ta, w)
    sp = T('vehicle_attitude_setpoint')
    ts = S(sp['timestamp'])
    rs, ps = A.euler(sp['q_d[0]'], sp['q_d[1]'], sp['q_d[2]'], sp['q_d[3]'])
    er = np.degrees(np.interp(ta[am], ts, rs) - r[am])
    ep = np.degrees(np.interp(ta[am], ts, ps) - p[am])
    th = T('vehicle_thrust_setpoint')
    tt = S(th['timestamp'])
    hte = T('hover_thrust_estimate')
    th_ = S(hte['timestamp'])
    ok = hte['valid'] > 0
    a0, a1 = tl[air][0], tl[air][-1]
    P('log %d: %.1f s in %d windows; attitude error std roll %.2f pitch %.2f deg, p95 |e| roll %.2f pitch %.2f deg; '
      'thrust median %.3f; hover-thrust estimate first 60 s %.3f, last 60 s %.3f' % (
          i, sum(b - a for a, b in w), len(w), np.std(er), np.std(ep), np.percentile(np.abs(er), 95),
          np.percentile(np.abs(ep), 95), np.median(-th['xyz[2]'][A.in_windows(tt, w)]),
          np.median(hte['hover_thrust'][ok & (th_ > a0) & (th_ < a0 + 60)]),
          np.median(hte['hover_thrust'][ok & (th_ > a1 - 60) & (th_ < a1)])))

# 5
P('')
P('== 5. PX4 source (same commit as the drone firmware): when optical flow may start')
px4 = os.path.expanduser('~/PX4-Autopilot')
head = subprocess.run(['git', '-C', px4, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
P('~/PX4-Autopilot HEAD %s (logs ver_sw 94cb2012792b2ae89f0b147cfee53ee31ae550be)' % head)
ek = os.path.join(px4, 'src/modules/ekf2/EKF')
for rel, a, b in (('aid_sources/optical_flow/optical_flow_control.cpp', 147, 160),
                  ('aid_sources/range_finder/range_height_control.cpp', 129, 160),
                  ('terrain_control.cpp', 119, 133)):
    src = open(os.path.join(ek, rel)).read().splitlines()
    P('--- %s:%d-%d' % (rel, a, b))
    for n in range(a, b + 1):
        P('%5d %s' % (n, src[n - 1]))

open(OUT, 'w').write('\n'.join(lines) + '\n')
print('\n'.join(lines))
