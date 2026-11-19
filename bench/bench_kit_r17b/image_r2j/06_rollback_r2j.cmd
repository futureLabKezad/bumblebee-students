@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: возвращает файлы образа на Pi из последней резервной копии, файлы, которых раньше не было, переносит в сторону и не удаляет. Зачем: отменить установку образа r2j одним щелчком. Как вернуть: повторная установка 05_install_r2j.cmd. ЗАГОТОВКА: нужны image_target.conf с путями и резерв, сделанный установкой. Необязательный аргумент: метка резерва ГГГГММДД_ЧЧММСС.
rem 06_rollback_r2j.cmd (Claude, 10.11.2026, на основе rollback_image.cmd набора r4). Заготовка. Условия правила 14 тут не нужны: откат возвращает дрон к прежнему состоянию.
cd /d "%~dp0"
set "H=lb@10.255.254.26"
set "MSG="
rem r4: необязательный аргумент - метка резервной копии ГГГГММДД_ЧЧММСС, только цифры и подчёркивание (нужна, если самая новая папка резерва неполная)
set "LABEL=%~1"
if defined LABEL (echo %LABEL%| findstr /r /x "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]" >nul || (set "MSG=метка должна быть вида 20261109_153000." & goto die))
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (image_rollback.sh image_target.conf) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if defined BB_KIT_OUT (set "OUT=%BB_KIT_OUT%") else (set "OUT=%~dp0..\out")
if not exist "%OUT%" mkdir "%OUT%"
set "R=%RANDOM%%RANDOM%"
set "LOG=%OUT%\rollback_r2j_%R%.log"
if exist "%LOG%" (set "MSG=файл %LOG% уже есть, не перезаписываю." & goto die)
title 06_rollback_r2j
echo Дрон должен быть на земле, моторы не крутятся.
set "OK="
set /p "OK=Наберите YES и Enter, чтобы вернуть прежние файлы образа, иначе остановка: "
if /i not "%OK%"=="YES" (set "MSG=остановлено, ничего не изменено." & goto die)
echo %DATE% %TIME% 06_rollback_r2j, подтверждено YES > "%LOG%"
ssh -n -o BatchMode=yes -o ConnectTimeout=15 %H% "test $(hostname) = bumblebee-20ec && mkdir /tmp/imgrb_%R% && echo HOST_OK" >> "%LOG%" 2>&1
findstr /c:"HOST_OK" "%LOG%" >nul
if errorlevel 1 (set "MSG=дрон не ответил, это не bumblebee-20ec или временная папка уже есть. Ничего не изменено." & goto die)
scp -o BatchMode=yes -o ConnectTimeout=15 "%~dp0image_target.conf" "%~dp0image_rollback.sh" %H%:/tmp/imgrb_%R%/ >> "%LOG%" 2>&1
if errorlevel 1 (set "MSG=копирование на дрон не удалось. Ничего не изменено." & goto die)
ssh -n -o BatchMode=yes -o ConnectTimeout=15 %H% "bash /tmp/imgrb_%R%/image_rollback.sh /tmp/imgrb_%R% %LABEL% < /dev/null 2>&1" >> "%LOG%" 2>&1
type "%LOG%"
findstr /c:"BB_IMAGE_ROLLBACK_DONE" "%LOG%" >nul
if errorlevel 1 (set "MSG=откат не дошёл до конца, смотрите строки выше. Не взлетать. Скажите Claude. Журнал: %LOG%" & goto die)
echo.
echo Готово. Скажите Claude. Затем 01_snimok_do.cmd этого набора (сверка настроек). Журнал: %LOG%
if not defined BB_NO_PAUSE pause
exit /b 0
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 1
