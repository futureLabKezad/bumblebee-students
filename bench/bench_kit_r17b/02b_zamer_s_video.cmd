@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН (косвенно): замер работы зрения на Pi 5 минут С видео на ПК. Дрон не взведён, моторы не запускаются, параметры и команды в PX4 не пишутся. Что меняется: на Pi детектор меток будится сообщением в /aruco_detect/wake раз в секунду, и vpe_fix в r2j на НЕвзведённом дроне передаёт позу по меткам в MAVROS (/mavros/mavros/pose_cov, таймер 30 Гц; vpe_fix.py, функция _evaluate_gate, по коду), то есть зрение может дойти до EKF2 (зависит от EKF2_EV_CTRL; на дроне не проверялось). Зачем: замер нагрузки и задержки зрения. Как остановить: закрыть окно или Ctrl+C, детектор засыпает примерно через 5 с. Окно видео с дрона на ПК должно быть открыто и показывать картинку.
rem 02b_zamer_s_video.cmd (Claude, 10.11.2026). Шаг 12, пункт 2 задания T31, второй замер. Первый: 02a_zamer_bez_video.cmd.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_measure.ps1 lib\bb_common.ps1 pi\vision_measure.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title 02b_zamer_s_video
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_measure.ps1" -Label s_video -DurationSec 300 -Mode measure -Wake 1
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: замер закончен. Скажите Claude, он прочитает сводку из папки out.) else if "%RC%"=="3" (echo Замер НЕ начат: дрон взведён или нет связи с полётным контроллером. Детектор не будился. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
