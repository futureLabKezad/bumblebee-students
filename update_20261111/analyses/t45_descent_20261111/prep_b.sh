#!/bin/bash
set -e; D=/work/t45_descent_20261111; T=/work/goal_step5b_20261109/scenarios/t45_descent_after_floor_r2.py; cd $D
python3 -I make_descent_r2.py; python3 -I -m py_compile descent_after_floor_r2.py; rm -rf __pycache__
[ -e $T ] && { echo exists; exit 1; }; cp descent_after_floor_r2.py $T; cmp descent_after_floor_r2.py $T
bash -n run_t45b.sh
cp SHA256SUMS.txt _aside/SHA256SUMS.txt.r2
sha256sum make_descent.py descent_after_floor.py DIFF_r6_descent.txt run_t45.sh t45_table.py make_descent_r2.py descent_after_floor_r2.py run_t45b.sh > SHA256SUMS.txt; sha256sum -c --quiet SHA256SUMS.txt && echo OK
