# run_mavros_check.ps1 (Claude, 10.11.2026, набор r2) - ТОЛЬКО ЧТЕНИЕ. Какой MAVROS на Pi, из какого коммита, совпадают ли пять исходников bp02 (pi\mavros_check.sh).
# Список: image_r2j\mavros_bp02_sources.tsv (колонка sha256_bp02). Ожидаемый коммит d63a23674dd80ff4525829ca4bd716bbcc773111 (тег backport-02).
# Коды выхода: 0 коммит d63a236, все 5 исходников совпали и активен MAVROS из bench_ws (не из apt); 5 иначе (СТОП: непроверенный MAVROS на дрон не идёт); 4 ошибка связи или скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$EXPECTED = 'd63a23674dd80ff4525829ca4bd716bbcc773111'
$tsv = Join-Path $here 'image_r2j\mavros_bp02_sources.tsv'
if (-not (Test-Path -LiteralPath $tsv)) { BB-Stop ('нет списка ' + $tsv) 4 }
$entries = New-Object Collections.Generic.List[string]
foreach ($l in [IO.File]::ReadAllLines($tsv)) {
    if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
    $f = $l.Split("`t")
    if ($f.Count -lt 3 -or $f[2] -cnotmatch '^[0-9a-f]{64}$' -or $f[0] -cnotmatch '^[A-Za-z0-9_./-]{1,120}$' -or $f[0] -match '\.\.') { BB-Stop ('строка списка не path TAB sha TAB sha: ' + $l) 4 }
    $entries.Add($f[2] + '  ' + $f[0])
}
if ($entries.Count -ne 5) { BB-Stop ('в списке должно быть 5 файлов, а их ' + $entries.Count) 4 }
$tpl = Join-Path $here 'pi\mavros_check.sh'
if (-not (Test-Path -LiteralPath $tpl)) { BB-Stop ('нет файла ' + $tpl) 4 }
$text = ([IO.File]::ReadAllText($tpl)) -replace "`r`n", "`n"
if (-not $text.Contains("#@@LIST@@`n")) { BB-Stop 'в pi\mavros_check.sh нет строки #@@LIST@@' 4 }
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$gen = BB-NewOutFile $outDir ('mavros_check_' + $stamp + '.generated.sh')
[IO.File]::WriteAllText($gen, $text.Replace("#@@LIST@@`n", (($entries -join "`n") + "`n")), (BB-Utf8NoBom))
$rawFile = BB-NewOutFile $outDir ('mavros_check_' + $stamp + '.txt')
$errFile = BB-NewOutFile $outDir ('mavros_check_' + $stamp + '.err.txt')
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $gen @()
Write-Host 'Читаю версию и источник MAVROS на Pi, только чтение ...'
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $rawFile $errFile 120
$raw = ''; if (Test-Path -LiteralPath $rawFile) { $raw = [IO.File]::ReadAllText($rawFile) }
if ($rc -ne 0 -or $raw -notmatch 'BB_MAVROS_CHECK_DONE') {
    $failed = $rawFile -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $rawFile) { Move-Item -LiteralPath $rawFile -Destination $failed }
    BB-Stop ('чтение MAVROS не закончилось (код ssh ' + $rc + '). ' + (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)) 4
}
foreach ($l in ($raw -split "`r?`n")) { if ($l -match '^(MAVROS_|BB_MAVROS_CHECK )') { Write-Host $l } }
$m = [regex]::Match($raw, 'BB_MAVROS_CHECK src_ok=(\d+) src_diff=(\d+) src_missing=(\d+)')
if (-not $m.Success) { BB-Stop 'в выводе нет итоговой строки BB_MAVROS_CHECK' 4 }
$okN = [int]$m.Groups[1].Value
$commit = ''
$g = [regex]::Match($raw, '(?m)^MAVROS_GIT_HEAD ([0-9a-f]{40})\s*$'); if ($g.Success) { $commit = $g.Groups[1].Value }
else { $g2 = [regex]::Match($raw, '(?m)^MAVROS_SRC_MODE commit=([0-9a-f]{40})\s*$'); if ($g2.Success) { $commit = $g2.Groups[1].Value } }
$pfx = ''; $p = [regex]::Match($raw, '(?m)^MAVROS_ACTIVE_PREFIX (\S+)'); if ($p.Success) { $pfx = $p.Groups[1].Value }
$overlay = ($pfx -match '/bench_ws/')
$why = New-Object Collections.Generic.List[string]
if ($commit -cne $EXPECTED) { $why.Add('коммит исходников «' + $commit + '», ожидается ' + $EXPECTED + ' (тег backport-02)') }
if ($okN -ne 5) { $why.Add('исходников bp02 совпало ' + $okN + ' из 5') }
if (-not $overlay) { $why.Add('активный MAVROS «' + $pfx + '» не из bench_ws: это apt-версия без исправлений или нет MAVROS') }
Write-Host ''
if ($why.Count -eq 0) { Add-Content -LiteralPath $rawFile -Value '# VERDICT OK' -Encoding UTF8; Write-Host ('Готово: MAVROS bp02 (коммит ' + $EXPECTED + ') собран и активен, 5 исходников совпали. Файл: ' + $rawFile); exit 0 }
Add-Content -LiteralPath $rawFile -Value '# VERDICT NOT_OK' -Encoding UTF8   # S1 (чат 1, 21:50): 07 проверяет эту строку
Write-Host '  СТОП: MAVROS bp02 на Pi не подтверждён. Непроверенный MAVROS на дрон не идёт; решает чат 1.  ' -ForegroundColor White -BackgroundColor Red
foreach ($w in $why) { Write-Host (' - ' + $w) }
Write-Host ('Файл: ' + $rawFile)
exit 5
