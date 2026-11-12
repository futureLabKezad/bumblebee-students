# REVIEW_A10 — independent review of c8_judge_r2h_a10_20261110 (10.11.2026)

**Verdict: ACCEPT WITH NOTES**. I found no MUST-FIX defect. The SHOULD items below are text corrections and one stale inherited test.

Method: read-only, `wsl.exe` only. I used `diff -r` A9 against A10 (excluding tests/out_*, reviews/, __pycache__), recomputed every pin sha, ran `sha256sum -c` of the product sums on both installs, grepped every consumer, read the new tests and their logs, and checked against the A9 SITL run `/work/sim/runs/INT_flight_C8a9_pilot_04`. No Gazebo, PX4, ROS node or drone was used. No file was written except this one, and no `__pycache__` was created (`find` of A10 and r2h shows 0).

## MUST-FIX
None.

## SHOULD
S1. **README "Объём ros.log" is wrong about the file.** The `VPE_GATE_DIAG` lines do not go to ros.log. supervisor.py:174-177 and 296-298 spawn the entry with `spawn(...,'wrapper')`, so stdout and stderr go to `wrapper.log`. In A9 pilot_04, ros.log is 2.3 KB and wrapper.log is 84 KB, with 75 DIAG lines of about 1.1 KB each (70 `_gate_tick` + 5 `state_callback`). At about 24 Hz plus 1 Hz, the 840 s supervisor cap allows roughly 20 MB of wrapper.log in the worst case. Nobody parses it (see B4), so this is harmless. The README should say wrapper.log.

S2. **README: «Первый прогон покажет строки `VPE_GATE_DIAG_START`» is false, and so is the implication that the judge gets them.** The entry imports `vpe_gate_diagnostic_p1` as a module and only uses `diagnostic_wrapper`. It never calls `diagnostic.main()`, which is the only code that prints `VPE_GATE_DIAG_START` (vpe_gate_diagnostic_p1.py:115). A9 pilot_04 has 0 START lines across all `*.log` files. The legacy reader (legacy/verify_package1b_gates_c8.py:122-145) scans only `ros.log` anyway. This is inherited from A9, and A10 does not change it. Still, `wrapper_startup_evidence` will be `[]` and the vision policy `unknown`, exactly as in A9. Correct the README text and do not expect START lines in the first run.

S3. **README table "мин. 3, медиана 8".** The median is not printed by `tests/a10_vpe_as_drone.py` and does not appear in `tests/out_184229/a10_vpe_as_drone.log`, which prints only min 3 of 16 and max gap 0.70 s. Either print it or drop it from the README.

