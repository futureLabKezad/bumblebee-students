# Исправленный образ r1 для Gazebo — 09.11.2026 (T5б)

Сделал чат «Разборы и правки кода» по задаче чата 1. Только копирование и сверка: без симулятора, без сборок. `/work/ws_package1b_port_03` не тронут.
Метки: **доказано** — факт или проверка; **скорее всего** — сильные признаки без контроля; **возможно** — догадка.

## Что это
- `src/bumblebee` — копия пакета port-rc3 из `/work/ws_package1b_port_03/src/bumblebee`. Без `.git` и `__pycache__`.
- Поверх копии — 5 файлов ред. 3 из `/work/param_profile_fix_01`: суммы папки сверены перед копированием.
  - `examples/drone.py`;
  - `examples/flight_profile.py`;
  - `examples/flight/flight.py`, `flight_marker.py`, `flight_marker_loop.py`.
- Больше ничего не менялось: `DIFF_vs_port_rc3.txt` — ровно 5 файлов (доказано, `diff -ruN`).
- Новые тесты исправления в образ не входят, они остались в `param_profile_fix_01`.

## Нужна ли пересборка — нет (доказано по коду)
- CMake ставит в install только узлы, скрипты, launch, camera_info и www (`CMakeLists.txt`:140–156). Папки examples в install нет.
- Запускатель берёт примеры из src (`run_scenario2.sh`:35, 64, 286–287: `EXAMPLES=$PRODUCT/src/bumblebee/examples`, `PYTHONPATH="$EXAMPLES"`). Узлы ROS он берёт из `$PRODUCT/install` (`run_scenario2.sh`:251).
- Все 5 изменённых файлов — примеры. Узлы, бинарники и install не меняются. Install можно и дальше брать из `/work/ws_package1b_port_03/install`.

## Манифесты
- `MANIFEST_SHA256.txt` — SHA256 всех файлов этой папки.
- `image_manifest_r1.tsv` — тот же формат, что `/work/goal_20261106/image_manifest.tsv`: 374 файла. Изменены 5 строк — столбец «исправленный образ», источник `param_profile_fix_01`. Старый манифест не тронут.

## Что поменять в запускателе (делает чат «Симулятор», я не правлю)
1. `run_scenario2.sh`: разделить место примеров и место install.
   - Новый ключ `--examples DIR` (по умолчанию как сейчас, `$PRODUCT/src/bumblebee`). Для r1: `--examples /work/fixed_image_r1_20261109/src/bumblebee`.
   - Из этого DIR брать `EXAMPLES` (стр. 35), `SCRIPT_PATH` (стр. 64) и список настроек профиля для наблюдения (стр. 260).
   - `source $PRODUCT/install/local_setup.bash` (стр. 251) оставить на port-rc3.
   - Путь к примерам записать в `run_info` прогона.
2. `pins_check2.py`: ключи `--src DIR` (сейчас `PRODUCT/src/bumblebee`) и `--manifest FILE` (сейчас `/work/goal_20261106/image_manifest.tsv`).
   - Для r1: `--src /work/fixed_image_r1_20261109/src/bumblebee --manifest /work/fixed_image_r1_20261109/image_manifest_r1.tsv`.
   - Строки «install vs src» для узлов (`aruco_detect`, `camera_fix`, `vpe_fix`, `setpoint_freshness`) сверять с src нового места: там они не менялись, поэтому совпадут.
3. Ожидаемый итог С1 на r1 (поправка 09.11): одно известное отличие — src/python/camera_fix.py DIFFERS. Манифест содержит исправление камеры, которое ждёт замера нагрузки Pi, а в src его нет. Так было и в прогоне b01 (pins.json). Остальные строки «same» (скорее всего).

## Что не проверено
- Прогонов на r1 ещё не было. Чтение настроек на настоящем MAVROS — прогоны 3 и 6 из `/work/param_profile_fix_01/GAZEBO_RUNS.md`.
