# run_mavros_build.ps1 (Claude, 10.11.2026, набор r2; решение чата 1 в 19:45) - МЕНЯЕТ ДРОН. ЗАГОТОВКА, Claude её не запускает: двойной щелчок владельца по 11_sborka_mavros_bp02.cmd (-Mode build) или 12_otkat_mavros_bp02.cmd (-Mode aside).
# build: собирает MAVROS bp02 на самом Pi из проверенного набора rc3 r3 (image_r2j\mavros_build\pi_kit, TRANSFER_SHA256SUMS 8bb42477…, коммит d63a236): передача файлов, m1_unpack.sh (< 1 мин), m2_build.sh 1 (оценка 7-10 мин, не измерено на Pi).
#        Не трогает apt-MAVROS, /opt/ros, start_bumblebee.sh, параметры PX4; моторы не взводит. Службу bumblebee останавливает ВЛАДЕЛЕЦ сам (пароль только его, правило 7), заряд батареи меряет сам.
# aside: переносит собранное (~/bench_ws/mavros ...) в ~/bench_ws/_aside_mavros_<метка>, ничего не удаляет; штатный MAVROS из apt остаётся тем же.
# Коды выхода: 0 готово; 4 условия не выполнены или ошибка (к дрону не обращались либо остановились до изменений); 6 изменения начались, но сборка не дошла до RC3M_M2_OK (смотреть журнал, при необходимости 12).
param(
    [Parameter(Mandatory = $true)][ValidateSet('build', 'aside')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$SafetyConfirmed
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$kit = Join-Path $here 'image_r2j\mavros_build\pi_kit'
if ($Mode -eq 'build' -and $SafetyConfirmed -ne 'BATTERY-SERVICE-BUILD') { BB-Stop 'не получены три подтверждения (батарея измерена, служба остановлена, начать сборку). Запускайте только через 11_sborka_mavros_bp02.cmd.' 4 }
if ($Mode -eq 'aside' -and $SafetyConfirmed -ne 'ASIDE') { BB-Stop 'нет подтверждения ASIDE. Запускайте только через 12_otkat_mavros_bp02.cmd.' 4 }
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$ssh = $null

function Run-Remote([string]$shPath, [string]$name, [string[]]$scriptArgs = @(), [int]$timeoutSec = 120) {
    $o = BB-NewOutFile $outDir ($name + '_' + $stamp + '.txt'); $e = BB-NewOutFile $outDir ($name + '_' + $stamp + '.err.txt')
    $remote = BB-RemoteCommand $shPath $scriptArgs
    $rc = BB-RunSsh $script:ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $o $e $timeoutSec
    return @{ Code = $rc; Out = $o; Text = $(if (Test-Path -LiteralPath $o) { [IO.File]::ReadAllText($o) } else { '' }) }
}

if ($Mode -eq 'aside') {
    $sh = Join-Path $here 'pi\mavros_build_aside.sh'
    if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
    $ssh = BB-FindSsh; BB-TestDrone $ssh
    $r = Run-Remote $sh 'mavros_aside' @() 180
    Get-Content -LiteralPath $r.Out -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
    if ($r.Code -eq 0 -and $r.Text -match 'BB_ASIDE_DONE') { Write-Host 'Готово: собранное перенесено в сторону (в ~/bench_ws/_aside_mavros_<метка>), ничего не удалено. Штатный MAVROS из apt не менялся. Проверьте 10_mavros_versiya.cmd.'; exit 0 }
    BB-Stop ('перенос не сделан или не закончен (код ' + $r.Code + '), строки выше. Ничего не удалялось.') 4
}

# ---- build ----
# 1. набор rc3 на ПК: суммы
$tl = Join-Path $kit 'TRANSFER_SHA256SUMS.txt'
if (-not (Test-Path -LiteralPath $tl)) { BB-Stop ('нет ' + $tl) 4 }
$tsum = (Get-FileHash -Algorithm SHA256 -LiteralPath $tl).Hash.ToLower()
if ($tsum -cne '8bb424779406342b776f62fbc71bbb0bd59c5772a77e8f19e400d0e38b22e363') { BB-Stop ('TRANSFER_SHA256SUMS.txt набора rc3 не тот (' + $tsum + '), ожидается 8bb42477…') 4 }
$expect = @{}
foreach ($l in [IO.File]::ReadAllLines($tl)) { if ($l -match '^([0-9a-f]{64})\s+(\S+)$') { $expect[$Matches[2]] = $Matches[1] } }
if ($expect.Count -ne 15) { BB-Stop ('в TRANSFER_SHA256SUMS.txt ' + $expect.Count + ' файлов вместо 15') 4 }
foreach ($k in $expect.Keys) {
    $p = Join-Path $kit $k
    if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('в наборе rc3 нет файла ' + $k) 4 }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() -cne $expect[$k]) { BB-Stop ('файл набора rc3 ' + $k + ' не сходится с TRANSFER_SHA256SUMS.txt') 4 }
}
$extra = @(Get-ChildItem -LiteralPath $kit -File | Where-Object { $_.Name -ne 'TRANSFER_SHA256SUMS.txt' -and -not $expect.ContainsKey($_.Name) })
if ($extra.Count -gt 0) { BB-Stop ('в наборе rc3 лишние файлы: ' + (($extra | ForEach-Object { $_.Name }) -join ', ')) 4 }
$et = [IO.File]::ReadAllText((Join-Path $kit 'EXPECTED_SRC.txt'))
if ($et -notmatch '(?m)^commit=d63a23674dd80ff4525829ca4bd716bbcc773111\s*$' -or $et -notmatch '(?m)^tag=backport-02\s*$') { BB-Stop 'EXPECTED_SRC.txt набора rc3 не про backport-02 / d63a236' 4 }
# 2. проверка на Pi (только чтение)
$pre = Join-Path $here 'pi\mavros_build_precheck.sh'
if (-not (Test-Path -LiteralPath $pre)) { BB-Stop ('нет файла ' + $pre) 4 }
$ssh = BB-FindSsh; BB-TestDrone $ssh
$p1 = Run-Remote $pre 'mavros_precheck' @() 90
if ($p1.Code -ne 0 -or $p1.Text -notmatch 'BB_MBPRE_DONE') { BB-Stop ('проверка перед сборкой не закончилась (код ' + $p1.Code + '). К дрону ничего не записано.') 4 }
$aptFile = BB-NewOutFile $outDir ('mavros_apt_state_' + $stamp + '.txt')
[IO.File]::WriteAllText($aptFile, (((BB-PickLines $p1.Text 'MBPRE') -join "`r`n") + "`r`n"), (BB-Utf8NoBom))
foreach ($l in (BB-PickLines $p1.Text 'MBPRE')) { Write-Host $l }
if ($p1.Text -notmatch '(?m)^BB_MBPRE_RESULT OK\s*$') {
    $why = ([regex]::Match($p1.Text, '(?m)^BB_MBPRE_RESULT (.*)$')).Groups[1].Value
    BB-Stop ('сборку начинать нельзя: ' + $why + '. К дрону ничего не записано (состояние apt сохранено в ' + $aptFile + ').') 4
}
Write-Host ('Состояние apt-MAVROS «до» записано: ' + $aptFile)
# 3. подготовка папки передачи (имя rc3_mavros обязательно: так ждёт m1_unpack.sh), без перезаписи
$stg = Join-Path $outDir ('stage_mavros_' + $stamp)
if (Test-Path -LiteralPath $stg) { BB-Stop ('папка уже есть, не перезаписываю: ' + $stg) 4 }
New-Item -ItemType Directory -Path (Join-Path $stg 'rc3_mavros') | Out-Null
Get-ChildItem -LiteralPath $kit -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $stg 'rc3_mavros') }
# 4. передача: ИЗМЕНЕНИЯ НА ДРОНЕ НАЧИНАЮТСЯ
$logFile = BB-NewOutFile $outDir ('mavros_build_' + $stamp + '.log')
Add-Content -LiteralPath $logFile -Value ((Get-Date).ToString('s') + ' начало, набор rc3 r3 (TRANSFER 8bb42477), коммит d63a236, apt-состояние: ' + (Split-Path $aptFile -Leaf)) -Encoding UTF8
$ssh = BB-FindSsh
function Ssh-Cmd([string]$cmd, [int]$t) {
    $o = [IO.Path]::GetTempFileName(); $e = [IO.Path]::GetTempFileName()
    try {
        $rc = BB-RunSsh $script:ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $cmd + '"') $o $e $t
        $txt = Get-Content -LiteralPath $o -Raw -ErrorAction SilentlyContinue; $er = Get-Content -LiteralPath $e -Raw -ErrorAction SilentlyContinue
        Add-Content -LiteralPath $logFile -Value ($cmd + "`r`n" + $txt + $er) -Encoding UTF8
        return @{ Code = $rc; Text = [string]$txt }
    } finally { Remove-Item -LiteralPath $o, $e -ErrorAction SilentlyContinue }
}
$mk = Ssh-Cmd 'mkdir -p /home/lb/bench_ws/incoming && test ! -e /home/lb/bench_ws/incoming/rc3_mavros && echo MKDIR_OK' 60
if ($mk.Code -ne 0 -or $mk.Text -notmatch 'MKDIR_OK') { BB-Stop ('не удалось подготовить ~/bench_ws/incoming (код ' + $mk.Code + '). Журнал: ' + $logFile) 4 }
$so = [IO.Path]::GetTempFileName(); $se = [IO.Path]::GetTempFileName()
$scp = Get-Command scp -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $scp) { BB-Stop 'scp не найден на этом ПК' 4 }
$scpRc = BB-RunSsh $scp ('-o BatchMode=yes -o ConnectTimeout=15 -r "' + (Join-Path $stg 'rc3_mavros') + '" ' + $script:BB_DroneHost + ':/home/lb/bench_ws/incoming/') $so $se 180
Add-Content -LiteralPath $logFile -Value ('scp код ' + $scpRc + ' ' + (Get-Content -LiteralPath $se -Raw -ErrorAction SilentlyContinue)) -Encoding UTF8
Remove-Item -LiteralPath $so, $se -ErrorAction SilentlyContinue
if ($scpRc -ne 0) { BB-Stop ('копирование набора rc3 на Pi не удалось (код ' + $scpRc + '). Журнал: ' + $logFile) 4 }
# 5. M1: распаковка исходников (до 1 мин)
Write-Host 'M1: распаковка исходников bp02 на Pi (до 1 минуты) ...'
$m1 = Ssh-Cmd 'bash /home/lb/bench_ws/incoming/rc3_mavros/m1_unpack.sh < /dev/null 2>&1' 180
Write-Host $m1.Text
if ($m1.Code -ne 0 -or $m1.Text -notmatch 'RC3M_M1_OK') { Write-Host ('  M1 не дошёл до RC3M_M1_OK (код ' + $m1.Code + '). Сборка не начата. Журнал: ' + $logFile + '. Перенос в сторону: 12_otkat_mavros_bp02.cmd.') -ForegroundColor White -BackgroundColor Red; exit 6 }
# 6. M2: сборка (оценка 7-10 минут, с запасом 20; не измерено на Pi). ssh -tt: Ctrl+C и закрытие окна останавливают сборку (ловушка в m2_build.sh), m2_stop.sh останавливает из любого окна.
Write-Host ''
Write-Host '  M2: сборка MAVROS bp02 на Pi, около 7-10 минут (с запасом 20). Не закрывайте окно. Остановить: Ctrl+C или m2_stop.sh.  ' -ForegroundColor White -BackgroundColor DarkRed
$argv = @('-tt', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', $script:BB_DroneHost, 'bash /home/lb/bench_ws/incoming/rc3_mavros/m2_build.sh 1')
$ErrorActionPreference = 'Continue'
$lines = New-Object Collections.Generic.List[string]
& $ssh.Source @argv 2>&1 | ForEach-Object { $line = [string]$_; Write-Host $line; $lines.Add($line); Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 }
$code = $LASTEXITCODE
Add-Content -LiteralPath $logFile -Value ((Get-Date).ToString('s') + ' M2 завершился, код ssh ' + $code) -Encoding UTF8
Write-Host ''
if ($code -eq 0 -and (($lines -join "`n") -match 'RC3M_M2_OK')) {
    Write-Host ('Готово: MAVROS bp02 собран в ~/bench_ws/mavros (RC3M_M2_OK). Штатный MAVROS из apt, start_bumblebee.sh и параметры PX4 не менялись. Журнал: ' + $logFile)
    Write-Host 'Дальше (НЕ в этом файле): отпечатки сборки M3 и строка подключения M4, потом 10_mavros_versiya.cmd. Службу bumblebee владелец запускает сам (пароль).'
    exit 0
}
Write-Host ('  M2 не дошёл до RC3M_M2_OK (код ssh ' + $code + '). Скажите Claude. Журнал: ' + $logFile + '. Перенос собранного в сторону: 12_otkat_mavros_bp02.cmd.') -ForegroundColor White -BackgroundColor Red
exit 6
