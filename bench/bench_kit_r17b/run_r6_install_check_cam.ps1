# run_r6_install_check_cam.ps1 (Claude, 12.11.2026, набор r6) - ТОЛЬКО ЧТЕНИЕ. Шаг 09c: сверка 09 для ВАРИАНТА «r2j + камера полных строк» (image_r2j_cam).
# Тот же скрипт Pi, что у 09 (pi\install_check.sh, не менялся), но списки варианта: python-узлы image_r2j_cam\INSTALL_SHA256_r2jcam.txt (camera_fix.py dabd5076),
# launch и fcu_detect image_r2j_cam\RUNTIME_PY_r2jcam.tsv (bumblebee.launch.py 5f0954d8); C++ исходники и бинарники - список r2j (image_r2j\CPP_SOURCES_r2j.tsv).
# Прежние ворота не ослаблены: 09 (r2j) проверяет как раньше и при стоящем варианте даёт СТОП (DIFF по camera_fix.py и bumblebee.launch.py).
# Файл ответа: out\sverka_r2jcam_<время>.txt (НЕ install_check_*: 07 его не принимает; разрешить полёт с вариантом - отдельное решение чата 1, правка ворот 07 не делалась).
# Коды выхода: 0 всё совпало с вариантом; 5 расхождение (СТОП); 4 ошибка связи или скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
. (Join-Path $here 'lib\bb_lists_r2jcam.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$listInst = Join-Path $here 'image_r2j_cam\INSTALL_SHA256_r2jcam.txt'
if (-not (Test-Path -LiteralPath $listInst)) { BB-Stop ('нет списка ' + $listInst) 4 }
$py = BLC-PyList $here
$bins = New-Object Collections.Generic.List[string]
foreach ($l in [IO.File]::ReadAllLines($listInst)) {
    if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
    $f = ($l.Trim() -replace '\s+', '  ').Split([string[]]@('  '), [StringSplitOptions]::None)
    if (-not $f[1].EndsWith('.py')) { $bins.Add($f[1]) }
}
$cpp = BL-CppList $here
$rt = BLC-RtList $here
if ($py.Count -lt 1 -or $cpp.Count -lt 1 -or $bins.Count -lt 1) { BB-Stop 'список пуст (python-узлов, C++ исходников или бинарников)' 4 }
$tpl = Join-Path $here 'pi\install_check.sh'
if (-not (Test-Path -LiteralPath $tpl)) { BB-Stop ('нет файла ' + $tpl) 4 }
$text = ([IO.File]::ReadAllText($tpl)) -replace "`r`n", "`n"
foreach ($mk in '#@@LIST@@', '#@@CPP@@', '#@@BINS@@', '#@@RT@@') { if (-not $text.Contains($mk + "`n")) { BB-Stop ('в pi\install_check.sh нет строки ' + $mk) 4 } }
$text = $text.Replace("#@@LIST@@`n", (($py -join "`n") + "`n")).Replace("#@@CPP@@`n", (($cpp -join "`n") + "`n")).Replace("#@@BINS@@`n", (($bins -join "`n") + "`n")).Replace("#@@RT@@`n", (($rt -join "`n") + "`n"))
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$gen = BB-NewOutFile $outDir ('sverka_r2jcam_' + $stamp + '.generated.sh')
[IO.File]::WriteAllText($gen, $text, (BB-Utf8NoBom))
$rawFile = BB-NewOutFile $outDir ('sverka_r2jcam_' + $stamp + '.txt')
$errFile = BB-NewOutFile $outDir ('sverka_r2jcam_' + $stamp + '.err.txt')
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $gen @()
Write-Host ('Сверяю на Pi с ВАРИАНТОМ r2j+камера: python-узлов ' + $py.Count + ', C++ исходников ' + $cpp.Count + ', бинарных узлов ' + $bins.Count + ', launch и fcu_detect ' + $rt.Count + ' (только чтение) ...')
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $rawFile $errFile 120
$raw = ''; if (Test-Path -LiteralPath $rawFile) { $raw = [IO.File]::ReadAllText($rawFile) }
if ($rc -ne 0 -or $raw -notmatch 'BB_INSTALL_CHECK_DONE') {
    $failed = $rawFile -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $rawFile) { Move-Item -LiteralPath $rawFile -Destination $failed }
    BB-Stop ('сверка не закончилась (код ssh ' + $rc + '). ' + (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)) 4
}
foreach ($l in ($raw -split "`r?`n")) { if ($l -match '^(INSTALL_|CPP_SRC|RT_FILE|BB_RTPY|OTHER_COPY|BB_INSTALL_CHECK )') { Write-Host $l } }
$m = [regex]::Match($raw, 'BB_INSTALL_CHECK ok=(\d+) diff=(\d+) missing=(\d+) noprefix=(\d+) cpp_ok=(\d+) cpp_diff=(\d+) cpp_missing=(\d+) bin_ok=(\d+) bin_missing=(\d+) stale=(\d+)')
if (-not $m.Success) { BB-Stop 'в выводе нет итоговой строки BB_INSTALL_CHECK с полями C++' 4 }
$v = @(1..10 | ForEach-Object { [int]$m.Groups[$_].Value })
$mr = [regex]::Match($raw, 'BB_RTPY ok=(\d+) diff=(\d+) missing=(\d+)')
if ($v[3] -eq 0 -and -not $mr.Success) { BB-Stop 'в выводе нет итоговой строки BB_RTPY (launch и fcu_detect)' 4 }
$rtOk = 0; $rtDiff = 0; $rtMiss = 0; if ($mr.Success) { $rtOk = [int]$mr.Groups[1].Value; $rtDiff = [int]$mr.Groups[2].Value; $rtMiss = [int]$mr.Groups[3].Value }
$okN = $v[0]; $diffN = $v[1]; $missN = $v[2]; $nop = $v[3]; $cok = $v[4]; $cdiff = $v[5]; $cmiss = $v[6]; $bok = $v[7]; $bmiss = $v[8]; $stale = $v[9]
Write-Host ''
if ($nop -eq 0 -and $diffN -eq 0 -and $missN -eq 0 -and $okN -eq $py.Count -and $cdiff -eq 0 -and $cmiss -eq 0 -and $cok -eq $cpp.Count -and $bmiss -eq 0 -and $bok -eq $bins.Count -and $stale -eq 0 -and $rtDiff -eq 0 -and $rtMiss -eq 0 -and $rtOk -eq $rt.Count) {
    Add-Content -LiteralPath $rawFile -Value '# VERDICT OK' -Encoding UTF8
    Write-Host ('Готово: на Pi исполняется ровно ВАРИАНТ r2j+камера: python-узлы (' + $okN + '), C++ исходники (' + $cok + '), launch и fcu_detect (' + $rtOk + ') совпали, бинарники (' + $bok + ') не старше исходников. Файл: ' + $rawFile)
    Write-Host '  Помните: 07 (взлёт) по этой сверке НЕ разрешится; полёт с вариантом - отдельное решение чата 1.'
    exit 0
}
Add-Content -LiteralPath $rawFile -Value '# VERDICT NOT_OK' -Encoding UTF8
Write-Host '  СТОП: на Pi исполняется НЕ вариант r2j+камера (расхождение, нет файла, нет install или пакет не пересобран). Скажите Claude, ничего не запускайте.  ' -ForegroundColor White -BackgroundColor Red
Write-Host ('  python: совпало ' + $okN + ' из ' + $py.Count + ', отличается ' + $diffN + ', нет ' + $missN + '; C++ исходники: совпало ' + $cok + ' из ' + $cpp.Count + ', отличается ' + $cdiff + ', нет ' + $cmiss + '; бинарники: ' + $bok + ' из ' + $bins.Count + ', нет ' + $bmiss + ', СТАРШЕ исходников ' + $stale + '; launch и fcu_detect: совпало ' + $rtOk + ' из ' + $rt.Count + ', отличается ' + $rtDiff + ', нет ' + $rtMiss + '; нет префикса ' + $nop + '. Файл: ' + $rawFile)
exit 5
