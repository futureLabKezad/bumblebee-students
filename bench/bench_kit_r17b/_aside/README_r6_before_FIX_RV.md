# _aside\r6_before_FIX_RV — набор r6 до правок независимой проверки RV (отложено, не запускать)

Claude, задача FIX, 12.11.2026 (часы ПК). Здесь байт в байт лежат прежние версии всех файлов r6, которые тронули две обязательные правки проверки RV (пароль sudo при `ssh -tt`; отдельный резерв варианта камеры, чтобы 06 из r5 не откатывал вариант вместо образа r2j). Пути внутри папки — те же, что в наборе. Ничего не удалено. Все 21 файл сверены со снимком набора до правок (`/work/kit_r6_20261112/FIX/kit_before_fix.sha`), см. раздел FIX в конце `..\DIFF_r5_r6.txt`.

| Что | Файлы |
|---|---|
| исходники и документы (скопированы, в наборе — исправленные) | `pi\r6_sys_change.sh`, `pi\r6_cam_precheck.sh`, `run_r6_sys.ps1`, `image_r2j_cam\run_r6_cam_install.ps1`, `image_r2j_cam\README.md`, `cards\КАРТОЧКИ_r6.md`, `tests\run_tests_r6.ps1`, `tests\run_tests_r6_pi.sh`, `proverka_r6\mutation_check_r6.sh`, `README.md`, `PROGRESS.md`, `proverka_r6\README.md` |
| выводы, сделанные заново (перенесены) | `SHA256SUMS.txt` (до правок, сумма файла 88c79e29…), `DIFF_r5_r6.txt`, `proverka_r6\tests_*_console.txt` (5), `proverka_r6\tests_r6_svodka.txt`, `proverka_r6\mutation_check_r6.txt` |

Запускать отсюда нельзя и не нужно: скрипты здесь — только для сравнения. Набор r6 после правок — в корне набора (README.md, раздел «Правки по независимой проверке RV»).
