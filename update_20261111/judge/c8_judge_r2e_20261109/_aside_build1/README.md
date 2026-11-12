# c8_judge_r2e_20261109: C8 on airframe 4061 / image r2e (T28, 09.11.2026). ТОЛЬКО СИМУЛЯТОР

Owner decision: variant B («Делаем Б?» → «да»), a copy of the judge for the new image.
Made by the chat «Разборы и правки кода». Nothing was started; no Gazebo was used.
`c8_executor_20261109`, `flight_verification_03`, `combined_13` and `analysis/exp_scripts` are not modified.

Labels: **доказано** = a check or file comparison was done; **скорее всего** = no control check.

## 1. Judge copy (`verify_flight_c8.py` + `legacy/verify_package1b_gates_c8.py`)

Only three things change compared with the accepted judge (`DIFF_judge.txt`, `DIFF_legacy.txt`; built by `tools/make_c8_judge.py`, which checks the sha of the sources):

- **Expected airframe.** It comes from a fixed table, `--identity` (required).
  - `rel3_4030`: the accepted judge's values.
  - `c8_4061`: SYS_AUTOSTART is 4061.
  - The check id stays `candidate4030` (historical name).
  - SIM_GZ_EN 1 and COM_OBL_RC_ACT 4 are unchanged.
- **Profile names.** `c8_4061` uses 18 names, which is the old 19 minus COM_SPOOLUP_TIME.
  - r2e INDOOR_ARUCO has 13 names; the same closure adds 5 children, giving 18.
- **Report folder.** Reports go only to `reviews/`, and the judge never overwrites.
  - The legacy verifier is this folder's copy, pinned by sha.
  - ROOT is still /work.

Every threshold and every pass/failed/unknown rule is the same.

**Proof (доказано):** `tools/compare_rel3.py`. It ran on all 13 rel3 runs of 26.10 (frozen_inputs_32, combined_13).
- The accepted judge was imported read-only; only its output folder was redirected here.
- With `--identity rel3_4030`, the copy's full JSON is identical to the accepted judge's, except the verifier sha. The exit code is also identical.
- The statuses of all checks equal the saved 26.10 reviews.
- Results: `reviews/rel3_proof/COMPARE_REL3.json` (all_identical: true) and `reviews/rel3_old_accepted_judge/`.

Control: `c8_4061` on rel3 kill (a 4030 run).
- Only `candidate4030` changes, and it is failed (4030 ≠ 4061).
- Some profile checks change, and they are failed (19 ≠ 18 names).
- Provenance and the measurements are unchanged.
- Test: `judge_c8_identity_effect`.

## 2. Executor revision b (`candidate/`, `executor/`, `launcher/`, `pins/`)

Built by `tools/make_c8_exec_b.py` on top of `c8_executor_20261109/executor_r2e` and launcher v31, with 34 replacements, each with its reason (`DIFF_exec_b.md`).

- **D1 (no rollback of 4061).** `sitl_setup.py` no longer writes NAV_RCL_ACT, COM_RCL_EXCEPT or COM_DISARM_LAND. The airframe values 3 / 0 / 0.5 stay.
  - The skipped 20EC values are recorded in `rc_observer.json` under `kept_airframe_values`.
  - The candidate RC contract `rc_expected09.json` asserts NAV_RCL_ACT 3 and COM_RCL_EXCEPT 0.
- **D2/D3 (whole r2e image).** The candidate `combined_c8_r2e` is combined_13 plus these r2e files:
  - `flight_profile.py` (13 names, 5b8e2a12);
  - `vpe_fix.py` (3b8a93d4);
  - `aruco_detect.py` (66f061ec).

  The pins in the closure, the freshness opt-in, the profile opt-in and the diagnostic helper/entry follow these files. run.sh copies the r2e `flight_profile.py` (sha checked).
- **D7 (honest identity).** `sitl_setup.py` records PX4's own SYS_AUTOSTART. `supervisor.py` writes `sitl_autostart` + source into audit.json. `vpe_profile_optin.py` requires 4061; the literal `sitl_4030: true` is gone.
- **Pins.** `pins/frozen_inputs_c8_r2e_b_01.json` (sha see SHA256SUMS.txt) is accepted only by launcher v32 (`launcher/ACCEPTED_PINS_b.txt`).
  - Its repo_files pin the judge copy.
  - Unchanged from v31: the r2e install sums (544f3179), MAVROS bp02 sums, model_v1 + plugin_v1, and the 4061 airframe chain.

Still open, not decided here:
- **BLOCKING (rule 9, owner): the judge check `real_parameters_before_arm`** (legacy :354-370). It compares the values before arm with
  `sim/ros_stack/flight_real_params.json` and `rc_real_params.json`: NAV_RCL_ACT 0, COM_RCL_EXCEPT 4, COM_DISARM_LAND 2.0.
  - With D1 (no rollback), PX4 holds 3 / 0 / 0.5. This check is therefore **failed in 12 of 13** (доказано from the code).
  - The question went to chat 1 with options А (4th judge change: a pinned expectation with these 3 values), Б (keep the rollback) and В (leave it as is). Not changed here.
- **D4 start order.** `C8_START_ORDER` has no default. goal_step4 showed that `gz_first` marks the rangefinder as stuck on the 4032 chain; run_scenario5 uses `px4_first`.
- **U2.** The heartbeat scenario is unknown by design, as in rel3.

## 3. Tests: `tests/test_c8_b.sh` — 17/17 PASS

Results are in `tests/out_*`. The two earlier runs were environment errors (ROS not sourced) and are kept in `tests/_env_fail_runs`. The tests cover:

- syntax;
- the launcher pins pre-check, exactly as the launcher runs it: ok, and the old v31 pins are refused;
- profile 13 / closure 18 = the judge names;
- D1;
- D7: the opt-in refuses 4030 and the old label, and passes 4061 up to the MAVROS route check;
- D2: VPE class composition with the r2e vpe_fix (ROS sourced, no node started), and the combined_13 pin refuses it;
- the judge's refusals and the identity effect.

## 4. How to run (WSL, one at a time, `cd /work`; about 10–15 min each)

```
export BB_COMBINED_ROOT=/work/c8_judge_r2e_20261109/candidate
export BB_FROZEN_PINS=/work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_01.json
export C8_START_ORDER=px4_first      # D4: Simulator chat's choice (no default)
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
  --frozen-pins /work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_01.json \
  --out /work/c8_judge_r2e_20261109/reviews/TAG_review.json
```

Exit codes: 0 = pass, 1 = failed, 2 = unknown. Check `host_check.json` `valid_host` first; if it is false, the run is INVALID.
