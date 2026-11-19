#!/bin/bash
# run_tests_r6_pi.sh (Claude, 12.11.2026, набор r6) - тесты Pi-скриптов r6 (pi/r6_*.sh) в WSL БЕЗ дрона, без ROS и без sudo.
# Поддельные команды (первые в PATH): hostname, systemctl, journalctl, ros2, pidstat, snap, apt-config, vcgencmd, iw, sudo, sleep, python3 (только для
# raw_layout_check.py, bench_recorder.py и camera_fix.py; остальное - настоящий /usr/bin/python3), детектор venv. Поддельные /proc (BB_TEST_PROC),
# /sys (BB_TEST_SYS), /etc (BB_TEST_ETC), журнал стека (BB_TEST_LOG), HOME. Настоящий ros2 и настоящий sudo НЕ вызываются (BB_TEST_NOROS, подделки первые в PATH).
# Запуск (WSL, низкий приоритет, один поток): nice -n 19 ionice -c3 bash tests/run_tests_r6_pi.sh <папка для песочницы>
# Ничего не пишет вне песочницы. Итог: строка «ИТОГ r6 Pi: PASS n, FAIL m», код 0 только при FAIL 0.
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r6pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
REALPY=/usr/bin/python3
FB="$W/fakebin"; FS="$W/state"; mkdir -p "$FB" "$FS"
export FS
# ---------- поддельные команды ----------
cat > "$FB/hostname" <<'EOF'
#!/bin/bash
echo "${FAKE_HOST:-bumblebee-20ec}"
EOF
cat > "$FB/systemctl" <<'EOF'
#!/bin/bash
echo "systemctl $*" >> "$FS/systemctl.log"
U="$FS/units"
get() { local f="$U/$1/$2"; if [ -f "$f" ]; then cat "$f"; else echo "$3"; fi; }
setv() { mkdir -p "$U/$1"; echo "$3" > "$U/$1/$2"; }
needroot() { [ "${FAKE_ROOT:-}" = 1 ] || { echo "Failed: Access denied" >&2; exit 1; }; }
case "${1:-}" in
  is-active) a=$(get "$2" active inactive); echo "$a"; [ "$a" = active ]; exit $? ;;
  is-enabled) get "$2" enabled disabled; exit 0 ;;
  --failed) cat "$FS/failed.txt" 2>/dev/null; exit 0 ;;
  list-timers) cat "$FS/timers.txt" 2>/dev/null; exit 0 ;;
  show)
    shift; unit=""; props=(); val=0
    while [ $# -gt 0 ]; do case "$1" in -p) props+=("$2"); shift 2;; --value) val=1; shift;; *) unit="$1"; shift;; esac; done
    for p in "${props[@]}"; do
      case "$p" in
        ActiveState) v=$(get "$unit" active inactive);; SubState) v=$(get "$unit" sub dead);; LoadState) v=$(get "$unit" load loaded);;
        NRestarts) v=$(get "$unit" nrestarts 0);; MainPID) v=$(get "$unit" mainpid 0);; ActiveEnterTimestampMonotonic) v=$(get "$unit" enter 0);;
        *) v="";;
      esac
      if [ "$val" = 1 ]; then echo "$v"; else echo "$p=$v"; fi
    done; exit 0 ;;
  mask)
    needroot; shift; [ "$1" = "--now" ] && shift
    [ -f "$FS/broken_mask" ] && exit 0
    for u in "$@"; do setv "$u" enabled masked; setv "$u" active inactive; mkdir -p "$BB_TEST_ETC/systemd/system"; ln -sf /dev/null "$BB_TEST_ETC/systemd/system/$u"; done; exit 0 ;;
  unmask)
    needroot; shift
    for u in "$@"; do setv "$u" enabled enabled; rm -f "$BB_TEST_ETC/systemd/system/$u"; done; exit 0 ;;
  start) needroot; setv "$2" active active; exit 0 ;;
  *) echo "fake systemctl: unknown $*" >&2; exit 1 ;;
esac
EOF
cat > "$FB/journalctl" <<'EOF'
#!/bin/bash
echo "journalctl $*" >> "$FS/journalctl.log"
if [ -f "$FS/journal_denied" ]; then echo "Hint: You are currently not seeing messages from other users and the system."; echo "      Users in groups 'adm', 'systemd-journal' can see all messages. insufficient permissions"; exit 0; fi
u=""; k=0
while [ $# -gt 0 ]; do case "$1" in -u) u="$2"; shift 2;; -k) k=1; shift;; *) shift;; esac; done
if [ "$k" = 1 ]; then cat "$FS/journal_kernel.txt" 2>/dev/null; else cat "$FS/journal_$u.txt" 2>/dev/null || echo "-- No entries --"; fi
EOF
cat > "$FB/ros2" <<'EOF'
#!/bin/bash
echo "ros2 $*" >> "$FS/ros2.log"
case "$1 $2" in
  "topic info") cat "$FS/topic_info.txt" 2>/dev/null ;;
  "node list") cat "$FS/nodes.txt" 2>/dev/null ;;
  "pkg prefix") cat "$FS/prefix_$3" 2>/dev/null || exit 1 ;;
  *) exit 1 ;;
esac
EOF
cat > "$FB/pidstat" <<'EOF'
#!/bin/bash
echo "pidstat $*" >> "$FS/pidstat.log"
echo "Linux 6.8.0 (bumblebee-20ec)"
echo "# Time UID PID %usr %system %guest %wait %CPU CPU Command"
echo "10:00:05 1000 1839 20.0 5.0 0.0 0.0 25.0 1 /opt/ros/jazzy/lib/mavros/mavros_node --ros-args password=SECRET123"
EOF
cat > "$FB/snap" <<'EOF'
#!/bin/bash
echo "snap $* root=${FAKE_ROOT:-0}" >> "$FS/snap.log"
case "$*" in
  "refresh --time") echo "timer: 00:00~24:00/4"; echo "last: today at 10:00 +04"; [ -f "$FS/snap_hold" ] && echo "hold: $(cat "$FS/snap_hold")"; echo "next: today at 16:00 +04" ;;
  "refresh --hold") [ "${FAKE_ROOT:-}" = 1 ] || exit 1; echo forever > "$FS/snap_hold"; echo "Auto-refresh of all snaps held indefinitely" ;;
  "refresh --unhold") [ "${FAKE_ROOT:-}" = 1 ] || exit 1; rm -f "$FS/snap_hold"; echo "Removed general refresh hold" ;;
  *) exit 1 ;;
