#!/usr/bin/env python3
"""Do the synthetic tests catch a loosened or broken evaluator? Each mutation goes into a COPY of the three files
in a temporary folder; the tests must FAIL on every copy. Run: python3 -I -B tests/mutation_check.py"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FILES = ('goal_common.py', 'c5_eval.py', 'c7_eval.py')

MUTATIONS = [
    ('c5_eval.py', 'C5 height tol 0.15', "'height_tol_m': 0.10", "'height_tol_m': 0.15"),
    ('c5_eval.py', 'C5 motors 3.5 s', "'motors_off_s': 3.0", "'motors_off_s': 3.5"),
    ('c5_eval.py', 'C5 mean instead of max', "dev = np.abs(h[i0:i1] - H)", "dev = np.abs(h[i0:i1].mean() - H)[None]"),
    ('c5_eval.py', 'C5 touchdown at 5 cm', "'touch_h_m': 0.01", "'touch_h_m': 0.05"),
    ('c5_eval.py', 'C5 height from default', "return float(node.value)", "return 1.0"),
    ('c5_eval.py', 'C5 touchdown waits for low speed (r1)', "touch = np.where(after & (h <= c['touch_h_m']))[0]",
     "touch = np.where(after & (h <= c['touch_h_m']) & (d['vz_up'] > -0.1))[0]"),
    ('goal_common.py', 'failsafe_flags ignored', "        for k, a in sorted(d['ff'].items()):",
     "        for k, a in []:"),
    ('goal_common.py', 'any flag allowed after landing', "if k in FF_AFTER_LAND_OK and first_req",
     "if first_req"),
    ('goal_common.py', 'Hold not an emergency',
     "            out.append('nav_state AUTO.LOITER (Hold) at %.2f s, not requested by the script' % t)",
     "            pass"),
    ('goal_common.py', 'r3: Hold by the text of the source (r2)', "        if not hold_requested(d, t, script_log):",
     "        if 'AUTO.LOITER' not in (script_src or ''):"),
    ('goal_common.py', 'r3: Hold by any DO_SET_MODE', "lambda c, p2, p3: (c == 176) & (p2 == 4) & (p3 == 3))",
     "lambda c, p2, p3: c == 176)"),
    ('goal_common.py', 'r3: guard landing ignored', "        if g:\n", "        if False:\n"),
    ('goal_common.py', 'r3: Guard /land line not a guard', "\n                               r'|Guard /land')", ")"),
    ('goal_common.py', 'r3: guard reason list shortened', "(Vision lost|Telemetry stale|EKF z=|Altitude overshoot|"
     "Position jump).*landing", "(Vision lost|Position jump).*landing"),
    ('goal_common.py', 'r3: no script.log passes', "        out.append('script.log missing: script landings not evaluated')",
     "        pass"),
    ('goal_common.py', 'r3: no failsafe_flags passes', "        out.append('failsafe_flags not in ULog: not evaluated')",
     "        pass"),
    ('goal_common.py', 'r3: no from_external passes', "    if d.get('cmd_ext_logged') is False:", "    if False:"),
    ('goal_common.py', 'r3: from_external ignored', " & np.asarray(d['cmd_ext'], bool)", ""),
    ('goal_common.py', 'r3: any DO_SET_MODE is a landing', "((c == 176) & (p2 == 4) & (p3 == 6))", "(c == 176)"),
    ('c5_eval.py', 'r3: C5 window starts 1 s late', "    i0 = int(np.argmax(band))",
     "    i0 = int(np.searchsorted(t, t[int(np.argmax(band))] + 1.0))"),
    ('c5_eval.py', 'r3: C5 window ends 1 s early', "    i1 = int(ends[0]) if len(ends) else len(t)",
     "    i1 = int(np.searchsorted(t, t[int(ends[0])] - 1.0)) if len(ends) else len(t)"),
    ('c7_eval.py', 'r3: C7 rounding before the point compare', "all(p['_err'] <= c['point_m'] for p in worst)",
     "all(round(p['_err'], 3) <= c['point_m'] for p in worst)"),
    ('c7_eval.py', 'r3: C7 rounding before the landing compare', "v['landing_within_0p15'] = dist0 <= c['landing_m']",
     "v['landing_within_0p15'] = round(dist0, 3) <= c['landing_m']"),
    ('c7_eval.py', 'r3: re-target radius 1 m', "radius = DEFAULT_TOL if k == 1 else route[k - 2][2]", "radius = 1.0"),
    ('c7_eval.py', 'r3: no re-targets allowed (r2)',
     "        return all(np.linalg.norm(H[j][2][:2] - H[prev][2][:2]) <= radius for j in range(prev + 1, nxt))",
     "        return nxt == prev + 1"),
    ('c7_eval.py', 'r3: point ends at its own hold (re-target ends it)',
     "b = H[idx[k + 2] - 1][1] if k + 2 < len(idx) else H[-1][1]", "b = H[i][1]"),
    ('c7_eval.py', 'C7 hold ends one sample early', "end = ts[j + 1] if j + 1 < len(ts) else t_to",
     "end = ts[j] if j + 1 < len(ts) else t_to"),
    ('c7_eval.py', 'C7 window ends 1 s before the next command', "                w = (t >= t_arr) & (t <= b)\n",
     "                w = (t >= t_arr) & (t <= b - 1.0)\n"),
    ('c7_eval.py', 'C7 window starts 2 s after arrival', "                w = (t >= t_arr) & (t <= b)\n",
     "                w = (t >= t_arr + 2.0) & (t <= b)\n"),
    ('c7_eval.py', 'C7 hold merge 0.3 m', "'hold_merge_m': 0.05", "'hold_merge_m': 0.3"),
    ('c7_eval.py', 'C7 landing mean 3-4 s after motors off',
     "w = (t >= t_off) & (t <= t_off + c['stand_after_off_s'])", "w = (t >= t_off + 3.0) & (t <= t_off + 4.0)"),
    ('goal_common.py', 'AUTO.LAND always counted as landing', "        if not land_requested(d, t, script_log):",
     "        if False:"),
    ('goal_common.py', 'script.log not needed for landing',
     "    if not script_log or not LAND_REQUEST_LOG.search(script_log):\n        return False", "    pass"),
    ('goal_common.py', 'landing command window 10 s', "LAND_CMD_WINDOW_S = 2.0", "LAND_CMD_WINDOW_S = 10.0"),
    ('c5_eval.py', 'C5 emergencies ignored', "v['no_emergency'] = not emerg", "v['no_emergency'] = True"),
    ('goal_common.py', 'exit code ignored', "    elif code != 0:", "    elif False:"),
    ('goal_common.py', 'unknown exit passes', "        out.append('script exit code unknown')", "        pass"),
    ('goal_common.py', 'DESCEND not an emergency', "12: 'DESCEND', ", ""),
    ('goal_common.py', 'took-over ignored', "    if np.any(d['user_took_over']):", "    if False:"),
    ('goal_common.py', 'missing line passes', "failed += ['not evaluated: ' + k for k in need if k not in lines]",
     "pass"),
    ('goal_common.py', 'sha not checked', "    if have != want:", "    if False:"),
    ('goal_common.py', 'date in fingerprint', "line.startswith('date ')", "line.startswith('@@@')"),
    ('c7_eval.py', 'C7 point 0.30', "'point_m': 0.25", "'point_m': 0.30"),
    ('c7_eval.py', 'C7 landing 0.20', "'landing_m': 0.15", "'landing_m': 0.20"),
    ('c7_eval.py', 'C7 9 in a row', "'in_a_row': 10", "'in_a_row': 9"),
    ('c7_eval.py', 'C7 only the moment of the next command', "e = float(max(err.max(), at_next))",
     "e = float(at_next)"),
    ('c7_eval.py', 'C7 flown not compared', "v['route_flown_as_coded'] = (flown is not None",
     "v['route_flown_as_coded'] = True or (flown is not None"),
    ('c7_eval.py', 'C7 intervention ignored', "v['offboard_until_land'] = bool(len(lands)) and not other",
     "v['offboard_until_land'] = bool(len(lands))"),
    ('c7_eval.py', 'C7 leg check off', "                if abs(want - have) > c['leg_match_m']:\n                    continue",
     "                if False:\n                    continue"),
    ('c7_eval.py', 'C7 fail does not reset', "s['in_a_row'] = s['in_a_row'] + 1 if r['C7'] == 'PASS' else 0",
     "s['in_a_row'] = s['in_a_row'] + (1 if r['C7'] == 'PASS' else 0)"),
    ('c7_eval.py', 'C7 change does not restart', "            s['in_a_row'] = 0\n            note",
     "            note"),
    ('c7_eval.py', 'C7 one script enough', "all(\n                done.get(k)", "any(\n                done.get(k)"),
]

missed = 0
for fname, name, old, new in MUTATIONS:
    src = open(os.path.join(ROOT, fname), encoding='utf-8').read()
    assert src.count(old) == 1, 'anchor not unique/absent: ' + name
    d = tempfile.mkdtemp(prefix='goalevalsmut_')
    try:
        os.makedirs(os.path.join(d, 'tests'))
        for f in FILES:
            shutil.copy(os.path.join(ROOT, f), d)
        open(os.path.join(d, fname), 'w', encoding='utf-8').write(src.replace(old, new))
        shutil.copy(os.path.join(HERE, 'test_goal_evals.py'), os.path.join(d, 'tests'))
        r = subprocess.run([sys.executable, '-I', '-B', '-W', 'ignore', os.path.join(d, 'tests', 'test_goal_evals.py')],
                           capture_output=True, text=True)
        caught = r.returncode != 0
        missed += not caught
        print('%-8s %s' % ('CAUGHT' if caught else 'MISSED', name))
    finally:
        shutil.rmtree(d)
print('%d/%d mutations caught' % (len(MUTATIONS) - missed, len(MUTATIONS)))
sys.exit(1 if missed else 0)
