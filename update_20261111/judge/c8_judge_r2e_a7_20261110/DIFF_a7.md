# DIFF_a7 — A7 против A6 (/work/c8_judge_r2e_a6_20261110, пины d61b25d7)

## Правки и причины
1. executor/vision_c8.launch.py — Header: what this copy is.
2. executor/vision_c8.launch.py — A7: the candidate must be exactly this package candidate (was: only .../integration/combined_*).
3. executor/vision_c8.launch.py — New file (A7).
4. executor/run.sh — Own folder.
5. executor/run.sh — A7: launch the package copy of the camera chain (the shared one refuses a candidate outside .../integration/combined_*).
6. launcher/host_run_wsl_c8_r2e_b.sh — Header.
7. launcher/host_run_wsl_c8_r2e_b.sh — First line.
8. launcher/host_run_wsl_c8_r2e_b.sh — Refusal text.
9. launcher/host_run_wsl_c8_r2e_b.sh — Runner.
10. launcher/host_run_wsl_c8_r2e_b.sh — Pins runner.
11. launcher/host_run_wsl_c8_r2e_b.sh — Banner.
12. launcher/host_run_wsl_c8_r2e_b.sh — host_check runner.
13. tests/test_c8_b2.sh — Test paths -> A7 (2 places).
14. tests/d1_check.py — Test paths -> A7 (1 places).
15. tests/ledger_check.py — Test paths -> A7 (1 places).
16. tests/a6_apply_order.py — Test paths -> A7 (1 places).
17. tests/test_c8_b2.sh — Pre-check uses pins A7.
18. tests/test_c8_b2.sh — Ledger test uses pins A7.
19. tests/test_c8_b2.sh — Control: the A6 pins are refused by the A7 launcher.
20. tests/test_c8_b2.sh — A7 test added.
21. tests/a7_vision_launch.py — New test (A7).

## Новый файл executor/vision_c8.launch.py против общего combined_trial_tools/vision.launch.py

```diff
--- /work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py	2026-10-15 12:12:30.073345700 +0400
+++ executor/vision_c8.launch.py	2026-11-10 03:44:59.277837523 +0400
@@ -1,4 +1,8 @@
-"""Ground camera chain for a separately frozen integration candidate."""
+"""Ground camera chain for a separately frozen integration candidate.
+
+C8 A7 copy (10.11.2026) of combined_trial_tools/vision.launch.py (sha c9fe8ba6): only the candidate-location
+check differs. It requires exactly the C8 package candidate c8_judge_r2e_a7_20261110/candidate (the shared file accepts
+only .../integration/combined_*). The detector-vs-manifest sha check is unchanged."""
 import hashlib
 import json
 import os
@@ -14,9 +18,8 @@
             os.environ.get('GZ_PARTITION') != 'bbtrial'):
         raise RuntimeError('Isolated SITL environment required')
     root = Path(os.environ['BB_COMBINED_ROOT']).resolve()
-    parent = Path('/work/parallel_work/20261015/integration')
-    if not root.is_relative_to(parent) or not root.name.startswith('combined_'):
-        raise RuntimeError('Separate integration candidate required')
+    if root != Path('/work/c8_judge_r2e_a7_20261110/candidate'):   # C8 A7: only this package's frozen candidate
+        raise RuntimeError('C8 package candidate required')
     detector_path = root/'vision/aruco_detect.py'
     manifest = json.loads((root/'manifest.json').read_text())
     if hashlib.sha256(detector_path.read_bytes()).hexdigest() != manifest['files']['vision/aruco_detect.py']:
```

### executor/run.sh

