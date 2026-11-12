#!/bin/bash
set -e; D=/work/t45_descent_20261111; T=/work/goal_step5b_20261109/scenarios/t45_descent_after_floor.py
[ -e $T ] && { echo exists; exit 1; }
cp $D/descent_after_floor.py $T; cmp $D/descent_after_floor.py $T
cd $D; mkdir -p _aside; cp run_t45.sh _aside/run_t45.sh.r1_script_path; cp SHA256SUMS.txt _aside/SHA256SUMS.txt.r1
sed -i "s|if \[ \$K = desc \]; then SCR=\$D/descent_after_floor.py; else SCR=\$H; fi|if [ \$K = desc ]; then SCR=$T; else SCR=\$H; fi   # r2: the launcher accepts only \$STEP5B/scenarios/*.py (copy, cmp-checked)|" run_t45.sh
grep -n "SCR=" run_t45.sh
sed -i "s|  \[ \"\$(sha256sum < \$H \| cut -c1-16)\" = a11b195ce1507607 \] \|\| { note \"STOP: hover r6 changed\"; exit 4; }|&\n  cmp -s \$D/descent_after_floor.py $T \|\| { note \"STOP: scenarios copy differs\"; exit 4; }|" run_t45.sh
grep -n "cmp -s" run_t45.sh; bash -n run_t45.sh
sha256sum make_descent.py descent_after_floor.py DIFF_r6_descent.txt run_t45.sh t45_table.py > SHA256SUMS.txt; mv RUN_LOG.md _aside/RUN_LOG.md.r1_refused
