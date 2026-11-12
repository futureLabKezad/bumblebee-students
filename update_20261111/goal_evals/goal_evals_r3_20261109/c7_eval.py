#!/usr/bin/env python3
"""c7_eval.py - criterion C7 (flight over the markers: flight_marker.py, flight_marker_loop.py). Claude, 09.11.2026.
Reads files only. Numbers: КРИТЕРИИ_УТВЕРЖДЕНЫ_20261109.md (C7); readings: КРИТЕРИИ_ТОЛКОВАНИЯ_20261109.md
("С7 и Ж5"). Nothing is loosened; a line that cannot be computed fails ("not evaluated").

One run:
  route            from the CODE of the script the run used (versions.txt sha256 checked): its drone.fly_to(x=, y=)
                   calls in order, number literals, or a `for (a, b) in LIST:` loop over a module-level list of
                   number pairs. Points are marker-map coordinates (the map of the scripts = the world's markers);
                   the truth is moved into the marker map by world.sdf + map.txt (2D fit), never by the drone's
                   estimate. The calls the script really made ('=== FLY TO (x, y, z) ===' in script.log, printed by
                   drone.fly_to) must equal the planned route; fewer = interrupted.
  holds            PX4 trajectory_setpoint (ULog): stretches where the setpoint does not move (< 3 mm per sample,
                   >= 0.4 s), neighbours closer than 0.05 m merged. Between arming and the first AUTO.LAND: hold 0 =
                   takeoff, then the route points in order (every leg length between them must match the route leg
                   within 0.05 m). r3: any other hold must be a re-target AT the point just reached (drone.hover(),
                   safe_land's approach/hover aim at the current estimate): within that point's fly_to tolerance
                   (after takeoff: 0.2) of its hold. No such reading = "not evaluated". Several readings: each is
                   scored and the worst counts.
  arrival          first time after the start of hold k when the EKF position is within the script's fly_to
                   tolerance (3D) of the setpoint - the script's own arrival test (navigate_wait).
  point error      max horizontal truth distance to route point k from arrival until the setpoint moves on to the
                   next route point (re-targets at point k included; for the last point the landing command).
                   This covers "at the moment of the next command" and "the whole wait"; the larger one counts.
                   Must be <= 0.25 m, compared unrounded (r3). Mean height is printed separately.
  landing          horizontal truth distance from the centre of marker 0 to where the vehicle stands after motors off
                   (mean over 1.0 s after arming_state leaves ARMED). Must be <= 0.15 m.
  no interruption  run valid (RTF >= 0.20, clock ok); no emergency (goal_common.emergencies: failsafe incl. a
                   failsafe_flags condition turning on while armed, AUTO_RTL/DESCEND/TERMINATION, Hold not asked by
                   the script, AUTO.LAND before the script asked to land, kill, exit code != 0 / unknown / 137 / 143);
                   OFFBOARD from takeoff until AUTO.LAND (any other mode = an intervention); all points reached.
  Edition r2 (09.11 ~11:00 readings): emergencies as above. r1: /work/goal_evals_20261109.
  Edition r3 (09.11, chat 1 after the independent review): no rounding before comparing; re-target holds;
                   emergencies of goal_common r3. r2: /work/goal_evals_r2_20261109.
Series: python3 -I c7_eval.py --series OUT_DIR RUN_OR_JSON...   (in flight order)
  per script: count of PASS in a row; any FAIL resets to 0; a change of code or settings (versions.txt without its
  date line, params_sitl.json) restarts the count at that run. C7 needs 10 in a row for each of the two scripts.
Usage: python3 -I c7_eval.py RUN_DIR [--out DIR] [--map MAP] [--ulog ULG] [--script FILE]
Writes OUT/c7_eval.json and .txt (never overwrites). Exit 0 PASS, 1 FAIL, 2 error.
"""
import ast
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goal_common as G  # noqa: E402

C7 = {'point_m': 0.25, 'landing_m': 0.15, 'in_a_row': 10,
      'sp_still_m': 0.003, 'hold_min_s': 0.4, 'hold_merge_m': 0.05, 'leg_match_m': 0.05, 'stand_after_off_s': 1.0}
NEED = ['run_valid', 'route_from_code', 'route_flown_as_coded', 'holds_match_route', 'all_points_reached',
        'points_within_0p25', 'landing_found', 'landing_within_0p15', 'offboard_until_land', 'no_emergency']
DEFAULT_TOL = 0.2   # drone.fly_to(tolerance=0.2) default


