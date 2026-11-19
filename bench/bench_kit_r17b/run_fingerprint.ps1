# run_fingerprint.ps1 (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58) - ТОЛЬКО ЧТЕНИЕ. Отпечатки собранных оверлеев на Pi (pi\overlay_fingerprint.sh): sha256 всех файлов install и проверка «бинарники не старше исходников».
# Запускается после КАЖДОЙ сборки (bumblebee: ~/bench_ws/r2j; MAVROS: ~/bench_ws/mavros). Отпечатки пишет ПК в out\fingerprint_<цель>_<время>.txt (на Pi ничего не создаётся).
# Для bumblebee ещё: python-узлы оверлея равны r2j по sha256, C++ исходники копии равны r2j, бинарники не старше изменённых исходников (флаг R). Для MAVROS: 5 исходников bp02 равны списку, бинарники не старше них.
# Коды выхода: 0 есть хотя бы один собранный оверлей и все собранные проверены без замечаний; 5 замечание (расхождение, STALE) или нет ни одного собранного оверлея; 4 ошибка связи или скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$cpp = BL-ApplyRealAlt $here (BL-CppList $here); $py = BL-PyList $here; $mv = BL-MavrosSrcList $here; $rt = BL-RtList $here   # S2 (чат 1, 21:50): launch и fcu_detect.py
$py = BL-ApplyJd2Alt $here $py   # r13 (17.11): aruco_detect.py - r2j ИЛИ детектор меток варианта jd2 (image_r2j\POSEFIX_JD2_20261117.tsv, метка POSEFIX_JD2), остальные python-узлы строго r2j
$py = BL-ApplyV11Alt $here $py   # r17 (19.11): вариант В1.1 - aruco_detect.py «r2j,jd2,v11» и vpe_fix.py «r2j,v1» (image_r2j\POSEFIX_V11_20261119.tsv, метка POSEFIX_V11), оба узла одного варианта; aruco В1 (890dafbf) - СТОП
$py = BL-ApplyR2mPyAlt $here $py; $rt = BL-ApplyR2mRtAlt $here $rt   # r14 (17.11): camera_fix.py и launch/bumblebee.launch.py - r2j ИЛИ камера r2m_cam (image_r2j\R2M_CAM_20261117.tsv, метка R2M_CAM), оба одного варианта; остальное строго r2j
$ssh = BB-FindSsh
$gens = @{
    bumblebee = BL-Generate (Join-Path $here 'pi\overlay_fingerprint.sh') @{ LIST = $py; CPP = $cpp; RT = $rt } $outDir ('fingerprint_bumblebee_' + $stamp + '.generated.sh')
    mavros    = BL-Generate (Join-Path $here 'pi\overlay_fingerprint.sh') @{ LIST = (New-Object Collections.Generic.List[string]); CPP = $mv; RT = (New-Object Collections.Generic.List[string]) } $outDir ('fingerprint_mavros_' + $stamp + '.generated.sh')
}
BB-TestDrone $ssh
$built = 0; $problems = 0
foreach ($t in 'bumblebee', 'mavros') {
    $o = BB-NewOutFile $outDir ('fingerprint_' + $t + '_' + $stamp + '.raw.txt'); $e = BB-NewOutFile $outDir ('fingerprint_' + $t + '_' + $stamp + '.err.txt')
    $remote = BB-RemoteCommand $gens[$t] @($t)
    Write-Host ('Отпечатки оверлея ' + $t + ' (только чтение) ...')
    $rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $o $e 180
    $raw = ''; if (Test-Path -LiteralPath $o) { $raw = [IO.File]::ReadAllText($o) }
    if ($rc -ne 0 -or $raw -notmatch 'BB_FP_DONE') {
        $failed = $o -replace '\.raw\.txt$', '.FAILED.txt'; if (Test-Path -LiteralPath $o) { Move-Item -LiteralPath $o -Destination $failed }
        BB-Stop ('чтение отпечатков ' + $t + ' не закончилось (код ' + $rc + '). ' + (Get-Content -LiteralPath $e -Raw -ErrorAction SilentlyContinue)) 4
    }
    $m = [regex]::Match($raw, 'BB_FP_RESULT files=(\d+) py_ok=(\d+) py_bad=(\d+) src_ok=(\d+) src_bad=(\d+) bin=(\d+) stale=(\d+) noinstall=(\d+)')
    if (-not $m.Success) { BB-Stop ('в выводе нет итоговой строки BB_FP_RESULT для ' + $t) 4 }
    $v = @(1..8 | ForEach-Object { [int]$m.Groups[$_].Value })
    if ($v[7] -eq 1) { Write-Host ('  ' + $t + ': оверлей не собран (нет install), пропускаю.'); continue }
    $mr = [regex]::Match($raw, 'BB_FP_RT ok=(\d+) diff=(\d+) missing=(\d+)')
    if (-not $mr.Success) { BB-Stop ('в выводе нет строки BB_FP_RT для ' + $t) 4 }
    $rtOk = [int]$mr.Groups[1].Value; $rtDiff = [int]$mr.Groups[2].Value; $rtMiss = [int]$mr.Groups[3].Value; $expRt = $(if ($t -eq 'bumblebee') { $rt.Count } else { 0 })
    $built++
    foreach ($l in ($raw -split "`r?`n")) { if ($l -match '^(FP_TARGET|FP_ROOT|PY_NODE|SRC |BIN |RT_FILE|BB_FP_RT |BB_FP_RESULT )' -and $l -notmatch ' OK( [R-])?$') { Write-Host ('  ' + $l) } }
    $expSrc = $(if ($t -eq 'bumblebee') { $cpp.Count } else { $mv.Count }); $expPy = $(if ($t -eq 'bumblebee') { $py.Count } else { 0 })
    $expBin = $(if ($t -eq 'bumblebee') { 6 } else { 3 })   # правка по проверке 10.11 (S3): бинарники по overlay_fingerprint.sh (bumblebee: simple_offboard, camera_markers, optical_flow_node, rc, shell, vpe_publisher; MAVROS: 3), неполная сборка не даёт OK
    $r2mN = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^PY_NODE camera_fix\.py OK R2M_CAM$' -or $_ -cmatch '^RT_FILE LAUNCH launch/bumblebee\.launch\.py OK R2M_CAM$' }).Count   # r14: оба файла r2m_cam (2) или ни одного (0)
    if ($r2mN -eq 1) { Write-Host ('  ' + $t + ': R2M_CAM только у ОДНОГО из двух файлов (camera_fix.py и launch/bumblebee.launch.py должны быть одного варианта) - пакет r2m_cam стоит не целиком.') }
    $v1N = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^PY_NODE aruco_detect\.py OK POSEFIX_V11$' -or $_ -cmatch '^PY_NODE vpe_fix\.py OK POSEFIX_V11$' }).Count   # r17: оба узла В1.1 (2) или ни одного (0)
    if (@($raw -split "`r?`n" | Where-Object { $_ -cmatch '^PY_NODE aruco_detect\.py DIFF got=890dafbfde99541a0742e26acc81e5f5a222390e7b8244e31fbbfc8f4ccc4338 ' }).Count -gt 0) { Write-Host ('  ' + $t + ': на дроне стоит В1 (aruco_detect.py 890dafbf...), он больше не допускается - нужен откат 49_otkat_posefix_v1.cmd из заготовки _aside_20261119\drone_pkg_posefix_v1_20261118 (49 пакета v1x при В1 откажет), потом установка В1.1: 48 из drone_pkg_posefix_v1x_20261119.') }
    if ($v1N -eq 1) { Write-Host ('  ' + $t + ': POSEFIX_V11 только у ОДНОГО из двух узлов (aruco_detect.py и vpe_fix.py должны быть одного варианта) - вариант В1.1 стоит не целиком.') }
    $okT = ($v[0] -gt 0 -and $v[2] -eq 0 -and $v[1] -eq $expPy -and $v[4] -eq 0 -and $v[3] -eq $expSrc -and $v[5] -eq $expBin -and $v[6] -eq 0 -and $rtDiff -eq 0 -and $rtMiss -eq 0 -and $rtOk -eq $expRt -and ($r2mN -eq 0 -or $r2mN -eq 2) -and ($v1N -eq 0 -or $v1N -eq 2))
    $fpFile = BB-NewOutFile $outDir ('fingerprint_' + $t + '_' + $stamp + '.txt')
    $hdr = @(('# отпечатки оверлея ' + $t + ' на Pi, ' + (Get-Date).ToString('s') + ', ТОЛЬКО ЧТЕНИЕ (шаг 15)'), ('# VERDICT ' + $(if ($okT) { 'OK' } else { 'NOT_OK' })), ('# ' + (($raw -split "`r?`n" | Where-Object { $_ -match '^BB_FP_RESULT ' } | Select-Object -First 1))), ('# ' + ($raw -split "`r?`n" | Where-Object { $_ -match '^BB_FP_RT ' } | Select-Object -First 1)))
    $body = @($raw -split "`r?`n" | Where-Object { $_ -match '^FP_FILE [0-9a-f]{64} ' } | ForEach-Object { $_.Substring(8, 64) + '  ' + $_.Substring(73) })
    $extra = @($raw -split "`r?`n" | Where-Object { $_ -match '^(BIN |SRC |PY_NODE |FP_EXEC |RT_FILE )' } | ForEach-Object { '# ' + $_ })
    [IO.File]::WriteAllText($fpFile, (($hdr + $body + $extra) -join "`r`n") + "`r`n", (BB-Utf8NoBom))
    if ($okT) { Write-Host ('  ' + $t + ': OK, файлов ' + $v[0] + ', бинарников ' + $v[5] + ', не старше исходников. Отпечатки: ' + $fpFile) }
    else { $problems++; Write-Host ('  ' + $t + ': ЗАМЕЧАНИЯ: python отличается ' + $v[2] + ' (ок ' + $v[1] + ' из ' + $expPy + '), исходники отличаются или нет ' + $v[4] + ' (ок ' + $v[3] + ' из ' + $expSrc + '), бинарников ' + $v[5] + ' (ждали ' + $expBin + '), СТАРШЕ исходников ' + $v[6] + ', launch и fcu_detect.py: совпало ' + $rtOk + ' из ' + $expRt + ', отличается ' + $rtDiff + ', нет ' + $rtMiss + '. Файл: ' + $fpFile) -ForegroundColor White -BackgroundColor DarkRed }
}
Write-Host ''
if ($built -eq 0) { Write-Host '  Нет ни одного собранного оверлея (~/bench_ws/r2j, ~/bench_ws/mavros): отпечатков нет.' -ForegroundColor White -BackgroundColor Red; exit 5 }
if ($problems -gt 0) { Write-Host '  СТОП: у собранного есть замечания (строки выше). Подключать нельзя, скажите Claude.' -ForegroundColor White -BackgroundColor Red; exit 5 }
Write-Host 'Готово: отпечатки записаны на ПК (в out), все собранные оверлеи без замечаний.'
exit 0
