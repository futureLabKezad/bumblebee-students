# run_r8_metki.ps1 (Claude, 13.11.2026, набор r8) - МЕНЯЕТ ДРОН временно. Шаг 25 (25_metki_nomera.cmd): ложные номера меток и поза по меткам, pi\r8_marker_wake.sh.
# Что меняет: Pi будит детектор меток сигналом /aruco_detect/wake раз в секунду, только во время окон записи (как 03, pi\vision_measure.sh); проснувшийся детектор
#   шлёт позу /aruco_map/pose, vpe_fix передаёт её в EKF2 и на НЕвзведённом дроне - меняется оценка положения EKF на земле. Файлы, параметры PX4, моторы не трогаются.
#   Как вернуть: детектор засыпает сам через 5 с после окна; EKF - выключить и включить дрон или сверить позицию EKF с рулеткой (последняя строка окна .cmd).
# Дрон неподвижно над меткой 0, сдвиги 0 / 5 / 10 / 15 см назад вдоль носа (рулетка). Проверка (pre, около 6 с) - уже с wake; потом 4 точки по 10 с (+2 с разгона).
# Правила СТОП (код 5, запись сразу прекращается, дальше точки не идут):
#   - номер с карты (0-20 без 17 и все номера карты дрона), но не 0 - «ЛОЖНЫЙ НОМЕР С КАРТЫ — СТОП»; номер не 0 и не с карты - «ЛОЖНЫЙ НОМЕР — СТОП»;
#   - поза /aruco_map/pose дальше 0,15 м от рулетки: |расстояние позы от метки 0 по карте - сдвиг по рулетке| > 0,15 м хотя бы у одной позы;
#   - в /tmp/bumblebee.log строка vpe_fix «gate RESEEDED» на позу дальше 0,15 м от рулетки (так же), или её позицию не разобрать.
# НЕ ПРОВЕРЕНО (код 6): детектор молчит даже с wake (на rc3 детектор 7eb7bdf3 wake не слушает); в точке нет сообщений, метка 0 не прочитана ни разу, нет ни одной позы,
#   карта или журнал vpe_fix не прочитаны; запись остановлена. Код 0 - все 4 точки: только номер 0, номер 0 прочитан, позы есть и все не дальше 0,15 м, RESEEDED на чужую позу нет.
# Вызывает только 25_metki_nomera.cmd, по фазам (вопросы «наберите N» задаёт .cmd): -Phase pre (проверка), rec -Cm N (запись точки), stop -Cm N (остановка), final (итог).
# Пишет на ПК out\metki_nomera_<метка>.txt (сводка; последняя строка «# VERDICT ...» - только в конце) и сырые ответы Pi out\metki_nomera_<метка>_<точка>.txt
#   (номер, центр и 4 угла каждой метки в каждом кадре, позы, строки RESEEDED); ничего не перезаписывает.
# Коды выхода: pre/rec - 0 можно дальше; 5 СТОП; 6 НЕ ПРОВЕРЕНО; 3 НЕ НАЧАТО (дрон взведён, нет связи с FCU или /mavros/state); 4 ошибка (ПК, связь, чужой дрон, файл уже есть, порядок фаз).
param([ValidateSet('pre', 'rec', 'stop', 'final')][string]$Phase = 'pre', [string]$Stamp = '', [int]$Cm = -1)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_r6.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
if ($Stamp -notmatch '^\d{8}_\d{6}$') { BB-Stop ('метка -Stamp не ГГГГММДД_ЧЧММСС: «' + $Stamp + '». Запускайте 25_metki_nomera.cmd.') 4 }
$points = @(0, 5, 10, 15)
if ($Phase -in 'rec', 'stop' -and $points -notcontains $Cm) { BB-Stop ('сдвиг -Cm должен быть 0, 5, 10 или 15, а не ' + $Cm) 4 }
$sh = Join-Path $here 'pi\r8_marker_wake.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$TOL = 0.15                                       # м: «поза дальше 0,15 м от рулетки» - СТОП
$MAP_FIXED = @(0..20 | Where-Object { $_ -ne 17 })   # номера карты поля 20EC (map.txt, копия дрона 12.11, sha256 528b5adb...): 0-20 без 17
$MAP_SHA_1211 = '528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611'
$MAP_SHA_REAL_1611 = '545e8e4617f4405cf7b9234f302c249ce60592c0b5487f02520f109d292a0826'   # r11: карта real 16.11 (map_final.txt, копия real_map_20261116\): те же номера 0-20 без 17; только подпись в сводке
$inv = [Globalization.CultureInfo]::InvariantCulture
$base = 'metki_nomera_' + $Stamp
$sumFile = Join-Path $outDir ($base + '.txt')
function Add-Sum([string]$s) {
    if (-not (Test-Path -LiteralPath $script:sumFile)) { [IO.File]::WriteAllBytes($script:sumFile, [byte[]](0xEF, 0xBB, 0xBF)) }
    [IO.File]::AppendAllText($script:sumFile, $s + "`r`n", (New-Object Text.UTF8Encoding($false)))
}
function Finish([int]$code, [string]$verdict, [string]$text) {
    Add-Sum ('ИТОГ ' + $text)
    Add-Sum ('# VERDICT ' + $verdict)
    $bg = 'DarkYellow'; if ($code -eq 0) { $bg = 'DarkGreen' } elseif ($code -eq 5 -or $code -eq 4) { $bg = 'DarkRed' }
    Write-Host ''
    Write-Host ('  ' + $text + '  ') -ForegroundColor White -BackgroundColor $bg
    Write-Host ('Файл: ' + $script:sumFile)
    exit $code
}
function D([string]$s) { return [double]::Parse($s, $script:inv) }
function F3([double]$v) { return $v.ToString('0.000', $script:inv) }
# Ответ Pi: конец, отказ по безопасности, ошибка.
function Check-Reply($r, [string]$what) {
    if ($r.Text -notmatch 'BB_R8MN_DONE') {
        if (Test-Path -LiteralPath $r.Out) { Move-Item -LiteralPath $r.Out -Destination ($r.Out -replace '\.txt$', '.FAILED.txt') }
        Finish 4 'ERROR' ($what + ': ответ Pi без конца (код ssh ' + $r.Code + '). ' + $r.Err.Trim())
    }
    $ref = @(R6-Lines $r.Text 'MN_REFUSED')
    if ($ref.Count -gt 0) {
        $woke = @(R6-Lines $r.Text 'MN_WAKE').Count -gt 0
        $tail = $(if ($woke) { ' Детектор будился, wake прекращён.' } else { ' Детектор не будился, на дроне ничего не менялось.' })
        Finish 3 'NOT_STARTED' ('НЕ НАЧАТО (' + $what + '): ' + ($ref -join '; ') + '.' + $tail)
    }
    $er = @(R6-Lines $r.Text 'MN_ERROR')
    if ($er.Count -gt 0 -or $r.Code -ne 0) { Finish 4 'ERROR' ($what + ': ошибка на Pi (код ' + $r.Code + '): ' + ($er -join '; ')) }
}
function Num([string]$line, [string]$key) {
    $m = [regex]::Match($line, '(?:^|\s)' + $key + '=(\d+)(?:\s|$)')
    if (-not $m.Success) { return -1 }
    return [int]$m.Groups[1].Value
}
# Разбор и оценка одного ответа Pi (фаза pre - сдвиг 0 см, дрон над меткой 0; rec - сдвиг Cm по рулетке).
# Возвращает @{ Line; Stop (причины СТОП); Flags (НЕ ПРОВЕРЕНО: NO_DATA, NO_ZERO, NO_POSE, NO_MAP, NO_LOG); LogTo; Msgs }
function Eval-Reply($r, [int]$cm, [string]$what) {
    $t = $r.Text
    $end = @(R6-Lines $t 'MN_END'); $det = @(R6-Lines $t 'MN_DETECTOR'); $mapL = @(R6-Lines $t 'MN_MAP'); $logL = @(R6-Lines $t 'MN_LOG')
    if ($end.Count -ne 1 -or $det.Count -ne 1 -or $mapL.Count -ne 1 -or $logL.Count -ne 1) { Finish 4 'ERROR' ($what + ': в ответе Pi нет ровно одной строки MN_END, MN_DETECTOR, MN_MAP и MN_LOG.') }
    $msgs = Num $end[0] 'msgs'; $wm = Num $end[0] 'with_markers'; $np = Num $end[0] 'poses'
    $ids = [regex]::Match($end[0], '(?:^|\s)ids=(\S+)').Groups[1].Value
    if ($msgs -lt 0 -or $wm -lt 0 -or $np -lt 0 -or $ids -eq '') { Finish 4 'ERROR' ($what + ': строка MN_END не разобрана: ' + $end[0]) }
    $nMsg = @(R6-Lines $t 'MN_MSG').Count
    if ($nMsg -ne $msgs) { Finish 4 'ERROR' ($what + ': строк MN_MSG ' + $nMsg + ', а в MN_END msgs=' + $msgs) }
    $poseL = @(R6-Lines $t 'MN_POSE')
    if ($poseL.Count -ne $np) { Finish 4 'ERROR' ($what + ': строк MN_POSE ' + $poseL.Count + ', а в MN_END poses=' + $np) }
    $stop = New-Object Collections.Generic.List[string]; $flags = New-Object Collections.Generic.List[string]
    # карта: номера и место метки 0 (карта дрона, только чтение)
    $mapIds = @($MAP_FIXED); $m0 = $null; $mapNote = ''
    $mm = [regex]::Match($mapL[0], '^file=(\S+) sha256=([0-9a-f]{64}) ids=(\S+) m0=(\S+)$')
    if ($mm.Success) {
        if ($mm.Groups[3].Value -ne 'none') { foreach ($x in ($mm.Groups[3].Value -split ',')) { if ($x -match '^-?\d+$') { $mapIds += [int]$x } } }
        $mz = [regex]::Match($mm.Groups[4].Value, '^(-?[0-9.]+),(-?[0-9.]+),(-?[0-9.]+)$')
        if ($mz.Success) { $m0 = @((D $mz.Groups[1].Value), (D $mz.Groups[2].Value)) }
        if ($mm.Groups[2].Value -eq $MAP_SHA_REAL_1611) { $mapNote = ' карта на дроне - карта real 16.11 (map_final.txt, sha256 545e8e46...)' }
        elseif ($mm.Groups[2].Value -ne $MAP_SHA_1211) { $mapNote = ' карта на дроне не та, что в копии 12.11 (sha256 ' + $mm.Groups[2].Value.Substring(0, 8) + '...)' }
    }
    if ($null -eq $m0) { $flags.Add('NO_MAP') }
    # номера
    $seen0 = $false
    if ($ids -ne 'none') {
        foreach ($kv in ($ids -split ',')) {
            if ($kv -notmatch '^(-?\d+):(\d+)$') { Finish 4 'ERROR' ($what + ': номера не разобраны: ' + $ids) }
            $i = [int]$Matches[1]; $k = $Matches[2]
            if ($i -eq 0) { $seen0 = $true }
            elseif ($mapIds -contains $i) { $stop.Add('ЛОЖНЫЙ НОМЕР С КАРТЫ — СТОП: номер ' + $i + ' — ' + $k + ' раз') }
            else { $stop.Add('ЛОЖНЫЙ НОМЕР — СТОП: номер ' + $i + ' — ' + $k + ' раз (на карте его нет)') }
        }
    }
    if ($msgs -eq 0) { $flags.Add('NO_DATA') } elseif (-not $seen0) { $flags.Add('NO_ZERO') }
    # позы против рулетки: |расстояние от метки 0 - сдвиг| (без направления: рулетка задаёт расстояние от центра метки 0)
    $want = $cm / 100.0; $maxDev = -1.0; $nBad = 0; $dMin = $null; $dMax = $null
    if ($np -eq 0) { $flags.Add('NO_POSE') }
    elseif ($null -ne $m0) {
        foreach ($pl in $poseL) {
            $pm = [regex]::Match($pl, '^t=\S+ x=(-?[0-9.]+) y=(-?[0-9.]+) z=(-?[0-9.]+) yaw=\S+$')
            if (-not $pm.Success) { Finish 4 'ERROR' ($what + ': строка MN_POSE не разобрана: ' + $pl) }
            $d = [Math]::Sqrt([Math]::Pow((D $pm.Groups[1].Value) - $m0[0], 2) + [Math]::Pow((D $pm.Groups[2].Value) - $m0[1], 2))
            $dev = [Math]::Abs($d - $want)
            if ($dev -gt $maxDev) { $maxDev = $dev }
            if ($null -eq $dMin -or $d -lt $dMin) { $dMin = $d }; if ($null -eq $dMax -or $d -gt $dMax) { $dMax = $d }
            if ($dev -gt $TOL) { $nBad++ }
        }
        if ($nBad -gt 0) { $stop.Add('ПОЗА ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП: ' + $nBad + ' из ' + $np + ' поз; по позе от центра метки 0 ' + (F3 $dMin) + '…' + (F3 $dMax) + ' м, по рулетке ' + (F3 $want) + ' м') }
    }
    # журнал vpe_fix: RESEEDED
    $logTo = $null; $nRs = 0
    $lm = [regex]::Match($logL[0], 'readable=yes from=(\d+) to=(\d+) ')
    if ($lm.Success) { $logTo = $lm.Groups[2].Value } else { $flags.Add('NO_LOG') }
    foreach ($rl in @(R6-Lines $t 'MN_RESEED')) {
        $nRs++
        $rm = [regex]::Match($rl, '^reason=\S+ x=(-?[0-9.]+) y=(-?[0-9.]+) z=(-?[0-9.]+) ')
        if (-not $rm.Success) { $stop.Add('RESEEDED — СТОП: позицию из строки vpe_fix не разобрать: ' + $rl); continue }
        if ($null -eq $m0) { $stop.Add('RESEEDED — СТОП: карта не прочитана, позицию не с чем сверить: ' + $rl); continue }
        $d = [Math]::Sqrt([Math]::Pow((D $rm.Groups[1].Value) - $m0[0], 2) + [Math]::Pow((D $rm.Groups[2].Value) - $m0[1], 2))
        if ([Math]::Abs($d - $want) -gt $TOL) { $stop.Add('RESEEDED НА ПОЗУ ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП: от центра метки 0 ' + (F3 $d) + ' м, по рулетке ' + (F3 $want) + ' м (' + $rl + ')') }
    }
    $ekf = @(R6-Lines $t 'MN_EKF')
    $line = 'сообщений ' + $msgs + ', кадров с метками ' + $wm + ', номера ' + $ids + ', поз ' + $np
    if ($maxDev -ge 0) { $line += ', отклонение позы от рулетки до ' + (F3 $maxDev) + ' м' }
    $line += ', RESEEDED ' + $nRs + ', журнал vpe_fix ' + $(if ($null -ne $logTo) { 'прочитан' } else { 'НЕ прочитан' })
    if ($ekf.Count -eq 1) { $line += ', EKF ' + $ekf[0] }
    $line += $mapNote
    $line += ' | ФЛАГИ: ' + $(if ($flags.Count -gt 0) { $flags -join ',' } else { '-' })
    if ($stop.Count -gt 0) { $line += ' — ' + ($stop -join '; ') }
    return @{ Line = $line; Stop = @($stop); Flags = @($flags); LogTo = $logTo; Msgs = $msgs }
}
function Sum-Lines { if (Test-Path -LiteralPath $script:sumFile) { return @([IO.File]::ReadAllLines($script:sumFile)) } else { return @() } }
function Point-Lines { return @(Sum-Lines | Where-Object { $_ -match '^ТОЧКА \d+ см: ' }) }
# Фазы после pre: сводка этой метки уже есть, проверка в ней прошла, итога ещё нет
function Need-Open {
    $l = @(Sum-Lines)
    if ($l.Count -eq 0 -or -not ($l | Where-Object { $_ -match '^ПРОВЕРКА .* msgs=[1-9]\d* ' })) { BB-Stop ('нет сводки ' + $script:sumFile + ' с удачной проверкой (фаза pre). Запускайте 25_metki_nomera.cmd. К дрону не обращались.') 4 }
    if ($l | Where-Object { $_ -match '^# VERDICT ' }) { BB-Stop ('в сводке ' + $script:sumFile + ' уже есть итог, ничего не дописываю. К дрону не обращались.') 4 }
}
# С какого байта читать журнал стека в следующей фазе: конец окна прошлой фазы (строка ЖУРНАЛ_ДО=), иначе start
function Log-From { $j = @(Sum-Lines | Where-Object { $_ -match '^ЖУРНАЛ_ДО=(\d+|start)$' }); if ($j.Count -gt 0) { return ($j[-1] -replace '^ЖУРНАЛ_ДО=', '') } else { return 'start' } }

