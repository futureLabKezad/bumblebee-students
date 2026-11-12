#!/usr/bin/env python3
"""make_t49.py (Claude «Симулятор», 11.11.2026; chat 1 T49). PROBE, NOT SCORED. Sensor position params (owner's 1:1 model:
rangefinder lens 0.183 m over the floor, flight controller ~0.049 m above the lens; flow on the same board).
Writes in this folder (open 'x'):
  af/4072_gz_bumblebee_t49a_rngpos005_ofpos005_minrng023 = 4070 v2 + EKF2_RNG_POS_Z 0.05, EKF2_OF_POS_Z 0.05, EKF2_MIN_RNG 0.23 (variant A)
  af/4073_gz_bumblebee_t49b_ofpos010                    = 4070 v2 + EKF2_OF_POS_Z 0.10 (variant B)
  run_scenario7j.sh.new = /work/goal_step5b_20261109/run_scenario7h.sh (12b60b08, not changed) + AIRFRAME 4072|4073 allowed;
                          edition text; 7j in the snapshot cp list and the versions sha list. Nothing else.
  t49_phases.py = /work/t45_flow_r2h_20261110/tools/t45_phases.py (not changed) with RUNS taken from the command line.
install_t49.sh copies af/* into /work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/ and 7j to $STEP5B (no overwrite)."""
import hashlib, os
H = '/work/t49_sensor_pos_probe_20261111'; S = '/work/goal_step5b_20261109'
sha8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
def wx(p, s, mode=None):
    with open(p, 'x', encoding='utf-8', newline='\n') as f:
        f.write(s)
    if mode:
        os.chmod(p, mode)
os.makedirs(os.path.join(H, 'af'), exist_ok=True)
BASE = '4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50'
base = open(os.path.join(S, 'px4_etc/init.d-posix/airframes', BASE), encoding='utf-8').read(); assert sha8(base) == '0224deec'
def af(num, name, title, params):
    body = ('#!/bin/sh\n#\n# @name Gazebo Bumblebee T49 probe %s (4070 v2 + %s)\n#\n# @type Quadrotor x\n#\n'
            '# Claude «Симулятор» 11.11.2026, T49 (chat 1): PROBE ONLY, not scored. Sensor positions from the owner\'s 1:1 model\n'
            '#   (Documents/Claude local/model_measure_20261111/ЗАМЕР_ПО_МОДЕЛИ_RU.md). Base 4070 v2 (0224deec) unchanged.\n#\n\n'
            '. ${R}etc/init.d-posix/airframes/%s\n\n' % (title, ', '.join('%s %s' % kv for kv in params), BASE)
            + ''.join('param set-default %s %s\n' % kv for kv in params))
    wx(os.path.join(H, 'af', '%d_%s' % (num, name)), body, 0o755); print(num, sha8(body))
af(4072, 'gz_bumblebee_t49a_rngpos005_ofpos005_minrng023', 'A «честные числа»',
   [('EKF2_RNG_POS_Z', '0.05'), ('EKF2_OF_POS_Z', '0.05'), ('EKF2_MIN_RNG', '0.23')])
af(4073, 'gz_bumblebee_t49b_ofpos010', 'B «одна настройка»', [('EKF2_OF_POS_Z', '0.10')])
h = open(os.path.join(S, 'run_scenario7h.sh'), encoding='utf-8').read(); assert sha8(h) == '12b60b08'
rep = [('case $AF in 4032|4034|4035|4036|4037|4038|4044|4045|4046|4047|4055|4056|4057|4058|4059|4060|4061|4070) ;;',
        'case $AF in 4032|4034|4035|4036|4037|4038|4044|4045|4046|4047|4055|4056|4057|4058|4059|4060|4061|4070|4072|4073) ;;'),
       ('echo "ТОЛЬКО СИМУЛЯТОР (ed.7h image_r2h_final;', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.7j af_4072_4073_t49; ed.7h image_r2h_final;'),
       ('$STEP5B/run_scenario7g.sh $STEP5B/run_scenario7h.sh ', '$STEP5B/run_scenario7g.sh $STEP5B/run_scenario7h.sh $STEP5B/run_scenario7j.sh '),
       ('run_scenario7g.sh run_scenario7h.sh ', 'run_scenario7g.sh run_scenario7h.sh run_scenario7j.sh ')]
for a, b in rep:
    assert h.count(a) == 1, a
    h = h.replace(a, b)
l = h.split('\n', 2)
h = l[0] + '\n' + l[1] + '\n' + '# Edition 7j (11.11, Claude, T49): ed.7h + AIRFRAME 4072|4073 (sensor-position probes, not scored). Maker: %s/make_t49.py\n' % H + l[2]
wx(os.path.join(H, 'run_scenario7j.sh.new'), h); print('7j', sha8(h))
t = open('/work/t45_flow_r2h_20261110/tools/t45_phases.py', encoding='utf-8').read(); print('t45_phases', sha8(t))
a = "RUNS = ['c8r2h_flow_01', 'c8r2h_flow_02', 'c8r2h_flow_03', 'ctl_r2h_flow_01', 'c8r2g_flow_02', 'c8r2g_flow_03', 'c8r2g_flow_04']"
assert t.count(a) == 1
t = t.replace(a, "RUNS = sys.argv[2:]   # t49_phases (11.11): runs from the command line; was the T45 list:\n# " + a)
t = t.replace('Usage: ~/px4-venv/bin/python3 -B t45_phases.py OUT.jsonl"""', 'Usage: ~/px4-venv/bin/python3 -B t49_phases.py OUT.jsonl RUN_TAG [...]"""', 1)
wx(os.path.join(H, 't49_phases.py'), t); print('t49_phases', sha8(t))
