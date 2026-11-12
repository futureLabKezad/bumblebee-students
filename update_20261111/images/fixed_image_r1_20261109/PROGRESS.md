# PROGRESS — T5б: исправленный образ r1 для Gazebo
Обновлено: 09.11.2026 10:15 (чат «Разборы и правки кода»).

## Готово
- src/bumblebee = port-rc3 + 5 файлов ред. 3 из param_profile_fix_01; разница ровно 5 файлов (DIFF_vs_port_rc3.txt).
- image_manifest_r1.tsv (5 строк изменены), MANIFEST_SHA256.txt, README.md.
- Пересборка не нужна: examples в install не ставятся, запускатель берёт их из src.

## Дальше
- Чат «Симулятор»: ключи --examples (run_scenario2.sh) и --src/--manifest (pins_check2.py) по README; затем прогоны 3 и 6 из GAZEBO_RUNS.md.
