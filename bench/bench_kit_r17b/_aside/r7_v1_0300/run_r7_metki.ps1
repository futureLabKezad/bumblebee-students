# run_r7_metki.ps1 (Claude, 13.11.2026, набор r7) - ТОЛЬКО ЧТЕНИЕ. Шаг 25 (25_metki_nomera.cmd): проверка ложных номеров меток, pi\r7_marker_ids.sh.
# Дрон неподвижно над меткой 0, сдвиги 0 / 5 / 10 / 15 см; в каждой точке 10 с записи /aruco_detect/markers (номер и 4 угла). Без взвода; детектор не будится;
# на Pi только подписка rclpy, ros2 CLI не вызывается (демон ros2 не запускается). Сначала короткая проверка: выдаёт ли детектор сообщения. По коду образа
# (aruco_detect.py, gate_by_flight_state) без взвода он спит; тогда ничего не записывается, двигать дрон не нужно, итог «НЕ ПРОВЕРЕНО».
# Вызывает только 25_metki_nomera.cmd, по фазам (вопросы «наберите N» задаёт .cmd): -Phase pre (проверка), rec -Cm N (запись точки), stop -Cm N (остановка), final (итог).
# Пишет на ПК out\metki_nomera_<метка>.txt (сводка; последняя строка «# VERDICT ...» - только в конце) и сырые ответы Pi out\metki_nomera_<метка>_<точка>.txt; ничего не перезаписывает.
# Коды выхода: pre - 0 детектор выдаёт сообщения, можно писать точки; rec - 0 точка записана. Итоговые: 0 все 4 точки, номеров кроме 0 нет; 5 ЛОЖНЫЙ НОМЕР
#   (номер не 0 хотя бы в одной точке); 6 НЕ ПРОВЕРЕНО (детектор молчит, в точке нет сообщений, запись остановлена); 3 НЕ НАЧАТО (дрон взведён, нет связи с FCU
#   или /mavros/state); 4 ошибка (ПК, связь, чужой дрон, файл уже есть, порядок фаз).
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
$sh = Join-Path $here 'pi\r7_marker_ids.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
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
# Ответ Pi: конец, отказ по безопасности, ошибка.
function Check-Reply($r, [string]$what) {
    if ($r.Text -notmatch 'BB_R7MN_DONE') {
        if (Test-Path -LiteralPath $r.Out) { Move-Item -LiteralPath $r.Out -Destination ($r.Out -replace '\.txt$', '.FAILED.txt') }
        Finish 4 'ERROR' ($what + ': ответ Pi без конца (код ssh ' + $r.Code + '). ' + $r.Err.Trim())
    }
    $ref = @(R6-Lines $r.Text 'MN_REFUSED')
    if ($ref.Count -gt 0) { Finish 3 'NOT_STARTED' ('НЕ НАЧАТО (' + $what + '): ' + ($ref -join '; ') + '. Детектор не будился, на дроне ничего не менялось.') }
    $er = @(R6-Lines $r.Text 'MN_ERROR')
    if ($er.Count -gt 0 -or $r.Code -ne 0) { Finish 4 'ERROR' ($what + ': ошибка на Pi (код ' + $r.Code + '): ' + ($er -join '; ')) }
}
function Num([string]$line, [string]$key) {
    $m = [regex]::Match($line, '(?:^|\s)' + $key + '=(\d+)(?:\s|$)')
    if (-not $m.Success) { return -1 }
    return [int]$m.Groups[1].Value
}
function Sum-Lines { if (Test-Path -LiteralPath $script:sumFile) { return @([IO.File]::ReadAllLines($script:sumFile)) } else { return @() } }
function Point-Lines { return @(Sum-Lines | Where-Object { $_ -match '^ТОЧКА \d+ см: ' }) }
function False-Points { return @(Point-Lines | Where-Object { $_ -match ' — ЛОЖНЫЙ НОМЕР: ' } | ForEach-Object { ($_ -replace '^ТОЧКА (\d+ см): .* — ЛОЖНЫЙ НОМЕР: (.*)$', '$1: $2') }) }
# Фазы после pre: сводка этой метки уже есть, проверка в ней прошла, итога ещё нет
function Need-Open {
    $l = @(Sum-Lines)
    if ($l.Count -eq 0 -or -not ($l | Where-Object { $_ -match '^ПРОВЕРКА .* msgs=[1-9]\d* ' })) { BB-Stop ('нет сводки ' + $script:sumFile + ' с удачной проверкой (фаза pre). Запускайте 25_metki_nomera.cmd. К дрону не обращались.') 4 }
    if ($l | Where-Object { $_ -match '^# VERDICT ' }) { BB-Stop ('в сводке ' + $script:sumFile + ' уже есть итог, ничего не дописываю. К дрону не обращались.') 4 }
}

