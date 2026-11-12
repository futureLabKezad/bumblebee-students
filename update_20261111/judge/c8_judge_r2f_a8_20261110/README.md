# c8_judge_r2f_a8_20261110 — пакет С8, редакция A8 (10.11.2026, T38). ТОЛЬКО СИМУЛЯТОР

A8 = A7 (`/work/c8_judge_r2e_a7_20261110`, пины 12a05438) + образ r2f + окончательный набор Gazebo airframe 4070. A7 не тронут.
Метки: **доказано** / **скорее всего** / **возможно**. Каждая изменённая строка — `DIFF_a8.md`, сборщик — `tools/make_a8.py`.

## Что изменилось против A7
1. **Образ r2f** — ровно тот, что прошёл проверку: `/work/fixed_image_r2f_20261110`, MANIFEST_SHA256.txt 2feb53fb (сборщик сверяет sha и `sha256sum -c`).
   - `executor/PRODUCT_SHA256SUMS.txt` пересчитан по install r2f: те же 522 пути в том же порядке. run.sh закрепляет его sha и sha drone.py r2f (94f9dfee).
   - `sitl_setup.py`: путь профиля → r2f (файл `flight_profile.py` в r2f тот же байт в байт).
   - Запускатель: по умолчанию install и src r2f.
   - Копии файлов образа в кандидате (`flight_profile.py`, `vpe_fix.py`, `aruco_detect.py`) в r2f не менялись — они те же байт в байт (доказано, сборщик и тест).
2. **Airframe 4070** Симулятора: `/work/goal_step5b_20261109/px4_etc/init.d-posix/airframes/4070_gz_bumblebee_final_4061_bat0_sdlog1` (sha 0bca708f) = `. 4061_…` + `BAT1_SOURCE 0` + `SDLOG_MODE 1`. Своего airframe в пакете нет.
   - Запускатель: `C8_AIRFRAME` по умолчанию 4070. Файл 4070 добавлен в пины (цепочка 4061… — как была).
   - `candidate/parameters/vpe_profile_optin.py`: проверка стенда «SITL airframe is not 4061» → 4070. Это **не файл образа** (нет в MANIFEST r2f, на дрон не идёт, в SITL отказывает при /etc/bumblebee) — правило С1 не задето.
3. **Ожидания `real_parameters_before_arm`** — identity `c8_4070` (одна новая строка таблицы судьи — данные, логика не тронута):
   - `expect/flight_real_params_4070.json` = файл 4061 + `BAT1_SOURCE 0` (владелец 09.11 «да», было 1) + `SDLOG_MODE 1` (владелец 10.11 «В», новое имя);
   - `expect/rc_real_params_4070.json` = файл 4061 без изменений.
   - Те же 18 имён профиля, что у c8_4061. Identity `c8_4061` и `rel3_4030` остались (для контроля).
4. **Новая настройка потока (если владелец утвердит)** = одна строка в `EXPECT_4070` (`tools/make_a8.py`) + та же строка в airframe 4070 у Симулятора + его новый sha в `AF4070_SHA`. Тест `a8_checks` сверяет ожидания с airframe строка в строку.
5. **Не менялись:** логика судьи и legacy-копия (8bcef313), порядок профиля A6, запуск камеры A7 (в нём только путь своего кандидата), исполнитель кроме строк выше.

## Тесты — `tests/test_c8_b2.sh`: 28 из 28 PASS
- 25 прежних (пути A8, образ r2f, airframe 4070 в проверке пинов).
- D7: стенд отказывает 4030, 4061 и старой метке; 4070 доходит до проверки маршрута MAVROS.
- `a8_checks`: identity c8_4070; ожидания = 4061 + ровно `EXPECT_4070` = строки airframe 4070; sitl_setup не трогает BAT1_SOURCE (KEEP_AIRFRAME) и SDLOG_MODE (его нет в файлах 20EC и профиле); судья отличается от A7 ровно на 5 строк (комментарий + строка таблицы), удалённых строк нет; пины и сумма продукта; install r2e сумму продукта не проходит.
- `judge_c8_4070_effect` (прогон rel3 kill): отличаются только candidate4030 и real_parameters_before_arm. В этом прогоне SDLOG_MODE уже 1, поэтому SDLOG_MODE там не виден — см. следующий тест.
- `a8_judge_on_a7_run` (**настоящий прогон 4061 из A7**, INT_flight_C8a7_kill_01): судья A8 как `c8_4061` даёт тот же вердикт, что A7 (pass, ни одна проверка не отличается). Как `c8_4070` — падает только на airframe (4061 вместо 4070) и на BAT1_SOURCE 1→0, SDLOG_MODE 0→1. Это доказывает, что судья реально проверяет обе новые настройки.
- Первая сборка (одна ошибка в самом тесте a8_checks, и тест на прогоне A7 добавлен позже) отложена: `/work/c8_judge_r2f_a8_20261110_build1_moved_aside`. Пины пересборки те же байт в байт (65d0f719).

## Разбор (низкий приоритет): legacy-проверка `s1_first_armed_trajectory_estimated_offset` у отмены 0 — `notes/S1_OFFSET_CANCEL.md`
Коротко: на вердикт не влияет (доказано), причина — частота журнала против «удержания на земле» (доказано по ULog).

## Как запускать (WSL, по одному, `cd /work`; теги новые, `INT_flight_C8a8_*`)
```
export BB_COMBINED_ROOT=/work/c8_judge_r2f_a8_20261110/candidate
export BB_FROZEN_PINS=/work/c8_judge_r2f_a8_20261110/pins/frozen_inputs_c8_r2f_a8_01.json
export C8_START_ORDER=px4_first
L=/work/c8_judge_r2f_a8_20261110/launcher/host_run_wsl_c8_r2e_b.sh
bash $L INT_flight_C8a8_kill_01 kill paused
```
Остальные сценарии — как в README A6/A7, с тегами `INT_flight_C8a8_*`. Судья:
```
/work/analysis/layout/.venv/bin/python -B -I /work/c8_judge_r2f_a8_20261110/verify_flight_c8.py --identity c8_4070 \
  --run /work/sim/runs/TAG --expected-manifest /work/c8_judge_r2f_a8_20261110/candidate/manifest.json \
  --frozen-pins /work/c8_judge_r2f_a8_20261110/pins/frozen_inputs_c8_r2f_a8_01.json \
  --out /work/c8_judge_r2f_a8_20261110/reviews/TAG_review.json
```
- Серию r2f Симулятор начинает только после решения по потоку (поручение T36).
- Возможно: с `SDLOG_MODE 1` журнал PX4 пишется с загрузки. run.sh берёт самый свежий `.ulg` после старта — должен быть один файл на прогон; проверка `fresh_single_ulog` это покажет. На 4070 ещё не гоняли.

## Суммы
`SHA256SUMS.txt` — все файлы пакета (кроме самого себя). Пины 65d0f719, судья 5b2d6106, манифест кандидата b1b1fa52.
