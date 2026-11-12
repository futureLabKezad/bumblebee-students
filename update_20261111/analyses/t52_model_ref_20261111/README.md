# T52 — модель Gazebo и набор настроек по эталону размеров (Claude «Симулятор», 11.11). Проверка НЕ зачёт.
Эталон: Documents\Claude local\model_measure_20261111\ЭТАЛОН_РАЗМЕРОВ_20EC.md. Принятое не менялось (новые файлы и номера).
- models/model_v2/bumblebee — модель зачёта (из model_v1 21d0ad76): imu (-0,059;-0,007;0,016), flow/lidar x 0,082, камера вниз (0,081;0;-0,034),
  роторы и motor_*_collision ±0,2262. models/model_v2b/bumblebee — то же из model_v1b (лидар на /c8/lidar_raw) — только для С8 «дальномер» (ретранслятор).
- af/4074_gz_bumblebee_t52_ref_dims — 4070 v2 + 10 настроек §3.1 (оси PX4); стоит в /work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/.
- sim_only_4074.json — sim_only_4070_v2.json + вариант 4074 (10 строк с причиной) — для сверки С2.
- Пускачи: 7k (= 7j + AF 4074 + sim_only_4074.json) и 7l (= 7k + образ r2j, высота 0,9 для инфо-оценок) в /work/goal_step5b_20261109/.
- scenarios/t52_hover_yaw.py — висение 20 с + поворот 90° и обратно (проверка знаков).
- Проверки: REVIEW_t52.md, REVIEW_7l.md (GO). Прогоны: RUN_LOG.md, t52_*.{checks,metrics}.json, *.eval.txt. Итог: T52_ИТОГ_20261111.md.
