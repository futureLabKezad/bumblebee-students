#!/usr/bin/env python3
"""Code pins round 3 (r2h, T44 10.11.2026): the vision path of src/python/vpe_fix.py (r2h) against r2g's vpe_fix
(ref/vpe_fix_r2g_3b8a93d4.py, a byte copy of fixed_image_r2g_20261110, sha 3b8a93d4).

The chain stays pinned: tests_r2/test_pins_r2.py (not edited) now pins the r2g copy against c33 / 7f107882 (CMake:
test_vpe_fix_h2_r2_pins, PIN_TARGET = the r2g copy); this file pins r2h against that copy. Same AST method.

Allowed to differ (r2h B1/B2), each with its reason:
  VpeFix.__init__              new state: markers_pos_time (B1), _recent_poses / _last_publish_time / _reentry_* (B2)
  VpeFix._single_marker_fresh  B1: >= 1 marker within 1.5 s instead of "the last message >= 1"
  VpeFix.markers_used_callback B1: records markers_pos_time; re-evaluates the gate on every message
  VpeFix.yaw_locked_callback   B1: re-evaluates the gate when yaw_locked changes
  VpeFix.aruco_map_callback    B2: an accepted pose is also kept in _recent_poses (exactly one added statement)
  VpeFix.publish_timer         B2: publishes _reentry_pose(now); stamps _last_publish_time
  VpeFix._maybe_reseed         B2: a reseed restarts _recent_poses with the seed
Added: VpeFix._reentry_pose, constants _REENTRY_GAP 0.3 / _REENTRY_N 3 / _REENTRY_HOLD 0.5 / _REENTRY_MAX_WAIT 0.3.
Nothing removed. Everything else (P1 state logic, the gate decision, the H2 parameter gate, guards, reseed, medoid,
all other constants, imports, other classes) is AST-identical to r2g.

Content (review of the final, S1): the declared parts are also pinned to the accepted final r2h (sha256 of their
ast.dump; ast.dump is stable within a Python minor version: 3.12 = ROS 2 Jazzy, PC and drone). A change of a declared
part therefore needs a new pin round, like any other part.

Env: PIN_TARGET (file under test), PIN_R2G (the r2g copy), PIN_HARNESS (tests_existing/harness, for rosstub and
_EXPECTED_CONSTANTS, as in test_pins_r2.py)
"""
import ast
import hashlib
import importlib.util
import os
import sys
import unittest

TARGET = os.environ['PIN_TARGET']
R2G = os.environ['PIN_R2G']
HARNESS = os.environ['PIN_HARNESS']
sys.path.insert(0, os.path.join(os.path.dirname(HARNESS), 'offline_suite'))
import rosstub  # noqa: E402
rosstub.install()
R2G_SHA = '3b8a93d4d0898369'
CHANGED = {'VpeFix.__init__', 'VpeFix._single_marker_fresh', 'VpeFix.markers_used_callback',
           'VpeFix.yaw_locked_callback', 'VpeFix.aruco_map_callback', 'VpeFix.publish_timer', 'VpeFix._maybe_reseed'}
ADDED = {'VpeFix._reentry_pose', 'const _REENTRY_GAP', 'const _REENTRY_N', 'const _REENTRY_HOLD',
         'const _REENTRY_MAX_WAIT'}
