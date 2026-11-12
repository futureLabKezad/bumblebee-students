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
    ('goal_common.py', 'Hold not an emergency', "if int(n) == LOITER and", "if False and"),
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
    ('c7_eval.py', 'C7 only the moment of the next command', "'err_m': G.rd(max(err.max(), at_next))",
     "'err_m': G.rd(at_next)"),
    ('c7_eval.py', 'C7 flown not compared', "v['route_flown_as_coded'] = (flown is not None",
     "v['route_flown_as_coded'] = True or (flown is not None"),
    ('c7_eval.py', 'C7 intervention ignored', "v['offboard_until_land'] = bool(len(lands)) and not other",
     "v['offboard_until_land'] = bool(len(lands))"),
    ('c7_eval.py', 'C7 leg check off', "ok = ok and abs(want - have) <= c['leg_match_m']", "pass"),
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
