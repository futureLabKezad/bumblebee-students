# run_r6_syscheck.ps1 (Claude, 12.11.2026, набор r6) - ТОЛЬКО ЧТЕНИЕ. Шаг 20: «ничего не отвалилось» Ч1–Ч6 (разбор P1), pi\r6_sys_check.sh. Около 1 минуты.
# Делать ДО каждой системной правки (это снимок «до»), сразу ПОСЛЕ неё и ещё раз после перезагрузки дрона. Новая версия шага 18 для служб (см. README r6):
# 18 r5 ждёт led-default, которого на исправном дроне нет (unit не включён; V1), поэтому 18 там даёт NOT_OK; 18 не менялся.
# Сравнение: с последним успешным файлом out\sys_check_*.txt (это «до»). Ч1 failed пуст; Ч2 семь служб active, NRestarts 0, нет ошибок в журнале за 10 минут,
# в ту же загрузку время входа в active не изменилось (служба не перезапускалась после «до»); Ч3 энергосбережение Wi-Fi выключено; Ч4 узлы ROS как в «до»;
# Ч5 pidstat 30 с только для сравнения; Ч6 смотрит владелец в приложении. Если после «до» менялся стек (события 07: установка/откат образа и варианта, сборки,
# подключение/отключение оверлея), Ч4 и «перезапуск после «до»» не сравниваются: другой список узлов и перезапуск службы тогда ожидаемы, файл становится новым «до».
# Плюс: правки ступени 1, которые по журналам шагов 23 сейчас применены, должны держаться
# (masked/inactive, hold forever) - так видно, что правка пережила перезагрузку.
# Файл: out\sys_check_<время>.txt (не перезаписывается), последняя строка «# VERDICT OK» или «# VERDICT NOT_OK».
# Коды выхода: 0 OK; 5 NOT_OK (что-то отвалилось или проверить нечем); 4 ошибка связи, чужой ПК или чужой дрон.
param([string]$Stamp = '')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if (-not $Stamp) { $Stamp = (Get-Date).ToString('yyyyMMdd_HHmmss') } elseif ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: ' + $Stamp) 4 }   # -Stamp только для тестов; переменные PowerShell не различают регистр: $stamp = $Stamp
$sh = Join-Path $here 'pi\r6_sys_check.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
# «до» выбирается ДО обращения к дрону: последний успешный файл
$base = $null
foreach ($f in @(Get-ChildItem -LiteralPath $outDir -File -Filter 'sys_check_*.txt' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch '\.err\.txt$|\.FAILED\.' } | Sort-Object LastWriteTime -Descending)) {
    if ((R6-LastLine $f.FullName) -ceq '# VERDICT OK') { $base = $f; break }
}
# Если ПОСЛЕ «до» менялся стек (те же события, что считает 07: установка/откат образа и варианта камеры, сборки, подключение оверлеев), другой список узлов
# и перезапуск служб ожидаемы: Ч4 и «перезапуск после «до»» не сравниваются, этот файл становится новым «до» (иначе после установки образа 20 не прошёл бы никогда).
$stackEvt = $null
if ($base) {
    $ev = @(Get-ChildItem -LiteralPath $outDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^(overlay_connect_|overlay_disconnect_|bb_build_|bb_aside_|mavros_build_|mavros_aside_|install_r2j_|rollback_r2j_|install_camera_dabd5076_)' -and $_.Name -notmatch '\.generated\.|\.err\.txt$' -and $_.LastWriteTime -gt $base.LastWriteTime } | Sort-Object LastWriteTime)
    if ($ev.Count -gt 0) { $stackEvt = $ev[-1] }
}
$ssh = BB-FindSsh
foreach ($n in @(('sys_check_' + $Stamp + '.txt'), ('sys_check_' + $Stamp + '.err.txt'))) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
BB-TestDrone $ssh
Write-Host 'Проверяю «ничего не отвалилось» Ч1–Ч6 (только чтение, около 1 минуты) ...'
$r = R6-Remote $ssh $sh @() $outDir ('sys_check_' + $stamp) 150
if ($r.Code -ne 0 -or $r.Text -notmatch 'BB_R6SC_DONE') {
    $failed = $r.Out -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $r.Out) { Move-Item -LiteralPath $r.Out -Destination $failed }
    BB-Stop ('проверка не закончилась (код ssh ' + $r.Code + '). ' + $r.Err) 4
}
$t = $r.Text
$why = New-Object Collections.Generic.List[string]
function KV([string]$line, [string]$key) { $m = [regex]::Match($line, '(?:^| )' + [regex]::Escape($key) + '=(\S*)'); if ($m.Success) { return $m.Groups[1].Value } else { return $null } }
# Ч1
$fc = @(R6-Lines $t 'SC_FAILED_COUNT'); $failedN = -1; if ($fc.Count -eq 1 -and $fc[0] -match '^\d+$') { $failedN = [int]$fc[0] }
if ($failedN -ne 0) { $why.Add('Ч1: systemctl --failed не пуст (' + $failedN + '): ' + ((R6-Lines $t 'SC_FAILED') -join ' | ')) }
# Ч2
$boot = @(R6-Lines $t 'SC_BOOT_ID'); $bootId = ''; if ($boot.Count -eq 1) { $bootId = $boot[0].Trim() }
$bt = ''; $bSvc = @{}; $bNodes = @(); $bBoot = ''
if ($base) {
    $bt = [IO.File]::ReadAllText($base.FullName)
    $bb = @(R6-Lines $bt 'SC_BOOT_ID'); if ($bb.Count -eq 1) { $bBoot = $bb[0].Trim() }
    foreach ($l in (R6-Lines $bt 'SC_SVC')) { $bSvc[($l -split ' ')[0]] = $l }
    $bNodes = @(R6-Lines $bt 'SC_NODE')
}
$svcs = @('bumblebee', 'wifi-manager', 'wifi-watchdog', 'notify-manager', 'avahi-daemon', 'NetworkManager', 'sys_metrics')
foreach ($s in $svcs) {
    $row = @(R6-Lines $t 'SC_SVC' | Where-Object { ($_ -split ' ')[0] -ceq $s })
    if ($row.Count -ne 1) { $why.Add('Ч2: ' + $s + ': нет строки состояния'); continue }
    $l = $row[0]
    if ((KV $l 'load') -cne 'loaded' -or (KV $l 'active') -cne 'active') { $why.Add('Ч2: ' + $s + ' не active (load=' + (KV $l 'load') + ', active=' + (KV $l 'active') + ', sub=' + (KV $l 'sub') + ')') }
    if ((KV $l 'nrestarts') -cne '0') { $why.Add('Ч2: ' + $s + ': NRestarts=' + (KV $l 'nrestarts') + ' (сама перезапускалась, скорее всего падала)') }
    if ($base -and -not $stackEvt -and $bootId -ne '' -and $bootId -ceq $bBoot -and $bSvc.ContainsKey($s)) {
        $e0 = KV $bSvc[$s] 'enter_mono'; $e1 = KV $l 'enter_mono'
        if ($e0 -and $e1 -and $e0 -cne $e1) { $why.Add('Ч2: ' + $s + ' перезапускалась после снимка «до» ' + $base.Name + ' (время входа в active ' + $e0 + ' -> ' + $e1 + ' мкс от загрузки)') }
    }
    $je = @(R6-Lines $t 'SC_JERR' | Where-Object { ($_ -split ' ')[0] -ceq $s })
    if ($je.Count -ne 1) { $why.Add('Ч2: ' + $s + ': нет строки журнала') }
    elseif ((KV $je[0] 'access') -cne 'ok') { $why.Add('Ч2: ' + $s + ': журнал прочитать нельзя (нет прав); проверить нечем, повышение прав не используется') }
    elseif ((KV $je[0] 'errors') -cne '0') { $why.Add('Ч2: ' + $s + ': в журнале за 10 минут ' + (KV $je[0] 'errors') + ' строк с Traceback, ImportError, ошибкой запуска или падением') }
}
# Ч3
$wf = @(R6-Lines $t 'SC_WIFI'); $wj = ''; if ($wf.Count -eq 1) { $wj = KV $wf[0] 'journal' }
if ($wj -cne 'disabled') {
    if ($wj -ceq 'enabled') { $why.Add('Ч3: энергосбережение Wi-Fi ВКЛЮЧЕНО (последняя строка ядра set_power_mgmt: power save enabled)') }
    else { $why.Add('Ч3: энергосбережение Wi-Fi проверить нечем (journal=' + $wj + ')') }
}
$wi = @(R6-Lines $t 'SC_WIFI_IW'); if ($wi.Count -eq 1 -and $wi[0] -ceq 'on') { $why.Add('Ч3: iw: Power save: on') }
# Ч4
$nrc = @(R6-Lines $t 'SC_NODES_RC'); $nodes = @(R6-Lines $t 'SC_NODE')
if ($nrc.Count -ne 1 -or $nrc[0] -cne '0' -or $nodes.Count -eq 0) { $why.Add('Ч4: список узлов ROS не прочитан (код ' + ($nrc -join ',') + ', узлов ' + $nodes.Count + ')') }
elseif ($base -and -not $stackEvt) {
    $cnt = @{}; foreach ($n in $bNodes) { $cnt[$n] = 1 + [int]$cnt[$n] }
    $cnt2 = @{}; foreach ($n in $nodes) { $cnt2[$n] = 1 + [int]$cnt2[$n] }
    $miss = @($cnt.Keys | Where-Object { [int]$cnt2[$_] -lt [int]$cnt[$_] } | Sort-Object)
    $extra = @($cnt2.Keys | Where-Object { [int]$cnt[$_] -lt [int]$cnt2[$_] } | Sort-Object)
    if ($miss.Count -gt 0 -or $extra.Count -gt 0) { $why.Add('Ч4: узлы ROS не как в «до» (' + $base.Name + '): пропали ' + ($miss -join ', ') + '; лишние ' + ($extra -join ', ')) }
}
# Ступень 1: применённые правки должны держаться (в том числе после перезагрузки)
$expect = @{}
foreach ($ch in 'fwupd', 'timers', 'snaphold') {
    $logs = @(Get-ChildItem -LiteralPath $outDir -File -Filter ('sys_' + $ch + '_*.log') -ErrorAction SilentlyContinue | Where-Object { $_.Name -match ('^sys_' + $ch + '_(apply|rollback)_') } | Sort-Object LastWriteTime)
    $state = ''
    foreach ($g in $logs) { $gt = [IO.File]::ReadAllText($g.FullName); if ($gt -match ('BB_SYS_DONE ' + $ch + ' (apply|rollback) OK')) { $state = $Matches[1] } }
    $expect[$ch] = $state
}
$st1 = @(R6-Lines $t 'SC_STEP1')
$units = @{ fwupd = @('fwupd-refresh.timer'); timers = @('man-db.timer', 'motd-news.timer', 'update-notifier-download.timer', 'update-notifier-motd.timer') }
foreach ($ch in 'fwupd', 'timers') {
    if ($expect[$ch] -ne 'apply') { continue }
    foreach ($u in $units[$ch]) {
        $row = @($st1 | Where-Object { ($_ -split ' ')[0] -ceq $u })
        if ($row.Count -ne 1 -or (KV $row[0] 'enabled') -cne 'masked' -or (KV $row[0] 'active') -cne 'inactive') { $why.Add('Ступень 1: ' + $u + ' по журналу шага 23 замаскирован, а сейчас ' + ($row -join ' ') + ' (правка не держится)') }
    }
}
if ($expect['snaphold'] -eq 'apply') {
    $row = @($st1 | Where-Object { $_.StartsWith('snap ') })
    if ($row.Count -ne 1 -or $row[0] -cnotmatch '^snap hold=forever\s*$') { $why.Add('Ступень 1: snap по журналу шага 23b на hold, а сейчас ' + ($row -join ' ') + ' (правка не держится)') }
}
# Ч5 (только для сравнения): средний %CPU по командам
$acc = @{}; $nn = @{}
foreach ($l in (R6-Lines $t 'SC_PS')) {
    if ($l.TrimStart().StartsWith('#') -or $l -match '^Linux ') { continue }
    $f = @($l.Trim() -split '\s+')
    if ($f.Count -lt 10) { continue }
    $cpu = 0.0; if (-not [double]::TryParse($f[7], [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$cpu)) { continue }
    $cmd = ($f[9..($f.Count - 1)] -join ' '); if ($cmd.Length -gt 70) { $cmd = $cmd.Substring(0, 70) }
    $acc[$cmd] = [double]$acc[$cmd] + $cpu; $nn[$cmd] = 1 + [int]$nn[$cmd]
}
$top = @($acc.Keys | Sort-Object { - $acc[$_] } | Select-Object -First 5 | ForEach-Object { ('{0,6:N1} %  {1}' -f ($acc[$_] / 6), $_) })
Write-Host ''
Write-Host ('Ч1 failed: ' + $failedN + '; Ч3 Wi-Fi power save: ' + $wj + '; Ч4 узлов: ' + $nodes.Count + $(if ($base -and $stackEvt) { ' (стек менялся после «до» ' + $base.Name + ': ' + $stackEvt.Name + '; узлы и перезапуски не сравниваются, этот файл - новое «до»)' } elseif ($base) { ' (сравнение с ' + $base.Name + ')' } else { ' (снимка «до» нет: этот файл станет «до»)' }))
foreach ($l in (R6-Lines $t 'SC_SVC')) { Write-Host ('  ' + $l) }
Write-Host 'Ч5 (pidstat 30 с, для сравнения, не критерий), больше всего CPU в среднем на интервал:'
foreach ($l in $top) { Write-Host ('  ' + $l) }
Write-Host ''
Write-Host 'Ч6 - посмотрите сами в приложении (это не проверяет файл): видео с главной и с передней камеры идёт; дрон виден в приложении и связь есть; телеметрия (высота, батарея) обновляется; огни и звук как обычно. Если что-то не так, скажите Claude.'
$bl = '# BASELINE ' + $(if ($base -and $stackEvt) { $base.Name + ' (стек менялся после него: ' + $stackEvt.Name + '; Ч4 и перезапуски не сравнивались)' } elseif ($base) { $base.Name } else { 'нет (этот файл - первый снимок «до»)' })
Add-Content -LiteralPath $r.Out -Value $bl -Encoding UTF8
if ($why.Count -eq 0) {
    Add-Content -LiteralPath $r.Out -Value '# VERDICT OK' -Encoding UTF8
    Write-Host 'Ч1–Ч5: НИЧЕГО НЕ ОТВАЛИЛОСЬ' -ForegroundColor White -BackgroundColor DarkGreen
    Write-Host ('Файл: ' + $r.Out)
    exit 0
}
foreach ($w in $why) { Add-Content -LiteralPath $r.Out -Value ('# WHY ' + $w) -Encoding UTF8 }
Add-Content -LiteralPath $r.Out -Value '# VERDICT NOT_OK' -Encoding UTF8
Write-Host 'СТОП: что-то не так:' -ForegroundColor White -BackgroundColor Red
foreach ($w in $why) { Write-Host (' - ' + $w) }
Write-Host '  Ничего не чинить и не перезапускать самому. Скажите Claude: решает чат 1. Если только что была правка ступени 1, её откат - свой файл 23*_otkat_*.cmd (после разрешения чата 1).'
Write-Host ('Файл: ' + $r.Out)
exit 5
