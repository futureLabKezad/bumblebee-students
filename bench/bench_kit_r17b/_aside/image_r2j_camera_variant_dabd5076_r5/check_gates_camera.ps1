# check_gates_camera.ps1 (Claude, 10.11.2026, набор r2; усилен по решению чата 1 в 19:19: гейт варианта не слабее основного) - условия установки ВАРИАНТА камеры. ТОЛЬКО на ПК, сети нет, дрон не трогает.
# Условия = ВСЕ условия основного check_gates.ps1 для этого образа + файл владельца:
#  1) gates\S2_S3_PASSED.txt В ЭТОЙ ПАПКЕ: S2=PASS, S3=PASS, ДАТА, ДОКАЗАТЕЛЬСТВО, СОЗДАЛ=чат 1 и ОБРАЗ_MANIFEST_SHA256 = sha256 ЭТОГО манифеста варианта (вариант не летал в Gazebo: флаг основного образа ему не годится);
#  2) свежая (не старше 30 мин) сверка настроек «СОВПАДАЕТ» полностью из таблицы MAVROS, число прочитанных = числу настроек компонента 1 в основе, без -AllowStreamFallback, COM_OBL_RC_ACT = 4;
#  3) gates\CAMERA_DABD5076_APPROVED.txt от чата 1 после слов владельца (с sha камеры);
#  4) DEST_ROOT и BACKUP_ROOT заполнены в ..\image_target.conf, есть ..\image_install.sh;
#  5) манифест варианта из одной строки camera_fix.py с sha256 dabd5076..., файл в payload сходится.
# Код выхода 0 = условия выполнены; 1 = нет (причины выводятся).
param([string]$Kit = '', [string]$OutDir = '', [int]$MaxAgeMin = 30)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Kit) { $Kit = $here }
$Kit = [IO.Path]::GetFullPath($Kit).TrimEnd('\')
$parent = Split-Path -Parent $Kit
$root = Split-Path -Parent $parent
if (-not $OutDir) { if ($env:BB_KIT_OUT) { $OutDir = $env:BB_KIT_OUT } else { $OutDir = Join-Path $root 'out' } }
$CAM = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
$bad = New-Object Collections.Generic.List[string]
function No([string]$s) { $script:bad.Add($s) }

# 5 (читаем раньше, нужен sha манифеста для флага S2/S3)
$man = Join-Path $Kit 'image_manifest.final.tsv'
$manSha = $null
if (-not (Test-Path -LiteralPath $man)) { No 'Нет image_manifest.final.tsv варианта.' }
else {
    $manSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $man).Hash.ToLower()
    $rows = @(Get-Content -LiteralPath $man -Encoding UTF8 | Where-Object { $_.Trim() -ne '' -and -not $_.StartsWith('#') })
    if ($rows.Count -ne 1) { No ('В манифесте варианта должна быть ровно одна строка, а их ' + $rows.Count) }
    else {
        $f = $rows[0].Split("`t")
        if ($f.Count -lt 2 -or $f[1] -cne $CAM -or $f[0] -notlike '*camera_fix.py' -or $f[0] -match '(^|[\\/])\.\.([\\/]|$)' -or $f[0].StartsWith('/') -or $f[0] -match 'TBD') { No ('Строка манифеста варианта не camera_fix.py с sha256 dabd5076...: ' + $rows[0]) }
        else {
            $pp = Join-Path (Join-Path $Kit 'payload') ($f[0] -replace '/', '\')
            if (-not (Test-Path -LiteralPath $pp)) { No ('В payload варианта нет файла ' + $f[0]) }
            elseif ((Get-FileHash -Algorithm SHA256 -LiteralPath $pp).Hash.ToLower() -ne $CAM) { No 'SHA256 файла camera_fix.py в payload варианта не сходится.' }
        }
    }
}
# 1. S2/S3 для этого образа
$g = Join-Path $Kit 'gates\S2_S3_PASSED.txt'
if (-not (Test-Path -LiteralPath $g)) { No 'Нет gates\S2_S3_PASSED.txt варианта: S2 и S3 в SITL с этим camera_fix ещё не подтверждены чатом 1 (правило 14). Флаг основного образа не годится.' }
else {
    $gt = Get-Content -LiteralPath $g -Encoding UTF8
    foreach ($k in 'S2=PASS', 'S3=PASS') { if (-not ($gt | Where-Object { $_.Trim() -eq $k })) { No ('В S2_S3_PASSED.txt варианта нет строки ' + $k) } }
    foreach ($k in 'ДАТА=', 'ДОКАЗАТЕЛЬСТВО=', 'СОЗДАЛ=чат 1') { if (-not ($gt | Where-Object { $_.Trim().StartsWith($k) })) { No ('В S2_S3_PASSED.txt варианта нет строки ' + $k + '...') } }
    $bindLine = $gt | Where-Object { $_.Trim().StartsWith('ОБРАЗ_MANIFEST_SHA256=') } | Select-Object -First 1
    if (-not $bindLine) { No 'В S2_S3_PASSED.txt варианта нет строки ОБРАЗ_MANIFEST_SHA256=<sha256 манифеста варианта>.' }
    else {
        $bound = ($bindLine.Trim() -replace '^ОБРАЗ_MANIFEST_SHA256=', '').Trim()
        if ($bound -cnotmatch '^[0-9a-f]{64}$') { No 'ОБРАЗ_MANIFEST_SHA256 в S2_S3_PASSED.txt варианта должен быть 64 символа 0-9a-f.' }
        elseif ($manSha -and $bound -cne $manSha) { No ('Флаг S2/S3 варианта выдан для другого образа: sha256 манифеста варианта (' + $manSha + ') не равен ОБРАЗ_MANIFEST_SHA256.') }
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
    if (-not (Test-Path -LiteralPath $bl)) { No ('Нет основы настроек рядом с набором (' + $bl + '): число прочитанных настроек не с чем сверить.') }
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
# 3. файл владельца
$g2 = Join-Path $Kit 'gates\CAMERA_DABD5076_APPROVED.txt'
if (-not (Test-Path -LiteralPath $g2)) { No 'Нет gates\CAMERA_DABD5076_APPROVED.txt: владелец вариант камеры не выбрал (или чат 1 ещё не записал выбор).' }
else {
    $at = Get-Content -LiteralPath $g2 -Encoding UTF8
    foreach ($k in 'ВЛАДЕЛЕЦ_ВЫБРАЛ=камера dabd5076', 'СОЗДАЛ=чат 1', ('CAMERA_SHA256=' + $CAM)) { if (-not ($at | Where-Object { $_.Trim() -ceq $k })) { No ('В CAMERA_DABD5076_APPROVED.txt нет строки ' + $k) } }
    foreach ($k in 'ДАТА=', 'СЛОВА_ВЛАДЕЛЬЦА=') { if (-not ($at | Where-Object { $_.Trim().StartsWith($k) -and $_.Trim().Length -gt $k.Length })) { No ('В CAMERA_DABD5076_APPROVED.txt нет заполненной строки ' + $k + '...') } }
}
# 4. цель установки
$conf = Join-Path $parent 'image_target.conf'
if (-not (Test-Path -LiteralPath $conf)) { No 'Нет ..\image_target.conf.' }
else {
    foreach ($k in 'DEST_ROOT', 'BACKUP_ROOT') {
        $line = Get-Content -LiteralPath $conf -Encoding UTF8 | Where-Object { $_ -match ('^' + $k + '=') } | Select-Object -First 1
        $v = ''; if ($line) { $v = ($line -replace ('^' + $k + '='), '').Trim() }
        if ($v -eq '' -or $v -match 'TBD') { No ('В ..\image_target.conf не заполнено ' + $k + ' (TBD).') }
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $parent 'image_install.sh'))) { No 'Нет ..\image_install.sh.' }
if ($bad.Count -eq 0) { Write-Host 'Условия установки варианта камеры выполнены (S2/S3 для этого образа, свежая сверка, COM_OBL_RC_ACT=4, разрешение владельца, цель, манифест и payload).'; exit 0 }
Write-Host ''
Write-Host '  СТОП: установка варианта камеры не разрешена. Не выполнены условия:  ' -ForegroundColor White -BackgroundColor Red
foreach ($b in $bad) { Write-Host (' - ' + $b) }
exit 1