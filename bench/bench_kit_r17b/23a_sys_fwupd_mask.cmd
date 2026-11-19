@echo off
chcp 65001 >nul
echo МЕНЯЕТ ДРОН: маскирует таймер fwupd-refresh.timer на Pi командой sudo systemctl mask --now; пароль sudo наберёте только вы, в этом окне. Зачем: ступень 1 разбора P1 - fwupd-refresh в случайное время качает метаданные прошивок и грузит Pi, на дроне он не нужен. Как вернуть: 23a_otkat_fwupd_mask.cmd снимает маску и снова запускает таймер, нужен свой файл-разрешение. Перед правкой нужен свежий успешный 20_nichego_ne_otvalilos.cmd, после правки сразу снова 20, после следующей перезагрузки дрона ещё раз 20. ЗАГОТОВКА: заблокирована без gates\SYS_FWUPD_MASK_APPROVED.txt от чата 1.
rem 23a_sys_fwupd_mask.cmd (Claude, 12.11.2026, набор r6; P1 ступень 1, одна правка за раз). Снимок до, правка, проверка is-enabled=masked и is-active=inactive делает pi\r6_sys_change.sh. Журнал: out\sys_fwupd_apply_ВРЕМЯ.log.
cd /d "%~dp0"
set "MSG="
if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E" (set "MSG=это не тот компьютер, нужен DESKTOP-H5CPN8E. Ничего не сделано." & goto die)
for %%F in (run_r6_sys.ps1 lib\bb_common.ps1 lib\bb_r6.ps1 pi\r6_sys_change.sh) do if not exist "%%F" (set "MSG=нет файла %%F рядом." & goto die)
if not exist "gates\SYS_FWUPD_MASK_APPROVED.txt" (set "MSG=нет разрешения gates\SYS_FWUPD_MASK_APPROVED.txt. Его создаёт только чат 1 после слов владельца. Ничего не сделано." & goto die)
echo.
echo Правила: Claude к дрону не подключается, пароль sudo вводите только вы. Моторы в этом шаге не нужны.
set "A1="
set /p "A1=1 из 2. Дрон на земле, моторы не запускаются, стек работает как обычно. Наберите SYS и Enter: "
if /i not "%A1%"=="SYS" (set "MSG=остановлено, ничего не сделано." & goto die)
set "A2="
set /p "A2=2 из 2. Сделать правку, пароль sudo наберёте вы, когда появится строка SYS_SUDO_PROMPT. Наберите YES и Enter: "
if /i not "%A2%"=="YES" (set "MSG=остановлено, ничего не сделано." & goto die)
title 23a_sys_fwupd_mask
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_r6_sys.ps1" -Change fwupd -Mode apply -Confirmed CHANGE-fwupd-apply
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
