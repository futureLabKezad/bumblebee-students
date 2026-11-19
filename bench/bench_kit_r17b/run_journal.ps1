# run_journal.ps1 (Claude, 10.11.2026, набор r2) - ТОЛЬКО ЧТЕНИЕ. Строки журнала bumblebee за время последнего полёта (pi\journal_window.sh) в out\takeoff_<время>_journal.txt.
# Вызывается из 07_vzlet_zagotovka.cmd ПОСЛЕ проверки «дрон разоружён». Окно = время от начала самого свежего out\takeoff_*.log до сейчас + 60 с; если оно больше 1800 с, файл полёта не свежий и журнал НЕ читается.
# Коды выхода: 0 прочитано; 4 не прочитано или не свежий полёт.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$logs = @(Get-ChildItem -LiteralPath $outDir -Filter 'takeoff_*.log' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '_journal' } | Sort-Object LastWriteTime)
if ($logs.Count -eq 0) { BB-Stop 'нет out\takeoff_*.log: журнал полёта не нашёл, журнал Pi не читаю.' 4 }
$flight = $logs[-1]
$first = Get-Content -LiteralPath $flight.FullName -Encoding UTF8 -TotalCount 1
$t0 = [datetime]::MinValue
if ($first -notmatch '^# takeoff (\S+)' -or -not [datetime]::TryParse($Matches[1], [ref]$t0)) { BB-Stop ('в первой строке ' + $flight.Name + ' нет времени начала: ' + $first) 4 }
$win = [int][math]::Ceiling(((Get-Date) - $t0).TotalSeconds) + 60
if ($win -lt 60) { $win = 60 }
if ($win -gt 1800) { BB-Stop ('окно ' + $win + ' с больше 1800: файл полёта ' + $flight.Name + ' не свежий. Журнал Pi не читаю.') 4 }
$base = $flight.BaseName + '_journal'
$file = BB-NewOutFile $outDir ($base + '.txt')
$errFile = BB-NewOutFile $outDir ($base + '.err.txt')
$sh = Join-Path $here 'pi\journal_window.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $sh @([string]$win)
Write-Host ('Читаю журнал bumblebee за последние ' + $win + ' с (только чтение) ...')
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $file $errFile 120
$raw = ''; if (Test-Path -LiteralPath $file) { $raw = [IO.File]::ReadAllText($file) }
if ($rc -ne 0 -or $raw -notmatch 'BB_JOURNAL_DONE rc=0') {
    $failed = $file -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $file) { Move-Item -LiteralPath $file -Destination $failed }
    Write-Host ('  Журнал Pi не прочитан (код ' + $rc + '): ' + $failed + ' ' + (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue))
    exit 4
}
$n = @($raw -split "`r?`n" | Where-Object { $_ -match '^\d{4}-\d\d-\d\dT' }).Count
Write-Host ('Журнал bumblebee за время полёта: ' + $n + ' строк. Файл: ' + $file)
exit 0