```diff
--- /work/c8_judge_r2e_a6_20261110/executor/run.sh	2026-11-10 01:25:27.459450852 +0400
+++ executor/run.sh	2026-11-10 03:44:59.277893953 +0400
@@ -4,7 +4,7 @@
 TAG=${TAG:?}; SCENARIO=${SCENARIO:-land}
 [[ "$TAG" =~ ^INT_flight_[a-zA-Z0-9_]+$ ]]
 case "$SCENARIO" in preflight|land|kill|freeze|mavros_restart|pilot|cancel_before|cancel|ack_cancel|heartbeat|guard_hold|cleanup_hold) ;; *) exit 2;; esac
-OWN=/work/c8_judge_r2e_a6_20261110/executor  # A6: this copy (revision b + apply order, ../DIFF_a6.md)
+OWN=/work/c8_judge_r2e_a7_20261110/executor  # A7: this copy (A6 + own camera launch file, ../DIFF_a7.md)
 export BB_COMBINED_ROOT=${BB_COMBINED_ROOT:?reviewed combined candidate required}
 # c8: target set as parameters; no default in run.sh (launcher/host_run_wsl_c8_r2e.sh passes them; defaults are there)
 export C8_AIRFRAME=${C8_AIRFRAME:?} C8_PX4_ETC=${C8_PX4_ETC:?} C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:?} C8_PRODUCT_SRC=${C8_PRODUCT_SRC:?}
@@ -109,7 +109,7 @@
 MPID=$!; printf '%s\n' "$MPID" > "$OUT/mavros.pid"
 # flight_trial_12: evidence of the MAVROS libraries the running mavros_node really mapped (read-only, after 8 s)
 ( sleep 8; for f in $(grep -oE '/[^ ]*(mavros|mavconn)[^ ]*\.so[^ ]*' "/proc/$MPID/maps" 2>/dev/null | sort -u); do sha256sum "$f"; done > "$OUT/mavros_loaded_libs.txt" 2>&1 || true ) &
-setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch /work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py > "$OUT/camera_stack.log" 2>&1 < /dev/null &
+setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch "$OWN/vision_c8.launch.py" > "$OUT/camera_stack.log" 2>&1 < /dev/null &
 CPID=$!; printf '%s\n' "$CPID" > "$OUT/camera_stack.pid"
 setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch "$OUT/flight.launch.py" > "$OUT/ros.log" 2>&1 < /dev/null &
 FPID=$!; printf '%s\n' "$FPID" > "$OUT/ros.pid"
```

### launcher/host_run_wsl_c8_r2e_b.sh

