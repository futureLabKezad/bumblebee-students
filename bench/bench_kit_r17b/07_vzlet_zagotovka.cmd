@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ВЗЛЁТ - моторы запустятся. Зачем: шаг 14, первый полёт скрипта по меткам в сетке в помещении. Как остановить: переключатель режима на пульте, CH8, Ctrl+C в этом окне, палец на аварийном выключателе. ЗАГОТОВКА: не запускается, пока нет takeoff.conf со скриптом, gates\TAKEOFF_APPROVED.txt от чата 1 после слов владельца и свежей сверки настроек. Запускает только владелец. Аргументов у этого файла нет: ничего из командной строки не пробрасывается; скрипт и его аргументы привязаны к разрешению чата 1.
rem 07_vzlet_zagotovka.cmd (Claude, 10.11.2026). Шаг 14 задания T31. Решение владельца 10.11: запуск скрипта - вариант 2, .cmd от Claude, двойной щелчок владельца. Claude этот файл не запускает. Причина рывка моторов 04.11 НЕ известна. Правило 3: моторы двинулись без понятной причины - СТОП, батарею отключить.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_07_takeoff.ps1 lib\bb_common.ps1) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "PCC=%~dp0params_check\params_check.cmd"
if not exist "%PCC%" (set "MSG=нет сверки настроек этого набора: %PCC%" & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
echo.
echo Меры безопасности обязательны на каждом шаге с моторами. Причина рывка моторов 04.11 неизвестна.
echo Винты ставят только после проверки без винтов.
set "A1="
set /p "A1=1 из 4. Дрон в сетке или на привязи, сетка не прижимает его к камере и дальномеру. Наберите NET и Enter: "
if /i not "%A1%"=="NET" (set "MSG=остановлено, взлёт не начат." & goto die)
set "A2="
set /p "A2=2 из 4. Рядом два человека, пилот с пультом наготове. Наберите TWO и Enter: "
if /i not "%A2%"=="TWO" (set "MSG=остановлено, взлёт не начат." & goto die)
set "A3="
set /p "A3=3 из 4. Палец на аварийном выключателе. Наберите KILL и Enter: "
if /i not "%A3%"=="KILL" (set "MSG=остановлено, взлёт не начат." & goto die)
set "A4="
set /p "A4=4 из 4. Дрон ВЗЛЕТИТ, моторы запустятся. Наберите YES и Enter, чтобы начать отсчёт: "
if /i not "%A4%"=="YES" (set "MSG=остановлено, взлёт не начат." & goto die)
title 07_vzlet_zagotovka
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_07_takeoff.ps1" -SafetyConfirmed NET-TWO-KILL-YES
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="4" (echo Взлёт не начат: условия не выполнены, строки выше. К дрону не обращались.) else (echo Скрипт на Pi закончил работу, код %RC%. Сразу читаем настройки после полёта.)
if "%RC%"=="4" goto fin
echo Проверяю только чтением, что дрон разоружён (перед чтением настроек).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_armcheck.ps1"
if errorlevel 1 (set "RC=5" & echo. & echo СТОП: дрон ВЗВЕДЁН или его состояние неизвестно. Настройки после полёта НЕ читаю. Разоружите дрон пультом или аварийным выключателем, отключите батарею и скажите Claude. & goto fin)
set "WAS_NP=%BB_NO_PAUSE%"
set "BB_NO_PAUSE=1"
echo Читаю только чтением журнал Pi за время полёта (пауза зрения после взлёта, для Ж3 и Ж5).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_journal.ps1"
if errorlevel 1 echo Журнал Pi не прочитан. Это не мешает: скажите Claude, настройки читаю дальше.
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
call "%PCC%" -Stamp after_flight_%STAMP%
set RC2=%ERRORLEVEL%
set "BB_NO_PAUSE=%WAS_NP%"
echo Настройки после полёта прочитаны, код %RC2%. Скажите Claude: он смотрит журнал takeoff в папке out и сверку.
:fin
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
