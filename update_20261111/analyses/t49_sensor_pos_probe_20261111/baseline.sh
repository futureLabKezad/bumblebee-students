#!/bin/bash
H=/work/t49_sensor_pos_probe_20261111; R=/work/goal_step5b_20261109/runs; PY=$HOME/px4-venv/bin/python3; cd $H
[ -e baseline_c5_metrics.jsonl ] || $PY -I -B t49_c5_metrics.py $(ls -d $R/s11_c5_??) > baseline_c5_metrics.jsonl 2>&1
[ -e baseline_phases.jsonl ] || $PY -B t49_phases.py baseline_phases.jsonl c8r2h_flow_01 c8r2h_flow_02 c8r2h_flow_03 ctl_r2h_flow_01 c8r2g_flow_02 c8r2g_flow_03 c8r2g_flow_04 > baseline_phases.out 2>&1
cat baseline_c5_metrics.jsonl | cut -c1-300; tail -3 baseline_phases.out; head -c 1500 baseline_phases.jsonl
