#!/usr/bin/env python3
"""Do the synthetic tests catch a loosened or broken c6_eval.py (edition r2)? Each mutation goes into a COPY in a
temporary folder (with goal_common.py, c5_eval.py, c7_eval.py next to it); the tests must FAIL on every copy.
r5: mutations named 'r5:' also run tests/test_c6_s10_runs.py (real runs s10_c6r6_01..10); both results are printed.
Run: python3 -I -B tests/mutation_check_c6.py"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(os.path.dirname(HERE), 'c6_eval.py'), encoding='utf-8').read()

MUTATIONS = [
    ('share 0.90', "'share_min': 0.95", "'share_min': 0.90"),
    ('max offset 0.25', "'offset_max_m': 0.20", "'offset_max_m': 0.25"),
    ('height tol 0.15', "'height_tol_m': 0.10", "'height_tol_m': 0.15"),
    ('hover 50 s', "'hover_s': 60.0", "'hover_s': 50.0"),
    ('jump b horizontal only', "P3 = np.column_stack([xyw, hw])", "P3 = xyw"),
    ('jump a neighbours only', "for k in range(1, n):", "for k in range(1, min(n, 2)):"),
    ('z resets ignored', "('ekf_z_reset', 'ekf_delta_z', 'z')", "('ekf_xy_reset', 'ekf_delta_xy', 'xy')"),
    ('offset from takeoff point', "off = np.linalg.norm(xyw - np.asarray(marker0), axis=1)",
     "off = np.linalg.norm(xyw - xy[0], axis=1)"),
    ('window ignores leaving OFFBOARD', "((nav != OFFBOARD) | ~armed)", "(~armed)"),
    ('emergency list ignored', "v['no_emergency'] = not emerg", "v['no_emergency'] = True"),
    ('emergency not computed passes', "    if emerg is not None:          #", "    if True:          #"),
    ('own short list instead of the shared one', "emerg = G.emergencies(dc, code, how, src, G.read_script_log(run))",
     "emerg = []"),
    ('r3: script sha not required', "v['script_matches_versions'] = src is not None",
     "v['script_matches_versions'] = True"),
    ('r3: sha line not needed', "'no_emergency', 'script_matches_versions']", "'no_emergency']"),
    ('missing line counts as pass', "failed += ['not evaluated: ' + k for k in need if k not in lines]", "pass"),
    ('r5: jump a only in the hover window (r4)', "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool)",
     "    ew = (et >= t[i0]) & (et < t_end)"),
    ('r5: jump a ends at the window end', "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool)",
     "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool) & (et < t_end)"),
    ('r5: jump a starts at the window', "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool)",
     "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool) & (et >= t[i0])"),
    ('r5: jump a also before arming', "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool)",
     "    ew = np.ones(len(et), bool)"),
    ('r5: arming sample left out', "    ew = _step(d['arm_t'], d['armed'], et, False).astype(bool)",
     "    ew = _step(d['arm_t'] + 1e-6, d['armed'], et, False).astype(bool)"),
    ('settling forgiven', "tw, xyw, hw = t[w], xy[w], h[w]",
     "tw, xyw, hw = t[w][250:], xy[w][250:], h[w][250:]"),
]

missed = 0
for name, old, new in MUTATIONS:
    assert SRC.count(old) == 1, 'anchor not unique/absent: ' + name
    d = tempfile.mkdtemp(prefix='c6evalmut_')
    try:
        os.makedirs(os.path.join(d, 'tests'))
        for f in ('goal_common.py', 'c5_eval.py', 'c7_eval.py'):
            shutil.copy(os.path.join(os.path.dirname(HERE), f), d)
        open(os.path.join(d, 'c6_eval.py'), 'w', encoding='utf-8').write(SRC.replace(old, new))
        shutil.copy(os.path.join(HERE, 'test_c6_eval.py'), os.path.join(d, 'tests'))
        shutil.copy(os.path.join(HERE, 'test_c6_s10_runs.py'), os.path.join(d, 'tests'))
        r = subprocess.run([sys.executable, '-I', '-B', '-W', 'ignore', os.path.join(d, 'tests', 'test_c6_eval.py')],
                           capture_output=True, text=True)
        caught = r.returncode != 0
        extra = ''
        if name.startswith('r5:'):
            r2 = subprocess.run([sys.executable, '-I', '-B', '-W', 'ignore',
                                 os.path.join(d, 'tests', 'test_c6_s10_runs.py')], capture_output=True, text=True)
            extra = '   (synthetic %s, s10 runs %s)' % ('fail' if caught else 'pass',
                                                     'fail' if r2.returncode != 0 else 'pass')
            caught = caught or r2.returncode != 0
        missed += not caught
        print('%-8s %s%s' % ('CAUGHT' if caught else 'MISSED', name, extra))
    finally:
        shutil.rmtree(d)
print('%d/%d mutations caught' % (len(MUTATIONS) - missed, len(MUTATIONS)))
sys.exit(1 if missed else 0)
