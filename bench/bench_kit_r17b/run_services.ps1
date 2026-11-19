# run_services.ps1 (Claude, 11.11.2026, набор r3; поручение чата 1 T47) - ТОЛЬКО ЧТЕНИЕ. Состояние трёх служб после установки образа: wifi-manager, notify-manager, led-default (pi\services_check.sh).
# Основание: _ПОПРАВКА_20261111_drone_py.md. Эти службы берут drone.py из /home/lb/ros2_ws/src/bumblebee/examples, после 05 со следующего включения они работают на drone.py r2j.
# Первый запуск ДО установки образа (05), для сравнения (служба могла перезапускаться и раньше; решение чата 1, 11.11). Второй запуск после установки образа (05) и ПОСЛЕ перезагрузки/включения дрона (службы должны были перезапуститься). Ничего не пишет на Pi, повышение прав не использует, служб не трогает.
# Итог одной строкой: «ВСЕ 3 АКТИВНЫ, ОШИБОК НЕТ» или «СТОП: ...». Файл ответа: out\services_check_<время>.txt, последней строкой «# VERDICT OK» или «# VERDICT NOT_OK».
# Коды выхода: 0 все три активны, ошибок нет; 5 СТОП (служба не active, падения или ошибки в журнале, журнал недоступен); 4 ошибка связи или скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$gen = BL-Generate (Join-Path $here 'pi\services_check.sh') @{} $outDir ('services_check_' + $stamp + '.generated.sh')
$rawFile = BB-NewOutFile $outDir ('services_check_' + $stamp + '.txt')
$errFile = BB-NewOutFile $outDir ('services_check_' + $stamp + '.err.txt')
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $gen @()
Write-Host 'Читаю состояние служб wifi-manager, notify-manager, led-default и их журналы за 10 минут (только чтение) ...'
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $rawFile $errFile 90
$raw = ''; if (Test-Path -LiteralPath $rawFile) { $raw = [IO.File]::ReadAllText($rawFile) }
if ($rc -ne 0 -or $raw -notmatch 'BB_SVC_DONE') {
    $failed = $rawFile -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $rawFile) { Move-Item -LiteralPath $rawFile -Destination $failed }
    BB-Stop ('чтение служб не закончилось (код ssh ' + $rc + '). ' + (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)) 4
}
$expected = @('wifi-manager', 'notify-manager', 'led-default')
$why = New-Object Collections.Generic.List[string]
$lines = @($raw -split "`r?`n")
foreach ($s in $expected) {
    $st = @($lines | Where-Object { $_ -cmatch ('^SVC ' + [regex]::Escape($s) + ' (\S+)\s*$') })
    if ($st.Count -ne 1) { $why.Add($s + ': нет строки состояния в ответе (' + $st.Count + ' строк)'); continue }
    $state = ([regex]::Match($st[0], '^SVC \S+ (\S+)\s*$')).Groups[1].Value
    if ($state -cne 'active') { $why.Add($s + ': служба не active, а «' + $state + '»') }
    $rr = @($lines | Where-Object { $_ -cmatch ('^SVC_RESTARTS ' + [regex]::Escape($s) + ' (\d+|unknown)\s*$') })
    if ($rr.Count -ne 1) { $why.Add($s + ': нет строки SVC_RESTARTS') }
    else {
        $rn = ([regex]::Match($rr[0], ' (\d+|unknown)\s*$')).Groups[1].Value
        if ($rn -ceq 'unknown') { $why.Add($s + ': число перезапусков не прочитано (unknown)') }
        elseif ([int]$rn -gt 0) { $why.Add($s + ': служба перезапускалась сама ' + $rn + ' раз (скорее всего падала)') }
    }
    $jj = @($lines | Where-Object { $_ -cmatch ('^SVC_JOURNAL ' + [regex]::Escape($s) + ' lines=\d+ access=(ok|denied)\s*$') })
    if ($jj.Count -ne 1) { $why.Add($s + ': нет строки SVC_JOURNAL') }
    elseif ($jj[0] -cmatch 'access=denied') { $why.Add($s + ': журнал прочитать нельзя (нет прав у пользователя lb); проверить нечем, повышение прав набором не используется') }
    $ee = @($lines | Where-Object { $_ -cmatch ('^SVC_ERRORS ' + [regex]::Escape($s) + ' (\d+)\s*$') })
    if ($ee.Count -ne 1) { $why.Add($s + ': нет строки SVC_ERRORS') }
    else { $en = [int]([regex]::Match($ee[0], ' (\d+)\s*$')).Groups[1].Value; if ($en -gt 0) { $why.Add($s + ': в журнале за 10 минут ' + $en + ' строк с Traceback, ImportError, ошибкой запуска или падением') } }
}
$sv = @($lines | Where-Object { $_ -cmatch '^SVC \S+ ' })
if ($sv.Count -ne 3) { $why.Add('в ответе ' + $sv.Count + ' строк SVC, ожидалось 3') }
if ($raw -notmatch '(?m)^BB_SVC_RESULT active=\d+ errors=\d+ restarts=\d+ denied=\d+\s*$') { $why.Add('нет итоговой строки BB_SVC_RESULT') }
Write-Host ''
foreach ($l in $lines) { if ($l -cmatch '^(SVC |SVC_RESTARTS |SVC_JOURNAL |SVC_ERRORS |BB_SVC_RESULT )') { Write-Host $l } }
foreach ($l in $lines) { if ($l -cmatch '^JT ') { Write-Host ('  ' + $l) } }
Write-Host ''
if ($why.Count -eq 0) {
    Add-Content -LiteralPath $rawFile -Value '# VERDICT OK' -Encoding UTF8
    Write-Host 'ВСЕ 3 АКТИВНЫ, ОШИБОК НЕТ' -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host ('Файл: ' + $rawFile)
    exit 0
}
Add-Content -LiteralPath $rawFile -Value '# VERDICT NOT_OK' -Encoding UTF8
Write-Host ('СТОП: ' + ($why -join '; ')) -ForegroundColor White -BackgroundColor Red
Write-Host '  Ничего не перезапускать и не чинить самому. Пришлите файл ниже чату 1 (через Claude): падения или ошибки импорта = СТОП, решает чат 1.'
Write-Host ('Файл: ' + $rawFile)
exit 5
