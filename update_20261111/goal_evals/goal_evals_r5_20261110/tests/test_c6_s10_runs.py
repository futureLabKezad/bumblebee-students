#!/usr/bin/env python3
"""r5 (10.11): c6_eval.py on the real Gazebo runs s10_c6r6_01..10 (/work/goal_step5b_20261109/runs, read only).
Expected (chat 1, recounted from the ULogs): 06/07/08 FAIL by no_jump_a_ekf alone (EKF jumps of 0.101 / 0.116 /
0.123 m on the takeoff, before the hover window; r4 passed them); the other seven PASS by their own facts.
A missing run folder is an error, not a skip. Run: python3 -I -B -W ignore tests/test_c6_s10_runs.py -v"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import c6_eval as E  # noqa: E402

RUNS = '/work/goal_step5b_20261109/runs/s10_c6r6_%02d'
EXPECT = {i: ('FAIL', ['no_jump_a_ekf']) if i in (6, 7, 8) else ('PASS', []) for i in range(1, 11)}


class S10Runs(unittest.TestCase):
    def check(self, i):
        out = tempfile.mkdtemp(prefix='c6s10_')
        try:
            with redirect_stdout(io.StringIO()):
                code = E.main([RUNS % i, '--out', os.path.join(out, 'o')])
            res = json.load(open(os.path.join(out, 'o', 'c6_eval.json'), encoding='utf-8'))
        finally:
            shutil.rmtree(out)
        word, failed = EXPECT[i]
        self.assertEqual((res['C6'], res['failed']), (word, failed), i)
        self.assertEqual(code, 0 if word == 'PASS' else 1)
        self.assertTrue(res['jump_a_scope'].startswith('armed flight'), res['jump_a_scope'])
        jumped = res['jump_a_ekf_resets'] or res['jump_a_ekf_max_move_lt_0p2s_m'] > 0.10
        self.assertEqual(bool(jumped), word == 'FAIL', res['jump_a_ekf_max_move_lt_0p2s_m'])
        if word == 'FAIL':   # the jump is on the takeoff, before the hover window
            at = res['jump_a_ekf_at_s'][1]
            self.assertLess(at, res['window']['from_s'])
        return res


for _i in range(1, 11):
    setattr(S10Runs, 'test_s10_c6r6_%02d' % _i, lambda self, i=_i: self.check(i))

if __name__ == '__main__':
    unittest.main()
