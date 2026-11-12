#!/bin/bash
# run_t52.sh (Claude «Симулятор», 11.11, T52 chat 1). CHECK, NOT SCORED. ТОЛЬКО СИМУЛЯТОР. One run at a time.
# Final r2h (r2hf) + vision 12 Hz. New = launcher 7k, AF 4074, model_v2 (reference dimensions); base = launcher 7k, AF 4070, model_v1 (as s11).
#   t52_c5_01   new: flight.py           -> c5 r5, t49_c5_metrics.py, t52_checks.py (standing values)
#   t52_c6_01   new: hover r6            -> c6 r5 (information), t52_checks.py
#   t52_yaw_01  new: t52_hover_yaw.py    -> t52_checks.py (innovations hover / turn)
#   t52_yawbase_01 base (4070 v2 + model_v1): t52_hover_yaw.py -> t52_checks.py (to compare signs)
# Params: the launcher's parity (sim_only_4074.json has variant 4074) — its UNEXPLAINED line goes into the run note. No stop on FAIL. Stops on setup/launcher failure, RTF gap, disk.
set -u
H=/work/t52_model_ref_20261111; LOG=$H/RUN_LOG.md; S=/work/goal_step5b_20261109; L=$S/run_scenario7k.sh
note() { echo "- $(date -Iseconds) $*" | tee -a "$LOG"; }
IMG=/work/fixed_image_r2h_20261110; HV=/work/c6_hover_script_r6_20261110/hover_marker0.py; EX=$IMG/src/bumblebee/examples/flight
YAW=$S/scenarios/t52_hover_yaw.py; E5=/work/goal_evals_r5_20261110; PY=$HOME/px4-venv/bin/python3; SER=/work/goal_series_r2g_20261110
T49=/work/t49_sensor_pos_probe_20261111
check() {
  (cd $H && sha256sum -c --quiet SHA256SUMS.txt) || { note "STOP: t52 sums"; exit 4; }
  (cd $IMG && sha256sum -c --quiet SHA256SUMS) || { note "STOP: r2h files"; exit 4; }
  cmp -s $H/run_scenario7k.sh.new $L || { note "STOP: installed 7k differs"; exit 4; }
  cmp -s $H/af/4074_gz_bumblebee_t52_ref_dims $S/px4_etc/init.d-posix/airframes/4074_gz_bumblebee_t52_ref_dims || { note "STOP: 4074 differs"; exit 4; }
  cmp -s $H/scenarios/t52_hover_yaw.py $YAW || { note "STOP: yaw scenario copy differs"; exit 4; }
  [ "$(sha256sum < $S/px4_etc/init.d-posix/airframes/4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50 | cut -c1-8)" = 0224deec ] || { note "STOP: 4070 v2 changed"; exit 4; }
  (cd $E5 && sha256sum -c --quiet SHA256SUMS.txt) || { note "STOP: evaluators r5 changed"; exit 4; }
}
cd $S
STEPS=("t52_c5_01 4074 v2 c5" "t52_c6_01 4074 v2 c6" "t52_yaw_01 4074 v2 yaw" "t52_yawbase_01 4070 v1 yaw")
for st in "${STEPS[@]}"; do
  set -- $st; TAG=$1; AF=$2; MV=$3; K=$4; RUN=$S/runs/$TAG
  check
  [ -e $RUN ] && { note "STOP: $TAG exists"; exit 4; }
  FREE=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d ' '); [ "${FREE:-0}" -ge 8 ] || { note "ПАУЗА: диск ${FREE} ГБ"; exit 3; }
  if [ $MV = v2 ]; then MOD=(--model $H/models/model_v2/bumblebee); else MOD=(); fi
  case $K in
    c5)  ARGS=(flight.py --image r2hf --vision-max-hz 12) ;;
    c6)  ARGS=("$HV" --image r2hf --vision-max-hz 12 --trial-map-file) ;;
    yaw) ARGS=("$YAW" --image r2hf --vision-max-hz 12 --trial-map-file) ;;
  esac
  note "$TAG start (CHECK, NOT scored, AF $AF, model $MV, $K)"
  bash $L "$TAG" $AF "${ARGS[@]}" "${MOD[@]}" > $H/$TAG.out 2>&1
  grep -q "^done $TAG" "$RUN/launcher.log" 2>/dev/null || { note "STOP: $TAG launcher did not finish ($(grep -h -m1 REFUSE $RUN/launcher.log $H/$TAG.out 2>/dev/null))"; exit 4; }
  GAP=$(python3 -I /work/goal_series_20261109/rtf_gap.py "$RUN"); [ "${GAP:-999}" -le 30 ] || { note "STOP: $TAG RTF gap ${GAP} s"; exit 4; }
  $PY -I -B $SER/imu_validity.py "$RUN" > "$RUN/imu_validity.out" 2>&1
  PAR=$(grep -h 'UNEXPLAINED' $RUN/parity.txt 2>/dev/null | tail -1)
  $PY -I -B $H/t52_checks.py "$RUN" > $H/$TAG.checks.json 2>&1
  case $K in
    c5) (cd $E5 && $PY -I -B -W ignore c5_eval.py "$RUN" --script $EX/flight.py > $H/$TAG.eval.txt 2>&1); RC=$?
        $PY -I -B $T49/t49_c5_metrics.py "$RUN" > $H/$TAG.metrics.json 2>&1 ;;
    c6) (cd $E5 && $PY -I -B -W ignore c6_eval.py "$RUN" --script $HV > $H/$TAG.eval.txt 2>&1); RC=$? ;;
    yaw) RC=-; echo "$(tail -1 $RUN/script.log)" > $H/$TAG.eval.txt ;;
  esac
  note "$TAG eval rc $RC ($(head -1 $H/$TAG.eval.txt | cut -c1-100)); parity: $PAR; $(tail -1 $RUN/imu_validity.out | cut -c1-50)"
  sleep 20
done
note "t52 done"
