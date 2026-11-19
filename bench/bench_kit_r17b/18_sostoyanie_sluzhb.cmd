@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: состояние трёх служб после установки образа (wifi-manager, notify-manager, led-default): systemctl is-active, число самостоятельных перезапусков и хвост журнала за последние 10 минут, поиск Traceback и ImportError. Зачем: эти службы берут drone.py из ros2_ws/src и после установки образа работают на drone.py r2j. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, службы не останавливает и не перезапускает. В конце одна строка: либо все три службы активны и ошибок нет, либо СТОП с причиной.
rem 18_sostoyanie_sluzhb.cmd (Claude, 11.11.2026, набор r3, поручение чата 1 T47, основание _ПОПРАВКА_20261111_drone_py.md). Первый запуск ДО установки образа (05), для сравнения: служба могла перезапускаться и раньше (решение чата 1, 11.11). Второй запуск после установки образа (05) и после включения (перезагрузки) дрона, чтобы службы уже работали на новом drone.py. Только чтение: файлы на Pi не создаются, пароль не нужен. Ответ: out\services_check_<время>.txt, последняя строка VERDICT OK или NOT_OK.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_services.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 pi\services_check.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 18_sostoyanie_sluzhb
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_services.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: все три службы активны, ошибок нет. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: служба не active или в журнале ошибки. Ничего не перезапускать, скажите Claude: решает чат 1.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
