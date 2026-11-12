#!/usr/bin/env python3
"""T45: per run (read-only) - (1) when vpe_fix stops publishing after LAND (ros.log 'publish=False', wall time mapped to
sim time with the injection record: RTF ~1), and the last 'published' line before it; (2) PX4 parameter differences between
the 7 runs (ULog initial parameters); (3) image of vpe_fix used (ros.log command line).
Usage: ~/px4-venv/bin/python3 -B t45_gate_params.py OUT.json"""
import glob, json, re, sys
from pyulog import ULog

RUNS = ['c8r2h_flow_01', 'c8r2h_flow_02', 'c8r2h_flow_03', 'ctl_r2h_flow_01', 'c8r2g_flow_02', 'c8r2g_flow_03', 'c8r2g_flow_04']
B = '/work/goal_step5b_20261109/runs/'
res, params = {}, {}
for run in RUNS:
    ev = json.load(open(B + run + '/c8_new_eval.json'))
    inj = [json.loads(l) for l in open(B + run + '/c8_inject.jsonl') if l.strip()][0]
    wall0, sim0 = inj['wall_before'], inj['sim_before']['sim_s']
    land_sim = ev['t_inj_sim_s'] + ev['landing_start_after_inj_s']
    rows, img = [], None
    for line in open(B + run + '/ros.log', errors='replace'):
        m = re.search(r'\[(\d{10}\.\d+)\] \[vpe_publisher\]: (.*)', line)
        if 'vpe_fix.py' in line and 'fixed_image_' in line and img is None:
            img = re.search(r'(fixed_image_[^/]+)', line).group(1)
        if not m:
            continue
        t = float(m.group(1)) - wall0 + sim0 - land_sim
        if -3 <= t <= 8 and 'VPE_GATE_DIAG' not in m.group(2):
            rows.append((round(t, 3), m.group(2)[:110]))
    off = [t for t, s in rows if 'publish=False' in s]
    res[run] = {'image': img, 'gate_off_after_land_s': off[0] if off else None, 'lines': rows}
    u = ULog(glob.glob(B + run + '/rootfs/log/*/' + ev['ulog'])[0])
    params[run] = u.initial_parameters
keys = sorted(set().union(*[set(p) for p in params.values()]))
diff = {k: {r: params[r].get(k) for r in RUNS} for k in keys if len({params[r].get(k) for r in RUNS}) > 1}
sel = {k: params[RUNS[0]].get(k) for k in ('EKF2_OF_QMIN', 'EKF2_OF_CTRL', 'EKF2_EV_CTRL', 'EKF2_HGT_REF', 'EKF2_NOAID_TOUT',
                                         'MPC_LAND_CRWL', 'MPC_LAND_SPEED', 'MPC_LAND_ALT3', 'EKF2_OF_GATE', 'EKF2_MIN_RNG',
                                         'SENS_FLOW_MINHGT', 'SENS_FLOW_MAXHGT', 'EKF2_OF_N_MIN', 'EKF2_OF_N_MAX', 'EKF2_OF_QMIN_GND')}
json.dump({'gate': res, 'param_diff': diff, 'params_run01': sel}, open(sys.argv[1], 'w'), indent=1)
for r in RUNS:
    print(r, res[r]['image'], 'gate off after LAND', res[r]['gate_off_after_land_s'])
print('param differences across runs:', {k: v for k, v in diff.items() if not k.startswith(('CAL_', 'SYS_'))})
print('selected:', sel)