```diff
--- /work/c8_judge_r2e_a6_20261110/launcher/host_run_wsl_c8_r2e_b.sh	2026-11-10 01:25:27.459587218 +0400
+++ launcher/host_run_wsl_c8_r2e_b.sh	2026-11-10 03:44:59.278038006 +0400
@@ -1,6 +1,6 @@
 #!/bin/bash
 # ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY). К дрону не подключается.
-# host_run_wsl_c8_r2e_b.sh = launcher v33-c8-r2e-a6 (A6, T32 10.11.2026: runner = c8_judge_r2e_a6_20261110/executor; was v32-c8-r2e-b) (Claude, T28 09.11.2026): copy of c8_executor_20261109/launcher/host_run_wsl_c8_r2e.sh
+# host_run_wsl_c8_r2e_b.sh = launcher v34-c8-r2e-a7 (A7, 10.11.2026: runner = c8_judge_r2e_a7_20261110/executor; A6 was v33, b was v32) (Claude, T28 09.11.2026): copy of c8_executor_20261109/launcher/host_run_wsl_c8_r2e.sh
 #   for the C8 executor revision b /work/c8_judge_r2e_20261109/executor. Changes: ../DIFF_exec_b.md (v31 changes: c8_executor_20261109/DIFF_r2e.md).
 #   bash host_run_wsl_c8_r2e_b.sh TAG SCENARIO [VIEW]      (no TRIAL argument: the runner is fixed; TRIAL lines below are v29 history)
 #   env (c8): C8_START_ORDER=gz_first|px4_first REQUIRED (no default); C8_AIRFRAME C8_PX4_ETC C8_PRODUCT_INSTALL C8_PRODUCT_SRC
@@ -26,14 +26,14 @@
 # requested renderer) AND the executor's own gates AND the independent verifier pass.
 # Never deletes anything; stops only exact process groups it started.
 set -u
-echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6; no real drone, no ssh"
+echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v34-c8-r2e-a7; no real drone, no ssh"
 TAG=${1:?TAG}; SCENARIO=${2:?SCENARIO}; VIEW=${3:-paused}; TRIAL=c8
-[ $# -le 3 ] || { echo "host_run_wsl_c8: REFUSED: no TRIAL argument in v33-c8-r2e-a6 (the runner is fixed)" >&2; exit 2; }
+[ $# -le 3 ] || { echo "host_run_wsl_c8: REFUSED: no TRIAL argument in v34-c8-r2e-a7 (the runner is fixed)" >&2; exit 2; }
 RENDER=${RENDER:-hr1}; KEEP_AWAKE=${KEEP_AWAKE:-0}
 HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
 WORK=/work
 INTEG=$WORK/parallel_work/20261015/integration
-RUNNER=$WORK/c8_judge_r2e_a6_20261110/executor/run.sh   # A6: the only runner of this launcher
+RUNNER=$WORK/c8_judge_r2e_a7_20261110/executor/run.sh   # A7: the only runner of this launcher
 OUT=$WORK/sim/runs/$TAG
 SIDE=$WORK/sim/runs/$TAG.launcher
 CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
@@ -147,7 +147,7 @@
     if extra: P.append('unexpected entries in the candidate: ' + ', '.join(sorted(extra)[:20]))
     rf = pins.get('repo_files')
     if not isinstance(rf, dict) or not rf: P.append('pins have no repo_files object'); rf = {}
-    runner = 'c8_judge_r2e_a6_20261110/executor/run.sh'  # A6: the fixed runner
+    runner = 'c8_judge_r2e_a7_20261110/executor/run.sh'  # A7: the fixed runner
     if runner not in rf: P.append('pins do not cover TRIAL %s (%s not pinned)' % (trial, runner))
     # c8: every file named by a C8_* parameter must be pinned in repo_files (another target set = new pins = new ACCEPTED_PINS)
     for key in ('C8_AF_FILE', 'C8_MODEL_SDF', 'C8_FLOW_PLUGIN', 'C8_DRONE_PY'):
@@ -206,7 +206,7 @@
 if [ "$RENDER" != sw ] && [ "${#GPU_VARS[@]}" = 0 ]; then die "gpu_env.sh gives no variables: hr1/hr0 would silently render on the CPU"; fi
 # atomic per-TAG lock: a second launcher with the same TAG cannot pass this line
 mkdir "$SIDE" 2>/dev/null || die "could not create $SIDE (TAG in use by another launcher?)"
-echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6" > "$SIDE/launcher.log"
+echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v34-c8-r2e-a7" > "$SIDE/launcher.log"
 echo "host_run_wsl: TAG=$TAG SCENARIO=$SCENARIO VIEW=$VIEW TRIAL=$TRIAL RENDER=$RENDER KEEP_AWAKE=$KEEP_AWAKE CANCEL_OFFSET_MS=${CANCEL_OFFSET:-default}" | tee -a "$SIDE/launcher.log"
 echo "host_run_wsl_c8: C8_AIRFRAME=$C8_AIRFRAME C8_START_ORDER=$C8_START_ORDER C8_PX4_ETC=$C8_PX4_ETC C8_PRODUCT_INSTALL=$C8_PRODUCT_INSTALL C8_PRODUCT_SRC=$C8_PRODUCT_SRC C8_MAVROS_INSTALL=$C8_MAVROS_INSTALL C8_MODEL=$C8_MODEL C8_FLOW_PLUGIN=$C8_FLOW_PLUGIN" | tee -a "$SIDE/launcher.log"
 echo "host_run_wsl: candidate $COMBINED matches frozen pins $PINS" | tee -a "$SIDE/launcher.log"
@@ -348,7 +348,7 @@
 out_unchanged = len(oh) == 2 and oh[0] == oh[1]
 cand = js('candidate_check.json')
 candidate_ok = bool(cand and cand.get('ok') is True)
-doc = {'tag': tag, 'scenario': scen, 'view': view, 'trial': 'c8_judge_r2e_a6_20261110/executor', 'combined_root': combined,
+doc = {'tag': tag, 'scenario': scen, 'view': view, 'trial': 'c8_judge_r2e_a7_20261110/executor', 'combined_root': combined,
        'runner_exit': int(rc), 'host_start': start, 'host_end': end, 'host_start_utc': s_utc, 'host_end_utc': e_utc,
        'host_start_epoch': int(s_ep), 'host_end_epoch': int(e_ep),
        'power_before': None, 'power_after': None, 'low_power_mode_before': None, 'low_power_mode_after': None,
```

### tests/test_c8_b2.sh

