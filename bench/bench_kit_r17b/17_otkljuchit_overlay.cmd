@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: откат подключения оверлея: возвращает ~/start_bumblebee.sh из копии «до» последнего подключения (~/bench_ws/_bk_start_bumblebee__метка_/start_bumblebee.sh.before), то есть возвращает штатный MAVROS из apt и прежнюю сборку ros2_ws. Зачем: отменить 16_podkljuchit_overlay.cmd. Как вернуть обратно: снова 16_podkljuchit_overlay.cmd (после новых отпечатков и разрешения). Отказывается, если start_bumblebee.sh после подключения кто-то менял или служба активна. Если подключали два оверлея (MAVROS, потом bumblebee), запускают дважды: сначала снимается bumblebee, потом MAVROS. Оверлеи на диске и копии не удаляются. ЗАГОТОВКА: Claude её не запускает; службу bumblebee владелец останавливает и запускает сам (пароль только его).
rem 17_otkljuchit_overlay.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:58). Гейта «да» для отката нет: откат всегда разрешён.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_overlay.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 pi\overlay_disconnect.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "A2="
set /p "A2=1 из 2. Службу bumblebee вы остановили сами на Pi (sudo systemctl stop bumblebee, пароль вводите вы). Наберите SERVICE и Enter: "
if /i not "%A2%"=="SERVICE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A3="
set /p "A3=2 из 2. Вернуть start_bumblebee.sh из копии «до». Наберите DISCONNECT и Enter: "
if /i not "%A3%"=="DISCONNECT" (set "MSG=остановлено, ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
title 17_otkljuchit_overlay
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_overlay.ps1" -Mode disconnect -Target last -SafetyConfirmed DISCONNECT-SERVICE
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: start_bumblebee.sh возвращён. Службу запускаете сами. Скажите Claude.) else (echo Откат не сделан, строки выше. Файл start_bumblebee.sh не менялся. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
