@echo off
chcp 65001 >nul
echo ТОЛЬКО ЧТЕНИЕ: сверка настроек дрона с утверждённым набором. Дрон не меняется. Запускать перед сессией и после каждого полёта, дрон на земле, моторы не крутятся. Займёт около 1,5 минуты.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_params_check.ps1 compare_params.ps1 params_read.sh baseline_20261104_1145.params approved_changes.txt profile_values.tsv ignore_counters.txt) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
title params_check
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_params_check.ps1" %*
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: настройки совпадают.) else if "%RC%"=="2" (echo СТОП до решения владельца. Скажите Claude.) else if "%RC%"=="3" (echo Сверка НЕ подтверждена: чтение неполное или есть UNKNOWN. Повторить имеет смысл, если в отчёте НЕ ПРОЧИТАНО или написано в таблице MAVROS N из. Если там UNKNOWN, повтор ничего не даст. Скажите Claude.) else (echo Не получилось, скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4