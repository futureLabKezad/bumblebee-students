# run_tests_r7.ps1 (Claude, 13.11.2026, набор r7) - тесты НОВОГО в r7 на ПК, в песочнице. К дрону не подключается: вместо ssh и scp стоят подделки
# fake_ssh_r7.exe и fake_scp_r6.exe (первые в PATH; сеть не открывают). Скрипт Pi шага 25 и установщик образа с настоящим payload проверяет run_tests_r7_pi.sh в WSL.
# K: r7 = копия r6: все файлы r6 (список _aside\SHA256SUMS_r6_copy.txt, его sha256 7498ee24...) байт в байт, кроме README.md и PROGRESS.md; новых файлов - только ожидаемые.
# P: payload и image_manifest.final.tsv r2j: формат, состав, байт в байт с образом /work/fixed_image_r2j_20261111 (чтение через \\wsl.localhost), hover r6, MAVROS bp02;
#    полнота против image_manifest_r2.tsv образа; списки набора (CPP_SOURCES, RUNTIME_PY, INSTALL_SHA256, required_shas);
#    P24 (v2, 13.11 ~05:30): модель «дрон после 05» по копии файлов дрона 12.11 (..\drone_backup_kit_20261111\...\FILES_SHA256.txt, только чтение).
# G: гейт 05 (check_gates.ps1) на копии: нет флага и TBD - отказ; флаг теста + TBD - отказ ТОЛЬКО по BACKUP_ROOT; + BACKUP_ROOT в копии - код 0. Гейт 05c/06c с TBD - отказ.
#    05_install_r2j.cmd с TBD - отказ без обращения к дрону.
# B: BACKUP_ROOT - одна строка в image_r2j\image_target.conf, TBD; backup_root_r7.ps1 (проверка; запись по слову владельца) на копии.
# N: шаг 25 (25_metki_nomera.cmd, run_r7_metki.ps1) на подделке ssh.
# S: статические проверки новых файлов. R (поправка r8): 01 зовёт params_check этого набора; out\ пуст.
# r8 (13.11): поправки под r8 - K3/K4 знают изменённые и новые файлы r8; R1/R2 - место r8; N-тесты идут на r7-версии 25 из _aside\r7_step25 (новый 25 - тесты W r8); S3 без params_check\.
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r7.ps1 [-ImgRoot <папка образа r2j в Windows-виде>]. Итог: «ИТОГ r7: PASS n, FAIL m».
param([string]$ImgRoot = '\\wsl.localhost\Ubuntu-24.04\work\fixed_image_r2j_20261111', [string]$HoverRoot = '\\wsl.localhost\Ubuntu-24.04\work\c6_hover_script_r6_20261110', [string]$MavRoot = '\\wsl.localhost\Ubuntu-24.04\work\ws_mavros214_bp02\src\mavros-source')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r7_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0; $script:seq = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') {
    if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") }
}
function Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
function Rel([string]$p) { return $p.Substring($Kit.Length + 1) }
$realPc = $env:COMPUTERNAME
if ($realPc -ne 'DESKTOP-H5CPN8E') { Note ('ВНИМАНИЕ: имя ПК ' + $realPc + ', тесты рассчитаны на DESKTOP-H5CPN8E') }
$IK = Join-Path $Kit 'image_r2j'
$MAN = Join-Path $IK 'image_manifest.final.tsv'

# ======================= K: копия r6 =======================
$r6s = Join-Path $Kit '_aside\SHA256SUMS_r6_copy.txt'
Check 'K1' 'список r6 лежит в _aside, sha256 = 7498ee24... (SHA256SUMS принятого r6)' ((Test-Path -LiteralPath $r6s) -and (Sha $r6s) -eq '7498ee2437fbf2aae97dfb6e02861d401fccd9b20589e87d85408c0af819afc4') ''
$r6 = @{}; foreach ($l in [IO.File]::ReadAllLines($r6s)) { if ($l -match '^([0-9a-f]{64})  (.+)$') { $r6[$Matches[2]] = $Matches[1] } }
$diffR6 = @(); $missR6 = @()
foreach ($k in $r6.Keys) {
    $p = Join-Path $Kit ($k -replace '/', '\')
    if (-not (Test-Path -LiteralPath $p)) { $missR6 += $k; continue }
    if ((Sha $p) -ne $r6[$k]) { $diffR6 += $k }
}
Check 'K2' ('все ' + $r6.Count + ' файлов r6 есть в r7') ($r6.Count -eq 235 -and $missR6.Count -eq 0) ($missR6 -join ', ')
Check 'K3' 'файлы r6 в r7 байт в байт как в r6, кроме README.md и PROGRESS.md (раздел r7 сверху); r8: и 01, 07 (params_check v3), тесты run_tests_bench.ps1 и run_tests_r6.ps1 (поправки под r8)' ((@($diffR6 | Where-Object { $_ -notin 'README.md', 'PROGRESS.md', '01_snimok_do.cmd', '07_vzlet_zagotovka.cmd', 'tests/run_tests_bench.ps1', 'tests/run_tests_r6.ps1' })).Count -eq 0) ($diffR6 -join ', ')
$manRows = @([IO.File]::ReadAllLines($MAN) | Where-Object { $_ -ne '' -and -not $_.StartsWith('#') })
$expNew = @('SHA256SUMS.txt', 'DIFF_r6_r7.txt', '_aside/SHA256SUMS_r6_copy.txt', '25_metki_nomera.cmd', 'run_r7_metki.ps1', 'pi/r7_marker_ids.sh', 'cards/КАРТОЧКА_25_МЕТКИ_НОМЕРА.md',
    'image_r2j/image_manifest.final.tsv', 'image_r2j/PAYLOAD_SOURCES_r2j.tsv', 'image_r2j/NOT_IN_PAYLOAD_r2j.txt', 'image_r2j/BUILD_LOG_payload_r2j.txt', 'image_r2j/backup_root_r7.ps1',
    'tests/run_tests_r7.ps1', 'tests/run_tests_r7_pi.sh', 'tests/fake_ssh_r7.cs') + @($manRows | ForEach-Object { 'image_r2j/payload/' + ($_ -split "`t")[0] })
$allNow = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | Where-Object { $_.FullName -notmatch '\\tests\\run_r[0-9a-z_]*_\d{8}' -and $_.FullName -notmatch '\\tests\\run_[a-z]_\d{8}' } | ForEach-Object { (Rel $_.FullName) -replace '\\', '/' })
# _aside/r7_v1_0300/*: прежние версии r7 (01:13-03:00) до правки 05:30 (находка по копии дрона 12.11) - байт в байт, в работе не участвуют
# r8 (13.11): новые файлы r8 (их точный список проверяет K4 тестов r8)
$expR8 = @('DIFF_r7_r8.txt', '_aside/SHA256SUMS_r7_copy.txt', '_aside/r7_step25/25_metki_nomera.cmd', 'run_r8_metki.ps1', 'pi/r8_marker_wake.sh', 'tests/run_tests_r8.ps1', 'tests/run_tests_r8_pi.sh', 'tests/fake_ssh_r8.cs') + @('approved_changes.txt', 'compare_params.ps1', 'ignore_counters.txt', 'params_check.cmd', 'params_read.sh', 'profile_values.tsv', 'run_params_check.ps1' | ForEach-Object { 'params_check/' + $_ })
$unexp = @($allNow | Where-Object { -not $r6.ContainsKey($_) -and $_ -notin $expNew -and $_ -notlike 'tests/pystub_r7/*' -and $_ -notlike 'proverka_r7/*' -and $_ -notlike '_aside/r7_v1_0300/*' -and $_ -notin $expR8 -and $_ -notlike 'tests/pystub_r8/*' -and $_ -notlike 'proverka_r8/*' })
Check 'K4' 'новых файлов в r7 - только ожидаемые (payload по манифесту, шаг 25, BACKUP_ROOT, тесты, proverka_r7, суммы)' ($unexp.Count -eq 0) ($unexp -join ', ')
$outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -Force -ErrorAction SilentlyContinue)
Check 'K5' 'папка out\ в r7 есть и пуста (ответы сессии лягут сюда)' ((Test-Path -LiteralPath (Join-Path $Kit 'out')) -and $outFiles.Count -eq 0) ($outFiles.Name -join ', ')

# ======================= R: место набора =======================
$r8pc = Join-Path $Kit 'params_check\params_check.cmd'
$c01 = [IO.File]::ReadAllText((Join-Path $Kit '01_snimok_do.cmd'))
Check 'R1' ('r8: 01 зовёт params_check этого набора (' + $r8pc + ', чтение таблицы MAVROS v3), а не ..\kit_20261109_r4') ((Test-Path -LiteralPath $r8pc) -and $c01.Contains('set "PCC=%~dp0params_check\params_check.cmd"') -and $c01 -notmatch 'kit_20261109_r4') ''
Check 'R2' 'набор r8 лежит рядом с r6 и r7 (не внутри папки сессии)' ((Test-Path -LiteralPath (Join-Path (Split-Path $Kit) 'bench_kit_20261112_r6')) -and (Test-Path -LiteralPath (Join-Path (Split-Path $Kit) 'bench_kit_20261113_r7')) -and (Split-Path $Kit -Leaf) -eq 'bench_kit_20261113_r8') (Split-Path $Kit)

