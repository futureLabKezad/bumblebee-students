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
    ff = _topic(u, 'failsafe_flags', required=False)
    d['ff_t'], d['ff'] = None, {}
    if ff is not None:
        o = np.argsort(sec(ff['timestamp']), kind='stable')
        d['ff_t'] = sec(ff['timestamp'])[o]
        for k, a in ff.items():
            if k == 'timestamp' or k.startswith('mode_req') or k.startswith('_'):
                continue
            a = np.asarray(a)[o]
            if a.dtype == bool or set(np.unique(a).tolist()) <= {0, 1}:
                d['ff'][k] = a.astype(bool)
    vc = _topic(u, 'vehicle_command', required=False)
    if vc is not None:
        d['cmd_t'] = sec(vc['timestamp'])
        d['cmd'] = vc['command'].astype(int)
        d['cmd_p2'] = vc['param2'].astype(float)
        d['cmd_p3'] = vc['param3'].astype(float)
        # r3: a missing from_external field is NOT taken as external; emergencies() reports it (not evaluated)
        d['cmd_ext_logged'] = 'from_external' in vc
        d['cmd_ext'] = (vc['from_external'].astype(bool) if 'from_external' in vc
                        else np.zeros(len(d['cmd']), bool))
    else:
        d['cmd_t'] = d['cmd'] = d['cmd_p2'] = d['cmd_p3'] = d['cmd_ext'] = np.array([])
        d['cmd_ext_logged'] = True   # no commands at all: nothing to classify
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


LOITER = 4
# r3 (chat 1, 09.11): only the script's own landing (safe_land prints '=== LANDING ===') is a requested landing.
LAND_REQUEST_LOG = re.compile(r'=== LANDING ===')
# r3: drone.py's guard landings (navigate_wait -> _land_if_offboard, drone.py r2b/r2d) are emergencies, always.
GUARD_LANDING_LOG = re.compile(r'(Vision lost|Telemetry stale|EKF z=|Altitude overshoot|Position jump).*landing'
                               r'|Guard /land')
# r4 (review of r3): the example scripts' OWN emergency/abort landings are emergencies too (decision 1: "asked by
# the script, but for an emergency reason"). Lines of the image r2b/r2c/r2d: flight.py 'VISION SILENT >3s during
# hover -- safe_land'; flight_marker.py 'vision silent >N s -- aborting'; flight_marker_loop.py 'vision silent
# >3.0s -- emergency land', 'Waypoint (x, y) failed -- aborting mission'. Matched without case.
SCRIPT_ABORT_LOG = re.compile(r'vision silent >|-- aborting|emergency land', re.IGNORECASE)
# r3: Hold counts as the script's only with a request line in script.log AND an external DO_SET_MODE AUTO/LOITER
# (176, param2 4, param3 3) within LAND_CMD_WINDOW_S before the switch. No image script prints it today.
HOLD_REQUEST_LOG = re.compile(r'=== HOLD ===')
LAND_CMD_WINDOW_S = 2.0
# Allowed after the script asked for the landing: it stops the OFFBOARD stream on purpose.
FF_AFTER_LAND_OK = {'offboard_control_signal_lost'}


def mode_entries(d, nav_value):
    """Times when the armed vehicle entered nav_state nav_value."""
    armed = d['arming_state'] == ARMED
    out = []
    for k in range(len(d['nav'])):
        if d['nav'][k] == nav_value and armed[k] and (k == 0 or d['nav'][k - 1] != nav_value):
            out.append(float(d['st_t'][k]))
    return out


def land_entries(d):
    """Times when the armed vehicle entered AUTO.LAND (nav_state 18)."""
    return mode_entries(d, LAND)


def _external_cmd_before(d, t_entry, want):
    t, c = np.asarray(d['cmd_t'], float), np.asarray(d['cmd'], int)
    if not len(t):
        return False
    sel = (t <= t_entry + 1e-6) & (t >= t_entry - LAND_CMD_WINDOW_S) & np.asarray(d['cmd_ext'], bool)
    return bool(np.any(sel & want(c, np.round(d['cmd_p2']), np.round(d['cmd_p3']))))


def land_requested(d, t_entry, script_log):
    """AUTO.LAND at t_entry counts as the script's landing only if (1) script.log shows the script's own landing
    ('=== LANDING ===', safe_land) and (2) an external command asked for it within LAND_CMD_WINDOW_S before:
    DO_SET_MODE (176) AUTO/LAND (param2 4, param3 6) or NAV_LAND (21). A PX4-internal switch has no external
    command. A drone.py guard landing is an emergency on its own (emergencies())."""
    if not script_log or not LAND_REQUEST_LOG.search(script_log):
        return False
    return _external_cmd_before(d, t_entry, lambda c, p2, p3: ((c == 176) & (p2 == 4) & (p3 == 6)) | (c == 21))


