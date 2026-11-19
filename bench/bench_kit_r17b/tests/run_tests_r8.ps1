# run_tests_r8.ps1 (Claude, 13.11.2026, набор r8) - тесты НОВОГО в r8 на ПК, в песочнице. К дрону не подключается: вместо ssh стоит подделка fake_ssh_r8.exe
# (первая в PATH; сеть не открывает). Скрипт Pi шага 25 (pi\r8_marker_wake.sh) проверяет run_tests_r8_pi.sh в WSL.
# K: r8 = копия r7 (список _aside\SHA256SUMS_r7_copy.txt, sha256 15c470d6...): все файлы r7 байт в байт, кроме ожидаемых правок; новых файлов - только ожидаемые; out\ пуст.
# V: сверка настроек v3 подключена: params_check\ = 8 файлов фикса /work/mavros_table_check_20261113/fix (params_read.sh 0f8894e1..., остальные 7 = kit_20261109_r4 байт в байт);
#    01 и 07 зовут params_check этого набора; путь к реестру по умолчанию = <Claude local>\РЕЕСТР_НАСТРОЕК_ДРОНА.md (неизменённый compare_params.ps1, только чтение реестра);
#    условие гейтов 05/05c/07 («из таблицы MAVROS N, из запасного потока 0») пропускает полный ответ v3 и не пропускает success=False;
#    цепочка 01 -> params_check v3 -> оценщик на подделке ssh: success=False -> в окне «Повторите 01 - не больше 2 раз, потом скажите Claude».
# W: шаг 25 r8 (25_metki_nomera.cmd, run_r8_metki.ps1) на подделке ssh: первая и последняя строки окна, wake, правила СТОП, НЕ ПРОВЕРЕНО, ошибки.
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r8.ps1. Итог: «ИТОГ r8: PASS n, FAIL m».
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r8_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
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
Remove-Item Env:BB_REGISTRY -ErrorAction SilentlyContinue

# ======================= K: копия r7 =======================
$r7s = Join-Path $Kit '_aside\SHA256SUMS_r7_copy.txt'
Check 'K1' 'список r7 лежит в _aside, sha256 = 15c470d6... (SHA256SUMS принятого r7), 367 строк' ((Test-Path -LiteralPath $r7s) -and (Sha $r7s) -eq '15c470d6a62052e360d17f175063a738d5ff19f6ee1f8f0e038338794b3d5e2f' -and @([IO.File]::ReadAllLines($r7s)).Count -eq 367) ''
$r7 = @{}; foreach ($l in [IO.File]::ReadAllLines($r7s)) { if ($l -match '^([0-9a-f]{64})  (.+)$') { $r7[$Matches[2]] = $Matches[1] } }
$diffR7 = @(); $missR7 = @()
foreach ($k in $r7.Keys) {
    $p = Join-Path $Kit ($k -replace '/', '\')
    if (-not (Test-Path -LiteralPath $p)) { $missR7 += $k; continue }
    if ((Sha $p) -ne $r7[$k]) { $diffR7 += $k }
}
Check 'K2' ('все ' + $r7.Count + ' файлов r7 есть в r8 (ничего не удалено и не перенесено)') ($r7.Count -eq 367 -and $missR7.Count -eq 0) ($missR7 -join ', ')
$chgWant = @('01_snimok_do.cmd', '07_vzlet_zagotovka.cmd', '25_metki_nomera.cmd', 'PROGRESS.md', 'README.md', 'cards/КАРТОЧКА_25_МЕТКИ_НОМЕРА.md', 'tests/run_tests_bench.ps1', 'tests/run_tests_r6.ps1', 'tests/run_tests_r7.ps1')
Check 'K3' ('изменены ровно ' + $chgWant.Count + ' файлов r7: 01 и 07 (params_check v3), 25 и его карточка (wake, СТОП), README, PROGRESS, три теста (поправки под r8)') ((@($diffR7 | Sort-Object) -join '|') -ceq (@($chgWant | Sort-Object) -join '|')) ($diffR7 -join ', ')
$newWant = @('SHA256SUMS.txt', 'DIFF_r7_r8.txt', '_aside/SHA256SUMS_r7_copy.txt', '_aside/r7_step25/25_metki_nomera.cmd', 'run_r8_metki.ps1', 'pi/r8_marker_wake.sh',
    'params_check/approved_changes.txt', 'params_check/compare_params.ps1', 'params_check/ignore_counters.txt', 'params_check/params_check.cmd', 'params_check/params_read.sh', 'params_check/profile_values.tsv', 'params_check/run_params_check.ps1',
    'tests/run_tests_r8.ps1', 'tests/run_tests_r8_pi.sh', 'tests/fake_ssh_r8.cs')
$allNow = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | Where-Object { $_.FullName -notmatch '\\tests\\run_r[0-9a-z_]*_\d{8}' -and $_.FullName -notmatch '\\tests\\run_[a-z]_\d{8}' } | ForEach-Object { (Rel $_.FullName) -replace '\\', '/' })
$unexp = @($allNow | Where-Object { -not $r7.ContainsKey($_) -and $_ -notin $newWant -and $_ -notlike 'tests/pystub_r8/*' -and $_ -notlike 'proverka_r8/*' })
Check 'K4' 'новых файлов в r8 - только ожидаемые (params_check v3, шаг 25 r8, r7-версия 25 в _aside, тесты, proverka_r8, суммы, DIFF)' ($unexp.Count -eq 0) ($unexp -join ', ')
$miss = @($newWant | Where-Object { $_ -ne 'SHA256SUMS.txt' -and $_ -ne 'DIFF_r7_r8.txt' -and $_ -notin $allNow })
Check 'K4b' 'все ожидаемые новые файлы на месте' ($miss.Count -eq 0) ($miss -join ', ')
$outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -Force -ErrorAction SilentlyContinue)
Check 'K5' 'папка out\ в r8 есть и пуста (ответы сессии лягут сюда)' ((Test-Path -LiteralPath (Join-Path $Kit 'out')) -and $outFiles.Count -eq 0) ($outFiles.Name -join ', ')
Check 'K6' 'набор r8 лежит в Claude local рядом с r7 (не внутри СЕССИЯ_20261113_v2)' ((Split-Path $Kit -Leaf) -eq 'bench_kit_20261113_r8' -and (Test-Path -LiteralPath (Join-Path (Split-Path $Kit) 'bench_kit_20261113_r7'))) (Split-Path $Kit)
Check 'K7' 'r7-версия 25_metki_nomera.cmd в _aside\r7_step25 байт в байт = 25 из r7 (92fbf590...)' ((Sha (Join-Path $Kit '_aside\r7_step25\25_metki_nomera.cmd')) -eq $r7['25_metki_nomera.cmd'] -and $r7['25_metki_nomera.cmd'] -eq '92fbf5907704b03db11590a3de8130f7cdefaad9f75d73d50e2597518833c279') ''

