# c8_judge_r2e_a6_20261110 — пакет С8, редакция A6 (T32, 10.11.2026). ТОЛЬКО СИМУЛЯТОР

A6 = сборка 2 (`/work/c8_judge_r2e_20261109`, пины 02 40d67c1c) + одна правка в исполнителе пакета. Сделал чат «Разборы и правки кода» по задаче чата 1.
Прежняя папка не тронута. Полное описание пакета (судья, ожидания А5, кандидат, правила запуска) — в её README.md. Здесь только то, что изменилось.
Метки: **доказано** / **скорее всего** / **возможно**.

## Что случилось (прогон rel3, 10.11 01:15)
`INT_flight_C8b_kill_01` упал до взлёта (`/work/c8_rel3_run_20261110/RUN_LOG.md`). Механизм доказан:
- исполнитель ставил профиль INDOOR_ARUCO в порядке словаря `flight_profile.py`, где MPC_XY_CRUISE 0,3 идёт раньше MPC_XY_VEL_MAX 0,4;
- на 4061 MPC_XY_VEL_MAX = 0,25, и PX4 записал CRUISE обратно как 0,25 (`MulticopterPositionControl.cpp:215–217`, «Cruise speed has been constrained by max speed»);
- проверка исполнителя (`supervisor.py:309`) упала. Так упали бы все 13 сценариев.

## Ответы на вопросы чата 1
1. **Откуда порядок** (доказано по коду). Цикл установки — в исполнителе пакета: `executor/supervisor.py:305` прежней папки, `for name,value in profile_values().items()`. Это копия ft24, не образ r2e. Порядок имён задаёт литерал `INDOOR_ARUCO` в `flight_profile.py`. Его не трогали.
2. **Можно ли только в пакете** — да (доказано тестом на модели и кодом PX4).
   - **Установка.** A6 ставит профиль по `restore_order` из кандидата: родитель раньше потомка, MPC_XY_VEL_MAX раньше MPC_XY_CRUISE. Имена и значения те же, меняется только порядок.
   - **Возврат.** Он уже шёл «родитель раньше потомка» (`profile_transaction.restore` → `restore_order`) и в прогоне вернул все 18 имён замыкания (`independent_after` = before).
     - Путь возврата «VEL_MAX обратно на 0,25, пока CRUISE ещё 0,3» ни один прогон ещё не проходил: в первом прогоне A6 посмотреть эту запись в журнале транзакции (проверка, NOTE).
     - «CRUISE раньше VEL_MAX» при возврате не нужно: PX4 сам урежет CRUISE, когда VEL_MAX вернётся к 0,25, а затем CRUISE пишется в своё 0,2 ≤ 0,25.
     - Тест `a6_apply_order` проходит этот путь и получает исходные значения всех 18 имён.
   - **Другие пары-ограничения** (доказано по коду PX4 94cb2012 и тесту).
     - Обратно в настройку PX4 пишет только: CRUISE и VEL_MANUAL ≤ XY_VEL_MAX; MAN_BACK и MAN_SIDE ≤ VEL_MANUAL; Z_V_AUTO_UP/DN ≤ Z_VEL_MAX_UP/DN (`:215–280`). Плюс наклон и газ висения, SYS_VEHICLE_RESP и MPC_XY_VEL_ALL / MPC_Z_VEL_ALL — их нет в профиле, а последние три на 4061 отрицательные, то есть выключены (проверка).
     - TKO_SPEED и LAND_SPEED урезаются только внутри, без записи (`:301–302`), поэтому проверку чтением не ломают.
     - Внутри профиля оба конца есть только у пары XY_VEL_MAX → XY_CRUISE.
     - Побочно: Z_VEL_MAX_UP 1,0 → 0,5 урезает Z_V_AUTO_UP 1,0 → 0,5. Его нет в профиле, но он есть в замыкании (18 имён) и возвращается при восстановлении. Так было и в rel3.
   - **Не меняются:** r2e, судья (sha c3757935, байт в байт), ожидания `expect/`, кандидат, значения профиля.
