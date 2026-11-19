# run_tests_r17a.ps1 (Claude, 19.11.2026, набор r17a = r17 + 3 поправки по проверке чата 1 wf_2a438f6b) - тесты НОВОГО в r17a на ПК, в песочнице. К дрону не подключается.
# Вместо ssh - подделка tests\fake_ssh_r13.cs (из r13, без изменений; сеть не открывает; для сквозных проверок подаёт скрипт Pi в WSL на поддельный «дом дрона»).
# СТРАЖ (как в r13-r17): перед КАЖДЫМ запуском шага тест сам проверяет, что ssh, который найдёт BB-FindSsh, - подделка (путь, sha, метка BB_FAKE_SSH_R13_NO_NETWORK),
#   для .cmd и 07 - ещё и в отдельном процессе powershell с тем же окружением. Иначе шаг НЕ запускается, тест - FAIL. Раздел G сам подменяет подделку заглушкой без метки и проверяет отказ.
# M: шаг 03 - строки детектора «joint rms median» из /tmp/bumblebee.log (строки JR скрипта Pi), «MAP != FIELD?» выделено, обрезка помечена, нет данных - код 5 и последняя строка окна не «Готово»;
#    на заготовленных ответах подделки, через 03_v_rukakh.cmd и сквозь НАСТОЯЩИЙ pi\vision_measure.sh в WSL (tests\r17a_wsl_vm.sh, тестовый журнал через BB_TEST_LOG).
# W: 09 - строка «POSEFIX_V11: на дроне В1.1 (детектор + vpe_fix)» и в файле отчёта (перед последней «# VERDICT OK»); последняя строка окна 09_sverka_install.cmd не «совпал с образом r2j»;
#    подсказка при старом В1 (09 и 15) ведёт на 49 заготовки _aside_20261119\drone_pkg_posefix_v1_20261118. E: 07 (не менялся) принимает настоящий отчёт 09 r17a. C: .cmd. K: r17a = копия r17 + только ожидаемые правки.
# Всё WSL - с nice -n 19 ionice -c3; тест и его дочерние процессы - с приоритетом Idle.
# Запуск: powershell -NoProfile -ExecutionPolicy Bypass -File tests\run_tests_r17a.ps1 [-Only M,W,E,G,C,K]. Итог: «ИТОГ r17a: PASS n, FAIL m».
param([string[]]$Only = @())
$ErrorActionPreference = 'Stop'
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ -ne '' })
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
try { [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'Idle' } catch { }
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r17a_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') { if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") } }
function Sha([string]$p) { return (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() }
function ShaText([string]$t) { return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($utf8n.GetBytes($t))) -replace '-', '').ToLower() }
function Want([string]$s) { return ($Only.Count -eq 0 -or $Only -contains $s) }
function LastLine([string]$t) { $a = @($t -split "`r?`n" | Where-Object { $_.Trim() -ne '' }); if ($a.Count) { return $a[-1].Trim() } else { return '' } }
if ($env:COMPUTERNAME -ne 'DESKTOP-H5CPN8E') { Note ('ВНИМАНИЕ: имя ПК ' + $env:COMPUTERNAME + ', шаги рассчитаны на DESKTOP-H5CPN8E') }
Remove-Item Env:BB_REGISTRY -ErrorAction SilentlyContinue; Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
$R2J = '66f061ecc14445de5901cee8d4dfcd59be98fcaa697b97cbf939a89bd0be9bd3'; $JD2 = 'b89bfb4327a184f5327ae83fa1e84752f0a2deac2a5a6ea5744bbb857072a915'
$V1A = '890dafbfde99541a0742e26acc81e5f5a222390e7b8244e31fbbfc8f4ccc4338'; $V11A = '81daec90eb32a61cccaefc623f9f685d8acbc402edcc7876140541be29c18472'
$S03R17 = 'f8aee55cadfe83a2506fc10dfa98fe2b7b3aadbd8a937efdc71a86e0c520d906'; $S09R17 = '157bafcdfb8c5a0180dfba81b60fc70f1812230828f8f52c01db5e22059edc61'   # 03_v_rukakh.cmd и 09_sverka_install.cmd r17
$S07R12 = 'a6af97877cc39b1f0de0cb98c1183ce8abc0f56af1ae1c4d83f7472a4a133b07'   # run_07_takeoff.ps1 r12 = ... = r17 = r17a (блок 3c), не меняется
$PV = 'POSEFIX_V11: на дроне В1.1 (детектор + vpe_fix)'; $PVF = '# ' + $PV
$HINT = 'нужен откат 49_otkat_posefix_v1.cmd из заготовки _aside_20261119' + [char]92 + 'drone_pkg_posefix_v1_20261118 (49 пакета v1x при В1 откажет), потом установка В1.1: 48 из drone_pkg_posefix_v1x_20261119'
$HINTOLD = 'нужен откат 49 (пакет drone_pkg_posefix_v1x_20261119)'
$OK09 = 'Готово: сверка install прошла. Что стоит на Pi - r2j или допущенный вариант POSEFIX_V11, R2M_CAM, POSEFIX_JD2 - смотрите в строках выше. Скажите Claude.'
$OLD09 = 'совпал с образом r2j'
$NOJ = 'НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА'
$OK03 = 'Готово: журнал записан. Скажите Claude.'; $STOP03 = 'СТОП: журнал записан, но НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА. Скажите Claude.'

