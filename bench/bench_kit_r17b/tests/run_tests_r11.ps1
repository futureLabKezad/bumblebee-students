# run_tests_r11.ps1 (Claude, 16.11.2026, набор r11) - тесты НОВОГО в r11 на ПК, в песочнице. К дрону не подключается: вместо ssh стоит подделка fake_ssh.exe (r5, сеть не открывает).
# G: сверка 01 (params_check\compare_params.ps1): решение владельца 16.11 «Не стоп, только запись» - отличия только в CAL_GYRO0..3_XOFF/YOFF/ZOFF не СТОП, а запись;
#    любое другое отличие (в том числе CAL_ACC*) - СТОП или UNKNOWN, как в r9.
# H: гейт сверки в 07 (run_07_takeoff.ps1) пропускает «СОВПАДАЕТ» и «СОВПАДАЕТ (гироскоп сдвинулся: N, запись)» и только их.
# P: takeoff.conf и takeoff_presets\ под примеры карты real 16.11 (и r2j); копии real_map_20261116; списки 09/15 с alt (image_r2j\EXAMPLES_REAL_20261116.tsv), 13 без alt.
# C: карточка взлёта (метка 0 по кадру нижней камеры), первая строка .cmd, шаг 25 узнаёт карту real. K: r11 = копия r9 + ожидаемые правки (r9 читается, не меняется).
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r11.ps1. Итог: «ИТОГ r11: PASS n, FAIL m».
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r11_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') {
    if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") }
}
function Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
$inv = [Globalization.CultureInfo]::InvariantCulture
if ($env:COMPUTERNAME -ne 'DESKTOP-H5CPN8E') { Note ('ВНИМАНИЕ: имя ПК ' + $env:COMPUTERNAME + ', тесты 07/09/15 рассчитаны на DESKTOP-H5CPN8E') }
Remove-Item Env:BB_REGISTRY -ErrorAction SilentlyContinue
Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue

# ---------- песочница: копия набора без tests, out, _aside, proverka_* ----------
$SB = Join-Path $Run 'sb\bench_kit_20261116_r11'
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Kit.Length + 1)
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -like '_aside\*' -or $rel -like 'proverka_*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest
}
New-Item -ItemType Directory -Force -Path (Join-Path $SB 'out') | Out-Null
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh.cs'))) -OutputAssembly (Join-Path $FakeDir 'ssh.exe') -OutputType ConsoleApplication
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'

# ======================= G: оценщик сверки 01 =======================
$cmpPs = Join-Path $SB 'params_check\compare_params.ps1'
$base = [ordered]@{}; $c125 = @{}
foreach ($l in [IO.File]::ReadLines((Join-Path $SB 'params_check\baseline_20261104_1145.params'))) {
    if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }
    $f = $l.Split("`t"); if ($f.Count -lt 5) { continue }
    if ($f[1] -eq '1') { $base[$f[2]] = @{ T = $f[3]; Ty = $f[4] } } elseif ($f[1] -eq '125') { $c125[$f[2]] = $true }
}
$appr = @{}
foreach ($l in [IO.File]::ReadLines((Join-Path $SB 'params_check\approved_changes.txt'))) { if ($l.Trim() -eq '' -or $l.StartsWith('#')) { continue }; $f = $l.Split("`t"); if ($f.Count -ge 2) { $appr[$f[0]] = $f[1] } }
function ExpText([string]$n) { if ($appr.ContainsKey($n)) { return $appr[$n] } else { return $base[$n].T } }
function New-Events([string]$name, [hashtable]$over, [string[]]$drop = @()) {
    # таблица MAVROS (строки P) = утверждённый набор; $over: имя -> другое значение (текст); $drop: имена, которых «нет на дроне»
    $p = Join-Path $Run ($name + '.raw.txt'); $sb = New-Object Text.StringBuilder
    [void]$sb.Append("PULL`tOK`tsuccess=True received=1127 (тест)`n")
    foreach ($n in $base.Keys) {
        if ($drop -contains $n) { continue }
        $k = $(if ($base[$n].Ty -eq '6') { 'i' } else { 'd' })
        $v = ExpText $n; if ($over.ContainsKey($n)) { $v = $over[$n] }
        [void]$sb.Append("P`t" + $n + "`t" + $k + "`t" + $v + "`n")
    }
    [IO.File]::WriteAllText($p, $sb.ToString(), $utf8n); return $p
}
$noReg = Join-Path $Run 'нет_реестра.md'
function Cmp([string]$name, [hashtable]$over, [string[]]$drop = @()) {
    $ev = New-Events $name $over $drop; $pre = Join-Path $Run ('params_' + $name)
    $so = Join-Path $Run ('cmp_' + $name + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $cmpPs + '" -Events "' + $ev + '" -OutPrefix "' + $pre + '" -Registry "' + $noReg + '"') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $rf = $pre + '_report.txt'; $rep = @(); if (Test-Path -LiteralPath $rf) { $rep = @([IO.File]::ReadAllLines($rf, [Text.Encoding]::UTF8)) }
    $now = ''; if (Test-Path -LiteralPath ($pre + '_now.txt')) { $now = [IO.File]::ReadAllText(($pre + '_now.txt'), [Text.Encoding]::UTF8) }
    return @{ Code = $p.ExitCode; Rep = $rep; Text = ($rep -join "`n"); First = $(if ($rep.Count) { $rep[0] } else { '' }); Now = $now; Report = $rf }
}
function Shift([string]$n, [double]$d) { return ([single]([double]::Parse((ExpText $n), $inv) + $d)).ToString('R', $inv) }
$N = $base.Count
Check 'G0' ('основа: ' + $N + ' настроек компонента 1; CAL_GYRO0_*OFF общие с компонентом 125, CAL_GYRO1_*OFF и CAL_ACC1_*OFF - только компонент 1 (так устроены тесты ниже)') ($N -gt 1000 -and $c125.ContainsKey('CAL_GYRO0_XOFF') -and -not $c125.ContainsKey('CAL_GYRO1_XOFF') -and -not $c125.ContainsKey('CAL_ACC1_XOFF') -and $c125.ContainsKey('CAL_ACC0_XOFF')) ''
$rxStrict = '^=== СОВПАДАЕТ: прочитано (\d+) из \1, отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)'
$rxGyro = '^=== СОВПАДАЕТ \(гироскоп сдвинулся: [1-9]\d*, запись\): прочитано (\d+) из \1, других отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)'

