@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ставит ВАРИАНТ камеры, camera_fix.py с sha256 dabd5076 вместо прежнего (4a15d699); прежний файл копируется в резерв. ТОЛЬКО ЕСЛИ ВЛАДЕЛЕЦ ВЫБРАЛ этот вариант (разрешение чата 1). Зачем: исправление полной строки камеры; на нагрузку Pi не проверено (PENDING). Как вернуть: ..\06_rollback_r2j.cmd (без метки откатывает самую новую резервную копию, то есть эту установку). ЗАГОТОВКА: заблокирована, пока не выполнены ВСЕ условия основной установки (S2/S3 для этого образа, свежая сверка настроек, COM_OBL_RC_ACT=4, DEST_ROOT и BACKUP_ROOT) и пока нет gates\CAMERA_DABD5076_APPROVED.txt.
rem 05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd (Claude, 10.11.2026, набор r2). Основан на 05_install_r2j.cmd. Условия проверяет check_gates_camera.ps1 на ПК, без сети.
cd /d "%~dp0"
set "H=lb@10.255.254.26"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (check_gates_camera.ps1 image_manifest.final.tsv ..\image_install.sh ..\image_target.conf) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if defined BB_KIT_OUT (set "OUT=%BB_KIT_OUT%") else (set "OUT=%~dp0..\..\out")
if not exist "%OUT%" mkdir "%OUT%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_gates_camera.ps1" -Kit "%~dp0." -OutDir "%OUT%"
if errorlevel 1 (set "MSG=условия установки варианта камеры не выполнены, ничего не изменено. Причины выше." & goto die)
set "R=%RANDOM%%RANDOM%"
set "LOG=%OUT%\install_camera_dabd5076_%R%.log"
if exist "%LOG%" (set "MSG=файл %LOG% уже есть, не перезаписываю." & goto die)
set "STG=%OUT%\stage_camera_%R%"
if exist "%STG%" (set "MSG=папка %STG% уже есть, не перезаписываю." & goto die)
title 05v_camera_dabd5076
echo Условия выполнены. Дрон должен быть на земле, моторы не крутятся, винты сняты или дрон закреплён.
set "OK="
set /p "OK=Наберите YES и Enter, чтобы заменить camera_fix.py на дроне вариантом dabd5076, иначе остановка: "
if /i not "%OK%"=="YES" (set "MSG=остановлено, ничего не изменено." & goto die)
mkdir "%STG%"
xcopy "%~dp0payload" "%STG%\payload\" /E /I /Q >nul
copy "%~dp0image_manifest.final.tsv" "%STG%\image_manifest.final.tsv" >nul
copy "%~dp0..\image_target.conf" "%STG%\image_target.conf" >nul
copy "%~dp0..\image_install.sh" "%STG%\image_install.sh" >nul
echo %DATE% %TIME% 05v_camera_dabd5076, подтверждено YES > "%LOG%"
ssh -n -o BatchMode=yes -o ConnectTimeout=15 %H% "test $(hostname) = bumblebee-20ec && mkdir /tmp/img_%R% && echo HOST_OK" >> "%LOG%" 2>&1
findstr /c:"HOST_OK" "%LOG%" >nul
if errorlevel 1 (set "MSG=дрон не ответил, это не bumblebee-20ec или временная папка уже есть. Ничего не изменено." & goto die)
scp -o BatchMode=yes -o ConnectTimeout=15 -r "%STG%\payload" "%STG%\image_manifest.final.tsv" "%STG%\image_target.conf" "%STG%\image_install.sh" %H%:/tmp/img_%R%/ >> "%LOG%" 2>&1
if errorlevel 1 (set "MSG=копирование на дрон не удалось. Файл камеры не заменён." & goto die)
ssh -n -o BatchMode=yes -o ConnectTimeout=15 %H% "bash /tmp/img_%R%/image_install.sh /tmp/img_%R% < /dev/null 2>&1" >> "%LOG%" 2>&1
type "%LOG%"
findstr /c:"BB_IMAGE_INSTALL_DONE" "%LOG%" >nul
if errorlevel 1 (set "MSG=установка не дошла до конца, смотрите строки выше. Не взлетать. Скажите Claude, при необходимости ..\06_rollback_r2j.cmd. Журнал: %LOG%" & goto die)
echo.
echo Готово: camera_fix.py с dabd5076 стоит. Скажите Claude. Затем 01_snimok_do.cmd в папке набора (снимок и sha файлов). Журнал: %LOG%
if not defined BB_NO_PAUSE pause
exit /b 0
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 1