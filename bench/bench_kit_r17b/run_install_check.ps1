# run_install_check.ps1 (Claude, 10.11.2026, набор r2; по решениям чата 1 в 19:19 и 19:45) - ТОЛЬКО ЧТЕНИЕ. Что реально исполняется на Pi (install пакета bumblebee) и совпадает ли с образом r2j (pi\install_check.sh).
# Списки: image_r2j\INSTALL_SHA256_r2j.txt (имена *.py: sha256 должны совпасть; остальные имена - бинарные узлы: sha не сверяются, проверяется «не старше изменённых исходников»),
#         image_r2j\CPP_SOURCES_r2j.tsv (C++ исходники и файлы сборки пакета: sha256 должны совпасть; флаг R = r2j меняет файл против дрона, нужна пересборка).
# Список «INSTALL_SHA256_pi» не выдумывается (решение чата 1 19:45): суммы бинарников Pi берутся только с самого Pi.
# Коды выхода: 0 всё совпало и пакет пересобран; 5 расхождение, нет файла, нет префикса install или бинарники старше изменённых исходников (СТОП, решение чата 1); 4 ошибка связи или скрипта.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here 'lib\bb_common.ps1')
. (Join-Path $here 'lib\bb_lists.ps1')
BB-AssertPc
$outDir = BB-OutDir $here
$listInst = Join-Path $here 'image_r2j\INSTALL_SHA256_r2j.txt'
$listCpp = Join-Path $here 'image_r2j\CPP_SOURCES_r2j.tsv'
foreach ($p in $listInst, $listCpp) { if (-not (Test-Path -LiteralPath $p)) { BB-Stop ('нет списка ' + $p) 4 } }
$py = New-Object Collections.Generic.List[string]
$bins = New-Object Collections.Generic.List[string]
foreach ($l in [IO.File]::ReadAllLines($listInst)) {
    if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
    if ($l -cnotmatch '^[0-9a-f]{64}\s+[A-Za-z0-9_.-]{1,60}$') { BB-Stop ('строка списка не «sha256  имя»: ' + $l) 4 }
    $f = ($l.Trim() -replace '\s+', '  ').Split([string[]]@('  '), [StringSplitOptions]::None)
    if ($f[1].EndsWith('.py')) { $py.Add(($l.Trim() -replace '\s+', '  ')) } else { $bins.Add($f[1]) }
}
$cpp = New-Object Collections.Generic.List[string]
foreach ($l in [IO.File]::ReadAllLines($listCpp)) {
    if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
    $f = $l.Split("`t")
    if ($f.Count -ne 3 -or $f[0] -cnotmatch '^[0-9a-f]{64}$' -or $f[1] -cnotmatch '^[A-Za-z0-9_./-]{1,150}$' -or $f[1] -match '\.\.' -or $f[2] -cnotmatch '^[R-]$') { BB-Stop ('строка списка C++ не sha256 TAB путь TAB R|-: ' + $l) 4 }
    $cpp.Add($f[0] + '  ' + $f[1] + '  ' + $f[2])
}
$cpp = BL-ApplyRealAlt $here $cpp   # r11 (16.11): flight_marker.py и flight_marker_loop.py - r2j ИЛИ карта real (image_r2j\EXAMPLES_REAL_20261116.tsv), остальное строго r2j
$rt = BL-RtList $here   # решение чата 1 21:50 (S2): launch-файлы и fcu_detect.py по sha256
$py = BL-ApplyJd2Alt $here $py   # r13 (17.11): aruco_detect.py - r2j ИЛИ детектор меток варианта jd2 (image_r2j\POSEFIX_JD2_20261117.tsv, метка POSEFIX_JD2), остальные python-узлы строго r2j
$py = BL-ApplyV11Alt $here $py   # r17 (19.11): вариант В1.1 - aruco_detect.py «r2j,jd2,v11» и vpe_fix.py «r2j,v1» (image_r2j\POSEFIX_V11_20261119.tsv, метка POSEFIX_V11), оба узла одного варианта; aruco В1 (890dafbf) - СТОП
$py = BL-ApplyR2mPyAlt $here $py; $rt = BL-ApplyR2mRtAlt $here $rt   # r14 (17.11): camera_fix.py и launch/bumblebee.launch.py - r2j ИЛИ камера r2m_cam (image_r2j\R2M_CAM_20261117.tsv, метка R2M_CAM), оба одного варианта; остальное строго r2j
if ($py.Count -lt 1 -or $cpp.Count -lt 1 -or $bins.Count -lt 1) { BB-Stop 'список пуст (python-узлов, C++ исходников или бинарников)' 4 }
$tpl = Join-Path $here 'pi\install_check.sh'
if (-not (Test-Path -LiteralPath $tpl)) { BB-Stop ('нет файла ' + $tpl) 4 }
$text = ([IO.File]::ReadAllText($tpl)) -replace "`r`n", "`n"
foreach ($mk in '#@@LIST@@', '#@@CPP@@', '#@@BINS@@', '#@@RT@@') { if (-not $text.Contains($mk + "`n")) { BB-Stop ('в pi\install_check.sh нет строки ' + $mk) 4 } }
$text = $text.Replace("#@@LIST@@`n", (($py -join "`n") + "`n")).Replace("#@@CPP@@`n", (($cpp -join "`n") + "`n")).Replace("#@@BINS@@`n", (($bins -join "`n") + "`n")).Replace("#@@RT@@`n", (($rt -join "`n") + "`n"))
$stamp = (Get-Date).ToString('yyyyMMdd_HHmmss')
$gen = BB-NewOutFile $outDir ('install_check_' + $stamp + '.generated.sh')
[IO.File]::WriteAllText($gen, $text, (BB-Utf8NoBom))
$rawFile = BB-NewOutFile $outDir ('install_check_' + $stamp + '.txt')
$errFile = BB-NewOutFile $outDir ('install_check_' + $stamp + '.err.txt')
$ssh = BB-FindSsh
BB-TestDrone $ssh
$remote = BB-RemoteCommand $gen @()
Write-Host ('Сверяю на Pi: python-узлов ' + $py.Count + ', C++ исходников ' + $cpp.Count + ', бинарных узлов ' + $bins.Count + ', launch и fcu_detect ' + $rt.Count + ' (только чтение) ...')
$rc = BB-RunSsh $ssh ($script:BB_SshOpts + ' ' + $script:BB_DroneHost + ' "' + $remote + '"') $rawFile $errFile 120
$raw = ''; if (Test-Path -LiteralPath $rawFile) { $raw = [IO.File]::ReadAllText($rawFile) }
if ($rc -ne 0 -or $raw -notmatch 'BB_INSTALL_CHECK_DONE') {
    $failed = $rawFile -replace '\.txt$', '.FAILED.txt'
    if (Test-Path -LiteralPath $rawFile) { Move-Item -LiteralPath $rawFile -Destination $failed }
    BB-Stop ('сверка install не закончилась (код ssh ' + $rc + '). ' + (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)) 4
}
foreach ($l in ($raw -split "`r?`n")) { if ($l -match '^(INSTALL_|CPP_SRC|RT_FILE|BB_RTPY|OTHER_COPY|BB_INSTALL_CHECK )') { Write-Host $l } }
$m = [regex]::Match($raw, 'BB_INSTALL_CHECK ok=(\d+) diff=(\d+) missing=(\d+) noprefix=(\d+) cpp_ok=(\d+) cpp_diff=(\d+) cpp_missing=(\d+) bin_ok=(\d+) bin_missing=(\d+) stale=(\d+)')
if (-not $m.Success) { BB-Stop 'в выводе нет итоговой строки BB_INSTALL_CHECK с полями C++' 4 }
$v = @(1..10 | ForEach-Object { [int]$m.Groups[$_].Value })
$mr = [regex]::Match($raw, 'BB_RTPY ok=(\d+) diff=(\d+) missing=(\d+)')
if ($v[3] -eq 0 -and -not $mr.Success) { BB-Stop 'в выводе нет итоговой строки BB_RTPY (launch и fcu_detect)' 4 }
$rtOk = 0; $rtDiff = 0; $rtMiss = 0; if ($mr.Success) { $rtOk = [int]$mr.Groups[1].Value; $rtDiff = [int]$mr.Groups[2].Value; $rtMiss = [int]$mr.Groups[3].Value }
$okN = $v[0]; $diffN = $v[1]; $missN = $v[2]; $nop = $v[3]; $cok = $v[4]; $cdiff = $v[5]; $cmiss = $v[6]; $bok = $v[7]; $bmiss = $v[8]; $stale = $v[9]
$r2mN = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^INSTALL_FILE camera_fix\.py OK R2M_CAM$' -or $_ -cmatch '^RT_FILE LAUNCH launch/bumblebee\.launch\.py OK R2M_CAM$' }).Count   # r14: оба файла r2m_cam (2) или ни одного (0); один из двух - пакет стоит не целиком
$v1N = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^INSTALL_FILE aruco_detect\.py OK POSEFIX_V11$' -or $_ -cmatch '^INSTALL_FILE vpe_fix\.py OK POSEFIX_V11$' }).Count   # r17: оба узла В1.1 (2) или ни одного (0); один из двух - В1.1 стоит не целиком
$oldV1 = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^INSTALL_FILE aruco_detect\.py DIFF got=890dafbfde99541a0742e26acc81e5f5a222390e7b8244e31fbbfc8f4ccc4338 ' }).Count   # r17: на дроне детектор В1 (r16), он больше не допускается
Write-Host ''
if ($nop -eq 0 -and $diffN -eq 0 -and $missN -eq 0 -and $okN -eq $py.Count -and $cdiff -eq 0 -and $cmiss -eq 0 -and $cok -eq $cpp.Count -and $bmiss -eq 0 -and $bok -eq $bins.Count -and $stale -eq 0 -and $rtDiff -eq 0 -and $rtMiss -eq 0 -and $rtOk -eq $rt.Count -and ($r2mN -eq 0 -or $r2mN -eq 2) -and ($v1N -eq 0 -or $v1N -eq 2)) {
    if ($v1N -eq 2) { Add-Content -LiteralPath $rawFile -Value '# POSEFIX_V11: на дроне В1.1 (детектор + vpe_fix)' -Encoding UTF8 }   # r17a (19.11, проверка wf_2a438f6b): строка и в файле отчёта, до «# VERDICT OK»
    Add-Content -LiteralPath $rawFile -Value '# VERDICT OK' -Encoding UTF8   # S1 (чат 1, 21:50): 07 проверяет эту строку (она последняя)
    $varOk = (@($raw -split "`r?`n" | Where-Object { $_ -cmatch '^INSTALL_FILE aruco_detect\.py OK POSEFIX_JD2$' }).Count -gt 0 -or $v1N -eq 2 -or $r2mN -eq 2)   # r17a: есть допущенный вариант - не писать «совпали с r2j» без оговорки
    Write-Host ('Готово: python-узлы (' + $okN + ') и C++ исходники (' + $cok + ') совпали с r2j' + $(if ($varOk) { ' и допущенными вариантами (какими - строки ниже)' } else { '' }) + ', launch-файлы и fcu_detect.py (' + $rtOk + ') совпали с r2j, бинарные узлы (' + $bok + ') не старше изменённых исходников. Файл: ' + $rawFile)
    $jd2N = @($raw -split "`r?`n" | Where-Object { $_ -cmatch '^INSTALL_FILE aruco_detect\.py OK POSEFIX_JD2$' }).Count   # r13: строка INSTALL_FILE ... OK POSEFIX_JD2 (детектор меток варианта jd2)
    if ($jd2N -gt 0) { Write-Host ('  POSEFIX_JD2: детектор меток варианта jd2 вместо r2j (aruco_detect.py из image_r2j\POSEFIX_JD2_20261117.tsv, пакет drone_pkg_posefix_jd2_20261117) - строк ' + $jd2N + '. Допускается набором r13; vpe_fix.py и остальные узлы - r2j.') }
    if ($v1N -eq 2) { Write-Host '  POSEFIX_V11: на дроне В1.1 (детектор + vpe_fix)' }   # r17: однозначная строка (решение владельца 19.11)
    if ($r2mN -eq 2) { Write-Host '  R2M_CAM: камера варианта r2m_cam вместо r2j (camera_fix.py и launch/bumblebee.launch.py из image_r2j\R2M_CAM_20261117.tsv, пакет drone_pkg_r2m_cam_20261117) - оба файла. Допускается набором r14; остальные узлы и launch-файлы - r2j.' }
    exit 0
}
Add-Content -LiteralPath $rawFile -Value '# VERDICT NOT_OK' -Encoding UTF8
if ($oldV1 -gt 0) { Write-Host '  СТОП: на дроне стоит В1 (aruco_detect.py 890dafbf...), он больше не допускается - нужен откат 49_otkat_posefix_v1.cmd из заготовки _aside_20261119\drone_pkg_posefix_v1_20261118 (49 пакета v1x при В1 откажет), потом установка В1.1: 48 из drone_pkg_posefix_v1x_20261119. Скажите Claude.' -ForegroundColor White -BackgroundColor Red }
if ($v1N -eq 1) { Write-Host '  POSEFIX_V11: на Pi только ОДИН из двух узлов варианта В1.1 (aruco_detect.py и vpe_fix.py должны быть оба В1.1 или оба не В1.1) - вариант В1.1 стоит не целиком. Это СТОП.' }
if ($r2mN -eq 1) { Write-Host '  R2M_CAM: на Pi только ОДИН из двух файлов r2m_cam (camera_fix.py и launch/bumblebee.launch.py должны быть оба r2j или оба r2m_cam) - пакет r2m_cam стоит не целиком. Это СТОП.' }
Write-Host '  СТОП: на Pi исполняется НЕ то, что в образе r2j (расхождение, нет файла, нет install или пакет не пересобран). Скажите Claude, ничего не запускайте.  ' -ForegroundColor White -BackgroundColor Red
Write-Host ('  python: совпало ' + $okN + ' из ' + $py.Count + ', отличается ' + $diffN + ', нет ' + $missN + '; C++ исходники: совпало ' + $cok + ' из ' + $cpp.Count + ', отличается ' + $cdiff + ', нет ' + $cmiss + '; бинарники: ' + $bok + ' из ' + $bins.Count + ', нет ' + $bmiss + ', СТАРШЕ исходников ' + $stale + '; launch и fcu_detect (по sha256): совпало ' + $rtOk + ' из ' + $rt.Count + ', отличается ' + $rtDiff + ', нет ' + $rtMiss + '; нет префикса ' + $nop + '. Файл: ' + $rawFile)
if ($stale -gt 0) { Write-Host '  Старые бинарники: r2j меняет C++ (simple_offboard.cpp, script_lease.h, state_link.h, CMakeLists.txt, package.xml) против образа на дроне; нужна сборка пакета на Pi (шаг МЕНЯЕТ ДРОН для владельца, в списке).' }
if ($rtDiff -gt 0 -or $rtMiss -gt 0) { Write-Host '  launch и fcu_detect.py: fcu_detect.py на Pi должен быть ИСПРАВЛЕННЫЙ (fcu_detect_fix_01, исправление порта; 5932a00a...), launch-файлы берутся из того install, который исполняется (после 13 и 16 это оверлей r2j).' }
exit 5
