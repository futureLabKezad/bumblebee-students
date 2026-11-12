#!/usr/bin/env python3
"""make_t52.py (Claude «Симулятор», 11.11.2026; chat 1 T52). Gazebo model and param set by the owner's 1:1 dimensions reference
(Documents/Claude local/model_measure_20261111/ЭТАЛОН_РАЗМЕРОВ_20EC.md; owner 11.11: «по этой модели поправь все остальное все размеры»).
Writes in this folder (open 'x' / refuse if exists); sources are NOT changed (sha asserted):
 models/model_v2/bumblebee   = /work/goal_t22_flow_20261109/model_v1/bumblebee (model.sdf 21d0ad76) with
     imu_sensor pose (0,0,0.0112) -> (-0.059,-0.007,0.016); flow_link + lidar_sensor_link (0.072,0.028,-0.034) -> (0.082,0.028,-0.034);
     main_camera_link (0.05,0,-0.07) -> (0.081,0,-0.034); rotor_0..3 links and motor_*_collision +-0.222739 -> +-0.2262. Nothing else.
 models/model_v2b/bumblebee  = /work/c8_range_model_20261109/model_v1b/bumblebee (lidar on /c8/lidar_raw, for С8 «дальномер») with the same.
 af/4074_gz_bumblebee_t52_ref_dims = 4070 v2 + EKF2_IMU_POS_X/Y/Z -0.059/0.007/-0.016, EKF2_RNG_POS_X/Y/Z 0.082/-0.028/0.034,
     EKF2_OF_POS_X/Y/Z 0.082/-0.028/0.034, EKF2_MIN_RNG 0.23 (PX4 axes: X fwd, Y right, Z down).
 sim_only_4074.json = /work/goal_af4070_20261110/sim_only_4070_v2.json + variant 4074 (= 4070 + these 10, each with its reason).
 run_scenario7k.sh.new = /work/goal_step5b_20261109/run_scenario7j.sh (ac97d212) + AIRFRAME 4074 + the parity / snapshot policy
     file sim_only_4074.json (it still holds 4070 etc. unchanged) + edition text + 7k in the snapshot cp / versions lists.
 scenarios/t52_hover_yaw.py = hover r6 (a11b195c) with HOVER_S 20 and, after the hover, yaw +90 deg and back over marker 0 (8 s watch
     each; drone.navigate_wait(..., yaw=..., frame_id='map'); position target unchanged). For the sign check of flow / range innovations."""
import hashlib, json, os, shutil
H = '/work/t52_model_ref_20261111'; S = '/work/goal_step5b_20261109'
sha8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
def wx(p, s, mode=None):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'x', encoding='utf-8', newline='\n') as f:
        f.write(s)
    if mode:
        os.chmod(p, mode)
