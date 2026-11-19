@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: откат правки 23b - снимает паузу обновлений snap командой sudo snap refresh --unhold; пароль sudo наберёте только вы, в этом окне. Зачем: вернуть обновления snap как было до 23b. Как вернуть обратно: 23b_sys_snap_hold.cmd с новым разрешением. После отката сразу 20_nichego_ne_otvalilos.cmd. ЗАГОТОВКА: заблокирована без gates\OTKAT_SYS_SNAP_HOLD_APPROVED.txt от чата 1.
rem 23b_otkat_snap_hold.cmd (Claude, 12.11.2026, набор r6). Проверка после отката: строки hold: forever в snap refresh --time нет. Журнал: out\sys_snaphold_rollback_ВРЕМЯ.log.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_sys.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r6_sys_change.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\OTKAT_SYS_SNAP_HOLD_APPROVED.txt" (set "MSG=нет разрешения gates\OTKAT_SYS_SNAP_HOLD_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
echo.
echo Правила: Claude к дрону не подключается, пароль sudo вводите только вы. Моторы в этом шаге не нужны.
set "A1="
set /p "A1=1 из 2. Дрон на земле, моторы не запускаются. Наберите SYS и Enter: "
if /i not "%A1%"=="SYS" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 2. Сделать откат, пароль sudo наберёте вы, когда появится строка SYS_SUDO_PROMPT. Наберите YES и Enter: "
if /i not "%A2%"=="YES" (set "MSG=остановлено, ничего не сделано." & goto die)
title 23b_otkat_snap_hold
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_sys.ps1" -Change snaphold -Mode rollback -Confirmed CHANGE-snaphold-rollback
set RC=%ERRORLEVEL%
echo.
if "%RC%"=="0" (echo Готово: откат применился. Сразу запустите 20_nichego_ne_otvalilos.cmd. Скажите Claude.) else if "%RC%"=="5" (echo Ничего не изменено, причины выше. Скажите Claude.) else (echo СТОП: откат не подтвердился или не получилось. Ничего не делать самим, скажите Claude.)
if not defined BB_NO_PAUSE pause
exit /b %RC%
:die
echo.
echo СТОП: %MSG%
if not defined BB_NO_PAUSE pause
exit /b 4