# ======================= V: сверка настроек v3 =======================
$PC = Join-Path $Kit 'params_check'
$want = [ordered]@{ 'approved_changes.txt' = 'cce6676e8b91bf9f9df957fe19d55fb9db4f37fa3b96c63e52f709855dc67c8c'; 'baseline_20261104_1145.params' = '3eab859527afe4a44f777467c60b5c873a7ec9c25ead47babdd939c2e378c58b'
    'compare_params.ps1' = '35d55b94ebeb75e0f3ad586831dc4642dd896f7d42faebbbec24df21081b0404'; 'ignore_counters.txt' = 'a52b76c5b6933eb3322afb6f0ef635d74be4e56e07e0d4383dfdf4099a658aec'
    'params_check.cmd' = 'ba93b3ead96c84aad6af9855d1172e0e701a2742163a09f6fe809fd5310f2471'; 'params_read.sh' = '0f8894e1d8089441fb332fb941c7666db56978ffc6ac1897ce6f670a79e6aeb3'
    'profile_values.tsv' = '838868fc9c2e0ceb33d406dad94bde471ee38b4d9a9a878ae2293449da808094'; 'run_params_check.ps1' = '9981f55a71e0662f469a6f39248ed2b33b283de3efb941ae94b82af297606af1' }
$have = @(Get-ChildItem -LiteralPath $PC -File | ForEach-Object { $_.Name } | Sort-Object)
$shaBad = @($want.Keys | Where-Object { -not (Test-Path -LiteralPath (Join-Path $PC $_)) -or (Sha (Join-Path $PC $_)) -ne $want[$_] })
Check 'V1' 'params_check\ = ровно 8 файлов фикса (SHA256SUMS /work/mavros_table_check_20261113/fix), params_read.sh v3 = 0f8894e1...' ((($have -join '|') -ceq (@($want.Keys | Sort-Object) -join '|')) -and $shaBad.Count -eq 0) (($have -join ', ') + ' / не та sha: ' + ($shaBad -join ', '))
$r4pc = Join-Path (Split-Path $Kit) 'kit_20261109_r4\params_check'
$r4bad = @($want.Keys | Where-Object { $_ -ne 'params_read.sh' -and (Sha (Join-Path $r4pc $_)) -ne (Sha (Join-Path $PC $_)) })
Check 'V2' '7 файлов (оценщик compare_params.ps1, основа, одобренные правки, профили, счётчики, params_check.cmd, run_params_check.ps1) байт в байт = kit_20261109_r4; params_read.sh отличается от v2 r4 (256c8890...)' ($r4bad.Count -eq 0 -and (Sha (Join-Path $r4pc 'params_read.sh')) -eq '256c88907d0d51d20a995dcdbae65cef83e450598a5eef48a963d5023b230d81' -and (Sha (Join-Path $PC 'params_read.sh')) -ne (Sha (Join-Path $r4pc 'params_read.sh'))) ($r4bad -join ', ')
$c01 = [IO.File]::ReadAllText((Join-Path $Kit '01_snimok_do.cmd')); $c07 = [IO.File]::ReadAllText((Join-Path $Kit '07_vzlet_zagotovka.cmd'))
Check 'V3' '01 и 07 зовут params_check этого набора: set "PCC=%~dp0params_check\params_check.cmd", call "%PCC%" -Stamp bench_ / after_flight_; про r4 ни слова' ($c01.Contains('set "PCC=%~dp0params_check\params_check.cmd"') -and $c01.Contains('call "%PCC%" -Stamp bench_%STAMP%') -and $c07.Contains('set "PCC=%~dp0params_check\params_check.cmd"') -and $c07.Contains('call "%PCC%" -Stamp after_flight_%STAMP%') -and $c01 -notmatch 'kit_20261109_r4|R4PC' -and $c07 -notmatch 'kit_20261109_r4|R4PC') ''
$r4refs = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | Where-Object { $_.Extension -in '.cmd', '.ps1', '.sh', '.py' } | Where-Object { $_.FullName -notmatch '\\tests\\|\\proverka_r[0-9]\\|\\_aside\\|\\image_r2j\\payload\\' } | Where-Object { [IO.File]::ReadAllText($_.FullName) -match 'kit_20261109_r4\\params_check' } | ForEach-Object { Rel $_.FullName })
Check 'V3b' 'ни один шаг набора (кроме тестов и _aside) не берёт params_check из kit_20261109_r4' ($r4refs.Count -eq 0) ($r4refs -join ', ')
$cp = [IO.File]::ReadAllText((Join-Path $PC 'compare_params.ps1'))
$regWant = Join-Path (Split-Path -Parent (Split-Path -Parent $PC)) 'РЕЕСТР_НАСТРОЕК_ДРОНА.md'
Check 'V4' ('реестр по умолчанию у compare_params.ps1 = две папки вверх от params_check: ' + $regWant + ' (файл есть; BB_REGISTRY не нужен)') ($cp.Contains("else { `$Registry = Join-Path (Split-Path -Parent (Split-Path -Parent `$here)) 'РЕЕСТР_НАСТРОЕК_ДРОНА.md' }") -and $regWant -eq (Join-Path (Split-Path $Kit) 'РЕЕСТР_НАСТРОЕК_ДРОНА.md') -and (Split-Path (Split-Path $Kit) -Leaf) -eq 'Claude local' -and (Test-Path -LiteralPath $regWant)) $regWant
# синтетический ответ v3 (только чтение файлов ПК): таблица MAVROS = основа компонента 1 (типы как в основе: 6 -> i, иначе d)
$tbl = New-Object Text.StringBuilder
foreach ($l in [IO.File]::ReadAllLines((Join-Path $PC 'baseline_20261104_1145.params'))) { if ($l -match "^1`t1`t") { $f = $l.Split("`t"); $kk = $(if ($f[4] -eq '6') { 'i' } else { 'd' }); [void]$tbl.Append("P`t" + $f[2] + "`t" + $kk + "`t" + $f[3] + "`n") } }
$evOk = "PULL`tNOTE`tdone success=True received=1108`n" + $tbl.ToString() + "PULL`tNOTE`ttable v3: requests 8, answers per request 12..12, full answers per request 1..1, conflicts 0, read 1107 of 1107`n"
$evBad = "PULL`tNOTE`tdone success=False received=1050`nPULL`tFAILED`tsuccess=False`n" + $tbl.ToString() + "PULL`tNOTE`ttable v3: requests 8, answers per request 12..12, full answers per request 1..1, conflicts 0, read 1107 of 1107`n"
[IO.File]::WriteAllText((Join-Path $Run 'ev_ok.raw.txt'), $evOk, $utf8n); [IO.File]::WriteAllText((Join-Path $Run 'ev_bad.raw.txt'), $evBad, $utf8n)
function Cmp([string]$ev, [string]$tag) {
    $pfx = Join-Path $Run ('params_' + $tag)
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PC 'compare_params.ps1') + '" -Events "' + (Join-Path $Run $ev) + '" -OutPrefix "' + $pfx + '"') -NoNewWindow -PassThru -Wait -RedirectStandardOutput ($pfx + '.console.txt') -RedirectStandardError ($pfx + '.console.err.txt')
    $rep = @(); if (Test-Path -LiteralPath ($pfx + '_report.txt')) { $rep = @([IO.File]::ReadAllLines($pfx + '_report.txt')) }
    return @{ Code = $p.ExitCode; Rep = $rep; First = $(if ($rep.Count) { $rep[0] } else { '' }) }
}
$c = Cmp 'ev_ok.raw.txt' 'reg'
Check 'V5' 'неизменённый compare_params.ps1 r8 без -Registry и без BB_REGISTRY читает реестр Claude local\РЕЕСТР_НАСТРОЕК_ДРОНА.md (строка «Реестр настроек» в отчёте, «Реестр не найден» нет)' (($c.Rep -contains ('Реестр настроек (только чтение): ' + $regWant)) -and -not ($c.Rep | Where-Object { $_ -match 'Реестр не найден' })) (($c.Rep | Where-Object { $_ -match 'Реестр' }) -join ' | ')
$gateTexts = @{ '05' = (Join-Path $Kit 'image_r2j\check_gates.ps1'); '05c' = (Join-Path $Kit 'image_r2j_cam\check_gates_r2j_cam.ps1'); '07' = (Join-Path $Kit 'run_07_takeoff.ps1') }
$gateRx = @{}
foreach ($g in $gateTexts.Keys) { $m = [regex]::Match([IO.File]::ReadAllText($gateTexts[$g]), "\`$first -notmatch '(\^=== СОВПАДАЕТ[^']+)'"); if ($m.Success) { $gateRx[$g] = $m.Groups[1].Value } }
$sameRx = @($gateRx.Values | Sort-Object -Unique)
Check 'V6' 'условие гейтов 05, 05c и 07 одно и то же («СОВПАДАЕТ ... из таблицы MAVROS N, из запасного потока 0»); гейты не менялись (файлы как в r7)' ($gateRx.Count -eq 3 -and $sameRx.Count -eq 1 -and $sameRx[0] -ceq '^=== СОВПАДАЕТ: прочитано (\d+) из \1, отличий нет \(из таблицы MAVROS \1, из запасного потока 0\)' -and (Sha $gateTexts['05']) -eq $r7['image_r2j/check_gates.ps1'] -and (Sha $gateTexts['05c']) -eq $r7['image_r2j_cam/check_gates_r2j_cam.ps1'] -and (Sha $gateTexts['07']) -eq $r7['run_07_takeoff.ps1']) ($gateRx.Values -join ' | ')
$env:BB_REGISTRY = Join-Path $Run 'нет_реестра.md'
$c = Cmp 'ev_ok.raw.txt' 'ok'
Check 'V7' 'полный ответ v3 (1107 из 1107, ParamPull success=True), без реестра: код 0, первая строка проходит условие гейтов 05/05c/07' ($c.Code -eq 0 -and $c.First -match $sameRx[0]) $c.First
$c = Cmp 'ev_bad.raw.txt' 'bad'
Check 'V8' 'ParamPull success=False (потеря PARAM_VALUE): код 3 «НЕ ПОДТВЕРЖДЕНО: ParamPull вернул success=False», условие гейтов НЕ проходит (безопасный отказ, как было)' ($c.Code -eq 3 -and $c.First.StartsWith('=== НЕ ПОДТВЕРЖДЕНО: ParamPull вернул success=False') -and $c.First -notmatch $sameRx[0]) $c.First
Remove-Item Env:BB_REGISTRY -ErrorAction SilentlyContinue