if ($Phase -eq 'pre') {
    $tags = @('pre') + @($points | ForEach-Object { 'p{0:D2}cm' -f $_ })
    foreach ($n in @(($base + '.txt')) + @($tags | ForEach-Object { ($base + '_' + $_ + '.txt'); ($base + '_' + $_ + '.err.txt'); ($base + '_' + $_ + '.FAILED.txt') })) { $null = BB-NewOutFile $outDir $n }   # не перезаписывать: проверка ДО обращения к дрону
    $ssh = BB-FindSsh
    BB-TestDrone $ssh
    Add-Sum ('# ТОЛЬКО ЧТЕНИЕ: шаг 25 «ложные номера меток» (run_r7_metki.ps1, набор r7), начато ' + (R6-Now) + ' по часам ПК.')
    Add-Sum '# Дрон неподвижно над меткой 0, без взвода; детектор не будился; на Pi только подписка rclpy (/mavros/state, /aruco_detect/markers), ros2 CLI не вызывался.'
    Write-Host 'Проверка: связь с полётным контроллером, дрон не взведён, выдаёт ли детектор номера меток (около 20 с, только чтение) ...'
    $pre = R6-Remote $ssh $sh @('pre', '4', 'pre') $outDir ($base + '_pre') 90
    Check-Reply $pre 'проверка'
    $st = @(R6-Lines $pre.Text 'MN_STATE'); $det = @(R6-Lines $pre.Text 'MN_DETECTOR')
    if ($det.Count -ne 1) { Finish 4 'ERROR' 'проверка: нет строки MN_DETECTOR в ответе Pi.' }
    $m0 = Num $det[0] 'msgs'
    if ($m0 -lt 0) { Finish 4 'ERROR' ('проверка: не прочитано число сообщений: ' + $det[0]) }
    Add-Sum ('ПРОВЕРКА ' + ($st -join ' ') + ' | ' + $det[0])
    if ($m0 -eq 0) {
        $cam = [regex]::Match($det[0], 'camera_subscription=(\S+)').Groups[1].Value
        Finish 6 'NOT_CHECKED' ('НЕ ПРОВЕРЕНО: детектор меток за 4 с не выдал ни одного сообщения (его подписка на кадры камеры: ' + $cam + '). По коду образа без взвода детектор спит и кадры не берёт (aruco_detect.py, gate_by_flight_state). Этот шаг только читает и будить его не может. Номера не проверены, двигать дрон не нужно. Скажите Claude.')
    }
    Write-Host ('Детектор выдаёт сообщения (' + $m0 + ' за 4 с). Дальше 4 точки.')
    exit 0
}
if ($Phase -eq 'rec') {
    Need-Open
    $tag = 'p{0:D2}cm' -f $Cm
    $prev = @($points | Where-Object { $_ -lt $Cm })
    $have = @(Point-Lines | ForEach-Object { [int]($_ -replace '^ТОЧКА (\d+) см: .*$', '$1') })
    if ((($have | ForEach-Object { [string]$_ }) -join ',') -cne (($prev | ForEach-Object { [string]$_ }) -join ',')) { BB-Stop ('точки пишутся по порядку 0, 5, 10, 15; записаны: ' + ($have -join ', ') + '. К дрону не обращались.') 4 }
    foreach ($n in @(($base + '_' + $tag + '.txt'), ($base + '_' + $tag + '.err.txt'), ($base + '_' + $tag + '.FAILED.txt'))) { $null = BB-NewOutFile $outDir $n }
    $ssh = BB-FindSsh
    BB-TestDrone $ssh
    Write-Host ('Запись 10 с в точке ' + $Cm + ' см (только чтение) ...')
    $r = R6-Remote $ssh $sh @('rec', '10', $tag) $outDir ($base + '_' + $tag) 90
    Check-Reply $r ('точка ' + $Cm + ' см')
    $end = @(R6-Lines $r.Text 'MN_END')
    if ($end.Count -ne 1) { Finish 4 'ERROR' ('точка ' + $Cm + ' см: нет строки MN_END в ответе Pi.') }
    $msgs = Num $end[0] 'msgs'; $wm = Num $end[0] 'with_markers'
    $ids = [regex]::Match($end[0], '(?:^|\s)ids=(\S+)').Groups[1].Value
    if ($msgs -lt 0 -or $wm -lt 0 -or $ids -eq '') { Finish 4 'ERROR' ('точка ' + $Cm + ' см: строка MN_END не разобрана: ' + $end[0]) }
    $nMsg = @(R6-Lines $r.Text 'MN_MSG').Count
    if ($nMsg -ne $msgs) { Finish 4 'ERROR' ('точка ' + $Cm + ' см: строк MN_MSG ' + $nMsg + ', а в MN_END msgs=' + $msgs) }
    $bad = @(); $seen0 = $false
    if ($ids -ne 'none') {
        foreach ($kv in ($ids -split ',')) {
            if ($kv -notmatch '^(-?\d+):(\d+)$') { Finish 4 'ERROR' ('точка ' + $Cm + ' см: номера не разобраны: ' + $ids) }
            if ([int]$Matches[1] -eq 0) { $seen0 = $true } else { $bad += ('номер ' + $Matches[1] + ' — ' + $Matches[2] + ' раз') }
        }
    }
    $txt = 'ТОЧКА ' + $Cm + ' см: сообщений ' + $msgs + ', кадров с метками ' + $wm + ', номера ' + $ids
    if ($bad.Count -gt 0) { $txt += ' — ЛОЖНЫЙ НОМЕР: ' + ($bad -join ', ') }
    elseif ($msgs -eq 0) { $txt += ' — НЕТ ДАННЫХ (детектор молчал)' }
    elseif (-not $seen0) { $txt += ' — метка 0 не прочитана ни разу' }
    Add-Sum $txt
    if ($bad.Count -gt 0) { Write-Host ('  ' + $txt + '  ') -ForegroundColor White -BackgroundColor DarkRed } else { Write-Host $txt }
    exit 0
}
if ($Phase -eq 'stop') {
    Need-Open
    Add-Sum ('ОСТАНОВЛЕНО владельцем перед точкой ' + $Cm + ' см')
    $fp = @(False-Points)
    if ($fp.Count -gt 0) { Finish 5 'FALSE_ID' ('ЛОЖНЫЙ НОМЕР: ' + ($fp -join '; ') + '. Запись остановлена перед точкой ' + $Cm + ' см. Дрон не трогать, скажите Claude.') }
    Finish 6 'NOT_CHECKED' ('НЕ ПРОВЕРЕНО: запись остановлена перед точкой ' + $Cm + ' см (эта и следующие точки не записаны). Скажите Claude.')
}
# final
Need-Open
$pl = @(Point-Lines)
$got = @($pl | ForEach-Object { [int]($_ -replace '^ТОЧКА (\d+) см: .*$', '$1') })
if ((($got | ForEach-Object { [string]$_ }) -join ',') -cne '0,5,10,15') { Finish 4 'ERROR' ('для итога нужны 4 точки 0, 5, 10, 15; в сводке: ' + ($got -join ', ') + '.') }
$fp = @(False-Points)
if ($fp.Count -gt 0) { Finish 5 'FALSE_ID' ('ЛОЖНЫЙ НОМЕР: ' + ($fp -join '; ') + '. Дрон не трогать, скажите Claude: соседних меток в кадре быть не должно, Claude сверит номер с картой.') }
$empty = @($pl | Where-Object { $_ -match ' — НЕТ ДАННЫХ' } | ForEach-Object { $_ -replace '^ТОЧКА (\d+ см): .*$', '$1' })
if ($empty.Count -gt 0) { Finish 6 'NOT_CHECKED' ('НЕ ПРОВЕРЕНО: в точках ' + ($empty -join ', ') + ' детектор не выдал ни одного сообщения. Скажите Claude.') }
$no0 = @($pl | Where-Object { $_ -match ' — метка 0 не прочитана ни разу' } | ForEach-Object { $_ -replace '^ТОЧКА (\d+ см): .*$', '$1' })
$note = ''; if ($no0.Count -gt 0) { $note = ' Метка 0 не прочитана ни разу в точках: ' + ($no0 -join ', ') + ' (это не ложный номер).' }
Finish 0 'ONLY_ID0' ('Во всех 4 точках номеров кроме 0 нет (по 10 с в каждой).' + $note + ' Скажите Claude.')