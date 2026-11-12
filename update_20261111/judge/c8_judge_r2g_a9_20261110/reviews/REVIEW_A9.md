# REVIEW A9: c8_judge_r2g_a9_20261110 compared with A8 (independent review, 10.11.2026)

**Verdict: ACCEPT WITH SHOULDs.** MUST-FIX: none. SHOULD: 3 (documentation and test strength only; the runtime behaviour fails closed).
Labels: **proven** (code, file or run checked), **likely**, **possible**.
Read-only review. Probes are in `/work/review_a9_20261110/` (helper scripts, mutants in `mut/`, test log `tests_run.log`).
The only writes into A9 were the package tests (`tests/out_104411`, `reviews/tests_out_104411`) and this file.

## What I checked
1. **My own `diff -r` from A8 to A9 (proven).** Every changed file serves one of the five listed purposes:
   - image r2g: `candidate/manifest.json` and `candidate/README.md` (texts and origins only), `executor/PRODUCT_SHA256SUMS.txt`, and the run.sh lines 7/27-28/46/82-83;
   - M1: `executor/run_sim.snapshot.sh`. The only change is the logger block, lines 156-167;
   - airframe v2: pins, launcher comments and paths, `ACCEPTED_PINS_b.txt`, and test paths;
   - expectation: `expect/flight_real_params_4070.json` gains only `EKF2_OF_QMIN {50, type 6}`. It has no MPC_LAND_CRWL;
   - S1/S2: `tests/a8_judge_on_a7_run.py` lines 40-41 and the README;
   - plus `sitl_setup.py` and `vision_c8.launch.py`, where only paths change (r2g, A9 candidate).
   No changes fall outside these purposes.
2. **Judge (proven).** `verify_flight_c8.py` differs from A8 in one line, line 40: the sha of the c8_4070 flight expectation, 5691758... changed to 9e471a6e.... That sha equals the file. The legacy copy is 8bcef313, identical to A8. The rc expectation for 4070 is the same file as for 4061 (99002dc2). flight 4061 = A7.
3. **Expectations against the airframe (proven).** The airframe `4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50` has sha 0224deec (as required). It contains `. 4061…` plus `set-default` BAT1_SOURCE 0, SDLOG_MODE 1 and EKF2_OF_QMIN 50. Compared with the 4061 file, flight_real_params_4070 differs in exactly BAT1_SOURCE 1→0, +SDLOG_MODE 1 and +EKF2_OF_QMIN 50.
4. **EKF2_OF_QMIN type (proven).** In PX4 v1.16.1 (94cb2012), `src/modules/ekf2/params_optical_flow.yaml:52-60` gives `type: int32`, default 1, range 0..255. The expectation type 6 (INT32) is correct. Note that the name applies only in air; EKF2_OF_QMIN_GND stays 0.
5. **Can anything overwrite the three names during a run? No (proven by code; also seen in real runs).**
   - `sitl_setup.py:20` KEEP_AIRFRAME contains BAT1_SOURCE, which is popped at line 341 before any write.
   - SDLOG_MODE and EKF2_OF_QMIN are not in `/work/sim/ros_stack/{flight,rc}_real_params.json`, not in the profile (flight_profile.py), and not in the candidate.
   - In the r2g src and install, only `selfcheck.py:763` mentions EKF2_OF_QMIN, and it only reads it (info).
   - The Simulator's two 4070v2 runs (`goal_step5b_20261109/runs/{ctl_4070v2_v12,diag_4070v2_v30}_r2f_r5_01`) have, in the ULog initial parameters, SDLOG_MODE 1, EKF2_OF_QMIN 50 and BAT1_SOURCE 0, with no changed_parameters for these names.
6. **Pins (proven).**
   - Every sha in repo_files (72), combined_files (15), ledger_files (31, plus @run/drone.py = 068e6eb4) and run_files (17) matches its file.
   - combined_manifest 4af0cf63, legacy 8bcef313, and sdk drone.py 068e6eb4 are all correct.
   - Airframe v2 is pinned (`repo_files`, 0224deec), and airframe_chain[0] is v2. Neither the v1 name nor 0bca708f appears.
   - No key contains r2f/A8. The one exception is the informational history string `c8_target.a8`, which the launcher and judge do not read.
   - `ACCEPTED_PINS_b.txt` holds only 4b46f4d4.
   - `PRODUCT_SHA256SUMS.txt` (95312b5b, 522 lines) passes on the r2g install and fails on the r2f install (40 mismatches).
   - r2g `MANIFEST_SHA256.txt` = 3d503cef, and `sha256sum -c` passes.
