#!/usr/bin/env python3
"""make_r2h_final.py - task T44 of chat 1 (10.11.2026; owner 18:17 «Да, r2h»): the FINAL r2h =
the r2h candidate (/work/fixed_image_r2h_candidate_20261110, SHA256SUMS 4f4b0ce9; handed out for control, not edited)
plus three things:
  1. SHOULD of the candidate review: with 2 fresh poses the medoid took the OLDER one (a tie goes to the first of the
     list, the list is oldest first). Now _reentry_pose gives the poses newest first: a tie goes to the newest. With 1
     or 3 distinct poses nothing changes (the medoid of 3 is unique unless two of them tie).
  2. code pins round 3: tests_r2/test_pins_r2.py (not edited) pins the vision path to c33 / 7f107882, which r2g's
     vpe_fix satisfies and r2h by design does not. Its CMake registration now points at a byte copy of r2g's vpe_fix
     (ref/vpe_fix_r2g_3b8a93d4.py) -- the chain c33 -> P1 -> H2 -> r2g stays pinned -- and the new
     tests_r3/test_pins_r3.py pins src/python/vpe_fix.py (r2h) against that copy: only the declared B1/B2 parts.
  3. camera_fix.py: as in r2g (the a45a264 file 4a15d699, the one Gazebo checks). Its image_manifest row keeps the
     pending camera fix dabd5076 with the mark PENDING; the owner decides in the morning (11.11).
drone.py: the candidate's bytes (fa6abf8b). Everything else: the candidate's bytes.
Usage: python3 -I make_r2h_final.py   (refuses to overwrite; then colcon, tools/test_all_r2h_final.sh, tools/finish_r2h_final.sh)
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

WORK = Path('/work')
CAND = WORK / 'fixed_image_r2h_candidate_20261110'
R2G = WORK / 'fixed_image_r2g_20261110'
DST = WORK / 'fixed_image_r2h_20261110'
HERE = Path(__file__).resolve().parent
CAND_SUMS = '4f4b0ce9d4f42f14a9060d12176503eafc5209ddb5a443099db0105152395fa2'
CAND_VPE = 'f2a7ca4f120eb8340f5b674d4f44e87da84b47bda511e6260285f36d0483a5cb'
CAND_DRONE = 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c'
R2G_VPE = '3b8a93d4d0898369'
CAMERA_FIX = '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310'
S = 'src/bumblebee/'
H2 = S + 'test/vpe_fix_h2_r2/'
LOG = []


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def edit(rel, edits):
    p = DST / rel
    t = p.read_text()
    for old, new, n, why in edits:
        c = t.count(old)
        if c != n:
            sys.exit('STOP: %s anchor %r: %d matches (want %d)' % (rel, old[:70], c, n))
        t = t.replace(old, new)
        LOG.append('%s: %s' % (rel, why))
    p.write_text(t)


def main():
    if DST.exists():
        sys.exit('STOP: refusing to overwrite ' + str(DST))
    if sha(CAND / 'SHA256SUMS') != CAND_SUMS:
        sys.exit('STOP: the candidate is not the reviewed one (SHA256SUMS)')
    for f in ('SHA256SUMS', 'MANIFEST_SHA256.txt'):
        subprocess.run(['sha256sum', '-c', '--quiet', f], cwd=CAND, check=True)
    if sha(CAND / S / 'src/python/vpe_fix.py') != CAND_VPE or sha(CAND / S / 'examples/drone.py') != CAND_DRONE:
        sys.exit('STOP: candidate vpe_fix/drone.py')
    if not sha(R2G / S / 'src/python/vpe_fix.py').startswith(R2G_VPE):
        sys.exit('STOP: r2g vpe_fix')
    if sha(CAND / S / 'src/python/camera_fix.py') != CAMERA_FIX or sha(R2G / S / 'src/python/camera_fix.py') != CAMERA_FIX:
        sys.exit('STOP: camera_fix is not the a45a264 / r2g file')

    DST.mkdir()
    for d in ('src', 'test', 'tools', 'notes'):
        shutil.copytree(CAND / d, DST / d, symlinks=True)
    shutil.copy2(CAND / 'image_manifest_r2.tsv', DST / 'image_manifest_r2.tsv')
    prev = DST / 'notes/prev_r2h_candidate'
    prev.mkdir()
    for f in ('README.md', 'PROGRESS.md', 'SHA256SUMS', 'MANIFEST_SHA256.txt', 'INSTALL_SHA256.txt', 'DIFF_vs_r1.txt'):
        shutil.copy2(CAND / f, prev / f)
    shutil.copytree(CAND / 'reviews', prev / 'reviews')
    shutil.move(str(DST / 'notes/test_logs'), str(prev / 'test_logs'))     # the candidate's logs; fresh ones are written anew
    LOG.append('copied src, test, tools, notes, image_manifest_r2.tsv; candidate README/PROGRESS/sums/reviews/test_logs -> notes/prev_r2h_candidate/')

    # 1. the SHOULD: a tie of the medoid goes to the newest pose
    edit(S + 'src/python/vpe_fix.py', [
        ("        one missing frame does not silence it, review S1); else the latest pose, as before.\"\"\"\n",
         "        one missing frame does not silence it, review S1); else the latest pose, as before. The medoid gets the\n"
         "        poses newest first, so a tie (always so with 2 poses) goes to the newest (T44, SHOULD of the review).\"\"\"\n",
         1, 'docstring of _reentry_pose'),
        ("        return self._medoid([p for (_t, p) in fresh])\n",
         "        # T44 (SHOULD of the candidate review): newest first, so a tie -- always so with 2 poses -- goes to the newest\n"
         "        return self._medoid([p for (_t, p) in reversed(fresh)])\n",
         1, '_reentry_pose: medoid of the fresh poses newest first'),
    ])

    # 2. pins round 3
    shutil.copy2(R2G / S / 'src/python/vpe_fix.py', DST / H2 / 'ref/vpe_fix_r2g_3b8a93d4.py')
    (DST / H2 / 'tests_r3').mkdir()
    shutil.copy2(HERE / 'test_pins_r3.py', DST / H2 / 'tests_r3/test_pins_r3.py')
    LOG.append(H2 + 'ref/vpe_fix_r2g_3b8a93d4.py: byte copy of r2g vpe_fix; tests_r3/test_pins_r3.py: new')
    edit(S + 'CMakeLists.txt', [
        ("  ament_add_pytest_test(test_vpe_fix_h2_r2_pins test/vpe_fix_h2_r2/tests_r2/test_pins_r2.py TIMEOUT 60\n"
         "    ENV PIN_TARGET=${_VPE} PIN_C33=${_H2R2}/ref/vpe_fix_c33_product.py PIN_P1=${_H2R2}/ref/vpe_fix_7f107882.py\n"
         "        PIN_HARNESS=${_H2R2}/tests_existing/harness)\n",
         "  # r2h (T44): code pins round 3. The round-2 pins pin r2g's vpe_fix (byte copy ref/vpe_fix_r2g_3b8a93d4.py), so\n"
         "  # the chain c33 -> P1 -> H2 -> r2g stays pinned; test_pins_r3 pins src/python/vpe_fix.py (r2h) against that\n"
         "  # copy: only the declared B1/B2 parts differ.\n"
         "  ament_add_pytest_test(test_vpe_fix_h2_r2_pins test/vpe_fix_h2_r2/tests_r2/test_pins_r2.py TIMEOUT 60\n"
         "    ENV PIN_TARGET=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py PIN_C33=${_H2R2}/ref/vpe_fix_c33_product.py\n"
         "        PIN_P1=${_H2R2}/ref/vpe_fix_7f107882.py PIN_HARNESS=${_H2R2}/tests_existing/harness)\n"
         "  ament_add_pytest_test(test_vpe_fix_pins_r3 test/vpe_fix_h2_r2/tests_r3/test_pins_r3.py TIMEOUT 60\n"
         "    ENV PIN_TARGET=${_VPE} PIN_R2G=${_H2R2}/ref/vpe_fix_r2g_3b8a93d4.py PIN_HARNESS=${_H2R2}/tests_existing/harness)\n",
         1, 'pins: round 2 on the r2g copy, round 3 on r2h'),
    ])
    edit(H2 + 'README.md', [
        ("| `tests_r2/test_in_air_writes.py` (1) | no extra ParamSet while armed against 7f107882 (1198 scenarios) |\n",
         "| `tests_r2/test_in_air_writes.py` (1) | no extra ParamSet while armed against 7f107882 (1198 scenarios) |\n"
         "| `tests_r3/test_pins_r3.py` (5) | r2h (T44, 10.11.2026): code pins round 3 -- `src/python/vpe_fix.py` against r2g's vpe_fix (`ref/vpe_fix_r2g_3b8a93d4.py`, byte copy): only the 7 declared B1/B2 methods differ, `_reentry_pose` and 4 `_REENTRY_*` constants added. Since r2h, CMake runs `test_pins_r2.py` on that r2g copy (the chain c33 -> P1 -> H2 -> r2g), not on `src/python/vpe_fix.py` |\n",
         1, 'README: round 3 row'),
    ])

    # 3. camera_fix: file as r2g; the manifest row keeps the pending fix, mark PENDING (owner decides 11.11)
    edit('image_manifest_r2.tsv', [
        ("\tcamera_fullrow_01\tchanged (PENDING: Pi load check at the bench)\n",
         "\tcamera_fullrow_01\tchanged (PENDING: Pi load check at the bench; owner decides 11.11 morning. "
         "r2h src keeps the a45a264 file 4a15d699 as r2g, the one Gazebo checks)\n",
         1, 'camera_fix row: PENDING kept, what r2h src holds'),
    ])

    # tests and tools: the folder name
    for rel in ('test/test_r2h.py', 'test/test_r2h_vpe.py'):
        edit(rel, [('fixed_image_r2h_candidate_20261110', 'fixed_image_r2h_20261110', 1, 'folder -> final')])
    edit('test/test_r2h_vpe.py', [
        ("R2G = B.load(str(R2G_VPE), 'vpe_fix_r2g_control')\n",
         "R2G = B.load(str(R2G_VPE), 'vpe_fix_r2g_control')\n"
         "CAND_VPE = Path('/work/fixed_image_r2h_candidate_20261110/src/bumblebee/src/python/vpe_fix.py')   # T44 control\n"
         "CAND = B.load(str(CAND_VPE), 'vpe_fix_r2h_candidate_control')\n", 1, 'candidate as a control'),
        ("\n\nif __name__ == '__main__':\n",
         "\n\nclass B2TwoPoses(unittest.TestCase):\n"
         "    \"\"\"T44 (SHOULD of the candidate review): a slow detector (6 Hz) ends the re-entry wait with 2 fresh poses; the\n"
         "    medoid of 2 is a tie and must go to the NEWER pose. Control: the candidate sends the older one.\"\"\"\n"
         "\n"
         "    @staticmethod\n"
         "    def det():\n"
         "        k = {'n': -1}\n"
         "\n"
         "        def d(t):\n"
         "            if 3.0 <= t < 4.5:\n"
         "                return 0, None\n"
         "            if t >= 4.5:\n"
         "                k['n'] += 1\n"
         "                return 2, (0.02 if k['n'] >= 1 else 0.0, 0.0, 1.0)     # back: x=0, then x=0.02\n"
         "            return 2, (0.0, 0.0, 1.0)\n"
         "        return d\n"
         "\n"
         "    def first_after_pause(self, mod):\n"
         "        s = Sim(mod, self.det(), frame=1.0 / 6.0)\n"
         "        s.run(8.0)\n"
         "        back = min(t for t, n in s.frames if t >= 4.5 and n > 0)\n"
         "        first = s.sent(after=back)[0]\n"
         "        n_fresh = sum(1 for t, n in s.frames if back - 1e-9 <= t <= first[0] and n > 0)\n"
         "        return first[1].pose.pose.position.x, n_fresh\n"
         "\n"
         "    def test_two_fresh_poses_give_the_newer(self):\n"
         "        x, n = self.first_after_pause(R2H)\n"
         "        self.assertEqual(n, 2)\n"
         "        self.assertAlmostEqual(x, 0.02)\n"
         "        cx, cn = self.first_after_pause(CAND)\n"
         "        self.assertEqual(cn, 2)\n"
         "        self.assertAlmostEqual(cx, 0.0)\n"
         "\n"
         "    def test_three_poses_medoid_unchanged(self):\n"
         "        \"\"\"24 Hz: 3 fresh poses (0, 0.01, 0.06) -> 0.01 on the final and on the candidate\"\"\"\n"
         "        for mod in (R2H, CAND):\n"
         "            det = B2Reentry.det_with_pause([0.0, 0.01, 0.06])\n"
         "            s = Sim(mod, det)\n"
         "            s.run(5.0)\n"
         "            self.assertAlmostEqual(s.sent(after=det.back[0])[0][1].pose.pose.position.x, 0.01)\n"
         "\n"
         "\nif __name__ == '__main__':\n", 1, 'B2TwoPoses tests'),
    ])
    shutil.copy2(HERE / 'test_r2h_final.py', DST / 'test/test_r2h_final.py')
    for f in ('make_r2h_final.py', 'test_all_r2h_final.sh', 'finish_r2h_final.sh'):
        shutil.copy2(HERE / f, DST / 'tools' / f)
    LOG.append('test/test_r2h_final.py: new; tools: make_r2h_final.py, test_all_r2h_final.sh, finish_r2h_final.sh')
    (DST / 'notes/build_edits_r2h_final.txt').write_text('\n'.join(LOG) + '\n')
    print('\n'.join(LOG))
    print('vpe_fix', sha(DST / S / 'src/python/vpe_fix.py'))


if __name__ == '__main__':
    main()