S4. **Stale inherited test `executor/tests/test_entry_order.py`.** It still builds the A9 composition (`vpe_freshness_optin.install(vpe_fix, enabled=True)`, `Node._freshness_pose_timeout_ns`). It is not run by `tests/test_c8_b2.sh`, and it is byte-identical to A9 (a10_checks' executor diff list confirms this). It now describes a composition A10 does not use. Mark it obsolete in the README or leave a note; do not edit it in place if it counts as accepted material.

S5. **Bench scope note for `a10_vpe_as_drone`.** The dynamic part loads the real r2h `VpeFix` and the real diagnostic wrapper, but not the `ProfileVpe` subclass from `vpe_profile_optin.make_node_class`. Only a static AST check covers it: no pose-path method is overridden. `__init__` is overridden and is not in POSE_PATH. That is acceptable, because the class methods are parameter-service only (list in the log), and d2_vpe_composition shows MRO `ProfileVpe, VpeFix, Node`. Still, say in the README that the profile class is covered statically, not on the bench.

S6. (info) **Wrapper cost at 24 Hz.** Each `_evaluate_gate` call now takes two `snapshot()` calls (including `vars(node)`) plus `json.dumps`, about 24 times per second in the vpe_fix executor threads. This is likely small, but it has not been measured. The first A10 SITL run should glance at RTF and at the `vpe_fix` publish rate.

## Checked and fine (with evidence)

### A. A9 → A10 difference
- `diff -rq` A9 against A10 shows changes only in these files:
  - texts: README, PROGRESS, DIFF_a10, SHA256SUMS, build_edits, candidate/README;
  - candidate/manifest.json, candidate/parameters/vpe_fix.py and vpe_profile_optin.py;
  - executor/PRODUCT_SHA256SUMS.txt, run.sh, sitl_setup.py, vision_c8.launch.py, vpe_diagnostic_entry.py and vpe_gate_diagnostic_p1.py;
  - launcher/ACCEPTED_PINS_b.txt and host_run_wsl_c8_r2e_b.sh;
  - the pins file (renamed);
  - tests: path renames, a9_checks → a10_checks, plus the new a10_vpe_as_drone;
  - tools: make_a9 → make_a10;
  - A9 `notes/` is not carried over. It is text only and nothing references it.
- **Byte-identical: `verify_flight_c8.py`, `legacy/`, `expect/`, `executor/run_sim.snapshot.sh`.** `diff -r` reports SAME. The pin shas are unchanged too (judge 1ab83ca4, legacy 8bcef313).
- Every hunk is (1) or (2) or text:
  - vpe_gate_diagnostic_p1.py: only the `TARGET_SHA256` line changed (3b8a93d4 → 66d806ba).
  - vpe_profile_optin.py: only the pinned VPE sha line changed.
  - sitl_setup.py: only the `PROFILE_SOURCE` path changed (r2g → r2h; flight_profile 5b8e2a12 has the same bytes).
  - vision_c8.launch.py: the candidate path only.
  - run.sh: OWN path, product-sums sha 48e9d830, drone.py sha fa6abf8b, and comments.
  - launcher: version v37, RUNNER, the default r2h install and src, and the trial path.
- vpe_diagnostic_entry.py: the helper sha changed (220fccd7), and exactly three statements were removed (import, sha assert, `install`). `a10_checks` checks this by AST (`removed == 3`, all freshness), and I confirmed it by diff.
- `candidate/parameters/vpe_fix.py` = r2h src = r2h install = 66d806ba. `aruco_detect.py` (66f061ec) and `flight_profile.py` = r2h.
- Inherited test edits are limited to paths and to the intended vpe_fix exceptions in a8_checks (the vpe_fix copy differs from A7; one extra sha line). These are tests, not gates or evaluators.

### B. Variant B safety
1. **Nothing needs the freshness module at run time.** grep over the judge, legacy, executor/*.py, *.sh and the launcher finds only the A10 comment in the entry and a historical comment in the launcher header. `freshness_diagnostics` and `_freshness*` are referenced nowhere outside the module itself and the tests and builder. supervisor.py's `fresh` hits are `FreshParamAdapter` (parameter reads), which is unrelated. `vpe_profile_optin.main()` has no freshness dependency: `make_node_class(VpeFix)` gives MRO `ProfileVpe, VpeFix, Node` (d2_vpe_composition log).
2. The file `vpe_freshness_optin.py` is kept byte-identical (fddfa6ec) and stays pinned. That is required, because run.sh:86 hashes `$CAND/*.py` into the ledger. Removing it would break `ledger_equals_pins`.
3. **No judged quantity depends on the pose stamp.**
   - verify_flight_c8.py has no vision, ArUco, VPE or `vehicle_visual` reference; its only "fresh" is `fresh_single_ulog`.
   - legacy reads vision only through `vpe_policy.json`, `aruco_policy.json` and the START markers. No executor file writes `vpe_policy.json`, and A9 pilot_04 has none, so the result is `unknown` in both A9 and A10.
   - The only stamp-related change is the outgoing `header.stamp` (now = `now()`, not the frame time), which is what the drone does. The age cut stays in vpe_fix at `_POSE_TIMEOUT = 0.5` (by receipt time), the same value the mixin used.
4. **The 24 Hz `VPE_GATE_DIAG` lines.** They are emitted only when `markers_used_callback` calls `_apply_gate()` (r2h B1). `publish_timer` calls `_apply_gate` only on an unknown FCU state, as in r2g. No judge or step parses the non-START lines:
   - legacy matches only `VPE_GATE_DIAG_START` and reads ros.log line by line (streaming);
   - gate.py:162 `read_text()` reads ros.log, not wrapper.log;
   - the launcher's `out_hash` hashes files, which is trivial at this size.
   There is no parse or performance risk to the verdict. See S1 and S6.

### C. Pins and launcher
- I recomputed every sha-valued entry of `pins/frozen_inputs_c8_r2h_a10_01.json` against the files: **135 match, 0 mismatch**. The 5 composite or special keys were checked by hand: `combined_manifest_sha256` = manifest 7c93354f; `run_files/flight_profile.py`; `legacy_verifier_sha256`; `sdk_drone_py.sha256` = r2h drone.py.
- The pins file sha 9ec805e7 is the only entry in `ACCEPTED_PINS_b.txt`. The only remaining "r2g" string in the pins is the A9 history note.
- Launcher precheck (extracted by the test): it accepts the A10 pins (`problems: []`, launcher_pins_ok.log). It refuses the A9 pins 4b46f4d4 as "not in ACCEPTED_PINS_b" (launcher_refuses_pins_01.log) and refuses the old r2e pins.
- **Product sums.** `cd r2h/install && sha256sum -c` passes (R2H_PASS). On r2g it fails (36 mismatches). run.sh pins the sums file at 48e9d830.
- **The 17 `__pycache__` lines are harmless.** The r2g `.pyc` files date from 10:05, the same minute as the r2g build (colcon or rosidl byte-compile). The r2h install has 0 `.pyc`. The A10 list is the A9 list minus exactly those 17 paths (sorted name diff), and the order is otherwise unchanged. `sha256sum -c` checks only the files it lists, so extra `.pyc` files written later cannot fail it. A run is unlikely to write any: run.sh:40 exports `PYTHONDONTWRITEBYTECODE=1`, the launcher uses `python3 -B`, and the tests use `-B` with `PYTHONDONTWRITEBYTECODE`. After the 31 tests the r2h install still has 0 `__pycache__`. Nothing in the run checks the install for extra files.
- `SHA256SUMS.txt` of the package: `sha256sum -c` passes (135 files).

### D. New tests
- `a10_checks.py` is real. It covers: hashes of judge, legacy, expect and run_sim against A9; the exact list of changed candidate and executor files; single-line sha edits that are the same statement apart from the sha; the AST diff of the entry; the manifest keys; `sha256sum -c` of the r2h MANIFEST and SHA256SUMS; pass on r2h and fail on r2g for the product sums; and the pin renames.
- `a10_vpe_as_drone.py` is real:
  - It composes the vision path the way the entry does: the candidate r2h `vpe_fix` plus `diagnostic_wrapper` on `VpeFix._evaluate_gate`.
  - A static AST check asserts that the entry has exactly that one attribute assignment and no freshness import.
  - The bench drives real timers, 24 Hz frames with real header stamps (30 ms latency), and a 1 s pause.
  - Result: 20 of 20 seeds give 16 of 16 samples in the first 0.5 s, with gaps ≤ 1/30 s. The samples are identical to plain vpe_fix, so the diagnostic is neutral.
  - **The control fails as it should.** The A9 composition on r2h gives a minimum of 3 of 16 and a gap of 0.70 s, which is above PX4's 0.4 s EV timeout. r2g with freshness equals r2g after the pause in 20 of 20 seeds; over the whole run they differ by 1 sample.
  - The PIN override (`fo.PIN_C33 = h(path)`) is in memory only and only for the control.
  - Limitation: see S5.
- `tests/out_184229` has all 31 test logs, and none contains a Traceback or AssertionError. The `RESULT pass=31` line itself is not saved in the out folder; it goes to stdout only.

### E. README against logs
These claims match: 505 = 522 − 17 paths; r2h shas 66d806ba, fa6abf8b, 548bd261, 9ec805e7, 7c93354f; the three statements removed; the judge and others unchanged; the composition result 16 of 16 and min 3, 0.70 s; r2g plus freshness the same after the pause, differing by 1 sample over the whole run; 31 tests. Exceptions: S1 (ros.log should be wrapper.log), S2 (START lines), S3 (median).
