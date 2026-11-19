@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: временно, только во время записи. Что: Pi будит детектор меток сигналом /aruco_detect/wake раз в секунду, как шаг 03; проснувшийся детектор шлёт позу по меткам, vpe_fix передаёт её в EKF2 полётного контроллера, и на невзведённом дроне меняется оценка положения EKF на земле. Файлы, настройки PX4 и моторы не меняются, взвода нет. Зачем: проверить, не выдаёт ли детектор ложные номера меток и неверную позу, пока дрон стоит над меткой 0. Как вернуть: детектор засыпает сам через 5 секунд после записи; EKF - выключить и включить дрон или сверить позицию EKF с рулеткой. Около 3 минут: проверка 6 секунд и 4 точки со сдвигом 0, 5, 10 и 15 см.
rem 25_metki_nomera.cmd (Claude, 13.11.2026, набор r8; в r7 был ТОЛЬКО ЧТЕНИЕ без wake - перенесён в _aside\r7_step25). Ответ: out\metki_nomera_ВРЕМЯ.txt, последняя строка # VERDICT.
rem Правила СТОП: номер не 0, особенно номер с карты 0-20 без 17; поза по меткам дальше 0,15 м от рулетки; строка vpe_fix RESEEDED на позу дальше 0,15 м. Вопросы задаёт этот файл; run_r8_metki.ps1 вызывается по фазам pre, rec, stop, final со вводом из nul.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r8_metki.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r8_marker_wake.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "PS1=%~dp0run_r8_metki.ps1"
set "STAMP="
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
if not defined STAMP (set "MSG=не получено время ПК. Ничего не сделано." & goto die)
title 25_metki_nomera
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Phase pre -Stamp %STAMP% < nul
set RC=%ERRORLEVEL%
if not "%RC%"=="0" goto fin
call :point 1 0
if not "%RC%"=="0" goto fin
call :point 2 5
if not "%RC%"=="0" goto fin
call :point 3 10
if not "%RC%"=="0" goto fin
call :point 4 15
if not "%RC%"=="0" goto fin
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Phase final -Stamp %STAMP% < nul
set RC=%ERRORLEVEL%
:fin
echo.
if "%RC%"=="0" (echo Готово: во всех 4 точках только номер 0, поза по меткам не дальше 0,15 м от рулетки, RESEEDED на чужую позу нет. Скажите Claude.) else if "%RC%"=="5" (echo СТОП: ложный номер или поза дальше 0,15 м от рулетки, причина выше. Дрон не трогать и не взлетать, скажите Claude.) else if "%RC%"=="6" (echo НЕ ПРОВЕРЕНО: причина выше. Скажите Claude.) else if "%RC%"=="3" (echo НЕ НАЧАТО: дрон взведён или нет связи с полётным контроллером. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
echo Перед взлётом выключите и включите дрон или сверьте позицию EKF с рулеткой
if not defined BB_NO_PAUSE pause
exit /b %RC%
:point
echo.
echo Точка %1 из 4: сдвиг %2 см назад, как в карточке. Поставьте дрон, уберите руки, 15 секунд дрон не трогать.
set "A="
set /p "A=Наберите %2 и Enter, любое другое - остановка: "
if "%A%"=="%2" goto pointrec
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Phase stop -Stamp %STAMP% -Cm %2 < nul
set RC=%ERRORLEVEL%
if "%RC%"=="0" set RC=4
exit /b 0
:pointrec
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Phase rec -Stamp %STAMP% -Cm %2 < nul
set RC=%ERRORLEVEL%
exit /b 0
:die
echo.
echo СТОП: %MSG%
echo Перед взлётом выключите и включите дрон или сверьте позицию EKF с рулеткой
if not defined BB_NO_PAUSE pause
exit /b 4
