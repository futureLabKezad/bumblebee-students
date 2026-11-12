#!/bin/bash
set -e; H=/work/t52_model_ref_20261111; S=/work/goal_step5b_20261109; cd $H
python3 -I make_7l.py; bash -n run_scenario7l.sh.new; bash -n run_t52b.sh
diff -u $S/run_scenario7k.sh run_scenario7l.sh.new > DIFF_7k_7l.txt || true; grep "^[-+][^-+]" DIFF_7k_7l.txt | cut -c1-220
[ -e $S/run_scenario7l.sh ] && { echo 7l exists; exit 1; }; cp -n run_scenario7l.sh.new $S/run_scenario7l.sh; chmod +x $S/run_scenario7l.sh; cmp run_scenario7l.sh.new $S/run_scenario7l.sh
cp SHA256SUMS.txt _aside/SHA256SUMS.txt.r1
sha256sum make_t52.py af/* sim_only_4074.json run_scenario7k.sh.new scenarios/t52_hover_yaw.py t52_checks.py run_t52.sh DIFF_7j_7k.txt DIFF_r6_yaw.txt MODELS_SHA256.txt REVIEW_t52.md make_7l.py run_scenario7l.sh.new DIFF_7k_7l.txt run_t52b.sh > SHA256SUMS.txt; sha256sum -c --quiet SHA256SUMS.txt && echo SUMS_OK
bash /work/goal_series_r2g_20261110/take_review_lock.sh "Симулятор (local_bc6f158c): пускач 7l (= 7k + r2j) и run_t52b.sh, 11.11 13:4x"
