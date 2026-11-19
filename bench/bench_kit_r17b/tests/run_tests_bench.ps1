# run_tests_bench.ps1 (Claude, 10.11.2026) - тесты набора стенда в песочнице. К дрону не подключается: вместо ssh стоит подделка fake_ssh.exe (первая в PATH),
# вместо params_check.cmd набора r4 в песочнице стоит заглушка, которая только записывает свои аргументы.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_b_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') {
    if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") }
}
$realPc = $env:COMPUTERNAME

# ---------- песочница ----------
$SB = Join-Path $Run 'sb\bench_kit_20261110'
New-Item -ItemType Directory -Path $SB -Force | Out-Null
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Kit.Length + 1)
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest
}
# в песочнице у cmd с set /p убрана строка chcp 65001 (она мешает set /p читать из файла, только в тесте; в боевых файлах она на месте)
foreach ($n in '03_v_rukakh.cmd', '04_vibratsiya.cmd', '07_vzlet_zagotovka.cmd', '11_sborka_mavros_bp02.cmd', '12_otkat_mavros_bp02.cmd', '13_sborka_bumblebee_r2j.cmd', '14_otkat_sborki_bumblebee.cmd', '16_podkljuchit_overlay.cmd', '17_otkljuchit_overlay.cmd') {
    $pp = Join-Path $SB $n
    $ls = [IO.File]::ReadAllText($pp) -split "`r`n"
    [IO.File]::WriteAllText($pp, (($ls | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
}
$R4dir = Join-Path $SB 'params_check'   # r8 (13.11): 01 и 07 зовут params_check этого набора (v3); заглушка встаёт на место его копии в песочнице (до r8 - ..\kit_20261109_r4)
New-Item -ItemType Directory -Path $R4dir -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $R4dir 'params_check.cmd'), "@echo off`r`necho ARGS=%* >> `"%BB_STUB_LOG%`"`r`necho NO_PAUSE=%BB_NO_PAUSE% KITOUT=%BB_KIT_OUT% >> `"%BB_STUB_LOG%`"`r`nexit /b %BB_STUB_RC%`r`n", $utf8n)
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh.cs'))) -OutputAssembly (Join-Path $FakeDir 'ssh.exe') -OutputType ConsoleApplication
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_scp.cs'))) -OutputAssembly (Join-Path $FakeDir 'scp.exe') -OutputType ConsoleApplication
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'

# канонические ответы "дрона"
$canPi = Join-Path $Run 'canned_pi_state.txt'
[IO.File]::WriteAllText($canPi, "PI_DATE 2026-11-10 10:00:00 +0400`nPI_MODEL Raspberry Pi 5 Model B`nPI_LOADAVG 0.41 0.35 0.30`nPI_TEMP temp=48.2'C`nPI_THROTTLED throttled=0x0`nPI_BUMBLEBEE_SERVICE active`nPI_MAVROS_STATE_ONE_SAMPLE:`n  connected: true`n  armed: false`nBB_PI_STATE_DONE`n", $utf8n)
$canArm = Join-Path $Run 'canned_arm_ok.txt'
[IO.File]::WriteAllText($canArm, "BB_ARM connected=true armed=false`nBB_ARM_STATE_DONE`n", $utf8n)
$canMeas = Join-Path $Run 'canned_measure.txt'
$measOk = @"
META script vision_measure.sh dur=300 label=bez_video mode=measure wake=1 start_epoch=1794000000 date=2026-11-10 10:05:00
META initial_state connected=True armed=False mode=MANUAL
SAMPLE t=5 cpu_total=31.0 temp=55.0 throttled=0x0 aruco_detect.py[1234]=60.2 vpe_fix.py[1300]=2.1
EVENT t=100.0 process_new aruco_detect.py pid=4321 (перезапуск или новый процесс)
SUMMARY label bez_video
SUMMARY markers_msgs count=2400 hz=8.00 gaps_over_0.5s=3 max_gap_s=1.10 start_delay_s=0.50 end_silence_s=0.10 top_gaps=1.10,0.70,0.60
SUMMARY camera_image_raw count=7200 hz=24.00 gaps_over_0.5s=0 max_gap_s=0.12 (подписка raw)
SUMMARY vision_pose /mavros/mavros/pose_cov count=0 hz=0.00 gaps_over_0.5s=0 max_gap_s=0.00
SUMMARY throttled_last 0x0
J aruco: detection ACTIVE (armed=False mode=MANUAL)
META python_exit 0
BB_BENCH_DONE rc=0
"@
$measOk = $measOk -replace "`r`n", "`n"
[IO.File]::WriteAllText($canMeas, $measOk, $utf8n)
$canBat = Join-Path $Run 'canned_battery_ok.txt'
[IO.File]::WriteAllText($canBat, "META script battery_check.sh dur=30 date=2026-11-10 10:00:00`nMETA state connected=True armed=False mode=MANUAL`nMETA battery_topic /mavros/battery`nMETA statustext_topic /mavros/statustext/recv`nBAT t=0.5 voltage_v=16.20 percentage=0.95 current_a=0.50 present=True cells_reported=4`nPARAM BAT1_SOURCE i 0`nPARAM BAT1_N_CELLS i 4`nPARAM BAT1_V_EMPTY d 3.5`nPARAM BAT1_V_CHARGED d 4.05`nSUMMARY duration_s 30.1`nSUMMARY battery_msgs count=30 hz=1.00 voltage_v min=16.10 max=16.30 mean=16.20 percentage min=0.94 max=0.96 present_values=True cells_reported=4`nSUMMARY statustext count=0 battery_related=0 (все строки выше, до 60)`nSUMMARY params_read 11 of 11`nMETA python_exit 0`nBB_BATTERY_DONE rc=0`n", $utf8n)
$canJournal = Join-Path $Run 'canned_journal_ok.txt'
[IO.File]::WriteAllText($canJournal, "META script journal_window.sh window_s=300 pi_date=2026-11-10 10:30:00 +0400`n2026-11-10T10:25:01.100000+0400 bumblebee[1]: [INFO] [1794000001.100] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_ok -> publish=True`nBB_JOURNAL_DONE rc=0`n", $utf8n)
function New-InstallCanned([int]$ok, [int]$diff, [int]$miss, [int]$nop, [int]$cdiff = 0, [int]$cmiss = 0, [int]$bmiss = 0, [int]$stale = 0, [int]$rtDiff = 0, [int]$rtMiss = 0) {
    $t = "INSTALL_ARCH aarch64`nINSTALL_PREFIX /home/lb/ros2_ws/install/bumblebee`nINSTALL_FILE aruco_detect.py OK`n"
    if ($nop -eq 0) { $t += "BB_RTPY ok=$(8 - $rtDiff - $rtMiss) diff=$rtDiff missing=$rtMiss`n" }   # S2: 7 launch-файлов + fcu_detect.py
    return ($t + "BB_INSTALL_CHECK ok=$ok diff=$diff missing=$miss noprefix=$nop cpp_ok=$(16 - $cdiff - $cmiss) cpp_diff=$cdiff cpp_missing=$cmiss bin_ok=$(6 - $bmiss) bin_missing=$bmiss stale=$stale`nBB_INSTALL_CHECK_DONE`n")
}
$canInstall = Join-Path $Run 'canned_install_ok.txt'; [IO.File]::WriteAllText($canInstall, (New-InstallCanned 10 0 0 0), $utf8n)
function New-SvcCanned([string]$st1 = 'active', [string]$st2 = 'active', [string]$st3 = 'active', [int]$nr3 = 0, [int]$er2 = 0, [bool]$den1 = $false) {
    # ответ services_check.sh: wifi-manager (st1), notify-manager (st2, er2 ошибок в журнале), led-default (st3, nr3 перезапусков)
    $names = @('wifi-manager', 'notify-manager', 'led-default'); $st = @($st1, $st2, $st3); $nr = @(0, 0, $nr3); $er = @(0, $er2, 0)
    $t = ''; $act = 0; $den = 0
    for ($i = 0; $i -lt 3; $i++) {
        $acc = 'ok'; if ($i -eq 0 -and $den1) { $acc = 'denied'; $den++ }
        if ($st[$i] -eq 'active') { $act++ }
        $t += "SVC $($names[$i]) $($st[$i])`nSVC_RESTARTS $($names[$i]) $($nr[$i])`nSVC_JOURNAL $($names[$i]) lines=2 access=$acc`nSVC_ERRORS $($names[$i]) $($er[$i])`nJT $($names[$i]) | May 01 10:00:00 started`n"
    }
    return ($t + "BB_SVC_RESULT active=$act errors=$($er2) restarts=$nr3 denied=$den`nBB_SVC_DONE`n")
}
$canSvc = Join-Path $Run 'canned_svc_ok.txt'; [IO.File]::WriteAllText($canSvc, (New-SvcCanned), $utf8n)
function New-MavrosCanned([string]$prefix, [string]$head, [int]$ok) {
    $t = "MAVROS_APT ros-jazzy-mavros=2.14.0-1noble`nMAVROS_ACTIVE_PREFIX $prefix`nMAVROS_PKG_VERSION 2.14.0`nMAVROS_SRC_MODE commit=$head`nMAVROS_GIT_HEAD $head`n"
    return ($t + "BB_MAVROS_CHECK src_ok=$ok src_diff=$(5 - $ok) src_missing=0`nBB_MAVROS_CHECK_DONE`n")
}
$bp02 = 'd63a23674dd80ff4525829ca4bd716bbcc773111'
$canMavros = Join-Path $Run 'canned_mavros_ok.txt'; [IO.File]::WriteAllText($canMavros, (New-MavrosCanned '/home/lb/bench_ws/mavros/install/mavros' $bp02 5), $utf8n)
$canMbpre = Join-Path $Run 'canned_mbpre_ok.txt'
[IO.File]::WriteAllText($canMbpre, "MBPRE service_bumblebee inactive`nMBPRE absent /home/lb/bench_ws/mavros`nMBPRE absent /home/lb/bench_ws/incoming/rc3_mavros`nMBPRE disk_free_mb 20000`nMBPRE builders_running 0`nMBPRE apt_state ros-jazzy-mavros=2.14.0-1noble ros-jazzy-libmavconn=2.14.0-1noble`nMBPRE active_prefix /opt/ros/jazzy`nMBPRE uname Linux 6.8.0 aarch64`nBB_MBPRE_RESULT OK`nBB_MBPRE_DONE`n", $utf8n)
$canAside = Join-Path $Run 'canned_aside_ok.txt'
[IO.File]::WriteAllText($canAside, "ASIDE /home/lb/bench_ws/mavros`nASIDE /home/lb/bench_ws/mavros_deps`nBB_ASIDE_DONE /home/lb/bench_ws/_aside_mavros_20261110_200000 files=2`n", $utf8n)
function New-FpCanned([string]$target, [int]$files, [int]$pyOk, [int]$pyBad, [int]$srcOk, [int]$srcBad, [int]$bin, [int]$stale, [int]$noinst, [int]$rtDiff = 0, [int]$rtMiss = 0) {
    $t = "FP_TARGET $target`nFP_ROOT /home/lb/bench_ws/x`n"
    if ($noinst -eq 0) { $first = $(if ($target -eq 'mavros') { 'mavros/lib/libmavros.so' } else { 'bumblebee/lib/bumblebee/aruco_detect.py' }); foreach ($i in 1..$files) { $t += 'FP_FILE ' + ([string]$i * 64).Substring(0, 64) + ' ' + $first + $(if ($i -gt 1) { ".$i" } else { '' }) + "`n" } }
    if ($noinst -eq 0) { $rtN = $(if ($target -eq 'bumblebee') { 8 } else { 0 }); $t += "BB_FP_RT ok=$($rtN - $rtDiff - $rtMiss) diff=$rtDiff missing=$rtMiss`n" }   # S2
    return ($t + "BB_FP_RESULT files=$files py_ok=$pyOk py_bad=$pyBad src_ok=$srcOk src_bad=$srcBad bin=$bin stale=$stale noinstall=$noinst`nBB_FP_DONE`n")
}
$canBbpre = Join-Path $Run 'canned_bbpre_ok.txt'
[IO.File]::WriteAllText($canBbpre, "BBPRE service_bumblebee inactive`nBBPRE absent /home/lb/bench_ws/r2j`nBBPRE colcon_defaults absent`nBBPRE src_ok=10 src_bad=0`nBBPRE disk_free_mb 20000`nBBPRE builders_running 0`nBBPRE dep ros-jazzy-rclcpp ii 1.0`nBBPRE live_prefix /home/lb/ros2_ws/install/bumblebee`nBBPRE uname Linux 6.8.0 aarch64`nBB_BBPRE_RESULT OK`nBB_BBPRE_DONE`n", $utf8n)
$canBbbuild = Join-Path $Run 'canned_bbbuild_ok.txt'
[IO.File]::WriteAllText($canBbbuild, "ИСХОДНИКИ r2j В /home/lb/bench_ws/r2j ГОТОВО`nStarting >>> bumblebee`nFinished <<< bumblebee [2min 25s]`nSummary: 1 package finished [2min 26s]`nBB_BBBUILD_OK 146`n", $utf8n)
$canBbaside = Join-Path $Run 'canned_bbaside_ok.txt'
[IO.File]::WriteAllText($canBbaside, "ASIDE /home/lb/bench_ws/r2j`nBB_BBASIDE_DONE /home/lb/bench_ws/_aside_bb_r2j_20261110_210000 files=1`n", $utf8n)
$canFpBb = Join-Path $Run 'canned_fp_bb_ok.txt'; [IO.File]::WriteAllText($canFpBb, (New-FpCanned 'bumblebee' 3 10 0 16 0 6 0 0), $utf8n)
$canFpMv = Join-Path $Run 'canned_fp_mv_none.txt'; [IO.File]::WriteAllText($canFpMv, (New-FpCanned 'mavros' 0 0 0 0 0 0 0 1), $utf8n)
$canConn = Join-Path $Run 'canned_conn_ok.txt'; [IO.File]::WriteAllText($canConn, "BB_CONN_DONE mavros /home/lb/bench_ws/_bk_start_bumblebee_20261111_090000`n", $utf8n)
$canDisc = Join-Path $Run 'canned_disc_ok.txt'; [IO.File]::WriteAllText($canDisc, "BB_DISC_DONE /home/lb/bench_ws/_bk_start_bumblebee_20261111_090000`n", $utf8n)
$canFg = Join-Path $Run 'canned_fg_ok.txt'
[IO.File]::WriteAllText($canFg, "FG_DIR /home/lb/ros2_ws/src/bumblebee/examples drone.py OK`nFG_NEAR /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/../drone.py OK`nBB_FG_RESULT OK`nBB_FG_DONE`n", $utf8n)
$baseSha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Kit 'image_r2j\START_BUMBLEBEE_BASELINE_s0b.sh')).Hash.ToLower()
$canSsc = Join-Path $Run 'canned_ssc_ok.txt'
[IO.File]::WriteAllText($canSsc, "SSC sha256 $baseSha bytes 2441`nSSC ros2_ws_lines 1`nSSC overlay_lines 0`nSSC line 16:source /opt/ros/jazzy/setup.bash`nSSC line 17:source /home/lb/ros2_ws/install/setup.bash`nBB_SSC_DONE`n", $utf8n)
$shaFile = Join-Path $Run 'sha_out.txt'

function Reset-Fake([string]$mode = 'normal') {
    foreach ($f in 'mode.txt', 'canned_pi_state.txt', 'canned_measure.txt', 'canned_arm.txt', 'arm_rc.txt', 'events.txt', 'measure_rc.txt', 'sha_out.txt', 'flight_rc.txt', 'calls.log', 'canned_battery.txt', 'canned_journal.txt', 'battery_rc.txt', 'journal_rc.txt', 'canned_install.txt', 'canned_mavros.txt', 'install_rc.txt', 'mavros_rc.txt', 'canned_mbpre.txt', 'canned_aside.txt', 'mbpre_rc.txt', 'aside_rc.txt', 'canned_bbpre.txt', 'canned_bbbuild.txt', 'canned_bbaside.txt', 'canned_fp_bumblebee.txt', 'canned_fp_mavros.txt', 'canned_conn.txt', 'canned_disc.txt', 'canned_fg.txt', 'canned_ssc.txt', 'fg_rc.txt', 'ssc_rc.txt', 'bbpre_rc.txt', 'bbbuild_rc.txt', 'bbaside_rc.txt', 'fp_rc.txt', 'conn_rc.txt', 'disc_rc.txt') { $p = Join-Path $FakeDir $f; if (Test-Path $p) { Remove-Item $p } }
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), $mode)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_pi_state.txt'), $canPi)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_measure.txt'), $canMeas)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_arm.txt'), $canArm)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_battery.txt'), $canBat)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_journal.txt'), $canJournal)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_install.txt'), $canInstall)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_mavros.txt'), $canMavros)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_mbpre.txt'), $canMbpre)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_aside.txt'), $canAside)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_bbpre.txt'), $canBbpre)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_bbbuild.txt'), $canBbbuild)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_bbaside.txt'), $canBbaside)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_fp_bumblebee.txt'), $canFpBb)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_fp_mavros.txt'), $canFpMv)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_conn.txt'), $canConn)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_disc.txt'), $canDisc)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_fg.txt'), $canFg)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_ssc.txt'), $canSsc)
    [IO.File]::WriteAllText((Join-Path $FakeDir 'canned_svc.txt'), $canSvc)
}
function Set-Canned([string]$ptrName, [string]$text) {
    $script:cn = 1 + [int]$script:cn
    $f = Join-Path $Run ('canned_' + $script:cn + '.txt')
    [IO.File]::WriteAllText($f, $text, $utf8n)
    [IO.File]::WriteAllText((Join-Path $FakeDir $ptrName), $f)
}
$script:seq = 0
function Run-Cmd([string]$cmdName, [string]$stdin, [string]$cmdArgs = '', [string]$pc = $realPc, [int]$stubRc = 0) {
    $script:seq++
    $clx = Join-Path $FakeDir "calls.log"; if (Test-Path $clx) { Remove-Item $clx }
    $id = 'r' + $script:seq
    $out = Join-Path $Run ('out_' + $id); New-Item -ItemType Directory -Path $out -Force | Out-Null
    $env:BB_KIT_OUT = $out
    $stubLog = Join-Path $Run ('stub_' + $id + '.log'); $env:BB_STUB_LOG = $stubLog; $env:BB_STUB_RC = [string]$stubRc
    $inFile = Join-Path $Run ($id + '_stdin.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $env:COMPUTERNAME = $pc
    $so = Join-Path $Run ($id + '_console.txt')
    $cmdPath = Join-Path $SB $cmdName
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + $cmdPath + '" ' + $cmdArgs + ' < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $sw.Stop()
    $env:COMPUTERNAME = $realPc
    $cl = Join-Path $FakeDir 'calls.log'
    $calls = @(); if (Test-Path $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    $con = ''; if (Test-Path $so) { $con = [IO.File]::ReadAllText($so) }
    $stub = @(); if (Test-Path $stubLog) { $stub = @(Get-Content -LiteralPath $stubLog -Encoding UTF8) }
    return @{ Code = $p.ExitCode; Calls = $calls; J = ($calls -join "`n"); Out = $out; Console = $con; Stub = $stub; Secs = $sw.Elapsed.TotalSeconds }
}
function Sha-Lf([string]$path) {
    $txt = ([IO.File]::ReadAllText($path)) -replace "`r`n", "`n"
    $b = (New-Object Text.UTF8Encoding($false)).GetBytes($txt)
    return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($b)) -replace '-', '').ToLower()
}

