#!/usr/bin/env python3
"""c6_eval.py - criterion C6 (hover over marker 0) from one Gazebo run. Claude, 09.11.2026. Reads files only.

Numbers: КРИТЕРИИ_УТВЕРЖДЕНЫ_20261109.md (C6), read as in КРИТЕРИИ_ТОЛКОВАНИЯ_20261109.md (C6/Zh4 items 1-3).
Nothing here loosens them; where a rule can be read two ways the stricter reading is used (marked STRICTER).

Input: a run folder of the step-5/5b stand: world.sdf, rootfs/log/*/*.ulg (absent = never armed), script.log,
rtf.txt, clock_check.txt, run_options.json (optional). Marker map: --map (default the stand's map.input.txt).

Frames (as goal_eval2.py of stand 5b): Gazebo ground truth vehicle_local_position_groundtruth (NED) -> world ENU
(x = gt.y, y = gt.x, z = -gt.z) -> marker map by a 2D rigid fit of the marker centres (world.sdf vs map file).
EKF estimate: vehicle_local_position, own frame (only its jumps are used).

Definitions:
  h            truth z minus its median over the first 1.0 s of the log (the log starts at arming, on the floor).
  window       from the first in-air truth sample with |h - 1.0| <= 0.10 m (end of the climb) to the first moment
               after it when the vehicle leaves OFFBOARD (landing, pilot, failsafe) or is disarmed. Item 3.
               STRICTER: safe_land's approach and 1.5 s hold, still in OFFBOARD, stay inside the window.
  offset       horizontal truth distance to the centre of marker 0 (item 1), NOT to the takeoff point.
  share_10cm   time share of the window (each sample weighted by its interval) with offset <= 0.10 m.
  jump a       in the window: (1) an EKF reset: xy_reset_counter grows with |delta_xy| > 0.10 m, or
               (STRICTER, z also) z_reset_counter grows with |delta_z| > 0.10 m; (2) the EKF position (3D) changes
               by > 0.10 m between two samples less than 0.2 s apart (STRICTER: any two samples, not only
               neighbours).
  jump b       in the window: the truth position (3D, STRICTER than horizontal only) moves > 0.10 m within any
               0.5 s. The horizontal-only value is printed as information.
  settling     time from the window start until offset <= 0.10 m and |h - 1.0| <= 0.10 m hold to the window
               end. Reported only: it is not forgiven (all of the window counts).
C6 verdict (all must hold): run valid (RTF >= 0.20, clock ok); took off; window >= 60.0 s; share_10cm >= 0.95;
  max offset <= 0.20 m; max |h - 1.0| <= 0.10 m; no jump a; no jump b; landed and disarmed after the window;
  no emergency = the ONE list shared with C5 and C7 (goal_common.emergencies, readings 09.11 ~10:35 / ~11:00):
  failsafe incl. failsafe_flags turning on while armed, RTL/DESCEND/TERMINATION, Hold not asked by the script,
  AUTO.LAND before the script asked to land, kill, script exit code != 0 / unknown / 137 / 143.
Edition r2 (09.11): no_failsafe + no_kill of r1 (/work/c6_eval_20261109) replaced by that shared no_emergency.
Edition r3 (09.11): script_matches_versions (the run's script = the sha256 in versions.txt, as C5/C7); the shared
  list of goal_common r3 (drone.py guard landings, missing data = not evaluated, Hold by the request log).
Usage: python3 -I c6_eval.py RUN_DIR [--out DIR] [--map MAP] [--ulog ULG]
Writes OUT/c6_eval.json and c6_eval.txt (OUT defaults to RUN_DIR; never overwrites). Exit 0 PASS, 1 FAIL, 2 error.
"""
import glob
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goal_common as G  # noqa: E402

C6 = {'height_m': 1.0, 'height_tol_m': 0.10, 'hover_s': 60.0, 'offset_10cm_m': 0.10, 'share_min': 0.95,
      'offset_max_m': 0.20, 'jump_m': 0.10, 'jump_ekf_dt_s': 0.2, 'jump_truth_dt_s': 0.5}
RTF_MIN = 0.20
MAP_FILE = '/work/sim/worlds/aruco_map/map.input.txt'
OFFBOARD = 14


def rd(x, n=3):
    return None if x is None else round(float(x), n)


