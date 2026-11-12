# Исправленный образ r2 для Gazebo — 09.11.2026 (T16)

Сделал чат «Разборы и правки кода» по задаче чата 1. Решение по вопросу 6 владелец передал: «Решай сам». Чат 1 выбрал F1-б, F2-б, F4-а и обе правки примеров.
Только ПК, без симулятора. Install port-rc3 и r1 не тронуты.
Метки: **доказано** — факт или проверка; **скорее всего** — сильные признаки без контроля; **возможно** — догадка.

## Что это
- `src/bumblebee` = образ r1 (`/work/fixed_image_r1_20261109`) + 4 файла из `/work/image_bugs_q6_20261109`. Суммы q6 сверены перед копированием.
  - `src/python/aruco_detect.py` — F1: сигнал `/aruco_detect/wake` держит детектор включённым 5 с.
  - `examples/drone.py`:
    - F1: `check_aruco()` шлёт этот сигнал, пока ждёт метки;
    - F2: `set_aruco_map()` только сверяет карту, при отличии — отказ;
    - F4: выключение до ожидания потоков.
  - `examples/flight/flight.py` — взлёт на 0,8 м.
  - `examples/flight/flight_marker_loop.py` — точки 13/12/11 на x = −0,72, промежуточные −0,36.
- `DIFF_vs_r1.txt` — ровно 4 файла (доказано, `diff -ruN`).
- `install/` — новая сборка пакета bumblebee: только он, `--executor sequential`, `nice -n 19`, `MAKEFLAGS=-j2`, окружение `/opt/ros/jazzy`, как у port-rc3. Журнал — `notes/build.log`.
- `image_manifest_r2.tsv` — формат как у `image_manifest.tsv`, по сравнению с r1 изменены 4 строки.
- `MANIFEST_SHA256.txt` — все файлы `src`, `test`, `notes` и документы. `INSTALL_SHA256.txt` — `install/bumblebee/lib/bumblebee`.

## Ключи запускателя (правит чат «Симулятор»)
1. **`--examples DIR`** = `/work/fixed_image_r2_20261109/src/bumblebee`. Оттуда брать `EXAMPLES`, `SCRIPT_PATH` и список профиля (`run_scenario2.sh`:35, 64, 260).
2. **`--install DIR`** = `/work/fixed_image_r2_20261109/install`: `source $DIR/local_setup.bash` вместо port-rc3 (стр. 251). Нужно из-за F1: `aruco_detect.py` — узел, он ставится в install (`CMakeLists.txt`:140).
   - Остальные `source` — ws_sitl, MAVROS bp02 — без изменений.
3. **`SCRIPT_H` для flight.py = 0,8** (стр. 56; было 1,5). Для flight_marker 0,7 и loop 1,3 — без изменений.
4. **`MAP_FILE` для F2-б.** Теперь `set_aruco_map()` ничего не пишет, а сверяет карту с `drone.MAP_FILE`.
   - На стенде это карта, которую загрузил детектор: `/work/ws_sitl/install/aruco_pose/share/aruco_pose/map/map.txt` (sha 528b5adb — та же, что `map.input.txt`).
   - `trial_runner.py --trial-map-file` должен ставить `drone.MAP_FILE` на этот файл — только чтение, а не на выходной файл.
   - Пробный ключ `--trial-map-file` больше не нужен для записи. Нужен только для пути: на ПК нет `/home/lb`.
5. **`pins_check2.py`**: `--src /work/fixed_image_r2_20261109/src/bumblebee`, `--manifest /work/fixed_image_r2_20261109/image_manifest_r2.tsv`. Строки «install vs src» — против `--install`.
   - Ожидаемо одно известное отличие: `src/python/camera_fix.py` DIFFERS. Манифест содержит исправление камеры, которое ждёт замера нагрузки Pi на стенде, а в src его нет. Так было и в прогоне b01 (доказано, `pins.json`).
6. Пробный ключ `--trial-aruco-always` для r2 не нужен: F1-б будит детектор сам. Проверка — прогон 2 из `/work/image_bugs_q6_20261109/GAZEBO_RUNS.md`.

## Тесты (без ROS) — `notes/TEST_RESULTS.txt`
- Q6 — 17 из 17; прежние тесты drone.py — 87 из 87 (2 пропущены); проверка профиля — 16 из 16.
- Независимая проверка заготовок T15 идёт. Её обязательные правки внесу в r2, если будут.
