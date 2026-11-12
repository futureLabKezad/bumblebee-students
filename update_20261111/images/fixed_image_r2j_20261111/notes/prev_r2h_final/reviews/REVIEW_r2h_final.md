# Review: r2h candidate -> r2h FINAL (/work/fixed_image_r2h_20261110), 10.11.2026

**Verdict: ACCEPT WITH NOTES**. There are no MUST-FIX items. The diff from the candidate is exactly the 4 declared items, and the only behaviour change is which pose wins a medoid tie. All sums check out. The notes below are about how strong the pins are, and about documentation.

Independent reviewer. Read-only, except for this file. Mutation copies were made in /tmp/rv_r3 and removed afterwards. No ROS, Gazebo, PX4 or drone was used.

## MUST-FIX
None.

## SHOULD
1. **test_pins_r3, the test that CMake runs, does not pin the contents of the declared parts.** It checks *which* parts differ from r2g, but not *what* they now contain. Its claim of "only the declared methods may differ" holds, but the bodies of the 7 CHANGED methods and of `_reentry_pose` can be anything. I tested this with mutations of a copy of the final vpe_fix (PIN_R2G = the ref copy):
   - `m_reentry`: `reversed(fresh)` changed back to `fresh` (the tie fix undone). r3 **OK**. test_r2h_vpe FAILs (B2TwoPoses). test_r2h_final would fail.
   - `m_hold`: `int(_REENTRY_HOLD * 1e9)` changed to `int(0.05 * 1e9)` (hold 0.05 s instead of 0.5 s). r3 **OK**. All 18 tests of test_r2h_vpe also **OK**. Only test_r2h_final would catch it, because its AST pin allows the docstring and the final return to differ, nothing else.
   - `m_b1thr`: B1 `markers_used >= 1` changed to `>= 2`. `m_b1tick`: the per-frame `_apply_gate()` removed. r3 **OK**. test_r2h_vpe FAILs (3 and 2 tests).
   - `m_changed`: `markers_used = 0` added in markers_used_callback. r3 OK and test_r2h_vpe OK. The change likely has no effect on behaviour.

   So inside colcon, a later edit to the B1/B2 logic is caught by none of the 44 registered tests. It is caught only by the top-level tests (test_r2h_final, test_r2h_vpe), and those depend on /work paths to the candidate and to r2g. Suggestion for the next round: r3 (or a sibling test) also pins `ast.dump` of the 8 declared parts against the accepted final. Use a sha prefix or a byte-copy ref, as was done for r2g. The r2 pins use the same "declared set" method, so this is not a regression. It is the place where the chain is weakest.
2. **No behaviour test pins the 0.5 s hold.** `m_hold` passes all of test_r2h_vpe. A short test would close this gap: after re-entry, it checks that the medoid is used for about 0.5 s and the latest pose after that.
3. **One file in notes/ was changed in place, not only added to.** `notes/DIFF_r2h_vs_r2g.txt` was regenerated for the final (diff vs candidate: new CMake hunk, new vpe_fix timestamps, hunk `@@ -1018,6 +1047,38 @@`). The content is correct. But the candidate's version was not moved into `notes/prev_r2h_candidate/`, which also has no copy of `image_manifest_r2.tsv`. Both survive unchanged in the candidate folder, which is intact: `SHA256SUMS` sha starts with 4f4b0ce9, and `sha256sum -c` passes for SHA256SUMS and MANIFEST. This is only a bookkeeping note.
4. **README test count.** README:41 says "44 из 44". `notes/colcon_test_vpe_r2h_final.log` says "Summary: 48 tests, 0 errors, 0 failures". Both are right. The 48 is the 44 pytest testcases (33+1+5+5 in `build/bumblebee/test_results/bumblebee/*.xunit.xml`, all 18:29, after the 18:24 edits) plus 4 CTest entries (`Testing/20261110-1429/Test.xml`, 4 passed). One clause in the README would stop a reader from seeing a mismatch.

## Checked and fine (evidence)

**A. The diff is exactly the 4 items.**
- `diff -rq candidate/src final/src` gives exactly these: CMakeLists.txt, src/python/vpe_fix.py and test/vpe_fix_h2_r2/README.md changed; `ref/vpe_fix_r2g_3b8a93d4.py` and `tests_r3/` added. Nothing else. drone.py and camera_fix.py are unchanged.
- The README.md change in the H2 folder adds one table row for tests_r3. It is part of item 2.
- vpe_fix `diff -u`: two hunks only, the docstring (+1 line, l.1056-1057) and the return (l.1079-1080): `return self._medoid([p for (_t, p) in reversed(fresh)])`.
- CMakeLists `diff -u`: one hunk in the vpe_fix pins block (l.214-221). It adds a comment, moves PIN_TARGET of `test_vpe_fix_h2_r2_pins` to the r2g copy, and adds `test_vpe_fix_pins_r3`.
- `diff -rq test`: test_r2h.py and test_r2h_vpe.py retargeted, test_r2h_final.py new. Nothing else.
- tools/: additions only (finish_r2h_final.sh, make_r2h_final.py, test_all_r2h_final.sh).
- notes/: additions, plus prev_r2h_candidate, plus test_logs replaced. The candidate's test_logs are all present in `notes/prev_r2h_candidate/test_logs` (diff -rq is empty). The one in-place change is SHOULD 3.
- Top-level DIFF_vs_r1.txt, PROGRESS.md, README.md, sums and TSV changed. These are expected. prev_r2h_candidate holds byte-equal copies of the candidate's README, MANIFEST, SHA256SUMS, PROGRESS and DIFF_vs_r1.
- The TSV diff is 6 rows: CMakeLists, camera_fix note, vpe_fix, H2 README, and 2 new rows.

