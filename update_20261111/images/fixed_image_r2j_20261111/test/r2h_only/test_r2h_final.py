#!/usr/bin/env python3
"""r2h FINAL against the r2h CANDIDATE (task T44, no ROS). The final = the candidate (SHA256SUMS 4f4b0ce9) plus:
  1. vpe_fix._reentry_pose: the medoid gets the fresh poses newest first, so a tie (always so with 2 poses) goes to
     the newest (SHOULD of the candidate review); nothing else in vpe_fix changes;
  2. code pins round 3: tests_r2/test_pins_r2.py (not edited) now pins the r2g copy ref/vpe_fix_r2g_3b8a93d4.py,
     tests_r3/test_pins_r3.py pins r2h against that copy (CMake: the vpe_fix block only);
  3. camera_fix.py stays the a45a264 file 4a15d699 (as r2g; Gazebo checks this one); its manifest row stays PENDING.
drone.py: the candidate's bytes. Run: python3 -B test/test_r2h_final.py -v   (from the final folder)
"""
import ast
import difflib
import filecmp
import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAND = Path('/work/fixed_image_r2h_candidate_20261110')
R2G = Path('/work/fixed_image_r2g_20261110')
assert ROOT.name == 'fixed_image_r2h_20261110', ROOT
S = 'src/bumblebee/'
VPE = S + 'src/python/vpe_fix.py'
H2 = S + 'test/vpe_fix_h2_r2/'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parts(path):
    out = {}
    for n in ast.parse(Path(path).read_text()).body:
        if isinstance(n, ast.ClassDef) and n.name == 'VpeFix':
            for m in n.body:
                out['VpeFix.' + m.name if isinstance(m, ast.FunctionDef) else 'VpeFix body ' + ast.dump(m)] = ast.dump(m)
        else:
            out[ast.dump(n)[:60] + str(getattr(n, 'lineno', ''))] = ast.dump(n)
    return out


def method(path, name):
    return [m for n in ast.parse(Path(path).read_text()).body if isinstance(n, ast.ClassDef) and n.name == 'VpeFix'
            for m in n.body if isinstance(m, ast.FunctionDef) and m.name == name][0]


def tree_files(root):
    return {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


class FinalVsCandidate(unittest.TestCase):
    def test_candidate_is_the_reviewed_one(self):
        self.assertTrue(sha(CAND / 'SHA256SUMS').startswith('4f4b0ce9'))

    def test_vpe_fix_only_reentry_pose_differs(self):
        a = {k: v for k, v in parts(CAND / VPE).items() if k.startswith('VpeFix')}
        b = {k: v for k, v in parts(ROOT / VPE).items() if k.startswith('VpeFix')}
        self.assertEqual(set(a), set(b))
        self.assertEqual({k for k in a if a[k] != b[k]}, {'VpeFix._reentry_pose'})
        # everything outside the class (constants, imports, functions): the same statements in the same order
        ta = [ast.dump(n) for n in ast.parse((CAND / VPE).read_text()).body if not (isinstance(n, ast.ClassDef) and n.name == 'VpeFix')]
        tb = [ast.dump(n) for n in ast.parse((ROOT / VPE).read_text()).body if not (isinstance(n, ast.ClassDef) and n.name == 'VpeFix')]
        self.assertEqual(ta, tb)

    def test_reentry_pose_differs_in_the_docstring_and_the_final_return_only(self):
        sa = method(CAND / VPE, '_reentry_pose').body
        sb = method(ROOT / VPE, '_reentry_pose').body
        self.assertEqual(len(sa), len(sb))
        diff = [i for i, (x, y) in enumerate(zip(sa, sb)) if ast.dump(x) != ast.dump(y)]
        self.assertEqual(diff, [0, len(sb) - 1])
        self.assertIsInstance(sb[0].value, ast.Constant)                 # the docstring
        ret = sb[-1]
        self.assertIsInstance(ret, ast.Return)
        self.assertEqual(ast.unparse(ret), 'return self._medoid([p for _t, p in reversed(fresh)])')
        self.assertEqual(ast.unparse(sa[-1]), 'return self._medoid([p for _t, p in fresh])')

    def test_drone_py_is_the_candidate_bytes(self):
        self.assertEqual(sha(ROOT / S / 'examples/drone.py'), sha(CAND / S / 'examples/drone.py'))
        self.assertTrue(sha(ROOT / S / 'examples/drone.py').startswith('fa6abf8b'))

    def test_camera_fix_is_r2g_and_its_row_stays_pending(self):
        p = 'src/python/camera_fix.py'
        self.assertEqual(sha(ROOT / S / p), sha(R2G / S / p))
        self.assertTrue(sha(ROOT / S / p).startswith('4a15d699'))
        rows = [r.split('\t') for r in (ROOT / 'image_manifest_r2.tsv').read_text().split('\n')
                if r.startswith('drone/ros2_ws/' + S + p + '\t')]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertTrue(r[1].startswith('4a15d699'))                      # on the drone (a45a264)
        self.assertTrue(r[2].startswith('dabd5076'))                      # the pending camera fix (not in src)
        self.assertEqual(r[3], 'camera_fullrow_01')
        self.assertIn('PENDING', r[4])

    def test_ref_copy_is_r2g_bytes(self):
        self.assertEqual((ROOT / H2 / 'ref/vpe_fix_r2g_3b8a93d4.py').read_bytes(), (R2G / VPE).read_bytes())

    def test_old_pins_file_not_edited(self):
        self.assertEqual(sha(ROOT / H2 / 'tests_r2/test_pins_r2.py'), sha(CAND / H2 / 'tests_r2/test_pins_r2.py'))

    def test_cmake_only_the_vpe_fix_pins_block(self):
        a = (CAND / S / 'CMakeLists.txt').read_text().splitlines()
        b = (ROOT / S / 'CMakeLists.txt').read_text().splitlines()
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        changed = [(t, i1, i2, j1, j2) for t, i1, i2, j1, j2 in sm.get_opcodes() if t != 'equal']
        start = a.index('  ament_add_pytest_test(test_vpe_fix_h2_r2_pins test/vpe_fix_h2_r2/tests_r2/test_pins_r2.py TIMEOUT 60')
        end = a.index('  ament_add_pytest_test(test_vpe_fix_h2_r2 test/vpe_fix_h2_r2/tests_r2/test_h2_r2.py TIMEOUT 120')
        for t, i1, i2, j1, j2 in changed:
            self.assertTrue(start - 1 <= i1 and i2 <= end, (t, a[i1:i2], b[j1:j2]))
        new = '\n'.join(b)
        self.assertIn('PIN_TARGET=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py', new)
        self.assertIn('ament_add_pytest_test(test_vpe_fix_pins_r3 test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py', new)
        self.assertIn('PIN_TARGET=${_VPE} PIN_R2G=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py', new)

    def test_src_differs_from_the_candidate_only_in_the_declared_files(self):
        a, b = tree_files(CAND / 'src'), tree_files(ROOT / 'src')
        self.assertEqual(b - a, {'bumblebee/test/vpe_fix_h2_r2/ref/vpe_fix_r2g_3b8a93d4.py',
                                 'bumblebee/test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py'})
        self.assertEqual(a - b, set())
        diff = {f for f in a if not filecmp.cmp(CAND / 'src' / f, ROOT / 'src' / f, shallow=False)}
        self.assertEqual(diff, {'bumblebee/src/python/vpe_fix.py', 'bumblebee/CMakeLists.txt',
                                'bumblebee/test/vpe_fix_h2_r2/README.md'})


if __name__ == '__main__':
    unittest.main()
