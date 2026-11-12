# Исправленный образ r2 для Gazebo — 09.11.2026, редакция r2c (= r2b + F5)

Сделал чат «Разборы и правки кода» по задаче T19 чата 1. r2b (`/work/fixed_image_r2_20261109`) заморожен и не тронут.
Метки: **доказано** — факт или проверка; **скорее всего** — сильные признаки без контроля; **возможно** — догадка.

## r2c — что изменилось по сравнению с r2b
Меняется только `examples/drone.py` (r2b `d5afa9a9…` → r2c `ac823ae5…`). Прежние файлы — в `notes/prev_r2b/`, разница — `notes/DIFF_r2c_vs_r2b.txt` (+10 строк), скрипт правки — `tools/make_r2c.py`.
1. **F5, причина (доказано, `notes/F5_REPRO.txt`).** Примеры передают целое `0` в поля float32 запроса navigate: `fly_to(x=0, …)` (flight_marker.py:170/178/184) и `safe_land(x=0, y=0)` (flight_marker.py:187, flight_marker_loop.py:136).
   - В Jazzy проверка типов на стороне Python выключена по умолчанию (`ROS_PYTHON_CHECK_FIELDS`). Целое доходит до C-преобразователя rosidl, его `assert(PyFloat_Check)` роняет весь процесс, дрон остаётся в OFFBOARD без скрипта.
   - `numpy.float32` падает так же; `nan` и `numpy.float64` проходят. Ошибка старая: те же вызовы есть в r1.
2. **Правка.** `navigate()` приводит `x, y, z, yaw, speed` к `float()` перед записью в запрос (`_NAVIGATE_FLOAT_FIELDS`). `nan` остаётся `nan`. Остальные поля и логика не меняются.
3. Другие запросы drone.py с полями float уже приводят типы (`SetParam`) или не имеют их (`GetTelemetry`).
4. Тесты: `test/test_r2c_navigate_float.py` — int, numpy и nan в каждом поле; с настоящим rosidl каждый случай в своём процессе, контроль r2b падает (`notes/TEST_RESULTS.txt`).
5. `install/` — копия r2b без изменений (`INSTALL_SHA256.txt` сверен): `drone.py` — пример, в install его нет. Папок `build/` и `log/` в r2c нет.

## Ключи запускателя для r2c
- `--examples /work/fixed_image_r2c_20261109/src/bumblebee`, `--install /work/fixed_image_r2c_20261109/install`, `pins_check2.py --src …r2c…/src/bumblebee --manifest …r2c…/image_manifest_r2.tsv`. Остальное — как ниже.

---
# Ниже — README r2b без изменений, кроме путей в «Ключах запускателя»

# Исправленный образ r2 для Gazebo — 09.11.2026 (T16), редакция r2b

Сделал чат «Разборы и правки кода» по задаче чата 1. Решение по вопросу 6 владелец передал: «Решай сам». Чат 1 выбрал F1-б, F2-б, F4-а и обе правки примеров.
Только ПК, без симулятора. Install port-rc3 и r1 не тронуты.
Метки: **доказано** — факт или проверка; **скорее всего** — сильные признаки без контроля; **возможно** — догадка.

## r2b — что изменилось по сравнению с r2.0 (тоже 09.11)
Меняется только `examples/drone.py` (r2.0 `ed6a4eca…` → r2b `d5afa9a9…`). Прежние файлы — в `notes/prev_r2.0/`, разница — `notes/DIFF_r2b_vs_r2.0.txt`.
1. **F1, дыра в r2.0.** Сигнал «проснись» шёл только внутри `check_aruco()`, а детектор держит его 5 с. В `wait_yaw_lock`, `wait_position_stable`, `require_vpe_link` и при ожидании зрения во `takeoff` детектор мог снова уснуть. Нашли чат «New chat» и независимая проверка T15.
   - Теперь фоновый поток `aruco-wake` шлёт сигнал каждые 2 с (`WAKE_PERIOD_S`).
   - Запускают его `check_aruco`, `wait_yaw_lock`, `require_vpe_link`, `wait_position_stable` и `takeoff`.
   - Поток останавливается после взвода (дальше детектор держит свой гейт), при выходе из скрипта (`_shutdown`) или через 180 с после последнего вызова проверки (`WAKE_MAX_S`). На земле постоянной нагрузки нет.
   - Поток daemon: выход скрипта он не держит.
2. **F2, обязательная правка проверки.** Короткая, нечисловая или повторная строка карты, а также пустая карта теперь дают `RuntimeError` с номером строки. Раньше было `IndexError`/`ValueError`.
3. **F2, проверка на дроне.** `C:\Users\User\Documents\Claude local\map_check_20261109\map_check.cmd` — ТОЛЬКО ЧТЕНИЕ. Показывает, какую карту загрузил работающий детектор (параметр `map_file`), её SHA256 и время. Сравнивает их с `drone.MAP_FILE` (`/home/lb/ros2_ws/src/aruco_pose/map/map.txt`).
   - Ответ: SAME, DIFFERENT или UNKNOWN. UNKNOWN бывает, если детектор не запущен или карта менялась после его старта.
   - Нужна потому, что детектор берёт копию из install (`FindPackageShare`), а скрипты сверяют с src. Копии могут различаться — тогда ложное «OK» или ложный отказ (возможно, на дроне не проверено).
   - Проверен только на ПК: синтаксис и пробный прогон без дрона дал UNKNOWN, как и ожидалось. На дрон его запускает только владелец, когда решит чат 1.
