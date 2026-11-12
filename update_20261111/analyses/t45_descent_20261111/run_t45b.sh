#!/bin/bash
# run_t45b.sh (Claude 11.11) = run_t45.sh r2 with the descent script r2 (0.1 m steps) only, tags t45b_desc_NN. NOT SCORED. ТОЛЬКО СИМУЛЯТОР. One run at a time. ≤ 1 h simulator.
# Final r2h (r2hf) + 4070 v2 + 12 Hz, launcher 7h (script use_sim_time), inject r4b.
#  1) T45: descent_after_floor.py x2 (tags t45_desc_NN): hover 15 s, floor_near_off at the 10th «[HOVER] t=», slow descent 1.0 -> 0.2 m.
#  2) С8 flow x4 (tags ctl_r2hf_flow_NN): hover r6 + floor_near_off as run_c8n_r2h.sh, evaluator c8_new_eval r2 --check flow;
#     a FAIL does not stop (controls: how often drift > 1 m).
# Stops only on setup/launcher failure, RTF gap > 30 s, disk < 8 GB.
set -u
D=/work/t45_descent_20261111; LOG=$D/RUN_LOG.md; S=/work/goal_step5b_20261109; L=$S/run_scenario7h.sh
note() { echo "- $(date -Iseconds) $*" | tee -a "$LOG"; }
IMG=/work/fixed_image_r2h_20261110; H=/work/c6_hover_script_r6_20261110/hover_marker0.py; E8=/work/c8_new_checks_20261109/c8_new_eval.py
PY=$HOME/px4-venv/bin/python3; SER=/work/goal_series_r2g_20261110
check() {
  (cd $D && sha256sum -c --quiet SHA256SUMS.txt) || { note "STOP: t45 sums"; exit 4; }
  [ "$(sha256sum < $L | cut -c1-8)" = 12b60b08 ] || { note "STOP: 7h changed"; exit 4; }
  (cd $IMG && sha256sum -c --quiet SHA256SUMS) || { note "STOP: r2h files"; exit 4; }
  [ "$(sha256sum < /work/c8_new_checks_20261109/c8_inject.py | cut -c1-8)" = 05fa4bf9 ] || { note "STOP: inject not r4b"; exit 4; }
  [ "$(sha256sum < $H | cut -c1-16)" = a11b195ce1507607 ] || { note "STOP: hover r6 changed"; exit 4; }
  cmp -s $D/descent_after_floor_r2.py /work/goal_step5b_20261109/scenarios/t45_descent_after_floor_r2.py || { note "STOP: scenarios copy differs"; exit 4; }
}
cd $S
STEPS=("t45b_desc_01 desc" "t45b_desc_02 desc")
for st in "${STEPS[@]}"; do
  set -- $st; TAG=$1; K=$2; RUN=$S/runs/$TAG
  check
  [ -e $RUN ] && { note "STOP: $TAG exists"; exit 4; }
  FREE=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d ' '); [ "${FREE:-0}" -ge 8 ] || { note "ПАУЗА: диск ${FREE} ГБ"; exit 3; }
  if [ $K = desc ]; then SCR=/work/goal_step5b_20261109/scenarios/t45_descent_after_floor_r2.py; else SCR=$H; fi   # r2: the launcher accepts only $STEP5B/scenarios/*.py (copy, cmp-checked)
  note "$TAG start (NOT scored, $K, r2h-final+7h)"
  bash $L "$TAG" 4070 "$SCR" --image r2hf --vision-max-hz 12 --trial-map-file \
    --inject-on '[HOVER] t=' 10 floor_near_off --after-inject-s 30 > $D/$TAG.out 2>&1
  grep -q "^done $TAG" "$RUN/launcher.log" 2>/dev/null || { note "STOP: $TAG launcher did not finish ($(grep -h -m1 REFUSE $RUN/launcher.log $D/$TAG.out 2>/dev/null))"; exit 4; }
  GAP=$(python3 -I /work/goal_series_20261109/rtf_gap.py "$RUN"); [ "${GAP:-999}" -le 30 ] || { note "STOP: $TAG RTF gap ${GAP} s"; exit 4; }
  $PY -I -B $SER/imu_validity.py "$RUN" > "$RUN/imu_validity.out" 2>&1
  if [ $K = flow ]; then
    $PY -I -B $E8 "$RUN" --check flow > $D/$TAG.eval.txt 2>&1; RC=$?
    DR=$(grep -m1 'drift:' $D/$TAG.eval.txt | cut -c1-90)
    note "$TAG eval rc $RC ($(head -1 $D/$TAG.eval.txt | cut -c1-80)); $DR; $(tail -1 $RUN/imu_validity.out | cut -c1-60)"
  else
    note "$TAG done; script end: $(tail -2 $RUN/script.log | tr '\n' ' ' | cut -c1-160); $(tail -1 $RUN/imu_validity.out | cut -c1-60)"
  fi
  sleep 20
done
note "t45b done"
