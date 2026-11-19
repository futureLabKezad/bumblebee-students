# run_bb_build.ps1 (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58) - МЕНЯЕТ ДРОН. ЗАГОТОВКА, Claude её не запускает: двойной щелчок владельца по 13_sborka_bumblebee_r2j.cmd (-Mode build) или 14_otkat_sborki_bumblebee.cmd (-Mode aside).
# build: пересборка ТОЛЬКО пакета bumblebee из исходников r2j (они стоят в ~/ros2_ws/src/bumblebee после 05_install_r2j.cmd) в ОТДЕЛЬНОМ оверлее ~/bench_ws/r2j, как 29.10 (набор s0b, step8b_build.sh, 2 мин 26 с, -j2).
#        ~/ros2_ws (прежняя сборка = резерв), /opt/ros, start_bumblebee.sh, параметры PX4 не трогаются; службу bumblebee останавливает ВЛАДЕЛЕЦ сам (пароль только его), батарею меряет сам.
# aside: переносит ~/bench_ws/r2j и журнал сборки в ~/bench_ws/_aside_bb_r2j_<метка>, ничего не удаляет.
# Коды выхода: 0 сборка прошла без stderr; 4 условия не выполнены или ошибка (изменений на дроне нет); 6 сборка начата, но не дошла до конца; 7 сборка прошла, но у неё есть stderr (строки показаны, решает чат 1; шаги дальше не делать).
param(
    [Parameter(Mandatory = $true)][ValidateSet('build', 'aside')][string]$Mode,
    [Parameter(Mandatory = $true)][string]$SafetyConfirmed
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if ($Mode -eq 'build' -and $SafetyConfirmed -ne 'BATTERY-SERVICE-BUILD') { BB-Stop 'не получены три подтверждения (батарея измерена, служба остановлена, начать сборку). Запускайте только через 13_sborka_bumblebee_r2j.cmd.' 4 }
if ($Mode -eq 'aside' -and $SafetyConfirmed -ne 'ASIDE') { BB-Stop 'нет подтверждения ASIDE. Запускайте только через 14_otkat_sborki_bumblebee.cmd.' 4 }
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
function Run-Remote([string]$genPath, [string]$name, [int]$timeoutSec) {
    $o = BB-NewOutFile $outDir ($name + '_' + $stamp + '.txt'); $e = BB-NewOutFile $outDir ($name + '_' + $stamp + '.err.txt')
    $remote = BB-RemoteCommand $genPath @()
    $rc = BB-RunSsh $script:ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $o $e $timeoutSec
    return @{ Code = $rc; Out = $o; Text = $(if (Test-Path -LiteralPath $o) { [IO.File]::ReadAllText($o) } else { '' }) }
}
$ssh = BB-FindSsh

if ($Mode -eq 'aside') {
    $gen = BL-Generate (Join-Path $here 'pi\bb_build_aside.sh') @{} $outDir ('bb_aside_' + $stamp + '.generated.sh')
    BB-TestDrone $ssh
    $r = Run-Remote $gen 'bb_aside' 180
    Get-Content -LiteralPath $r.Out -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
    if ($r.Code -eq 0 -and $r.Text -match 'BB_BBASIDE_DONE') { Write-Host 'Готово: сборка r2j перенесена в сторону (~/bench_ws/_aside_bb_r2j_<метка>), ничего не удалено. ~/ros2_ws не менялся.'; exit 0 }
    BB-Stop ('перенос не сделан или не закончен (код ' + $r.Code + '), строки выше. Ничего не удалялось.') 4
}

# ---- build ----
$cpp = BL-CppList $here; $hov = BL-HoverSha $here
$genPre = BL-Generate (Join-Path $here 'pi\bb_build_precheck.sh') @{ CPP = $cpp; HOVER = $hov } $outDir ('bb_precheck_' + $stamp + '.generated.sh')
$genBuild = BL-Generate (Join-Path $here 'pi\bb_build.sh') @{ CPP = $cpp; HOVER = $hov } $outDir ('bb_build_' + $stamp + '.generated.sh')
BB-TestDrone $ssh
$p1 = Run-Remote $genPre 'bb_precheck' 90
if ($p1.Code -ne 0 -or $p1.Text -notmatch 'BB_BBPRE_DONE') { BB-Stop ('проверка перед сборкой не закончилась (код ' + $p1.Code + '). К дрону ничего не записано.') 4 }
$stateFile = BB-NewOutFile $outDir ('bb_state_before_' + $stamp + '.txt')
[IO.File]::WriteAllText($stateFile, (((BB-PickLines $p1.Text 'BBPRE') -join "`r`n") + "`r`n"), (BB-Utf8NoBom))
foreach ($l in (BB-PickLines $p1.Text 'BBPRE')) { if ($l -notmatch '^BBPRE dep ') { Write-Host $l } }
if ($p1.Text -notmatch '(?m)^BB_BBPRE_RESULT OK\s*$') {
    $why = ([regex]::Match($p1.Text, '(?m)^BB_BBPRE_RESULT (.*)$')).Groups[1].Value
    BB-Stop ('сборку начинать нельзя: ' + $why + '. К дрону ничего не записано (состояние «до» в ' + $stateFile + ').') 4
}
Write-Host ('Состояние «до» записано: ' + $stateFile + '. Прежняя сборка ~/ros2_ws остаётся нетронутой (это и есть резерв).')
$logFile = BB-NewOutFile $outDir ('bb_build_' + $stamp + '.log')
Add-Content -LiteralPath $logFile -Value ((Get-Date).ToString('s') + ' начало сборки bumblebee r2j в ~/bench_ws/r2j; состояние до: ' + (Split-Path $stateFile -Leaf)) -Encoding UTF8
Write-Host ''
Write-Host '  Сборка пакета bumblebee на Pi: ОЦЕНКА около 2,5 минут (29.10 на этом Pi: 2 мин 26 с, -j2), с запасом 10. Не закрывайте окно. Остановить: Ctrl+C.  ' -ForegroundColor White -BackgroundColor DarkRed
$remote = BB-RemoteCommand $genBuild @()
$argv = @('-tt', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3', $script:BB_DroneHost, $remote)
$ErrorActionPreference = 'Continue'
$lines = New-Object Collections.Generic.List[string]
& $ssh.Source @argv 2>&1 | ForEach-Object { $line = [string]$_; Write-Host $line; $lines.Add($line); Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8 }
$code = $LASTEXITCODE
Add-Content -LiteralPath $logFile -Value ((Get-Date).ToString('s') + ' сборка завершилась, код ssh ' + $code) -Encoding UTF8
$all = ($lines -join "`n")
Write-Host ''
if ($all -match 'BB_BBBUILD_OK (\d+)') { Write-Host ('Готово: bumblebee r2j собран в ~/bench_ws/r2j за ' + $Matches[1] + ' с, stderr нет. Дальше: 15_otpechatki_sborki.cmd. Журнал: ' + $logFile); exit 0 }
if ($all -match 'BB_BBBUILD_STDERR') { Write-Host ('  Сборка прошла, но у неё есть stderr (строки выше). Дальше НЕ идти: решает чат 1. Журнал: ' + $logFile) -ForegroundColor White -BackgroundColor DarkRed
    # S4 (чат 1, 21:50): код 7 = СТОП. Ничего не игнорировать, не повторять сборку, не продолжать 15, 16, 09, 10.
    if ($all -match 'led_msgs not found') { Write-Host '  В журнале есть известное предупреждение «led_msgs not found — skipping led node» (то же было в журнале сборки 29.10; скорее всего, на дроне нет пакета led_msgs и узел led пропускается). Другие строки stderr, если они есть, проверьте выше. Это НЕ значит «можно продолжать»: решает чат 1.' }
    else { Write-Host '  Причина НЕ известная (в журнале нет «led_msgs not found»): смотрите строки выше с stderr или WARNING.' }
    Write-Host '  Что делать: ничего не запускать и сборку не повторять. Прислать чату 1 (через Claude) файл журнала, который назван выше (out\bb_build_<время>.log), и сказать «код 7». Сборка в ~/bench_ws/r2j остаётся на диске, ~/ros2_ws не тронут, ~/ros2_ws не менялся, подключение оверлея не делалось; убирать сборку (14) не нужно, пока чат 1 не решил.'
    exit 7 }
Write-Host ('  Сборка не дошла до конца (код ssh ' + $code + '). Скажите Claude. Журнал: ' + $logFile + '. Перенос в сторону: 14_otkat_sborki_bumblebee.cmd.') -ForegroundColor White -BackgroundColor Red
exit 6
