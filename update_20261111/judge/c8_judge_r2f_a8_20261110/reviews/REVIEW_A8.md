# REVIEW A8 — c8_judge_r2f_a8_20261110 vs A7 (independent reviewer, 10.11.2026)

Scope: read-only review. No Gazebo, no PX4, no drone, no ssh. Own probes: `/work/review_a8_20261110/` (p1–p7, mut.sh,
resid.py; `mut_M1`, `mut_M2` = relocated judge copies for mutation tests; symlinks there point read-only into /work).
Labels: **доказано** (proven) / **скорее всего** (likely) / **возможно** (possible).

## Verdict: REJECT (1 MUST-FIX). Everything else in the package checks out (static content is correct).

The package content is correct and fully explained (diff, pins, image r2f, expectations, judge row, tests 28/28).
The problem is outside the diff, in an unchanged executor file: in the documented start order (`C8_START_ORDER=px4_first`)
`SDLOG_MODE 1` makes the run keep only a short boot log that ends before setup, arm and flight.
A8 cannot produce a valid 4070 run until this is fixed (A9, executor change, its own review).

---

## MUST-FIX

### M1. px4_first + SDLOG_MODE 1: the logger is stopped and never restarted, so flight.ulg is only a boot stub (доказано by code; no 4070 run exists yet)
- `executor/run_sim.snapshot.sh:153-157` (pinned, unchanged from A7):
  `px4-logger stop; sleep 1` then `if [ "$(px4-param show -q SDLOG_MODE)" = 0 ]; then px4-logger start -b 1000 -t; fi`.
  This copies Simulator scripts (goal_step4 run_goal.sh:153-156, run_scenario5.sh:260-261, run_scenario7.sh:317-318),
  and those comments say the restart was written for SDLOG_MODE 0.
- With 4070: `rcS:181` sets SDLOG_MODE 1 by default, and airframe 4070 sets it to 1 again. `init.d/rc.logging:11-14,34` adds `-e`,
  so the logger runs in boot_until_disarm mode (PX4 logger.cpp:288-291, 654-655) and opens a log file at boot.
  Then `run_sim.snapshot.sh:155` stops the logger, which closes that file. Line 156 does not restart the logger
  because SDLOG_MODE is not 0. From then on, nothing is logged for the rest of the run.
- Order in `executor/run.sh`: line 97 (run_sim.snapshot.sh, including the logger stop) runs before line 98 (sitl_setup), the proxy, MAVROS and the flight.
  So the only ULog covers PX4 boot up to EKF tilt alignment.
- Consequences (reasoned from code):
  - `run.sh:68-70`: fresh_log_count = 1 and copied = true, so the judge's `fresh_single_ulog` **passes**.
    README line 49 says "fresh_single_ulog это покажет". It will not.
  - In the legacy copy, `intervals` is empty and `first_arm` is None, so the parameter snapshot is the end of the stub (pre-setup).
    `candidate4030` and `real_parameters_before_arm` can still pass (the 4061/4070 boot values equal the expectation, because D1 says
    setup changes none of them on 4061), with `actual_arm_observed: false`.
  - Flight scenarios (kill/freeze/mavros_restart/land/cancel): the ULog-based core checks become failed/unknown, so the run fails.
    It fails closed, but the whole r2f/4070 series is wasted.
  - No-arm scenarios (`preflight`, `cancel_before`): the ULog halves of `no_arm_preflight_ulog` and `cancel_before_no_arm`
    (legacy:422-428) become **vacuously true**, because the log ended before the scenario. The proxy half still guards
    against a real arm. The verdict can still pass, but one independent evidence layer is silently void (скорее всего).
- Contrast that proves the mechanism: rel3 runs (4030, SDLOG_MODE 1 from rcS) had logs from boot (ULog start 8.2 s,
  first arm 49.2 s, 28/89 logged param changes). They used the older runner without this restart. A7 4061 runs
  (SDLOG_MODE 0) have logs that start at arm (start 50.83 s vs arm 50.83 s), because the restart ran (probe p4.py).
- The tests did not catch this. `a8_checks` only checks that sitl_setup does not write SDLOG_MODE. No test greps the
  executor for code that reads SDLOG_MODE.
