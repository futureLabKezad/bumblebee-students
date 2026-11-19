@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ВРЕМЕННО, стек, его файлы, службы и PX4 не меняются. Что: около 10 минут рядом со стеком работают временные процессы, каждый не дольше 4 минут: в фазе C второй camera_fix полных строк пишет новые темы /main_camera/image_raw_full; стендовый детектор через opencv47_venv пишет только в темы /bench/... и до vpe_fix и PX4 не доходит; запись только читает. Это добавляет нагрузку Pi, результаты - новые файлы в ~/bench_ws/camera_fullrow_r6/_метка_/cost. Зачем: цена камеры полных строк на настоящем Pi без установки, фазы A, C, A2 процедуры PI_PERF. Как вернуть: процессы заканчиваются сами по timeout или по сигналу после записи, ни один файл стека не меняется; Ctrl+C останавливает. ЗАГОТОВКА: заблокирована без gates\CAM_COST_APPROVED.txt от чата 1 и успешного К-1.
rem 22_kamera_cena_A_C_A2.cmd (Claude, 12.11.2026, набор r6; PI_PERF фазы A, C, A2 и «конец замера» без ssh-окна и без pgrep -f). Пороги К-2...К-8 решает владелец: файл только пишет числа. Ответ: out\camera_cost_ВРЕМЯ_*.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_cost.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 lib\bb_r6.ps1 pi\r6_cost_phase.sh pi\r6_cost_end.sh pi\r6_cam_incoming.sh camera_fullrow\SHA256SUMS_camera_fullrow.txt) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\CAM_COST_APPROVED.txt" (set "MSG=нет разрешения gates\CAM_COST_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
echo.
echo Правила: Claude к дрону не подключается. Причина рывка моторов 04.11 неизвестна. Взвода в этом шаге нет совсем, винты СНЯТЫ. Во время замера дрон не трогать, свет не менять.
set "A1="
set /p "A1=1 из 2. Моторы выключены, винты сняты, дрон разоружён, передатчик выключен, дрон неподвижно стоит над меткой 0. Наберите SCENE и Enter: "
if /i not "%A1%"=="SCENE" (set "MSG=остановлено, ничего не сделано." & goto die)
set "BB_RULER_X="
set /p "BB_RULER_X=Рулетка: смещение камеры от центра метки 0 по оси X карты, в сантиметрах, например 12 или -3,5: "
set "BB_RULER_Y="
set /p "BB_RULER_Y=Рулетка: смещение по оси Y карты, в сантиметрах: "
set "BB_RULER_H="
set /p "BB_RULER_H=Рулетка: высота объектива над меткой, в сантиметрах: "
set "BB_DASHBOARD="
set /p "BB_DASHBOARD=Приложение с видео сейчас открыто? Y или N: "
set "A2="
set /p "A2=2 из 2. Начать замер: около 10 минут, окно не закрывать. Наберите START и Enter: "
if /i not "%A2%"=="START" (set "MSG=остановлено, ничего не сделано." & goto die)
title 22_kamera_cena_A_C_A2
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_cost.ps1" -Confirmed COST-TEMP
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: три фазы записаны, стек как был. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: замер не закончен как надо. Ничего не чинить, скажите Claude.) else (echo Не получилось, строки выше. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