# ---------------------------------------------------------------- route from code
def _num(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_num(node.operand)
    raise ValueError('not a number literal: %s' % ast.dump(node)[:80])


def _is_fly_to(n):
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'fly_to'
            and isinstance(n.func.value, ast.Name) and n.func.value.id == 'drone')


def _kw(call, name, pos):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return call.args[pos] if len(call.args) > pos else None


def route_from_code(src):
    """[(x, y, tolerance)] in execution order. Only the two patterns of the image's examples are understood."""
    tree = ast.parse(src)
    lists = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and isinstance(n.value, (ast.List, ast.Tuple)):
            try:
                lists[n.targets[0].id] = [(_num(e.elts[0]), _num(e.elts[1])) for e in n.value.elts]
            except (ValueError, AttributeError, IndexError):
                pass
    route = []

    def tol_of(call):
        t = _kw(call, 'tolerance', 4)
        return DEFAULT_TOL if t is None else _num(t)

    def walk(stmts, env):
        for s in stmts:
            if isinstance(s, ast.For):
                if not (isinstance(s.iter, ast.Name) and s.iter.id in lists and isinstance(s.target, ast.Tuple)):
                    if any(_is_fly_to(n) for n in ast.walk(s)):
                        raise ValueError('fly_to inside a loop that is not "for (a, b) in LIST"')
                    continue
                names = [e.id for e in s.target.elts]
                for pt in lists[s.iter.id]:
                    walk(s.body, dict(env, **{names[0]: pt[0], names[1]: pt[1]}))
                continue
            if isinstance(s, (ast.FunctionDef, ast.ClassDef)):
                if any(_is_fly_to(n) for n in ast.walk(s)):
                    raise ValueError('fly_to inside a function: not understood')
                continue
            calls = [n for n in ast.walk(s) if _is_fly_to(n)]
            if isinstance(s, ast.While) and calls:
                raise ValueError('fly_to inside a while loop: not understood')
            if isinstance(s, ast.Try):
                if any(_is_fly_to(n) for hd in s.handlers for n in ast.walk(hd)):
                    raise ValueError('fly_to inside an except handler: not understood')
                walk(s.body + s.orelse + s.finalbody, env)
                continue
            if isinstance(s, (ast.If, ast.With)):
                head = s.test if isinstance(s, ast.If) else s.items
                head_calls = [n for n in ast.walk(head if isinstance(head, ast.AST) else ast.Tuple(elts=[
                    i.context_expr for i in head], ctx=ast.Load())) if _is_fly_to(n)]
                add(head_calls, env)
                walk(s.body + getattr(s, 'orelse', []), env)
                continue
            add(calls, env)

    def add(calls, env):
        for c in calls:
            x, y = _kw(c, 'x', 0), _kw(c, 'y', 1)
            xv = env[x.id] if isinstance(x, ast.Name) and x.id in env else _num(x)
            yv = env[y.id] if isinstance(y, ast.Name) and y.id in env else _num(y)
            route.append((xv, yv, tol_of(c)))

    walk(tree.body, {})
    if not route:
        raise ValueError('no drone.fly_to() call found')
    return route


def route_from_log(path):
    out = []
    try:
        for line in open(path, encoding='utf-8', errors='replace'):
            m = re.search(r'=== FLY TO \((-?[\d.]+), (-?[\d.]+), (-?[\d.]+)\) ===', line)
            if m:
                out.append((float(m.group(1)), float(m.group(2))))
    except OSError:
        return None
    return out


# ---------------------------------------------------------------- holds of the setpoint
def holds(sp_t, sp, t_from, t_to):
    """[(t_start, t_end, xyz)] stretches where the setpoint does not move, between t_from and t_to."""
    c = C7
    sel = (sp_t >= t_from) & (sp_t <= t_to)
    ts, P = sp_t[sel], sp[sel]
    if len(ts) < 2:
        return []
    still = np.r_[False, np.linalg.norm(np.diff(P, axis=0), axis=1) < c['sp_still_m']]
    runs, i = [], 0
    while i < len(ts):
        if still[i]:
            j = i
            while j + 1 < len(ts) and still[j + 1]:
                j += 1
            s = i - 1   # the sample before the first 'still' one already holds the value
            end = ts[j + 1] if j + 1 < len(ts) else t_to
            if ts[j] - ts[s] >= c['hold_min_s']:
                runs.append([float(ts[s]), float(end), P[j].copy()])
            i = j + 1
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and np.linalg.norm(merged[-1][2][:2] - r[2][:2]) < c['hold_merge_m']:
            merged[-1][1] = r[1]
            merged[-1][2] = r[2]
        else:
            merged.append(r)
    return [(a, b, p) for a, b, p in merged]


