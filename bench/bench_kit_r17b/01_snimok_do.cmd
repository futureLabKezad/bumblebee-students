@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: снимок состояния Pi 20EC и настроек PX4 до стенда. Читает процессор, температуру, троттлинг, версии, файлы образа, затем настройки PX4 через params_check этого набора - чтение таблицы MAVROS v3. Ничего не меняет, моторы не взводятся. Займёт около 3 минут.
rem 01_snimok_do.cmd (Claude, 10.11.2026; r8 13.11.2026: сверка из params_check этого набора, params_read.sh v3 - берёт только полный ответ /mavros/mavros/get_parameters). Шаг 12, пункт 1 задания T31. Не пишет на дрон; файлов на Pi не создаёт.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_01_snapshot.ps1 lib\bb_common.ps1 pi\pi_state.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
set "PCC=%~dp0params_check\params_check.cmd"
if not exist "%PCC%" (set "MSG=нет сверки настроек этого набора: %PCC%" & goto die)
if not defined BB_KIT_OUT set "BB_KIT_OUT=%~dp0out"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"
title 01_snimok_do
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_01_snapshot.ps1" -Stamp %STAMP%
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (set "MSG=состояние Pi не прочитано, код %RC%. Настройки не читал." & goto die)
echo.
echo Теперь настройки PX4, около 1,5 минуты ...
set "WAS_NP=%BB_NO_PAUSE%"
set "BB_NO_PAUSE=1"
call "%PCC%" -Stamp bench_%STAMP%
set RC2=%ERRORLEVEL%
set "BB_NO_PAUSE=%WAS_NP%"
echo.
if "%RC2%"=="0" (echo Готово: настройки PX4 совпали с утверждённым набором.) else if "%RC2%"=="2" (echo Готово: настройки прочитаны, есть отличия от утверждённого набора. Это снимок до стенда, смотрит Claude.) else if "%RC2%"=="3" (echo НЕ ПОДТВЕРЖДЕНО: настройки прочитаны не полностью, например ParamPull success=False. Повторите 01 - не больше 2 раз, потом скажите Claude.) else (echo Настройки не прочитаны. Скажите Claude.)
echo Файлы в папке out рядом с этим файлом: bench_pi_state_%STAMP%.txt и params_bench_%STAMP%_report.txt
if not defined BB_NO_PAUSE pause
exit /b 0
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
