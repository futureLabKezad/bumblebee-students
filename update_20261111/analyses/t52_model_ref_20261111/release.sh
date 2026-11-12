#!/bin/bash
cd /work/t52_model_ref_20261111 || exit 1
sha256sum REVIEW_t52.md > REVIEW_SHA256.txt
grep -q "T52" /work/REVIEW_LOCK.txt && mv -n /work/REVIEW_LOCK.txt /work/_aside_locks_20261110/REVIEW_LOCK_released_$(date +%H%M%S)_t52.txt && echo LOCK_RELEASED
sed -i "s|^task: .*|task: НЕ ЗАЧЁТ: T52 проверка модели v2 + набора 4074 (run_t52.sh, 4 прогона), 11.11 13:4x|" /work/SIM_LOCK.txt; tail -1 /work/SIM_LOCK.txt
echo "- 13:4x REVIEW_t52.md: GO. 5a: камера в модели v2 (0,081;0;-0,034) не совпадает с образом r2hf (0,05;0;-0,07) -> позиция по зрению сдвинута ~3 см вперёд и поворачивается с курсом; yaw (4074+v2) и yawbase (4070+v1) отличаются двумя вещами — сравнение знаков в повороте читать с этой оговоркой; чистый ответ — на r2j. Оценщик С5 r5 берёт высоту из скрипта (AST takeoff height) — числа 0,8 в нём нет, новая редакция не нужна; 0,8 — только SCRIPT_H пускача для инфо-оценок (для r2j поставить 0,9). Замок освобождён, run_t52 запущен." >> /work/goal_series_20261109/PROGRESS.md
