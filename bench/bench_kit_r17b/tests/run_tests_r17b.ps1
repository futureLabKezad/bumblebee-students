# run_tests_r17b.ps1 (Claude, 19.11.2026, набор r17b = r17a + одна строка COM_RC_OVERRIDE 3 в params_check\approved_changes.txt) - тесты на ПК, в песочнице. К дрону не подключается.
# P: оценщик сверки 01 (params_check\compare_params.ps1, тот же вызов, что в run_params_check.ps1) на НАСТОЯЩЕМ ответе Pi из 01 r14 владельца 19.11 14:37
#    (bench_kit_20261117_r14\out\params_bench_20261119_143717.raw.txt, только чтение, берётся копия): r17b - СОВПАДАЕТ; r17a - СТОП (контроль); тот же ответ с COM_RC_OVERRIDE 1 - СТОП.
# E: 07 (не менялся) с отчётом P1 доходит до подделки ssh, с отчётом P2 отказывает до ssh. Подделка ssh и страж - как в r13-r17a (tests\fake_ssh_r13.cs).
# K: r17b = r17a + только эта строка (и SHA256SUMS, README_r17b, DIFF_r17a_r17b, этот тест, proverka_r17b).
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r17b.ps1. Итог: «ИТОГ r17b: PASS n, FAIL m».
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try { [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'Idle' } catch { }
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r17b_' + (Get-Date).ToString('yyyyMMdd_HHmmss')); New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') { if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") } }
function Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
Remove-Item Env:BB_REGISTRY -ErrorAction SilentlyContinue; Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
$LC = Split-Path -Parent $Kit; if (-not (Test-Path -LiteralPath (Join-Path $LC 'bench_kit_20261117_r14'))) { $LC = Join-Path $env:USERPROFILE 'Documents\Claude local' }   # прогон на копии: соседи - только чтение настоящих
$RawSrc = Join-Path $LC 'bench_kit_20261117_r14\out\params_bench_20261119_143717.raw.txt'
$Reg = Join-Path $LC 'РЕЕСТР_НАСТРОЕК_ДРОНА.md'
$ApprA = Join-Path $LC 'bench_kit_20261119_r17a\params_check\approved_changes.txt'
$RE07 = '^=== СОВПАДАЕТ: прочитано (\d+) из \1, отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)'; $RE07g = '^=== СОВПАДАЕТ \(гироскоп сдвинулся: [1-9]\d*, запись\): прочитано (\d+) из \1, других отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)'   # оба вида, которые принимает 07 (второй - решение владельца 16.11, только CAL_GYRO*OFF)
# песочница: копия набора без tests, out, proverka_*, SHA256SUMS (её папка-родитель - «папка проекта» для 07)
$SBP = Join-Path $Run 'sb'; $SB = Join-Path $SBP 'bench_kit_20261119_r17b'
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Kit.Length + 1)
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -like '_aside\*' -or $rel -like 'proverka_*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null; Copy-Item -LiteralPath $_.FullName -Destination $dest
}
New-Item -ItemType Directory -Force -Path (Join-Path $SB 'out') | Out-Null

