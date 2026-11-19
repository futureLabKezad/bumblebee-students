@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ставит вариант образа r2j + камера полных строк: camera_fix.py dabd5076 и bumblebee.launch.py с full_rows - у главной камеры True, у второй False - и в src, и в install оверлея r2j, то есть туда, откуда стек их реально запускает; прежние файлы r2j копируются в резерв. Зачем: камера полных строк по просьбе владельца 12.11, меньше шума позы. Как вернуть: 06c_otkat_r2j_cam.cmd одним щелчком возвращает файлы r2j 4a15d699 и 62be01db из резерва этой установки, нужен свой файл-разрешение. ЗАГОТОВКА: заблокирована, пока нет gates\R2J_CAM_APPROVED.txt и gates\S2_S3_PASSED.txt варианта от чата 1, свежей сверки настроек с COM_OBL_RC_ACT=4 и заполненных DEST_ROOT и BACKUP_ROOT. Службу bumblebee останавливаете и потом запускаете вы сами.
rem 05c_install_r2j_cam.cmd (Claude, 12.11.2026, набор r6). Вместо сломанного 05v r5: тот клал файл только в src, а стек запускает install - молча ничего не менялось. Условия: check_gates_r2j_cam.ps1; на Pi до установки только чтение pi\r6_cam_precheck.sh. Журнал: ..\out\install_r2j_cam_НОМЕР.log, его видит 07 как событие.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_cam_install.ps1 check_gates_r2j_cam.ps1 image_manifest.final.tsv VARIANT_FILES.tsv ..\image_r2j\image_install.sh ..\image_r2j\image_target.conf ..\lib\bb_common.ps1 ..\lib\bb_lists.ps1 ..\lib\bb_lists_r2jcam.ps1 ..\lib\bb_r6.ps1 ..\pi\r6_cam_precheck.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\R2J_CAM_APPROVED.txt" (set "MSG=нет разрешения gates\R2J_CAM_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0..\out"
echo.
echo Правила: Claude к дрону не подключается, пароль и sudo вводите только вы. Причина рывка моторов 04.11 неизвестна. Моторы в этом шаге не нужны, винты СНЯТЫ.
set "A1="
set /p "A1=1 из 2. Службу bumblebee вы остановили сами на Pi, пароль вводили вы. Наберите SERVICE и Enter: "
if /i not "%A1%"=="SERVICE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 2. Заменить 4 файла камеры на дроне вариантом, старые уйдут в резерв. Наберите YES и Enter: "
if /i not "%A2%"=="YES" (set "MSG=остановлено, ничего не сделано." & goto die)
title 05c_install_r2j_cam
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_cam_install.ps1" -Mode install -Confirmed SERVICE-YES-install
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: файлы варианта легли. Запустите службу сами, подождите 2 минуты, потом 24a_proverka_kamery_polnye_stroki.cmd. Скажите Claude.) else (echo СТОП: не сделано или не до конца, строки выше. Не взлетать, скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 1