7. **Tests (proven).** `tests/test_c8_b2.sh` gives 30/30 PASS (`tests/out_104411`). The S1 test printed `EKF2_OF_QMIN: (1, 50)` among the c8_4070 mismatches, so the new name is really judged.
8. **SHA256SUMS.txt (proven).** Before my test run it verified completely: 133 lines, with every file of the package listed.

## M1 fix: logger semantics (run_sim.snapshot.sh:155-167)
- **-e in PX4 1.16 (proven, `src/modules/logger/logger.cpp`).**
  - `-e` sets `boot_until_disarm` (lines 288-291). `start_log_file(Full)` is called at task start (line 654). SDLOG_BOOT_BAT is 0 in the 4032 chain, so boot logging is not disabled.
  - At the first arm, `start_stop_logging` (lines 1140-1150) calls `start_log_file`. That call returns early because the file is already open, so **the same file continues** through arm.
  - Disarm closes the file by a delayed stop. A re-arm opens a **new** file, the same as mode 0.
  - So a scenario with two arms gives two fresh logs and `fresh_single_ulog` fails, exactly as in A7. The README line 32 statement is correct.
- **`-b 1000 -t` (proven).** These match LOGGER_BUF 1000 and `-t` in `ROMFS/.../rc.logging`.
- **Order "stop → move → start" is correct (proven).**
  - `px4-logger stop` waits for the task to exit (ModuleBase stop), plus `sleep 1`.
  - Even if the file were still being written, `mv` stays on the same filesystem (OUT/rootfs → OUT/boot_log_before_restart). It is a rename, so the open fd keeps writing into the moved file and no data is lost (reasoned).
- **set -euo pipefail (proven).**
  - There is no pipe.
  - `find -exec … \;` ignores the exit status of mv. If mv failed, the boot log would stay in rootfs/log, so fresh_log_count would be 2 and the judge would fail. This fails closed.
  - The `-d` guard is harmless. A mutant without the guard behaves the same.
  - A failing `px4-param` or `px4-logger start` aborts run_sim, and run.sh aborts with it. Also fails closed.
- **Name collisions (proven with a probe; harmless).** `mv -n` (coreutils 9.4) prints "not replacing", returns 0 and leaves the file in place. This leads to count 2, so the judge fails. The aside folder is new for every run, and a run has exactly one boot log, so this is not reachable in practice.
- **run.sh cleanup (proven).**
  - run.sh only does `rglob('*.ulg')` in `OUT/rootfs/log`, so the aside folder is not counted.
  - The judge's `evidence_sha256` uses a list of file names, so the aside folder adds no evidence.
  - Real-run analogue: the Simulator's ed.7b/7c script uses the same restart (`-b 1000 -t -e`) but does not move the boot log. Its runs have exactly **two** .ulg files:
    - a boot log covering sim 0.4–1.0 s (0.3 MB);
    - the restarted log from 2.2 s to 221 s, with arm at 131.7 s, 69 MB and **0 dropouts**.
  - So with A9's move, exactly one log remains. **Likely** for an A9 run; this is not proven, because A9's own runner was not run (no Gazebo in this review).
- **Judge ULog checks with a log that starts before setup and arm (proven by code).**
  - `parameters_at(first_arm)` (legacy:244-250) folds `changed_parameters` up to the first arm. So sitl_setup's writes, now logged as changes after the initial values, are counted. They are not hidden by the initial defaults.
  - Arm intervals come from `vehicle_status` transitions. `rc_valid_while_armed` is limited to armed intervals.
  - `ulog_gazebo_sim_clock_alignment` compares at the same sim timestamps. The extra pre-arm samples are stationary and add no interpolation error.
  - Nothing reads `initial_parameters` alone or the first row as the arm.
