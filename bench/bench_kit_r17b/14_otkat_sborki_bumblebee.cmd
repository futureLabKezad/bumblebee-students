@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: откат сборки bumblebee r2j на Pi: переносит ~/bench_ws/r2j и журнал сборки в новую папку ~/bench_ws/_aside_bb_r2j__метка_, ничего не удаляя. Зачем: убрать сборку r2j; прежняя сборка ~/ros2_ws не менялась и остаётся главной. Как вернуть обратно: содержимое _aside_bb_r2j__метка_ можно вернуть на место вручную; повторная сборка: 13_sborka_bumblebee_r2j.cmd. Отказывается, если идёт сборка или start_bumblebee.sh уже подключает оверлей bench_ws/r2j (сначала 17_otkljuchit_overlay.cmd). Исходники образа r2j в ~/ros2_ws/src возвращает 06_rollback_r2j.cmd, а не этот файл. ЗАГОТОВКА: Claude её не запускает; запускает владелец.
rem 14_otkat_sborki_bumblebee.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:58). Перенос делает pi\bb_build_aside.sh (mv, без rm).
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_bb_build.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 pi\bb_build_aside.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "A1="
set /p "A1=Перенести сборку bumblebee r2j в сторону (ничего не удаляется). Наберите ASIDE и Enter: "
if /i not "%A1%"=="ASIDE" (set "MSG=остановлено, ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
title 14_otkat_sborki_bumblebee
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_bb_build.ps1" -Mode aside -SafetyConfirmed ASIDE
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: сборка r2j перенесена в сторону. Скажите Claude.) else (echo Откат не сделан или не закончен, строки выше. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