def match_route(H, route):
    """r3: every way to read the holds H as [takeoff, point 1..N] plus re-targets. Returns a list of index lists
    [0, i1, .., iN] (increasing) such that
      - legs: |setpoint distance hold i(k-1) -> hold ik - route leg k-1 -> k| <= leg_match_m for k >= 2;
      - every other hold j is a re-target at the point just matched (drone.hover() / safe_land's approach and
        hover re-aim the setpoint at the current estimate): it lies after i(k) and before i(k+1), within the
        tolerance of that point's fly_to (after the takeoff hold: DEFAULT_TOL) of hold ik, horizontally.
    An empty list = the holds cannot be read as the route ('not evaluated')."""
    c = C7
    N = len(route)
    out = []

    def ok_extras(prev, nxt, radius):
        return all(np.linalg.norm(H[j][2][:2] - H[prev][2][:2]) <= radius for j in range(prev + 1, nxt))

    def go(path):
        k = len(path)          # next route point number (1..N)
        last = path[-1]
        radius = DEFAULT_TOL if k == 1 else route[k - 2][2]
        if k == N + 1:
            if ok_extras(last, len(H), radius):
                out.append(list(path))
            return
        for j in range(last + 1, len(H)):
            if not ok_extras(last, j, radius):
                break
            if k >= 2:
                want = float(np.hypot(route[k - 1][0] - route[k - 2][0], route[k - 1][1] - route[k - 2][1]))
                have = float(np.linalg.norm(H[j][2][:2] - H[last][2][:2]))
                if abs(want - have) > c['leg_match_m']:
                    continue
            go(path + [j])

    if len(H) >= N + 1:
        go([0])
    return out


