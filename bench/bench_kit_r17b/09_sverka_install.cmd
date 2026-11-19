@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: что реально исполняется на Pi (install пакета bumblebee, ros2 pkg prefix bumblebee) и совпадает ли с образом r2j: python-узлы по sha256, C++ исходники по sha256, бинарные узлы не должны быть старше изменённых исходников. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, ничего не копирует и не собирает. Расхождение, нет файла, нет install или пакет не пересобран: СТОП, не запускать ничего, сказать Claude.
rem 09_sverka_install.cmd (Claude, 10.11.2026, набор r2, решения чата 1 в 19:19 и 19:45). Запускать сразу после установки образа (05) и после сборки пакета на Pi. Бинарники Pi по sha256 с r2j не сверяются (у r2j они x86, у Pi свои): выдуманного списка сумм нет. r2j меняет C++ (simple_offboard.cpp, script_lease.h, state_link.h, CMakeLists.txt, package.xml) против образа на дроне, поэтому после установки нужна сборка пакета на Pi (шаг МЕНЯЕТ ДРОН для владельца): до неё здесь будет СТОП по «бинарник старше исходников».
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_install_check.ps1 lib\bb_common.ps1 pi\install_check.sh image_r2j\INSTALL_SHA256_r2j.txt image_r2j\CPP_SOURCES_r2j.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 09_sverka_install
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_install_check.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: сверка install прошла. Что стоит на Pi - r2j или допущенный вариант POSEFIX_V11, R2M_CAM, POSEFIX_JD2 - смотрите в строках выше. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: на Pi исполняется не то, что в образе r2j. Ничего не запускать, скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
