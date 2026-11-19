# run_tests_r6.ps1 (Claude, 12.11.2026, набор r6) - тесты НОВЫХ шагов r6 на ПК в песочнице. К дрону не подключается: вместо ssh и scp стоят подделки
# fake_ssh_r6.exe и fake_scp_r6.exe (первые в PATH; сеть не открывают). Скрипты Pi здесь не исполняются (их проверяет run_tests_r6_pi.sh в WSL):
# подделка ssh отдаёт заготовленные ответы «дрона» и сохраняет посланные скрипты (sent_*.sh), чтобы проверить, ЧТО ушло бы на Pi.
# Проверяется: первая строка (ТОЛЬКО ЧТЕНИЕ / МЕНЯЕТ ДРОН: что, зачем, как вернуть), проверка имени ПК и дрона, отказ без разрешения, одноразовость разрешений,
# отказ перезаписи, разбор ответов и итоговые коды, нет pgrep -f / pkill и паролей ни в файлах, ни в посланных скриптах, порядок вызовов.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_r6_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0; $script:seq = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') {
    if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") }
}
$realPc = $env:COMPUTERNAME
if ($realPc -ne 'DESKTOP-H5CPN8E') { Note ('ВНИМАНИЕ: имя ПК ' + $realPc + ', тесты рассчитаны на DESKTOP-H5CPN8E') }

# ---------- песочница ----------
$SB = Join-Path $Run 'sb\bench_kit_r6'
New-Item -ItemType Directory -Path $SB -Force | Out-Null
Get-ChildItem -LiteralPath $Kit -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($Kit.Length + 1)
    if ($rel -like 'tests\*' -or $rel -like 'out\*' -or $rel -eq 'SHA256SUMS.txt') { return }
    $dest = Join-Path $SB $rel; New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $dest
}
# в песочнице у cmd с set /p убрана строка chcp 65001 (она мешает set /p читать из файла; только в тесте, в боевых файлах она на месте)
$setp = @('21_kamera_K1_raskladka.cmd', '22_kamera_cena_A_C_A2.cmd', '23a_sys_fwupd_mask.cmd', '23a_otkat_fwupd_mask.cmd', '23b_sys_snap_hold.cmd', '23b_otkat_snap_hold.cmd', '23c_sys_taimery_mask.cmd', '23c_otkat_taimery_mask.cmd', 'image_r2j_cam\05c_install_r2j_cam.cmd', 'image_r2j_cam\06c_otkat_r2j_cam.cmd', '_aside\image_r2j_camera_variant_dabd5076_r5\05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd')
foreach ($n in $setp) {
    $pp = Join-Path $SB $n
    $ls = [IO.File]::ReadAllText($pp) -split "`r`n"
    [IO.File]::WriteAllText($pp, (($ls | Where-Object { $_ -ne 'chcp 65001 >nul' }) -join "`r`n"), $utf8n)
}
$FakeDir = Join-Path $Run 'fake'; New-Item -ItemType Directory -Path $FakeDir | Out-Null
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_ssh_r6.cs'))) -OutputAssembly (Join-Path $FakeDir 'ssh.exe') -OutputType ConsoleApplication
Add-Type -TypeDefinition ([IO.File]::ReadAllText((Join-Path $T 'fake_scp_r6.cs'))) -OutputAssembly (Join-Path $FakeDir 'scp.exe') -OutputType ConsoleApplication
$oldPath = $env:PATH; $env:PATH = $FakeDir + ';' + $oldPath
$env:BB_NO_PAUSE = '1'
$Can = Join-Path $Run 'canned'; New-Item -ItemType Directory -Path $Can | Out-Null

function Reset-Fake([string]$mode = 'normal') {
    Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Extension -ne '.exe' -and $_.Extension -ne '.pdb' } | Remove-Item
    [IO.File]::WriteAllText((Join-Path $FakeDir 'mode.txt'), $mode)
}
function Set-Canned([string]$key, [string[]]$texts, [int]$rc = 0) {
    $paths = @()
    $i = 0
    foreach ($t in $texts) { $i++; $p = Join-Path $Can ($key + '_' + [guid]::NewGuid().ToString('N').Substring(0, 8) + '.txt'); [IO.File]::WriteAllText($p, ($t -replace "`r`n", "`n"), $utf8n); $paths += $p }
    [IO.File]::WriteAllText((Join-Path $FakeDir ('canned_' + $key + '.txt')), ($paths -join '|'))
    if ($rc -ne 0) { [IO.File]::WriteAllText((Join-Path $FakeDir ('rc_' + $key + '.txt')), [string]$rc) }
}
function New-Out([string]$name = '') { if ($name -eq '') { $name = 'out_' + [guid]::NewGuid().ToString('N').Substring(0, 6) }; $o = Join-Path $Run $name; New-Item -ItemType Directory -Path $o -Force | Out-Null; return $o }
function Read-Calls { $cl = Join-Path $FakeDir 'calls.log'; if (Test-Path $cl) { return @(Get-Content -LiteralPath $cl -Encoding UTF8) } else { return @() } }
function Sent-Scripts { return @(Get-ChildItem -LiteralPath $FakeDir -Filter 'sent_*.sh' -File | Sort-Object { [int]($_.BaseName -replace 'sent_', '') } | ForEach-Object { [IO.File]::ReadAllText($_.FullName) }) }
# перед каждым запуском: журнал вызовов, посланные скрипты и счётчики очередей ответов подделки - с нуля (заготовки ответов и режим остаются)
function Clear-Run { Get-ChildItem -LiteralPath $FakeDir -File | Where-Object { $_.Name -eq 'calls.log' -or $_.Name -eq 'sent_count.txt' -or $_.Name -like 'sent_*.sh' -or $_.Name -like 'count_*.txt' } | Remove-Item }
function Run-Cmd([string]$cmdRel, [string]$stdin, [string]$out, [string]$pc = $realPc, [hashtable]$envx = @{}) {
    Clear-Run
    $script:seq++
    $id = 'r' + $script:seq
    $env:BB_KIT_OUT = $out
    foreach ($k in $envx.Keys) { Set-Item -Path ('env:' + $k) -Value $envx[$k] }
    $inFile = Join-Path $Run ($id + '_stdin.txt'); [IO.File]::WriteAllText($inFile, $stdin)
    $env:COMPUTERNAME = $pc
    $so = Join-Path $Run ($id + '_console.txt')
    $cmdPath = Join-Path $SB $cmdRel
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList ('/c ""' + $cmdPath + '" < "' + $inFile + '""') -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $env:COMPUTERNAME = $realPc
    foreach ($k in $envx.Keys) { Remove-Item -Path ('env:' + $k) -ErrorAction SilentlyContinue }
    $calls = Read-Calls
    $con = ''; if (Test-Path $so) { $con = [IO.File]::ReadAllText($so) }
    return @{ Code = $p.ExitCode; Calls = @($calls); J = ($calls -join "`n"); Console = $con; Sent = @(Sent-Scripts) }
}
function Run-Ps([string]$ps1Rel, [string]$argLine, [string]$out, [string]$pc = $realPc) {
    Clear-Run
    $script:seq++
    $id = 'p' + $script:seq
    $env:BB_KIT_OUT = $out
    $env:COMPUTERNAME = $pc
    $so = Join-Path $Run ($id + '_console.txt')
    $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $SB $ps1Rel) + '" ' + $argLine) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err')
    $env:COMPUTERNAME = $realPc
    $calls = Read-Calls
    $con = ''; if (Test-Path $so) { $con = [IO.File]::ReadAllText($so) }
    return @{ Code = $p.ExitCode; Calls = @($calls); J = ($calls -join "`n"); Console = $con; Sent = @(Sent-Scripts) }
}
function Files([string]$dir, [string]$filter) { return @(Get-ChildItem -LiteralPath $dir -File -Filter $filter -ErrorAction SilentlyContinue | Sort-Object LastWriteTime) }
function LastLine([string]$p) { $l = @([IO.File]::ReadAllLines($p) | Where-Object { $_.Trim() -ne '' }); if ($l.Count) { return $l[-1].Trim() } else { return '' } }
function Gate([string]$path, [string]$id, [string[]]$extra = @(), [string]$drop = '') {
    $lines = @(('ПРАВКА=' + $id), 'ВЛАДЕЛЕЦ_СКАЗАЛ=да', 'ДАТА=2026-11-13 10:00', 'СЛОВА_ВЛАДЕЛЬЦА=тест (в песочнице; настоящий файл создаёт только чат 1)', 'СОЗДАЛ=чат 1') + $extra
    if ($drop) { $lines = @($lines | Where-Object { -not $_.StartsWith($drop) }) }
    New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
    [IO.File]::WriteAllText($path, (($lines -join "`r`n") + "`r`n"), $utf8)
}
function NoGate([string]$path) { if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path } }
$G = Join-Path $SB 'gates'

