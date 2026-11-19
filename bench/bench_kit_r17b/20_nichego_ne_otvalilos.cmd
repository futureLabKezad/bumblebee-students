@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: проверка «ничего не отвалилось» Ч1-Ч6 из разбора P1: systemctl --failed пуст; bumblebee, wifi-manager, wifi-watchdog, notify-manager, avahi-daemon, NetworkManager, sys_metrics работают, сами не перезапускались, в журнале за 10 минут нет ошибок; энергосбережение Wi-Fi выключено; узлы ROS как в снимке до правки; pidstat 30 секунд для сравнения; что посмотреть в приложении самим. Делать ДО каждой системной правки, сразу ПОСЛЕ неё и ещё раз после перезагрузки дрона. Этот файл ничего не взводит, моторы не запускаются, в PX4 и на Pi ничего не пишет, службы не трогает. Около 1 минуты.
rem 20_nichego_ne_otvalilos.cmd (Claude, 12.11.2026, набор r6). Новая версия проверки служб рядом с шагом 18: 18 r5 ждёт led-default, которого на исправном дроне нет, и там даёт NOT_OK (V1); 18 не менялся. Ответ: out\sys_check_ВРЕМЯ.txt, последняя строка VERDICT OK или NOT_OK.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_syscheck.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r6_sys_check.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 20_nichego_ne_otvalilos
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_syscheck.ps1"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: ничего не отвалилось. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: что-то не так, причины выше. Ничего не чинить, скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