# ======================= P: payload и манифест =======================
$mt = [IO.File]::ReadAllText($MAN)
$bad = @(); $paths = @(); $shaOf = @{}
foreach ($r in $manRows) {
    $f = $r.Split("`t")
    if ($f.Count -ne 2 -or $f[1] -cnotmatch '^[0-9a-f]{64}$') { $bad += $r; continue }
    $paths += $f[0]; $shaOf[$f[0]] = $f[1]
}
Check 'P1' 'манифест: UTF-8 без BOM, только LF, без TBD; 68 строк «путь<TAB>sha256» (режим не задан, как у r2h)' ([IO.File]::ReadAllBytes($MAN)[0] -ne 0xEF -and -not $mt.Contains("`r") -and $mt -notmatch 'TBD' -and $manRows.Count -eq 68 -and $bad.Count -eq 0) ($bad -join ' | ')
$unsafe = @($paths | Where-Object { $_ -match '(^|/)\.\.?(/|$)' -or $_.StartsWith('/') -or $_ -match '//' -or $_ -match '[\\ ]' -or $_ -match '^[A-Za-z]:' })
$ord = [string[]]$paths.Clone(); [Array]::Sort($ord, [StringComparer]::Ordinal)
Check 'P2' 'пути без «..», «.», «//», пробелов и «\», не абсолютные; каждый путь один раз; строки отсортированы (по байтам, как sorted() сборщика)' ($unsafe.Count -eq 0 -and (@($paths | Sort-Object -Unique)).Count -eq $paths.Count -and (($paths -join "`n") -ceq ($ord -join "`n"))) ($unsafe -join ', ')
$pay = Join-Path $IK 'payload'
$payFiles = @(Get-ChildItem -LiteralPath $pay -Recurse -File | ForEach-Object { $_.FullName.Substring($pay.Length + 1) -replace '\\', '/' })
$extra = @($payFiles | Where-Object { $_ -ne 'README.md' -and $_ -notin $paths }); $missing = @($paths | Where-Object { $_ -notin $payFiles })
Check 'P3' 'payload = ровно строки манифеста (плюс README.md r6): лишних и недостающих нет' ($extra.Count -eq 0 -and $missing.Count -eq 0 -and $payFiles.Count -eq 69) (('лишние: ' + ($extra -join ', ')) + ('; нет: ' + ($missing -join ', ')))
$shaBad = @($paths | Where-Object { (Sha (Join-Path $pay ($_ -replace '/', '\'))) -ne $shaOf[$_] })
Check 'P4' 'sha256 каждого файла payload = строке манифеста' ($shaBad.Count -eq 0) ($shaBad -join ', ')
Check 'P5' 'fcu_detect.py нет ни в манифесте, ни в payload (на дроне остаётся исправленный 5932a00a)' (-not ($paths | Where-Object { $_ -match '(?i)(^|/)fcu_detect\.py$' }) -and -not ($payFiles | Where-Object { $_ -match '(?i)(^|/)fcu_detect\.py$' })) ''
$req = @{}; foreach ($l in [IO.File]::ReadAllLines((Join-Path $IK 'required_shas.txt'))) { if ($l -match '^([A-Z0-9_]+)=([0-9a-f]{64})$') { $req[$Matches[1]] = $Matches[2] } }
Check 'P6' 'flight.py Ж3 (b69cc5e7..., FLIGHT_PY_SHA256) - ровно ros2_ws/src/bumblebee/examples/flight/flight.py' ($shaOf['ros2_ws/src/bumblebee/examples/flight/flight.py'] -eq $req['FLIGHT_PY_SHA256'] -and $req['FLIGHT_PY_SHA256'] -eq 'b69cc5e72509bbe2f141e48844b999e3a046ac6a78d28484239536b426c807b3') ''
Check 'P7' 'hover r6 (a11b195c..., HOVER_R6_SHA256) - examples/hover_marker0.py' ($shaOf['ros2_ws/src/bumblebee/examples/hover_marker0.py'] -eq $req['HOVER_R6_SHA256'] -and $req['HOVER_R6_SHA256'] -eq 'a11b195ce1507607967ff6a7402726d9eef7b4f12850a9e864f5ae27d1f513f7') ''
$cams = @($paths | Where-Object { $_ -like '*camera_fix.py' })
Check 'P8' 'camera_fix.py ровно один: src/python, камера по умолчанию 4a15d699 (не вариант dabd5076)' ($cams.Count -eq 1 -and $cams[0] -eq 'ros2_ws/src/bumblebee/src/python/camera_fix.py' -and $shaOf[$cams[0]] -eq $req['CAMERA_DEFAULT_SHA256'] -and $shaOf.Values -notcontains $req['CAMERA_VARIANT_SHA256']) ($cams -join ', ')
$mavRows = @([IO.File]::ReadAllLines((Join-Path $IK 'mavros_bp02_sources.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | ForEach-Object { , ($_ -split "`t") })
$mavOk = @($mavRows | Where-Object { $shaOf[('image_r2j_ref/mavros_bp02_d63a236/' + $_[0])] -eq $_[2] })
Check 'P9' 'все 5 исходников MAVROS bp02 (sha256_bp02) - справочная копия image_r2j_ref/mavros_bp02_d63a236/ (вне ~/bench_ws)' ($mavRows.Count -eq 5 -and $mavOk.Count -eq 5 -and @($paths | Where-Object { $_ -like 'image_r2j_ref/*' }).Count -eq 5 -and -not ($paths | Where-Object { $_ -like 'bench_ws/*' })) ''
$other = @($paths | Where-Object { $_ -notlike 'ros2_ws/src/bumblebee/*' -and $_ -notlike 'image_r2j_ref/mavros_bp02_d63a236/*' })
Check 'P10' 'все прочие пути - только ros2_ws/src/bumblebee/... (DEST_ROOT=/home/lb)' ($other.Count -eq 0) ($other -join ', ')
# сверка с источниками в WSL (только чтение через \\wsl.localhost)
$srcOk = (Test-Path -LiteralPath (Join-Path $ImgRoot 'SHA256SUMS'))
Check 'P11' ('образ r2j доступен для сверки: ' + $ImgRoot + '; sha256 SHA256SUMS = 14fbcf74..., image_manifest_r2.tsv = 0c02e391...') ($srcOk -and (Sha (Join-Path $ImgRoot 'SHA256SUMS')) -eq '14fbcf74d847605c927181245f23e5c598c551a24249991070770ea49bf26094' -and (Sha (Join-Path $ImgRoot 'image_manifest_r2.tsv')) -eq '0c02e391c6763ec24aba026512a4caf89e348f3a3507a637423c0d665a345c33') ''
if ($srcOk) {
    $img = @{}; foreach ($l in [IO.File]::ReadAllLines((Join-Path $ImgRoot 'image_manifest_r2.tsv'))) { if ($l -eq '' -or $l.StartsWith('#')) { continue }; $f = $l.Split("`t"); $img[$f[0]] = $f }
    $byteBad = @()
    foreach ($p in ($paths | Where-Object { $_ -like 'ros2_ws/src/bumblebee/*' -and $_ -ne 'ros2_ws/src/bumblebee/examples/hover_marker0.py' })) {
        $src = Join-Path $ImgRoot ('src\' + ($p.Substring('ros2_ws/src/'.Length) -replace '/', '\'))
        if (-not (Test-Path -LiteralPath $src)) { $byteBad += ('нет ' + $p); continue }
        $a = [IO.File]::ReadAllBytes($src); $b = [IO.File]::ReadAllBytes((Join-Path $pay ($p -replace '/', '\')))
        if ($a.Length -ne $b.Length -or [Convert]::ToBase64String($a) -cne [Convert]::ToBase64String($b)) { $byteBad += $p }
        elseif (-not $img.ContainsKey('drone/' + $p) -or $img['drone/' + $p][2] -ne $shaOf[$p]) { $byteBad += ('колонка образа: ' + $p) }
    }
    Check 'P12' 'файлы payload из образа байт в байт = src образа r2j, и sha = колонке sha256_fixed_image его манифеста (62 файла)' ($byteBad.Count -eq 0 -and @($paths | Where-Object { $_ -like 'ros2_ws/src/bumblebee/*' -and $_ -ne 'ros2_ws/src/bumblebee/examples/hover_marker0.py' }).Count -eq 62) ($byteBad -join ', ')
    $need = @($img.Values | Where-Object { $_[0].StartsWith('drone/ros2_ws/src/') -and $_[0] -notmatch '(?i)/fcu_detect\.py$' -and -not ($_[1] -ne '-' -and $_[1] -eq $_[2]) } | ForEach-Object { $_[0].Substring(6) })
    $lost = @($need | Where-Object { $_ -notin $paths })
    Check 'P13' ('полнота: все строки образа под drone/ros2_ws/src/, которые r2j меняет или добавляет против дрона a45a264 (' + $need.Count + '), есть в манифесте') ($need.Count -eq 56 -and $lost.Count -eq 0) ($lost -join ', ')
    $sameIn = @($paths | Where-Object { $img.ContainsKey('drone/' + $_) -and $img['drone/' + $_][1] -eq $img['drone/' + $_][2] })
    # v2 (13.11 ~05:30): кроме камеры по умолчанию - ровно 5 добавок по копии дрона 12.11 (на дроне не равны r2j, их ждут 09, 13, 15); каждая по копии дрона отличается или её нет (P24)
    $addV2 = @('ros2_ws/src/bumblebee/launch/aruco.launch.py', 'ros2_ws/src/bumblebee/launch/led.launch.py', 'ros2_ws/src/bumblebee/launch/simulator.launch.py', 'ros2_ws/src/bumblebee/src/python/qos_relay.py', 'ros2_ws/src/bumblebee/src/python/set_params.py')
    $sameWant = @(@('ros2_ws/src/bumblebee/src/python/camera_fix.py') + $addV2 | Sort-Object)
    Check 'P14' 'из строк, равных в колонке a45a264 и в r2j, в манифесте только camera_fix.py по умолчанию (явно, как в r2h) и 5 добавок v2 по копии дрона 12.11' ((@($sameIn | Sort-Object) -join ',') -ceq ($sameWant -join ',')) ($sameIn -join ', ')
    $notImg = @($paths | Where-Object { -not $img.ContainsKey('drone/' + $_) })
    Check 'P15' 'не из манифеста образа - только hover r6 и 5 исходников MAVROS' ($notImg.Count -eq 6 -and $notImg -contains 'ros2_ws/src/bumblebee/examples/hover_marker0.py') ($notImg -join ', ')
    $fcuRow = $img['drone/ros2_ws/src/bumblebee/scripts/fcu_detect.py']
    Check 'P16' 'в образе fcu_detect.py: колонка образа = исправленный 5932a00a, а в src лежит прежний ee174fd1 - поэтому он не ставится' ($fcuRow[2] -eq '5932a00afc79e421a7bb26a7e84564cf106afdcbc009642c7e872ab86b839bf5' -and (Sha (Join-Path $ImgRoot 'src\bumblebee\scripts\fcu_detect.py')).StartsWith('ee174fd1')) ''
}
$hv = Join-Path $HoverRoot 'hover_marker0.py'
Check 'P17' 'hover r6 в payload байт в байт = /work/c6_hover_script_r6_20261110/hover_marker0.py' ((Test-Path -LiteralPath $hv) -and (Sha $hv) -eq (Sha (Join-Path $pay 'ros2_ws\src\bumblebee\examples\hover_marker0.py'))) ''
$mvb = @($mavRows | Where-Object { $s = Join-Path $MavRoot ($_[0] -replace '/', '\'); -not (Test-Path -LiteralPath $s) -or (Sha $s) -ne (Sha (Join-Path $pay ('image_r2j_ref\mavros_bp02_d63a236\' + ($_[0] -replace '/', '\')))) })
Check 'P18' 'исходники MAVROS в payload байт в байт = /work/ws_mavros214_bp02/src/mavros-source (тег backport-02)' ($mvb.Count -eq 0) ''
$cpp = @([IO.File]::ReadAllLines((Join-Path $IK 'CPP_SOURCES_r2j.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | ForEach-Object { , ($_ -split "`t") })
$cppR = @($cpp | Where-Object { $_[2] -eq 'R' }); $cppRin = @($cppR | Where-Object { $shaOf[$_[1]] -eq $_[0] })
$cppIn = @($cpp | Where-Object { $shaOf.ContainsKey($_[1]) -and $shaOf[$_[1]] -ne $_[0] })
Check 'P19' 'CPP_SOURCES_r2j.tsv: все 5 строк R (пересборка) в payload с той же sha; ни одна строка списка не лежит в payload с другой sha' ($cppR.Count -eq 5 -and $cppRin.Count -eq 5 -and $cppIn.Count -eq 0) ''
$rt = @([IO.File]::ReadAllLines((Join-Path $IK 'RUNTIME_PY_r2j.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | ForEach-Object { , ($_ -split "`t") })
$rtBad = @($rt | Where-Object { $_[1] -eq 'LAUNCH' -and $shaOf.ContainsKey('ros2_ws/src/bumblebee/' + $_[2]) -and $shaOf['ros2_ws/src/bumblebee/' + $_[2]] -ne $_[0] })
Check 'P20' 'RUNTIME_PY_r2j.tsv: launch-файлы в payload с той же sha (bumblebee, main_camera, second_camera, mavros_scoped_config), строка FCU не в payload' ($rtBad.Count -eq 0 -and $shaOf['ros2_ws/src/bumblebee/launch/bumblebee.launch.py'] -eq '62be01dbb13305bca321d538690252863dedadb8a376e65e54d9f6c15116bf15' -and $shaOf.ContainsKey('ros2_ws/src/bumblebee/launch/main_camera.launch.py') -and $shaOf.ContainsKey('ros2_ws/src/bumblebee/launch/second_camera.launch.py') -and $shaOf.ContainsKey('ros2_ws/src/bumblebee/launch/mavros_scoped_config.py')) ''
$ins = @{}; foreach ($l in [IO.File]::ReadAllLines((Join-Path $IK 'INSTALL_SHA256_r2j.txt'))) { if ($l -match '^([0-9a-f]{64})  (\S+)$') { $ins[$Matches[2]] = $Matches[1] } }
Check 'P21' 'INSTALL_SHA256_r2j.txt: aruco_detect.py, vpe_fix.py, setpoint_freshness.py, camera_fix.py в payload src/python с той же sha' ((@('aruco_detect.py', 'vpe_fix.py', 'setpoint_freshness.py', 'camera_fix.py') | Where-Object { $shaOf['ros2_ws/src/bumblebee/src/python/' + $_] -eq $ins[$_] }).Count -eq 4) ''
$ps = @([IO.File]::ReadAllLines((Join-Path $IK 'PAYLOAD_SOURCES_r2j.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | ForEach-Object { , ($_ -split "`t") })
$psBad = @($ps | Where-Object { $shaOf[$_[0]] -ne $_[1] })
$kinds = @{}; foreach ($x in $ps) { $k = ($x[2] -split ' ')[0]; $kinds[$k] = 1 + [int]$kinds[$k] }
Check 'P22' 'PAYLOAD_SOURCES_r2j.tsv = манифесту (68 строк): changed 13, new 43, camera 1, hover 1, MAVROS 5, drone1211-changed 4, drone1211-absent 1' ($ps.Count -eq 68 -and $psBad.Count -eq 0 -and $kinds['changed'] -eq 13 -and $kinds['new'] -eq 43 -and $kinds['camera'] -eq 1 -and $kinds['hover'] -eq 1 -and $kinds['MAVROS'] -eq 5 -and $kinds['drone1211-changed'] -eq 4 -and $kinds['drone1211-absent'] -eq 1) (($kinds.Keys | ForEach-Object { $_ + '=' + $kinds[$_] }) -join ' ')
$nip = [IO.File]::ReadAllText((Join-Path $IK 'NOT_IN_PAYLOAD_r2j.txt'))
Check 'P23' 'NOT_IN_PAYLOAD_r2j.txt: fcu_detect (1), 48 файлов вне ros2_ws/src, 274 равных в колонке a45a264 (5 из них взяты добавками), 54 файла, которые на дроне 12.11 не равны r2j и не ставятся, с разбором' ($nip -match 'drone/ros2_ws/src/bumblebee/scripts/fcu_detect\.py\tfcu_detect' -and ([regex]::Matches($nip, '\tвне drone/ros2_ws/src/')).Count -eq 48 -and $nip -match 'плюс 274 строк' -and ([regex]::Matches($nip, '\tНА_ДРОНЕ_ИНАЧЕ\t')).Count -eq 54 -and ([regex]::Matches($nip, 'отличается только шапкой лицензии')).Count -eq 31) ''
# P24 (v2): «дрон после 05» = файлы НАСТОЯЩЕГО дрона по копии 12.11 (FILES_SHA256.txt) + строки манифеста; на этой модели проверки самого набора:
#   CPP_SOURCES (13 и 15), RUNTIME_PY launch и FCU (09, 15), python-узлы INSTALL_SHA256 (09), файлы install(PROGRAMS) из CMakeLists r2j (без них 13 не соберётся).
#   Контроль: прежний манифест r7 v1 (63 строки, _aside) на той же модели не сходится ровно в 6 местах (3 launch, set_params, qos_relay в INSTALL и в сборке).
$dfs = Join-Path (Split-Path $Kit) 'drone_backup_kit_20261111\out\drone_backup_20261112_102053\FILES_SHA256.txt'
function Model-Fails([string]$manPath) {
    $drone = @{}; foreach ($l in [IO.File]::ReadAllLines($dfs)) { if ($l.Length -gt 66 -and $l.Substring(64, 2) -eq '  ' -and $l.Substring(66).StartsWith('home/lb/')) { $drone[$l.Substring(74)] = $l.Substring(0, 64) } }
    $pm = @{}; foreach ($l in [IO.File]::ReadAllLines($manPath)) { if ($l -ne '' -and -not $l.StartsWith('#')) { $f = $l.Split("`t"); $pm[$f[0]] = $f[1] } }
    $post = { param($p) if ($pm.ContainsKey($p)) { $pm[$p] } elseif ($drone.ContainsKey($p)) { $drone[$p] } else { $null } }
    $fl = @()
    foreach ($x in $cpp) { if ((& $post $x[1]) -ne $x[0]) { $fl += ('CPP ' + $x[1]) } }
    foreach ($x in $rt) { $full = $(if ($x[1] -eq 'FCU') { $x[2] } else { 'ros2_ws/src/bumblebee/' + $x[2] }); if ((& $post $full) -ne $x[0]) { $fl += ('RT ' + $full) } }
    $cm = [IO.File]::ReadAllText((Join-Path $ImgRoot 'src\bumblebee\CMakeLists.txt')) -replace "`r`n", "`n"
    $progs = @(([regex]::Match($cm, '(?s)install\(PROGRAMS\n(.*?)\n\s*DESTINATION')).Groups[1].Value -split '\s+' | Where-Object { $_ } | ForEach-Object { 'ros2_ws/src/bumblebee/' + $_ })
    foreach ($p in $progs) { if ($null -eq (& $post $p)) { $fl += ('CMAKE ' + $p) } }
    foreach ($k in $ins.Keys) { if ($k -notlike '*.py') { continue }; $src = @($progs | Where-Object { $_.EndsWith('/' + $k) }); if ($src.Count -ne 1 -or (& $post $src[0]) -ne $ins[$k]) { $fl += ('INSTALL ' + $k) } }
    if ((& $post 'ros2_ws/src/bumblebee/examples/hover_marker0.py') -ne $req['HOVER_R6_SHA256']) { $fl += 'HOVER' }
    return @{ Fails = $fl; Progs = $progs.Count }
}
if ($srcOk -and (Test-Path -LiteralPath $dfs)) {
    $m2 = Model-Fails $MAN
    $m1 = Model-Fails (Join-Path $Kit '_aside\r7_v1_0300\image_r2j\image_manifest.final.tsv')
    $v1want = @('CMAKE ros2_ws/src/bumblebee/src/python/qos_relay.py', 'INSTALL qos_relay.py', 'INSTALL set_params.py', 'RT ros2_ws/src/bumblebee/launch/aruco.launch.py', 'RT ros2_ws/src/bumblebee/launch/led.launch.py', 'RT ros2_ws/src/bumblebee/launch/simulator.launch.py')
    Check 'P24' ('модель «дрон после 05» (копия дрона 12.11 + манифест r7): проверки набора 09, 13, 15 и сборка сходятся (install(PROGRAMS) ' + $m2.Progs + ' файлов); контроль - манифест v1 (63) не сходится ровно в 6 местах') ($m2.Fails.Count -eq 0 -and $m2.Progs -eq 10 -and ((@($m1.Fails | Sort-Object) -join '|') -ceq (@($v1want | Sort-Object) -join '|'))) ('v2: ' + ($m2.Fails -join ', ') + ' / v1: ' + ($m1.Fails -join ', '))
} else { Check 'P24' ('копия дрона 12.11 (' + $dfs + ') и образ доступны для модели «дрон после 05»') $false '' }

# ======================= песочница и подделки (для G, B, N) =======================
$SB = Join-Path $Run 'sb\bench_kit_r7'
New-Item -ItemType Directory -Path $SB -Force | Out-Null
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = Rel $_.FullName
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest
}
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh_r7.cs'))) -OutputAssembly (Join-Path $FakeDir 'ssh.exe') -OutputType ConsoleApplication
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_scp_r6.cs'))) -OutputAssembly (Join-Path $FakeDir 'scp.exe') -OutputType ConsoleApplication
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'
$sshNow = (Get-Command ssh -CommandType Application | Select-Object -First 1).Source; $scpNow = (Get-Command scp -CommandType Application | Select-Object -First 1).Source
Check 'T0' 'в PATH первыми стоят подделки ssh и scp (настоящий OpenSSH в тестах не вызывается)' ($sshNow -eq (Join-Path $FakeDir 'ssh.exe') -and $scpNow -eq (Join-Path $FakeDir 'scp.exe')) ($sshNow + ' ' + $scpNow)
$Can = Join-Path $Run 'canned'; New-Item -ItemType Directory -Path $Can | Out-Null
function Reset-Fake([string]$mode = 'normal') {
    Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Extension -ne '.exe' -and $_.Extension -ne '.pdb' } | Remove-Item
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), $mode)
}
function Set-Canned([string]$key, [string]$text, [int]$rc = 0) {
    $p = Join-Path $Can ($key + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt'); [IO.File]::WriteAllText($p, ($text -replace "`r`n", "`n"), $utf8n)
    [IO.File]::WriteAllText((Join-Path $FakeDir ('canned_' + $key + '.txt')), $p)
    if ($rc -ne 0) { [IO.File]::WriteAllText((Join-Path $FakeDir ('rc_' + $key + '.txt')), [string]$rc) }
}
function New-Out { $o = Join-Path $Run ('out_' + [guid]::NewGuid().ToString('N').Substring(0, 6)); New-Item -ItemType Directory -Path $o -Force | Out-Null; return $o }
function Read-Calls { $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path $cl) { return @(Get-Content -LiteralPath $cl -Encoding UTF8) } else { return @() } }
function Sent-Scripts { return @(Get-ChildItem -LiteralPath $FakeDir -Filter 'sent_*.sh' -File | Sort-Object { [int]($_.BaseName -replace 'sent_', '') } | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) }
function Clear-Run { Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Name -eq 'calls.log' -or $_.Name -eq 'sent_count.txt' -or $_.Name -like 'sent_*.sh' -or $_.Name -like 'count_*.txt' } | Remove-Item }
function Run-Cmd([string]$cmdRel, [string]$stdin, [string]$out, [string]$pc = $realPc) {
    Clear-Run
    $script:seq++
    $id = 'r' + $script:seq
    $env:BB_KIT_OUT = $out
    $inFile = Join-Path $Run ($id + '_stdin.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $env:COMPUTERNAME = $pc
    $so = Join-Path $Run ($id + '_console.txt')
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + (Join-Path $SB $cmdRel) + '" < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $env:COMPUTERNAME = $realPc
    $calls = Read-Calls
    $con = ''; if (Test-Path $so) { $con = [IO.File]::ReadAllText($so) }
    return @{ Code = $p.ExitCode; Calls = @($calls); J = ($calls -join "`n"); Console = $con; Sent = @(Sent-Scripts) }
}
function Run-Ps([string]$ps1Rel, [string]$argLine, [string]$out, [string]$stdin = '') {
    Clear-Run
    $script:seq++
    $id = 'p' + $script:seq
    $env:BB_KIT_OUT = $out
    $inFile = Join-Path $Run ($id + '_stdin.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $so = Join-Path $Run ($id + '_console.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB $ps1Rel) + '" ' + $argLine) -NoNewWindow -PassThru -Wait -RedirectStandardInput $inFile -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $calls = Read-Calls
    $con = ''; if (Test-Path $so) { $con = [IO.File]::ReadAllText($so) }
    return @{ Code = $p.ExitCode; Calls = @($calls); J = ($calls -join "`n"); Console = $con; Sent = @(Sent-Scripts) }
}
function Fresh-Params([string]$out) {
    $n = @([IO.File]::ReadAllLines((Join-Path $Kit 'params_check\baseline_20261104_1145.params')) | Where-Object { $_ -match "^1`t1`t" }).Count
    [IO.File]::WriteAllText((Join-Path $out 'params_T_report.txt'), ('=== СОВПАДАЕТ: прочитано ' + $n + ' из ' + $n + ', отличий нет (из таблицы MAVROS ' + $n + ', из запасного потока 0) ===' + "`r`n"), $utf8)
    [IO.File]::WriteAllText((Join-Path $out 'params_T.params'), ("1`t1`tCOM_OBL_RC_ACT`t4`t6`r`n"), $utf8)
}
function Gates05([string]$ikDir, [string]$out) {
    $rf = Join-Path $Run ('gates_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ikDir 'check_gates.ps1') -Kit $ikDir -OutDir $out -ReportFile $rf | Out-Null
    $code = $LASTEXITCODE; $o = ''; if (Test-Path $rf) { $o = [IO.File]::ReadAllText($rf) }
    return @{ Code = $code; Text = $o; Lines = @($o -split "`r?`n" | Where-Object { $_.StartsWith('- ') }) }
}
function Copy-Ik([string]$name) { $d = Join-Path $Run $name; New-Item -ItemType Directory -Path $d | Out-Null; Copy-Item -LiteralPath $IK -Destination (Join-Path $d 'image_r2j') -Recurse; Copy-Item -LiteralPath (Join-Path $Kit 'params_check') -Destination (Join-Path $d 'params_check') -Recurse; New-Item -ItemType Directory -Path (Join-Path $d 'out') | Out-Null; return $d }
function Set-Flag([string]$ikDir) {
    $s = Sha (Join-Path $ikDir 'image_manifest.final.tsv')
    [IO.File]::WriteAllText((Join-Path $ikDir 'gates\S2_S3_PASSED.txt'), ("S2=PASS`r`nS3=PASS`r`nДАТА=2026-11-13`r`nДОКАЗАТЕЛЬСТВО=тест в песочнице (настоящий флаг выписывает только чат 1)`r`nОБРАЗ_MANIFEST_SHA256=" + $s + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
}
function Set-Broot([string]$confPath, [string]$v) { $t = [IO.File]::ReadAllText($confPath); [IO.File]::WriteAllText($confPath, ($t -replace '(?m)^BACKUP_ROOT=TBD$', ('BACKUP_ROOT=' + $v)), $utf8n) }

# ======================= G: гейты 05 / 05c / 06c и BACKUP_ROOT =======================
$o0 = New-Out
$g = Gates05 $IK $o0
Check 'G1' 'настоящий r7 (без копии): гейт 05 отказывает: нет флага S2/S3, нет сверки, BACKUP_ROOT (TBD); про манифест и payload замечаний нет' ($g.Code -eq 1 -and $g.Text -match 'S2_S3_PASSED' -and $g.Text -match 'Нет сверки' -and $g.Text -match 'не заполнено BACKUP_ROOT \(TBD\)' -and $g.Lines.Count -eq 3) $g.Text
$d1 = Copy-Ik 'g2'; Fresh-Params (Join-Path $d1 'out')
$g = Gates05 (Join-Path $d1 'image_r2j') (Join-Path $d1 'out')
Check 'G2' 'копия r7, свежая сверка: отказ ровно по двум причинам - нет флага S2/S3 и BACKUP_ROOT (TBD)' ($g.Code -eq 1 -and $g.Lines.Count -eq 2 -and $g.Text -match 'S2_S3_PASSED' -and $g.Text -match 'BACKUP_ROOT') $g.Text
Set-Flag (Join-Path $d1 'image_r2j')
$g = Gates05 (Join-Path $d1 'image_r2j') (Join-Path $d1 'out')
Check 'G3' 'та же копия + флаг теста на sha этого манифеста: отказ ТОЛЬКО по BACKUP_ROOT (TBD) - без строки владельца 05 не пойдёт' ($g.Code -eq 1 -and $g.Lines.Count -eq 1 -and $g.Text -match 'не заполнено BACKUP_ROOT \(TBD\)') $g.Text
Set-Broot (Join-Path $d1 'image_r2j\image_target.conf') '/home/lb/bb_backup'
$g = Gates05 (Join-Path $d1 'image_r2j') (Join-Path $d1 'out')
Check 'G4' 'та же копия + BACKUP_ROOT в копии: гейт 05 = код 0 (манифест и payload r7 проходят все проверки состава: flight.py, hover r6, камера, MAVROS, без fcu_detect)' ($g.Code -eq 0 -and $g.Text.Trim() -eq 'OK') $g.Text
Add-Content -LiteralPath (Join-Path $d1 'image_r2j\payload\ros2_ws\src\bumblebee\examples\drone.py') -Value '# x'
$g = Gates05 (Join-Path $d1 'image_r2j') (Join-Path $d1 'out')
Check 'G5' 'контроль: изменённый файл payload (drone.py) - гейт 05 отказывает (sha не сходится)' ($g.Code -eq 1 -and $g.Text -match 'SHA256 файла ros2_ws/src/bumblebee/examples/drone\.py не сходится') $g.Text
foreach ($mode in 'install', 'rollback') {
    $so = Join-Path $Run ('camgate_' + $mode + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $Kit 'image_r2j_cam\check_gates_r2j_cam.ps1') + '" -Kit "' + (Join-Path $Kit 'image_r2j_cam') + '" -OutDir "' + $o0 + '" -Mode ' + $mode) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $t = [IO.File]::ReadAllText($so)
    Check 'G6' ('гейт варианта камеры (05c/06c), режим ' + $mode + ', настоящий r7: отказ, среди причин - BACKUP_ROOT (TBD)') ($p.ExitCode -eq 1 -and $t -match 'не заполнено BACKUP_ROOT \(TBD\)') ''
}
$o5 = New-Out; Fresh-Params $o5
Set-Flag (Join-Path $SB 'image_r2j')
$ls = [IO.File]::ReadAllText((Join-Path $SB 'image_r2j\05_install_r2j.cmd')) -split "`r`n"
[IO.File]::WriteAllText((Join-Path $SB 'image_r2j\05_install_r2j.cmd'), (($ls | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
Reset-Fake
$r = Run-Cmd 'image_r2j\05_install_r2j.cmd' "YES`r`n" $o5
Check 'G7' '05 из песочницы r7 с флагом теста и свежей сверкой, BACKUP_ROOT = TBD: код 1, «условия не выполнены», к дрону не обращались (ни ssh, ни scp)' ($r.Code -eq 1 -and $r.Console -match 'BACKUP_ROOT' -and $r.Calls.Count -eq 0 -and -not (Test-Path (Join-Path $FakeDir 'scp_calls.log'))) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Remove-Item -LiteralPath (Join-Path $SB 'image_r2j\gates\S2_S3_PASSED.txt')

# ======================= B: BACKUP_ROOT одной строкой =======================
$conf = [IO.File]::ReadAllText((Join-Path $IK 'image_target.conf'))
Check 'B1' 'image_r2j\image_target.conf r7 = r6 байт в байт: ровно одна строка BACKUP_ROOT=TBD и DEST_ROOT=/home/lb' ((Sha (Join-Path $IK 'image_target.conf')) -eq $r6['image_r2j/image_target.conf'] -and ([regex]::Matches($conf, '(?m)^BACKUP_ROOT=')).Count -eq 1 -and $conf -match '(?m)^BACKUP_ROOT=TBD$' -and $conf -match '(?m)^DEST_ROOT=/home/lb$') ''
$assign = @(Get-ChildItem -LiteralPath $Kit -Recurse -File -Include '*.conf', '*.sh', '*.ps1', '*.cmd', '*.py' | Where-Object { $_.FullName -notmatch '\\tests\\|\\_aside\\|\\proverka_r[0-9]\\|\\image_r2j\\payload\\' } | Where-Object { [IO.File]::ReadAllText($_.FullName) -match '(?m)^\s*BACKUP_ROOT=[^$]' } | ForEach-Object { Rel $_.FullName })
Check 'B2' 'значение BACKUP_ROOT задаётся только в image_r2j\image_target.conf (05, 06, 05c, 06c читают эту одну строку)' ($assign.Count -eq 1 -and $assign[0] -eq 'image_r2j\image_target.conf') ($assign -join ', ')
$br = Join-Path $Kit 'image_r2j\backup_root_r7.ps1'
$p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $br + '"') -NoNewWindow -PassThru -Wait -RedirectStandardOutput (Join-Path $Run 'br0.txt') -RedirectStandardError (Join-Path $Run 'br0.err')
Check 'B3' 'backup_root_r7.ps1 без ключей на настоящем r7: код 1 «не задан (TBD)», файл не изменён' ($p.ExitCode -eq 1 -and ([IO.File]::ReadAllText((Join-Path $Run 'br0.txt'))) -match 'не задан \(TBD\)' -and (Sha (Join-Path $IK 'image_target.conf')) -eq $r6['image_r2j/image_target.conf']) ''
function Br([string]$dir, [string]$argLine) {
    $so = Join-Path $Run ('br_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $dir 'backup_root_r7.ps1') + '" ' + $argLine) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    return @{ Code = $p.ExitCode; Text = [IO.File]::ReadAllText($so) }
}
$bd = Join-Path (Copy-Ik 'b1') 'image_r2j'; $c0 = Sha (Join-Path $bd 'image_target.conf')
$badVals = @('/tmp/bak', '/home/lb', '/home/lb/ros2_ws/bak', '/home/lb/bench_ws/bak', 'home/lb/bak', '/home/lb/bb backup', '/home/lb/a;b', '/home/lb/../x', '/home/lb/bak/', '/x', '/home/lb/bak$(id)')
$allRefused = $true
foreach ($v in $badVals) { $x = Br $bd ('-Set "' + $v + '" -OwnerWords "тест"'); if ($x.Code -ne 2 -or $x.Text -notmatch 'Ничего не изменено') { $allRefused = $false; Note ('  не отказал: ' + $v + ' -> ' + $x.Code) } }
Check 'B4' ('-Set с негодным значением (' + $badVals.Count + ' случаев: /tmp, DEST_ROOT, ros2_ws, bench_ws, относительный, пробел, ;, .., / в конце, короткий, $()): код 2, файл тот же') ($allRefused -and (Sha (Join-Path $bd 'image_target.conf')) -eq $c0 -and -not (Test-Path (Join-Path $bd 'BACKUP_ROOT_ЗАПИСЬ.txt'))) ''
$x = Br $bd '-Set "/home/lb/bb_backup"'
Check 'B5' '-Set без слов владельца: код 2, файл тот же' ($x.Code -eq 2 -and (Sha (Join-Path $bd 'image_target.conf')) -eq $c0) $x.Text
$x = Br $bd '-Set "/home/lb/bb_backup" -OwnerWords "тест: папка резерва /home/lb/bb_backup"'
$before = [IO.File]::ReadAllText((Join-Path $Kit 'image_r2j\image_target.conf')) -split "`n"; $after = [IO.File]::ReadAllText((Join-Path $bd 'image_target.conf')) -split "`n"
$dl = @(); for ($i = 0; $i -lt [Math]::Max($before.Count, $after.Count); $i++) { if ($i -ge $before.Count -or $i -ge $after.Count -or $before[$i] -cne $after[$i]) { $dl += $i } }
$rec = Join-Path $bd 'BACKUP_ROOT_ЗАПИСЬ.txt'
$asideOk = @(Get-ChildItem -LiteralPath $bd -Directory -Filter '_aside_conf_*' | Where-Object { (Sha (Join-Path $_.FullName 'image_target.conf')) -eq $c0 }).Count -eq 1
Check 'B6' '-Set по слову владельца (на копии): код 0, изменилась ровно одна строка (BACKUP_ROOT=/home/lb/bb_backup), прежний файл в _aside_conf_*, запись со словами и sha до/после' ($x.Code -eq 0 -and $dl.Count -eq 1 -and $after[$dl[0]] -ceq 'BACKUP_ROOT=/home/lb/bb_backup' -and $asideOk -and (Test-Path $rec) -and ([IO.File]::ReadAllText($rec)) -match 'СЛОВА_ВЛАДЕЛЬЦА=тест: папка резерва /home/lb/bb_backup' -and ([IO.File]::ReadAllText($rec)) -match ('SHA256_ДО=' + $c0) -and ([IO.File]::ReadAllText($rec)) -match ('SHA256_ПОСЛЕ=' + (Sha (Join-Path $bd 'image_target.conf')))) $x.Text
$x2 = Br $bd ''
$x3 = Br $bd '-Set "/home/lb/other" -OwnerWords "тест"'
Check 'B7' 'после записи: проверка - код 0 «задан и годен»; второй -Set - отказ (код 2, менять только новым решением владельца)' ($x2.Code -eq 0 -and $x3.Code -eq 2 -and ([IO.File]::ReadAllText((Join-Path $bd 'image_target.conf'))) -match '(?m)^BACKUP_ROOT=/home/lb/bb_backup$') ($x2.Text + $x3.Text)
Set-Flag $bd; $bo = Join-Path (Split-Path $bd) 'out'; Fresh-Params $bo
$g = Gates05 $bd $bo
Check 'B8' 'копия после -Set + флаг теста: гейт 05 = код 0 (строка, записанная инструментом, гейт проходит)' ($g.Code -eq 0) $g.Text
$x4 = Br (Join-Path (Copy-Ik 'b2') 'image_r2j') '-Set "/home/lb/bb_backup" -OwnerWords "тест"'; $twice = Join-Path $Run 'b3\image_r2j'; $null = Copy-Ik 'b3'
[IO.File]::AppendAllText((Join-Path $twice 'image_target.conf'), "`nBACKUP_ROOT=/home/lb/x`n", $utf8n)
$x5 = Br $twice ''
Check 'B9' 'две строки BACKUP_ROOT= в файле: проверка - код 2 «должна быть ровно одна»' ($x4.Code -eq 0 -and $x5.Code -eq 2 -and $x5.Text -match 'ровно одна') $x5.Text

# ======================= N: шаг 25 на подделке ssh =======================
$SH25 = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r7_marker_ids.sh')) -replace "`r`n", "`n"
# в песочнице у 25 убрана строка chcp 65001: она мешает set /p читать ответы из файла (как в тестах r6; в боевом файле она на месте)
Copy-Item -LiteralPath (Join-Path $Kit '_aside\r7_step25\25_metki_nomera.cmd') -Destination (Join-Path $SB '25_metki_nomera.cmd') -Force   # r8: в корне новый 25 (тесты W r8); N-тесты идут на r7-версии (run_r7_metki.ps1 и pi\r7_marker_ids.sh на месте)
$ls = [IO.File]::ReadAllText((Join-Path $SB '25_metki_nomera.cmd')) -split "`r`n"
[IO.File]::WriteAllText((Join-Path $SB '25_metki_nomera.cmd'), (($ls | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
function Pre([string]$det, [string]$state = 'MN_STATE connected=True armed=False mode=POSCTL') { return ("MN_META script r7_marker_ids.sh mode=pre seconds=4 label=pre date=2026-11-13 10:00:00`n" + $state + "`n" + $det + "`nMN_END label=pre msgs=0 with_markers=0 ids=none`nBB_R7MN_DONE rc=0`n") }
$preSleep = Pre 'MN_DETECTOR label=pre publishers=1 nodes=aruco_detect camera_subscription=no msgs=0 with_markers=0 seconds=4'
$preAwake = Pre 'MN_DETECTOR label=pre publishers=1 nodes=aruco_detect camera_subscription=yes msgs=60 with_markers=58 seconds=4'
function Rec([string]$label, [int[]]$ids, [int]$extraEmpty = 0, [int]$claim = -1) {
    $s = "MN_META script r7_marker_ids.sh mode=rec seconds=10 label=$label date=2026-11-13 10:00:10`nMN_STATE connected=True armed=False mode=POSCTL`n"
    $n = 0; $wm = 0; $cnt = @{}
    foreach ($i in $ids) { $n++; $wm++; $cnt[$i] = 1 + [int]$cnt[$i]; $s += ('MN_MSG t=' + ('{0:F3}' -f ($n * 0.08)) + ' n=1 id=' + $i + " c=466.0,399.0;239.0,402.0;237.0,109.0;464.0,104.0`n") }
    for ($k = 0; $k -lt $extraEmpty; $k++) { $n++; $s += ('MN_MSG t=' + ('{0:F3}' -f ($n * 0.08)) + " n=0`n") }
    $idsTxt = (@($cnt.Keys | Sort-Object | ForEach-Object { [string]$_ + ':' + $cnt[$_] }) -join ','); if ($idsTxt -eq '') { $idsTxt = 'none' }
    if ($claim -ge 0) { $n = $claim }
    $s += "MN_DETECTOR label=$label publishers=1 nodes=aruco_detect camera_subscription=yes msgs=$n with_markers=$wm seconds=10`nMN_END label=$label msgs=$n with_markers=$wm ids=$idsTxt`nBB_R7MN_DONE rc=0`n"
    return $s
}
$zeros = @(0) * 100
function Set-AllRec([hashtable]$byLabel) { foreach ($l in 'p00cm', 'p05cm', 'p10cm', 'p15cm') { $t = $byLabel[$l]; if (-not $t) { $t = Rec $l $zeros 3 }; Set-Canned ('mn_' + $l) $t } }
function Sum([string]$out) { $f = @(Get-ChildItem -LiteralPath $out -File -Filter 'metki_nomera_*.txt' | Where-Object { $_.Name -match '^metki_nomera_\d{8}_\d{6}\.txt$' }); if ($f.Count -eq 1) { return [IO.File]::ReadAllText($f[0].FullName) } else { return '' } }
function LastV([string]$t) { $l = @($t -split "`r?`n" | Where-Object { $_.Trim() -ne '' }); if ($l.Count) { return $l[-1] } else { return '' } }
function Keys($r) { return (@($r.Calls | ForEach-Object { if ($_ -match 'key=(\S*)') { $Matches[1] } }) -join ',') }
$c25 = [IO.File]::ReadAllText((Join-Path $Kit '_aside\r7_step25\25_metki_nomera.cmd')); $b25 = [IO.File]::ReadAllBytes((Join-Path $Kit '_aside\r7_step25\25_metki_nomera.cmd')); $l25 = $c25 -split "`r`n"
Check 'N1' '25: UTF-8 без BOM, CRLF; строки 1-2 @echo off и chcp 65001; первая строка «ТОЛЬКО ЧТЕНИЕ:», про моторы, без < > | & ^ % и без скобок' ($b25[0] -ne 0xEF -and ([regex]::Matches($c25, "`r`n")).Count -eq ([regex]::Matches($c25, "`n")).Count -and $l25[0] -ceq '@echo off' -and $l25[1] -ceq 'chcp 65001 >nul' -and $l25[2].StartsWith('echo ТОЛЬКО ЧТЕНИЕ: ') -and $l25[2] -match 'моторы' -and $l25[2] -notmatch '[<>|&^%()]' -and $l25[2] -notmatch 'МЕНЯЕТ ДРОН') $l25[2]
$psLines = @($l25 | Where-Object { $_.StartsWith('powershell -NoProfile -ExecutionPolicy Bypass -File') })
Check 'N2' '25: проверка имени ПК и файлов до запуска; нет ssh, scp, sudo; один set /p; каждый вызов run_r7_metki.ps1 со вводом из nul (4 фазы)' ($c25 -match 'if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E"' -and $c25 -match 'for %%F in \(run_r7_metki\.ps1 lib\\bb_common\.ps1 lib\\bb_r6\.ps1 pi\\r7_marker_ids\.sh\)' -and $c25 -notmatch '(?i)\bssh\b|\bscp\b|\bsudo\b' -and ([regex]::Matches($c25, 'set /p')).Count -eq 1 -and $psLines.Count -eq 4 -and @($psLines | Where-Object { $_.EndsWith(' < nul') }).Count -eq 4) ''
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preSleep
$r = Run-Cmd '25_metki_nomera.cmd' '' $o 'OTHER-PC'
Check 'N3' '25: чужой ПК - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$o = New-Out; Reset-Fake 'wrong_host'; Set-Canned 'mn_pre' $preSleep
$r = Run-Cmd '25_metki_nomera.cmd' '' $o
Check 'N4' '25: на связи не bumblebee-20ec - код 4, скрипт на Pi не послан' ($r.Code -eq 4 -and $r.Calls.Count -eq 1 -and $r.Calls[0] -match 'HOST_OK' -and $r.Sent.Count -eq 0) ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preSleep; Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n10`r`n15`r`n" $o
$s = Sum $o
Check 'N5' '25: детектор спит (msgs=0 за 4 с) - код 6 НЕ ПРОВЕРЕНО, точки не записывались (2 вызова: имя дрона и проверка), вердикт NOT_CHECKED' ($r.Code -eq 6 -and $r.Calls.Count -eq 2 -and $r.Calls[1] -match 'key=mn_pre' -and (LastV $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'детектор меток за 4 с не выдал ни одного сообщения' -and $s -match 'подписка на кадры камеры: no' -and $r.Console -match 'НЕ ПРОВЕРЕНО' -and $r.Console -notmatch 'Точка 1 из 4') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Check 'N6' '25: на Pi ушёл ровно pi\r7_marker_ids.sh (тот же текст, LF) с аргументами «pre 4 pre»; первая строка сводки - ТОЛЬКО ЧТЕНИЕ' ($r.Sent.Count -eq 1 -and $r.Sent[0] -ceq $SH25 -and $r.Calls[1] -match '\| base64 -d\)\\?" _ pre 4 pre' -and ($s -split "`r?`n")[0].TrimStart([char]0xFEFF).StartsWith('# ТОЛЬКО ЧТЕНИЕ: шаг 25')) $r.J
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' "MN_STATE connected=True armed=True mode=POSCTL`nMN_REFUSED armed (дрон взведён: шаг только для невзведённого дрона)`nBB_R7MN_DONE rc=3`n" 3
$r = Run-Cmd '25_metki_nomera.cmd' '' $o; $s = Sum $o
Check 'N7' '25: дрон взведён - код 3 НЕ НАЧАТО, вердикт NOT_STARTED, точки не записывались' ($r.Code -eq 3 -and $r.Calls.Count -eq 2 -and (LastV $s) -ceq '# VERDICT NOT_STARTED' -and $s -match 'НЕ НАЧАТО' -and $r.Console -match 'НЕ НАЧАТО') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n10`r`n15`r`n" $o; $s = Sum $o
Check 'N8' '25: детектор работает, 4 точки только с номером 0 - код 0, ONLY_ID0; перед каждой точкой снова проверка имени дрона' ($r.Code -eq 0 -and (Keys $r) -ceq ',mn_pre,,mn_p00cm,,mn_p05cm,,mn_p10cm,,mn_p15cm' -and (LastV $s) -ceq '# VERDICT ONLY_ID0' -and ([regex]::Matches($s, '(?m)^ТОЧКА \d+ см: сообщений 103, кадров с метками 100, номера 0:100\s*$')).Count -eq 4 -and $r.Console -match 'Готово: во всех 4 точках только номер 0' -and $r.Console -match 'Точка 4 из 4: сдвиг 15 см') ((Keys $r) + ' code=' + $r.Code)
Check 'N9' '25: аргументы на Pi «rec 10 p00cm» ... «rec 10 p15cm»; сырые ответы каждой точки - в out\metki_nomera_*_pNNcm.txt' ($r.Calls[3] -match '_ rec 10 p00cm' -and $r.Calls[9] -match '_ rec 10 p15cm' -and @(Get-ChildItem -LiteralPath $o -File -Filter 'metki_nomera_*_p*cm.txt' | Where-Object { $_.Name -notmatch 'err' }).Count -eq 4) $r.J
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{ 'p10cm' = (Rec 'p10cm' (@(0) * 40 + @(38) * 7 + @(0) * 40) 2) }
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n10`r`n15`r`n" $o; $s = Sum $o
Check 'N10' '25: в точке 10 см номер 38 - код 5, FALSE_ID, строка точки «ЛОЖНЫЙ НОМЕР: номер 38 — 7 раз», в окне ЛОЖНЫЙ НОМЕР' ($r.Code -eq 5 -and (LastV $s) -ceq '# VERDICT FALSE_ID' -and $s -match 'ТОЧКА 10 см: сообщений 89, кадров с метками 87, номера 0:80,38:7 — ЛОЖНЫЙ НОМЕР: номер 38 — 7 раз' -and $r.Console -match 'ЛОЖНЫЙ НОМЕР') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`nx`r`n" $o; $s = Sum $o
Check 'N11' '25: набрано не то число перед точкой 5 см - запись остановлена: код 6, NOT_CHECKED, записана только точка 0 см' ($r.Code -eq 6 -and (Keys $r) -ceq ',mn_pre,,mn_p00cm' -and (LastV $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'ОСТАНОВЛЕНО владельцем перед точкой 5 см') ((Keys $r) + ' code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{ 'p05cm' = (Rec 'p05cm' (@(9) * 3) 0) }
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n" $o; $s = Sum $o
Check 'N12' '25: ложный номер 9 в 5 см, потом остановка (ввод кончился) - код 5 FALSE_ID (ложный номер не теряется)' ($r.Code -eq 5 -and (LastV $s) -ceq '# VERDICT FALSE_ID' -and $s -match 'номер 9 — 3 раз' -and $s -match 'ОСТАНОВЛЕНО владельцем перед точкой 10 см') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{ 'p15cm' = (Rec 'p15cm' @() 0) }
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n10`r`n15`r`n" $o; $s = Sum $o
Check 'N13' '25: в точке 15 см детектор не выдал ни одного сообщения - код 6 NOT_CHECKED (не «только 0»)' ($r.Code -eq 6 -and (LastV $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'ТОЧКА 15 см: сообщений 0, кадров с метками 0, номера none — НЕТ ДАННЫХ') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{ 'p05cm' = (Rec 'p05cm' @() 30) }
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n10`r`n15`r`n" $o; $s = Sum $o
# r7 13.11 ~05:40 (строже прежнего): точка без единого прочитанного номера 0 не проверена - итог НЕ ПРОВЕРЕНО (6), а не «только 0» (0)
Check 'N14' '25: в точке 5 см кадры есть, а метка 0 ни разу не прочитана - код 6 NOT_CHECKED «метка 0 не прочитана ни разу в точках: 5 см» (не «только 0»)' ($r.Code -eq 6 -and (LastV $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'метка 0 не прочитана ни разу в точках: 5 см' -and $r.Console -notmatch 'Готово: во всех 4 точках') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preAwake; Set-AllRec @{ 'p00cm' = (Rec 'p00cm' $zeros 0 50) }
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`n5`r`n" $o
Check 'N15' '25: в ответе Pi строк MN_MSG не столько, сколько msgs в MN_END - код 4, ERROR (не «только 0»), дальше не пошли' ($r.Code -eq 4 -and (LastV (Sum $o)) -ceq '# VERDICT ERROR' -and (Keys $r) -ceq ',mn_pre,,mn_p00cm') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' ($preAwake -replace 'BB_R7MN_DONE rc=0\n', '')
$r = Run-Cmd '25_metki_nomera.cmd' '' $o
Check 'N16' '25: ответ проверки без BB_R7MN_DONE - код 4, сырой ответ переименован в .FAILED.txt' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $o -File -Filter '*_pre.FAILED.txt').Count -eq 1) ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' "MN_ERROR markers_import_failed ModuleNotFoundError('aruco_pose')`nBB_R7MN_DONE rc=4`n" 4
$r = Run-Cmd '25_metki_nomera.cmd' '' $o
Check 'N17' '25: на Pi нет aruco_pose (MN_ERROR) - код 4, ERROR' ($r.Code -eq 4 -and (LastV (Sum $o)) -ceq '# VERDICT ERROR') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'mn_pre' $preSleep
[IO.File]::WriteAllText((Join-Path $o 'metki_nomera_20261113_100000_p10cm.err.txt'), 'x')
$r = Run-Ps 'run_r7_metki.ps1' '-Phase pre -Stamp 20261113_100000' $o
Check 'N18' '25: файл ответа этой метки времени уже есть - код 4, «не перезаписываю», к дрону не обращались' ($r.Code -eq 4 -and $r.Console -match 'не перезаписываю' -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-Ps 'run_r7_metki.ps1' '-Phase pre -Stamp 2026-11-13' $o
Check 'N19' '25: метка -Stamp не ГГГГММДД_ЧЧММСС - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$rp = [IO.File]::ReadAllText((Join-Path $Kit 'run_r7_metki.ps1'))
Check 'N20' 'run_r7_metki.ps1: первая строка ТОЛЬКО ЧТЕНИЕ; BB-AssertPc и отказ перезаписи до обращения к дрону; BB-TestDrone до скрипта Pi; scp нет' ($rp.Split("`n")[0] -match 'ТОЛЬКО ЧТЕНИЕ' -and $rp.IndexOf('BB-AssertPc') -lt $rp.IndexOf('BB-TestDrone $ssh') -and $rp.IndexOf('BB-NewOutFile $outDir $n') -lt $rp.IndexOf('BB-TestDrone $ssh') -and $rp.IndexOf('BB-TestDrone $ssh') -lt $rp.IndexOf('R6-Remote') -and $rp -notmatch '(?i)\bscp\b') ''
$o = New-Out; Reset-Fake; Set-AllRec @{}
$r = Run-Ps 'run_r7_metki.ps1' '-Phase rec -Stamp 20261113_100001 -Cm 0' $o
Check 'N21' '25: фаза rec без удачной проверки (нет сводки) - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$sum2 = Join-Path $o 'metki_nomera_20261113_100002.txt'
[IO.File]::WriteAllText($sum2, ("# x`r`nПРОВЕРКА connected=True armed=False mode=POSCTL | label=pre publishers=1 nodes=aruco_detect camera_subscription=yes msgs=60 with_markers=58 seconds=4`r`n"), $utf8)
$r = Run-Ps 'run_r7_metki.ps1' '-Phase rec -Stamp 20261113_100002 -Cm 5' $o
Check 'N22' '25: точка 5 см раньше точки 0 см - код 4 (порядок 0, 5, 10, 15), к дрону не обращались' ($r.Code -eq 4 -and $r.Console -match 'по порядку' -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-Ps 'run_r7_metki.ps1' '-Phase rec -Stamp 20261113_100002 -Cm 7' $o
Check 'N23' '25: сдвиг не 0/5/10/15 - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
[IO.File]::AppendAllText($sum2, "ТОЧКА 0 см: сообщений 10, кадров с метками 10, номера 0:10`r`n", $utf8n)
$r = Run-Ps 'run_r7_metki.ps1' '-Phase final -Stamp 20261113_100002' $o
Check 'N24' '25: итог при одной записанной точке из 4 - код 4, ERROR (не «только 0»)' ($r.Code -eq 4 -and (LastV ([IO.File]::ReadAllText($sum2))) -ceq '# VERDICT ERROR') ('code=' + $r.Code)
$r = Run-Ps 'run_r7_metki.ps1' '-Phase stop -Stamp 20261113_100002 -Cm 5' $o
Check 'N25' '25: после итога сводка закрыта - фаза stop ничего не дописывает, код 4' ($r.Code -eq 4 -and $r.Console -match 'уже есть итог') ('code=' + $r.Code)
# ======================= S: статические проверки новых файлов =======================
$newCode = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | Where-Object { $_.FullName -notmatch '\\tests\\run_r[0-9a-z_]*_\d{8}' -and $_.FullName -notmatch '\\tests\\run_[a-z]_\d{8}' -and $_.Extension -in '.sh', '.ps1', '.cmd', '.py', '.cs' } | Where-Object { -not $r6.ContainsKey(((Rel $_.FullName) -replace '\\', '/')) })
$enc = @()
foreach ($f in $newCode) {
    $b = [IO.File]::ReadAllBytes($f.FullName); $x = [IO.File]::ReadAllText($f.FullName)
    if ($f.Extension -eq '.ps1' -and -not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)) { $enc += ((Rel $f.FullName) + ': .ps1 без BOM') }
    if ($f.Extension -eq '.sh' -and $x.Contains("`r")) { $enc += ((Rel $f.FullName) + ': .sh не LF') }
    if ($f.Extension -eq '.cmd' -and ($b[0] -eq 0xEF -or ([regex]::Matches($x, "`r`n")).Count -ne ([regex]::Matches($x, "`n")).Count)) { $enc += ((Rel $f.FullName) + ': .cmd не CRLF без BOM') }
}
Check 'S1' ('кодировки новых файлов (' + $newCode.Count + '): .ps1 с BOM, .sh только LF, .cmd CRLF без BOM (как требуют тесты r5 S4 и r6 S1)') ($enc.Count -eq 0) ($enc -join '; ')
$mine = @($newCode | Where-Object { $_.FullName -notmatch '\\image_r2j\\payload\\' -and $_.FullName -notmatch '\\tests\\' -and $_.FullName -notmatch '\\params_check\\' })   # r8: params_check\ = принятая сверка r4 (адрес дрона в run_params_check.ps1 по замыслу) + v3
$pg = @(); $sec = @()
foreach ($f in $mine) {
    $i = 0
    foreach ($l in [IO.File]::ReadAllLines($f.FullName)) { $i++; $t = $l.Trim(); if ($t.StartsWith('#') -or $t.StartsWith('//') -or $t -match '^(?i)(rem|echo|@echo) ') { continue }; if ($t -match '\bpgrep\b|\bpkill\b|killall') { $pg += ((Rel $f.FullName) + ':' + $i) } }
    $t = [IO.File]::ReadAllText($f.FullName)
    if ($t -match '10\.255\.254\.26|lb@10\.') { $sec += ((Rel $f.FullName) + ': адрес дрона') }
    if ($t -match '(?i)(password|passwd|psk)\s*=\s*\S{3,}') { $sec += ((Rel $f.FullName) + ': пароль?') }
    if ($t -match '-----BEGIN [A-Z ]*PRIVATE KEY-----' -or $t -match 'ssh-(rsa|ed25519) AAAA') { $sec += ((Rel $f.FullName) + ': ключ') }
    if ($t -match '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}') { $sec += ((Rel $f.FullName) + ': почта?') }
}
Check 'S2' ('мои новые файлы (' + $mine.Count + ', кроме тестов и payload): нет pgrep, pkill, killall вне комментариев (правило 13)') ($pg.Count -eq 0) ($pg -join ', ')
Check 'S3' 'мои новые файлы: нет адреса дрона, паролей, ключей, адресов почты (адрес дрона - только в lib\bb_common.ps1 r6)' ($sec.Count -eq 0) ($sec -join '; ')
$payCode = @($newCode | Where-Object { $_.FullName -match '\\image_r2j\\payload\\' })
$pf = @(); foreach ($f in $payCode) { $t = [IO.File]::ReadAllText($f.FullName); if ($t -match '\b(pgrep|pkill)\s+-[A-Za-z]*f' -or $t -match '10\.255\.254\.26') { $pf += (Rel $f.FullName) } }
Check 'S4' ('payload (' + $payCode.Count + ' файлов кода из образа): нет pgrep -f / pkill -f и адреса дрона (их ловят и тесты r6 S7b/S8)') ($pf.Count -eq 0) ($pf -join ', ')

$env:PATH = $oldPath
Note ('ИТОГ r7: PASS ' + $script:pass + ', FAIL ' + $script:fail)
if ($script:fail -gt 0) { exit 1 }
exit 0
