@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: откат варианта камеры полных строк: возвращает camera_fix.py r2j 4a15d699 и bumblebee.launch.py r2j 62be01db в src и в install оверлея r2j из резерва установки 05c; то, что стоит сейчас, сохраняется рядом с резервом, ничего не удаляется. Зачем: вернуть прежнюю камеру r2j. Как вернуть обратно: 05c_install_r2j_cam.cmd снова, с новым разрешением. ЗАГОТОВКА: заблокирована без gates\OTKAT_R2J_CAM_APPROVED.txt от чата 1 и без заполненных DEST_ROOT и BACKUP_ROOT. Службу bumblebee останавливаете и потом запускаете вы сами.
rem 06c_otkat_r2j_cam.cmd (Claude, 12.11.2026, набор r6). Резерв ищется по sha256 манифеста варианта, откат делает прежний ..\image_r2j\image_rollback.sh с этой меткой. Журнал: ..\out\rollback_r2j_cam_НОМЕР.log, его видит 07 как событие.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_cam_install.ps1 check_gates_r2j_cam.ps1 image_manifest.final.tsv VARIANT_FILES.tsv ..\image_r2j\image_rollback.sh ..\image_r2j\image_target.conf ..\lib\bb_common.ps1 ..\lib\bb_lists.ps1 ..\lib\bb_lists_r2jcam.ps1 ..\lib\bb_r6.ps1 ..\pi\r6_cam_precheck.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\OTKAT_R2J_CAM_APPROVED.txt" (set "MSG=нет разрешения gates\OTKAT_R2J_CAM_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0..\out"
echo.
echo Правила: Claude к дрону не подключается, пароль и sudo вводите только вы. Моторы в этом шаге не нужны.
set "A1="
set /p "A1=1 из 2. Службу bumblebee вы остановили сами на Pi, пароль вводили вы. Наберите SERVICE и Enter: "
if /i not "%A1%"=="SERVICE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 2. Вернуть прежние файлы камеры r2j. Наберите YES и Enter: "
if /i not "%A2%"=="YES" (set "MSG=остановлено, ничего не сделано." & goto die)
title 06c_otkat_r2j_cam
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_cam_install.ps1" -Mode rollback -Confirmed SERVICE-YES-rollback
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: прежние файлы r2j вернулись. Запустите службу сами, подождите 2 минуты, потом 24b_proverka_kamery_r2j.cmd, затем 09 и 10. Скажите Claude.) else (echo СТОП: не сделано или не до конца, строки выше. Не взлетать, скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 1