if ($Phase -eq 'pre') {
    $tags = @('pre') + @($points | ForEach-Object { 'p{0:D2}cm' -f $_ })
    foreach ($n in @(($base + '.txt')) + @($tags | ForEach-Object { ($base + '_' + $_ + '.txt'); ($base + '_' + $_ + '.err.txt'); ($base + '_' + $_ + '.FAILED.txt') })) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
    $ssh = BB-FindSsh
    BB-TestDrone $ssh
    Add-Sum ('# МЕНЯЕТ ДРОН временно: шаг 25 «ложные номера меток и поза» (run_r8_metki.ps1, набор r8), начато ' + (R6-Now) + ' по часам ПК.')
    Add-Sum '# Дрон неподвижно над меткой 0, без взвода; детектор будится сигналом /aruco_detect/wake 1 Гц только во время окон записи; поза по меткам идёт через vpe_fix в EKF2. Перед взлётом выключить и включить дрон или сверить позицию EKF с рулеткой.'
    Write-Host 'Проверка: связь с полётным контроллером, дрон не взведён; потом детектор будится и около 6 с пишутся номера и поза. Дрон не трогать ...'
    $pre = R6-Remote $ssh $sh @('pre', '6', 'pre', 'start') $outDir ($base + '_pre') 90
    Check-Reply $pre 'проверка'
    $st = @(R6-Lines $pre.Text 'MN_STATE'); $det = @(R6-Lines $pre.Text 'MN_DETECTOR')
    if ($det.Count -ne 1) { Finish 4 'ERROR' 'проверка: нет строки MN_DETECTOR в ответе Pi.' }
    $m0n = Num $det[0] 'msgs'
    if ($m0n -lt 0) { Finish 4 'ERROR' ('проверка: не прочитано число сообщений: ' + $det[0]) }
    $ev = Eval-Reply $pre 0 'проверка'
    Add-Sum ('ПРОВЕРКА ' + ($st -join ' ') + ' | ' + $det[0] + ' | ' + $ev.Line)
    if ($null -ne $ev.LogTo) { Add-Sum ('ЖУРНАЛ_ДО=' + $ev.LogTo) }
    if ($ev.Stop.Count -gt 0) { Finish 5 'STOP' ('СТОП (проверка, дрон над меткой 0): ' + ($ev.Stop -join '; ') + '. Дрон не трогать и не взлетать, скажите Claude.') }
    if ($m0n -eq 0) {
        $cam = [regex]::Match($det[0], 'camera_subscription=(\S+)').Groups[1].Value
        Finish 6 'NOT_CHECKED' ('НЕ ПРОВЕРЕНО: детектор меток за 6 с не выдал ни одного сообщения, хотя Pi слал сигнал wake (его подписка на кадры камеры: ' + $cam + '). На rc3 детектор (aruco_detect.py 7eb7bdf3) сигнал wake не слушает и без взвода спит; на r2j слушает. Номера не проверены, двигать дрон не нужно. Скажите Claude.')
    }
    Write-Host ('Детектор выдаёт сообщения (' + $m0n + ' за 6 с). Дальше 4 точки.')
    exit 0
}
if ($Phase -eq 'rec') {
    Need-Open
    $tag = 'p{0:D2}cm' -f $Cm
    $prev = @($points | Where-Object { $_ -lt $Cm })
    $have = @(Point-Lines | ForEach-Object { [int]($_ -replace '^ТОЧКА (\d+) см: .*$', '$1') })
    if ((($have | ForEach-Object { [string]$_ }) -join ',') -cne (($prev | ForEach-Object { [string]$_ }) -join ',')) { BB-Stop ('точки пишутся по порядку 0, 5, 10, 15; записаны: ' + ($have -join ', ') + '. К дрону не обращались.') 4 }
    foreach ($n in @(($base + '_' + $tag + '.txt'), ($base + '_' + $tag + '.err.txt'), ($base + '_' + $tag + '.FAILED.txt'))) { $null = BB-NewOutFile $outDir $n }
    $from = Log-From
    $ssh = BB-FindSsh
    BB-TestDrone $ssh
    Write-Host ('Запись в точке ' + $Cm + ' см: 2 с разгона и 10 с записи, детектор будится. Дрон не трогать ...')
    $r = R6-Remote $ssh $sh @('rec', '10', $tag, $from) $outDir ($base + '_' + $tag) 90
    Check-Reply $r ('точка ' + $Cm + ' см')
    $ev = Eval-Reply $r $Cm ('точка ' + $Cm + ' см')
    $txt = 'ТОЧКА ' + $Cm + ' см: ' + $ev.Line
    Add-Sum $txt
    if ($null -ne $ev.LogTo) { Add-Sum ('ЖУРНАЛ_ДО=' + $ev.LogTo) } else { Add-Sum 'ЖУРНАЛ_ДО=start' }
    if ($ev.Stop.Count -gt 0) {
        Write-Host ('  ' + $txt + '  ') -ForegroundColor White -BackgroundColor DarkRed
        Finish 5 'STOP' ('СТОП в точке ' + $Cm + ' см: ' + ($ev.Stop -join '; ') + '. Запись прекращена. Дрон не трогать и не взлетать, скажите Claude.')
    }
    Write-Host $txt
    exit 0
}
if ($Phase -eq 'stop') {
    Need-Open
    Add-Sum ('ОСТАНОВЛЕНО владельцем перед точкой ' + $Cm + ' см')
    Finish 6 'NOT_CHECKED' ('НЕ ПРОВЕРЕНО: запись остановлена перед точкой ' + $Cm + ' см (эта и следующие точки не записаны). Скажите Claude.')
}
# final
Need-Open
$pl = @(Point-Lines)
$got = @($pl | ForEach-Object { [int]($_ -replace '^ТОЧКА (\d+) см: .*$', '$1') })
if ((($got | ForEach-Object { [string]$_ }) -join ',') -cne '0,5,10,15') { Finish 4 'ERROR' ('для итога нужны 4 точки 0, 5, 10, 15; в сводке: ' + ($got -join ', ') + '.') }
if ($pl | Where-Object { $_ -match ' — .*СТОП' }) { Finish 5 'STOP' ('СТОП: в сводке есть точка со СТОП. Дрон не трогать и не взлетать, скажите Claude.') }
$why = @{ 'NO_DATA' = 'детектор не выдал ни одного сообщения'; 'NO_ZERO' = 'метка 0 не прочитана ни разу'; 'NO_POSE' = 'ни одной позы по меткам'; 'NO_MAP' = 'карта меток не прочитана'; 'NO_LOG' = 'журнал vpe_fix не прочитан' }
$miss = New-Object Collections.Generic.List[string]
foreach ($f in 'NO_DATA', 'NO_ZERO', 'NO_POSE', 'NO_MAP', 'NO_LOG') {
    $pts = @($pl | Where-Object { ($_ -replace '^.* \| ФЛАГИ: ([^ ]*).*$', '$1') -split ',' -contains $f } | ForEach-Object { $_ -replace '^ТОЧКА (\d+ см): .*$', '$1' })
    if ($pts.Count -gt 0) { $miss.Add($why[$f] + ' в точках: ' + ($pts -join ', ')) }
}
if ($miss.Count -gt 0) { Finish 6 'NOT_CHECKED' ('НЕ ПРОВЕРЕНО: ' + ($miss -join '; ') + '. Ложных номеров и поз дальше 0,15 м не найдено, но эти точки не проверены. Скажите Claude.') }
Finish 0 'OK' ('Во всех 4 точках: только номер 0, поза по меткам не дальше 0,15 м от рулетки, RESEEDED на чужую позу нет (по 10 с в каждой точке). Скажите Claude.')
