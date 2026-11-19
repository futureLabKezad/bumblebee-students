# run_params_check.ps1 (Claude, 09.11.2026) - ТОЛЬКО ЧТЕНИЕ дрона. Запускается из params_check.cmd.
# Читает настройки PX4 через ssh (params_read.sh, ничего не меняет и не пишет на Pi), сохраняет их в файл с датой
# и временем и сверяет с утверждённым набором (compare_params.ps1).
# Коды выхода: 0 совпало; 2 СТОП (отличия); 3 неполно; 4 ошибка связи или чтения.
param(
    [string]$DroneHost = 'lb@10.255.254.26',
    [string]$OutDir = '',
    [string]$Stamp = '',
    [string]$Label = '',
    [int]$ReadTimeoutSec = 120,
    [string]$ExpectPc = 'DESKTOP-H5CPN8E'
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $OutDir) {
    if ($env:BB_KIT_OUT) { $OutDir = $env:BB_KIT_OUT } else { $OutDir = Join-Path (Split-Path -Parent $here) 'out' }
}
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') }
function Stop-Run([string]$msg, [int]$code) {
    Write-Host ''
    Write-Host ('  СТОП: ' + $msg + '  ') -ForegroundColor White -BackgroundColor DarkRed
    exit $code
}

if ($env:COMPUTERNAME -ne $ExpectPc) { Stop-Run ('это не тот компьютер (' + $env:COMPUTERNAME + '), нужен ' + $ExpectPc + '. Ничего не сделано.') 4 }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$prefix = Join-Path $OutDir ('params_' + $Stamp)
$eventsFile = $prefix + '.raw.txt'
foreach ($f in @($eventsFile, ($prefix + '.FAILED.txt'))) {
    if (Test-Path -LiteralPath $f) { Stop-Run ('файл уже есть, не перезаписываю: ' + $f) 4 }
}
$readSh = Join-Path $here 'params_read.sh'
$compare = Join-Path $here 'compare_params.ps1'
foreach ($f in @($readSh, $compare)) { if (-not (Test-Path -LiteralPath $f)) { Stop-Run ('нет файла ' + $f) 4 } }

$ssh = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $ssh) { Stop-Run 'ssh не найден на этом ПК' 4 }
Write-Host ('ssh: ' + $ssh.Source)

function Run-Ssh([string]$argLine, [string]$outPath, [string]$errPath, [int]$timeoutSec, [string]$stdinPath = '') {
    if ($stdinPath) {
        $p = Start-Process -FilePath $ssh.Source -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardInput $stdinPath -RedirectStandardOutput $outPath -RedirectStandardError $errPath
    }
    else {
        $p = Start-Process -FilePath $ssh.Source -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardOutput $outPath -RedirectStandardError $errPath
    }
    $null = $p.Handle   # без этого ExitCode после WaitForExit(ms) бывает пустым
    if (-not $p.WaitForExit($timeoutSec * 1000)) {
        try { Stop-Process -Id $p.Id -Force } catch { }
        return -999
    }
    $p.WaitForExit()
    return [int]$p.ExitCode
}

$opts = '-n -T -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3'
# чтение идёт без -n: имена настроек основы подаются в stdin (по одному в строке, LF, в конце перевод строки)
$optsRead = '-T -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3'
$baseNames = New-Object Collections.Generic.List[string]
foreach ($l in [IO.File]::ReadLines((Join-Path $here 'baseline_20261104_1145.params'))) {
    if ($l.StartsWith('#') -or $l.Trim() -eq '') { continue }
    $f = $l.Split("`t"); if ($f.Count -ge 5 -and $f[1] -eq '1') { $baseNames.Add($f[2]) }
}
$namesFile = [IO.Path]::GetTempFileName()
[IO.File]::WriteAllText($namesFile, (($baseNames -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))
$tmpOut = [IO.Path]::GetTempFileName(); $tmpErr = [IO.Path]::GetTempFileName()
try {
    # 1. имя дрона
    Write-Host 'Проверяю, что на связи именно bumblebee-20ec ...'
    $rc = Run-Ssh ($opts + ' ' + $DroneHost + ' "test $(hostname) = bumblebee-20ec && echo HOST_OK"') $tmpOut $tmpErr 30
    $o = (Get-Content -LiteralPath $tmpOut -Raw -ErrorAction SilentlyContinue)
    if ($rc -ne 0 -or $o -notmatch 'HOST_OK') {
        $e = (Get-Content -LiteralPath $tmpErr -Raw -ErrorAction SilentlyContinue)
        Stop-Run ('дрон не ответил или это не bumblebee-20ec (код ' + $rc + '). Ничего не прочитано. ' + $e) 4
    }

    # 2. чтение настроек: скрипт идёт в команде ssh, файлов на Pi нет
    $txt = ([IO.File]::ReadAllText($readSh)) -replace "`r`n", "`n"
    $b64 = [Convert]::ToBase64String((New-Object Text.UTF8Encoding($false)).GetBytes($txt))
    $remote = 'bash -c \"$(echo ' + $b64 + ' | base64 -d)\"'
    Write-Host ('Читаю настройки, около 1 минуты (макс. ' + $ReadTimeoutSec + ' с) ...')
    $rc = Run-Ssh ($optsRead + ' ' + $DroneHost + ' "' + $remote + '"') $eventsFile $tmpErr $ReadTimeoutSec $namesFile
    $err = (Get-Content -LiteralPath $tmpErr -Raw -ErrorAction SilentlyContinue)
    $size = 0; if (Test-Path -LiteralPath $eventsFile) { $size = (Get-Item -LiteralPath $eventsFile).Length }
    if ($rc -ne 0 -or $err -notmatch 'BB_PARAMS_READ_DONE' -or $size -lt 100) {
        if (Test-Path -LiteralPath $eventsFile) { Move-Item -LiteralPath $eventsFile -Destination ($prefix + '.FAILED.txt') }
        Stop-Run ('чтение не закончилось (код ' + $rc + ', получено ' + $size + ' байт). Ничего не сверено. ' + $err) 4
    }
    $tl = ($err -split "`r?`n" | Where-Object { $_ -like 'TABLE_READ*' } | Select-Object -Last 1)
    Write-Host ('Прочитано. ' + $tl + '. Сверяю ...')
}
finally {
    Remove-Item -LiteralPath $tmpOut, $tmpErr, $namesFile -ErrorAction SilentlyContinue
}

& $compare -Events $eventsFile -OutPrefix $prefix -Label $Label
exit $LASTEXITCODE
