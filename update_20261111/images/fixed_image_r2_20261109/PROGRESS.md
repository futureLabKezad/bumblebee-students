# PROGRESS — T16: исправленный образ r2 (редакция r2b)
Обновлено: 09.11.2026.

## Готово
- r2.0: src = r1 + 4 файла q6 (DIFF_vs_r1.txt); image_manifest_r2.tsv (4 строки); сборка пакета bumblebee — exit 0 за 75 с, install/ (INSTALL_SHA256.txt).
- r2b: drone.py — фоновое «проснись» на всю предполётную проверку (до взвода / выхода / 180 с); строки карты -> RuntimeError. tools/make_r2b.py, notes/DIFF_r2b_vs_r2.0.txt, прежние файлы в notes/prev_r2.0/. install не пересобирался (drone.py — пример).
- Тесты: 17/17, 8/8 (новый test_r2b_wake.py), 87/87, 16/16.
- Проверка T15: GO_AFTER_FIXES; правки 1, 3 — в коде; 2 — notes/GAZEBO_RUNS_r2.md; 4 — notes/КАРТОЧКА_6_ПОПРАВКИ.md; 5 — прогон 1 в Gazebo.
- map_check.cmd (только чтение, дрон): C:\Users\User\Documents\Claude local\map_check_20261109 (копия в notes/map_check_20261109).

## Дальше
- Симулятор: ключи запуска по README, прогоны из notes/GAZEBO_RUNS_r2.md.
- map_check.cmd на дроне — только когда решит чат 1, двойной щелчок владельца.
