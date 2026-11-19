@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: батарея 20EC через MAVROS 30 секунд: видно ли напряжение, есть ли предупреждения батареи, настройки BAT1_N_CELLS, BAT1_V_EMPTY, BAT1_V_CHARGED и соседние. Этот файл ничего не взводит, моторы не запускаются, в PX4 ничего не пишет, детектор не будит. Дрон не взведён, винты сняты.
rem 08_batareya.cmd (Claude, 10.11.2026, набор r2). Проверка после BAT1_SOURCE 1 -> 0 (группа 1): напряжение должно быть видно, предупреждений батареи быть не должно. Скрипт pi\battery_check.sh только подписывается и читает таблицу настроек MAVROS.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_battery.ps1 lib\bb_common.ps1 pi\battery_check.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 08_batareya
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_battery.ps1" -Label bat -DurationSec 30
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: батарея прочитана. Скажите Claude, он прочитает сводку из папки out.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
