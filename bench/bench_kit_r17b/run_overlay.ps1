# run_overlay.ps1 (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58) - МЕНЯЕТ ДРОН. ЗАГОТОВКА, Claude её не запускает: двойной щелчок владельца по 16_podkljuchit_overlay.cmd (-Mode connect) или 17_otkljuchit_overlay.cmd (-Mode disconnect).
# connect: подключает собранный оверлей (-Target mavros или bumblebee) одной строкой в ~/start_bumblebee.sh (pi\overlay_connect.sh). ТОЛЬКО ПОСЛЕ «ДА» ВЛАДЕЛЬЦА: нужен файл gates\OVERLAY_<ЦЕЛЬ>_APPROVED.txt от чата 1 со словами владельца
#          и sha256 файла отпечатков (out\fingerprint_<цель>_*.txt, самый свежий, с VERDICT OK, снят шагом 15). Файлы оверлея на Pi должны быть ровно как в отпечатках.
# disconnect: возвращает start_bumblebee.sh из копии «до» (pi\overlay_disconnect.sh), то есть откат на штатный MAVROS из apt и прежнюю сборку ros2_ws; оверлей на диске остаётся; гейт «да» для отката не нужен.
# Службу bumblebee владелец останавливает и запускает сам (пароль только его).
# Коды выхода: 0 готово; 4 условия не выполнены или ошибка (файл на Pi не менялся).
param(
    [Parameter(Mandatory = $true)][ValidateSet('connect', 'disconnect')][string]$Mode,
    [Parameter(Mandatory = $true)][ValidateSet('mavros', 'bumblebee', 'last')][string]$Target,
    [Parameter(Mandatory = $true)][string]$SafetyConfirmed
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if ($Mode -eq 'connect' -and $Target -eq 'last') { BB-Stop 'для подключения цель mavros или bumblebee' 4 }
if ($Mode -eq 'connect' -and $SafetyConfirmed -ne 'CONNECT-SERVICE') { BB-Stop 'нет подтверждений (служба остановлена, подключить). Запускайте только через 16_podkljuchit_overlay.cmd.' 4 }
if ($Mode -eq 'disconnect' -and $SafetyConfirmed -ne 'DISCONNECT-SERVICE') { BB-Stop 'нет подтверждений (служба остановлена, отключить). Запускайте только через 17_otkljuchit_overlay.cmd.' 4 }
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$ssh = BB-FindSsh
function Run-Remote([string]$genPath, [string]$name, [string[]]$scriptArgs) {
    $o = BB-NewOutFile $outDir ($name + '_' + $stamp + '.txt'); $e = BB-NewOutFile $outDir ($name + '_' + $stamp + '.err.txt')
    $remote = BB-RemoteCommand $genPath $scriptArgs
    $rc = BB-RunSsh $script:ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $o $e 120
    return @{ Code = $rc; Out = $o; Text = $(if (Test-Path -LiteralPath $o) { [IO.File]::ReadAllText($o) } else { '' }) }
}
if ($Mode -eq 'disconnect') {
    $gen = BL-Generate (Join-Path $here 'pi\overlay_disconnect.sh') @{} $outDir ('overlay_disconnect_' + $stamp + '.generated.sh')
    BB-TestDrone $ssh
    $r = Run-Remote $gen 'overlay_disconnect' @()
    Get-Content -LiteralPath $r.Out -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
    if ($r.Code -eq 0 -and $r.Text -match 'BB_DISC_DONE') { Write-Host 'Готово: start_bumblebee.sh возвращён из копии «до», оверлей на диске остался. Службу запускаете сами (пароль). Проверьте 10_mavros_versiya.cmd и 09_sverka_install.cmd.'; exit 0 }
    BB-Stop ('откат не сделан (код ' + $r.Code + '), строки выше. Файл start_bumblebee.sh не менялся.') 4
}
# ---- connect ----
$T = $Target
$bad = New-Object Collections.Generic.List[string]
$fps = @(Get-ChildItem -LiteralPath $outDir -Filter ('fingerprint_' + $T + '_*.txt') -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' } | Sort-Object LastWriteTime)
$fp = $null; if ($fps.Count -gt 0) { $fp = $fps[-1] }
if (-not $fp) { $bad.Add('нет отпечатков оверлея ' + $T + ' (out\fingerprint_' + $T + '_*.txt): сначала 15_otpechatki_sborki.cmd после сборки.') }
else {
    $fpText = [IO.File]::ReadAllText($fp.FullName)
    if ($fpText -notmatch '(?m)^# VERDICT OK\s*$') { $bad.Add('в последних отпечатках ' + $T + ' нет «VERDICT OK»: ' + $fp.Name) }
}
$ap = Join-Path $here ('gates\OVERLAY_' + $T.ToUpper() + '_APPROVED.txt')
if (-not (Test-Path -LiteralPath $ap)) { $bad.Add('нет gates\OVERLAY_' + $T.ToUpper() + '_APPROVED.txt: «да» владельца на подключение оверлея ' + $T + ' ещё не записано чатом 1.') }
else {
    $at = Get-Content -LiteralPath $ap -Encoding UTF8
    foreach ($k in ('ПОДКЛЮЧИТЬ=' + $T), 'ВЛАДЕЛЕЦ_СКАЗАЛ=да', 'СОЗДАЛ=чат 1') { if (-not ($at | Where-Object { $_.Trim() -ceq $k })) { $bad.Add('в ' + (Split-Path $ap -Leaf) + ' нет строки ' + $k) } }
    foreach ($k in 'ДАТА=', 'СЛОВА_ВЛАДЕЛЬЦА=') { if (-not ($at | Where-Object { $_.Trim().StartsWith($k) -and $_.Trim().Length -gt $k.Length })) { $bad.Add('в ' + (Split-Path $ap -Leaf) + ' нет заполненной строки ' + $k + '...') } }
    if ($fp) {
        $fpSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $fp.FullName).Hash.ToLower()
        if (-not ($at | Where-Object { $_.Trim() -ceq ('ОТПЕЧАТКИ_SHA256=' + $fpSha) })) { $bad.Add('в ' + (Split-Path $ap -Leaf) + ' нет строки ОТПЕЧАТКИ_SHA256=' + $fpSha + ' (разрешение выдано не для этих отпечатков: после новой сборки или нового снятия отпечатков нужно новое разрешение)') }
    }
}
if ($bad.Count -gt 0) {
    Write-Host ''
    Write-Host '  СТОП: подключение оверлея не разрешено. К дрону не обращались. Не выполнены условия:  ' -ForegroundColor White -BackgroundColor Red
    foreach ($b in $bad) { Write-Host (' - ' + $b) }
    exit 4
}
$fpList = New-Object Collections.Generic.List[string]
foreach ($l in [IO.File]::ReadAllLines($fp.FullName)) { if ($l -match '^[0-9a-f]{64}  \S+$') { $fpList.Add($l) } }
if ($fpList.Count -lt 1) { BB-Stop ('в файле отпечатков нет ни одной строки «sha256  путь»: ' + $fp.Name) 4 }
# Правка по проверке 10.11 (M1): список из ~500 строк не помещается в командную строку ssh (предел Windows 32 767 знаков), поэтому на Pi уходят только
# сумма списка и число файлов. Список: строки «sha256  путь» (пути от install), сортировка по байтам пути (как LC_ALL=C sort), каждая строка с переводом строки.
$fpKeys = [string[]]@($fpList | ForEach-Object { $_.Substring(66) }); $fpVals = [string[]]@($fpList)
[Array]::Sort($fpKeys, $fpVals, [StringComparer]::Ordinal)
$fpText = (($fpVals -join "`n") + "`n")
$fpHash = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash((New-Object Text.UTF8Encoding($false)).GetBytes($fpText))) -replace '-', '').ToLower()
$fpCfg = @(('FPHASH=' + $fpHash), ('FPCOUNT=' + $fpList.Count))
$gen = BL-Generate (Join-Path $here 'pi\overlay_connect.sh') @{ FPCFG = $fpCfg } $outDir ('overlay_connect_' + $T + '_' + $stamp + '.generated.sh')
BB-TestDrone $ssh
# Решение чата 1 (20:10): СНАЧАЛА только чтением читаем нынешний start_bumblebee.sh на дроне и сравниваем с известным по s0b
# (image_r2j\START_BUMBLEBEE_BASELINE_s0b.sh, sha256 58c14783…). Отличается: СТОП, решает владелец, файл не менялся.
$base = Join-Path $here 'image_r2j\START_BUMBLEBEE_BASELINE_s0b.sh'
if (-not (Test-Path -LiteralPath $base)) { BB-Stop ('нет эталона ' + $base) 4 }
$bt = ([IO.File]::ReadAllText($base)) -replace "`r`n", "`n"
function BL-Sha([string]$text) { return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash((New-Object Text.UTF8Encoding($false)).GetBytes($text))) -replace '-', '').ToLower() }
$lws = 'source /home/lb/ros2_ws/install/setup.bash'; $lmv = 'source /home/lb/bench_ws/mavros/install/local_setup.bash'
$allowed = @{}
$allowed[(BL-Sha $bt)] = 'как в s0b (эталон)'
if ($T -eq 'bumblebee') { $allowed[(BL-Sha ($bt.Replace($lws + "`n", $lws + "`n" + $lmv + "`n")))] = 'как в s0b плюс строка MAVROS сразу после ros2_ws (подключено этим набором)' }
$genSsc = BL-Generate (Join-Path $here 'pi\start_script_check.sh') @{} $outDir ('start_script_check_' + $T + '_' + $stamp + '.generated.sh')
$p0 = Run-Remote $genSsc ('start_script_check_' + $T) @()
Get-Content -LiteralPath $p0.Out -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
$ms = [regex]::Match($p0.Text, '(?m)^SSC sha256 ([0-9a-f]{64}) bytes (\d+)')
if ($p0.Code -ne 0 -or $p0.Text -notmatch 'BB_SSC_DONE' -or -not $ms.Success) {
    BB-Stop ('нынешний start_bumblebee.sh прочитать не удалось (код ' + $p0.Code + '): ' + $(if ($p0.Text -match 'SSC missing') { 'файла нет на дроне' } else { 'ответ неполный' }) + '. Решает владелец. Файл не менялся.') 4
}
if (-not $allowed.ContainsKey($ms.Groups[1].Value)) {
    Write-Host ''
    Write-Host '  СТОП: start_bumblebee.sh на дроне ОТЛИЧАЕТСЯ от известного по s0b. Подключение не делается, файл не менялся. Решает владелец.  ' -ForegroundColor White -BackgroundColor Red
    Write-Host (' - на дроне sha256 ' + $ms.Groups[1].Value + ', байт ' + $ms.Groups[2].Value + '; допустимо: ' + (($allowed.Keys | ForEach-Object { $_ + ' (' + $allowed[$_] + ')' }) -join '; '))
    exit 4
}
Write-Host ('start_bumblebee.sh на дроне ' + $allowed[$ms.Groups[1].Value] + ': можно подключать (оверлей встанет после строки source ~/ros2_ws, чтобы перекрывать его).')
$r = Run-Remote $gen ('overlay_connect_' + $T) @($T)
Get-Content -LiteralPath $r.Out -ErrorAction SilentlyContinue | Where-Object { $_ -notmatch '^FPGOT ' } | ForEach-Object { Write-Host $_ }
if ($r.Text -match '(?m)^FPGOT ') {
    # Pi показал, что у него лежит; называем отличия от отпечатков (до 15 строк). Дрон при этом не менялся.
    $got = @{}; foreach ($l in ($r.Text -split "`r?`n")) { if ($l -match '^FPGOT ([0-9a-f]{64})  (\S+)$') { $got[$Matches[2]] = $Matches[1] } }
    $want = @{}; foreach ($l in $fpList) { $want[$l.Substring(66)] = $l.Substring(0, 64) }
    $diffs = New-Object Collections.Generic.List[string]
    foreach ($k in ($want.Keys | Sort-Object)) { if (-not $got.ContainsKey($k)) { $diffs.Add('нет на Pi: ' + $k) } elseif ($got[$k] -ne $want[$k]) { $diffs.Add('другое содержимое: ' + $k) } }
    foreach ($k in ($got.Keys | Sort-Object)) { if (-not $want.ContainsKey($k)) { $diffs.Add('лишний на Pi: ' + $k) } }
    Write-Host ('Отличия оверлея от отпечатков (' + $diffs.Count + '):')
    foreach ($d in ($diffs | Select-Object -First 15)) { Write-Host (' - ' + $d) }
}
if ($r.Code -eq 0 -and $r.Text -match 'BB_CONN_DONE') { Write-Host ('Готово: оверлей ' + $T + ' подключён строкой в start_bumblebee.sh (копии до и после: ~/bench_ws/_bk_start_bumblebee_<метка>). Службу запускаете сами (пароль). Откат: 17_otkljuchit_overlay.cmd. Затем 09 и 10.'); exit 0 }
BB-Stop ('подключение не сделано (код ' + $r.Code + '), строки выше. start_bumblebee.sh не менялся.') 4
