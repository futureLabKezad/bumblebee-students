# DIFF_a6 — A6 против сборки 2 (/work/c8_judge_r2e_20261109, пины 02 40d67c1c), сгенерировано из build_edits.json и diff -u

## Правки и причины
1. executor/supervisor.py — A6: import the candidate closure order (parents before children).
2. executor/supervisor.py — A6: apply the profile parents-before-children; same names and values, only the order changes.
3. executor/run.sh — Own folder is the new copy.
4. launcher/host_run_wsl_c8_r2e_b.sh — Header: version and runner.
5. launcher/host_run_wsl_c8_r2e_b.sh — First printed line: version.
6. launcher/host_run_wsl_c8_r2e_b.sh — Version in a refusal.
7. launcher/host_run_wsl_c8_r2e_b.sh — Runner = A6.
8. launcher/host_run_wsl_c8_r2e_b.sh — Pins must cover this runner.
9. launcher/host_run_wsl_c8_r2e_b.sh — launcher.log banner.
10. launcher/host_run_wsl_c8_r2e_b.sh — host_check names the real runner.
11. tests/test_c8_b2.sh — Test paths -> the A6 folder (2 places).
12. tests/d1_check.py — Test paths -> the A6 folder (1 places).
13. tests/ledger_check.py — Test paths -> the A6 folder (1 places).
14. tests/test_c8_b2.sh — Pre-check uses pins A6.
15. tests/test_c8_b2.sh — Ledger test uses pins A6.
16. tests/test_c8_b2.sh — Control: the previous pins (02 of build 2) are refused by the A6 launcher.
17. tests/test_c8_b2.sh — Overwrite refusal is tested on a guard file in the A6 reviews folder.
18. tests/test_c8_b2.sh — The rel3 proof of the identical judge (sha c3757935) stays in the build-2 folder.
19. tests/test_c8_b2.sh — A6 test added.
20. tests/a6_apply_order.py — New test (A6).

## Построчно

### executor/supervisor.py

```diff
--- /work/c8_judge_r2e_20261109/executor/supervisor.py	2026-11-09 16:58:55.893777457 +0400
+++ executor/supervisor.py	2026-11-10 01:25:27.459348639 +0400
@@ -29,7 +29,7 @@
 from bumblebee.srv import SetParam
 from ros_raw_bridge import RosRawBridge,PymavlinkCodec
 from fresh_param_adapter import FreshParamAdapter
-from sitl_profile_closure_candidate import closure_names,profile_values
+from sitl_profile_closure_candidate import closure_names,profile_values,restore_order  # A6: restore_order for the apply order
 from pymavlink import mavutil
 from mavros import mavlink as convert
 
@@ -302,7 +302,11 @@
     def _prepare_once():
         r=call(Trigger,'/vpe_fix/prepare_profile',Trigger.Request());return r.success,r.message
     prepare_when_wrapper_ready(_prepare_once,ready_deadline,2.0,ready_px4)
-    for name,value in profile_values().items():
+    profile=profile_values()
+    # A6 (T32, 10.11): parents before children (MPC_XY_VEL_MAX before MPC_XY_CRUISE). In dict order PX4 committed
+    # MPC_XY_CRUISE 0.3 down to the old MPC_XY_VEL_MAX 0.25 of airframe 4061 (MulticopterPositionControl.cpp:215-217).
+    for name in restore_order(tuple(profile)):
+        value=profile[name]
         req=SetParam.Request();req.param_id=name;req.ptype=1;req.value=value;req.ttl_sec=0.;req.persistent=False
         assert call(SetParam,'/vpe_fix/set_param',req).success,'Apply failed '+name
     report['independent_applied']=read_all()
```

### executor/run.sh

