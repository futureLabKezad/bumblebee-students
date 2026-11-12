#!/usr/bin/env python3
"""c5_eval.py - criterion C5 (takeoff-hover-landing with flight.py) from one Gazebo run. Claude, 09.11.2026.
Reads files only. Numbers: КРИТЕРИИ_УТВЕРЖДЕНЫ_20261109.md (C5); readings: КРИТЕРИИ_ТОЛКОВАНИЯ_20261109.md
(sections "С5 и Ж3"). Nothing is loosened; a line that cannot be computed fails ("not evaluated").

  script height H  from the script the run used (versions.txt sha256 checked): its single drone.takeoff(height=H)
                   call, a number literal. Not from a command-line option.
  h                Gazebo truth z minus its median over the first 1.0 s of the log (log starts at arming, on the floor).
  window           first armed sample with |h - H| <= 0.10 m, to the landing command: the first later moment the
                   vehicle leaves OFFBOARD (AUTO.LAND after /land, or a pilot/failsafe mode) or is disarmed.
                   Every truth sample in it must be within H +- 0.10 m (maximum deviation, not the mean).
  touchdown        first truth sample after the window with h <= 0.01 m (the model rests at h = 0 exactly in
                   Gazebo: s04). Speed is NOT used (reading of 09.11 ~11:00): a bounce does not move it later.
  motors off       first vehicle_status sample after touchdown with arming_state != ARMED ("disarmed").
                   Delay = motors off - touchdown <= 3.0 s.
  no emergency     over the whole run (goal_common.emergencies, readings ~10:35 and ~11:00): failsafe
                   (vehicle_status.failsafe, failsafe_and_user_took_over, a failsafe_flags condition turning on while
                   armed), AUTO_RTL / DESCEND / TERMINATION, Hold not asked by the script, AUTO.LAND before the
                   script asked to land, 'Kill engaged', script exit code != 0 or unknown (137/143 = stand ended it).
  Edition r2 (09.11): touchdown without speed; emergencies as above. r1: /work/goal_evals_20261109.
  run valid        RTF >= 0.20 and clock check ok (stand rule, unchanged).
Usage: python3 -I c5_eval.py RUN_DIR [--out DIR] [--map MAP] [--ulog ULG] [--script FILE]
Writes OUT/c5_eval.json and .txt (OUT defaults to RUN_DIR; never overwrites). Exit 0 PASS, 1 FAIL, 2 error.
"""
import ast
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goal_common as G  # noqa: E402

C5 = {'height_tol_m': 0.10, 'motors_off_s': 3.0, 'touch_h_m': 0.01}
NEED = ['run_valid', 'script_height_known', 'took_off', 'height_window_found', 'height_within_0p10',
        'touchdown_found', 'motors_off_found', 'motors_off_le_3s', 'no_emergency']


def script_height(src):
    """H from the single drone.takeoff(...) call (keyword height= or first argument), a number literal."""
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == 'takeoff' and isinstance(n.func.value, ast.Name) and n.func.value.id == 'drone']
    if len(calls) != 1:
        raise ValueError('expected exactly one drone.takeoff() call, found %d' % len(calls))
    c = calls[0]
    node = next((k.value for k in c.keywords if k.arg == 'height'), c.args[0] if c.args else None)
    if node is None:
        return 1.0   # drone.takeoff default height=1.0 (drone.py)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    raise ValueError('drone.takeoff height is not a number literal')


