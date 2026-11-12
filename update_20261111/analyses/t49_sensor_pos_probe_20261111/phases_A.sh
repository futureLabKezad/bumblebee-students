#!/bin/bash
cd /work/t49_sensor_pos_probe_20261111; [ -e t49A_phases.jsonl ] || $HOME/px4-venv/bin/python3 -B t49_phases.py t49A_phases.jsonl t49A_flow_01 > t49A_phases.out 2>&1; tail -2 t49A_phases.out; python3 -c "import json; d=json.loads(open(\"t49A_phases.jsonl\").readline()); print({k:d.get(k) for k in (\"drift_td\",\"blind_s\",\"vel_resets\")}); print(\"C vel_err_mean\", d[\"phaseC_flow_to_td\"][\"vel_err_mean\"])"
python3 -c "
import json
for l in open(\"baseline_phases.jsonl\"):
    d=json.loads(l); print(d[\"run\"], d[\"drift_td\"], [r[\"delta_vxy\"] for r in d[\"vel_resets\"]], d[\"phaseC_flow_to_td\"][\"vel_err_mean\"])"