DIGESTS = {
    'VpeFix.__init__': 'f7bfb962bb3258f8cb5b3f31730a61d4cf9a639c1a379eff14d721b979a5ea4b',
    'VpeFix._maybe_reseed': 'e35321f44f3fe1551a36904cd38ed92ab3a3b33c302dae1e6395c9fe6bdcd6a3',
    'VpeFix._reentry_pose': 'e2fd39815ef72dcd295852c8cc82bf8ad153b2bf7b033db6d7cbb717059ef9a5',
    'VpeFix._single_marker_fresh': 'fd8536f34866873c7ceef75e5499c2cf4ea2dc1b532e6077a9dab8d92095db82',
    'VpeFix.aruco_map_callback': '7da3d38a55f618ada8533235ebe8ca61225fc8597ef9279023a000948a0fe1fb',
    'VpeFix.markers_used_callback': '585476054dae507605de71b94e239df363f7905fcfc958006c8b0ff4b129dfe7',
    'VpeFix.publish_timer': '3c734041146f4b823a232b65f989082377effe054bb836ac371b1d5d697813ff',
    'VpeFix.yaw_locked_callback': '8cd89c71284a81e4ba0ad7a9e35b0556a81c747dca96f0351230696f7e812852',
    'const _REENTRY_GAP': 'b2c45f7fe015c16e902eaa49d31812d3cfe6d1f34a388beac50ffb8ec2518385',
    'const _REENTRY_HOLD': '58547221ee78862df0bb04b94411232b1c0ac1918af7004d5c66795b18b1b8b8',
    'const _REENTRY_MAX_WAIT': 'b2c45f7fe015c16e902eaa49d31812d3cfe6d1f34a388beac50ffb8ec2518385',
    'const _REENTRY_N': '9084d9e7883c1863a636c76e7bbb39dcab454c4a629ddb9b02e896f4c3ea1c29',
}
REENTRY = {'_REENTRY_GAP': 0.3, '_REENTRY_N': 3, '_REENTRY_HOLD': 0.5, '_REENTRY_MAX_WAIT': 0.3}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tree(path):
    return ast.parse(open(path).read())


def parts(t):
    """every top-level part: constants, imports, classes, functions, VpeFix methods, VpeFix non-method body, other
    statements"""
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
    return [m for n in tree(path).body if isinstance(n, ast.ClassDef) and n.name == 'VpeFix' for m in n.body
            if isinstance(m, ast.FunctionDef) and m.name == name][0]


class PinsR3(unittest.TestCase):
    def test_r3_reference_is_r2g(self):
        with open(R2G, 'rb') as h:
            self.assertTrue(hashlib.sha256(h.read()).hexdigest().startswith(R2G_SHA))

    def test_r3_only_the_declared_parts_differ_from_r2g(self):
        a, b = parts(tree(R2G)), parts(tree(TARGET))
        self.assertEqual({k for k in a if k in b and a[k] != b[k]}, CHANGED)
        self.assertEqual(set(b) - set(a), ADDED)
        self.assertEqual(set(a) - set(b), set())

    def test_r3_declared_parts_are_the_accepted_final(self):
        self.assertEqual(set(DIGESTS), CHANGED | ADDED)
        b = parts(tree(TARGET))
        for k, v in DIGESTS.items():
            self.assertEqual(hashlib.sha256(b[k].encode()).hexdigest(), v, k)

    def test_r3_aruco_map_callback_one_added_statement(self):
        sa = [ast.dump(s) for s in method(R2G, 'aruco_map_callback').body]
        sb = [ast.dump(s) for s in method(TARGET, 'aruco_map_callback').body]
        self.assertEqual(len(sb), len(sa) + 1)
        extra = [s for s in sb if s not in sa]
        self.assertEqual(len(extra), 1)
        self.assertIn("attr='_recent_poses'", extra[0])
        self.assertEqual([s for s in sb if s in sa], sa)

    def test_r3_p1_gate_h2_and_guard_code_unchanged(self):
        for m in ('_evaluate_gate', '_apply_gate', 'state_callback', '_fcu_state_unknown', '_state_clock_ns',
                  '_state_watchdog_tick', '_gate_tick', '_multi_marker_fresh', '_medoid', '_handle_set_param',
                  '_param_set_with_retry', '_restore_one', '_param_set_once'):
            self.assertEqual(ast.dump(method(R2G, m)), ast.dump(method(TARGET, m)), m)

    def test_r3_constants(self):
        a, b = parts(tree(R2G)), parts(tree(TARGET))
        for k, v in a.items():
            if k.startswith('const '):
                self.assertEqual(b.get(k), v, k)
        mod = load(TARGET, 'pin_r3_target')
        for k, v in REENTRY.items():
            self.assertEqual(getattr(mod, k), v, k)
        fresh = load(os.path.join(HARNESS, 'vpe_freshness_optin_c09.py'), 'pin_r3_fresh')
        for k, v in fresh._EXPECTED_CONSTANTS.items():
            self.assertEqual(getattr(mod, k), v, k)


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, descriptions=False))
