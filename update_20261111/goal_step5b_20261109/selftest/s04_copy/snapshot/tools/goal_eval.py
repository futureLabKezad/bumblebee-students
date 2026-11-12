#!/usr/bin/env python3
"""goal_eval.py - goal step 5 (Claude, 06.11.2026). SIMULATOR ONLY, reads files only.

ONE evaluator for the goal scenarios (section 7 of РАЗБОР_И_ПУТЬ_К_ЦЕЛИ_20261105.md), from Gazebo ground truth in the
PX4 ULog (vehicle_local_position_groundtruth; GZBridge publishes NED = (world y, world x, -world z), absolute world frame).
It MEASURES; the pass/fail numbers are the criteria of section 1 as PROPOSED 05.11 (not yet approved by the owner,
question 3). They are copied here unchanged and are never edited to fit a result.

Definitions (fixed before any scenario run):
  world        Xw = gt.y, Yw = gt.x, Zw = -gt.z (metres, Gazebo world frame = marker world frame).
  h            Zw minus its median in the first 1.0 s of the log (the log starts at arming, vehicle on the floor).
  in air       actuator_armed.armed and vehicle_land_detected.landed False.
  hover        runs of >= 3 s in air with |vz_gt| <= 0.10 m/s and h >= 0.3 m, trimmed 1.0 s at both ends.
  main hover   the longest hover run; its mean h is the "flight height".
  touchdown    last downward crossing of h = 0.05 m before the disarm; motors off = actuator_armed.armed -> False.
  failsafe     vehicle_status.failsafe True at any time while armed (also listed: nav_state changes, kill, messages).
  C6 hover     (with --marker X Y): horizontal distance of (Xw, Yw) to the marker centre during the main hover;
               p95 and max; also jumps of the EKF position > 0.10 m between consecutive samples (vehicle_local_position).
Proposed criteria used for the verdict lines (section 1, 05.11):
  C5: |flight height - script height| <= 0.10 m; motors off <= 3.0 s after touchdown; no failsafe.
  C6: p95 horizontal <= 0.10 m and max <= 0.20 m; |h - 1.0| <= 0.10 m (as p95); no EKF jump > 0.10 m.
Usage: python3 -I goal_eval.py RUN_DIR ULOG --script-height H [--marker X Y] [--out-suffix S]
Writes RUN_DIR/goal_eval<S>.json and .txt (refuses to overwrite).
"""
import json
import os
import sys

import numpy as np
from pyulog import ULog

NAV = {0: 'MANUAL', 1: 'ALTCTL', 2: 'POSCTL', 3: 'MISSION', 4: 'LOITER', 5: 'RTL', 10: 'ACRO', 12: 'DESCEND',
       13: 'TERMINATION', 14: 'OFFBOARD', 15: 'STAB', 17: 'TAKEOFF', 18: 'LAND', 20: 'PRECLAND'}
PROPOSED = {'C5_height_tol_m': 0.10, 'C5_motors_off_s': 3.0,
            'C6_p95_m': 0.10, 'C6_max_m': 0.20, 'C6_height_tol_m': 0.10, 'C6_jump_m': 0.10}


def topic(u, name, mid=0):
    for d in u.data_list:
        if d.name == name and d.multi_id == mid:
            return d.data
    return None


def runs(mask, t, min_s, trim):
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if (not m or i == len(mask) - 1) and start is not None:
            end = i if not m else i + 1
            if t[end - 1] - t[start] >= min_s:
                sel = np.zeros(len(mask), dtype=bool)
                sel[start:end] = (t[start:end] >= t[start] + trim) & (t[start:end] <= t[end - 1] - trim)
                if sel.any():
                    out.append(sel)
            start = None
    return out


