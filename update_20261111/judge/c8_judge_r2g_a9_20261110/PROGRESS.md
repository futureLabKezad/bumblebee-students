# PROGRESS A9 (T38/T39 чата 1), 10.11.2026
- Основание: A8 REJECT (M1 журнал), T39 (r2g), чат 1 «вариант 1» (EKF2_OF_QMIN 50 новым именем), airframe 4070 v2 Симулятора (0224deec).
- Сборка 1: 29/30 (тест пускача с именем airframe v1). Отложена: /work/c8_judge_r2g_a9_20261110_build1_moved_aside.
- Сборка 2 (эта): 30/30 (tests/out_102534). Пины те же (4b46f4d4).
- Проверка: одна, через /work/REVIEW_LOCK.txt (ждёт замок).
- Не трогал: A7, A8, r2g, airframe Симулятора, дрон, Gazebo.
- 10:5x проверка A9: принято с замечаниями (reviews/REVIEW_A9.md), MUST-FIX нет. S1/S3 — README, S2 — тест a9_logger_restart (поддельный логгер создаёт файл). Прежние — notes/_before_review/. Исполнитель, судья, пины не менялись. Замок снят.
