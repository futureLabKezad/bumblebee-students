@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: какой MAVROS стоит и активен на Pi, из какого коммита собран и совпадают ли пять исходных файлов bp02 (ожидается коммит d63a236, тег backport-02). Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, ничего не собирает. Не d63a236, не все 5 файлов или активна версия из apt: СТОП, непроверенный MAVROS на дрон не идёт.
rem 10_mavros_versiya.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:19). Пока MAVROS bp02 на Pi не собран (сборку делает набор MAVROS rc3, не этот набор), здесь будет СТОП: активна apt-версия 2.14 без исправлений. Это состояние, а не поломка.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_mavros_check.ps1 lib\bb_common.ps1 pi\mavros_check.sh image_r2j\mavros_bp02_sources.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 10_mavros_versiya
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_mavros_check.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: MAVROS bp02 подтверждён. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: MAVROS bp02 на Pi не подтверждён. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
