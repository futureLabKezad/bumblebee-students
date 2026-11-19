@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: журнал детектора 3 минуты, пока владелец сам взводит дрон БЕЗ ВИНТОВ пультом. Этот файл ничего не взводит и не запускает моторы, в PX4 ничего не пишет и детектор не будит. Он только пишет журнал.
rem 04_vibratsiya.cmd (Claude, 10.11.2026). Шаг 13, пункт 4 задания T31. Взвод делает только владелец пультом (правило 1). Правило 3: моторы двинулись без понятной причины - СТОП, батарею отключить, дальше решает владелец. Причина рывка 04.11 НЕ известна.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_measure.ps1 lib\bb_common.ps1 pi\vision_measure.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
echo.
echo Меры безопасности на каждом шаге с моторами: винты СНЯТЫ, палец на аварийном выключателе, дрон закреплён или в сетке, рядом второй человек. Причина рывка моторов 04.11 неизвестна.
set "OK="
set /p "OK=Все четыре меры выполнены. Наберите SAFE и Enter, иначе остановка: "
if /i not "%OK%"=="SAFE" (set "MSG=остановлено, журнал не начат." & goto die)
title 04_vibratsiya
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_measure.ps1" -Label vibration -DurationSec 180 -Mode vibration -Wake 0
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: журнал записан. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
