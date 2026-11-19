@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: откат камеры применился? После 06c и после того, как вы сами запустили службу bumblebee и подождали 2 минуты: оба работающих camera_fix исполняют прежний файл r2j 4a15d699 и запущены после его возврата, launch r2j, в журнале запуска нет full_rows и full-row, без перезапусков и смертей процессов. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, службы не трогает. Около 30 секунд.
rem 24b_proverka_kamery_r2j.cmd (Claude, 12.11.2026, набор r6). Ответ: out\cam_verify_r2j_ВРЕМЯ.txt, последняя строка VERDICT OK или NOT_OK. Потом 09 и 10.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_camverify.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 lib\bb_lists_r2jcam.ps1 lib\bb_r6.ps1 pi\r6_cam_verify.sh image_r2j_cam\VARIANT_FILES.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 24b_proverka_kamery_r2j
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_camverify.ps1" -Mode r2j
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: работает прежняя камера r2j. Дальше 09 и 10. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: откат не подтверждён, причины выше. Ничего не чинить, скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
