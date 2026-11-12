#!/bin/bash
set -e; H=/work/t52_model_ref_20261111; S=/work/goal_step5b_20261109; AD=$S/px4_etc/init.d-posix/airframes; cd $H
bash -n run_t52.sh; python3 -I -m py_compile t52_checks.py; rm -rf __pycache__
b=4074_gz_bumblebee_t52_ref_dims; [ -e $AD/$b ] && { echo exists; exit 1; }; cp -n af/$b $AD/$b; cmp af/$b $AD/$b
[ -e $S/run_scenario7k.sh ] && { echo 7k exists; exit 1; }; cp -n run_scenario7k.sh.new $S/run_scenario7k.sh; chmod +x $S/run_scenario7k.sh; cmp run_scenario7k.sh.new $S/run_scenario7k.sh
[ -e $S/scenarios/t52_hover_yaw.py ] && { echo yaw exists; exit 1; }; cp -n scenarios/t52_hover_yaw.py $S/scenarios/; cmp scenarios/t52_hover_yaw.py $S/scenarios/t52_hover_yaw.py
diff -u /work/c6_hover_script_r6_20261110/hover_marker0.py scenarios/t52_hover_yaw.py > DIFF_r6_yaw.txt || true
python3 -I -c "import json;a=json.load(open(\"/work/goal_af4070_20261110/sim_only_4070_v2.json\"));b=json.load(open(\"sim_only_4074.json\"));print(\"variants\",sorted(b[\"variants\"]));print(\"4070 same:\",a[\"variants\"][\"4070\"]==b[\"variants\"][\"4070\"]);print(\"other keys same:\",all(a[k]==b[k] for k in a if k not in (\"variants\",\"title\")))"
find models -type f | sort | xargs sha256sum > MODELS_SHA256.txt
sha256sum make_t52.py af/* sim_only_4074.json run_scenario7k.sh.new scenarios/t52_hover_yaw.py t52_checks.py run_t52.sh DIFF_7j_7k.txt DIFF_r6_yaw.txt MODELS_SHA256.txt build.sh > SHA256SUMS.txt; sha256sum -c --quiet SHA256SUMS.txt && sha256sum -c --quiet MODELS_SHA256.txt && echo SUMS_OK
bash /work/goal_series_r2g_20261110/take_review_lock.sh "Симулятор (local_bc6f158c): T52 — модель v2/v2b, набор 4074, sim_only_4074, пускач 7k, сценарий yaw, 11.11 13:2x"
