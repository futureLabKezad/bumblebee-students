@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: проверка ложных номеров меток. Дрон стоит неподвижно над меткой 0, моторы не запускаются и не взводятся. Сначала около 20 секунд проверка, выдаёт ли детектор номера; потом 4 точки со сдвигом 0, 5, 10 и 15 см, в каждой 10 секунд записи номеров и углов меток. Этот файл ничего не взводит, детектор не будит, в PX4 и на Pi ничего не пишет, ros2 на Pi не вызывает. Около 3 минут.
rem 25_metki_nomera.cmd (Claude, 13.11.2026, набор r7). Ответ: out\metki_nomera_ВРЕМЯ.txt, последняя строка # VERDICT. По коду образа без взвода детектор спит - тогда окно через 20 секунд скажет НЕ ПРОВЕРЕНО и двигать дрон не нужно.
rem Вопросы задаёт этот файл; run_r7_metki.ps1 вызывается по фазам pre, rec, stop, final, всегда со вводом из nul - он не читает ничего, что набирают в окне.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r7_metki.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r7_marker_ids.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "PS1=%~dp0run_r7_metki.ps1"
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
if "%RC%"=="0" (echo Готово: во всех 4 точках только номер 0. Скажите Claude.) else if "%RC%"=="5" (echo ЛОЖНЫЙ НОМЕР: детектор выдал номер не 0. Дрон не трогать, скажите Claude.) else if "%RC%"=="6" (echo НЕ ПРОВЕРЕНО: причина выше. Скажите Claude.) else if "%RC%"=="3" (echo НЕ НАЧАТО: дрон взведён или нет связи с полётным контроллером. Скажите Claude.) else (echo Не получилось. Скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:point
echo.
echo Точка %1 из 4: сдвиг %2 см, как в карточке. Поставьте дрон, уберите руки, 15 секунд дрон не трогать.
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
if not defined BB_NO_PAUSE pause
exit /b 4