esac
EOF
cat > "$FB/apt-config" <<'EOF'
#!/bin/bash
echo 'APT::Periodic::Update-Package-Lists "0";'; echo 'APT::Periodic::Unattended-Upgrade "0";'; echo 'Dir "/";'
EOF
cat > "$FB/vcgencmd" <<'EOF'
#!/bin/bash
case "$1" in measure_temp) echo "temp=48.0'C";; get_throttled) echo "throttled=0x0";; measure_clock) echo "frequency(0)=2400000000";; *) echo "?";; esac
EOF
cat > "$FB/sudo" <<'EOF'
#!/bin/bash
l=$(printf '%s ' "$@" | tr '\n' ' '); echo "sudo ${l% }" >> "$FS/sudo.log"
if [ "${1:-}" = "-p" ]; then printf '%s' "$2"; shift 2; fi
if [ -f "$FS/sudo_fail" ]; then echo "Sorry, try again."; echo "sudo: 3 incorrect password attempts"; exit 1; fi
FAKE_ROOT=1 exec "$@"
EOF
cat > "$FB/sleep" <<'EOF'
#!/bin/bash
exit 0
EOF
cat > "$FB/python3" <<'EOF'
#!/bin/bash
echo "python3 $*" >> "$FS/python3.log"
all="$*"; out=""
args=("$@")
for ((i=0; i<${#args[@]}; i++)); do [ "${args[$i]}" = "--out" ] && out="${args[$((i+1))]}"; done
case "$all" in
  *raw_layout_check.py*)
    [ -e "$out" ] && { echo "СТОП: $out уже есть (не перезаписываю)"; exit 2; }
    mkdir -p "$out"; printf 'RAWFRAME' > "$out/raw_frame_0.bin"; echo '{"ok": true}' > "$out/meta.json"
    if [ -f "$FS/k1_bad" ]; then echo "СТОП: раскладка кадра не та, что ожидалась"; exit 1; fi
    echo "RAW CHECK ГОТОВО: 5/5 кадров: step 1280, 614400 байт, нули в заполнении при шаге 1600 ($out)"; exit 0 ;;
  *bench_recorder.py*)
    [ -e "$out" ] && { echo "STOP: exists"; exit 2; }
    mkdir -p "$out"; echo '{"idle_pct_of_all_cores": 55.0, "topics": {"markers": {"hz": 10.0}}}' > "$out/summary.json"; echo "t,busy" > "$out/samples.csv"
    echo "$all" > "$FS/recorder_args.txt"; echo "RECORDER ГОТОВО: $out"; exit 0 ;;
  *camera_fix.py*)
    echo "$all" > "$FS/camfix_args.txt"
    echo "[INFO] [1.0] [main_camera.main_camera_fix_full]: camera_fix: image_raw_yuv -> image_raw_full (period=5, full_rows=True, source_pitch=1600)"
    [ -f "$FS/camfix_nostats" ] || echo "[INFO] [31.0] [main_camera.main_camera_fix_full]: camera_fix stats 30s: full-row frames 720, legacy frames 0"
    exit 0 ;;
  *) exec /usr/bin/python3 "$@" ;;
