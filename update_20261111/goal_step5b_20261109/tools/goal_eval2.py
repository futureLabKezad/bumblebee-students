#!/usr/bin/env python3
"""goal_eval2.py - goal step 5b (Claude, 09.11.2026). SIMULATOR ONLY, reads files only.

Evaluator for the marker scenarios, from Gazebo GROUND TRUTH (ULog vehicle_local_position_groundtruth), not from the
drone's own estimate. goal_eval.py (step 5) stays as it is and still runs; this one adds waypoints, path, landing
point, profile (F3), RTF, parity and run validity. It MEASURES; the С numbers it prints are the PROPOSED criteria of
05.11 (section 1 of РАЗБОР_И_ПУТЬ_К_ЦЕЛИ_20261105.md, not approved yet, question 3), copied unchanged; every verdict is
"пробно, не в зачёт" (trial, not counted).

Frames (fixed before the runs):
  world      Gazebo world, ENU. GZBridge ground truth NED = (world y, world x, -world z): Xw = gt.y, Yw = gt.x, Zw = -gt.z.
  marker map the frame of the image's map (aruco_pose/map/map.txt = /work/sim/worlds/aruco_map/map.input.txt).
             world -> map comes from the WORLD FILE of the run (RUN/world.sdf: <include> of model://aruco_N with
             its pose) and the map file: 2D rigid fit (rotation + shift) of the 20 marker centres, residuals printed;
             z_map = Zw + dz with dz = mean(map z - world z of the markers).
  EKF frame  what the script calls 'map' (fly_to -> navigate_wait(frame_id='map'), drone.py:2068-2073): the PX4 local
             frame as MAVROS gives it, ENU: x = lp.y, y = lp.x, z = -lp.z (vehicle_local_position).
Definitions:
  h          Zw minus its median over the first 1.0 s of the log (the log starts at arming, vehicle on the floor).
  in air     armed and not landed (vehicle_land_detected).
  took off   h_max >= 0.20 m while in air.
  waypoint   each '=== FLY TO (x, y, z) ===' line of script.log, in order (the script's own targets, EKF frame).
             reached = first time after the previous one with EKF 3D distance to the target < the script's
             tolerance (the script's own test, navigate_wait, drone.py:1999). Measured over the 1.0 s after reach
             (the script hovers >= 1 s there): mean ground-truth position in the marker map.
             intended point = the same (x, y) in the MARKER MAP (the script's author means markers: 'cruises over
             marker 2 at (0, 1.4)'); intended height = script height above the start (takeoff(height=H)).
  path       per leg, max horizontal distance of the ground-truth path from the straight segment between the
             intended points (marker map; leg 1 starts at marker 0 = (0, 0) for the marker scripts, at the start
             point for others), and from the segment between the two measured waypoint positions (shape only).
  hold       per waypoint window: max and std of the horizontal distance to the window mean.
  touchdown  last downward crossing of h = 0.05 m before the last disarm; landing point = ground truth there.
             intended landing: marker 0 (0, 0) for flight_marker*.py (safe_land(x=0, y=0)), the start point for
             flight.py (safe_land(x=start_x, y=start_y)) and for unknown scripts.
  motors off actuator_armed true -> false; delay = motors off - touchdown.
  failsafe   vehicle_status.failsafe while armed; nav_state sequence; PX4 messages of level WARNING or worse.
Proposed criteria used for the trial verdict lines (unchanged copy):
  С5: |flight height - script height| <= 0.10 m; motors off <= 3.0 s after touchdown; no failsafe.
  С7: every point <= 0.25 m from the script's route point; landing <= 0.15 m from marker 0; no interruption.
Validity (unchanged rule): RTF >= 0.20 (min of rtf.txt), clock check ok, C2 parity unexplained 0 is reported.
Usage: python3 -I goal_eval2.py RUN_DIR --script NAME --script-height H [--ulog ULG]
Writes RUN_DIR/goal_eval2.json and goal_eval2.txt (refuses to overwrite).
"""
import json
import math
import os
import re
import statistics
import sys

import numpy as np