# ======================= песочница и подделки (для V-цепочки и W) =======================
$SB = Join-Path $Run 'sb\bench_kit_r8'
New-Item -ItemType Directory -Path $SB -Force | Out-Null
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = Rel $_.FullName
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest
}
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh_r8.cs'))) -OutputAssembly (Join-Path $FakeDir 'ssh.exe') -OutputType ConsoleApplication
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'
$sshNow = (Get-Command ssh -CommandType Application | Select-Object -First 1).Source
Check 'T0' 'в PATH первой стоит подделка ssh (настоящий OpenSSH в тестах не вызывается)' ($sshNow -eq (Join-Path $FakeDir 'ssh.exe')) $sshNow
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
function LastLine([string]$t) { $l = @($t -split "`r?`n" | Where-Object { $_.Trim() -ne '' }); if ($l.Count) { return $l[-1].Trim() } else { return '' } }

# ======================= V: цепочка 01 -> params_check v3 -> оценщик (подделка ssh) =======================
$canPi = "PI_DATE 2026-11-13 08:00:00 +0400`nPI_MODEL Raspberry Pi 5 Model B`nPI_LOADAVG 0.41 0.35 0.30`nPI_TEMP temp=48.2'C`nPI_THROTTLED throttled=0x0`nPI_BUMBLEBEE_SERVICE active`nPI_MAVROS_STATE_ONE_SAMPLE:`n  connected: true`n  armed: false`nBB_PI_STATE_DONE`n"
$o = New-Out; Reset-Fake; Set-Canned 'pi_state' $canPi; Set-Canned 'params' $evBad
$r = Run-Cmd '01_snimok_do.cmd' '' $o
$rep = @(Get-ChildItem -LiteralPath $o -File -Filter 'params_bench_*_report.txt')
$first = ''; if ($rep.Count -eq 1) { $first = [IO.File]::ReadAllLines($rep[0].FullName)[0] }
$pcall = @($r.Calls | Where-Object { $_ -match ' key=params ' })
Check 'V9' '01 из песочницы, ParamPull success=False: params_check этого набора прочитал таблицу через params_read.sh v3 (sha посланного скрипта 0f8894e1...), отчёт в out набора «НЕ ПОДТВЕРЖДЕНО»' ($pcall.Count -eq 1 -and $pcall[0] -match 'payload_sha=0f8894e1d8089441fb332fb941c7666db56978ffc6ac1897ce6f670a79e6aeb3' -and $first.StartsWith('=== НЕ ПОДТВЕРЖДЕНО: ParamPull вернул success=False')) ($first + ' / ' + ($pcall -join ' '))
Check 'V10' 'окно 01 простыми словами: «НЕ ПОДТВЕРЖДЕНО ... Повторите 01 - не больше 2 раз, потом скажите Claude.»' ($r.Console -match 'НЕ ПОДТВЕРЖДЕНО: настройки прочитаны не полностью, например ParamPull success=False\. Повторите 01 - не больше 2 раз, потом скажите Claude\.') (LastLine $r.Console)
$o = New-Out; Reset-Fake; Set-Canned 'pi_state' $canPi; Set-Canned 'params' $evOk
$r = Run-Cmd '01_snimok_do.cmd' '' $o
$rep = @(Get-ChildItem -LiteralPath $o -File -Filter 'params_bench_*_report.txt'); $first = ''; if ($rep.Count -eq 1) { $first = [IO.File]::ReadAllLines($rep[0].FullName)[0] }
Check 'V11' '01 из песочницы, полный ответ v3: «Готово: настройки PX4 совпали», первая строка отчёта проходит условие гейтов 05/05c/07' ($r.Console -match 'Готово: настройки PX4 совпали с утверждённым набором' -and $first -match $sameRx[0]) $first

