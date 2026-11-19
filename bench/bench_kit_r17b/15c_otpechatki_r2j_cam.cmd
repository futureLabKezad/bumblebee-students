@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: отпечатки оверлея bumblebee ~/bench_ws/r2j для ВАРИАНТА r2j + камера полных строк: sha256 всех файлов install, python-узлы и launch-файлы равны варианту, C++ исходники копии равны r2j, бинарники не старше исходников. Отпечатки пишет ПК в out, на Pi ничего не создаётся. Прежний 15 проверяет r2j как раньше; эти отпечатки шаг 16 не берёт. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет.
rem 15c_otpechatki_r2j_cam.cmd (Claude, 12.11.2026, набор r6). Скрипт Pi тот же, что у 15 (pi\overlay_fingerprint.sh, цель bumblebee). Ответ: out\otpechatki_r2jcam_ВРЕМЯ.txt.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_fingerprint_cam.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 lib\bb_lists_r2jcam.ps1 pi\overlay_fingerprint.sh image_r2j_cam\INSTALL_SHA256_r2jcam.txt image_r2j_cam\RUNTIME_PY_r2jcam.tsv image_r2j\CPP_SOURCES_r2j.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 15c_otpechatki_r2j_cam
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_fingerprint_cam.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: оверлей = вариант r2j + камера. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: есть замечания, строки выше. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