$g1 = Cmp 'g1_none' @{}
Check 'G1' 'ничего не сдвинулось: код 0, «=== СОВПАДАЕТ: прочитано N из N, отличий нет (из таблицы MAVROS N, из запасного потока 0)» - как в r9, блока гироскопа нет' ($g1.Code -eq 0 -and $g1.First -match $rxStrict -and $g1.First.StartsWith('=== СОВПАДАЕТ: прочитано ' + $N + ' из ' + $N + ', отличий нет') -and $g1.Text -notmatch 'Гироскоп сдвинулся' -and $g1.Text -notmatch 'ОТЛИЧИЯ: СТОП') ($g1.Code.ToString() + ' ' + $g1.First)
$gy = @{ 'CAL_GYRO1_XOFF' = (Shift 'CAL_GYRO1_XOFF' 0.0035); 'CAL_GYRO1_ZOFF' = (Shift 'CAL_GYRO1_ZOFF' -0.002); 'CAL_GYRO1_YOFF' = (Shift 'CAL_GYRO1_YOFF' 0.001) }
$g2 = Cmp 'g2_gyro' $gy
$g2blk = @($g2.Rep | Where-Object { $_ -match '^CAL_GYRO\d_[XYZ]OFF: ждали ' })
Check 'G2' 'ТОЛЬКО гироскоп (CAL_GYRO1_XOFF, CAL_GYRO1_YOFF, CAL_GYRO1_ZOFF): код 0, НЕ СТОП, первая строка «=== СОВПАДАЕТ (гироскоп сдвинулся: 3, запись): прочитано N из N, других отличий нет (из таблицы MAVROS N, из запасного потока 0)»' ($g2.Code -eq 0 -and $g2.First.StartsWith('=== СОВПАДАЕТ (гироскоп сдвинулся: 3, запись): прочитано ' + $N + ' из ' + $N + ', других отличий нет (из таблицы MAVROS ' + $N + ', из запасного потока 0)') -and $g2.First -match $rxGyro -and $g2.First -notmatch $rxStrict) ($g2.Code.ToString() + ' ' + $g2.First)
Check 'G2' 'гироскоп: отдельный блок «--- Гироскоп сдвинулся (запись, не стоп): 3 ---», в каждой строке имя, ждали, стало; СТОП-блока и UNKNOWN нет' ((@($g2.Rep | Where-Object { $_ -ceq '--- Гироскоп сдвинулся (запись, не стоп): 3 ---' }).Count -eq 1) -and $g2blk.Count -eq 3 -and (@($g2blk | Where-Object { $_ -match '^CAL_GYRO1_XOFF: ждали ' + [regex]::Escape((ExpText 'CAL_GYRO1_XOFF')) + ' \(.+\), стало ' + [regex]::Escape($gy['CAL_GYRO1_XOFF']) + '$' }).Count -eq 1) -and (@($g2blk | Where-Object { $_ -match '^CAL_GYRO1_YOFF: ждали .+, стало ' }).Count -eq 1) -and $g2.Text -notmatch 'ОТЛИЧИЯ: СТОП' -and $g2.Text -notmatch '--- UNKNOWN') ($g2blk -join ' | ')
Check 'G2' 'гироскоп: строка для СЕЙЧАС_ОТ_ВАС - «совпадает, гироскоп сдвинулся у 3 (запись, не стоп)»' ($g2.Now -match 'совпадает' -and $g2.Now -match 'гироскоп сдвинулся у 3 \(запись, не стоп') $g2.Now
$g3 = Cmp 'g3_gyro_acc' (@{ 'CAL_ACC1_XOFF' = (Shift 'CAL_ACC1_XOFF' 0.01) } + $gy)
$g3stop = @($g3.Rep | Where-Object { $_ -match '^CAL_\w+: на дроне ' })
Check 'G3' 'гироскоп + CAL_ACC1_XOFF: код 2, «=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 1 ===»; в СТОП-блоке только CAL_ACC1_XOFF; гироскоп - отдельным блоком (3)' ($g3.Code -eq 2 -and $g3.First -ceq '=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 1 ===' -and $g3stop.Count -eq 1 -and $g3stop[0].StartsWith('CAL_ACC1_XOFF: на дроне ') -and (@($g3.Rep | Where-Object { $_ -ceq '--- Гироскоп сдвинулся (запись, не стоп): 3 ---' }).Count -eq 1) -and $g3.First -notmatch $rxStrict -and $g3.First -notmatch $rxGyro) ($g3.Code.ToString() + ' ' + $g3.First + ' | ' + ($g3stop -join ' | '))
$g4 = Cmp 'g4_acc' @{ 'CAL_ACC1_XOFF' = (Shift 'CAL_ACC1_XOFF' 0.01) }
Check 'G4' 'только CAL_ACC1_XOFF: код 2, СТОП (1), блока гироскопа нет - как в r9' ($g4.Code -eq 2 -and $g4.First -ceq '=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 1 ===' -and $g4.Text -notmatch 'Гироскоп сдвинулся' -and $g4.Now -match '^СТОП') ($g4.Code.ToString() + ' ' + $g4.First)
$g5 = Cmp 'g5_acc0' @{ 'CAL_ACC0_XOFF' = (Shift 'CAL_ACC0_XOFF' 0.01) }
Check 'G5' 'CAL_ACC0_XOFF (имя общее с компонентом 125): код 3 UNKNOWN, как в r9 - не «СОВПАДАЕТ», не запись гироскопа' ($g5.Code -eq 3 -and $g5.First.StartsWith('=== НЕ ПОДТВЕРЖДЕНО (UNKNOWN)') -and $g5.Text -notmatch 'Гироскоп сдвинулся' -and $g5.First -notmatch 'СОВПАДАЕТ') ($g5.Code.ToString() + ' ' + $g5.First)
$g6 = Cmp 'g6_gyro_rot' @{ 'CAL_GYRO1_ROT' = '2' }
Check 'G6' 'CAL_GYRO1_ROT (не поправка XOFF/YOFF/ZOFF): код 2, СТОП - запись только для 12 имён CAL_GYRO0..3_XOFF/YOFF/ZOFF' ($g6.Code -eq 2 -and $g6.First -ceq '=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 1 ===' -and $g6.Text -match 'CAL_GYRO1_ROT: на дроне 2') ($g6.Code.ToString() + ' ' + $g6.First)
$g7 = Cmp 'g7_gyro_missing' $gy @('MPC_XY_P')
Check 'G7' 'гироскоп + одна настройка не прочитана: код 3 «СВЕРКА НЕПОЛНАЯ», не «СОВПАДАЕТ» (неполная сверка по-прежнему не проходит)' ($g7.Code -eq 3 -and $g7.First.StartsWith('=== СВЕРКА НЕПОЛНАЯ') -and $g7.First -notmatch $rxGyro) ($g7.Code.ToString() + ' ' + $g7.First)
$g8 = Cmp 'g8_gyro_samevalue' @{ 'CAL_GYRO1_XOFF' = (ExpText 'CAL_GYRO1_XOFF') }
Check 'G8' 'гироскоп со значением как ждали: код 0, строгое «СОВПАДАЕТ» (запись не появляется без сдвига)' ($g8.Code -eq 0 -and $g8.First -match $rxStrict) $g8.First
$g11 = Cmp 'g11_gyro0_shared' @{ 'CAL_GYRO0_YOFF' = (Shift 'CAL_GYRO0_YOFF' 0.001) }
Check 'G11' 'r11b: CAL_GYRO0_YOFF (имя общее с компонентом 125): код 3 UNKNOWN, как в r9 - не запись гироскопа' ($g11.Code -eq 3 -and $g11.First.StartsWith('=== НЕ ПОДТВЕРЖДЕНО (UNKNOWN)') -and $g11.Text -notmatch 'Гироскоп сдвинулся') ($g11.Code.ToString() + ' ' + $g11.First)
$cmp9 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261113_r9\params_check\compare_params.ps1'
if (Test-Path -LiteralPath $cmp9) {
    # контроль: те же события «только гироскоп» оценщиком r9 (только чтение r9, вывод в песочницу) - СТОП или UNKNOWN; значит, G2 проверяет именно правку r11
    $ev9 = Join-Path $Run 'g2_gyro.raw.txt'; $pre9 = Join-Path $Run 'params_r9_g2'
    $p9 = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $cmp9 + '" -Events "' + $ev9 + '" -OutPrefix "' + $pre9 + '" -Registry "' + $noReg + '"') -NoNewWindow -PassThru -Wait -RedirectStandardOutput ($pre9 + '.con.txt') -RedirectStandardError ($pre9 + '.con.err')
    $f9 = @([IO.File]::ReadAllLines(($pre9 + '_report.txt'), [Text.Encoding]::UTF8))[0]
    Check 'G10' 'контроль: оценщик r9 на тех же событиях «только гироскоп» даёт СТОП (код 2), а не «СОВПАДАЕТ»' ($p9.ExitCode -eq 2 -and $f9.StartsWith('=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 3 ===')) ($p9.ExitCode.ToString() + ' ' + $f9)
}
$cmpTxt = [IO.File]::ReadAllText($cmpPs)
Check 'G9' 'в оценщике запись гироскопа задана одним шаблоном ^CAL_GYRO[0-3]_[XYZ]OFF$ (ровно 12 имён), других исключений из СТОП нет' ($cmpTxt.Contains("-cmatch '^CAL_GYRO[0-3]_[XYZ]OFF$'") -and ([regex]::Matches($cmpTxt, 'CAL_GYRO\[')).Count -eq 1) ''

