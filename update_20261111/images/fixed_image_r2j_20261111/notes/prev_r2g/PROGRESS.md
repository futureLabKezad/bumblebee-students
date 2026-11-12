# PROGRESS r2g (T39 чата 1), 10.11.2026
- Владелец про S4: «да». Поручение T39: r2f + одна правка S4, новая папка, тесты, одна проверка.
- Папка — копия r2f (src, test, tools, notes, image_manifest_r2.tsv; reviews r2f -> notes/prev_r2f/reviews). README/PROGRESS/суммы r2f — notes/prev_r2f/.
- tools/make_r2g.py: sha r2f drone.py, 7 якорей по одному совпадению. Отсчёт «зрения нет» — от взвода (обоснование в README).
- colcon: как r2f; notes/build_r2g.log exit 0, 62 с.
- Тесты: tools/test_all_r2g.sh -> notes/test_logs/ (SUMMARY_run.txt). Всё OK. Журналы тестов r2f — notes/r2f_test_logs/.
- Проверка: одна, через /work/REVIEW_LOCK.txt.
- Не трогал: r2f, дрон, Gazebo, чужие папки.
- 10:3x проверка r2g: принято с замечанием (reviews/REVIEW_r2g.md), MUST-FIX нет. SHOULD-1 (тест пропажи связи) внесён; README дополнен (install, заметки проверки). Прежние файлы — notes/_before_review/. Код drone.py не менялся. Замок снят.
