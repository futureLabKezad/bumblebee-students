# c8_judge_r2e_20261109: C8 on airframe 4061 / image r2e (T28, 09.11.2026). ТОЛЬКО СИМУЛЯТОР

Owner decisions:
- variant B («Делаем Б?» → «да»): a copy of the judge for the new image;
- set 4061, and the judge expects exactly this set («да»): variant A5, see chat 1 09.11.

Made by the chat «Разборы и правки кода». Nothing was started; no Gazebo was used.
`c8_executor_20261109`, `flight_verification_03`, `combined_13`, `analysis/exp_scripts` and `sim/ros_stack` are not modified.

Current build: **build 2 (A5)**.
- Build 1 (only 3 values kept) is moved aside, unchanged, in `_aside_build1/`.
- Its independent review is in `/work/review_c8_judge_r2e_20261109/`.

Labels: **доказано** = a check or file comparison was done; **скорее всего** = no control check.

## 1. Judge copy (`verify_flight_c8.py` + `legacy/verify_package1b_gates_c8.py` + `expect/`)

Changes compared with the accepted judge (`DIFF_judge.txt`, `DIFF_legacy.txt`, `DIFF_expect.txt`; built by `tools/make_c8_judge_v2.py`, which checks the sha of every source):

1. **Expected airframe.** It comes from a fixed table, `--identity` (required).
   - `rel3_4030`: the accepted judge's values.
   - `c8_4061`: SYS_AUTOSTART is 4061.
   - The check id stays `candidate4030` (historical name).
   - SIM_GZ_EN 1 and COM_OBL_RC_ACT 4 are unchanged.
2. **Profile names.** `c8_4061` uses 18 names, which is the old 19 minus COM_SPOOLUP_TIME.
   - r2e INDOOR_ARUCO has 13 names; the same closure adds 5 children, giving 18.
3. **Report folder.** Reports go only to `reviews/`, and the judge never overwrites.
   - The legacy verifier is this folder's copy, pinned by sha.
   - ROOT is still /work.
4. **The expectation of `real_parameters_before_arm`** (variant A5; owner «да» to "the judge expects the approved set").
   - For `c8_4061` only, the judge uses `expect/flight_real_params_4061.json` and `expect/rc_real_params_4061.json`.
   - Their sha is pinned in the judge, and a changed file makes the judge refuse.
   - A copy of the files in the run folder cannot replace them.
   - They differ from `sim/ros_stack/*_real_params.json` in **exactly 5 numbers**, the values of airframe 4061 (`DIFF_expect.txt`, test `expect_diff_exactly_five`):

     | Parameter | Old value | 4061 value |
     |---|---|---|
     | NAV_RCL_ACT | 0 | 3 |
     | COM_RCL_EXCEPT | 4 | 0 |
     | COM_DISARM_LAND | 2.0 | 0.5 |
     | COM_SPOOLUP_TIME | 0.0 | 1.0 |
     | BAT1_SOURCE | -1 | 1 |

   - `rel3_4030` uses the original lookup with the old files.

Every threshold and every pass/failed/unknown rule is the same.

**Proof (доказано):** `tools/compare_rel3_v2.py`. It ran on all 13 rel3 runs of 26.10 (frozen_inputs_32, combined_13).
- The accepted judge was imported read-only; only its output folder was redirected here.
- With `--identity rel3_4030`, the copy's full JSON is identical to the accepted judge's, except the verifier sha. The exit code is also identical.
- The statuses of all checks equal the saved 26.10 reviews.
- Results: `reviews/rel3_proof_v2/COMPARE_REL3.json` (all_identical: true). The build 1 proof is in `reviews/rel3_proof/`.

Control: `c8_4061` on rel3 kill (a 4030 run that holds the old file values).
- `candidate4030` is failed (4030 ≠ 4061).
- `real_parameters_before_arm` is failed on exactly these 5 names, with the 4061 values as expectation.
- The profile-name checks are failed (19 ≠ 18).
- Everything else is unchanged.
- Test: `judge_c8_identity_effect`.

## 2. Executor revision b (`candidate/`, `executor/`, `launcher/`, `pins/`)

Built by `tools/make_c8_exec_b2.py` on top of `c8_executor_20261109/executor_r2e` and launcher v31, with 34 replacements, each with its reason (`DIFF_exec_b.md`).

- **D1 (A5, no rollback of 4061).** `sitl_setup.py` does not write NAV_RCL_ACT, COM_RCL_EXCEPT, COM_DISARM_LAND, COM_SPOOLUP_TIME or BAT1_SOURCE. These are all 5 names whose 20EC-file value differs from 4061.
  - The skipped file values are recorded in `rc_observer.json` under `kept_airframe_values`.
  - Test `d1_setup_changes_on_4061` runs the real composition lines of `sitl_setup.py` against the 4061 ULog (goal run l1_r2e_4061_loop). Setup changes **no** 4061 value.
  - The candidate RC contract `rc_expected09.json` asserts NAV_RCL_ACT 3 and COM_RCL_EXCEPT 0.