```diff
--- /work/c8_judge_r2e_20261109/executor/run.sh	2026-11-09 16:58:55.893559322 +0400
+++ executor/run.sh	2026-11-10 01:25:27.459450852 +0400
@@ -4,7 +4,7 @@
 TAG=${TAG:?}; SCENARIO=${SCENARIO:-land}
 [[ "$TAG" =~ ^INT_flight_[a-zA-Z0-9_]+$ ]]
 case "$SCENARIO" in preflight|land|kill|freeze|mavros_restart|pilot|cancel_before|cancel|ack_cancel|heartbeat|guard_hold|cleanup_hold) ;; *) exit 2;; esac
-OWN=/work/c8_judge_r2e_20261109/executor  # c8-r2e-b: this copy (c8 executor_r2e + revision b, ../DIFF_exec_b.md)
+OWN=/work/c8_judge_r2e_a6_20261110/executor  # A6: this copy (revision b + apply order, ../DIFF_a6.md)
 export BB_COMBINED_ROOT=${BB_COMBINED_ROOT:?reviewed combined candidate required}
 # c8: target set as parameters; no default in run.sh (launcher/host_run_wsl_c8_r2e.sh passes them; defaults are there)
 export C8_AIRFRAME=${C8_AIRFRAME:?} C8_PX4_ETC=${C8_PX4_ETC:?} C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:?} C8_PRODUCT_SRC=${C8_PRODUCT_SRC:?}
```

### launcher/host_run_wsl_c8_r2e_b.sh

