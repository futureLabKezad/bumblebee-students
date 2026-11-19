# run_battery.ps1 (Claude, 10.11.2026, набор r2) - ТОЛЬКО ЧТЕНИЕ. Батарея 20EC через MAVROS (pi\battery_check.sh): напряжение, текстовые сообщения PX4, настройки батареи.
# Запускается из 08_batareya.cmd. Моторы не взводит, в PX4 ничего не пишет, детектор не будит.
# Коды выхода: 0 прочитано; 4 ошибка.
param(
    [string]$Label = 'bat',
    [int]$DurationSec = 30
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$null = BB-SafeLabel $Label 'метка'
if ($DurationSec -lt 10 -or $DurationSec -gt 300) { BB-Stop 'длительность должна быть от 10 до 300 секунд' 4 }
$outDir = BB-OutDir $here
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$base = 'bench_battery_' + $Label + '_' + $stamp
$rawFile = BB-NewOutFile $outDir ($base + '.raw.txt')
$sumFile = BB-NewOutFile $outDir ($base + '.summary.txt')
$errFile = BB-NewOutFile $outDir ($base + '.err.txt')
$sh = Join-Path $here 'pi\battery_check.sh'
if (-not (Test-Path -LiteralPath $sh)) { BB-Stop ('нет файла ' + $sh) 4 }
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $sh @([string]$DurationSec)
Write-Host ('Читаю батарею ' + $DurationSec + ' с (напряжение, сообщения PX4, настройки BAT*). Моторы не взводятся, ничего не пишется. Ждите ...')
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $rawFile $errFile ($DurationSec + 90)
$raw = ''; if (Test-Path -LiteralPath $rawFile) { $raw = [IO.File]::ReadAllText($rawFile) }
$err = ''; if (Test-Path -LiteralPath $errFile) { $err = [IO.File]::ReadAllText($errFile) }
if ($rc -ne 0 -or $raw -notmatch 'BB_BATTERY_DONE rc=0') {
    $failed = $rawFile -replace '\.raw\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $rawFile) { Move-Item -LiteralPath $rawFile -Destination $failed }
    BB-Stop ('чтение батареи не закончилось (код ssh ' + $rc + '). Сырой вывод: ' + $failed + ' ' + $err) 4
}
$sum = New-Object Collections.Generic.List[string]
$sum.Add('Батарея 20EC через MAVROS. Только факты чтения, оценок нет. Файл сырых данных: ' + (Split-Path $rawFile -Leaf))
$sum.Add('Дата ПК: ' + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '   метка: ' + $Label)
foreach ($pre in 'META', 'BAT', 'STATUSTEXT', 'PARAM', 'SUMMARY') {
    foreach ($l in (BB-PickLines $raw $pre)) { $sum.Add($l) }
}
[IO.File]::WriteAllText($sumFile, (($sum -join "`r`n") + "`r`n"), (BB-Utf8NoBom))
Write-Host ''
foreach ($l in $sum) { Write-Host $l }
Write-Host ''
Write-Host ('Сводка: ' + $sumFile)
Write-Host ('Сырые данные: ' + $rawFile)
exit 0
