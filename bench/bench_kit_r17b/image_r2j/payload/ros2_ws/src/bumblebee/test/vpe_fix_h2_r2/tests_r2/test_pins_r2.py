#!/usr/bin/env python3
"""Code pins for the round-2 H2 candidate (new; the two P1 pins of vpe_p1_fix_02 offline_suite/test_final.py are not
edited and keep failing/passing as they do).

The same AST method as test_keep_untouched_code_and_constants / test_fix_added_methods of the P1 suite, plus a pin of
the P1 code itself against the accepted P1 file 7f107882. The only parts allowed to differ are the H2 set below, each
with its reason:

  _Override                        journal entry of one override: two new slots, unconfirmed and requested (the state
                                   of a write whose outcome is unknown). Nothing else in the class changes.
  VpeFix._handle_set_param         the gate service: keeps the entry after an unknown outcome, drops it only when no
                                   request was sent, no TTL in the air for it, clears the mark after a successful
                                   write, logs a noop that finds such an entry. EV_CTRL guard, cache checks, noop
                                   answer, first-write-wins and the success path are the 7f107882 lines.
  VpeFix._param_set_with_retry     when attempt 2 was not sent but attempt 1 was, the result says so (else the caller
                                   would take 'not sent' and drop an override PX4 may hold). Attempts, pause and log
                                   line unchanged.
  VpeFix._restore_one              never writes an unconfirmed original while armed (held for the disarm edge);
                                   '; was unconfirmed' in the restored line. Pop, cancel, write, cache update and the
                                   FAILED line unchanged.
Added: module constant _SET_NOT_SENT (the literal _param_set_once already returns). No method is added or removed.
Not touched (round 1 had changed them): VpeFix.__init__, VpeFix._on_parameter_event, VpeFix._param_set_once.

Env: PIN_TARGET (file under test), PIN_C33 (c33 copy), PIN_P1 (7f107882 copy), PIN_HARNESS (tests_existing/harness)
"""
import ast
import importlib.util
import os
import sys
import unittest

TARGET = os.environ['PIN_TARGET']
C33 = os.environ['PIN_C33']
P1 = os.environ['PIN_P1']
HARNESS = os.environ['PIN_HARNESS']
sys.path.insert(0, os.path.join(os.path.dirname(HARNESS), 'offline_suite'))
import rosstub  # noqa: E402
rosstub.install()
P1_CHANGED = {'__init__', '_evaluate_gate', 'state_callback', 'publish_timer'}            # as in test_final.py
P1_ADDED = {'_state_clock_ns', '_fcu_state_unknown', '_log_state_ignored', '_state_watchdog_tick'}
H2_CHANGED = {'_Override', 'VpeFix._handle_set_param', 'VpeFix._param_set_with_retry', 'VpeFix._restore_one'}
H2_ADDED = {'const _SET_NOT_SENT'}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def tree(path):
    return ast.parse(open(path).read())


def consts(t):
    return {n2.id: ast.dump(n.value) for n in t.body if isinstance(n, ast.Assign)
            for n2 in n.targets if isinstance(n2, ast.Name)}


def defs(t):
    """the same keys as test_final.py: top-level functions/classes by name, VpeFix methods as VpeFix.NAME"""
    out = {}
    for n in t.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name != 'VpeFix':
            out[n.name] = ast.dump(n)
        if isinstance(n, ast.ClassDef) and n.name == 'VpeFix':
            for m in n.body:
                if isinstance(m, ast.FunctionDef):
                    out['VpeFix.' + m.name] = ast.dump(m)
    return out


def parts(t):
    out = {'const ' + k: v for k, v in consts(t).items()}
    out.update(defs(t))
    for n in t.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out['import ' + ast.dump(n)] = ''
        if isinstance(n, ast.ClassDef) and n.name == 'VpeFix':
            out['class VpeFix bases'] = repr([ast.dump(b) for b in n.bases])
            out['class VpeFix non-method body'] = repr([ast.dump(m) for m in n.body
                                                        if not isinstance(m, ast.FunctionDef)])
    return out


def methods(t):
    return {m.name for n in t.body if isinstance(n, ast.ClassDef) and n.name == 'VpeFix'
            for m in n.body if isinstance(m, ast.FunctionDef)}


class PinsR2(unittest.TestCase):
    def test_r2_keep_untouched_code_and_constants_vs_c33(self):
        """test_keep_untouched_code_and_constants with the H2 set added to the P1 set, nothing else"""
        ta, tb = tree(C33), tree(TARGET)
        ca, cb = consts(ta), consts(tb)
        for k, v in ca.items():
            self.assertEqual(cb.get(k), v, k)
        da, db = defs(ta), defs(tb)
        skipped = []
        for k, v in da.items():
            if k.split('.')[-1] in P1_CHANGED or k in H2_CHANGED:
                skipped.append(k)
                continue
            self.assertEqual(db.get(k), v, k)
        self.assertEqual(sorted(skipped), sorted({'VpeFix.' + m for m in P1_CHANGED} | H2_CHANGED))
        fresh = load(os.path.join(HARNESS, 'vpe_freshness_optin_c09.py'), 'pin_fresh')
        mod = load(TARGET, 'pin_target')
        for k, v in fresh._EXPECTED_CONSTANTS.items():
            self.assertEqual(getattr(mod, k), v, k)

    def test_r2_added_methods(self):
        """test_fix_added_methods unchanged in substance: the added methods are exactly the four of P1"""
        self.assertEqual(methods(tree(TARGET)) - methods(tree(C33)), P1_ADDED)
        self.assertEqual(methods(tree(C33)) - methods(tree(TARGET)), set())

    def test_r2_p1_code_identical_to_7f107882(self):
        """every P1-changed and P1-added method and every constant is AST-identical to the accepted P1 file"""
        a, b = defs(tree(P1)), defs(tree(TARGET))
        for m in sorted(P1_CHANGED | P1_ADDED):
            self.assertIn('VpeFix.' + m, a)
            self.assertEqual(b.get('VpeFix.' + m), a['VpeFix.' + m], m)
        ca, cb = consts(tree(P1)), consts(tree(TARGET))
        for k, v in ca.items():
            self.assertEqual(cb.get(k), v, k)

    def test_r2_only_the_declared_h2_set_differs_from_7f107882(self):
        """every part of 7f107882 (constants, imports, classes, functions, methods, VpeFix body) outside the H2 set is
        AST-identical; the parts that differ are exactly the H2 set (the list is complete and not padded)"""
        a, b = parts(tree(P1)), parts(tree(TARGET))
        changed = {k for k in a if k in b and a[k] != b[k]}
        self.assertEqual(changed, H2_CHANGED)
        self.assertEqual(set(b) - set(a), H2_ADDED)
        self.assertEqual(set(a) - set(b), set())

    def test_r2_not_sent_constant_is_the_literal_of_param_set_once(self):
        mod = load(TARGET, 'pin_target2')
        src = ast.get_source_segment(open(TARGET).read(), [m for n in tree(TARGET).body if isinstance(n, ast.ClassDef)
                                                            and n.name == 'VpeFix' for m in n.body
                                                            if isinstance(m, ast.FunctionDef)
                                                            and m.name == '_param_set_once'][0])
        self.assertIn("return False, %r" % mod._SET_NOT_SENT, src.replace('"', "'"))


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2, descriptions=False))