# ======================= S: статические проверки новых файлов =======================
$newCmd = @('19_nagruzka_pi.cmd', '20_nichego_ne_otvalilos.cmd', '21_kamera_K1_raskladka.cmd', '22_kamera_cena_A_C_A2.cmd', '23a_sys_fwupd_mask.cmd', '23a_otkat_fwupd_mask.cmd', '23b_sys_snap_hold.cmd', '23b_otkat_snap_hold.cmd', '23c_sys_taimery_mask.cmd', '23c_otkat_taimery_mask.cmd', '24a_proverka_kamery_polnye_stroki.cmd', '24b_proverka_kamery_r2j.cmd', '09c_sverka_install_r2j_cam.cmd', '15c_otpechatki_r2j_cam.cmd', 'image_r2j_cam\05c_install_r2j_cam.cmd', 'image_r2j_cam\06c_otkat_r2j_cam.cmd')
$readOnly = @('19_nagruzka_pi.cmd', '20_nichego_ne_otvalilos.cmd', '24a_proverka_kamery_polnye_stroki.cmd', '24b_proverka_kamery_r2j.cmd', '09c_sverka_install_r2j_cam.cmd', '15c_otpechatki_r2j_cam.cmd')
$gateOf = @{ '21_kamera_K1_raskladka.cmd' = 'CAM_K1_APPROVED.txt'; '22_kamera_cena_A_C_A2.cmd' = 'CAM_COST_APPROVED.txt'; '23a_sys_fwupd_mask.cmd' = 'SYS_FWUPD_MASK_APPROVED.txt'; '23a_otkat_fwupd_mask.cmd' = 'OTKAT_SYS_FWUPD_APPROVED.txt'; '23b_sys_snap_hold.cmd' = 'SYS_SNAP_HOLD_APPROVED.txt'; '23b_otkat_snap_hold.cmd' = 'OTKAT_SYS_SNAP_HOLD_APPROVED.txt'; '23c_sys_taimery_mask.cmd' = 'SYS_TIMERS_MASK_APPROVED.txt'; '23c_otkat_taimery_mask.cmd' = 'OTKAT_SYS_TIMERS_APPROVED.txt'; 'image_r2j_cam\05c_install_r2j_cam.cmd' = 'R2J_CAM_APPROVED.txt'; 'image_r2j_cam\06c_otkat_r2j_cam.cmd' = 'OTKAT_R2J_CAM_APPROVED.txt' }
foreach ($c in $newCmd) {
    $p = Join-Path $Kit $c
    $b = [IO.File]::ReadAllBytes($p)
    $txt = (New-Object Text.UTF8Encoding($false, $true)).GetString($b)
    $crlf = ([regex]::Matches($txt, "`r`n")).Count; $lf = ([regex]::Matches($txt, "`n")).Count
    Check 'S1' ($c + ': UTF-8 без BOM, все строки CRLF') ($b[0] -ne 0xEF -and $crlf -eq $lf -and $crlf -gt 5) ('crlf=' + $crlf + ' lf=' + $lf)
    $ln = $txt -split "`r`n"
    Check 'S2' ($c + ': строки 1-2 @echo off и chcp 65001') ($ln[0] -ceq '@echo off' -and $ln[1] -ceq 'chcp 65001 >nul') ''
    if ($readOnly -contains $c) { Check 'S3' ($c + ': первая строка «ТОЛЬКО ЧТЕНИЕ:»') ($ln[2].StartsWith('echo ТОЛЬКО ЧТЕНИЕ: ')) $ln[2] }
    else { Check 'S3' ($c + ': первая строка «МЕНЯЕТ ДРОН:» с «Зачем» и «Как вернуть»') ($ln[2].StartsWith('echo МЕНЯЕТ ДРОН: ') -and $ln[2] -match 'Зачем' -and $ln[2] -match 'Как вернуть') $ln[2] }
    Check 'S4' ($c + ': в первой строке нет < > | & ^ %') ($ln[2] -notmatch '[<>|&^%]') $ln[2]
    Check 'S5' ($c + ': проверка имени ПК DESKTOP-H5CPN8E') ($txt -match 'if /i not "%COMPUTERNAME%"=="DESKTOP-H5CPN8E"') ''
    if ($gateOf.ContainsKey($c)) { Check 'S6' ($c + ': до вопросов проверяет файл-разрешение gates\' + $gateOf[$c]) ($txt -match ('if not exist "gates\\' + [regex]::Escape($gateOf[$c]) + '"')) '' }
}
$codeFiles = @(Get-ChildItem -LiteralPath $Kit -Recurse -File | Where-Object { $_.FullName -notmatch '\\tests\\run_|\\out\\' -and $_.Extension -in '.sh', '.ps1', '.cmd', '.py', '.cs' })
$r5sums = @{}
foreach ($l in [IO.File]::ReadAllLines((Join-Path (Split-Path $Kit) 'bench_kit_20261112_r5\SHA256SUMS.txt'))) { if ($l.Length -gt 66) { $r5sums[$l.Substring(66)] = $l.Substring(0, 64) } }
# r8 (13.11): params_check\ - принятая сверка kit_20261109_r4 (адрес дрона в run_params_check.ps1 по замыслу) + params_read.sh v3; её проверяют тесты r8 (V), здесь она не «новый файл r6»
$newFiles = @($codeFiles | Where-Object { -not $r5sums.ContainsKey(($_.FullName.Substring($Kit.Length + 1) -replace '\\', '/')) -and $_.FullName -notmatch '\\_aside\\' -and $_.FullName -notmatch '\\params_check\\' })
$pg = @(); $pgf = @()
foreach ($f in $codeFiles) {
    $i = 0; $rel = $f.FullName.Substring($Kit.Length + 1)
    foreach ($l in [IO.File]::ReadAllLines($f.FullName)) {
        $i++; $t = $l.Trim()
        if ($t.StartsWith('#') -or $t.StartsWith('//') -or $t -match '^(?i)(rem|echo|@echo) ' -or $t -match '^\s*"""') { continue }
        if ($t -match '\bpgrep\b|\bpkill\b|killall' -and $newFiles.FullName -contains $f.FullName) { $pg += ($rel + ':' + $i) }
        if ($t -match '\b(pgrep|pkill)\s+-[A-Za-z]*f') { $pgf += $rel }
    }
}
Check 'S7' ('в коде новых файлов r6 (' + $newFiles.Count + ') нет pgrep, pkill, killall вне комментариев') ($pg.Count -eq 0) ($pg -join ', ')
$pgfu = @($pgf | Sort-Object -Unique)
$refs = @($codeFiles | Where-Object { $_.FullName -notmatch '\\mavros_build\\pi_kit\\' -and ([IO.File]::ReadAllText($_.FullName) -match 'm5_check74') })
Check 'S7b' ('во всём наборе pgrep/pkill с -f есть только в принятом pi_kit rc3 (m5_check74_rc3.sh), и ни один шаг набора его не запускает') ($pgfu.Count -eq 1 -and $pgfu[0] -ceq 'image_r2j\mavros_build\pi_kit\m5_check74_rc3.sh' -and $refs.Count -eq 0) (($pgfu -join ', ') + ' ссылки: ' + (($refs | ForEach-Object { $_.Name }) -join ', '))
$sec = @()
foreach ($f in $newFiles) {
    $t = [IO.File]::ReadAllText($f.FullName)
    if ($t -match '10\.255\.254\.26|lb@10\.') { $sec += ($f.Name + ': адрес дрона') }
    if ($t -match '(?i)(password|passwd|psk)\s*=\s*\S{3,}' -and $f.Name -notmatch '^(run_tests_r6|r6_)') { $sec += ($f.Name + ': пароль?') }
    if ($t -match '-----BEGIN [A-Z ]*PRIVATE KEY-----' -or $t -match 'ssh-(rsa|ed25519) AAAA') { $sec += ($f.Name + ': ключ') }
    if ($t -match '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}') { $sec += ($f.Name + ': адрес почты?') }
    if ($t -match 'sudo\s+-S|echo\s+\S+\s*\|\s*sudo') { $sec += ($f.Name + ': пароль в sudo через stdin') }
}
Check 'S8' ('в новых файлах r6 (' + $newFiles.Count + ') нет адреса дрона, паролей, ключей, адресов почты, sudo -S') ($sec.Count -eq 0) ($sec -join '; ')
$ro = @('r6_pi_load.sh', 'r6_sys_check.sh', 'r6_cam_incoming.sh', 'r6_cost_end.sh', 'r6_cam_precheck.sh', 'r6_cam_verify.sh')
foreach ($n in $ro) {
    $t = [IO.File]::ReadAllText((Join-Path $Kit ('pi\' + $n)))
    $code = (($t -split "`n") | Where-Object { -not $_.Trim().StartsWith('#') }) -join "`n"
    $w = @([regex]::Matches($code, '(?<![0-9&<-])>{1,2}\s*(?!/dev/null|&)\S') | ForEach-Object { $_.Value })
    Check 'S9' ('pi\' + $n + ': первая строка-комментарий ТОЛЬКО ЧТЕНИЕ, проверка hostname, нет sudo, rm, mv, cp, mkdir, tee, systemctl start/stop/mask, записи > в файл') ($t -match '(?m)^# ТОЛЬКО ЧТЕНИЕ' -and $t -match '\[ "\$\(hostname\)" = "bumblebee-20ec" \]' -and $code -cnotmatch '\bsudo\b|\brm\s|\bmv\s|\bcp\s|\bmkdir\b|\btee\b|systemctl (start|stop|restart|mask|unmask|enable|disable)' -and $w.Count -eq 0) ($w -join ' ')
}
foreach ($n in 'r6_k1.sh', 'r6_cost_phase.sh', 'r6_sys_change.sh', 'r6_cam_mkdir.sh') {
    $t = [IO.File]::ReadAllText((Join-Path $Kit ('pi\' + $n)))
    Check 'S10' ('pi\' + $n + ': первая строка-комментарий МЕНЯЕТ ДРОН, проверка hostname') ($t -match '(?m)^# МЕНЯЕТ ДРОН' -and $t -match '\[ "\$\(hostname\)" = "bumblebee-20ec" \]') ''
}
$k1t = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_k1.sh')); $cpt = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_cost_phase.sh'))
Check 'S11' 'r6_k1.sh и r6_cost_phase.sh: отказ, если папка результата уже есть («ничего не перезаписываю»)' ($k1t -match 'уже есть, ничего не перезаписываю' -and $cpt -match 'уже есть \$f, ничего не перезаписываю') ''
Check 'S12' 'r6_cost_phase.sh: детектор через ~/opencv47_venv/bin/python3, все выходы детектора в /bench, gate_by_flight_state:=false, timeout не больше 240 с' ($cpt -match 'VENV="\$HOME/opencv47_venv/bin/python3"' -and $cpt -match 'timeout -s INT 230 "\$VENV"' -and $cpt -match '-r markers:=/bench/aruco_detect/markers' -and $cpt -match '-r /aruco_detect/markers_used:=/bench/aruco_detect/markers_used' -and $cpt -match '-r /aruco_detect/yaw_locked:=/bench/aruco_detect/yaw_locked' -and $cpt -match '-r /tf:=/bench/tf' -and $cpt -match '-r map_pose:=/bench/aruco_map/pose' -and $cpt -match 'gate_by_flight_state:=false' -and -not ([regex]::Matches($cpt, 'timeout -s INT (\d+)') | Where-Object { [int]$_.Groups[1].Value -gt 240 })) ''
$lt = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_pi_load.sh')); $sct = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_sys_check.sh'))
$lsc = ((($lt + "`n" + $sct) -split "`n") | Where-Object { -not $_.Trim().StartsWith('#') }) -join "`n"
Check 'S13' 'r6_pi_load.sh и r6_sys_check.sh (код без комментариев): ros2 только с --no-daemon, нет ros2 topic hz, нет --selftest, /tmp/bumblebee.log не читают' (@([regex]::Matches($lsc, 'ros2 (topic|node) [^\r\n]*') | Where-Object { $_.Value -notmatch '--no-daemon' }).Count -eq 0 -and @([regex]::Matches($lsc, 'ros2 (topic|node) ')).Count -ge 3 -and $lsc -notmatch 'topic hz' -and $lsc -notmatch '--selftest' -and $lsc -notmatch 'bumblebee\.log') ''
Check 'S14' 'r6_pi_load.sh: pidstat -u -r -h -l 5 24, snap refresh --time, list-timers --all, apt-config dump periodic, journalctl -b -k set_power_mgmt, MainPID служб, регулятор частоты' ($lt -match 'pidstat -u -r -h -l 5 24' -and $lt -match 'snap refresh --time' -and $lt -match 'systemctl list-timers --all' -and $lt -match 'apt-config dump 2>/dev/null \| grep -i periodic' -and $lt -match 'journalctl -b -k' -and $lt -match 'set_power_mgmt' -and $lt -match 'systemctl show -p MainPID --value' -and $lt -match 'scaling_governor') ''
$st = [IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_sys_change.sh'))
$sudoBare = @([regex]::Matches($st, '(?m)(^|[;&|({]|\bthen|\bdo|\belse)\s*sudo\b(?! -p "\$P")'))
Check 'S15' 'r6_sys_change.sh: mask --now, unmask, snap --hold/--unhold, каждый sudo только с -p и подсказкой, кончающейся переводом строки' ($st -match 'sudo -p "\$P" systemctl mask --now \$UNITS' -and $st -match 'sudo -p "\$P" systemctl unmask \$UNITS' -and $st -match 'sudo -p "\$P" snap refresh --hold' -and $st -match 'sudo -p "\$P" snap refresh --unhold' -and $st.Contains('P=$''SYS_SUDO_PROMPT ') -and $st.Contains('потом Enter:\n''') -and $sudoBare.Count -eq 0) ('без -p: ' + $sudoBare.Count)
# правка 1 проверки RV (12.11): пароль sudo не должен попасть на экран и в out\sys_*.log, если его набрали раньше подсказки (ssh -tt отражает набранное)
$stl = [IO.File]::ReadAllLines((Join-Path $Kit 'pi\r6_sys_change.sh'))
$mi = [Array]::IndexOf($stl, '# BB_R6SYS_MARK'); $si = -1
for ($i = 0; $i -lt $stl.Count; $i++) { if ($stl[$i] -match '^\s*[^#\s].*\bsudo -p ') { $si = $i; break } }
Check 'S15b' 'r6_sys_change.sh: сразу после # BB_R6SYS_MARK эхо терминала выключается (stty -echo, если ввод - терминал), trap возвращает его при любом выходе; это раньше первого sudo' ($mi -ge 0 -and ($mi + 1) -lt $stl.Count -and $stl[$mi + 1] -ceq "if [ -t 0 ]; then stty -echo 2>/dev/null; trap 'stty echo 2>/dev/null' EXIT; fi" -and $si -gt ($mi + 1) -and @($stl | Where-Object { $_ -match 'stty -echo' -and $_ -notmatch '^\s*#' }).Count -eq 1) ('метка=' + $mi + ' первый sudo=' + $si)
$rsl = [IO.File]::ReadAllLines((Join-Path $Kit 'run_r6_sys.ps1')); $fli = -1; $sshi = -1
for ($i = 0; $i -lt $rsl.Count; $i++) { if ($fli -lt 0 -and $rsl[$i] -ceq 'try { $Host.UI.RawUI.FlushInputBuffer() } catch { }') { $fli = $i }; if ($sshi -lt 0 -and $rsl[$i].StartsWith('& $ssh.Source @argv')) { $sshi = $i } }
$cardR6 = [IO.File]::ReadAllText((Join-Path $Kit 'cards\КАРТОЧКИ_r6.md'))
Check 'S15c' 'run_r6_sys.ps1: буфер ввода окна очищается прямо перед ssh -tt; в окне и в карточке С1–С3: «до строки SYS_SUDO_PROMPT ничего не набирать»' ($fli -ge 0 -and $sshi -eq ($fli + 1) -and ($rsl -join "`n").Contains('До строки SYS_SUDO_PROMPT ничего не набирайте.') -and $cardR6.Contains('до строки `SYS_SUDO_PROMPT` ничего не набирать')) ('flush=' + $fli + ' ssh=' + $sshi)
$fr5 = @(); foreach ($k in $r5sums.Keys) { $p = Join-Path $Kit ($k -replace '/', '\'); if ((Test-Path -LiteralPath $p) -and $k -notin 'README.md', 'PROGRESS.md', 'tests/run_tests_image.ps1', 'tests/run_tests_bench.ps1', '01_snimok_do.cmd', '07_vzlet_zagotovka.cmd') { if ((Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() -ne $r5sums[$k]) { $fr5 += $k } } }
Check 'S16' 'все файлы r5 в r6 байт в байт как в r5, кроме README.md, PROGRESS.md и тестов tests\run_tests_image.ps1 и run_tests_bench.ps1 (правка под перенос 05v и новые .cmd); r8: и 01, 07 (params_check этого набора, v3)' ($fr5.Count -eq 0) ($fr5 -join ', ')
$moved = @($r5sums.Keys | Where-Object { $_ -like 'image_r2j/camera_variant_dabd5076/*' })
$movedOk = @($moved | Where-Object { $p = Join-Path $Kit ('_aside\image_r2j_camera_variant_dabd5076_r5\' + ($_.Substring('image_r2j/camera_variant_dabd5076/'.Length) -replace '/', '\')); (Test-Path -LiteralPath $p) -and (Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLower() -eq $r5sums[$_] })
Check 'S17' ('05v r5 перенесён в _aside целиком и байт в байт (' + $moved.Count + ' файлов), в image_r2j его больше нет') ($moved.Count -eq 6 -and $movedOk.Count -eq 6 -and -not (Test-Path -LiteralPath (Join-Path $Kit 'image_r2j\camera_variant_dabd5076'))) ''

# ======================= L: 19 нагрузка Pi =======================
$loadOk = "LOAD_DATE 2026-11-13 10:00:00 +0400`nLOAD_LOADAVG 2.80 2.90 1.50`nLOAD_TEMP temp=48.0'C`nLOAD_THROTTLED throttled=0x0`nLOAD_GOVERNOR cpu0 governor=ondemand cur_khz=2400000 min_khz=1500000 max_khz=2400000`nLOAD_WIFI_PS_JOURNAL access=ok last=disabled`nLOAD_RELIABLE /mavros/mavros/pose_reliable publishers=1 subscribers=1`nLOAD_NODE /mavros`nLOAD_TIMER NEXT LEFT`nPS5 # Time UID PID %usr %system %guest %wait %CPU CPU minflt/s majflt/s VSZ RSS %MEM Command`nPS5 10:00:05 1000 1839 20.0 5.0 0.0 0.0 25.0 1 0.0 0.0 1 1 0.1 mavros_node`nLOAD_PIDSTAT done`nBB_R6LOAD_DONE`n"
Reset-Fake; Set-Canned 'load' @($loadOk); $o = New-Out
$r = Run-Cmd '19_nagruzka_pi.cmd' '' $o
$f = Files $o 'pi_load_*.txt' | Where-Object { $_.Name -notmatch 'err|FAILED' }
Check 'L1' '19: код 0, файл out\pi_load_*.txt с BB_R6LOAD_DONE, сначала проверка имени дрона, потом скрипт с меткой load' ($r.Code -eq 0 -and $f.Count -eq 1 -and ([IO.File]::ReadAllText($f[0].FullName) -match 'BB_R6LOAD_DONE') -and $r.Calls.Count -eq 2 -and $r.Calls[0] -match 'HOST_OK' -and $r.Calls[1] -match 'key=load') ('code=' + $r.Code + ' ' + $r.J)
Check 'L2' '19: посланный скрипт = pi\r6_pi_load.sh (тот же текст), в нём нет sudo' ($r.Sent.Count -eq 1 -and $r.Sent[0] -ceq ([IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_pi_load.sh')) -replace "`r`n", "`n") -and $r.Sent[0] -notmatch '(?m)^[^#]*\bsudo\b') ''
Reset-Fake 'wrong_host'; Set-Canned 'load' @($loadOk); $o = New-Out
$r = Run-Cmd '19_nagruzka_pi.cmd' '' $o
Check 'L3' '19: чужой дрон: код 4, скрипт не послан' ($r.Code -eq 4 -and $r.Calls.Count -eq 1 -and $r.Sent.Count -eq 0) ('code=' + $r.Code)
Reset-Fake; $o = New-Out
$r = Run-Cmd '19_nagruzka_pi.cmd' '' $o 'OTHER-PC'
Check 'L4' '19: чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Reset-Fake 'nodone'; Set-Canned 'load' @("LOAD_DATE x`n"); $o = New-Out
$r = Run-Cmd '19_nagruzka_pi.cmd' '' $o
Check 'L5' '19: ответ без конца: код 4, файл переименован в .FAILED.txt' ($r.Code -eq 4 -and (Files $o '*FAILED*').Count -eq 1) ('code=' + $r.Code)
Reset-Fake; Set-Canned 'load' @($loadOk); $o = New-Out
[IO.File]::WriteAllText((Join-Path $o 'pi_load_20261113_100000.txt'), 'старый файл')
$r = Run-Ps 'run_r6_load.ps1' '-Stamp 20261113_100000' $o
Check 'L6' '19: файл с той же меткой уже есть: код 4, не перезаписан, к дрону не обращались' ($r.Code -eq 4 -and ([IO.File]::ReadAllText((Join-Path $o 'pi_load_20261113_100000.txt')) -ceq 'старый файл') -and $r.Calls.Count -eq 0) ('code=' + $r.Code + ' calls=' + $r.Calls.Count)

# ======================= C: 20 ничего не отвалилось =======================
function New-Sc([string]$boot = 'b1', [int]$failed = 0, [hashtable]$svc = @{}, [string]$wifi = 'disabled', [string]$iw = 'off', [string[]]$nodes = @('/mavros', '/mavros/mavros', '/aruco_detect', '/transform_listener_impl_X'), [hashtable]$step1 = @{}, [string]$snap = 'none', [hashtable]$jerr = @{}, [int]$nodesRc = 0) {
    $t = "SC_DATE 2026-11-13 10:00:00 +0400`nSC_BOOT_ID $boot`nSC_UPTIME_S 600.0`nSC_FAILED_COUNT $failed`n"
    for ($i = 0; $i -lt $failed; $i++) { $t += "SC_FAILED x$i.service loaded failed failed X`n" }
    $em = 1000000
    foreach ($s in 'bumblebee', 'wifi-manager', 'wifi-watchdog', 'notify-manager', 'avahi-daemon', 'NetworkManager', 'sys_metrics') {
        $em += 1000
        $line = "SC_SVC $s load=loaded active=active sub=running nrestarts=0 mainpid=100 enter_mono=$em"
        if ($svc.ContainsKey($s)) { $line = $svc[$s] }
        $t += $line + "`n"
        $je = "SC_JERR $s errors=0 access=ok"; if ($jerr.ContainsKey($s)) { $je = $jerr[$s] }
        $t += $je + "`n"
    }
    $t += "SC_INFO led-default enabled=disabled active=inactive nrestarts=0`n"
    if ($wifi -ne '') { $t += "SC_WIFI journal=$wifi`n" }
    $t += "SC_WIFI_IW $iw`n"
    foreach ($u in 'fwupd-refresh.timer', 'man-db.timer', 'motd-news.timer', 'update-notifier-download.timer', 'update-notifier-motd.timer') { $v = 'enabled=enabled active=active'; if ($step1.ContainsKey($u)) { $v = $step1[$u] }; $t += "SC_STEP1 $u $v`n" }
    $t += "SC_STEP1 snap hold=$snap`nSC_NODES_RC $nodesRc`n"
    foreach ($n in $nodes) { $t += "SC_NODE $n`n" }
    $t += "SC_PS # Time UID PID %usr %system %guest %wait %CPU CPU Command`nSC_PS 10:00:05 1000 1839 20.0 5.0 0.0 0.0 25.0 1 mavros_node`nBB_R6SC_DONE`n"
    return $t
}
$OC = New-Out 'out_sc'
function Run-Sc([string]$text, [string]$stamp, [string]$out = $OC) { Reset-Fake; Set-Canned 'sc' @($text); return Run-Ps 'run_r6_syscheck.ps1' ('-Stamp ' + $stamp) $out }
function ScFile([string]$stamp, [string]$out = $OC) { return (Join-Path $out ('sys_check_' + $stamp + '.txt')) }
$r = Run-Sc (New-Sc) '20261113_100001'
Check 'C1' '20: первый запуск (нет «до»): код 0, VERDICT OK, BASELINE нет' ($r.Code -eq 0 -and (LastLine (ScFile '20261113_100001')) -ceq '# VERDICT OK' -and ([IO.File]::ReadAllText((ScFile '20261113_100001')) -match '# BASELINE нет')) ('code=' + $r.Code + ' ' + $r.Console)
Start-Sleep -Milliseconds 1100
$r = Run-Sc (New-Sc) '20261113_100002'
Check 'C2' '20: второй запуск как «до»: код 0, BASELINE = первый файл' ($r.Code -eq 0 -and ([IO.File]::ReadAllText((ScFile '20261113_100002')) -match '# BASELINE sys_check_20261113_100001.txt')) ('code=' + $r.Code)
$r = Run-Sc (New-Sc -failed 1) '20261113_100003'
Check 'C3' '20: Ч1 failed не пуст: код 5, WHY Ч1, VERDICT NOT_OK' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100003')) -match '# WHY Ч1') -and (LastLine (ScFile '20261113_100003')) -ceq '# VERDICT NOT_OK') ('code=' + $r.Code)
Start-Sleep -Milliseconds 1100
$r = Run-Sc (New-Sc) '20261113_100004'
Check 'C4' '20: «до» - только файл с VERDICT OK (свежий NOT_OK пропущен)' ($r.Code -eq 0 -and ([IO.File]::ReadAllText((ScFile '20261113_100004')) -match '# BASELINE sys_check_20261113_100002.txt')) ''
$r = Run-Sc (New-Sc -svc @{ 'wifi-watchdog' = 'SC_SVC wifi-watchdog load=loaded active=active sub=running nrestarts=2 mainpid=100 enter_mono=1003000' }) '20261113_100005'
Check 'C5' '20: Ч2 NRestarts 2: код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100005')) -match 'NRestarts=2')) ''
$r = Run-Sc (New-Sc -svc @{ 'bumblebee' = 'SC_SVC bumblebee load=loaded active=activating sub=start nrestarts=0 mainpid=100 enter_mono=1001000' }) '20261113_100006'
Check 'C6' '20: Ч2 служба activating: код 5' ($r.Code -eq 5) ''
$r = Run-Sc (New-Sc -svc @{ 'notify-manager' = 'SC_SVC notify-manager load=loaded active=active sub=running nrestarts=0 mainpid=101 enter_mono=9999999' }) '20261113_100007'
Check 'C7' '20: Ч2 та же загрузка, время входа в active изменилось (перезапуск после «до»): код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100007')) -match 'перезапускалась после снимка')) ''
$r = Run-Sc (New-Sc -boot 'b2' -svc @{ 'notify-manager' = 'SC_SVC notify-manager load=loaded active=active sub=running nrestarts=0 mainpid=101 enter_mono=9999999' }) '20261113_100008'
Check 'C8' '20: другая загрузка (перезагрузка): новое время входа не ошибка, код 0' ($r.Code -eq 0) ('code=' + $r.Code)
Start-Sleep -Milliseconds 1100
$r = Run-Sc (New-Sc -boot 'b2' -jerr @{ 'wifi-manager' = 'SC_JERR wifi-manager errors=3 access=ok' }) '20261113_100009'
Check 'C9' '20: Ч2 в журнале wifi-manager 3 ошибки: код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100009')) -match 'wifi-manager: в журнале')) ''
$r = Run-Sc (New-Sc -boot 'b2' -jerr @{ 'sys_metrics' = 'SC_JERR sys_metrics errors=0 access=denied' }) '20261113_100010'
Check 'C10' '20: Ч2 журнал недоступен: код 5 (проверить нечем)' ($r.Code -eq 5) ''
$r = Run-Sc (New-Sc -boot 'b2' -wifi 'enabled') '20261113_100011'
Check 'C11' '20: Ч3 энергосбережение Wi-Fi включено: код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100011')) -match 'Wi-Fi ВКЛЮЧЕНО')) ''
$r = Run-Sc (New-Sc -boot 'b2' -wifi 'none') '20261113_100012'
Check 'C12' '20: Ч3 строк set_power_mgmt нет: код 5 (проверить нечем)' ($r.Code -eq 5) ''
$r = Run-Sc (New-Sc -boot 'b2' -iw 'on') '20261113_100013'
Check 'C13' '20: Ч3 iw Power save on: код 5' ($r.Code -eq 5) ''
$r = Run-Sc (New-Sc -boot 'b2' -nodes @('/mavros', '/mavros/mavros', '/transform_listener_impl_X')) '20261113_100014'
Check 'C14' '20: Ч4 пропал узел /aruco_detect: код 5, назван' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100014')) -match 'пропали /aruco_detect')) ''
$r = Run-Sc (New-Sc -boot 'b2' -nodes @('/mavros', '/mavros/mavros', '/aruco_detect', '/transform_listener_impl_X', '/lishniy')) '20261113_100015'
Check 'C15' '20: Ч4 лишний узел: код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100015')) -match 'лишние /lishniy')) ''
$r = Run-Sc (New-Sc -boot 'b2' -nodesRc 124) '20261113_100016'
Check 'C16' '20: Ч4 ros2 node list не ответил: код 5' ($r.Code -eq 5) ''
[IO.File]::WriteAllText((Join-Path $OC 'sys_fwupd_apply_20261113_100500.log'), "PERMISSION_SHA256=x`r`nBB_SYS_DONE fwupd apply OK`r`n", $utf8n)
$r = Run-Sc (New-Sc -boot 'b2') '20261113_100017'
Check 'C17' '20: по журналу 23a fwupd замаскирован, а на Pi enabled/active: код 5 «правка не держится»' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100017')) -match 'fwupd-refresh.timer по журналу шага 23 замаскирован')) ''
$r = Run-Sc (New-Sc -boot 'b3' -step1 @{ 'fwupd-refresh.timer' = 'enabled=masked active=inactive' }) '20261113_100018'
Check 'C18' '20: fwupd masked/inactive и после перезагрузки: код 0' ($r.Code -eq 0) ('code=' + $r.Code + ' ' + $r.Console)
Start-Sleep -Milliseconds 1100
[IO.File]::WriteAllText((Join-Path $OC 'sys_fwupd_rollback_20261113_100600.log'), "PERMISSION_SHA256=y`r`nBB_SYS_DONE fwupd rollback OK`r`n", $utf8n)
(Get-Item (Join-Path $OC 'sys_fwupd_rollback_20261113_100600.log')).LastWriteTime = (Get-Date).AddSeconds(1)
$r = Run-Sc (New-Sc -boot 'b3') '20261113_100019'
Check 'C19' '20: после отката 23a ожидания маски нет: enabled/active - код 0' ($r.Code -eq 0) ('code=' + $r.Code + ' ' + $r.Console)
[IO.File]::WriteAllText((Join-Path $OC 'sys_snaphold_apply_20261113_100700.log'), "BB_SYS_DONE snaphold apply OK`r`n", $utf8n)
$r = Run-Sc (New-Sc -boot 'b3') '20261113_100020'
Check 'C20' '20: по журналу 23b hold, а на Pi hold нет: код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100020')) -match 'snap по журналу шага 23b')) ''
$r = Run-Sc (New-Sc -boot 'b3' -snap 'forever') '20261113_100021'
Check 'C21' '20: hold forever держится: код 0' ($r.Code -eq 0) ('code=' + $r.Code)
Start-Sleep -Milliseconds 1100
$ev = Join-Path $OC 'overlay_connect_20261113_101500.txt'; [IO.File]::WriteAllText($ev, "BB_CONN_DONE bumblebee /x`r`n", $utf8n)
$chg = @{ 'bumblebee' = 'SC_SVC bumblebee load=loaded active=active sub=running nrestarts=0 mainpid=7777 enter_mono=8888888' }
$r = Run-Sc (New-Sc -boot 'b3' -snap 'forever' -svc $chg -nodes @('/mavros', '/mavros/mavros', '/aruco_detect', '/transform_listener_impl_X', '/novyy_uzel_r2j')) '20261113_100022'
Check 'C25' '20: после «до» менялся стек (событие 07 overlay_connect_*): другой список узлов и перезапуск bumblebee не СТОП, код 0, файл помечен как новое «до»' ($r.Code -eq 0 -and ([IO.File]::ReadAllText((ScFile '20261113_100022')) -match 'стек менялся после него: overlay_connect_20261113_101500\.txt')) ('code=' + $r.Code + ' ' + $r.Console)
Start-Sleep -Milliseconds 1100
$r = Run-Sc (New-Sc -boot 'b3' -snap 'forever' -svc $chg) '20261113_100023'
Check 'C26' '20: следующий запуск сравнивает уже с новым «до»: узел /novyy_uzel_r2j пропал -> код 5' ($r.Code -eq 5 -and ([IO.File]::ReadAllText((ScFile '20261113_100023')) -match '# BASELINE sys_check_20261113_100022\.txt') -and ([IO.File]::ReadAllText((ScFile '20261113_100023')) -match 'пропали /novyy_uzel_r2j')) ('code=' + $r.Code)
$h0 = (Get-FileHash -Algorithm SHA256 -LiteralPath (ScFile '20261113_100023')).Hash
$r = Run-Sc (New-Sc -boot 'b3') '20261113_100023'
Check 'C27' '20: файл с той же меткой уже есть: код 4, не перезаписан, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and (Get-FileHash -Algorithm SHA256 -LiteralPath (ScFile '20261113_100023')).Hash -eq $h0) ('code=' + $r.Code)
Reset-Fake 'wrong_host'; Set-Canned 'sc' @((New-Sc)); $o = New-Out
$r = Run-Cmd '20_nichego_ne_otvalilos.cmd' '' $o
Check 'C22' '20 (cmd): чужой дрон: код 4, скрипт не послан' ($r.Code -eq 4 -and $r.Sent.Count -eq 0) ('code=' + $r.Code)
$r = Run-Cmd '20_nichego_ne_otvalilos.cmd' '' $o 'OTHER-PC'
Check 'C23' '20 (cmd): чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'sc' @((New-Sc)); $o = New-Out
$r = Run-Cmd '20_nichego_ne_otvalilos.cmd' '' $o
Check 'C24' '20 (cmd): обычный запуск: код 0, посланный скрипт = pi\r6_sys_check.sh' ($r.Code -eq 0 -and $r.Sent.Count -eq 1 -and $r.Sent[0] -ceq ([IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_sys_check.sh')) -replace "`r`n", "`n")) ('code=' + $r.Code)

# ======================= K: 21 К-1 =======================
$ciAbsent = "CI_DIR /home/lb/bench_ws/incoming/camera_fullrow_r6`nCI_STATE absent`nBB_R6CI_DONE`n"
$ciOk = "CI_DIR /home/lb/bench_ws/incoming/camera_fullrow_r6`nCI_FILE camera_fix.py OK`nCI_FILE bench_recorder.py OK`nCI_FILE raw_layout_check.py OK`nCI_FILE SHA256SUMS_camera_fullrow.txt OK`nCI_STATE ok`nBB_R6CI_DONE`n"
$ciBad = "CI_DIR /home/lb/bench_ws/incoming/camera_fullrow_r6`nCI_FILE camera_fix.py DIFF got=0000`nCI_STATE bad`nBB_R6CI_DONE`n"
$k1Ok = "K1_DIR /home/lb/bench_ws/camera_fullrow_r6/20261113_101000/K1`nK1_THROTTLED_START throttled=0x0`nK1_PY_RC 0`nK1_OUT RAW CHECK ГОТОВО: 5/5 кадров`nK1_FRAME0 bytes=614400 sha256=ab`nК1 ГОТОВО /home/lb/bench_ws/camera_fullrow_r6/20261113_101000/K1`nBB_R6K1_DONE`n"
$k1Bad = "K1_DIR /home/lb/bench_ws/camera_fullrow_r6/20261113_101000/K1`nK1_PY_RC 1`nK1_OUT СТОП: раскладка кадра не та`nК1 НЕ ГОТОВО: нет строки RAW CHECK ГОТОВО`nBB_R6K1_DONE`n"
function K1Gate { Gate (Join-Path $G 'CAM_K1_APPROVED.txt') '21_kamera_K1' }
NoGate (Join-Path $G 'CAM_K1_APPROVED.txt'); Reset-Fake; $o = New-Out
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
Check 'K1' '21: нет разрешения: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'нет разрешения') ('code=' + $r.Code)
Gate (Join-Path $G 'CAM_K1_APPROVED.txt') '21_kamera_K1' @() 'СЛОВА_ВЛАДЕЛЬЦА='
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
Check 'K2' '21: в разрешении нет СЛОВА_ВЛАДЕЛЬЦА: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Gate (Join-Path $G 'CAM_K1_APPROVED.txt') '22_kamera_cena'
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
Check 'K3' '21: разрешение от другого шага (ПРАВКА=22...): код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
K1Gate
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "no`r`n" $o
Check 'K4' '21: ответ не K1: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o 'OTHER-PC'
Check 'K5' '21: чужой ПК: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake 'wrong_host'; $o = New-Out
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
Check 'K6' '21: чужой дрон: код 4, ничего не скопировано и не послано' ($r.Code -eq 4 -and $r.Sent.Count -eq 0 -and $r.J -notmatch 'SCP') ''
Reset-Fake; Set-Canned 'ci' @($ciAbsent, $ciOk); Set-Canned 'mk' @("MKDIR_OK /home/lb/bench_ws/incoming/camera_fullrow_r6`n"); Set-Canned 'k1' @($k1Ok); $OK1 = New-Out 'out_k1'
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $OK1
$kf = @(Files $OK1 'k1_raw_layout_*.txt' | Where-Object { $_.Name -notmatch 'err' })
$order = @($r.Calls | ForEach-Object { if ($_ -match 'key=(\w+)') { $Matches[1] } elseif ($_ -match 'HOST_OK') { 'host' } elseif ($_ -match 'SCP rec=False') { 'up' } elseif ($_ -match 'SCP rec=True') { 'down' } else { '?' } }) -join ','
Check 'K7' '21: папки нет: порядок host, ci(absent), mk, scp upload, ci(ok), k1, scp download; код 0' ($r.Code -eq 0 -and $order -ceq 'host,ci,mk,up,ci,k1,down') ('code=' + $r.Code + ' order=' + $order)
Check 'K8' '21: на Pi копируются ровно 4 файла (camera_fix dabd5076, bench_recorder, raw_layout_check, SHA256SUMS) в incoming/camera_fullrow_r6' ($r.J -match 'upload=camera_fix\.py:dabd507659933d08' -and $r.J -match 'upload=bench_recorder\.py:08c2ccac' -and $r.J -match 'upload=raw_layout_check\.py:8a811032' -and $r.J -match 'upload=SHA256SUMS_camera_fullrow\.txt' -and $r.J -match 'lb@[^ ]+:/home/lb/bench_ws/incoming/camera_fullrow_r6/') ''
Check 'K9' '21: файл К-1 с PERMISSION_SHA256 и «# VERDICT OK», копия папки K1 на ПК' ($kf.Count -eq 1 -and ([IO.File]::ReadAllText($kf[0].FullName) -match 'PERMISSION_SHA256=[0-9a-f]{64}') -and (LastLine $kf[0].FullName) -ceq '# VERDICT OK' -and @(Get-ChildItem -LiteralPath $OK1 -Directory -Filter 'k1_*' | Where-Object { Test-Path (Join-Path $_.FullName 'K1\FAKE_DOWNLOADED.txt') }).Count -eq 1) ''
$ciSent = @($r.Sent | Where-Object { $_ -match 'BB_R6CI_MARK' })
Check 'K10' '21: в скрипт проверки папки подставлены суммы 4 файлов' ($ciSent.Count -ge 1 -and $ciSent[0] -match 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83  camera_fix.py' -and $ciSent[0] -notmatch '(?m)^#@@CAMFILES@@\s*$') ''
Reset-Fake; Set-Canned 'ci' @($ciAbsent, $ciOk); Set-Canned 'mk' @("MKDIR_OK`n"); Set-Canned 'k1' @($k1Ok)
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $OK1
Check 'K11' '21: то же разрешение второй раз (после созданных на Pi файлов): код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Gate (Join-Path $G 'CAM_K1_APPROVED.txt') '21_kamera_K1' @('ПРИМЕЧАНИЕ=второе «да»')
Reset-Fake; Set-Canned 'ci' @($ciOk); Set-Canned 'k1' @($k1Bad); $o = New-Out
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
$kf = @(Files $o 'k1_raw_layout_*.txt' | Where-Object { $_.Name -notmatch 'err' })
Check 'K12' '21: папка уже есть и верна: не копирует (нет mkdir и upload); К-1 НЕ ГОТОВО: код 5, VERDICT NOT_OK' ($r.Code -eq 5 -and $r.J -notmatch 'key=mk' -and $r.J -notmatch 'SCP rec=False' -and $kf.Count -eq 1 -and (LastLine $kf[0].FullName) -ceq '# VERDICT NOT_OK') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'ci' @($ciBad); Set-Canned 'k1' @($k1Ok); $o = New-Out
Gate (Join-Path $G 'CAM_K1_APPROVED.txt') '21_kamera_K1' @('ПРИМЕЧАНИЕ=третье «да»')
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
Check 'K13' '21: на Pi папка с чужими файлами: код 4, не перезаписывает, К-1 не запускается' ($r.Code -eq 4 -and $r.J -notmatch 'key=k1' -and $r.J -notmatch 'SCP') ('code=' + $r.Code)
$cf = Join-Path $SB 'camera_fullrow\bench_recorder.py'; $cfb = [IO.File]::ReadAllBytes($cf); [IO.File]::AppendAllText($cf, "# x`n")
Reset-Fake; $o = New-Out
$r = Run-Cmd '21_kamera_K1_raskladka.cmd' "K1`r`n" $o
[IO.File]::WriteAllBytes($cf, $cfb)
Check 'K14' '21: файл замера в наборе изменён: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'ci' @($ciOk); Set-Canned 'k1' @($k1Ok); $o = New-Out
New-Item -ItemType Directory -Path (Join-Path $o 'k1_20261113_101000') | Out-Null
$r = Run-Ps 'run_r6_k1.ps1' '-Confirmed K1-NEWFILES -Stamp 20261113_101000' $o
Check 'K15' '21: папка out\k1_<метка> уже есть: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-Ps 'run_r6_k1.ps1' '-Confirmed K1 -Stamp 20261113_101001' $o
Check 'K16' '21: runner без подтверждения из окна: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''

# ======================= CO: 22 цена камеры =======================
function CostPhase([string]$ph, [bool]$ok = $true) {
    $j = '{"idle_pct_of_all_cores":55.0,"topics":{"markers":{"hz":10.0,"latency_ms_p50":40,"latency_ms_p95":60},"pose":{"hz":9.5,"latency_ms_p50":45,"latency_ms_p95":70},"image":{"hz":24.0}},"processes":{"camfix":{"cpu_pct_of_one_core":20.0},"camfix_full":{"cpu_pct_of_one_core":' + $(if ($ph -eq 'C') { '24.0' } else { '0.0' }) + '},"aruco_bench":{"cpu_pct_of_one_core":30.0}},"temp_c_max":55.0,"throttled_end":"throttled=0x0"}'
    $t = "COST_PHASE $ph`nCOST_START throttled=0x0 temp=50.0'C died=0`nCOST_RECORDER_RC 0`nCOST_END throttled=0x0 temp=55.0'C died=0`n"
    if ($ph -eq 'C') { $t += "COST_CAMFIX_FULL [x] camera_fix stats 30s: full-row frames 720, legacy frames 0`n" }
    $t += "COST_SUMMARY_JSON $j`n"
    if ($ok) { $t += "ФАЗА $ph ГОТОВО: /home/lb/bench_ws/camera_fullrow_r6/x/cost/$ph`n" } else { $t += "ФАЗА $ph НЕ ГОТОВО: в журнале main_camera_fix_full нет строк stats`n" }
    return $t + "BB_R6COST_DONE`n"
}
$endOk = "END_STAMP x`nEND_STACK '__node:=main_camera_fix ' 1`nEND_STACK '__node:=aruco_detect ' 1`nEND_STACK 'mavros_node' 1`nКАМЕРА: ЗАМЕР ЗАКОНЧЕН, СТЕК КАК БЫЛ — ГОТОВО`nBB_R6END_DONE`n"
$endBad = "END_STAMP x`nEND_MEAS_LEFT 123 x aruco_detect_bench`nКОНЕЦ ЗАМЕРА НЕ ГОТОВО: процессы_замера_ещё_работают`nBB_R6END_DONE`n"
function CostGate { Gate (Join-Path $G 'CAM_COST_APPROVED.txt') '22_kamera_cena' }
function Seed-K1([string]$out, [string]$verdict = '# VERDICT OK', [int]$ageMin = 0) { $p = Join-Path $out 'k1_raw_layout_20261113_100000.txt'; [IO.File]::WriteAllText($p, ("К1 ГОТОВО x`r`nBB_R6K1_DONE`r`n" + $verdict + "`r`n"), $utf8n); (Get-Item $p).LastWriteTime = (Get-Date).AddMinutes(-$ageMin) }
$costIn = "SCENE`r`n12`r`n-3,5`r`n45`r`nN`r`nSTART`r`n"
NoGate (Join-Path $G 'CAM_COST_APPROVED.txt'); Reset-Fake; $o = New-Out; Seed-K1 $o
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO1' '22: нет разрешения: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
CostGate; $o = New-Out
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO2' '22: нет результата К-1: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and $r.Console -match 'нет результата К-1') ('code=' + $r.Code)
$o = New-Out; Seed-K1 $o '# VERDICT NOT_OK'
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO3' '22: последний К-1 НЕ ГОТОВО: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$o = New-Out; Seed-K1 $o '# VERDICT OK' 181
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO4' '22: К-1 старше 180 минут: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$o = New-Out; Seed-K1 $o
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' "SCENE`r`n12 & calc`r`n0`r`n45`r`nN`r`nSTART`r`n" $o
Check 'CO5' '22: рулетка не числом (с & в тексте): код 4, к дрону не обращались, команда не выполнилась' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' "SCENE`r`n12`r`n0`r`n5`r`nN`r`nSTART`r`n" $o
Check 'CO6' '22: высота меньше 10 см: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' "SCENE`r`n12`r`n0`r`n45`r`nN`r`nno`r`n" $o
Check 'CO7' '22: не START: код 4' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Reset-Fake; Set-Canned 'ci' @($ciOk); Set-Canned 'cost_A' @((CostPhase 'A')); Set-Canned 'cost_C' @((CostPhase 'C')); Set-Canned 'cost_A2' @((CostPhase 'A2')); Set-Canned 'end' @($endOk)
$OCO = New-Out 'out_cost'; Seed-K1 $OCO
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $OCO
$order = @($r.Calls | ForEach-Object { if ($_ -match 'key=(\w+)') { $Matches[1] } elseif ($_ -match 'HOST_OK') { 'host' } elseif ($_ -match 'SCP rec=True') { 'down' } else { '?' } }) -join ','
$sf = @(Files $OCO 'camera_cost_*_summary.txt'); $pf = @(Files $OCO 'camera_cost_*_protocol.txt')
Check 'CO8' '22: порядок host, ci, A, C, A2, end, копия папки; код 0' ($r.Code -eq 0 -and $order -ceq 'host,ci,cost_A,cost_C,cost_A2,end,down') ('code=' + $r.Code + ' order=' + $order)
Check 'CO9' '22: числа записаны без порогов (VERDICT MEASURED), протокол с рулеткой 12 / -3,5 / 45 и приложением N' ($sf.Count -eq 1 -and (LastLine $sf[0].FullName) -ceq '# VERDICT MEASURED' -and ([IO.File]::ReadAllText($sf[0].FullName) -match 'A и A2 по частоте markers') -and $pf.Count -eq 1 -and ([IO.File]::ReadAllText($pf[0].FullName) -match 'РУЛЕТКА_X_СМ=12') -and ([IO.File]::ReadAllText($pf[0].FullName) -match 'РУЛЕТКА_Y_СМ=-3,5') -and ([IO.File]::ReadAllText($pf[0].FullName) -match 'РУЛЕТКА_ВЫСОТА_СМ=45') -and ([IO.File]::ReadAllText($pf[0].FullName) -match 'ПРИЛОЖЕНИЕ_ОТКРЫТО=N')) ''
$cs = @($r.Sent | Where-Object { $_ -match 'BB_R6COST_MARK' })
Check 'CO10' '22: посланный скрипт фазы = pi\r6_cost_phase.sh (3 раза), конец = pi\r6_cost_end.sh' ($cs.Count -eq 3 -and $cs[0] -ceq ([IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_cost_phase.sh')) -replace "`r`n", "`n") -and @($r.Sent | Where-Object { $_ -ceq ([IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_cost_end.sh')) -replace "`r`n", "`n") }).Count -eq 1) ''
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $OCO
Check 'CO11' '22: то же разрешение второй раз: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Gate (Join-Path $G 'CAM_COST_APPROVED.txt') '22_kamera_cena' @('ПРИМЕЧАНИЕ=второе')
Reset-Fake; Set-Canned 'ci' @($ciOk); Set-Canned 'cost_A' @((CostPhase 'A')); Set-Canned 'cost_C' @((CostPhase 'C' $false)); Set-Canned 'cost_A2' @((CostPhase 'A2')); Set-Canned 'end' @($endOk)
$o = New-Out; Seed-K1 $o
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO12' '22: фаза C не готова: A2 не запускается, конец замера делается, код 5, VERDICT NOT_DONE' ($r.Code -eq 5 -and $r.J -notmatch 'key=cost_A2' -and $r.J -match 'key=end' -and (LastLine (Files $o 'camera_cost_*_summary.txt')[0].FullName) -ceq '# VERDICT NOT_DONE') ('code=' + $r.Code)
Gate (Join-Path $G 'CAM_COST_APPROVED.txt') '22_kamera_cena' @('ПРИМЕЧАНИЕ=третье')
Reset-Fake; Set-Canned 'ci' @($ciOk); Set-Canned 'cost_A' @((CostPhase 'A')); Set-Canned 'cost_C' @((CostPhase 'C')); Set-Canned 'cost_A2' @((CostPhase 'A2')); Set-Canned 'end' @($endBad)
$o = New-Out; Seed-K1 $o
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO13' '22: «стек как был» не подтвердился: код 5' ($r.Code -eq 5) ('code=' + $r.Code)
Gate (Join-Path $G 'CAM_COST_APPROVED.txt') '22_kamera_cena' @('ПРИМЕЧАНИЕ=четвёртое')
Reset-Fake; Set-Canned 'ci' @($ciAbsent); $o = New-Out; Seed-K1 $o
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO14' '22: на Pi нет файлов замера: код 4, фазы не запускаются, ничего не копирует' ($r.Code -eq 4 -and $r.J -notmatch 'key=cost' -and $r.J -notmatch 'SCP') ('code=' + $r.Code)
Reset-Fake 'wrong_host'; $o = New-Out; Seed-K1 $o
$r = Run-Cmd '22_kamera_cena_A_C_A2.cmd' $costIn $o
Check 'CO15' '22: чужой дрон: код 4, скриптов не послано' ($r.Code -eq 4 -and $r.Sent.Count -eq 0) ''
Reset-Fake; Set-Canned 'ci' @($ciOk); $o = New-Out; Seed-K1 $o; [IO.File]::WriteAllText((Join-Path $o 'camera_cost_20261113_120000_C.txt'), 'старый')
$env:BB_RULER_X = '12'; $env:BB_RULER_Y = '0'; $env:BB_RULER_H = '45'; $env:BB_DASHBOARD = 'N'
$r = Run-Ps 'run_r6_cost.ps1' '-Confirmed COST-TEMP -Stamp 20261113_120000' $o
foreach ($k in 'BB_RULER_X', 'BB_RULER_Y', 'BB_RULER_H', 'BB_DASHBOARD') { Remove-Item -Path ('env:' + $k) -ErrorAction SilentlyContinue }
Check 'CO16' '22: файл фазы с той же меткой уже есть: код 4, не перезаписан, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and [IO.File]::ReadAllText((Join-Path $o 'camera_cost_20261113_120000_C.txt')) -ceq 'старый') ('code=' + $r.Code + ' calls=' + $r.Calls.Count)

