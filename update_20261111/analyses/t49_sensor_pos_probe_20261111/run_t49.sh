#!/bin/bash
# run_t49.sh (Claude «Симулятор», 11.11, T49 chat 1). PROBE, NOT SCORED. ТОЛЬКО СИМУЛЯТОР. One run at a time.
# Final r2h (r2hf) + launcher 7j (= 7h + AF 4072/4073; script use_sim_time as 7g) + 12 Hz. Per variant (A = AF 4072, B = AF 4073):
#   flight.py x2 (tags t49A_c5_NN) -> evaluator c5 r5 + t49_c5_metrics.py;
#   С8 flow x3 (t49A_flow_NN; hover r6 + floor_near_off at the 10th «[HOVER] t=», inject r4b) -> c8_new_eval r2 --check flow;
#   hover r6 x1 (t49A_c6_01) -> c6 r5 (information).
# No stop on FAIL (probe). Stops on setup/launcher failure, RTF gap > 30 s, disk < 8 GB. Usage: bash run_t49.sh [A B]
set -u
H=/work/t49_sensor_pos_probe_20261111; LOG=$H/RUN_LOG.md; S=/work/goal_step5b_20261109; L=$S/run_scenario7j.sh
note() { echo "- $(date -Iseconds) $*" | tee -a "$LOG"; }
IMG=/work/fixed_image_r2h_20261110; HV=/work/c6_hover_script_r6_20261110/hover_marker0.py; EX=$IMG/src/bumblebee/examples/flight
E5=/work/goal_evals_r5_20261110; E8=/work/c8_new_checks_20261109/c8_new_eval.py; PY=$HOME/px4-venv/bin/python3; SER=/work/goal_series_r2g_20261110
check() {
  (cd $H && sha256sum -c --quiet SHA256SUMS.txt) || { note "STOP: t49 sums"; exit 4; }
  (cd $IMG && sha256sum -c --quiet SHA256SUMS) || { note "STOP: r2h files"; exit 4; }
  [ "$(sha256sum < /work/c8_new_checks_20261109/c8_inject.py | cut -c1-8)" = 05fa4bf9 ] || { note "STOP: inject not r4b"; exit 4; }
  [ "$(sha256sum < $HV | cut -c1-16)" = a11b195ce1507607 ] || { note "STOP: hover r6 changed"; exit 4; }
  [ "$(sha256sum < $E5/c6_eval.py | cut -c1-8)" = 7b635222 ] || { note "STOP: c6_eval not r5"; exit 4; }
  [ "$(sha256sum < $S/px4_etc/init.d-posix/airframes/4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50 | cut -c1-8)" = 0224deec ] || { note "STOP: 4070 v2 changed"; exit 4; }   # r2 (F2)
  (cd $E5 && sha256sum -c --quiet SHA256SUMS.txt) || { note "STOP: evaluators r5 changed"; exit 4; }   # r2 (F2)
  for f in $H/af/*; do cmp -s $f $S/px4_etc/init.d-posix/airframes/$(basename $f) || { note "STOP: installed airframe differs: $(basename $f)"; exit 4; }; done
  cmp -s $H/run_scenario7j.sh.new $L || { note "STOP: installed 7j differs"; exit 4; }
}
cd $S
VARS=("$@"); [ ${#VARS[@]} -gt 0 ] || VARS=(A B)
for V in "${VARS[@]}"; do
  case $V in A) AF=4072 ;; B) AF=4073 ;; *) note "unknown variant $V"; exit 4 ;; esac
  for st in "c5_01 c5" "c5_02 c5" "flow_01 flow" "flow_02 flow" "flow_03 flow" "c6_01 c6"; do
    set -- $st; TAG=t49${V}_$1; K=$2; RUN=$S/runs/$TAG
    check
    [ -e $RUN ] && { note "STOP: $TAG exists"; exit 4; }
    FREE=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d ' '); [ "${FREE:-0}" -ge 8 ] || { note "ПАУЗА: диск ${FREE} ГБ"; exit 3; }
    case $K in
      c5)   ARGS=(flight.py --image r2hf --vision-max-hz 12) ;;
      flow) ARGS=("$HV" --image r2hf --vision-max-hz 12 --trial-map-file --inject-on '[HOVER] t=' 10 floor_near_off --after-inject-s 30) ;;
      c6)   ARGS=("$HV" --image r2hf --vision-max-hz 12 --trial-map-file) ;;
    esac
    note "$TAG start (PROBE, NOT scored, variant $V AF $AF, $K)"
    bash $L "$TAG" $AF "${ARGS[@]}" > $H/$TAG.out 2>&1
    grep -q "^done $TAG" "$RUN/launcher.log" 2>/dev/null || { note "STOP: $TAG launcher did not finish ($(grep -h -m1 REFUSE $RUN/launcher.log $H/$TAG.out 2>/dev/null))"; exit 4; }
    GAP=$(python3 -I /work/goal_series_20261109/rtf_gap.py "$RUN"); [ "${GAP:-999}" -le 30 ] || { note "STOP: $TAG RTF gap ${GAP} s"; exit 4; }
    $PY -I -B $SER/imu_validity.py "$RUN" > "$RUN/imu_validity.out" 2>&1
    PRM=$($PY -I -B $H/t49_params_check.py "$RUN" $V 2>&1); PRC=$?   # r2 (review F1): params really in PX4
    note "$TAG $PRM"; [ $PRC = 0 ] || { note "STOP: $TAG variant params not in PX4 (rc $PRC)"; exit 4; }
    case $K in
      c5)   (cd $E5 && $PY -I -B -W ignore c5_eval.py "$RUN" --script $EX/flight.py > $H/$TAG.eval.txt 2>&1); RC=$?
            $PY -I -B $H/t49_c5_metrics.py "$RUN" > $H/$TAG.metrics.json 2>&1 ;;
      flow) $PY -I -B $E8 "$RUN" --check flow > $H/$TAG.eval.txt 2>&1; RC=$? ;;
      c6)   (cd $E5 && $PY -I -B -W ignore c6_eval.py "$RUN" --script $HV > $H/$TAG.eval.txt 2>&1); RC=$? ;;
    esac
    note "$TAG eval rc $RC ($(head -1 $H/$TAG.eval.txt | cut -c1-110)); $(grep -m1 -hE 'touchdown .*delay|drift:' $H/$TAG.eval.txt | cut -c1-90); $(tail -1 $RUN/imu_validity.out | cut -c1-50)"
    sleep 20
  done
done
note "t49 done"