- Fix options (the owner/orchestrator decides; each changes the executor, not the judge):
  (a) For SDLOG_MODE ≠ 0, skip the stop/restart. One boot log covers the whole run. The judge's TOPICS
      (legacy:42-44) need no estimator topic, so the reason for the restart does not apply to the judge. The Simulator's
      own analysis may still want estimator_status_flags.
  (b) Restart with the rc.logging arguments for the current mode (`-e` for 1). That leaves 2 fresh logs (boot stub + restarted log),
      so `fresh_single_ulog` = 2 and fails. run.sh would then need to filter on a post-restart marker, which changes the meaning of
      ulog_copy_status and needs review.
  (c) Use `gz_first` for the A8 series. That conflicts with decision D4 (px4_first).
  In every case, add a static test that the logger path handles SDLOG_MODE 1, and add a dry check that flight.ulg contains
  the first arm (for example a test on a ULog from one 4070 smoke run).

## SHOULD

### S1. `tests/a8_judge_on_a7_run.py:40-43`: the generic part is self-referential; only the hard-coded pair discriminates (доказано by mutation)
- `want` is computed from `evidence.values`, which the judge fills only for names that are in the expectation file.
  If a name is missing from the expectation file, it drops out of both `mm` and `want`, so `set(mm) == want` still holds.
- Mutation M1 (expectation without SDLOG_MODE, EXPECT_4070 unchanged) and M2 (both without it): `set(mm)==want` → True,
  and only the literal `{'BAT1_SOURCE','SDLOG_MODE'} <= want` fails (`/work/review_a8_20261110/resid.py` on `mut_M1/2`).
  So the test does catch today's two names, but a future third EXPECT_4070 line (README item 4) would not be checked by this test.
- Suggest: `assert set(EXPECT) <= set(vals)`. `a8_judge_effect.py:31-35` already does this (`assert k in rb['values']`), and
  `a8_checks.py:59-61` covers the file-vs-EXPECT match, so this is defence in depth, not a hole today.

### S2. README item 4, "one line in the builder", is understated (доказано, `tools/make_a8.py:33-38,46,78-79`)
- make_a8.py builds only from A7 into the fixed folder `c8_judge_r2f_a8_20261110` and refuses to overwrite it. A new flow setting
  means: the EXPECT_4070 line, plus AF4070_SHA, plus new DST/NEW/PINS_NAME/launcher version strings (a new package A9), plus the
  stale comment text "+ those 2 values" (judge comment, make_a8.py:126-127).
  The data change is one line. The rebuild is a new revision. State this plainly so nobody edits A8 in place.

### S3. The launcher accepts any pinned chain airframe as `C8_AIRFRAME` (pre-existing; скорее всего harmless)
- `launcher/host_run_wsl_c8_r2e_b.sh:153-155` only requires that the AF file is in `repo_files`. 4061…4030 are pinned as chain
  members, so `C8_AIRFRAME=4061` passes the launcher, run.sh and sitl_setup (`--expected-autostart` = the env value). It is refused
  only later, at the VPE opt-in (`vpe_profile_optin.py:147`, after the simulator started) and by the judge (`SYS_AUTOSTART`).
  It fails closed, but it costs a simulator run. Optional: compare C8_AIRFRAME with `pins.c8_target.airframe` in the pre-check.

## NOTE

- N1 (доказано) diff -r A7↔A8 (excluding reviews/, tests/out_*, notes/, docs) = exactly the files in DIFF_a8.md. Changed-line
  counts match. Only in A7: DIFF_a7.md, tools/make_a7.py, tests/_failed_first_run, pins a7. Only in A8: 2 expect files, pins a8,
  3 tests, make_a8.py. Every change serves the listed purposes (image r2f, airframe 4070, expectations, tests).
- N2 (доказано) Judge: +5 lines only (2 comment lines + the c8_4070 row), no deleted line, logic identical. Legacy copy sha
  8bcef313 in both A7 and A8 and in pins `legacy_verifier_sha256`. Judge sha 5b2d6106.