# ======================= P: оценщик 01 на настоящем ответе Pi (14:37) =======================
$haveRaw = Test-Path -LiteralPath $RawSrc
Check 'P0' ('настоящий ответ Pi 01 r14 19.11 14:37 есть (только чтение): ' + $RawSrc + '; в нём таблица MAVROS «P COM_RC_OVERRIDE i 3»') ($haveRaw -and ([IO.File]::ReadAllText($RawSrc)).Contains("`nP`tCOM_RC_OVERRIDE`ti`t3`n")) ''
function Compare-Run([string]$name, [string]$raw, [string]$approved = '') {
    $d = Join-Path $Run ('p_' + $name); New-Item -ItemType Directory -Path $d | Out-Null
    $a = '-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB 'params_check\compare_params.ps1') + '" -Events "' + $raw + '" -OutPrefix "' + (Join-Path $d 'params_bench_t') + '" -Registry "' + $Reg + '"'
    if ($approved) { $a += ' -Approved "' + $approved + '"' }
    $so = Join-Path $d 'console.txt'
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList $a -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $rp = Join-Path $d 'params_bench_t_report.txt'; $rt = $(if (Test-Path -LiteralPath $rp) { [IO.File]::ReadAllText($rp) } else { '' })
    return @{ Code = $p.ExitCode; Report = $rp; Text = $rt; First = $(if ($rt) { ($rt -split "`r?`n")[0].TrimStart([char]0xFEFF) } else { '' }) }
}
$p1 = $null; $p2 = $null
if ($haveRaw) {
    $raw1 = Join-Path $Run 'params_bench_20261119_143717.raw.txt'; Copy-Item -LiteralPath $RawSrc -Destination $raw1
    $p1 = Compare-Run 'r17b' $raw1
    Check 'P1' ('01 (оценщик r17b) на ответе 14:37: код 0, первая строка «=== СОВПАДАЕТ …» одного из двух видов, которые принимает 07, строки «COM_RC_OVERRIDE: на дроне» нет, в списке одобренных «COM_RC_OVERRIDE: 3 (одобрено 2026-11-19 …)»: ' + $p1.First) ($p1.Code -eq 0 -and ($p1.First -match $RE07 -or $p1.First -match $RE07g) -and -not $p1.Text.Contains('COM_RC_OVERRIDE: на дроне') -and $p1.Text.Contains('COM_RC_OVERRIDE: 3 (одобрено 2026-11-19; решение владельца 19.11 14:21')) ('code=' + $p1.Code)
    if (Test-Path -LiteralPath $ApprA) {
        $p0 = Compare-Run 'r17a_kontrol' $raw1 $ApprA
        Check 'P1k' ('контроль: тот же ответ с одобренными правками r17a (без строки COM_RC_OVERRIDE) - код 2, СТОП, «COM_RC_OVERRIDE: на дроне 3, ожидалось 1»: ' + $p0.First) ($p0.Code -eq 2 -and $p0.First.StartsWith('=== СТОП') -and $p0.Text.Contains('COM_RC_OVERRIDE: на дроне 3, ожидалось 1 (основа)')) ('code=' + $p0.Code)
    }
    # тот же ответ, но на дроне COM_RC_OVERRIDE 1 (строка таблицы MAVROS и оба события)
    $rawTxt = [IO.File]::ReadAllText($raw1); $n1 = ([regex]::Matches($rawTxt, "`nP`tCOM_RC_OVERRIDE`ti`t3`n")).Count
    $t2 = $rawTxt.Replace("`nP`tCOM_RC_OVERRIDE`ti`t3`n", "`nP`tCOM_RC_OVERRIDE`ti`t1`n")
    $t2 = [regex]::Replace($t2, '(E - name: COM_RC_OVERRIDE\r?\nE   value:\r?\nE     type: 2\r?\nE     bool_value: false\r?\nE     integer_value: )3', '${1}1')
    $nE = ([regex]::Matches($t2, 'E - name: COM_RC_OVERRIDE\r?\nE   value:\r?\nE     type: 2\r?\nE     bool_value: false\r?\nE     integer_value: 1')).Count
    $raw2 = Join-Path $Run 'params_bench_t_override1.raw.txt'; [IO.File]::WriteAllText($raw2, $t2, $utf8n)
    $p2 = Compare-Run 'override1' $raw2
    Check 'P2' ('тот же ответ, но COM_RC_OVERRIDE 1 (таблица ' + $n1 + ', событий ' + $nE + '): код 2, первая строка «=== СТОП …», строка «COM_RC_OVERRIDE: на дроне 1, ожидалось 3 …»: ' + $p2.First) ($n1 -eq 1 -and $nE -ge 1 -and $p2.Code -eq 2 -and $p2.First.StartsWith('=== СТОП') -and $p2.Text.Contains('COM_RC_OVERRIDE: на дроне 1, ожидалось 3')) ('code=' + $p2.Code + ' ' + (($p2.Text -split "`r?`n" | Where-Object { $_ -match 'COM_RC_OVERRIDE' }) -join ' | '))
}

