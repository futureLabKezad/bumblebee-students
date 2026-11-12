# PROGRESS — оценщики С5/С6/С7, редакция r5 (чат «Скрипты полёта», 10.11)

## Готово (10.11)
- [x] Копия r4 (без check_runs r4); одна правка в c6_eval.py: п. 2а на всём взведённом полёте (от взвода до снятия с охраны); сброс до взвода не считается.
- [x] c5_eval.py, c7_eval.py, goal_common.py — байт в байт r4.
- [x] Тесты: test_goal_evals 54/54, test_c6_eval 46/46, test_c6_s10_runs 10/10; поломки 61/61, 21/21.
- [x] s10_c6r6_01…10 → check_runs/: 06, 07, 08 FAIL по no_jump_a_ekf, остальные PASS.
- [x] Проверка разницы r4→r5 (один агент, замок /work/REVIEW_LOCK.txt): обязательных правок нет; по советам S1, S2 — 2 теста, S6 — слово в README.
- [x] Суммы последним действием; путь и sha — Симулятору и чату 1; замок снят.

## Если продолжает другой чат
Папку после передачи не править — новой редакцией. Тесты: `~/px4-venv/bin/python3 -I -B -W ignore tests/test_goal_evals.py -v`, `tests/test_c6_eval.py`, `tests/test_c6_s10_runs.py` (нужны прогоны /work/goal_step5b_20261109/runs/s10_c6r6_*); поломки: `tests/mutation_check.py`, `tests/mutation_check_c6.py`.