def model(src_dir, out_dir, want8):
    s = open(os.path.join(src_dir, 'model.sdf'), encoding='utf-8').read(); assert sha8(s) == want8, (src_dir, sha8(s))
    rep = [('        <pose>0 0 0.0112 0 0 0</pose>', '        <pose>-0.059 -0.007 0.016 0 0 0</pose>', 1),
           ('<pose relative_to="base_link">0.072 0.028 -0.034 0 0 0</pose>', '<pose relative_to="base_link">0.082 0.028 -0.034 0 0 0</pose>', 1),
           ('<pose relative_to="base_link">0.072 0.028 -0.034 0 1.5708 0</pose>', '<pose relative_to="base_link">0.082 0.028 -0.034 0 1.5708 0</pose>', 1),
           ('<pose relative_to="base_link">0.05 0 -0.07 0 1.5708 0</pose>', '<pose relative_to="base_link">0.081 0 -0.034 0 1.5708 0</pose>', 1),
           ('0.222739', '0.2262', 16)]   # 8 poses (4 rotor links + 4 motor collisions), x and y each
    for a, b, n in rep:
        assert s.count(a) == n, (a, s.count(a))
        s = s.replace(a, b)
    assert not os.path.exists(out_dir)
    shutil.copytree(src_dir, out_dir)
    with open(os.path.join(out_dir, 'model.sdf'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(s)
    print(out_dir, sha8(s))
model('/work/goal_t22_flow_20261109/model_v1/bumblebee', os.path.join(H, 'models/model_v2/bumblebee'), '21d0ad76')
model('/work/c8_range_model_20261109/model_v1b/bumblebee', os.path.join(H, 'models/model_v2b/bumblebee'),
      sha8(open('/work/c8_range_model_20261109/model_v1b/bumblebee/model.sdf', encoding='utf-8').read()))
P = [('EKF2_IMU_POS_X', -0.059), ('EKF2_IMU_POS_Y', 0.007), ('EKF2_IMU_POS_Z', -0.016),
     ('EKF2_RNG_POS_X', 0.082), ('EKF2_RNG_POS_Y', -0.028), ('EKF2_RNG_POS_Z', 0.034),
     ('EKF2_OF_POS_X', 0.082), ('EKF2_OF_POS_Y', -0.028), ('EKF2_OF_POS_Z', 0.034), ('EKF2_MIN_RNG', 0.23)]
BASE = '4070_gz_bumblebee_final_4061_bat0_sdlog1_ofqmin50'
assert sha8(open(os.path.join(S, 'px4_etc/init.d-posix/airframes', BASE), encoding='utf-8').read()) == '0224deec'
af = ('#!/bin/sh\n#\n# @name Gazebo Bumblebee T52 reference dimensions (4070 v2 + sensor positions by the owner\'s 1:1 model)\n#\n'
      '# @type Quadrotor x\n#\n# Claude «Симулятор» 11.11.2026, T52 (chat 1; owner 11.11). Values: ЭТАЛОН_РАЗМЕРОВ_20EC.md §3.1 (PX4 axes).\n#\n\n'
      '. ${R}etc/init.d-posix/airframes/%s\n\n' % BASE + ''.join('param set-default %s %s\n' % (k, v) for k, v in P))
wx(os.path.join(H, 'af', '4074_gz_bumblebee_t52_ref_dims'), af, 0o755); print('4074', sha8(af))
so = open('/work/goal_af4070_20261110/sim_only_4070_v2.json', encoding='utf-8').read(); print('sim_only_4070_v2', sha8(so))
d = json.loads(so)
v = json.loads(json.dumps(d['variants']['4070']))
v['name'] = 't52_ref_dims_4070v2'
why = 'эталон размеров 20EC по модели владельца 1:1 (ЭТАЛОН_РАЗМЕРОВ_20EC.md §3.1); утверждено владельцем 11.11, реестр настроек; на дрон — только карточкой QGC владельца (T54)'
for k, x in P:
    v['changes'][k] = x
    v['reasons_ru'][k] = '%s = %s: %s' % (k, x, why)
v['note_ru'] = 'T52 (11.11): 4070 v2 + места датчиков и EKF2_MIN_RNG по эталону размеров. Для Gazebo вместе с моделью model_v2.'
d['variants']['4074'] = v
d['title'] += ' + 4074 (T52, эталон размеров)'
d['source_policy_t52'] = {'file': 'sim_only_4070_v2.json (a6b91c1c... as accepted)', 'note': 'copy + variant 4074; nothing else changed'}
wx(os.path.join(H, 'sim_only_4074.json'), json.dumps(d, ensure_ascii=False, indent=1))
j = open(os.path.join(S, 'run_scenario7j.sh'), encoding='utf-8').read(); assert sha8(j) == 'ac97d212'
SO = '%s/sim_only_4074.json' % H
rep = [('4060|4061|4070|4072|4073) ;;', '4060|4061|4070|4072|4073|4074) ;;'),
       ('[ -f /work/goal_af4070_20261110/sim_only_4070_v2.json ]', '[ -f /work/goal_af4070_20261110/sim_only_4070_v2.json ] && [ -f %s ]' % SO),
       ('cp /work/goal_af4070_20261110/sim_only_4070_v2.json "$RUN/snapshot/sim_only.json"', 'cp %s "$RUN/snapshot/sim_only.json"' % SO),
       ('echo "ТОЛЬКО СИМУЛЯТОР (ed.7j af_4072_4073_t49;', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.7k af_4074_t52 sim_only_4074; ed.7j af_4072_4073_t49;'),
       ('$STEP5B/run_scenario7h.sh $STEP5B/run_scenario7j.sh ', '$STEP5B/run_scenario7h.sh $STEP5B/run_scenario7j.sh $STEP5B/run_scenario7k.sh '),
       ('run_scenario7h.sh run_scenario7j.sh ', 'run_scenario7h.sh run_scenario7j.sh run_scenario7k.sh ')]
for a, b in rep:
    assert j.count(a) == 1, a
    j = j.replace(a, b)
l = j.split('\n', 2)
j = l[0] + '\n' + l[1] + '\n' + '# Edition 7k (11.11, Claude, T52): ed.7j + AIRFRAME 4074 + policy file %s. Maker: %s/make_t52.py\n' % (SO, H) + l[2]
wx(os.path.join(H, 'run_scenario7k.sh.new'), j); print('7k', sha8(j))
r6 = open('/work/c6_hover_script_r6_20261110/hover_marker0.py', encoding='utf-8').read(); assert r6.startswith(r6[:10]) and hashlib.sha256(r6.encode()).hexdigest().startswith('a11b195ce1507607')
rep = [('"""\nhover_marker0.py -- take off', '"""\nt52_hover_yaw.py (T52 sign check, Claude 11.11; from hover r6) -- STUDY ONLY: hover 20 s, yaw +90 deg and back.\nhover_marker0.py -- take off'),
       ('HOVER_S = 65.0 ', 'HOVER_S = 20.0   # T52: was 65.0;'),
       ('                held, reason = hold_over_marker0(HOVER_S)\n',
        '                held, reason = hold_over_marker0(HOVER_S)\n'
        '                for yaw_t, tag in ((math.pi / 2, \'[YAW90]\'), (0.0, \'[YAW0]\')):   # T52: yaw turn over marker 0, position target unchanged\n'
        '                    if reason is not None:\n'
        '                        break\n'
        '                    print(\'=== T52 %s yaw %.2f rad ===\' % (tag, yaw_t), flush=True)\n'
        '                    drone.navigate_wait(x=MARKER0_X, y=MARKER0_Y, z=hover_z, yaw=yaw_t, speed=FLY_SPEED, frame_id=\'map\', tolerance=FLY_TOL)\n'
        '                    _, reason, _ = watch(8.0, tag)\n')]
for a, b in rep:
    assert r6.count(a) == 1, a
    r6 = r6.replace(a, b)
wx(os.path.join(H, 'scenarios', 't52_hover_yaw.py'), r6); print('t52_hover_yaw', sha8(r6))
