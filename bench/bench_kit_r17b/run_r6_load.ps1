# run_r6_load.ps1 (Claude, 12.11.2026, набор r6) - ТОЛЬКО ЧТЕНИЕ. Шаг 19: что грузит Pi (шаг 0 разбора P1, pi\r6_pi_load.sh). Около 3 минут.
# Пишет на ПК out\pi_load_<время>.txt (не перезаписывает); на Pi ничего не создаётся, sudo не нужен, стек и PX4 не трогаются.
# Коды выхода: 0 прочитано; 4 ошибка связи, чужой ПК или чужой дрон.
param([string]$Stamp = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') } elseif ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: ' + $Stamp) 4 }   # -Stamp только для тестов; переменные PowerShell не различают регистр: $stamp = $Stamp
$sh = Join-Path $here 'pi\r6_pi_load.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$ssh = BB-FindSsh
foreach ($n in @(('pi_load_' + $Stamp + '.txt'), ('pi_load_' + $Stamp + '.err.txt'))) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
BB-TestDrone $ssh
Write-Host 'Читаю нагрузку Pi: службы, процессы, частоту ядер, Wi-Fi, обновления, таймеры, подписчиков, затем pidstat 2 минуты (только чтение, около 3 минут) ...'
$r = R6-Remote $ssh $sh @() $outDir ('pi_load_' + $stamp) 300
if ($r.Code -ne 0 -or $r.Text -notmatch 'BB_R6LOAD_DONE') {
    $failed = $r.Out -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $r.Out) { Move-Item -LiteralPath $r.Out -Destination $failed }
    BB-Stop ('чтение нагрузки не закончилось (код ssh ' + $r.Code + '). ' + $r.Err) 4
}
Write-Host ''
foreach ($l in ($r.Text -split "`r?`n")) { if ($l -match '^(LOAD_DATE|LOAD_LOADAVG|LOAD_TEMP|LOAD_THROTTLED|LOAD_GOVERNOR cpu0|LOAD_WIFI_PS_JOURNAL|LOAD_WIFI_PS_IW|LOAD_RELIABLE |LOAD_PIDSTAT|LOAD_SNAP hold)') { Write-Host $l } }
$nPs = @(R6-Lines $r.Text 'PS5').Count; $nNodes = @(R6-Lines $r.Text 'LOAD_NODE').Count; $nTim = @(R6-Lines $r.Text 'LOAD_TIMER').Count
Write-Host ('Строк pidstat: ' + $nPs + ', узлов ROS: ' + $nNodes + ', строк таймеров: ' + $nTim + '. Разбирает Claude (пороги и выводы - не здесь).')
Add-Content -LiteralPath $r.Out -Value ('# PC ' + (R6-Now) + ' шаг 19, ТОЛЬКО ЧТЕНИЕ, строк pidstat ' + $nPs) -Encoding UTF8
Write-Host ('Готово. Файл: ' + $r.Out)
exit 0
