#!/usr/bin/env python3
"""goal_common.py - shared reading of one run of the step-5 / 5b Gazebo stand, for c5_eval.py and c7_eval.py.
Claude, 09.11.2026. Reads files only. Same frames and validity rule as c6_eval.py (/work/c6_eval_20261109).

Run folder: world.sdf, rootfs/log/*/*.ulg (absent = never armed), launcher.log ('script exit N'), script_end.txt (5b),
script.log, versions.txt ('script REL SHA256'), snapshot/run_scenario*.sh ('PRODUCT=...'), rtf.txt, clock_check.txt,
run_options.json (5b), params_sitl.json.
"""
import glob
import hashlib
import json
import os
import re

import numpy as np

RTF_MIN = 0.20
MAP_FILE = '/work/sim/worlds/aruco_map/map.input.txt'
OFFBOARD, LAND = 14, 18
# nav_state values that only a failsafe (or a human) would select during a script flight (PX4 v1.16.1
# vehicle_status.msg): AUTO_RTL 5, DESCEND 12, TERMINATION 13. Any of them = an emergency mode.
EMERGENCY_NAV = {5: 'AUTO_RTL', 12: 'DESCEND', 13: 'TERMINATION'}
ARMED = 2   # vehicle_status.arming_state ARMED (PX4 v1.16.1)


def rd(x, n=3):
    return None if x is None else round(float(x), n)


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------- frames
def world_to_map(world_sdf, map_file):
    """2D rigid transform world -> marker map from the marker centres (method of goal_eval2.py / c6_eval.py)."""
    world, mp = {}, {}
    s = open(world_sdf, encoding='utf-8').read()
    for mid, x, y, _z, _r, _p, _yaw in re.findall(
            r'<include>\s*<uri>model://aruco_(\d+)</uri>\s*<pose>(\S+) (\S+) (\S+) (\S+) (\S+) (\S+)</pose>\s*</include>', s):
        world[int(mid)] = (float(x), float(y))
    for line in open(map_file, encoding='utf-8'):
        if line.startswith('#') or not line.strip():
            continue
        f = line.split()
        mp[int(f[0])] = (float(f[2]), float(f[3]))
    ids = sorted(set(world) & set(mp))
    if len(ids) < 2 or 0 not in ids:
        raise ValueError('world/map: need marker 0 and >= 2 common markers, have %s' % ids)
    A = np.array([world[i] for i in ids])
    B = np.array([mp[i] for i in ids])
    ca, cb = A.mean(0), B.mean(0)
    U, _, Vt = np.linalg.svd((A - ca).T @ (B - cb))
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[1] *= -1
        R = Vt.T @ U.T
    t = cb - R @ ca
    return {'R': R, 't': t, 'n_markers': len(ids), 'marker0_map_xy': np.array(mp[0]),
            'max_residual_m': float(np.linalg.norm(A @ R.T + t - B, axis=1).max())}


# ---------------------------------------------------------------- ULog
def _topic(u, name, required=True):
    for d in u.data_list:
        if d.name == name and d.multi_id == 0:
            return d.data
    if required:
        raise KeyError('ULog has no topic ' + name)
    return None


def load_ulog(ulg, T):
    """ULog -> plain arrays, seconds from log start; truth in the marker map, EKF and setpoints in the EKF frame (ENU)."""
    from pyulog import ULog
    u = ULog(ulg)
    t0 = np.int64(u.start_timestamp)
    sec = lambda a: (np.asarray(a).astype(np.int64) - t0) / 1e6  # noqa: E731
    gt = _topic(u, 'vehicle_local_position_groundtruth')
    lp = _topic(u, 'vehicle_local_position')
    st = _topic(u, 'vehicle_status')
    ts = _topic(u, 'trajectory_setpoint', required=False)
    d = {}
    o = np.argsort(sec(gt['timestamp']), kind='stable')
    d['t'] = sec(gt['timestamp'])[o]
    d['xy'] = np.column_stack([gt['y'][o], gt['x'][o]]) @ T['R'].T + T['t']
    d['z'] = -gt['z'][o]
    d['vz_up'] = -gt['vz'][o]
    o = np.argsort(sec(lp['timestamp']), kind='stable')
    d['ekf_t'] = sec(lp['timestamp'])[o]
    d['ekf_xyz'] = np.column_stack([lp['y'][o], lp['x'][o], -lp['z'][o]])
    o = np.argsort(sec(st['timestamp']), kind='stable')
    d['st_t'] = sec(st['timestamp'])[o]
    d['nav'] = st['nav_state'][o].astype(int)
    d['arming_state'] = st['arming_state'][o].astype(int)
    d['failsafe'] = st['failsafe'][o].astype(bool)
    d['user_took_over'] = (st['failsafe_and_user_took_over'][o].astype(bool)
                           if 'failsafe_and_user_took_over' in st else np.zeros(len(o), bool))
    if ts is not None:
        o = np.argsort(sec(ts['timestamp']), kind='stable')
        d['sp_t'] = sec(ts['timestamp'])[o]
        d['sp_xyz'] = np.column_stack([ts['position[1]'][o], ts['position[0]'][o], -ts['position[2]'][o]])
    else:
        d['sp_t'] = None
        d['sp_xyz'] = None
    d['kill'] = any('Kill engaged' in m.message for m in u.logged_messages)
    d['px4_messages'] = [(rd((int(m.timestamp) - int(t0)) / 1e6, 2), m.message.strip()) for m in u.logged_messages][:80]
    return d


