@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ТОЛЬКО НОВЫЕ ФАЙЛЫ, стек, службы и PX4 не трогает. Что: кладёт 3 файла замера камеры полных строк и их суммы в новую папку ~/bench_ws/incoming/camera_fullrow_r6, если её ещё нет, и пишет 5 сырых кадров главной камеры, две картинки и meta.json в новую папку ~/bench_ws/camera_fullrow_r6/_метка_/K1; сама проверка только подписывается на /main_camera/image_raw_yuv, ничего не публикует, до 1 минуты. Зачем: критерий К-1 процедуры PI_PERF - главная посылка камеры полных строк: step 1280, 614400 байт, нули при шаге строки 1600. Как вернуть: эти папки не стоят ни на одном пути запуска и стеку не мешают; убрать их можно целиком в сторону, ничего не удаляя. ЗАГОТОВКА: заблокирована без gates\CAM_K1_APPROVED.txt от чата 1.
rem 21_kamera_K1_raskladka.cmd (Claude, 12.11.2026, набор r6; P2: К-1 пишет файлы на Pi, поэтому пометка МЕНЯЕТ ДРОН, только новые файлы). Ответ: out\k1_raw_layout_ВРЕМЯ.txt и копия папки out\k1_ВРЕМЯ\K1.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_k1.ps1 lib\bb_common.ps1 lib\bb_lists.ps1 lib\bb_r6.ps1 pi\r6_k1.sh pi\r6_cam_incoming.sh pi\r6_cam_mkdir.sh camera_fullrow\camera_fix.py camera_fullrow\raw_layout_check.py camera_fullrow\bench_recorder.py camera_fullrow\SHA256SUMS_camera_fullrow.txt) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\CAM_K1_APPROVED.txt" (set "MSG=нет разрешения gates\CAM_K1_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
echo.
echo Правила: Claude к дрону не подключается. Причина рывка моторов 04.11 неизвестна. Моторы в этом шаге не нужны, винты СНЯТЫ.
set "A1="
set /p "A1=Дрон на земле, моторы не запускаются, винты сняты, главная камера смотрит на метку 0. Наберите K1 и Enter: "
if /i not "%A1%"=="K1" (set "MSG=остановлено, ничего не сделано." & goto die)
title 21_kamera_K1_raskladka
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_k1.ps1" -Confirmed K1-NEWFILES
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: К-1 ГОТОВО. Скажите Claude.) else if "%RC%"=="5" (echo К-1 НЕ ГОТОВО: шаг 22 не делать. Скажите Claude.) else (echo Не получилось, строки выше. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
