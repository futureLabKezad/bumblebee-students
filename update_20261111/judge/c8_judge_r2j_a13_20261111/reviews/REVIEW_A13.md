# REVIEW_A13: independent review of c8_judge_r2j_a13_20261111 against A12 (11.11.2026)

Reviewer: independent agent. The review was read-only. This file is the only thing it wrote. No Gazebo, PX4, drone or ssh was used.

## Verdict: ACCEPT WITH NOTES

There is no MUST-FIX. The package does what it says: it switches C8 to the T52 model_v2 and airframe 4074. Judge logic, S tests and criteria are unchanged.

## MUST-FIX
None.

## SHOULD
1. model_v2 does more than move the sensors. It also moves the 4 rotors from ±0.222739 to ±0.2262 (rotor links and visuals, 8 pose lines, `diff model_v1 model_v2`). README and DIFF_a13.md list only the camera, IMU and flow/lidar poses, so add a line about the rotors. PX4 CA_ROTOR*_PX/PY in the chain are still 0.25 (from 4032), and 0.2227 in 4030. That mismatch existed before and is now slightly smaller. It is outside this package, but the flight dynamics change, so A12 flight numbers are not directly comparable with A13 (скорее всего a small effect).
2. 4074 sets EKF2_MIN_RNG 0.23, which overrides 0.28 from 4060 in the same chain. This is not judged and not written by sitl_setup, so the package is not affected. Record it for traceability: on the Gazebo floor dist_bottom is ≈0.28, which is above 0.23.
3. The lever arms in model.sdf are relative to the base_link origin. The base_link inertial (CoM) pose is (-0.00055, 0, -0.0959) in Gazebo axes. PX4 EKF2_*_POS are relative to the CoG. This existed in model_v1 too. It matters only if the reference §3.1 origin is not the CoG (возможно; not verified here). This is a question for the Simulator chat, not a defect of A13.
4. The `verify_flight_c8.py` hunk in DIFF_a13.md is a difflib alignment artifact: it shows the 2 real_params lines before the `'c8_4074'` line. A plain `diff` confirms the net effect is exactly the new row placed after c8_4070, plus the comment. A reader may be confused, so a note in the DIFF would help.

## Checked items (evidence)
1. **Judge.** `diff A12 A13 verify_flight_c8.py` adds 2 comment lines and 1 row: `c8_4074` = autostart 4074, names `NAMES_REL3 - {COM_SPOOLUP_TIME}` (same as c8_4070), and the same `expect/flight_real_params_4070.json` (9e471a6e) and `rc_real_params_4070.json` (99002dc2). There are no removed lines and no other changes. The expect files are byte-identical to A12, and their sha256 equals the pinned values in the row.
   - Reusing the 4070 expectations is correct (доказано). `grep EKF2_(IMU|RNG|OF)_POS|EKF2_MIN_RNG|_POS_` finds nothing in `expect/*.json` or in `/work/sim/ros_stack/{rc,flight}_real_params.json`.
   - `executor/sitl_setup.py` is byte-identical to A12. It writes only the keys from those JSON files, plus COM_OBL_RC_ACT, minus KEEP_AIRFRAME, so it never writes the 10 new names.
   - No runtime file of the package (.py/.json/.sh outside tests/tools/pins/legacy) contains these names. Their values from airframe 4074 therefore reach PX4 untouched and are not judged.
2. **Opt-in.** In `candidate/parameters/vpe_profile_optin.py` only lines 147–148 change: 4070 → 4074 in the condition and the message. The candidate manifest changes only this file's sha (a11f755e) and the scope/notes texts.
3. **Pins.** a4ad2b2f matches ACCEPTED_PINS_b.txt.
   - After renaming a12→a13 and model_v1→model_v2, repo_files equals the A12 set plus the 4074 airframe. Nothing is missing and no model_v1 key is left.
   - Five shas change as expected: run.sh, verify_flight_c8.py 706fea59, model.sdf 1618e853, vpe_profile_optin.py and vision_c8.launch.py.
   - All 73 repo_files shas were recomputed and match, including model.sdf 1618e853…, 4074 61237522…, 4070 v2 0224deec… and the judge 706fea59….
   - c8_target: airframe 4074, chain = [4074] + the A12 chain, model = t52 model_v2, judge `--identity c8_4074`, candidate/executor/launcher are a13. combined_files, run_files and ledger_files differ only by the 3 changed files.
   - `sha256sum -c SHA256SUMS.txt` reports all OK.
4. **Airframe 4074.** It sources 4070 v2 and sets exactly the 10 values: IMU -0.059/0.007/-0.016, RNG and OF 0.082/-0.028/0.034, MIN_RNG 0.23.
   - The model.sdf poses are: IMU sensor -0.059 -0.007 0.016 (in base_link), flow_link and lidar_sensor_link 0.082 0.028 -0.034 relative_to base_link, and the camera 0.081 0 -0.034.
   - The signs are consistent (доказано by the transform). Gazebo FLU → PX4 FRD keeps X and negates Y and Z: IMU (-0.059,-0.007,0.016) → (-0.059,0.007,-0.016), flow/lidar (0.082,0.028,-0.034) → (0.082,-0.028,0.034). Both match the airframe.
   - The camera has no PX4 parameter. The runner TF in vision_c8.launch.py is 0.081 0 -0.034, the same as the model.
5. **Tests and launcher.** tests/RESULT_test_c8_b2.txt: `RESULT pass=32 fail=0` (32 PASS lines, 0 FAIL). The launcher defaults are `C8_AIRFRAME=${C8_AIRFRAME:-4074}` and `C8_MODEL=${C8_MODEL:-/work/t52_model_ref_20261111/models/model_v2/bumblebee}`. The launcher_pins_refuses_old test now uses the A12 pins.
6. **Scope.** Files changed against A12 are the docs, candidate README/manifest/opt-in, executor run.sh and vision_c8.launch.py (path only), the test_entry_order path, the launcher and its pins list, test path renames, a8_checks, test_c8_b2.sh and the judge. New files are pins a13, a13_checks.py, make_a13.py and DIFF_a13.md. model_v2 differs from model_v1 only in model.sdf (`diff -rq`).