# ======================= SY: 23 правки ступени 1 =======================
$sysOk = @{ fwupd = "SYS_CHANGE fwupd apply`nSYS_BEFORE fwupd-refresh.timer enabled=enabled active=active load=loaded`nSYS_SUDO x`nSYS_SUDO_PROMPT пароль`nSYS_CMD_RC 0`nSYS_AFTER fwupd-refresh.timer enabled=masked active=inactive load=masked`nBB_SYS_DONE fwupd apply OK`n" }
function SysOut([string]$ch, [string]$mode, [string]$end) { return ("SYS_CHANGE $ch $mode`nSYS_BEFORE x`nSYS_SUDO_PROMPT пароль`n" + $end + "`n") }
function Seed-Sc([string]$out, [string]$verdict = '# VERDICT OK', [int]$ageMin = 0, [string]$name = 'sys_check_20261113_090000.txt') { $p = Join-Path $out $name; [IO.File]::WriteAllText($p, ("SC_BOOT_ID b1`r`nBB_R6SC_DONE`r`n# BASELINE нет`r`n" + $verdict + "`r`n"), $utf8n); (Get-Item $p).LastWriteTime = (Get-Date).AddMinutes(-$ageMin) }
$sysCmds = @(
    @('23a_sys_fwupd_mask.cmd', 'fwupd', 'apply', 'SYS_FWUPD_MASK_APPROVED.txt', '23a_fwupd_mask'),
    @('23a_otkat_fwupd_mask.cmd', 'fwupd', 'rollback', 'OTKAT_SYS_FWUPD_APPROVED.txt', '23a_otkat_fwupd_mask'),
    @('23b_sys_snap_hold.cmd', 'snaphold', 'apply', 'SYS_SNAP_HOLD_APPROVED.txt', '23b_snap_hold'),
    @('23b_otkat_snap_hold.cmd', 'snaphold', 'rollback', 'OTKAT_SYS_SNAP_HOLD_APPROVED.txt', '23b_otkat_snap_hold'),
    @('23c_sys_taimery_mask.cmd', 'timers', 'apply', 'SYS_TIMERS_MASK_APPROVED.txt', '23c_taimery_mask'),
    @('23c_otkat_taimery_mask.cmd', 'timers', 'rollback', 'OTKAT_SYS_TIMERS_APPROVED.txt', '23c_otkat_taimery_mask'))