esac
EOF
chmod +x "$FB"/*
mkdir -p "$W/fakebin_iw"
cat > "$W/fakebin_iw/iw" <<'EOF'
#!/bin/bash
cat "$FS/iw.txt"
EOF
chmod +x "$W/fakebin_iw/iw"
export PATH="$FB:/usr/bin:/bin"
export BB_TEST_NOROS=1
# ---------- поддельные /proc, /sys, /etc, HOME ----------
P="$W/proc"; mkdir -p "$P/sys/kernel/random"
echo "600.00 1000.00" > "$P/uptime"; echo "0.10 0.20 0.30 1/100 999" > "$P/loadavg"; echo "btime 1794000000" > "$P/stat"; echo "boot-1111" > "$P/sys/kernel/random/boot_id"
mkproc() { local pid="$1"; shift; mkdir -p "$P/$pid"; printf '%s\0' "$@" > "$P/$pid/cmdline"; echo "$pid (python3) S 1 1 1 0 -1 4194560 100 0 0 0 10 5 0 0 20 0 7 0 ${STARTT:-60000} 100000 1000" > "$P/$pid/stat"; }
rmproc() { rm -rf "${P:?}/$1"; }
export BB_TEST_PROC="$P"
S="$W/sys"; mkdir -p "$S/devices/system/cpu/cpu0/cpufreq"; echo ondemand > "$S/devices/system/cpu/cpu0/cpufreq/scaling_governor"; echo 2400000 > "$S/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
export BB_TEST_SYS="$S"
E="$W/etc"; mkdir -p "$E/systemd/system" "$E/NetworkManager/conf.d"; printf '[connection]\nwifi.powersave = 2\n' > "$E/NetworkManager/conf.d/zz-bumblebee-wifi-powersave.conf"
export BB_TEST_ETC="$E"
H="$W/home"; mkdir -p "$H"
printf '#!/bin/bash\nsource /opt/ros/jazzy/setup.bash\nsource /home/lb/ros2_ws/install/setup.bash\nsource /home/lb/bench_ws/r2j/install/local_setup.bash\nexec ros2 launch bumblebee bumblebee.launch.py\n' > "$H/start_bumblebee.sh"
export HOME="$H"
units() { for u in "$@"; do mkdir -p "$FS/units/$u"; echo active > "$FS/units/$u/active"; echo enabled > "$FS/units/$u/enabled"; echo loaded > "$FS/units/$u/load"; echo running > "$FS/units/$u/sub"; echo 0 > "$FS/units/$u/nrestarts"; echo 100 > "$FS/units/$u/mainpid"; echo 5000000 > "$FS/units/$u/enter"; done; }
reset_state() {
  rm -rf "$FS"; mkdir -p "$FS"
  units bumblebee wifi-manager wifi-watchdog notify-manager avahi-daemon NetworkManager sys_metrics fwupd-refresh.timer man-db.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer
  echo 4242 > "$FS/units/bumblebee/mainpid"
  printf '[    8.8] kernel: brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled\n[   20.8] kernel: brcmfmac: brcmf_cfg80211_set_power_mgmt: power save disabled\n' > "$FS/journal_kernel.txt"
  printf 'Type: geometry_msgs/msg/PoseStamped\n\nPublisher count: 1\n\nNode name: qos_relay\nNode namespace: /\nEndpoint type: PUBLISHER\n\nSubscription count: 0\n\n' > "$FS/topic_info.txt"
  printf '/mavros\n/mavros/mavros\n/aruco_detect\n/transform_listener_impl_aaaade807f58\n' > "$FS/nodes.txt"
  printf 'NEXT LEFT LAST PASSED UNIT ACTIVATES\nThu 2026-11-13 00:00:00 +04 10h - - fwupd-refresh.timer fwupd-refresh.service\n' > "$FS/timers.txt"
  rm -f "$E/systemd/system/"*
}
gen() { # gen <шаблон> <маркер> <файл со строками> <выход>: строка маркера заменяется содержимым файла (как BL-Generate на ПК)
  awk -v mk="$2" -v f="$3" '$0 == mk { while ((getline l < f) > 0) print l; next } { print }' "$1" > "$4"
}
run() { # run <имя> <скрипт> [аргументы]: stdout -> $W/<имя>.out, stderr -> .err, код -> RC
  local n="$1" sc="$2"; shift 2
  bash "$sc" "$@" > "$W/$n.out" 2> "$W/$n.err"; RC=$?
  O="$W/$n.out"
}
has() { grep -q -a -E -- "$1" "$O"; }
PI="$KIT/pi"
# ======================= P1: чужой хост у всех новых скриптов =======================
reset_state
for sc in r6_pi_load.sh r6_sys_check.sh r6_sys_change.sh r6_cam_incoming.sh r6_cam_mkdir.sh r6_k1.sh r6_cost_phase.sh r6_cost_end.sh r6_cam_precheck.sh r6_cam_verify.sh; do
  FAKE_HOST=other-pi run "host_$sc" "$PI/$sc" fwupd apply
  t "P1 $sc: чужое имя хоста -> код 1, STOP в stderr, в stdout ничего" '[ "$RC" = 1 ] && grep -q "STOP: hostname is other-pi" "$W/host_$sc.err" && [ ! -s "$O" ]'
done
t "P1b после отказов по имени хоста ни одна поддельная команда не вызывалась (systemctl, sudo, ros2, python3)" '[ ! -e "$FS/systemctl.log" ] && [ ! -e "$FS/sudo.log" ] && [ ! -e "$FS/ros2.log" ] && [ ! -e "$FS/python3.log" ]'
# ======================= P2: r6_pi_load.sh =======================
reset_state; before=$(find "$H" -type f | sort | sha256sum)
run load "$PI/r6_pi_load.sh"
t "P2 load: код 0 и BB_R6LOAD_DONE" '[ "$RC" = 0 ] && has "^BB_R6LOAD_DONE$"'
t "P2 load: службы с MainPID (bumblebee mainpid=4242), регулятор cpu0 ondemand, Wi-Fi last=disabled, conf zz-bumblebee" 'has "^LOAD_SERVICE bumblebee active=active enabled=enabled mainpid=4242 nrestarts=0" && has "^LOAD_GOVERNOR cpu0 governor=ondemand" && has "^LOAD_WIFI_PS_JOURNAL access=ok last=disabled" && has "^LOAD_NM_CONF .*zz-bumblebee-wifi-powersave.conf wifi.powersave=2"'
t "P2 load: подписчики *_reliable из ros2 topic info (publishers=1 subscribers=0) для трёх тем" '[ "$(grep -c "^LOAD_RELIABLE /mavros/mavros/.*_reliable publishers=1 subscribers=0" "$O")" = 3 ]'
t "P2 load: все вызовы ros2 с --no-daemon, нет topic hz" '[ "$(grep -c . "$FS/ros2.log")" -ge 4 ] && ! grep -v -- "--no-daemon" "$FS/ros2.log" | grep -q . && ! grep -q "topic hz" "$FS/ros2.log"'
t "P2 load: pidstat -u -r -h -l 5 24, snap refresh --time, apt periodic, list-timers" 'grep -q "^pidstat -u -r -h -l 5 24$" "$FS/pidstat.log" && has "^LOAD_SNAP timer:" && has "^LOAD_APT APT::Periodic::Update-Package-Lists" && has "^LOAD_TIMER .*fwupd-refresh.timer"'
t "P2 load: слово пароля в командной строке процесса замаскировано (password=***)" 'has "password=\*\*\*" && ! has "SECRET123"'
t "P2 load: sudo не вызывался, systemctl только чтение (show/is-enabled), в HOME ничего не появилось" '[ ! -e "$FS/sudo.log" ] && ! grep -q -E "systemctl (start|stop|restart|mask|unmask)" "$FS/systemctl.log" && [ "$(find "$H" -type f | sort | sha256sum)" = "$before" ]'
touch "$FS/journal_denied"; run load2 "$PI/r6_pi_load.sh"
t "P3 load: журнал ядра недоступен -> access=denied, всё равно DONE" 'has "^LOAD_WIFI_PS_JOURNAL access=denied" && has "^BB_R6LOAD_DONE$"'
# ======================= P4-P5: r6_sys_check.sh =======================
reset_state; before=$(find "$H" -type f | sort | sha256sum)
run sc "$PI/r6_sys_check.sh"
t "P4 sc: код 0, DONE, failed 0, 7 служб SC_SVC, SC_WIFI journal=disabled, нет iw" '[ "$RC" = 0 ] && has "^BB_R6SC_DONE$" && has "^SC_FAILED_COUNT 0$" && [ "$(grep -c "^SC_SVC " "$O")" = 7 ] && has "^SC_WIFI journal=disabled$" && has "^SC_WIFI_IW n/a"'
t "P4 sc: SC_SVC с nrestarts и enter_mono, SC_JERR access=ok errors=0" 'has "^SC_SVC notify-manager load=loaded active=active sub=running nrestarts=0 mainpid=100 enter_mono=5000000$" && [ "$(grep -c "^SC_JERR .* errors=0 access=ok$" "$O")" = 7 ]'
t "P4 sc: узлы через ros2 node list --no-daemon, transform_listener_impl_<адрес> нормализован" 'grep -q "^ros2 node list --no-daemon" "$FS/ros2.log" && has "^SC_NODE /transform_listener_impl_X$" && ! has "aaaade807f58"'
t "P4 sc: состояние ступени 1 справкой (5 таймеров и snap hold=none), pidstat 30 с, ничего не записано" '[ "$(grep -c "^SC_STEP1 .*timer enabled=enabled active=active$" "$O")" = 5 ] && has "^SC_STEP1 snap hold=none$" && grep -q "^pidstat -u -h -l 5 6$" "$FS/pidstat.log" && [ "$(find "$H" -type f | sort | sha256sum)" = "$before" ] && [ ! -e "$FS/sudo.log" ]'
printf 'x.service loaded failed failed X\ny.service loaded failed failed Y\n' > "$FS/failed.txt"
printf 'Nov 13 wifi_manager[1]: Traceback (most recent call last):\nNov 13 wifi_manager[1]: ImportError: no module\n' > "$FS/journal_wifi-manager.txt"
printf '[ 30.0] kernel: brcmfmac: brcmf_cfg80211_set_power_mgmt: power save enabled\n' > "$FS/journal_kernel.txt"
echo 3 > "$FS/units/wifi-watchdog/nrestarts"; echo "Power save: on" > "$FS/iw.txt"
PATH="$FB:$W/fakebin_iw:/usr/bin:/bin" run sc2 "$PI/r6_sys_check.sh"
t "P5 sc: failed 2, ошибки журнала wifi-manager (2 строки), NRestarts 3, Wi-Fi enabled, iw on" 'has "^SC_FAILED_COUNT 2$" && has "^SC_JERR wifi-manager errors=2 access=ok$" && has "^SC_SVC wifi-watchdog .* nrestarts=3 " && has "^SC_WIFI journal=enabled$" && has "^SC_WIFI_IW on$"'
touch "$FS/journal_denied"; run sc3 "$PI/r6_sys_check.sh"
t "P5 sc: журнал недоступен -> SC_JERR access=denied, SC_WIFI journal=denied" '[ "$(grep -c "^SC_JERR .* access=denied$" "$O")" = 7 ] && has "^SC_WIFI journal=denied$"'
# ======================= P6-P14: r6_sys_change.sh =======================
reset_state
run sys_fw "$PI/r6_sys_change.sh" fwupd apply
t "P6 fwupd apply: код 0, снимок до (enabled/active), подсказка sudo строкой, после masked/inactive, BB_SYS_DONE" '[ "$RC" = 0 ] && has "^SYS_BEFORE fwupd-refresh.timer enabled=enabled active=active" && has "^SYS_SUDO_PROMPT пароль sudo" && has "^SYS_AFTER fwupd-refresh.timer enabled=masked active=inactive" && has "^BB_SYS_DONE fwupd apply OK$"'
t "P6 fwupd apply: sudo вызван ровно раз, с -p и systemctl mask --now fwupd-refresh.timer; маска в etc -> /dev/null" '[ "$(grep -c . "$FS/sudo.log")" = 1 ] && grep -q "^sudo -p .* systemctl mask --now fwupd-refresh.timer$" "$FS/sudo.log" && [ "$(readlink "$E/systemd/system/fwupd-refresh.timer")" = /dev/null ]'
run sys_fw2 "$PI/r6_sys_change.sh" fwupd apply
t "P7 fwupd apply повторно (уже masked): BB_SYS_STOP, код 3, sudo не вызывался" '[ "$RC" = 3 ] && has "^BB_SYS_STOP .*is-enabled=masked" && [ "$(grep -c . "$FS/sudo.log")" = 1 ]'
run sys_fw3 "$PI/r6_sys_change.sh" fwupd rollback
t "P9 fwupd rollback: код 0, unmask и start, после enabled/active, маски нет" '[ "$RC" = 0 ] && has "^BB_SYS_DONE fwupd rollback OK$" && grep -q "systemctl unmask fwupd-refresh.timer" "$FS/sudo.log" && grep -q "systemctl start fwupd-refresh.timer" "$FS/sudo.log" && has "^SYS_AFTER fwupd-refresh.timer enabled=enabled active=active" && [ ! -e "$E/systemd/system/fwupd-refresh.timer" ]'
run sys_fw4 "$PI/r6_sys_change.sh" fwupd rollback
t "P9 fwupd rollback, когда маски нет: BB_SYS_STOP, код 3" '[ "$RC" = 3 ] && has "^BB_SYS_STOP"'
reset_state; printf '[Timer]\n' > "$E/systemd/system/fwupd-refresh.timer"
run sys_fw5 "$PI/r6_sys_change.sh" fwupd apply
t "P8 fwupd apply, в /etc свой файл юнита: BB_SYS_STOP, sudo не вызывался" '[ "$RC" = 3 ] && has "^BB_SYS_STOP .*есть_/etc/systemd/system/fwupd-refresh.timer" && [ ! -e "$FS/sudo.log" ]'
reset_state
run sys_tm "$PI/r6_sys_change.sh" timers apply
t "P10 timers apply: код 0, 4 таймера masked/inactive одной командой sudo" '[ "$RC" = 0 ] && has "^BB_SYS_DONE timers apply OK$" && [ "$(grep -c "^SYS_AFTER .*timer enabled=masked active=inactive" "$O")" = 4 ] && grep -q "systemctl mask --now man-db.timer motd-news.timer update-notifier-download.timer update-notifier-motd.timer$" "$FS/sudo.log"'
run sys_tm2 "$PI/r6_sys_change.sh" timers rollback
t "P10 timers rollback: код 0, все 4 enabled/active" '[ "$RC" = 0 ] && [ "$(grep -c "^SYS_AFTER .*timer enabled=enabled active=active" "$O")" = 4 ]'
reset_state; echo not-found > "$FS/units/motd-news.timer/load"
run sys_tm3 "$PI/r6_sys_change.sh" timers apply
t "P10 timers apply, один таймер не загружен: BB_SYS_STOP, sudo не вызывался" '[ "$RC" = 3 ] && has "motd-news.timer:LoadState=not-found" && [ ! -e "$FS/sudo.log" ]'
reset_state
run sys_sn "$PI/r6_sys_change.sh" snaphold apply
t "P11 snaphold apply: код 0, sudo snap refresh --hold, после «hold: forever»" '[ "$RC" = 0 ] && has "^BB_SYS_DONE snaphold apply OK$" && grep -q "snap refresh --hold$" "$FS/sudo.log" && has "^SYS_AFTER_SNAP hold: forever$"'
run sys_sn2 "$PI/r6_sys_change.sh" snaphold apply
t "P11 snaphold apply повторно: BB_SYS_STOP «уже hold»" '[ "$RC" = 3 ] && has "snap:уже_hold_forever"'
run sys_sn3 "$PI/r6_sys_change.sh" snaphold rollback
t "P11 snaphold rollback: код 0, hold нет" '[ "$RC" = 0 ] && has "^BB_SYS_DONE snaphold rollback OK$" && ! has "^SYS_AFTER_SNAP hold:"'
reset_state; echo "24 days ago, at 11:09 +04" > "$FS/snap_hold"
run sys_sn4 "$PI/r6_sys_change.sh" snaphold apply
t "P11 snaphold: просроченная пауза («24 days ago») не считается hold: правка идёт, код 0" '[ "$RC" = 0 ] && has "^SYS_BEFORE_SNAP hold: 24 days ago" && has "^BB_SYS_DONE snaphold apply OK$"'
reset_state; touch "$FS/sudo_fail"
run sys_nc "$PI/r6_sys_change.sh" fwupd apply
t "P12 sudo не принял пароль: BB_SYS_NOCHANGE, код 5, таймер как был" '[ "$RC" = 5 ] && has "^BB_SYS_NOCHANGE fwupd apply" && [ "$(cat "$FS/units/fwupd-refresh.timer/enabled")" = enabled ]'
reset_state; touch "$FS/broken_mask"
run sys_bm "$PI/r6_sys_change.sh" fwupd apply
t "P13 mask «прошёл», но не применился: BB_SYS_FAIL, код 4 (правка, которая тихо не применилась)" '[ "$RC" = 4 ] && has "^BB_SYS_FAIL fwupd apply rc=0 check=1"'
run sys_bad "$PI/r6_sys_change.sh" rm_rf apply
t "P14 неизвестная правка: BB_SYS_STOP, код 3" '[ "$RC" = 3 ] && has "^BB_SYS_STOP неизвестная правка"'
run sys_bad2 "$PI/r6_sys_change.sh" fwupd now
t "P14 неизвестный режим: BB_SYS_STOP, код 3" '[ "$RC" = 3 ] && has "^BB_SYS_STOP неизвестный режим"'
# ======================= P15-P16: incoming и mkdir =======================
reset_state
CF="$KIT/camera_fullrow"
{ for f in camera_fix.py bench_recorder.py raw_layout_check.py SHA256SUMS_camera_fullrow.txt; do echo "$(sha256sum "$CF/$f" | cut -c1-64)  $f"; done; } > "$W/camfiles.txt"
gen "$PI/r6_cam_incoming.sh" "#@@CAMFILES@@" "$W/camfiles.txt" "$W/ci.sh"
run ci1 "$W/ci.sh"
t "P15 incoming: папки нет -> CI_STATE absent" 'has "^CI_STATE absent$" && has "^BB_R6CI_DONE$"'
run mk1 "$PI/r6_cam_mkdir.sh"
t "P16 mkdir: новая папка, MKDIR_OK" '[ "$RC" = 0 ] && has "^MKDIR_OK " && [ -d "$H/bench_ws/incoming/camera_fullrow_r6" ]'
cp "$CF/camera_fix.py" "$CF/bench_recorder.py" "$CF/raw_layout_check.py" "$CF/SHA256SUMS_camera_fullrow.txt" "$H/bench_ws/incoming/camera_fullrow_r6/"
run mk2 "$PI/r6_cam_mkdir.sh"
t "P16 mkdir повторно: папка уже есть -> без MKDIR_OK, код не 0, файлы целы" '[ "$RC" != 0 ] && ! has "MKDIR_OK" && [ "$(ls "$H/bench_ws/incoming/camera_fullrow_r6" | wc -l)" = 4 ]'
run ci2 "$W/ci.sh"
t "P15 incoming: 4 файла верны -> CI_STATE ok" 'has "^CI_STATE ok$" && [ "$(grep -c "^CI_FILE .* OK$" "$O")" = 4 ]'
echo x > "$H/bench_ws/incoming/camera_fullrow_r6/extra.txt"
run ci3 "$W/ci.sh"
t "P15 incoming: лишний файл называется (CI_EXTRA), суммы верны -> ok" 'has "^CI_EXTRA extra.txt$" && has "^CI_STATE ok$"'
rm "$H/bench_ws/incoming/camera_fullrow_r6/extra.txt"; cp "$H/bench_ws/incoming/camera_fullrow_r6/bench_recorder.py" "$W/br.bak"; echo "# x" >> "$H/bench_ws/incoming/camera_fullrow_r6/bench_recorder.py"
run ci4 "$W/ci.sh"
t "P15 incoming: файл изменён -> DIFF и CI_STATE bad" 'has "^CI_FILE bench_recorder.py DIFF" && has "^CI_STATE bad$"'
cp "$W/br.bak" "$H/bench_ws/incoming/camera_fullrow_r6/bench_recorder.py"
# ======================= P17: r6_k1.sh =======================
export BB_TEST_LOG="$W/bumblebee.log"; printf '[INFO] [x-1]: process has died [pid 1]\n' > "$BB_TEST_LOG"
run k1bad "$PI/r6_k1.sh" 2026-11-13
t "P17 k1: метка не ГГГГММДД_ЧЧММСС -> НЕ ГОТОВО, код 2, ничего не создано" '[ "$RC" = 2 ] && has "^К1 НЕ ГОТОВО: метка" && [ ! -e "$H/bench_ws/camera_fullrow_r6" ]'
mkproc 7001 python3 "$H/bench_ws/incoming/camera_fullrow_r6/raw_layout_check.py" --out /x
run k1busy "$PI/r6_k1.sh" 20261113_101000
t "P17 k1: уже работает процесс замера (нашёлся в /proc без pgrep) -> НЕ ГОТОВО, папка не создана" 'has "^К1 НЕ ГОТОВО: уже работает процесс замера: 7001" && [ ! -e "$H/bench_ws/camera_fullrow_r6/20261113_101000" ]'
rmproc 7001; mkproc 7002 bash -c "# BB_R6K1_MARK raw_layout_check.py aruco_detect_bench"
mkproc 1843 python3 /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/camera_fix.py --ros-args -r __node:=main_camera_fix -r __ns:=/main_camera
run k1 "$PI/r6_k1.sh" 20261113_101000
t "P17 k1: свой скрипт (метка BB_R6) не считается процессом замера; К1 ГОТОВО, K1_DIR, meta, кадр 0" '[ "$RC" = 0 ] && has "^К1 ГОТОВО " && has "^K1_DIR " && has "^K1_META " && has "^K1_FRAME0 bytes=8 " && [ -f "$H/bench_ws/camera_fullrow_r6/20261113_101000/K1/raw_check/meta.json" ]'
t "P17 k1: записано «до»: троттлинг, температура, число process has died (1), процессы стека (1)" 'has "^K1_THROTTLED_START throttled=0x0" && has "^K1_DIED_START 1$" && has "^K1_STACK_PROCS 1$"'
t "P17 k1: raw_layout_check запущен системным python3 -B с --candidate из incoming и --n 5" 'grep -q "python3 -B $H/bench_ws/incoming/camera_fullrow_r6/raw_layout_check.py --out $H/bench_ws/camera_fullrow_r6/20261113_101000/K1/raw_check --candidate $H/bench_ws/incoming/camera_fullrow_r6/camera_fix.py --n 5" "$FS/python3.log"'
t "P17 k1: на Pi новые файлы только в ~/bench_ws/camera_fullrow_r6 и incoming (больше ничего в HOME)" '[ -z "$(find "$H" -type f ! -path "$H/bench_ws/camera_fullrow_r6/*" ! -path "$H/bench_ws/incoming/camera_fullrow_r6/*" ! -name start_bumblebee.sh)" ]'
run k1again "$PI/r6_k1.sh" 20261113_101000
t "P17 k1: та же метка второй раз -> «уже есть, ничего не перезаписываю»" 'has "^К1 НЕ ГОТОВО: папка .* уже есть, ничего не перезаписываю"'
touch "$FS/k1_bad"; run k1b "$PI/r6_k1.sh" 20261113_101001
t "P17 k1: раскладка не та -> К1 НЕ ГОТОВО, но K1_DIR есть (файлы создавались)" 'has "^К1 НЕ ГОТОВО: нет строки RAW CHECK ГОТОВО" && has "^K1_DIR "'
rm -f "$FS/k1_bad"; mv "$H/bench_ws/incoming/camera_fullrow_r6" "$W/inc_aside"
run k1noinc "$PI/r6_k1.sh" 20261113_101002
t "P17 k1: нет папки файлов замера -> НЕ ГОТОВО" 'has "^К1 НЕ ГОТОВО: нет .*incoming/camera_fullrow_r6"'
mv "$W/inc_aside" "$H/bench_ws/incoming/camera_fullrow_r6"; cp "$H/bench_ws/incoming/camera_fullrow_r6/camera_fix.py" "$W/cf.bak"; echo "#" >> "$H/bench_ws/incoming/camera_fullrow_r6/camera_fix.py"
run k1sum "$PI/r6_k1.sh" 20261113_101003
t "P17 k1: суммы файлов замера не сходятся -> НЕ ГОТОВО, папка не создана" 'has "^К1 НЕ ГОТОВО: sha256" && [ ! -e "$H/bench_ws/camera_fullrow_r6/20261113_101003" ]'
cp "$W/cf.bak" "$H/bench_ws/incoming/camera_fullrow_r6/camera_fix.py"
# ======================= P18-P19: цена A, C, A2 и конец =======================
PFX="$W/pfx"; mkdir -p "$PFX/bumblebee/lib/bumblebee" "$PFX/bumblebee/share/bumblebee/launch" "$PFX/aruco_pose/share/aruco_pose/map"
echo "# aruco" > "$PFX/bumblebee/lib/bumblebee/aruco_detect.py"; echo "# launch" > "$PFX/bumblebee/share/bumblebee/launch/aruco.launch.py"; echo "0 0.15 0 0" > "$PFX/aruco_pose/share/aruco_pose/map/map.txt"
echo "$PFX/bumblebee" > "$FS/prefix_bumblebee"; echo "$PFX/aruco_pose" > "$FS/prefix_aruco_pose"
mkdir -p "$H/opencv47_venv/bin"; printf '#!/bin/bash\necho "venv $*" >> "$FS/venv.log"\nexit 0\n' > "$H/opencv47_venv/bin/python3"; chmod +x "$H/opencv47_venv/bin/python3"
mkproc 1839 /opt/ros/jazzy/lib/mavros/mavros_node --ros-args -r __node:=mavros
mkproc 2204 /home/lb/opencv47_venv/bin/python3 /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/aruco_detect.py --ros-args -r __node:=aruco_detect -r __ns:=/
rmproc 7002
run cA "$PI/r6_cost_phase.sh" 20261113_102000 A
t "P18 cost A: ФАЗА A ГОТОВО, summary, recorder на /main_camera/image_raw, без camera_fix полных строк" '[ "$RC" = 0 ] && has "^ФАЗА A ГОТОВО: " && has "^COST_SUMMARY_JSON " && grep -q -- "--image-topic /main_camera/image_raw " "$FS/recorder_args.txt" && [ ! -e "$FS/camfix_args.txt" ]'
t "P18 cost A: детектор через ~/opencv47_venv/bin/python3 -B, aruco_detect стека, gate_by_flight_state:=false, все выходы в /bench" 'grep -q "^venv -B $PFX/bumblebee/lib/bumblebee/aruco_detect.py --ros-args -r __node:=aruco_detect_bench" "$FS/venv.log" && grep -q "gate_by_flight_state:=false" "$FS/venv.log" && grep -q -- "-r markers:=/bench/aruco_detect/markers" "$FS/venv.log" && grep -q -- "-r /tf:=/bench/tf" "$FS/venv.log" && grep -q -- "-r /aruco_detect/markers_used:=/bench/aruco_detect/markers_used" "$FS/venv.log" && grep -q -- "-r image_raw:=/main_camera/image_raw " "$FS/venv.log"'
t "P18 cost A: стек до фазы: по одному main_camera_fix, aruco_detect, mavros_node" 'has "^COST_STACK_BEFORE .__node:=main_camera_fix . 1$" && has "^COST_STACK_BEFORE .__node:=aruco_detect . 1$" && has "^COST_STACK_BEFORE .mavros_node. 1$"'
run cC "$PI/r6_cost_phase.sh" 20261113_102000 C
t "P18 cost C: camera_fix полных строк в новые темы (__node:=main_camera_fix_full, output_topic:=image_raw_full, camera_info_full), детектор и запись на image_raw_full, ГОТОВО" '[ "$RC" = 0 ] && has "^ФАЗА C ГОТОВО: " && grep -q -- "__node:=main_camera_fix_full -p output_topic:=image_raw_full -r camera_info:=camera_info_full" "$FS/camfix_args.txt" && grep -q -- "--image-topic /main_camera/image_raw_full" "$FS/recorder_args.txt" && has "^COST_CAMFIX_FULL .*full-row frames 720, legacy frames 0"'
run cC2 "$PI/r6_cost_phase.sh" 20261113_102000 C
t "P18 cost C той же метки второй раз: «уже есть, ничего не перезаписываю», ничего не запускалось" 'has "^ФАЗА C НЕ ГОТОВО: уже есть .*ничего не перезаписываю"'
touch "$FS/camfix_nostats"; run cC3 "$PI/r6_cost_phase.sh" 20261113_102001 C
t "P18 cost C без строк stats у кандидата: НЕ ГОТОВО" 'has "^ФАЗА C НЕ ГОТОВО: в журнале main_camera_fix_full нет строк stats"'
rm -f "$FS/camfix_nostats"
mkproc 1850 python3 /x/lib/bumblebee/camera_fix.py --ros-args -r __node:=main_camera_fix -r __ns:=/main_camera
run cA3 "$PI/r6_cost_phase.sh" 20261113_102002 A
t "P18 cost: в стеке два main_camera_fix -> НЕ ГОТОВО до запуска чего-либо" 'has "^ФАЗА A НЕ ГОТОВО: в стеке не ровно один процесс" && [ ! -e "$H/bench_ws/camera_fullrow_r6/20261113_102002/cost" ]'
rmproc 1850
run cX "$PI/r6_cost_phase.sh" 20261113_102003 B
t "P18 cost: фаза не A/C/A2 -> НЕ ГОТОВО" 'has "^ФАЗА B НЕ ГОТОВО: фаза"'
mv "$H/opencv47_venv" "$W/venv_aside"; run cV "$PI/r6_cost_phase.sh" 20261113_102004 A
t "P18 cost: нет ~/opencv47_venv/bin/python3 -> НЕ ГОТОВО (системный OpenCV 4.6 без ArucoDetector)" 'has "^ФАЗА A НЕ ГОТОВО: нет .*opencv47_venv/bin/python3"'
mv "$W/venv_aside" "$H/opencv47_venv"
t "P18 cost: новые файлы только в ~/bench_ws/camera_fullrow_r6/*/cost" '[ -z "$(find "$H/bench_ws/camera_fullrow_r6" -type f -path "*/cost/*" -prune -o -type f ! -path "*/K1/*" -print)" ]'
run e1 "$PI/r6_cost_end.sh" 20261113_102000
t "P19 end: процессов замера нет, стек по одному -> ГОТОВО" 'has "^КАМЕРА: ЗАМЕР ЗАКОНЧЕН, СТЕК КАК БЫЛ — ГОТОВО$" && has "^END_DIED 1$"'
mkproc 7100 timeout -s INT 230 /home/lb/opencv47_venv/bin/python3 x.py --ros-args -r __node:=aruco_detect_bench
run e2 "$PI/r6_cost_end.sh" 20261113_102000
t "P19 end: остался процесс замера -> НЕ ГОТОВО, назван pid" 'has "^END_MEAS_LEFT 7100 " && has "^КОНЕЦ ЗАМЕРА НЕ ГОТОВО:"'
rmproc 7100
# ======================= P20: r6_cam_precheck.sh =======================
mkf() { mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"; }
RS="$W/r2jfiles"; mkf "$RS/cam_r2j" "camera r2j"; mkf "$RS/cam_var" "camera variant"; mkf "$RS/ln_r2j" "launch r2j"; mkf "$RS/ln_var" "launch variant"
sh_() { sha256sum "$1" | cut -c1-64; }
CR=$(sh_ "$RS/cam_r2j"); CV=$(sh_ "$RS/cam_var"); LR=$(sh_ "$RS/ln_r2j"); LV=$(sh_ "$RS/ln_var")
{ echo "ros2_ws/src/bumblebee/src/python/camera_fix.py $CR $CV"; echo "ros2_ws/src/bumblebee/launch/bumblebee.launch.py $LR $LV"; echo "bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py $CR $CV"; echo "bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py $LR $LV"; } > "$W/camvar.txt"
BR="$W/backup"; MS=$(printf 'x\n' | sha256sum | cut -c1-64)
printf 'BROOT=%s\nMSHA=%s\n' "$BR" "$MS" > "$W/cpargs.txt"
gen "$PI/r6_cam_precheck.sh" "#@@CAMVAR@@" "$W/camvar.txt" "$W/cp1.sh"; gen "$W/cp1.sh" "#@@CPARGS@@" "$W/cpargs.txt" "$W/cp.sh"
setfiles() { mkf "$H/ros2_ws/src/bumblebee/src/python/camera_fix.py" "camera $1"; mkf "$H/ros2_ws/src/bumblebee/launch/bumblebee.launch.py" "launch $1"; mkf "$H/bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py" "camera $1"; mkf "$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" "launch $1"; }
setfiles r2j; echo inactive > "$FS/units/bumblebee/active"
export BB_TEST_PREFIX="$H/bench_ws/r2j/install/bumblebee"
run cp1 "$W/cp.sh" install
t "P20 precheck install: служба inactive, строка оверлея, префикс = оверлей r2j, 4 файла r2j -> CP_RESULT OK" 'has "^CP_SERVICE bumblebee inactive$" && has "^CP_OVERLAY_LINE yes$" && has "^CP_COUNT files=4 r2j=4 cam=0$" && has "^CP_RESULT OK$"'
echo active > "$FS/units/bumblebee/active"; run cp2 "$W/cp.sh" install
t "P20 precheck install: служба active -> STOP" 'has "^CP_RESULT STOP.*служба_bumblebee_active"'
echo inactive > "$FS/units/bumblebee/active"; BB_TEST_PREFIX="$H/ros2_ws/install/bumblebee" run cp3 "$W/cp.sh" install
t "P20 precheck install: исполняется ros2_ws, а не оверлей -> STOP (правка легла бы не туда)" 'has "^CP_RESULT STOP.*исполняется_не_оверлей_r2j"'
cp "$H/start_bumblebee.sh" "$W/sb.bak"; grep -v "bench_ws/r2j" "$W/sb.bak" > "$H/start_bumblebee.sh"; run cp4 "$W/cp.sh" install
t "P20 precheck install: в start_bumblebee.sh нет строки оверлея -> STOP" 'has "^CP_OVERLAY_LINE no$" && has "^CP_RESULT STOP"'
cp "$W/sb.bak" "$H/start_bumblebee.sh"; setfiles variant; run cp5 "$W/cp.sh" install
t "P20 precheck install: файлы уже вариант -> STOP (не r2j)" 'has "^CP_COUNT files=4 r2j=0 cam=4$" && has "^CP_RESULT STOP.*файлы_не_равны_r2j"'
run cp6 "$W/cp.sh" installed
t "P20 precheck installed: 4 файла = вариант -> OK" 'has "^CP_RESULT OK$"'
mkdir -p "$BR/20261113_090000/files" "$BR/20261113_100000/files" "$BR/20261113_110000/files"
for b in 20261113_090000 20261113_100000 20261113_110000; do printf 'x\n' > "$BR/$b/installed_manifest.tsv"; : > "$BR/$b/files.sha256"; done
printf 'y\n' > "$BR/20261113_110000/installed_manifest.tsv"; touch "$BR/20261113_090000/ROLLED_BACK"
run cp7 "$W/cp.sh" rollback
t "P20 precheck rollback: список резервов с совпадением манифеста и пометкой отката" 'has "^CP_BACKUP 20261113_090000 match=1 rolled_back=1 complete=1$" && has "^CP_BACKUP 20261113_100000 match=1 rolled_back=0 complete=1$" && has "^CP_BACKUP 20261113_110000 match=0 rolled_back=0 complete=1$" && has "^CP_RESULT OK$"'
setfiles r2j; run cp8 "$W/cp.sh" rolledback
t "P20 precheck rolledback: 4 файла = r2j -> OK" 'has "^CP_RESULT OK$"'
ln -sf "$H/ros2_ws/src/bumblebee/launch/bumblebee.launch.py" "$W/lnk"; rm "$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py"; ln -s "$W/lnk" "$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py"
run cp9 "$W/cp.sh" install
t "P20 precheck: символьная ссылка на месте файла -> STOP" 'has "^CP_FILE .*bumblebee.launch.py SYMLINK$" && has "^CP_RESULT STOP"'
rm "$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py"; setfiles r2j
t "P20 precheck: только чтение (sudo не вызывался, systemctl только is-active)" '[ ! -e "$FS/sudo.log" ] && ! grep -q -E "systemctl (start|stop|restart|mask|unmask)" "$FS/systemctl.log"'
# ======================= P21: r6_cam_verify.sh =======================
reset_state; rm -rf "$P"/[0-9]*
CAMF="$H/bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py"; mkf "$CAMF" "camera variant"; mkf "$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" "launch variant"
now=$(date +%s); BT=1794000000; echo "btime $BT" > "$P/stat"; ST=$(( (now - BT + 100) * 100 ))
STARTT=$ST mkproc 5001 python3 "$CAMF" --ros-args -r __node:=main_camera_fix -r __ns:=/main_camera --params-file /tmp/launch_params_x
STARTT=$ST mkproc 5002 python3 "$CAMF" --ros-args -r __node:=second_camera_fix -r __ns:=/second_camera
mkproc 5003 bash -c "# BB_R6CV_MARK /lib/bumblebee/camera_fix.py"
cat > "$BB_TEST_LOG" <<EOF2
[INFO] [launch]: All log files can be found below /home/lb/.ros/log/2026-11-13-09-00-00-000000-bumblebee-20ec-1111
[camera_fix.py-5] [INFO 1.0] [main_camera.main_camera_fix]: camera_fix: image_raw_yuv -> image_raw (period=5)
[ERROR] [camera_fix.py-5]: process has died [pid 9, exit code 1]
[INFO] [launch]: All log files can be found below /home/lb/.ros/log/2026-11-13-10-00-00-000000-bumblebee-20ec-4242
[INFO] [camera_fix.py-5]: process started with pid [5001]
[camera_fix.py-5] [INFO 2.0] [main_camera.main_camera_fix]: camera_fix: image_raw_yuv -> image_raw (period=5, full_rows=True, source_pitch=1600)
[camera_fix.py-5] [INFO 2.1] [main_camera.main_camera_fix]: camera_fix: full-row read: 384 sensor rows at pitch 1600 -> 640x480
[INFO] [camera_fix.py-17]: process started with pid [5002]
[camera_fix.py-17] [INFO 9.0] [second_camera.second_camera_fix]: camera_fix: image_raw_yuv -> image_raw (period=5, full_rows=False, source_pitch=1600)
[camera_fix.py-5] [INFO 32.0] [main_camera.main_camera_fix]: camera_fix stats 30s: full-row frames 720, legacy frames 0
[camera_fix.py-17] [INFO 39.0] [second_camera.second_camera_fix]: camera_fix stats 30s: full-row frames 0, legacy frames 715
EOF2
export BB_TEST_PREFIX="$H/bench_ws/r2j/install/bumblebee" BB_TEST_HZ=100
run cv1 "$PI/r6_cam_verify.sh" cam
SH=$(sha256sum "$CAMF" | cut -c1-64)
t "P21 verify: служба (MainPID 4242), префикс, sha launch" 'has "^CV_SERVICE active=active mainpid=4242 nrestarts=0$" && has "^CV_PREFIX $H/bench_ws/r2j/install/bumblebee$" && has "^CV_LAUNCH sha=$(sha256sum "$H/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" | cut -c1-64)$"'
t "P21 verify: два работающих camera_fix найдены через /proc (свой скрипт с меткой BB_R6 отброшен), sha файла, in_prefix=yes, запущены позже изменения файла" '[ "$(grep -c "^CV_PROC " "$O")" = 2 ] && has "^CV_PROC node=main_camera_fix pid=5001 sha=$SH in_prefix=yes" && has "^CV_PROC node=second_camera_fix pid=5002 sha=$SH in_prefix=yes" && ! has "pid=5003" && s=$(grep "^CV_PROC node=main" "$O" | sed -E "s/.*start_epoch=([0-9]+) file_ctime=([0-9]+).*/\1 \2/") && [ "${s% *}" -gt "${s#* }" ]'
t "P21 verify: журнал - только последний запуск (pid 4242 = MainPID), full_rows True/False, read384, stats, 2 запуска, 0 смертей" 'has "^CV_LOG access=ok run_line=4 launch_pid=4242 mainpid=4242 match=yes$" && has "^CV_START main lines=1 full_rows_true=1 full_rows_false=0$" && has "^CV_START second lines=1 full_rows_true=0 full_rows_false=1$" && has "^CV_FULLROW main read384=1 any=1 not_possible=0$" && has "^CV_STATS main full=720 legacy=0$" && has "^CV_STATS second full=0 legacy=715$" && has "^CV_CAMFIX_STARTED 2$" && has "^CV_DIED 0$" && has "^CV_ERRORS 0$"'
echo 9999 > "$FS/units/bumblebee/mainpid"; run cv2 "$PI/r6_cam_verify.sh" cam
t "P21 verify: MainPID не совпал с pid в журнале -> match=no" 'has "match=no$"'
echo 4242 > "$FS/units/bumblebee/mainpid"; rm -rf "$P/5001" "$P/5002"
STARTT=100 mkproc 5001 python3 "$CAMF" --ros-args -r __node:=main_camera_fix
run cv3 "$PI/r6_cam_verify.sh" cam
t "P21 verify: процесс запущен ДО изменения файла -> start_epoch меньше file_ctime" 's=$(grep "^CV_PROC node=main" "$O" | sed -E "s/.*start_epoch=([0-9]+) file_ctime=([0-9]+).*/\1 \2/") && [ "${s% *}" -lt "${s#* }" ]'
chmod 000 "$BB_TEST_LOG"; run cv4 "$PI/r6_cam_verify.sh" cam
if [ "$(id -u)" != 0 ]; then t "P21 verify: журнал не читается -> CV_LOG access=denied" 'has "^CV_LOG access=denied$"'; fi
chmod 644 "$BB_TEST_LOG"
run cv5 "$PI/r6_cam_verify.sh" what
t "P21 verify: неизвестный режим -> CV_STOP" 'has "^CV_STOP"'
t "P21 verify: только чтение (sudo нет, systemctl только show)" '[ ! -e "$FS/sudo.log" ] && ! grep -q -E "systemctl (start|stop|restart|mask|unmask)" "$FS/systemctl.log"'
# ======================= P22: статически по всем pi/r6_*.sh =======================
bad=""
for f in "$PI"/r6_*.sh; do
  if grep -v -E '^\s*#' "$f" | grep -q -E '\bpgrep\b|\bpkill\b|killall'; then bad="$bad ${f##*/}"; fi
done
t "P22 нет pgrep/pkill/killall вне комментариев ни в одном pi/r6_*.sh" '[ -z "$bad" ]'
bad=""
for f in "$PI"/r6_*.sh; do bash -n "$f" || bad="$bad ${f##*/}"; done
t "P22 bash -n проходит у всех pi/r6_*.sh" '[ -z "$bad" ]'
echo ""
echo "ИТОГ r6 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