def evaluate(d, H, code=0, how=None, script_src=None, script_log=None):
    """d: arrays as goal_common.load_ulog(). Returns (res, lines)."""
    c = C5
    res, v = {}, {}
    t, h0 = d['t'], d['z']
    z0 = float(np.median(h0[t <= 1.0])) if np.any(t <= 1.0) else float(h0[0])
    h = h0 - z0
    armed = G.step(d['st_t'], d['arming_state'] == G.ARMED, t, False)
    nav = G.step(d['st_t'], d['nav'], t, -1)
    res['h_max_m'] = G.rd(h[armed].max()) if armed.any() else G.rd(h.max())
    v['took_off'] = bool(armed.any() and h[armed].max() >= 0.20)
    emerg = G.emergencies(d, code, how, script_src, script_log)
    res['failsafe_flags_on_at_start'] = G.ff_on_at_start(d)
    res['emergencies'] = emerg
    v['no_emergency'] = not emerg
    band = armed & (np.abs(h - H) <= c['height_tol_m'])
    if not band.any():
        v['height_window_found'] = False
        return res, v
    i0 = int(np.argmax(band))
    ends = np.where((np.arange(len(t)) > i0) & ((nav != G.OFFBOARD) | ~armed))[0]
    i1 = int(ends[0]) if len(ends) else len(t)
    v['height_window_found'] = True
    dev = np.abs(h[i0:i1] - H)
    res['window'] = {'from_s': G.rd(t[i0], 2), 'to_s': G.rd(t[min(i1, len(t) - 1)], 2),
                     'ends_because': ('end of log' if i1 >= len(t) else 'disarmed' if not armed[i1]
                                      else 'left OFFBOARD (nav_state %d)' % nav[i1])}
    res['height_dev_max_m'] = G.rd(dev.max())
    res['height_mean_m'] = G.rd(h[i0:i1].mean())
    k = int(np.argmax(dev))
    res['height_dev_max_at_s'] = G.rd(t[i0 + k], 2)
    v['height_within_0p10'] = float(dev.max()) <= c['height_tol_m']
    # touchdown and motors off
    after = np.arange(len(t)) >= i1
    touch = np.where(after & (h <= c['touch_h_m']))[0]
    if not len(touch):
        v['touchdown_found'] = False
        return res, v
    t_td = float(t[touch[0]])
    v['touchdown_found'] = True
    res['touchdown_s'] = G.rd(t_td, 3)
    off = np.where((d['st_t'] >= t_td) & (d['arming_state'] != G.ARMED))[0]
    if not len(off):
        v['motors_off_found'] = False
        return res, v
    t_off = float(d['st_t'][off[0]])
    v['motors_off_found'] = True
    res['motors_off_s'] = G.rd(t_off, 3)
    res['motors_off_after_touchdown_s'] = G.rd(t_off - t_td, 3)
    v['motors_off_le_3s'] = (t_off - t_td) <= c['motors_off_s']
    return res, v


def main(argv):
    if not argv or argv[0].startswith('-'):
        print(__doc__)
        return 2
    run = argv[0].rstrip('/')
    opt = lambda k, dflt: argv[argv.index(k) + 1] if k in argv else dflt  # noqa: E731
    out = opt('--out', run)
    for b in ('c5_eval.json', 'c5_eval.txt'):
        if os.path.exists(os.path.join(out, b)):
            print('refusing to overwrite ' + os.path.join(out, b))
            return 2
    res = {'run': run, 'criteria': 'C5 approved 09.11 + КРИТЕРИИ_ТОЛКОВАНИЯ_20261109.md', 'numbers': C5}
    validity = G.stand_validity(run)
    res['validity'] = validity
    lines = {'run_valid': validity['valid']}
    path, src, problem = G.script_source(run, opt('--script', None))
    res['script'] = {'path': path, 'problem': problem}
    H = None
    if src is not None:
        try:
            H = script_height(src)
        except (ValueError, SyntaxError) as e:
            res['script']['problem'] = str(e)
    lines['script_height_known'] = H is not None
    res['script_height_m'] = H
    code, how = G.script_exit(run)
    res['script_exit'] = {'code': code, 'how': how}
    ulg = G.find_ulog(run, opt('--ulog', None))
    res['ulog'] = ulg
    if ulg is None:
        lines['took_off'] = False
        res['note'] = 'no ULog: the vehicle never armed'
    elif H is not None:
        T = G.world_to_map(os.path.join(run, 'world.sdf'), opt('--map', G.MAP_FILE))
        d = G.load_ulog(ulg, T)
        r, v = evaluate(d, H, code, how, src, G.read_script_log(run))
        res.update(r)
        lines.update(v)
    word, failed = G.verdict(lines, NEED)
    res.update({'verdict_lines': lines, 'failed': failed, 'C5': word})
    L = ['C5 %s  failed: %s' % (word, ', '.join(failed) or '-'),
         'run %s; valid %s %s; script %s H=%s %s; exit %s (%s)' % (
             os.path.basename(run), validity['valid'], validity['invalid_reasons'], path, H, problem or '', code, how)]
    if 'window' in res:
        L.append('window %s..%s s (%s); height dev max %s m at %s s (need <=0.10), mean %s m' % (
            res['window']['from_s'], res['window']['to_s'], res['window']['ends_because'], res['height_dev_max_m'],
            res['height_dev_max_at_s'], res['height_mean_m']))
    if 'touchdown_s' in res:
        L.append('touchdown %s s, motors off %s s, delay %s s (need <=3.0)' % (
            res['touchdown_s'], res.get('motors_off_s'), res.get('motors_off_after_touchdown_s')))
    L.append('emergencies: %s' % (('not evaluated' if 'emergencies' not in res else res['emergencies'] or '-')))
    if res.get('note'):
        L.append(res['note'])
    try:
        G.write_out(out, 'c5_eval', res, L)
    except FileExistsError as e:
        print(e)
        return 2
    print('\n'.join(L))
    return 0 if word == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
