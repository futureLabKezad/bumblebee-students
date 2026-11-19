@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: правка камеры полных строк применилась? После 05c и после того, как вы сами запустили службу bumblebee и подождали 2 минуты: оба работающих camera_fix исполняют файл dabd5076 из того install, что реально исполняется, и запущены после его замены; launch с full_rows; в журнале запуска full_rows=True у главной и False у второй, full-row read 384, legacy frames 0, без перезапусков и смертей процессов. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, службы не трогает. Около 30 секунд.
rem 24a_proverka_kamery_polnye_stroki.cmd (Claude, 12.11.2026, набор r6; урок Wi-Fi: проверять, что правка действительно работает). Ответ: out\cam_verify_cam_ВРЕМЯ.txt, последняя строка VERDICT OK или NOT_OK.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_camverify.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 lib\bb_lists_r2jcam.ps1 lib\bb_r6.ps1 pi\r6_cam_verify.sh image_r2j_cam\VARIANT_FILES.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 24a_proverka_kamery_polnye_stroki
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_camverify.ps1" -Mode cam
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: камера полных строк работает. Дальше 09c и 15c. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: правка не подтверждена, причины выше. Ничего не чинить, скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