```diff
--- /work/c8_judge_r2e_a6_20261110/tests/test_c8_b2.sh	2026-11-10 01:25:27.459879055 +0400
+++ tests/test_c8_b2.sh	2026-11-10 03:44:59.278338070 +0400
@@ -2,7 +2,7 @@
 # T28 static tests (no Gazebo, no PX4, no node started). Run from anywhere: bash tests/test_c8_b.sh
 # Writes nothing outside tests/out_<time>/ of this folder (no bytecode: PYTHONDONTWRITEBYTECODE=1).
 set -uo pipefail
-D=/work/c8_judge_r2e_a6_20261110
+D=/work/c8_judge_r2e_a7_20261110
 export PYTHONDONTWRITEBYTECODE=1
 O=$D/tests/out_$(date +%H%M%S); mkdir -p "$O"
 PASS=0; FAIL=0
@@ -26,7 +26,7 @@
   C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf \
   C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
   C8_DRONE_PY=/work/fixed_image_r2e_20261109/src/bumblebee/examples/drone.py \
-  python3 -I $O/precheck.py $D/candidate $D/pins/frozen_inputs_c8_r2e_a6_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
+  python3 -I $O/precheck.py $D/candidate $D/pins/frozen_inputs_c8_r2e_a7_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
 # control: the old v31 pins are not accepted by this launcher
 t launcher_pins_refuses_old bash -c "! env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl \
   C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
@@ -64,7 +64,7 @@
 # 5. D7: the VPE opt-in refuses a wrong / missing airframe and passes 4061 up to the MAVROS route check
 cat > $O/optin_case.py <<'PY'
 import json, sys, runpy
-D = '/work/c8_judge_r2e_a6_20261110'
+D = '/work/c8_judge_r2e_a7_20261110'
 audit, o = json.loads(sys.argv[1]), sys.argv[2]
 cfg = o + '/fake_mavros.yaml'; open(cfg, 'w').write('fcu_url: wrong\n')
 audit.update(sim_gz_en_1=True, all_fcu_paths_guarded=True, no_hardware=True, raw_topics_verified=True, exclusive_profile_writer=True,
@@ -120,7 +120,7 @@
 J="/work/analysis/layout/.venv/bin/python -B -I $D/verify_flight_c8.py --run /work/sim/runs/INT_flight_pc_rel3_kill_01 --expected-manifest /work/parallel_work/20261015/integration/combined_13/manifest.json --frozen-pins /work/parallel_work/20261015/integration/flight_verification_03/frozen_inputs_32.json"
 t judge_needs_identity bash -c "$J --out $D/reviews/x_noid.json > $O/noid.txt 2>&1; rc=\$?; [ \$rc = 2 ] && grep -q 'the following arguments are required: --identity' $O/noid.txt && [ ! -e $D/reviews/x_noid.json ]"
 # the ledger run.sh will write equals the pins' ledger_files, keyed as the judge keys it
-t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_a6_01.json
+t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_a7_01.json
 t judge_refuses_unknown_identity bash -c "$J --out $D/reviews/x_bad.json --identity c8_4030 2>&1 | grep -q 'invalid choice'; [ ! -e $D/reviews/x_bad.json ]"
 t judge_refuses_out_outside bash -c "$J --out $O/x.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'; [ ! -e $O/x.json ]"
 t judge_refuses_overwrite bash -c "$J --out $D/reviews/OVERWRITE_GUARD.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'"
@@ -183,10 +183,12 @@
 t launcher_refuses_pins_01 bash -c "! env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl \
   C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
   C8_DRONE_PY=/work/fixed_image_r2e_20261109/src/bumblebee/examples/drone.py \
-  python3 -I $O/precheck.py $D/candidate /work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_02.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
+  python3 -I $O/precheck.py $D/candidate /work/c8_judge_r2e_a6_20261110/pins/frozen_inputs_c8_r2e_a6_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
 
 # A6: apply order on the 4061 baseline (candidate KnownCapsModel = the PX4 committed clamps): new order reaches every
 # profile value; the old dict order reproduces the run failure (MPC_XY_CRUISE 0.25); the restore returns the baseline.
 t a6_apply_order python3 -B -I $D/tests/a6_apply_order.py
+# A7: the package camera launch accepts exactly this candidate, refuses others and a changed detector (ROS sourced, no node started)
+t a7_vision_launch bash -c "set +u; source /opt/ros/jazzy/setup.bash; source /work/ws_sitl/install/setup.bash; set -u; python3 -B $D/tests/a7_vision_launch.py"
 echo "RESULT pass=$PASS fail=$FAIL (logs $O)"
 [ "$FAIL" = 0 ]
```

## Без изменений (байт в байт)
- verify_flight_c8.py
- legacy/verify_package1b_gates_c8.py
- expect/flight_real_params_4061.json
- expect/rc_real_params_4061.json
- executor/supervisor.py
- candidate/ (весь)