4. Примеры, `hover_marker0.py` и `aruco_detect.py` не менялись (доказано, `DIFF_vs_r1.txt` — те же 4 файла; меняется только `drone.py`). `install/` не пересобирался: `drone.py` — пример, в install его нет.

## Что это
- `src/bumblebee` = образ r1 (`/work/fixed_image_r1_20261109`) + 4 файла из `/work/image_bugs_q6_20261109`. Суммы q6 сверены перед копированием. `drone.py` затем поправлен в r2b (`tools/make_r2b.py`).
  - `src/python/aruco_detect.py` — F1: сигнал `/aruco_detect/wake` держит детектор включённым 5 с.
  - `examples/drone.py`:
    - F1: фоновое «проснись» на всю предполётную проверку, до взвода (r2b);
    - F2: `set_aruco_map()` только сверяет карту, при отличии — отказ;
    - F4: выключение до ожидания потоков.
  - `examples/flight/flight.py` — взлёт на 0,8 м.
  - `examples/flight/flight_marker_loop.py` — точки 13/12/11 на x = −0,72, промежуточные −0,36.
- `DIFF_vs_r1.txt` — ровно 4 файла (доказано, `diff -ruN`).
- `install/` — сборка пакета bumblebee из r2.0: только он, `--executor sequential`, `nice -n 19`, `MAKEFLAGS=-j2`, окружение `/opt/ros/jazzy`, как у port-rc3. Журнал — `notes/build.log`.
- `image_manifest_r2.tsv` — формат как у `image_manifest.tsv`, по сравнению с r1 изменены 4 строки; строка `drone.py` — сумма r2b.
- `MANIFEST_SHA256.txt` — все файлы `src`, `test`, `tools`, `notes` и документы. `INSTALL_SHA256.txt` — `install/bumblebee/lib/bumblebee`.

## Ключи запускателя (правит чат «Симулятор»)
1. **`--examples DIR`** = `/work/fixed_image_r2c_20261109/src/bumblebee`. Оттуда брать `EXAMPLES`, `SCRIPT_PATH` и список профиля (`run_scenario2.sh`:35, 64, 260).
2. **`--install DIR`** = `/work/fixed_image_r2c_20261109/install`: `source $DIR/local_setup.bash` вместо port-rc3 (стр. 251). Нужно из-за F1: `aruco_detect.py` — узел, он ставится в install (`CMakeLists.txt`:140).
   - Остальные `source` — ws_sitl, MAVROS bp02 — без изменений.
3. **`SCRIPT_H` для flight.py = 0,8** (стр. 56; было 1,5). Для flight_marker 0,7 и loop 1,3 — без изменений.
4. **`MAP_FILE` для F2-б.** Теперь `set_aruco_map()` ничего не пишет, а сверяет карту с `drone.MAP_FILE`.
   - На стенде это карта, которую загрузил детектор: `/work/ws_sitl/install/aruco_pose/share/aruco_pose/map/map.txt` (sha 528b5adb — та же, что `map.input.txt`).
   - `trial_runner.py --trial-map-file` должен ставить `drone.MAP_FILE` на этот файл — только чтение, а не на выходной файл.
   - Пробный ключ `--trial-map-file` больше не нужен для записи. Нужен только для пути: на ПК нет `/home/lb`.
5. **`pins_check2.py`**: `--src /work/fixed_image_r2c_20261109/src/bumblebee`, `--manifest /work/fixed_image_r2c_20261109/image_manifest_r2.tsv`. Строки «install vs src» — против `--install`.
   - Ожидаемо одно известное отличие: `src/python/camera_fix.py` DIFFERS. Манифест содержит исправление камеры, которое ждёт замера нагрузки Pi на стенде, а в src его нет. Так было и в прогоне b01 (доказано, `pins.json`).
6. Пробный ключ `--trial-aruco-always` для r2 не нужен: F1-б будит детектор сам. Проверка — прогоны из `notes/GAZEBO_RUNS_r2.md` (заменяет `GAZEBO_RUNS.md` из q6 для r2).

## Тесты (без ROS) — `notes/TEST_RESULTS.txt`
- Q6 — 17 из 17 (тест `check_aruco` переделан под фоновый поток); r2b — 8 из 8 (`test/test_r2b_wake.py`); прежние тесты drone.py — 87 из 87 (2 пропущены); проверка профиля — 16 из 16.
- `test_r2b_wake.py`: настоящие потоки, время сжато в 20 раз. Порядок и длительность — как в flight.py: метки 3 с, курс до 20 с, стабильность 3 с, связь VPE 2 с, ожидание зрения 4 с, затем взвод.
  - Детектор бодр всё время: промежуток между сигналами не больше 5 с в масштабе.
  - После взвода сигналов нет, поток закрыт и закрыл публикатор.
  - После выхода скрипта сигналов нет. Тайм-аут без взвода останавливает поток. Поток один, сколько бы раз его ни звали.
- Независимая проверка T15: GO_AFTER_FIXES (`/work/image_bugs_q6_20261109_check/REVIEW.md`). Обязательные правки 1 и 3 сделаны в r2b, правка 2 — в `notes/GAZEBO_RUNS_r2.md`, правка 4 — в `notes/КАРТОЧКА_6_ПОПРАВКИ.md`. Пункт 5 (выход F4 с настоящим rclpy) — прогон 1 в Gazebo.
