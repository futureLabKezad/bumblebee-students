# check_gates.ps1 (Claude, 09.11.2026) - проверка условий установки образа. ТОЛЬКО на ПК, сети нет, дрон не трогает.
# Условия (правило 14 /work/CLAUDE.md и порядок набора): S2/S3 пройдены (файл чата 1, привязан к sha256 манифеста образа), свежая сверка настроек
# совпала и на дроне COM_OBL_RC_ACT=4, цель установки заполнена, манифест без TBD, payload сходится с SHA256.
# Код выхода 0 = все условия выполнены; 1 = не выполнены (причины выводятся).
param(
    [string]$Kit = '',
    [string]$OutDir = '',
    [int]$MaxAgeMin = 30,
    [string]$ReportFile = ''
)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Kit) { $Kit = $here }
$Kit = [IO.Path]::GetFullPath($Kit).TrimEnd('\')   # r4 (Н-4): «-Kit папка\.» из .cmd давало неверный родитель
if (-not $OutDir) { if ($env:BB_KIT_OUT) { $OutDir = $env:BB_KIT_OUT } else { $OutDir = Join-Path (Split-Path -Parent $Kit) 'out' } }
$bad = New-Object Collections.Generic.List[string]
function No([string]$s) { $script:bad.Add($s) }

$boundSha = $null
# 1. S2/S3
$g = Join-Path $Kit 'gates\S2_S3_PASSED.txt'
if (-not (Test-Path -LiteralPath $g)) { No 'Нет gates\S2_S3_PASSED.txt: S2 и S3 в SITL ещё не подтверждены чатом 1 (правило 14).' }
else {
    $gt = Get-Content -LiteralPath $g -Encoding UTF8
    foreach ($k in 'S2=PASS', 'S3=PASS') { if (-not ($gt | Where-Object { $_.Trim() -eq $k })) { No ('В S2_S3_PASSED.txt нет строки ' + $k) } }
    foreach ($k in 'ДАТА=', 'ДОКАЗАТЕЛЬСТВО=', 'СОЗДАЛ=чат 1') { if (-not ($gt | Where-Object { $_.Trim().StartsWith($k) })) { No ('В S2_S3_PASSED.txt нет строки ' + $k + '...') } }
    # r2j (поправка по проверке 10.11): флаг привязан к образу, то есть к sha256 файла image_manifest.final.tsv (а он содержит sha256 каждого файла payload)
    $bindLine = $gt | Where-Object { $_.Trim().StartsWith('ОБРАЗ_MANIFEST_SHA256=') } | Select-Object -First 1
    if (-not $bindLine) { No 'В S2_S3_PASSED.txt нет строки ОБРАЗ_MANIFEST_SHA256=<sha256 файла image_manifest.final.tsv>: флаг S2/S3 должен быть выдан для этого образа.' }
    else {
        $boundSha = ($bindLine.Trim() -replace '^ОБРАЗ_MANIFEST_SHA256=', '').Trim()
        if ($boundSha -cnotmatch '^[0-9a-f]{64}$') { No 'ОБРАЗ_MANIFEST_SHA256 в S2_S3_PASSED.txt должен быть 64 символа 0-9a-f.'; $boundSha = $null }
    }
}

# 2. свежая сверка настроек
$rep = $null
if (Test-Path -LiteralPath $OutDir) {
    $rep = Get-ChildItem -LiteralPath $OutDir -Filter 'params_*_report.txt' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
}
if (-not $rep) { No 'Нет сверки настроек (out\params_*_report.txt). Сначала 01_snimok_do.cmd этого набора.' }
else {
    $age = ((Get-Date) - $rep.LastWriteTime).TotalMinutes
    if ($age -gt $MaxAgeMin) { No ('Последняя сверка настроек старая: ' + [int]$age + ' мин, нужна не старше ' + $MaxAgeMin + '. Запустите 01_snimok_do.cmd этого набора.') }
    $first = (Get-Content -LiteralPath $rep.FullName -Encoding UTF8 -TotalCount 1)
    # A-6 (r2): совпадение должно быть полным и только из таблицы MAVROS (из запасного потока 0), без ключа -AllowStreamFallback
    if ($first -notmatch '^=== СОВПАДАЕТ: прочитано (\d+) из \1, отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)') { No ('Последняя сверка не «СОВПАДАЕТ полностью из таблицы MAVROS»: ' + $first) }
    # r3 (Ж-8): число прочитанных должно равняться числу настроек компонента 1 в основе набора
    $bl = Join-Path (Join-Path (Split-Path -Parent $Kit) 'params_check') 'baseline_20261104_1145.params'
    if (-not (Test-Path -LiteralPath $bl)) { No ('Нет основы настроек рядом с набором (' + $bl + '): число прочитанных настроек не с чем сверить.') }
    elseif ($first -match '^=== СОВПАДАЕТ: прочитано (\d+) из') {
        $readN = [int]$Matches[1]
        $blN = @(Get-Content -LiteralPath $bl -Encoding UTF8 | Where-Object { $_ -match "^1\t1\t" }).Count
        if ($readN -ne $blN) { No ('Сверка прочитала ' + $readN + ' настроек, а в основе компонента 1 их ' + $blN) }
    }
    $repText = [IO.File]::ReadAllText($rep.FullName)
    if ($repText -match 'AllowStreamFallback') { No 'Отчёт сверки сделан с ключом -AllowStreamFallback: для гейтов не годится. Повторить 01_snimok_do.cmd (сверка без ключа).' }
    $pf = $rep.FullName -replace '_report\.txt$', '.params'
    if (-not (Test-Path -LiteralPath $pf)) { No ('Нет файла настроек рядом с отчётом: ' + $pf) }
    else {
        $row = Get-Content -LiteralPath $pf -Encoding UTF8 | Where-Object { $_ -match "^1\t1\tCOM_OBL_RC_ACT\t" } | Select-Object -First 1
        if (-not $row) { No 'В прочитанных настройках нет COM_OBL_RC_ACT.' }
        elseif ($row -notmatch "^1\t1\tCOM_OBL_RC_ACT\t4\t") { No ('COM_OBL_RC_ACT на дроне не 4 (правило 14): ' + $row.Trim()) }
    }
}

# 3. цель установки
$conf = Join-Path $Kit 'image_target.conf'
if (-not (Test-Path -LiteralPath $conf)) { No 'Нет image_target.conf.' }
else {
    foreach ($k in 'DEST_ROOT', 'BACKUP_ROOT') {
        $line = Get-Content -LiteralPath $conf -Encoding UTF8 | Where-Object { $_ -match ('^' + $k + '=') } | Select-Object -First 1
        $v = ''; if ($line) { $v = ($line -replace ('^' + $k + '='), '').Trim() }
        if ($v -eq '' -or $v -match 'TBD') { No ('В image_target.conf не заполнено ' + $k + ' (TBD).') }
    }
}

# 4. манифест и payload
$man = Join-Path $Kit 'image_manifest.final.tsv'
if (-not (Test-Path -LiteralPath $man)) { No 'Нет image_manifest.final.tsv: состав образа не утверждён.' }
else {
    $n = 0; $rows = New-Object Collections.Generic.List[object]
    foreach ($l in (Get-Content -LiteralPath $man -Encoding UTF8)) {
        if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
        $f = $l.Split("`t")
        # A-7 (r2): необязательная 3-я колонка = режим файла (755, 644 ...)
        if ($f.Count -lt 2 -or $f.Count -gt 3 -or $f[1] -cnotmatch '^[0-9a-f]{64}$' -or ($f.Count -eq 3 -and $f[2] -cnotmatch '^(0[0-7]{3}|[0-7]{3})$')) { No ('Строка манифеста не path<TAB>sha256[<TAB>режим] (или TBD): ' + $l); continue }
        if ($f[0] -match '(^|[\\/])\.\.([\\/]|$)' -or $f[0].StartsWith('/') -or $f[0] -match '^[A-Za-z]:' -or $f[0] -match '(^|[\\/])\.([\\/]|$)' -or $f[0] -match '[\\/]{2}') { No ('Небезопасный путь в манифесте (.., сегмент «.», двойной «/», абсолютный): ' + $f[0]); continue }
        # решение чата 1 (22:00): fcu_detect.py НЕ ставится образом. На дроне с 05.11 14:10 стоит исправленный (fcu_detect_fix_01, 5932a00a...), а в src r2j лежит прежний (ee174fd1...): установка вернула бы старую ошибку порта.
        if ($f[0] -match '(^|[\\/])fcu_detect\.py$') { No ('В манифесте есть ' + $f[0] + ': fcu_detect.py образом НЕ ставится (решение чата 1, 22:00): на дроне стоит исправленный 5932a00a..., в src r2j прежний ee174fd1... (старая ошибка порта). Уберите строку из манифеста и файл из payload.'); continue }
        $n++; $rows.Add(@{ path = $f[0]; sha = $f[1] })
        $pp = Join-Path (Join-Path $Kit 'payload') ($f[0] -replace '/', '\')
        if (-not (Test-Path -LiteralPath $pp)) { No ('В payload нет файла ' + $f[0]); continue }
        $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $pp).Hash.ToLower()
        if ($h -ne $f[1]) { No ('SHA256 файла ' + $f[0] + ' не сходится с манифестом.') }
    }
    if ($n -eq 0) { No 'Манифест пуст.' }
    foreach ($fd in @(Get-ChildItem -LiteralPath (Join-Path $Kit 'payload') -Recurse -File -Filter 'fcu_detect.py' -ErrorAction SilentlyContinue)) { No ('В payload лежит ' + $fd.FullName + ': fcu_detect.py в payload быть не должен (решение чата 1, 22:00; на дроне стоит исправленный 5932a00a..., прежний вернул бы старую ошибку порта).') }
    # r2 (поручение чата 1, 10.11): состав образа r2j. Скрипт висения hover r6, MAVROS bp02 и камера по умолчанию (camera_fix 4a15d699, он проверен в Gazebo).
    $reqv = @{}; $rq = Join-Path $Kit 'required_shas.txt'
    if (Test-Path -LiteralPath $rq) { foreach ($l in (Get-Content -LiteralPath $rq -Encoding UTF8)) { if ($l -match '^(HOVER_R6_SHA256|CAMERA_DEFAULT_SHA256|CAMERA_VARIANT_SHA256|FLIGHT_PY_SHA256)=([0-9a-f]{64})$') { $reqv[$Matches[1]] = $Matches[2] } } }
    if ($reqv.Count -ne 4) { No 'Нет required_shas.txt рядом с набором или в нём не четыре суммы (HOVER_R6_SHA256, CAMERA_DEFAULT_SHA256, CAMERA_VARIANT_SHA256, FLIGHT_PY_SHA256).' }
    $HOVER_SHA = $reqv['HOVER_R6_SHA256']
    $CAM_DEFAULT_SHA = $reqv['CAMERA_DEFAULT_SHA256']
    $CAM_VARIANT_SHA = $reqv['CAMERA_VARIANT_SHA256']
    $FLIGHT_SHA = $reqv['FLIGHT_PY_SHA256']
    if (-not ($rows | Where-Object { $_.sha -ceq $FLIGHT_SHA -and $_.path -like 'ros2_ws/src/bumblebee/examples/flight/flight.py' })) { No 'В манифесте нет ros2_ws/src/bumblebee/examples/flight/flight.py (Ж3, sha256 b69cc5e7...): takeoff.conf ссылается на него, он идёт на дрон вместе с образом.' }
    if (-not ($rows | Where-Object { $_.sha -ceq $HOVER_SHA -and $_.path -like 'ros2_ws/src/bumblebee/examples/*.py' })) { No 'В манифесте нет скрипта висения hover r6 в ros2_ws/src/bumblebee/examples/ (решение чата 1 20:10: он должен попасть в копию оверлея) (sha256 a11b195c...13f7): он идёт на дрон вместе с образом, sha сверяется при установке.' }
    foreach ($r in ($rows | Where-Object { $_.path -like '*camera_fix.py' })) {
        if ($r.sha -ceq $CAM_VARIANT_SHA) { No 'В основном манифесте camera_fix.py с sha256 dabd5076...: этот вариант идёт только отдельной папкой camera_variant_dabd5076 и только если владелец выберет. В основной образ входит прежний camera_fix (4a15d699...).' }
        elseif ($r.sha -cne $CAM_DEFAULT_SHA) { No ('camera_fix.py в манифесте с неожиданным sha256 ' + $r.sha + ' (ожидается прежний 4a15d699..., проверенный в Gazebo).') }
    }
    # MAVROS bp02: только исходники (5 файлов, sha256_bp02 = файлы тега backport-02 d63a236, сверены с /work/ws_mavros214_bp02, см. MAVROS_ORIGIN.md).
    # Список «сборок для Pi» MAVROS_ARM64_SHA256SUMS.txt не принимается: это набор проверок m5, а не результат настоящей сборки на Pi.
    $src = @(); $sp = Join-Path $Kit 'mavros_bp02_sources.tsv'
    if (Test-Path -LiteralPath $sp) { $src = @(Get-Content -LiteralPath $sp -Encoding UTF8 | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | ForEach-Object { ($_ -split "`t")[2] } | Where-Object { $_ -cmatch '^[0-9a-f]{64}$' }) }
    if ($src.Count -ne 5) { No 'Нет списка mavros_bp02_sources.tsv рядом с набором (5 исходников MAVROS bp02).' }
    else {
        $have = @($rows | ForEach-Object { $_.sha })
        $okSrc = (@($src | Where-Object { $have -ccontains $_ })).Count -eq $src.Count
        if (-not $okSrc) { No 'В манифесте нет MAVROS bp02: нужны все 5 исходников (mavros_bp02_sources.tsv, колонка sha256_bp02). Частичный набор и «сборки для Pi» не годятся: настоящей сборки на Pi нет (MAVROS_ORIGIN.md).' }
    }
    $manSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $man).Hash.ToLower()
    if ($boundSha -and $manSha -ne $boundSha) { No ('Флаг S2/S3 выдан для другого образа: sha256 image_manifest.final.tsv (' + $manSha + ') не равен ОБРАЗ_MANIFEST_SHA256 в S2_S3_PASSED.txt.') }
}

if ($ReportFile) { $rl = @(); if ($bad.Count -eq 0) { $rl = @('OK') } else { $rl = @($bad | ForEach-Object { '- ' + $_ }) }; [IO.File]::WriteAllLines($ReportFile, [string[]]$rl, (New-Object Text.UTF8Encoding($true))) }
if ($bad.Count -eq 0) { Write-Host 'Условия установки выполнены: S2/S3, свежая сверка, COM_OBL_RC_ACT=4, цель, манифест и payload (с flight.py, hover r6, исходниками MAVROS bp02 и камерой по умолчанию).'; exit 0 }
Write-Host ''
Write-Host '  СТОП: установка образа не разрешена. Не выполнены условия:  ' -ForegroundColor White -BackgroundColor Red
foreach ($b in $bad) { Write-Host (' - ' + $b) }
exit 1
