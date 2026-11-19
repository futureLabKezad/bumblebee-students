# run_measure.ps1 (Claude, 10.11.2026) - замер зрения на Pi (pi\vision_measure.sh). Запускается из 02a/02b/03/04 .cmd.
# Моторы не взводит, параметры и команды в PX4 не пишет. Единственное действие на Pi: при -Wake 1 будит детектор меток (топик /aruco_detect/wake).
# Коды выхода: 0 замер закончен; 3 замер НЕ начат по безопасности (дрон взведён в режиме measure или нет связи с FCU); 4 ошибка;
# 5 (r17a, только шаг 03) замер закончен и записан, но строк детектора «joint rms median» за замер нет = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА.
param(
    [string]$Label = 'zamer',
    [int]$DurationSec = 300,
    [ValidateSet('measure', 'vibration')][string]$Mode = 'measure',
    [ValidateSet(0, 1)][int]$Wake = 1,
    [string]$Place = '',
    [string]$CameraHeightCm = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$null = BB-SafeLabel $Label 'метка'
if ($DurationSec -lt 10 -or $DurationSec -gt 1800) { BB-Stop 'длительность должна быть от 10 до 1800 секунд' 4 }
if ($Place -ne '') { $null = BB-SafeLabel $Place 'место' }
if ($CameraHeightCm -ne '' -and ($CameraHeightCm -notmatch '^\d{1,3}([.,]\d)?$' -or [double]($CameraHeightCm -replace ',', '.') -gt 300)) { BB-Stop ('высота камеры над полом, см: число до 300, а не «' + $CameraHeightCm + '»') 4 }
$outDir = BB-OutDir $here
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$base = 'bench_' + $Label + '_' + $stamp
$rawFile = BB-NewOutFile $outDir ($base + '.raw.txt')
$sumFile = BB-NewOutFile $outDir ($base + '.summary.txt')
$errFile = BB-NewOutFile $outDir ($base + '.err.txt')
$sh = Join-Path $here 'pi\vision_measure.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $sh @([string]$DurationSec, $Label, $Mode, [string]$Wake)
Write-Host ('Замер ' + $DurationSec + ' с, метка ' + $Label + ', режим ' + $Mode + ', будить детектор: ' + $(if ($Wake -eq 1) { 'да' } else { 'нет' }) + '. Моторы не взводятся. Ждите ...')
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $rawFile $errFile ($DurationSec + 120)
$raw = ''; if (Test-Path -LiteralPath $rawFile) { $raw = [IO.File]::ReadAllText($rawFile) }
$err = ''; if (Test-Path -LiteralPath $errFile) { $err = [IO.File]::ReadAllText($errFile) }
$refused = BB-PickLines $raw 'REFUSED'
if ($refused.Count -gt 0) {
    Write-Host ''
    Write-Host '  ЗАМЕР НЕ НАЧАТ (по безопасности, дрон ничем не будился):  ' -ForegroundColor Black -BackgroundColor Yellow
    foreach ($l in $refused) { Write-Host $l }
    [IO.File]::WriteAllText($sumFile, ("ЗАМЕР НЕ НАЧАТ`r`n" + ($refused -join "`r`n") + "`r`n"), (BB-Utf8NoBom))
    exit 3
}
if ($rc -ne 0 -or $raw -notmatch 'BB_BENCH_DONE rc=0') {
    $failed = $rawFile -replace '\.raw\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $rawFile) { Move-Item -LiteralPath $rawFile -Destination $failed }
    BB-Stop ('замер не закончился (код ssh ' + $rc + '). Сырой вывод: ' + $failed + ' ' + $err) 4
}
$sum = New-Object Collections.Generic.List[string]
$sum.Add('Замер зрения на Pi 20EC. Только факты замера, оценок нет. Файл сырых данных: ' + (Split-Path $rawFile -Leaf))
$sum.Add('Дата ПК: ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '   метка: ' + $Label + '   режим: ' + $Mode)
if ($Place -ne '') { $sum.Add('ОПЕРАТОР (введено вручную): место = ' + $Place) }
if ($CameraHeightCm -ne '') { $sum.Add('ОПЕРАТОР (введено вручную): высота камеры над полом = ' + $CameraHeightCm + ' см') }
foreach ($l in (BB-PickLines $raw 'META')) { $sum.Add($l) }
foreach ($l in (BB-PickLines $raw 'SUMMARY')) { $sum.Add($l) }
# r17 (19.11, решение владельца, поправка по проверке review_v11_20261119): только для шага 03 (метки hand_*) - частота детектора меток из уже посчитанного hz_all
# (строка SUMMARY markers_used скрипта Pi; markers_msgs и vision_pose частотой детектора НЕ считаются); порога нет; ничего дополнительно не будится
# r17a (19.11, MAJOR проверки wf_2a438f6b): строки детектора «joint rms median» - не из journald (стек пишет в /tmp/bumblebee.log), а из строк JR скрипта Pi
# (новые байты /tmp/bumblebee.log с начала замера, только чтение). Детектор пишет эту строку, только если за последние 2 с было >=10 решений по >=2 меткам
# карты сразу, и не чаще раза в 5 с. «MAP != FIELD?» выделяется красным. Обрезка вывода помечается. Нет строк - код 5 (не «Готово»).
$is03 = ($Label -cmatch '^hand_(center|camera_over|back8)$')
$noJoint = $false
$jrMap = @()
if ($is03) {
    $hzLine = @(BB-PickLines $raw 'SUMMARY' | Where-Object { $_ -cmatch '^SUMMARY markers_used msgs=\d+ .* hz_all=([0-9]+(\.[0-9]+)?)\s*$' }) | Select-Object -First 1
    $detHz = $null; if ($hzLine -and $hzLine -cmatch ' hz_all=([0-9]+(\.[0-9]+)?)\s*$') { $detHz = [double]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture) }
    if ($null -ne $detHz) { $sum.Add('ЧАСТОТА ДЕТЕКТОРА: ' + $detHz.ToString('0.0#', [Globalization.CultureInfo]::GetCultureInfo('ru-RU')) + ' кадр/с (по /aruco_detect/markers_used)') }
    else { $sum.Add('ЧАСТОТА ДЕТЕКТОРА: нет данных - сообщений /aruco_detect/markers_used за замер не было (детектор спал или не запущен)') }
    $sum.Add('В1.1 проверялся в Gazebo при 6,1 кадр/с; любое число заметно ≠ 6,1 — сказать владельцу до полёта')
    $jrAll = BB-PickLines $raw 'JR'
    $jr = @($jrAll | Where-Object { $_ -cmatch 'joint (PnP )?rms median' })
    $jrMap = @($jrAll | Where-Object { $_ -cmatch 'MAP != FIELD\?' })
    $jrNoLog = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^JR_NOLOG\s*$' })
    $jrNote = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^JR_NOTE ' })
    $jrCnt = @(BB-PickLines $raw 'JR_COUNT' | Where-Object { $_ -cmatch '^JR_COUNT \d+\s*$' })
    $jrCut = @(BB-PickLines $raw 'JR_CUT' | Where-Object { $_ -cmatch '^JR_CUT shown=\d+ total=\d+\s*$' })
    $sum.Add('JOINT RMS (строки детектора «joint rms median» из /tmp/bumblebee.log за замер): ' + $jr.Count)
    if ($jrCut.Count -gt 0 -and $jrCut[0] -cmatch '^JR_CUT shown=(\d+) total=(\d+)') { $sum.Add('  ВЫВОД ОБРЕЗАН: на Pi показаны первые ' + $Matches[1] + ' из ' + $Matches[2] + ' строк детектора про joint rms (остальные - только в /tmp/bumblebee.log на Pi)') }
    if ($jrNote.Count -gt 0) { $sum.Add('  журнал стека /tmp/bumblebee.log стал короче, чем до замера (перезапуск стека?): прочитан весь (JR_NOTE)') }
    foreach ($l in $jrAll) { if ($l -cmatch 'MAP != FIELD\?') { $sum.Add('  >>> MAP != FIELD? >>> ' + $l) } else { $sum.Add('  ' + $l) } }
    if ($jrMap.Count -gt 0) { $sum.Add('MAP != FIELD? - детектор считает, что карта меток не совпадает с полем; строк: ' + $jrMap.Count + '. Сказать Claude до полёта.') }
    if ($jrNoLog.Count -gt 0) { $noJoint = $true; $sum.Add('  журнал стека /tmp/bumblebee.log на Pi не найден или его размер до замера не прочитан (JR_NOLOG)') }
    elseif ($jrCnt.Count -eq 0) { $noJoint = $true; $sum.Add('  скрипт Pi не прислал строку JR_COUNT - журнал /tmp/bumblebee.log не прочитан') }
    if ($jr.Count -eq 0) { $noJoint = $true }
    if ($noJoint) { $sum.Add('НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА') }
}
$ev = BB-PickLines $raw 'EVENT'
$sum.Add('События во время замера: ' + $ev.Count)
foreach ($l in ($ev | Select-Object -First 30)) { $sum.Add('  ' + $l) }
$smp = BB-PickLines $raw 'SAMPLE'
$sum.Add('Замеров нагрузки каждые 5 с: ' + $smp.Count + ' (все в сыром файле)')
foreach ($l in ($smp | Select-Object -First 3)) { $sum.Add('  ' + $l) }
$jl = @($raw -split "`r?`n" | Where-Object { $_.StartsWith('J ') })
$sum.Add('Строки журнала bumblebee за время замера: ' + $jl.Count)
# r17a: обрезка помечается - на Pi (head -80, строка J_CUT) и в сводке (первые 40)
$jCut = @(BB-PickLines $raw 'J_CUT' | Where-Object { $_ -cmatch '^J_CUT shown=\d+ total=\d+\s*$' })
if ($jCut.Count -gt 0 -and $jCut[0] -cmatch '^J_CUT shown=(\d+) total=(\d+)') { $sum.Add('  ВЫВОД ОБРЕЗАН: на Pi показаны первые ' + $Matches[1] + ' из ' + $Matches[2] + ' строк журнала') }
if ($jl.Count -gt 40) { $sum.Add('  ВЫВОД ОБРЕЗАН: в сводке первые 40 из ' + $jl.Count + ', все - в сыром файле') }
foreach ($l in ($jl | Select-Object -First 40)) { $sum.Add('  ' + $l) }
[IO.File]::WriteAllText($sumFile, (($sum -join "`r`n") + "`r`n"), (BB-Utf8NoBom))
Write-Host ''
foreach ($l in $sum) { if ($l.StartsWith('  >>> MAP != FIELD?') -or $l.StartsWith('MAP != FIELD?')) { Write-Host $l -ForegroundColor White -BackgroundColor Red } else { Write-Host $l } }
Write-Host ''
if ($is03) { Write-Host ('  ' + (@($sum | Where-Object { $_.StartsWith('ЧАСТОТА ДЕТЕКТОРА: ') })[0]) + '. В1.1 проверялся в Gazebo при 6,1 кадр/с; любое число заметно ≠ 6,1 — сказать владельцу до полёта.  ') -ForegroundColor Black -BackgroundColor Yellow; Write-Host '' }
if ($jrMap.Count -gt 0) { Write-Host ('  MAP != FIELD? - детектор ' + $jrMap.Count + ' раз(а) написал, что карта меток не совпадает с полем. Сказать Claude до полёта.  ') -ForegroundColor White -BackgroundColor Red; Write-Host '' }
Write-Host ('Сводка: ' + $sumFile)
Write-Host ('Сырые данные: ' + $rawFile)
if ($noJoint) {
    Write-Host ''
    Write-Host '  НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА (в /tmp/bumblebee.log за замер нет строк детектора «joint rms median»). Журнал записан.  ' -ForegroundColor White -BackgroundColor Red
    exit 5
}
exit 0