```diff
--- /work/c8_judge_r2e_20261109/launcher/host_run_wsl_c8_r2e_b.sh	2026-11-09 16:58:55.894490195 +0400
+++ launcher/host_run_wsl_c8_r2e_b.sh	2026-11-10 01:25:27.459587218 +0400
@@ -1,6 +1,6 @@
 #!/bin/bash
 # ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY). К дрону не подключается.
-# host_run_wsl_c8_r2e_b.sh = launcher v32-c8-r2e-b (Claude, T28 09.11.2026): copy of c8_executor_20261109/launcher/host_run_wsl_c8_r2e.sh
+# host_run_wsl_c8_r2e_b.sh = launcher v33-c8-r2e-a6 (A6, T32 10.11.2026: runner = c8_judge_r2e_a6_20261110/executor; was v32-c8-r2e-b) (Claude, T28 09.11.2026): copy of c8_executor_20261109/launcher/host_run_wsl_c8_r2e.sh
 #   for the C8 executor revision b /work/c8_judge_r2e_20261109/executor. Changes: ../DIFF_exec_b.md (v31 changes: c8_executor_20261109/DIFF_r2e.md).
 #   bash host_run_wsl_c8_r2e_b.sh TAG SCENARIO [VIEW]      (no TRIAL argument: the runner is fixed; TRIAL lines below are v29 history)
 #   env (c8): C8_START_ORDER=gz_first|px4_first REQUIRED (no default); C8_AIRFRAME C8_PX4_ETC C8_PRODUCT_INSTALL C8_PRODUCT_SRC
@@ -26,14 +26,14 @@
 # requested renderer) AND the executor's own gates AND the independent verifier pass.
 # Never deletes anything; stops only exact process groups it started.
 set -u
-echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v32-c8-r2e-b; no real drone, no ssh"
+echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6; no real drone, no ssh"
 TAG=${1:?TAG}; SCENARIO=${2:?SCENARIO}; VIEW=${3:-paused}; TRIAL=c8
-[ $# -le 3 ] || { echo "host_run_wsl_c8: REFUSED: no TRIAL argument in v32-c8-r2e-b (the runner is fixed)" >&2; exit 2; }
+[ $# -le 3 ] || { echo "host_run_wsl_c8: REFUSED: no TRIAL argument in v33-c8-r2e-a6 (the runner is fixed)" >&2; exit 2; }
 RENDER=${RENDER:-hr1}; KEEP_AWAKE=${KEEP_AWAKE:-0}
 HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
 WORK=/work
 INTEG=$WORK/parallel_work/20261015/integration
-RUNNER=$WORK/c8_judge_r2e_20261109/executor/run.sh   # c8-r2e-b: the only runner of this launcher
+RUNNER=$WORK/c8_judge_r2e_a6_20261110/executor/run.sh   # A6: the only runner of this launcher
 OUT=$WORK/sim/runs/$TAG
 SIDE=$WORK/sim/runs/$TAG.launcher
 CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
@@ -147,7 +147,7 @@
     if extra: P.append('unexpected entries in the candidate: ' + ', '.join(sorted(extra)[:20]))
     rf = pins.get('repo_files')
     if not isinstance(rf, dict) or not rf: P.append('pins have no repo_files object'); rf = {}
-    runner = 'c8_judge_r2e_20261109/executor/run.sh'  # c8-r2e-b: the fixed runner
+    runner = 'c8_judge_r2e_a6_20261110/executor/run.sh'  # A6: the fixed runner
     if runner not in rf: P.append('pins do not cover TRIAL %s (%s not pinned)' % (trial, runner))
     # c8: every file named by a C8_* parameter must be pinned in repo_files (another target set = new pins = new ACCEPTED_PINS)
     for key in ('C8_AF_FILE', 'C8_MODEL_SDF', 'C8_FLOW_PLUGIN', 'C8_DRONE_PY'):
@@ -206,7 +206,7 @@
 if [ "$RENDER" != sw ] && [ "${#GPU_VARS[@]}" = 0 ]; then die "gpu_env.sh gives no variables: hr1/hr0 would silently render on the CPU"; fi
 # atomic per-TAG lock: a second launcher with the same TAG cannot pass this line
 mkdir "$SIDE" 2>/dev/null || die "could not create $SIDE (TAG in use by another launcher?)"
-echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v32-c8-r2e-b" > "$SIDE/launcher.log"
+echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v33-c8-r2e-a6" > "$SIDE/launcher.log"
 echo "host_run_wsl: TAG=$TAG SCENARIO=$SCENARIO VIEW=$VIEW TRIAL=$TRIAL RENDER=$RENDER KEEP_AWAKE=$KEEP_AWAKE CANCEL_OFFSET_MS=${CANCEL_OFFSET:-default}" | tee -a "$SIDE/launcher.log"
 echo "host_run_wsl_c8: C8_AIRFRAME=$C8_AIRFRAME C8_START_ORDER=$C8_START_ORDER C8_PX4_ETC=$C8_PX4_ETC C8_PRODUCT_INSTALL=$C8_PRODUCT_INSTALL C8_PRODUCT_SRC=$C8_PRODUCT_SRC C8_MAVROS_INSTALL=$C8_MAVROS_INSTALL C8_MODEL=$C8_MODEL C8_FLOW_PLUGIN=$C8_FLOW_PLUGIN" | tee -a "$SIDE/launcher.log"
 echo "host_run_wsl: candidate $COMBINED matches frozen pins $PINS" | tee -a "$SIDE/launcher.log"
@@ -348,7 +348,7 @@
 out_unchanged = len(oh) == 2 and oh[0] == oh[1]
 cand = js('candidate_check.json')
 candidate_ok = bool(cand and cand.get('ok') is True)
-doc = {'tag': tag, 'scenario': scen, 'view': view, 'trial': 'c8_judge_r2e_20261109/executor', 'combined_root': combined,
+doc = {'tag': tag, 'scenario': scen, 'view': view, 'trial': 'c8_judge_r2e_a6_20261110/executor', 'combined_root': combined,
        'runner_exit': int(rc), 'host_start': start, 'host_end': end, 'host_start_utc': s_utc, 'host_end_utc': e_utc,
        'host_start_epoch': int(s_ep), 'host_end_epoch': int(e_ep),
        'power_before': None, 'power_after': None, 'low_power_mode_before': None, 'low_power_mode_after': None,
```

### tests/test_c8_b2.sh

