# run_r6_sys.ps1 (Claude, 12.11.2026, набор r6) - МЕНЯЕТ ДРОН. ЗАГОТОВКА: Claude её не запускает; двойной щелчок владельца по 23a/23b/23c_*.cmd.
# Системная правка ступени 1 (разбор P1) или её откат, по одной: -Change fwupd | snaphold | timers, -Mode apply | rollback (pi\r6_sys_change.sh через ssh -tt,
# sudo спрашивает пароль владельца в этом же окне; Claude пароль не видит и не вводит).
# Условия до обращения к дрону (иначе ничего не делается):
#  - файл-разрешение в gates\ для ЭТОЙ правки и ЭТОГО режима (создаёт только чат 1 после слов владельца; одно разрешение = один успешный запуск);
#  - для apply: свежий (не старше 60 минут) успешный снимок «до» шага 20 (out\sys_check_*.txt с «# VERDICT OK»), сделанный ПОСЛЕ последней правки/отката ступени 1
#    (так правки идут строго по одной: правка -> 20 -> следующая). Для отката снимок не нужен (откат нужен как раз когда что-то не так).
# Журнал: out\sys_<правка>_<режим>_<время>.log (не перезаписывается): первые строки PERMISSION_SHA256 и BASELINE, дальше весь вывод с Pi.
# Коды выхода: 0 правка (откат) применилась и проверена; 5 условия не выполнены или команда не выполнена (на дроне ничего не изменилось);
#              6 правка не подтвердилась (состояние неизвестно: сказать Claude, откат своим файлом); 4 ошибка связи, чужой ПК, чужой дрон, нет разрешения.
param(
    [Parameter(Mandatory = $true)][ValidateSet('fwupd', 'snaphold', 'timers')][string]$Change,
    [Parameter(Mandatory = $true)][ValidateSet('apply', 'rollback')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$Confirmed,
    [string]$Stamp = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if ($Confirmed -cne ('CHANGE-' + $Change + '-' + $Mode)) { BB-Stop 'нет подтверждения в окне. Запускайте только через 23a/23b/23c_*.cmd.' 4 }
$gates = @{
    'fwupd:apply'       = @('SYS_FWUPD_MASK_APPROVED.txt', '23a_fwupd_mask')
    'fwupd:rollback'    = @('OTKAT_SYS_FWUPD_APPROVED.txt', '23a_otkat_fwupd_mask')
    'snaphold:apply'    = @('SYS_SNAP_HOLD_APPROVED.txt', '23b_snap_hold')
    'snaphold:rollback' = @('OTKAT_SYS_SNAP_HOLD_APPROVED.txt', '23b_otkat_snap_hold')
    'timers:apply'      = @('SYS_TIMERS_MASK_APPROVED.txt', '23c_taimery_mask')
    'timers:rollback'   = @('OTKAT_SYS_TIMERS_APPROVED.txt', '23c_otkat_taimery_mask')
}
$g = $gates[$Change + ':' + $Mode]
$perm = R6-Permission (Join-Path (Join-Path $here 'gates') $g[0]) $g[1]
if (-not $perm.Ok) { BB-Stop ($perm.Why + '. К дрону не обращались.') 4 }
$logPrefix = 'sys_' + $Change + '_' + $Mode + '_'
$okMarker = 'BB_SYS_DONE ' + $Change + ' ' + $Mode + ' OK'
if (R6-PermissionUsed $outDir $logPrefix $perm.Sha $okMarker) { BB-Stop ('разрешение ' + $g[0] + ' уже использовано успешным запуском (журнал в out\' + $logPrefix + '*). Нужно новое «да» владельца и новый файл от чата 1. К дрону не обращались.') 4 }
$baseLine = 'нет (откат)'
if ($Mode -eq 'apply') {
    $evt = @(Get-ChildItem -LiteralPath $outDir -File -Filter 'sys_*.log' -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^sys_(fwupd|snaphold|timers)_(apply|rollback)_' } | Sort-Object LastWriteTime)
    $lastEvt = $null; if ($evt.Count -gt 0) { $lastEvt = $evt[-1] }
    $base = $null
    foreach ($f in @(Get-ChildItem -LiteralPath $outDir -File -Filter 'sys_check_*.txt' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '\.err\.txt$|\.FAILED\.' } | Sort-Object LastWriteTime -Descending)) { $base = $f; break }
    if (-not $base) { BB-Stop 'нет снимка «до»: сначала 20_nichego_ne_otvalilos.cmd (Ч1–Ч6). К дрону не обращались.' 5 }
    if ((R6-LastLine $base.FullName) -cne '# VERDICT OK') { BB-Stop ('последний снимок шага 20 (' + $base.Name + ') не «# VERDICT OK»: что-то уже не так, правку не делаем. К дрону не обращались.') 5 }
    if (((Get-Date) - $base.LastWriteTime).TotalMinutes -gt 60) { BB-Stop ('снимок «до» ' + $base.Name + ' старше 60 минут: повторите 20_nichego_ne_otvalilos.cmd. К дрону не обращались.') 5 }
    if ($lastEvt -and $base.LastWriteTime -le $lastEvt.LastWriteTime) { BB-Stop ('снимок «до» ' + $base.Name + ' сделан ДО последней правки или отката ступени 1 (' + $lastEvt.Name + '): правки идут по одной, сначала 20_nichego_ne_otvalilos.cmd. К дрону не обращались.') 5 }
    $baseLine = $base.Name
}
$sh = Join-Path $here 'pi\r6_sys_change.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') } elseif ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: ' + $Stamp) 4 }   # -Stamp только для тестов; переменные PowerShell не различают регистр: $stamp = $Stamp
$log = BB-NewOutFile $outDir ($logPrefix + $stamp + '.log')
[IO.File]::WriteAllText($log, ('# ' + (R6-Now) + ' шаг 23 ' + $Change + ' ' + $Mode + ' (МЕНЯЕТ ДРОН)' + "`r`nPERMISSION_SHA256=" + $perm.Sha + "`r`nPERMISSION_FILE=" + $g[0] + "`r`nBASELINE=" + $baseLine + "`r`n"), (BB-Utf8NoBom))
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $sh @($Change, $Mode)
$argv = @('-tt', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', $script:BB_DroneHost, $remote)
Write-Host ''
Write-Host '  Сейчас на Pi: снимок «до», правка, проверка. До строки SYS_SUDO_PROMPT ничего не набирайте. Когда она появится, наберите ПАРОЛЬ (только вы; символы не видны) и Enter.  ' -ForegroundColor White -BackgroundColor DarkRed
$ErrorActionPreference = 'Continue'
$lines = New-Object Collections.Generic.List[string]
# Правка 1 проверки RV (12.11): всё, что набрано в окне до этой строки, выбрасывается, чтобы ssh -tt не отправил это на Pi (там оно отразилось бы на экран и в журнал).
# Эхо на Pi выключает pi\r6_sys_change.sh (stty -echo). Окно без консоли (тесты) даёт исключение - его пропускаем.
try { $Host.UI.RawUI.FlushInputBuffer() } catch { }
& $ssh.Source @argv 2>&1 | ForEach-Object { $line = ([string]$_).TrimEnd("`r"); Write-Host $line; $lines.Add($line); Add-Content -LiteralPath $log -Value $line -Encoding UTF8 }
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
Add-Content -LiteralPath $log -Value ('# ' + (R6-Now) + ' конец, код ssh ' + $code) -Encoding UTF8
$all = ($lines -join "`n")
Write-Host ''
if ($all -match [regex]::Escape($okMarker)) {
    Write-Host ('Готово: правка ' + $Change + ' (' + $Mode + ') применилась и проверена на Pi. Журнал: ' + $log) -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host '  Сразу: 20_nichego_ne_otvalilos.cmd (Ч1–Ч6, сравнит со снимком «до»). После следующей перезагрузки дрона: ещё раз 20 (он проверит, что правка держится).'
    exit 0
}
if ($all -match 'BB_SYS_STOP') { Write-Host ('  СТОП: условия на Pi не выполнены, ничего не изменено (строка BB_SYS_STOP выше). Скажите Claude. Журнал: ' + $log) -ForegroundColor White -BackgroundColor Red; exit 5 }
if ($all -match 'BB_SYS_NOCHANGE') { Write-Host ('  Команда не выполнена (например, пароль не принят): на дроне всё как было. Скажите Claude. Журнал: ' + $log) -ForegroundColor White -BackgroundColor Red; exit 5 }
Write-Host ('  СТОП: правка НЕ подтвердилась (код ssh ' + $code + '). Состояние нужно смотреть: ничего не делайте сами, скажите Claude. Откат - свой файл 23*_otkat_*.cmd после разрешения чата 1. Журнал: ' + $log) -ForegroundColor White -BackgroundColor Red
exit 6