# ======================= W: шаг 25 r8 на подделке ssh =======================
$SH25 = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r8_marker_wake.sh')) -replace "`r`n", "`n"
# в песочнице у 25 убрана строка chcp 65001: она мешает set /p читать ответы из файла (как в тестах r6 и r7; в боевом файле она на месте)
$ls = [IO.File]::ReadAllText((Join-Path $SB '25_metki_nomera.cmd')) -split "`r`n"
[IO.File]::WriteAllText((Join-Path $SB '25_metki_nomera.cmd'), (($ls | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
$REM = 'Перед взлётом выключите и включите дрон или сверьте позицию EKF с рулеткой'
$MAPOK = 'MN_MAP file=/home/lb/ros2_ws/install/aruco_pose/share/aruco_pose/map/map.txt sha256=528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611 ids=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,18,19,20 m0=0.000,0.000,-0.320'
# ответ Pi (pi\r8_marker_wake.sh): номера (по сообщению, -1 = пустое сообщение), позы «x,y», строки RESEEDED ('x,y,z' или 'bad'), журнал, карта
function Rep8([string]$label, [int[]]$ids = @(), [object[]]$poses = @(), [string[]]$reseed = @(), [string]$log = 'ok', [int]$logTo = 1000, [string]$map = $MAPOK, [int]$claimMsgs = -1, [int]$claimPoses = -1, [string]$cam = 'yes') {
    $mode = $(if ($label -eq 'pre') { 'pre' } else { 'rec' })
    $s = "MN_META script r8_marker_wake.sh mode=$mode seconds=10 label=$label logfrom=start date=2026-11-13 10:00:00`n" + $map + "`nMN_STATE connected=True armed=False mode=POSCTL`nMN_WAKE sent=12 topic=/aruco_detect/wake hz=1 warmup_s=2`n"
    $n = 0; $wm = 0; $cnt = @{}
    foreach ($i in $ids) {
        $n++
        if ($i -lt 0) { $s += ('MN_MSG t=' + ('{0:F3}' -f ($n * 0.08)) + " n=0`n"); continue }
        $wm++; $cnt[$i] = 1 + [int]$cnt[$i]; $s += ('MN_MSG t=' + ('{0:F3}' -f ($n * 0.08)) + ' n=1 id=' + $i + " ctr=351.5,253.5 c=466.0,399.0;239.0,402.0;237.0,109.0;464.0,104.0`n")
    }
    $np = 0
    foreach ($p in $poses) { $np++; $xy = ([string]$p) -split ','; $s += ('MN_POSE t=' + ('{0:F3}' -f ($np * 0.1)) + ' x=' + $xy[0] + ' y=' + $xy[1] + " z=-0.220 yaw=1.571`n") }
    $s += "MN_EKF n=50 x=0.010 y=0.000 z=-0.010 (последняя /mavros/local_position/pose, сведения)`n"
    if ($claimMsgs -ge 0) { $n = $claimMsgs }; if ($claimPoses -ge 0) { $np = $claimPoses }
    $s += "MN_DETECTOR label=$label publishers=1 nodes=aruco_detect camera_subscription=$cam msgs=$n with_markers=$wm poses=$np seconds=10`n"
    if ($log -eq 'ok') { $s += "MN_LOG file=/tmp/bumblebee.log readable=yes from=500 to=$logTo rotated=no cut=no lines=20 reseeded=$($reseed.Count) deferred=0 rejected=0`n" } else { $s += "MN_LOG file=/tmp/bumblebee.log readable=no reason=PermissionError`n" }
    foreach ($rs in $reseed) {
        if ($rs -eq 'bad') { $s += "MN_RESEED reason=unparsed x=na y=na z=na line=vpe_fix: gate RESEEDED garbled`n"; continue }
        $xyz = $rs -split ','
        $s += ('MN_RESEED reason=xy-jump x=' + $xyz[0] + ' y=' + $xyz[1] + ' z=' + $xyz[2] + ' line=[vpe_fix]: vpe_fix: gate RESEEDED (xy-jump) age=1.20s new_xyz=(' + $rs + ")`n")
    }
    $idsTxt = (@($cnt.Keys | Sort-Object | ForEach-Object { [string]$_ + ':' + $cnt[$_] }) -join ','); if ($idsTxt -eq '') { $idsTxt = 'none' }
    $s += "MN_END label=$label msgs=$n with_markers=$wm ids=$idsTxt poses=$np`nBB_R8MN_DONE rc=0`n"
    return $s
}
$z100 = @(@(0) * 97 + @(-1) * 3)
function Poses([double]$dist, [int]$k = 30) { $d = $dist.ToString('0.000', [Globalization.CultureInfo]::InvariantCulture); return @(1..$k | ForEach-Object { '0.000,-' + $d }) }   # позы «x,y»: центр дрона на $dist м за меткой 0
$preAwake = Rep8 'pre' (@(0) * 50) (Poses 0.0 10) @() 'ok' 1000
$preSleep = Rep8 'pre' @() @() @() 'ok' 1000 $MAPOK -1 -1 'no'
$cmOf = @{ 'p00cm' = 0.0; 'p05cm' = 0.05; 'p10cm' = 0.10; 'p15cm' = 0.15 }; $toOf = @{ 'p00cm' = 2000; 'p05cm' = 3000; 'p10cm' = 4000; 'p15cm' = 5000 }
function Set-AllRec([hashtable]$byLabel) { foreach ($l in 'p00cm', 'p05cm', 'p10cm', 'p15cm') { $t = $byLabel[$l]; if (-not $t) { $t = Rep8 $l $z100 (Poses $cmOf[$l]) @() 'ok' $toOf[$l] }; Set-Canned ('w8_' + $l) $t } }
function Sum([string]$out) { $f = @(Get-ChildItem -LiteralPath $out -File -Filter 'metki_nomera_*.txt' | Where-Object { $_.Name -match '^metki_nomera_\d{8}_\d{6}\.txt$' }); if ($f.Count -eq 1) { return [IO.File]::ReadAllText($f[0].FullName) } else { return '' } }
function Keys($r) { return (@($r.Calls | ForEach-Object { if ($_ -match 'key=(\S*)') { $Matches[1] } }) -join ',') }
$ALL4 = "0`r`n5`r`n10`r`n15`r`n"

$c25 = [IO.File]::ReadAllText((Join-Path $Kit '25_metki_nomera.cmd')); $b25 = [IO.File]::ReadAllBytes((Join-Path $Kit '25_metki_nomera.cmd')); $l25 = $c25 -split "`r`n"
Check 'W1' '25: UTF-8 без BOM, CRLF; строки 1-2 @echo off и chcp 65001; первая строка «МЕНЯЕТ ДРОН: временно» с Что, Зачем, Как вернуть, wake, EKF, моторы; без < > | & ^ % и скобок' ($b25[0] -ne 0xEF -and ([regex]::Matches($c25, "`r`n")).Count -eq ([regex]::Matches($c25, "`n")).Count -and $l25[0] -ceq '@echo off' -and $l25[1] -ceq 'chcp 65001 >nul' -and $l25[2].StartsWith('echo МЕНЯЕТ ДРОН: временно') -and $l25[2] -match 'Что:' -and $l25[2] -match 'Зачем:' -and $l25[2] -match 'Как вернуть:' -and $l25[2] -match '/aruco_detect/wake' -and $l25[2] -match 'EKF' -and $l25[2] -match 'моторы' -and $l25[2] -notmatch '[<>|&^%()]' -and $l25[2] -notmatch 'ТОЛЬКО ЧТЕНИЕ') $l25[2]
$psLines = @($l25 | Where-Object { $_.StartsWith('powershell -NoProfile -ExecutionPolicy Bypass -File') })
Check 'W2' '25: проверка имени ПК и файлов до запуска; нет ssh, scp, sudo; один set /p; каждый вызов run_r8_metki.ps1 со вводом из nul (4 фазы); run_r7_metki.ps1 не вызывается' ($c25 -match 'if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E"' -and $c25 -match 'for %%F in \(run_r8_metki\.ps1 lib\\bb_common\.ps1 lib\\bb_r6\.ps1 pi\\r8_marker_wake\.sh\)' -and $c25 -notmatch '(?i)\bssh\b|\bscp\b|\bsudo\b' -and ([regex]::Matches($c25, 'set /p')).Count -eq 1 -and $psLines.Count -eq 4 -and @($psLines | Where-Object { $_.EndsWith(' < nul') }).Count -eq 4 -and $c25 -notmatch 'run_r7_metki|r7_marker_ids') ''
$i1 = [array]::IndexOf($l25, ('echo ' + $REM)); $iFin = [array]::IndexOf($l25, ':fin'); $iDie = [array]::IndexOf($l25, ':die')
$remLines = @(for ($i = 0; $i -lt $l25.Count; $i++) { if ($l25[$i] -ceq ('echo ' + $REM)) { $i } })
Check 'W3' '25: напоминание «Перед взлётом выключите и включите дрон или сверьте позицию EKF с рулеткой» - последняя строка вывода и после итога (:fin), и после СТОП (:die)' ($remLines.Count -eq 2 -and $remLines[0] -gt $iFin -and $l25[$remLines[0] + 1] -ceq 'if not defined BB_NO_PAUSE pause' -and $remLines[1] -gt $iDie -and $l25[$remLines[1] + 1] -ceq 'if not defined BB_NO_PAUSE pause') ($remLines -join ',')
$refs7 = @(Get-ChildItem -LiteralPath $Kit -File -Filter '*.cmd' | Where-Object { [IO.File]::ReadAllText($_.FullName) -match 'run_r7_metki|r7_marker_ids' } | ForEach-Object { $_.Name })
Check 'W4' 'ни один .cmd в корне r8 не вызывает шаг 25 r7 (run_r7_metki.ps1, pi\r7_marker_ids.sh остались только для тестов r7)' ($refs7.Count -eq 0) ($refs7 -join ', ')
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preSleep
$r = Run-Cmd '25_metki_nomera.cmd' '' $o 'OTHER-PC'
Check 'W5' '25: чужой ПК - код 4, к дрону не обращались; последняя строка окна - напоминание про EKF' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and (LastLine $r.Console) -ceq $REM) ('code=' + $r.Code + ' last=' + (LastLine $r.Console))
$o = New-Out; Reset-Fake 'wrong_host'; Set-Canned 'w8_pre' $preSleep
$r = Run-Cmd '25_metki_nomera.cmd' '' $o
Check 'W6' '25: на связи не bumblebee-20ec - код 4, скрипт на Pi не послан' ($r.Code -eq 4 -and $r.Calls.Count -eq 1 -and $r.Calls[0] -match 'HOST_OK' -and $r.Sent.Count -eq 0) ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preSleep; Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W7' '25: детектор молчит и с wake (как rc3: 7eb7bdf3 wake не слушает) - код 6 НЕ ПРОВЕРЕНО, точки не записывались, в тексте wake и rc3; последняя строка окна - напоминание' ($r.Code -eq 6 -and $r.Calls.Count -eq 2 -and (LastLine $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'хотя Pi слал сигнал wake' -and $s -match 'На rc3 детектор' -and $r.Console -match 'НЕ ПРОВЕРЕНО' -and $r.Console -notmatch 'Точка 1 из 4' -and (LastLine $r.Console) -ceq $REM) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Check 'W8' '25: на Pi ушёл ровно pi\r8_marker_wake.sh (тот же текст, LF) с аргументами «pre 6 pre start»; первая строка сводки - «# МЕНЯЕТ ДРОН временно», вторая - про EKF' ($r.Sent.Count -eq 1 -and $r.Sent[0] -ceq $SH25 -and $r.Calls[1] -match '\| base64 -d\)\\?" _ pre 6 pre start' -and ($s -split "`r?`n")[0].TrimStart([char]0xFEFF).StartsWith('# МЕНЯЕТ ДРОН временно: шаг 25') -and ($s -split "`r?`n")[1] -match 'сверить позицию EKF с рулеткой') $r.J
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' ($MAPOK + "`nMN_STATE connected=True armed=True mode=POSCTL`nMN_REFUSED armed (дрон взведён: шаг только для невзведённого дрона; wake не посылался)`nBB_R8MN_DONE rc=3`n") 3
$r = Run-Cmd '25_metki_nomera.cmd' '' $o; $s = Sum $o
Check 'W9' '25: дрон взведён - код 3 НЕ НАЧАТО, «Детектор не будился», точки не записывались' ($r.Code -eq 3 -and $r.Calls.Count -eq 2 -and (LastLine $s) -ceq '# VERDICT NOT_STARTED' -and $s -match 'Детектор не будился' -and $r.Console -match 'НЕ НАЧАТО') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W10' '25: всё чисто (только номер 0, позы на рулетке, RESEEDED нет, журнал прочитан) - код 0, VERDICT OK, перед каждой точкой снова имя дрона; последняя строка окна - напоминание' ($r.Code -eq 0 -and (Keys $r) -ceq ',w8_pre,,w8_p00cm,,w8_p05cm,,w8_p10cm,,w8_p15cm' -and (LastLine $s) -ceq '# VERDICT OK' -and ([regex]::Matches($s, '(?m)^ТОЧКА \d+ см: сообщений 100, кадров с метками 97, номера 0:97, поз 30, отклонение позы от рулетки до 0\.000 м, RESEEDED 0, журнал vpe_fix прочитан, EKF .* \| ФЛАГИ: -\s*$')).Count -eq 4 -and $r.Console -match 'Готово: во всех 4 точках только номер 0' -and (LastLine $r.Console) -ceq $REM) ((Keys $r) + ' code=' + $r.Code)
Check 'W11' '25: журнал стека читается без пропусков: каждая точка получает байт конца прошлой фазы (pre 1000 -> p00cm, 2000 -> p05cm, 3000 -> p10cm, 4000 -> p15cm)' ($r.Calls[3] -match '_ rec 10 p00cm 1000\s*\]' -and $r.Calls[5] -match '_ rec 10 p05cm 2000\s*\]' -and $r.Calls[7] -match '_ rec 10 p10cm 3000\s*\]' -and $r.Calls[9] -match '_ rec 10 p15cm 4000\s*\]') $r.J
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p10cm' = (Rep8 'p10cm' (@(0) * 80 + @(5) * 3) (Poses 0.10) @() 'ok' 4000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W12' '25: номер 5 (с карты) в точке 10 см - «ЛОЖНЫЙ НОМЕР С КАРТЫ — СТОП», код 5, запись прекращена (15 см не писалась), VERDICT STOP; напоминание последней строкой' ($r.Code -eq 5 -and (Keys $r) -ceq ',w8_pre,,w8_p00cm,,w8_p05cm,,w8_p10cm' -and (LastLine $s) -ceq '# VERDICT STOP' -and $s -match 'ЛОЖНЫЙ НОМЕР С КАРТЫ — СТОП: номер 5 — 3 раз' -and $r.Console -match 'СТОП: ложный номер или поза' -and (LastLine $r.Console) -ceq $REM) ((Keys $r) + ' code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p05cm' = (Rep8 'p05cm' (@(0) * 80 + @(38) * 7) (Poses 0.05) @() 'ok' 3000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W13' '25: номер 38 (не с карты) - «ЛОЖНЫЙ НОМЕР — СТОП ... на карте его нет», код 5, дальше 5 см не пошли' ($r.Code -eq 5 -and (Keys $r) -ceq ',w8_pre,,w8_p00cm,,w8_p05cm' -and $s -match 'ЛОЖНЫЙ НОМЕР — СТОП: номер 38 — 7 раз \(на карте его нет\)' -and $s -notmatch 'С КАРТЫ') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p00cm' = (Rep8 'p00cm' (@(0) * 80 + @(17) * 2) (Poses 0.0) @() 'ok' 2000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W14' '25: номер 17 (его на карте нет: 0-20 без 17) - «ЛОЖНЫЙ НОМЕР — СТОП ... на карте его нет», код 5' ($r.Code -eq 5 -and $s -match 'ЛОЖНЫЙ НОМЕР — СТОП: номер 17 — 2 раз \(на карте его нет\)') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' (Rep8 'pre' (@(0) * 50 + @(9) * 2) (Poses 0.0 10) @() 'ok' 1000); Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W15' '25: ложный номер 9 с карты уже в проверке (дрон над меткой 0) - код 5 СТОП сразу, точки не писались' ($r.Code -eq 5 -and $r.Calls.Count -eq 2 -and $s -match 'СТОП \(проверка, дрон над меткой 0\): ЛОЖНЫЙ НОМЕР С КАРТЫ — СТОП: номер 9' -and (LastLine $s) -ceq '# VERDICT STOP') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p10cm' = (Rep8 'p10cm' $z100 (@(Poses 0.10 20) + @('0.000,-0.251')) @() 'ok' 4000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W16' '25: в точке 10 см одна поза в 0,251 м от метки 0 (отклонение 0,151 > 0,15) - «ПОЗА ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП», код 5' ($r.Code -eq 5 -and $s -match 'ПОЗА ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП: 1 из 21 поз; по позе от центра метки 0 0\.100…0\.251 м, по рулетке 0\.100 м' -and (Keys $r) -ceq ',w8_pre,,w8_p00cm,,w8_p05cm,,w8_p10cm') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p10cm' = (Rep8 'p10cm' $z100 (@(Poses 0.10 20) + @('0.000,-0.249')) @() 'ok' 4000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W17' '25: поза в 0,249 м от метки 0 при рулетке 10 см (отклонение 0,149) - не СТОП, итог код 0' ($r.Code -eq 0 -and (LastLine $s) -ceq '# VERDICT OK' -and $s -match 'ТОЧКА 10 см: .*отклонение позы от рулетки до 0\.149 м') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p15cm' = (Rep8 'p15cm' $z100 (Poses 0.31) @() 'ok' 5000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W18' '25: в точке 15 см позы в 0,31 м (отклонение 0,16) - СТОП, код 5 (проверяется и дальняя сторона)' ($r.Code -eq 5 -and $s -match 'ТОЧКА 15 см: .*ПОЗА ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП: 30 из 30 поз') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p05cm' = (Rep8 'p05cm' $z100 (Poses 0.05) @('3.400,0.000,-0.220') 'ok' 3000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W19' '25: в журнале vpe_fix «gate RESEEDED» на позу 3,4 м (как фантом в Gazebo) - «RESEEDED НА ПОЗУ ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП», код 5' ($r.Code -eq 5 -and $s -match 'RESEEDED НА ПОЗУ ДАЛЬШЕ 0,15 м ОТ РУЛЕТКИ — СТОП: от центра метки 0 3\.400 м, по рулетке 0\.050 м' -and (Keys $r) -ceq ',w8_pre,,w8_p00cm,,w8_p05cm') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p05cm' = (Rep8 'p05cm' $z100 (Poses 0.05) @('0.000,-0.060,-0.220') 'ok' 3000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W20' '25: RESEEDED на позу в 1 см от рулетки - не СТОП (правило только про дальше 0,15 м), RESEEDED 1 в сводке, итог код 0' ($r.Code -eq 0 -and $s -match 'ТОЧКА 5 см: .*RESEEDED 1, ' -and (LastLine $s) -ceq '# VERDICT OK') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p00cm' = (Rep8 'p00cm' $z100 (Poses 0.0) @('bad') 'ok' 2000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W21' '25: строка RESEEDED, позицию которой не разобрать - СТОП, код 5' ($r.Code -eq 5 -and $s -match 'RESEEDED — СТОП: позицию из строки vpe_fix не разобрать') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p05cm' = (Rep8 'p05cm' $z100 @() @() 'ok' 3000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W22' '25: в точке 5 см ни одной позы по меткам - код 6 НЕ ПРОВЕРЕНО «ни одной позы по меткам в точках: 5 см» (не «всё чисто»)' ($r.Code -eq 6 -and (LastLine $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'ни одной позы по меткам в точках: 5 см' -and $r.Console -notmatch 'Готово:') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p10cm' = (Rep8 'p10cm' $z100 (Poses 0.10) @() 'no' 4000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W23' '25: журнал vpe_fix не прочитан в точке 10 см - код 6 «журнал vpe_fix не прочитан в точках: 10 см»; следующая точка читает журнал с начала своей записи (start)' ($r.Code -eq 6 -and $s -match 'журнал vpe_fix не прочитан в точках: 10 см' -and $r.Calls[9] -match '_ rec 10 p15cm start\s*\]') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p00cm' = (Rep8 'p00cm' $z100 (Poses 0.0) @() 'ok' 2000 'MN_MAP error=share_not_found_PackageNotFoundError') }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W24' '25: карта меток не прочитана в точке 0 см - позы не с чем сверить: код 6 «карта меток не прочитана в точках: 0 см»' ($r.Code -eq 6 -and $s -match 'карта меток не прочитана в точках: 0 см') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p15cm' = (Rep8 'p15cm' (@(-1) * 30) (Poses 0.15) @() 'ok' 5000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W25' '25: в точке 15 см кадры есть, метка 0 не прочитана ни разу - код 6 «метка 0 не прочитана ни разу в точках: 15 см»' ($r.Code -eq 6 -and $s -match 'метка 0 не прочитана ни разу в точках: 15 см') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p15cm' = (Rep8 'p15cm' @() @() @() 'ok' 5000) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W26' '25: в точке 15 см детектор не выдал ни одного сообщения - код 6 «детектор не выдал ни одного сообщения в точках: 15 см»' ($r.Code -eq 6 -and $s -match 'детектор не выдал ни одного сообщения в точках: 15 см') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{}
$r = Run-Cmd '25_metki_nomera.cmd' "0`r`nx`r`n" $o; $s = Sum $o
Check 'W27' '25: набрано не то число перед точкой 5 см - запись остановлена: код 6, NOT_CHECKED, записана только точка 0 см; напоминание последней строкой' ($r.Code -eq 6 -and (Keys $r) -ceq ',w8_pre,,w8_p00cm' -and (LastLine $s) -ceq '# VERDICT NOT_CHECKED' -and $s -match 'ОСТАНОВЛЕНО владельцем перед точкой 5 см' -and (LastLine $r.Console) -ceq $REM) ((Keys $r) + ' code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p00cm' = (Rep8 'p00cm' $z100 (Poses 0.0) @() 'ok' 2000 $MAPOK 50) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o
Check 'W28' '25: строк MN_MSG не столько, сколько msgs в MN_END - код 4 ERROR, дальше не пошли' ($r.Code -eq 4 -and (LastLine (Sum $o)) -ceq '# VERDICT ERROR' -and (Keys $r) -ceq ',w8_pre,,w8_p00cm') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p00cm' = (Rep8 'p00cm' $z100 (Poses 0.0) @() 'ok' 2000 $MAPOK -1 99) }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o
Check 'W29' '25: строк MN_POSE не столько, сколько poses в MN_END - код 4 ERROR' ($r.Code -eq 4 -and (LastLine (Sum $o)) -ceq '# VERDICT ERROR') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' ($preAwake -replace 'BB_R8MN_DONE rc=0\n', '')
$r = Run-Cmd '25_metki_nomera.cmd' '' $o
Check 'W30' '25: ответ проверки без BB_R8MN_DONE - код 4, сырой ответ переименован в .FAILED.txt' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $o -File -Filter '*_pre.FAILED.txt').Count -eq 1) ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' "MN_ERROR markers_import_failed ModuleNotFoundError('aruco_pose')`nBB_R8MN_DONE rc=4`n" 4
$r = Run-Cmd '25_metki_nomera.cmd' '' $o
Check 'W31' '25: на Pi нет aruco_pose (MN_ERROR) - код 4, ERROR' ($r.Code -eq 4 -and (LastLine (Sum $o)) -ceq '# VERDICT ERROR') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preAwake; Set-AllRec @{ 'p05cm' = ($MAPOK + "`nMN_STATE connected=True armed=False mode=POSCTL`nMN_WAKE sent=2 topic=/aruco_detect/wake hz=1 warmup_s=2`nMN_REFUSED armed_during (дрон взвели во время записи: wake прекращён, запись прервана)`nBB_R8MN_DONE rc=3`n") }
$r = Run-Cmd '25_metki_nomera.cmd' $ALL4 $o; $s = Sum $o
Check 'W32' '25: дрон взвели во время записи 5 см - код 3, «Детектор будился, wake прекращён», дальше не пошли' ($r.Code -eq 3 -and $s -match 'Детектор будился, wake прекращён' -and (Keys $r) -ceq ',w8_pre,,w8_p00cm,,w8_p05cm') ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-Canned 'w8_pre' $preSleep
[IO.File]::WriteAllText((Join-Path $o 'metki_nomera_20261113_100000_p10cm.err.txt'), 'x')
$r = Run-Ps 'run_r8_metki.ps1' '-Phase pre -Stamp 20261113_100000' $o
Check 'W33' '25: файл ответа этой метки времени уже есть - код 4, «не перезаписываю», к дрону не обращались' ($r.Code -eq 4 -and $r.Console -match 'не перезаписываю' -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-Ps 'run_r8_metki.ps1' '-Phase pre -Stamp 2026-11-13' $o
Check 'W34' '25: метка -Stamp не ГГГГММДД_ЧЧММСС - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$o = New-Out; Reset-Fake; Set-AllRec @{}
$r = Run-Ps 'run_r8_metki.ps1' '-Phase rec -Stamp 20261113_100001 -Cm 0' $o
Check 'W35' '25: фаза rec без удачной проверки (нет сводки) - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$sum2 = Join-Path $o 'metki_nomera_20261113_100002.txt'
[IO.File]::WriteAllText($sum2, ("# x`r`nПРОВЕРКА connected=True armed=False mode=POSCTL | label=pre publishers=1 nodes=aruco_detect camera_subscription=yes msgs=60 with_markers=58 poses=10 seconds=6 | x`r`nЖУРНАЛ_ДО=1000`r`n"), $utf8)
$r = Run-Ps 'run_r8_metki.ps1' '-Phase rec -Stamp 20261113_100002 -Cm 5' $o
Check 'W36' '25: точка 5 см раньше точки 0 см - код 4 (порядок 0, 5, 10, 15), к дрону не обращались' ($r.Code -eq 4 -and $r.Console -match 'по порядку' -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-Ps 'run_r8_metki.ps1' '-Phase rec -Stamp 20261113_100002 -Cm 7' $o
Check 'W37' '25: сдвиг не 0/5/10/15 - код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
[IO.File]::AppendAllText($sum2, "ТОЧКА 0 см: сообщений 10, кадров с метками 10, номера 0:10, поз 3 | ФЛАГИ: -`r`n", $utf8n)
$r = Run-Ps 'run_r8_metki.ps1' '-Phase final -Stamp 20261113_100002' $o
Check 'W38' '25: итог при одной записанной точке из 4 - код 4, ERROR (не «всё чисто»)' ($r.Code -eq 4 -and (LastLine ([IO.File]::ReadAllText($sum2))) -ceq '# VERDICT ERROR') ('code=' + $r.Code)
$r = Run-Ps 'run_r8_metki.ps1' '-Phase stop -Stamp 20261113_100002 -Cm 5' $o
Check 'W39' '25: после итога сводка закрыта - фаза stop ничего не дописывает, код 4' ($r.Code -eq 4 -and $r.Console -match 'уже есть итог') ('code=' + $r.Code)
$rp = [IO.File]::ReadAllText((Join-Path $Kit 'run_r8_metki.ps1'))
Check 'W40' 'run_r8_metki.ps1: первая строка МЕНЯЕТ ДРОН временно; BB-AssertPc и отказ перезаписи до обращения к дрону; BB-TestDrone до скрипта Pi; scp нет; порог 0,15 м' ($rp.Split("`n")[0] -match 'МЕНЯЕТ ДРОН временно' -and $rp.IndexOf('BB-AssertPc') -lt $rp.IndexOf('BB-TestDrone $ssh') -and $rp.IndexOf('BB-NewOutFile $outDir $n') -lt $rp.IndexOf('BB-TestDrone $ssh') -and $rp.IndexOf('BB-TestDrone $ssh') -lt $rp.IndexOf('R6-Remote') -and $rp -notmatch '(?i)\bscp\b' -and $rp -match '\$TOL = 0\.15\s') ''
$fs = Join-Path (Split-Path $Kit) 'drone_backup_kit_20261111\out\drone_backup_20261112_102053\FILES_SHA256.txt'
$mapLine = @(); if (Test-Path -LiteralPath $fs) { $mapLine = @([IO.File]::ReadAllLines($fs) | Where-Object { $_ -match '  home/lb/ros2_ws/src/aruco_pose/map/map\.txt$' }) }
Check 'W41' 'sha256 карты в run_r8_metki.ps1 (528b5adb...) = map.txt дрона по копии 12.11 (FILES_SHA256.txt, только чтение)' ($mapLine.Count -eq 1 -and $mapLine[0].StartsWith('528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611') -and $rp.Contains("'528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611'")) ($mapLine -join ' ')
$card = [IO.File]::ReadAllText((Join-Path $Kit 'cards\КАРТОЧКА_25_МЕТКИ_НОМЕРА.md'))
Check 'W42' 'карточка 25: набор r8, МЕНЯЕТ ДРОН временно, правила СТОП, напоминание про EKF, rc3 - сведения' ($card -match 'набор r8' -and $card -match 'МЕНЯЕТ ДРОН: временно' -and $card -match 'ЛОЖНЫЙ НОМЕР С КАРТЫ — СТОП' -and $card -match '0,15 м' -and $card -match 'RESEEDED' -and $card.Contains($REM) -and $card -match 'rc3' -and $card -match 'bench_kit_20261113_r8\\25_metki_nomera\.cmd') ''

$env:PATH = $oldPath
Note ('ИТОГ r8: PASS ' + $script:pass + ', FAIL ' + $script:fail)
if ($script:fail -gt 0) { exit 1 }
exit 0
