@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: откат сборки MAVROS bp02 на Pi: переносит ~/bench_ws/mavros, mavros_deps, mavros_src_mode.txt, ~/bench_ws/incoming/rc3_mavros, журналы и отпечатки сборки в новую папку ~/bench_ws/_aside_mavros__метка_, ничего не удаляя. Зачем: вернуть Pi к состоянию «только штатный MAVROS из apt» (apt эта сборка не меняла). Как вернуть обратно: содержимое _aside_mavros__метка_ можно вернуть на место вручную; повторная сборка: 11_sborka_mavros_bp02.cmd. Отказывается, если идёт сборка или start_bumblebee.sh уже подключает оверлей bench_ws/mavros. ЗАГОТОВКА: Claude её не запускает; запускает владелец.
rem 12_otkat_mavros_bp02.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:45). Перенос делает pi\mavros_build_aside.sh (mv, без rm).
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_mavros_build.ps1 lib\bb_common.ps1 pi\mavros_build_aside.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "A1="
set /p "A1=Перенести собранный MAVROS в сторону (ничего не удаляется). Наберите ASIDE и Enter: "
if /i not "%A1%"=="ASIDE" (set "MSG=остановлено, ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
title 12_otkat_mavros_bp02
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_mavros_build.ps1" -Mode aside -SafetyConfirmed ASIDE
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: собранное перенесено в сторону. Запустите 10_mavros_versiya.cmd и скажите Claude.) else (echo Откат не сделан или не закончен, строки выше. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
