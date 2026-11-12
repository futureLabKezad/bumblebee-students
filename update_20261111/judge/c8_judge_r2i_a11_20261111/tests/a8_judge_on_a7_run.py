#!/usr/bin/env python3
"""A8: the A8 judge on a real 4061 run of A7 (INT_flight_C8a7_kill_01, judged by A7 as pass).
 - as c8_4061: every legacy check and the scenario status equal A7's own review (the A8 judge copy behaves as A7's);
 - as c8_4070: only candidate4030 (SYS_AUTOSTART expected 4070) and real_parameters_before_arm fail, the latter with
   exactly the EXPECT_4070 names whose 4061 value differs (BAT1_SOURCE 1 -> 0, SDLOG_MODE 0 -> 1 on this run).
argv: OUT_DIR (inside this package's reviews/)"""
import ast
import json
import subprocess
import sys
from pathlib import Path

D = Path('/work/c8_judge_r2i_a11_20261111')
A7 = Path('/work/c8_judge_r2e_a7_20261110')
RUN = Path('/work/sim/runs/INT_flight_C8a7_kill_01')
PY = '/work/analysis/layout/.venv/bin/python'
out = Path(sys.argv[1])
src = (D / 'tools/make_a11.py').read_text()
EXPECT = [ast.literal_eval(n.value) for n in ast.parse(src).body
          if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'EXPECT_4070' for t in n.targets)][0]
ref = json.load(open(A7 / 'reviews/INT_flight_C8a7_kill_01_review.json'))
res = {}
for ident in ('c8_4061', 'c8_4070'):
    o = out / ('a7kill_as_%s.json' % ident)
    subprocess.run([PY, '-B', '-I', str(D / 'verify_flight_c8.py'), '--identity', ident, '--run', str(RUN),
                    '--expected-manifest', str(A7 / 'candidate/manifest.json'),
                    '--frozen-pins', str(A7 / 'pins/frozen_inputs_c8_r2e_a7_01.json'), '--out', str(o)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res[ident] = json.load(open(o))
la = ref['legacy_full_report']['checks']
b = res['c8_4061']; lb = b['legacy_full_report']['checks']
assert set(la) == set(lb) and all(la[k]['status'] == lb[k]['status'] for k in la), [k for k in la if la[k]['status'] != lb[k]['status']]
assert b['scenario_status'] == ref['scenario_status'] == 'pass'
c = res['c8_4070']; lc = c['legacy_full_report']['checks']
diff = sorted(k for k in la if la[k]['status'] != lc[k]['status'])
assert diff == ['candidate4030', 'real_parameters_before_arm'], diff
assert set(lc['candidate4030']['evidence']['mismatches']) == {'SYS_AUTOSTART'} and \
    lc['candidate4030']['evidence']['mismatches']['SYS_AUTOSTART'] == {'actual': 4061, 'expected': 4070}
mm = lc['real_parameters_before_arm']['evidence']['mismatches']
# A9 (S1 of the A8 review): every EXPECT_4070 name must really be judged (not only the ones that differ here)
assert set(EXPECT) <= set(lc['real_parameters_before_arm']['evidence']['values']), sorted(EXPECT)
want = {k for k, (v, t) in EXPECT.items()
        if lc['real_parameters_before_arm']['evidence']['values'].get(k) is not None
        and abs(float(lc['real_parameters_before_arm']['evidence']['values'][k]) - v) > .001}
assert set(mm) == want and {'BAT1_SOURCE', 'SDLOG_MODE'} <= want, (mm, want)
assert all(mm[k]['expected'] == EXPECT[k][0] for k in mm)
assert c['scenario_status'] == 'failed'
print('A8 judge on A7 kill_01: c8_4061 = A7 review (pass); c8_4070 fails only on', diff, {k: (v['actual'], v['expected']) for k, v in mm.items()})
