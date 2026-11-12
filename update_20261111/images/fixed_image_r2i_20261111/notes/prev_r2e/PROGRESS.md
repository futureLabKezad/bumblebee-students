# PROGRESS r2e — 09.11.2026

- r2e = r2d + правки независимой проверки (обязательная 1 и желательные 2–5). Сборка 63 с, тесты и пробы ревьюера прошли (notes/TEST_RESULTS.txt).
- Не сделано: Gazebo (notes/GAZEBO_RUNS_r2e.md). В папке build/ и log/ этой сборки, в манифест не входят.

---
# PROGRESS r2d — 09.11.2026

- T26 чата 1: r2d = r2c + F7 (подлёт 0,12 м + почти остановился) + T25 (аренда скрипта в simple_offboard). Сборка 89 с, тесты прошли (notes/TEST_RESULTS.txt).
- Не сделано: Gazebo (notes/GAZEBO_RUNS_r2d.md, делает Симулятор), независимая проверка (в очереди у чата 1).
- В папке есть build/ и log/ этой сборки, в манифест не входят.

---
# PROGRESS — T19: исправленный образ r2 (редакция r2c)
Обновлено: 09.11.2026.

## Готово
- r2c = r2b + F5: navigate() приводит поля float32 к float (tools/make_r2c.py, notes/DIFF_r2c_vs_r2b.txt). Причина доказана без симулятора (notes/F5_REPRO.txt).
- Тесты: test_r2c_navigate_float.py 6/6 (без ROS и с настоящим rosidl, 35 случаев + контроль r2b); Q6 17/17; r2b 8/8; guards 87/87.
- DIFF_vs_r1.txt пересчитан: те же 4 файла. image_manifest_r2.tsv: строка drone.py — сумма r2c. install — копия r2b, сверен.
- Независимая проверка не назначена (решение чата 1: правку проверит Gazebo).

## Дальше
- Симулятор: flight_marker.py и flight_marker_loop.py на r2c до посадки (прогон 3 из notes/GAZEBO_RUNS_r2.md), ключи — README r2c.

## История r2b
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
