# Вариант образа «r2j + камера полных строк» (image_r2j_cam, набор r6)

Только если владелец выберет (через чат 1). Основа — принятый r2j. Отличие от r2j ровно в двух файлах (доказано генератором `gen_lists_r2jcam.py` и `diff` списков):
- `camera_fix.py` **dabd5076…** (вместо 4a15d699) — читает все строки сенсора с шагом 1600 (кандидат `camera_fullrow_01`);
- `bumblebee.launch.py` **5f0954d8…** (вместо 62be01db) — явно `full_rows: True` у `main_camera_fix` и `full_rows: False` у `second_camera_fix` (вторую камеру полный путь не проверял ни один замер).

Источник: образ `/work/fixed_image_r2jf_20261112` (SHA256SUMS `fecff133…`, проверка v14 R: GO с правками), см. `R2JCAM_SOURCE.txt`. Из образа взяты только эти два файла; его `setup.sh` и прочий install не используются (П4: POSIX setup.sh r2jf указывает на install r2j).

## Куда кладётся (4 места, `VARIANT_FILES.tsv`, пути от `/home/lb`)
| Место | Зачем |
|---|---|
| `ros2_ws/src/bumblebee/src/python/camera_fix.py`, `ros2_ws/src/bumblebee/launch/bumblebee.launch.py` | исходники: будущая сборка 13 возьмёт вариант |
| `bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py` (режим 755), `bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py` | то, что стек реально исполняет после 13 и 16 |

Копию исходников внутри оверлея (`bench_ws/r2j/src/...`) вариант НЕ трогает: из неё ничего не исполняется, 15 и 15c сверяют там только C++ и скрипты полёта (они не меняются).

## Шаги
1. Условия (`check_gates_r2j_cam.ps1`, на ПК): `gates\S2_S3_PASSED.txt` ЭТОГО манифеста, свежая сверка настроек с COM_OBL_RC_ACT=4, `gates\R2J_CAM_APPROVED.txt`, DEST_ROOT=/home/lb и BACKUP_ROOT в `..\image_r2j\image_target.conf` (сейчас BACKUP_ROOT=TBD — установка откажет), манифест и payload по sha256.
2. Владелец сам останавливает службу (`sudo systemctl stop bumblebee`), двойной щелчок `05c_install_r2j_cam.cmd`. До установки на Pi проверка только чтением (`..\pi\r6_cam_precheck.sh install`): служба не active, в `start_bumblebee.sh` строка оверлея r2j, `ros2 pkg prefix bumblebee` = оверлей r2j, 4 файла сейчас ровно r2j. Иначе СТОП: правка легла бы не туда, где исполняется. Установка — прежний `..\image_r2j\image_install.sh` (резерв в BACKUP_ROOT). После — проверка «файлы легли».
3. Владелец сам запускает службу, ждёт 2 минуты, `..\24a_proverka_kamery_polnye_stroki.cmd`: работающие оба camera_fix = dabd5076 из исполняемого префикса и запущены ПОСЛЕ замены файла, launch 5f0954d8, в журнале запуска `full_rows=True` у главной и `False` у второй, `full-row read: 384 …`, `legacy frames 0` во всех строках stats главной (полных кадров не меньше 600), без перезапусков и «process has died».
4. `..\09c_sverka_install_r2j_cam.cmd` и `..\15c_otpechatki_r2j_cam.cmd` — сверки со списками варианта (`INSTALL_SHA256_r2jcam.txt`, `RUNTIME_PY_r2jcam.tsv`; C++ — список r2j).
5. Откат: владелец останавливает службу, `06c_otkat_r2j_cam.cmd` (нужен `gates\OTKAT_R2J_CAM_APPROVED.txt`): резерв ИМЕННО этой установки ищется по sha256 её манифеста, откат — прежний `..\image_r2j\image_rollback.sh` с этой меткой; после — 4 файла = r2j. Потом служба, `..\24b_proverka_kamery_r2j.cmd`, затем 09 и 10.

## Что с прежними воротами (не ослаблены)
- 09 и 15 (r2j) не менялись и проверяют r2j как раньше: при стоящем варианте они дают СТОП (DIFF по двум файлам).
- 09c пишет `out\sverka_r2jcam_*.txt`, 15c — `out\otpechatki_r2jcam_*.txt`: 07 (взлёт) и 16 (подключение оверлея) эти файлы НЕ берут. **Полёт с вариантом этим набором не разрешается** — это отдельное решение чата 1 (правку ворот 07 я не делал).
- Журналы установки и отката называются `install_r2j_cam_*.log` и `rollback_r2j_cam_*.log`: 07 видит их как события (`install_r2j_`, `rollback_r2j_`), то есть любая установка или откат варианта обесценивает прежние 09 и 10.
- Разрешения одноразовые: успешный запуск с тем же файлом-разрешением второй раз не пройдёт.