PROPOSED = {'C5_height_tol_m': 0.10, 'C5_motors_off_s': 3.0, 'C7_point_m': 0.25, 'C7_landing_m': 0.15}
NAV = {0: 'MANUAL', 1: 'ALTCTL', 2: 'POSCTL', 3: 'MISSION', 4: 'LOITER', 5: 'RTL', 10: 'ACRO', 12: 'DESCEND',
       13: 'TERMINATION', 14: 'OFFBOARD', 15: 'STAB', 17: 'TAKEOFF', 18: 'LAND', 20: 'PRECLAND'}
MAP_FILE = '/work/sim/worlds/aruco_map/map.input.txt'
MARKER_SCRIPTS = ('flight_marker.py', 'flight_marker_loop.py')


def rd(x, n=3):
    return None if x is None else round(float(x), n)


def world_to_map(world_sdf, map_file):
    world = {}
    s = open(world_sdf, encoding='utf-8').read()
    for mid, x, y, z, r, p, yaw in re.findall(
            r'<include>\s*<uri>model://aruco_(\d+)</uri>\s*<pose>(\S+) (\S+) (\S+) (\S+) (\S+) (\S+)</pose>\s*</include>', s):
        world[int(mid)] = (float(x), float(y), float(z), float(yaw))
    mp = {}
    for line in open(map_file, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        f = line.split()
        mp[int(f[0])] = (float(f[2]), float(f[3]), float(f[4]), float(f[5]), float(f[1]))
    ids = sorted(set(world) & set(mp))
    A = np.array([world[i][:2] for i in ids])
    Bm = np.array([mp[i][:2] for i in ids])
    ca, cb = A.mean(0), Bm.mean(0)
    H = (A - ca).T @ (Bm - cb)
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[1] *= -1
        R = Vt.T @ U.T
    t = cb - R @ ca
    res = np.linalg.norm((A @ R.T + t) - Bm, axis=1)
    dz = float(np.mean([mp[i][2] - world[i][2] for i in ids]))
    yaw_diff = max(abs(math.remainder(mp[i][3] - world[i][3], 2 * math.pi)) for i in ids)
    return {'R': R, 't': t, 'dz': dz, 'n_markers': len(ids), 'rot_deg': math.degrees(math.atan2(R[1, 0], R[0, 0])),
            'shift_m': t.tolist(), 'max_residual_m': float(res.max()), 'max_marker_yaw_diff_rad': yaw_diff,
            'only_in_world': sorted(set(world) - set(mp)), 'only_in_map': sorted(set(mp) - set(world))}


def topic(u, name, mid=0):
    for d in u.data_list:
        if d.name == name and d.multi_id == mid:
            return d.data
    return None


def seg_dist(P, a, b):
    """distance of each point of P (N,2) to segment a-b"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-12:
        return np.linalg.norm(P - a, axis=1)
    u = np.clip(((P - a) @ ab) / L2, 0, 1)
    return np.linalg.norm(P - (a + np.outer(u, ab)), axis=1)


def parse_script_log(path):
    out = {'fly_to': [], 'takeoff_h': None, 'precision_approach': None, 'profile': None, 'profile_missing': [],
           'events': [], 'landed_line': False, 'start_xy_ekf': None}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        m = re.search(r'=== FLY TO \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\) ===', line)
        if m:
            out['fly_to'].append(tuple(float(v) for v in m.groups()))
        m = re.search(r'=== TAKEOFF to ([\d.]+)m ===', line)
        if m:
            out['takeoff_h'] = float(m.group(1))
        m = re.search(r'Precision approach to \((-?[\d.]+), (-?[\d.]+)\)', line)
        if m:
            out['precision_approach'] = (float(m.group(1)), float(m.group(2)))
        m = re.search(r"Flight profile '(\w+)': (\d+)/(\d+) params applied", line)
        if m:
            out['profile'] = {'name': m.group(1), 'applied': int(m.group(2)), 'total': int(m.group(3))}
        m = re.search(r'(WARN|ERR)\s+(\w+)=(\S+) (rejected|raised)(.*)', line)
        if m and ('final' in m.group(5) or m.group(1) == 'ERR' or 'pass' not in m.group(5)):
            out['profile_missing'].append({'name': m.group(2), 'why': (m.group(4) + m.group(5)).strip()[:160]})
        m = re.search(r'\[START\] x=(-?[\d.]+) y=(-?[\d.]+) z=(-?[\d.]+)', line)
        if m:
            out['start_xy_ekf'] = (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        if line.strip() == 'Landed and disarmed.':
            out['landed_line'] = True
        if re.search(r'PREFLIGHT FAIL|ERROR|aborting|abort|NOT reached|failed|vision silent|Vision lost|'
                     r'Traceback|Error|CRITICAL|TIMEOUT|refused|pilot/failsafe|unhealthy|Interrupt', line):
            out['events'].append(line.strip()[:200])
    return out


def main():
    args = sys.argv[1:]
    run = args[0]
    script = args[args.index('--script') + 1]
    script_h = float(args[args.index('--script-height') + 1])
    ulg = args[args.index('--ulog') + 1] if '--ulog' in args else None
    outj, outt = os.path.join(run, 'goal_eval2.json'), os.path.join(run, 'goal_eval2.txt')
    for p in (outj, outt):
        if os.path.exists(p):
            sys.exit('refusing to overwrite ' + p)
    name = os.path.basename(script)
    res = {'run': os.path.basename(run.rstrip('/')), 'script': name, 'script_height_m': script_h,
           'criteria_status': 'PROPOSED 05.11, not approved (question 3); trial run: пробно, не в зачёт',
           'proposed_criteria': PROPOSED}
    # ---- stand files: RTF, clock, parity, options, script end, stand-in, map written
    rtf = []
    if os.path.exists(os.path.join(run, 'rtf.txt')):
        for line in open(os.path.join(run, 'rtf.txt')):
            m = re.search(r'real_time_factor: ([\d.eE+-]+)', line)
            if m:
                rtf.append(float(m.group(1)))
    res['rtf'] = {'samples': len(rtf), 'min': rd(min(rtf)) if rtf else None,
                  'median': rd(statistics.median(rtf)) if rtf else None}
    clock_ok = None
    try:
        clock_ok = json.loads(open(os.path.join(run, 'clock_check.txt')).read().strip().splitlines()[-1]).get('ok')
    except (OSError, ValueError, IndexError):
        pass
    res['clock_ok'] = clock_ok
    unexplained = None
    try:
        unexplained = len(json.load(open(os.path.join(run, 'parity.json')))['summary']['unexplained'])
    except (OSError, ValueError, KeyError):
        pass
    res['c2_parity_unexplained'] = unexplained
    valid_reasons = []
    if not rtf:
        valid_reasons.append('no RTF samples')
    elif min(rtf) < 0.20:
        valid_reasons.append('RTF min %.3f < 0.20' % min(rtf))
    if clock_ok is not True:
        valid_reasons.append('clock check not ok (%s)' % clock_ok)
    res['valid'] = not valid_reasons
    res['invalid_reasons'] = valid_reasons
    for fname, key in (('run_options.json', 'run_options'), ('trial_runner.json', 'trial_runner')):
        try:
            res[key] = json.load(open(os.path.join(run, fname)))
        except (OSError, ValueError):
            res[key] = None
    try:
        res['script_end'] = open(os.path.join(run, 'script_end.txt')).read().strip()
    except OSError:
        res['script_end'] = None
    calls = []
    try:
        calls = [json.loads(l) for l in open(os.path.join(run, 'standin_pkill.jsonl')) if l.strip()]
    except (OSError, ValueError):
        pass
    res['pkill_standin_calls'] = [{'argv': c.get('argv'), 'exit': c.get('exit'), 'signalled': c.get('signalled'),
                                   'matched_outside_untouched': len(c.get('matched_outside_session_untouched', []))}
                                  for c in calls]
    wm = os.path.join(run, 'aruco_map_written', 'map.txt')
    if os.path.exists(wm):
        import hashlib
        s_w = hashlib.sha256(open(wm, 'rb').read()).hexdigest()
        s_i = hashlib.sha256(open(MAP_FILE, 'rb').read()).hexdigest()
        res['map_written'] = {'sha256': s_w, 'image_map_sha256': s_i, 'identical_to_image_map': s_w == s_i}
    # ---- script log
    sl = parse_script_log(os.path.join(run, 'script.log'))
    res['profile'] = sl['profile']
    res['profile_missing'] = sl['profile_missing']
    res['script_events'] = sl['events'][:40]
    res['fly_to_targets_ekf'] = sl['fly_to']
    # ---- world -> marker map
    T = world_to_map(os.path.join(run, 'world.sdf'), MAP_FILE)
    res['world_to_map'] = {k: (rd(v, 4) if isinstance(v, float) else v) for k, v in T.items() if k not in ('R', 't')}
    if ulg is None or not os.path.exists(ulg):
        res['ulog'] = None
        res['took_off'] = False
        res['note'] = 'no ULog: never armed'
        write(res, outj, outt)
        return
    from pyulog import ULog
    u = ULog(ulg)
    t0 = u.start_timestamp
    gt, st, ld, aa, lp = (topic(u, n) for n in ('vehicle_local_position_groundtruth', 'vehicle_status',
                                                  'vehicle_land_detected', 'actuator_armed', 'vehicle_local_position'))
    res['ulog'] = os.path.basename(ulg)
    # timestamps as signed numbers: some topics have samples a little BEFORE the log start (uint64 would wrap)
    sec = lambda a: (np.asarray(a).astype(np.int64) - np.int64(t0)) / 1e6  # noqa: E731
    order = np.argsort(sec(gt['timestamp']), kind='stable')
    gt = {k: v[order] for k, v in gt.items()}
    t = sec(gt['timestamp'])
    Pw = np.column_stack([gt['y'], gt['x']])
    Pm = Pw @ T['R'].T + T['t']
    Zw = -gt['z']
    Zm = Zw + T['dz']
    z0 = float(np.median(Zw[t <= 1.0]))
    h = Zw - z0
    armed = np.interp(gt['timestamp'], aa['timestamp'], aa['armed'].astype(float)) > 0.5
    landed = np.interp(gt['timestamp'], ld['timestamp'], ld['landed'].astype(float), left=1) > 0.5
    air = armed & ~landed
    start_m = Pm[t <= 1.0].mean(0)
    res['start_marker_map_xy'] = [rd(start_m[0]), rd(start_m[1])]
    res['start_base_link_z_marker_map'] = rd(float(np.median(Zm[t <= 1.0])))
    res['h_max_m'] = rd(h[air].max() if air.any() else h.max())
    res['took_off'] = bool(air.any() and h[air].max() >= 0.20)
    res['air_s'] = rd(float(np.sum(np.diff(t)[air[:-1]])), 1)
    # EKF frame (what the script calls 'map')
    lo = np.argsort(sec(lp['timestamp']), kind='stable')
    lp = {k: v[lo] for k, v in lp.items()}
    lt = sec(lp['timestamp'])
    E = np.column_stack([lp['y'], lp['x'], -lp['z']])
    ekf_at = lambda tt: np.array([np.interp(tt, lt, E[:, k]) for k in range(3)])  # noqa: E731
    gt_m_at = lambda tt: np.array([np.interp(tt, t, Pm[:, 0]), np.interp(tt, t, Pm[:, 1]), np.interp(tt, t, h)])  # noqa: E731
    e0 = ekf_at(0.0)
    res['ekf_at_arm_xyz'] = [rd(v) for v in e0]
    res['ekf_frame_offset_at_arm_xy'] = [rd(start_m[0] - e0[0]), rd(start_m[1] - e0[1])]
    if air.sum() > 50:
        ta = t[air]
        Ea = np.column_stack([np.interp(ta, lt, E[:, 0]), np.interp(ta, lt, E[:, 1])])
        Ga = Pm[air]
        Ec, Gc = Ea - Ea.mean(0), Ga - Ga.mean(0)
        Hm = Ec.T @ Gc
        Uu, _, Vv = np.linalg.svd(Hm)
        Rr = Vv.T @ Uu.T
        if np.linalg.det(Rr) < 0:
            Vv[1] *= -1
            Rr = Vv.T @ Uu.T
        spread = float(np.sqrt(np.mean(np.sum(Gc ** 2, 1))))
        res['truth_xy_spread_in_air_m'] = rd(spread)
        if spread >= 0.30:   # a rotation fit needs real horizontal motion; a hover in place gives noise only
            res['ekf_to_marker_map_rotation_deg_in_air'] = rd(math.degrees(math.atan2(Rr[1, 0], Rr[0, 0])), 1)
            res['ekf_vs_truth_xy_rms_after_best_fit_m'] = rd(float(np.sqrt(np.mean(np.sum((Ec @ Rr.T - Gc) ** 2, 1)))))
        else:
            res['ekf_to_marker_map_rotation_deg_in_air'] = 'not determinable (horizontal spread < 0.30 m)'
        res['ekf_minus_truth_max_xy_m_in_air'] = rd(float(np.max(np.linalg.norm(
            (Ea - Ea[0]) - (Ga - Ga[0]), axis=1))))
    # main hover (as goal_eval.py)
    vz = gt['vz']
    mask = air & (np.abs(vz) <= 0.10) & (h >= 0.3)
    best, start, run_ = None, None, []
    for i, mm in enumerate(mask):
        if mm and start is None:
            start = i
        if (not mm or i == len(mask) - 1) and start is not None:
            end = i if not mm else i + 1
            if t[end - 1] - t[start] >= 3.0:
                run_.append((start, end))
            start = None
    if run_:
        s0, s1 = max(run_, key=lambda r: t[r[1] - 1] - t[r[0]])
        sel = (t >= t[s0] + 1.0) & (t <= t[s1 - 1] - 1.0)
        if sel.any():
            res['main_hover'] = {'from_s': rd(t[s0], 1), 'len_s': rd(t[s1 - 1] - t[s0], 1),
                                 'h_mean_m': rd(h[sel].mean()), 'h_std_m': rd(h[sel].std()),
                                 'xy_max_dev_m': rd(np.max(np.linalg.norm(Pm[sel] - Pm[sel].mean(0), axis=1)))}
            res['flight_height_m'] = res['main_hover']['h_mean_m']
            res['flight_height_err_m'] = rd(res['main_hover']['h_mean_m'] - script_h)
    # waypoints
    tol = 0.25
    is_marker = name in MARKER_SCRIPTS
    wps = []
    t_prev = 0.0
    takeoff_reach = None
    if sl['takeoff_h'] is not None:
        # takeoff target = EKF position at arm + H (drone.takeoff: navigate_wait to (x, y, z + height), tolerance 0.15)
        tgt = e0 + np.array([0, 0, sl['takeoff_h']])
        d = np.linalg.norm(E - tgt, axis=1)
        idx = np.where((lt > 0) & (d < 0.15))[0]
        takeoff_reach = float(lt[idx[0]]) if len(idx) else None
        res['takeoff'] = {'target_h_m': sl['takeoff_h'], 'reached_s': rd(takeoff_reach, 2),
                          'h_at_reach_m': rd(gt_m_at(takeoff_reach)[2]) if takeoff_reach is not None else None}
        if takeoff_reach is not None:
            t_prev = takeoff_reach
    intended_prev = np.array([0.0, 0.0]) if is_marker else start_m.copy()
    measured_prev = gt_m_at(t_prev)[:2] if takeoff_reach is not None else start_m.copy()
    ekf_prev = e0[:2].copy()
    for k, (x, y, z) in enumerate(sl['fly_to']):
        tgt = np.array([x, y, z])
        d = np.linalg.norm(E - tgt, axis=1)
        idx = np.where((lt > t_prev + 0.2) & (d < tol))[0]
        w = {'n': k + 1, 'target_ekf': [x, y, z], 'intended_marker_map_xy': [x, y], 'reached': bool(len(idx))}
        if len(idx):
            tr = float(lt[idx[0]])
            win = (t >= tr) & (t <= tr + 1.0)
            pm = Pm[win].mean(0)
            hm = float(h[win].mean())
            w.update({'reached_s': rd(tr, 2), 'measured_marker_map_xy': [rd(pm[0]), rd(pm[1])],
                      'h_m': rd(hm), 'horiz_err_m': rd(np.hypot(pm[0] - x, pm[1] - y)),
                      'vert_err_vs_script_height_m': rd(hm - script_h),
                      'hold_max_dev_m': rd(np.max(np.linalg.norm(Pm[win] - pm, axis=1))),
                      'hold_std_m': rd(float(np.sqrt(np.mean(np.sum((Pm[win] - pm) ** 2, 1))))),
                      'ekf_err_to_own_target_m': rd(np.linalg.norm(ekf_at(tr + 0.5)[:2] - tgt[:2]))})
            leg = (t >= t_prev) & (t <= tr)
            if leg.sum() > 2:
                w['leg_max_dev_from_intended_line_m'] = rd(seg_dist(Pm[leg], intended_prev, [x, y]).max())
                w['leg_max_dev_from_measured_line_m'] = rd(seg_dist(Pm[leg], measured_prev, pm).max())
                le = (lt >= t_prev) & (lt <= tr)
                if le.sum() > 2:
                    w['leg_ekf_max_dev_from_own_line_m'] = rd(seg_dist(E[le][:, :2], ekf_prev, tgt[:2]).max())
            t_prev, measured_prev, ekf_prev = tr, pm, tgt[:2]
        intended_prev = np.array([x, y])
        wps.append(w)
        if not len(idx):
            break
    res['waypoints'] = wps
    res['waypoints_planned_in_log'] = len(sl['fly_to'])
    # touchdown / motors off / landing point
    arm_t = sec(aa['timestamp'])
    offs = np.where(aa['armed'][:-1].astype(bool) & ~aa['armed'][1:].astype(bool))[0]
    t_off = float(arm_t[offs[-1] + 1]) if len(offs) else None
    down = np.where((h[:-1] >= 0.05) & (h[1:] < 0.05))[0]
    down = down[t[down + 1] <= (t_off if t_off is not None else 1e9)]
    t_td = float(t[down[-1] + 1]) if len(down) else None
    res['touchdown_s'], res['motors_off_s'] = rd(t_td, 2), rd(t_off, 2)
    res['motors_off_after_touchdown_s'] = rd(t_off - t_td, 2) if (t_td is not None and t_off is not None) else None
    res['arm_to_disarm_s'] = rd(t_off, 1) if t_off is not None else None
    if t_td is not None:
        lp_xy = gt_m_at(t_td)[:2]
        intended_land = np.array([0.0, 0.0]) if is_marker else start_m
        res['landing'] = {'touchdown_marker_map_xy': [rd(lp_xy[0]), rd(lp_xy[1])],
                          'intended_xy': [rd(intended_land[0]), rd(intended_land[1])],
                          'intended_is': 'marker 0' if is_marker else 'start point',
                          'error_m': rd(np.linalg.norm(lp_xy - intended_land))}
    # failsafe, modes, PX4 messages
    seq, last = [], None
    for ts, ns, fs in zip(st['timestamp'], st['nav_state'], st['failsafe']):
        key = (int(ns), int(fs))
        if key != last:
            seq.append({'t_s': rd((int(ts) - int(t0)) / 1e6, 2), 'nav': NAV.get(int(ns), int(ns)), 'failsafe': bool(fs)})
            last = key
    res['nav_sequence'] = seq
    st_armed = np.interp(st['timestamp'], aa['timestamp'], aa['armed'].astype(float)) > 0.5
    res['failsafe_while_armed'] = bool(np.any(st['failsafe'].astype(bool) & st_armed))
    msgs = []
    for m in u.logged_messages:
        lvl = m.log_level if isinstance(m.log_level, int) else int(str(m.log_level)[-1])
        if lvl <= 4:
            msgs.append({'t_s': rd((int(m.timestamp) - int(t0)) / 1e6, 2), 'level': lvl, 'text': m.message.strip()[:160]})
    res['px4_warnings'] = msgs[:40]
    all_msgs = [m.message.strip() for m in u.logged_messages]
    res['kill_engaged'] = any('Kill engaged' in m for m in all_msgs)
    res['px4_messages_all'] = [{'t_s': rd((int(m.timestamp) - int(t0)) / 1e6, 2), 'text': m.message.strip()[:120]}
                               for m in u.logged_messages][:60]
    # trial verdicts against the PROPOSED numbers
    v = {}
    if name == 'flight.py' or not is_marker:
        if 'flight_height_err_m' in res:
            v['C5_height'] = abs(res['flight_height_err_m']) <= PROPOSED['C5_height_tol_m']
        v['C5_motors_off'] = (res['motors_off_after_touchdown_s'] is not None
                              and res['motors_off_after_touchdown_s'] <= PROPOSED['C5_motors_off_s'])
        v['C5_no_failsafe'] = not res['failsafe_while_armed'] and not res['kill_engaged']
    if is_marker:
        reached = [w for w in wps if w['reached']]
        v['C7_all_waypoints_reached'] = len(reached) == res['waypoints_planned_in_log'] and len(reached) > 0
        v['C7_points_within_0.25m'] = bool(reached) and all(w['horiz_err_m'] <= PROPOSED['C7_point_m'] for w in reached)
        v['C7_landing_within_0.15m'] = 'landing' in res and res['landing']['error_m'] <= PROPOSED['C7_landing_m']
        v['C7_no_failsafe'] = not res['failsafe_while_armed'] and not res['kill_engaged']
    res['verdict_vs_proposed_trial'] = v
    write(res, outj, outt)


def write(res, outj, outt):
    with open(outj, 'x', encoding='utf-8') as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    L = []
    L.append('criteria: ' + res['criteria_status'])
    L.append('valid: %s %s; RTF min %s median %s; clock ok %s; C2 parity unexplained %s' % (
        res['valid'], res['invalid_reasons'], res['rtf']['min'], res['rtf']['median'], res['clock_ok'],
        res['c2_parity_unexplained']))
    p = res.get('profile')
    L.append('profile: %s; missing: %s' % ('%s %d/%d' % (p['name'], p['applied'], p['total']) if p else None,
                                            [m['name'] for m in res.get('profile_missing', [])]))
    if res.get('map_written'):
        L.append('map written by set_aruco_map identical to image map.txt: %s' % res['map_written']['identical_to_image_map'])
    if res.get('pkill_standin_calls'):
        L.append('pkill stand-in calls: %s' % json.dumps(res['pkill_standin_calls']))
    L.append('world->marker map: rot %.3f deg, shift %s, max residual %.4f m, dz %.3f m, markers %d' % (
        res['world_to_map']['rot_deg'], res['world_to_map']['shift_m'], res['world_to_map']['max_residual_m'],
        res['world_to_map']['dz'], res['world_to_map']['n_markers']))
    L.append('script end: %s' % res.get('script_end'))
    if res.get('ulog'):
        L.append('took off %s; h max %s m; air %s s; flight height %s m (err %s vs %s); start (marker map) %s' % (
            res['took_off'], res['h_max_m'], res['air_s'], res.get('flight_height_m'), res.get('flight_height_err_m'),
            res['script_height_m'], res['start_marker_map_xy']))
        L.append('EKF at arm %s; EKF frame offset to marker map at arm %s; EKF->map rotation in air %s deg' % (
            res['ekf_at_arm_xyz'], res['ekf_frame_offset_at_arm_xy'], res.get('ekf_to_marker_map_rotation_deg_in_air')))
        for w in res.get('waypoints', []):
            if w['reached']:
                L.append('  wp%d target %s -> measured %s err %.3f m (vert %+.3f), hold max %.3f, leg dev %s / shape %s / ekf own %s, reached %.1f s' % (
                    w['n'], w['intended_marker_map_xy'], w['measured_marker_map_xy'], w['horiz_err_m'],
                    w['vert_err_vs_script_height_m'], w['hold_max_dev_m'], w.get('leg_max_dev_from_intended_line_m'),
                    w.get('leg_max_dev_from_measured_line_m'), w.get('leg_ekf_max_dev_from_own_line_m'), w['reached_s']))
            else:
                L.append('  wp%d target %s NOT reached' % (w['n'], w['intended_marker_map_xy']))
        L.append('landing %s' % json.dumps(res.get('landing')))
        L.append('touchdown %s s, motors off %s s, delay %s s; arm->disarm %s s; failsafe while armed %s; kill %s' % (
            res['touchdown_s'], res['motors_off_s'], res['motors_off_after_touchdown_s'], res['arm_to_disarm_s'],
            res['failsafe_while_armed'], res['kill_engaged']))
        L.append('nav: ' + ' -> '.join('%s%s@%s' % (s['nav'], '(FS)' if s['failsafe'] else '', s['t_s'])
                                       for s in res['nav_sequence']))
        L.append('PX4 warnings: %s' % json.dumps([m['text'] for m in res['px4_warnings']], ensure_ascii=False))
    L.append('script events: %s' % json.dumps(res.get('script_events', [])[:12], ensure_ascii=False))
    L.append('verdict vs PROPOSED (пробно, не в зачёт): %s' % json.dumps(res.get('verdict_vs_proposed_trial', {})))
    with open(outt, 'x', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