def hold_requested(d, t_entry, script_log):
    """Hold (AUTO.LOITER) at t_entry is the script's only with '=== HOLD ===' in script.log and an external
    DO_SET_MODE AUTO/LOITER (176, param2 4, param3 3) within LAND_CMD_WINDOW_S before."""
    if not script_log or not HOLD_REQUEST_LOG.search(script_log):
        return False
    return _external_cmd_before(d, t_entry, lambda c, p2, p3: (c == 176) & (p2 == 4) & (p3 == 3))


def emergencies(d, code, how, script_src=None, script_log=None):
    """'Ни одного аварийного режима' (readings of 09.11 ~10:35 and ~11:00). Any of:
    vehicle_status.failsafe / failsafe_and_user_took_over; a failsafe_flags condition that turns on while armed
    (conditions already on at the log start are listed, not counted; offboard_control_signal_lost after the
    script's own landing is expected); nav_state AUTO_RTL / DESCEND / TERMINATION while armed; Hold (AUTO.LOITER)
    while armed unless the script requested it (script.log + external command); AUTO.LAND not requested by the
    script; a drone.py guard landing (script.log); kill; script exit code != 0 or unknown (137/143 = ended by
    the stand). Edition r3: data that is missing (failsafe_flags, from_external, script.log) is an entry
    '... not evaluated', i.e. a fail. script_src is no longer used (Hold is judged by the request log)."""
    out = []
    armed_st = d['arming_state'] == ARMED
    if np.any(d['failsafe']):
        out.append('vehicle_status.failsafe at %.2f s' % d['st_t'][np.argmax(d['failsafe'])])
    if np.any(d['user_took_over']):
        out.append('failsafe_and_user_took_over at %.2f s' % d['st_t'][np.argmax(d['user_took_over'])])
    if script_log is None:
        out.append('script.log missing: script landings not evaluated')
    else:
        g = GUARD_LANDING_LOG.search(script_log)
        if g:
            line = script_log[script_log.rfind('\n', 0, g.start()) + 1:].split('\n', 1)[0]
            out.append('drone.py emergency landing: %s' % line.strip()[:160])
        s = SCRIPT_ABORT_LOG.search(script_log)
        if s:
            line = script_log[script_log.rfind('\n', 0, s.start()) + 1:].split('\n', 1)[0]
            out.append('script emergency landing / abort: %s' % line.strip()[:160])
    if d.get('cmd_ext_logged') is False:
        out.append('vehicle_command.from_external not in ULog: requested landings not evaluated')
    lands = land_entries(d)
    first_req = next((t for t in lands if land_requested(d, t, script_log)), None)
    for t in lands:
        if not land_requested(d, t, script_log):
            out.append('AUTO.LAND at %.2f s not requested by the script' % t)
    if d.get('ff_t') is None:
        out.append('failsafe_flags not in ULog: not evaluated')
    else:
        armed_ff = step(d['st_t'], armed_st, d['ff_t'], False)
        for k, a in sorted(d['ff'].items()):
            on = np.where(a & ~np.r_[False, a[:-1]] & armed_ff)[0]
            on = [i for i in on if i > 0 or not a[0]]
            for i in on:
                tt = float(d['ff_t'][i])
                if k in FF_AFTER_LAND_OK and first_req is not None and tt >= first_req:
                    continue
                out.append('failsafe_flags.%s on at %.2f s' % (k, tt))
                break
    for k, n in enumerate(d['nav']):
        if not armed_st[k]:
            continue
        if int(n) in EMERGENCY_NAV:
            out.append('nav_state %s at %.2f s' % (EMERGENCY_NAV[int(n)], d['st_t'][k]))
            break
    for t in mode_entries(d, LOITER):
        if not hold_requested(d, t, script_log):
            out.append('nav_state AUTO.LOITER (Hold) at %.2f s, not requested by the script' % t)
            break
    if d.get('kill'):
        out.append('Kill engaged')
    if code is None:
        out.append('script exit code unknown')
    elif code != 0:
        out.append('script exit code %d (%s)%s' % (code, how or 'launcher.log',
                                                   ' = ended by the stand' if code in (137, 143) else ''))
    return out


def ff_on_at_start(d):
    """failsafe_flags conditions already on in the first sample (information only)."""
    if d.get('ff_t') is None or not len(d['ff_t']):
        return None
    return sorted(k for k, a in d['ff'].items() if a[0])


def read_script_log(run):
    try:
        return open(os.path.join(run, 'script.log'), encoding='utf-8', errors='replace').read()
    except OSError:
        return None


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