```diff
--- /work/c8_judge_r2e_20261109/tests/test_c8_b2.sh	2026-11-09 16:59:29.932465190 +0400
+++ tests/test_c8_b2.sh	2026-11-10 01:25:27.459879055 +0400
@@ -2,7 +2,7 @@
 # T28 static tests (no Gazebo, no PX4, no node started). Run from anywhere: bash tests/test_c8_b.sh
 # Writes nothing outside tests/out_<time>/ of this folder (no bytecode: PYTHONDONTWRITEBYTECODE=1).
 set -uo pipefail
-D=/work/c8_judge_r2e_20261109
+D=/work/c8_judge_r2e_a6_20261110
 export PYTHONDONTWRITEBYTECODE=1
 O=$D/tests/out_$(date +%H%M%S); mkdir -p "$O"
 PASS=0; FAIL=0
@@ -26,7 +26,7 @@
   C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf \
   C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
   C8_DRONE_PY=/work/fixed_image_r2e_20261109/src/bumblebee/examples/drone.py \
-  python3 -I $O/precheck.py $D/candidate $D/pins/frozen_inputs_c8_r2e_b_02.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
+  python3 -I $O/precheck.py $D/candidate $D/pins/frozen_inputs_c8_r2e_a6_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
 # control: the old v31 pins are not accepted by this launcher
 t launcher_pins_refuses_old bash -c "! env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl \
   C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
@@ -64,7 +64,7 @@
 # 5. D7: the VPE opt-in refuses a wrong / missing airframe and passes 4061 up to the MAVROS route check
 cat > $O/optin_case.py <<'PY'
 import json, sys, runpy
-D = '/work/c8_judge_r2e_20261109'
+D = '/work/c8_judge_r2e_a6_20261110'
 audit, o = json.loads(sys.argv[1]), sys.argv[2]
 cfg = o + '/fake_mavros.yaml'; open(cfg, 'w').write('fcu_url: wrong\n')
 audit.update(sim_gz_en_1=True, all_fcu_paths_guarded=True, no_hardware=True, raw_topics_verified=True, exclusive_profile_writer=True,
@@ -120,15 +120,15 @@
 J="/work/analysis/layout/.venv/bin/python -B -I $D/verify_flight_c8.py --run /work/sim/runs/INT_flight_pc_rel3_kill_01 --expected-manifest /work/parallel_work/20261015/integration/combined_13/manifest.json --frozen-pins /work/parallel_work/20261015/integration/flight_verification_03/frozen_inputs_32.json"
 t judge_needs_identity bash -c "$J --out $D/reviews/x_noid.json > $O/noid.txt 2>&1; rc=\$?; [ \$rc = 2 ] && grep -q 'the following arguments are required: --identity' $O/noid.txt && [ ! -e $D/reviews/x_noid.json ]"
 # the ledger run.sh will write equals the pins' ledger_files, keyed as the judge keys it
-t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_b_02.json
+t ledger_equals_pins python3 -B -I $D/tests/ledger_check.py $D/pins/frozen_inputs_c8_r2e_a6_01.json
 t judge_refuses_unknown_identity bash -c "$J --out $D/reviews/x_bad.json --identity c8_4030 2>&1 | grep -q 'invalid choice'; [ ! -e $D/reviews/x_bad.json ]"
 t judge_refuses_out_outside bash -c "$J --out $O/x.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'; [ ! -e $O/x.json ]"
-t judge_refuses_overwrite bash -c "$J --out $D/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'"
+t judge_refuses_overwrite bash -c "$J --out $D/reviews/OVERWRITE_GUARD.json --identity rel3_4030 2>&1 | grep -q 'only inside c8_judge_r2e_20261109/reviews'"
 # 9. judge copy: the identity takes effect and changes only the identity / profile-name checks (rel3 kill run, 4030)
 mkdir -p $D/reviews/tests_$(basename $O)
 t judge_c8_identity_effect bash -c "$J --identity c8_4061 --out $D/reviews/tests_$(basename $O)/kill_as_c8_4061.json >/dev/null; python3 -B -I -c \"
 import json
-a=json.load(open('$D/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json'))
+a=json.load(open('/work/c8_judge_r2e_20261109/reviews/rel3_proof_v2/INT_flight_pc_rel3_kill_01_review.json'))
 b=json.load(open('$D/reviews/tests_$(basename $O)/kill_as_c8_4061.json'))
 la,lb=a['legacy_full_report']['checks'],b['legacy_full_report']['checks']
 diff=sorted(k for k in set(la)|set(lb) if la.get(k,{}).get('status')!=lb.get(k,{}).get('status'))
@@ -183,7 +183,10 @@
 t launcher_refuses_pins_01 bash -c "! env C8_AF_FILE=/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4061_gz_bumblebee_candidate_4060_disarm_rcl_obl \
   C8_MODEL_SDF=/work/goal_t22_flow_20261109/model_v1/bumblebee/model.sdf C8_FLOW_PLUGIN=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so \
   C8_DRONE_PY=/work/fixed_image_r2e_20261109/src/bumblebee/examples/drone.py \
-  python3 -I $O/precheck.py $D/candidate $D/_aside_build1/pins/frozen_inputs_c8_r2e_b_01.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
+  python3 -I $O/precheck.py $D/candidate /work/c8_judge_r2e_20261109/pins/frozen_inputs_c8_r2e_b_02.json c8 /work $D/launcher/ACCEPTED_PINS_b.txt"
 
+# A6: apply order on the 4061 baseline (candidate KnownCapsModel = the PX4 committed clamps): new order reaches every
+# profile value; the old dict order reproduces the run failure (MPC_XY_CRUISE 0.25); the restore returns the baseline.
+t a6_apply_order python3 -B -I $D/tests/a6_apply_order.py
 echo "RESULT pass=$PASS fail=$FAIL (logs $O)"
 [ "$FAIL" = 0 ]
```