# ---------- S: статические проверки ----------
$cmds = Get-ChildItem -LiteralPath $Kit -Filter '*.cmd' | Sort-Object Name
# r6 (12.11): в корне добавлены .cmd r6 (09c, 15c, 19-24); их проверяет tests\run_tests_r6.ps1. Здесь, как в r5, - 17 .cmd r5 в корне; вариант камеры r5 (05v) отложен в _aside
$cmds = @($cmds | Where-Object { $_.Name -match '^(0[1-9]|1[0-8])[ab]?_' -and $_.Name -notmatch '^(09c|15c)_' })
Check 'S1' ('в наборе .cmd: ' + $cmds.Count + ' (01, 02a, 02b, 03, 04, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18 в корне)') ($cmds.Count -eq 17) (($cmds | ForEach-Object { $_.Name }) -join ',')
$allCmd = @($cmds) + @(Get-ChildItem -LiteralPath (Join-Path $Kit 'image_r2j') -Filter '*.cmd') + @(Get-ChildItem -LiteralPath (Join-Path $Kit '_aside\image_r2j_camera_variant_dabd5076_r5') -Filter '*.cmd')
foreach ($c in $allCmd) {
    $bytes = [IO.File]::ReadAllBytes($c.FullName)
    $txt = [IO.File]::ReadAllText($c.FullName)
    $lines = Get-Content -LiteralPath $c.FullName -Encoding UTF8
    $first = ($lines | Where-Object { $_ -notmatch '^@echo off|^chcp|^rem' } | Select-Object -First 1)
    Check 'S1' ($c.Name + ': первая строка «ТОЛЬКО ЧТЕНИЕ» или «МЕНЯЕТ ДРОН»') ($first -match '^echo (ТОЛЬКО ЧТЕНИЕ|МЕНЯЕТ ДРОН( \(косвенно\))?): ') $first
    Check 'S1' ($c.Name + ': концы строк CRLF, без BOM') (($txt -split "`n").Count -gt 5 -and -not ($txt -match "[^`r]`n") -and -not ($bytes[0] -eq 0xEF)) ''
    Check 'S1' ($c.Name + ': проверка имени ПК DESKTOP-H5CPN8E') ($txt -match 'COMPUTERNAME%"=="DESKTOP-H5CPN8E"') ''
    Check 'S1' ($c.Name + ': нет «if ...(...)» с круглыми скобками в тексте echo внутри блока') (-not (($lines | Where-Object { $_ -match '^if .*\(echo [^)]*\([^)]*\)' -and $_ -notmatch 'findstr' }).Count)) ''
}
foreach ($n in '01_snimok_do.cmd', '04_vibratsiya.cmd', '08_batareya.cmd', '09_sverka_install.cmd', '10_mavros_versiya.cmd', '15_otpechatki_sborki.cmd', '18_sostoyanie_sluzhb.cmd') {
    $lines = Get-Content -LiteralPath (Join-Path $Kit $n) -Encoding UTF8
    $first = ($lines | Where-Object { $_ -notmatch '^@echo off|^chcp|^rem' } | Select-Object -First 1)
    Check 'S2' ($n + ': ТОЛЬКО ЧТЕНИЕ, не МЕНЯЕТ ДРОН') ($first -match '^echo ТОЛЬКО ЧТЕНИЕ: ' -and $first -match 'моторы' -and $first -notmatch 'МЕНЯЕТ ДРОН') ''
    Check 'S2' ($n + ': в тексте нет sudo, scp, reboot, param set, arming') (-not (($lines -join "`n") -match 'sudo|scp |reboot|param set|arming|set_mode')) ''
}
foreach ($n in '02a_zamer_bez_video.cmd', '02b_zamer_s_video.cmd', '03_v_rukakh.cmd') {
    $lines = Get-Content -LiteralPath (Join-Path $Kit $n) -Encoding UTF8
    $first = ($lines | Where-Object { $_ -notmatch '^@echo off|^chcp|^rem' } | Select-Object -First 1)
    Check 'S2' ($n + ': первая строка честно «МЕНЯЕТ ДРОН (косвенно)»: моторы, vpe_fix передаёт позу в MAVROS, Как остановить; нет «ТОЛЬКО ЧТЕНИЕ»') ($first -match '^echo МЕНЯЕТ ДРОН \(косвенно\): ' -and $first -match 'моторы' -and $first -match 'vpe_fix' -and $first -match 'pose_cov' -and $first -match 'Как остановить' -and $first -notmatch 'ТОЛЬКО ЧТЕНИЕ' -and $first -notmatch 'ничего не пишется') ''
    Check 'S2' ($n + ': в тексте нет sudo, scp, reboot, param set, arming') (-not (($lines -join "`n") -match 'sudo|scp |reboot|param set|arming|set_mode')) ''
}
$t7 = Get-Content -LiteralPath (Join-Path $Kit '07_vzlet_zagotovka.cmd') -Encoding UTF8
Check 'S3' '07: первая строка «МЕНЯЕТ ДРОН: ВЗЛЁТ - моторы запустятся ... Как остановить: переключатель режима, CH8, Ctrl+C»' (($t7 | Where-Object { $_ -match '^echo МЕНЯЕТ ДРОН: ВЗЛЁТ - моторы запустятся' } | Select-Object -First 1) -match 'Как остановить: переключатель режима на пульте, CH8, Ctrl\+C') ''
$p5 = Get-Content -LiteralPath (Join-Path $Kit 'image_r2j\05_install_r2j.cmd') -Encoding UTF8
Check 'S3' '05: «МЕНЯЕТ ДРОН: … r2j насовсем … Как вернуть: 06_rollback_r2j.cmd», условия правила 14 в первой строке' (($p5 | Where-Object { $_ -match '^echo МЕНЯЕТ ДРОН' } | Select-Object -First 1) -match 'r2j' -and ($p5 | Where-Object { $_ -match '^echo МЕНЯЕТ ДРОН' } | Select-Object -First 1) -match 'правила 14' -and ($p5 | Where-Object { $_ -match '^echo МЕНЯЕТ ДРОН' } | Select-Object -First 1) -match 'Как вернуть: 06_rollback_r2j\.cmd') ''
foreach ($f in (Get-ChildItem -LiteralPath $Kit -Recurse -Filter '*.ps1' | Where-Object { $_.FullName -notmatch '\\tests\\run_[a-z]_\d' })) {
    $b = [IO.File]::ReadAllBytes($f.FullName)
    Check 'S4' ($f.Name + ': UTF-8 с BOM') ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF) ''
}
foreach ($f in (Get-ChildItem -LiteralPath $Kit -Recurse -Filter '*.sh' | Where-Object { $_.FullName -notmatch '\\tests\\run_[a-z]_\d' })) {
    $x = [IO.File]::ReadAllText($f.FullName)
    Check 'S4' ($f.Name + ': концы строк LF') (-not $x.Contains("`r")) ''
}
# Pi-скрипты: только чтение (код без комментариев)
foreach ($n in 'battery_check.sh', 'journal_window.sh', 'install_check.sh', 'mavros_check.sh', 'mavros_build_precheck.sh', 'bb_build_precheck.sh', 'overlay_fingerprint.sh') {
    $code = (([IO.File]::ReadAllLines((Join-Path $Kit ('pi\' + $n))) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
    $code = [regex]::Replace($code, "(?s)<<'PY'.*?\nPY", '')
    $code = $code.Replace('<version>', '')   # тег package.xml в grep/sed, не перенаправление
    $noRedir = ($code -replace '2>&1', '' -replace '> /dev/null', '' -replace '>/dev/null', '' -replace '>&2', '' -replace '< /dev/null', '')
    Check 'S5' ($n + ': нет перенаправления вывода в файл (> или >>), кроме /dev/null, 2>&1 и >&2') (-not ($noRedir -match '>')) ''
}
foreach ($n in 'pi_state.sh', 'vision_measure.sh', 'arm_state.sh', 'battery_check.sh', 'journal_window.sh', 'install_check.sh', 'mavros_check.sh', 'mavros_build_precheck.sh', 'bb_build_precheck.sh', 'overlay_fingerprint.sh') {
    $code = (([IO.File]::ReadAllLines((Join-Path $Kit ('pi\' + $n))) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
    Check 'S5' ($n + ': нет записи (sudo, rm, mv, cp, tee, mkdir, touch, chmod, systemctl restart/start/stop, reboot)') (-not ($code -match '(^|[\s;|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|chown|reboot|shutdown)\s' -or $code -match 'systemctl\s+(restart|start|stop|enable|disable|kill)')) ''
    Check 'S5' ($n + ': нет команд PX4/MAVROS на запись (param set, service call, cmd/arming, set_mode, setpoint, offboard, CommandBool, ParamSet)') (-not ($code -match 'ros2 param set|ros2 service call|cmd/arming|cmd/command|set_mode|SetMode|CommandBool|ParamSetV2|ParamSet|mavros/setpoint|motor_test|/mavros/cmd')) ''
}
$vm = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\vision_measure.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'S5' 'vision_measure.sh: единственная публикация — Bool в /aruco_detect/wake (create_publisher один раз)' (([regex]::Matches($vm, 'create_publisher')).Count -eq 1 -and $vm -match "create_publisher\(Bool, '/aruco_detect/wake'") ''
Check 'S5' 'vision_measure.sh: замер отказывается при armed в режиме measure и при отсутствии связи с FCU до того, как создан издатель wake' (($vm.IndexOf('REFUSED armed') -gt 0) -and ($vm.IndexOf('REFUSED armed') -lt $vm.IndexOf('create_publisher')) -and ($vm.IndexOf('REFUSED fcu_not_connected') -lt $vm.IndexOf('create_publisher'))) ''
Check 'S5' 'vision_measure.sh: без pgrep -f и pkill (правило 13)' (-not ($vm -match 'pgrep|pkill')) ''

$asc = [IO.File]::ReadAllLines((Join-Path $Kit 'pi\arm_state.sh'))
Check 'S5' 'arm_state.sh: ТОЛЬКО ЧТЕНИЕ в заголовке, проверка имени дрона, нет publisher/pub/create_publisher' (($asc[1] -match 'ТОЛЬКО ЧТЕНИЕ') -and (($asc -join "`n") -match 'bumblebee-20ec') -and -not (($asc -join "`n") -match 'create_publisher|ros2 topic pub|ros2 service')) ''
$ac = [IO.File]::ReadAllText((Join-Path $Kit 'run_armcheck.ps1'))
Check 'S5' 'run_armcheck.ps1: ТОЛЬКО ЧТЕНИЕ в первой строке, коды 0/5/4, не пишет на дрон (только ssh с pi\arm_state.sh)' (($ac.Split("`n")[0] -match 'ТОЛЬКО ЧТЕНИЕ') -and $ac -match 'exit 5' -and $ac -match 'exit 0' -and -not ($ac -match 'scp|Set-Content -LiteralPath \$sh')) ''
# ---------- A: 01 снимок ----------
Reset-Fake
$r = Run-Cmd '01_snimok_do.cmd' ''
$stateFiles = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_pi_state_*.txt' | Where-Object { $_.Name -notmatch 'err|FAILED' })
Check 'A1' '01: код 0, файл состояния Pi создан' ($r.Code -eq 0 -and $stateFiles.Count -eq 1) ('code=' + $r.Code + ' files=' + $stateFiles.Count)
Check 'A1' '01: два вызова ssh (имя дрона, pi_state.sh); скрипт = pi\pi_state.sh (SHA256, LF)' ($r.Calls.Count -eq 2 -and $r.J -match (Sha-Lf (Join-Path $Kit 'pi\pi_state.sh'))) ('вызовов ' + $r.Calls.Count)
Check 'A1' '01: ssh с -n -T BatchMode, без sudo и записи' ($r.J -match 'BatchMode=yes' -and $r.J -match '\[-n\]' -and -not ($r.J -match 'sudo|scp|reboot')) ''
Check 'A1' '01: после этого вызван params_check.cmd r4 с -Stamp bench_<время>, BB_NO_PAUSE=1, отчёты в out набора' (($r.Stub -join ' ') -match 'ARGS=-Stamp bench_\d{8}_\d{6}' -and ($r.Stub -join ' ') -match 'NO_PAUSE=1' -and ($r.Stub -join ' ') -match [regex]::Escape($r.Out)) ($r.Stub -join ' | ')
Check 'A1' '01: на экране сказано, что настройки совпали (код r4 = 0)' ($r.Console -match 'настройки PX4 совпали') ''
$r = Run-Cmd '01_snimok_do.cmd' '' '' $realPc 2
Check 'A2' '01: код r4 = 2 (отличия): сообщение «есть отличия … снимок до стенда», код 0' ($r.Code -eq 0 -and $r.Console -match 'есть отличия от утверждённого набора') ('code=' + $r.Code)
$r = Run-Cmd '01_snimok_do.cmd' '' '' $realPc 4
Check 'A2' '01: код r4 = 4: сообщение «Настройки не прочитаны»' ($r.Console -match 'Настройки не прочитаны') ''
Reset-Fake 'wrong_host'
$r = Run-Cmd '01_snimok_do.cmd' ''
Check 'A3' '01: чужой дрон: код 4, чтение не делалось, r4 не вызывался' ($r.Code -eq 4 -and $r.Calls.Count -eq 1 -and $r.Stub.Count -eq 0) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake
$r = Run-Cmd '01_snimok_do.cmd' '' '' 'OTHER-PC'
Check 'A3' '01: чужой ПК: код 4, ssh не вызывался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake 'nodone'
$r = Run-Cmd '01_snimok_do.cmd' ''
Check 'A3' '01: pi_state.sh оборвался (нет BB_PI_STATE_DONE): код 4, файл .FAILED, r4 не вызывался' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_pi_state_*.FAILED.txt').Count -eq 1 -and $r.Stub.Count -eq 0) ('code=' + $r.Code)
Reset-Fake 'fail'
$r = Run-Cmd '01_snimok_do.cmd' ''
Check 'A3' '01: нет связи: код 4' ($r.Code -eq 4) ''

# ---------- B: 02a/02b замер ----------
foreach ($pair in @(@('02a_zamer_bez_video.cmd', 'bez_video'), @('02b_zamer_s_video.cmd', 's_video'))) {
    Reset-Fake
    $r = Run-Cmd $pair[0] ''
    $sum = @(Get-ChildItem -LiteralPath $r.Out -Filter ('bench_' + $pair[1] + '_*.summary.txt'))
    $rawf = @(Get-ChildItem -LiteralPath $r.Out -Filter ('bench_' + $pair[1] + '_*.raw.txt'))
    Check 'B1' ($pair[0] + ': код 0, сводка и сырой файл созданы') ($r.Code -eq 0 -and $sum.Count -eq 1 -and $rawf.Count -eq 1) ('code=' + $r.Code)
    Check 'B1' ($pair[0] + ': 2 вызова ssh, аргументы Pi: 300 ' + $pair[1] + ' measure 1; скрипт = pi\vision_measure.sh (SHA256, LF)') ($r.Calls.Count -eq 2 -and $r.J -match ('_ 300 ' + $pair[1] + ' measure 1\]') -and $r.J -match (Sha-Lf (Join-Path $Kit 'pi\vision_measure.sh'))) $r.J
    $st = ''; if ($sum.Count -eq 1) { $st = [IO.File]::ReadAllText($sum[0].FullName) }
    Check 'B1' ($pair[0] + ': сводка содержит SUMMARY, события и строки журнала; нет оценок «хорошо/плохо»') ($st -match 'SUMMARY markers_msgs count=2400' -and $st -match 'process_new' -and $st -match 'detection ACTIVE' -and -not ($st -match '(?i)\bOK\b|хорошо|плохо|норма')) $st
    Check 'B1' ($pair[0] + ': на экране видна сводка') ($r.Console -match 'markers_msgs' -and $r.Console -match 'Готово: замер закончен') ''
}
Reset-Fake; Set-Canned 'canned_measure.txt' "META initial_state connected=True armed=True mode=MANUAL`nREFUSED armed (дрон взведён: замер без взвода не начат, детектор не будился)`nBB_BENCH_DONE rc=3`n"
[IO.File]::WriteAllText((Join-Path $FakeDir 'measure_rc.txt'), '3')
$r = Run-Cmd '02a_zamer_bez_video.cmd' ''
$sumR = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_bez_video_*.summary.txt')
Check 'B2' '02a: дрон взведён (REFUSED armed): код 3, «ЗАМЕР НЕ НАЧАТ», сводка с причиной, сообщение владельцу' ($r.Code -eq 3 -and $sumR.Count -eq 1 -and [IO.File]::ReadAllText($sumR[0].FullName) -match 'ЗАМЕР НЕ НАЧАТ' -and $r.Console -match 'Замер НЕ начат') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_measure.txt' "META initial_state connected=False armed=False mode=MANUAL`nREFUSED fcu_not_connected (MAVROS не связан)`nBB_BENCH_DONE rc=3`n"; [IO.File]::WriteAllText((Join-Path $FakeDir 'measure_rc.txt'), '3')
$r = Run-Cmd '02b_zamer_s_video.cmd' ''
Check 'B2' '02b: нет связи MAVROS с FCU (REFUSED): код 3' ($r.Code -eq 3) ''
Reset-Fake 'nodone'
$r = Run-Cmd '02a_zamer_bez_video.cmd' ''
Check 'B3' '02a: замер оборвался (нет BB_BENCH_DONE rc=0): код 4, .FAILED, сводки «хорошо» нет' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_bez_video_*.FAILED.txt').Count -eq 1 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_bez_video_*.summary.txt').Count -eq 0) ('code=' + $r.Code)
Reset-Fake 'wrong_host'
$r = Run-Cmd '02a_zamer_bez_video.cmd' ''
Check 'B3' '02a: чужой дрон: код 4, замер не запускался' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ''
Reset-Fake
$r = Run-Cmd '02a_zamer_bez_video.cmd' '' '' 'OTHER-PC'
Check 'B3' '02a: чужой ПК: код 4, ssh не вызывался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''

# защита от перезаписи
$testDir = Join-Path $Run 'ow'; New-Item -ItemType Directory -Path $testDir | Out-Null
$exist = Join-Path $testDir 'x.txt'; [IO.File]::WriteAllText($exist, 'old')
$ps = ". '" + (Join-Path $Kit 'lib\bb_common.ps1') + "'; BB-NewOutFile '" + $testDir + "' 'x.txt'"
& powershell -NoProfile -ExecutionPolicy Bypass -Command $ps 2>&1 | Out-Null
Check 'B4' 'BB-NewOutFile не перезаписывает существующий файл: код 4, файл не изменён' ($LASTEXITCODE -eq 4 -and [IO.File]::ReadAllText($exist) -eq 'old') ('code=' + $LASTEXITCODE)

# ---------- C: 03 в руках ----------
Reset-Fake
$r = Run-Cmd '03_v_rukakh.cmd' "1`r`n150`r`n"
$sum3 = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_hand_center_*.summary.txt')
Check 'C1' '03: место 1, высота 150: код 0, метка hand_center, аргументы Pi 120 hand_center measure 1' ($r.Code -eq 0 -and $r.J -match '_ 120 hand_center measure 1\]' -and $sum3.Count -eq 1) ('code=' + $r.Code + ' ' + $r.J)
Check 'C1' '03: в сводке введённое вручную: место и высота камеры 150 см' ($sum3.Count -eq 1 -and ([IO.File]::ReadAllText($sum3[0].FullName)) -match 'ОПЕРАТОР \(введено вручную\): высота камеры над полом = 150 см') ''
foreach ($pair in @(@('2', 'hand_camera_over'), @('3', 'hand_back8'))) {
    Reset-Fake
    $r = Run-Cmd '03_v_rukakh.cmd' ($pair[0] + "`r`n98.5`r`n")
    Check 'C1' ('03: место ' + $pair[0] + ' даёт метку ' + $pair[1] + ', высота 98.5') ($r.Code -eq 0 -and $r.J -match ('_ 120 ' + $pair[1] + ' measure 1\]')) ('code=' + $r.Code)
}
Reset-Fake
$r = Run-Cmd '03_v_rukakh.cmd' "9`r`n150`r`n"
Check 'C2' '03: место 9: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$r = Run-Cmd '03_v_rukakh.cmd' "1`r`nabc`r`n"
Check 'C2' '03: высота «abc»: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
$r = Run-Cmd '03_v_rukakh.cmd' "1`r`n150; calc`r`n"
Check 'C2' '03: высота с лишними знаками «150; calc»: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)

# ---------- D: 04 вибрация ----------
Reset-Fake
$r = Run-Cmd '04_vibratsiya.cmd' "SAFE`r`n"
Check 'D1' '04: SAFE: код 0, аргументы Pi 180 vibration vibration 0 (детектор НЕ будится)' ($r.Code -eq 0 -and $r.J -match '_ 180 vibration vibration 0\]') ('code=' + $r.Code + ' ' + $r.J)
$r = Run-Cmd '04_vibratsiya.cmd' "no`r`n"
Check 'D1' '04: без SAFE: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$r = Run-Cmd '04_vibratsiya.cmd' "SAFE`r`n" '' 'OTHER-PC'
Check 'D1' '04: чужой ПК: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$c4 = [IO.File]::ReadAllText((Join-Path $Kit '04_vibratsiya.cmd'))
Check 'D2' '04: в тексте названы меры безопасности (винты сняты, выключатель, второй человек, причина 04.11 неизвестна, правило 3)' ($c4 -match 'винты СНЯТЫ' -and $c4 -match 'аварийном выключателе' -and $c4 -match 'второй человек' -and $c4 -match 'Причина рывка моторов 04\.11 неизвестна|Причина рывка 04\.11 НЕ известна' -and $c4 -match 'Правило 3') ''

# ---------- E: 07 взлёт (заготовка) ----------
$conf = Join-Path $SB 'takeoff.conf'
$gate = Join-Path $SB 'gates\TAKEOFF_APPROVED.txt'
$sha64 = ('ab' * 32); $drone64 = ('fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c')
function Set-TakeoffReady([string]$conf, [string]$gate, [string]$sha, [string]$outDirFor) {
    [IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py`nSCRIPT_SHA256=$sha`nDRONE_PY_SHA256=$drone64`nSCRIPT_ARGS=--height 0.8`n", $utf8n)
    [IO.File]::WriteAllText($gate, "ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-11 12:00`r`nСЛОВА_ВЛАДЕЛЬЦА=тест`r`nСКРИПТ_SHA256=$sha`r`nАРГУМЕНТЫ=--height 0.8`r`nСОЗДАЛ=чат 1`r`n", $utf8)
}
function New-ParamsReport([string]$dir, [string]$first, [int]$ageMin = 0) {
    $rp = Join-Path $dir 'params_x_report.txt'
    [IO.File]::WriteAllText($rp, $first + "`r`n", $utf8)
    (Get-Item $rp).LastWriteTime = (Get-Date).AddMinutes(-$ageMin)
    # S1 (чат 1, 21:50): 07 требует успешные 09 и 10 (последняя строка «# VERDICT OK»); по умолчанию кладём их, отдельные тесты S1 их портят
    foreach ($kn in 'install_check', 'mavros_check') { $cf = Join-Path $dir ($kn + '_20261111_080000.txt'); [IO.File]::WriteAllText($cf, ("INSTALL_ARCH aarch64`r`nBB_DONE`r`n# VERDICT OK`r`n"), $utf8); (Get-Item $cf).LastWriteTime = (Get-Date).AddMinutes(-5) }
}
$strict = '=== СОВПАДАЕТ: прочитано 1107 из 1107, отличий нет (из таблицы MAVROS 1107, из запасного потока 0); у 23 имён значения компонентов 1 и 125 в основе равны, по ним компонент 1 не подтверждён ==='
Reset-Fake
$r = Run-Cmd '07_vzlet_zagotovka.cmd' "NET`r`nTWO`r`nKILL`r`nYES`r`n"
Check 'E1' '07 в исходном виде заблокирован: код 4, к дрону не обращались; причины: нет TAKEOFF_APPROVED.txt, нет сверки (takeoff.conf заполнен, TBD уже нет)' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -notmatch 'TBD' -and $r.Console -match 'TAKEOFF_APPROVED' -and $r.Console -match 'нет сверки настроек') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
$r = Run-Cmd '07_vzlet_zagotovka.cmd' "NET`r`nTWO`r`nXXX`r`n"
Check 'E1' '07: третье подтверждение неверное: код 4 сразу в .cmd, PowerShell не запускался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -notmatch 'взлёт не разрешён') ('code=' + $r.Code)
$r = Run-Cmd '07_vzlet_zagotovka.cmd' "NET`r`nTWO`r`nKILL`r`nno`r`n"
Check 'E1' '07: на «YES» ответили no: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$r = Run-Cmd '07_vzlet_zagotovka.cmd' "NET`r`nTWO`r`nKILL`r`nYES`r`n" '' 'OTHER-PC'
Check 'E1' '07: чужой ПК: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$ps1 = Join-Path $SB 'run_07_takeoff.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -SafetyConfirmed 'NET' 2>&1 | Out-Null
Check 'E1' '07: ps1 без полного набора подтверждений не пускает (код 4)' ($LASTEXITCODE -eq 4) ('code=' + $LASTEXITCODE)

# полный проход в песочнице: все условия выполнены
Set-TakeoffReady $conf $gate $sha64 ''
Reset-Fake
[IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
$script:seq++; $outE = Join-Path $Run 'out_e_ok'; New-Item -ItemType Directory -Path $outE -Force | Out-Null
New-ParamsReport $outE $strict 0
# Run-Cmd создаёт свою out, поэтому запускаем вручную с нужной
function Run-07([string]$outDir, [string]$stdin = "NET`r`nTWO`r`nKILL`r`nYES`r`n", [string]$extra = '', [int]$stubRc = 0) {
    $env:BB_KIT_OUT = $outDir; $sl = Join-Path $Run ('stub_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.log'); $env:BB_STUB_LOG = $sl; $env:BB_STUB_RC = [string]$stubRc
    $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path $cl) { Remove-Item $cl }
    $inFile = Join-Path $Run ('in7_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $so = Join-Path $Run ('con7_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + (Join-Path $SB '07_vzlet_zagotovka.cmd') + '" ' + $extra + ' < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $sw.Stop()
    $calls = @(); if (Test-Path $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    $stub = @(); if (Test-Path $sl) { $stub = @(Get-Content -LiteralPath $sl -Encoding UTF8) }
    return @{ Code = $p.ExitCode; Calls = $calls; J = ($calls -join "`n"); Console = [IO.File]::ReadAllText($so); Stub = $stub; Secs = $sw.Elapsed.TotalSeconds; Out = $outDir }
}
$r = Run-07 $outE
$logs = @(Get-ChildItem -LiteralPath $outE -Filter 'takeoff_*.log')
Check 'E2' '07 при выполненных условиях: код 0; порядок вызовов ssh: имя дрона, sha256sum, проверка drone.py (только чтение), запуск скрипта (-tt) с окружением ROS, затем имя дрона и проверка «разоружён», затем имя дрона и чтение журнала Pi (только чтение)' ($r.Code -eq 0 -and $r.Calls.Count -eq 8 -and $r.Calls[7] -match '<b64:' -and $r.Calls[2] -match '<b64:' -and $r.J -match (Sha-Lf (Join-Path $Kit 'pi\journal_window.sh')) -and $r.Calls[1] -match 'sha256sum /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py' -and $r.Calls[3] -match '\[-tt\]' -and $r.Calls[3] -match 'cd /home/lb && python3 /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py --height 0\.8' -and $r.Calls[3] -match 'bumblebee-ros\.sh' -and $r.Calls[5] -match '<b64:') ('code=' + $r.Code + ' ' + $r.J)
Check 'E2' '07: отсчёт не меньше 10 секунд (прошло не меньше 9,5 с до запуска)' ($r.Secs -ge 9.5) ('секунд ' + [int]$r.Secs)
Check 'E2' '07: журнал takeoff_*.log создан, в нём разрешение, sha256 скрипта, сверка настроек до и вывод скрипта' ($logs.Count -eq 1 -and ([IO.File]::ReadAllText($logs[0].FullName)) -match 'sha256 ' + $sha64 -and ([IO.File]::ReadAllText($logs[0].FullName)) -match 'FAKE_FLIGHT_START' -and ([IO.File]::ReadAllText($logs[0].FullName)) -match 'СОВПАДАЕТ') ''
Check 'E2' '07: после полёта сразу вызван params_check r4 с -Stamp after_flight_ и BB_NO_PAUSE=1' (($r.Stub -join ' ') -match 'ARGS=-Stamp after_flight_\d{8}_\d{6}' -and ($r.Stub -join ' ') -match 'NO_PAUSE=1') ($r.Stub -join ' | ')
Check 'E2' '07: на экране красное предупреждение «ВЗЛЁТ … МОТОРЫ» и способы остановки' ($r.Console -match 'ВЗЛЁТ' -and $r.Console -match 'переключатель режима на пульте, CH8, Ctrl\+C') ''
# скрипт на Pi вернул ошибку
$outE2 = Join-Path $Run 'out_e_rc'; New-Item -ItemType Directory -Path $outE2 -Force | Out-Null; New-ParamsReport $outE2 $strict 0
[IO.File]::WriteAllText((Join-Path $FakeDir 'flight_rc.txt'), '1')
$r = Run-07 $outE2
Check 'E3' '07: скрипт на Pi завершился с кодом 1: код 1, настройки после всё равно читаются' ($r.Code -eq 1 -and ($r.Stub -join ' ') -match 'after_flight_') ('code=' + $r.Code)
# sha на Pi не совпал
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), (('cd' * 32) + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
$outE3 = Join-Path $Run 'out_e_sha'; New-Item -ItemType Directory -Path $outE3 -Force | Out-Null; New-ParamsReport $outE3 $strict 0
$r = Run-07 $outE3
Check 'E3' '07: sha256 скрипта на Pi не тот: код 4, скрипт полёта не запускался, отсчёта не было' ($r.Code -eq 4 -and -not ($r.J -match 'python3 /home/lb') -and $r.Secs -lt 9) ('code=' + $r.Code + ' secs=' + [int]$r.Secs)
Reset-Fake 'sha_missing'
$outE3b = Join-Path $Run 'out_e_nofile'; New-Item -ItemType Directory -Path $outE3b -Force | Out-Null; New-ParamsReport $outE3b $strict 0
$r = Run-07 $outE3b
Check 'E3' '07: скрипта на Pi нет: код 4, не запускался' ($r.Code -eq 4 -and -not ($r.J -match 'python3 /home/lb')) ''
# условия ps1
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
$outE4 = Join-Path $Run 'out_e_stale'; New-Item -ItemType Directory -Path $outE4 -Force | Out-Null; New-ParamsReport $outE4 $strict 45
$r = Run-07 $outE4
Check 'E4' '07: сверка старше 30 минут: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'старая') ''
$outE5 = Join-Path $Run 'out_e_stop'; New-Item -ItemType Directory -Path $outE5 -Force | Out-Null; New-ParamsReport $outE5 '=== СТОП до решения владельца (Ж6): отличий от утверждённого набора: 2 ==='
$r = Run-07 $outE5
Check 'E4' '07: сверка с отличиями (СТОП): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$outE6 = Join-Path $Run 'out_e_draft'; New-Item -ItemType Directory -Path $outE6 -Force | Out-Null; New-ParamsReport $outE6 '=== ЧЕРНОВИК, НЕ ДЛЯ ГЕЙТОВ (-AllowStreamFallback): отличий нет, прочитано 1107 из 1107, но 30 значений только из запасного потока (из таблицы MAVROS 1077) ==='
$r = Run-07 $outE6
Check 'E4' '07: черновой отчёт -AllowStreamFallback не годится: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
# разрешение с другим sha
Set-TakeoffReady $conf $gate $sha64 ''
[IO.File]::WriteAllText($gate, ("ШАГ=14`r`nВЗЛЁТ_РАЗРЕШИЛ=владелец`r`nДАТА=2026-11-11`r`nСЛОВА_ВЛАДЕЛЬЦА=тест`r`nСКРИПТ_SHA256=" + ('cd' * 32) + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
$outE7 = Join-Path $Run 'out_e_gate'; New-Item -ItemType Directory -Path $outE7 -Force | Out-Null; New-ParamsReport $outE7 $strict 0
$r = Run-07 $outE7
Check 'E4' '07: sha в TAKEOFF_APPROVED.txt не совпадает с takeoff.conf: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не совпадает') ''
Set-TakeoffReady $conf $gate $sha64 ''
[IO.File]::WriteAllText($gate, "ШАГ=13`r`nВЗЛЁТ_РАЗРЕШИЛ=помощник`r`nСОЗДАЛ=я`r`n", $utf8)
$r = Run-07 $outE7
Check 'E4' '07: разрешение не от чата 1 / не на шаг 14 / без даты и слов владельца: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
# опасные значения в takeoff.conf
Set-TakeoffReady $conf $gate $sha64 ''
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/../etc/x.py`nSCRIPT_SHA256=$sha64`nSCRIPT_ARGS=`n", $utf8n)
$r = Run-07 $outE7
Check 'E5' '07: путь скрипта с «..»: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/flight/x.py`nSCRIPT_SHA256=$sha64`nSCRIPT_ARGS=; reboot`n", $utf8n)
$r = Run-07 $outE7
Check 'E5' '07: SCRIPT_ARGS с «; reboot»: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Set-TakeoffReady $conf $gate $sha64 ''
function Run-Ps1Direct([string]$outDir, [string]$extraArgs) {
    $env:BB_KIT_OUT = $outDir
    $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path $cl) { Remove-Item $cl }
    $o = & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -SafetyConfirmed NET-TWO-KILL-YES @($extraArgs -split ' ') 2>&1 | Out-String
    $calls = @(); if (Test-Path $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    return @{ Code = $LASTEXITCODE; Calls = $calls; Console = $o }
}
$r = Run-Ps1Direct $outE7 '-CountdownSec 5'
Check 'E5' '07: ps1 с -CountdownSec 5 (меньше 10) отклоняется: код 4, к дрону не обращались, отсчёт не начинался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'от 10 до 300') ('code=' + $r.Code)
$r = Run-Ps1Direct $outE7 '-MaxParamsAgeMin 99999'
Check 'E5' '07: ps1 с -MaxParamsAgeMin 99999 отклоняется (возраст сверки только 0-30 минут): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'от 0 до 30') ('code=' + $r.Code + ' ' + $r.Console)
$r = Run-Ps1Direct $outE7 '-MaxParamsAgeMin NaN'
Check 'E5' '07: ps1 с -MaxParamsAgeMin NaN отклоняется (NaN не должен отключать проверку свежести): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'от 0 до 30') ('code=' + $r.Code + ' ' + $r.Console)
$r = Run-Ps1Direct $outE7 '-ConfPath C:\other\takeoff.conf'
Check 'E5' '07: ps1 с чужим -ConfPath отклоняется: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'свободный путь не принимается') ('code=' + $r.Code + ' ' + $r.Console)
# у .cmd нет параметров: лишнее в командной строке не пробрасывается
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
$outE8 = Join-Path $Run 'out_e_noargs'; New-Item -ItemType Directory -Path $outE8 -Force | Out-Null; New-ParamsReport $outE8 $strict 45
$r = Run-07 $outE8 "NET`r`nTWO`r`nKILL`r`nYES`r`n" '-MaxParamsAgeMin 99999 -CountdownSec 5'
Check 'E6' '07: параметры в командной строке .cmd не пробрасываются: старая сверка (45 мин) всё равно отклоняет, код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'старая') ('code=' + $r.Code)
Check 'E6' '07: в тексте .cmd нет %* и %1 (ничего из командной строки не передаётся)' (-not (([IO.File]::ReadAllText((Join-Path $Kit '07_vzlet_zagotovka.cmd'))) -match '%\*|%1')) ''
$outE9 = Join-Path $Run 'out_e_noargs_ok'; New-Item -ItemType Directory -Path $outE9 -Force | Out-Null; New-ParamsReport $outE9 $strict 0
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
$r = Run-07 $outE9 "NET`r`nTWO`r`nKILL`r`nYES`r`n" '-CountdownSec 5'
Check 'E6' '07: лишний -CountdownSec 5 в командной строке не сокращает отсчёт (прошло не меньше 9,5 с)' ($r.Code -eq 0 -and $r.Secs -ge 9.5) ('code=' + $r.Code + ' secs=' + [int]$r.Secs)
# аргументы скрипта привязаны к разрешению
Set-TakeoffReady $conf $gate $sha64 ''
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py`nSCRIPT_SHA256=$sha64`nDRONE_PY_SHA256=$drone64`nSCRIPT_ARGS=--height 1.5`n", $utf8n)
$r = Run-07 $outE7
Check 'E7' '07: SCRIPT_ARGS в takeoff.conf изменены после разрешения (1.5 вместо 0.8): код 4, к дрону не обращались, причина названа' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не равны АРГУМЕНТЫ') ('code=' + $r.Code + ' ' + $r.Console)
Set-TakeoffReady $conf $gate $sha64 ''
[IO.File]::WriteAllText($gate, (([IO.File]::ReadAllLines($gate, [Text.Encoding]::UTF8) | Where-Object { $_ -notmatch '^АРГУМЕНТЫ=' }) -join "`r`n") + "`r`n", $utf8)
$r = Run-07 $outE7
Check 'E7' '07: в разрешении нет строки АРГУМЕНТЫ=: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'нет строки АРГУМЕНТЫ') ('code=' + $r.Code)
Set-TakeoffReady $conf $gate $sha64 ''
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py`nSCRIPT_SHA256=$sha64`nDRONE_PY_SHA256=$drone64`n", $utf8n)
$r = Run-07 $outE7
Check 'E7' '07: в разрешении АРГУМЕНТЫ=--height 0.8, а в takeoff.conf аргументов нет: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Set-TakeoffReady $conf $gate $sha64 ''
# после полёта читаем настройки только при разоружённом дроне
function Run-After([string]$armText, [int]$armRc = 0, [bool]$noCanned = $false) {
    Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
    if ($noCanned) { Remove-Item (Join-Path $FakeDir 'canned_arm.txt') } else { Set-Canned 'canned_arm.txt' $armText }
    [IO.File]::WriteAllText((Join-Path $FakeDir 'arm_rc.txt'), [string]$armRc)
    $od = Join-Path $Run ('out_e_arm_' + [guid]::NewGuid().ToString('N').Substring(0, 6)); New-Item -ItemType Directory -Path $od -Force | Out-Null; New-ParamsReport $od $strict 0
    return (Run-07 $od)
}
$r = Run-After "BB_ARM connected=true armed=true`nBB_ARM_STATE_DONE`n"
Check 'E8' '07: после полёта дрон ВЗВЕДЁН (armed=true): код 5, params_check НЕ вызывался, на экране «ВЗВЕДЁН» и что делать' ($r.Code -eq 5 -and $r.Stub.Count -eq 0 -and $r.Console -match 'ВЗВЕДЁН' -and $r.Console -match 'Настройки после полёта НЕ читаю') ('code=' + $r.Code + ' stub=' + ($r.Stub -join '|'))
Check 'E8' '07: при armed=true журнал Pi не читается (нет вызова journal_window.sh, нет файла takeoff_*_journal.txt)' (-not ($r.J -match (Sha-Lf (Join-Path $Kit 'pi\journal_window.sh'))) -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'takeoff_*_journal*.txt').Count -eq 0) ''
$r = Run-After "BB_ARM connected=true armed=?`nBB_ARM_STATE_DONE`n"
Check 'E8' '07: состояние «взведён» не прочитано (armed=?): код 5, params_check НЕ вызывался' ($r.Code -eq 5 -and $r.Stub.Count -eq 0) ('code=' + $r.Code + ' stub=' + ($r.Stub -join '|'))
$r = Run-After "BB_ARM connected=false armed=false`nBB_ARM_STATE_DONE`n"
Check 'E8' '07: нет связи с контроллером (connected=false armed=false): код 5, params_check НЕ вызывался' ($r.Code -eq 5 -and $r.Stub.Count -eq 0) ('code=' + $r.Code)
$r = Run-After "BB_ARM connected=true armed=false`n" 3
Check 'E8' '07: проверка не дошла до конца (нет BB_ARM_STATE_DONE, код ssh 3): код 5, params_check НЕ вызывался' ($r.Code -eq 5 -and $r.Stub.Count -eq 0) ('code=' + $r.Code)
$r = Run-After '' 0 $true
Check 'E8' '07: проверка вернула пустой вывод: код 5, params_check НЕ вызывался' ($r.Code -eq 5 -and $r.Stub.Count -eq 0) ('code=' + $r.Code)
$r = Run-After "BB_ARM connected=true armed=false`nBB_ARM_STATE_DONE`n"
Check 'E8' '07: после полёта дрон разоружён: код 0, params_check вызван' ($r.Code -eq 0 -and ($r.Stub -join ' ') -match 'after_flight_') ('code=' + $r.Code + ' stub=' + ($r.Stub -join '|'))
$jf = @(Get-ChildItem -LiteralPath $r.Out -Filter 'takeoff_*_journal.txt')
Check 'E9' '07: при разоружённом дроне журнал Pi прочитан только чтением: файл takeoff_*_journal.txt с BB_JOURNAL_DONE, настройки тоже прочитаны' ($jf.Count -eq 1 -and ([IO.File]::ReadAllText($jf[0].FullName)) -match 'BB_JOURNAL_DONE rc=0' -and ($r.Stub -join ' ') -match 'after_flight_') ('files=' + $jf.Count)
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py')); [IO.File]::WriteAllText((Join-Path $FakeDir 'journal_rc.txt'), '3')
$odJ = Join-Path $Run 'out_e_jfail'; New-Item -ItemType Directory -Path $odJ -Force | Out-Null; New-ParamsReport $odJ $strict 0
$r = Run-07 $odJ
Check 'E9' '07: журнал Pi не прочитан (код ssh 3): код 0, файл .FAILED, сообщение, настройки после полёта всё равно прочитаны' ($r.Code -eq 0 -and @(Get-ChildItem -LiteralPath $odJ -Filter 'takeoff_*_journal.FAILED.txt').Count -eq 1 -and $r.Console -match 'Журнал Pi не прочитан' -and ($r.Stub -join ' ') -match 'after_flight_') ('code=' + $r.Code)

# ---------- R: набор r2 (08 батарея, версии, коды пустых мест) ----------
Reset-Fake
$r = Run-Cmd '08_batareya.cmd' ''
$bsum = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_battery_bat_*.summary.txt'); $braw = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_battery_bat_*.raw.txt')
Check 'R1' '08: код 0, сводка и сырой файл созданы' ($r.Code -eq 0 -and $bsum.Count -eq 1 -and $braw.Count -eq 1) ('code=' + $r.Code)
Check 'R1' '08: 2 вызова ssh (имя дрона, battery_check.sh), аргумент 30; скрипт = pi\battery_check.sh (SHA256, LF)' ($r.Calls.Count -eq 2 -and $r.J -match '_ 30\]' -and $r.J -match (Sha-Lf (Join-Path $Kit 'pi\battery_check.sh'))) $r.J
$bst = ''; if ($bsum.Count -eq 1) { $bst = [IO.File]::ReadAllText($bsum[0].FullName) }
Check 'R1' '08: сводка содержит напряжение, BAT1_N_CELLS, BAT1_V_EMPTY, BAT1_V_CHARGED; нет оценок хорошо/плохо' ($bst -match 'voltage_v min=16\.10' -and $bst -match 'PARAM BAT1_N_CELLS i 4' -and $bst -match 'PARAM BAT1_V_EMPTY d 3\.5' -and $bst -match 'PARAM BAT1_V_CHARGED d 4\.05' -and -not ($bst -match '(?i)\bOK\b|хорошо|плохо|норма')) $bst
Check 'R1' '08: на экране видна сводка и «Готово: батарея прочитана»' ($r.Console -match 'battery_msgs' -and $r.Console -match 'Готово: батарея прочитана') ''
Reset-Fake 'nodone'
$r = Run-Cmd '08_batareya.cmd' ''
Check 'R2' '08: скрипт оборвался (нет BB_BATTERY_DONE): код 4, файл .FAILED, сводки нет' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_battery_*.FAILED.txt').Count -eq 1 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'bench_battery_*.summary.txt').Count -eq 0) ('code=' + $r.Code)
Reset-Fake 'wrong_host'
$r = Run-Cmd '08_batareya.cmd' ''
Check 'R2' '08: чужой дрон: код 4, чтение не делалось (один вызов, имя дрона)' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake
$r = Run-Cmd '08_batareya.cmd' '' '' 'OTHER-PC'
Check 'R2' '08: чужой ПК: код 4, ssh не вызывался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Check 'R3' '01: сводка состояния Pi показывает версию OpenCV (строка PI_OPENCV в скрипте pi_state.sh есть, python3 -B, только чтение)' ((([IO.File]::ReadAllText((Join-Path $Kit 'pi\pi_state.sh'))) -match 'PI_OPENCV \$\(timeout 30 python3 -B -c .import cv2; print\(cv2\.__version__\)') -and (([IO.File]::ReadAllText((Join-Path $Kit 'run_01_snapshot.ps1'))) -match 'PI_OPENCV')) ''

# ---------- R9/R10: 09 сверка install, 10 версия MAVROS (решение чата 1, 19:19) ----------
Reset-Fake
$r = Run-Cmd '09_sverka_install.cmd' ''
$gen = @(Get-ChildItem -LiteralPath $r.Out -Filter 'install_check_*.generated.sh'); $ir = @(Get-ChildItem -LiteralPath $r.Out -Filter 'install_check_*.txt' | Where-Object { $_.Name -notmatch 'generated|err|FAILED' })
Check 'R4' '09: python, C++ исходники и бинарники совпали: код 0, файл ответа создан, 2 вызова ssh (имя дрона, сверка)' ($r.Code -eq 0 -and $ir.Count -eq 1 -and $r.Calls.Count -eq 2 -and $r.Console -match 'install на Pi совпал') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
$gtxt = ''; if ($gen.Count -eq 1) { $gtxt = [IO.File]::ReadAllText($gen[0].FullName) }
$listLines = @([IO.File]::ReadAllLines((Join-Path $Kit 'image_r2j\INSTALL_SHA256_r2j.txt')) | Where-Object { $_ -match '^[0-9a-f]{64}\s' })
$pyLines = @($listLines | Where-Object { $_ -match '\.py$' }); $binNames = @($listLines | Where-Object { $_ -notmatch '\.py$' } | ForEach-Object { ($_ -split '\s+')[1] })
$cppLines = @([IO.File]::ReadAllLines((Join-Path $Kit 'image_r2j\CPP_SOURCES_r2j.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' })
Check 'R4' '09: на Pi уходит pi\install_check.sh с тремя списками: 10 python-узлов (sha256 и имя), 16 строк (11 C++ и файлов сборки, 5 скриптов полёта) (sha256, путь, флаг; r11: у flight_marker.py и flight_marker_loop.py sha256 r2j,real - ровно 2 строки), 6 бинарных узлов (только имена); строк-заглушек нет' ($gen.Count -eq 1 -and $pyLines.Count -eq 10 -and $cppLines.Count -eq 16 -and $binNames.Count -eq 6 -and @($pyLines | Where-Object { $gtxt.Contains(($_ -replace '\s+', '  ')) }).Count -eq 10 -and @($cppLines | Where-Object { $f = $_.Split("`t"); $gtxt -match ('(?m)^' + $f[0] + '(,[0-9a-f]{64})?  ' + [regex]::Escape($f[1]) + '  ' + [regex]::Escape($f[2]) + '$') }).Count -eq 16 -and ([regex]::Matches($gtxt, '(?m)^[0-9a-f]{64},[0-9a-f]{64}  ')).Count -eq 2 -and @($binNames | Where-Object { $gtxt -match ('(?m)^' + [regex]::Escape($_) + '\s*$') }).Count -eq 6 -and -not ($gtxt -match '(?m)^#@@(LIST|CPP|BINS|RT)@@\s*$') -and $gtxt.Contains('BB_INSTALL_MARK')) ('gen=' + $gen.Count + ' py=' + $pyLines.Count + ' cpp=' + $cppLines.Count + ' bin=' + $binNames.Count)
Check 'R4' '09: бинарные узлы НЕ сверяются по sha256 с r2j: их суммы в скрипт не передаются (ни одна сумма x86-бинарника r2j в скрипте не стоит)' (@($listLines | Where-Object { $_ -notmatch '\.py$' } | Where-Object { $gtxt.Contains(($_ -split '\s+')[0]) }).Count -eq 0) ''
Check 'R4' '09: в списке C++ ровно 5 файлов с флагом R (CMakeLists.txt, package.xml, script_lease.h, simple_offboard.cpp, state_link.h): r2j меняет C++ против образа на дроне' (@($cppLines | Where-Object { $_.Split("`t")[2] -eq 'R' }).Count -eq 5 -and ($cppLines -join ' ') -match 'state_link\.h\tR' -and ($cppLines -join ' ') -match 'simple_offboard\.cpp\tR' -and ($cppLines -join ' ') -match 'script_lease\.h\tR') ''
$rtLines = @([IO.File]::ReadAllLines((Join-Path $Kit 'image_r2j\RUNTIME_PY_r2j.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' })
Check 'R4' '09 (S2, чат 1 21:50): в скрипт для Pi вставлены 8 строк «sha256  вид  путь»: 7 launch-файлов пакета и fcu_detect.py (исправленный 5932a00a…, путь ros2_ws/src/bumblebee/scripts/fcu_detect.py), заглушки #@@RT@@ нет' ($rtLines.Count -eq 8 -and @($rtLines | Where-Object { $f = $_.Split("`t"); $gtxt.Contains($f[0] + '  ' + $f[1] + '  ' + $f[2]) }).Count -eq 8 -and $gtxt.Contains('5932a00afc79e421a7bb26a7e84564cf106afdcbc009642c7e872ab86b839bf5  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py') -and -not $gtxt.Contains('ee174fd1a610eacc9bdcf1a995379f068200abc49045774dbeec088982ed9f00') -and @($rtLines | Where-Object { $_ -match "`tLAUNCH`t" }).Count -eq 7) ''
$irTxt = ''; if ($ir.Count -eq 1) { $irTxt = ([IO.File]::ReadAllText($ir[0].FullName)).TrimEnd() }
Check 'R4' '09 (S1, чат 1 21:50): при успехе в конец файла сверки дописано «# VERDICT OK» (его проверяет 07)' ($irTxt -match '# VERDICT OK$') $irTxt
foreach ($case in @(@('launch-файл отличается', (New-InstallCanned 10 0 0 0 0 0 0 0 1 0)), @('fcu_detect.py нет или прежний', (New-InstallCanned 10 0 0 0 0 0 0 0 0 1)), @('python отличается', (New-InstallCanned 9 1 0 0)), @('python нет', (New-InstallCanned 9 0 1 0)), @('нет префикса', (New-InstallCanned 0 0 0 1)), @('python меньше списка', (New-InstallCanned 9 0 0 0)), @('C++ исходник отличается', (New-InstallCanned 10 0 0 0 1 0 0 0)), @('C++ исходника нет', (New-InstallCanned 10 0 0 0 0 1 0 0)), @('бинарника нет', (New-InstallCanned 10 0 0 0 0 0 1 0)), @('бинарник старше исходников', (New-InstallCanned 10 0 0 0 0 0 0 1)))) {
    Reset-Fake; Set-Canned 'canned_install.txt' $case[1]
    $r = Run-Cmd '09_sverka_install.cmd' ''
    $irn = @(Get-ChildItem -LiteralPath $r.Out -Filter 'install_check_*.txt' | Where-Object { $_.Name -notmatch 'generated|err|FAILED' }); $irnTxt = ''; if ($irn.Count -eq 1) { $irnTxt = ([IO.File]::ReadAllText($irn[0].FullName)).TrimEnd() }
    Check 'R5' ('09: ответ «' + $case[0] + '»: код 5 и красное СТОП, ничего не запускать; в файле последней строкой «# VERDICT NOT_OK»') ($r.Code -eq 5 -and $r.Console -match 'СТОП' -and $irnTxt -match '# VERDICT NOT_OK$') ('code=' + $r.Code)
}Reset-Fake 'nodone'
$r = Run-Cmd '09_sverka_install.cmd' ''
Check 'R5' '09: сверка оборвалась (нет BB_INSTALL_CHECK_DONE): код 4, файл .FAILED' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'install_check_*.FAILED.txt').Count -eq 1) ('code=' + $r.Code)
Reset-Fake 'wrong_host'
$r = Run-Cmd '09_sverka_install.cmd' ''
Check 'R5' '09: чужой дрон: код 4, сверка не делалась (один вызов)' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ('code=' + $r.Code)
Reset-Fake
$r = Run-Cmd '09_sverka_install.cmd' '' '' 'OTHER-PC'
Check 'R5' '09: чужой ПК: код 4, ssh не вызывался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake
$r = Run-Cmd '10_mavros_versiya.cmd' ''
$mr = @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_check_*.txt' | Where-Object { $_.Name -notmatch 'generated|err|FAILED' }); $mg = @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_check_*.generated.sh')
$mgt = ''; if ($mg.Count -eq 1) { $mgt = [IO.File]::ReadAllText($mg[0].FullName) }
Check 'R6' '10: коммит d63a236, 5 исходников, активен MAVROS из bench_ws: код 0' ($r.Code -eq 0 -and $mr.Count -eq 1 -and $r.Calls.Count -eq 2 -and $r.Console -match 'MAVROS bp02 подтверждён') ('code=' + $r.Code)
$srcLines = @([IO.File]::ReadAllLines((Join-Path $Kit 'image_r2j\mavros_bp02_sources.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' })
Check 'R6' '10: на Pi уходит pi\mavros_check.sh с 5 строками «sha256  путь» из mavros_bp02_sources.tsv (колонка bp02), заглушки нет' ($mg.Count -eq 1 -and $srcLines.Count -eq 5 -and @($srcLines | Where-Object { $f = $_.Split("`t"); $mgt.Contains($f[2] + '  ' + $f[0]) }).Count -eq 5 -and -not ($mgt -match '(?m)^#@@LIST@@\s*$') -and $mgt.Contains('BB_MAVROS_MARK')) ''
$mrTxt = ''; if ($mr.Count -eq 1) { $mrTxt = ([IO.File]::ReadAllText($mr[0].FullName)).TrimEnd() }
Check 'R6' '10 (S1, чат 1 21:50): при успехе в конец файла дописано «# VERDICT OK» (его проверяет 07)' ($mrTxt -match '# VERDICT OK$') $mrTxt
foreach ($case in @(@('другой коммит', (New-MavrosCanned '/home/lb/bench_ws/mavros/install/mavros' ('a' * 40) 5), 'коммит исходников'), @('4 из 5 исходников', (New-MavrosCanned '/home/lb/bench_ws/mavros/install/mavros' $bp02 4), 'совпало 4 из 5'), @('активен apt', (New-MavrosCanned '/opt/ros/jazzy' $bp02 5), 'не из bench_ws'))) {
    Reset-Fake; Set-Canned 'canned_mavros.txt' $case[1]
    $r = Run-Cmd '10_mavros_versiya.cmd' ''
    $mrn = @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_check_*.txt' | Where-Object { $_.Name -notmatch 'generated|err|FAILED' }); $mrnTxt = ''; if ($mrn.Count -eq 1) { $mrnTxt = ([IO.File]::ReadAllText($mrn[0].FullName)).TrimEnd() }
    Check 'R7' ('10: «' + $case[0] + '»: код 5, СТОП, причина названа; в файле последней строкой «# VERDICT NOT_OK»') ($r.Code -eq 5 -and $r.Console -match 'СТОП' -and $r.Console -match $case[2] -and $mrnTxt -match '# VERDICT NOT_OK$') ('code=' + $r.Code + ' ' + $r.Console)
}
Reset-Fake 'nodone'
$r = Run-Cmd '10_mavros_versiya.cmd' ''
Check 'R7' '10: чтение оборвалось: код 4, файл .FAILED' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_check_*.FAILED.txt').Count -eq 1) ('code=' + $r.Code)
Check 'R7' 'check_gates и список: MAVROS_ARM64_SHA256SUMS.txt в наборе нет (это был тестовый образец m5, MAVROS_ORIGIN.md)' (-not (Test-Path (Join-Path $Kit 'image_r2j\MAVROS_ARM64_SHA256SUMS.txt')) -and (Test-Path (Join-Path $Kit 'image_r2j\MAVROS_ORIGIN.md'))) ''

# ---------- R11/R12: заготовки сборки MAVROS bp02 на Pi (11) и переноса в сторону (12); Claude их не запускает, тесты с поддельными ssh и scp ----------
$tokBuild = "BATTERY`r`nSERVICE`r`nBUILD`r`n"
$MBkit = Join-Path $SB 'image_r2j\mavros_build\pi_kit'
Reset-Fake
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
$apt = @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_apt_state_*.txt'); $stgd = @(Get-ChildItem -LiteralPath $r.Out -Directory -Filter 'stage_mavros_*'); $blog = @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_build_*.log')
Check 'R11' '11: три подтверждения, проверка Pi пройдена: код 0; порядок: имя дрона, проверка (чтение), mkdir, scp, M1, M2' ($r.Code -eq 0 -and $r.Calls.Count -eq 6 -and $r.Calls[1] -match '<b64:' -and $r.Calls[2] -match 'mkdir -p /home/lb/bench_ws/incoming' -and $r.Calls[3] -match 'SCP' -and $r.Calls[4] -match 'm1_unpack\.sh' -and $r.Calls[5] -match '\[-tt\]' -and $r.Calls[5] -match 'm2_build\.sh 1') ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.J)
Check 'R11' '11: состояние apt «до» записано в out\mavros_apt_state_*.txt; журнал сборки с RC3M_M2_OK; папка передачи stage_mavros_*\rc3_mavros содержит 16 файлов набора rc3' ($apt.Count -eq 1 -and ([IO.File]::ReadAllText($apt[0].FullName)) -match 'apt_state ros-jazzy-mavros=2\.14\.0' -and $blog.Count -eq 1 -and ([IO.File]::ReadAllText($blog[0].FullName)) -match 'RC3M_M2_OK' -and $stgd.Count -eq 1 -and @(Get-ChildItem -LiteralPath (Join-Path $stgd[0].FullName 'rc3_mavros') -File).Count -eq 16) ('apt=' + $apt.Count + ' log=' + $blog.Count)
Check 'R11' '11: на экране оценка времени 7-10 минут, «не закрывайте окно», и что apt, start_bumblebee.sh, PX4 не менялись' ($r.Console -match '7-10 минут' -and $r.Console -match 'Не закрывайте окно' -and $r.Console -match 'start_bumblebee\.sh и параметры PX4 не менялись') ''
$mcode = ([IO.File]::ReadAllText((Join-Path $Kit 'run_mavros_build.ps1')) -split "`n" | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n"
Check 'R11' 'код run_mavros_build.ps1: нет sudo, apt, systemctl, start_bumblebee, set_mode, arming, param set (службу и пароль не трогает; подключение MAVROS не делает)' (-not ($mcode -match '(?i)sudo\s|apt-get|apt\s+install|systemctl|reboot|set_mode|arming|param set|\.bashrc|/opt/ros/jazzy/lib')) ''
foreach ($bad in @("BATTERY`r`nSERVICE`r`nXXX`r`n", "BATTERY`r`nNO`r`nBUILD`r`n", "NO`r`nSERVICE`r`nBUILD`r`n")) {
    Reset-Fake; $r = Run-Cmd '11_sborka_mavros_bp02.cmd' $bad
    Check 'R11' ('11: неверное подтверждение (' + ($bad -replace "`r`n", '/').Trim('/') + '): код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
}
Reset-Fake; $r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild '' 'OTHER-PC'
Check 'R11' '11: чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'canned_mbpre.txt' "MBPRE service_bumblebee active`nMBPRE absent /home/lb/bench_ws/mavros`nMBPRE apt_state ros-jazzy-mavros=2.14.0-1noble`nBB_MBPRE_RESULT STOP служба_bumblebee_активна(остановите_сами_sudo_systemctl_stop_bumblebee)`nBB_MBPRE_DONE`n"
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: служба bumblebee активна (проверка Pi сказала STOP): код 4, ничего не записано на дрон (только имя дрона и проверка), apt-состояние всё равно сохранено' ($r.Code -eq 4 -and $r.Calls.Count -eq 2 -and $r.J -notmatch 'mkdir' -and $r.J -notmatch 'SCP' -and $r.J -notmatch 'm1_unpack' -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'mavros_apt_state_*.txt').Count -eq 1 -and $r.Console -match 'сборку начинать нельзя') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; Set-Canned 'canned_mbpre.txt' "MBPRE exists /home/lb/bench_ws/mavros`nBB_MBPRE_RESULT STOP уже_есть_mavros`nBB_MBPRE_DONE`n"
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: ~/bench_ws/mavros уже есть: STOP, ничего не перезаписывается (код 4, без mkdir и scp)' ($r.Code -eq 4 -and $r.J -notmatch 'mkdir' -and $r.J -notmatch 'SCP') ('code=' + $r.Code)
Reset-Fake 'wrong_host'
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: чужой дрон: код 4, проверка и копирование не делались (один вызов)' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ('code=' + $r.Code)
Reset-Fake 'm1_fail'
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: M1 не дошёл до RC3M_M1_OK: код 6, сборка (M2) не запускалась, подсказка про 12_otkat_mavros_bp02.cmd' ($r.Code -eq 6 -and $r.J -notmatch 'm2_build' -and $r.Console -match '12_otkat_mavros_bp02') ('code=' + $r.Code)
Reset-Fake 'm2_fail'
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: M2 не дошёл до RC3M_M2_OK: код 6, «Скажите Claude»' ($r.Code -eq 6 -and $r.Console -match 'M2 не дошёл до RC3M_M2_OK') ('code=' + $r.Code)
Reset-Fake 'mkdir_fail'
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: ~/bench_ws/incoming не подготовлена: код 4, scp не было' ($r.Code -eq 4 -and $r.J -notmatch 'SCP') ('code=' + $r.Code)
# набор rc3 подменён: к дрону не обращаемся
Reset-Fake
Add-Content -LiteralPath (Join-Path $MBkit 'm2_build.sh') -Value '# tampered' -Encoding UTF8
$r = Run-Cmd '11_sborka_mavros_bp02.cmd' $tokBuild
Check 'R12' '11: файл набора rc3 изменён (m2_build.sh): код 4 ДО обращения к дрону, названа несходящаяся сумма' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не сходится с TRANSFER_SHA256SUMS') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
$mbReal = Join-Path $Kit 'image_r2j\mavros_build\pi_kit'
$tl = @([IO.File]::ReadAllLines((Join-Path $mbReal 'TRANSFER_SHA256SUMS.txt')) | Where-Object { $_ -match '^[0-9a-f]{64}\s' })
$badSum = @($tl | Where-Object { $m = [regex]::Match($_, '^([0-9a-f]{64})\s+(\S+)$'); (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $mbReal $m.Groups[2].Value)).Hash.ToLower() -ne $m.Groups[1].Value })
Check 'R13' 'настоящий набор rc3 в image_r2j\mavros_build\pi_kit: 15 файлов, все суммы сходятся с TRANSFER_SHA256SUMS (сумма самого списка 8bb42477…), EXPECTED_SRC: backport-02, d63a236' ($tl.Count -eq 15 -and $badSum.Count -eq 0 -and (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $mbReal 'TRANSFER_SHA256SUMS.txt')).Hash.ToLower() -eq '8bb424779406342b776f62fbc71bbb0bd59c5772a77e8f19e400d0e38b22e363' -and ([IO.File]::ReadAllText((Join-Path $mbReal 'EXPECTED_SRC.txt'))) -match 'commit=d63a23674dd80ff4525829ca4bd716bbcc773111') ('files=' + $tl.Count + ' bad=' + $badSum.Count)
Reset-Fake
$r = Run-Cmd '12_otkat_mavros_bp02.cmd' "ASIDE`r`n"
Check 'R13' '12: ASIDE: код 0; порядок: имя дрона, перенос (mv, без rm), сообщение «ничего не удалено»' ($r.Code -eq 0 -and $r.Calls.Count -eq 2 -and $r.Calls[1] -match '<b64:' -and $r.Console -match 'ничего не удалено') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; $r = Run-Cmd '12_otkat_mavros_bp02.cmd' "NO`r`n"
Check 'R13' '12: без ASIDE: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'canned_aside.txt' "STOP: start_bumblebee.sh подключает оверлей bench_ws/mavros: сначала отключить подключение, ничего не перенесено`n"; [IO.File]::WriteAllText((Join-Path $FakeDir 'aside_rc.txt'), '1')
$r = Run-Cmd '12_otkat_mavros_bp02.cmd' "ASIDE`r`n"
Check 'R13' '12: Pi отказал (оверлей подключён, код 1, нет BB_ASIDE_DONE): код 4, «Ничего не удалялось»' ($r.Code -eq 4 -and $r.Console -match 'Ничего не удалялось') ('code=' + $r.Code)
Reset-Fake; $r = Run-Cmd '12_otkat_mavros_bp02.cmd' "ASIDE`r`n" '' 'OTHER-PC'
Check 'R13' '12: чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''

# ---------- R14-R18: шаги 13 (сборка bumblebee r2j), 14 (в сторону), 15 (отпечатки), 16 (подключение оверлея), 17 (отключение); Claude их не запускает ----------
function Run-In([string]$cmdName, [string]$outDir, [string]$stdin, [string]$pc = $realPc) {
    $env:BB_KIT_OUT = $outDir; $sl = Join-Path $Run ('stub_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.log'); $env:BB_STUB_LOG = $sl; $env:BB_STUB_RC = '0'
    $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path $cl) { Remove-Item $cl }
    $inFile = Join-Path $Run ('inx_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $so = Join-Path $Run ('conx_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt')
    $env:COMPUTERNAME = $pc
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + (Join-Path $SB $cmdName) + '" < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $env:COMPUTERNAME = $realPc
    $calls = @(); if (Test-Path $cl) { $calls = @(Get-Content -LiteralPath $cl -Encoding UTF8) }
    return @{ Code = $p.ExitCode; Calls = $calls; J = ($calls -join "`n"); Console = [IO.File]::ReadAllText($so); Out = $outDir }
}
function New-Out { $o = Join-Path $Run ('out_x_' + [guid]::NewGuid().ToString('N').Substring(0, 6)); New-Item -ItemType Directory -Path $o -Force | Out-Null; return $o }
$tok13 = "BATTERY`r`nSERVICE`r`nBUILD`r`n"
Reset-Fake
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
$gp = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bb_precheck_*.generated.sh'); $gb = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bb_build_*.generated.sh'); $bl = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bb_build_*.log'); $bs = @(Get-ChildItem -LiteralPath $r.Out -Filter 'bb_state_before_*.txt')
Check 'R14' '13: три подтверждения, проверка Pi пройдена, сборка до BB_BBBUILD_OK: код 0; 3 вызова ssh (имя дрона, проверка чтением, сборка -tt); копирования на дрон (scp) нет' ($r.Code -eq 0 -and $r.Calls.Count -eq 3 -and $r.Calls[1] -match '<b64:' -and $r.Calls[2] -match '\[-tt\]' -and $r.J -notmatch 'SCP' -and $r.Console -match 'bumblebee r2j собран') ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.J)
$cppLines = @([IO.File]::ReadAllLines((Join-Path $Kit 'image_r2j\CPP_SOURCES_r2j.tsv')) | Where-Object { $_ -notmatch '^#' -and $_.Trim() -ne '' })
$gtB = ''; if ($gb.Count -eq 1) { $gtB = [IO.File]::ReadAllText($gb[0].FullName) }; $gtP = ''; if ($gp.Count -eq 1) { $gtP = [IO.File]::ReadAllText($gp[0].FullName) }
Check 'R14' '13: на Pi уходят pi\bb_build_precheck.sh и pi\bb_build.sh с 16 строками «sha256  путь  флаг» из CPP_SOURCES_r2j.tsv, строк-заглушек нет; состояние «до» и журнал сборки записаны в out' ($gp.Count -eq 1 -and $gb.Count -eq 1 -and $cppLines.Count -eq 16 -and @($cppLines | Where-Object { $f = $_.Split("`t"); $gtB.Contains($f[0] + '  ' + $f[1] + '  ' + $f[2]) -and $gtP.Contains($f[0] + '  ' + $f[1] + '  ' + $f[2]) }).Count -eq 16 -and -not ($gtB -match '(?m)^#@@CPP@@\s*$') -and -not ($gtP -match '(?m)^#@@CPP@@\s*$') -and $gtB.Contains('BB_BBBUILD_MARK') -and $bl.Count -eq 1 -and ([IO.File]::ReadAllText($bl[0].FullName)) -match 'BB_BBBUILD_OK' -and $bs.Count -eq 1) ('gp=' + $gp.Count + ' gb=' + $gb.Count)
$hovSha = (@([IO.File]::ReadAllLines((Join-Path $Kit 'image_r2j\required_shas.txt')) | Where-Object { $_ -match '^HOVER_R6_SHA256=' }) | Select-Object -First 1) -replace '^HOVER_R6_SHA256=', ''
Check 'R14' '13 (r3, замечание проверки): в скрипты precheck и сборки подставлен sha256 hover r6 (a11b195c…, из required_shas.txt) отдельной строкой, заглушки #@@HOVER@@ нет' ($hovSha -match '^[0-9a-f]{64}$' -and $hovSha.StartsWith('a11b195c') -and $gtB -match ('(?m)^' + $hovSha + '\s*$') -and $gtP -match ('(?m)^' + $hovSha + '\s*$') -and -not ($gtB -match '(?m)^#@@HOVER@@\s*$') -and -not ($gtP -match '(?m)^#@@HOVER@@\s*$')) ''
Check 'R14' '13: на экране оценка времени (около 2,5 минут, 29.10: 2 мин 26 с), «не закрывайте окно», прежняя сборка ~/ros2_ws нетронута как резерв' ($r.Console -match '2,5 минут' -and $r.Console -match '2 мин 26 с' -and $r.Console -match 'Не закрывайте окно' -and $r.Console -match 'ros2_ws остаётся нетронутой') ''
$bcodeP = ([IO.File]::ReadAllText((Join-Path $Kit 'run_bb_build.ps1')) -split "`n" | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n"
Check 'R14' 'код run_bb_build.ps1: нет sudo, systemctl, apt, set_mode, arming, param set, start_bumblebee (службу и пароль не трогает, подключение оверлея не делает)' (-not ($bcodeP -match '(?i)sudo\s|apt-get|apt\s+install|systemctl|reboot|set_mode|arming|param set|start_bumblebee')) ''
foreach ($bad in @("BATTERY`r`nSERVICE`r`nXXX`r`n", "BATTERY`r`nNO`r`nBUILD`r`n", "NO`r`nSERVICE`r`nBUILD`r`n")) {
    Reset-Fake; $r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $bad
    Check 'R14' ('13: неверное подтверждение (' + ($bad -replace "`r`n", '/').Trim('/') + '): код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
}
Reset-Fake; $r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13 '' 'OTHER-PC'
Check 'R14' '13: чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'canned_bbpre.txt' "BBPRE service_bumblebee active`nBBPRE src_ok=10 src_bad=0`nBB_BBPRE_RESULT STOP служба_bumblebee_активна(остановите_сами_sudo_systemctl_stop_bumblebee)`nBB_BBPRE_DONE`n"
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
Check 'R15' '13: проверка Pi сказала STOP (служба активна): код 4, сборка не запускалась (2 вызова: имя дрона, проверка), состояние «до» записано' ($r.Code -eq 4 -and $r.Calls.Count -eq 2 -and @($r.Calls | Where-Object { $_ -match '\[-tt\]' }).Count -eq 0 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'bb_state_before_*.txt').Count -eq 1 -and $r.Console -match 'сборку начинать нельзя') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; Set-Canned 'canned_bbbuild.txt' "Summary: 1 package finished [2min 26s]`n  1 package had stderr output: bumblebee`nBB_BBBUILD_STDERR 146 с: у сборки есть stderr (строки выше).`n"
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
Check 'R15' '13: сборка прошла, но есть stderr (BB_BBBUILD_STDERR): код 7, «Дальше не идти: решает чат 1», ничего не принимается заранее' ($r.Code -eq 7 -and $r.Console -match 'есть stderr' -and $r.Console -match 'решает чат 1') ('code=' + $r.Code)
Check 'R15' '13 (S4, чат 1 21:50): код 7 без «led_msgs not found»: «Причина НЕ известная», что делать: ничего не запускать, не повторять, прислать журнал чату 1' ($r.Code -eq 7 -and $r.Console -match 'Причина НЕ известная' -and $r.Console -match 'сборку не повторять' -and $r.Console -match 'Прислать чату 1' -and $r.Console -notmatch 'известное предупреждение') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_bbbuild.txt' "Summary: 1 package finished [2min 26s]`n  1 package had stderr output: bumblebee`n--- stderr: bumblebee`n  led_msgs not found — skipping led node (install led_msgs to enable)`nBB_BBBUILD_STDERR 146 с: у сборки есть stderr (строки выше).`n"
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
Check 'R15' '13 (S4, чат 1 21:50): код 7 с «led_msgs not found»: «известное предупреждение», но НЕ «можно продолжать» (решает чат 1), что прислать и что делать владельцу' ($r.Code -eq 7 -and $r.Console -match 'известное предупреждение .led_msgs not found' -and $r.Console -match 'НЕ значит .можно продолжать.' -and $r.Console -match 'решает чат 1' -and $r.Console -match 'bb_build_<время>\.log' -and $r.Console -match 'сборку не повторять') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_bbbuild.txt' "BB_BBBUILD_STOP исходник не равен r2j: ros2_ws/src/bumblebee/src/cpp/rc.cpp`n"
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
Check 'R15' '13: сборка остановилась сама (BB_BBBUILD_STOP, нет OK): код 6, «не дошла до конца», подсказка про 14' ($r.Code -eq 6 -and $r.Console -match 'не дошла до конца' -and $r.Console -match '14_otkat_sborki_bumblebee') ('code=' + $r.Code)
Reset-Fake 'wrong_host'
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
Check 'R15' '13: чужой дрон: код 4, проверка и сборка не делались (один вызов)' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ('code=' + $r.Code)
Reset-Fake 'nodone'
$r = Run-Cmd '13_sborka_bumblebee_r2j.cmd' $tok13
Check 'R15' '13: проверка Pi оборвалась (нет BB_BBPRE_DONE): код 4, сборка не запускалась' ($r.Code -eq 4 -and @($r.Calls | Where-Object { $_ -match '\[-tt\]' }).Count -eq 0) ('code=' + $r.Code)
Reset-Fake
$r = Run-Cmd '14_otkat_sborki_bumblebee.cmd' "ASIDE`r`n"
Check 'R16' '14: ASIDE: код 0; 2 вызова ssh (имя дрона, перенос mv); «ничего не удалено», ~/ros2_ws не менялся' ($r.Code -eq 0 -and $r.Calls.Count -eq 2 -and $r.Console -match 'ничего не удалено' -and $r.Console -match 'ros2_ws не менялся') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; $r = Run-Cmd '14_otkat_sborki_bumblebee.cmd' "NO`r`n"
Check 'R16' '14: без ASIDE: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'canned_bbaside.txt' "STOP: start_bumblebee.sh подключает оверлей bench_ws/r2j: сначала отключить, ничего не перенесено`n"; [IO.File]::WriteAllText((Join-Path $FakeDir 'bbaside_rc.txt'), '1')
$r = Run-Cmd '14_otkat_sborki_bumblebee.cmd' "ASIDE`r`n"
Check 'R16' '14: Pi отказал (оверлей подключён): код 4, «Ничего не удалялось»' ($r.Code -eq 4 -and $r.Console -match 'Ничего не удалялось') ('code=' + $r.Code)
# 15: отпечатки
Reset-Fake
$r = Run-Cmd '15_otpechatki_sborki.cmd' ''
$fpb = @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' }); $fpm = @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_mavros_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' })
$fbt = ''; if ($fpb.Count -eq 1) { $fbt = [IO.File]::ReadAllText($fpb[0].FullName) }
Check 'R17' '15: bumblebee собран и без замечаний, MAVROS не собран: код 0; файл отпечатков bumblebee с «VERDICT OK» и строками «sha256  путь» записан на ПК; для mavros файла нет (оверлей не собран)' ($r.Code -eq 0 -and $fpb.Count -eq 1 -and $fpm.Count -eq 0 -and $fbt -match '(?m)^# VERDICT OK\s*$' -and $fbt -match '(?m)^[0-9a-f]{64}  bumblebee/lib/bumblebee/aruco_detect\.py\s*$' -and $r.Console -match 'mavros: оверлей не собран') ('code=' + $r.Code + ' bb=' + $fpb.Count + ' mv=' + $fpm.Count)
Check 'R17' '15: 3 вызова ssh (имя дрона, bumblebee, mavros), ничего не пишется на Pi (в вызовах нет mkdir, tee, sudo)' ($r.Calls.Count -eq 3 -and $r.J -notmatch 'sudo|mkdir|tee ') ('calls=' + $r.Calls.Count)
Check 'R17' '15: на экране «бинарники не старше исходников» не заявлено без проверки: строка итога содержит число бинарников' ($r.Console -match 'бинарников 6') ''
Reset-Fake; Set-Canned 'canned_fp_mavros.txt' (New-FpCanned 'mavros' 3 0 0 5 0 3 0 0); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R17' '15: собраны оба оверлея без замечаний: код 0, два файла отпечатков' ($r.Code -eq 0 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_mavros_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' }).Count -eq 1) ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 3 10 0 16 0 6 1 0); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
$fpb = @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' })
Check 'R18' '15: бинарник старше исходников (stale=1): код 5, красное СТОП «подключать нельзя», в файле отпечатков «VERDICT NOT_OK»' ($r.Code -eq 5 -and $r.Console -match 'СТОП' -and $fpb.Count -eq 1 -and ([IO.File]::ReadAllText($fpb[0].FullName)) -match '(?m)^# VERDICT NOT_OK\s*$') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 3 9 1 15 0 6 0 0); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R18' '15: один python-узел отличается (py_bad=1): код 5' ($r.Code -eq 5) ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 3 10 0 15 1 6 0 0); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R18' '15: один C++ исходник копии отличается (src_bad=1): код 5' ($r.Code -eq 5) ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 3 10 0 16 0 5 0 0); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
$fpb5 = @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' })
Check 'R18' '15 (правка по проверке 10.11, S3): собрано 5 бинарников из 6 (неполная сборка bumblebee): код 5, «VERDICT NOT_OK», на экране «ждали 6»' ($r.Code -eq 5 -and $fpb5.Count -eq 1 -and ([IO.File]::ReadAllText($fpb5[0].FullName)) -match '(?m)^# VERDICT NOT_OK\s*$' -and $r.Console -match 'ждали 6') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 3 10 0 16 0 6 0 0 1 0); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
$fpr = @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_bumblebee_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' })
Check 'R18' '15 (S2, чат 1 21:50): один launch-файл оверлея отличается от r2j: код 5, «VERDICT NOT_OK», в файле отпечатков строка BB_FP_RT' ($r.Code -eq 5 -and $fpr.Count -eq 1 -and ([IO.File]::ReadAllText($fpr[0].FullName)) -match '(?m)^# VERDICT NOT_OK\s*$' -and ([IO.File]::ReadAllText($fpr[0].FullName)) -match '# BB_FP_RT ok=7 diff=1') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 3 10 0 16 0 6 0 0 0 1); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R18' '15 (S2): fcu_detect.py на Pi нет (missing=1): код 5' ($r.Code -eq 5) ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_fp_bumblebee.txt' (New-FpCanned 'bumblebee' 0 0 0 0 0 0 0 1); $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R18' '15: ни один оверлей не собран: код 5, «Нет ни одного собранного оверлея»' ($r.Code -eq 5 -and $r.Console -match 'Нет ни одного собранного оверлея') ('code=' + $r.Code)
Reset-Fake 'nodone'; $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R18' '15: чтение оборвалось (нет BB_FP_DONE): код 4, файл .FAILED, отпечатков нет' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_*.FAILED.txt').Count -ge 1 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'fingerprint_*_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|FAILED|generated' }).Count -eq 0) ('code=' + $r.Code)
Reset-Fake 'wrong_host'; $r = Run-Cmd '15_otpechatki_sborki.cmd' ''
Check 'R18' '15: чужой дрон: код 4, чтение не делалось (один вызов)' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ('code=' + $r.Code)
# 16: подключение оверлея, гейт «да» владельца
$tok16 = "MAVROS`r`nSERVICE`r`nCONNECT`r`n"
function Seed-Overlay([string]$out, [string]$verdict = 'OK', [bool]$approve = $true, [string]$apprSha = '', [int]$extraFiles = 0) {
    $fp = Join-Path $out 'fingerprint_mavros_20261110_200000.txt'
    $extraTxt = ''; if ($extraFiles -gt 0) { foreach ($i in 1..$extraFiles) { $extraTxt += ('{0:x64}' -f $i) + '  bumblebee/include/bumblebee/msg/detail/file_' + $i + '_with_a_long_path__.hpp' + "`r`n" } }
    [IO.File]::WriteAllText($fp, ("# отпечатки (тест)`r`n# VERDICT " + $verdict + "`r`n" + ('a' * 64) + "  mavros/lib/libmavros.so`r`n" + ('b' * 64) + "  local_setup.bash`r`n" + $extraTxt), $utf8n)
    $gd = Join-Path $SB 'gates'; New-Item -ItemType Directory -Path $gd -Force | Out-Null
    $ap = Join-Path $gd 'OVERLAY_MAVROS_APPROVED.txt'; if (Test-Path $ap) { Remove-Item $ap }
    if ($approve) {
        $sha = (Get-FileHash -Algorithm SHA256 -LiteralPath $fp).Hash.ToLower(); if ($apprSha -ne '') { $sha = $apprSha }
        [IO.File]::WriteAllText($ap, ("ПОДКЛЮЧИТЬ=mavros`r`nВЛАДЕЛЕЦ_СКАЗАЛ=да`r`nДАТА=2026-11-11 09:00`r`nСЛОВА_ВЛАДЕЛЬЦА=тест`r`nОТПЕЧАТКИ_SHA256=" + $sha + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
    }
}
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $false
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R19' '16: нет gates\OVERLAY_MAVROS_APPROVED.txt («да» владельца не записано чатом 1): код 4, к дрону не обращались, причина названа' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'OVERLAY_MAVROS_APPROVED') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $true ('0' * 64)
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R19' '16: разрешение выдано для других отпечатков (sha не тот): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'ОТПЕЧАТКИ_SHA256') ('code=' + $r.Code)
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'NOT_OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R19' '16: в отпечатках VERDICT NOT_OK: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'VERDICT OK') ('code=' + $r.Code)
Reset-Fake; $o16 = New-Out
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R19' '16: нет отпечатков вообще (шаг 15 не делался): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'нет отпечатков') ('code=' + $r.Code)
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
$gc = @(Get-ChildItem -LiteralPath $o16 -Filter 'overlay_connect_mavros_*.generated.sh'); $gct = ''; if ($gc.Count -eq 1) { $gct = [IO.File]::ReadAllText($gc[0].FullName) }
Check 'R19' '16: разрешение и отпечатки в порядке, три подтверждения: код 0; 3 вызова ssh (имя дрона, чтение start_bumblebee.sh, подключение); в скрипт вставлены FPHASH и FPCOUNT, заглушки нет' ($r.Code -eq 0 -and $r.Calls.Count -eq 3 -and $gc.Count -eq 1 -and -not ($gct -match '(?m)^#@@FPCFG@@\s*$') -and $gct.Contains('BB_CONN_MARK') -and $r.Console -match 'подключён') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
# правка по проверке 10.11 (M1): в скрипт идёт СУММА списка и число файлов, а не весь список (500 строк не помещаются в командную строку ssh, предел Windows 32 767 знаков)
$fpl = @(('a' * 64) + '  mavros/lib/libmavros.so'; ('b' * 64) + '  local_setup.bash')
function Get-ListHash([string[]]$lines) { $k = [string[]]@($lines | ForEach-Object { $_.Substring(66) }); $v = [string[]]@($lines); [Array]::Sort($k, $v, [StringComparer]::Ordinal); $tx = (($v -join "`n") + "`n"); return (([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash((New-Object Text.UTF8Encoding($false)).GetBytes($tx))) -replace '-', '').ToLower()) }
Check 'R19' '16: в скрипт подставлены FPHASH (сумма отсортированного списка «sha256  путь») и FPCOUNT=2, самих строк списка в скрипте нет' ($gct -match ('(?m)^FPHASH=' + (Get-ListHash $fpl) + '\s*$') -and $gct -match '(?m)^FPCOUNT=2\s*$' -and -not $gct.Contains(('a' * 64) + '  mavros/lib/libmavros.so')) ''
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $true '' 600
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
$gcB = @(Get-ChildItem -LiteralPath $o16 -Filter 'overlay_connect_mavros_*.generated.sh'); $gctB = ''; if ($gcB.Count -eq 1) { $gctB = [IO.File]::ReadAllText($gcB[0].FullName) }
$fplB = @(([IO.File]::ReadAllLines((Join-Path $o16 'fingerprint_mavros_20261110_200000.txt')) | Where-Object { $_ -match '^[0-9a-f]{64}  \S+$' }))
$maxLen = ($r.Calls | ForEach-Object { $_.Length } | Measure-Object -Maximum).Maximum
Check 'R19' '16: отпечатки из 602 файлов (как у настоящего install bumblebee, 505 файлов): код 0, ни один вызов ssh не длиннее 30000 знаков (предел Windows 32 767), FPCOUNT=602, FPHASH совпадает с независимым расчётом' ($r.Code -eq 0 -and $r.Calls.Count -eq 3 -and $maxLen -lt 30000 -and $gctB -match '(?m)^FPCOUNT=602\s*$' -and $gctB -match ('(?m)^FPHASH=' + (Get-ListHash $fplB) + '\s*$')) ('code=' + $r.Code + ' maxLen=' + $maxLen)
foreach ($bad in @("MAVROS`r`nSERVICE`r`nXXX`r`n", "MAVROS`r`nNO`r`nCONNECT`r`n", "EVIL`r`nSERVICE`r`nCONNECT`r`n", "`r`nSERVICE`r`nCONNECT`r`n")) {
    Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $true
    $r = Run-In '16_podkljuchit_overlay.cmd' $o16 $bad
    Check 'R19' ('16: неверное подтверждение или цель (' + ($bad -replace "`r`n", '/').Trim('/') + '): код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
}
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16 'OTHER-PC'
Check 'R19' '16: чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'canned_conn.txt' "BB_CONN_STOP служба bumblebee запущена: остановите сами (sudo systemctl stop bumblebee)`n"; [IO.File]::WriteAllText((Join-Path $FakeDir 'conn_rc.txt'), '1'); $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R20' '16: Pi отказал (служба активна): код 4, «start_bumblebee.sh не менялся»' ($r.Code -eq 4 -and $r.Console -match 'не менялся') ('code=' + $r.Code)
Seed-Overlay (New-Out) 'OK' $false
Reset-Fake
$r = Run-Cmd '17_otkljuchit_overlay.cmd' "SERVICE`r`nDISCONNECT`r`n"
Check 'R20' '17: SERVICE и DISCONNECT: код 0 БЕЗ гейта «да» (откат всегда разрешён); 2 вызова ssh (имя дрона, откат)' ($r.Code -eq 0 -and $r.Calls.Count -eq 2 -and $r.Console -match 'возвращён') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
foreach ($bad in @("SERVICE`r`nXXX`r`n", "NO`r`nDISCONNECT`r`n")) { Reset-Fake; $r = Run-Cmd '17_otkljuchit_overlay.cmd' $bad; Check 'R20' ('17: неверное подтверждение (' + ($bad -replace "`r`n", '/').Trim('/') + '): код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code) }
Reset-Fake; Set-Canned 'canned_disc.txt' "BB_DISC_STOP start_bumblebee.sh не равен копии .after: после подключения его кто-то менял, откат не делаю`n"; [IO.File]::WriteAllText((Join-Path $FakeDir 'disc_rc.txt'), '1')
$r = Run-Cmd '17_otkljuchit_overlay.cmd' "SERVICE`r`nDISCONNECT`r`n"
Check 'R20' '17: Pi отказал (файл менялся после подключения): код 4, «не менялся»' ($r.Code -eq 4 -and $r.Console -match 'не менялся') ('code=' + $r.Code)
Remove-Item (Join-Path $SB 'gates\OVERLAY_MAVROS_APPROVED.txt') -ErrorAction SilentlyContinue
Check 'R20' 'настоящий набор: gates\OVERLAY_*_APPROVED.txt НЕТ (подключение оверлея без «да» владельца заблокировано); в gates\README.md описан формат' (-not (Test-Path (Join-Path $Kit 'gates\OVERLAY_MAVROS_APPROVED.txt')) -and -not (Test-Path (Join-Path $Kit 'gates\OVERLAY_BUMBLEBEE_APPROVED.txt')) -and (([IO.File]::ReadAllText((Join-Path $Kit 'gates\README.md'))) -match 'OVERLAY_') -and (([IO.File]::ReadAllText((Join-Path $Kit 'gates\README.md'))) -match 'ОТПЕЧАТКИ_SHA256=')) ''

# ---------- решение чата 1 (20:10): гейт drone.py перед взлётом, скрипты полёта из оверлея, чтение start_bumblebee.sh перед подключением ----------
function Reset-Takeoff { Set-TakeoffReady $conf $gate $sha64 '' }
Reset-Takeoff
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
Set-Canned 'canned_fg.txt' "FG_DIR /home/lb/ros2_ws/src/bumblebee/examples drone.py DIFF got=$('1' * 64) want=$drone64`nBB_FG_RESULT STOP drone.py_в_/home/lb/ros2_ws/src/bumblebee/examples_не_r2j`nBB_FG_DONE`n"
$odg = Join-Path $Run 'out_e_fg'; New-Item -ItemType Directory -Path $odg -Force | Out-Null; New-ParamsReport $odg $strict 0
$r = Run-07 $odg
Check 'E10' '07: drone.py, который импортирует скрипт, НЕ равен r2j (проверка Pi сказала STOP): код 4, запуска скрипта нет, отсчёта нет, на экране «НЕ равен r2j» и строка FG_DIR' ($r.Code -eq 4 -and @($r.Calls | Where-Object { $_ -match '\[-tt\]' }).Count -eq 0 -and $r.Secs -lt 9 -and $r.Console -match 'НЕ равен r2j' -and $r.Console -match 'FG_DIR') ('code=' + $r.Code + ' secs=' + [int]$r.Secs)
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py')); Set-Canned 'canned_fg.txt' "FG_DIR /x drone.py OK`n"
$odg2 = Join-Path $Run 'out_e_fg2'; New-Item -ItemType Directory -Path $odg2 -Force | Out-Null; New-ParamsReport $odg2 $strict 0
$r = Run-07 $odg2
Check 'E10' '07: ответ проверки drone.py оборвался (нет BB_FG_DONE): код 4, взлёт не начат' ($r.Code -eq 4 -and @($r.Calls | Where-Object { $_ -match '\[-tt\]' }).Count -eq 0 -and $r.Secs -lt 9) ('code=' + $r.Code)
Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py'))
$odg3 = Join-Path $Run 'out_e_fg3'; New-Item -ItemType Directory -Path $odg3 -Force | Out-Null; New-ParamsReport $odg3 $strict 0
$r = Run-07 $odg3
$fgs = @(Get-ChildItem -LiteralPath $odg3 -Filter 'flight_gate_*.generated.sh'); $fgt = ''; if ($fgs.Count -eq 1) { $fgt = [IO.File]::ReadAllText($fgs[0].FullName) }
Check 'E10' '07: в скрипт проверки drone.py вставлены путь скрипта (из оверлея) и sha256 drone.py r2j (fa6abf8b…), заглушки нет' ($r.Code -eq 0 -and $fgs.Count -eq 1 -and $fgt -match '(?m)^SCRIPT=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0\.py\s*$' -and $fgt -match ('(?m)^WANT=' + $drone64 + '\s*$') -and -not ($fgt -match '(?m)^#@@FGCFG@@\s*$') -and $fgt.Contains('BB_FG_MARK')) ('code=' + $r.Code + ' files=' + $fgs.Count)
# takeoff.conf без DRONE_PY_SHA256 или со скриптом вне оверлея: код 4 до обращения к дрону
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py`nSCRIPT_SHA256=$sha64`nSCRIPT_ARGS=--height 0.8`n", $utf8n)
Reset-Fake; $odg4 = Join-Path $Run 'out_e_fg4'; New-Item -ItemType Directory -Path $odg4 -Force | Out-Null; New-ParamsReport $odg4 $strict 0
$r = Run-07 $odg4
Check 'E11' '07: в takeoff.conf нет DRONE_PY_SHA256: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'DRONE_PY_SHA256') ('code=' + $r.Code)
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/ros2_ws/src/bumblebee/examples/flight/flight.py`nSCRIPT_SHA256=$sha64`nDRONE_PY_SHA256=$drone64`nSCRIPT_ARGS=--height 0.8`n", $utf8n)
Reset-Fake; $odg5 = Join-Path $Run 'out_e_fg5'; New-Item -ItemType Directory -Path $odg5 -Force | Out-Null; New-ParamsReport $odg5 $strict 0
$r = Run-07 $odg5
Check 'E11' '07: скрипт полёта лежит НЕ в оверлее (/home/lb/ros2_ws/...): код 4, к дрону не обращались, причина названа' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'должен лежать в оверлее') ('code=' + $r.Code)
[IO.File]::WriteAllText($conf, "SCRIPT_REMOTE_PATH=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py`nSCRIPT_SHA256=$sha64`nDRONE_PY_SHA256=abc`nSCRIPT_ARGS=--height 0.8`n", $utf8n)
Reset-Fake; $odg6 = Join-Path $Run 'out_e_fg6'; New-Item -ItemType Directory -Path $odg6 -Force | Out-Null; New-ParamsReport $odg6 $strict 0
$r = Run-07 $odg6
Check 'E11' '07: DRONE_PY_SHA256 не 64 символа: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match '64 символа') ('code=' + $r.Code)
Reset-Takeoff
# ---------- решение чата 1 (21:50), S1: 07 требует свежие успешные 09 и 10 после последнего 16/17 или сборки ----------
function New-Out07([string]$name) { $d = Join-Path $Run $name; New-Item -ItemType Directory -Path $d -Force | Out-Null; New-ParamsReport $d $strict 0; return $d }
function Set-Chk([string]$d, [string]$kind, [string]$text, [int]$ageMin) { $cf = Join-Path $d ($kind + '_20261111_080000.txt'); [IO.File]::WriteAllText($cf, $text, $utf8); (Get-Item $cf).LastWriteTime = (Get-Date).AddMinutes(-$ageMin) }
function Set-Evt([string]$d, [string]$name, [int]$ageMin) { $ef = Join-Path $d $name; [IO.File]::WriteAllText($ef, "BB_CONN_DONE mavros /x`r`n", $utf8); (Get-Item $ef).LastWriteTime = (Get-Date).AddMinutes(-$ageMin) }
function Reset-S1 { Set-TakeoffReady $conf $gate $sha64 ''; Reset-Fake; [IO.File]::WriteAllText((Join-Path $FakeDir 'sha_out.txt'), ($sha64 + '  /home/lb/bench_ws/r2j/src/bumblebee/examples/flight/hover_marker0.py')) }
Reset-S1; $d = New-Out07 'out_s1a'; Get-ChildItem $d -Filter 'install_check_*' | Remove-Item
$r = Run-07 $d
Check 'S1' '07: нет сверки 09 (install_check): код 4, к дрону не обращались, причина названа' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'нет сверки 09_sverka_install') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-S1; $d = New-Out07 'out_s1b'; Get-ChildItem $d -Filter 'mavros_check_*' | Remove-Item
$r = Run-07 $d
Check 'S1' '07: нет сверки 10 (mavros_check): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'нет сверки 10_mavros_versiya') ('code=' + $r.Code)
Reset-S1; $d = New-Out07 'out_s1c'; Set-Chk $d 'install_check' "BB_INSTALL_CHECK ok=1`r`n# VERDICT NOT_OK`r`n" 5
$r = Run-07 $d
Check 'S1' '07: последняя сверка 09 неуспешна (# VERDICT NOT_OK): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'не успешна') ('code=' + $r.Code)
Reset-S1; $d = New-Out07 'out_s1d'; Set-Chk $d 'mavros_check' "BB_MAVROS_CHECK src_ok=5`r`n" 5
$r = Run-07 $d
Check 'S1' '07: в сверке 10 нет строки «# VERDICT OK» (старый формат, без вердикта): код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Reset-S1; $d = New-Out07 'out_s1e'; Set-Evt $d 'overlay_connect_mavros_20261111_081000.txt' 1
$r = Run-07 $d
Check 'S1' '07: после успешных 09 и 10 было подключение оверлея (16): код 4, «сделана ДО последнего подключения», к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'ДО последнего подключения') ('code=' + $r.Code)
foreach ($evn in 'overlay_disconnect_last_20261111_081000.txt', 'bb_build_20261111_081000.log', 'mavros_build_20261111_081000.log', 'bb_aside_20261111_081000.txt', 'mavros_aside_20261111_081000.txt', 'install_r2j_12345678.log', 'rollback_r2j_12345678.log', 'install_camera_dabd5076_12345678.log') {
    Reset-S1; $d = New-Out07 'out_s1f'; if (Test-Path $d) { Remove-Item $d -Recurse -Force }; $d = New-Out07 ('out_s1f_' + [guid]::NewGuid().ToString('N').Substring(0, 6)); Set-Evt $d $evn 1
    $r = Run-07 $d
    Check 'S1' ('07: событие ' + ($evn -replace '_\d{8}.*$', '') + ' новее сверок: код 4') ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'ДО последнего подключения') ('code=' + $r.Code)
}
Reset-S1; $d = New-Out07 'out_s1g'; Set-Chk $d 'install_check' "BB_INSTALL_CHECK ok=1`r`n# VERDICT OK`r`n" 200; Set-Chk $d 'mavros_check' "BB_MAVROS_CHECK src_ok=5`r`n# VERDICT OK`r`n" 200
$r = Run-07 $d
Check 'S1' '07: успешные 09 и 10 старше 180 минут: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'старше 180') ('code=' + $r.Code)
Reset-S1; $d = New-Out07 'out_s1h'; Set-Evt $d 'overlay_connect_mavros_20261111_070000.generated.sh' 1; Set-Evt $d 'overlay_connect_mavros_20261111_070000.err.txt' 1; Set-Evt $d 'start_script_check_mavros_20261111_070000.txt' 1; Set-Evt $d 'fingerprint_bumblebee_20261111_070000.txt' 1; Set-Evt $d 'bb_precheck_20261111_070000.txt' 1
$r = Run-07 $d
Check 'S1' '07: generated, .err.txt, start_script_check, отпечатки и предпроверки НЕ считаются подключением/сборкой: код 0 (скрипт отработал), сверки 09 и 10 приняты' ($r.Code -eq 0 -and @($r.Calls | Where-Object { $_ -match '\[-tt\]' }).Count -eq 1) ('code=' + $r.Code)
Reset-Takeoff
# 16: нынешний start_bumblebee.sh читается чтением и сравнивается с s0b ДО подключения
$baseTxt = ([IO.File]::ReadAllText((Join-Path $Kit 'image_r2j\START_BUMBLEBEE_BASELINE_s0b.sh'))) -replace "`r`n", "`n"
function Get-TextSha([string]$text) { return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash((New-Object Text.UTF8Encoding($false)).GetBytes($text))) -replace '-', '').ToLower() }
$lws = 'source /home/lb/ros2_ws/install/setup.bash'; $lmv = 'source /home/lb/bench_ws/mavros/install/local_setup.bash'
$withM = $baseTxt.Replace($lws + "`n", $lws + "`n" + $lmv + "`n")
Check 'R21' 'эталон START_BUMBLEBEE_BASELINE_s0b.sh в наборе: sha256 58c14783… (как в s0b), ровно одна строка source ros2_ws, без CR' ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Kit 'image_r2j\START_BUMBLEBEE_BASELINE_s0b.sh')).Hash.ToLower() -eq '58c14783f2f22c453721756fa088d4868c4ff5e3a439a57ed1abd96ed3ed9be2' -and ([regex]::Matches($baseTxt, '(?m)^' + [regex]::Escape($lws) + '$')).Count -eq 1 -and $withM -ne $baseTxt -and (Get-TextSha $baseTxt) -eq '58c14783f2f22c453721756fa088d4868c4ff5e3a439a57ed1abd96ed3ed9be2') ''
Reset-Fake; $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R21' '16: start_bumblebee.sh на дроне как в s0b: проверка чтением (3 вызова: имя дрона, чтение start_bumblebee.sh, подключение), код 0; на экране «можно подключать» и «после строки source ~/ros2_ws»' ($r.Code -eq 0 -and $r.Calls.Count -eq 3 -and $r.Console -match 'можно подключать' -and $r.Console -match 'после строки source ~/ros2_ws') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; Set-Canned 'canned_ssc.txt' ("SSC sha256 " + ('9' * 64) + " bytes 2500`nSSC ros2_ws_lines 1`nSSC overlay_lines 0`nBB_SSC_DONE`n"); $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R21' '16: start_bumblebee.sh на дроне ОТЛИЧАЕТСЯ от s0b: код 4, СТОП «решает владелец», подключение не вызывалось (2 вызова: имя дрона, чтение)' ($r.Code -eq 4 -and $r.Calls.Count -eq 2 -and $r.Console -match 'ОТЛИЧАЕТСЯ' -and $r.Console -match 'Решает владелец' -and @(Get-ChildItem -LiteralPath $o16 -Filter 'overlay_connect_mavros_*.txt' -ErrorAction SilentlyContinue | Where-Object { $_.Name -notmatch 'generated|err' }).Count -eq 0) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Reset-Fake; Set-Canned 'canned_ssc.txt' "SSC missing /home/lb/start_bumblebee.sh`nBB_SSC_DONE`n"; $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R21' '16: start_bumblebee.sh на дроне нет: код 4, «файла нет на дроне», подключение не вызывалось' ($r.Code -eq 4 -and $r.Console -match 'файла нет на дроне' -and $r.Calls.Count -eq 2) ('code=' + $r.Code)
Reset-Fake; Set-Canned 'canned_ssc.txt' ("SSC sha256 " + (Get-TextSha $withM) + " bytes 2500`nSSC ros2_ws_lines 1`nSSC overlay_lines 1`nBB_SSC_DONE`n"); $o16 = New-Out; Seed-Overlay $o16 'OK' $true
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 $tok16
Check 'R21' '16: цель MAVROS, а в файле уже строка MAVROS (эталон + строка MAVROS): код 4 «ОТЛИЧАЕТСЯ» (для MAVROS допустим только чистый эталон)' ($r.Code -eq 4 -and $r.Console -match 'ОТЛИЧАЕТСЯ') ('code=' + $r.Code)
# цель bumblebee при уже подключённом MAVROS: разрешён эталон + строка MAVROS
Reset-Fake; Set-Canned 'canned_ssc.txt' ("SSC sha256 " + (Get-TextSha $withM) + " bytes 2500`nSSC ros2_ws_lines 1`nSSC overlay_lines 1`nBB_SSC_DONE`n"); $o16 = New-Out
$fpB = Join-Path $o16 'fingerprint_bumblebee_20261110_200000.txt'; [IO.File]::WriteAllText($fpB, ("# VERDICT OK`r`n" + ('c' * 64) + "  bumblebee/lib/bumblebee/node`r`n"), $utf8n)
$gdir = Join-Path $SB 'gates'; $apB = Join-Path $gdir 'OVERLAY_BUMBLEBEE_APPROVED.txt'
[IO.File]::WriteAllText($apB, ("ПОДКЛЮЧИТЬ=bumblebee`r`nВЛАДЕЛЕЦ_СКАЗАЛ=да`r`nДАТА=2026-11-11 09:00`r`nСЛОВА_ВЛАДЕЛЬЦА=тест`r`nОТПЕЧАТКИ_SHA256=" + (Get-FileHash -Algorithm SHA256 -LiteralPath $fpB).Hash.ToLower() + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8)
$r = Run-In '16_podkljuchit_overlay.cmd' $o16 "BUMBLEBEE`r`nSERVICE`r`nCONNECT`r`n"
Check 'R21' '16: цель BUMBLEBEE при уже подключённом MAVROS (эталон + строка MAVROS): проверка пройдена, подключение вызвано: код 0, 3 вызова' ($r.Code -eq 0 -and $r.Calls.Count -eq 3) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)
Remove-Item $apB -ErrorAction SilentlyContinue
$ssccode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\start_script_check.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'R21' 'start_script_check.sh: только чтение (нет rm, mv, cp, tee, mkdir, touch, chmod, sudo, перенаправления в файл)' (-not ($ssccode -match '(^|[\s;|&(])(rm|mv|cp|tee|mkdir|touch|chmod|sudo)\s') -and -not (($ssccode -replace '2>/dev/null', '' -replace '2>&1', '') -match '>\s*[^&\s]')) ''
Check 'R21' 'flight_gate.sh: только чтение (нет rm, mv, cp, tee, mkdir, touch, chmod, sudo, перенаправления в файл)' (-not ((([IO.File]::ReadAllLines((Join-Path $Kit 'pi\flight_gate.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n") -match '(^|[\s;|&(])(rm|mv|cp|tee|mkdir|touch|chmod|sudo)\s')) ''

# ---------- K: карточки шагов ----------
$cardsTxt = [IO.File]::ReadAllText((Join-Path $Kit 'cards\КАРТОЧКИ_ШАГОВ_СТЕНДА.md'))
$cardParts = [regex]::Split($cardsTxt, '(?m)^## Карточка ') | Select-Object -Skip 1
Check 'K1' 'карточек 22, нумерация «N из 22» подряд' ($cardParts.Count -eq 22 -and (@(1..22 | Where-Object { $cardParts[$_ - 1] -match ('^' + $_ + ' из 22') }).Count -eq 22)) ($cardParts.Count)
foreach ($i in 15, 16, 18, 21) {
    $c = $cardParts[$i - 1]
    Check 'K2' ("карточка $i (с моторами): четыре меры безопасности") ($c -match 'винты (СНЯТЫ|ставят только)|винты только после|винты поставлены только' -and $c -match 'аварийном выключателе' -and $c -match 'закреплён или в сетке|сетка или привязь|дрон в сетке' -and $c -match 'два человека|второй человек') ''
    Check 'K2' ("карточка $i (с моторами): «Причина рывка … 04.11 неизвестна» и правило 3 / СТОП, батарею отключить") ($c -match 'Причина рывка.*неизвестна' -and $c -match '(?i)правило 3|СТОП, батарею отключить') ''
}
foreach ($i in 1..22) {
    $c = $cardParts[$i - 1]
    Check 'K3' ("карточка $i : есть «Что меняется»") ($c -match 'Что меняется') ''
}
$cmdNames = [regex]::Matches($cardsTxt, '`((?:image_r2j\\)?[0-9]{2}[a-z]?_[a-z0-9_]+\.cmd)`') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
Check 'K4' 'все .cmd, названные в карточках, существуют в наборе' (@($cmdNames | Where-Object { -not (Test-Path (Join-Path $Kit $_)) }).Count -eq 0 -and $cmdNames.Count -ge 7) ($cmdNames -join ',')
Check 'K4' 'в карточках нет ssh, scp, sudo' (-not ($cardsTxt -match '\b(ssh|scp|sudo)\b')) ''
Check 'K4' 'карточки 5, 19, 20, 21, 22: ЗАГОТОВКА (заблокированы)' (($cardParts[4] -match 'ЗАГОТОВКА') -and ($cardParts[18] -match 'ЗАГОТОВКА') -and ($cardParts[19] -match 'ЗАГОТОВКА') -and ($cardParts[20] -match 'ЗАГОТОВКА') -and ($cardParts[21] -match 'ЗАГОТОВКА')) ''
Check 'K4' 'карточка 21: отсчёт не меньше 10 с, NET TWO KILL YES, способы остановки' ($cardParts[20] -match 'не меньше 10 секунд' -and $cardParts[20] -match 'NET' -and $cardParts[20] -match 'переключатель режима на пульте, CH8, Ctrl\+C') ''
# порядок по поправке чата 1 (~10:00): снимок -> группы QGC 1,3,2 -> сверка -> установка r2j -> группа 4 -> сверка -> стенд на r2j -> висение -> взлёт
Check 'K5' 'порядок: 1 снимок (01), 2 группы QGC 1-3-2, 3 сверка r4, 4 батарея (08), 5 установка r2j (05), 6 группа 4 и новые строки, 7 сверка (01), потом стенд' ($cardParts[0] -match '01_snimok_do\.cmd' -and $cardParts[1] -match '1 → 3 → 2' -and $cardParts[2] -match 'params_check\.cmd' -and $cardParts[3] -match '08_batareya\.cmd' -and $cardParts[4] -match '05_install_r2j\.cmd' -and $cardParts[5] -match 'группа 4' -and $cardParts[6] -match '01_snimok_do\.cmd') ''
Check 'K5' 'порядок: замеры 02a, 02b, 03, 04 стоят ПОСЛЕ установки r2j и группы 4 (карточки 9, 11, 12-14, 15)' ($cardParts[8] -match '02a_zamer_bez_video\.cmd' -and $cardParts[10] -match '02b_zamer_s_video\.cmd' -and $cardParts[11] -match '03_v_rukakh\.cmd' -and $cardParts[14] -match '04_vibratsiya\.cmd') ''
$idx = @{}
foreach ($nm in '01_snimok_do.cmd', '05_install_r2j.cmd', '02a_zamer_bez_video.cmd', '02b_zamer_s_video.cmd', '03_v_rukakh.cmd', '04_vibratsiya.cmd', '07_vzlet_zagotovka.cmd') { $idx[$nm] = $cardsTxt.IndexOf('`' + $nm) ; if ($idx[$nm] -lt 0) { $idx[$nm] = $cardsTxt.IndexOf('\' + $nm + '`') } }
Check 'K5' 'в тексте установка r2j (05) стоит раньше любого замера зрения (02a, 02b, 03, 04) и раньше взлёта (07)' (($idx['05_install_r2j.cmd'] -gt 0) -and ($idx['05_install_r2j.cmd'] -lt $idx['02a_zamer_bez_video.cmd']) -and ($idx['05_install_r2j.cmd'] -lt $idx['02b_zamer_s_video.cmd']) -and ($idx['05_install_r2j.cmd'] -lt $idx['03_v_rukakh.cmd']) -and ($idx['05_install_r2j.cmd'] -lt $idx['04_vibratsiya.cmd']) -and ($idx['05_install_r2j.cmd'] -lt $idx['07_vzlet_zagotovka.cmd'])) (($idx.GetEnumerator() | ForEach-Object { $_.Key + '=' + $_.Value }) -join ' ')
Check 'K5' 'ручное висение в сетке (карточка 18) стоит после журнала вибрации и журналов SD и перед взлётом; в карточке 5 условие правила 14 и COM_OBL_RC_ACT = 4' (($cardParts[17] -match 'ручное висение' -or $cardParts[17] -match 'Ручное висение') -and $cardParts[4] -match 'COM_OBL_RC_ACT. = 4' -and $cardParts[4] -match 'не старше 30 минут') ''
Check 'K5' 'нет замера на старом образе и нет сравнения старого и нового camera_fix (в карточках и README)' (-not ($cardsTxt -match '(?i)на старом образе, замер|замер на старом образе:') -and -not (([IO.File]::ReadAllText((Join-Path $Kit 'README.md'))) -match '(?i)старого и нового camera_fix:') ) ''
Check 'K6' 'карточка 2: шаг 0 до группы 1 — копия всех журналов с SD через QGC Log Download, не нажимать Erase All, старые журналы терять нельзя' (($cardParts[1] -match 'Шаг 0, ДО группы 1') -and ($cardParts[1] -match 'Log Download') -and ($cardParts[1] -match 'Не нажимать «Erase All»') -and ($cardParts[1] -match 'SDLOG_DIRS_MAX') -and ($cardParts[1] -match 'терять нельзя') -and ($cardParts[1].IndexOf('Шаг 0') -lt $cardParts[1].IndexOf('Сделайте'))) ''
Check 'K6' 'карточка 21: после полёта проверка «разоружён» (run_armcheck), при взведённом настройки не читаются; аргументов у окна нет' (($cardParts[20] -match 'run_armcheck\.ps1') -and ($cardParts[20] -match 'НЕ читаются') -and ($cardParts[20] -match 'свободных аргументов у окна нет')) ''
Check 'K6' 'README и gates: в gates\README.md строка АРГУМЕНТЫ=, в image_r2j\gates\README.md строка ОБРАЗ_MANIFEST_SHA256=' (([IO.File]::ReadAllText((Join-Path $Kit 'gates\README.md'))) -match 'АРГУМЕНТЫ=' -and ([IO.File]::ReadAllText((Join-Path $Kit 'image_r2j\gates\README.md'))) -match 'ОБРАЗ_MANIFEST_SHA256=') ''
Check 'K7' 'карточка 4: батарея: 08_batareya.cmd, BAT1_N_CELLS, BAT1_V_EMPTY, BAT1_V_CHARGED, напряжение видно, предупреждений нет, ТОЛЬКО ЧТЕНИЕ' (($cardParts[3] -match '08_batareya\.cmd') -and ($cardParts[3] -match 'BAT1_N_CELLS') -and ($cardParts[3] -match 'BAT1_V_EMPTY') -and ($cardParts[3] -match 'BAT1_V_CHARGED') -and ($cardParts[3] -match 'напряжение видно') -and ($cardParts[3] -match 'предупреждений батареи') -and ($cardParts[3] -match 'ТОЛЬКО ЧТЕНИЕ')) ''
Check 'K7' 'карточка 5: образ r2j, MAVROS bp02, hover r6 (a11b195c), прежняя камера 4a15d699, вариант dabd5076 отдельно (карточка 22)' (($cardParts[4] -match 'r2j') -and ($cardParts[4] -match 'MAVROS bp02') -and ($cardParts[4] -match 'a11b195c') -and ($cardParts[4] -match '4a15d699') -and ($cardParts[4] -match 'dabd5076') -and ($cardParts[4] -match 'карточка 22')) ''
Check 'K7' 'карточка 9 (02a): паузы длиннее 0,4 с, 12 Гц, markers_used, сбросы EKF смотреть по журналу SD (карточка 17)' (($cardParts[8] -match '0,4 с') -and ($cardParts[8] -match '12 Гц') -and ($cardParts[8] -match 'markers_used') -and ($cardParts[8] -match 'карточка 17')) ''
Check 'K7' 'карточка 17: журналы SD в out\ulg, не нажимать Erase All, ulog_stand_report.py, xy_reset_counter, hover_thrust_estimate, только чтение' (($cardParts[16] -match 'out\\ulg') -and ($cardParts[16] -match 'Не нажимать «Erase All»') -and ($cardParts[16] -match 'ulog_stand_report\.py') -and ($cardParts[16] -match 'xy_reset_counter') -and ($cardParts[16] -match 'hover_thrust_estimate') -and ($cardParts[16] -match 'ничего')) ''
Check 'K7' 'карточки 18 и 21: T41 (hover_thrust_estimate, 4 с вместо 2,3 с), пауза зрения после взлёта, запас сторожа около 1 с со слов чата 1, journal_vision_pauses.py' (($cardParts[17] -match 'hover_thrust_estimate') -and ($cardParts[17] -match 'примерно через 4 с вместо ~2,3 с') -and ($cardParts[20] -match 'journal_vision_pauses\.py') -and ($cardParts[20] -match 'около 1 с \(со слов чата 1\)')) ''
Check 'K7' 'карточка 22: ТОЛЬКО ЕСЛИ ВЛАДЕЛЕЦ ВЫБЕРЕТ, dabd5076, PENDING, откат 06_rollback_r2j, вопрос владельцу' (($cardParts[21] -match 'ТОЛЬКО ЕСЛИ ВЛАДЕЛЕЦ ВЫБЕРЕТ') -and ($cardParts[21] -match 'dabd5076') -and ($cardParts[21] -match 'PENDING') -and ($cardParts[21] -match '06_rollback_r2j\.cmd') -and ($cardParts[21] -match 'вопрос владельцу')) ''
Check 'K7' 'в карточках нет r2g и qgc_card_set_20261109_r7; ссылка на карточки QGC r9' ((-not ($cardsTxt -match 'r2g')) -and ($cardsTxt -match 'qgc_card_set_20261109_r9') -and (-not ($cardsTxt -match 'qgc_card_set_20261109_r7'))) ''
Check 'K7' 'карточка 7: после снимка шаги только чтением 09_sverka_install.cmd (install на Pi со списком r2j, расхождение: СТОП) и 10_mavros_versiya.cmd (пока MAVROS bp02 не собран, СТОП)' (($cardParts[6] -match '09_sverka_install\.cmd') -and ($cardParts[6] -match '10_mavros_versiya\.cmd') -and ($cardParts[6] -match 'СТОП')) ''
Check 'K7' 'карточка 5: DEST_ROOT = /home/lb по принятому набору s0b, узлы исполняются из install, BACKUP_ROOT пока TBD, сборок MAVROS для Pi нет' (($cardParts[4] -match 'DEST_ROOT = /home/lb') -and ($cardParts[4] -match 'install') -and ($cardParts[4] -match 'BACKUP_ROOT пока TBD') -and ($cardParts[4] -match 'сборок MAVROS для Pi в /work нет')) ''
# ---------- r3 (T47): 18_sostoyanie_sluzhb.cmd, состояние трёх служб после установки образа (только чтение) ----------
Reset-Fake
$r = Run-Cmd '18_sostoyanie_sluzhb.cmd' ''
$svf = @(Get-ChildItem -LiteralPath $r.Out -Filter 'services_check_*.txt' | Where-Object { $_.Name -notmatch 'generated|err|FAILED' }); $svg = @(Get-ChildItem -LiteralPath $r.Out -Filter 'services_check_*.generated.sh')
$svt = ''; if ($svf.Count -eq 1) { $svt = ([IO.File]::ReadAllText($svf[0].FullName)).TrimEnd() }
Check 'V1' '18: все три службы active, ошибок нет: код 0, итог «ВСЕ 3 АКТИВНЫ, ОШИБОК НЕТ», 2 вызова ssh (имя дрона, чтение), файл ответа, последняя строка «# VERDICT OK»' ($r.Code -eq 0 -and $r.Console -match 'ВСЕ 3 АКТИВНЫ, ОШИБОК НЕТ' -and $r.Calls.Count -eq 2 -and $r.Calls[1] -match '<b64:' -and $svf.Count -eq 1 -and $svt -match '# VERDICT OK$') ('code=' + $r.Code + ' calls=' + $r.Calls.Count + ' ' + $r.Console)
Check 'V1' '18: на Pi уходит pi\services_check.sh (метка BB_SVC_MARK), без заглушек, без списков; в вызовах нет sudo, systemctl stop/start/restart, scp' ($svg.Count -eq 1 -and ([IO.File]::ReadAllText($svg[0].FullName)).Contains('BB_SVC_MARK') -and $r.J -notmatch 'sudo|SCP' -and $r.Calls.Count -eq 2) ''
Check 'V1' '18: на экране видны строки SVC и хвост журнала JT' ($r.Console -match 'SVC wifi-manager active' -and $r.Console -match 'JT led-default \|') ''
$cases = @(
    @('wifi-manager не active (inactive)', (New-SvcCanned 'inactive'), 'wifi-manager: служба не active'),
    @('notify-manager failed', (New-SvcCanned 'active' 'failed'), 'notify-manager: служба не active'),
    @('led-default activating', (New-SvcCanned 'active' 'active' 'activating'), 'led-default: служба не active'),
    @('Traceback или ImportError в журнале notify-manager', (New-SvcCanned 'active' 'active' 'active' 0 2), 'notify-manager: в журнале за 10 минут 2 строк'),
    @('led-default перезапускалась сама', (New-SvcCanned 'active' 'active' 'active' 3), 'led-default: служба перезапускалась сама 3 раз'),
    @('журнал wifi-manager недоступен', (New-SvcCanned 'active' 'active' 'active' 0 0 $true), 'wifi-manager: журнал прочитать нельзя')
)
foreach ($case in $cases) {
    Reset-Fake; Set-Canned 'canned_svc.txt' $case[1]
    $r = Run-Cmd '18_sostoyanie_sluzhb.cmd' ''
    $f2 = @(Get-ChildItem -LiteralPath $r.Out -Filter 'services_check_*.txt' | Where-Object { $_.Name -notmatch 'generated|err|FAILED' }); $t2 = ''; if ($f2.Count -eq 1) { $t2 = ([IO.File]::ReadAllText($f2[0].FullName)).TrimEnd() }
    Check 'V2' ('18: «' + $case[0] + '»: код 5, итог «СТОП: ...» с причиной, не «ВСЕ 3 АКТИВНЫ», в файле «# VERDICT NOT_OK»') ($r.Code -eq 5 -and $r.Console -match ('СТОП: .*' + [regex]::Escape($case[2])) -and $r.Console -notmatch 'ВСЕ 3 АКТИВНЫ' -and $t2 -match '# VERDICT NOT_OK$') ('code=' + $r.Code + ' ' + $r.Console)
}
Reset-Fake; Set-Canned 'canned_svc.txt' "SVC wifi-manager active`nSVC_RESTARTS wifi-manager 0`nSVC_JOURNAL wifi-manager lines=1 access=ok`nSVC_ERRORS wifi-manager 0`nBB_SVC_RESULT active=1 errors=0 restarts=0 denied=0`nBB_SVC_DONE`n"
$r = Run-Cmd '18_sostoyanie_sluzhb.cmd' ''
Check 'V2' '18: в ответе только одна служба из трёх: код 5, «СТОП», не «ВСЕ 3 АКТИВНЫ»' ($r.Code -eq 5 -and $r.Console -match 'СТОП: ' -and $r.Console -notmatch 'ВСЕ 3 АКТИВНЫ') ('code=' + $r.Code)
Reset-Fake 'nodone'
$r = Run-Cmd '18_sostoyanie_sluzhb.cmd' ''
Check 'V3' '18: чтение оборвалось (нет BB_SVC_DONE): код 4, файл .FAILED, не «ВСЕ 3 АКТИВНЫ»' ($r.Code -eq 4 -and @(Get-ChildItem -LiteralPath $r.Out -Filter 'services_check_*.FAILED.txt').Count -eq 1 -and $r.Console -notmatch 'ВСЕ 3 АКТИВНЫ') ('code=' + $r.Code)
Reset-Fake 'wrong_host'
$r = Run-Cmd '18_sostoyanie_sluzhb.cmd' ''
Check 'V3' '18: чужой дрон: код 4, службы не читались (один вызов)' ($r.Code -eq 4 -and $r.Calls.Count -eq 1) ('code=' + $r.Code)
Reset-Fake
$r = Run-Cmd '18_sostoyanie_sluzhb.cmd' '' '' 'OTHER-PC'
Check 'V3' '18: чужой ПК: код 4, ssh не вызывался' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake
$sbT = Join-Path $SB 'run_services.ps1'
Check 'V3' '18: файл ответа не перезаписывается (в коде BB-NewOutFile для services_check_<время>.txt)' (([IO.File]::ReadAllText($sbT)) -match "BB-NewOutFile \`$outDir \('services_check_' \+ \`$stamp \+ '\.txt'\)") ''
$cmd18 = [IO.File]::ReadAllText((Join-Path $Kit '18_sostoyanie_sluzhb.cmd')); $ps18 = [IO.File]::ReadAllText((Join-Path $Kit 'run_services.ps1')); $sh18 = [IO.File]::ReadAllText((Join-Path $Kit 'pi\services_check.sh'))
Check 'V4' '18: ни в .cmd, ни в .ps1, ни в .sh нет записи на дрон и остановки служб (sudo, scp, reboot, param set, arming, set_mode, systemctl stop/start/restart/kill, rm, mv)' (-not (($cmd18 + "`n" + $ps18) -match 'sudo|scp |reboot|param set|arming|set_mode|systemctl\s+(stop|start|restart|kill)') -and -not (($sh18 -split "`n" | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n" -match '(^|[\s;|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|reboot)\s')) ''
# карточка замера рулеткой (r3)
$cardR = [IO.File]::ReadAllText((Join-Path $Kit 'cards\КАРТОЧКА_ЗАМЕРА_РУЛЕТКОЙ.md'))
Check 'V5' 'карточка замера рулеткой: ТОЛЬКО ЧТЕНИЕ, батарея ОТКЛЮЧЕНА, пропеллеры СНЯТЫ, «Для цели: шаг 10», EKF2_RNG_POS_Z = 0,10 (владелец считает «скорее всего неверно»), линза дальномера, пол, центр контроллера, камера' ($cardR -match 'ТОЛЬКО ЧТЕНИЕ' -and $cardR -match 'Батарея — ОТКЛЮЧЕНА' -and $cardR -match 'Пропеллеры — СНЯТЫ' -and $cardR -match 'Для цели: шаг 10' -and $cardR -match 'EKF2_RNG_POS_Z' -and $cardR -match '0,10' -and $cardR -match 'скорее всего неверно' -and $cardR -match 'линз' -and $cardR -match 'центр' -and $cardR -match 'пол' -and $cardR -match '(?i)камер') ''
Check 'V5' 'карточка замера рулеткой: в шаблоне карточки (Зачем, Сделайте, Где, После шага, Что будет, Ждать, Если не так, Что меняется на дроне), ничего не меняется на дроне, в QGC ничего не нажимать/менять' ((@('Зачем', 'Сделайте', 'Где', 'После шага', 'Что будет', 'Ждать', 'Если не так', 'Что меняется на дроне') | Where-Object { $cardR -notmatch ('\*\*' + $_) }).Count -eq 0 -and $cardR -match 'Что меняется на дроне:\*\* ничего' -and $cardR -match 'Менять настройки в QGC вам не нужно') ''
# порядок со сборками и 18
$ordR = [IO.File]::ReadAllText((Join-Path $Kit 'cards\ПОРЯДОК_СО_СБОРКАМИ.md'))
Check 'V5' 'ПОРЯДОК_СО_СБОРКАМИ.md: после установки образа и включения шаг 18_sostoyanie_sluzhb.cmd (только чтение) и карточка замера рулеткой упомянуты' ($ordR -match '18_sostoyanie_sluzhb\.cmd' -and $ordR -match 'КАРТОЧКА_ЗАМЕРА_РУЛЕТКОЙ') ''
# файлы набора в песочнице вне tests не менялись тестами
# r11 (16.11): takeoff.conf под пример карты real - flight_marker.py 28992fe4…; flight.py r2j - в takeoff_presets\r2j_flight.conf (тесты r11 P2-P6)
Check 'Z1' 'настоящие takeoff.conf и gates\ набора: r11 - flight_marker.py КАРТЫ REAL ИЗ ОВЕРЛЕЯ (путь /home/lb/bench_ws/r2j/..., sha256 28992fe4… (0,9 м), DRONE_PY_SHA256 fa6abf8b…, аргументов нет, пометка «ВЛАДЕЛЕЦ ПОДТВЕРЖДАЕТ»), TAKEOFF_APPROVED.txt нет' (([IO.File]::ReadAllText((Join-Path $Kit 'takeoff.conf'))) -match '(?m)^SCRIPT_REMOTE_PATH=/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/flight_marker\.py\s*$' -and ([IO.File]::ReadAllText((Join-Path $Kit 'takeoff.conf'))) -match '(?m)^SCRIPT_SHA256=28992fe4df6bb404a2d403e001b0f2e8e6a3985c4d5a0681dd6d441b97c0ed7a\s*$' -and ([IO.File]::ReadAllText((Join-Path $Kit 'takeoff.conf'))) -match '(?m)^DRONE_PY_SHA256=fa6abf8b545b356ecdd5291417625ee77b58ef862fe7f3b00486dc8ef72d0c9c\s*$' -and ([IO.File]::ReadAllText((Join-Path $Kit 'takeoff.conf'))) -match '(?m)^SCRIPT_ARGS=\s*$' -and ([IO.File]::ReadAllText((Join-Path $Kit 'takeoff.conf'))) -match 'ВЛАДЕЛЕЦ ПОДТВЕРЖДАЕТ' -and -not (Test-Path (Join-Path $Kit 'gates\TAKEOFF_APPROVED.txt'))) ''
$env:PATH = $oldPath; $env:COMPUTERNAME = $realPc
Note ''
Note ('ИТОГ: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
