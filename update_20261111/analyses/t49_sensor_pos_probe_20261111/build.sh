#!/bin/bash
set -e; H=/work/t49_sensor_pos_probe_20261111; S=/work/goal_step5b_20261109; cd $H
python3 -I make_t49.py
bash -n run_scenario7j.sh.new; python3 -I -m py_compile t49_phases.py t49_c5_metrics.py; rm -rf __pycache__
diff -u $S/run_scenario7h.sh run_scenario7j.sh.new > DIFF_7h_7j.txt || true; diff -u /work/t45_flow_r2h_20261110/tools/t45_phases.py t49_phases.py > DIFF_t45_t49_phases.txt || true
grep "^[-+][^-+]" DIFF_7h_7j.txt | cut -c1-200; cat af/4072_* | tail -4; cat af/4073_* | tail -2