# ======================= H: гейт сверки в 07 =======================
$p07 = Join-Path $SB 'run_07_takeoff.ps1'; $t07 = [IO.File]::ReadAllText($p07)
$conf = Join-Path $SB 'takeoff.conf'; $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
function Read-Conf([string]$p) { $h = @{}; foreach ($l in [IO.File]::ReadAllLines($p)) { $t = $l.Trim(); if ($t -eq '' -or $t.StartsWith('#')) { continue }; $i = $t.IndexOf('='); if ($i -gt 0) { $h[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim() } }; return $h }
function Write-Gate([string]$sha) { [IO.File]::WriteAllText($gate, "ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-16 тест`r`nСЛОВА_ВЛАДЕЛЬЦА=тест r11`r`nСКРИПТ_SHA256=$sha`r`nАРГУМЕНТЫ=`r`nСОЗДАЛ=чат 1`r`n", $utf8) }
function New-Out([string]$name, [string]$first) {
    $o = Join-Path $Run ('out_' + $name); New-Item -ItemType Directory -Path $o -Force | Out-Null
    $rp = Join-Path $o 'params_bench_t_report.txt'; [IO.File]::WriteAllText($rp, $first + "`r`n", $utf8)
    foreach ($kn in 'install_check', 'mavros_check') { $cf = Join-Path $o ($kn + '_20261116_080000.txt'); [IO.File]::WriteAllText($cf, ("BB_DONE`r`n# VERDICT OK`r`n"), $utf8); (Get-Item $cf).LastWriteTime = (Get-Date).AddMinutes(-5) }
    return $o
}
function Reset-Fake([string]$shaOut) {
    foreach ($f in 'calls.log', 'sha_out.txt', 'mode.txt', 'flight_rc.txt', 'canned_fg.txt', 'canned_install.txt', 'canned_fp_bumblebee.txt', 'canned_fp_mavros.txt') { $p = Join-Path $FakeDir $f; if (Test-Path $p) { Remove-Item $p } }
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), 'normal')
    [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), $shaOut)
    $fg = Join-Path $Run 'canned_fg_ok.txt'; [IO.File]::WriteAllText($fg, "FG_DIR /home/lb/ros2_ws/src/bumblebee/examples drone.py OK`nBB_FG_RESULT OK`nBB_FG_DONE`n", $utf8n)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_fg.txt'), $fg)
}
function Run-07Ps([string]$outDir) {
    $env:BB_KIT_OUT = $outDir
    $so = Join-Path $Run ('c07_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $p07 + '" -SafetyConfirmed NET-TWO-KILL-YES') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $sw.Stop(); Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
    $cl = Join-Path $FakeDir 'calls.log'; $calls = @(); if (Test-Path $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    return @{ Code = $p.ExitCode; Calls = $calls; J = ($calls -join "`n"); Console = ([IO.File]::ReadAllText($so) + [IO.File]::ReadAllText($so + '.err')); Secs = $sw.Elapsed.TotalSeconds }
}
Check 'H0' '07: условие сверки - строгое «СОВПАДАЕТ» как в r9 (то же выражение) ИЛИ «СОВПАДАЕТ (гироскоп сдвинулся: N≥1, запись) ... других отличий нет ... из запасного потока 0»' ($t07.Contains("`$first -notmatch '" + $rxStrict + "' -and `$first -notmatch '" + $rxGyro + "'")) ''
$cf = Read-Conf $conf; $real = $cf['SCRIPT_SHA256']
Write-Gate $real
$bad = ('cd' * 32) + '  ' + $cf['SCRIPT_REMOTE_PATH']   # sha на «Pi» другой: 07 остановится сразу после проверки sha, до отсчёта
$cases = @(
    @('H1', $g2.First, $true, 'отчёт «гироскоп сдвинулся» (G2) проходит гейт сверки: 07 дошёл до дрона (проверка sha256), отказ только из-за sha'),
    @('H2', $g1.First, $true, 'строгий отчёт «СОВПАДАЕТ» (G1) проходит, как в r9'),
    @('H3', $g3.First, $false, 'отчёт гироскоп + ACC (G3, СТОП): код 4, к дрону не обращались, причина «не СОВПАДАЕТ»'),
    @('H4', $g4.First, $false, 'отчёт ACC (G4, СТОП): код 4, к дрону не обращались'),
    @('H5', $g5.First, $false, 'отчёт UNKNOWN (G5): код 4, к дрону не обращались'),
    @('H6', $g7.First, $false, 'отчёт НЕПОЛНАЯ с гироскопом (G7): код 4'),
    @('H7', ('=== СОВПАДАЕТ (гироскоп сдвинулся: 0, запись): прочитано ' + $N + ' из ' + $N + ', других отличий нет (из таблицы MAVROS ' + $N + ', из запасного потока 0) ==='), $false, 'подделка «гироскоп сдвинулся: 0»: код 4'),
    @('H8', ('=== СОВПАДАЕТ (гироскоп сдвинулся: 2, запись): прочитано ' + $N + ' из ' + $N + ', других отличий нет (из таблицы MAVROS ' + ($N - 3) + ', из запасного потока 3) ==='), $false, '«гироскоп сдвинулся», но 3 значения из запасного потока: код 4'),
    @('H9', ('=== СОВПАДАЕТ (гироскоп сдвинулся: 2, запись): прочитано ' + $N + ' из ' + $N + ', отличий нет (из таблицы MAVROS ' + $N + ', из запасного потока 0) ==='), $false, 'смесь форм («гироскоп» + «отличий нет» без «других»): код 4 - принимается только точный вид оценщика')
)
foreach ($c in $cases) {
    Reset-Fake $bad
    $r = Run-07Ps (New-Out $c[0] $c[1])
    if ($c[2]) { Check $c[0] ('07: ' + $c[3]) ($r.Code -eq 4 -and $r.Calls.Count -ge 2 -and $r.J -match ('sha256sum ' + [regex]::Escape($cf['SCRIPT_REMOTE_PATH'])) -and $r.Console -notmatch 'СОВПАДАЕТ полностью' -and $r.Console -match 'sha256 не равен' -and $r.Secs -lt 9) ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console) }
    else { Check $c[0] ('07: ' + $c[3]) ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не «СОВПАДАЕТ полностью из таблицы MAVROS»') ('code=' + $r.Code + ' calls=' + $r.Calls.Count) }
}
# полный проход: отчёт «гироскоп сдвинулся», sha на «Pi» = flight_marker.py карты real -> отсчёт 10 с и запуск скрипта из оверлея
Reset-Fake ($real + '  ' + $cf['SCRIPT_REMOTE_PATH'])
$oF = New-Out 'h10_full' $g2.First
$r = Run-07Ps $oF
$lg = @(Get-ChildItem -LiteralPath $oF -Filter 'takeoff_*.log')
Check 'H10' '07 полный проход с отчётом «гироскоп сдвинулся»: код 0, отсчёт ≥ 9,5 с, запущен flight_marker.py карты real из оверлея (-tt), в журнале takeoff первая строка сверки с «гироскоп сдвинулся: 3»' ($r.Code -eq 0 -and $r.Secs -ge 9.5 -and $r.J -match 'cd /home/lb && python3 /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/flight_marker\.py\]' -and $r.J -match '\[-tt\]' -and $lg.Count -eq 1 -and ([IO.File]::ReadAllText($lg[0].FullName)) -match 'гироскоп сдвинулся: 3' -and ([IO.File]::ReadAllText($lg[0].FullName)) -match ('sha256 ' + $real)) ('code=' + $r.Code + ' secs=' + [int]$r.Secs + ' ' + $r.J)
if (Test-Path $gate) { Remove-Item -LiteralPath $gate }

# ======================= P: takeoff.conf, пресеты, копии карты real, списки 09/15 =======================
$want = @{ 'aruco_z_test.py' = 'fd6cba69e62eebbe7628f5516916e8072bc79c14c9b1980b25ead795c5d700f1'; 'flight_marker.py' = '28992fe4df6bb404a2d403e001b0f2e8e6a3985c4d5a0681dd6d441b97c0ed7a'; 'flight_marker_loop.py' = '915a443e76e796cbf01b7b4771f86028df469acc04e7be8d3124f34d1f24cd37'; 'map_final.txt' = '545e8e4617f4405cf7b9234f302c249ce60592c0b5487f02520f109d292a0826' }
$rm = Join-Path $Kit 'real_map_20261116'
Check 'P1' 'real_map_20261116: копии трёх примеров карты real и map_final.txt, sha256 = заданным владельцем/чатом 1 (fd6cba69…, 28992fe4…, 915a443e…, 545e8e46…0826)' (@($want.Keys | Where-Object { -not (Test-Path (Join-Path $rm $_)) -or (Sha (Join-Path $rm $_)) -ne $want[$_] }).Count -eq 0) ''
$kc = [IO.File]::ReadAllText((Join-Path $Kit 'takeoff.conf')); $kcf = Read-Conf (Join-Path $Kit 'takeoff.conf')
Check 'P2' 'настоящий takeoff.conf: flight_marker.py КАРТЫ REAL из оверлея (/home/lb/bench_ws/r2j/.../flight/flight_marker.py, sha256 28992fe4…), DRONE_PY_SHA256 fa6abf8b… (r2j), аргументов нет, ровно 4 ключа, пометка «ВЛАДЕЛЕЦ ПОДТВЕРЖДАЕТ»; TAKEOFF_APPROVED.txt в наборе нет' ($kcf.Count -eq 4 -and $kcf['SCRIPT_REMOTE_PATH'] -ceq '/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/flight_marker.py' -and $kcf['SCRIPT_SHA256'] -ceq $want['flight_marker.py'] -and $kcf['DRONE_PY_SHA256'] -ceq 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c' -and $kcf['SCRIPT_ARGS'] -ceq '' -and $kc -match 'ВЛАДЕЛЕЦ ПОДТВЕРЖДАЕТ' -and -not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt'))) ($kcf | Out-String)
$pre = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'takeoff_presets') -Filter '*.conf' | Sort-Object Name)
$expPre = @{ 'real_aruco_z_test.conf' = @('flight/aruco_z_test.py', $want['aruco_z_test.py'], 'real'); 'real_flight_marker.conf' = @('flight/flight_marker.py', $want['flight_marker.py'], 'real'); 'real_flight_marker_loop.conf' = @('flight/flight_marker_loop.py', $want['flight_marker_loop.py'], 'real');
    'r2j_flight.conf' = @('flight/flight.py', '', 'r2j'); 'r2j_flight_marker.conf' = @('flight/flight_marker.py', '', 'r2j'); 'r2j_flight_marker_loop.conf' = @('flight/flight_marker_loop.py', '', 'r2j'); 'r2j_hover_marker0.conf' = @('hover_marker0.py', '', 'r2j') }
