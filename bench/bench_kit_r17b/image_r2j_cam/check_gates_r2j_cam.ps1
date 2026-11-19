# check_gates_r2j_cam.ps1 (Claude, 12.11.2026, набор r6) - условия установки (и отката) ВАРИАНТА образа «r2j + камера полных строк». ТОЛЬКО на ПК, сети нет, дрон не трогает.
# Основа - check_gates_camera.ps1 набора r5 (гейт варианта не слабее основного, решение чата 1 10.11 19:19); все его условия сохранены, плюс свои:
# -Mode install:
#  1) gates\S2_S3_PASSED.txt В ЭТОЙ ПАПКЕ: S2=PASS, S3=PASS, ДАТА, ДОКАЗАТЕЛЬСТВО, СОЗДАЛ=чат 1, ОБРАЗ_MANIFEST_SHA256 = sha256 ЭТОГО манифеста (флаг основного r2j не годится);
#  2) свежая (не старше 30 мин) сверка настроек «СОВПАДАЕТ» полностью из таблицы MAVROS, число = числу настроек компонента 1 в основе, без -AllowStreamFallback, COM_OBL_RC_ACT = 4;
#  3) gates\R2J_CAM_APPROVED.txt от чата 1 после слов владельца: ПРАВКА=05c_r2j_cam, ВЛАДЕЛЕЦ_СКАЗАЛ=да, ДАТА, СЛОВА_ВЛАДЕЛЬЦА, СОЗДАЛ=чат 1,
#     CAMERA_SHA256=dabd5076..., LAUNCH_SHA256=5f0954d8..., MANIFEST_SHA256=<sha256 этого манифеста>;
#  4) ..\image_r2j\image_target.conf: DEST_ROOT=/home/lb (пути варианта от HOME) и BACKUP_ROOT заполнен; есть ..\image_r2j\image_install.sh;
#  5) манифест ровно из 4 строк VARIANT_FILES.tsv (sha варианта; у camera_fix.py в install режим 755), payload сходится по sha256, списки 09c/15c согласованы.
# -Mode rollback: gates\OTKAT_R2J_CAM_APPROVED.txt (ПРАВКА=06c_otkat_r2j_cam, ВЛАДЕЛЕЦ_СКАЗАЛ=да, ДАТА, СЛОВА_ВЛАДЕЛЬЦА, СОЗДАЛ=чат 1); image_target.conf как в 4; есть ..\image_r2j\image_rollback.sh;
#     S2/S3 и сверка настроек для отката не нужны (откат возвращает прежнее состояние r2j, как 06 в r5).
# Код выхода 0 = условия выполнены; 1 = нет (причины выводятся). Ничего не создаёт.
param([string]$Kit = '', [string]$OutDir = '', [int]$MaxAgeMin = 30, [ValidateSet('install', 'rollback')][string]$Mode = 'install')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Kit) { $Kit = $here }
$Kit = [IO.Path]::GetFullPath($Kit).TrimEnd('\')
$root = Split-Path -Parent $Kit
. (Join-Path $root 'lib\bb_r6.ps1')
if (-not $OutDir) { if ($env:BB_KIT_OUT) { $OutDir = $env:BB_KIT_OUT } else { $OutDir = Join-Path $root 'out' } }
$CAM = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
$LAUNCH = '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294'
$bad = New-Object Collections.Generic.List[string]
function No([string]$s) { $script:bad.Add($s) }
$man = Join-Path $Kit 'image_manifest.final.tsv'
$manSha = $null
# 4. цель установки (общая с образом r2j)
$conf = Join-Path $root 'image_r2j\image_target.conf'
if (-not (Test-Path -LiteralPath $conf)) { No 'Нет ..\image_r2j\image_target.conf.' }
else {
    foreach ($k in 'DEST_ROOT', 'BACKUP_ROOT') {
        $line = Get-Content -LiteralPath $conf -Encoding UTF8 | Where-Object { $_ -match ('^' + $k + '=') } | Select-Object -First 1
        $v = ''; if ($line) { $v = ($line -replace ('^' + $k + '='), '').Trim() }
        if ($v -eq '' -or $v -match 'TBD') { No ('В ..\image_r2j\image_target.conf не заполнено ' + $k + ' (TBD).') }
        elseif ($k -eq 'DEST_ROOT' -and $v -cne '/home/lb') { No ('DEST_ROOT = ' + $v + ', а пути варианта рассчитаны от /home/lb (HOME пользователя lb).') }
        elseif ($k -eq 'BACKUP_ROOT' -and $v -notmatch '^/[A-Za-z0-9_./-]+$') { No ('BACKUP_ROOT не абсолютный путь из безопасных знаков: ' + $v) }
    }
}
if ($Mode -eq 'rollback') {
    if (-not (Test-Path -LiteralPath (Join-Path $root 'image_r2j\image_rollback.sh'))) { No 'Нет ..\image_r2j\image_rollback.sh.' }
    $p = R6-Permission (Join-Path $Kit 'gates\OTKAT_R2J_CAM_APPROVED.txt') '06c_otkat_r2j_cam'
    if (-not $p.Ok) { No $p.Why }
    if ($bad.Count -eq 0) { Write-Host 'Условия отката варианта выполнены (разрешение чата 1, цель установки, image_rollback.sh).'; exit 0 }
    Write-Host ''
    Write-Host '  СТОП: откат варианта не разрешён. Не выполнены условия:  ' -ForegroundColor White -BackgroundColor Red
    foreach ($b in $bad) { Write-Host (' - ' + $b) }
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $root 'image_r2j\image_install.sh'))) { No 'Нет ..\image_r2j\image_install.sh.' }
# 5. манифест, payload, списки
$vfp = Join-Path $Kit 'VARIANT_FILES.tsv'
$vrows = @(); if (Test-Path -LiteralPath $vfp) { $vrows = @(Get-Content -LiteralPath $vfp -Encoding UTF8 | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') }) }
if ($vrows.Count -ne 4) { No 'В VARIANT_FILES.tsv не 4 места.' }
if (-not (Test-Path -LiteralPath $man)) { No 'Нет image_manifest.final.tsv варианта.' }
else {
    $manSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $man).Hash.ToLower()
    $rows = @(Get-Content -LiteralPath $man -Encoding UTF8 | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') })
    if ($rows.Count -ne 4) { No ('В манифесте варианта должно быть 4 строки, а их ' + $rows.Count) }
    $seen = @{}
    foreach ($r in $rows) {
        $f = $r.Split("`t")
        if ($f.Count -lt 2 -or $f.Count -gt 3 -or $f[1] -cnotmatch '^[0-9a-f]{64}$') { No ('Строка манифеста не path<TAB>sha256[<TAB>режим]: ' + $r); continue }
        if ($f[0] -match '(^|[\\/])\.\.?([\\/]|$)' -or $f[0].StartsWith('/') -or $f[0] -match '[\\/]{2}' -or $f[0] -match 'TBD') { No ('Небезопасный путь в манифесте: ' + $f[0]); continue }
        if ($f[0] -match '(^|[\\/])fcu_detect\.py$') { No 'В манифесте варианта fcu_detect.py: образом не ставится (решение чата 1, 22:00).'; continue }
        $vr = @($vrows | Where-Object { $_.Split("`t")[0] -ceq $f[0] })
        if ($vr.Count -ne 1) { No ('Путь манифеста не из VARIANT_FILES.tsv: ' + $f[0]); continue }
        if ($f[1] -cne $vr[0].Split("`t")[2]) { No ('sha256 в манифесте для ' + $f[0] + ' не равен sha варианта из VARIANT_FILES.tsv') }
        if ($f[1] -cne $CAM -and $f[1] -cne $LAUNCH) { No ('В манифесте варианта чужой файл (не dabd5076 и не 5f0954d8): ' + $f[0]) }
        if ($f[0] -like '*/camera_fix.py' -and $f[1] -cne $CAM) { No ('camera_fix.py в манифесте не dabd5076: ' + $f[0]) }
        if ($f[0] -like '*/bumblebee.launch.py' -and $f[1] -cne $LAUNCH) { No ('bumblebee.launch.py в манифесте не 5f0954d8: ' + $f[0]) }
        if ($f[0] -ceq 'bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py' -and ($f.Count -ne 3 -or $f[2] -cne '755')) { No 'У camera_fix.py в install оверлея должен стоять режим 755 (исполняемый узел).' }
        if ($seen.ContainsKey($f[0])) { No ('Путь дважды в манифесте: ' + $f[0]) }; $seen[$f[0]] = 1
        $pp = Join-Path (Join-Path $Kit 'payload') ($f[0] -replace '/', '\')
        if (-not (Test-Path -LiteralPath $pp)) { No ('В payload варианта нет файла ' + $f[0]) }
        elseif ((Get-FileHash -Algorithm SHA256 -LiteralPath $pp).Hash.ToLower() -cne $f[1]) { No ('SHA256 файла ' + $f[0] + ' в payload не сходится с манифестом.') }
    }
    foreach ($fd in @(Get-ChildItem -LiteralPath (Join-Path $Kit 'payload') -Recurse -File -ErrorAction SilentlyContinue)) {
        $rel = $fd.FullName.Substring((Join-Path $Kit 'payload').Length + 1) -replace '\\', '/'
        if (-not $seen.ContainsKey($rel)) { No ('В payload лишний файл (его нет в манифесте): ' + $rel) }
    }
}
foreach ($pair in @(@('INSTALL_SHA256_r2jcam.txt', ($CAM + '  camera_fix.py')), @('RUNTIME_PY_r2jcam.tsv', ($LAUNCH + "`tLAUNCH`tlaunch/bumblebee.launch.py")))) {
    $lp = Join-Path $Kit $pair[0]
    if (-not (Test-Path -LiteralPath $lp)) { No ('Нет списка ' + $pair[0] + ' (для 09c и 15c).') }
    elseif (-not (Get-Content -LiteralPath $lp -Encoding UTF8 | Where-Object { $_ -ceq $pair[1] })) { No ('В ' + $pair[0] + ' нет строки варианта.') }
}
# 1. S2/S3 для этого манифеста
$g = Join-Path $Kit 'gates\S2_S3_PASSED.txt'
if (-not (Test-Path -LiteralPath $g)) { No 'Нет gates\S2_S3_PASSED.txt варианта: S2 и S3 в SITL с r2j+камера (r2jf) ещё не подтверждены чатом 1 (правило 14). Флаг основного образа не годится.' }
else {
    $gt = Get-Content -LiteralPath $g -Encoding UTF8
    foreach ($k in 'S2=PASS', 'S3=PASS') { if (-not ($gt | Where-Object { $_.Trim() -eq $k })) { No ('В S2_S3_PASSED.txt варианта нет строки ' + $k) } }
    foreach ($k in 'ДАТА=', 'ДОКАЗАТЕЛЬСТВО=', 'СОЗДАЛ=чат 1') { if (-not ($gt | Where-Object { $_.Trim().StartsWith($k) })) { No ('В S2_S3_PASSED.txt варианта нет строки ' + $k + '...') } }
    $bindLine = $gt | Where-Object { $_.Trim().StartsWith('ОБРАЗ_MANIFEST_SHA256=') } | Select-Object -First 1
    if (-not $bindLine) { No 'В S2_S3_PASSED.txt варианта нет строки ОБРАЗ_MANIFEST_SHA256=<sha256 манифеста варианта>.' }
    else {
        $bound = ($bindLine.Trim() -replace '^ОБРАЗ_MANIFEST_SHA256=', '').Trim()
        if ($bound -cnotmatch '^[0-9a-f]{64}$') { No 'ОБРАЗ_MANIFEST_SHA256 в S2_S3_PASSED.txt варианта должен быть 64 символа 0-9a-f.' }
        elseif ($manSha -and $bound -cne $manSha) { No ('Флаг S2/S3 выдан для другого манифеста: sha256 манифеста варианта (' + $manSha + ') не равен ОБРАЗ_MANIFEST_SHA256.') }
    }
}
# 2. свежая сверка настроек (как в основном гейте)
$rep = $null
if (Test-Path -LiteralPath $OutDir) { $rep = Get-ChildItem -LiteralPath $OutDir -Filter 'params_*_report.txt' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1 }
if (-not $rep) { No 'Нет сверки настроек (out\params_*_report.txt). Сначала 01_snimok_do.cmd этого набора.' }
else {
    $age = ((Get-Date) - $rep.LastWriteTime).TotalMinutes
    if ($age -gt $MaxAgeMin) { No ('Последняя сверка настроек старая: ' + [int]$age + ' мин, нужна не старше ' + $MaxAgeMin + '. Запустите 01_snimok_do.cmd этого набора.') }
    $first = (Get-Content -LiteralPath $rep.FullName -Encoding UTF8 -TotalCount 1)
    if ($first -notmatch '^=== СОВПАДАЕТ: прочитано (\d+) из \1, отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)') { No ('Последняя сверка не «СОВПАДАЕТ полностью из таблицы MAVROS»: ' + $first) }
    $bl = Join-Path (Join-Path $root 'params_check') 'baseline_20261104_1145.params'
    if (-not (Test-Path -LiteralPath $bl)) { No ('Нет основы настроек рядом с набором (' + $bl + ').') }
    elseif ($first -match '^=== СОВПАДАЕТ: прочитано (\d+) из') {
        $readN = [int]$Matches[1]
        $blN = @(Get-Content -LiteralPath $bl -Encoding UTF8 | Where-Object { $_ -match "^1\t1\t" }).Count
        if ($readN -ne $blN) { No ('Сверка прочитала ' + $readN + ' настроек, а в основе компонента 1 их ' + $blN) }
    }
    if ([IO.File]::ReadAllText($rep.FullName) -match 'AllowStreamFallback') { No 'Отчёт сверки сделан с ключом -AllowStreamFallback: для гейтов не годится.' }
    $pf = $rep.FullName -replace '_report\.txt$', '.params'
    if (-not (Test-Path -LiteralPath $pf)) { No ('Нет файла настроек рядом с отчётом: ' + $pf) }
    else {
        $row = Get-Content -LiteralPath $pf -Encoding UTF8 | Where-Object { $_ -match "^1\t1\tCOM_OBL_RC_ACT\t" } | Select-Object -First 1
        if (-not $row) { No 'В прочитанных настройках нет COM_OBL_RC_ACT.' }
        elseif ($row -notmatch "^1\t1\tCOM_OBL_RC_ACT\t4\t") { No ('COM_OBL_RC_ACT на дроне не 4 (правило 14): ' + $row.Trim()) }
    }
}
# 3. разрешение владельца через чат 1
$extra = @(('CAMERA_SHA256=' + $CAM), ('LAUNCH_SHA256=' + $LAUNCH))
if ($manSha) { $extra += ('MANIFEST_SHA256=' + $manSha) }
$p = R6-Permission (Join-Path $Kit 'gates\R2J_CAM_APPROVED.txt') '05c_r2j_cam' $extra
if (-not $p.Ok) { No $p.Why }
if ($bad.Count -eq 0) { Write-Host 'Условия установки варианта r2j+камера выполнены (S2/S3 для этого манифеста, свежая сверка, COM_OBL_RC_ACT=4, разрешение владельца, цель, манифест, payload, списки).'; exit 0 }
Write-Host ''
Write-Host '  СТОП: установка варианта r2j+камера не разрешена. Не выполнены условия:  ' -ForegroundColor White -BackgroundColor Red
foreach ($b in $bad) { Write-Host (' - ' + $b) }
exit 1