- N3 (доказано) Image: r2f MANIFEST_SHA256.txt = 2feb53fb and `sha256sum -c` OK. The candidate's flight_profile.py, vpe_fix.py and
  aruco_detect.py are byte-identical to r2f (and to A7). vpe_profile_optin.py (and every other candidate harness file) is absent
  from r2f MANIFEST_SHA256.txt, from image_manifest_r2.tsv and from the r2f tree (find + grep), so rule C1 is not touched.
  Its only change is the 4061→4070 check (2 lines).
- N4 (доказано) Candidate manifest: every file sha matches, there are no unlisted files (README/manifest only), and it equals
  pins `combined_files` and `combined_manifest_sha256`.
- N5 (доказано) Pins 65d0f719: every repo/ledger sha matches the current files. run_files match the executor and r2f.
  No key still points to r2e or A7 (the only "r2e" string is the launcher's file name). Airframe 4070 is pinned and the chain is
  listed. ACCEPTED_PINS lists only 65d0f719. PRODUCT_SHA256SUMS (051433…) verifies against the r2f install and fails on r2e.
  run.sh pins r2f drone.py 94f9dfee, and flight_profile 5b8e2a12 is identical.
- N6 (доказано) Expectations: `flight_real_params_4070.json` = the 4061 file with BAT1_SOURCE 1→0 plus a new SDLOG_MODE 1, both type 6
  (INT32 in PX4, correct). rc file identical. This matches airframe 4070 (`param set-default` lines). sitl_setup cannot overwrite either one:
  BAT1_SOURCE is popped by KEEP_AIRFRAME (`sitl_setup.py:20,339`), and SDLOG_MODE is not in /work/sim/ros_stack/*.json,
  rc_expected09.json or the profile. Nothing else in executor/candidate/launcher hard-codes 4061 in a way that would affect a 4070 run
  (only comments).
- N7 (скорее всего) BAT1_SOURCE 0 is a parity value only in C8. sitl_setup writes `SIM_BAT_ENABLE 0` (sim_only, expected by the judge),
  and 4030/4032 set CBRK_SUPPLY_CHK. No simulated voltage exists, so the "voltage visible" decision is not exercised by C8.
- N8 (доказано) SDLOG_MODE 1 apart from M1: the judge works with logs from boot. `parameters_at` folds the logged changes up to the first
  arm (legacy:244-250), as on all rel3 runs. With gz_first or after fix (a), no-arm scenarios get 1 log instead of 0 (A7
  cancel_before_05 had fresh_log_count 0, rel3 had 1). That is an improvement. Re-arm count behaviour is the same as mode 0.
  Clock-alignment checks use groundtruth overlap and are not tied to the log start (legacy:491-512).
- N9 (доказано) notes/S1_OFFSET_CANCEL.md is correct. `s1_first_armed_trajectory_estimated_offset` (legacy:777-792) is in no verdict
  set (common+core legacy:796-816, full_cancel 829, not in verify_flight_c8 scenario_measurements). ULog numbers reproduced:
  rel3 off0 +0.148 s 0.114/0.102, rel3 off50 +0.096 s 0.605/0.103, A7 off0 +0.024 s 0.482/−0.022. The next records are at the estimate.
  trajectory_setpoint is logged every 0.2 s. The 0.5 m = `ground_hold_offset` 0.5 (r2f simple_offboard.cpp:231,1044).
  The mechanism (log phase vs ground hold) is confirmed.
- N10 (доказано) Tests: I ran `tests/test_c8_b2.sh` myself (nice 19): 28/28 PASS (`tests/out_100559`). SHA256SUMS.txt verifies
  and covers every package file.
- N11 cosmetic, stale comments: `executor/vision_c8.launch.py:3,21` "C8 A7"; `executor/run.sh:82` "flight_profile.py is the r2e copy"
  (the bytes are identical); judge error text "c8_judge_r2e_20261109/reviews" (unchanged logic, do not touch).
- N12 (возможно, outside A8) r2f drone.py's T35 vision watchdog is active only after the first `/mavros/mavros/pose_cov` pose. The candidate
  vpe_fix publishes exactly that topic (vpe_fix.py:264), and no harness file uses the changed drone.py internals. No action is needed.
