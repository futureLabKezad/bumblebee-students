#!/usr/bin/env python3
"""r2h code pins (no ROS): vpe_fix.py r2h against r2g's vpe_fix.py (3b8a93d4), part by part (the AST method of
src/bumblebee/test/vpe_fix_h2_r2/tests_r2/test_pins_r2.py, which is NOT edited: it pins the vision path to the c33
product and fails on r2h by design -- see README).

Allowed to differ (r2h B1/B2), each with its reason:
  VpeFix.__init__              new state: markers_pos_time (B1), _recent_poses / _last_publish_time / _reentry_* (B2)
  VpeFix._single_marker_fresh  B1: >= 1 marker within 1.5 s instead of "the last message >= 1"
  VpeFix.markers_used_callback B1: records markers_pos_time; re-evaluates the gate on every message
  VpeFix.yaw_locked_callback   B1: re-evaluates the gate when yaw_locked changes
  VpeFix.aruco_map_callback    B2: an accepted pose is also kept in _recent_poses (one line)
  VpeFix.publish_timer         B2: publishes _reentry_pose(now); stamps _last_publish_time
  VpeFix._maybe_reseed         B2 (review S2): a reseed restarts _recent_poses with the seed (two lines)
Added: VpeFix._reentry_pose, constants _REENTRY_GAP / _REENTRY_N / _REENTRY_HOLD / _REENTRY_MAX_WAIT. Nothing removed.
Everything else (P1 state logic, _evaluate_gate, _apply_gate, guards, reseed, the parameter gate, constants) is
AST-identical to r2g. Also: aruco_map_callback differs from r2g by exactly one added statement.
Run: python3 -B test/test_pins_r2h.py -v
"""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R2H = ROOT / 'src/bumblebee/src/python/vpe_fix.py'
R2G = Path('/work/fixed_image_r2g_20261110/src/bumblebee/src/python/vpe_fix.py')
CHANGED = {'VpeFix.__init__', 'VpeFix._single_marker_fresh', 'VpeFix.markers_used_callback',
           'VpeFix.yaw_locked_callback', 'VpeFix.aruco_map_callback', 'VpeFix.publish_timer', 'VpeFix._maybe_reseed'}
ADDED = {'VpeFix._reentry_pose', 'const _REENTRY_GAP', 'const _REENTRY_N', 'const _REENTRY_HOLD', 'const _REENTRY_MAX_WAIT'}


def parts(path):
    t = ast.parse(path.read_text())
    out = {}
    for n in t.body:
        if isinstance(n, ast.Assign):
            for n2 in n.targets:
                if isinstance(n2, ast.Name):
                    out['const ' + n2.id] = ast.dump(n.value)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out['import ' + ast.dump(n)] = ''
        elif isinstance(n, ast.ClassDef) and n.name == 'VpeFix':
            out['class VpeFix bases'] = repr([ast.dump(b) for b in n.bases])
            out['class VpeFix non-method body'] = repr([ast.dump(m) for m in n.body if not isinstance(m, ast.FunctionDef)])
            for m in n.body:
                if isinstance(m, ast.FunctionDef):
                    out['VpeFix.' + m.name] = ast.dump(m)
        elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out[n.name] = ast.dump(n)
        else:
            out['stmt ' + ast.dump(n)] = ''
    return out


def method(path, name):
    t = ast.parse(path.read_text())
    return [m for n in t.body if isinstance(n, ast.ClassDef) and n.name == 'VpeFix' for m in n.body
            if isinstance(m, ast.FunctionDef) and m.name == name][0]


class PinsR2H(unittest.TestCase):
    def test_only_the_declared_parts_differ_from_r2g(self):
        a, b = parts(R2G), parts(R2H)
        self.assertEqual({k for k in a if k in b and a[k] != b[k]}, CHANGED)
        self.assertEqual(set(b) - set(a), ADDED)
        self.assertEqual(set(a) - set(b), set())

    def test_aruco_map_callback_one_added_statement(self):
        a, b = method(R2G, 'aruco_map_callback'), method(R2H, 'aruco_map_callback')
        sa, sb = [ast.dump(s) for s in a.body], [ast.dump(s) for s in b.body]
        self.assertEqual(len(sb), len(sa) + 1)
        extra = [s for s in sb if s not in sa]
        self.assertEqual(len(extra), 1)
        self.assertIn("attr='_recent_poses'", extra[0])
        self.assertEqual([s for s in sb if s in sa], sa)

    def test_p1_state_and_gate_decision_unchanged(self):
        for m in ('_evaluate_gate', '_apply_gate', 'state_callback', '_fcu_state_unknown', '_state_clock_ns',
                  '_state_watchdog_tick', '_gate_tick', '_multi_marker_fresh', '_medoid'):
            self.assertEqual(ast.dump(method(R2G, m)), ast.dump(method(R2H, m)), m)

    def test_gate_constants_unchanged(self):
        a, b = parts(R2G), parts(R2H)
        for c in ('_QUALITY_MULTI_TIMEOUT', '_QUALITY_SINGLE_TIMEOUT', '_GATE_HYSTERESIS', '_POSE_TIMEOUT',
                  '_XY_JUMP_MAX', '_Z_JUMP_MAX', '_MAX_VISION_SPEED', '_STATE_STALE_TIMEOUT', '_STATE_STAMP_MAX_AGE'):
            self.assertEqual(a['const ' + c], b['const ' + c], c)

    def test_r2g_is_the_reference(self):
        import hashlib
        self.assertTrue(hashlib.sha256(R2G.read_bytes()).hexdigest().startswith('3b8a93d4d0898369'))


if __name__ == '__main__':
    unittest.main()
