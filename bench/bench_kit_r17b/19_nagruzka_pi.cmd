@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: что грузит Pi 20EC, шаг 0 разбора P1: службы и их главные процессы, процессы стека, регулятор частоты ядер, температура и троттлинг, энергосбережение Wi-Fi по журналу ядра без sudo, snap refresh --time, таймеры, apt periodic, кто читает темы *_reliable и список узлов ROS через ros2 --no-daemon, затем pidstat 2 минуты. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, службы и стек не трогает. Около 3 минут.
rem 19_nagruzka_pi.cmd (Claude, 12.11.2026, набор r6; P1 шаг 0 и поправки V1: без ros2 topic hz по кадрам, без notify_manager --selftest, /tmp/bumblebee.log не трогает, ros2 только --no-daemon). Ответ: out\pi_load_ВРЕМЯ.txt.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_load.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r6_pi_load.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 19_nagruzka_pi
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_load.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: нагрузка Pi прочитана. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
