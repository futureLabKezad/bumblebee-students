# run_tests_image.ps1 (Claude, 10.11.2026, копия теста набора r4 для image_r2j) - тесты заготовки установки образа. К дрону не подключается.
# A: check_gates.ps1 (условия правила 14) на копии набора в песочнице; B: 05_install_r2j.cmd / 06_rollback_r2j.cmd с поддельными ssh и scp;
# C: image_install.sh и image_rollback.sh в WSL на поддельном корне (hostname подменён функцией только в тесте).
$ErrorActionPreference = 'Stop'
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$IK = Join-Path $Kit 'image_r2j'
# r6 (12.11): вариант камеры r5 (05v) отложен в _aside набора (README r6); V-тесты ниже идут на его копии в песочнице, как раньше
$CVA = Join-Path $Kit '_aside\image_r2j_camera_variant_dabd5076_r5'
$Run = Join-Path $T ('run_i_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') {
    if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") }
}
$realPc = $env:COMPUTERNAME
$OutDir = Join-Path $Run 'out'; New-Item -ItemType Directory -Path $OutDir | Out-Null
$env:BB_KIT_OUT = $OutDir; $env:BB_NO_PAUSE = '1'

# r3 (Ж-8): рядом с песочницей лежит params_check\baseline (check_gates сверяет число прочитанных настроек с числом настроек компонента 1 в основе)
New-Item -ItemType Directory -Path (Join-Path $Run 'params_check') | Out-Null
Copy-Item -LiteralPath (Join-Path (Join-Path $Kit 'params_check') 'baseline_20261104_1145.params') -Destination (Join-Path $Run 'params_check')
# ---------- песочница набора ----------
$script:ikN = 0
# r2j (поправка по проверке 10.11): флаг S2/S3 привязан к sha256 манифеста; Set-Flag пишет флаг для ТЕКУЩЕГО манифеста, Rebind пересчитывает после правки манифеста в тесте
function Set-Flag([string]$d, [string]$sha = '') {
    if ($sha -eq '') { $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $d 'image_manifest.final.tsv')).Hash.ToLower() }
    [IO.File]::WriteAllText((Join-Path $d 'gates\S2_S3_PASSED.txt'), ("S2=PASS`r`nS3=PASS`r`nДАТА=2026-11-10`r`nДОКАЗАТЕЛЬСТВО=тест (копия в песочнице, настоящий файл создаёт только чат 1)`r`nОБРАЗ_MANIFEST_SHA256=" + $sha + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
}
function Rebind([string]$d) { Set-Flag $d }function New-Kit {
    $script:ikN++
    $d = Join-Path $Run ('ik' + $script:ikN)
    Copy-Item -LiteralPath $IK -Destination $d -Recurse
    # 05_install_r2j.cmd без строки chcp 65001 (она мешает set /p читать из файла, только в тесте)
    foreach ($n in '05_install_r2j.cmd', '06_rollback_r2j.cmd') {
        $p = Join-Path $d $n
        $lines = [IO.File]::ReadAllText($p) -split "`r`n"
        [IO.File]::WriteAllText($p, (($lines | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
    }
    $payload = Join-Path $d 'payload'
    New-Item -ItemType Directory -Path (Join-Path $payload 'sub') -Force | Out-Null
    [IO.File]::WriteAllText((Join-Path $payload 'a.txt'), "file a`n", $utf8n)
    [IO.File]::WriteAllText((Join-Path $payload 'sub\b.txt'), "file b`n", $utf8n)
    $ha = (Get-FileHash -Algorithm SHA256 (Join-Path $payload 'a.txt')).Hash.ToLower()
    $hb = (Get-FileHash -Algorithm SHA256 (Join-Path $payload 'sub\b.txt')).Hash.ToLower()
    # r2 (набор r2): обязательный состав образа r2j. В песочнице это поддельные файлы, а их суммы подставлены в required_shas.txt и списки MAVROS песочницы.
    $shaOf = @{}; $rowsTxt = "# тест`na.txt`t$ha`nsub/b.txt`t$hb`n"
    New-Item -ItemType Directory -Path (Join-Path $payload 'src') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $payload 'ros2_ws\src\bumblebee\examples\flight') -Force | Out-Null
    $tsvTxt = "# path`tsha256_base`tsha256_bp02`n"
    foreach ($n in 'ros2_ws/src/bumblebee/examples/flight/hover.py', 'camera_fix.py', 'ros2_ws/src/bumblebee/examples/flight/flight.py', 'src/f1.cpp', 'src/f2.cpp', 'src/f3.cpp', 'src/f4.cpp', 'src/f5.cpp') {
        [IO.File]::WriteAllText((Join-Path $payload ($n -replace '/', '\')), ('fake ' + $n + "`n"), $utf8n)
        $shaOf[$n] = (Get-FileHash -Algorithm SHA256 (Join-Path $payload ($n -replace '/', '\'))).Hash.ToLower()
        $rowsTxt += $n + "`t" + $shaOf[$n] + "`n"
        if ($n -like 'src/*') { $tsvTxt += 'mavros/' + $n + "`t" + ('0' * 64) + "`t" + $shaOf[$n] + "`n" }
    }
    [IO.File]::WriteAllText((Join-Path $d 'image_manifest.final.tsv'), $rowsTxt, $utf8n)
    [IO.File]::WriteAllText((Join-Path $d 'required_shas.txt'), ("HOVER_R6_SHA256=" + $shaOf['ros2_ws/src/bumblebee/examples/flight/hover.py'] + "`nCAMERA_DEFAULT_SHA256=" + $shaOf['camera_fix.py'] + "`nCAMERA_VARIANT_SHA256=" + ('d' * 64) + "`nFLIGHT_PY_SHA256=" + $shaOf['ros2_ws/src/bumblebee/examples/flight/flight.py'] + "`n"), $utf8n)
    [IO.File]::WriteAllText((Join-Path $d 'mavros_bp02_sources.tsv'), $tsvTxt, $utf8n)
    [IO.File]::WriteAllText((Join-Path $d 'image_target.conf'), "DEST_ROOT=/tmp/dest_test`nBACKUP_ROOT=/tmp/bak_test`n", $utf8n)
    Set-Flag $d
    return $d
}
function New-FreshParams([string]$stamp, [string]$first = '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ===', [string]$obl = '4', [int]$ageMin = 0, [string]$more = '') {
    $rp = Join-Path $OutDir ('params_' + $stamp + '_report.txt')
    [IO.File]::WriteAllText($rp, $first + "`r`n" + $more, $utf8)
    [IO.File]::WriteAllText((Join-Path $OutDir ('params_' + $stamp + '.params')), "# тест`r`n1`t1`tBAT1_SOURCE`t1`t6`r`n1`t1`tCOM_OBL_RC_ACT`t$obl`t6`r`n", $utf8)
    (Get-Item $rp).LastWriteTime = (Get-Date).AddMinutes(-$ageMin)
}
function Clear-Params {
    $dst = Join-Path $Run ('moved_' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    New-Item -ItemType Directory -Path $dst | Out-Null
    Get-ChildItem $OutDir -Filter 'params_*' | Move-Item -Destination $dst
}
function Gates([string]$kitDir) {
    $rf = Join-Path $Run ('gates_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $kitDir 'check_gates.ps1') -Kit $kitDir -OutDir $OutDir -ReportFile $rf | Out-Null
    $code = $LASTEXITCODE
    $o = ''; if (Test-Path $rf) { $o = [IO.File]::ReadAllText($rf) }
    return @{ Code = $code; Text = $o }
}

# ---------- A: условия ----------
Clear-Params; New-FreshParams 'A1'
$k = New-Kit
$g = Gates $k
Check 'A1' 'все условия выполнены: код 0' ($g.Code -eq 0) $g.Text

$k = New-Kit; Remove-Item (Join-Path $k 'gates\S2_S3_PASSED.txt')
$g = Gates $k
Check 'A2' 'нет S2_S3_PASSED.txt: код 1, причина названа' ($g.Code -eq 1 -and $g.Text -match 'S2_S3_PASSED') ''
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'gates\S2_S3_PASSED.txt'), "S2=PASS`r`nДАТА=2026-11-10`r`n", $utf8)
$g = Gates $k
Check 'A3' 'в файле нет S3=PASS и остального: код 1' ($g.Code -eq 1 -and $g.Text -match 'S3=PASS') ''

# привязка флага S2/S3 к образу (поправка по проверке 10.11)
$k = New-Kit; Set-Flag $k ('0' * 64)
$g = Gates $k
Check 'A3b' 'флаг S2/S3 выдан для другого образа (чужой sha манифеста): код 1, «другого образа»' ($g.Code -eq 1 -and $g.Text -match 'другого образа') $g.Text
$k = New-Kit; $fp = Join-Path $k 'gates\S2_S3_PASSED.txt'
[IO.File]::WriteAllText($fp, (([IO.File]::ReadAllLines($fp) | Where-Object { $_ -notmatch '^ОБРАЗ_MANIFEST_SHA256=' }) -join "`r`n") + "`r`n", $utf8)
$g = Gates $k
Check 'A3b' 'во флаге S2/S3 нет строки ОБРАЗ_MANIFEST_SHA256=: код 1, строка названа' ($g.Code -eq 1 -and $g.Text -match 'ОБРАЗ_MANIFEST_SHA256') $g.Text
$k = New-Kit; Set-Flag $k 'NOT-A-HASH'
$g = Gates $k
Check 'A3b' 'ОБРАЗ_MANIFEST_SHA256 не 64 символа 0-9a-f: код 1' ($g.Code -eq 1 -and $g.Text -match '64 символа') $g.Text
$k = New-Kit; $mp = Join-Path $k 'image_manifest.final.tsv'
Add-Content -LiteralPath $mp -Value ("c.txt`t" + ('a' * 64)) -Encoding UTF8
[IO.File]::WriteAllText((Join-Path $k 'payload\c.txt'), 'x', $utf8n)
$g = Gates $k
Check 'A3b' 'манифест изменён после выдачи флага: код 1 (флаг больше не годится), флаг больше не годится (payload в этом тесте тоже не сходится, но требуется именно причина «другого образа»)' ($g.Code -eq 1 -and $g.Text -match 'другого образа') $g.Text
$k = New-Kit; $kh = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $k 'image_manifest.final.tsv')).Hash.ToUpper()
Set-Flag $k $kh
$g = Gates $k
Check 'A3b' 'sha манифеста во флаге в верхнем регистре: код 1 (строгое сравнение строчными)' ($g.Code -eq 1) $g.Text
Clear-Params
$k = New-Kit; $g = Gates $k
Check 'A4' 'нет сверки настроек: код 1' ($g.Code -eq 1 -and $g.Text -match 'Нет сверки настроек') ''
Clear-Params; New-FreshParams 'A5' '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ===' '4' 45
$g = Gates $k
Check 'A5' 'сверка старше 30 минут: код 1' ($g.Code -eq 1 -and $g.Text -match 'старая') ''
Clear-Params; New-FreshParams 'A6' '=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 1 ==='
$g = Gates $k
Check 'A6' 'сверка с отличиями: код 1' ($g.Code -eq 1 -and $g.Text -match 'не «СОВПАДАЕТ полностью') ''
Clear-Params; New-FreshParams 'A7' '=== СВЕРКА НЕПОЛНАЯ: прочитано 1077 из 1107. Совпадение НЕ подтверждено. Повторить чтение. ==='
$g = Gates $k
Check 'A7' 'неполная сверка: код 1' ($g.Code -eq 1) ''
Clear-Params; New-FreshParams 'A8' '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ===' '0'
$g = Gates $k
Check 'A8' 'COM_OBL_RC_ACT=0: код 1, названо правило 14' ($g.Code -eq 1 -and $g.Text -match 'COM_OBL_RC_ACT на дроне не 4') ''

Clear-Params; New-FreshParams 'A9'
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'image_target.conf'), "DEST_ROOT=TBD`nBACKUP_ROOT=/tmp/x`n", $utf8n)
$g = Gates $k
Check 'A9' 'DEST_ROOT=TBD: код 1' ($g.Code -eq 1 -and $g.Text -match 'DEST_ROOT') ''
$k = New-Kit; Remove-Item (Join-Path $k 'image_manifest.final.tsv')
$g = Gates $k
Check 'A10' 'нет манифеста: код 1' ($g.Code -eq 1 -and $g.Text -match 'состав образа не утверждён') ''
$k = New-Kit; Add-Content -LiteralPath (Join-Path $k 'image_manifest.final.tsv') -Value "c.txt`tTBD"
$g = Gates $k
Check 'A11' 'в манифесте TBD: код 1' ($g.Code -eq 1 -and $g.Text -match 'TBD') ''
$k = New-Kit; Add-Content -LiteralPath (Join-Path $k 'payload\a.txt') -Value 'tampered'
$g = Gates $k
Check 'A12' 'payload изменён после манифеста: код 1, SHA256 не сходится' ($g.Code -eq 1 -and $g.Text -match 'SHA256 файла a\.txt') ''
$k = New-Kit; Remove-Item (Join-Path $k 'payload\sub\b.txt')
$g = Gates $k
Check 'A13' 'файла из манифеста нет в payload: код 1' ($g.Code -eq 1 -and $g.Text -match 'нет файла sub/b.txt') ''
$k = New-Kit; Add-Content -LiteralPath (Join-Path $k 'image_manifest.final.tsv') -Value ("..\..\evil.txt`t" + ('a' * 64))
$g = Gates $k
Check 'A14' 'путь с .. в манифесте: код 1, небезопасный путь' ($g.Code -eq 1 -and $g.Text -match 'Небезопасный путь') ''
# ===== r2 =====
# A-6: отчёт, сделанный с -AllowStreamFallback, гейты не проходит
$strictHdr = '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ==='
Clear-Params; New-FreshParams 'A16' '=== ЧЕРНОВИК, НЕ ДЛЯ ГЕЙТОВ (-AllowStreamFallback): отличий нет, прочитано 1107 из 1107, но 30 значений только из запасного потока (из таблицы MAVROS 1077) ==='
$k = New-Kit; $g = Gates $k
Check 'A16' 'A-6: отчёт-ЧЕРНОВИК с -AllowStreamFallback: код 1' ($g.Code -eq 1) $g.Text
Clear-Params; New-FreshParams 'A17' '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1077, из запасного потока 30) ==='
$g = Gates $k
Check 'A17' 'A-6: «СОВПАДАЕТ», но часть значений из запасного потока (30): код 1' ($g.Code -eq 1 -and $g.Text -match 'из таблицы MAVROS') $g.Text
Clear-Params; New-FreshParams 'A18' $strictHdr '4' 0 ("Режим: значения из запасного потока считаются прочитанными (-AllowStreamFallback).`r`n")
$g = Gates $k
Check 'A18' 'A-6: первая строка строгая, но в отчёте ключ -AllowStreamFallback: код 1, причина названа' ($g.Code -eq 1 -and $g.Text -match 'AllowStreamFallback') $g.Text
Clear-Params; New-FreshParams 'A19' '=== НЕ ПОДТВЕРЖДЕНО (UNKNOWN): 2 имён есть и у компонента 1, и у компонента 125 ==='
$g = Gates $k
Check 'A19' 'A-4: отчёт с UNKNOWN (подмена компонентом 125 возможна): код 1' ($g.Code -eq 1) $g.Text
Clear-Params; New-FreshParams 'A20'
$g = Gates $k
Check 'A20' 'строгий отчёт без ключа: код 0 (гейты не стали глуше)' ($g.Code -eq 0) $g.Text
# A-7: необязательная 3-я колонка манифеста = режим файла
$k = New-Kit
$mp = Join-Path $k 'image_manifest.final.tsv'
$ml = [IO.File]::ReadAllText($mp) -split "`n" | Where-Object { $_ -ne '' }
[IO.File]::WriteAllText($mp, (($ml | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`t755" } else { $_ } }) -join "`n") + "`n", $utf8n)
Rebind $k
$g = Gates $k
Check 'A21' 'A-7: манифест с режимом 755 в 3-й колонке: код 0' ($g.Code -eq 0) $g.Text
$k = New-Kit; $mp = Join-Path $k 'image_manifest.final.tsv'
$ml = [IO.File]::ReadAllText($mp) -split "`n" | Where-Object { $_ -ne '' }
[IO.File]::WriteAllText($mp, (($ml | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`tabc" } else { $_ } }) -join "`n") + "`n", $utf8n)
$g = Gates $k
Check 'A21' 'A-7: режим abc в манифесте: код 1' ($g.Code -eq 1 -and $g.Text -match 'режим') $g.Text
Clear-Params; New-FreshParams 'A22'
# r3: Ж-8 (число прочитанных = числу настроек основы), Ж-5 (режим, заглавный hex)
Clear-Params; New-FreshParams 'A23' '=== СОВПАДАЕТ: прочитано 1000 из 1000, отличий нет (из таблицы MAVROS 1000, из запасного потока 0) ==='
$k = New-Kit; $g = Gates $k
Check 'A23' 'Ж-8: «прочитано 1000 из 1000», а в основе 1107: код 1' ($g.Code -eq 1 -and $g.Text -match 'в основе компонента 1 их 1107') $g.Text
Clear-Params; New-FreshParams 'A24'
$k = New-Kit; $mp = Join-Path $k 'image_manifest.final.tsv'
$ml = [IO.File]::ReadAllText($mp) -split "`n" | Where-Object { $_ -ne '' }
[IO.File]::WriteAllText($mp, (($ml | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`t4755" } else { $_ } }) -join "`n") + "`n", $utf8n)
$g = Gates $k
Check 'A24' 'Ж-5: режим 4755 (setuid) не принимается: код 1' ($g.Code -eq 1 -and $g.Text -match 'режим') $g.Text
$k = New-Kit; $mp = Join-Path $k 'image_manifest.final.tsv'
$ml = [IO.File]::ReadAllText($mp) -split "`n" | Where-Object { $_ -ne '' }
[IO.File]::WriteAllText($mp, (($ml | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`t0755" } else { $_ } }) -join "`n") + "`n", $utf8n)
Rebind $k
$g = Gates $k
Check 'A25' 'O-2: режим 0755 гейт пропускает: код 0' ($g.Code -eq 0) $g.Text
$k = New-Kit; $mp = Join-Path $k 'image_manifest.final.tsv'
$ml = [IO.File]::ReadAllText($mp) -split "`n" | Where-Object { $_ -ne '' }
[IO.File]::WriteAllText($mp, (($ml | ForEach-Object { if ($_ -match '^a\.txt') { [regex]::Replace($_, "`t[0-9a-f]{64}", [Text.RegularExpressions.MatchEvaluator]{ param($m) $m.Value.ToUpper() }) } else { $_ } }) -join "`n") + "`n", $utf8n)
$g = Gates $k
Check 'A26' 'Ж-5: SHA256 заглавными буквами в манифесте: гейт отклоняет (на Pi это был бы sha256 mismatch): код 1' ($g.Code -eq 1) $g.Text
# r4 Н-4: -Kit с «\.» на конце (так зовёт .cmd) не должен отключать сверку с основой; нет основы = отказ
Clear-Params; New-FreshParams 'A27' '=== СОВПАДАЕТ: прочитано 1106 из 1106, отличий нет (из таблицы MAVROS 1106, из запасного потока 0) ==='
$k = New-Kit
$rf = Join-Path $Run 'gates_dot.txt'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $k 'check_gates.ps1') -Kit ($k + '\.') -OutDir $OutDir -ReportFile $rf | Out-Null
$gt = [IO.File]::ReadAllText($rf)
Check 'A27' 'Н-4: -Kit «папка\.» тоже сверяет число прочитанных с основой (1106 против 1107): код 1' ($LASTEXITCODE -eq 1 -and $gt -match 'в основе компонента 1 их 1107') $gt
Clear-Params; New-FreshParams 'A28'
$nb = Join-Path $Run 'nobase'; New-Item -ItemType Directory -Path $nb | Out-Null
$kk = New-Kit; Copy-Item -LiteralPath $kk -Destination (Join-Path $nb 'ik') -Recurse
$g = Gates (Join-Path $nb 'ik')
Check 'A28' 'Н-4: основы рядом с набором нет: отказ (код 1), а не тихий пропуск проверки' ($g.Code -eq 1 -and $g.Text -match 'Нет основы настроек') $g.Text
# настоящий набор сейчас обязан быть заблокирован
Clear-Params
$g = Gates $IK
Check 'A15' 'настоящий image_kit сейчас заблокирован (нет S2/S3, TBD, нет манифеста): код 1' ($g.Code -eq 1 -and $g.Text -match 'S2_S3_PASSED' -and $g.Text -match 'TBD') ''

# ---------- A40: обязательный состав образа r2j (hover r6, MAVROS bp02, камера по умолчанию), check_gates.ps1 ----------
function Set-Rows([string]$k, [string[]]$names) {
    $txt = "# тест`n"
    foreach ($n in $names) { $txt += $n + "`t" + (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $k ('payload\' + ($n -replace '/', '\')))).Hash.ToLower() + "`n" }
    [IO.File]::WriteAllText((Join-Path $k 'image_manifest.final.tsv'), $txt, $utf8n); Rebind $k
}
$baseRows = @('a.txt', 'sub/b.txt', 'ros2_ws/src/bumblebee/examples/flight/hover.py', 'camera_fix.py', 'ros2_ws/src/bumblebee/examples/flight/flight.py', 'src/f1.cpp', 'src/f2.cpp', 'src/f3.cpp', 'src/f4.cpp', 'src/f5.cpp')
Clear-Params; New-FreshParams 'A40'
$k = New-Kit; Set-Rows $k $baseRows; $g = Gates $k
Check 'A40' 'полный состав (a, b, hover r6, камера по умолчанию, flight.py, 5 исходников MAVROS bp02): код 0' ($g.Code -eq 0) $g.Text
$k = New-Kit; Set-Rows $k ($baseRows | Where-Object { $_ -ne 'ros2_ws/src/bumblebee/examples/flight/hover.py' }); $g = Gates $k
Check 'A40' 'в манифесте нет скрипта висения hover r6: код 1, причина названа' ($g.Code -eq 1 -and $g.Text -match 'hover r6') $g.Text
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'payload\ros2_ws\src\bumblebee\examples\flight\hover.py'), "other hover`n", $utf8n); Set-Rows $k $baseRows; $g = Gates $k
Check 'A40' 'hover.py другой (sha не тот, что в required_shas.txt): код 1, hover r6' ($g.Code -eq 1 -and $g.Text -match 'hover r6') $g.Text
$k = New-Kit; Set-Rows $k ($baseRows | Where-Object { $_ -ne 'ros2_ws/src/bumblebee/examples/flight/flight.py' }); $g = Gates $k
Check 'A40' 'в манифесте нет flight.py (Ж3, на него ссылается takeoff.conf): код 1, «flight.py»' ($g.Code -eq 1 -and $g.Text -match 'flight\.py') $g.Text
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'payload\ros2_ws\src\bumblebee\examples\flight\flight.py'), "other flight`n", $utf8n); Set-Rows $k $baseRows; $g = Gates $k
Check 'A40' 'flight.py другой (sha не тот, что в required_shas.txt): код 1, «flight.py»' ($g.Code -eq 1 -and $g.Text -match 'flight\.py') $g.Text
# решение чата 1 (20:10): hover r6 и flight.py обязаны лежать в ros2_ws/src/bumblebee/examples/ (иначе 13 не скопирует их в оверлей)
$k = New-Kit; Copy-Item -LiteralPath (Join-Path $k 'payload\ros2_ws\src\bumblebee\examples\flight\hover.py') -Destination (Join-Path $k 'payload\hover_out.py')
Set-Rows $k (@($baseRows | Where-Object { $_ -ne 'ros2_ws/src/bumblebee/examples/flight/hover.py' }) + 'hover_out.py'); $g = Gates $k
Check 'A40' 'hover r6 (sha верный) лежит вне ros2_ws/src/bumblebee/examples/: код 1, «в ros2_ws/src/bumblebee/examples/»' ($g.Code -eq 1 -and $g.Text -match 'hover r6 в ros2_ws/src/bumblebee/examples/') $g.Text
$k = New-Kit; New-Item -ItemType Directory -Path (Join-Path $k 'payload\x') -Force | Out-Null; Copy-Item -LiteralPath (Join-Path $k 'payload\ros2_ws\src\bumblebee\examples\flight\flight.py') -Destination (Join-Path $k 'payload\x\flight.py')
Set-Rows $k (@($baseRows | Where-Object { $_ -ne 'ros2_ws/src/bumblebee/examples/flight/flight.py' }) + 'x/flight.py'); $g = Gates $k
Check 'A40' 'flight.py (sha верный) лежит вне ros2_ws/src/bumblebee/examples/flight/: код 1' ($g.Code -eq 1 -and $g.Text -match 'ros2_ws/src/bumblebee/examples/flight/flight\.py') $g.Text
# решение чата 1 (22:00): fcu_detect.py образом не ставится
$k = New-Kit; New-Item -ItemType Directory -Path (Join-Path $k 'payload\ros2_ws\src\bumblebee\scripts') -Force | Out-Null; [IO.File]::WriteAllText((Join-Path $k 'payload\ros2_ws\src\bumblebee\scripts\fcu_detect.py'), "fcu fix`n", $utf8n)
Set-Rows $k ($baseRows + 'ros2_ws/src/bumblebee/scripts/fcu_detect.py'); $g = Gates $k
Check 'A42' 'в манифесте есть scripts/fcu_detect.py: код 1, «fcu_detect.py образом НЕ ставится»' ($g.Code -eq 1 -and $g.Text -match 'fcu_detect\.py образом НЕ ставится') $g.Text
$k = New-Kit; New-Item -ItemType Directory -Path (Join-Path $k 'payload\scripts') -Force | Out-Null; [IO.File]::WriteAllText((Join-Path $k 'payload\scripts\FCU_DETECT.PY'), "fcu fix`n", $utf8n)
Set-Rows $k ($baseRows + 'scripts/FCU_DETECT.PY'); $g = Gates $k
Check 'A42' 'путь в другом регистре (FCU_DETECT.PY) тоже отклонён: код 1' ($g.Code -eq 1 -and $g.Text -match 'НЕ ставится') $g.Text
$k = New-Kit; New-Item -ItemType Directory -Path (Join-Path $k 'payload\x') -Force | Out-Null; [IO.File]::WriteAllText((Join-Path $k 'payload\x\fcu_detect.py'), "fcu fix`n", $utf8n); Set-Rows $k $baseRows; $g = Gates $k
Check 'A42' 'fcu_detect.py лежит в payload, но в манифесте его нет: код 1, «в payload быть не должен»' ($g.Code -eq 1 -and $g.Text -match 'в payload быть не должен') $g.Text
# r3 (замечание проверки 11.11): пути с сегментом «.» и двойным «/» (тот же файл, что без них) не принимаются
$k = New-Kit; Set-Rows $k ($baseRows + './a.txt'); $g = Gates $k
Check 'A43' 'в манифесте путь ./a.txt (тот же файл, что a.txt): код 1, «Небезопасный путь»' ($g.Code -eq 1 -and $g.Text -match 'Небезопасный путь') $g.Text
$k = New-Kit; Set-Rows $k (($baseRows | Where-Object { $_ -ne 'sub/b.txt' }) + 'sub/./b.txt'); $g = Gates $k
Check 'A43' 'путь sub/./b.txt: код 1' ($g.Code -eq 1 -and $g.Text -match 'Небезопасный путь') $g.Text
$k = New-Kit; Set-Rows $k (($baseRows | Where-Object { $_ -ne 'sub/b.txt' }) + 'sub//b.txt'); $g = Gates $k
Check 'A43' 'путь sub//b.txt: код 1' ($g.Code -eq 1 -and $g.Text -match 'Небезопасный путь') $g.Text
$k = New-Kit; Set-Rows $k ($baseRows | Where-Object { $_ -ne 'camera_fix.py' }); $g = Gates $k
Check 'A41' 'camera_fix.py в манифесте отсутствует (на дроне остаётся прежний): код 0' ($g.Code -eq 0) $g.Text
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'payload\camera_fix.py'), "variant camera`n", $utf8n)
$vs = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $k 'payload\camera_fix.py')).Hash.ToLower()
$rq = Join-Path $k 'required_shas.txt'; [IO.File]::WriteAllText($rq, (([IO.File]::ReadAllLines($rq) | ForEach-Object { if ($_ -match '^CAMERA_VARIANT_SHA256=') { 'CAMERA_VARIANT_SHA256=' + $vs } else { $_ } }) -join "`n") + "`n", $utf8n)
Set-Rows $k $baseRows; $g = Gates $k
Check 'A41' 'в основном манифесте camera_fix.py варианта dabd5076 (по sha из required_shas): код 1, «отдельной папкой … только если владелец выберет»' ($g.Code -eq 1 -and $g.Text -match 'dabd5076' -and $g.Text -match 'только если владелец выберет') $g.Text
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'payload\camera_fix.py'), "unknown camera`n", $utf8n); Set-Rows $k $baseRows; $g = Gates $k
Check 'A41' 'camera_fix.py с неожиданным sha (не прежний и не вариант): код 1, «неожиданным»' ($g.Code -eq 1 -and $g.Text -match 'неожиданным') $g.Text
$k = New-Kit; Set-Rows $k ($baseRows | Where-Object { $_ -ne 'src/f5.cpp' }); $g = Gates $k
Check 'A42' 'MAVROS bp02: из 5 исходников в манифесте только 4: код 1, «MAVROS bp02»' ($g.Code -eq 1 -and $g.Text -match 'MAVROS bp02') $g.Text
$k = New-Kit; Set-Rows $k ($baseRows | Where-Object { $_ -notmatch '^src/' }); $g = Gates $k
Check 'A42' 'MAVROS bp02: нет ни одного исходника: код 1' ($g.Code -eq 1 -and $g.Text -match 'MAVROS bp02') $g.Text
$k = New-Kit; [IO.File]::WriteAllText((Join-Path $k 'payload\src\f3.cpp'), "changed source`n", $utf8n); Set-Rows $k $baseRows; $g = Gates $k
Check 'A42' 'MAVROS bp02: один исходник другой (sha не из mavros_bp02_sources.tsv): код 1' ($g.Code -eq 1 -and $g.Text -match 'MAVROS bp02') $g.Text
$k = New-Kit; Remove-Item (Join-Path $k 'mavros_bp02_sources.tsv'); $g = Gates $k
Check 'A43' 'нет списка mavros_bp02_sources.tsv: код 1, «Нет списка mavros_bp02_sources.tsv»' ($g.Code -eq 1 -and $g.Text -match 'Нет списка mavros_bp02_sources\.tsv') $g.Text
$k = New-Kit; Add-Content -LiteralPath (Join-Path $k 'mavros_bp02_sources.tsv') -Value ("mavros/src/f6.cpp`t" + ('0' * 64) + "`t" + ('e' * 64)) -Encoding UTF8; $g = Gates $k
Check 'A43' 'в списке MAVROS шесть строк вместо пяти: код 1 (список другой, чем ожидается)' ($g.Code -eq 1 -and $g.Text -match 'mavros_bp02_sources') $g.Text
$k = New-Kit; Remove-Item (Join-Path $k 'required_shas.txt'); $g = Gates $k
Check 'A44' 'нет required_shas.txt: код 1, причина названа' ($g.Code -eq 1 -and $g.Text -match 'required_shas') $g.Text
$k = New-Kit; $rq = Join-Path $k 'required_shas.txt'; [IO.File]::WriteAllText($rq, (([IO.File]::ReadAllLines($rq) | Where-Object { $_ -notmatch '^FLIGHT_PY_SHA256=' }) -join "`n") + "`n", $utf8n); $g = Gates $k
Check 'A44' 'в required_shas.txt нет суммы flight.py (три суммы вместо четырёх): код 1, «четыре суммы»' ($g.Code -eq 1 -and $g.Text -match 'четыре суммы') $g.Text
$rqReal = [IO.File]::ReadAllText((Join-Path $IK 'required_shas.txt'))
Check 'A45' 'настоящий required_shas.txt: hover r6 a11b195c…, камера по умолчанию 4a15d699…, вариант dabd5076…, flight.py b69cc5e7… (0,9 м) (полные суммы)' ($rqReal -match 'HOVER_R6_SHA256=a11b195ce1507607967ff6a7402726d9eef7b4f12850a9e864f5ae27d1f513f7' -and $rqReal -match 'CAMERA_DEFAULT_SHA256=4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310' -and $rqReal -match 'CAMERA_VARIANT_SHA256=dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83' -and $rqReal -match 'FLIGHT_PY_SHA256=b69cc5e72509bbe2f141e48844b999e3a046ac6a78d28484239536b426c807b3') ''
$m5 = @([IO.File]::ReadAllLines((Join-Path $IK 'mavros_bp02_sources.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' })
Check 'A45' 'настоящий список MAVROS bp02: 5 исходников с суммами bp02; списка «сборок для Pi» в наборе нет (он был тестовым образцом m5)' ($m5.Count -eq 5 -and @($m5 | Where-Object { ($_ -split "`t")[2] -cmatch '^[0-9a-f]{64}$' }).Count -eq 5 -and -not (Test-Path (Join-Path $IK 'MAVROS_ARM64_SHA256SUMS.txt'))) ''
$tgt = [IO.File]::ReadAllText((Join-Path $IK 'image_target.conf'))
Check 'A46' 'настоящий image_target.conf: DEST_ROOT = /home/lb (источник: принятый набор s0b), BACKUP_ROOT остаётся TBD' ($tgt -match '(?m)^DEST_ROOT=/home/lb\s*$' -and $tgt -match '(?m)^BACKUP_ROOT=TBD\s*$' -and $tgt -match 's0b') ''
# ---------- B: .cmd с поддельными ssh и scp ----------
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh.cs'))) -OutputAssembly (Join-Path $FakeDir 'ssh.exe') -OutputType ConsoleApplication
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_scp.cs'))) -OutputAssembly (Join-Path $FakeDir 'scp.exe') -OutputType ConsoleApplication
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
function Run-I([string]$id, [string]$kitDir, [string]$cmdName, [string]$mode, [string]$stdinText, [string]$pcName = $realPc, [string]$cmdArgs = '') {
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), $mode)
    $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path $cl) { Remove-Item $cl }
    $inFile = Join-Path $Run ($id + '_stdin.txt'); [IO.File]::WriteAllText($inFile, $stdinText)
    $env:COMPUTERNAME = $pcName
    $so = Join-Path $Run ($id + '_console.txt')
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + (Join-Path $kitDir $cmdName) + '" ' + $cmdArgs + ' < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $env:COMPUTERNAME = $realPc
    $calls = @(); if (Test-Path $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    return @{ Code = $p.ExitCode; Calls = $calls; J = ($calls -join "`n") }
}
Clear-Params; New-FreshParams 'B1'
$k = New-Kit
$r = Run-I 'B1' $k '05_install_r2j.cmd' 'normal' "YES`r`n"
Check 'B1' 'условия выполнены, YES: код 0; порядок: имя дрона, scp, установка' ($r.Code -eq 0 -and $r.J -match '(?s)HOST_OK.*SCP.*image_install\.sh /tmp/img_\d+') ('code=' + $r.Code)
Check 'B1' 'временная папка /tmp/img_N создаётся новой; sudo не используется' ($r.J -match 'mkdir /tmp/img_\d+' -and -not ($r.J -match 'sudo')) ''
Check 'B1' 'на дрон идут payload, манифест, конфиг и image_install.sh' ($r.J -match 'payload' -and $r.J -match 'image_manifest\.final\.tsv' -and $r.J -match 'image_install\.sh\]') ''
$r = Run-I 'B2' $k '05_install_r2j.cmd' 'normal' "no`r`n"
Check 'B2' 'не YES: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-I 'B3' $k '05_install_r2j.cmd' 'normal' "YES`r`n" 'OTHER-PC'
Check 'B3' 'чужой ПК: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
$r = Run-I 'B4' $k '05_install_r2j.cmd' 'nodone' "YES`r`n"
Check 'B4' 'установка не дошла до конца: код 1' ($r.Code -eq 1) ('code=' + $r.Code)
$r = Run-I 'B5' $k '05_install_r2j.cmd' 'wrong_host' "YES`r`n"
Check 'B5' 'чужой дрон: код 1, scp и установки нет' ($r.Code -eq 1 -and -not ($r.J -match 'SCP') -and -not ($r.J -match 'image_install\.sh')) ''
$k2 = New-Kit; Remove-Item (Join-Path $k2 'gates\S2_S3_PASSED.txt')
$r = Run-I 'B6' $k2 '05_install_r2j.cmd' 'normal' "YES`r`n"
Check 'B6' 'нет S2/S3: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
Clear-Params; New-FreshParams 'B7' '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ===' '0'
$r = Run-I 'B7' $k '05_install_r2j.cmd' 'normal' "YES`r`n"
Check 'B7' 'COM_OBL_RC_ACT=0: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
$r = Run-I 'B8' $k '06_rollback_r2j.cmd' 'normal' "YES`r`n"
Check 'B8' 'откат: код 0, имя дрона, scp, image_rollback.sh' ($r.Code -eq 0 -and $r.J -match '(?s)HOST_OK.*SCP.*image_rollback\.sh /tmp/imgrb_\d+') ('code=' + $r.Code)
$r = Run-I 'B9' $k '06_rollback_r2j.cmd' 'normal' "no`r`n"
Check 'B9' 'откат без YES: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
$r = Run-I 'B12' $k '06_rollback_r2j.cmd' 'normal' "YES`r`n" $realPc '20261109_153000'
Check 'B12' 'r4: откат с явной меткой: метка уходит в команду на Pi, код 0' ($r.Code -eq 0 -and $r.J -match 'image_rollback\.sh /tmp/imgrb_\d+ 20261109_153000') ('code=' + $r.Code)
$r = Run-I 'B13' $k '06_rollback_r2j.cmd' 'normal' "YES`r`n" $realPc 'abc'
Check 'B13' 'r4: плохая метка «abc»: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
foreach ($n in '05_install_r2j.cmd', '06_rollback_r2j.cmd') {
    $lines = Get-Content -LiteralPath (Join-Path $IK $n) -Encoding UTF8
    $first = ($lines | Where-Object { $_ -notmatch '^@echo off|^chcp|^rem' } | Select-Object -First 1)
    Check 'B10' ($n + ': первая строка МЕНЯЕТ ДРОН: что, зачем, как вернуть') ($first -match '^echo МЕНЯЕТ ДРОН: .*Зачем: .*Как вернуть: ') $first
}
# ---------- V: вариант камеры dabd5076 (отдельная папка, только если владелец выберет) ----------
$CAMV = 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'
function New-CamKit {
    $k = New-Kit
    $cv = Join-Path $k 'camera_variant_dabd5076'
    Copy-Item -LiteralPath $CVA -Destination $cv -Recurse   # r6: копия из _aside на прежнее место в песочнице
    $p = Join-Path $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd'
    $lines = [IO.File]::ReadAllText($p) -split "`r`n"
    [IO.File]::WriteAllText($p, (($lines | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
    return $cv
}
function Set-VariantFlag([string]$cv, [string]$sha = '') {
    if ($sha -eq '') { $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $cv 'image_manifest.final.tsv')).Hash.ToLower() }
    [IO.File]::WriteAllText((Join-Path $cv 'gates\S2_S3_PASSED.txt'), ("S2=PASS`r`nS3=PASS`r`nДАТА=2026-11-11`r`nДОКАЗАТЕЛЬСТВО=тест (копия в песочнице)`r`nОБРАЗ_MANIFEST_SHA256=" + $sha + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
}
# Approve-Cam: разрешение владельца + флаг S2/S3 варианта (привязан к манифесту варианта); свежая сверка настроек кладётся отдельно (Clear-Params; New-FreshParams)
function Approve-Cam([string]$cv, [string]$sha = $CAMV) {
    [IO.File]::WriteAllText((Join-Path $cv 'gates\CAMERA_DABD5076_APPROVED.txt'), ("ВЛАДЕЛЕЦ_ВЫБРАЛ=камера dabd5076`r`nДАТА=2026-11-11 09:00`r`nСЛОВА_ВЛАДЕЛЬЦА=тест`r`nCAMERA_SHA256=" + $sha + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
    Set-VariantFlag $cv
}
Clear-Params; New-FreshParams 'V0'
function CamGates([string]$cv) {
    $o = (& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $cv 'check_gates_camera.ps1') -Kit $cv 2>&1 | Out-String)
    return @{ Code = $LASTEXITCODE; Text = $o }
}
$g = CamGates $CVA
Check 'V1' 'r6: настоящая папка варианта (теперь в _aside) заблокирована: нет разрешения и нет ..\image_target.conf рядом: код 1' ($g.Code -eq 1 -and $g.Text -match 'CAMERA_DABD5076_APPROVED' -and $g.Text -match 'image_target\.conf') $g.Text
$cv = New-CamKit; Approve-Cam $cv; $g = CamGates $cv
Check 'V2' 'разрешение чата 1, DEST_ROOT и BACKUP_ROOT заполнены, манифест из одной строки, payload сходится: код 0' ($g.Code -eq 0 -and $g.Text -match 'выполнены') $g.Text
$cv = New-CamKit; Approve-Cam $cv; $ap = Join-Path $cv 'gates\CAMERA_DABD5076_APPROVED.txt'
[IO.File]::WriteAllText($ap, (([IO.File]::ReadAllLines($ap) | Where-Object { $_ -notmatch '^CAMERA_SHA256=' }) -join "`r`n") + "`r`n", $utf8); $g = CamGates $cv
Check 'V3' 'в разрешении нет строки CAMERA_SHA256=: код 1' ($g.Code -eq 1 -and $g.Text -match 'CAMERA_SHA256') $g.Text
$cv = New-CamKit; Approve-Cam $cv ('0' * 64); $g = CamGates $cv
Check 'V3' 'в разрешении чужой sha камеры: код 1' ($g.Code -eq 1 -and $g.Text -match 'CAMERA_SHA256') $g.Text
$cv = New-CamKit; Approve-Cam $cv; $ap = Join-Path $cv 'gates\CAMERA_DABD5076_APPROVED.txt'
[IO.File]::WriteAllText($ap, (([IO.File]::ReadAllLines($ap) | Where-Object { $_ -notmatch '^СОЗДАЛ=' }) -join "`r`n") + "`r`n", $utf8); $g = CamGates $cv
Check 'V3' 'в разрешении нет «СОЗДАЛ=чат 1»: код 1' ($g.Code -eq 1 -and $g.Text -match 'СОЗДАЛ') $g.Text
# усиление 19:19: гейт варианта не слабее основного (S2/S3 для ЭТОГО образа, свежая сверка настроек, COM_OBL_RC_ACT = 4)
$cv = New-CamKit; Approve-Cam $cv; Remove-Item (Join-Path $cv 'gates\S2_S3_PASSED.txt'); $g = CamGates $cv
Check 'V13' 'у варианта нет своего S2_S3_PASSED.txt (флаг основного образа не годится): код 1' ($g.Code -eq 1 -and $g.Text -match 'S2_S3_PASSED') $g.Text
$cv = New-CamKit; Approve-Cam $cv; Set-VariantFlag $cv ('0' * 64); $g = CamGates $cv
Check 'V13' 'флаг S2/S3 варианта привязан к другому манифесту: код 1, «другого образа»' ($g.Code -eq 1 -and $g.Text -match 'другого образа') $g.Text
$cv = New-CamKit; Approve-Cam $cv; $fp = Join-Path $cv 'gates\S2_S3_PASSED.txt'
[IO.File]::WriteAllText($fp, (([IO.File]::ReadAllLines($fp) | Where-Object { $_ -notmatch '^S3=PASS' }) -join "`r`n") + "`r`n", $utf8); $g = CamGates $cv
Check 'V13' 'во флаге варианта нет S3=PASS: код 1' ($g.Code -eq 1 -and $g.Text -match 'S3=PASS') $g.Text
$cv = New-CamKit; Approve-Cam $cv; Set-VariantFlag $cv ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $cv 'image_manifest.final.tsv')).Hash.ToUpper()); $g = CamGates $cv
Check 'V13' 'sha манифеста во флаге варианта заглавными: код 1 (строгое сравнение)' ($g.Code -eq 1) $g.Text
Clear-Params
$cv = New-CamKit; Approve-Cam $cv; $g = CamGates $cv
Check 'V14' 'нет сверки настроек: код 1, «Нет сверки настроек»' ($g.Code -eq 1 -and $g.Text -match 'Нет сверки настроек') $g.Text
New-FreshParams 'V14a' '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ===' '4' 45; $g = CamGates $cv
Check 'V14' 'сверка настроек старше 30 минут: код 1, «старая»' ($g.Code -eq 1 -and $g.Text -match 'старая') $g.Text
Clear-Params; New-FreshParams 'V14b' '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0) ===' '0'; $g = CamGates $cv
Check 'V14' 'COM_OBL_RC_ACT на дроне 0, не 4: код 1 (правило 14)' ($g.Code -eq 1 -and $g.Text -match 'COM_OBL_RC_ACT') $g.Text
Clear-Params; New-FreshParams 'V14c' '=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 1 ==='; $g = CamGates $cv
Check 'V14' 'сверка с отличиями: код 1, «не «СОВПАДАЕТ»»' ($g.Code -eq 1 -and $g.Text -match 'СОВПАДАЕТ') $g.Text
Clear-Params; New-FreshParams 'V14d' '=== СОВПАДАЕТ: прочитано 1000 из 1000, отличий нет (из таблицы MAVROS 1000, из запасного потока 0) ==='; $g = CamGates $cv
Check 'V14' 'прочитано 1000 настроек, а в основе 1107: код 1' ($g.Code -eq 1 -and $g.Text -match 'в основе компонента 1 их 1107') $g.Text
Clear-Params; New-FreshParams 'V14e'; $g = CamGates $cv
Check 'V14' 'всё в порядке (S2/S3 варианта, свежая сверка, разрешение, цель, манифест): код 0' ($g.Code -eq 0) $g.Text
$cv = New-CamKit; Approve-Cam $cv; Add-Content -LiteralPath (Join-Path $cv 'image_manifest.final.tsv') -Value ("extra.py`t" + ('a' * 64)) -Encoding UTF8; $g = CamGates $cv
Check 'V4' 'в манифесте варианта две строки (в камеру добавили ещё файл): код 1' ($g.Code -eq 1 -and $g.Text -match 'ровно одна строка') $g.Text
$cv = New-CamKit; Approve-Cam $cv; Add-Content -LiteralPath (Join-Path $cv 'payload\ros2_ws\src\bumblebee\src\python\camera_fix.py') -Value '# tampered' -Encoding UTF8; $g = CamGates $cv
Check 'V4' 'файл camera_fix.py в payload варианта изменён: код 1, sha не сходится' ($g.Code -eq 1 -and $g.Text -match 'не сходится') $g.Text
$cv = New-CamKit; Approve-Cam $cv; [IO.File]::WriteAllText((Join-Path (Split-Path -Parent $cv) 'image_target.conf'), "DEST_ROOT=TBD`nBACKUP_ROOT=/tmp/bak_test`n", $utf8n); $g = CamGates $cv
Check 'V4' 'DEST_ROOT = TBD в image_target.conf: код 1' ($g.Code -eq 1 -and $g.Text -match 'DEST_ROOT') $g.Text
$cv = New-CamKit; Approve-Cam $cv; $mp = Join-Path $cv 'image_manifest.final.tsv'
[IO.File]::WriteAllText($mp, ("ros2_ws/src/bumblebee/src/python/other_file.py`t" + $CAMV + "`n"), $utf8n); $g = CamGates $cv
Check 'V4' 'строка манифеста варианта не про camera_fix.py: код 1' ($g.Code -eq 1 -and $g.Text -match 'Строка манифеста варианта') $g.Text
$realSha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $CVA 'payload\ros2_ws\src\bumblebee\src\python\camera_fix.py')).Hash.ToLower()
$realMan = [IO.File]::ReadAllText((Join-Path $CVA 'image_manifest.final.tsv'))
Check 'V5' 'настоящий payload варианта: sha256 camera_fix.py = dabd5076… и он же в манифесте варианта' ($realSha -eq $CAMV -and $realMan -match $CAMV -and $realMan -match 'camera_fix\.py') $realSha
# 05v с поддельными ssh и scp
$cv = New-CamKit; Approve-Cam $cv
$r = Run-I 'V6' $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' 'normal' "YES`r`n"
$stg = @(Get-ChildItem -LiteralPath $OutDir -Directory -Filter 'stage_camera_*' -ErrorAction SilentlyContinue)
Check 'V6' '05v: разрешение и условия есть, YES: код 0; порядок: имя дрона, scp, установка' ($r.Code -eq 0 -and $r.J -match '(?s)HOST_OK.*SCP.*image_install\.sh /tmp/img_\d+') ('code=' + $r.Code + ' ' + $r.J)
Check 'V6' '05v: на дрон идёт подготовленная папка stage_camera_* (payload, манифест варианта, конфиг и image_install.sh из папки выше), а не основной payload' ($r.J -match 'stage_camera_\d+\\payload' -and $r.J -match 'stage_camera_\d+\\image_manifest\.final\.tsv' -and $r.J -match 'stage_camera_\d+\\image_install\.sh' -and $stg.Count -ge 1 -and (Test-Path -LiteralPath (Join-Path $stg[0].FullName 'payload\ros2_ws\src\bumblebee\src\python\camera_fix.py')) -and ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stg[0].FullName 'payload\ros2_ws\src\bumblebee\src\python\camera_fix.py')).Hash.ToLower() -eq $CAMV) -and -not (Test-Path -LiteralPath (Join-Path $stg[0].FullName 'payload\ros2_ws\src\bumblebee\examples\flight\hover.py'))) ($r.J + ' stage=' + $stg.Count)
$cv = New-CamKit
$r = Run-I 'V7' $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' 'normal' "YES`r`n"
Check 'V7' '05v без разрешения: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$cv = New-CamKit; Approve-Cam $cv
$r = Run-I 'V8' $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' 'normal' "no`r`n"
Check 'V8' '05v: не YES: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-I 'V9' $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' 'normal' "YES`r`n" 'OTHER-PC'
Check 'V9' '05v: чужой ПК: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
$r = Run-I 'V10' $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' 'wrong_host' "YES`r`n"
Check 'V10' '05v: чужой дрон: код 1, scp и установки нет' ($r.Code -eq 1 -and -not ($r.J -match 'SCP') -and -not ($r.J -match 'image_install\.sh')) ''
$r = Run-I 'V11' $cv '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' 'nodone' "YES`r`n"
Check 'V11' '05v: установка не дошла до конца: код 1' ($r.Code -eq 1) ('code=' + $r.Code)
$vl = Get-Content -LiteralPath (Join-Path $CVA '05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd') -Encoding UTF8
$vfirst = ($vl | Where-Object { $_ -notmatch '^@echo off|^chcp|^rem' } | Select-Object -First 1)
Check 'V12' '05v: первая строка МЕНЯЕТ ДРОН: что (camera_fix dabd5076), «ТОЛЬКО ЕСЛИ ВЛАДЕЛЕЦ ВЫБРАЛ», зачем, PENDING, как вернуть (06_rollback_r2j.cmd)' ($vfirst -match '^echo МЕНЯЕТ ДРОН: ' -and $vfirst -match 'dabd5076' -and $vfirst -match 'ТОЛЬКО ЕСЛИ ВЛАДЕЛЕЦ ВЫБРАЛ' -and $vfirst -match 'Зачем: ' -and $vfirst -match 'PENDING' -and $vfirst -match 'Как вернуть: .*06_rollback_r2j\.cmd') $vfirst
$env:PATH = $oldPath

# ---------- C: Pi-скрипты в WSL на поддельном корне ----------
function Wsl([string]$cmd) { $o = & wsl.exe -e bash -c $cmd 2>&1 | Out-String; return @{ Code = $LASTEXITCODE; Text = $o } }
function WslPath([string]$p) { return (& wsl.exe wslpath -a ($p -replace '\\', '/')).Trim() }
$sh1 = WslPath (Join-Path $IK 'image_install.sh'); $sh2 = WslPath (Join-Path $IK 'image_rollback.sh')
$HN = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'
function New-Stage([string]$name) {
    $s = Join-Path $Run $name
    Copy-Item -LiteralPath (New-Kit) -Destination $s -Recurse
    return $s
}
$w = (Wsl 'echo ok').Text
if ($w -notmatch 'ok') { Check 'C0' 'WSL доступен' $false $w }
else {
    $stage = New-Stage 'stage1'
    $sp = WslPath $stage
    $root = "/tmp/bb_img_test_$([guid]::NewGuid().ToString('N').Substring(0,6))"
    [IO.File]::WriteAllText((Join-Path $stage 'image_target.conf'), "DEST_ROOT=$root/dest`nBACKUP_ROOT=$root/bak`n", $utf8n)
    Wsl "mkdir -p $root/dest/sub; printf 'OLD A\n' > $root/dest/a.txt" | Out-Null
    $i = Wsl "$HN bash '$sh1' '$sp'"
    Check 'C1' 'установка: код 0, маркер BB_IMAGE_INSTALL_DONE' ($i.Code -eq 0 -and $i.Text -match 'BB_IMAGE_INSTALL_DONE') $i.Text
    $a = (Wsl "cat $root/dest/a.txt").Text.Trim(); $b = (Wsl "cat $root/dest/sub/b.txt").Text.Trim()
    Check 'C1' 'файлы на месте: a.txt новый, sub/b.txt создан' ($a -eq 'file a' -and $b -eq 'file b') ($a + '|' + $b)
    $bk = (Wsl "ls $root/bak").Text.Trim()
    Check 'C1' 'резерв создан: метка времени, старый a.txt сохранён, b.txt в списке новых' ($bk -match '^\d{8}_\d{6}$' -and (Wsl "cat $root/bak/$bk/files/a.txt").Text.Trim() -eq 'OLD A' -and (Wsl "cat $root/bak/$bk/NEW_FILES.txt").Text -match 'sub/b\.txt') $bk
    $rb = Wsl "$HN bash '$sh2' '$sp'"
    Check 'C2' 'откат: код 0, маркер BB_IMAGE_ROLLBACK_DONE' ($rb.Code -eq 0 -and $rb.Text -match 'BB_IMAGE_ROLLBACK_DONE') $rb.Text
    Check 'C2' 'a.txt снова старый, новый sub/b.txt перенесён в сторону, не удалён' ((Wsl "cat $root/dest/a.txt").Text.Trim() -eq 'OLD A' -and (Wsl "test -e $root/dest/sub/b.txt && echo yes || echo no").Text.Trim() -eq 'no' -and (Wsl "cat $root/bak/$bk/rolled_back_new/sub/b.txt").Text.Trim() -eq 'file b') ''
    $rb2 = Wsl "$HN bash '$sh2' '$sp'"
    Check 'C2' 'повторный откат той же копии отказывает' ($rb2.Code -ne 0 -and $rb2.Text -match 'already rolled back') $rb2.Text

    # решение чата 1 (22:00): установщик на Pi отказывает, если в манифесте fcu_detect.py (до любых изменений)
    $stageF = New-Stage 'stageF'; $spF = WslPath $stageF
    [IO.File]::WriteAllText((Join-Path $stageF 'image_target.conf'), "DEST_ROOT=$root/destF`nBACKUP_ROOT=$root/bakF`n", $utf8n)
    New-Item -ItemType Directory -Path (Join-Path $stageF 'payload\scripts') -Force | Out-Null; [IO.File]::WriteAllText((Join-Path $stageF 'payload\scripts\fcu_detect.py'), "fcu fix`n", $utf8n)
    $fsha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stageF 'payload\scripts\fcu_detect.py')).Hash.ToLower()
    [IO.File]::AppendAllText((Join-Path $stageF 'image_manifest.final.tsv'), ("scripts/fcu_detect.py`t" + $fsha + "`n"), $utf8n)
    $x = Wsl "$HN bash '$sh1' '$spF'"
    Check 'C5' 'установщик: в манифесте fcu_detect.py: код 1, «fcu_detect.py must not be installed», DEST и BACKUP не созданы' ($x.Code -eq 1 -and $x.Text -match 'fcu_detect\.py must not be installed' -and (Wsl "test -e $root/destF -o -e $root/bakF && echo yes || echo no").Text.Trim() -eq 'no') $x.Text
    # r3 (замечание проверки 11.11): установщик не принимает путь ./a.txt (повтор a.txt, который проверка повторов по тексту не ловила)
    $stageG = New-Stage 'stageG'; $spG = WslPath $stageG
    [IO.File]::WriteAllText((Join-Path $stageG 'image_target.conf'), "DEST_ROOT=$root/destG`nBACKUP_ROOT=$root/bakG`n", $utf8n)
    $gsha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $stageG 'payload\a.txt')).Hash.ToLower()
    [IO.File]::AppendAllText((Join-Path $stageG 'image_manifest.final.tsv'), ("./a.txt`t" + $gsha + "`n"), $utf8n)
    $x = Wsl "$HN bash '$sh1' '$spG'"
    Check 'C6' 'установщик: в манифесте ./a.txt рядом с a.txt: код 1, «unsafe path», DEST и BACKUP не созданы' ($x.Code -eq 1 -and $x.Text -match 'unsafe path' -and (Wsl "test -e $root/destG -o -e $root/bakG && echo yes || echo no").Text.Trim() -eq 'no') $x.Text

    # чужой хост (без подмены hostname)
    $stage2 = New-Stage 'stage2'; $sp2 = WslPath $stage2
    [IO.File]::WriteAllText((Join-Path $stage2 'image_target.conf'), "DEST_ROOT=$root/dest2`nBACKUP_ROOT=$root/bak2`n", $utf8n)
    $x = Wsl "bash '$sh1' '$sp2'"
    Check 'C3' 'не тот хост: код 1, ничего не создано' ($x.Code -eq 1 -and $x.Text -match 'wrong host' -and (Wsl "test -e $root/dest2 && echo yes || echo no").Text.Trim() -eq 'no') $x.Text
    # повреждённый payload: отказ до любых изменений
    Add-Content -LiteralPath (Join-Path $stage2 'payload\a.txt') -Value 'tampered'
    $x = Wsl "$HN bash '$sh1' '$sp2'"
    Check 'C4' 'SHA256 payload не сходится: код 1, DEST и BACKUP не созданы' ($x.Code -eq 1 -and $x.Text -match 'sha256 mismatch' -and (Wsl "test -e $root/dest2 -o -e $root/bak2 && echo yes || echo no").Text.Trim() -eq 'no') $x.Text
    # TBD в конфиге
    $stage3 = New-Stage 'stage3'; $sp3 = WslPath $stage3
    [IO.File]::WriteAllText((Join-Path $stage3 'image_target.conf'), "DEST_ROOT=TBD`nBACKUP_ROOT=$root/bak3`n", $utf8n)
    $x = Wsl "$HN bash '$sh1' '$sp3'"
    Check 'C5' 'DEST_ROOT=TBD: код 1' ($x.Code -eq 1 -and $x.Text -match 'TBD') $x.Text
    # небезопасный путь в манифесте
    $stage4 = New-Stage 'stage4'; $sp4 = WslPath $stage4
    [IO.File]::WriteAllText((Join-Path $stage4 'image_target.conf'), "DEST_ROOT=$root/dest4`nBACKUP_ROOT=$root/bak4`n", $utf8n)
    Add-Content -LiteralPath (Join-Path $stage4 'image_manifest.final.tsv') -Value ("../x.txt`t" + ('a' * 64))
    $x = Wsl "$HN bash '$sh1' '$sp4'"
    Check 'C6' 'путь с .. в манифесте: код 1, unsafe path' ($x.Code -eq 1 -and $x.Text -match 'unsafe path') $x.Text
    # ===== r2 =====
    # C8 (A-7) + C9 (A-8): режимы файлов и CRLF в конфиге и манифесте
    $stage5 = Join-Path $Run 'stage5'; Copy-Item -LiteralPath (New-Kit) -Destination $stage5 -Recurse; $sp5 = WslPath $stage5
    $pl5 = Join-Path $stage5 'payload'
    [IO.File]::WriteAllText((Join-Path $pl5 'run.sh'), "#!/bin/bash`necho run`n", $utf8n)
    [IO.File]::WriteAllText((Join-Path $pl5 'keep.sh'), "echo keep`n", $utf8n)
    [IO.File]::WriteAllText((Join-Path $pl5 'mode.sh'), "echo mode`n", $utf8n)
    [IO.File]::WriteAllText((Join-Path $pl5 'data.txt'), "data`n", $utf8n)
    $mrows = @()
    foreach ($n in 'a.txt', 'sub/b.txt', 'run.sh', 'keep.sh', 'mode.sh', 'data.txt') {
        $h = (Get-FileHash -Algorithm SHA256 (Join-Path $pl5 ($n -replace '/', '\'))).Hash.ToLower()
        $row = $n + "`t" + $h; if ($n -eq 'mode.sh') { $row += "`t700" }
        $mrows += $row
    }
    $root5 = "/tmp/bb_img_test5_$([guid]::NewGuid().ToString('N').Substring(0,6))"
    # конфиг и манифест с CRLF (как после правки в Windows)
    [IO.File]::WriteAllText((Join-Path $stage5 'image_manifest.final.tsv'), (($mrows -join "`r`n") + "`r`n"), $utf8n)
    [IO.File]::WriteAllText((Join-Path $stage5 'image_target.conf'), "DEST_ROOT=$root5/dest`r`nBACKUP_ROOT=$root5/bak`r`n", $utf8n)
    Wsl "mkdir -p $root5/dest; printf 'OLD A\n' > $root5/dest/a.txt; printf 'old keep\n' > $root5/dest/keep.sh; chmod 755 $root5/dest/keep.sh; printf 'old mode\n' > $root5/dest/mode.sh; chmod 644 $root5/dest/mode.sh" | Out-Null
    $i5 = Wsl "$HN bash '$sh1' '$sp5'"
    Check 'C9' 'A-8: конфиг и манифест с CRLF: установка проходит, код 0' ($i5.Code -eq 0 -and $i5.Text -match 'BB_IMAGE_INSTALL_DONE') $i5.Text
    Check 'C9' 'A-8: каталоги без символа \r в имени (нет dest с лишним символом)' ((Wsl "ls $root5 | wc -l").Text.Trim() -eq '2' -and (Wsl "test -f $root5/dest/data.txt && echo yes || echo no").Text.Trim() -eq 'yes') ((Wsl "ls -la $root5").Text)
    $m = { param($f) (Wsl "stat -c %a $root5/dest/$f").Text.Trim() }
    Check 'C8' 'A-7: новый файл с #! получает 755' ((& $m 'run.sh') -eq '755') (& $m 'run.sh')
    Check 'C8' 'A-7: старый исполняемый keep.sh (755) остаётся 755, хотя в payload он обычный' ((& $m 'keep.sh') -eq '755') (& $m 'keep.sh')
    Check 'C8' 'A-7: режим из 3-й колонки манифеста (mode.sh 700) применён, старые 644 заменены' ((& $m 'mode.sh') -eq '700') (& $m 'mode.sh')
    Check 'C8' 'A-7: новый обычный файл без #! получает 644' ((& $m 'data.txt') -eq '644') (& $m 'data.txt')
    $bk5 = (Wsl "ls $root5/bak").Text.Trim()
    Check 'C8' 'A-7: резерв сохранил режим старого keep.sh (755)' ((Wsl "stat -c %a $root5/bak/$bk5/files/keep.sh").Text.Trim() -eq '755') ''
    # C10 (A-9): перед откатом сохраняется установленная версия
    $before = (Wsl "cat $root5/dest/a.txt; cat $root5/dest/mode.sh").Text
    $rb5 = Wsl "$HN bash '$sh2' '$sp5'"
    Check 'C10' 'откат прошёл: код 0, маркер, указана папка с сохранённой установленной версией' ($rb5.Code -eq 0 -and $rb5.Text -match 'BB_IMAGE_ROLLBACK_DONE' -and $rb5.Text -match 'saved_installed=.*before_rollback_') $rb5.Text
    $brd = (Wsl "ls -d $root5/bak/$bk5/before_rollback_*").Text.Trim()
    Check 'C10' 'A-9: до отката сохранены установленные a.txt (file a) и mode.sh (режим 700)' ((Wsl "cat $brd/files/a.txt").Text.Trim() -eq 'file a' -and (Wsl "stat -c %a $brd/files/mode.sh").Text.Trim() -eq '700' -and (Wsl "cat $brd/files/mode.sh").Text.Trim() -eq 'echo mode') $brd
    Check 'C10' 'A-9: сохранены и новые файлы образа (run.sh, data.txt, sub/b.txt), которые откат уберёт в сторону' ((Wsl "test -f $brd/files/run.sh -a -f $brd/files/data.txt -a -f $brd/files/sub/b.txt && echo yes || echo no").Text.Trim() -eq 'yes') ''
    Check 'C10' 'A-9: files.sha256 сохранённой версии сходится' ((Wsl "cd $brd/files && sha256sum -c --quiet $brd/files.sha256 && echo OK").Text -match 'OK') ''
    Check 'C10' 'откат вернул старые a.txt и mode.sh (режим 644), keep.sh остался 755' ((Wsl "cat $root5/dest/a.txt").Text.Trim() -eq 'OLD A' -and (& $m 'mode.sh') -eq '644' -and (& $m 'keep.sh') -eq '755') ''
    Check 'C10' 'откат: run.sh, data.txt, sub/b.txt убраны с места и лежат в rolled_back_new' ((Wsl "test ! -e $root5/dest/run.sh -a ! -e $root5/dest/data.txt -a -f $root5/bak/$bk5/rolled_back_new/run.sh && echo yes || echo no").Text.Trim() -eq 'yes') ''
    # плохой режим в манифесте: отказ до любых изменений
    $stage6 = Join-Path $Run 'stage6'; Copy-Item -LiteralPath (New-Kit) -Destination $stage6 -Recurse; $sp6 = WslPath $stage6
    $m6 = Join-Path $stage6 'image_manifest.final.tsv'
    $l6 = [IO.File]::ReadAllText($m6) -split "`n" | Where-Object { $_ -ne '' }
    [IO.File]::WriteAllText($m6, (($l6 | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`t9zz" } else { $_ } }) -join "`n") + "`n", $utf8n)
    [IO.File]::WriteAllText((Join-Path $stage6 'image_target.conf'), "DEST_ROOT=$root5/dest6`nBACKUP_ROOT=$root5/bak6`n", $utf8n)
    $x = Wsl "$HN bash '$sh1' '$sp6'"
    Check 'C8' 'A-7: неверный режим 9zz в манифесте: код 1, DEST и BACKUP не созданы' ($x.Code -eq 1 -and $x.Text -match 'bad mode' -and (Wsl "test -e $root5/dest6 -o -e $root5/bak6 && echo yes || echo no").Text.Trim() -eq 'no') $x.Text
    # ===== r3 =====
    function Stage-R3([string]$name, [string]$confText) {
        $s = Join-Path $Run $name; Copy-Item -LiteralPath (New-Kit) -Destination $s -Recurse
        [IO.File]::WriteAllText((Join-Path $s 'image_target.conf'), $confText, $utf8n)
        return $s
    }
    $root7 = "/tmp/bb_img_test7_$([guid]::NewGuid().ToString('N').Substring(0,6))"
    # C11 (O-1): установка только НОВЫХ файлов, потом откат (files.sha256 пустой)
    $s11 = Stage-R3 'stage11' "DEST_ROOT=$root7/d11`nBACKUP_ROOT=$root7/b11`n"; $sp11 = WslPath $s11
    $i = Wsl "$HN bash '$sh1' '$sp11'"
    Check 'C11' 'O-1: установка только новых файлов: код 0' ($i.Code -eq 0 -and $i.Text -match 'BB_IMAGE_INSTALL_DONE' -and $i.Text -match '0 old files, 10 new files') $i.Text
    $rb = Wsl "$HN bash '$sh2' '$sp11'"
    Check 'C11' 'O-1: откат при пустом files.sha256: код 0, новые файлы убраны в rolled_back_new, не удалены' ($rb.Code -eq 0 -and $rb.Text -match 'BB_IMAGE_ROLLBACK_DONE' -and (Wsl "test ! -e $root7/d11/a.txt -a ! -e $root7/d11/sub/b.txt && echo yes || echo no").Text.Trim() -eq 'yes' -and (Wsl "ls $root7/b11/*/rolled_back_new/a.txt").Text -match 'a\.txt') $rb.Text
    # C12 (O-2): режим 0755 в манифесте
    $s12 = Stage-R3 'stage12' "DEST_ROOT=$root7/d12`nBACKUP_ROOT=$root7/b12`n"; $sp12 = WslPath $s12
    $m12 = Join-Path $s12 'image_manifest.final.tsv'
    $l12 = [IO.File]::ReadAllText($m12) -split "`n" | Where-Object { $_ -ne '' }
    [IO.File]::WriteAllText($m12, (($l12 | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`t0755" } else { $_ } }) -join "`n") + "`n", $utf8n)
    $i = Wsl "$HN bash '$sh1' '$sp12'"
    Check 'C12' 'O-2: режим 0755 в манифесте: установка код 0, файл с режимом 755' ($i.Code -eq 0 -and (Wsl "stat -c %a $root7/d12/a.txt").Text.Trim() -eq '755') $i.Text
    $rb = Wsl "$HN bash '$sh2' '$sp12'"
    Check 'C12' 'O-2: откат после неё проходит' ($rb.Code -eq 0) $rb.Text
    # C13 (O-3): символьная ссылка на месте файла
    $s13 = Stage-R3 'stage13' "DEST_ROOT=$root7/d13`nBACKUP_ROOT=$root7/b13`n"; $sp13 = WslPath $s13
    Wsl "mkdir -p $root7/d13 && printf 'real\n' > $root7/real.txt && ln -s $root7/real.txt $root7/d13/a.txt" | Out-Null
    $i = Wsl "$HN bash '$sh1' '$sp13'"
    Check 'C13' 'O-3: на месте a.txt символьная ссылка: установка отказывает (код 1), ссылка и цель целы, резерв не создан' ($i.Code -eq 1 -and $i.Text -match 'symbolic link' -and (Wsl "test -L $root7/d13/a.txt && cat $root7/real.txt").Text.Trim() -eq 'real' -and (Wsl "test -e $root7/b13 && echo yes || echo no").Text.Trim() -eq 'no') $i.Text
    # C14 (Н-2, r4): новая папка резерва неполная (установка упала на резервировании). Тихо откатывать предыдущую установку нельзя.
    $s14 = Stage-R3 'stage14' "DEST_ROOT=$root7/d14`nBACKUP_ROOT=$root7/b14`n"; $sp14 = WslPath $s14
    $i = Wsl "$HN bash '$sh1' '$sp14'"
    $lab14 = ([regex]::Match($i.Text, 'BB_IMAGE_INSTALL_DONE (\d{8}_\d{6})')).Groups[1].Value
    Wsl "mkdir -p $root7/b14/29990101_000000/files" | Out-Null
    $rb = Wsl "$HN bash '$sh2' '$sp14'"
    Check 'C14' 'Н-2: самая новая папка резерва неполная: откат ОСТАНАВЛИВАЕТСЯ (код 1), называет её и метку предыдущей, ничего не откатил' ($i.Code -eq 0 -and $rb.Code -eq 1 -and $rb.Text -match 'newest backup folder 29990101_000000 is incomplete' -and $rb.Text -match "previous complete backup is: $lab14" -and (Wsl "test -e $root7/d14/a.txt && echo yes || echo no").Text.Trim() -eq 'yes') $rb.Text
    $rb = Wsl "$HN bash '$sh2' '$sp14' $lab14"
    Check 'C14' 'Н-2: с явной меткой предыдущей установки откат проходит (код 0)' ($rb.Code -eq 0 -and $rb.Text -match 'BB_IMAGE_ROLLBACK_DONE') $rb.Text
    $rb = Wsl "$HN bash '$sh2' '$sp14' '../x'"
    Check 'C14' 'Н-2: метка с путём «../x» отвергается (код 1)' ($rb.Code -eq 1 -and $rb.Text -match 'bad backup label') $rb.Text
    # C14c: маркер BACKUP_FAILED (установка упала при резервировании) тоже делает папку неполной
    $s14c = Stage-R3 'stage14c' "DEST_ROOT=$root7/d14c`nBACKUP_ROOT=$root7/b14c`n"; $sp14c = WslPath $s14c
    $i = Wsl "$HN bash '$sh1' '$sp14c'"
    $lab = ([regex]::Match($i.Text, 'BB_IMAGE_INSTALL_DONE (\d{8}_\d{6})')).Groups[1].Value
    Wsl "touch $root7/b14c/$lab/BACKUP_FAILED" | Out-Null
    $rb = Wsl "$HN bash '$sh2' '$sp14c'"
    Check 'C14c' 'Н-2: папка с маркером BACKUP_FAILED считается неполной: STOP' ($rb.Code -eq 1 -and $rb.Text -match 'incomplete') $rb.Text
    # C18 (Н-1): files.sha256 обнулён, хотя старые файлы сохранены: откат не должен считать, что старых файлов не было
    $s18 = Stage-R3 'stage18' "DEST_ROOT=$root7/d18`nBACKUP_ROOT=$root7/b18`n"; $sp18 = WslPath $s18
    Wsl "mkdir -p $root7/d18 && printf 'OLD A\n' > $root7/d18/a.txt" | Out-Null
    $i = Wsl "$HN bash '$sh1' '$sp18'"
    $lab = ([regex]::Match($i.Text, 'BB_IMAGE_INSTALL_DONE (\d{8}_\d{6})')).Groups[1].Value
    Wsl ": > $root7/b18/$lab/files.sha256" | Out-Null
    $rb = Wsl "$HN bash '$sh2' '$sp18'"
    Check 'C18' 'Н-1: files.sha256 обнулён при сохранённом старом a.txt: откат STOP (код 2, «inconsistent»), a.txt остаётся новым' ($i.Code -eq 0 -and $rb.Code -eq 2 -and $rb.Text -match 'inconsistent' -and (Wsl "cat $root7/d18/a.txt").Text.Trim() -eq 'file a') $rb.Text
    # C19 (Н-3): манифест без завершающего перевода строки
    $s19 = Stage-R3 'stage19' "DEST_ROOT=$root7/d19`nBACKUP_ROOT=$root7/b19`n"; $sp19 = WslPath $s19
    $m19 = Join-Path $s19 'image_manifest.final.tsv'
    [IO.File]::WriteAllText($m19, ([IO.File]::ReadAllText($m19).TrimEnd("`n")), $utf8n)
    $i = Wsl "$HN bash '$sh1' '$sp19'"
    Check 'C19' 'Н-3: манифест без \n в конце: ставятся все файлы (в том числе a.txt и sub/b.txt, последняя строка манифеста не теряется), files=10' ($i.Code -eq 0 -and $i.Text -match 'files=10' -and (Wsl "test -f $root7/d19/a.txt -a -f $root7/d19/sub/b.txt && echo yes || echo no").Text.Trim() -eq 'yes') $i.Text
    # C20: один путь дважды в манифесте
    $s20 = Stage-R3 'stage20' "DEST_ROOT=$root7/d20`nBACKUP_ROOT=$root7/b20`n"; $sp20 = WslPath $s20
    $m20 = Join-Path $s20 'image_manifest.final.tsv'
    $l20 = [IO.File]::ReadAllText($m20) -split "`n" | Where-Object { $_ -ne '' }
    [IO.File]::WriteAllText($m20, (($l20 + ($l20 | Where-Object { $_ -match '^a\.txt' })) -join "`n") + "`n", $utf8n)
    $x = Wsl "$HN bash '$sh1' '$sp20'"
    Check 'C20' 'r4: один путь дважды в манифесте: STOP, ничего не создано' ($x.Code -eq 1 -and $x.Text -match 'listed twice' -and (Wsl "test -e $root7/d20 -o -e $root7/b20 && echo yes || echo no").Text.Trim() -eq 'no') $x.Text    # C15: BOM и CRLF в конфиге и манифесте
    $s15 = Stage-R3 'stage15' ''; $sp15 = WslPath $s15
    $bom = New-Object Text.UTF8Encoding($true)
    [IO.File]::WriteAllText((Join-Path $s15 'image_target.conf'), "DEST_ROOT=$root7/d15`r`nBACKUP_ROOT=$root7/b15`r`n", $bom)
    $m15 = Join-Path $s15 'image_manifest.final.tsv'
    [IO.File]::WriteAllText($m15, ([IO.File]::ReadAllText($m15) -replace "`n", "`r`n"), $bom)
    $i = Wsl "$HN bash '$sh1' '$sp15'"
    Check 'C15' 'Ж-5: конфиг и манифест с BOM и CRLF: установка проходит' ($i.Code -eq 0 -and $i.Text -match 'BB_IMAGE_INSTALL_DONE') $i.Text
    # C16/C17: относительный корень, setuid
    $s16 = Stage-R3 'stage16' "DEST_ROOT=relative/dest`nBACKUP_ROOT=$root7/b16`n"; $sp16 = WslPath $s16
    $x = Wsl "$HN bash '$sh1' '$sp16'"
    Check 'C16' 'Ж-6: DEST_ROOT не абсолютный: код 1' ($x.Code -eq 1 -and $x.Text -match 'absolute') $x.Text
    $s17 = Stage-R3 'stage17' "DEST_ROOT=$root7/d17`nBACKUP_ROOT=$root7/b17`n"; $sp17 = WslPath $s17
    $m17 = Join-Path $s17 'image_manifest.final.tsv'
    $l17 = [IO.File]::ReadAllText($m17) -split "`n" | Where-Object { $_ -ne '' }
    [IO.File]::WriteAllText($m17, (($l17 | ForEach-Object { if ($_ -match '^a\.txt') { $_ + "`t4755" } else { $_ } }) -join "`n") + "`n", $utf8n)
    $x = Wsl "$HN bash '$sh1' '$sp17'"
    Check 'C17' 'Ж-5: режим 4755 на Pi: код 1, ничего не создано' ($x.Code -eq 1 -and $x.Text -match 'bad mode' -and (Wsl "test -e $root7/d17 -o -e $root7/b17 && echo yes || echo no").Text.Trim() -eq 'no') $x.Text
    Note ('Временный каталог теста в WSL оставлен: ' + $root + ', ' + $root5 + ', ' + $root7 + ' (не удаляю, правило 11)')
}
$piScripts = (Get-Content -LiteralPath (Join-Path $IK 'image_install.sh'), (Join-Path $IK 'image_rollback.sh') -Raw) -join "`n"
Check 'C7' 'в Pi-скриптах нет rm, sudo, reboot, systemctl' (-not ($piScripts -match '(^|\s)(rm|sudo|reboot|systemctl)\s')) ''

Note ''
Note ('ИТОГ: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