- **D2/D3 (whole r2e image).** The candidate `combined_c8_r2e` is combined_13 plus these r2e files:
  - `flight_profile.py` (13 names, 5b8e2a12);
  - `vpe_fix.py` (3b8a93d4);
  - `aruco_detect.py` (66f061ec).

  The pins in the closure, the freshness opt-in, the profile opt-in and the diagnostic helper/entry follow these files. run.sh copies the r2e `flight_profile.py` (sha checked).
- **D7 (honest identity).** `sitl_setup.py` records PX4's own SYS_AUTOSTART. `supervisor.py` writes `sitl_autostart` + source into audit.json. `vpe_profile_optin.py` requires 4061; the literal `sitl_4030: true` is gone.
- **Pins.** `pins/frozen_inputs_c8_r2e_b_02.json` is accepted only by launcher v32 (`launcher/ACCEPTED_PINS_b.txt`); pins 01 are refused.
  - Its repo_files pin the judge copy and `expect/`.
  - Its ledger equals what run.sh will record (test `ledger_equals_pins`).
  - Unchanged from v31: the r2e install sums (544f3179), MAVROS bp02 sums, model_v1 + plugin_v1, and the 4061 airframe chain.

Known differences and open points:
- **BAT1_SOURCE (known difference, chat 1 09.11).** In 4061 it is 1, and the judge expects what 4061 really holds, 1. In the approved set it is 0. This means the battery group is not enabled in Gazebo.
  - A separate control run with BAT1_SOURCE 0 comes later; it is not part of this series.
- **COM_SPOOLUP_TIME 1.0** is the 20EC value, and r2e does not change it. C8 flies with it: the arm and cancel scenarios depend on this window.
- **Scope note (review SHOULD 2).** C8 writes and restores INDOOR_ARUCO (13 values), as the earlier C8 harness did. The r2e product itself writes no parameters, and its examples check INDOOR_ARUCO_SLOW.
- **D4 start order.** `C8_START_ORDER` has no default. goal_step4 showed that `gz_first` marks the rangefinder as stuck on the 4032 chain; run_scenario5 uses `px4_first`.
- **U2.** The heartbeat scenario is unknown by design, as in rel3.

## 3. Tests: `tests/test_c8_b2.sh` — 22/22 PASS

Results are in `tests/out_*`; the build 1 tests (`test_c8_b.sh`) are kept. The tests cover:

- syntax;
- the launcher pins pre-check, exactly as the launcher runs it: pins 02 ok; v31 pins and pins 01 refused;
- profile 13 / closure 18 = the judge names;
- D1 on the 4061 ULog;
- the RC contract;
- D7: the opt-in refuses 4030 and the old label, and passes 4061 up to the MAVROS route check;
- D2: VPE class composition with the r2e vpe_fix (ROS sourced, no node started), and the combined_13 pin refuses it;
- the ledger against the pins;
- the judge's refusals and the identity effect;
- `expect` = exactly 5 numbers, and the sha pin is enforced.

## 4. How to run (WSL, one at a time, `cd /work`; about 10–15 min each)

```
export BB_COMBINED_ROOT=/work/c8_judge_r2e_20261109/candidate
export BB_FROZEN_PINS=/work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_02.json
export C8_START_ORDER=px4_first      # D4: the Simulator chat's choice (no default)
L=/work/c8_judge_r2e_20261109/launcher/host_run_wsl_c8_r2e_b.sh
bash $L INT_flight_C8b_kill_01 kill paused
bash $L INT_flight_C8b_freeze_02 freeze paused
bash $L INT_flight_C8b_mavros_restart_03 mavros_restart paused
bash $L INT_flight_C8b_pilot_04 pilot paused
bash $L INT_flight_C8b_cancel_before_05 cancel_before paused
bash $L INT_flight_C8b_ack_cancel_06 ack_cancel paused
CANCEL_OFFSET_MS=0   bash $L INT_flight_C8b_cancel_off0_07 cancel paused
CANCEL_OFFSET_MS=50  bash $L INT_flight_C8b_cancel_off50_08 cancel paused
CANCEL_OFFSET_MS=200 bash $L INT_flight_C8b_cancel_off200_09 cancel paused
CANCEL_OFFSET_MS=500 bash $L INT_flight_C8b_cancel_off500_10 cancel paused
CANCEL_OFFSET_MS=900 bash $L INT_flight_C8b_cancel_off900_11 cancel paused
CANCEL_OFFSET_MS=980 bash $L INT_flight_C8b_cancel_off980_12 cancel paused
bash $L INT_flight_C8b_heartbeat_13 heartbeat paused
```

Judge for each TAG (writes only to `reviews/`):

```
/work/analysis/layout/.venv/bin/python -B -I /work/c8_judge_r2e_20261109/verify_flight_c8.py --identity c8_4061 \
  --run /work/sim/runs/TAG --expected-manifest /work/c8_judge_r2e_20261109/candidate/manifest.json \
  --frozen-pins /work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_02.json \
  --out /work/c8_judge_r2e_20261109/reviews/TAG_review.json
```

Exit codes: 0 = pass, 1 = failed, 2 = unknown. Check `host_check.json` `valid_host` first; if it is false, the run is INVALID.