# ---------- песочница: копия набора без tests, out, _aside, proverka_* (её папка-родитель = «папка проекта» для 07) ----------
$SBP = Join-Path $Run 'sb'; $SB = Join-Path $SBP 'bench_kit_20261119_r17a'
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Kit.Length + 1)
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -like '_aside\*' -or $rel -like 'proverka_*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null; Copy-Item -LiteralPath $_.FullName -Destination $dest
}
New-Item -ItemType Directory -Force -Path (Join-Path $SB 'out') | Out-Null
# в песочнице у 03_v_rukakh.cmd (set /p) убрана строка chcp 65001 - она мешает set /p читать ответы из файла (как в tests\run_tests_bench.ps1, только в тесте; в наборе она на месте, M0 проверяет файл набора)
$p03 = Join-Path $SB '03_v_rukakh.cmd'; [IO.File]::WriteAllText($p03, ((@([IO.File]::ReadAllText($p03) -split "`r`n") | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
$FakeExe = Join-Path $FakeDir 'ssh.exe'
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh_r13.cs'))) -OutputAssembly $FakeExe -OutputType ConsoleApplication
$script:FakeSha = Sha $FakeExe
$Marker = 'BB_FAKE_SSH_R13_NO_NETWORK'
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'
# ---------- страж: ssh, который найдёт шаг, - подделка (как в r13-r17) ----------
function Has-Marker([string]$p) { $l1 = [Text.Encoding]::GetEncoding(28591); $hay = $l1.GetString([IO.File]::ReadAllBytes($p)); $needle = $l1.GetString([Text.Encoding]::Unicode.GetBytes($Marker)); return $hay.Contains($needle) }
function Guard-Why([string]$src) {
    if (-not $src) { return 'ssh не найден' }
    if ($src -ne $FakeExe) { return ('первый ssh в PATH - не подделка этого прогона: ' + $src) }
    if ((Sha $src) -ne $script:FakeSha) { return ('sha ssh не равен sha собранной подделки: ' + $src) }
    if (-not (Has-Marker $src)) { return ('в ssh нет метки ' + $Marker + ': ' + $src) }
    return ''
}
function Guard-InProc { $c = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; return (Guard-Why $(if ($c) { $c.Source } else { '' })) }
function Guard-Child {
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes('$c = Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1; if ($c) { [Console]::Out.Write($c.Source) }'))
    $gi = Join-Path $Run 'guard_empty_stdin.txt'; if (-not (Test-Path -LiteralPath $gi)) { [IO.File]::WriteAllText($gi, '') }
    $go = Join-Path $Run ('guard_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -NonInteractive -EncodedCommand ' + $enc) -NoNewWindow -PassThru -RedirectStandardInput $gi -RedirectStandardOutput $go -RedirectStandardError ($go + '.err')
    $null = $p.Handle
    if (-not $p.WaitForExit(60000)) { try { Stop-Process -Id $p.Id -Force } catch { }; return 'страж: дочерний powershell не ответил за 60 с' }
    $src = ([IO.File]::ReadAllText($go)).Trim()
    return (Guard-Why $src)
}
$script:guardRefusals = 0
function Reset-Fake([string]$mode = 'normal', [string]$exec = '', [string]$shaOut = '') {
    $aside = Join-Path $Run ('fake_state_' + [guid]::NewGuid().ToString('N').Substring(0, 8)); $moved = $false
    foreach ($f in @(Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Name -notlike 'ssh.*' })) { if (-not $moved) { New-Item -ItemType Directory -Path $aside | Out-Null; $moved = $true }; Move-Item -LiteralPath $f.FullName -Destination $aside }
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), $mode)
    if ($exec) { [IO.File]::WriteAllText((Join-Path $FakeDir 'exec_wsl.txt'), $exec) }
    if ($shaOut) { [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), $shaOut) }
}
function Calls { $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path -LiteralPath $cl) { return @(Get-Content -LiteralPath $cl -Encoding UTF8) } else { return @() } }
function Run-Ps([string]$script, [string]$outDir, [string]$more = '', [switch]$ChildGuard, [switch]$GuardControl) {
    $why = Guard-InProc
    if (-not $why -and $ChildGuard) { $why = Guard-Child }
    if ($why) {
        if (-not $GuardControl) { $script:guardRefusals++; Check 'GUARD' ('страж: ' + $script + ' НЕ запущен - ' + $why) $false '' }
        return @{ Code = -1; Console = ('SSH_GUARD ' + $why); Calls = @(Calls); Guard = $false }
    }
    if ($outDir) { $env:BB_KIT_OUT = $outDir }
    $so = Join-Path $Run ('c_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB $script) + '" ' + $more) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
    return @{ Code = $p.ExitCode; Console = ([IO.File]::ReadAllText($so) + [IO.File]::ReadAllText($so + '.err')); Calls = @(Calls); Guard = $true }
}
# .cmd из песочницы через cmd.exe (как Run-Cmd в tests\run_tests_bench.ps1): ввод - из файла; страж - в этом процессе и в отдельном powershell
function Run-Cmd([string]$cmdName, [string]$stdin, [string]$outDir) {
    $why = Guard-InProc; if (-not $why) { $why = Guard-Child }
    if ($why) { $script:guardRefusals++; Check 'GUARD' ('страж: ' + $cmdName + ' НЕ запущен - ' + $why) $false ''; return @{ Code = -1; Console = ('SSH_GUARD ' + $why); Calls = @(Calls); Guard = $false } }
    $env:BB_KIT_OUT = $outDir
    $id = [guid]::NewGuid().ToString('N').Substring(0, 8)
    $inFile = Join-Path $Run ('in_' + $id + '.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $so = Join-Path $Run ('cmd_' + $id + '.txt')
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + (Join-Path $SB $cmdName) + '" < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    Remove-Item Env:BB_KIT_OUT -ErrorAction SilentlyContinue
    $b = [IO.File]::ReadAllBytes($so); $txt = [Text.Encoding]::UTF8.GetString($b)
    return @{ Code = $p.ExitCode; Console = ($txt + [IO.File]::ReadAllText($so + '.err')); Out = $txt; Calls = @(Calls); Guard = $true }
}
function New-OutDir([string]$name) { $o = Join-Path $Run ('out_' + $name); New-Item -ItemType Directory -Path $o -Force | Out-Null; return $o }
function Latest([string]$dir, [string]$filter) { return @(Get-ChildItem -LiteralPath $dir -File -Filter $filter | Where-Object { $_.Name -notmatch '\.generated\.|\.err\.txt$|\.raw\.txt$' } | Sort-Object LastWriteTime) }
function Wsl([string[]]$a) { $ErrorActionPreference = 'Continue'; return (& wsl.exe -e nice -n 19 ionice -c3 @a 2>&1 | Out-String) }
Check 'G0' ('страж: собранная подделка - первый ssh в PATH (в этом процессе и в отдельном powershell), sha ' + $script:FakeSha.Substring(0, 12) + '…, метка ' + $Marker + ' в файле') ((Guard-InProc) -eq '' -and (Guard-Child) -eq '') ((Guard-InProc) + ' | ' + (Guard-Child))
$kitW = ''; try { $kitW = (& wsl.exe -e wslpath -a ($Kit.Replace('\', '/')) | Out-String).Trim() } catch { }

# ======================= M: шаг 03 - joint rms из /tmp/bumblebee.log (строки JR), MAP != FIELD?, обрезка, нет данных = код 5 =======================
if (Want 'M') {
    $c03 = [IO.File]::ReadAllText((Join-Path $Kit '03_v_rukakh.cmd'))
    $br5 = ' else if "%RC%"=="5" (echo ' + $STOP03 + ')'
    $c03old = $c03.Replace($br5, '').Replace('rem 03_v_rukakh.cmd (Claude, 10.11.2026; r17a 19.11: код 5 = нет строк joint rms, не «Готово»).', 'rem 03_v_rukakh.cmd (Claude, 10.11.2026).')
    $l03 = @($c03 -split "`r`n")
    Check 'M0' '03_v_rukakh.cmd = r17 + только ветка «код 5 -> СТОП: ... НЕТ ДАННЫХ JOINT RMS ...» и пометка в rem; первая строка - «МЕНЯЕТ ДРОН (косвенно)» как раньше; вызов run_measure.ps1 тот же' ((ShaText $c03old) -eq $S03R17 -and $c03.Contains($br5) -and $l03[2].StartsWith('echo МЕНЯЕТ ДРОН (косвенно):') -and $c03.Contains('-Label %LABEL% -DurationSec 120 -Mode measure -Wake 1 -Place %LABEL% -CameraHeightCm "%HH%"')) (ShaText $c03old)
    $rmT = [IO.File]::ReadAllText((Join-Path $SB 'run_measure.ps1'))
    Check 'M0b' 'run_measure.ps1: «exit 5» один раз и только после «НЕТ ДАННЫХ JOINT RMS»; аргументы для Pi те же (длительность, метка, режим, wake); BB_TEST_LOG не задаётся' (([regex]::Matches($rmT, 'exit 5')).Count -eq 1 -and $rmT.IndexOf('exit 5') -gt $rmT.LastIndexOf('НЕТ ДАННЫХ JOINT RMS') -and $rmT.Contains('$remote = BB-RemoteCommand $sh @([string]$DurationSec, $Label, $Mode, [string]$Wake)') -and -not $rmT.Contains('BB_TEST_LOG')) ''
    $vmExp = ShaText (([IO.File]::ReadAllText((Join-Path $SB 'pi\vision_measure.sh'))) -replace "`r`n", "`n")
    # M0c: команда ssh для 03 (скрипт Pi в base64 в командной строке) должна влезать в предел Windows 32 767 знаков с запасом 500 (первый вариант r17a его превысил: 33 446)
    $ps3 = ". '" + (Join-Path $SB 'lib\bb_common.ps1') + "'; `$r = BB-RemoteCommand '" + (Join-Path $SB 'pi\vision_measure.sh') + "' @('120','hand_camera_over','measure','1'); [Console]::Out.Write((`$script:BB_SshOpts + ' ' + `$script:BB_DroneHost + ' `"' + `$r + '`"').Length)"
    $alen = 0; [void][int]::TryParse(((& powershell -NoProfile -ExecutionPolicy Bypass -Command $ps3 2>&1 | Out-String).Trim()), [ref]$alen)
    $full = $alen + '"C:\WINDOWS\System32\OpenSSH\ssh.exe" '.Length
    Check 'M0c' ('03: командная строка ssh (настоящий путь ssh + ключи + скрипт Pi в base64) = ' + $full + ' знаков, предел Windows 32767, запас не меньше 500') ($alen -gt 30000 -and $full -le (32767 - 500)) ('длина ' + $full)
    $JR1 = 'JR [aruco_detect.py-19] [INFO 1793342400.201] [aruco_detect]: aruco_detect: joint rms median 1.23 px (2 s, n=12)'
    $JRM = 'JR [aruco_detect.py-19] [WARN 1793342400.202] [aruco_detect]: aruco_detect: MAP != FIELD? joint PnP rms median 3.10 px over 2 s (> 2.5)'
    $JRC = 'JR [aruco_detect.py-19] [INFO 1793342400.203] [aruco_detect]: aruco_detect: map mismatch cleared (rms median 1.50 px)'
    $JR2 = 'JR [aruco_detect.py-19] [INFO 1793342400.204] [aruco_detect]: aruco_detect: joint rms median 1.31 px (2 s, n=13)'
    $JJ = 'J aruco_detect: joint rms median 1.23 px (2 s, n=12)'
    $many = @(1..60 | ForEach-Object { 'JR [aruco_detect.py-19] [INFO 1793342400.' + (300 + $_) + '] [aruco_detect]: aruco_detect: joint rms median 1.' + (10 + $_) + ' px (2 s, n=' + $_ + ')' })
    $jl80 = @(1..80 | ForEach-Object { 'J aruco: detection ACTIVE k=' + $_ })
    function New-Raw03([string[]]$tail, [string]$hz = '6.10') {
        $raw = "META host bumblebee-20ec`nSUMMARY markers_msgs count=0 hz=0.00 gaps_over_0.5s=0 max_gap_s=0 start_delay_s=120 end_silence_s=120 top_gaps=-`nSUMMARY vision_pose /mavros/vision_pose/pose count=600 hz=5.00 gaps_over_0.5s=0 max_gap_s=0.3`n"
        $raw += "SUMMARY markers_used msgs=732 with_ge1=700 (95.6%) with_0=32 hz_all=" + $hz + "`nMETA python_exit 0`n"
        foreach ($l in $tail) { $raw += $l + "`n" }
        return ($raw + "BB_BENCH_DONE rc=0`n")
    }
    function Run-03([string]$label, [string]$raw, [switch]$ViaCmd) {
        $cf = Join-Path $Run ('canned_measure_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt'); [IO.File]::WriteAllText($cf, $raw, $utf8n)
        Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_.txt'), $cf)
        $o = New-OutDir ('m_' + [guid]::NewGuid().ToString('N').Substring(0, 6))
        if ($ViaCmd) { $pl = @{ hand_center = '1'; hand_camera_over = '2'; hand_back8 = '3' }[$label]; $r = Run-Cmd '03_v_rukakh.cmd' ($pl + "`r`n50`r`n") $o }
        else { $r = Run-Ps 'run_measure.ps1' $o ('-Label ' + $label + ' -DurationSec 120 -Mode measure -Wake 1 -Place ' + $label + ' -CameraHeightCm 50') }
        $sf = @(Get-ChildItem -LiteralPath $o -Filter ('bench_' + $label + '_*.summary.txt')); $r.Sum = $(if ($sf.Count -eq 1) { [IO.File]::ReadAllText($sf[0].FullName) } else { '' })
        $r.Raw = @(Get-ChildItem -LiteralPath $o -Filter ('bench_' + $label + '_*.raw.txt')).Count
        $sent = @(Get-ChildItem -LiteralPath $FakeDir -Filter 'sent_*.sh')
        $r.CallOk = ($r.Calls.Count -eq 2 -and $r.Calls[1] -match ('_ 120 ' + $label + ' measure 1\]') -and $sent.Count -eq 1 -and (Sha $sent[0].FullName) -eq $vmExp -and -not (($r.Calls -join ' ').Contains('BB_TEST_LOG')))
        return $r
    }
    function JointLine([int]$n) { return ('JOINT RMS (строки детектора «joint rms median» из /tmp/bumblebee.log за замер): ' + $n) }
    # M1: заготовленные ответы Pi
    $r = Run-03 'hand_center' (New-Raw03 @('J aruco: detection ACTIVE', $JR1, $JRM, $JRC, 'JR_COUNT 3'))
    $ok = $r.Guard -and $r.Code -eq 0 -and $r.CallOk -and $r.Sum.Contains((JointLine 2)) -and $r.Sum.Contains('  ' + $JR1) -and $r.Sum.Contains('  >>> MAP != FIELD? >>> ' + $JRM) -and $r.Sum.Contains('  ' + $JRC) -and $r.Sum.Contains('MAP != FIELD? - детектор считает, что карта меток не совпадает с полем; строк: 1. Сказать Claude до полёта.') -and $r.Console.Contains('MAP != FIELD? - детектор 1 раз(а) написал') -and -not $r.Sum.Contains($NOJ) -and -not $r.Console.Contains($NOJ) -and $r.Sum.Contains('ЧАСТОТА ДЕТЕКТОРА: 6,1 кадр/с') -and -not $r.Sum.Contains('ВЫВОД ОБРЕЗАН')
    Check 'M1' '03 (подделка): JR median + MAP != FIELD? + cleared - код 0; JOINT RMS 2 (median и MAP), строки JR в итоге, MAP выделено «>>> MAP != FIELD? >>>» и отдельной строкой «Сказать Claude до полёта» (в окне - красным); частота 6,1; «НЕТ ДАННЫХ» нет' $ok ('code=' + $r.Code + ' call=' + $r.CallOk + ' | ' + (($r.Sum -split "`r?`n" | Where-Object { $_ -match 'JOINT|MAP|JR|НЕТ' }) -join ' | '))
    $r = Run-03 'hand_camera_over' (New-Raw03 @($JR1, $JR2, 'JR_COUNT 2'))
    Check 'M2' '03 (подделка): две строки median - код 0; JOINT RMS 2; ни «>>>», ни «MAP != FIELD?», ни «ВЫВОД ОБРЕЗАН», ни «НЕТ ДАННЫХ»' ($r.Guard -and $r.Code -eq 0 -and $r.CallOk -and $r.Sum.Contains((JointLine 2)) -and $r.Sum.Contains('  ' + $JR2) -and -not $r.Sum.Contains('>>>') -and -not $r.Sum.Contains('MAP != FIELD?') -and -not $r.Console.Contains('MAP != FIELD?') -and -not $r.Sum.Contains('ВЫВОД ОБРЕЗАН') -and -not $r.Sum.Contains($NOJ)) ('code=' + $r.Code)
    $r = Run-03 'hand_back8' (New-Raw03 (@($many) + @('JR_CUT shown=60 total=75', 'JR_COUNT 75')))
    Check 'M3' '03 (подделка): на Pi обрезано (JR_CUT shown=60 total=75) - код 0; «ВЫВОД ОБРЕЗАН: на Pi показаны первые 60 из 75 строк детектора»; JOINT RMS 60 (показанные)' ($r.Guard -and $r.Code -eq 0 -and $r.Sum.Contains('  ВЫВОД ОБРЕЗАН: на Pi показаны первые 60 из 75 строк детектора про joint rms') -and $r.Sum.Contains((JointLine 60)) -and $r.Sum.Contains('  ' + $many[59]) -and -not $r.Sum.Contains($NOJ)) ('code=' + $r.Code)
    $nd = @(
        @('JR_COUNT 0', @('J aruco: detection ACTIVE', 'JR_COUNT 0'), ''),
        @('JR_NOLOG', @('JR_NOLOG'), '  журнал стека /tmp/bumblebee.log на Pi не найден или его размер до замера не прочитан (JR_NOLOG)'),
        @('строки joint только в journald (как ждал r17), JR_COUNT нет', @($JJ), '  скрипт Pi не прислал строку JR_COUNT'),
        @('только «map mismatch cleared»', @($JRC, 'JR_COUNT 1'), ''),
        @('JR_NOTE и 0 строк', @('JR_NOTE log shrank, reading all', 'JR_COUNT 0'), '  журнал стека /tmp/bumblebee.log стал короче, чем до замера (перезапуск стека?): прочитан весь (JR_NOTE)')
    )
    foreach ($c in $nd) {
        $r = Run-03 'hand_center' (New-Raw03 $c[1])
        $ok = $r.Guard -and $r.Code -eq 5 -and $r.CallOk -and $r.Sum.Contains($NOJ) -and $r.Sum.Contains((JointLine 0)) -and (LastLine $r.Console).Contains($NOJ) -and $r.Raw -eq 1 -and -not $r.Console.Contains('Готово') -and $(if ($c[2]) { $r.Sum.Contains($c[2]) } else { $true })
        Check 'M4' ('03 (подделка), ' + $c[0] + ': код 5; сводка и сырой файл записаны; «НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА» в сводке и последней строкой окна; «Готово» нет') $ok ('code=' + $r.Code + ' last=' + (LastLine $r.Console))
    }
    $r = Run-03 'hand_center' (New-Raw03 (@($JR1, 'JR_COUNT 1') + $jl80 + @('J_CUT shown=80 total=95')))
    Check 'M5' '03 (подделка): journald обрезан на Pi (J_CUT shown=80 total=95) и в сводке (первые 40 из 80) - обе обрезки помечены; код 0' ($r.Guard -and $r.Code -eq 0 -and $r.Sum.Contains('  ВЫВОД ОБРЕЗАН: на Pi показаны первые 80 из 95 строк журнала') -and $r.Sum.Contains('  ВЫВОД ОБРЕЗАН: в сводке первые 40 из 80, все - в сыром файле') -and $r.Sum.Contains('Строки журнала bumblebee за время замера: 80')) ('code=' + $r.Code)
    $raw = "META x`nSUMMARY markers_used msgs=732 with_ge1=700 (95.6%) with_0=32 hz_all=6.10`nJ aruco: detection ACTIVE`nBB_BENCH_DONE rc=0`n"; $cf = Join-Path $Run 'canned_measure_vib.txt'; [IO.File]::WriteAllText($cf, $raw, $utf8n)
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_.txt'), $cf); $o = New-OutDir 'm_vib'
    $r = Run-Ps 'run_measure.ps1' $o '-Label vib_test -DurationSec 60 -Mode vibration -Wake 0'
    $sf = @(Get-ChildItem -LiteralPath $o -Filter 'bench_vib_test_*.summary.txt'); $st = $(if ($sf.Count -eq 1) { [IO.File]::ReadAllText($sf[0].FullName) } else { '' })
    Check 'M6' 'другие шаги (метка не hand_*, строк JR нет): код 0, строк «JOINT RMS», «НЕ ЛЕТАТЬ», «MAP», «ВЫВОД ОБРЕЗАН» нет - как в r17' ($r.Guard -and $r.Code -eq 0 -and $sf.Count -eq 1 -and -not $st.Contains('JOINT RMS') -and -not $st.Contains('НЕ ЛЕТАТЬ') -and -not $st.Contains('MAP') -and -not $st.Contains('ВЫВОД ОБРЕЗАН')) ('code=' + $r.Code)
    # M7: через 03_v_rukakh.cmd - последняя строка окна
    $r = Run-03 'hand_center' (New-Raw03 @($JR1, 'JR_COUNT 1')) -ViaCmd
    Check 'M7' '03_v_rukakh.cmd (подделка, место 1, высота 50): строки joint есть - код 0, последняя строка окна «Готово: журнал записан. Скажите Claude.»' ($r.Guard -and $r.Code -eq 0 -and $r.CallOk -and (LastLine $r.Out) -ceq $OK03 -and $r.Sum.Contains((JointLine 1))) ('code=' + $r.Code + ' last=' + (LastLine $r.Out))
    $r = Run-03 'hand_center' (New-Raw03 @('JR_COUNT 0')) -ViaCmd
    Check 'M7' '03_v_rukakh.cmd (подделка): строк joint нет - код 5, последняя строка окна «СТОП: журнал записан, но НЕТ ДАННЫХ JOINT RMS = НЕ ЛЕТАТЬ ДО РЕШЕНИЯ ВЛАДЕЛЬЦА. Скажите Claude.», «Готово» в окне нет' ($r.Guard -and $r.Code -eq 5 -and $r.CallOk -and (LastLine $r.Out) -ceq $STOP03 -and -not $r.Out.Contains('Готово') -and $r.Sum.Contains($NOJ)) ('code=' + $r.Code + ' last=' + (LastLine $r.Out))
    # M8: сквозь НАСТОЯЩИЙ pi\vision_measure.sh в WSL (тестовый журнал стека через BB_TEST_LOG ставит runner теста, не набор)
    $VB = ''; $vi = ''
    try { $VB = (Wsl @('bash', '-c', 'mktemp -d /tmp/r17avm_XXXXXX')).Trim(); $vi = Wsl @('bash', ($kitW + '/tests/r17a_wsl_vm.sh'), 'init', $VB) } catch { $vi = $_.Exception.Message }
    $vmOk = ($vi -match ('VM17A_OK ' + [regex]::Escape($VB)))
    Check 'M8' ('WSL: поддельное окружение для vision_measure.sh в ' + $VB) $vmOk $vi
    if ($vmOk) {
        $wcases = @(
            @('joint', 0, $OK03, @((JointLine 2), '>>> MAP != FIELD? >>> JR [aruco_detect.py-19] [WARN 1793342400.202]', 'map mismatch cleared (rms median 1.50 px)', 'MAP != FIELD? - детектор считает'), @('9.91', '9.92', $NOJ)),
            @('none', 5, $STOP03, @((JointLine 0), $NOJ), @('9.91', 'Готово')),
            @('many', 0, $OK03, @((JointLine 60), 'ВЫВОД ОБРЕЗАН: на Pi показаны первые 60 из 75 строк детектора'), @($NOJ)),
            @('nolog', 5, $STOP03, @('журнал стека /tmp/bumblebee.log на Pi не найден', $NOJ), @('Готово')),
            @('jcut', 0, $OK03, @((JointLine 1), 'ВЫВОД ОБРЕЗАН: на Pi показаны первые 80 из 95 строк журнала'), @('J aruco_detect: joint'))
        )
        foreach ($c in $wcases) {
            $ci = Wsl @('bash', ($kitW + '/tests/r17a_wsl_vm.sh'), 'case', $VB, $c[0]); $cok = ($ci -match ('CASE17A_OK ' + $c[0] + ' '))
            Reset-Fake 'normal' ($VB + '/vm_runner.sh'); $o = New-OutDir ('m8_' + $c[0])
            $r = Run-Cmd '03_v_rukakh.cmd' ("1`r`n50`r`n") $o
            $sf = @(Get-ChildItem -LiteralPath $o -Filter 'bench_hand_center_*.summary.txt'); $st = $(if ($sf.Count -eq 1) { [IO.File]::ReadAllText($sf[0].FullName) } else { '' })
            $ok = $cok -and $r.Guard -and $r.Code -eq $c[1] -and (LastLine $r.Out) -ceq $c[2]; $miss = @()
            foreach ($m in $c[3]) { if (-not ($st + $r.Out).Contains($m)) { $ok = $false; $miss += $m } }
            foreach ($m in $c[4]) { if (($st + $r.Out).Contains($m)) { $ok = $false; $miss += ('лишнее ' + $m) } }
            Check 'M8' ('03_v_rukakh.cmd сквозь настоящий vision_measure.sh (WSL, случай ' + $c[0] + '): код ' + $c[1] + ', последняя строка окна «' + $c[2].Substring(0, 12) + '…»') $ok ('case=' + $cok + ' code=' + $r.Code + ' last=' + (LastLine $r.Out) + ' нет/лишнее: ' + ($miss -join ' ; '))
        }
    }
}

# ======================= W: 09 и 15 (строка POSEFIX_V11 в файле отчёта, последняя строка окна 09, подсказка при старом В1) =======================
$wslOk = $false; $WB = ''; $r09v11m = $null; $r09old = $null
if ((Want 'W') -or (Want 'E')) {
    try {
        $WB = (Wsl @('bash', '-c', 'mktemp -d /tmp/r17apc_XXXXXX')).Trim()
        $ti = Wsl @('bash', ($kitW + '/tests/r17_wsl_tree.sh'), 'init', $WB)
        $wslOk = ($ti -match ('TREE17_OK ' + [regex]::Escape($WB)))
    } catch { $ti = $_.Exception.Message }
    Check 'W0' ('WSL: поддельный дом дрона r17 (tests\r17_wsl_tree.sh, образы в /work - только чтение) в ' + $WB) $wslOk $ti
}
function Variant([string]$v, [string]$c) { $o = Wsl @('bash', ($kitW + '/tests/r17_wsl_tree.sh'), 'variant', $WB, $v, $c); return ($o -match ('VARIANT17_OK ' + $v + ' ' + $c + ' ')) }
if ((Want 'W') -or (Want 'E')) {
    if ($wslOk) {
        # вариант, камера, код, есть ли строка POSEFIX_V11 в файле, «и допущенными вариантами» в строке Готово, подсказка В1
        $cases = @(@('v11', 'r2j', 0, $true, $true, $false), @('v11', 'r2m', 0, $true, $true, $false), @('r2j', 'r2j', 0, $false, $false, $false), @('jd2', 'r2m', 0, $false, $true, $false),
                   @('v1', 'r2j', 5, $false, $false, $true), @('v11_aruco', 'r2j', 5, $false, $false, $false))
        foreach ($c in $cases) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('w09_' + $c[0] + '_' + $c[1]); $r = Run-Ps 'run_install_check.ps1' $o
            $f = @(Latest $o 'install_check_*.txt'); $ft = $(if ($f.Count -eq 1) { [IO.File]::ReadAllText($f[-1].FullName) -replace "`r`n", "`n" } else { '' })
            $ln = @($ft.Trim() -split "`n" | ForEach-Object { $_.Trim() })
            $nPV = @($ln | Where-Object { $_ -ceq $PVF }).Count
            $ok = $vok -and $r.Guard -and $r.Code -eq $c[2] -and $ln.Count -ge 2 -and $ln[-1] -ceq $(if ($c[2] -eq 0) { '# VERDICT OK' } else { '# VERDICT NOT_OK' })
            if ($c[3]) { $ok = $ok -and $nPV -eq 1 -and $ln[-2] -ceq $PVF -and $r.Console.Contains('  ' + $PV) } else { $ok = $ok -and $nPV -eq 0 -and -not $ft.Contains('# POSEFIX_V11') }
            if ($c[2] -eq 0) { $ok = $ok -and ($r.Console.Contains(') совпали с r2j и допущенными вариантами (какими - строки ниже), launch-файлы') -eq $c[4]) -and ($r.Console.Contains(') совпали с r2j, launch-файлы') -eq (-not $c[4])) }
            if ($c[5]) { $ok = $ok -and $r.Console.Contains($HINT) -and -not $r.Console.Contains($HINTOLD) } else { $ok = $ok -and -not $r.Console.Contains('на дроне стоит В1 (') }
            Check 'W1' ('09 сквозная (WSL, ' + $c[0] + ' + ' + $c[1] + '): код ' + $c[2] + '; строка «# ' + $PV + '» в файле отчёта ' + $(if ($c[3]) { 'ровно одна, предпоследней, последняя «# VERDICT OK»' } else { 'нет' }) + $(if ($c[2] -eq 0) { '; в строке «Готово» ' + $(if ($c[4]) { 'оговорка «и допущенными вариантами»' } else { 'просто «совпали с r2j»' }) } else { '' }) + $(if ($c[5]) { '; подсказка ведёт на 49 заготовки _aside_20261119\drone_pkg_posefix_v1_20261118' } else { '' })) $ok ('variant=' + $vok + ' code=' + $r.Code + ' nPV=' + $nPV + ' хвост: ' + (($ln | Select-Object -Last 3) -join ' | '))
            if ($c[0] -eq 'v11' -and $c[1] -eq 'r2m' -and $ok) { $r09v11m = $f[-1].FullName }
            if ($c[0] -eq 'v1' -and $ok) { $r09old = $f[-1].FullName }
        }
        foreach ($c in @(@('v1', 'r2j', 5), @('v11', 'r2j', 0))) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('w15_' + $c[0]); $r = Run-Ps 'run_fingerprint.ps1' $o
            $ok = $vok -and $r.Guard -and $r.Code -eq $c[2]
            if ($c[0] -eq 'v1') { $ok = $ok -and $r.Console.Contains('bumblebee: на дроне стоит В1 (aruco_detect.py 890dafbf...), он больше не допускается - ' + $HINT + '.') -and -not $r.Console.Contains($HINTOLD) } else { $ok = $ok -and -not $r.Console.Contains('на дроне стоит В1') }
            Check 'W2' ('15 сквозная (WSL, ' + $c[0] + ' + ' + $c[1] + '): код ' + $c[2] + $(if ($c[0] -eq 'v1') { '; подсказка: откат 49 заготовки _aside_20261119\drone_pkg_posefix_v1_20261118, потом 48 из v1x; старой подсказки «пакет v1x» нет' } else { '; подсказки В1 нет' })) $ok ('variant=' + $vok + ' code=' + $r.Code)
        }
        # W3: 09_sverka_install.cmd - последняя строка окна
        foreach ($c in @(@('v11', 'r2m', 0, $OK09), @('r2j', 'r2j', 0, $OK09), @('v1', 'r2j', 5, 'СТОП: на Pi исполняется не то, что в образе r2j. Ничего не запускать, скажите Claude.'))) {
            $vok = Variant $c[0] $c[1]; Reset-Fake 'normal' ($WB + '/runner13.sh'); $o = New-OutDir ('w09cmd_' + $c[0] + '_' + $c[1])
            $r = Run-Cmd '09_sverka_install.cmd' '' $o
            $ok = $vok -and $r.Guard -and $r.Code -eq $c[2] -and (LastLine $r.Out) -ceq $c[3] -and -not $r.Out.Contains($OLD09)
            if ($c[0] -eq 'v11') { $ok = $ok -and $r.Out.Contains('  ' + $PV) }
            Check 'W3' ('09_sverka_install.cmd (WSL, ' + $c[0] + ' + ' + $c[1] + '): код ' + $c[2] + ', последняя строка окна «' + $c[3].Substring(0, 30) + '…», «совпал с образом r2j» в окне нет') $ok ('variant=' + $vok + ' code=' + $r.Code + ' last=' + (LastLine $r.Out))
        }
        $null = Variant 'r2j' 'r2j'
    }
    $c09 = [IO.File]::ReadAllText((Join-Path $SB '09_sverka_install.cmd'))
    Check 'W4' '09_sverka_install.cmd = r17, кроме текста при коде 0 (новый текст есть, первая строка «ТОЛЬКО ЧТЕНИЕ» та же); в run_install_check.ps1 и run_fingerprint.ps1 старой подсказки «откат 49 (пакет v1x)» нет' ($c09.Contains('(echo ' + $OK09 + ')') -and -not $c09.Contains($OLD09) -and (ShaText ($c09.Replace('(echo ' + $OK09 + ')', '(echo Готово: install на Pi совпал с образом r2j. Скажите Claude.)'))) -eq $S09R17 -and -not ([IO.File]::ReadAllText((Join-Path $SB 'run_install_check.ps1'))).Contains($HINTOLD) -and -not ([IO.File]::ReadAllText((Join-Path $SB 'run_fingerprint.ps1'))).Contains($HINTOLD)) ''
    $pkA = Join-Path (Split-Path -Parent $Kit) '_aside_20261119\drone_pkg_posefix_v1_20261118\49_otkat_posefix_v1.cmd'
    if (-not (Test-Path -LiteralPath $pkA)) { $pkA = Join-Path $env:USERPROFILE 'Documents\Claude local\_aside_20261119\drone_pkg_posefix_v1_20261118\49_otkat_posefix_v1.cmd' }   # прогон на копии: только чтение настоящего файла
    if (Test-Path -LiteralPath $pkA) { $l49 = [IO.File]::ReadAllText($pkA); Check 'W5' 'подсказка указывает на существующий файл: _aside_20261119\drone_pkg_posefix_v1_20261118\49_otkat_posefix_v1.cmd (первая строка «МЕНЯЕТ ДРОН: откат исправления позы v1»)' ($l49.Contains('echo МЕНЯЕТ ДРОН: откат исправления позы v1')) '' }
    else { Note ('W5 пропущен: рядом с набором нет ' + $pkA + ' (прогон на копии без соседей)') }
    # W6: НАСТОЯЩИЙ ответ Pi с дрона - отчёт 09 r17, который владелец снял 19.11 в 13:55 (out набора r17, только чтение): на дроне В1.1 + r2m_cam.
    # Ответ Pi = файл без последней строки «# VERDICT OK» (её дописывает ПК); он подаётся подделкой ssh в 09_sverka_install.cmd r17a.
    $real9 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261119_r17\out\install_check_20261119_135506.txt'
    if (-not (Test-Path -LiteralPath $real9)) { $real9 = Join-Path $env:USERPROFILE 'Documents\Claude local\bench_kit_20261119_r17\out\install_check_20261119_135506.txt' }
    $script:r09real = $null
    if (Test-Path -LiteralPath $real9) {
        $rt = ([IO.File]::ReadAllText($real9) -replace "`r`n", "`n").TrimEnd("`n")
        $rawPi = $(if ($rt.EndsWith("`n# VERDICT OK")) { $rt.Substring(0, $rt.Length - "`n# VERDICT OK".Length) + "`n" } else { '' })
        $cfr = Join-Path $Run 'canned_real09_drone_20261119_135506.txt'; [IO.File]::WriteAllText($cfr, $rawPi, $utf8n)
        Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $cfr)
        $o = New-OutDir 'w6_real_drone'; $r = Run-Cmd '09_sverka_install.cmd' '' $o
        $f = @(Latest $o 'install_check_*.txt'); $ft = $(if ($f.Count -eq 1) { [IO.File]::ReadAllText($f[-1].FullName) -replace "`r`n", "`n" } else { '' }); $ln = @($ft.Trim() -split "`n")
        $ok = $rawPi -ne '' -and $r.Guard -and $r.Code -eq 0 -and $ln.Count -ge 2 -and $ln[-1] -ceq '# VERDICT OK' -and $ln[-2] -ceq $PVF -and $ft.StartsWith($rawPi) -and $r.Out.Contains('  ' + $PV) -and $r.Out.Contains('  R2M_CAM: камера варианта r2m_cam') -and $r.Out.Contains(') совпали с r2j и допущенными вариантами (какими - строки ниже), launch-файлы') -and (LastLine $r.Out) -ceq $OK09 -and -not $r.Out.Contains($OLD09)
        Check 'W6' 'настоящий ответ Pi с дрона (09 r17 владельца 19.11 13:55: В1.1 + r2m_cam) через 09_sverka_install.cmd r17a: код 0; файл = ответ Pi + «# POSEFIX_V11: …» + «# VERDICT OK» последней; в окне строки POSEFIX_V11 и R2M_CAM, последняя строка - новый текст, «совпал с образом r2j» нет' $ok ('code=' + $r.Code + ' last=' + (LastLine $r.Out) + ' хвост: ' + (($ln | Select-Object -Last 2) -join ' | '))
        if ($ok) { $script:r09real = $f[-1].FullName }
    }
    else { Note ('W6 пропущен: нет ' + $real9) }
}

# ======================= E: 07 (не менялся) принимает настоящий отчёт 09 r17a со строкой POSEFIX_V11 =======================
if (Want 'E') {
    $p07 = Join-Path $SB 'run_07_takeoff.ps1'
    $conf = Join-Path $SB 'takeoff.conf'; $gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
    $cf = @{}; foreach ($l in [IO.File]::ReadAllLines($conf)) { $t9 = $l.Trim(); if ($t9 -eq '' -or $t9.StartsWith('#')) { continue }; $i = $t9.IndexOf('='); if ($i -gt 0) { $cf[$t9.Substring(0, $i).Trim()] = $t9.Substring($i + 1).Trim() } }
    [IO.File]::WriteAllText($gate, ("ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-19 тест`r`nСЛОВА_ВЛАДЕЛЬЦА=тест r17a`r`nСКРИПТ_SHA256=" + $cf['SCRIPT_SHA256'] + "`r`nАРГУМЕНТЫ=`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
    $strict = '=== СОВПАДАЕТ: прочитано 1127 из 1127, отличий нет (из таблицы MAVROS 1127, из запасного потока 0) ==='
    function New-Out07([string]$name, [string]$from09) {
        $o = New-OutDir ('e_' + $name)
        $rp = Join-Path $o 'params_bench_t_report.txt'; [IO.File]::WriteAllText($rp, $strict + "`r`n", $utf8)
        $c9 = Join-Path $o 'install_check_20261119_080000.txt'; Copy-Item -LiteralPath $from09 -Destination $c9; (Get-Item -LiteralPath $c9).LastWriteTime = (Get-Date).AddMinutes(-5)
        $c10 = Join-Path $o 'mavros_check_20261119_080000.txt'; [IO.File]::WriteAllText($c10, "BB_DONE`r`n# VERDICT OK`r`n", $utf8); (Get-Item -LiteralPath $c10).LastWriteTime = (Get-Date).AddMinutes(-5)
        return $o
    }
    $script:asideN = 0
    function Clear-Pkgs { $script:asideN++; $a = Join-Path $Run ('pkg_aside_' + $script:asideN); foreach ($d in @(Get-ChildItem -LiteralPath $SBP -Directory | Where-Object { $_.Name -like 'drone_pkg_*' })) { if (-not (Test-Path $a)) { New-Item -ItemType Directory -Path $a | Out-Null }; Move-Item -LiteralPath $d.FullName -Destination $a } }
    function Pkg-File([string]$pkg, [string]$name, [double]$ageMin) { $d = Join-Path $SBP ($pkg + '\out'); New-Item -ItemType Directory -Force -Path $d | Out-Null; $f = Join-Path $d $name; [IO.File]::WriteAllText($f, "тест`r`n", $utf8); (Get-Item -LiteralPath $f).LastWriteTime = (Get-Date).AddMinutes(-$ageMin); return $f }
    $badSha = ('cd' * 32) + '  ' + $cf['SCRIPT_REMOTE_PATH']
    function Run07([string]$o) { Reset-Fake 'normal' '' $badSha; return (Run-Ps 'run_07_takeoff.ps1' $o '-SafetyConfirmed NET-TWO-KILL-YES' -ChildGuard) }
    function Passed($r) { return ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -ge 2 -and $r.Console -match 'sha256 не равен' -and $r.Console -notmatch 'взлёт не разрешён' -and @($r.Calls | Where-Object { $_ -notmatch [regex]::Escape($Marker) }).Count -eq 0) }
    Check 'E0' '07 r17a = run_07_takeoff.ps1 r17 = ... = r12 байт в байт (sha a6af9787…, ворота 07 не трогались)' ((Sha $p07) -eq $S07R12) (Sha $p07)
    $pk = 'drone_pkg_posefix_v1x_20261119'
    if ($r09v11m) {
        $t9 = [IO.File]::ReadAllText($r09v11m); $ll = @($t9.Trim() -split "`r?`n")
        Check 'E1a' 'настоящий отчёт 09 r17a (В1.1 + r2m_cam): предпоследняя строка «# POSEFIX_V11: …», последняя «# VERDICT OK»' ($ll[-1].Trim() -ceq '# VERDICT OK' -and $ll[-2].Trim() -ceq $PVF) (($ll | Select-Object -Last 2) -join ' | ')
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261119_070000.log' 30
        $r = Run07 (New-Out07 'e1_real09' $r09v11m); Check 'E1' '07: настоящий отчёт 09 r17a со строкой POSEFIX_V11 в файле, сделан после 48 - условия пройдены, 07 дошёл до подделки ssh' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261119_120000.log' 2
        $r = Run07 (New-Out07 'e2_real09_late' $r09v11m); Check 'E2' '07: тот же отчёт, но журнал 48 позже него - код 4 до подделки (3c работает и с новой строкой)' ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'ДО последней установки или отката пакета на дрон') ('code=' + $r.Code + ' ' + $r.Console)
    }
    elseif (-not (Want 'W')) { Note 'E1, E2 пропущены: раздел W (источник настоящих отчётов 09 r17a) не запускался' }
    else { Check 'E1' 'нет настоящего отчёта 09 r17a В1.1 + r2m_cam (W1 не прошёл)' $false '' }
    if ($script:r09real) {
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261119_070000.log' 30; $null = Pkg-File 'drone_pkg_r2m_cam_20261117' 'r2m_cam_install_20261119_070000.log' 40
        $r = Run07 (New-Out07 'e4_real_drone09' $script:r09real); Check 'E4' '07: отчёт 09 r17a по НАСТОЯЩЕМУ ответу Pi с дрона (В1.1 + r2m_cam, строка POSEFIX_V11 в файле), журналы 48 и 44 старше - условия пройдены (до подделки)' (Passed $r) ('code=' + $r.Code + ' ' + $r.Console)
    }
    if ($r09old) {
        Clear-Pkgs; $null = Pkg-File $pk 'posefix_v1_install_20261119_070000.log' 30
        $r = Run07 (New-Out07 'e3_old09' $r09old); Check 'E3' '07: настоящий отчёт 09 r17a при старом В1 («# VERDICT NOT_OK») - код 4 до подделки, «не успешна»' ($r.Guard -and $r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не успешна') ('code=' + $r.Code)
    }
    Clear-Pkgs; Move-Item -LiteralPath $gate -Destination (Join-Path $Run 'gate_aside_TAKEOFF_APPROVED.txt')
}

# ======================= G: страж сам отказывает, если ssh - не подделка (контроль, как в r13-r17) =======================
if (Want 'G') {
    $stubSrc = 'using System; using System.IO; public static class StubSshNoMarker { public static int Main(string[] a) { File.AppendAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "stub_called.txt"), DateTime.Now.ToString("s") + Environment.NewLine); Console.Error.WriteLine("stub ssh"); return 255; } }'
    $stubDir = Join-Path $Run 'stub_bez_metki'; New-Item -ItemType Directory -Path $stubDir | Out-Null; $stubExe = Join-Path $stubDir 'ssh.exe'
    Add-Type -TypeDefinition $stubSrc -OutputAssembly $stubExe -OutputType ConsoleApplication
    $env:PATH = $stubDir + ';' + $FakeDir + ';' + $oldPath
    $og = New-OutDir 'g_path'; $r = Run-Ps 'run_measure.ps1' $og '-Label hand_center -DurationSec 120 -Mode measure -Wake 1' -ChildGuard -GuardControl
    $env:PATH = $FakeDir + ';' + $oldPath
    Check 'G1' 'контроль стража: ssh-заглушка без метки стоит в PATH раньше подделки - страж отказал, шаг 03 НЕ запускался (заглушка не вызвана, out пуст)' ((-not $r.Guard) -and $r.Code -eq -1 -and $r.Console -match 'не подделка' -and -not (Test-Path -LiteralPath (Join-Path $stubDir 'stub_called.txt')) -and @(Get-ChildItem -LiteralPath $og -Force).Count -eq 0) ($r.Console)
    $fakeKeep = Join-Path $Run 'fake_keep_ssh.exe'; Copy-Item -LiteralPath $FakeExe -Destination $fakeKeep; Copy-Item -LiteralPath $stubExe -Destination $FakeExe -Force
    $og = New-OutDir 'g_swap'; $r = Run-Ps 'run_install_check.ps1' $og '' -ChildGuard -GuardControl
    Check 'G2' 'контроль стража: на месте подделки заглушка без метки (другой sha) - страж отказал, 09 НЕ запускался' ((-not $r.Guard) -and $r.Code -eq -1 -and $r.Console -match 'sha ssh не равен' -and -not (Test-Path -LiteralPath (Join-Path $FakeDir 'stub_called.txt')) -and @(Get-ChildItem -LiteralPath $og -Force).Count -eq 0) ($r.Console)
    Copy-Item -LiteralPath $fakeKeep -Destination $FakeExe -Force
    Check 'G3' 'после контроля подделка возвращена: страж снова пропускает' ((Guard-InProc) -eq '' -and (Guard-Child) -eq '' -and (Sha $FakeExe) -eq $script:FakeSha) ''
    Check 'G4' 'страж за весь прогон не отказал ни разу, кроме двух контрольных (G1, G2)' ($script:guardRefusals -eq 0) ('отказов: ' + $script:guardRefusals)
}

# ======================= C: .cmd =======================
if (Want 'C') {
    $cmds = @(Get-ChildItem -LiteralPath $Kit -Filter '*.cmd' -File)
    $badCmd = @($cmds | Where-Object { $l = @([IO.File]::ReadAllLines($_.FullName, [Text.Encoding]::UTF8)); -not ($l.Count -ge 3 -and $l[0] -eq '@echo off' -and $l[2] -match '^echo (ТОЛЬКО ЧТЕНИЕ|МЕНЯЕТ ДРОН)') } | ForEach-Object { $_.Name })
    Check 'C1' ('все .cmd в корне набора (' + $cmds.Count + '): первая выводимая строка - ТОЛЬКО ЧТЕНИЕ или МЕНЯЕТ ДРОН; новых .cmd нет') ($badCmd.Count -eq 0 -and $cmds.Count -eq 32) ($badCmd -join ', ')
    $par = @(@($STOP03, $OK09) | Where-Object { $_ -match '[()&|<>%]' })
    Check 'C2' 'новые тексты echo внутри if (...) в 03 и 09 без скобок, &, |, <, >, % (иначе cmd ломает строку)' ($par.Count -eq 0) ''
}

# ======================= K: r17a = копия r17 + ожидаемые правки =======================
if (Want 'K') {
    $r17 = Join-Path (Split-Path -Parent $Kit) 'bench_kit_20261119_r17'
    if (Test-Path -LiteralPath $r17) {
        $changed = @('run_measure.ps1', 'pi\vision_measure.sh', 'run_install_check.ps1', 'run_fingerprint.ps1', '03_v_rukakh.cmd', '09_sverka_install.cmd', 'SHA256SUMS.txt')
        $r17f = @(Get-ChildItem -LiteralPath $r17 -Recurse -File | ForEach-Object { $_.FullName.Substring($r17.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and $_ -notmatch '^tests\\run_[^\\]+\\' })
        $miss = @(); $diff = @(); $same = 0
        foreach ($rel in $r17f) { $k = Join-Path $Kit $rel; if (-not (Test-Path -LiteralPath $k)) { $miss += $rel; continue }; if ((Sha $k) -ne (Sha (Join-Path $r17 $rel))) { if ($changed -notcontains $rel) { $diff += $rel } } else { $same++ } }
        Check 'K1' ('все файлы r17 есть в r17a; изменены только ожидаемые 7 (run_measure.ps1, vision_measure.sh, 09, 15, 03 и 09 .cmd, SHA256SUMS), байт в байт одинаковых: ' + $same) ($miss.Count -eq 0 -and $diff.Count -eq 0) (($miss + $diff) -join ', ')
        $chg = @($changed | Where-Object { $_ -ne 'SHA256SUMS.txt' -and (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r17 $_)) })
        Check 'K1b' 'все 6 ожидаемых файлов действительно изменены' ($chg.Count -eq 6) ($chg -join ', ')
        $newOk = '^(README_r17a\.md|DIFF_r17_r17a\.txt|tests\\run_tests_r17a\.ps1|tests\\run_tests_r17a_pi\.sh|tests\\r17a_wsl_vm\.sh|proverka_r17a\\.+|tests\\run_[^\\]+\\.+)$'
        $new = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object { $_.FullName.Substring($Kit.Length + 1) } | Where-Object { $_ -notlike 'out\*' -and -not (Test-Path -LiteralPath (Join-Path $r17 $_)) -and $_ -notmatch $newOk })
        Check 'K2' 'новых файлов, кроме ожидаемых (README_r17a, DIFF_r17_r17a, тесты r17a, proverka_r17a), нет' ($new.Count -eq 0) ($new -join ', ')
        $rd = @('README.md', 'README_r17.md', 'PROGRESS.md', 'run_07_takeoff.ps1', 'lib\bb_lists.ps1', 'lib\bb_common.ps1', 'pi\install_check.sh', 'pi\overlay_fingerprint.sh', 'image_r2j\POSEFIX_V11_20261119.tsv', 'image_r2j\POSEFIX_JD2_20261117.tsv', 'image_r2j\R2M_CAM_20261117.tsv', 'tests\run_tests_r17.ps1', 'tests\run_tests_r17_pi.sh') | Where-Object { (Sha (Join-Path $Kit $_)) -ne (Sha (Join-Path $r17 $_)) }
        Check 'K5' 'README, README_r17, PROGRESS.md, 07, списки и функции списков, скрипты Pi 09/15, тесты r17 не менялись (байт в байт как в r17)' (@($rd).Count -eq 0) (@($rd) -join ', ')
    }
    else { Check 'K0' 'папка r17 рядом не найдена: сравнение с r17 не сделано' $false $r17 }
    Check 'K3' 'gates\: TAKEOFF_APPROVED.txt и OVERLAY_*_APPROVED.txt нет; image_r2j\gates\S2_S3_PASSED.txt нет' (-not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_MAVROS_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_BUMBLEBEE_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'image_r2j\gates\S2_S3_PASSED.txt'))) ''
    $outFiles = @(Get-ChildItem -LiteralPath (Join-Path $Kit 'out') -File -ErrorAction SilentlyContinue)
    Check 'K4' 'out\ набора r17a пуст (тесты пишут только в tests\run_r17a_*)' ($outFiles.Count -eq 0) (($outFiles | ForEach-Object { $_.Name }) -join ', ')
}

$env:PATH = $oldPath
Note ''
Note ('WSL-песочницы: ' + $WB + ' ' + $VB + ' (не удалялись)')
Note ('ИТОГ r17a: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