def evaluate(d, route, flown, marker0=(0.0, 0.0), code=0, how=None, script_src=None, script_log=None):
    """d: arrays as goal_common.load_ulog(); route [(x, y, tol)] from code; flown [(x, y)] from script.log."""
    c = C7
    res, v = {}, {}
    t = d['t']
    z0 = float(np.median(d['z'][t <= 1.0])) if np.any(t <= 1.0) else float(d['z'][0])
    h = d['z'] - z0
    emerg = G.emergencies(d, code, how, script_src, script_log)
    res['failsafe_flags_on_at_start'] = G.ff_on_at_start(d)
    res['emergencies'] = emerg
    v['no_emergency'] = not emerg
    res['route_marker_map'] = [[p[0], p[1]] for p in route]
    res['flown_from_log'] = flown
    v['route_flown_as_coded'] = (flown is not None and len(flown) == len(route)
                                 and all(abs(a[0] - b[0]) < 1e-3 and abs(a[1] - b[1]) < 1e-3
                                         for a, b in zip(flown, route)))
    arm = d['arming_state'] == G.ARMED
    if not arm.any():
        v['landing_found'] = False
        return res, v
    t_arm = float(d['st_t'][np.argmax(arm)])
    lands = np.where((d['st_t'] > t_arm) & (d['nav'] == G.LAND))[0]
    t_land = float(d['st_t'][lands[0]]) if len(lands) else float(t[-1])
    # OFFBOARD from takeoff to AUTO.LAND
    seg = (d['st_t'] >= t_arm) & (d['st_t'] < t_land) & arm
    other = sorted({int(n) for n in d['nav'][seg]} - {G.OFFBOARD})
    v['offboard_until_land'] = bool(len(lands)) and not other
    res['modes_before_land'] = other
    # holds
    if d.get('sp_t') is None:
        v['holds_match_route'] = False
        res['holds_problem'] = 'no trajectory_setpoint in ULog'
        return res, v
    H = holds(d['sp_t'], d['sp_xyz'], t_arm, t_land)
    res['holds'] = [{'from_s': G.rd(a, 2), 'to_s': G.rd(b, 2), 'sp_ekf': [G.rd(x) for x in p]} for a, b, p in H]
    ways = match_route(H, route)
    res['hold_readings'] = [w_[1:] for w_ in ways]
    legs = []
    if ways:
        for k in range(1, len(route)):
            want = float(np.hypot(route[k][0] - route[k - 1][0], route[k][1] - route[k - 1][1]))
            have = float(np.linalg.norm(H[ways[0][k + 1]][2][:2] - H[ways[0][k]][2][:2]))
            legs.append([G.rd(want), G.rd(have)])
    res['legs_route_vs_setpoint_m'] = legs
    v['holds_match_route'] = bool(ways)
    if ways:
        # every reading of the holds is scored; per point the WORST reading counts (r3)
        et, E = d['ekf_t'], d['ekf_xyz']
        worst = [None] * len(route)
        for idx in ways:
            for k, (x, y, tol) in enumerate(route):
                i = idx[k + 1]
                a, p = H[i][0], H[i][2]
                # the point is left when the setpoint moves to the next route point: the end of the last hold
                # before the next point's hold (re-targets at this point included); last point: the last hold
                b = H[idx[k + 2] - 1][1] if k + 2 < len(idx) else H[-1][1]
                inside = (et >= a) & (et <= b)
                dist = np.linalg.norm(E[inside] - p, axis=1)
                near = np.where(dist < tol)[0]
                if not len(near):
                    worst[k] = {'n': k + 1, 'route': [x, y], 'reached': False}
                    continue
                t_arr = float(et[inside][near[0]])
                w = (t >= t_arr) & (t <= b)
                if not w.any():
                    w = np.abs(t - b) == np.abs(t - b).min()
                err = np.hypot(d['xy'][w, 0] - x, d['xy'][w, 1] - y)
                at_next = float(np.hypot(*(d['xy'][w][-1] - [x, y])))
                e = float(max(err.max(), at_next))
                if worst[k] is not None and (not worst[k]['reached'] or worst[k]['_err'] >= e):
                    continue
                worst[k] = {'n': k + 1, 'route': [x, y], 'reached': True, 'arrival_s': G.rd(t_arr, 2),
                            'next_command_s': G.rd(b, 2), 'err_at_next_command_m': G.rd(at_next),
                            'err_max_wait_m': G.rd(err.max()), 'err_m': G.rd(e), '_err': e,
                            'height_mean_m': G.rd(h[w].mean())}
        reached = all(p['reached'] for p in worst)
        # compared WITHOUT rounding (r3)
        v['all_points_reached'] = reached
        v['points_within_0p25'] = reached and all(p['_err'] <= c['point_m'] for p in worst)
        res['points'] = [{k_: val for k_, val in p.items() if k_ != '_err'} for p in worst]
    # landing
    off = np.where((d['st_t'] > t_land) & ~arm)[0] if len(lands) else np.array([], int)
    if not len(off):
        v['landing_found'] = False
        return res, v
    t_off = float(d['st_t'][off[0]])
    w = (t >= t_off) & (t <= t_off + c['stand_after_off_s'])
    if not w.any():
        v['landing_found'] = False
        return res, v
    pos = d['xy'][w].mean(0)
    v['landing_found'] = True
    dist0 = float(np.hypot(*(pos - np.asarray(marker0))))
    res['landing'] = {'motors_off_s': G.rd(t_off, 2), 'stands_at_marker_map': [G.rd(pos[0]), G.rd(pos[1])],
                      'dist_to_marker0_m': G.rd(dist0)}
    v['landing_within_0p15'] = dist0 <= c['landing_m']   # compared WITHOUT rounding (r3)
    return res, v


# ---------------------------------------------------------------- series
def series(records):
    """records: [{'run', 'script', 'C7', 'fingerprint'}] in flight order -> per-script counts and the log."""
    state, log = {}, []
    for r in records:
        s = state.setdefault(r['script'], {'in_a_row': 0, 'fp': None, 'best': 0})
        note = ''
        if s['fp'] is not None and r['fingerprint'] != s['fp']:
            changed = sorted(k for k in set(s['fp']) | set(r['fingerprint'])
                             if s['fp'].get(k) != r['fingerprint'].get(k))
            s['in_a_row'] = 0
            note = 'code/settings changed (%s): count restarts' % ', '.join(changed[:6])
        s['fp'] = r['fingerprint']
        s['in_a_row'] = s['in_a_row'] + 1 if r['C7'] == 'PASS' else 0
        s['best'] = max(s['best'], s['in_a_row'])
        log.append({'run': r['run'], 'script': r['script'], 'C7': r['C7'], 'in_a_row': s['in_a_row'], 'note': note})
    done = {k: s['in_a_row'] >= C7['in_a_row'] for k, s in state.items()}
    return {'per_script_in_a_row_now': {k: s['in_a_row'] for k, s in state.items()}, 'reached_10': done,
            'C7_series_done': (set(done) >= {'flight_marker.py', 'flight_marker_loop.py'} and all(
                done.get(k) for k in ('flight_marker.py', 'flight_marker_loop.py'))), 'log': log}


