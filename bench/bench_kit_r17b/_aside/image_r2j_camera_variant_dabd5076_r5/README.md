# Вариант камеры: camera_fix.py dabd5076… (ТОЛЬКО ЕСЛИ ВЛАДЕЛЕЦ ВЫБЕРЕТ)

По умолчанию в образ r2j входит прежний `camera_fix.py` (sha256 4a15d6997ff1…), он проверен в Gazebo. Этот каталог нужен только если владелец выберет исправленный `camera_fix.py` (sha256 dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83, исправление «полной строки», `parallel_work/20261015/integration/camera_fullrow_01/candidate/camera_fix.py`).
**Метка файла в манифесте образа: «PENDING: Pi load check at the bench»** (нагрузка Pi с этим файлом на стенде не проверена; в Gazebo этот вариант не прогонялся: решение чата 1). Утром это вопрос владельцу (решение чата 1, 10.11 ~18:20).

Что здесь:
- `payload\ros2_ws\src\bumblebee\src\python\camera_fix.py` — файл варианта (копия, sha256 проверяется);
- `image_manifest.final.tsv` — одна строка, путь относительно `DEST_ROOT` подтверждает чат 1 вместе с `DEST_ROOT`;
- `check_gates_camera.ps1` — условия установки на ПК, без сети;
- `05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd` — установка варианта (МЕНЯЕТ ДРОН); основной `image_manifest.final.tsv` и основная установка не затрагиваются; `image_target.conf` и `image_install.sh` берутся из папки выше;
- `gates\README.md` — какой файл-разрешение нужен.

Условия: `gates\CAMERA_DABD5076_APPROVED.txt` создаёт только чат 1 после слов владельца; `DEST_ROOT` и `BACKUP_ROOT` заполнены в `..\image_target.conf`; манифест из одной строки с sha dabd5076…, файл в payload сходится по sha256.
Откат: `..\06_rollback_r2j.cmd` без метки откатывает САМУЮ НОВУЮ резервную копию, то есть эту установку камеры. Если после неё делалась другая установка, метку нужной копии подскажет Claude.
Не проверено: нагрузка Pi с этим файлом; живая установка не запускалась.