### tests/d1_check.py

```diff
--- /work/c8_judge_r2e_20261109/tests/d1_check.py	2026-11-09 16:58:55.837684548 +0400
+++ tests/d1_check.py	2026-11-10 01:25:27.459697409 +0400
@@ -13,7 +13,7 @@
 
 from pyulog import ULog
 
-SETUP = Path('/work/c8_judge_r2e_20261109/executor/sitl_setup.py')
+SETUP = Path('/work/c8_judge_r2e_a6_20261110/executor/sitl_setup.py')
 src = SETUP.read_text().splitlines(True)
 a = next(i for i, l in enumerate(src) if l.strip().startswith("params = json.loads(Path('/work/sim/ros_stack/rc_real_params.json')"))
 b = next(i for i, l in enumerate(src) if "report['kept_airframe_values']" in l)
```

### tests/ledger_check.py

```diff
--- /work/c8_judge_r2e_20261109/tests/ledger_check.py	2026-11-09 16:58:55.839372254 +0400
+++ tests/ledger_check.py	2026-11-10 01:25:27.459729260 +0400
@@ -9,7 +9,7 @@
 import sys
 from pathlib import Path
 
-D = Path('/work/c8_judge_r2e_20261109')
+D = Path('/work/c8_judge_r2e_a6_20261110')
 LINE = ('sha256sum "$OWN"/*.py "$OWN/run.sh" "$CAND"/*.py "$CAND"/*.json "$BB_COMBINED_ROOT/vision/aruco_detect.py" '
         '"$C8_PRODUCT_INSTALL/bumblebee/lib/bumblebee/simple_offboard" "$C8_PRODUCT_SRC/src/python/setpoint_freshness.py" '
         '"$OUT/drone.py" > "$OUT/flight_source.sha256"')
```

## Без изменений (байт в байт)
- verify_flight_c8.py
- legacy/verify_package1b_gates_c8.py
- expect/flight_real_params_4061.json
- expect/rc_real_params_4061.json
- candidate/ (весь)
- executor/MAVROS_BP02_SHA256SUMS.txt
- executor/PRODUCT_SHA256SUMS.txt
- executor/RTF_MIN.md
- executor/cleanup_land.py
- executor/flight.launch.py
- executor/gate.py
- executor/package1b_gate.original.py
- executor/preflight_tools_sha256.json
- executor/px4_source_evidence/
- executor/rc_emulator.py
- executor/rtf_audit_journal.json
- executor/run_sim.snapshot.sh
- executor/s4_oracle.py
- executor/sitl_setup.original.py
- executor/sitl_setup.py
- executor/start_mavros_bp02.py
- executor/tests/
- executor/vpe_diagnostic_entry.py
- executor/vpe_gate_diagnostic_p1.py