foreach ($sc in $sysCmds) {
    $cmd = $sc[0]; $ch = $sc[1]; $md = $sc[2]; $gf = Join-Path $G $sc[3]; $gid = $sc[4]
    NoGate $gf; Reset-Fake; $o = New-Out; Seed-Sc $o
    $r = Run-Cmd $cmd "SYS`r`nYES`r`n" $o
    Check 'SY1' ($cmd + ': нет разрешения: код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
    Gate $gf ($gid + '_x')
    $r = Run-Cmd $cmd "SYS`r`nYES`r`n" $o
    Check 'SY2' ($cmd + ': разрешение с чужим ПРАВКА=: код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
    Gate $gf $gid
    $r = Run-Cmd $cmd "SYS`r`nno`r`n" $o
    Check 'SY3' ($cmd + ': не YES: код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
    Reset-Fake; Set-Canned 'sys' @((SysOut $ch $md ("BB_SYS_DONE $ch $md OK"))); $o = New-Out; Seed-Sc $o
    $r = Run-Cmd $cmd "SYS`r`nYES`r`n" $o
    $lg = @(Files $o ('sys_' + $ch + '_' + $md + '_*.log'))
    Check 'SY4' ($cmd + ': обычный запуск: код 0; ssh -tt; аргументы «' + $ch + ' ' + $md + '»; журнал с PERMISSION_SHA256 и BB_SYS_DONE') ($r.Code -eq 0 -and $r.J -match '\[-tt\]' -and $r.J -match ('_ ' + $ch + ' ' + $md + '\]') -and $lg.Count -eq 1 -and ([IO.File]::ReadAllText($lg[0].FullName) -match 'PERMISSION_SHA256=[0-9a-f]{64}') -and ([IO.File]::ReadAllText($lg[0].FullName) -match ('BB_SYS_DONE ' + $ch + ' ' + $md + ' OK'))) ('code=' + $r.Code + ' ' + $r.J)
    Check 'SY5' ($cmd + ': посланный скрипт = pi\r6_sys_change.sh') ($r.Sent.Count -eq 1 -and $r.Sent[0] -ceq ([IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_sys_change.sh')) -replace "`r`n", "`n")) ''
    $r = Run-Cmd $cmd "SYS`r`nYES`r`n" $o
    Check 'SY6' ($cmd + ': то же разрешение второй раз: код 4, к дрону не обращались') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
    Gate $gf $gid @('ПРИМЕЧАНИЕ=ещё раз')
    Reset-Fake 'wrong_host'; $o = New-Out; Seed-Sc $o
    $r = Run-Cmd $cmd "SYS`r`nYES`r`n" $o
    Check 'SY7' ($cmd + ': чужой дрон: код 4, скрипт не послан') ($r.Code -eq 4 -and $r.Sent.Count -eq 0) ''
    $r = Run-Cmd $cmd "SYS`r`nYES`r`n" $o 'OTHER-PC'
    Check 'SY8' ($cmd + ': чужой ПК: код 4') ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
}
Gate (Join-Path $G 'SYS_FWUPD_MASK_APPROVED.txt') '23a_fwupd_mask' @('ПРИМЕЧАНИЕ=условия')
Reset-Fake; Set-Canned 'sys' @((SysOut 'fwupd' 'apply' 'BB_SYS_DONE fwupd apply OK')); $o = New-Out
$r = Run-Cmd '23a_sys_fwupd_mask.cmd' "SYS`r`nYES`r`n" $o
Check 'SY9' '23a apply: нет снимка «до» шага 20: код 5, к дрону не обращались' ($r.Code -eq 5 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
$o = New-Out; Seed-Sc $o '# VERDICT NOT_OK'
$r = Run-Cmd '23a_sys_fwupd_mask.cmd' "SYS`r`nYES`r`n" $o
Check 'SY10' '23a apply: последний снимок 20 NOT_OK: код 5' ($r.Code -eq 5 -and $r.Calls.Count -eq 0) ''
$o = New-Out; Seed-Sc $o '# VERDICT OK' 61
$r = Run-Cmd '23a_sys_fwupd_mask.cmd' "SYS`r`nYES`r`n" $o
Check 'SY11' '23a apply: снимок старше 60 минут: код 5' ($r.Code -eq 5 -and $r.Calls.Count -eq 0) ''
$o = New-Out; Seed-Sc $o '# VERDICT OK' 5
$ev = Join-Path $o 'sys_timers_apply_20261113_095900.log'; [IO.File]::WriteAllText($ev, "BB_SYS_DONE timers apply OK`r`n", $utf8n); (Get-Item $ev).LastWriteTime = (Get-Date).AddMinutes(-1)
$r = Run-Cmd '23a_sys_fwupd_mask.cmd' "SYS`r`nYES`r`n" $o
Check 'SY12' '23a apply: снимок сделан ДО последней правки 23c (правки по одной): код 5' ($r.Code -eq 5 -and $r.Calls.Count -eq 0 -and $r.Console -match 'по одной') ('code=' + $r.Code)
Gate (Join-Path $G 'OTKAT_SYS_FWUPD_APPROVED.txt') '23a_otkat_fwupd_mask' @('ПРИМЕЧАНИЕ=без снимка')
Reset-Fake; Set-Canned 'sys' @((SysOut 'fwupd' 'rollback' 'BB_SYS_DONE fwupd rollback OK')); $o = New-Out
$r = Run-Cmd '23a_otkat_fwupd_mask.cmd' "SYS`r`nYES`r`n" $o
Check 'SY13' '23a откат: снимок «до» не нужен (откат нужен, когда что-то не так): код 0' ($r.Code -eq 0) ('code=' + $r.Code)
foreach ($case in @(@('BB_SYS_STOP условия не выполнены: x (ничего не изменено)', 5, 'SY14', 'на Pi условия не выполнены (BB_SYS_STOP): код 5'), @('BB_SYS_NOCHANGE fwupd apply rc=1 (команда не выполнена, состояние как до)', 5, 'SY15', 'sudo не принял пароль (BB_SYS_NOCHANGE): код 5'), @('BB_SYS_FAIL fwupd apply rc=0 check=1', 6, 'SY16', 'правка не подтвердилась (BB_SYS_FAIL): код 6'))) {
    Gate (Join-Path $G 'SYS_FWUPD_MASK_APPROVED.txt') '23a_fwupd_mask' @('ПРИМЕЧАНИЕ=' + $case[2])
    Reset-Fake; Set-Canned 'sys' @((SysOut 'fwupd' 'apply' $case[0])); $o = New-Out; Seed-Sc $o
    $r = Run-Cmd '23a_sys_fwupd_mask.cmd' "SYS`r`nYES`r`n" $o
    Check $case[2] ('23a: ' + $case[3]) ($r.Code -eq $case[1]) ('code=' + $r.Code)
}
$o = New-Out; Seed-Sc $o
$r = Run-Ps 'run_r6_sys.ps1' '-Change fwupd -Mode apply -Confirmed CHANGE-fwupd-rollback' $o
Check 'SY17' 'run_r6_sys.ps1: подтверждение от другого режима: код 4, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0) ''
Gate (Join-Path $G 'OTKAT_SYS_FWUPD_APPROVED.txt') '23a_otkat_fwupd_mask' @('ПРИМЕЧАНИЕ=перезапись')
Reset-Fake; Set-Canned 'sys' @((SysOut 'fwupd' 'rollback' 'BB_SYS_DONE fwupd rollback OK')); $o = New-Out; [IO.File]::WriteAllText((Join-Path $o 'sys_fwupd_rollback_20261113_130000.log'), 'старый')
$r = Run-Ps 'run_r6_sys.ps1' '-Change fwupd -Mode rollback -Confirmed CHANGE-fwupd-rollback -Stamp 20261113_130000' $o
Check 'SY18' 'run_r6_sys.ps1: журнал с той же меткой уже есть: код 4, не перезаписан, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and [IO.File]::ReadAllText((Join-Path $o 'sys_fwupd_rollback_20261113_130000.log')) -ceq 'старый') ('code=' + $r.Code)

# ======================= V: 24 «правка применилась» =======================
function New-Cv([string]$mode = 'cam', [hashtable]$ov = @{}) {
    $cam = $(if ($mode -eq 'cam') { 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83' } else { '4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310' })
    $ln = $(if ($mode -eq 'cam') { '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294' } else { '62be01dbb13305bca321d538690252863dedadb8a376e65e54d9f6c15116bf15' })
    $v = [ordered]@{
        svc = 'CV_SERVICE active=active mainpid=4242 nrestarts=0'
        pfx = 'CV_PREFIX /home/lb/bench_ws/r2j/install/bumblebee'
        launch = "CV_LAUNCH sha=$ln"
        p1 = "CV_PROC node=main_camera_fix pid=5001 sha=$cam in_prefix=yes start_epoch=1794000100 file_ctime=1794000000 path=/home/lb/bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py"
        p2 = "CV_PROC node=second_camera_fix pid=5002 sha=$cam in_prefix=yes start_epoch=1794000108 file_ctime=1794000000 path=/home/lb/bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py"
        log = 'CV_LOG access=ok run_line=100 launch_pid=4242 mainpid=4242 match=yes'
        sm = $(if ($mode -eq 'cam') { 'CV_START main lines=1 full_rows_true=1 full_rows_false=0' } else { 'CV_START main lines=1 full_rows_true=0 full_rows_false=0' })
        ss = $(if ($mode -eq 'cam') { 'CV_START second lines=1 full_rows_true=0 full_rows_false=1' } else { 'CV_START second lines=1 full_rows_true=0 full_rows_false=0' })
        fm = $(if ($mode -eq 'cam') { 'CV_FULLROW main read384=1 any=1 not_possible=0' } else { 'CV_FULLROW main read384=0 any=0 not_possible=0' })
        fs = 'CV_FULLROW second any=0'
        st = $(if ($mode -eq 'cam') { "CV_STATS main full=720 legacy=0`nCV_STATS main full=718 legacy=0`nCV_STATS second full=0 legacy=715" } else { '' })
        died = 'CV_DIED 0'; started = 'CV_CAMFIX_STARTED 2'; errs = 'CV_ERRORS 0'
    }
    foreach ($k in $ov.Keys) { $v[$k] = $ov[$k] }
    return ("CV_MODE $mode`n" + ((@($v.Values) | Where-Object { $_ -ne '' }) -join "`n") + "`nBB_R6CV_DONE`n")
}
function Cv([string]$mode, [string]$text, [string]$stamp) { Reset-Fake; Set-Canned 'cv' @($text); $o = New-Out; $r = Run-Ps 'run_r6_camverify.ps1' ('-Mode ' + $mode + ' -Stamp ' + $stamp) $o; $r.File = Join-Path $o ('cam_verify_' + $mode + '_' + $stamp + '.txt'); return $r }
$r = Cv 'cam' (New-Cv) '20261113_110000'
Check 'V1' '24a: всё как надо: код 0, VERDICT OK' ($r.Code -eq 0 -and (LastLine $r.File) -ceq '# VERDICT OK') ('code=' + $r.Code + ' ' + $r.Console)
$cases = @(
    @('V2', 'главная исполняет старый camera_fix (4a15d699)', @{ p1 = 'CV_PROC node=main_camera_fix pid=5001 sha=4a15d6997ff14752e6228b5c55cbc4665428c692b305fc25eb0e8cc26d9e1310 in_prefix=yes start_epoch=1794000100 file_ctime=1794000000 path=/x/lib/bumblebee/camera_fix.py' }),
    @('V3', 'файл менялся ПОСЛЕ запуска процесса (стек не перезапущен)', @{ p2 = 'CV_PROC node=second_camera_fix pid=5002 sha=dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83 in_prefix=yes start_epoch=1794000108 file_ctime=1794000200 path=/x/lib/bumblebee/camera_fix.py' }),
    @('V4', 'процесс не из исполняемого префикса', @{ p1 = 'CV_PROC node=main_camera_fix pid=5001 sha=dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83 in_prefix=no start_epoch=1794000100 file_ctime=1794000000 path=/home/lb/ros2_ws/install/bumblebee/lib/bumblebee/camera_fix.py' }),
    @('V5', 'второго camera_fix нет', @{ p2 = '' }),
    @('V6', 'launch в префиксе старый (62be01db)', @{ launch = 'CV_LAUNCH sha=62be01dbb13305bca321d538690252863dedadb8a376e65e54d9f6c15116bf15' }),
    @('V7', 'у второй камеры full_rows=True', @{ ss = 'CV_START second lines=1 full_rows_true=1 full_rows_false=0' }),
    @('V8', 'нет «full-row read: 384»', @{ fm = 'CV_FULLROW main read384=0 any=1 not_possible=0' }),
    @('V9', 'в stats главной legacy frames 3', @{ st = "CV_STATS main full=720 legacy=0`nCV_STATS main full=715 legacy=3" }),
    @('V10', 'stats ещё нет (рано)', @{ st = '' }),
    @('V11', 'полных кадров меньше 600', @{ st = 'CV_STATS main full=300 legacy=0' }),
    @('V12', 'в журнале запуска process has died', @{ died = 'CV_DIED 1' }),
    @('V13', 'camera_fix запускались 3 раза (перезапуск)', @{ started = 'CV_CAMFIX_STARTED 3' }),
    @('V14', 'журнал не от текущего запуска (pid не совпал)', @{ log = 'CV_LOG access=ok run_line=100 launch_pid=1111 mainpid=4242 match=no' }),
    @('V15', 'журнал недоступен', @{ log = 'CV_LOG access=denied' }),
    @('V16', 'служба не active', @{ svc = 'CV_SERVICE active=inactive mainpid=0 nrestarts=0' }),
    @('V17', 'служба перезапускалась сама', @{ svc = 'CV_SERVICE active=active mainpid=4242 nrestarts=1' }),
    @('V18', 'у главной full-row read not possible', @{ fm = 'CV_FULLROW main read384=1 any=1 not_possible=2' }),
    @('V19', 'ошибки camera_fix в журнале', @{ errs = 'CV_ERRORS 2' })
)
$i = 0
foreach ($c in $cases) { $i++; $r = Cv 'cam' (New-Cv 'cam' $c[2]) ('20261113_1101' + ('{0:D2}' -f $i)); Check $c[0] ('24a: ' + $c[1] + ': код 5, VERDICT NOT_OK') ($r.Code -eq 5 -and (LastLine $r.File) -ceq '# VERDICT NOT_OK') ('code=' + $r.Code) }
$r = Cv 'r2j' (New-Cv 'r2j') '20261113_110300'
Check 'V20' '24b: прежняя камера r2j: код 0' ($r.Code -eq 0) ('code=' + $r.Code + ' ' + $r.Console)
$r = Cv 'r2j' (New-Cv 'r2j' @{ sm = 'CV_START main lines=1 full_rows_true=1 full_rows_false=0' }) '20261113_110301'
Check 'V21' '24b: после отката в журнале full_rows=True: код 5' ($r.Code -eq 5) ''
$r = Cv 'r2j' (New-Cv 'cam') '20261113_110302'
Check 'V22' '24b: работает dabd5076 (откат не применился): код 5' ($r.Code -eq 5) ''
Reset-Fake 'wrong_host'; $o = New-Out
$r = Run-Cmd '24a_proverka_kamery_polnye_stroki.cmd' '' $o
Check 'V23' '24a (cmd): чужой дрон: код 4' ($r.Code -eq 4 -and $r.Sent.Count -eq 0) ''
Reset-Fake; Set-Canned 'cv' @((New-Cv)); $o = New-Out
$r = Run-Cmd '24a_proverka_kamery_polnye_stroki.cmd' '' $o
Check 'V24' '24a (cmd): обычный: код 0, посланный скрипт = pi\r6_cam_verify.sh с аргументом cam' ($r.Code -eq 0 -and $r.Sent.Count -eq 1 -and $r.Sent[0] -ceq ([IO.File]::ReadAllText((Join-Path $Kit 'pi\r6_cam_verify.sh')) -replace "`r`n", "`n") -and $r.J -match '_ cam\]') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'cv' @((New-Cv)); $o = New-Out; [IO.File]::WriteAllText((Join-Path $o 'cam_verify_cam_20261113_110400.txt'), 'старый')
$r = Run-Ps 'run_r6_camverify.ps1' '-Mode cam -Stamp 20261113_110400' $o
Check 'V25' '24a: файл с той же меткой уже есть: код 4, не перезаписан, к дрону не обращались' ($r.Code -eq 4 -and $r.Calls.Count -eq 0 -and [IO.File]::ReadAllText((Join-Path $o 'cam_verify_cam_20261113_110400.txt')) -ceq 'старый') ('code=' + $r.Code)

# ======================= I, F: 09c и 15c =======================
$inst = "INSTALL_ARCH aarch64`nINSTALL_PREFIX /home/lb/bench_ws/r2j/install/bumblebee`nINSTALL_FILE camera_fix.py OK`nBB_RTPY ok=8 diff=0 missing=0`nBB_INSTALL_CHECK ok=10 diff=0 missing=0 noprefix=0 cpp_ok=16 cpp_diff=0 cpp_missing=0 bin_ok=6 bin_missing=0 stale=0`nBB_INSTALL_CHECK_DONE`n"
Reset-Fake; Set-Canned 'install' @($inst); $o = New-Out
$r = Run-Cmd '09c_sverka_install_r2j_cam.cmd' '' $o
$vf = @(Files $o 'sverka_r2jcam_*.txt' | Where-Object { $_.Name -notmatch 'err|generated' })
Check 'I1' '09c: всё совпало: код 0, файл out\sverka_r2jcam_*.txt с VERDICT OK, файлов install_check_* нет (07 их не берёт)' ($r.Code -eq 0 -and $vf.Count -eq 1 -and (LastLine $vf[0].FullName) -ceq '# VERDICT OK' -and (Files $o 'install_check_*').Count -eq 0) ('code=' + $r.Code)
Check 'I2' '09c: в посланный скрипт подставлены списки варианта: camera_fix.py dabd5076, bumblebee.launch.py 5f0954d8, нет 4a15d699 и 62be01db' ($r.Sent.Count -eq 1 -and $r.Sent[0] -match 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83  camera_fix\.py' -and $r.Sent[0] -match '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294  LAUNCH  launch/bumblebee\.launch\.py' -and $r.Sent[0] -notmatch '4a15d6997ff14752' -and $r.Sent[0] -notmatch '62be01dbb13305bc' -and $r.Sent[0] -notmatch '(?m)^#@@(LIST|CPP|BINS|RT)@@\s*$') ''
Reset-Fake; Set-Canned 'install' @(($inst -replace 'ok=10 diff=0', 'ok=9 diff=1')); $o = New-Out
$r = Run-Cmd '09c_sverka_install_r2j_cam.cmd' '' $o
Check 'I3' '09c: расхождение python-узла: код 5, VERDICT NOT_OK' ($r.Code -eq 5 -and (LastLine (@(Files $o 'sverka_r2jcam_*.txt' | Where-Object { $_.Name -notmatch 'err|generated' })[0].FullName)) -ceq '# VERDICT NOT_OK') ('code=' + $r.Code)
$t09 = [IO.File]::ReadAllText((Join-Path $Kit 'run_install_check.ps1')); $t07 = [IO.File]::ReadAllText((Join-Path $Kit 'run_07_takeoff.ps1'))
Check 'I4' 'прежние ворота не тронуты: run_install_check.ps1 и run_07_takeoff.ps1 = r5; 07 берёт только install_check_*.txt' (((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Kit 'run_install_check.ps1')).Hash.ToLower() -eq $r5sums['run_install_check.ps1']) -and ((Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $Kit 'run_07_takeoff.ps1')).Hash.ToLower() -eq $r5sums['run_07_takeoff.ps1']) -and $t07 -match "@\('install_check', '09_sverka_install.cmd'\)") ''
$evRe = '^(overlay_connect_|overlay_disconnect_|bb_build_|bb_aside_|mavros_build_|mavros_aside_|install_r2j_|rollback_r2j_|install_camera_dabd5076_)'
Check 'I5' 'журналы варианта install_r2j_cam_*.log и rollback_r2j_cam_*.log 07 считает событиями (обесценивают прежние 09 и 10); sverka_r2jcam_ и otpechatki_r2jcam_ - не install_check_ и не fingerprint_bumblebee_' ('install_r2j_cam_123.log' -match $evRe -and 'rollback_r2j_cam_123.log' -match $evRe -and $t07.Contains($evRe) -and 'sverka_r2jcam_1.txt' -notlike 'install_check_*' -and 'otpechatki_r2jcam_1.txt' -notlike 'fingerprint_bumblebee_*') ''
$fpc = "FP_TARGET bumblebee`nFP_ROOT /home/lb/bench_ws/r2j`nFP_FILE " + ('a' * 64) + " bumblebee/lib/bumblebee/camera_fix.py`nBB_FP_RT ok=8 diff=0 missing=0`nBB_FP_RESULT files=1 py_ok=10 py_bad=0 src_ok=16 src_bad=0 bin=6 stale=0 noinstall=0`nBB_FP_DONE`n"
Reset-Fake; Set-Canned 'fp' @($fpc); $o = New-Out
$r = Run-Cmd '15c_otpechatki_r2j_cam.cmd' '' $o
$ff = @(Files $o 'otpechatki_r2jcam_*.txt' | Where-Object { $_.Name -notmatch 'raw|err|generated' })
Check 'F1' '15c: без замечаний: код 0, out\otpechatki_r2jcam_*.txt с VERDICT OK, fingerprint_* не создаётся (16 его не берёт), цель bumblebee' ($r.Code -eq 0 -and $ff.Count -eq 1 -and (LastLine $ff[0].FullName) -ceq '# VERDICT OK' -and (Files $o 'fingerprint_*').Count -eq 0 -and $r.J -match '_ bumblebee\]') ('code=' + $r.Code)
Check 'F2' '15c: в посланный скрипт подставлены списки варианта' ($r.Sent.Count -eq 1 -and $r.Sent[0] -match 'dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83  camera_fix\.py' -and $r.Sent[0] -match '5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294  LAUNCH' -and $r.Sent[0] -notmatch '4a15d6997ff14752') ''
Reset-Fake; Set-Canned 'fp' @(($fpc -replace 'py_ok=10 py_bad=0', 'py_ok=9 py_bad=1')); $o = New-Out
$r = Run-Cmd '15c_otpechatki_r2j_cam.cmd' '' $o
Check 'F3' '15c: python-узел отличается: код 5' ($r.Code -eq 5) ('code=' + $r.Code)

# ======================= G: вариант образа 05c / 06c =======================
$IK = Join-Path $SB 'image_r2j_cam'; $conf = Join-Path $SB 'image_r2j\image_target.conf'; $confOrig = [IO.File]::ReadAllBytes($conf)
$manSha = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $IK 'image_manifest.final.tsv')).Hash.ToLower()
$PC = Join-Path $Run 'params_check_note.txt'
function Set-Conf([string]$dest = '/home/lb', [string]$backup = '/home/lb/bb_backup') { [IO.File]::WriteAllText($conf, ("DEST_ROOT=" + $dest + "`nBACKUP_ROOT=" + $backup + "`n"), $utf8n) }
function Set-S2([string]$sha = $manSha) { New-Item -ItemType Directory -Force -Path (Join-Path $IK 'gates') | Out-Null; [IO.File]::WriteAllText((Join-Path $IK 'gates\S2_S3_PASSED.txt'), ("S2=PASS`r`nS3=PASS`r`nДАТА=2026-11-13`r`nДОКАЗАТЕЛЬСТВО=тест`r`nОБРАЗ_MANIFEST_SHA256=" + $sha + "`r`nСОЗДАЛ=чат 1`r`n"), $utf8) }
function Set-CamGate([string[]]$extra = @(('CAMERA_SHA256=dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'), ('LAUNCH_SHA256=5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294'), ('MANIFEST_SHA256=' + $manSha))) { Gate (Join-Path $IK 'gates\R2J_CAM_APPROVED.txt') '05c_r2j_cam' $extra }
$blN = @(Get-Content -LiteralPath (Join-Path $SB 'params_check\baseline_20261104_1145.params') -Encoding UTF8 | Where-Object { $_ -match "^1\t1\t" }).Count
function Seed-Params([string]$out, [string]$obl = '4', [int]$ageMin = 0) {
    $rep = Join-Path $out 'params_bench_20261113_100000_report.txt'; $par = Join-Path $out 'params_bench_20261113_100000.params'
    [IO.File]::WriteAllText($rep, ("=== СОВПАДАЕТ: прочитано $blN из $blN, отличий нет (из таблицы MAVROS $blN, из запасного потока 0)`r`n"), $utf8)
    [IO.File]::WriteAllText($par, ("1`t1`tCOM_OBL_RC_ACT`t" + $obl + "`t6`r`n"), $utf8)
    (Get-Item $rep).LastWriteTime = (Get-Date).AddMinutes(-$ageMin)
}
function Gates-Cam([string]$out, [string]$mode = 'install') { $so = Join-Path $Run ('g_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.txt'); $p = Start-Process -FilePath 'powershell.exe' -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $IK 'check_gates_r2j_cam.ps1') + '" -Kit "' + $IK + '" -OutDir "' + $out + '" -Mode ' + $mode) -NoNewWindow -PassThru -Wait -RedirectStandardOutput $so -RedirectStandardError ($so + '.err'); return @{ Code = $p.ExitCode; Text = [IO.File]::ReadAllText($so) } }
$o = New-Out
$g = Gates-Cam $o
Check 'G1' 'гейт варианта как есть в наборе: код 1 (BACKUP_ROOT TBD, нет S2/S3 варианта, нет сверки настроек, нет разрешения)' ($g.Code -eq 1 -and $g.Text -match 'BACKUP_ROOT \(TBD\)' -and $g.Text -match 'S2_S3_PASSED.txt варианта' -and $g.Text -match 'Нет сверки настроек' -and $g.Text -match 'R2J_CAM_APPROVED.txt') $g.Text
Set-Conf; Set-S2; Set-CamGate; $OG = New-Out 'out_g'; Seed-Params $OG
$g = Gates-Cam $OG
Check 'G2' 'гейт варианта: все условия выполнены: код 0' ($g.Code -eq 0) $g.Text
$gc = @(
    @('G3', 'S2/S3 выдан для другого манифеста', { Set-S2 ('0' * 64) }, { Set-S2 }),
    @('G4', 'COM_OBL_RC_ACT не 4', { Seed-Params $OG '0' }, { Seed-Params $OG }),
    @('G5', 'сверка настроек старше 30 минут', { Seed-Params $OG '4' 31 }, { Seed-Params $OG }),
    @('G6', 'в разрешении нет MANIFEST_SHA256', { Set-CamGate @(('CAMERA_SHA256=dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'), ('LAUNCH_SHA256=5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294')) }, { Set-CamGate }),
    @('G7', 'в разрешении чужая сумма камеры', { Set-CamGate @(('CAMERA_SHA256=' + ('1' * 64)), ('LAUNCH_SHA256=5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294'), ('MANIFEST_SHA256=' + $manSha)) }, { Set-CamGate }),
    @('G8', 'DEST_ROOT не /home/lb', { Set-Conf '/home/other' }, { Set-Conf }),
    @('G9', 'BACKUP_ROOT TBD', { Set-Conf '/home/lb' 'TBD' }, { Set-Conf })
)
foreach ($c in $gc) { & $c[2]; $g = Gates-Cam $OG; Check $c[0] ('гейт варианта: ' + $c[1] + ': код 1') ($g.Code -eq 1) $g.Text; & $c[3] }
$pl = Join-Path $IK 'payload\bench_ws\r2j\install\bumblebee\lib\bumblebee\camera_fix.py'; $plb = [IO.File]::ReadAllBytes($pl); [IO.File]::AppendAllText($pl, "#x`n")
$g = Gates-Cam $OG; [IO.File]::WriteAllBytes($pl, $plb)
Check 'G10' 'гейт варианта: файл payload изменён: код 1' ($g.Code -eq 1 -and $g.Text -match 'не сходится') $g.Text
$ex = Join-Path $IK 'payload\ros2_ws\src\bumblebee\examples\x.py'; New-Item -ItemType Directory -Force -Path (Split-Path $ex) | Out-Null; [IO.File]::WriteAllText($ex, "x`n")
$g = Gates-Cam $OG; Remove-Item -LiteralPath $ex; Remove-Item -LiteralPath (Split-Path $ex)
Check 'G11' 'гейт варианта: лишний файл в payload: код 1' ($g.Code -eq 1 -and $g.Text -match 'лишний файл') $g.Text
$mf = Join-Path $IK 'image_manifest.final.tsv'; $mfb = [IO.File]::ReadAllBytes($mf); [IO.File]::AppendAllText($mf, "ros2_ws/src/bumblebee/scripts/fcu_detect.py`t" + ('2' * 64) + "`n")
$g = Gates-Cam $OG; [IO.File]::WriteAllBytes($mf, $mfb)
Check 'G12' 'гейт варианта: в манифесте 5 строк и fcu_detect.py: код 1' ($g.Code -eq 1 -and $g.Text -match 'fcu_detect') $g.Text
$g = Gates-Cam $OG
Check 'G13' 'гейт варианта после возврата всех правок теста снова 0 (тест сам ничего не испортил)' ($g.Code -eq 0) $g.Text
$cpInstOk = "CP_SERVICE bumblebee inactive`nCP_OVERLAY_LINE yes`nCP_PREFIX /home/lb/bench_ws/r2j/install/bumblebee`nCP_COUNT files=4 r2j=4 cam=0`nCP_RESULT OK`nBB_R6CP_DONE`n"
$cpInstd = "CP_SERVICE bumblebee inactive`nCP_COUNT files=4 r2j=0 cam=4`nCP_RESULT OK`nBB_R6CP_DONE`n"
$cpStop = "CP_SERVICE bumblebee active`nCP_RESULT STOP служба_bumblebee_active`nBB_R6CP_DONE`n"
function Inst([string]$out, [string]$stdin = "SERVICE`r`nYES`r`n") { return Run-Cmd 'image_r2j_cam\05c_install_r2j_cam.cmd' $stdin $out }
Reset-Fake; Set-Canned 'cp_install' @($cpInstOk); Set-Canned 'cp_installed' @($cpInstd)
$r = Inst $OG
$il = @(Files $OG 'install_r2j_cam_*.log')
$order = @($r.Calls | ForEach-Object { if ($_ -match 'key=(\w+)') { $Matches[1] } elseif ($_ -match 'HOST_OK') { 'host' } elseif ($_ -match 'SCP') { 'scp' } elseif ($_ -match 'image_install\.sh') { 'install' } else { '?' } }) -join ','
Check 'G14' '05c: обычный запуск: код 0; порядок host, cp_install, host(+mkdir /tmp), scp, image_install.sh, cp_installed' ($r.Code -eq 0 -and $order -ceq 'host,cp_install,host,scp,install,cp_installed') ('code=' + $r.Code + ' order=' + $order + ' ' + $r.Console)
Check 'G15' '05c: на Pi уходят payload (4 файла), манифест варианта, image_target.conf и прежний image_install.sh' ($r.J -match 'upload_dir=payload:files=4' -and $r.J -match 'upload=image_manifest\.final\.tsv:' + $manSha -and $r.J -match 'upload=image_target\.conf' -and $r.J -match ('upload=image_install\.sh:' + $r5sums['image_r2j/image_install.sh'])) $r.J
Check 'G16' '05c: журнал install_r2j_cam_*.log (07 видит его как событие) с PERMISSION_SHA256 и BB_IMAGE_INSTALL_DONE' ($il.Count -eq 1 -and ([IO.File]::ReadAllText($il[0].FullName) -match 'PERMISSION_SHA256=[0-9a-f]{64}') -and ([IO.File]::ReadAllText($il[0].FullName) -match 'BB_IMAGE_INSTALL_DONE')) ''
$cpS = @($r.Sent | Where-Object { $_ -match 'BB_R6CP_MARK' })
Check 'G17' '05c: в проверку на Pi подставлены 4 места варианта, BACKUP_ROOT и sha256 манифеста (не в аргументах ssh)' ($cpS.Count -ge 1 -and $cpS[0] -match 'bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix\.py 4a15d699' -and $cpS[0] -match 'BROOT=/home/lb/bb_backup' -and $cpS[0] -match 'MSHA=[0-9a-f]{64}' -and $r.J -notmatch 'bb_backup\]') ''
# правка 2 проверки RV (12.11): резерв варианта - в своей папке BACKUP_ROOT/r2j_cam (своя копия image_target.conf), иначе 06 r5 без метки откатил бы вариант вместо образа
$r5ConfSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $conf).Hash.ToLower()
$tcd = @(Get-ChildItem -LiteralPath $OG -Directory -Filter 'cam_target_install_*'); $tcf = ''; $tcs = 'нет'
if ($tcd.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $tcd[0].FullName 'image_target.conf'))) { $tcf = [IO.File]::ReadAllText((Join-Path $tcd[0].FullName 'image_target.conf')); $tcs = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $tcd[0].FullName 'image_target.conf')).Hash.ToLower() }
$ilt = ''; if ($il.Count -eq 1) { $ilt = [IO.File]::ReadAllText($il[0].FullName) }
Check 'G15b' '05c: на Pi уходит СВОЯ копия image_target.conf (out\cam_target_install_*): DEST_ROOT=/home/lb, BACKUP_ROOT=/home/lb/bb_backup/r2j_cam; общий image_target.conf r5 не уходит; в журнале BACKUP_ROOT_VARIANT и VARIANT_BACKUP с меткой' ($tcd.Count -eq 1 -and $tcf -cmatch '(?m)^DEST_ROOT=/home/lb$' -and $tcf -cmatch '(?m)^BACKUP_ROOT=/home/lb/bb_backup/r2j_cam$' -and @([regex]::Matches($tcf, '(?m)^(DEST_ROOT|BACKUP_ROOT)=')).Count -eq 2 -and -not $tcf.Contains("`r") -and $r.J -match ('upload=image_target\.conf:' + $tcs) -and $r.J -notmatch ('upload=image_target\.conf:' + $r5ConfSha) -and $ilt -match 'BACKUP_ROOT_VARIANT=/home/lb/bb_backup/r2j_cam\r?\n' -and $ilt -match ('TARGET_CONF_SHA256=' + $tcs) -and $ilt -match 'VARIANT_BACKUP=/home/lb/bb_backup/r2j_cam/20261113_100000') ('папок=' + $tcd.Count + ' conf=' + $tcf)
Check 'G17b' '05c: BROOT для проверки на Pi - папка резерва варианта /home/lb/bb_backup/r2j_cam (не общий BACKUP_ROOT)' ($cpS.Count -ge 1 -and $cpS[0] -cmatch '(?m)^BROOT=/home/lb/bb_backup/r2j_cam$') ''
$r = Inst $OG
Check 'G18' '05c: то же разрешение второй раз: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ('code=' + $r.Code)
Set-CamGate @(('CAMERA_SHA256=dabd507659933d082541069cbeed4fab5a8bab814a26ea5fef249e3dcb214e83'), ('LAUNCH_SHA256=5f0954d82ba7b8034e169fa60c99edd8cd501921e923faa5f10f795ccf388294'), ('MANIFEST_SHA256=' + $manSha), 'ПРИМЕЧАНИЕ=второе')
Reset-Fake; Set-Canned 'cp_install' @($cpStop); $o = New-Out; Seed-Params $o
$r = Inst $o
Check 'G19' '05c: проверка на Pi STOP (служба active): код 1, установки нет, ничего не скопировано' ($r.Code -eq 1 -and $r.J -notmatch 'image_install\.sh' -and $r.J -notmatch 'SCP') ('code=' + $r.Code)
Reset-Fake 'install_fail'; Set-Canned 'cp_install' @($cpInstOk); $o = New-Out; Seed-Params $o
$r = Inst $o
Check 'G20' '05c: установка не дошла до конца: код 1, проверки «файлы легли» нет' ($r.Code -eq 1 -and $r.J -notmatch 'key=cp_installed') ('code=' + $r.Code)
Reset-Fake; Set-Canned 'cp_install' @($cpInstOk); Set-Canned 'cp_installed' @(($cpInstd -replace 'CP_RESULT OK', 'CP_RESULT STOP файлы_не_равны_варианту')); $o = New-Out; Seed-Params $o
$r = Inst $o
Check 'G21' '05c: после установки файлы не те: код 1' ($r.Code -eq 1) ('code=' + $r.Code)
Reset-Fake; $o = New-Out; Seed-Params $o
$r = Inst $o "SERVICE`r`nno`r`n"
Check 'G22' '05c: не YES: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
$r = Inst $o "no`r`nYES`r`n"
Check 'G23' '05c: служба не подтверждена (не SERVICE): код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
$r = Run-Cmd 'image_r2j_cam\05c_install_r2j_cam.cmd' "SERVICE`r`nYES`r`n" $o 'OTHER-PC'
Check 'G24' '05c: чужой ПК: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
Reset-Fake 'wrong_host'; $o = New-Out; Seed-Params $o
$r = Inst $o
Check 'G25' '05c: чужой дрон: код не 0 (4), ничего не послано и не скопировано' ($r.Code -ne 0 -and $r.Sent.Count -eq 0 -and $r.J -notmatch 'SCP') ('code=' + $r.Code)
NoGate (Join-Path $IK 'gates\R2J_CAM_APPROVED.txt'); Reset-Fake; $o = New-Out; Seed-Params $o
$r = Inst $o
Check 'G26' '05c: нет разрешения: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
# 06c
$g = Gates-Cam $OG 'rollback'
Check 'G27' 'гейт отката варианта без разрешения: код 1' ($g.Code -eq 1 -and $g.Text -match 'OTKAT_R2J_CAM_APPROVED.txt') $g.Text
Gate (Join-Path $IK 'gates\OTKAT_R2J_CAM_APPROVED.txt') '06c_otkat_r2j_cam'
$g = Gates-Cam (New-Out) 'rollback'
Check 'G28' 'гейт отката: разрешение есть, S2/S3 и сверка настроек не нужны: код 0' ($g.Code -eq 0) $g.Text
$cpRb = "CP_SERVICE bumblebee inactive`nCP_COUNT files=4 r2j=0 cam=4`nCP_BACKUP 20261113_090000 match=1 rolled_back=0 complete=1`nCP_BACKUP 20261113_100000 match=1 rolled_back=0 complete=1`nCP_BACKUP 20261113_110000 match=0 rolled_back=0 complete=1`nCP_BACKUP 20261113_120000 match=1 rolled_back=1 complete=1`nCP_RESULT OK`nBB_R6CP_DONE`n"
$cpRbd = "CP_SERVICE bumblebee inactive`nCP_COUNT files=4 r2j=4 cam=0`nCP_RESULT OK`nBB_R6CP_DONE`n"
Reset-Fake; Set-Canned 'cp_rollback' @($cpRb); Set-Canned 'cp_rolledback' @($cpRbd); $o = New-Out
$r = Run-Cmd 'image_r2j_cam\06c_otkat_r2j_cam.cmd' "SERVICE`r`nYES`r`n" $o
$rl = @(Files $o 'rollback_r2j_cam_*.log')
Check 'G29' '06c: выбирает самый новый полный неоткаченный резерв ИМЕННО этой установки (20261113_100000), откат прежним image_rollback.sh с этой меткой, код 0' ($r.Code -eq 0 -and $r.J -match 'image_rollback\.sh /tmp/imgrb_\d+ 20261113_100000' -and $r.J -match 'key=cp_rolledback') ('code=' + $r.Code + ' ' + $r.J)
Check 'G30' '06c: журнал rollback_r2j_cam_*.log с PERMISSION_SHA256 и BB_IMAGE_ROLLBACK_DONE; на Pi уходят только image_target.conf и image_rollback.sh' ($rl.Count -eq 1 -and ([IO.File]::ReadAllText($rl[0].FullName) -match 'PERMISSION_SHA256=') -and ([IO.File]::ReadAllText($rl[0].FullName) -match 'BB_IMAGE_ROLLBACK_DONE') -and $r.J -match ('upload=image_rollback\.sh:' + $r5sums['image_r2j/image_rollback.sh']) -and $r.J -notmatch 'upload_dir=payload') ''
$tcr = @(Get-ChildItem -LiteralPath $o -Directory -Filter 'cam_target_rollback_*'); $tcrf = ''; $tcrs = 'нет'
if ($tcr.Count -eq 1 -and (Test-Path -LiteralPath (Join-Path $tcr[0].FullName 'image_target.conf'))) { $tcrf = [IO.File]::ReadAllText((Join-Path $tcr[0].FullName 'image_target.conf')); $tcrs = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $tcr[0].FullName 'image_target.conf')).Hash.ToLower() }
$cpR = @($r.Sent | Where-Object { $_ -match 'BB_R6CP_MARK' })
Check 'G30b' '06c: резерв ищется и откатывается в папке варианта: своя копия image_target.conf (BACKUP_ROOT=/home/lb/bb_backup/r2j_cam) уходит на Pi вместо общей, BROOT проверки на Pi - та же папка' ($tcr.Count -eq 1 -and $tcrf -cmatch '(?m)^DEST_ROOT=/home/lb$' -and $tcrf -cmatch '(?m)^BACKUP_ROOT=/home/lb/bb_backup/r2j_cam$' -and $r.J -match ('upload=image_target\.conf:' + $tcrs) -and $r.J -notmatch ('upload=image_target\.conf:' + $r5ConfSha) -and $cpR.Count -ge 1 -and $cpR[0] -cmatch '(?m)^BROOT=/home/lb/bb_backup/r2j_cam$') ('папок=' + $tcr.Count + ' conf=' + $tcrf)
Gate (Join-Path $IK 'gates\OTKAT_R2J_CAM_APPROVED.txt') '06c_otkat_r2j_cam' @('ПРИМЕЧАНИЕ=второе')
Reset-Fake; Set-Canned 'cp_rollback' @(($cpRb -replace 'match=1', 'match=0')); $o = New-Out
$r = Run-Cmd 'image_r2j_cam\06c_otkat_r2j_cam.cmd' "SERVICE`r`nYES`r`n" $o
Check 'G31' '06c: резерва этой установки нет: код 1, откат не запускается' ($r.Code -eq 1 -and $r.J -notmatch 'image_rollback\.sh') ('code=' + $r.Code)
NoGate (Join-Path $IK 'gates\OTKAT_R2J_CAM_APPROVED.txt'); Reset-Fake; $o = New-Out
$r = Run-Cmd 'image_r2j_cam\06c_otkat_r2j_cam.cmd' "SERVICE`r`nYES`r`n" $o
Check 'G32' '06c: нет разрешения: код 1, к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0) ''
[IO.File]::WriteAllBytes($conf, $confOrig)

# ======================= A: отложенный 05v из r5 =======================
Reset-Fake; $o = New-Out
$r = Run-Cmd '_aside\image_r2j_camera_variant_dabd5076_r5\05v_camera_dabd5076_tolko_esli_vladelec_vyberet.cmd' "YES`r`n" $o
Check 'A1' '05v r5 из _aside не запускается: код 1 «нет файла ..\image_install.sh рядом», к дрону не обращались' ($r.Code -eq 1 -and $r.Calls.Count -eq 0 -and $r.Console -match 'image_install\.sh') ('code=' + $r.Code + ' ' + $r.Console)

$env:PATH = $oldPath
Note ''
Note ("ИТОГ r6: PASS $script:pass, FAIL $script:fail")
if ($script:fail -gt 0) { exit 1 } else { exit 0 }
