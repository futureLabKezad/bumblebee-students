#!/bin/bash
cd /work/t45_descent_20261111; R=/work/goal_step5b_20261109/runs
$HOME/px4-venv/bin/python3 -I -B t45_table.py $R/t45_desc_01 $R/t45_desc_02 2>&1 | tee t45_table.txt