# ======================= E: 07 видит новое значение (через отчёт 01) =======================
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
$FakeExe = Join-Path $FakeDir 'ssh.exe'
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh_r13.cs'))) -OutputAssembly $FakeExe -OutputType ConsoleApplication
$FakeSha = Sha $FakeExe; $Marker = 'BB_FAKE_SSH_R13_NO_NETWORK'
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath; $env:BB_NO_PAUSE = '1'
function Has-Marker([string]$p) { $l1 = [Text.Encoding]::GetEncoding(28591); return $l1.GetString([IO.File]::ReadAllBytes($p)).Contains($l1.GetString([Text.Encoding]::Unicode.GetBytes($Marker))) }
function Guard-Why([string]$src) { if (-not $src) { return 'ssh не найден' }; if ($src -ne $FakeExe) { return ('первый ssh в PATH - не подделка: ' + $src) }; if ((Sha $src) -ne $FakeSha) { return 'sha ssh не равен' }; if (-not (Has-Marker $src)) { return 'нет метки' }; return '' }
function Guard-Child {
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes('$c = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { [Console]::Out.Write($c.Source) }'))
    $gi = Join-Path $Run 'guard_in.txt'; if (-not (Test-Path -LiteralPath $gi)) { [IO.File]::WriteAllText($gi, '') }
    $go = Join-Path $Run ('guard_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -NonInteractive -EncodedCommand ' + $enc) -NoNewWindow -PassThru -RedirectStandardInput $gi -RedirectStandardOutput $go -RedirectStandardError ($go + '.err')
    $null = $p.Handle; if (-not $p.WaitForExit(60000)) { try { Stop-Process -Id $p.Id -Force } catch { }; return 'страж: нет ответа 60 с' }
    return (Guard-Why ([IO.File]::ReadAllText($go)).Trim())
}
function Guard-InProc { $c = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; return (Guard-Why $(if ($c) { $c.Source } else { '' })) }
$g = (Guard-InProc) + (Guard-Child)
Check 'G0' ('страж: первый ssh в PATH (здесь и в отдельном powershell) - собранная подделка с меткой ' + $Marker) ($g -eq '') $g
$conf = Join-Path $SB 'takeoff.conf'; $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
$cf = @{}; foreach ($l in [IO.File]::ReadAllLines($conf)) { $t9 = $l.Trim(); if ($t9 -eq '' -or $t9.StartsWith('#')) { continue }; $i = $t9.IndexOf('='); if ($i -gt 0) { $cf[$t9.Substring(0, $i).Trim()] = $t9.Substring($i + 1).Trim() } }
[IO.File]::WriteAllText($gate, ("ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-19 тест`r`nСЛОВА_ВЛАДЕЛЬЦА=тест r17b`r`nСКРИПТ_SHA256=" + $cf['SCRIPT_SHA256'] + "`r`nАРГУМЕНТЫ=`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
function Run07([string]$report, [string]$name) {
    $o = Join-Path $Run ('e_' + $name); New-Item -ItemType Directory -Path $o | Out-Null
    Copy-Item -LiteralPath $report -Destination (Join-Path $o 'params_bench_t_report.txt')
    foreach ($kn in 'install_check', 'mavros_check') { $c = Join-Path $o ($kn + '_20261119_080000.txt'); [IO.File]::WriteAllText($c, "BB_DONE`r`n# VERDICT OK`r`n", $utf8); (Get-Item -LiteralPath $c).LastWriteTime = (Get-Date).AddMinutes(-5) }
    foreach ($f in @(Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Name -notlike 'ssh.*' })) { Move-Item -LiteralPath $f.FullName -Destination (Join-Path $Run ('fake_old_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '_' + $f.Name)) }
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), 'normal'); [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), (('cd' * 32) + '  ' + $cf['SCRIPT_REMOTE_PATH']))
    $why = (Guard-InProc) + (Guard-Child); if ($why) { Check 'GUARD' ('страж: 07 НЕ запущен - ' + $why) $false ''; return @{ Code = -1; Console = ''; Calls = @() } }
    $env:BB_KIT_OUT = $o; $so = Join-Path $Run ('c07_' + $name + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB 'run_07_takeoff.ps1') + '" -SafetyConfirmed NET-TWO-KILL-YES') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
    $cl = Join-Path $FakeDir 'calls.log'; $calls = @(); if (Test-Path -LiteralPath $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    return @{ Code = $p.ExitCode; Console = ([IO.File]::ReadAllText($so) + [IO.File]::ReadAllText($so + '.err')); Calls = $calls }
}
Check 'E0' '07 r17b = r17a = r12 байт в байт (sha a6af9787…)' ((Sha (Join-Path $SB 'run_07_takeoff.ps1')) -eq 'a6af97877cc39b1f0de0cb98c1183ce8abc0f56af1ae1c4d83f7472a4a133b07') ''
if ($p1 -and (Test-Path -LiteralPath $p1.Report)) {
    $r = Run07 $p1.Report 'p1'
    Check 'E1' '07 с отчётом 01 r17b по ответу 14:37 (COM_RC_OVERRIDE 3): условие сверки настроек пройдено, 07 дошёл до подделки ssh (все вызовы - подделка), «сверка настроек» в отказах нет' ($r.Code -eq 4 -and $r.Calls.Count -ge 2 -and $r.Console -match 'sha256 не равен' -and $r.Console -notmatch 'взлёт не разрешён' -and @($r.Calls | Where-Object { $_ -notmatch $Marker }).Count -eq 0) ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console)
}
if ($p2 -and (Test-Path -LiteralPath $p2.Report)) {
    $r = Run07 $p2.Report 'p2'
    Check 'E2' '07 с отчётом 01 r17b при COM_RC_OVERRIDE 1 (СТОП): код 4, «взлёт не разрешён», к дрону не обращался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'взлёт не разрешён') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
}
Move-Item -LiteralPath $gate -Destination (Join-Path $Run 'gate_aside_TAKEOFF_APPROVED.txt')
$env:PATH = $oldPath

