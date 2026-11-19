@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: собирает MAVROS bp02 (исправления #2138, #2149, #2093 и ещё два, коммит d63a236, тег backport-02) на самом Pi из проверенного набора rc3 r3 в ~/bench_ws/mavros: копирует 16 файлов в ~/bench_ws/incoming/rc3_mavros, распаковывает исходники (m1, меньше минуты) и собирает пакет mavros (m2, ОЦЕНКА 7-10 минут, с запасом 20; на Pi не измерялось). Зачем: в сессии 1 штатный MAVROS 2.14 упал при записи параметра (Н1), сборок для Pi в готовом виде нет. Как вернуть: 12_otkat_mavros_bp02.cmd переносит собранное в ~/bench_ws/_aside_mavros__метка_, ничего не удаляя; штатный MAVROS из apt, /opt/ros, start_bumblebee.sh и параметры PX4 эта сборка НЕ меняет (состояние apt «до» записывается в out\mavros_apt_state_*.txt и сверяется командой 10_mavros_versiya.cmd после отката). Моторы не взводятся. ЗАГОТОВКА: Claude её не запускает; запускает владелец после решения; службу bumblebee владелец останавливает сам (пароль только его), заряд батареи меряет сам.
rem 11_sborka_mavros_bp02.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:45). Набор rc3 r3: image_r2j\mavros_build\pi_kit (TRANSFER_SHA256SUMS 8bb42477, суммы всех 15 файлов проверяет run_mavros_build.ps1 на ПК до обращения к дрону). Подключение собранного (m4, строка в start_bumblebee.sh) и отпечатки m3 в этот файл НЕ входят.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_mavros_build.ps1 lib\bb_common.ps1 pi\mavros_build_precheck.sh image_r2j\mavros_build\pi_kit\TRANSFER_SHA256SUMS.txt) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
echo.
echo Правила: Claude к дрону не подключается, пароль и sudo вводите только вы. Причина рывка моторов 04.11 неизвестна. Моторы в этом шаге не нужны, винты должны быть СНЯТЫ.
set "A1="
set /p "A1=1 из 3. Заряд батареи измерен вами мультиметром или проверкой банок: не меньше 21,0 В и каждая банка не меньше 3,5 В. Наберите BATTERY и Enter: "
if /i not "%A1%"=="BATTERY" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 3. Службу bumblebee вы остановили сами на Pi (sudo systemctl stop bumblebee, пароль вводите вы). Наберите SERVICE и Enter: "
if /i not "%A2%"=="SERVICE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A3="
set /p "A3=3 из 3. Начать сборку: около 7-10 минут (оценка), окно не закрывать. Наберите BUILD и Enter: "
if /i not "%A3%"=="BUILD" (set "MSG=остановлено, ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
title 11_sborka_mavros_bp02
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_mavros_build.ps1" -Mode build -SafetyConfirmed BATTERY-SERVICE-BUILD
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: MAVROS bp02 собран на Pi. Скажите Claude.) else if "%RC%"=="6" (echo Сборка не дошла до конца. Скажите Claude. Перенос в сторону: 12_otkat_mavros_bp02.cmd.) else (echo Сборка не начата или не удалась, строки выше. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
