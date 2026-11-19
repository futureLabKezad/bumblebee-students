# run_01_snapshot.ps1 (Claude, 10.11.2026) - ТОЛЬКО ЧТЕНИЕ. Состояние Pi 20EC (pi\pi_state.sh) в файл out\bench_pi_state_<время>.txt.
# Настройки PX4 «до» читает следом params_check.cmd набора r4 (его вызывает 01_snimok_do.cmd). Коды выхода: 0 прочитано; 4 ошибка.
param([string]$Stamp = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') }
$null = BB-SafeLabel $Stamp 'штамп'
$file = BB-NewOutFile $outDir ('bench_pi_state_' + $Stamp + '.txt')
$errFile = BB-NewOutFile $outDir ('bench_pi_state_' + $Stamp + '.err.txt')
$sh = Join-Path $here 'pi\pi_state.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $sh @()
Write-Host 'Читаю состояние Pi (до 1 минуты) ...'
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $file $errFile 120
$raw = ''; if (Test-Path -LiteralPath $file) { $raw = [IO.File]::ReadAllText($file) }
if ($rc -ne 0 -or $raw -notmatch 'BB_PI_STATE_DONE') {
    $failed = $file -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $file) { Move-Item -LiteralPath $file -Destination $failed }
    BB-Stop ('чтение состояния Pi не закончилось (код ' + $rc + '). ' + (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)) 4
}
Write-Host ''
foreach ($l in ($raw -split "`r?`n")) { if ($l -match '^(PI_DATE|PI_MODEL|PI_UPTIME|PI_LOADAVG|PI_TEMP|PI_THROTTLED|PI_ARM_CLOCK|PI_BUMBLEBEE_SERVICE|PI_MEM_MB|PI_PYTHON|PI_OPENCV)') { Write-Host $l } }
if ($raw -match 'armed:\s*\r?\n?\s*True|armed: True') { Write-Host ''; Write-Host '  ВНИМАНИЕ: PX4 сообщает armed = True (дрон взведён).  ' -ForegroundColor Black -BackgroundColor Yellow }
Write-Host ''
Write-Host ('Состояние Pi: ' + $file)
exit 0
