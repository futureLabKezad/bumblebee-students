@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН (косвенно): журнал зрения 2 минуты, пока дрон у вас в руках над полем с метками. Дрон не взведён, моторы не запускаются, винты не нужны. Параметры и команды в PX4 не пишутся. Что меняется: на Pi детектор меток будится сообщением в /aruco_detect/wake раз в секунду, и vpe_fix в r2j на НЕвзведённом дроне передаёт позу по меткам в MAVROS (/mavros/mavros/pose_cov, таймер 30 Гц; vpe_fix.py, функция _evaluate_gate, по коду), то есть зрение может дойти до EKF2 (зависит от EKF2_EV_CTRL; на дроне не проверялось). Зачем: замер нагрузки и задержки зрения. Как остановить: закрыть окно или Ctrl+C, детектор засыпает примерно через 5 с. Файл пишет журнал на ПК.
rem 03_v_rukakh.cmd (Claude, 10.11.2026; r17a 19.11: код 5 = нет строк joint rms, не «Готово»). Шаг 12, пункт 3 задания T31. Три места: 1 центр на метке 0, 2 камера над меткой 0, 3 на 8 см позади.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_measure.ps1 lib\bb_common.ps1 pi\vision_measure.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "PL="
set /p "PL=Место: 1 центр дрона на метке 0, 2 камера над меткой 0, 3 на 8 см позади метки. Наберите 1, 2 или 3 и Enter: "
set "LABEL="
if "%PL%"=="1" set "LABEL=hand_center"
if "%PL%"=="2" set "LABEL=hand_camera_over"
if "%PL%"=="3" set "LABEL=hand_back8"
if not defined LABEL (set "MSG=нужно набрать 1, 2 или 3. Ничего не сделано." & goto die)
set "HH="
set /p "HH=Высота камеры над полом по рулетке в сантиметрах, только число: "
if not defined HH (set "MSG=высота камеры не введена. Ничего не сделано." & goto die)
title 03_v_rukakh
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_measure.ps1" -Label %LABEL% -DurationSec 120 -Mode measure -Wake 1 -Place %LABEL% -CameraHeightCm "%HH%"
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: журнал записан. Скажите Claude.) else if "%RC%"=="3" (echo Журнал НЕ начат: дрон взведён или нет связи с полётным контроллером. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: журнал записан, но НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
