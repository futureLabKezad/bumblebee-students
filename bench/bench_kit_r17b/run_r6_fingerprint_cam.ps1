# run_r6_fingerprint_cam.ps1 (Claude, 12.11.2026, набор r6) - ТОЛЬКО ЧТЕНИЕ. Шаг 15c: отпечатки оверлея bumblebee (~/bench_ws/r2j) для ВАРИАНТА «r2j + камера полных строк».
# Тот же скрипт Pi, что у 15 (pi\overlay_fingerprint.sh, не менялся), цель bumblebee; списки варианта: python-узлы INSTALL_SHA256_r2jcam.txt, launch и fcu_detect RUNTIME_PY_r2jcam.tsv;
# C++ исходники копии оверлея - список r2j (вариант их не меняет; копию исходников в оверлее вариант тоже не трогает).
# Прежние ворота не ослаблены: 15 (r2j) проверяет как раньше. Файл: out\otpechatki_r2jcam_<время>.txt (НЕ fingerprint_bumblebee_*: 16 его не берёт; подключение
# оверлея с вариантом заново - отдельное решение чата 1). MAVROS вариант не меняет: его отпечатки - прежний 15.
# Коды выхода: 0 без замечаний; 5 замечание или нет оверлея; 4 ошибка связи или скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
. (Join-Path $here 'lib\bb_lists_r2jcam.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$cpp = BL-CppList $here; $py = BLC-PyList $here; $rt = BLC-RtList $here
$gen = BL-Generate (Join-Path $here 'pi\overlay_fingerprint.sh') @{ LIST = $py; CPP = $cpp; RT = $rt } $outDir ('otpechatki_r2jcam_' + $stamp + '.generated.sh')
$ssh = BB-FindSsh
BB-TestDrone $ssh
$o = BB-NewOutFile $outDir ('otpechatki_r2jcam_' + $stamp + '.raw.txt'); $e = BB-NewOutFile $outDir ('otpechatki_r2jcam_' + $stamp + '.err.txt')
$remote = BB-RemoteCommand $gen @('bumblebee')
Write-Host 'Отпечатки оверлея bumblebee для варианта r2j+камера (только чтение) ...'
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $o $e 180
$raw = ''; if (Test-Path -LiteralPath $o) { $raw = [IO.File]::ReadAllText($o) }
if ($rc -ne 0 -or $raw -notmatch 'BB_FP_DONE') {
    $failed = $o -replace '\.raw\.txt$', '.FAILED.txt'; if (Test-Path -LiteralPath $o) { Move-Item -LiteralPath $o -Destination $failed }
    BB-Stop ('чтение отпечатков не закончилось (код ' + $rc + '). ' + (Get-Content -LiteralPath $e -Raw -ErrorAction SilentlyContinue)) 4
}
$m = [regex]::Match($raw, 'BB_FP_RESULT files=(\d+) py_ok=(\d+) py_bad=(\d+) src_ok=(\d+) src_bad=(\d+) bin=(\d+) stale=(\d+) noinstall=(\d+)')
if (-not $m.Success) { BB-Stop 'в выводе нет итоговой строки BB_FP_RESULT' 4 }
$v = @(1..8 | ForEach-Object { [int]$m.Groups[$_].Value })
if ($v[7] -eq 1) { Write-Host '  Оверлей ~/bench_ws/r2j не собран (нет install): отпечатков нет.' -ForegroundColor White -BackgroundColor Red; exit 5 }
$mr = [regex]::Match($raw, 'BB_FP_RT ok=(\d+) diff=(\d+) missing=(\d+)')
if (-not $mr.Success) { BB-Stop 'в выводе нет строки BB_FP_RT' 4 }
$rtOk = [int]$mr.Groups[1].Value; $rtDiff = [int]$mr.Groups[2].Value; $rtMiss = [int]$mr.Groups[3].Value
foreach ($l in ($raw -split "`r?`n")) { if ($l -match '^(FP_TARGET|FP_ROOT|PY_NODE|SRC |BIN |RT_FILE|BB_FP_RT |BB_FP_RESULT )' -and $l -notmatch ' OK( [R-])?$') { Write-Host ('  ' + $l) } }
$okT = ($v[0] -gt 0 -and $v[2] -eq 0 -and $v[1] -eq $py.Count -and $v[4] -eq 0 -and $v[3] -eq $cpp.Count -and $v[5] -eq 6 -and $v[6] -eq 0 -and $rtDiff -eq 0 -and $rtMiss -eq 0 -and $rtOk -eq $rt.Count)
$fpFile = BB-NewOutFile $outDir ('otpechatki_r2jcam_' + $stamp + '.txt')
$hdr = @(('# отпечатки оверлея bumblebee на Pi для ВАРИАНТА r2j+камера, ' + (Get-Date).ToString('s') + ', ТОЛЬКО ЧТЕНИЕ (шаг 15c)'), ('# ' + (($raw -split "`r?`n" | Where-Object { $_ -match '^BB_FP_RESULT ' } | Select-Object -First 1))), ('# ' + ($raw -split "`r?`n" | Where-Object { $_ -match '^BB_FP_RT ' } | Select-Object -First 1)))
$body = @($raw -split "`r?`n" | Where-Object { $_ -match '^FP_FILE [0-9a-f]{64} ' } | ForEach-Object { $_.Substring(8, 64) + '  ' + $_.Substring(73) })
$extra = @($raw -split "`r?`n" | Where-Object { $_ -match '^(BIN |SRC |PY_NODE |FP_EXEC |RT_FILE )' } | ForEach-Object { '# ' + $_ })
$verdict = '# VERDICT ' + $(if ($okT) { 'OK' } else { 'NOT_OK' })
[IO.File]::WriteAllText($fpFile, (($hdr + $body + $extra + @($verdict)) -join "`r`n") + "`r`n", (BB-Utf8NoBom))
if ($okT) { Write-Host ('Готово: оверлей bumblebee = ВАРИАНТ r2j+камера (файлов ' + $v[0] + ', бинарников ' + $v[5] + ', не старше исходников). Отпечатки: ' + $fpFile); exit 0 }
Write-Host ('  ЗАМЕЧАНИЯ: python отличается ' + $v[2] + ' (ок ' + $v[1] + ' из ' + $py.Count + '), исходники отличаются или нет ' + $v[4] + ' (ок ' + $v[3] + ' из ' + $cpp.Count + '), бинарников ' + $v[5] + ' (ждали 6), СТАРШЕ исходников ' + $v[6] + ', launch и fcu_detect.py: совпало ' + $rtOk + ' из ' + $rt.Count + ', отличается ' + $rtDiff + ', нет ' + $rtMiss + '. Файл: ' + $fpFile) -ForegroundColor White -BackgroundColor DarkRed
exit 5