# ---------------------------------------------------------------- input
def world_to_map(world_sdf, map_file):
    """2D rigid transform world -> marker map from the marker centres (same method as goal_eval2.py)."""
    world, mp = {}, {}
    s = open(world_sdf, encoding='utf-8').read()
    for mid, x, y, z, _r, _p, yaw in re.findall(
            r'<include>\s*<uri>model://aruco_(\d+)</uri>\s*<pose>(\S+) (\S+) (\S+) (\S+) (\S+) (\S+)</pose>\s*</include>', s):
        world[int(mid)] = (float(x), float(y), float(z))
    for line in open(map_file, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        f = line.split()
        mp[int(f[0])] = (float(f[2]), float(f[3]), float(f[4]))
    ids = sorted(set(world) & set(mp))
    if len(ids) < 2 or 0 not in ids:
        raise ValueError('world/map: need marker 0 and >= 2 common markers, have %s' % ids)
    A = np.array([world[i][:2] for i in ids])
    B = np.array([mp[i][:2] for i in ids])
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[1] *= -1
        R = Vt.T @ U.T
    t = cb - R @ ca
    return {'R': R, 't': t, 'n_markers': len(ids), 'marker0_map_xy': np.array(mp[0][:2]),
            'max_residual_m': float(np.linalg.norm(A @ R.T + t - B, axis=1).max())}


def _topic(u, name):
    for d in u.data_list:
        if d.name == name and d.multi_id == 0:
            return d.data
    raise KeyError('ULog has no topic ' + name)


def load_ulog(ulg, T):
    """ULog -> plain arrays (seconds from log start; truth already in the marker map)."""
    from pyulog import ULog
    u = ULog(ulg)
    t0 = np.int64(u.start_timestamp)
    sec = lambda a: (np.asarray(a).astype(np.int64) - t0) / 1e6  # noqa: E731
    gt, lp, st, aa = (_topic(u, n) for n in ('vehicle_local_position_groundtruth', 'vehicle_local_position',
                                              'vehicle_status', 'actuator_armed'))
    try:
        ld = _topic(u, 'vehicle_land_detected')
    except KeyError:
        ld = None
    o = np.argsort(sec(gt['timestamp']), kind='stable')
    Pw = np.column_stack([gt['y'][o], gt['x'][o]])
    d = {'t': sec(gt['timestamp'])[o], 'xy': Pw @ T['R'].T + T['t'], 'z': -gt['z'][o]}
    o = np.argsort(sec(lp['timestamp']), kind='stable')
    d['ekf_t'] = sec(lp['timestamp'])[o]
    d['ekf_xyz'] = np.column_stack([lp['y'][o], lp['x'][o], -lp['z'][o]])
    d['ekf_xy_reset'] = lp['xy_reset_counter'][o].astype(int)
    d['ekf_delta_xy'] = np.hypot(lp['delta_xy[0]'][o], lp['delta_xy[1]'][o])
    d['ekf_z_reset'] = lp['z_reset_counter'][o].astype(int)
    d['ekf_delta_z'] = np.abs(lp['delta_z'][o])
    d['st_t'] = sec(st['timestamp'])
    d['nav'] = st['nav_state'].astype(int)
    d['failsafe'] = st['failsafe'].astype(bool)
    d['arm_t'] = sec(aa['timestamp'])
    d['armed'] = aa['armed'].astype(bool)
    d['land_t'] = sec(ld['timestamp']) if ld is not None else None
    d['landed'] = ld['landed'].astype(bool) if ld is not None else None
    d['kill'] = any('Kill engaged' in m.message for m in u.logged_messages)
    return d


def stand_validity(run):
    rtf = []
    try:
        for line in open(os.path.join(run, 'rtf.txt')):
            m = re.search(r'real_time_factor: ([\d.eE+-]+)', line)
            if m:
                rtf.append(float(m.group(1)))
    except OSError:
        pass
    clock_ok = None
    try:
        clock_ok = json.loads(open(os.path.join(run, 'clock_check.txt')).read().strip().splitlines()[-1]).get('ok')
    except (OSError, ValueError, IndexError):
        pass
    why = []
    if not rtf:
        why.append('no RTF samples')
    elif min(rtf) < RTF_MIN:
        why.append('RTF min %.3f < %.2f' % (min(rtf), RTF_MIN))
    if clock_ok is not True:
        why.append('clock check not ok (%s)' % clock_ok)
    return {'valid': not why, 'invalid_reasons': why, 'rtf_min': rd(min(rtf)) if rtf else None, 'clock_ok': clock_ok}


# ---------------------------------------------------------------- evaluation (pure, tested on synthetic data)
def _step(ts, vs, at, left):
    """value of a step signal (ts, vs) at times `at` (last sample at or before; `left` before the first)."""
    i = np.searchsorted(ts, at, side='right') - 1
    out = np.where(i >= 0, vs[np.clip(i, 0, None)], left)
    return out


def _max_move_within(t, P, dt, strict_lt):
    """largest |P[j] - P[i]| over pairs with t[j] - t[i] < dt (strict_lt) or <= dt; also where it happens."""
    best, where = 0.0, None
    n = len(t)
    for k in range(1, n):
        gap = t[k:] - t[:-k]
        inside = (gap < dt) if strict_lt else (gap <= dt + 1e-9)
        if not inside.any():
            break   # t is sorted: larger lags only get longer
        m = np.linalg.norm(P[k:] - P[:-k], axis=1)
        m[~inside] = 0.0
        i = int(np.argmax(m))
        if m[i] > best:
            best, where = float(m[i]), (float(t[i]), float(t[i + k]))
    return best, where


def evaluate(d, marker0=(0.0, 0.0), emerg=None):
    """d: arrays as load_ulog() returns; emerg: goal_common.emergencies() list (None = not evaluated).
    Returns (result dict, verdict dict)."""
    c = C6
    d = dict(d, _emerg=emerg)
    t, xy, z = d['t'], d['xy'], d['z']
    res, v = {}, {}
    z0 = float(np.median(z[t <= 1.0])) if np.any(t <= 1.0) else float(z[0])
    h = z - z0
    armed = _step(d['arm_t'], d['armed'], t, False)
    if d.get('land_t') is not None:
        landed = _step(d['land_t'], d['landed'], t, True)
    else:
        landed = h < 0.05
    air = armed & ~landed
    res['h_max_m'] = rd(h[air].max()) if air.any() else rd(h.max())
    v['took_off'] = bool(air.any() and h[air].max() >= 0.20)
    nav = _step(d['st_t'], d['nav'], t, -1)
    # window
    ok_h = air & (np.abs(h - c['height_m']) <= c['height_tol_m'])
    if not ok_h.any():
        res['window'] = None
        v['hover_window_found'] = False
        return res, finish(res, v, d, t, h, armed)
    i0 = int(np.argmax(ok_h))
    ends = np.where((np.arange(len(t)) > i0) & ((nav != OFFBOARD) | ~armed))[0]
    i1 = int(ends[0]) if len(ends) else len(t)   # exclusive
    w = np.zeros(len(t), bool)
    w[i0:i1] = True
    tw, xyw, hw = t[w], xy[w], h[w]
    t_end = float(t[i1]) if i1 < len(t) else float(t[-1])
    res['window'] = {'from_s': rd(t[i0], 2), 'to_s': rd(t_end, 2), 'len_s': rd(t_end - t[i0], 2),
                     'ends_because': ('end of log' if i1 >= len(t) else
                                      'disarmed' if not armed[i1] else 'left OFFBOARD (nav_state %d)' % nav[i1])}
    v['hover_window_found'] = True
    v['hover_60s'] = (t_end - t[i0]) >= c['hover_s']
    off = np.linalg.norm(xyw - np.asarray(marker0), axis=1)
    herr = np.abs(hw - c['height_m'])
    wt = np.diff(np.append(tw, t_end))
    share = float(np.sum(wt[off <= c['offset_10cm_m']]) / max(np.sum(wt), 1e-9))
    res['offset_share_le_10cm'] = rd(share, 4)
    res['offset_max_m'] = rd(off.max())
    res['offset_mean_m'] = rd(off.mean())
    res['height_err_max_m'] = rd(herr.max())
    res['height_mean_m'] = rd(hw.mean())
    v['share_10cm_ge_95pct'] = share >= c['share_min']
    v['offset_max_le_20cm'] = float(off.max()) <= c['offset_max_m']
    v['height_err_le_10cm'] = float(herr.max()) <= c['height_tol_m']
    # settling (reported only)
    good = (off <= c['offset_10cm_m']) & (herr <= c['height_tol_m'])
    bad_idx = np.where(~good)[0]
    if not len(bad_idx):
        res['settling_s'] = 0.0
    elif bad_idx[-1] == len(good) - 1:
        res['settling_s'] = None
        res['settling_note'] = 'never settled until the window end'
    else:
        res['settling_s'] = rd(tw[bad_idx[-1] + 1] - tw[0], 2)
    # jump a: EKF
    et = d['ekf_t']
    ew = (et >= t[i0]) & (et < t_end)
    resets = []
    for key, dkey, name in (('ekf_xy_reset', 'ekf_delta_xy', 'xy'), ('ekf_z_reset', 'ekf_delta_z', 'z')):
        cnt, dl = d[key], d[dkey]
        grew = np.where(np.diff(cnt) > 0)[0] + 1
        for k in grew:
            if ew[k] and dl[k] > c['jump_m']:
                resets.append({'t_s': rd(et[k], 2), 'axis': name, 'delta_m': rd(dl[k])})
    res['jump_a_ekf_resets'] = resets
    mv, where = _max_move_within(et[ew], d['ekf_xyz'][ew], c['jump_ekf_dt_s'], strict_lt=True)
    res['jump_a_ekf_max_move_lt_0p2s_m'] = rd(mv)
    res['jump_a_ekf_at_s'] = [rd(x, 2) for x in where] if where else None
    v['no_jump_a_ekf'] = not resets and mv <= c['jump_m']
    # jump b: truth
    P3 = np.column_stack([xyw, hw])
    mv, where = _max_move_within(tw, P3, c['jump_truth_dt_s'], strict_lt=False)
    res['jump_b_truth_max_move_0p5s_m'] = rd(mv)
    res['jump_b_truth_at_s'] = [rd(x, 2) for x in where] if where else None
    v['no_jump_b_truth'] = mv <= c['jump_m']
    # information only: horizontal part alone (the verdict uses 3D, STRICTER)
    res['jump_b_truth_max_move_0p5s_xy_only_m'] = rd(_max_move_within(tw, xyw, c['jump_truth_dt_s'], False)[0])
    res['window_end_t'] = t_end
    return res, finish(res, v, d, t, h, armed)


def finish(res, v, d, t, h, armed):
    """landing, emergencies -> verdict lines."""
    t_end = res.pop('window_end_t', None)
    offs = np.where(d['armed'][:-1] & ~d['armed'][1:])[0]
    t_off = float(d['arm_t'][offs[-1] + 1]) if len(offs) else None
    res['motors_off_s'] = rd(t_off, 2)
    landed_end = (d['landed'][-1] if d.get('landed') is not None else bool(h[-1] < 0.05))
    v['landed_and_disarmed_after_hover'] = bool(t_off is not None and (t_end is None or t_off >= t_end)
                                                and not d['armed'][-1] and landed_end and h[-1] < 0.10)
    emerg = d.get('_emerg')
    if emerg is not None:          # None: not evaluated -> the verdict fails on the missing line
        res['emergencies'] = list(emerg)
        v['no_emergency'] = not emerg
    return v


def verdict(v, validity):
    lines = dict(v)
    lines['run_valid'] = validity['valid']
    need = ['run_valid', 'took_off', 'hover_window_found', 'hover_60s', 'share_10cm_ge_95pct', 'offset_max_le_20cm',
            'height_err_le_10cm', 'no_jump_a_ekf', 'no_jump_b_truth', 'landed_and_disarmed_after_hover',
            'no_emergency', 'script_matches_versions']
    failed = [k for k in need if k in lines and not lines[k]]
    failed += ['not evaluated: ' + k for k in need if k not in lines]   # missing = not shown = not passed
    return ('PASS' if not failed else 'FAIL'), failed, lines


# ---------------------------------------------------------------- main
def main(argv):
    if not argv or argv[0].startswith('-'):
        print(__doc__)
        return 2
    run = argv[0].rstrip('/')
    opt = lambda k, dflt: argv[argv.index(k) + 1] if k in argv else dflt  # noqa: E731
    out = opt('--out', run)
    mapf = opt('--map', MAP_FILE)
    ulg = opt('--ulog', None)
    if ulg is None:
        found = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')), key=os.path.getmtime)
        ulg = found[-1] if found else None
    outj, outt = os.path.join(out, 'c6_eval.json'), os.path.join(out, 'c6_eval.txt')
    for p in (outj, outt):
        if os.path.exists(p):
            print('refusing to overwrite ' + p)
            return 2
    os.makedirs(out, exist_ok=True)
    res = {'run': run, 'criteria': 'C6 approved 09.11 (КРИТЕРИИ_УТВЕРЖДЕНЫ_20261109.md) + КРИТЕРИИ_ТОЛКОВАНИЯ_20261109.md',
           'numbers': C6, 'ulog': ulg}
    validity = stand_validity(run)
    res['validity'] = validity
    try:
        res['trial_deviations'] = json.load(open(os.path.join(run, 'run_options.json'))).get('trial_deviations')
    except (OSError, ValueError):
        res['trial_deviations'] = None
    events = []
    try:
        for line in open(os.path.join(run, 'script.log'), encoding='utf-8', errors='replace'):
            if re.search(r'PREFLIGHT FAIL|C6 HOVER RESULT|HOVER END|Traceback|pilot/failsafe|Vision lost|vision silent',
                         line):
                events.append(line.strip()[:200])
    except OSError:
        pass
    res['script_events'] = events[:20]
    # r3: the script of the run must be the one in versions.txt (sha256), as in C5 and C7
    s_path, src, problem = G.script_source(run)
    res['script'] = {'path': s_path, 'problem': problem}
    T = world_to_map(os.path.join(run, 'world.sdf'), mapf)
    res['world_to_map'] = {'n_markers': T['n_markers'], 'max_residual_m': rd(T['max_residual_m'], 4),
                           'marker0_map_xy': [rd(x) for x in T['marker0_map_xy']]}
    if ulg is None:
        res['note'] = 'no ULog: the vehicle never armed'
        v = {'took_off': False}
    else:
        d = load_ulog(ulg, T)
        dc = G.load_ulog(ulg, G.world_to_map(os.path.join(run, 'world.sdf'), mapf))
        code, how = G.script_exit(run)
        res['script_exit'] = {'code': code, 'how': how}
        emerg = G.emergencies(dc, code, how, src, G.read_script_log(run))
        res['failsafe_flags_on_at_start'] = G.ff_on_at_start(dc)
        r, v = evaluate(d, marker0=T['marker0_map_xy'], emerg=emerg)
        res.update(r)
    v['script_matches_versions'] = src is not None
    word, failed, lines = verdict(v, validity)
    res['verdict_lines'] = lines
    res['failed'] = failed
    res['C6'] = word
    with open(outj, 'x', encoding='utf-8') as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    L = ['C6 %s  failed: %s' % (word, ', '.join(failed) or '-'),
         'run %s; valid %s %s; ulog %s' % (os.path.basename(run), validity['valid'], validity['invalid_reasons'], ulg),
         'trial deviations: %s' % res['trial_deviations']]
    if res.get('window'):
        w = res['window']
        L.append('window %.2f..%.2f s (%.1f s, ends: %s); settling %s s' % (
            w['from_s'], w['to_s'], w['len_s'], w['ends_because'], res.get('settling_s')))
        L.append('offset to marker 0: <=10 cm %.1f %% of the time (need >=95), max %.3f m (need <=0.20); '
                 'height err max %.3f m (need <=0.10)' % (100 * res['offset_share_le_10cm'], res['offset_max_m'],
                                                         res['height_err_max_m']))
        L.append('jump a (EKF): resets >0.10 m %s; max move <0.2 s %.3f m at %s' % (
            res['jump_a_ekf_resets'], res['jump_a_ekf_max_move_lt_0p2s_m'], res['jump_a_ekf_at_s']))
        L.append('jump b (truth): max move in 0.5 s %.3f m at %s (horizontal only %.3f m, information)' % (
            res['jump_b_truth_max_move_0p5s_m'], res['jump_b_truth_at_s'],
            res['jump_b_truth_max_move_0p5s_xy_only_m']))
    L.append('verdict lines: %s' % lines)
    L.append('emergencies: %s' % ('not evaluated' if 'emergencies' not in res else res['emergencies'] or '-'))
    if res.get('note'):
        L.append(res['note'])
    if events:
        L.append('script: ' + ' | '.join(events[:5]))
    open(outt, 'x', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))
    return 0 if word == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
