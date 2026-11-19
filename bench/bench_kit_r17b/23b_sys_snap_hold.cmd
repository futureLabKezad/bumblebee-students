@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: ставит все snap на паузу обновлений без срока командой sudo snap refresh --hold; пароль sudo наберёте только вы, в этом окне. Зачем: ступень 1 разбора P1 - snapd сам проверяет и ставит обновления, примерно через 5 минут после включения и потом время от времени, это грузит Pi; на дроне не нужно. Как вернуть: 23b_otkat_snap_hold.cmd снимает паузу командой sudo snap refresh --unhold, нужен свой файл-разрешение. Перед правкой нужен свежий успешный 20_nichego_ne_otvalilos.cmd, после правки сразу снова 20, после следующей перезагрузки дрона ещё раз 20. ЗАГОТОВКА: заблокирована без gates\SYS_SNAP_HOLD_APPROVED.txt от чата 1.
rem 23b_sys_snap_hold.cmd (Claude, 12.11.2026, набор r6; P1 ступень 1). Проверка: в snap refresh --time есть строка hold: forever. Журнал: out\sys_snaphold_apply_ВРЕМЯ.log.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_sys.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r6_sys_change.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\SYS_SNAP_HOLD_APPROVED.txt" (set "MSG=нет разрешения gates\SYS_SNAP_HOLD_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
echo.
echo Правила: Claude к дрону не подключается, пароль sudo вводите только вы. Моторы в этом шаге не нужны.
set "A1="
set /p "A1=1 из 2. Дрон на земле, моторы не запускаются, стек работает как обычно. Наберите SYS и Enter: "
if /i not "%A1%"=="SYS" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 2. Сделать правку, пароль sudo наберёте вы, когда появится строка SYS_SUDO_PROMPT. Наберите YES и Enter: "
if /i not "%A2%"=="YES" (set "MSG=остановлено, ничего не сделано." & goto die)
title 23b_sys_snap_hold
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_sys.ps1" -Change snaphold -Mode apply -Confirmed CHANGE-snaphold-apply
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: правка применилась. Сразу запустите 20_nichego_ne_otvalilos.cmd. Скажите Claude.) else if "%RC%"=="5" (echo Ничего не изменено, причины выше. Скажите Claude.) else (echo СТОП: правка не подтвердилась или не получилось. Ничего не делать самим, скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
