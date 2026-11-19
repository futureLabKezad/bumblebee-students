@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: пересобирает ТОЛЬКО пакет bumblebee из исходников образа r2j на самом Pi в отдельной папке ~/bench_ws/r2j (оверлей): копирует ~/ros2_ws/src/bumblebee (исходники r2j после 05_install_r2j.cmd) и запускает colcon build --packages-select bumblebee, как 29.10 на этом Pi (набор s0b: 2 мин 26 с, -j2); ОЦЕНКА около 2,5 минут, с запасом 10. Зачем: r2j меняет C++ (simple_offboard.cpp, script_lease.h, state_link.h, CMakeLists.txt, package.xml) против образа на дроне, а C++-узлы исполняются из install, им нужна сборка (Python-скрипты, читающие src напрямую, например drone.py и скрипты служб, работают на новых файлах после установки 05 и без сборки: проверка 18_sostoyanie_sluzhb.cmd). Как вернуть: прежняя сборка ~/ros2_ws вообще не трогается (это резерв); 14_otkat_sborki_bumblebee.cmd переносит ~/bench_ws/r2j в ~/bench_ws/_aside_bb_r2j__метка_, ничего не удаляя. Подключение оверлея к запуску (строка в start_bumblebee.sh) этим файлом НЕ делается: это 16_podkljuchit_overlay.cmd, только после «да» владельца. Моторы не взводятся. ЗАГОТОВКА: Claude её не запускает; запускает владелец; службу bumblebee останавливает сам (пароль только его), батарею меряет сам.
rem 13_sborka_bumblebee_r2j.cmd (Claude, 10.11.2026, набор r2, решение чата 1 в 19:58). Сначала только чтение (pi\bb_build_precheck.sh: служба не active, исходники равны r2j, ~/bench_ws/r2j нет, диск, нет colcon, пакеты apt), состояние «до» пишется в out\bb_state_before_*.txt. Любой stderr сборки = СТОП и решение чата 1.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_bb_build.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 pi\bb_build_precheck.sh pi\bb_build.sh image_r2j\CPP_SOURCES_r2j.tsv) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
echo.
echo Правила: Claude к дрону не подключается, пароль и sudo вводите только вы. Причина рывка моторов 04.11 неизвестна. Моторы в этом шаге не нужны, винты должны быть СНЯТЫ.
set "A1="
set /p "A1=1 из 3. Заряд батареи измерен вами мультиметром или проверкой банок: не меньше 21,0 В и каждая банка не меньше 3,5 В. Наберите BATTERY и Enter: "
if /i not "%A1%"=="BATTERY" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 3. Службу bumblebee вы остановили сами на Pi (sudo systemctl stop bumblebee, пароль вводите вы). Наберите SERVICE и Enter: "
if /i not "%A2%"=="SERVICE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A3="
set /p "A3=3 из 3. Начать сборку: около 2,5 минут (оценка), окно не закрывать. Наберите BUILD и Enter: "
if /i not "%A3%"=="BUILD" (set "MSG=остановлено, ничего не сделано." & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
title 13_sborka_bumblebee_r2j
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_bb_build.ps1" -Mode build -SafetyConfirmed BATTERY-SERVICE-BUILD
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: bumblebee r2j собран. Дальше 15_otpechatki_sborki.cmd. Скажите Claude.) else if "%RC%"=="7" (echo Сборка прошла, но у неё есть stderr. Дальше не идти, скажите Claude.) else if "%RC%"=="6" (echo Сборка не дошла до конца. Скажите Claude. Перенос в сторону: 14_otkat_sborki_bumblebee.cmd.) else (echo Сборка не начата или не удалась, строки выше. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