**B. The tie change is correct.**
- `fresh` is a list built by a list comprehension over the deque `_recent_poses` (vpe_fix.py:1069), so `reversed()` cannot fail. The deque is filled in arrival order (l.937, l.1004), so `reversed` gives newest first.
- `waited` still uses `fresh[0]`, the oldest pose (l.1074), before the reversal. Unchanged.
- `_medoid` (l.957-968) keeps the first minimum (`cost < best_cost`), so with newest first, a tie goes to the newest.
- 1 pose: the result is identical.
- 2 poses: always a tie, and bitwise. `(a-b)**2 == (b-a)**2` exactly in IEEE, and `0.0+d == d+0.0`. So the newest always wins, which equals the pre-B2 "latest pose" and is fresher than before.
- 3 poses: the winner changes only on an exact float tie. Realistically that means two bit-identical positions (cost d, d, 2d). Then the newer of the pair wins. Its position is the same, and only orientation/stamp could differ. An isosceles exact tie is practically impossible with noisy poses.
- The 3-pose medoid is unchanged: B2TwoPoses.test_three_poses_medoid_unchanged gives 0.01 on the final and on the candidate.

**C. test_pins_r3 and the chain.**
- My run on the final: 5/5 OK.
- On the r2g copy: FAILED (failures=2, errors=1), matching `pins_r3_on_r2g_EXPECTED_FAIL.txt`.
- Mutations caught by r3:
  - `_REENTRY_HOLD = 0.6`: test_r3_constants FAIL.
  - `_medoid` `<` to `<=` (a non-declared method): 2 FAILs.
  - A new constant `_EXTRA`: FAIL.
  - A new `import math`: FAIL.

  For what r3 does not catch, see SHOULD 1.
- CTest env (build/bumblebee/CTestTestfile.cmake l.37, l.39):
  - r3 gets PIN_TARGET=src/python/vpe_fix.py, PIN_R2G=ref copy, PIN_HARNESS=tests_existing/harness, which is everything it reads.
  - r2 pins get PIN_TARGET=ref copy, plus PIN_C33, PIN_P1 and PIN_HARNESS.
- The ref copy has sha 3b8a93d4…9e2725, the same as `/work/fixed_image_r2g_20261110/src/bumblebee/src/python/vpe_fix.py`, and r3 checks a 16-hex prefix of it.
- test_pins_r2.py is byte-identical to the candidate's.
- Chain c33 -> P1 -> H2 -> r2g: r2 on the r2g copy is 5 OK (log and xunit). r3 pins r2h against r2g. Still pinned.

**D. The new tests are real.**
- I made a copy of test_r2h_vpe.py with R2H pointed at other files:
  - The candidate vpe_fix: **FAIL** test_two_fresh_poses_give_the_newer (the other 17 OK). So without the control assertion, the test still fails without the fix.
  - `m_reentry`: the same FAIL.
  - The final: 18/18 OK.
- test_r2h_final (9 tests) pins final == candidate everywhere except `_reentry_pose` docstring + return (AST, plus `ast.unparse` of both returns), drone.py bytes (fa6abf8b), the camera_fix row, the ref bytes, the CMake block range, and the src file set.
- Retargets only change the folder-name assertions (test_r2h.py:23, test_r2h_vpe.py:22). The targets still resolve to the final folder, and the controls (r2g, candidate) are absolute paths, so the comparisons are not self-vs-self.

**E. TSV and sums.**
- `sha256sum -c` of SHA256SUMS: rc 0. MANIFEST_SHA256.txt (479 entries): rc 0.
- Every file outside build/install/log is in MANIFEST, except the nested sums/manifests and moved_aside pytest caches. That is the same convention as before. The new files are present.
- INSTALL_SHA256 matches install/: vpe_fix 66d806ba, camera_fix 4a15d699.
- TSV: all 225 bumblebee rows with a sha match the src files, except camera_fix (PENDING dabd5076, while src = 4a15d699, as declared) and fcu_detect (inherited and documented in README:28). No src file is missing from the TSV.
- New rows: ref 3b8a93d4 and test_pins_r3 b46c4ed6, both correct.
- Updated rows: CMakeLists 453130e9, vpe_fix 66d806ba, H2 README 9fbad9f5, all correct.
- README claims match the logs: all of `notes/test_logs_summary_r2h_final.txt` is exit 0 OK, and the two EXPECTED_FAIL controls fail. The colcon xunit results are all 0 failures.

**F. What a flight would care about.**
- The only behaviour change in vpe_fix is the tie winner (see B). With a slow detector and 2 fresh poses at re-entry, the first published pose is now the newer one, so there is less latency. No constant, gate, guard, reseed or H2 code changed (r3 plus test_r2h_final).
- drone.py, camera_fix.py and all C++ sources are byte-identical to the candidate.
- The C++ binaries in install/ differ from the candidate's but have the same size (simple_offboard 38526816, vpe_publisher 9257424). This is most likely just the from-scratch rebuild embedding the new build path: 22 and 8 path strings respectively. I did not compare them further.
- Out of scope, risk only: the freshness-wrapper question (notes/T44_freshness_vs_B2.md) is still open. It is not affected by this diff.
