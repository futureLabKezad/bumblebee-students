# c8_judge_r2e_a7_20261110 — пакет С8, редакция A7 (10.11.2026). ТОЛЬКО СИМУЛЯТОР

A7 = A6 (`/work/c8_judge_r2e_a6_20261110`, пины d61b25d7) + своя копия запуска камеры. A6 не тронут. Полное описание пакета — в README сборки 2 (`/work/c8_judge_r2e_20261109`) и A6. Здесь только то, что изменилось.
Метки: **доказано** / **скорее всего** / **возможно**.

## Что случилось (прогон Симулятора INT_flight_C8a6_kill_01, 10.11 ~03:40)
- **Профиль.** A6 поставил его верно: VEL_MAX 0,4 раньше CRUISE 0,3.
- **Возврат.** PX4 написал «Cruise speed has been constrained», но итог верный: after = before по всем 18 именам (Симулятор).
- **Провал до взлёта: «Default detector did not start»** (доказано по коду и `camera_stack.log`).
  - `executor/run.sh:112` запускал общий `/work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py`.
  - Тот принимает кандидат только из `.../integration/combined_*` (`:16–19`) и отказал: «Separate integration candidate required». Кандидат пакета лежит в папке пакета.
  - Та же строка была и в C8b_kill_01: там до неё не дошло, прогон упал раньше на профиле.

## Что изменилось (`DIFF_a7.md`, сборщик `tools/make_a7.py`)
- **Новый файл `executor/vision_c8.launch.py`.** Это копия общего файла (sha c9fe8ba6) байт в байт, кроме двух мест:
  - заголовок;
  - проверка места: теперь кандидат должен быть ровно `/work/c8_judge_r2e_a7_20261110/candidate`.

  Сверка детектора с манифестом кандидата осталась. Параметры детектора, мост камеры и `camera_fix` — те же.
- **`executor/run.sh`:** путь своей папки; камера запускается из `"$OWN/vision_c8.launch.py"`.
- **Пускач:** v34-c8-r2e-a7, исполнитель A7, свой `ACCEPTED_PINS_b.txt`.
- **Пины `pins/frozen_inputs_c8_r2e_a7_01.json`.** Это пины A6 с новой папкой; новые суммы `run.sh`; добавлен `vision_c8.launch.py` в repo_files, run_files и ledger_files. Остальные суммы сверены — не изменились.
- **Не менялись:** судья (c3757935), ожидания, кандидат, профиль и порядок A6, r2e.
- **Общий `vision.launch.py`** остаётся в repo_files как прежде (не изменён), но этот пакет его больше не запускает.

## Тесты: `tests/test_c8_b2.sh` — 24/24 PASS
23 прежних (пути A7) и новый `a7_vision_launch`:
- копия принимает кандидат A7 (4 действия);
- отказывает: кандидату A6, `combined_13`, чужому окружению, изменённому детектору;
- отличается от общего файла только заголовком и проверкой места.

Первый запуск тестов упал из-за ошибки в самом тесте: не вернул окружение. Лог — `tests/_failed_first_run/`.

## Что дальше может упасть (не проверено)
- **Где остановился прогон.** Он упал на запуске камеры. Шаги после неё в этом пакете на 4061/r2e ещё не проходили.
- **Что проверено.** Пути к папкам пакета в исполнителе и кандидате: другие проверки места кандидата не нашлись (`grep`). Но поведение дальше покажет только прогон (возможно).

## Как запускать (WSL, по одному, `cd /work`; новые теги — `INT_flight_C8a6_kill_01` занят)
```
export BB_COMBINED_ROOT=/work/c8_judge_r2e_a7_20261110/candidate
export BB_FROZEN_PINS=/work/c8_judge_r2e_a7_20261110/pins/frozen_inputs_c8_r2e_a7_01.json
export C8_START_ORDER=px4_first
L=/work/c8_judge_r2e_a7_20261110/launcher/host_run_wsl_c8_r2e_b.sh
bash $L INT_flight_C8a7_kill_01 kill paused
```
Остальные 12 сценариев — те же команды, что в README A6, но с тегами `INT_flight_C8a7_*`.
Судья:
```
/work/analysis/layout/.venv/bin/python -B -I /work/c8_judge_r2e_a7_20261110/verify_flight_c8.py --identity c8_4061 \
  --run /work/sim/runs/TAG --expected-manifest /work/c8_judge_r2e_a7_20261110/candidate/manifest.json \
  --frozen-pins /work/c8_judge_r2e_a7_20261110/pins/frozen_inputs_c8_r2e_a7_01.json \
  --out /work/c8_judge_r2e_a7_20261110/reviews/TAG_review.json
```
