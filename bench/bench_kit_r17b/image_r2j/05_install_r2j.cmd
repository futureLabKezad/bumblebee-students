@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ставит исправленный образ r2j на Pi насовсем, заменяя файлы по манифесту, старые копирует в резерв. Зачем: решение владельца 10.11, вариант 1, образ r2j остаётся на дроне. Как вернуть: 06_rollback_r2j.cmd одним щелчком. ЗАГОТОВКА: не запускается, пока не выполнены условия правила 14 - С8 включая S2/S3 пройден на r2j и наборе 4062, COM_OBL_RC_ACT=4 на дроне - и пока не вписаны путь и sha r2j; флаг S2/S3 привязан к sha256 манифеста этого образа.
rem 05_install_r2j.cmd (Claude, 10.11.2026, на основе install_image.cmd набора r4). Заготовка для r2j. Условия проверяет check_gates.ps1 на ПК, без сети.
cd /d "%~dp0"
set "H=lb@10.255.254.26"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (check_gates.ps1 image_install.sh image_target.conf) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if defined BB_KIT_OUT (set "OUT=%BB_KIT_OUT%") else (set "OUT=%~dp0..\out")
if not exist "%OUT%" mkdir "%OUT%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_gates.ps1" -Kit "%~dp0." -OutDir "%OUT%"
if errorlevel 1 (set "MSG=условия установки не выполнены, ничего не изменено. Причины выше." & goto die)
set "R=%RANDOM%%RANDOM%"
set "LOG=%OUT%\install_r2j_%R%.log"
if exist "%LOG%" (set "MSG=файл %LOG% уже есть, не перезаписываю." & goto die)
title 05_install_r2j
echo Условия выполнены. Дрон должен быть на земле, моторы не крутятся, винты сняты или дрон закреплён.
set "OK="
set /p "OK=Наберите YES и Enter, чтобы заменить файлы образа на дроне, иначе остановка: "
if /i not "%OK%"=="YES" (set "MSG=остановлено, ничего не изменено." & goto die)
echo %DATE% %TIME% 05_install_r2j, подтверждено YES > "%LOG%"
ssh -n -o BatchMode=yes -o ConnectTimeout=15 %H% "test $(hostname) = bumblebee-20ec && mkdir /tmp/img_%R% && echo HOST_OK" >> "%LOG%" 2>&1
findstr /c:"HOST_OK" "%LOG%" >nul
if errorlevel 1 (set "MSG=дрон не ответил, это не bumblebee-20ec или временная папка уже есть. Ничего не изменено." & goto die)
scp -o BatchMode=yes -o ConnectTimeout=15 -r "%~dp0payload" "%~dp0image_manifest.final.tsv" "%~dp0image_target.conf" "%~dp0image_install.sh" %H%:/tmp/img_%R%/ >> "%LOG%" 2>&1
if errorlevel 1 (set "MSG=копирование на дрон не удалось. Файлы образа не заменены." & goto die)
ssh -n -o BatchMode=yes -o ConnectTimeout=15 %H% "bash /tmp/img_%R%/image_install.sh /tmp/img_%R% < /dev/null 2>&1" >> "%LOG%" 2>&1
type "%LOG%"
findstr /c:"BB_IMAGE_INSTALL_DONE" "%LOG%" >nul
if errorlevel 1 (set "MSG=установка не дошла до конца, смотрите строки выше. Не взлетать. Скажите Claude, при необходимости 06_rollback_r2j.cmd. Журнал: %LOG%" & goto die)
echo.
echo Готово. Скажите Claude. Затем 01_snimok_do.cmd этого набора (сверка настроек). Журнал: %LOG%
if not defined BB_NO_PAUSE pause
exit /b 0
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 1
