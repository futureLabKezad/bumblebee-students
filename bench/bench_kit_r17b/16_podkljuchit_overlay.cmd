@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: подключает собранный оверлей (MAVROS bp02 из ~/bench_ws/mavros или bumblebee r2j из ~/bench_ws/r2j) вместо штатного одной строкой source в ~/start_bumblebee.sh: копия файла до замены в ~/bench_ws/_bk_start_bumblebee__метка_, добавляется ровно одна строка, файлы оверлея должны быть ровно как в отпечатках шага 15. Зачем: чтобы после запуска службы работали исправления bp02 (Н1: падение штатного MAVROS при записи параметра) или C++ r2j вместо штатных из apt и прежней сборки. Как вернуть (откат на apt и прежнюю сборку): 17_otkljuchit_overlay.cmd возвращает start_bumblebee.sh из копии; оверлей на диске остаётся. ТОЛЬКО ПОСЛЕ «ДА» ВЛАДЕЛЬЦА (решение утром): без gates\OVERLAY_«ЦЕЛЬ»_APPROVED.txt от чата 1 файл откажется. ЗАГОТОВКА: Claude её не запускает; службу bumblebee владелец останавливает и запускает сам (пароль только его). Моторы не взводятся.
rem 16_podkljuchit_overlay.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:58; аналог шагов УМ и У2 набора s0b / rc3). Порядок строк как у УМ и У2: ros2_ws, затем MAVROS, затем bumblebee; оверлей, подключённый позже, главнее. Если подключаете оба: сначала MAVROS, потом bumblebee.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_overlay.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 pi\overlay_connect.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
echo.
echo Правила: Claude к дрону не подключается, пароль и sudo вводите только вы. Причина рывка моторов 04.11 неизвестна. Винты СНЯТЫ.
set "T="
set /p "T=1 из 3. Что подключаем: наберите MAVROS (оверлей MAVROS bp02) или BUMBLEBEE (оверлей bumblebee r2j) и Enter: "
set "TG="
if /i "%T%"=="MAVROS" set "TG=mavros"
if /i "%T%"=="BUMBLEBEE" set "TG=bumblebee"
if not defined TG (set "MSG=нужно MAVROS или BUMBLEBEE. Ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 3. Службу bumblebee вы остановили сами на Pi (sudo systemctl stop bumblebee, пароль вводите вы). Наберите SERVICE и Enter: "
if /i not "%A2%"=="SERVICE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A3="
set /p "A3=3 из 3. Подключить оверлей %TG% (владелец сказал «да»). Наберите CONNECT и Enter: "
if /i not "%A3%"=="CONNECT" (set "MSG=остановлено, ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
title 16_podkljuchit_overlay
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_overlay.ps1" -Mode connect -Target %TG% -SafetyConfirmed CONNECT-SERVICE
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: оверлей %TG% подключён. Службу запускаете сами. Скажите Claude.) else (echo Подключение не сделано, строки выше. Файл start_bumblebee.sh не менялся. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