Check 'P3' ('takeoff_presets: ровно 7 вариантов (3 карты real, 4 образа r2j): ' + (($pre | ForEach-Object { $_.Name }) -join ', ')) ($pre.Count -eq 7 -and @($pre | Where-Object { -not $expPre.ContainsKey($_.Name) }).Count -eq 0) ''
foreach ($pf in $pre) {
    if (-not $expPre.ContainsKey($pf.Name)) { continue }
    $e = $expPre[$pf.Name]; $h = Read-Conf $pf.FullName
    $src = $(if ($e[2] -eq 'real') { Join-Path $rm (Split-Path $e[0] -Leaf) } else { Join-Path $Kit ('image_r2j\payload\ros2_ws\src\bumblebee\examples\' + $e[0].Replace('/', '\')) })
    $wsha = $(if ($e[1]) { $e[1] } else { Sha $src })
    Check 'P4' ($pf.Name + ': 4 ключа, путь в оверлее /home/lb/bench_ws/r2j/src/bumblebee/examples/' + $e[0] + ', sha256 = файл ' + $(if ($e[2] -eq 'real') { 'real_map_20261116' } else { 'payload r2j' }) + ', drone.py r2j, без аргументов') ($h.Count -eq 4 -and $h['SCRIPT_REMOTE_PATH'] -ceq ('/home/lb/bench_ws/r2j/src/bumblebee/examples/' + $e[0]) -and $h['SCRIPT_SHA256'] -ceq $wsha -and (Test-Path $src) -and (Sha $src) -eq $wsha -and $h['DRONE_PY_SHA256'] -ceq 'fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c' -and $h['SCRIPT_ARGS'] -ceq '') ($h | Out-String)
    # пресет как takeoff.conf песочницы + разрешение с его sha: 07 проходит все свои условия и сверяет на «Pi» именно этот путь (sha на «Pi» другой -> код 4 до отсчёта)
    Copy-Item -LiteralPath $pf.FullName -Destination $conf -Force; Write-Gate $h['SCRIPT_SHA256']; Reset-Fake (('cd' * 32) + '  x')
    $r = Run-07Ps (New-Out ('p_' + $pf.BaseName) $g1.First)
    Check 'P5' ($pf.Name + ' в takeoff.conf + разрешение с его sha: 07 принимает conf и разрешение, на «Pi» сверяет sha256sum этого пути, при чужом sha - код 4 до отсчёта') ($r.Code -eq 4 -and $r.J -match ('sha256sum ' + [regex]::Escape($h['SCRIPT_REMOTE_PATH'])) -and $r.Console -match 'sha256 не равен' -and $r.Secs -lt 9) ('code=' + $r.Code + ' ' + $r.Console)
}
Copy-Item -LiteralPath (Join-Path $Kit 'takeoff.conf') -Destination $conf -Force; if (Test-Path $gate) { Remove-Item -LiteralPath $gate }
Check 'P6' 'takeoff.conf r11 = пресет real_flight_marker.conf по ключам' ((Compare-Object @((Read-Conf (Join-Path $Kit 'takeoff.conf')).GetEnumerator() | ForEach-Object { $_.Key + '=' + $_.Value }) @((Read-Conf (Join-Path $Kit 'takeoff_presets\real_flight_marker.conf')).GetEnumerator() | ForEach-Object { $_.Key + '=' + $_.Value })) -eq $null) ''
# списки 09/15 с alt
$bbc = Join-Path $SB 'lib\bb_common.ps1'; $bbl = Join-Path $SB 'lib\bb_lists.ps1'
$lj = Join-Path $Run 'lists.txt'
$ps = ". '" + $bbc + "'; . '" + $bbl + "'; `$a = BL-CppList '" + $SB + "'; `$b = BL-ApplyRealAlt '" + $SB + "' (BL-CppList '" + $SB + "'); [IO.File]::WriteAllText('" + $lj + "', ((`$a -join [char]10) + [char]10 + '=====' + [char]10 + (`$b -join [char]10)), (New-Object Text.UTF8Encoding(`$false)))"
& powershell -NoProfile -ExecutionPolicy Bypass -Command $ps 2>&1 | Out-Null
$lt = [IO.File]::ReadAllText($lj) -split '=====' ; $la = @($lt[0].Trim() -split "`n"); $lb = @($lt[1].Trim() -split "`n")
$r2jFm = '1e0063fb3557a516767122a3031d38678be10e58efb2cc07a3e83df538e529fb'; $r2jFl = '7f36db429eb26f7e878aa16ee7998b883eeaa00e184b5a5c5dc07544318e1d1d'
Check 'P7' 'BL-CppList (его берёт сборка 13) без изменений: 16 строк, ни одной с запятой (13 требует только r2j)' ($la.Count -eq 16 -and @($la | Where-Object { $_ -match ',' }).Count -eq 0) ($la -join ' | ')
Check 'P8' 'BL-ApplyRealAlt (09 и 15): те же 16 строк, только две изменены - flight_marker.py «1e0063fb…,28992fe4…» и flight_marker_loop.py «7f36db42…,915a443e…», флаг «-»' ($lb.Count -eq 16 -and @($lb | Where-Object { $_ -match ',' }).Count -eq 2 -and ($lb -contains ($r2jFm + ',' + $want['flight_marker.py'] + '  ros2_ws/src/bumblebee/examples/flight/flight_marker.py  -')) -and ($lb -contains ($r2jFl + ',' + $want['flight_marker_loop.py'] + '  ros2_ws/src/bumblebee/examples/flight/flight_marker_loop.py  -')) -and @(Compare-Object @($la | Where-Object { $_ -notmatch 'flight_marker' }) @($lb | Where-Object { $_ -notmatch 'flight_marker' })).Count -eq 0) ($lb -join ' | ')
# 09 и 15 на подделке: сгенерированный скрипт Pi содержит строки с alt
$o9 = Join-Path $Run 'out_09'; New-Item -ItemType Directory -Path $o9 | Out-Null
Reset-Fake ''; $ci = Join-Path $Run 'canned_install.txt'; [IO.File]::WriteAllText($ci, "INSTALL_ARCH aarch64`nBB_RTPY ok=0 diff=0 missing=0`nBB_INSTALL_CHECK ok=0 diff=0 missing=0 noprefix=0 cpp_ok=0 cpp_diff=0 cpp_missing=0 bin_ok=0 bin_missing=0 stale=0`nBB_INSTALL_CHECK_DONE`n", $utf8n); [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $ci)
$env:BB_KIT_OUT = $o9; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SB 'run_install_check.ps1') 2>&1 | Out-Null; $rc9 = $LASTEXITCODE; Remove-Item Env:BB_KIT_OUT
$g9 = @(Get-ChildItem -LiteralPath $o9 -Filter 'install_check_*.generated.sh'); $g9t = $(if ($g9.Count -eq 1) { [IO.File]::ReadAllText($g9[0].FullName) } else { '' })
Check 'P9' '09 (run_install_check.ps1) на подделке: в скрипте для Pi строки примеров с alt (r2j,real) и функция shamatch; остальные строки C++ без запятой' ($g9.Count -eq 1 -and $g9t.Contains($r2jFm + ',' + $want['flight_marker.py'] + '  ros2_ws/src/bumblebee/examples/flight/flight_marker.py  -') -and $g9t.Contains($r2jFl + ',' + $want['flight_marker_loop.py'] + '  ros2_ws/src/bumblebee/examples/flight/flight_marker_loop.py  -') -and $g9t.Contains('shamatch()') -and ([regex]::Matches($g9t, '[0-9a-f]{64},[0-9a-f]{64}')).Count -eq 2) ('rc=' + $rc9)
$o15 = Join-Path $Run 'out_15'; New-Item -ItemType Directory -Path $o15 | Out-Null
Reset-Fake ''
$env:BB_KIT_OUT = $o15; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SB 'run_fingerprint.ps1') 2>&1 | Out-Null; Remove-Item Env:BB_KIT_OUT
$g15 = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_bumblebee_*.generated.sh'); $g15m = @(Get-ChildItem -LiteralPath $o15 -Filter 'fingerprint_mavros_*.generated.sh')
$g15t = $(if ($g15.Count -eq 1) { [IO.File]::ReadAllText($g15[0].FullName) } else { '' }); $g15mt = $(if ($g15m.Count -eq 1) { [IO.File]::ReadAllText($g15m[0].FullName) } else { '' })
Check 'P10' '15 (run_fingerprint.ps1): в скрипте bumblebee 2 строки с alt, в скрипте MAVROS - ни одной (bp02 без изменений)' ($g15.Count -eq 1 -and ([regex]::Matches($g15t, '[0-9a-f]{64},[0-9a-f]{64}')).Count -eq 2 -and $g15m.Count -eq 1 -and ([regex]::Matches($g15mt, '[0-9a-f]{64},[0-9a-f]{64}')).Count -eq 0) ''
# плохой список alt -> СТОП до обращения к дрону
$altP = Join-Path $SB 'image_r2j\EXAMPLES_REAL_20261116.tsv'; $altKeep = [IO.File]::ReadAllText($altP)
$bads = @(
    @('путь, которого нет в CPP_SOURCES_r2j.tsv', ($want['aruco_z_test.py'] + "`tros2_ws/src/bumblebee/examples/flight/aruco_z_test.py`n")),
    @('файл с флагом R (C++)', ($want['flight_marker.py'] + "`tros2_ws/src/bumblebee/src/cpp/simple_offboard.cpp`n")),
    @('не 64 hex', ("XYZ`tros2_ws/src/bumblebee/examples/flight/flight_marker.py`n")),
    @('путь вне examples/', ($want['flight_marker.py'] + "`tros2_ws/src/bumblebee/CMakeLists.txt`n")),
    @('повтор пути', ($want['flight_marker.py'] + "`tros2_ws/src/bumblebee/examples/flight/flight_marker.py`n" + $want['flight_marker_loop.py'] + "`tros2_ws/src/bumblebee/examples/flight/flight_marker.py`n"))
)
foreach ($b in $bads) {
    [IO.File]::WriteAllText($altP, $b[1], $utf8n); Reset-Fake ''
    $o = Join-Path $Run ('out_alt_' + [guid]::NewGuid().ToString('N').Substring(0, 6)); New-Item -ItemType Directory -Path $o | Out-Null
    $env:BB_KIT_OUT = $o; & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SB 'run_install_check.ps1') 2>&1 | Out-Null; $rc = $LASTEXITCODE; Remove-Item Env:BB_KIT_OUT
    $cl = Join-Path $FakeDir 'calls.log'; $nc = $(if (Test-Path $cl) { @(Get-Content $cl).Count } else { 0 })
    Check 'P11' ('09: в списке alt ' + $b[0] + ': код 4, к дрону не обращались') ($rc -eq 4 -and $nc -eq 0) ('rc=' + $rc + ' calls=' + $nc)
}
[IO.File]::WriteAllText($altP, $altKeep, $utf8n)
$bbs = [IO.File]::ReadAllText((Join-Path $SB 'run_bb_build.ps1'))
Check 'P12' 'сборка 13 (run_bb_build.ps1) alt не берёт: BL-ApplyRealAlt и EXAMPLES_REAL в ней нет' ($bbs -notmatch 'BL-ApplyRealAlt' -and $bbs -notmatch 'EXAMPLES_REAL') ''

