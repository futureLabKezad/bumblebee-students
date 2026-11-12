#!/bin/bash
set -e; H=/work/t49_sensor_pos_probe_20261111; cd $H; bash -n run_t49.sh; python3 -I -m py_compile t49_params_check.py; rm -rf __pycache__
diff _aside/run_t49.sh.r1_reviewed run_t49.sh > DIFF_run_t49_r1_r2.txt || true; cat DIFF_run_t49_r1_r2.txt
python3 -I t49_params_check.py /work/goal_step5b_20261109/runs/s11_c5_01 B || echo "(expected mismatch on 4070: OF_POS_Z 0.03)"
cp SHA256SUMS.txt _aside/SHA256SUMS.txt.r1
sha256sum make_t49.py af/* run_scenario7j.sh.new t49_phases.py t49_c5_metrics.py run_t49.sh DIFF_7h_7j.txt DIFF_t45_t49_phases.txt build.sh rebuild.sh install.sh REVIEW_t49.md t49_params_check.py DIFF_run_t49_r1_r2.txt > SHA256SUMS.txt; sha256sum -c --quiet SHA256SUMS.txt && echo SUMS_OK
grep -q "T49" /work/REVIEW_LOCK.txt && mv -n /work/REVIEW_LOCK.txt /work/_aside_locks_20261110/REVIEW_LOCK_released_$(date +%H%M%S)_t49.txt && echo LOCK_RELEASED
sed -i "s|^task: .*|task: НЕ ЗАЧЁТ: T49 места датчиков, наборы 4072/4073 (run_t49.sh, 12 прогонов), 11.11 13:2x|" /work/SIM_LOCK.txt