- **cancel_before / preflight (no arm).**
  - With `-e` these runs now **get** a log, from the restart until PX4 shuts down (proven by the logger code).
  - In A7 (mode 0) they had none: `INT_flight_C8a7_cancel_before_05` had fresh_log_count 0, so `fresh_single_ulog` failed.
  - `cancel_before_no_arm` and `no_arm_preflight_ulog` become decidable. This is an improvement, not a loosening; it is the intended use of those checks.
  - The file is closed only by PX4's `shutdown` after SIGINT from stop_sim.sh, which sends KILL after 3 s. The tail of the log may be truncated (**possible**). pyulog reads truncated logs, and the checks need `vehicle_command` and no dropouts, not a clean end.
- **gz_first (untouched, likely fine).**
  - PX4's own rcS:358-363 starts `logger start -b 1000 -t -p ekf2_timestamps -e` from boot, after Gazebo is up.
  - That produces one fresh log from boot to disarm, so count 1.
- **Mutation probes on `tests/a9_logger_restart.py` (proven).** Each mutant below makes the test fail:
  - drop `-e`;
  - `-f` instead of `-e`;
  - skip the move;
  - copy instead of move;
  - delete the boot log;
  - accept mode 2.
  Survivors: removing the `-d` guard (equivalent, fine) and **moving the logs after the start** (see S2).

## MUST-FIX
None.

## SHOULD
- **S1: README:12 and run_sim.snapshot.sh:156 say "the arguments rc.logging uses". That is not exact (proven).**
  - In SITL, rcS:358-363 sets `LOGGER_ARGS "-p ekf2_timestamps"` before `rc.logging`. So PX4's own start is `-b 1000 -t -p ekf2_timestamps [-e]`.
  - The restart drops `-p ekf2_timestamps` in both modes. The logger then polls on its timer, not on the EKF timestamps topic.
  - This is not a regression: A7 and A8 mode 0, and the Simulator's ed.7b/7c, restart the same way, and the A7 runs passed the judge.
  - The claim should say "the SDLOG_MODE part of rc.logging (`-e`); `-p ekf2_timestamps` is not passed, as in A7". Do not change the code in this package; it would be a behaviour change.
- **S2: `tests/a9_logger_restart.py` does not check the order "move before start" (proven by mutant `mut/move_after_start.sh`, test PASSED).**
  - The fake `px4-logger` (line 38) creates no file.
  - A runner that moved logs *after* `start -e` would move the new flight log aside too, giving fresh_log_count 0 on a real run. That fails closed, but would cost a full run.
  - Fix in the next revision: make the fake `start` create `rootfs/log/<date>/<time>.ulg`, and assert that the boot log is aside and exactly the new log is in rootfs/log.
- **S3: The README does not say that with SDLOG_MODE 1 the no-arm scenarios (cancel_before, preflight) now produce a ULog (in A7 they had 0).**
  - The no-arm log is closed only at PX4 shutdown, so its tail may be truncated (possible).
  - This changes which checks are decidable for these scenarios. The owner and the Simulator should know before reading those verdicts.
  - One line in "Чего тесты не покажут" is enough.

## NOTE
- Stale texts. None of them affects behaviour (proven):
  - `launcher/host_run_wsl_c8_r2e_b.sh:65` says "C8 set A8 … 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1", without EKF2_OF_QMIN;
  - `tests/a8_checks.py:8` says "image copies = r2f bytes", and line 23 names the r2g path `R2F`;
  - the `tests/a9_checks.py:3` docstring says the expectations and judge are byte-identical to A8. The asserts themselves correctly allow the 4070 sha and EKF2_OF_QMIN.
- The r2g install differs from r2f in 40 built files (.so, .pyc, binaries, setup scripts). It is a rebuild, not only drone.py. This is consistent with the reviewed r2g MANIFEST (3d503cef) and the pinned PRODUCT_SHA256SUMS. README:9 is about the candidate copies and is accurate.
- The restarted log is much larger with `-e`: about 69 MB in the Simulator's 4070v2 runs, against 8 MB in A7 kill_01, because it covers about 130 s before arm. The run.sh disk guard (8 GB) is sufficient.
- README S3 (pre-existing; the launcher accepts another pinned chain airframe) is unchanged, as stated.
- After my test run, `tests/out_104411` and `reviews/tests_out_104411` and this file are not listed in SHA256SUMS.txt. That is expected.