# ======================= C: карточка, .cmd, шаг 25 =======================
$card = [IO.File]::ReadAllText((Join-Path $Kit 'cards\КАРТОЧКИ_ШАГОВ_СТЕНДА.md'))
$c21 = [regex]::Match($card, '(?s)## Карточка 21 из 22.*?(?=\n## )').Value
Check 'C1' 'карточка 21 (ВЗЛЁТ): шаг перед взводом - дрон точно на метке 0, по кадру нижней камеры метка 0 видна (не у края), иначе не взлетать; причина - Gazebo, сдвиг 8 см' ($c21 -match 'Перед взводом' -and $c21 -match 'метк\w* 0' -and $c21 -match 'нижней камеры' -and $c21 -match 'не у края' -and $c21 -match '8 см' -and $c21 -match 'Gazebo' -and $c21.IndexOf('Перед взводом') -lt $c21.IndexOf('**Сделайте:**')) ''
Check 'C1b' 'карточка 21: про пресеты takeoff_presets и карту real' ($c21 -match 'takeoff_presets' -and $c21 -match 'карт\w* real') ''
$cmds = @(Get-ChildItem -LiteralPath $Kit -Filter '*.cmd' -File)
$badCmd = @($cmds | Where-Object { $l = @([IO.File]::ReadAllLines($_.FullName, [Text.Encoding]::UTF8)); -not ($l.Count -ge 3 -and $l[0] -eq '@echo off' -and $l[2] -match '^echo (ТОЛЬКО ЧТЕНИЕ|МЕНЯЕТ ДРОН)') } | ForEach-Object { $_.Name })
Check 'C2' ('все .cmd в корне набора (' + $cmds.Count + '): первая выводимая строка - ТОЛЬКО ЧТЕНИЕ или МЕНЯЕТ ДРОН, как в r9') ($badCmd.Count -eq 0) ($badCmd -join ', ')
$r8m = [IO.File]::ReadAllText((Join-Path $Kit 'run_r8_metki.ps1'))
Check 'C3' 'шаг 25 (run_r8_metki.ps1): sha карты 12.11 (528b5adb…) на месте, карта real 16.11 (545e8e46…0826) узнаётся и подписывается, номера карты те же (0-20 без 17)' ($r8m.Contains("'528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611'") -and $r8m.Contains("'" + $want['map_final.txt'] + "'") -and $r8m -match 'карта real 16\.11') ''
$mapIds = @([IO.File]::ReadAllLines((Join-Path $rm 'map_final.txt')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' } | ForEach-Object { [int]($_.Split("`t")[0]) } | Sort-Object)
Check 'C4' 'map_final.txt: номера 0-20 без 17 (как карта 12.11: шаг 25 не назовёт номера карты real ложными), метка 0 в (0, 0)' ((($mapIds -join ',') -eq ((0..20 | Where-Object { $_ -ne 17 }) -join ',')) -and ([IO.File]::ReadAllLines((Join-Path $rm 'map_final.txt')) | Where-Object { $_ -match '^0\t' }) -match '^0\t0\.190\t0\.000\t0\.000\t') ($mapIds -join ',')

# ======================= K: r11 = копия r9 + ожидаемые правки =======================
$r9 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261113_r9'
if (Test-Path -LiteralPath $r9) {
    $changed = @('run_07_takeoff.ps1', 'params_check\compare_params.ps1', 'takeoff.conf', 'lib\bb_lists.ps1', 'run_install_check.ps1', 'run_fingerprint.ps1', 'pi\install_check.sh', 'pi\overlay_fingerprint.sh', 'run_r8_metki.ps1', 'cards\КАРТОЧКИ_ШАГОВ_СТЕНДА.md', 'SHA256SUMS.txt')
    $changedTests = @(Get-Content -LiteralPath (Join-Path $Kit 'proverka_r11\OLD_TESTS_CHANGED.txt') -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -and -not $_.StartsWith('#') })
    $notCopied = @('gates\OVERLAY_BUMBLEBEE_APPROVED.txt', 'gates\OVERLAY_MAVROS_APPROVED.txt', 'image_r2j\gates\S2_S3_PASSED.txt')
    $r9f = @(Get-ChildItem -LiteralPath $r9 -Recurse -File | ForEach-Object { $_.FullName.Substring($r9.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and $_ -notmatch '^tests\\run_[^\\]+\\' })
    $miss = @(); $diff = @(); $same = 0
    foreach ($rel in $r9f) {
        $k = Join-Path $Kit $rel
        if ($notCopied -contains $rel) { if (Test-Path -LiteralPath $k) { $miss += ('СКОПИРОВАН ' + $rel) }; continue }
        if (-not (Test-Path -LiteralPath $k)) { $miss += $rel; continue }
        if ((Sha $k) -ne (Sha (Join-Path $r9 $rel))) { if ($changed -notcontains $rel -and $changedTests -notcontains $rel) { $diff += $rel } } else { $same++ }
    }
    Check 'K1' ('все файлы r9 (кроме out\, папок прогонов и 3 файлов-разрешений) есть в r11; изменены только ожидаемые (' + ($changed.Count + $changedTests.Count) + '), байт в байт одинаковых: ' + $same) ($miss.Count -eq 0 -and $diff.Count -eq 0) (($miss + $diff) -join ', ')
    $newOk = '^(README_r11\.md|DIFF_r9_r11\.txt|takeoff_presets\\[^\\]+\.conf|real_map_20261116\\[^\\]+|image_r2j\\EXAMPLES_REAL_20261116\.tsv|tests\\run_tests_r11\.ps1|tests\\run_tests_r11_pi\.sh|proverka_r11\\.+|_aside\\r11_[^\\]+\\.+|tests\\run_[^\\]+\\.+)$'
    $new = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object { $_.FullName.Substring($Kit.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and -not (Test-Path -LiteralPath (Join-Path $r9 $_)) -and $_ -notmatch $newOk })
    Check 'K2' 'новых файлов, кроме ожидаемых (README_r11, DIFF_r9_r11, takeoff_presets, real_map_20261116, EXAMPLES_REAL, тесты r11, proverka_r11, _aside\r11_*), нет' ($new.Count -eq 0) ($new -join ', ')
    Check 'K3' 'gates\: TAKEOFF_APPROVED.txt и OVERLAY_*_APPROVED.txt нет; image_r2j\gates\S2_S3_PASSED.txt нет (разрешения в новый набор не копировались)' (-not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_MAVROS_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_BUMBLEBEE_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'image_r2j\gates\S2_S3_PASSED.txt'))) ''
}
else { Check 'K0' 'папка r9 рядом не найдена: сравнение с r9 не сделано' $false $r9 }
$outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -File -ErrorAction SilentlyContinue)
Check 'K4' 'out\ набора r11 пуст (тесты пишут только в tests\run_r11_*)' ($outFiles.Count -eq 0) (($outFiles | ForEach-Object { $_.Name }) -join ', ')

$env:PATH = $oldPath
Note ''
Note ('ИТОГ r11: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
