@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: сверка 09 для ВАРИАНТА r2j + камера полных строк: что реально исполняется на Pi совпадает с вариантом - python-узлы, в том числе camera_fix.py dabd5076, C++ исходники, launch-файлы, в том числе bumblebee.launch.py 5f0954d8, и исправленный fcu_detect.py по sha256; бинарники не старше исходников. Прежняя 09 проверяет r2j как раньше и при стоящем варианте даёт СТОП. По этой сверке взлёт 07 НЕ разрешится: полёт с вариантом - отдельное решение чата 1. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет.
rem 09c_sverka_install_r2j_cam.cmd (Claude, 12.11.2026, набор r6). Скрипт Pi тот же, что у 09 (pi\install_check.sh), списки image_r2j_cam. Ответ: out\sverka_r2jcam_ВРЕМЯ.txt.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_install_check_cam.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 lib\bb_lists_r2jcam.ps1 pi\install_check.sh image_r2j_cam\INSTALL_SHA256_r2jcam.txt image_r2j_cam\RUNTIME_PY_r2jcam.tsv image_r2j\CPP_SOURCES_r2j.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 09c_sverka_install_r2j_cam
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_install_check_cam.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: на Pi исполняется ровно вариант r2j + камера. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: на Pi исполняется не вариант. Ничего не запускать, скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