def main():
    args = sys.argv[1:]
    run_dir, ulg = args[0], args[1]
    script_h = float(args[args.index('--script-height') + 1])
    marker = [float(args[args.index('--marker') + 1]), float(args[args.index('--marker') + 2])] if '--marker' in args else None
    sfx = args[args.index('--out-suffix') + 1] if '--out-suffix' in args else ''
    outj, outt = os.path.join(run_dir, f'goal_eval{sfx}.json'), os.path.join(run_dir, f'goal_eval{sfx}.txt')
    for p in (outj, outt):
        if os.path.exists(p):
            sys.exit(f'refusing to overwrite {p}')

    u = ULog(ulg)
    t0 = u.start_timestamp
    gt, st, ld, aa = (topic(u, n) for n in ('vehicle_local_position_groundtruth', 'vehicle_status',
                                              'vehicle_land_detected', 'actuator_armed'))
    lp = topic(u, 'vehicle_local_position')
    t = (gt['timestamp'] - t0) / 1e6
    Xw, Yw, Zw = gt['y'], gt['x'], -gt['z']
    z0 = np.median(Zw[t <= 1.0])
    h = Zw - z0
    armed = np.interp(gt['timestamp'], aa['timestamp'], aa['armed'].astype(float)) > 0.5
    landed = np.interp(gt['timestamp'], ld['timestamp'], ld['landed'].astype(float), left=1) > 0.5
    air = armed & ~landed
    res = {'ulog': os.path.basename(ulg), 'script_height_m': script_h, 'proposed_criteria': PROPOSED,
           'criteria_status': 'PROPOSED 05.11, not approved by the owner (question 3); trial runs do not count',
           'start_world_xy': [round(float(np.median(Xw[t <= 1.0])), 3), round(float(np.median(Yw[t <= 1.0])), 3)],
           'h_max_m': round(float(h.max()), 3), 'air_s': round(float(np.sum(np.diff(t)[air[:-1]])), 1)}
    hov = runs(air & (np.abs(gt['vz']) <= 0.10) & (h >= 0.3), t, 3.0, 1.0)
    res['hover_runs'] = [{'from_s': round(float(t[s][0]), 1), 'len_s': round(float(t[s][-1] - t[s][0]), 1),
                          'h_mean_m': round(float(np.mean(h[s])), 3), 'h_p95_abs_err_m': round(float(np.percentile(np.abs(h[s] - script_h), 95)), 3)}
                         for s in hov]
    main_sel = max(hov, key=lambda s: s.sum()) if hov else None
    if main_sel is not None:
        res['flight_height_m'] = round(float(np.mean(h[main_sel])), 3)
        res['flight_height_err_m'] = round(float(np.mean(h[main_sel]) - script_h), 3)
    # touchdown -> motors off
    arm_t = (aa['timestamp'] - t0) / 1e6
    offs = np.where(aa['armed'][:-1].astype(bool) & ~aa['armed'][1:].astype(bool))[0]
    t_off = float(arm_t[offs[-1] + 1]) if len(offs) else None
    down = np.where((h[:-1] >= 0.05) & (h[1:] < 0.05))[0]
    down = down[t[down + 1] <= (t_off if t_off is not None else 1e9)]
    t_td = float(t[down[-1] + 1]) if len(down) else None
    res['touchdown_s'], res['motors_off_s'] = t_td, t_off
    res['motors_off_after_touchdown_s'] = round(t_off - t_td, 2) if (t_td is not None and t_off is not None) else None
    # failsafe / modes / messages
    seq, last = [], None
    for ts, ns, fs in zip(st['timestamp'], st['nav_state'], st['failsafe']):
        key = (int(ns), int(fs))
        if key != last:
            seq.append({'t_s': round((ts - t0) / 1e6, 2), 'nav': NAV.get(int(ns), int(ns)), 'failsafe': bool(fs)})
            last = key
    res['nav_sequence'] = seq
    st_armed = np.interp(st['timestamp'], aa['timestamp'], aa['armed'].astype(float)) > 0.5
    res['failsafe_while_armed'] = bool(np.any(st['failsafe'].astype(bool) & st_armed))
    res['messages'] = [{'t_s': round((m.timestamp - t0) / 1e6, 2), 'text': m.message.strip()} for m in u.logged_messages][:60]
    res['kill_engaged'] = any('Kill engaged' in m['text'] for m in res['messages'])
    # C6 marker hover
    if marker is not None and main_sel is not None:
        d = np.hypot(Xw[main_sel] - marker[0], Yw[main_sel] - marker[1])
        res['marker_xy'] = marker
        res['marker_dist_p95_m'] = round(float(np.percentile(d, 95)), 3)
        res['marker_dist_max_m'] = round(float(np.max(d)), 3)
        res['hover_len_s'] = round(float(t[main_sel][-1] - t[main_sel][0]), 1)
    if lp is not None:
        lt = (lp['timestamp'] - t0) / 1e6
        jumps = np.hypot(np.diff(lp['x']), np.diff(lp['y']))
        in_air_lp = np.interp(lp['timestamp'][1:], gt['timestamp'], air.astype(float)) > 0.5
        res['ekf_xy_jumps_over_0p10_m'] = int(np.sum((jumps > 0.10) & in_air_lp))
        res['ekf_xy_resets'] = int(lp['xy_reset_counter'][-1] - lp['xy_reset_counter'][0]) if 'xy_reset_counter' in lp else None
    # verdict lines against the PROPOSED numbers (informative only for trial runs)
    v = {}
    if 'flight_height_err_m' in res:
        v['C5_height'] = abs(res['flight_height_err_m']) <= PROPOSED['C5_height_tol_m']
    v['C5_motors_off'] = (res['motors_off_after_touchdown_s'] is not None and res['motors_off_after_touchdown_s'] <= PROPOSED['C5_motors_off_s'])
    v['C5_no_failsafe'] = not res['failsafe_while_armed'] and not res['kill_engaged']
    if 'marker_dist_p95_m' in res:
        v['C6_p95'] = res['marker_dist_p95_m'] <= PROPOSED['C6_p95_m']
        v['C6_max'] = res['marker_dist_max_m'] <= PROPOSED['C6_max_m']
        v['C6_no_jump'] = res.get('ekf_xy_jumps_over_0p10_m', 1) == 0
    res['verdict_vs_proposed'] = v
    json.dump(res, open(outj, 'x'), indent=1)
    with open(outt, 'x') as f:
        f.write(f"criteria: {res['criteria_status']}\n")
        f.write(f"script height {script_h} m; flight height {res.get('flight_height_m')} m (err {res.get('flight_height_err_m')}); "
                f"h max {res['h_max_m']} m; air {res['air_s']} s; hover runs {json.dumps(res['hover_runs'])}\n")
        f.write(f"touchdown {t_td} s, motors off {t_off} s, delta {res['motors_off_after_touchdown_s']} s; "
                f"failsafe while armed {res['failsafe_while_armed']}; kill {res['kill_engaged']}\n")
        if 'marker_dist_p95_m' in res:
            f.write(f"marker {marker}: p95 {res['marker_dist_p95_m']} m, max {res['marker_dist_max_m']} m over {res['hover_len_s']} s\n")
        f.write(f"EKF xy jumps > 0.10 m in air: {res.get('ekf_xy_jumps_over_0p10_m')}; xy resets {res.get('ekf_xy_resets')}\n")
        f.write('nav: ' + ' -> '.join(f"{s['nav']}{'(FS)' if s['failsafe'] else ''}@{s['t_s']}" for s in seq) + '\n')
        f.write(f"verdict vs PROPOSED (trial, not counted): {json.dumps(v)}\n")
    print(open(outt).read(), end='')


if __name__ == '__main__':
    main()
