# bb_common.ps1 (Claude, 10.11.2026) - общие функции стенда. Подключается через ". lib\bb_common.ps1". Сама ничего не запускает и к дрону не подключается.
# Все обращения к дрону идут только из .cmd, которые запускает владелец двойным щелчком (правило 2).
$script:BB_ExpectPc = 'DESKTOP-H5CPN8E'
$script:BB_DroneHost = 'lb@10.255.254.26'
$script:BB_DroneName = 'bumblebee-20ec'
$script:BB_SshOpts = '-n -T -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=3'

function BB-Stop([string]$msg, [int]$code) {
    Write-Host ''
    Write-Host ('  СТОП: ' + $msg + '  ') -ForegroundColor White -BackgroundColor DarkRed
    exit $code
}
function BB-AssertPc {
    if ($env:COMPUTERNAME -ne $script:BB_ExpectPc) { BB-Stop ('это не тот компьютер (' + $env:COMPUTERNAME + '), нужен ' + $script:BB_ExpectPc + '. Ничего не сделано.') 4 }
}
function BB-OutDir([string]$kitRoot) {
    $o = $env:BB_KIT_OUT
    if (-not $o) { $o = Join-Path $kitRoot 'out' }
    if (-not (Test-Path -LiteralPath $o)) { New-Item -ItemType Directory -Path $o | Out-Null }
    return $o
}
# Имя файла журнала: без перезаписи. Если файл уже есть, остановка.
function BB-NewOutFile([string]$dir, [string]$name) {
    $p = Join-Path $dir $name
    if (Test-Path -LiteralPath $p) { BB-Stop ('файл уже есть, не перезаписываю: ' + $p) 4 }
    return $p
}
function BB-SafeLabel([string]$s, [string]$what) {
    if ($s -notmatch '^[A-Za-z0-9_-]{1,40}$') { BB-Stop ($what + ' может содержать только латинские буквы, цифры, _ и - (до 40 знаков): «' + $s + '»') 4 }
    return $s
}
function BB-FindSsh {
    $s = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $s) { BB-Stop 'ssh не найден на этом ПК' 4 }
    Write-Host ('ssh: ' + $s.Source)
    return $s
}
function BB-RunSsh($ssh, [string]$argLine, [string]$outPath, [string]$errPath, [int]$timeoutSec) {
    $p = Start-Process -FilePath $ssh.Source -ArgumentList $argLine -NoNewWindow -PassThru -RedirectStandardOutput $outPath -RedirectStandardError $errPath
    $null = $p.Handle   # без этого ExitCode после WaitForExit(ms) бывает пустым
    if (-not $p.WaitForExit($timeoutSec * 1000)) { try { Stop-Process -Id $p.Id -Force } catch { }; return -999 }
    $p.WaitForExit()
    return [int]$p.ExitCode
}
# Проверка, что на связи именно bumblebee-20ec. Ничего не меняет.
function BB-TestDrone($ssh) {
    $to = [IO.Path]::GetTempFileName(); $te = [IO.Path]::GetTempFileName()
    try {
        Write-Host 'Проверяю, что на связи именно bumblebee-20ec ...'
        $rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "test $(hostname) = bumblebee-20ec && echo HOST_OK"') $to $te 30
        $o = Get-Content -LiteralPath $to -Raw -ErrorAction SilentlyContinue
        $e = Get-Content -LiteralPath $te -Raw -ErrorAction SilentlyContinue
        if ($rc -ne 0 -or $o -notmatch 'HOST_OK') { BB-Stop ('дрон не ответил или это не bumblebee-20ec (код ' + $rc + '). Ничего не прочитано. ' + $e) 4 }
    }
    finally { Remove-Item -LiteralPath $to, $te -ErrorAction SilentlyContinue }
}
# Скрипт Pi идёт внутри команды ssh (base64), файлов на Pi не создаётся. Аргументы только из безопасных знаков.
function BB-RemoteCommand([string]$shPath, [string[]]$scriptArgs) {
    $txt = ([IO.File]::ReadAllText($shPath)) -replace "`r`n", "`n"
    $b64 = [Convert]::ToBase64String((New-Object Text.UTF8Encoding($false)).GetBytes($txt))
    $argTxt = ''
    foreach ($a in $scriptArgs) {
        if ($a -notmatch '^[A-Za-z0-9_.-]{1,60}$') { BB-Stop ('недопустимый аргумент для Pi: «' + $a + '»') 4 }
        $argTxt += ' ' + $a
    }
    return 'bash -c \"$(echo ' + $b64 + ' | base64 -d)\" _' + $argTxt
}
# Из сырого вывода достаёт строки "SUMMARY ключ значение" и "META ...".
function BB-PickLines([string]$raw, [string]$prefix) {
    return @($raw -split "`r?`n" | Where-Object { $_.StartsWith($prefix + ' ') })
}
function BB-Utf8NoBom { return (New-Object Text.UTF8Encoding($false)) }