def main_series(argv):
    out = argv[0]
    recs = []
    for p in argv[1:]:
        j = p if p.endswith('.json') else os.path.join(p, 'c7_eval.json')
        r = json.load(open(j, encoding='utf-8'))
        recs.append({'run': r['run'], 'script': os.path.basename(r['script']['path'] or '?'), 'C7': r['C7'],
                     'fingerprint': r['fingerprint']})
    s = series(recs)
    L = ['C7 series: in a row now %s; 10 reached %s; series done %s' % (
        s['per_script_in_a_row_now'], s['reached_10'], s['C7_series_done'])]
    L += ['  %s %s %s -> %d %s' % (e['run'], e['script'], e['C7'], e['in_a_row'], e['note']) for e in s['log']]
    try:
        G.write_out(out, 'c7_series', s, L)
    except FileExistsError as e:
        print(e)
        return 2
    print('\n'.join(L))
    return 0 if s['C7_series_done'] else 1


def main(argv):
    if not argv or argv[0].startswith('-') and argv[0] != '--series':
        print(__doc__)
        return 2
    if argv[0] == '--series':
        return main_series(argv[1:])
    run = argv[0].rstrip('/')
    opt = lambda k, dflt: argv[argv.index(k) + 1] if k in argv else dflt  # noqa: E731
    out = opt('--out', run)
    for b in ('c7_eval.json', 'c7_eval.txt'):
        if os.path.exists(os.path.join(out, b)):
            print('refusing to overwrite ' + os.path.join(out, b))
            return 2
    res = {'run': run, 'criteria': 'C7 approved 09.11 + КРИТЕРИИ_ТОЛКОВАНИЯ_20261109.md', 'numbers': C7}
    validity = G.stand_validity(run)
    res['validity'] = validity
    res['fingerprint'] = G.run_fingerprint(run)
    lines = {'run_valid': validity['valid']}
    path, src, problem = G.script_source(run, opt('--script', None))
    res['script'] = {'path': path, 'problem': problem}
    route = None
    if src is not None:
        try:
            route = route_from_code(src)
        except (ValueError, SyntaxError, KeyError) as e:
            res['script']['problem'] = str(e)
    lines['route_from_code'] = route is not None
    flown = route_from_log(os.path.join(run, 'script.log'))
    code, how = G.script_exit(run)
    res['script_exit'] = {'code': code, 'how': how}
    ulg = G.find_ulog(run, opt('--ulog', None))
    res['ulog'] = ulg
    T = G.world_to_map(os.path.join(run, 'world.sdf'), opt('--map', G.MAP_FILE))
    if ulg is None:
        res['note'] = 'no ULog: the vehicle never armed'
    elif route is not None:
        d = G.load_ulog(ulg, T)
        r, v = evaluate(d, route, flown, T['marker0_map_xy'], code, how, src, G.read_script_log(run))
        res.update(r)
        lines.update(v)
    word, failed = G.verdict(lines, NEED)
    res.update({'verdict_lines': lines, 'failed': failed, 'C7': word})
    L = ['C7 %s  failed: %s' % (word, ', '.join(failed) or '-'),
         'run %s; valid %s %s; script %s %s; exit %s (%s)' % (
             os.path.basename(run), validity['valid'], validity['invalid_reasons'], path,
             res['script']['problem'] or '', code, how),
         'route (code): %s; flown (log): %s' % ([p[:2] for p in route] if route else None, flown)]
    for p in res.get('points', []):
        L.append('  point %d %s: %s' % (p['n'], p['route'], 'not reached' if not p['reached'] else
                 'err %.3f m (at next command %.3f, max in wait %.3f), height %.2f m' % (
                     p['err_m'], p['err_at_next_command_m'], p['err_max_wait_m'], p['height_mean_m'])))
    if 'landing' in res:
        L.append('landing: %.3f m from marker 0 (need <=0.15)' % res['landing']['dist_to_marker0_m'])
    if 'holds' in res and not lines.get('holds_match_route', True):
        L.append('holds (setpoint) %d for %d route points; legs %s' % (
            len(res['holds']), len(route or []), res.get('legs_route_vs_setpoint_m')))
    L.append('emergencies: %s; modes before land: %s' % (
        'not evaluated' if 'emergencies' not in res else res['emergencies'] or '-', res.get('modes_before_land')))
    if res.get('note'):
        L.append(res['note'])
    try:
        G.write_out(out, 'c7_eval', res, L)
    except FileExistsError as e:
        print(e)
        return 2
    print('\n'.join(L))
    return 0 if word == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
