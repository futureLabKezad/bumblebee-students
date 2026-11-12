# c8_judge_r2i_a11_20261111 — пакет С8, редакция A11 (11.11.2026, T46). ТОЛЬКО СИМУЛЯТОР

A11 = A10 ред. 2 (`/work/c8_judge_r2h_a10_20261110`, SHA256SUMS.txt 4f44222b, пины 9ec805e7) + образ **r2i** байт в байт (`/work/fixed_image_r2i_20261111`, SHA256SUMS 38daf429, MANIFEST_SHA256.txt 855f9f93).
- A10 не тронут. Каждая строка разницы — `DIFF_a11.md`, сборщик — `tools/make_a11.py`.
- Тесты S, судья (1ab83ca4), legacy, ожидания, airframe 4070 v2, run_sim.snapshot.sh — байты A10. Вариант Б (без freshness) — как в A10.
- Правка S9 живёт в образе (simple_offboard r2i), не в тесте.

## Что изменилось против A10
1. **Кандидат.**
   - `candidate/parameters/vpe_fix.py` = r2i (f0dc7c18): зрение и в AUTO.LAND.
   - `flight_profile.py` и `aruco_detect.py` побайтно одинаковы в r2h и r2i (сборщик сверяет).
   - Пин vpe_fix в `vpe_profile_optin.py` = r2i. Манифест кандидата — sha этих двух файлов и тексты.
2. **Исполнитель.**
   - `PRODUCT_SHA256SUMS.txt` пересчитан по install r2i: те же 505 путей, тот же порядок. Бинарник simple_offboard r2i несёт правку S9.
   - Кэш Python `__pycache__` в install r2i (его оставили ROS-тесты образа, в суммы r2i он не входит) в список не берётся, как и в A10.
   - run.sh закрепляет эти суммы. sha drone.py прежний: drone.py r2i — байты r2h (fa6abf8b).
   - `TARGET_SHA256` в `vpe_gate_diagnostic_p1.py` = r2i; `vpe_diagnostic_entry.py` — sha нового помощника; путь профиля в sitl_setup — r2i.
   - `executor/tests/test_entry_order.py`: только пути. Перезапущен на r2i — ALL OK, журнал тот же текст.
3. **Пускач, пины, тесты.**
   - Пускач v38-c8-r2i-a11, пины `frozen_inputs_c8_r2i_a11_01.json` (f6de13cf); пины A10 пускач отвергает (тест).
   - Тесты — пути A11. `a10_checks.py` заменён на `a11_checks.py` (разница A10 → A11). В `a8_checks.py` — сумма MANIFEST r2i и sha r2i в сравнении vpe_profile_optin с A7.
   - `a10_vpe_as_drone.py` (имя прежнее) теперь проверяет состав A11: 16 из 16 выборок после паузы, как на дроне.

## Тесты — `tests/test_c8_b2.sh`: 31 из 31 PASS (`tests/out_130657`)
- 29 прежних на путях A11 и `a11_checks`. Он проверяет:
  - судья, ожидания, run_sim и freshness — байты A10;
  - отличаются ровно две строки sha и строка помощника;
  - пины — ключи A10 с новыми путями и верными sha;
  - суммы продукта проходят на r2i и не проходят на r2h; пускач по умолчанию берёт r2i.
- Сборка 1 отложена (`…_build1_moved_aside`): три теста A8 читали значения из `tools/make_a10.py`. Это имя теперь заменяется, а журнал test_entry_order совпал с A10 — `a11_checks` это учитывает.

## Чего тесты не покажут
- Прогон SITL я не запускал (запрет Gazebo). Зачёт делает Симулятор.
- В посадке (AUTO.LAND) vpe_fix r2i публикует позы. Судья и legacy публикацию vpe_fix не разбирают: поиск по их коду (pose_cov, vision, publish) ничего не находит, AUTO.LAND они смотрят только по HEARTBEAT PX4 (доказано по коду). Как это скажется на прогонах S, покажет зачёт.

## Независимая проверка
Одна, разница A10 → A11, через `/work/REVIEW_LOCK.txt` — после «ок» чата 1.

## Как запускать (WSL, по одному, `cd /work`; теги `INT_flight_C8a11_*`)
```
export BB_COMBINED_ROOT=/work/c8_judge_r2i_a11_20261111/candidate
export BB_FROZEN_PINS=/work/c8_judge_r2i_a11_20261111/pins/frozen_inputs_c8_r2i_a11_01.json
export C8_START_ORDER=px4_first
L=/work/c8_judge_r2i_a11_20261111/launcher/host_run_wsl_c8_r2e_b.sh
bash $L INT_flight_C8a11_heartbeat_13 heartbeat paused
```
Судья:
```
/work/analysis/layout/.venv/bin/python -B -I /work/c8_judge_r2i_a11_20261111/verify_flight_c8.py --identity c8_4070 \
  --run /work/sim/runs/TAG --expected-manifest /work/c8_judge_r2i_a11_20261111/candidate/manifest.json \
  --frozen-pins /work/c8_judge_r2i_a11_20261111/pins/frozen_inputs_c8_r2i_a11_01.json \
  --out /work/c8_judge_r2i_a11_20261111/reviews/TAG_review.json
```

## Суммы
`SHA256SUMS.txt` — все файлы пакета. Пины f6de13cf, манифест кандидата 02c5faf4.