def find_ulog(run, given=None):
    if given:
        return given
    found = sorted(glob.glob(os.path.join(run, 'rootfs', 'log', '*', '*.ulg')), key=os.path.getmtime)
    return found[-1] if found else None


# ---------------------------------------------------------------- stand files
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


def script_exit(run):
    """(code or None, how): the launcher's 'script exit N' line; script_end.txt says whether the stand ended it."""
    code = None
    try:
        for line in open(os.path.join(run, 'launcher.log'), encoding='utf-8', errors='replace'):
            m = re.match(r'script exit (-?\d+)', line.strip())
            if m:
                code = int(m.group(1))
    except OSError:
        pass
    how = None
    try:
        how = open(os.path.join(run, 'script_end.txt'), encoding='utf-8').read().strip()
    except OSError:
        pass
    return code, how


def script_source(run, given=None):
    """(path, text, problem). The script the run used, checked against the sha256 in versions.txt."""
    rel = want = None
    try:
        for line in open(os.path.join(run, 'versions.txt'), encoding='utf-8'):
            m = re.match(r'script (\S+) ([0-9a-f]{64})\s*$', line.strip())
            if m:
                rel, want = m.group(1), m.group(2)
    except OSError:
        return None, None, 'no versions.txt'
    if rel is None:
        return None, None, 'no "script REL SHA" line in versions.txt'
    path = given
    if path is None:
        if rel.startswith('/'):
            path = rel
        else:
            product = None
            for sh in glob.glob(os.path.join(run, 'snapshot', 'run_scenario*.sh')):
                for line in open(sh, encoding='utf-8'):
                    m = re.match(r'PRODUCT=(\S+)', line.strip())
                    if m:
                        product = m.group(1)
            if product is None:
                return None, None, 'PRODUCT= not found in snapshot/run_scenario*.sh'
            path = os.path.join(product, 'src', 'bumblebee', rel)
    if not os.path.exists(path):
        return None, None, 'script file not found: ' + path
    have = sha256(path)
    if have != want:
        return path, None, 'script sha256 %s... differs from versions.txt %s... (file changed after the run)' % (
            have[:12], want[:12])
    return path, open(path, encoding='utf-8').read(), None


def run_fingerprint(run):
    """What a C7 series compares between runs: versions.txt without its date line, plus params_sitl.json."""
    fp = {}
    try:
        for line in open(os.path.join(run, 'versions.txt'), encoding='utf-8'):
            line = line.rstrip('\n')
            if not line.strip() or line.startswith('date '):
                continue
            parts = line.split()
            if re.fullmatch(r'[0-9a-f]{64}', parts[0]) and len(parts) >= 2:
                fp['file ' + parts[-1]] = parts[0]
            else:
                fp[parts[0] + (' ' + parts[1] if parts[0] in ('airframe',) else '')] = line
    except OSError:
        fp['versions.txt'] = 'missing'
    p = os.path.join(run, 'params_sitl.json')
    fp['params_sitl.json'] = sha256(p) if os.path.exists(p) else 'missing'
    return fp


def step(ts, vs, at, left):
    """value of a step signal (ts, vs) at times `at` (last sample at or before; `left` before the first)."""
    i = np.searchsorted(ts, at, side='right') - 1
    return np.where(i >= 0, vs[np.clip(i, 0, None)], left)


def emergencies(d, code, how):
    """'Ни одного аварийного режима' (C5 reading of 09.11): failsafe flags, emergency nav states, kill, script exit."""
    out = []
    if np.any(d['failsafe']):
        out.append('vehicle_status.failsafe at %.2f s' % d['st_t'][np.argmax(d['failsafe'])])
    if np.any(d['user_took_over']):
        out.append('failsafe_and_user_took_over at %.2f s' % d['st_t'][np.argmax(d['user_took_over'])])
    for k, n in enumerate(d['nav']):
        if int(n) in EMERGENCY_NAV:
            out.append('nav_state %s at %.2f s' % (EMERGENCY_NAV[int(n)], d['st_t'][k]))
            break
    if d.get('kill'):
        out.append('Kill engaged')
    if code is None:
        out.append('script exit code unknown')
    elif code != 0:
        out.append('script exit code %d (%s)' % (code, how or 'launcher.log'))
    return out


def write_out(out, base, res, lines):
    outj, outt = os.path.join(out, base + '.json'), os.path.join(out, base + '.txt')
    for p in (outj, outt):
        if os.path.exists(p):
            raise FileExistsError('refusing to overwrite ' + p)
    os.makedirs(out, exist_ok=True)
    with open(outj, 'x', encoding='utf-8') as f:
        json.dump(res, f, indent=1, ensure_ascii=False, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    open(outt, 'x', encoding='utf-8').write('\n'.join(lines) + '\n')


def verdict(lines, need):
    """PASS only if every needed line is present and True; a missing line is 'not evaluated' = fail."""
    failed = [k for k in need if k in lines and not lines[k]]
    failed += ['not evaluated: ' + k for k in need if k not in lines]
    return ('PASS' if not failed else 'FAIL'), failed