# ======================= K: r17b = r17a + одна строка =======================
$A = Join-Path $LC 'bench_kit_20261119_r17a'
if (Test-Path -LiteralPath $A) {
    $af = @(Get-ChildItem -LiteralPath $A -Recurse -File | ForEach-Object { $_.FullName.Substring($A.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and $_ -notmatch '^tests\\run_[^\\]+\\' })
    $diff = @($af | Where-Object { $k = Join-Path $Kit $_; -not (Test-Path -LiteralPath $k) -or (Sha $k) -ne (Sha (Join-Path $A $_)) })
    Check 'K1' ('все файлы r17a есть в r17b; изменены только params_check\approved_changes.txt и SHA256SUMS.txt (одинаковых ' + ($af.Count - $diff.Count) + ')') (@($diff | Where-Object { $_ -ne 'params_check\approved_changes.txt' -and $_ -ne 'SHA256SUMS.txt' }).Count -eq 0 -and $diff -contains 'params_check\approved_changes.txt') ($diff -join ', ')
    $ta = [IO.File]::ReadAllText((Join-Path $A 'params_check\approved_changes.txt')); $tb = [IO.File]::ReadAllText((Join-Path $Kit 'params_check\approved_changes.txt'))
    $add = $(if ($tb.StartsWith($ta)) { $tb.Substring($ta.Length) } else { '' })
    Check 'K2' 'approved_changes.txt r17b = r17a + ровно одна строка в конце «COM_RC_OVERRIDE TAB 3 TAB 2026-11-19 TAB решение владельца 19.11 14:21 …» (LF, без BOM)' ($add -ne '' -and ([regex]::Matches($add, "`n")).Count -eq 1 -and $add.EndsWith("`n") -and -not $add.Contains("`r") -and $add.StartsWith("COM_RC_OVERRIDE`t3`t2026-11-19`tрешение владельца 19.11 14:21 «COM_RC_OVERRIDE = 3? 2»") -and $add.Contains('поставил владелец в QGC 19.11 14:37') -and $add.Contains('params_bench_20261119_143717.params: COM_RC_OVERRIDE 3, COM_RC_STICK_OV 30')) $add
    $new = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object { $_.FullName.Substring($Kit.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and -not (Test-Path -LiteralPath (Join-Path $A $_)) -and $_ -notmatch '^(README_r17b\.md|DIFF_r17a_r17b\.txt|tests\\run_tests_r17b\.ps1|proverka_r17b\\.+|tests\\run_[^\\]+\\.+)$' })
    Check 'K3' 'новых файлов, кроме README_r17b, DIFF_r17a_r17b, теста r17b и proverka_r17b, нет; out\ пуст; разрешений в gates\ нет' ($new.Count -eq 0 -and @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -File -ErrorAction SilentlyContinue).Count -eq 0 -and -not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt'))) ($new -join ', ')
}
else { Check 'K0' 'папка r17a не найдена' $false $A }
Note ''
Note ('ИТОГ r17b: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
