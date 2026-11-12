#!/usr/bin/env python3
"""A8: the judge with --identity c8_4070 on the rel3 kill run (airframe 4030, 20EC-file values) against the same run
judged as c8_4061 (test 9 of test_c8_b2.sh). Expected: every check the same, except real_parameters_before_arm and
candidate4030 (SYS_AUTOSTART expected 4070), where the c8_4070 expectation adds exactly the EXPECT_4070 names.
argv: REVIEW_AS_C8_4061 REVIEW_AS_C8_4070"""
import ast
import json
import sys
from pathlib import Path

D = Path('/work/c8_judge_r2f_a8_20261110')
src = (D / 'tools/make_a8.py').read_text()
EXPECT = [ast.literal_eval(n.value) for n in ast.parse(src).body
          if isinstance(n, ast.Assign) and any(getattr(t, 'id', None) == 'EXPECT_4070' for t in n.targets)][0]
a, b = (json.load(open(p)) for p in sys.argv[1:3])
la, lb = a['legacy_full_report']['checks'], b['legacy_full_report']['checks']
assert set(la) == set(lb)
same = sorted(k for k in la if k not in ('candidate4030', 'real_parameters_before_arm') and la[k] != lb[k])
assert not same, same
assert lb['candidate4030']['status'] == 'failed' and lb['candidate4030']['evidence']['mismatches']['SYS_AUTOSTART']['expected'] == 4070
ra, rb = la['real_parameters_before_arm']['evidence'], lb['real_parameters_before_arm']['evidence']
assert lb['real_parameters_before_arm']['status'] == 'failed'
assert rb['expected_count'] == ra['expected_count'] + len([k for k in EXPECT if k not in ra['values']]), (ra['expected_count'], rb['expected_count'])
assert [s['path'] for s in rb['sources']] == [str(D / 'expect/flight_real_params_4070.json'), str(D / 'expect/rc_real_params_4070.json')]
exp_b = {k: v['expected'] for k, v in rb['mismatches'].items()}
exp_a = {k: v['expected'] for k, v in ra['mismatches'].items()}
# the 4061 mismatches stay, with the 4070 value where EXPECT_4070 sets one; each EXPECT_4070 name is checked
for k, v in exp_a.items():
    if k not in EXPECT:
        assert exp_b[k] == v, (k, exp_b.get(k), v)
for k, (v, t) in EXPECT.items():
    actual = rb['values'].get(k)
    assert k in rb['values'], k
    if actual is None:
        assert k in rb['missing'], k
    elif abs(float(actual) - v) > .001:
        assert exp_b[k] == v, (k, exp_b.get(k))
    else:
        assert k not in rb['mismatches'], k
assert set(exp_b) - set(exp_a) <= set(EXPECT)
assert a['provenance'] == b['provenance'] and a['supplementary'] == b['supplementary'] and a['profile19'] == b['profile19']
print('c8_4070 vs c8_4061 on rel3 kill: only candidate4030 / real_parameters_before_arm differ; 4070 mismatches',
      {k: (rb['values'].get(k), exp_b.get(k)) for k in sorted(exp_b)})
