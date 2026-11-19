# gates — разрешения для новых шагов r6 (создаёт ТОЛЬКО чат 1 после слов владельца)

Файлов сейчас НЕТ, поэтому все шаги r6 с пометкой «МЕНЯЕТ ДРОН» заблокированы. Claude-сборщик эти файлы не создаёт. Формат одинаковый (строки, порядок любой):
```
ПРАВКА=<код шага из таблицы>
ВЛАДЕЛЕЦ_СКАЗАЛ=да
ДАТА=<дата и время>
СЛОВА_ВЛАДЕЛЬЦА=<дословно>
СОЗДАЛ=чат 1
```
| Файл | ПРАВКА= | Шаг |
|---|---|---|
| `CAM_K1_APPROVED.txt` | `21_kamera_K1` | 21: К-1, только новые файлы на Pi |
| `CAM_COST_APPROVED.txt` | `22_kamera_cena` | 22: цена камеры A → C → A2, временные процессы |
| `SYS_FWUPD_MASK_APPROVED.txt` | `23a_fwupd_mask` | 23a: mask fwupd-refresh.timer |
| `OTKAT_SYS_FWUPD_APPROVED.txt` | `23a_otkat_fwupd_mask` | откат 23a |
| `SYS_SNAP_HOLD_APPROVED.txt` | `23b_snap_hold` | 23b: snap refresh --hold |
| `OTKAT_SYS_SNAP_HOLD_APPROVED.txt` | `23b_otkat_snap_hold` | откат 23b |
| `SYS_TIMERS_MASK_APPROVED.txt` | `23c_taimery_mask` | 23c: mask man-db, motd-news, update-notifier-download, update-notifier-motd |
| `OTKAT_SYS_TIMERS_APPROVED.txt` | `23c_otkat_taimery_mask` | откат 23c |

Разрешения варианта камеры (`R2J_CAM_APPROVED.txt`, `OTKAT_R2J_CAM_APPROVED.txt`, `S2_S3_PASSED.txt`) лежат в `image_r2j_cam\gates\` (формат там в README.md).
- **Одноразовые.** Шаг проверяет `out\`: если там уже есть журнал успешного запуска с sha256 этого файла-разрешения, отказ (нужно новое «да»). Для 21 и 22 «успешный» = на Pi уже создавались файлы по этому разрешению.
- **Откаты тоже по разрешению** (правило задания r6: шаги «МЕНЯЕТ ДРОН» открываются только файлом-разрешением). В r5 откаты 06, 12, 14, 17 шли без разрешения — их не менял.
- **Правки ступени 1 — строго по одной:** 23a/23b/23c (apply) требуют свежий (не старше 60 минут) успешный `20_nichego_ne_otvalilos.cmd`, сделанный ПОСЛЕ последней правки или отката ступени 1.
