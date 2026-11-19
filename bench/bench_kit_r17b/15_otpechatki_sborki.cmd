@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: отпечатки собранных оверлеев на Pi (bumblebee в ~/bench_ws/r2j и MAVROS в ~/bench_ws/mavros): sha256 всех файлов install записываются на ПК в out\fingerprint_*.txt, и проверяется, что бинарники не старше исходников; для bumblebee ещё python-узлы и C++ исходники равны r2j, для MAVROS пять исходников bp02 равны списку. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, ничего не копирует и не собирает. Нет сборки: «оверлей не собран», это не ошибка.
rem 15_otpechatki_sborki.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:58; аналог шага m3). Запускать после КАЖДОЙ сборки (13 и 11). Замечание (расхождение или бинарник старше исходников): СТОП, подключать нельзя. Файл отпечатков нужен для 16_podkljuchit_overlay.cmd.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_fingerprint.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 pi\overlay_fingerprint.sh image_r2j\CPP_SOURCES_r2j.tsv image_r2j\INSTALL_SHA256_r2j.txt image_r2j\mavros_bp02_sources.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 15_otpechatki_sborki
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_fingerprint.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: отпечатки записаны на ПК, замечаний нет. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: у собранного есть замечания или нет сборки. Подключать нельзя, скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
