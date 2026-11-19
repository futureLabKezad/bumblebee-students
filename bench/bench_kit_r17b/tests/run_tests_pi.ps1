# run_tests_pi.ps1 (Claude, 10.11.2026) - тесты Pi-скриптов стенда в WSL без дрона и без ROS: функции замера, main() с поддельным rclpy, проверка аргументов оболочки.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$OutputEncoding = [Text.Encoding]::UTF8
$T = Split-Path -Parent $MyInvocation.MyCommand.Path
$Kit = Split-Path -Parent $T
$Run = Join-Path $T ('run_p_' + (Get-Date).ToString('yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $Run | Out-Null
$Log = Join-Path $Run 'results.txt'
$utf8 = New-Object Text.UTF8Encoding($true); $utf8n = New-Object Text.UTF8Encoding($false)
$script:pass = 0; $script:fail = 0
function Note([string]$s) { Write-Host $s; [IO.File]::AppendAllText($Log, $s + "`r`n", $utf8) }
function Check([string]$id, [string]$what, [bool]$ok, [string]$info = '') {
    if ($ok) { $script:pass++; Note ("PASS $id $what") } else { $script:fail++; Note ("FAIL $id $what  $info") }
}
function ToWsl([string]$p) { return (& wsl.exe wslpath -a ($p.Replace('\', '/'))).Trim() }
function Wsl-Script([string]$name, [string]$body) {
    $f = Join-Path $Run $name
    [IO.File]::WriteAllText($f, ($body -replace "`r`n", "`n"), $utf8n)
    $old = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $o = & wsl.exe -e bash (ToWsl $f) 2>&1 | Out-String
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $old
    [IO.File]::WriteAllText((Join-Path $Run ($name + '.out.txt')), $o, $utf8n)
    return @{ Text = $o; Code = $rc }
}
$w = (Wsl-Script 'probe.sh' 'echo ok').Text
if ($w -notmatch 'ok') { Check 'P0' 'WSL доступен' $false $w; Note 'ИТОГ: PASS 0, FAIL 1'; exit 1 }
$KitW = ToWsl $Kit
$sh = "$KitW/pi/vision_measure.sh"
$r = Wsl-Script 'prep.sh' @"
sed -n '/^# BB_BENCH_PY_BEGIN/,/^# BB_BENCH_PY_END/p' '$sh' > /tmp/bb_vm_code.py
bash -n '$sh' && echo SH_OK
bash -n '$KitW/pi/pi_state.sh' && echo STATE_OK
python3 -m py_compile /tmp/bb_vm_code.py && echo PY_OK
"@
Check 'P1' 'bash -n для vision_measure.sh и pi_state.sh, py_compile встроенного python' ($r.Text -match 'SH_OK' -and $r.Text -match 'STATE_OK' -and $r.Text -match 'PY_OK') $r.Text

# ---- функции ----
$unit = @'
import sys, runpy, os, tempfile
os.environ['BB_BENCH_MAIN'] = '0'
sys.argv = ['x', '10', 'l', 'measure', '0']
ns = runpy.run_path('/tmp/bb_vm_code.py', run_name='bbtest')
rs = ns['rate_stats']; ls = ns['latency_stats']
def chk(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
t = [i / 30.0 for i in range(1, 300)]
r = rs(t, 0, 10)
chk('steady_30hz_no_gaps', r['gaps_over'] == 0 and abs(r['hz'] - 29.9) < 0.2)
t2 = [x for x in t if not (3.0 < x < 4.2)]
r = rs(t2, 0, 10)
chk('one_gap_1.2s', r['gaps_over'] == 1 and 1.1 < r['max_gap'] < 1.4)
chk('gap_exactly_0.5_not_counted', rs([0.0, 0.5, 1.0], 0, 1.0)['gaps_over'] == 0)
r = rs([], 0, 10)
chk('empty', r['count'] == 0 and r['hz'] == 0 and r['start_delay'] == 10 and r['end_silence'] == 10)
r = rs([2.0, 2.1, 2.2], 0, 10)
chk('start_delay_and_end_silence', abs(r['start_delay'] - 2.0) < 1e-9 and abs(r['end_silence'] - 7.8) < 1e-9)
chk('outside_window_ignored', rs([-1, 11, 5], 0, 10)['count'] == 1)
l = ls([10, 20, 30, 40, 100])
chk('latency', l['n'] == 5 and l['mean'] == 40 and l['p50'] == 30 and l['max'] == 100 and 80 < l['p95'] < 100)
chk('latency_empty', ls([])['n'] == 0)
v, f = ns['parse_throttled']('throttled=0x0'); chk('throttled_zero', v == 0 and f == [])
v, f = ns['parse_throttled']('throttled=0x50005'); chk('throttled_flags', 'undervoltage_now' in f and 'throttled_occurred' in f and 'soft_temp_limit_now' not in f)
v, f = ns['parse_throttled']('garbage'); chk('throttled_garbage', v is None and f == [])
chk('pid_ticks_with_spaces_in_comm', ns['parse_pid_ticks']('123 (a b) c) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14') == 23)
b, t_ = ns['parse_proc_stat_cpu']('cpu  100 0 50 800 20 0 5 0 0 0'); chk('proc_stat', (b, t_) == (155, 975))
root = tempfile.mkdtemp()
def mk(pid, cmd):
    d = os.path.join(root, str(pid)); os.makedirs(d); open(os.path.join(d, 'cmdline'), 'wb').write(cmd.replace(' ', '\0').encode())
mk(11, 'python3 /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/aruco_detect.py --ros-args')
mk(12, 'python3 /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/vpe_fix.py')
mk(13, 'bash -c # BB_BENCH_PY_BEGIN aruco_detect.py vpe_fix.py')
mk(14, 'vim notes_about_aruco_detect.py.txt')
found = ns['scan_watch'](root)
chk('scan_finds_detector_and_vpe', found.get('aruco_detect.py') == [11] and found.get('vpe_fix.py') == [12])
chk('scan_skips_own_script_and_editor', 13 not in sum(found.values(), []) and 14 not in sum(found.values(), []))
'@
[IO.File]::WriteAllText((Join-Path $Run 'unit.py'), ($unit -replace "`r`n", "`n"), $utf8n)
$r = Wsl-Script 'unit.sh' ("python3 '" + (ToWsl (Join-Path $Run 'unit.py')) + "'")
$unitLines = @($r.Text -split "`n" | Where-Object { $_ -match '^(PASS|FAIL) ' })
foreach ($l in $unitLines) { Check 'P2' ('функция: ' + $l.Substring(5).Trim()) ($l.StartsWith('PASS ')) '' }
Check 'P2' 'функции: прогнано не меньше 14 проверок' ($unitLines.Count -ge 14) $r.Text

# ---- main() с поддельным rclpy ----
$stub = ToWsl (Join-Path $T 'pystub')
$harness = "$stub/pi_main_test.py"
function Run-Main([string]$scn, [string]$dur, [string]$mode, [string]$wake, [string]$label = 'tst') {
    return (Wsl-Script ('main_' + $scn + '_' + $mode + '_' + $wake + '_' + $dur + '.sh') ("BB_STUB_SCENARIO=$scn python3 '$harness' /tmp/bb_vm_code.py $dur $label $mode $wake"))
}
$m = Run-Main 'armed' '3' 'measure' '1'
Check 'P3' 'main: дрон взведён (measure): REFUSED armed, rc 3, ни одного издателя не создано (детектор не будился)' ($m.Text -match 'REFUSED armed' -and $m.Text -match 'STUB_RC 3' -and $m.Text -match 'STUB_PUBLISHERS none' -and $m.Text -match 'STUB_PUBLISHED_COUNT 0') $m.Text
$m = Run-Main 'disconnected' '3' 'measure' '1'
Check 'P3' 'main: нет связи MAVROS с FCU: REFUSED fcu_not_connected, rc 3, издателей нет' ($m.Text -match 'REFUSED fcu_not_connected' -and $m.Text -match 'STUB_RC 3' -and $m.Text -match 'STUB_PUBLISHERS none') $m.Text
$m = Run-Main 'nostate' '3' 'measure' '1'
Check 'P3' 'main: /mavros/state молчит 8 с: REFUSED no_mavros_state, rc 3, издателей нет' ($m.Text -match 'REFUSED no_mavros_state' -and $m.Text -match 'STUB_RC 3' -and $m.Text -match 'STUB_PUBLISHERS none') $m.Text
$m = Run-Main 'ok' '6' 'measure' '1'
Check 'P4' 'main: дрон не взведён, будить детектор: rc 0, единственный издатель /aruco_detect/wake, Bool true раз в секунду (4-7 сообщений за 6 с)' ($m.Text -match 'STUB_RC 0' -and $m.Text -match 'STUB_PUBLISHERS /aruco_detect/wake\r?\n' -and $m.Text -match 'STUB_PUBLISHED_COUNT [4-7]\r?\n' -and $m.Text -match 'META wake publishing_1Hz') $m.Text
$cnt = ([regex]::Match($m.Text, 'SUMMARY markers_msgs count=(\d+) hz=([\d.]+)'))
Check 'P4' 'main: поток меток считается (около 20 Гц от поддельного детектора)' ($cnt.Success -and [int]$cnt.Groups[1].Value -ge 80 -and [int]$cnt.Groups[1].Value -le 140) ($cnt.Value)
$cam = ([regex]::Match($m.Text, 'SUMMARY camera_image_raw count=(\d+) hz=([\d.]+)'))
Check 'P4' 'main: кадры камеры считаются без разбора сообщений (около 24 Гц)' ($cam.Success -and [int]$cam.Groups[1].Value -ge 100 -and [int]$cam.Groups[1].Value -le 170 -and $m.Text -match 'META camera_subscription raw') ($cam.Value)
Check 'P4' 'main: задержка меток около 50 мс, метка в кадре в 100 процентах, id 0' ($m.Text -match 'SUMMARY latency_ms_header_to_now n=\d+ mean=([4-9]\d|1\d\d)\.' -and $m.Text -match 'with_marker=\d+ \(100\.0%\)' -and $m.Text -match 'SUMMARY marker_ids_seen 0:\d+') ''
Check 'P4' 'main: найден топик зрения /mavros/mavros/pose_cov (в заглушке 0 сообщений: заглушка vpe_fix не воспроизводит) и пометка про disarmed (warm-up) из vpe_fix.py, функция _evaluate_gate' ($m.Text -match 'META vision_topics /mavros/mavros/pose_cov' -and $m.Text -match 'SUMMARY vision_pose /mavros/mavros/pose_cov count=0' -and $m.Text -match 'vpe_fix в r2j на НЕвзведённом дроне пропускает позу в MAVROS') ''
Check 'P4' 'main: есть замер нагрузки SAMPLE и итоги SUMMARY (длительность, cpu, температура, троттлинг, процессы)' ($m.Text -match '(?m)^SAMPLE t=5 ' -and $m.Text -match 'SUMMARY duration_s' -and $m.Text -match 'SUMMARY throttled_flags_seen' -and $m.Text -match 'SUMMARY process_ids_changed') ''
$m = Run-Main 'ok' '3' 'measure' '0'
Check 'P4' 'main: WAKE=0: издателей нет, «META wake off», сообщений в wake не уходит' ($m.Text -match 'STUB_PUBLISHERS none' -and $m.Text -match 'META wake off' -and $m.Text -match 'STUB_PUBLISHED_COUNT 0') $m.Text
$m = Run-Main 'vib_armed' '3' 'vibration' '0'
Check 'P5' 'main: режим vibration, дрон взведён владельцем: замер идёт (rc 0), издателей нет, взведённое состояние записано' ($m.Text -match 'STUB_RC 0' -and $m.Text -match 'STUB_PUBLISHERS none' -and $m.Text -match 'META initial_state connected=True armed=True' -and $m.Text -match 'SUMMARY markers_msgs') $m.Text
$code = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\vision_measure.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P5' 'код: нет create_client, create_service, ActionClient (только подписки и один издатель)' (-not ($code -match 'create_client|create_service|ActionClient')) ''

# ---- оболочка: проверка аргументов ----
$hn = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'
function Run-Sh([string]$argText, [bool]$fakeHost = $true) {
    $body = ''
    if ($fakeHost) { $body += $hn + "`n" }
    $body += "bash '$sh' $argText`necho EXIT=`$?`n"
    return (Wsl-Script ('sh_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.sh') $body)
}
$s = Run-Sh '5 lbl measure 1';      Check 'P6' 'оболочка: длительность 5 с отклонена (нужно 10..1800)' ($s.Text -match 'STOP: duration must be 10..1800' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh '99999 lbl measure 1';  Check 'P6' 'оболочка: длительность 99999 отклонена' ($s.Text -match 'STOP: duration' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh 'abc lbl measure 1';    Check 'P6' 'оболочка: длительность abc отклонена' ($s.Text -match "STOP: bad duration 'abc'" -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh '30 "a b" measure 1';   Check 'P6' 'оболочка: метка с пробелом отклонена' ($s.Text -match 'STOP: bad label' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh '30 "x;y" measure 1';   Check 'P6' 'оболочка: метка x;y отклонена' ($s.Text -match 'STOP: bad label' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh '30 lbl fly 1';         Check 'P6' 'оболочка: режим fly отклонён' ($s.Text -match "STOP: bad mode 'fly'" -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh '30 lbl measure 2';     Check 'P6' 'оболочка: WAKE=2 отклонён' ($s.Text -match "STOP: bad wake '2'" -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Sh '30 lbl measure 1' $false; Check 'P6' 'оболочка: не тот хост (hostname не подменён): STOP, до python не дошло' ($s.Text -match 'STOP: hostname is' -and $s.Text -match 'EXIT=1' -and $s.Text -notmatch 'META script') $s.Text
$s = Run-Sh '30 lbl measure 1';     Check 'P6' 'оболочка: корректные аргументы доходят до запуска (META script ...)' ($s.Text -match 'META script vision_measure.sh dur=30 label=lbl mode=measure wake=1') $s.Text
# ---- arm_state.sh (проверка «разоружён» после полёта, 07) ----
$arm = "$KitW/pi/arm_state.sh"
function Run-Arm([string]$armedVal, [string]$connVal = 'true', [bool]$fakeHost = $true) {
    $body = "d=`$(mktemp -d)`n"
    $body += "cat > `$d/ros2 <<'EOF'`n#!/bin/bash`nf=`"`$*`"`ncase `"`$f`" in *`"--field armed`"*) echo -e `"`$STUB_ARMED`";; *`"--field connected`"*) echo -e `"`$STUB_CONN`";; esac`nEOF`nchmod +x `$d/ros2`n"
    if ($fakeHost) { $body += $hn + "`n" }
    $body += "source(){ :; }; export -f source;`n"  # в WSL стоит настоящий ROS: без этого source ставит настоящий ros2 раньше заглушки
    $body += "PATH=`$d:`$PATH STUB_ARMED='$armedVal' STUB_CONN='$connVal' bash '$arm'`necho EXIT=`$?`nrm -rf `$d`n"
    return (Wsl-Script ('arm_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.sh') $body)
}
$s = Run-Arm 'false';  Check 'P7' 'arm_state.sh: armed=false, connected=true: «BB_ARM connected=true armed=false» и BB_ARM_STATE_DONE' ($s.Text -match 'BB_ARM connected=true armed=false' -and $s.Text -match 'BB_ARM_STATE_DONE' -and $s.Text -match 'EXIT=0') $s.Text
$s = Run-Arm 'true';   Check 'P7' 'arm_state.sh: armed=true читается как armed=true' ($s.Text -match 'BB_ARM connected=true armed=true') $s.Text
$s = Run-Arm 'True';   Check 'P7' 'arm_state.sh: регистр не важен (True -> true)' ($s.Text -match 'armed=true') $s.Text
$s = Run-Arm 'maybe';  Check 'P7' 'arm_state.sh: непонятный ответ -> armed=? (не false)' ($s.Text -match 'armed=\?' -and $s.Text -notmatch 'armed=false') $s.Text
$s = Run-Arm '';       Check 'P7' 'arm_state.sh: пустой ответ -> armed=?' ($s.Text -match 'armed=\?') $s.Text
$s = Run-Arm 'false' 'false'; Check 'P7' 'arm_state.sh: connected=false печатается как есть' ($s.Text -match 'connected=false armed=false') $s.Text
$s = Run-Arm 'false' 'true' $false; Check 'P7' 'arm_state.sh: не тот хост: STOP, ответа BB_ARM нет' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'BB_ARM ' -and $s.Text -match 'EXIT=1') $s.Text
Check 'P7' 'arm_state.sh: синтаксис bash -n' ((Wsl-Script 'armn.sh' "bash -n '$arm' && echo ARM_SYNTAX_OK").Text -match 'ARM_SYNTAX_OK') ''
# ---------- набор r2: gap_counts и markers_used в vision_measure.sh ----------
$unit2 = @'
import sys, runpy, os
os.environ['BB_BENCH_MAIN'] = '0'
sys.argv = ['x', '10', 'l', 'measure', '0']
ns = runpy.run_path('/tmp/bb_vm_code.py', run_name='bbtest')
gc = ns['gap_counts']
def chk(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
t = [i / 30.0 for i in range(1, 300)]
r = gc(t, 0, 10)
chk('gap_counts_steady_no_gaps', r['over_0.4'] == 0 and r['over_1.0'] == 0 and r['over_1.5'] == 0 and r['max'] < 0.05)
t2 = [x for x in t if not (3.0 < x < 4.2)]
r = gc(t2, 0, 10)
chk('gap_counts_one_gap_1.2s', r['over_0.4'] == 1 and r['over_1.0'] == 1 and r['over_1.5'] == 0 and 1.1 < r['max'] < 1.4)
r = gc([0.0, 0.45, 1.0, 2.6], 0, 10)
chk('gap_counts_three_gaps', r['over_0.4'] == 3 and r['over_1.0'] == 1 and r['over_1.5'] == 1 and abs(r['max'] - 1.6) < 1e-9)
chk('gap_counts_exactly_0.4_not_counted', gc([0.0, 0.4, 0.8], 0, 1)['over_0.4'] == 0)
chk('gap_counts_empty', gc([], 0, 10)['n'] == 0 and gc([], 0, 10)['max'] == 0.0 and gc([5.0], 0, 10)['over_0.4'] == 0)
chk('gap_counts_outside_window_ignored', gc([-5.0, 1.0, 1.1, 50.0], 0, 10)['n'] == 2)
'@
[IO.File]::WriteAllText((Join-Path $Run 'unit2.py'), ($unit2 -replace "`r`n", "`n"), $utf8n)
$r = Wsl-Script 'unit2.sh' ("python3 '" + (ToWsl (Join-Path $Run 'unit2.py')) + "'")
$u2 = @($r.Text -split "`n" | Where-Object { $_ -match '^(PASS|FAIL) ' })
foreach ($l in $u2) { Check 'P8' ('функция: ' + $l.Substring(5).Trim()) ($l.StartsWith('PASS ')) '' }
Check 'P8' 'функции gap_counts: прогнано 6 проверок' ($u2.Count -eq 6) $r.Text
$m = Run-Main 'ok' '6' 'measure' '0'
Check 'P9' 'main (r2): markers_used считается, один пропуск «значение >= 1» больше 0,4 с и больше 1,0 с (в заглушке нули 1,5-2,6 с), нулевых сообщений больше 0' ($m.Text -match 'SUMMARY markers_used msgs=\d+ with_ge1=\d+ \([\d.]+%\) with_0=([1-9]\d*)' -and $m.Text -match 'SUMMARY markers_used_ge1_pauses .*over_0\.4s=1 over_1\.0s=1 over_1\.5s=0') $m.Text
Check 'P9' 'main (r2): кадры image_raw_yuv считаются отдельно от image_raw (около 24 Гц), в сводке строка camera_image_raw_yuv' ($m.Text -match 'META camera_yuv_topic /main_camera/image_raw_yuv' -and $m.Text -match 'SUMMARY camera_image_raw_yuv count=(\d+) ' -and [int]([regex]::Match($m.Text, 'SUMMARY camera_image_raw_yuv count=(\d+) ').Groups[1].Value) -ge 100) $m.Text
Check 'P9' 'main (r2): для топика зрения есть строка vision_pose_pauses с over_0.4s (в заглушке сообщений нет: 0)' ($m.Text -match 'SUMMARY vision_pose_pauses /mavros/mavros/pose_cov over_0\.4s=0 over_1\.0s=0 over_1\.5s=0') $m.Text
Check 'P9' 'main (r2): по-прежнему единственный издатель или ни одного (WAKE=0: издателей нет)' ($m.Text -match 'STUB_PUBLISHERS none') ''

# ---------- набор r2: battery_check.sh ----------
$bc = "$KitW/pi/battery_check.sh"
$r = Wsl-Script 'prep_bc.sh' @"
sed -n '/^# BB_BATT_PY_BEGIN/,/^# BB_BATT_PY_END/p' '$bc' > /tmp/bb_bc_code.py
bash -n '$bc' && echo BC_OK
bash -n '$KitW/pi/journal_window.sh' && echo JW_OK
python3 -m py_compile /tmp/bb_bc_code.py && echo BCPY_OK
"@
Check 'P10' 'bash -n для battery_check.sh и journal_window.sh, py_compile встроенного python батареи' ($r.Text -match 'BC_OK' -and $r.Text -match 'JW_OK' -and $r.Text -match 'BCPY_OK') $r.Text
$unit3 = @'
import sys, runpy, os
os.environ['BB_BATT_MAIN'] = '0'
sys.argv = ['x', '10']
ns = runpy.run_path('/tmp/bb_bc_code.py', run_name='bbtest')
def chk(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
ib = ns['is_battery_text']
chk('text_low_battery', ib('Low battery'))
chk('text_critical', ib('CRITICAL: battery empty'))
chk('text_failsafe', ib('Failsafe activated'))
chk('text_voltage', ib('voltage dropped'))
chk('text_unrelated', not ib('Armed by RC') and not ib('') and not ib(None))
st = ns['stats']
s = st([16.0, 16.4, float('nan')])
chk('stats_ignores_nan', s['n'] == 2 and s['min'] == 16.0 and s['max'] == 16.4 and abs(s['mean'] - 16.2) < 1e-9)
chk('stats_empty', st([]) is None and st([float('nan')]) is None)
ft = ns['find_topic']
names = [('/mavros/battery', ['sensor_msgs/msg/BatteryState']), ('/other/battery', ['std_msgs/msg/String']), ('/mavros/statustext/recv', ['mavros_msgs/msg/StatusText'])]
chk('find_topic_by_suffix_and_type', ft(names, '/battery', 'BatteryState') == '/mavros/battery' and ft(names, '/statustext/recv', 'StatusText') == '/mavros/statustext/recv')
chk('find_topic_wrong_type_not_found', ft([('/x/battery', ['std_msgs/msg/String'])], '/battery', 'BatteryState') is None)
class PV:
    def __init__(self, t, b=False, i=0, d=0.0):
        self.type = t; self.bool_value = b; self.integer_value = i; self.double_value = d
pv = ns['param_value']
chk('param_value_int_double_bool_unset', pv(PV(2, i=4)) == ('i', 4) and pv(PV(3, d=3.5)) == ('d', 3.5) and pv(PV(1, b=True)) == ('i', 1) and pv(PV(0)) is None)
chk('params_list_has_the_asked_names', all(n in ns['PARAMS'] for n in ('BAT1_N_CELLS', 'BAT1_V_EMPTY', 'BAT1_V_CHARGED', 'BAT1_SOURCE')))
'@
[IO.File]::WriteAllText((Join-Path $Run 'unit3.py'), ($unit3 -replace "`r`n", "`n"), $utf8n)
$r = Wsl-Script 'unit3.sh' ("python3 '" + (ToWsl (Join-Path $Run 'unit3.py')) + "'")
$u3 = @($r.Text -split "`n" | Where-Object { $_ -match '^(PASS|FAIL) ' })
foreach ($l in $u3) { Check 'P11' ('функция: ' + $l.Substring(5).Trim()) ($l.StartsWith('PASS ')) '' }
Check 'P11' 'функции батареи: прогнано 11 проверок' ($u3.Count -eq 11) $r.Text
$hb = "$stub/pi_batt_test.py"
function Run-Batt([string]$scn, [string]$dur = '2') { return (Wsl-Script ('batt_' + $scn + '.sh') ("BB_STUB_SCENARIO=$scn python3 '$hb' /tmp/bb_bc_code.py $dur")) }
$m = Run-Batt 'ok'
Check 'P12' 'main батареи: rc 0, издателей нет, напряжение 16.20 в сводке, 9 из 11 настроек прочитаны (двух нет в таблице заглушки), BAT1_N_CELLS 4, BAT1_V_EMPTY 3.5, BAT1_V_CHARGED 4.05' ($m.Text -match 'STUB_RC 0' -and $m.Text -match 'STUB_PUBLISHERS none' -and $m.Text -match 'SUMMARY battery_msgs count=\d+ hz=[\d.]+ voltage_v min=16\.20 max=16\.20' -and $m.Text -match 'PARAM BAT1_N_CELLS i 4' -and $m.Text -match 'PARAM BAT1_V_EMPTY d 3\.5' -and $m.Text -match 'PARAM BAT1_V_CHARGED d 4\.05' -and $m.Text -match 'SUMMARY params_read 9 of 11') $m.Text
Check 'P12' 'main батареи: настройки, которых нет в таблице, названы «not_in_MAVROS_table», а не выдуманы; сообщений о батарее среди текстов PX4 нет' ($m.Text -match 'PARAM BAT1_A_PER_V not_in_MAVROS_table' -and $m.Text -match 'PARAM CBRK_SUPPLY_CHK not_in_MAVROS_table' -and $m.Text -match 'SUMMARY statustext count=0 battery_related=0') $m.Text
Check 'P12' 'main батареи: один вызов чтения настроек, темы найдены по суффиксу, состояние дрона записано' ($m.Text -match 'STUB_SERVICE_CALLS 1' -and $m.Text -match 'META battery_topic /mavros/battery' -and $m.Text -match 'META statustext_topic /mavros/statustext/recv' -and $m.Text -match 'META state connected=True armed=False mode=MANUAL') $m.Text
$m = Run-Batt 'bat_warn'
Check 'P12' 'main батареи: сообщение PX4 «Low battery» попало в сводку с пометкой battery_related=yes и счётчиком 1' ($m.Text -match 'STATUSTEXT t=[\d.]+ severity=4 battery_related=yes text=Low battery' -and $m.Text -match 'SUMMARY statustext count=1 battery_related=1') $m.Text
$m = Run-Batt 'nosvc'
Check 'P12' 'main батареи: сервис настроек не отвечает: сказано словами, настройки 0 из 11, rc 0' ($m.Text -match 'META get_parameters service not answering' -and $m.Text -match 'SUMMARY params_read 0 of 11' -and $m.Text -match 'STUB_RC 0') $m.Text
$bcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\battery_check.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P12' 'код battery_check.sh: нет издателей, ParamSet, ParamPull, команд, режимов и записи' (-not ($bcode -match 'create_publisher|ParamSet|ParamPull|CommandBool|SetMode|ros2 service call|ros2 topic pub|setpoint|cmd/')) ''
$hnb = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'
function Run-Bsh([string]$argText, [bool]$fakeHost = $true) {
    $body = ''
    if ($fakeHost) { $body += $hnb + "`n" }
    $body += "bash '$bc' $argText`necho EXIT=`$?`n"
    return (Wsl-Script ('bsh_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.sh') $body)
}
$s = Run-Bsh '5';    Check 'P13' 'battery_check.sh: длительность 5 с отклонена (нужно 10..300)' ($s.Text -match 'STOP: duration must be 10\.\.300' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Bsh 'abc';  Check 'P13' 'battery_check.sh: длительность abc отклонена' ($s.Text -match "STOP: bad duration 'abc'" -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Bsh '999';  Check 'P13' 'battery_check.sh: длительность 999 отклонена' ($s.Text -match 'STOP: duration must be 10\.\.300' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Bsh '30' $false; Check 'P13' 'battery_check.sh: не тот хост: STOP, до python не дошло' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'META script' -and $s.Text -match 'EXIT=1') $s.Text
# ---------- набор r2: journal_window.sh с поддельным journalctl ----------
$jw = "$KitW/pi/journal_window.sh"
function Run-Jw([string]$argText, [bool]$fakeHost = $true) {
    $body = "d=`$(mktemp -d)`n"
    $body += "cat > `$d/journalctl <<'EOF'`n#!/bin/bash`necho `"JARGS `$*`" >> `"`$JLOG`"`necho '2026-11-10T10:00:10.000000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_ok -> publish=True'`necho '2026-11-10T10:00:11.000000+0400 h bumblebee[1]: [INFO] some unrelated line about wifi'`necho '2026-11-10T10:00:12.000000+0400 h bumblebee[1]: [INFO] aruco_detect: searching profile -> SEARCHING (8 empty frames)'`nEOF`nchmod +x `$d/journalctl`n"
    if ($fakeHost) { $body += $hnb + "`n" }
    $body += "JLOG=`$d/jlog PATH=`$d:`$PATH bash '$jw' $argText`necho EXIT=`$?`ncat `$d/jlog 2>/dev/null`nrm -rf `$d`n"
    return (Wsl-Script ('jw_' + [guid]::NewGuid().ToString('N').Substring(0, 6) + '.sh') $body)
}
$s = Run-Jw '300'
Check 'P14' 'journal_window.sh: окно 300 с: journalctl вызван с --since «300 seconds ago» и -u bumblebee, в вывод попали строки шлюза и детектора, посторонняя строка отброшена, BB_JOURNAL_DONE rc=0' ($s.Text -match 'JARGS -u bumblebee --since 300 seconds ago' -and $s.Text -match 'publish=True' -and $s.Text -match 'SEARCHING' -and $s.Text -notmatch 'wifi' -and $s.Text -match 'BB_JOURNAL_DONE rc=0' -and $s.Text -match 'EXIT=0') $s.Text
$s = Run-Jw '30';    Check 'P14' 'journal_window.sh: окно 30 с отклонено (нужно 60..1800)' ($s.Text -match 'STOP: window must be 60\.\.1800' -and $s.Text -match 'EXIT=1' -and $s.Text -notmatch 'JARGS') $s.Text
$s = Run-Jw 'abc';   Check 'P14' 'journal_window.sh: окно abc отклонено, journalctl не вызывался' ($s.Text -match "STOP: bad window 'abc'" -and $s.Text -notmatch 'JARGS') $s.Text
$s = Run-Jw '300' $false; Check 'P14' 'journal_window.sh: не тот хост: STOP, journalctl не вызывался' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'JARGS' -and $s.Text -match 'EXIT=1') $s.Text
# ---------- набор r2: tools_pc (разбор на ПК, только чтение) ----------
$tp = "$KitW/tools_pc"
$jtxt = @'
2026-11-10T10:00:00.000000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: disarmed (warm-up) -> publish=True
2026-11-10T10:00:10.000000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_ok -> publish=True
2026-11-10T10:00:12.000000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_bad (publish suspended) -> publish=False
2026-11-10T10:00:14.500000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_ok -> publish=True
2026-11-10T10:00:20.000000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_bad (publish suspended) -> publish=False
2026-11-10T10:00:20.600000+0400 h bumblebee[1]: [INFO] [1.0] [vpe_publisher]: vpe_fix gate: OFFBOARD + vision_ok -> publish=True
2026-11-10T10:00:21.000000+0400 h bumblebee[1]: [INFO] aruco_detect: searching profile -> SEARCHING (8 empty frames)
2026-11-10T10:00:21.200000+0400 h bumblebee[1]: [INFO] vpe_fix: resume after 0.9 s without a publish: waiting for 3 fresh poses (medoid)
'@
[IO.File]::WriteAllText((Join-Path $Run 'journal_sample.txt'), ($jtxt -replace "`r`n", "`n"), $utf8n)
$r = Wsl-Script 'jvp.sh' ("python3 -B -I '$tp/journal_vision_pauses.py' '" + (ToWsl (Join-Path $Run 'journal_sample.txt')) + "'")
Check 'P15' 'journal_vision_pauses.py: на синтетическом журнале 2 закрытых периода (2,50 и 0,60 с), самый длинный 2.50, сумма 3.10, первая публикация в OFFBOARD сразу (0.00), resume 1, переключений профиля 1' ($r.Text -match 'OFFBOARD_CLOSED count=2' -and $r.Text -match 'length_s=2\.50' -and $r.Text -match 'length_s=0\.60' -and $r.Text -match 'LONGEST_CLOSED_S 2\.50' -and $r.Text -match 'TOTAL_CLOSED_S 3\.10' -and $r.Text -match 'FIRST_OK_AFTER_OFFBOARD_S 0\.00' -and $r.Text -match 'RESUME 1' -and $r.Text -match 'PROFILE_FLIPS_AFTER_OFFBOARD 1') $r.Text
[IO.File]::WriteAllText((Join-Path $Run 'journal_open.txt'), (($jtxt -split "`n" | Select-Object -First 3) -join "`n") + "`n2026-11-10T10:00:18.000000+0400 h bumblebee[1]: [INFO] other line`n", $utf8n)
$r = Wsl-Script 'jvp2.sh' ("python3 -B -I '$tp/journal_vision_pauses.py' '" + (ToWsl (Join-Path $Run 'journal_open.txt')) + "'")
Check 'P15' 'journal_vision_pauses.py: шлюз так и остался закрытым до конца журнала: период назван открытым, длина считается до последней строки (6 с)' ($r.Text -match 'последний период открыт до конца журнала' -and $r.Text -match 'length_s=6\.00') $r.Text
[IO.File]::WriteAllText((Join-Path $Run 'journal_none.txt'), "2026-11-10T10:00:00.000000+0400 h bumblebee[1]: [INFO] nothing about the gate`n", $utf8n)
$r = Wsl-Script 'jvp3.sh' ("python3 -B -I '$tp/journal_vision_pauses.py' '" + (ToWsl (Join-Path $Run 'journal_none.txt')) + "'")
Check 'P15' 'journal_vision_pauses.py: в журнале нет строк шлюза с OFFBOARD: сказано «не измеримо», а не «0 пауз»' ($r.Text -match 'в журнале нет строки шлюза с OFFBOARD' -and $r.Text -match 'not measurable' -and $r.Text -notmatch 'LONGEST_CLOSED_S') $r.Text
$r = Wsl-Script 'jvp4.sh' ("python3 -B -I '$tp/journal_vision_pauses.py' /nonexistent/file.txt; echo EXIT=`$?")
Check 'P15' 'journal_vision_pauses.py: нет файла: ERROR и код 2' ($r.Text -match 'ERROR file=' -and $r.Text -match 'EXIT=2') $r.Text
# ---------- набор r2: install_check.sh и mavros_check.sh (поддельные ros2, hostname и дерево файлов) ----------
$ic = "$KitW/pi/install_check.sh"; $mc = "$KitW/pi/mavros_check.sh"
$r = Wsl-Script 'prep_ic.sh' "bash -n '$ic' && echo IC_OK`nbash -n '$mc' && echo MC_OK"
Check 'P18' 'bash -n для install_check.sh и mavros_check.sh' ($r.Text -match 'IC_OK' -and $r.Text -match 'MC_OK') $r.Text
$tplIc = @'
set +e
d=$(mktemp -d)
H=$d/home
B=$H/ros2_ws/src/bumblebee/src/cpp
P=$d/pfx/lib/bumblebee
mkdir -p $B $P $d/bin $d/pfx/share/bumblebee/launch $H/ros2_ws/src/bumblebee/scripts
echo l1 > $d/pfx/share/bumblebee/launch/bumblebee.launch.py; echo fcu_fixed > $H/ros2_ws/src/bumblebee/scripts/fcu_detect.py
echo a > $P/a.py; echo b > $P/b.py; echo binS > $P/simple_offboard; echo binH > $P/shell
echo rsrc > $B/x.cpp; echo nsrc > $B/y.cpp
touch -d '2026-01-01 00:00:00' $B/x.cpp
touch -d '2026-01-02 00:00:00' $P/simple_offboard $P/shell
sa=$(sha256sum $P/a.py | cut -c1-64); sb=$(sha256sum $P/b.py | cut -c1-64); sx=$(sha256sum $B/x.cpp | cut -c1-64); sy=$(sha256sum $B/y.cpp | cut -c1-64); sl=$(sha256sum $d/pfx/share/bumblebee/launch/bumblebee.launch.py | cut -c1-64); sf=$(sha256sum $H/ros2_ws/src/bumblebee/scripts/fcu_detect.py | cut -c1-64)
__MUTATION__
cat > $d/bin/ros2 <<EOF
#!/bin/bash
if [ "\$1" = pkg ]; then echo __PFX__; fi
EOF
chmod +x $d/bin/ros2
LIST="$sa  a.py\n$sb  b.py"
CPP="$sx  ros2_ws/src/bumblebee/src/cpp/x.cpp  R\n$sy  ros2_ws/src/bumblebee/src/cpp/y.cpp  -"
BINS="simple_offboard\nshell"
RT="$sl  LAUNCH  launch/bumblebee.launch.py\n$sf  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"
awk -v l="$LIST" -v c="$CPP" -v b="$BINS" -v r="$RT" '{ if ($0 == "#@@LIST@@") printf "%s\n", l; else if ($0 == "#@@CPP@@") printf "%s\n", c; else if ($0 == "#@@BINS@@") printf "%s\n", b; else if ($0 == "#@@RT@@") printf "%s\n", r; else print }' '__IC__' > $d/gen.sh
__HOST__
source(){ :; }; export -f source
HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh
echo EXIT=$?
rm -rf $d
'@
function Run-Ic([string]$mode) {
    $mut = @{ pydiff = 'echo changed > $P/b.py'; pymissing = 'rm $P/b.py'; cppdiff = 'echo changed > $B/y.cpp'; cppmissing = 'rm $B/y.cpp'; stale = "touch -d '2025-12-01 00:00:00' `$P/simple_offboard"; binmissing = 'rm $P/shell'; launchdiff = 'echo changed > $d/pfx/share/bumblebee/launch/bumblebee.launch.py'; launchmissing = 'rm $d/pfx/share/bumblebee/launch/bumblebee.launch.py'; fcudiff = 'echo fcu_old > $H/ros2_ws/src/bumblebee/scripts/fcu_detect.py'; fcumissing = 'rm $H/ros2_ws/src/bumblebee/scripts/fcu_detect.py' }
    $m = ''; if ($mut.ContainsKey($mode)) { $m = $mut[$mode] }
    $pfx = '$d/pfx'; if ($mode -eq 'noprefix') { $pfx = '' }
    $host_ = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'; if ($mode -eq 'badhost') { $host_ = '' }
    $body = $tplIc.Replace('__MUTATION__', $m).Replace('__PFX__', $pfx).Replace('__IC__', $ic).Replace('__HOST__', $host_)
    return (Wsl-Script ('ic_' + $mode + '.sh') $body)
}
$ico = 'noprefix=0 cpp_ok=2 cpp_diff=0 cpp_missing=0 bin_ok=2 bin_missing=0 stale=0'
$s = Run-Ic 'ok'
Check 'P19' 'install_check.sh: всё совпало: python OK x2, C++ исходники OK x2, бинарники не старше изменённых исходников: итог ok=2 diff=0 missing=0 ... stale=0, префикс назван, BB_INSTALL_CHECK_DONE' ($s.Text -match 'INSTALL_FILE a\.py OK' -and $s.Text -match 'INSTALL_FILE b\.py OK' -and $s.Text -match 'CPP_SRC ros2_ws/src/bumblebee/src/cpp/x\.cpp OK R' -and $s.Text -match 'INSTALL_BIN simple_offboard sha=[0-9a-f]{64}' -and $s.Text -match ('BB_INSTALL_CHECK ok=2 diff=0 missing=0 ' + $ico) -and $s.Text -match 'INSTALL_PREFIX /tmp/' -and $s.Text -match 'BB_INSTALL_CHECK_DONE' -and $s.Text -cnotmatch 'STALE' -and $s.Text -match 'RT_FILE LAUNCH launch/bumblebee\.launch\.py OK' -and $s.Text -match 'RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect\.py OK' -and $s.Text -match 'BB_RTPY ok=2 diff=0 missing=0') $s.Text
$s = Run-Ic 'pydiff'
Check 'P19' 'install_check.sh: python-узел изменён: «INSTALL_FILE b.py DIFF», итог ok=1 diff=1' ($s.Text -match 'INSTALL_FILE b\.py DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'BB_INSTALL_CHECK ok=1 diff=1 missing=0 ') $s.Text
$s = Run-Ic 'pymissing'
Check 'P19' 'install_check.sh: python-узла нет: «INSTALL_FILE b.py MISSING», missing=1' ($s.Text -match 'INSTALL_FILE b\.py MISSING' -and $s.Text -match 'BB_INSTALL_CHECK ok=1 diff=0 missing=1 ') $s.Text
$s = Run-Ic 'cppdiff'
Check 'P19' 'install_check.sh: C++ исходник (не R) изменён: «CPP_SRC y.cpp DIFF», cpp_ok=1 cpp_diff=1, stale не растёт (флаг «-» не считается)' ($s.Text -match 'CPP_SRC ros2_ws/src/bumblebee/src/cpp/y\.cpp DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'cpp_ok=1 cpp_diff=1 cpp_missing=0 bin_ok=2 bin_missing=0 stale=0') $s.Text
$s = Run-Ic 'cppmissing'
Check 'P19' 'install_check.sh: C++ исходника нет: «CPP_SRC y.cpp MISSING», cpp_missing=1' ($s.Text -match 'CPP_SRC ros2_ws/src/bumblebee/src/cpp/y\.cpp MISSING' -and $s.Text -match 'cpp_ok=1 cpp_diff=0 cpp_missing=1 ') $s.Text
$s = Run-Ic 'stale'
Check 'P19' 'install_check.sh: бинарник старше изменённого исходника (флаг R): «INSTALL_BIN simple_offboard ... STALE», stale=1' ($s.Text -match 'INSTALL_BIN simple_offboard sha=[0-9a-f]{64} mtime=\d+ newest_changed_src=\d+ STALE' -and $s.Text -match 'bin_ok=2 bin_missing=0 stale=1' -and $s.Text -notmatch 'INSTALL_BIN shell [^\n]*STALE') $s.Text
$s = Run-Ic 'binmissing'
Check 'P19' 'install_check.sh: бинарника нет: «INSTALL_BIN shell MISSING», bin_missing=1' ($s.Text -match 'INSTALL_BIN shell MISSING' -and $s.Text -match 'bin_ok=1 bin_missing=1 stale=0') $s.Text
# S2 (чат 1, 21:50): launch-файлы из <префикс>/share/bumblebee/launch и fcu_detect.py (исправление порта) по sha256
$s = Run-Ic 'launchdiff'
Check 'P19' 'install_check.sh: launch-файл в install, который исполняется, отличается: «RT_FILE LAUNCH ... DIFF», BB_RTPY ok=1 diff=1' ($s.Text -match 'RT_FILE LAUNCH launch/bumblebee\.launch\.py DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'BB_RTPY ok=1 diff=1 missing=0') $s.Text
$s = Run-Ic 'launchmissing'
Check 'P19' 'install_check.sh: launch-файла нет: «RT_FILE LAUNCH ... MISSING», missing=1' ($s.Text -match 'RT_FILE LAUNCH launch/bumblebee\.launch\.py MISSING' -and $s.Text -match 'BB_RTPY ok=1 diff=0 missing=1') $s.Text
$s = Run-Ic 'fcudiff'
Check 'P19' 'install_check.sh: fcu_detect.py на Pi прежний (не исправленный): «RT_FILE FCU ... DIFF», diff=1' ($s.Text -match 'RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect\.py DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'BB_RTPY ok=1 diff=1 missing=0') $s.Text
$s = Run-Ic 'fcumissing'
Check 'P19' 'install_check.sh: fcu_detect.py на Pi нет: MISSING, missing=1' ($s.Text -match 'RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect\.py MISSING' -and $s.Text -match 'BB_RTPY ok=1 diff=0 missing=1') $s.Text
$s = Run-Ic 'noprefix'
Check 'P19' 'install_check.sh: ros2 не знает пакет bumblebee: noprefix=1, файлы не проверяются' ($s.Text -match 'INSTALL_PREFIX none' -and $s.Text -match 'noprefix=1' -and $s.Text -notmatch 'INSTALL_FILE' -and $s.Text -notmatch 'CPP_SRC') $s.Text
$s = Run-Ic 'badhost'
Check 'P19' 'install_check.sh: не тот хост: STOP, ни одной сверки' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'INSTALL_FILE' -and $s.Text -match 'EXIT=1') $s.Text
$srcTpl = @'
set +e
d=$(mktemp -d)
H=$d/home
mkdir -p $H/ros2_ws/install $H/bench_ws/r2j/install $d/bin
echo x > $H/ros2_ws/install/setup.bash; echo x > $H/bench_ws/r2j/install/local_setup.bash
printf 'source /home/lb/ros2_ws/install/setup.bash\nsource /home/lb/bench_ws/r2j/install/local_setup.bash\nsource /tmp/evil.sh\nsource /home/lb/bench_ws/mavros/install/local_setup.bash; touch /tmp/BB_PWNED_TEST\n' > $H/start_bumblebee.sh
rm -f /tmp/BB_PWNED_TEST
printf '#!/bin/bash\nexit 0\n' > $d/bin/ros2; chmod +x $d/bin/ros2
awk '{ if ($0 == "#@@LIST@@" || $0 == "#@@CPP@@" || $0 == "#@@BINS@@") print "# пусто"; else print }' '__SCRIPT__' > $d/gen.sh
hostname(){ echo bumblebee-20ec; }; export -f hostname
source(){ echo "SRC $1"; }; export -f source
HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh
echo EXIT=$?
echo PWNED=$(test -e /tmp/BB_PWNED_TEST && echo yes || echo no)
rm -rf $d
'@
$s = Wsl-Script 'ic_overlay_src.sh' $srcTpl.Replace('__SCRIPT__', $ic)
Check 'P19' 'install_check.sh: подключает как запуск службы ТОЛЬКО четыре известные строки source из start_bumblebee.sh (ros2_ws, r2j найдены и подключены), постороннюю строку и строку с «; touch» не выполняет' ($s.Text -match 'SRC [^\r\n]*/home/ros2_ws/install/setup\.bash' -and $s.Text -match 'SRC [^\r\n]*/home/bench_ws/r2j/install/local_setup\.bash' -and $s.Text -notmatch 'evil' -and $s.Text -match 'PWNED=no') $s.Text
$icode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\install_check.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P19' 'install_check.sh: в коде нет записи, publisher, ParamSet, команд (только sha256sum, stat, find, ros2 pkg prefix)' (-not ($icode -match 'create_publisher|ParamSet|ParamPull|ros2 service call|ros2 topic pub|(^|[\s;|&(])(rm|mv|cp|tee|mkdir|touch|chmod|sudo|colcon|cmake|make)\s')) ''
function Run-Mc([string]$mode) {
    # mode: ok | diff | missing | apt | badhost | nogit
    $body = "set +e`nd=`$(mktemp -d)`nS=`$d/home/bench_ws/mavros/src/mavros-source`nmkdir -p `$S/mavros/src `$d/bin `$d/home/bench_ws/mavros/install/mavros/share/mavros`nfor n in f1 f2 f3 f4 f5; do echo `"src `$n`" > `$S/mavros/src/`$n.cpp; done`n"
    $body += "echo '<version>2.14.0</version>' > `$d/home/bench_ws/mavros/install/mavros/share/mavros/package.xml`n"
    $body += "L=''; for n in f1 f2 f3 f4 f5; do L=`"`$L`$(sha256sum `$S/mavros/src/`$n.cpp | cut -c1-64)  mavros/src/`$n.cpp\n`"; done`n"
    if ($mode -eq 'diff') { $body += "echo changed > `$S/mavros/src/f2.cpp`n" }
    if ($mode -eq 'missing') { $body += "rm `$S/mavros/src/f5.cpp`n" }
    if ($mode -ne 'nogit') { $body += "echo 'commit=d63a23674dd80ff4525829ca4bd716bbcc773111' > `$d/home/bench_ws/mavros_src_mode.txt`n" }
    $pfx = '$d/home/bench_ws/mavros/install/mavros'; if ($mode -eq 'apt') { $pfx = '/opt/ros/jazzy' }
    $body += "cat > `$d/bin/ros2 <<EOF`n#!/bin/bash`nif [ `"\`$1`" = pkg ]; then echo $pfx; fi`nEOF`nchmod +x `$d/bin/ros2`n"
    $body += "awk -v l=`"`$L`" '{ if (`$0 == `"#@@LIST@@`") printf `"%s`", l; else print }' '$mc' > `$d/gen.sh`n"
    if ($mode -ne 'badhost') { $body += "hostname(){ echo bumblebee-20ec; }; export -f hostname;`n" }
    $body += "source(){ :; }; export -f source;`nHOME=`$d/home PATH=`$d/bin:`$PATH bash `$d/gen.sh`necho EXIT=`$?`nrm -rf `$d`n"
    return (Wsl-Script ('mc_' + $mode + '.sh') $body)
}
$s = Run-Mc 'ok'
Check 'P20' 'mavros_check.sh: 5 исходников совпали, коммит из mavros_src_mode.txt, активный префикс из bench_ws, версия пакета: итог src_ok=5, BB_MAVROS_CHECK_DONE' ($s.Text -match 'BB_MAVROS_CHECK src_ok=5 src_diff=0 src_missing=0' -and $s.Text -match 'MAVROS_SRC_MODE commit=d63a23674dd80ff4525829ca4bd716bbcc773111' -and $s.Text -match 'MAVROS_ACTIVE_PREFIX .*/home/bench_ws/mavros/install/mavros' -and $s.Text -match 'MAVROS_PKG_VERSION 2\.14\.0' -and $s.Text -match 'BB_MAVROS_CHECK_DONE') $s.Text
$s = Run-Mc 'diff'
Check 'P20' 'mavros_check.sh: один исходник изменён: «DIFF», src_ok=4 src_diff=1' ($s.Text -match 'MAVROS_SRC mavros/src/f2\.cpp DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'src_ok=4 src_diff=1 src_missing=0') $s.Text
$s = Run-Mc 'missing'
Check 'P20' 'mavros_check.sh: исходника нет: «MISSING», src_missing=1' ($s.Text -match 'MAVROS_SRC mavros/src/f5\.cpp MISSING' -and $s.Text -match 'src_ok=4 src_diff=0 src_missing=1') $s.Text
$s = Run-Mc 'apt'
Check 'P20' 'mavros_check.sh: активен MAVROS из /opt/ros (apt): префикс назван как есть' ($s.Text -match 'MAVROS_ACTIVE_PREFIX /opt/ros/jazzy') $s.Text
$s = Run-Mc 'nogit'
Check 'P20' 'mavros_check.sh: нет mavros_src_mode.txt и нет git: «MAVROS_SRC_MODE none», «MAVROS_GIT_HEAD none» (коммит не выдумывается)' ($s.Text -match 'MAVROS_SRC_MODE none' -and $s.Text -match 'MAVROS_GIT_HEAD none') $s.Text
$s = Run-Mc 'badhost'
Check 'P20' 'mavros_check.sh: не тот хост: STOP, ничего не читалось' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'MAVROS_SRC' -and $s.Text -match 'EXIT=1') $s.Text
$mcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\mavros_check.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P20' 'mavros_check.sh: в коде нет записи и сборки (нет colcon, cmake, make, git checkout/fetch/pull, apt, pip), git только rev-parse и describe' (-not ($mcode -match '(^|[\s;|&(])(colcon|cmake|make|apt|apt-get|pip|rm|mv|cp|tee|mkdir|touch|chmod|sudo)\s' -or $mcode -match 'git\s+(-C\s+\S+\s+)?(checkout|fetch|pull|clone|reset|clean|add|commit|config)') -and $mcode -match 'rev-parse' -and $mcode -match 'describe') ''
# ---------- набор r2: mavros_build_precheck.sh (чтение) и mavros_build_aside.sh (перенос в сторону, без удаления) ----------
$pc = "$KitW/pi/mavros_build_precheck.sh"; $as = "$KitW/pi/mavros_build_aside.sh"
$r = Wsl-Script 'prep_mb.sh' "bash -n '$pc' && echo PC_OK`nbash -n '$as' && echo AS_OK"
Check 'P21' 'bash -n для mavros_build_precheck.sh и mavros_build_aside.sh' ($r.Text -match 'PC_OK' -and $r.Text -match 'AS_OK') $r.Text
$tplPc = @'
set +e
d=$(mktemp -d)
mkdir -p $d/home/bench_ws $d/bin
cat > $d/bin/systemctl <<EOF
#!/bin/bash
echo __SVC__
EOF
cat > $d/bin/df <<EOF
#!/bin/bash
printf 'Filesystem 1M-blocks Used Available Capacity Mounted\nx 100000 1 __FREE__ 1%% /\n'
EOF
cat > $d/bin/ps <<EOF
#!/bin/bash
echo __PS__
EOF
cat > $d/bin/ros2 <<EOF
#!/bin/bash
if [ "\$1" = pkg ]; then echo /opt/ros/jazzy; fi
EOF
chmod +x $d/bin/*
__EXTRA__
__HOST__
source(){ :; }; export -f source
HOME=$d/home PATH=$d/bin:$PATH bash '__PC__'
echo EXIT=$?
rm -rf $d
'@
function Run-Pc([string]$mode) {
    $svc = 'inactive'; $free = '20000'; $ps = 'bash'; $extra = ''; $host_ = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'
    if ($mode -eq 'svc') { $svc = 'active' }
    if ($mode -eq 'disk') { $free = '100' }
    if ($mode -eq 'busy') { $ps = 'colcon' }
    if ($mode -eq 'exists') { $extra = 'mkdir -p $d/home/bench_ws/mavros' }
    if ($mode -eq 'incoming') { $extra = 'mkdir -p $d/home/bench_ws/incoming/rc3_mavros' }
    if ($mode -eq 'badhost') { $host_ = '' }
    $body = $tplPc.Replace('__SVC__', $svc).Replace('__FREE__', $free).Replace('__PS__', $ps).Replace('__EXTRA__', $extra).Replace('__HOST__', $host_).Replace('__PC__', $pc)
    return (Wsl-Script ('mbpre_' + $mode + '.sh') $body)
}
$s = Run-Pc 'ok'
Check 'P22' 'precheck: всё в порядке (служба не active, mavros и incoming нет, диск 20000 МБ, сборок нет): BB_MBPRE_RESULT OK, состояние apt и префикс напечатаны' ($s.Text -match 'MBPRE service_bumblebee inactive' -and $s.Text -match 'MBPRE absent .*/bench_ws/mavros' -and $s.Text -match 'MBPRE disk_free_mb 20000' -and $s.Text -match 'MBPRE builders_running 0' -and $s.Text -match 'MBPRE apt_state ' -and $s.Text -match 'MBPRE active_prefix /opt/ros/jazzy' -and $s.Text -match 'BB_MBPRE_RESULT OK' -and $s.Text -match 'BB_MBPRE_DONE') $s.Text
$s = Run-Pc 'svc'
Check 'P22' 'precheck: служба bumblebee активна: STOP с просьбой остановить самому (sudo не вызывается скриптом)' ($s.Text -match 'BB_MBPRE_RESULT STOP.*служба_bumblebee_активна') $s.Text
$s = Run-Pc 'disk'
Check 'P22' 'precheck: мало места (100 МБ): STOP' ($s.Text -match 'BB_MBPRE_RESULT STOP.*мало_места_на_диске') $s.Text
$s = Run-Pc 'busy'
Check 'P22' 'precheck: идёт colcon: STOP' ($s.Text -match 'MBPRE builders_running [1-9]' -and $s.Text -match 'BB_MBPRE_RESULT STOP.*идёт_сборка') $s.Text
$s = Run-Pc 'exists'
Check 'P22' 'precheck: ~/bench_ws/mavros уже есть: STOP (ничего не перезаписывается)' ($s.Text -match 'MBPRE exists .*/bench_ws/mavros' -and $s.Text -match 'BB_MBPRE_RESULT STOP.*уже_есть_mavros') $s.Text
$s = Run-Pc 'incoming'
Check 'P22' 'precheck: ~/bench_ws/incoming/rc3_mavros уже есть: STOP' ($s.Text -match 'BB_MBPRE_RESULT STOP.*уже_есть_rc3_mavros') $s.Text
$s = Run-Pc 'badhost'
Check 'P22' 'precheck: не тот хост: STOP, ничего не читалось' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'MBPRE' -and $s.Text -match 'EXIT=1') $s.Text
$pcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\mavros_build_precheck.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P22' 'precheck: в коде нет записи и остановки служб (нет rm, mv, cp, tee, mkdir, touch, chmod, sudo, systemctl stop/start/restart, colcon, cmake)' (-not ($pcode -match '(^|[\s;|&(])(rm|mv|cp|tee|mkdir|touch|chmod|sudo|colcon|cmake)\s' -or $pcode -match 'systemctl\s+(stop|start|restart|enable|disable|kill)')) ''
$tplAs = @'
set +e
d=$(mktemp -d)
H=$d/home
mkdir -p $H/bench_ws/mavros/src $H/bench_ws/mavros_deps $H/bench_ws/incoming/rc3_mavros $d/bin
echo s > $H/bench_ws/mavros/src/f.cpp; echo m > $H/bench_ws/mavros_src_mode.txt; echo l > $H/bench_ws/build_mavros_1.log; echo w > $H/bench_ws/mavros_watch_1.txt; echo k > $H/bench_ws/incoming/rc3_mavros/m1_unpack.sh
echo '#!/bin/bash' > $H/start_bumblebee.sh; echo 'source /home/lb/ros2_ws/install/setup.bash' >> $H/start_bumblebee.sh
echo keep > $H/bench_ws/other_file.txt
cat > $d/bin/ps <<EOF
#!/bin/bash
echo __PS__
EOF
chmod +x $d/bin/ps
__EXTRA__
before=$(find $H -type f | sed "s|$H/||" | sort | md5sum | cut -c1-32)
n_before=$(find $H -type f | wc -l)
__HOST__
HOME=$H PATH=$d/bin:$PATH bash '__AS__'
echo EXIT=$?
echo FILES_BEFORE=$n_before FILES_AFTER=$(find $H -type f | wc -l)
echo MAVROS_DIR_EXISTS=$(test -e $H/bench_ws/mavros && echo yes || echo no)
echo ASIDE_HAS_F=$(find $H/bench_ws/_aside_mavros_* -name f.cpp 2>/dev/null | wc -l)
echo OTHER_KEPT=$(test -f $H/bench_ws/other_file.txt && echo yes || echo no)
echo START_SCRIPT_BYTES=$(wc -c < $H/start_bumblebee.sh)
rm -rf $d
'@
function Run-As([string]$mode) {
    $ps = 'bash'; $extra = ''; $host_ = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'
    if ($mode -eq 'busy') { $ps = 'colcon' }
    if ($mode -eq 'overlay') { $extra = 'echo ''source /home/lb/bench_ws/mavros/install/local_setup.bash'' >> $H/start_bumblebee.sh' }
    if ($mode -eq 'nothing') { $extra = 'rm -rf $H/bench_ws/mavros' }
    if ($mode -eq 'badhost') { $host_ = '' }
    $body = $tplAs.Replace('__PS__', $ps).Replace('__EXTRA__', $extra).Replace('__HOST__', $host_).Replace('__AS__', $as)
    return (Wsl-Script ('mbas_' + $mode + '.sh') $body)
}
$s = Run-As 'ok'
Check 'P23' 'aside: перенос в сторону: BB_ASIDE_DONE, ~/bench_ws/mavros больше нет на месте, но файл f.cpp лежит в _aside_mavros_<метка>; число файлов до и после ОДИНАКОВОЕ (ничего не удалено); чужой файл и start_bumblebee.sh не тронуты' ($s.Text -match 'BB_ASIDE_DONE .*/bench_ws/_aside_mavros_\d{8}_\d{6} files=\d+' -and $s.Text -match 'MAVROS_DIR_EXISTS=no' -and $s.Text -match 'ASIDE_HAS_F=1' -and $s.Text -match 'FILES_BEFORE=(\d+) FILES_AFTER=\1' -and $s.Text -match 'OTHER_KEPT=yes' -and $s.Text -match 'EXIT=0') $s.Text
$s = Run-As 'overlay'
Check 'P23' 'aside: start_bumblebee.sh подключает оверлей bench_ws/mavros: STOP, ничего не перенесено (папка на месте)' ($s.Text -match 'STOP: start_bumblebee\.sh подключает оверлей' -and $s.Text -match 'MAVROS_DIR_EXISTS=yes' -and $s.Text -match 'ASIDE_HAS_F=0' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-As 'busy'
Check 'P23' 'aside: идёт сборка (colcon): STOP, ничего не перенесено' ($s.Text -match 'STOP: идёт сборка' -and $s.Text -match 'MAVROS_DIR_EXISTS=yes' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-As 'nothing'
Check 'P23' 'aside: нечего переносить (нет ~/bench_ws/mavros): STOP' ($s.Text -match 'STOP: нет .*bench_ws/mavros, нечего переносить' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-As 'badhost'
Check 'P23' 'aside: не тот хост: STOP, ничего не перенесено' ($s.Text -match 'STOP: hostname is' -and $s.Text -match 'MAVROS_DIR_EXISTS=yes' -and $s.Text -match 'EXIT=1') $s.Text
$acode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\mavros_build_aside.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P23' 'aside: в коде нет удаления (нет rm, rmdir, shred, unlink, find -delete) и нет sudo; только mv и mkdir' (-not ($acode -match '(^|[\s;|&(])(rm|rmdir|shred|unlink|sudo)\s' -or $acode -match '-delete') -and $acode -match '(^|[\s;|&(])mv\s') ''
# ---------- набор r2: шаги 13-17 (bb_build_precheck, bb_build (только отказы), bb_build_aside, overlay_fingerprint, overlay_connect, overlay_disconnect) ----------
$bpc = "$KitW/pi/bb_build_precheck.sh"; $bbd = "$KitW/pi/bb_build.sh"; $bas = "$KitW/pi/bb_build_aside.sh"; $ofp = "$KitW/pi/overlay_fingerprint.sh"; $ocn = "$KitW/pi/overlay_connect.sh"; $odc = "$KitW/pi/overlay_disconnect.sh"
$r = Wsl-Script 'prep_bb.sh' "for f in '$bpc' '$bbd' '$bas' '$ofp' '$ocn' '$odc'; do bash -n `"`$f`" && echo SYN_OK; done"
Check 'P24' 'bash -n для шести скриптов шагов 13-17' (([regex]::Matches($r.Text, 'SYN_OK')).Count -eq 6) $r.Text
# общая заготовка: поддельный HOME, systemctl, ps, df, ros2, dpkg-query; список подставляется awk-ом вместо маркеров
$bbCommon = @'
set +e
d=$(mktemp -d)
H=$d/home
SRC=$H/ros2_ws/src/bumblebee
mkdir -p $SRC/src/cpp $SRC/src/python $d/bin $H/bench_ws
mkdir -p $SRC/examples; echo hover_r6 > $SRC/examples/hover_marker0.py; echo '<package/>' > $SRC/package.xml; echo cmake > $SRC/CMakeLists.txt; echo x > $SRC/src/cpp/a.cpp; echo y > $SRC/src/cpp/b.h
sp=$(sha256sum $SRC/package.xml | cut -c1-64); sc=$(sha256sum $SRC/CMakeLists.txt | cut -c1-64); sa=$(sha256sum $SRC/src/cpp/a.cpp | cut -c1-64); sb=$(sha256sum $SRC/src/cpp/b.h | cut -c1-64); sh=$(sha256sum $SRC/examples/hover_marker0.py | cut -c1-64)
CPP="$sp  ros2_ws/src/bumblebee/package.xml  R\n$sc  ros2_ws/src/bumblebee/CMakeLists.txt  R\n$sa  ros2_ws/src/bumblebee/src/cpp/a.cpp  -\n$sb  ros2_ws/src/bumblebee/src/cpp/b.h  R"
cat > $d/bin/systemctl <<EOF
#!/bin/bash
if [ "\$1" = is-active ]; then if [ "\$2" != --quiet ]; then echo __SVC__; fi; [ "__SVC__" = active ]; exit \$?; fi
EOF
cat > $d/bin/ps <<EOF
#!/bin/bash
echo __PS__
EOF
cat > $d/bin/df <<EOF
#!/bin/bash
printf 'Filesystem 1M-blocks Used Available Capacity Mounted\nx 100000 1 20000 1%% /\n'
EOF
cat > $d/bin/dpkg-query <<'EOF'
#!/bin/bash
full=0; pk=()
for a in "$@"; do case "$a" in -W) ;; *Package*) full=1;; *Status-Abbrev*) ;; *) pk+=("$a");; esac; done
for p in "${pk[@]}"; do if [ $full = 1 ]; then echo "$p ii 1.0"; else echo ii; fi; done
EOF
cat > $d/bin/ros2 <<EOF
#!/bin/bash
if [ "\$1" = pkg ]; then echo /home/lb/ros2_ws/install/bumblebee; fi
EOF
chmod +x $d/bin/*
__EXTRA__
awk -v c="$CPP" -v h="$sh" '{ if ($0 == "#@@CPP@@") printf "%s\n", c; else if ($0 == "#@@HOVER@@") printf "%s\n", h; else print }' '__SCRIPT__' > $d/gen.sh
__HOST__
source(){ :; }; export -f source
HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh __ARGS__
echo EXIT=$?
__AFTER__
rm -rf $d
'@
function Run-Bb([string]$script, [string]$name, [string]$extra = '', [string]$svc = 'inactive', [string]$ps = 'bash', [bool]$goodHost = $true, [string]$after = '', [string]$argText = '') {
    $host_ = ''; if ($goodHost) { $host_ = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;' }
    $body = $bbCommon.Replace('__EXTRA__', $extra).Replace('__SVC__', $svc).Replace('__PS__', $ps).Replace('__SCRIPT__', $script).Replace('__HOST__', $host_).Replace('__AFTER__', $after).Replace('__ARGS__', $argText)
    return (Wsl-Script ('bb_' + $name + '.sh') $body)
}
$s = Run-Bb $bpc 'pre_ok'
Check 'P25' 'bb_build_precheck: исходники равны r2j (4 из 4), службы нет, ~/bench_ws/r2j нет, диск, нет сборок: BB_BBPRE_RESULT OK' ($s.Text -match 'BBPRE src_ok=4 src_bad=0' -and $s.Text -match 'BBPRE hover_r6 found=1' -and $s.Text -match 'BBPRE absent .*/bench_ws/r2j' -and $s.Text -match 'BBPRE colcon_defaults absent' -and $s.Text -match 'BB_BBPRE_RESULT OK' -and $s.Text -match 'BB_BBPRE_DONE') $s.Text
$s = Run-Bb $bpc 'pre_svc' '' 'active'
Check 'P25' 'bb_build_precheck: служба bumblebee активна: STOP с просьбой остановить самому' ($s.Text -match 'BB_BBPRE_RESULT STOP.*служба_bumblebee_активна') $s.Text
$s = Run-Bb $bpc 'pre_diff' 'echo changed > $SRC/src/cpp/b.h'
Check 'P25' 'bb_build_precheck: исходник не равен r2j: STOP «сначала 05_install_r2j»' ($s.Text -match 'BBPRE src DIFF .*b\.h' -and $s.Text -match 'BB_BBPRE_RESULT STOP.*исходники_не_равны_r2j') $s.Text
$s = Run-Bb $bpc 'pre_missing' 'rm $SRC/src/cpp/a.cpp'
Check 'P25' 'bb_build_precheck: исходника нет: STOP' ($s.Text -match 'BBPRE src MISSING .*a\.cpp' -and $s.Text -match 'BB_BBPRE_RESULT STOP') $s.Text
# r3 (замечание проверки 11.11): сверка hover r6 в 13: в ~/ros2_ws/src/bumblebee/examples должен лежать файл с sha256 hover r6 (имя любое), иначе STOP до сборки
$s = Run-Bb $bpc 'pre_nohover' 'rm $SRC/examples/hover_marker0.py'
Check 'P25' 'bb_build_precheck: hover r6 нет в examples: STOP «нет_hover_r6», BBPRE hover_r6 found=0' ($s.Text -match 'BBPRE hover_r6 found=0' -and $s.Text -match 'BB_BBPRE_RESULT STOP.*нет_hover_r6_в_ros2_ws_src_bumblebee_examples') $s.Text
$s = Run-Bb $bpc 'pre_otherhover' 'echo other > $SRC/examples/hover_marker0.py'
Check 'P25' 'bb_build_precheck: в examples лежит другой hover (sha не тот): STOP' ($s.Text -match 'BBPRE hover_r6 found=0' -and $s.Text -match 'BB_BBPRE_RESULT STOP.*нет_hover_r6') $s.Text
$s = Run-Bb $bpc 'pre_renamedhover' 'mv $SRC/examples/hover_marker0.py $SRC/examples/hover_renamed.py'
Check 'P25' 'bb_build_precheck: hover r6 под другим именем (sha тот же): принимается, found=1 (сверка по sha256, а не по имени)' ($s.Text -match 'BBPRE hover_r6 found=1' -and $s.Text -match 'BB_BBPRE_RESULT OK') $s.Text
$s = Run-Bb $bbd 'bld_nohover' 'rm $SRC/examples/hover_marker0.py' 'inactive' 'bash' $true "echo W_EXISTS=`$(test -e `$H/bench_ws/r2j && echo yes || echo no)"
Check 'P26' 'bb_build: hover r6 нет в исходниках: BB_BBBUILD_STOP «hover r6», копия не создана (W_EXISTS=no)' ($s.Text -match 'BB_BBBUILD_STOP .*hover r6' -and $s.Text -match 'W_EXISTS=no') $s.Text
$bcodeH = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\bb_build.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P26' 'bb_build: код проверяет hover r6 дважды: в исходниках образа и в копии оверлея (W/src/bumblebee/examples)' ($bcodeH -match 'ros2_ws/src/bumblebee/examples' -and $bcodeH -match '\$W/src/bumblebee/examples' -and $bcodeH -match 'hover r6') ''
$s = Run-Bb $bpc 'pre_exists' 'mkdir -p $H/bench_ws/r2j'
Check 'P25' 'bb_build_precheck: ~/bench_ws/r2j уже есть: STOP' ($s.Text -match 'BBPRE exists .*bench_ws/r2j' -and $s.Text -match 'BB_BBPRE_RESULT STOP.*уже_есть_bench_ws_r2j') $s.Text
$s = Run-Bb $bpc 'pre_defaults' 'mkdir -p $H/.colcon; echo x > $H/.colcon/defaults.yaml'
Check 'P25' 'bb_build_precheck: есть ~/.colcon/defaults.yaml: STOP' ($s.Text -match 'BB_BBPRE_RESULT STOP.*есть_colcon_defaults') $s.Text
$s = Run-Bb $bpc 'pre_busy' '' 'inactive' 'colcon'
Check 'P25' 'bb_build_precheck: идёт colcon: STOP' ($s.Text -match 'BB_BBPRE_RESULT STOP.*идёт_сборка') $s.Text
$s = Run-Bb $bpc 'pre_host' '' 'inactive' 'bash' $false
Check 'P25' 'bb_build_precheck: не тот хост: STOP, ничего не читалось' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'BBPRE' -and $s.Text -match 'EXIT=1') $s.Text
$pcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\bb_build_precheck.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P25' 'bb_build_precheck: в коде нет записи и остановки служб (нет rm, mv, cp, tee, mkdir, touch, chmod, sudo, colcon build, systemctl stop/start)' (-not ($pcode -match '(^|[\s;|&(])(rm|mv|cp|tee|mkdir|touch|chmod|sudo|cmake)\s' -or $pcode -match 'colcon\s+build' -or $pcode -match 'systemctl\s+(stop|start|restart|enable|disable|kill)')) ''
# bb_build: проверяются только отказы ДО сборки (настоящий colcon в тестах не запускается)
$s = Run-Bb $bbd 'bld_svc' '' 'active' 'bash' $true "echo W_EXISTS=`$(test -e `$H/bench_ws/r2j && echo yes || echo no)"
Check 'P26' 'bb_build: служба активна: BB_BBBUILD_STOP, ничего не создано (~/bench_ws/r2j нет)' ($s.Text -match 'BB_BBBUILD_STOP служба bumblebee запущена' -and $s.Text -match 'W_EXISTS=no' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Bb $bbd 'bld_diff' 'echo changed > $SRC/src/cpp/b.h' 'inactive' 'bash' $true "echo W_EXISTS=`$(test -e `$H/bench_ws/r2j && echo yes || echo no)"
Check 'P26' 'bb_build: исходник не равен r2j: STOP до копирования (~/bench_ws/r2j не создан)' ($s.Text -match 'BB_BBBUILD_STOP исходник не равен r2j: .*b\.h' -and $s.Text -match 'W_EXISTS=no') $s.Text
$s = Run-Bb $bbd 'bld_exists' 'mkdir -p $H/bench_ws/r2j; echo keep > $H/bench_ws/r2j/keep.txt' 'inactive' 'bash' $true "echo KEEP=`$(cat `$H/bench_ws/r2j/keep.txt)"
Check 'P26' 'bb_build: ~/bench_ws/r2j уже есть: STOP, содержимое не тронуто (ничего не перезаписывается)' ($s.Text -match 'BB_BBBUILD_STOP уже есть .*bench_ws/r2j' -and $s.Text -match 'KEEP=keep') $s.Text
$s = Run-Bb $bbd 'bld_log' 'echo old > $H/bench_ws/build_r2j_1.log' 'inactive' 'bash' $true "echo LOG=`$(cat `$H/bench_ws/build_r2j_1.log)"
Check 'P26' 'bb_build: журнал build_r2j_1.log уже есть: STOP, не перезаписан' ($s.Text -match 'BB_BBBUILD_STOP уже есть .*build_r2j_1\.log' -and $s.Text -match 'LOG=old') $s.Text
$s = Run-Bb $bbd 'bld_defaults' 'mkdir -p $H/.colcon; echo x > $H/.colcon/defaults.yaml'
Check 'P26' 'bb_build: есть ~/.colcon/defaults.yaml: STOP' ($s.Text -match 'BB_BBBUILD_STOP есть .*defaults\.yaml') $s.Text
$s = Run-Bb $bbd 'bld_busy' '' 'inactive' 'make'
Check 'P26' 'bb_build: идёт другая сборка (make): STOP' ($s.Text -match 'BB_BBBUILD_STOP идёт другая сборка') $s.Text
$s = Run-Bb $bbd 'bld_host' '' 'inactive' 'bash' $false
Check 'P26' 'bb_build: не тот хост: STOP, ничего не делалось' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'BB_BBBUILD' -and $s.Text -match 'EXIT=1') $s.Text
$bcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\bb_build.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
$bcodeS = [regex]::Replace($bcode, '"[^"]*"', '""')
Check 'P26' 'bb_build: в коде одна сборка пакета bumblebee в чистом окружении (colcon build --packages-select bumblebee, MAKEFLAGS=-j2, env -i), нет rm, mv, sudo, systemctl stop/start, apt, записи в ros2_ws и start_bumblebee.sh (тексты сообщений в кавычках не считаются)' ($bcode -match 'MAKEFLAGS=-j2 colcon build --packages-select bumblebee --cmake-args -DBUILD_TESTING=OFF' -and $bcode -match 'env -i' -and -not ($bcodeS -match '(^|[\s;|&(])(rm|mv|sudo|apt|apt-get|pip)\s' -or $bcodeS -match 'systemctl\s+(stop|start|restart)' -or $bcodeS -match 'start_bumblebee' -or $bcode -match '>\s*"?\$HOME/ros2_ws')) ''
# bb_build_aside
$asEx = 'mkdir -p $H/bench_ws/r2j/src; echo s > $H/bench_ws/r2j/src/f.cpp; echo l > $H/bench_ws/build_r2j_1.log; echo k > $H/bench_ws/other.txt; mkdir -p $H/ros2_ws/install/bumblebee; echo live > $H/ros2_ws/install/bumblebee/live.txt; echo ''#!/bin/bash'' > $H/start_bumblebee.sh'
$asAfter = 'echo MOVED_F=$(find $H/bench_ws/_aside_bb_r2j_* -name f.cpp 2>/dev/null | wc -l); echo R2J_GONE=$(test -e $H/bench_ws/r2j && echo no || echo yes); echo LIVE_KEPT=$(test -f $H/ros2_ws/install/bumblebee/live.txt && echo yes || echo no); echo OTHER_KEPT=$(test -f $H/bench_ws/other.txt && echo yes || echo no)'
$s = Run-Bb $bas 'as_ok' $asEx 'inactive' 'bash' $true $asAfter
Check 'P27' 'bb_build_aside: BB_BBASIDE_DONE, ~/bench_ws/r2j и журнал в _aside_bb_r2j_<метка>, ~/ros2_ws (прежняя сборка) и чужие файлы не тронуты' ($s.Text -match 'BB_BBASIDE_DONE .*_aside_bb_r2j_\d{8}_\d{6} files=2' -and $s.Text -match 'MOVED_F=1' -and $s.Text -match 'R2J_GONE=yes' -and $s.Text -match 'LIVE_KEPT=yes' -and $s.Text -match 'OTHER_KEPT=yes' -and $s.Text -match 'EXIT=0') $s.Text
$s = Run-Bb $bas 'as_overlay' ($asEx + '; echo ''source /home/lb/bench_ws/r2j/install/local_setup.bash'' >> $H/start_bumblebee.sh') 'inactive' 'bash' $true $asAfter
Check 'P27' 'bb_build_aside: оверлей r2j подключён в start_bumblebee.sh: STOP, ничего не перенесено' ($s.Text -match 'STOP: start_bumblebee\.sh подключает оверлей bench_ws/r2j' -and $s.Text -match 'R2J_GONE=no' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Bb $bas 'as_busy' $asEx 'inactive' 'colcon' $true $asAfter
Check 'P27' 'bb_build_aside: идёт сборка: STOP, ничего не перенесено' ($s.Text -match 'STOP: идёт сборка' -and $s.Text -match 'R2J_GONE=no') $s.Text
$s = Run-Bb $bas 'as_none' ''
Check 'P27' 'bb_build_aside: нечего переносить: STOP' ($s.Text -match 'STOP: нет .*bench_ws/r2j, нечего переносить') $s.Text
$s = Run-Bb $bas 'as_host' $asEx 'inactive' 'bash' $false $asAfter
Check 'P27' 'bb_build_aside: не тот хост: STOP, ничего не перенесено' ($s.Text -match 'STOP: hostname is' -and $s.Text -match 'R2J_GONE=no') $s.Text
$acode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\bb_build_aside.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P27' 'bb_build_aside: в коде нет удаления (rm, rmdir, shred, unlink, -delete) и sudo; только mv и mkdir' (-not ($acode -match '(^|[\s;|&(])(rm|rmdir|shred|unlink|sudo)\s' -or $acode -match '-delete') -and $acode -match '(^|[\s;|&(])mv\s') ''
# overlay_fingerprint: заготовка своя (списки LIST, CPP; дерево оверлея)
$fpTpl = @'
set +e
d=$(mktemp -d)
H=$d/home
mkdir -p $d/bin
__TREE__
cat > $d/bin/systemctl <<EOF
#!/bin/bash
exit 0
EOF
chmod +x $d/bin/*
LIST="$pa  a.py\n$pb  b.py"
CPPL="$sx  __SRCREL__x.cpp  R\n$sy  __SRCREL__y.cpp  -"
__EXTRA__
awk -v l="$LIST" -v c="$CPPL" -v r="$RTL" '{ if ($0 == "#@@LIST@@") printf "%s\n", l; else if ($0 == "#@@CPP@@") printf "%s\n", c; else if ($0 == "#@@RT@@") printf "%s\n", r; else print }' '__SCRIPT__' > $d/gen.sh
hostname(){ echo bumblebee-20ec; }; export -f hostname
HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh __TARGET__
echo EXIT=$?
rm -rf $d
'@
$treeBb = 'P=$H/bench_ws/r2j/install/bumblebee/lib/bumblebee; S=$H/bench_ws/r2j/src/bumblebee/src/cpp; mkdir -p $P $S; echo a > $P/a.py; echo b > $P/b.py; echo bin1 > $P/simple_offboard; echo bin2 > $P/shell; echo rs > $S/x.cpp; echo ns > $S/y.cpp; touch -d "2026-01-01 00:00:00" $S/x.cpp; touch -d "2026-01-02 00:00:00" $P/simple_offboard $P/shell; pa=$(sha256sum $P/a.py | cut -c1-64); pb=$(sha256sum $P/b.py | cut -c1-64); sx=$(sha256sum $S/x.cpp | cut -c1-64); sy=$(sha256sum $S/y.cpp | cut -c1-64); LD=$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch; FC=$H/ros2_ws/src/bumblebee/scripts; mkdir -p $LD $FC; echo l1 > $LD/bumblebee.launch.py; echo fcu_fixed > $FC/fcu_detect.py; RTL="$(sha256sum $LD/bumblebee.launch.py | cut -c1-64)  LAUNCH  launch/bumblebee.launch.py\n$(sha256sum $FC/fcu_detect.py | cut -c1-64)  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"'
$treeMv = 'I=$H/bench_ws/mavros/install/mavros; S=$H/bench_ws/mavros/src/mavros-source; mkdir -p $I/lib/mavros $S; echo l1 > $I/lib/libmavros.so; echo l2 > $I/lib/libmavros_plugins.so; echo mn > $I/lib/mavros/mavros_node; echo rs > $S/x.cpp; echo ns > $S/y.cpp; touch -d "2026-01-01 00:00:00" $S/x.cpp $S/y.cpp; touch -d "2026-01-02 00:00:00" $I/lib/libmavros.so $I/lib/libmavros_plugins.so $I/lib/mavros/mavros_node; pa=0; pb=0; sx=$(sha256sum $S/x.cpp | cut -c1-64); sy=$(sha256sum $S/y.cpp | cut -c1-64); RTL=""'
function Run-Fp([string]$target, [string]$extra = '') {
    $tree = $treeBb; $rel = 'ros2_ws/src/bumblebee/src/cpp/'
    if ($target -eq 'mavros') { $tree = $treeMv; $rel = '' }
    $body = $fpTpl.Replace('__TREE__', $tree).Replace('__SRCREL__', $rel).Replace('__EXTRA__', $extra).Replace('__SCRIPT__', $ofp).Replace('__TARGET__', $target)
    return (Wsl-Script ('fp_' + $target + '.sh') $body)
}
$s = Run-Fp 'bumblebee'
Check 'P28' 'overlay_fingerprint bumblebee: все файлы install с sha256, python OK x2, исходники OK x2, бинарники не старше исходников: py_ok=2 src_ok=2 bin=2 stale=0' ($s.Text -match 'FP_FILE [0-9a-f]{64} bumblebee/lib/bumblebee/a\.py' -and $s.Text -match 'PY_NODE a\.py OK' -and $s.Text -match 'SRC bumblebee/src/cpp/x\.cpp OK R' -and $s.Text -match 'BB_FP_RESULT files=5 py_ok=2 py_bad=0 src_ok=2 src_bad=0 bin=2 stale=0 noinstall=0' -and $s.Text -match 'RT_FILE LAUNCH launch/bumblebee\.launch\.py OK' -and $s.Text -match 'RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect\.py OK' -and $s.Text -match 'BB_FP_RT ok=2 diff=0 missing=0' -and $s.Text -match 'BB_FP_DONE') $s.Text
$s = Run-Fp 'bumblebee' 'touch -d "2025-12-01 00:00:00" $P/simple_offboard'
Check 'P28' 'overlay_fingerprint bumblebee: бинарник старше изменённого исходника: BIN ... STALE, stale=1' ($s.Text -match 'BIN bumblebee/lib/bumblebee/simple_offboard sha=[0-9a-f]{64} mtime=\d+ newest_source=\d+ STALE' -and $s.Text -match 'bin=2 stale=1') $s.Text
$s = Run-Fp 'bumblebee' 'echo changed > $P/b.py'
Check 'P28' 'overlay_fingerprint bumblebee: python-узел изменён: PY_NODE b.py DIFF, py_bad=1' ($s.Text -match 'PY_NODE b\.py DIFF' -and $s.Text -match 'py_ok=1 py_bad=1') $s.Text
$s = Run-Fp 'bumblebee' 'echo changed > $S/y.cpp'
Check 'P28' 'overlay_fingerprint bumblebee: C++ исходник копии изменён: SRC DIFF, src_bad=1' ($s.Text -match 'SRC bumblebee/src/cpp/y\.cpp DIFF' -and $s.Text -match 'src_ok=1 src_bad=1') $s.Text
# S2 (чат 1, 21:50): launch-файлы оверлея и fcu_detect.py (исправление порта, по полному пути ros2_ws/src) в отпечатках
$s = Run-Fp 'bumblebee' 'echo changed > $LD/bumblebee.launch.py'
Check 'P28' 'overlay_fingerprint bumblebee: launch-файл оверлея изменён: RT_FILE LAUNCH ... DIFF, BB_FP_RT diff=1' ($s.Text -match 'RT_FILE LAUNCH launch/bumblebee\.launch\.py DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'BB_FP_RT ok=1 diff=1 missing=0') $s.Text
$s = Run-Fp 'bumblebee' 'echo fcu_old > $FC/fcu_detect.py'
Check 'P28' 'overlay_fingerprint bumblebee: fcu_detect.py на Pi прежний: RT_FILE FCU ... DIFF, diff=1' ($s.Text -match 'RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect\.py DIFF' -and $s.Text -match 'BB_FP_RT ok=1 diff=1 missing=0') $s.Text
$s = Run-Fp 'bumblebee' 'rm $FC/fcu_detect.py'
Check 'P28' 'overlay_fingerprint bumblebee: fcu_detect.py нет: MISSING, missing=1' ($s.Text -match 'RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect\.py MISSING' -and $s.Text -match 'BB_FP_RT ok=1 diff=0 missing=1') $s.Text
$s = Run-Fp 'bumblebee' 'rm $LD/bumblebee.launch.py'
Check 'P28' 'overlay_fingerprint bumblebee: launch-файла в оверлее нет: MISSING, missing=1' ($s.Text -match 'RT_FILE LAUNCH launch/bumblebee\.launch\.py MISSING' -and $s.Text -match 'BB_FP_RT ok=1 diff=0 missing=1') $s.Text
$s = Run-Fp 'mavros'
Check 'P28' 'overlay_fingerprint mavros: 3 бинарника, источник MAVROS, не старше: bin=3 stale=0 src_ok=2' ($s.Text -match 'BIN mavros/lib/libmavros\.so sha=' -and $s.Text -match 'BIN mavros/lib/mavros/mavros_node sha=' -and $s.Text -match 'src_ok=2 src_bad=0 bin=3 stale=0 noinstall=0' -and $s.Text -match 'BB_FP_RT ok=0 diff=0 missing=0') $s.Text
$s = Run-Fp 'mavros' 'touch -d "2025-12-01 00:00:00" $I/lib/libmavros.so'
Check 'P28' 'overlay_fingerprint mavros: libmavros.so старше исходников: STALE, stale=1' ($s.Text -match 'libmavros\.so sha=[0-9a-f]{64} mtime=\d+ newest_source=\d+ STALE' -and $s.Text -match 'bin=3 stale=1') $s.Text
$s = Run-Fp 'mavros' 'rm -rf $H/bench_ws/mavros/install'
Check 'P28' 'overlay_fingerprint: оверлей не собран: noinstall=1, без отпечатков' ($s.Text -match 'noinstall=1' -and $s.Text -notmatch 'FP_FILE' -and $s.Text -match 'BB_FP_DONE') $s.Text
$s = Wsl-Script 'fp_badarg.sh' "hostname(){ echo bumblebee-20ec; }; export -f hostname; bash '$ofp' evil; echo EXIT=`$?"
Check 'P28' 'overlay_fingerprint: цель «evil» отклонена' ($s.Text -match "STOP: bad target 'evil'" -and $s.Text -match 'EXIT=1') $s.Text
$fcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\overlay_fingerprint.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
Check 'P28' 'overlay_fingerprint: в коде нет записи (rm, mv, cp, tee, mkdir, touch, chmod, sudo, colcon, перенаправления в файл)' (-not ($fcode -match '(^|[\s;|&(])(rm|mv|cp|tee|mkdir|touch|chmod|sudo|colcon|cmake)\s') -and -not (($fcode -replace '2>/dev/null', '' -replace '2>&1', '') -match '>\s*[^&\s]')) ''
# overlay_connect / overlay_disconnect
$cnTpl = @'
set +e
d=$(mktemp -d)
H=$d/home
mkdir -p $d/bin $H/bench_ws
cat > $d/bin/systemctl <<EOF
#!/bin/bash
if [ "\$1" = is-active ]; then [ "__SVC__" = active ]; exit \$?; fi
EOF
chmod +x $d/bin/*
printf '#!/bin/bash\nsource /etc/profile\nsource /home/lb/ros2_ws/install/setup.bash\nexport X=1\n' > $H/start_bumblebee.sh
chmod 755 $H/start_bumblebee.sh
__TREE__
__EXTRA__
FPN=$(cd $I && find . -type f ! -path '*/__pycache__/*' | wc -l)
FPH=$(cd $I && find . -type f ! -path '*/__pycache__/*' | sed 's|^\./||' | LC_ALL=C sort | while read f; do echo "$(sha256sum $f | cut -c1-64)  $f"; done | sha256sum | cut -c1-64)
FPL="FPHASH=$FPH\nFPCOUNT=$FPN"
awk -v l="$FPL" '{ if ($0 == "#@@FPCFG@@") printf "%s\n", l; else print }' '__SCRIPT__' > $d/gen.sh
cp $H/start_bumblebee.sh $d/orig.sh
hostname(){ echo bumblebee-20ec; }; export -f hostname
HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh __ARGS__
echo EXIT=$?
__AFTER__
rm -rf $d
'@
$treeCnMv = 'I=$H/bench_ws/mavros/install; mkdir -p $I/mavros/lib; echo l1 > $I/mavros/lib/libmavros.so; echo l2 > $I/mavros/lib/x.so; echo setup > $I/local_setup.bash'
$treeCnBb = 'I=$H/bench_ws/r2j/install; mkdir -p $I/bumblebee/lib; echo b1 > $I/bumblebee/lib/node; echo setup > $I/local_setup.bash'
function Run-Cn([string]$script, [string]$target, [string]$extra = '', [string]$svc = 'inactive', [string]$after = '', [string]$argText = '') {
    $tree = $treeCnMv; if ($target -eq 'bumblebee') { $tree = $treeCnBb }
    if ($argText -eq '') { $argText = $target }
    $body = $cnTpl.Replace('__SVC__', $svc).Replace('__TREE__', $tree).Replace('__EXTRA__', $extra).Replace('__SCRIPT__', $script).Replace('__AFTER__', $after).Replace('__ARGS__', $argText)
    return (Wsl-Script ('cn_' + $target + '_' + [guid]::NewGuid().ToString('N').Substring(0, 5) + '.sh') $body)
}
$cnAfter = 'echo ADDED=$(diff $d/orig.sh $H/start_bumblebee.sh | grep -c "^>"); echo REMOVED=$(diff $d/orig.sh $H/start_bumblebee.sh | grep -c "^<"); echo LINES=$(grep -n "^source /home/lb" $H/start_bumblebee.sh | tr "\n" " "); echo BK_FILES=$(ls $H/bench_ws/_bk_start_bumblebee_*/ 2>/dev/null | tr "\n" " "); echo MODE=$(stat -c %a $H/start_bumblebee.sh)'
$s = Run-Cn $ocn 'mavros' '' 'inactive' $cnAfter
Check 'P29' 'overlay_connect mavros: BB_CONN_DONE; добавлена РОВНО одна строка (ничего не удалено), сразу после строки ros2_ws; копии .before и .after сохранены; права 755' ($s.Text -match 'BB_CONN_DONE mavros .*_bk_start_bumblebee_\d{8}_\d{6}' -and $s.Text -match 'ADDED=1' -and $s.Text -match 'REMOVED=0' -and $s.Text -match 'LINES=3:source /home/lb/ros2_ws/install/setup.bash 4:source /home/lb/bench_ws/mavros/install/local_setup.bash' -and $s.Text -match 'start_bumblebee\.sh\.after' -and $s.Text -match 'start_bumblebee\.sh\.before' -and $s.Text -match 'MODE=755') $s.Text
$s = Run-Cn $ocn 'bumblebee' 'sed -i "s|^source /home/lb/ros2_ws/install/setup.bash\$|&\nsource /home/lb/bench_ws/mavros/install/local_setup.bash|" $H/start_bumblebee.sh; cp $H/start_bumblebee.sh $d/orig.sh' 'inactive' $cnAfter
Check 'P29' 'overlay_connect bumblebee при уже подключённом MAVROS: строка r2j встаёт ПОСЛЕ строки MAVROS (порядок ros2_ws, MAVROS, bumblebee), добавлена одна строка' ($s.Text -match 'BB_CONN_DONE bumblebee' -and $s.Text -match 'ADDED=1' -and $s.Text -match 'REMOVED=0' -and $s.Text -match 'LINES=3:source /home/lb/ros2_ws/install/setup.bash 4:source /home/lb/bench_ws/mavros/install/local_setup.bash 5:source /home/lb/bench_ws/r2j/install/local_setup.bash') $s.Text
$s = Run-Cn $ocn 'bumblebee' '' 'inactive' $cnAfter
Check 'P29' 'overlay_connect bumblebee без MAVROS-строки: r2j сразу после ros2_ws' ($s.Text -match 'BB_CONN_DONE bumblebee' -and $s.Text -match 'LINES=3:source /home/lb/ros2_ws/install/setup.bash 4:source /home/lb/bench_ws/r2j/install/local_setup.bash') $s.Text
$s = Run-Cn $ocn 'mavros' '' 'active' $cnAfter
Check 'P29' 'overlay_connect: служба активна: STOP, start_bumblebee.sh не менялся (ADDED=0), копий нет' ($s.Text -match 'BB_CONN_STOP служба bumblebee запущена' -and $s.Text -match 'ADDED=0' -and $s.Text -match 'BK_FILES=\s' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Cn $ocn 'mavros' 'echo "source /home/lb/bench_ws/mavros/install/local_setup.bash" >> $H/start_bumblebee.sh; cp $H/start_bumblebee.sh $d/orig.sh' 'inactive' $cnAfter
Check 'P29' 'overlay_connect: строка этого оверлея уже есть: STOP, файл не менялся' ($s.Text -match 'BB_CONN_STOP в start_bumblebee.sh уже есть строка bench_ws/mavros' -and $s.Text -match 'ADDED=0') $s.Text
$body = $cnTpl.Replace('__SVC__', 'inactive').Replace('__TREE__', $treeCnMv).Replace('__SCRIPT__', $ocn).Replace('__ARGS__', 'mavros').Replace('__AFTER__', $cnAfter).Replace('__EXTRA__', ':')
# лишний файл и изменённый файл добавляются ПОСЛЕ снятия отпечатков: вставка между строкой FPL=... и awk
$body = $body.Replace("awk -v l=`"`$FPL`"", "echo extra > `$I/mavros/lib/extra.so`nawk -v l=`"`$FPL`"")
$s = Wsl-Script 'cn_extra.sh' $body
Check 'P29' 'overlay_connect: после снятия отпечатков в оверлее появился лишний файл: STOP «лишние или пропавшие», start_bumblebee.sh не менялся' ($s.Text -match 'BB_CONN_STOP в оверлее \d+ файлов, в отпечатках \d+' -and $s.Text -match 'ADDED=0') $s.Text
$body2 = $cnTpl.Replace('__SVC__', 'inactive').Replace('__TREE__', $treeCnMv).Replace('__SCRIPT__', $ocn).Replace('__ARGS__', 'mavros').Replace('__AFTER__', $cnAfter).Replace('__EXTRA__', ':')
$body2 = $body2.Replace("awk -v l=`"`$FPL`"", "echo changed > `$I/mavros/lib/libmavros.so`nawk -v l=`"`$FPL`"")
$s = Wsl-Script 'cn_changed.sh' $body2
Check 'P29' 'overlay_connect: файл оверлея изменён после снятия отпечатков (число файлов то же): STOP «файлы оверлея не равны отпечаткам» с суммами и строками FPGOT, start_bumblebee.sh не менялся' ($s.Text -match 'BB_CONN_STOP файлы оверлея не равны отпечаткам' -and $s.Text -match 'FPGOT [0-9a-f]{64}  mavros/lib/libmavros\.so' -and $s.Text -match 'ADDED=0') $s.Text
# сумма списка считается на ПК (порядковая сортировка по пути) и на Pi (LC_ALL=C sort) ОДИНАКОВО: берём список с Pi, считаем сумму в PowerShell, подставляем в скрипт
$lst = Wsl-Script 'cn_list.sh' ($cnTpl.Replace('__SVC__', 'inactive').Replace('__TREE__', $treeCnMv).Replace('__SCRIPT__', $ocn).Replace('__ARGS__', 'mavros').Replace('__AFTER__', '').Replace('__EXTRA__', ':').Replace('rm -rf $d', 'true').Replace('HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh mavros', 'cd $I && find . -type f | sed "s|^\./||" | while read f; do echo "LST $(sha256sum $f | cut -c1-64)  $f"; done'))
$lstLines = @(($lst.Text -split "`r?`n") | Where-Object { $_ -match '^LST [0-9a-f]{64}  \S+$' } | ForEach-Object { $_.Substring(4) })
$lk = [string[]]@($lstLines | ForEach-Object { $_.Substring(66) }); $lv = [string[]]@($lstLines); [Array]::Sort($lk, $lv, [StringComparer]::Ordinal)
$lhash = ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash((New-Object Text.UTF8Encoding($false)).GetBytes((($lv -join "`n") + "`n")))) -replace '-', '').ToLower()
$bodyX = $cnTpl.Replace('__SVC__', 'inactive').Replace('__TREE__', $treeCnMv).Replace('__SCRIPT__', $ocn).Replace('__ARGS__', 'mavros').Replace('__AFTER__', $cnAfter).Replace('__EXTRA__', ':')
$bodyX = $bodyX.Replace('FPL="FPHASH=$FPH\nFPCOUNT=$FPN"', 'FPL="FPHASH=' + $lhash + '\nFPCOUNT=' + $lstLines.Count + '"')
$s = Wsl-Script 'cn_pshash.sh' $bodyX
Check 'P29' 'overlay_connect: сумма списка, посчитанная НА ПК (PowerShell, порядковая сортировка), принимается Pi (та же сумма по sort LC_ALL=C): BB_CONN_DONE' ($lstLines.Count -eq 3 -and $s.Text -match 'BB_CONN_DONE mavros' -and $s.Text -match 'ADDED=1') ($lst.Text + $s.Text)
$bodyY = $cnTpl.Replace('__SVC__', 'inactive').Replace('__TREE__', $treeCnMv).Replace('__SCRIPT__', $ocn).Replace('__ARGS__', 'mavros').Replace('__AFTER__', $cnAfter).Replace('__EXTRA__', ':')
$bodyY = $bodyY.Replace('FPL="FPHASH=$FPH\nFPCOUNT=$FPN"', 'FPL="FPCOUNT=$FPN"')
$s = Wsl-Script 'cn_nohash.sh' $bodyY
Check 'P29' 'overlay_connect: в скрипте нет суммы списка (FPHASH): STOP, start_bumblebee.sh не менялся' ($s.Text -match 'BB_CONN_STOP в скрипте нет суммы списка отпечатков' -and $s.Text -match 'ADDED=0') $s.Text
$s = Run-Cn $ocn 'mavros' 'rm -rf $H/bench_ws/mavros/install' 'inactive' $cnAfter
Check 'P29' 'overlay_connect: оверлей не собран: STOP, файл не менялся' ($s.Text -match 'BB_CONN_STOP нет .*install \(оверлей не собран\)' -and $s.Text -match 'ADDED=0') $s.Text
$s = Run-Cn $ocn 'mavros' 'echo "source /home/lb/ros2_ws/install/setup.bash" >> $H/start_bumblebee.sh; cp $H/start_bumblebee.sh $d/orig.sh' 'inactive' $cnAfter
Check 'P29' 'overlay_connect: строка ros2_ws встречается дважды: STOP' ($s.Text -match 'BB_CONN_STOP в start_bumblebee.sh не ровно одна строка ros2_ws' -and $s.Text -match 'ADDED=0') $s.Text
$s = Run-Cn $ocn 'mavros' '' 'inactive' $cnAfter 'evil'
Check 'P29' 'overlay_connect: цель «evil» отклонена' ($s.Text -match "STOP: bad target 'evil'" -and $s.Text -match 'ADDED=0') $s.Text
$ccode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\overlay_connect.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
$ccodeS = [regex]::Replace($ccode, '"[^"]*"', '""')
Check 'P29' 'overlay_connect: в коде нет rm, sudo, systemctl stop/start, reboot; файл заменяется только через .bbnew и mv -f после копии (тексты сообщений в кавычках не считаются)' (-not ($ccodeS -match '(^|[\s;|&(])(rm|sudo|reboot|shutdown)\s' -or $ccodeS -match 'systemctl\s+(stop|start|restart)') -and $ccode -match 'mv -f "\$S\.bbnew" "\$S"' -and $ccode -match 'start_bumblebee\.sh\.before') ''
# disconnect: после connect в той же заготовке
$dcAfter = 'sed -i "s|^source /home/lb/ros2_ws/install/setup.bash\$|&\nsource /home/lb/bench_ws/mavros/install/local_setup.bash|" $H/start_bumblebee.sh'
function Run-Dc([string]$mode) {
    # mode: ok | modified | twice | nobackup | svc
    $pre = 'HOME=$H PATH=$d/bin:$PATH bash $d/gen.sh mavros > /dev/null 2>&1'
    $tail = ''
    if ($mode -eq 'modified') { $tail = 'echo "export Y=2" >> $H/start_bumblebee.sh' }
    $bodyD = $cnTpl.Replace('__SVC__', 'inactive').Replace('__TREE__', $treeCnMv).Replace('__EXTRA__', ':').Replace('__ARGS__', 'mavros').Replace('__AFTER__', 'echo CNT=$(grep -c "bench_ws/mavros" $H/start_bumblebee.sh)')
    $bodyD = $bodyD.Replace('__SCRIPT__', $ocn)
    # после основной команды (подключение) запускаем откат: подставляем второй gen
    $disc = "awk '{ print }' '$odc' > `$d/gen2.sh`n"
    if ($mode -eq 'svc') { $dcRun = "sed -i 's/inactive/active/' `$d/bin/systemctl`n" } else { $dcRun = '' }
    $runD = ($disc + $dcRun + $tail + "`nHOME=`$H PATH=`$d/bin:`$PATH bash `$d/gen2.sh`necho DISC_EXIT=`$?`necho CMP_ORIG=`$(cmp -s `$d/orig.sh `$H/start_bumblebee.sh && echo same || echo different)`necho RESTORED=`$(ls `$H/bench_ws/_bk_start_bumblebee_*/RESTORED 2>/dev/null | wc -l)`n")
    if ($mode -eq 'twice') { $runD += "HOME=`$H PATH=`$d/bin:`$PATH bash `$d/gen2.sh`necho DISC2_EXIT=`$?`n" }
    if ($mode -eq 'two') {
        # правка по проверке 10.11 (M2): подключены ДВА оверлея (MAVROS уже подключён основной частью, затем bumblebee); откат запускают дважды, третий раз откатывать нечего
        $twoSnip = @'
I2=$H/bench_ws/r2j/install; mkdir -p $I2/bumblebee/lib; echo b1 > $I2/bumblebee/lib/node; echo setup > $I2/local_setup.bash
FPN2=$(cd $I2 && find . -type f | wc -l)
FPH2=$(cd $I2 && find . -type f | sed 's|^\./||' | LC_ALL=C sort | while read f; do echo "$(sha256sum $f | cut -c1-64)  $f"; done | sha256sum | cut -c1-64)
awk -v l="FPHASH=$FPH2\nFPCOUNT=$FPN2" '{ if ($0 == "#@@FPCFG@@") printf "%s\n", l; else print }' '__OCN__' > $d/gen3.sh
sleep 1
HOME=$H PATH=$d/bin:$PATH bash $d/gen3.sh bumblebee
echo C2_EXIT=$?
echo AFTER2=$(grep -c "bench_ws/" $H/start_bumblebee.sh)
awk '{ print }' '__ODC__' > $d/gen2.sh
HOME=$H PATH=$d/bin:$PATH bash $d/gen2.sh
echo D1_EXIT=$?
echo AFTERD1=$(grep -c "bench_ws/mavros" $H/start_bumblebee.sh) $(grep -c "bench_ws/r2j" $H/start_bumblebee.sh)
HOME=$H PATH=$d/bin:$PATH bash $d/gen2.sh
echo D2_EXIT=$?
echo CMP_ORIG=$(cmp -s $d/orig.sh $H/start_bumblebee.sh && echo same || echo different)
HOME=$H PATH=$d/bin:$PATH bash $d/gen2.sh
echo D3_EXIT=$?
echo RESTORED=$(ls $H/bench_ws/_bk_start_bumblebee_*/RESTORED 2>/dev/null | wc -l)
'@
        $runD = $twoSnip.Replace('__OCN__', $ocn).Replace('__ODC__', $odc)
    }
    if ($mode -eq 'nobackup') { $runD = $disc + "rm -rf `$H/bench_ws/_bk_start_bumblebee_*`nHOME=`$H PATH=`$d/bin:`$PATH bash `$d/gen2.sh`necho DISC_EXIT=`$?`n" }
    $bodyD = $bodyD.Replace('echo CNT=$(grep -c "bench_ws/mavros" $H/start_bumblebee.sh)', $runD)
    return (Wsl-Script ('dc_' + $mode + '.sh') $bodyD)
}
$s = Run-Dc 'ok'
Check 'P30' 'overlay_disconnect: после подключения откат возвращает start_bumblebee.sh ПОБАЙТНО как до (cmp), папка копии помечена RESTORED, BB_DISC_DONE' ($s.Text -match 'BB_CONN_DONE mavros' -and $s.Text -match 'BB_DISC_DONE .*_bk_start_bumblebee_' -and $s.Text -match 'DISC_EXIT=0' -and $s.Text -match 'CMP_ORIG=same' -and $s.Text -match 'RESTORED=1') $s.Text
$s = Run-Dc 'modified'
Check 'P30' 'overlay_disconnect: после подключения файл изменили вручную: STOP, откат не делается (файл остался как есть)' ($s.Text -match 'BB_DISC_STOP start_bumblebee\.sh не равен копии \.after' -and $s.Text -match 'DISC_EXIT=1' -and $s.Text -match 'CMP_ORIG=different' -and $s.Text -match 'RESTORED=0') $s.Text
$s = Run-Dc 'twice'
Check 'P30' 'overlay_disconnect: повторный откат, когда подключён один оверлей: STOP «все копии уже откачены»' ($s.Text -match 'DISC_EXIT=0' -and $s.Text -match 'BB_DISC_STOP все копии уже откачены' -and $s.Text -match 'DISC2_EXIT=1') $s.Text
$s = Run-Dc 'two'
Check 'P30' 'overlay_disconnect: подключены ДВА оверлея (MAVROS, потом bumblebee): первый откат снимает bumblebee (MAVROS остаётся), второй снимает MAVROS и файл ПОБАЙТНО как до всего (cmp), третий: STOP «все копии уже откачены»; обе копии с RESTORED' ($s.Text -match 'C2_EXIT=0' -and $s.Text -match 'AFTER2=2' -and $s.Text -match 'D1_EXIT=0' -and $s.Text -match 'AFTERD1=1 0' -and $s.Text -match 'D2_EXIT=0' -and $s.Text -match 'CMP_ORIG=same' -and $s.Text -match 'D3_EXIT=1' -and $s.Text -match 'BB_DISC_STOP все копии уже откачены' -and $s.Text -match 'RESTORED=2') $s.Text
$s = Run-Dc 'nobackup'
Check 'P30' 'overlay_disconnect: нет копий: STOP «нечего откатывать»' ($s.Text -match 'BB_DISC_STOP нет копий' -and $s.Text -match 'DISC_EXIT=1') $s.Text
$s = Run-Dc 'svc'
Check 'P30' 'overlay_disconnect: служба активна: STOP, файл не менялся' ($s.Text -match 'BB_DISC_STOP служба bumblebee запущена' -and $s.Text -match 'CMP_ORIG=different' -and $s.Text -match 'DISC_EXIT=1') $s.Text
$dcode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\overlay_disconnect.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
$dcodeS = [regex]::Replace($dcode, '"[^"]*"', '""')
Check 'P30' 'overlay_disconnect: в коде нет rm, sudo, systemctl stop/start; копии не удаляются (тексты сообщений в кавычках не считаются)' (-not ($dcodeS -match '(^|[\s;|&(])(rm|sudo|reboot|shutdown)\s' -or $dcodeS -match 'systemctl\s+(stop|start|restart)')) ''
# ---------- решение чата 1 (20:10): flight_gate.sh (drone.py скрипта полёта = r2j) и start_script_check.sh ----------
$fgs = "$KitW/pi/flight_gate.sh"; $ssc = "$KitW/pi/start_script_check.sh"
$r = Wsl-Script 'prep_fg.sh' "bash -n '$fgs' && echo FG_OK`nbash -n '$ssc' && echo SSC_OK"
Check 'P31' 'bash -n для flight_gate.sh и start_script_check.sh' ($r.Text -match 'FG_OK' -and $r.Text -match 'SSC_OK') $r.Text
$fgTpl = @'
set +e
d=$(mktemp -d)
H=$d/home
EX=$H/ros2_ws/src/bumblebee/examples
OV=$H/bench_ws/r2j/src/bumblebee/examples
mkdir -p $EX $OV/flight
echo 'drone r2j' > $EX/drone.py; echo 'drone r2j' > $OV/drone.py
printf 'import sys\nsys.path.insert(0, "/home/lb/ros2_ws/src/bumblebee/examples")\nimport drone\n' > $OV/flight/flight.py
WANT=$(sha256sum $EX/drone.py | cut -c1-64)
__EXTRA__
CFGL="SCRIPT=__SCRIPTPATH__\nWANT=${__WANTVAR__:-$WANT}"
awk -v c="$CFGL" '{ if ($0 == "#@@FGCFG@@") printf "%s\n", c; else print }' '__SCRIPT__' > $d/gen.sh
__HOST__
HOME=$H bash $d/gen.sh
echo EXIT=$?
rm -rf $d
'@
function Run-Fg([string]$mode) {
    $extra = ''; $spath = '/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/flight.py'; $wantVar = 'WANT'; $host_ = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;'
    if ($mode -eq 'import_diff') { $extra = 'echo old > $EX/drone.py' }
    if ($mode -eq 'import_missing') { $extra = 'rm $EX/drone.py' }
    if ($mode -eq 'near_diff') { $extra = 'echo old > $OV/drone.py' }
    if ($mode -eq 'noinsert_nodrone') { $extra = 'printf "import drone\n" > $OV/flight/flight.py; rm $OV/drone.py' }
    if ($mode -eq 'noinsert_ok') { $extra = 'printf "import drone\n" > $OV/flight/flight.py; cp $EX/drone.py $OV/flight/drone.py' }
    if ($mode -eq 'two_dirs') { $extra = 'mkdir -p $H/other; echo bad > $H/other/drone.py; printf "import sys\nsys.path.insert(0, \"/home/lb/ros2_ws/src/bumblebee/examples\")\nsys.path.insert(0, ''/home/lb/other'')\nimport drone\n" > $OV/flight/flight.py' }
    if ($mode -eq 'noscript') { $spath = '/home/lb/bench_ws/r2j/src/bumblebee/examples/flight/none.py' }
    if ($mode -eq 'badscript') { $spath = '/etc/passwd.py' }
    if ($mode -eq 'badwant') { $extra = 'BADW=abc'; $wantVar = 'BADW' }
    if ($mode -eq 'badhost') { $host_ = '' }
    $body = $fgTpl.Replace('__EXTRA__', $extra).Replace('__SCRIPTPATH__', $spath).Replace('__WANTVAR__', $wantVar).Replace('__SCRIPT__', $fgs).Replace('__HOST__', $host_)
    return (Wsl-Script ('fg_' + $mode + '.sh') $body)
}
$s = Run-Fg 'ok'
Check 'P32' 'flight_gate: скрипт из оверлея с жёстким sys.path.insert на ros2_ws/src: drone.py там и рядом в оверлее равны r2j: BB_FG_RESULT OK (FG_DIR OK, FG_NEAR OK x2)' ($s.Text -match 'FG_DIR /home/lb/ros2_ws/src/bumblebee/examples drone\.py OK' -and ([regex]::Matches($s.Text, 'FG_NEAR .* OK')).Count -eq 1 -and $s.Text -match 'BB_FG_RESULT OK' -and $s.Text -match 'BB_FG_DONE') $s.Text
$s = Run-Fg 'import_diff'
Check 'P32' 'flight_gate: drone.py в каталоге импорта (ros2_ws/src) СТАРЫЙ, а в оверлее новый: STOP (именно этот файл импортирует скрипт)' ($s.Text -match 'FG_DIR /home/lb/ros2_ws/src/bumblebee/examples drone\.py DIFF got=[0-9a-f]{64} want=[0-9a-f]{64}' -and $s.Text -match 'BB_FG_RESULT STOP.*drone\.py_в_/home/lb/ros2_ws/src/bumblebee/examples_не_r2j') $s.Text
$s = Run-Fg 'import_missing'
Check 'P32' 'flight_gate: в каталоге импорта нет drone.py: STOP «нет_drone.py_в_…»' ($s.Text -match 'FG_DIR .* drone\.py MISSING' -and $s.Text -match 'BB_FG_RESULT STOP.*нет_drone\.py_в_') $s.Text
$s = Run-Fg 'near_diff'
Check 'P32' 'flight_gate: drone.py рядом со скриптом в оверлее не r2j (а в каталоге импорта r2j): STOP «drone.py_рядом_не_r2j»' ($s.Text -match 'FG_NEAR .* DIFF' -and $s.Text -match 'BB_FG_RESULT STOP.*drone\.py_рядом_не_r2j') $s.Text
$s = Run-Fg 'noinsert_nodrone'
Check 'P32' 'flight_gate: в скрипте нет sys.path.insert и drone.py в папке скрипта нет: STOP (Python его бы не нашёл или взял бы чужой)' ($s.Text -match 'BB_FG_RESULT STOP.*нет_sys\.path\.insert_и_нет_drone\.py_в_папке_скрипта') $s.Text
$s = Run-Fg 'noinsert_ok'
Check 'P32' 'flight_gate: нет sys.path.insert, drone.py лежит в папке самого скрипта и равен r2j: OK' ($s.Text -match 'FG_NEAR .* OK' -and $s.Text -match 'BB_FG_RESULT OK') $s.Text
$s = Run-Fg 'two_dirs'
Check 'P32' 'flight_gate: две строки sys.path.insert, во второй каталоге drone.py чужой: STOP, первая OK и вторая DIFF названы' ($s.Text -match 'FG_DIR /home/lb/ros2_ws/src/bumblebee/examples drone\.py OK' -and $s.Text -match 'FG_DIR /home/lb/other drone\.py DIFF' -and $s.Text -match 'BB_FG_RESULT STOP') $s.Text
$s = Run-Fg 'noscript'
Check 'P32' 'flight_gate: скрипта нет на Pi: STOP «скрипта_нет»' ($s.Text -match 'BB_FG_RESULT STOP скрипта_нет') $s.Text
$s = Run-Fg 'badscript'
Check 'P32' 'flight_gate: путь скрипта не /home/lb/...py: отклонён, ничего не читалось' ($s.Text -match "STOP: bad SCRIPT" -and $s.Text -match 'EXIT=1' -and $s.Text -notmatch 'FG_DIR') $s.Text
$s = Run-Fg 'badwant'
Check 'P32' 'flight_gate: ожидаемая сумма не 64 hex: отклонена' ($s.Text -match 'STOP: bad WANT' -and $s.Text -match 'EXIT=1') $s.Text
$s = Run-Fg 'badhost'
Check 'P32' 'flight_gate: не тот хост: STOP, ничего не читалось' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'FG_' -and $s.Text -match 'EXIT=1') $s.Text
$sscTpl = @'
set +e
d=$(mktemp -d)
H=$d/home
mkdir -p $H
__EXTRA__
cp '__SCRIPT__' $d/gen.sh
hostname(){ echo bumblebee-20ec; }; export -f hostname
HOME=$H bash $d/gen.sh
echo EXIT=$?
rm -rf $d
'@
function Run-Ssc([string]$mode) {
    $extra = 'printf "#!/bin/bash\nsource /opt/ros/jazzy/setup.bash\nsource /home/lb/ros2_ws/install/setup.bash\nexport X=1\n" > $H/start_bumblebee.sh'
    if ($mode -eq 'overlay') { $extra = $extra + '; echo "source /home/lb/bench_ws/mavros/install/local_setup.bash" >> $H/start_bumblebee.sh' }
    if ($mode -eq 'none') { $extra = ':' }
    return (Wsl-Script ('ssc_' + $mode + '.sh') ($sscTpl.Replace('__EXTRA__', $extra).Replace('__SCRIPT__', $ssc)))
}
$s = Run-Ssc 'ok'
Check 'P33' 'start_script_check: печатает sha256 и размер start_bumblebee.sh, число строк ros2_ws (1), число строк оверлеев (0), все строки source с номерами, BB_SSC_DONE' ($s.Text -match 'SSC sha256 [0-9a-f]{64} bytes \d+' -and $s.Text -match 'SSC ros2_ws_lines 1' -and $s.Text -match 'SSC overlay_lines 0' -and $s.Text -match 'SSC line 2:source /opt/ros/jazzy/setup\.bash' -and $s.Text -match 'SSC line 3:source /home/lb/ros2_ws/install/setup\.bash' -and $s.Text -match 'BB_SSC_DONE') $s.Text
$s = Run-Ssc 'overlay'
Check 'P33' 'start_script_check: с подключённым оверлеем overlay_lines 1' ($s.Text -match 'SSC overlay_lines 1') $s.Text
$s = Run-Ssc 'none'
Check 'P33' 'start_script_check: файла нет: «SSC missing», без sha' ($s.Text -match 'SSC missing' -and $s.Text -notmatch 'SSC sha256' -and $s.Text -match 'BB_SSC_DONE') $s.Text
# ULog-отчёт: функции (нужен pyulog, он стоит в px4-venv WSL) и настоящий журнал Gazebo, если он есть (контроль по T41: прогон c7marker_01)
$venv = '/home/user/px4-venv/bin/python'
$hasVenv = (Wsl-Script 'venv.sh' "test -x $venv && echo VENV_YES").Text -match 'VENV_YES'
if ($hasVenv) {
    $unit4 = @'
import sys, os
sys.path.insert(0, sys.argv[1])
import numpy as np
import ulog_stand_report as u
def chk(name, ok):
    print(('PASS ' if ok else 'FAIL ') + name)
t = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
armed = np.array([False, True, True, False, False])
chk('armed_periods_one', u.armed_periods(t, armed) == [(1.0, 3.0)])
chk('armed_periods_open_until_end', u.armed_periods(t, np.array([False, True, True, True, True])) == [(1.0, 4.0)])
chk('armed_periods_none', u.armed_periods(t, np.zeros(5, dtype=bool)) == [])
ps = u.pauses([0.0, 0.1, 0.2, 0.7, 0.8, 2.0])
chk('pauses_two_over_0.4', len(ps) == 2 and abs(ps[0][2] - 0.5) < 1e-9 and abs(ps[1][2] - 1.2) < 1e-9)
chk('pauses_exactly_0.4_not_counted', u.pauses([0.0, 0.4, 0.8]) == [])
chk('pauses_too_few_samples', u.pauses([1.0]) == [] and u.pauses([]) == [])
cc = u.counter_changes(np.array([0.0, 1.0, 2.0, 3.0]), np.array([0, 0, 1, 1]), np.array([0.0, 0.0, 0.03, 0.0]), np.array([0.0, 0.0, 0.04, 0.0]))
chk('counter_changes_size_5cm', len(cc) == 1 and abs(cc[0][1] - 0.05) < 1e-9 and cc[0][0] == 2.0)
chk('counter_changes_wrap_255_to_0', len(u.counter_changes(np.array([0.0, 1.0]), np.array([255, 0]), np.array([0.0, 0.1]), np.array([0.0, 0.0]))) == 1)
chk('share_true_half', abs(u.share_true(np.array([0.0, 1.0, 2.0]), np.array([1, 0, 0])) - 0.5) < 1e-9)
'@
    [IO.File]::WriteAllText((Join-Path $Run 'unit4.py'), ($unit4 -replace "`r`n", "`n"), $utf8n)
    $r = Wsl-Script 'unit4.sh' ("$venv -B -I '" + (ToWsl (Join-Path $Run 'unit4.py')) + "' '$tp'")
    $u4 = @($r.Text -split "`n" | Where-Object { $_ -match '^(PASS|FAIL) ' })
    foreach ($l in $u4) { Check 'P16' ('ulog_stand_report: ' + $l.Substring(5).Trim()) ($l.StartsWith('PASS ')) '' }
    Check 'P16' 'ulog_stand_report: прогнано 9 проверок' ($u4.Count -eq 9) $r.Text
    $r = Wsl-Script 'ulog_real.sh' ("F=`$(ls -S /work/goal_step5b_20261109/runs/s10_c7marker_01/rootfs/log/*/*.ulg 2>/dev/null | head -1); if [ -z `"`$F`" ]; then echo NO_SAMPLE; else $venv -B -I '$tp/ulog_stand_report.py' `"`$F`"; fi")
    if ($r.Text -match 'NO_SAMPLE') { Note 'P17 пропущен: нет журнала Gazebo c7marker_01 в /work (проверка по настоящему ULog)' }
    else {
        Check 'P17' 'ulog_stand_report на настоящем журнале Gazebo (c7marker_01 из T41): hover_thrust_estimate нет, dist_bottom до 0.980, сбросы xy считаются, посадка: ground_contact около 2.9 с, landed около 3.6 с, выключение около 4.1 с после касания пола (как в таблице T41)' ($r.Text -match 'HOVER_THRUST_ESTIMATE in_log=no' -and $r.Text -match 'DIST_BOTTOM_MAX armed=1 max_m=0\.980' -and $r.Text -match 'XY_RESETS count=[1-9]' -and $r.Text -match 'ground_contact=2\.[89]\d maybe_landed=3\.\d+ landed=3\.[56]\d' -and $r.Text -match 'disarm=4\.[01]\d' -and $r.Text -match 'BATTERY \(no battery_status') $r.Text
    }
} else { Note 'P16 пропущен: нет /home/user/px4-venv (pyulog) в WSL' }
# ---------- r3 (T47): services_check.sh, состояние трёх служб (только чтение) ----------
$svc = "$KitW/pi/services_check.sh"
$r = Wsl-Script 'prep_svc.sh' "bash -n '$svc' && echo SVC_SYN_OK"
Check 'P34' 'bash -n для services_check.sh' ($r.Text -match 'SVC_SYN_OK') $r.Text
$svcTpl = @'
set +e
d=$(mktemp -d)
mkdir -p $d/bin
cat > $d/bin/systemctl <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$SVC_LOG"
n="${2//-/_}"
case "$1" in
  is-active) eval "st=\${ST_$n:-active}"; echo "$st"; [ "$st" = active ]; exit $? ;;
  show) eval "nr=\${NR_$n:-0}"; echo "$nr"; exit 0 ;;
esac
exit 0
EOF
cat > $d/bin/journalctl <<'EOF'
#!/bin/bash
echo "journalctl $*" >> "$SVC_LOG"
svc="$2"; n="${svc//-/_}"
eval "t=\${JR_$n:-}"
printf '%b' "$t"
exit 0
EOF
chmod +x $d/bin/*
export SVC_LOG=$d/log.txt
__ENV__
cp '__SCRIPT__' $d/gen.sh
__HOST__
HOME=$d PATH=$d/bin:$PATH bash $d/gen.sh
echo EXIT=$?
echo CALLS=$(cat $d/log.txt | tr '\n' '|')
rm -rf $d
'@
function Run-Svc([string]$env = '', [bool]$goodHost = $true, [string]$name = 'svc') {
    $host_ = ''; if ($goodHost) { $host_ = 'hostname(){ echo bumblebee-20ec; }; export -f hostname;' }
    $body = $svcTpl.Replace('__ENV__', $env).Replace('__SCRIPT__', $svc).Replace('__HOST__', $host_)
    return (Wsl-Script ('svc_' + $name + '_' + [guid]::NewGuid().ToString('N').Substring(0, 5) + '.sh') $body)
}
$jOk = "export JR_wifi_manager='May 01 wifi-manager started on 0.0.0.0:8765\n'; export JR_notify_manager='May 01 notify started\n'; export JR_led_default='May 01 led ok\n'"
$s = Run-Svc $jOk
Check 'P34' 'services_check: три службы active, перезапусков 0, журнал без ошибок: SVC x3, BB_SVC_RESULT active=3 errors=0 restarts=0 denied=0, BB_SVC_DONE' ($s.Text -match 'SVC wifi-manager active' -and $s.Text -match 'SVC notify-manager active' -and $s.Text -match 'SVC led-default active' -and $s.Text -match 'SVC_RESTARTS wifi-manager 0' -and $s.Text -match 'SVC_JOURNAL wifi-manager lines=1 access=ok' -and $s.Text -match 'SVC_ERRORS led-default 0' -and $s.Text -match 'JT wifi-manager \| May 01 wifi-manager started' -and $s.Text -match 'BB_SVC_RESULT active=3 errors=0 restarts=0 denied=0' -and $s.Text -match 'BB_SVC_DONE') $s.Text
Check 'P34' 'services_check: journalctl вызывается с -u <служба>, --since "-10 min" и --no-pager для каждой из трёх служб; systemctl только is-active и show' ($s.Text -match 'journalctl -u wifi-manager --since -10 min --no-pager' -and $s.Text -match 'journalctl -u notify-manager --since -10 min --no-pager' -and $s.Text -match 'journalctl -u led-default --since -10 min --no-pager' -and $s.Text -match 'systemctl is-active wifi-manager' -and $s.Text -match 'systemctl show led-default -p NRestarts --value' -and $s.Text -notmatch 'systemctl (stop|start|restart|enable|disable|kill|reset-failed|daemon-reload)') $s.Text
$s = Run-Svc ($jOk + '; export ST_notify_manager=inactive')
Check 'P34' 'services_check: notify-manager не active (inactive): SVC ... inactive, active=2' ($s.Text -match 'SVC notify-manager inactive' -and $s.Text -match 'BB_SVC_RESULT active=2 ') $s.Text
$s = Run-Svc ($jOk + '; export ST_led_default=failed')
Check 'P34' 'services_check: led-default failed: active=2' ($s.Text -match 'SVC led-default failed' -and $s.Text -match 'active=2 ') $s.Text
$s = Run-Svc ($jOk + '; export ST_wifi_manager=activating')
Check 'P34' 'services_check: wifi-manager activating (ещё не active): active=2' ($s.Text -match 'SVC wifi-manager activating' -and $s.Text -match 'active=2 ') $s.Text
$s = Run-Svc ($jOk + '; export JR_notify_manager=''May 01 Traceback (most recent call last):\nMay 01 ImportError: cannot import name x\n''')
Check 'P34' 'services_check: в журнале notify-manager Traceback и ImportError: SVC_ERRORS notify-manager 2, errors=2' ($s.Text -match 'SVC_ERRORS notify-manager 2' -and $s.Text -match 'BB_SVC_RESULT active=3 errors=2 ' -and $s.Text -match 'JT notify-manager \| May 01 ImportError') $s.Text
$s = Run-Svc ($jOk + '; export JR_led_default=''systemd: led-default.service: Failed with result exit-code.\n''')
Check 'P34' 'services_check: «Failed with result» в журнале считается ошибкой: SVC_ERRORS led-default 1' ($s.Text -match 'SVC_ERRORS led-default 1' -and $s.Text -match 'errors=1 ') $s.Text
$s = Run-Svc ($jOk + '; export JR_wifi_manager=''systemd: Stopping wifi-manager.service...\nsystemd: Deactivated successfully.\nsystemd: Started wifi-manager.service.\n''')
Check 'P34' 'services_check: обычная остановка и запуск службы в журнале НЕ ошибка: errors=0' ($s.Text -match 'SVC_ERRORS wifi-manager 0' -and $s.Text -match 'BB_SVC_RESULT active=3 errors=0 ') $s.Text
$s = Run-Svc ($jOk + '; export NR_led_default=3')
Check 'P34' 'services_check: led-default перезапускался сам 3 раза: SVC_RESTARTS led-default 3, restarts=3' ($s.Text -match 'SVC_RESTARTS led-default 3' -and $s.Text -match 'restarts=3 ') $s.Text
$s = Run-Svc ($jOk + '; export JR_wifi_manager=''Hint: You are currently not seeing messages from other users and the system.\n''')
Check 'P34' 'services_check: нет прав читать журнал: SVC_JOURNAL ... access=denied, denied=1 (проверить нечем)' ($s.Text -match 'SVC_JOURNAL wifi-manager lines=1 access=denied' -and $s.Text -match 'denied=1') $s.Text
$s = Run-Svc ($jOk + '; export JR_led_default=''No journal files were opened due to insufficient permissions.\n''')
Check 'P34' 'services_check: «insufficient permissions»: access=denied' ($s.Text -match 'SVC_JOURNAL led-default lines=1 access=denied') $s.Text
$s = Run-Svc '' $false 'badhost'
Check 'P34' 'services_check: не тот хост: STOP, ни одной службы не читалось' ($s.Text -match 'STOP: hostname is' -and $s.Text -notmatch 'SVC ' -and $s.Text -notmatch 'CALLS=.*systemctl' -and $s.Text -match 'EXIT=1') $s.Text
$scode = (([IO.File]::ReadAllLines((Join-Path $Kit 'pi\services_check.sh')) | Where-Object { -not $_.TrimStart().StartsWith('#') }) -join "`n")
$scodeS = [regex]::Replace($scode, '"[^"]*"', '""')
Check 'P34' 'services_check: в коде нет sudo, rm, mv, cp, tee, mkdir, touch, chmod, reboot, systemctl stop/start/restart/kill/enable/disable/reset-failed/daemon-reload, journalctl --vacuum/--rotate/--flush (только чтение)' (-not ($scodeS -match '(^|[\s;|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|reboot|shutdown)\s' -or $scodeS -match 'systemctl\s+(stop|start|restart|enable|disable|kill|reset-failed|daemon-reload|mask)' -or $scodeS -match 'journalctl[^\n]*--(vacuum|rotate|flush|sync)' -or (($scodeS -replace '2>/dev/null', '' -replace '2>&1', '') -match '>\s*[^&\s=]'))) $scode
Note ''
Note ('ИТОГ: PASS ' + $script:pass + ', FAIL ' + $script:fail)
exit $script:fail
