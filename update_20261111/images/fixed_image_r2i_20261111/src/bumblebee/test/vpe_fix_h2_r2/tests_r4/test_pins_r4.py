#!/usr/bin/env python3
"""Code pins round 4 (r2i, T46 11.11.2026): src/python/vpe_fix.py (r2i) against r2h's vpe_fix
(ref/vpe_fix_r2h_66d806ba.py, a byte copy of fixed_image_r2h_20261110, sha 66d806ba).

The chain stays pinned: tests_r2/test_pins_r2.py pins the r2g copy (c33 -> P1 -> H2 -> r2g), tests_r3/test_pins_r3.py
pins the r2h copy against the r2g copy (CMake: PIN_TARGET = the r2h copy since r2i), this file pins r2i against the
r2h copy. Same AST method.

Allowed to differ (owner 11.11 «Зрение при посадке»: publish in AUTO.LAND on the same vision condition):
  VpeFix.__init__        new state: in_auto_land (the last reported mode was AUTO.LAND)
  VpeFix._evaluate_gate  OFFBOARD or AUTO.LAND -> the vision condition; any other armed mode: no publish
  VpeFix.state_callback  records in_auto_land; a change of it re-evaluates the gate at once (P1b)
  module docstring       the gate description (three lines)
Nothing added or removed. B1/B2 of r2h, P1 state knowledge, H2 parameter gate, guards, reseed, constants: AST-identical.
Content: the three changed parts are pinned to the accepted r2i (sha256 of ast.dump; Python 3.12 = Jazzy).

Env: PIN_TARGET (file under test), PIN_R2H (the r2h copy), PIN_HARNESS (tests_existing/harness)
"""
import ast
import hashlib
import importlib.util
import os
import sys
import unittest

TARGET = os.environ['PIN_TARGET']
R2H = os.environ['PIN_R2H']
HARNESS = os.environ['PIN_HARNESS']
sys.path.insert(0, os.path.join(os.path.dirname(HARNESS), 'offline_suite'))
import rosstub  # noqa: E402
rosstub.install()
R2H_SHA = '66d806baf5ef6884'
CHANGED = {'VpeFix.__init__', 'VpeFix._evaluate_gate', 'VpeFix.state_callback'}
DIGESTS = {
    'VpeFix.__init__': 'c86e039fdc23c401a1e22e73faf99e9058ae329f578817327c53ffcdaf6bca1b',
    'VpeFix._evaluate_gate': 'cc12ac14d7f814f55f02b6416b09fc52c560f0a51fdcfd5e0a724714331f2225',
    'VpeFix.state_callback': 'cd3612b2077fcce30cb79a148b59877a65a3e6d013672b806540fb38d1c2036a',
}
DOC_OLD = ['    - ARMED in non-OFFBOARD mode.',
           '    - ARMED + OFFBOARD + vision bad. Baro is secondary altitude source.']
DOC_NEW = ['    - ARMED + AUTO.LAND + the same vision condition (r2i, owner 11.11: vision while landing).',
           '    - ARMED in any other mode (pilot: STABILIZED, ALTCTL, POSCTL, ...; other AUTO modes).',
           '    - ARMED + OFFBOARD/AUTO.LAND + vision bad. Baro is secondary altitude source.']


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tree(path):
    return ast.parse(open(path).read())


def parts(t):
    out = {}
    body = t.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]                                   # the module docstring: compared separately
    for n in body:
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


class PinsR4(unittest.TestCase):
    def test_r4_reference_is_r2h(self):
        with open(R2H, 'rb') as h:
            self.assertTrue(hashlib.sha256(h.read()).hexdigest().startswith(R2H_SHA))

    def test_r4_only_the_declared_parts_differ_from_r2h(self):
        a, b = parts(tree(R2H)), parts(tree(TARGET))
        self.assertEqual({k for k in a if k in b and a[k] != b[k]}, CHANGED)
        self.assertEqual(set(b) - set(a), set())
        self.assertEqual(set(a) - set(b), set())

    def test_r4_declared_parts_are_the_accepted_r2i(self):
        self.assertEqual(set(DIGESTS), CHANGED)
        b = parts(tree(TARGET))
        for k, v in DIGESTS.items():
            self.assertEqual(hashlib.sha256(b[k].encode()).hexdigest(), v, k)

    def test_r4_docstring_only_the_gate_lines(self):
        da, db = ast.get_docstring(tree(R2H), clean=False), ast.get_docstring(tree(TARGET), clean=False)
        la, lb = da.split('\n'), db.split('\n')
        self.assertEqual([x for x in la if x not in lb], DOC_OLD)
        self.assertEqual([x for x in lb if x not in la], DOC_NEW)

    def test_r4_constants_and_harness(self):
        a, b = parts(tree(R2H)), parts(tree(TARGET))
        for k, v in a.items():
            if k.startswith('const '):
                self.assertEqual(b.get(k), v, k)
        mod = load(TARGET, 'pin_r4_target')
        fresh = load(os.path.join(HARNESS, 'vpe_freshness_optin_c09.py'), 'pin_r4_fresh')
        for k, v in fresh._EXPECTED_CONSTANTS.items():
            self.assertEqual(getattr(mod, k), v, k)


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, descriptions=False))