3. **Почему старый rel3 проходил** (доказано по ULog `INT_flight_pc_rel3_kill_01`). На 4030 MPC_XY_VEL_MAX = 12, CRUISE = 5. Урезать было нечего, и порядок ни на что не влиял.

## Что изменилось (`DIFF_a6.md`, сборщик `tools/make_a6.py`)
- `executor/supervisor.py`: порядок установки — единственная правка поведения.
- `executor/run.sh`: путь своей папки.
- `launcher/host_run_wsl_c8_r2e_b.sh`: v33-c8-r2e-a6, исполнитель A6, свой `ACCEPTED_PINS_b.txt`.
- `pins/frozen_inputs_c8_r2e_a6_01.json` = пины 02, где переименована папка и новые суммы `supervisor.py` и `run.sh`. Другие суммы сверены и не изменились.
- Тесты: пути переведены на A6, добавлен `tests/a6_apply_order.py`.
- В тексте отказа судьи осталось старое имя папки («only inside c8_judge_r2e_20261109/reviews»). Судью не меняю, чтобы не терять доказательство «бит в бит». На деле он пишет только в `reviews/` этой папки.

## Тесты: `tests/test_c8_b2.sh` — 23/23 PASS
22 прежних (пути A6) + `a6_apply_order`. Базовые значения — настоящие значения 4061 из провалившегося прогона, только чтение.
- Старый порядок воспроизводит CRUISE 0,25.
- Новый порядок доводит до профиля все 13 значений.
- Возврат даёт все 18 исходных.
- Пара внутри профиля одна.

## Как запускать (WSL, по одному, `cd /work`). Новые теги: `INT_flight_C8b_kill_01` уже занят.
```
export BB_COMBINED_ROOT=/work/c8_judge_r2e_a6_20261110/candidate
export BB_FROZEN_PINS=/work/c8_judge_r2e_a6_20261110/pins/frozen_inputs_c8_r2e_a6_01.json
export C8_START_ORDER=px4_first      # D4: выбор Симулятора
L=/work/c8_judge_r2e_a6_20261110/launcher/host_run_wsl_c8_r2e_b.sh
bash $L INT_flight_C8a6_kill_01 kill paused
bash $L INT_flight_C8a6_freeze_02 freeze paused
bash $L INT_flight_C8a6_mavros_restart_03 mavros_restart paused
bash $L INT_flight_C8a6_pilot_04 pilot paused
bash $L INT_flight_C8a6_cancel_before_05 cancel_before paused
bash $L INT_flight_C8a6_ack_cancel_06 ack_cancel paused
CANCEL_OFFSET_MS=0   bash $L INT_flight_C8a6_cancel_off0_07 cancel paused
CANCEL_OFFSET_MS=50  bash $L INT_flight_C8a6_cancel_off50_08 cancel paused
CANCEL_OFFSET_MS=200 bash $L INT_flight_C8a6_cancel_off200_09 cancel paused
CANCEL_OFFSET_MS=500 bash $L INT_flight_C8a6_cancel_off500_10 cancel paused
CANCEL_OFFSET_MS=900 bash $L INT_flight_C8a6_cancel_off900_11 cancel paused
CANCEL_OFFSET_MS=980 bash $L INT_flight_C8a6_cancel_off980_12 cancel paused
bash $L INT_flight_C8a6_heartbeat_13 heartbeat paused
```
Судья на каждый TAG (пишет только в `reviews/` этой папки):
```
/work/analysis/layout/.venv/bin/python -B -I /work/c8_judge_r2e_a6_20261110/verify_flight_c8.py --identity c8_4061 \
  --run /work/sim/runs/TAG --expected-manifest /work/c8_judge_r2e_a6_20261110/candidate/manifest.json \
  --frozen-pins /work/c8_judge_r2e_a6_20261110/pins/frozen_inputs_c8_r2e_a6_01.json \
  --out /work/c8_judge_r2e_a6_20261110/reviews/TAG_review.json
```
Выход: 0 — пройден, 1 — провал, 2 — неизвестно. Сначала смотреть `host_check.json` `valid_host`.
