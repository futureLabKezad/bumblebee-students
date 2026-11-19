#!/bin/bash
# run_tests_r7_pi.sh (Claude, 13.11.2026, набор r7) - тесты r7 в WSL БЕЗ дрона, без ROS и без sudo. Ничего не пишет вне песочницы.
# M: pi/r7_marker_ids.sh (шаг 25) на поддельном rclpy (tests/pystub_r7, сценарий BB_R7_SCN); настоящий ROS не подключается: «source» заглушён функцией,
#    PYTHONPATH = заглушка, поддельные ros2, sudo, hostname первыми в PATH.
# I: НАСТОЯЩИЕ image_r2j/image_install.sh и image_rollback.sh набора с НАСТОЯЩИМ payload и image_manifest.final.tsv r7 на поддельном корне:
#    с BACKUP_ROOT=TBD (настоящий image_target.conf) оба отказывают до любых изменений; с корнем песочницы - установка 63 файлов и откат до прежнего состояния.
# Запуск (WSL, низкий приоритет, один поток): nice -n 19 ionice -c3 bash tests/run_tests_r7_pi.sh [папка для песочницы, по умолчанию /tmp]
# Итог: строка «ИТОГ r7 Pi: PASS n, FAIL m», код 0 только при FAIL 0.
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r7pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
FB="$W/fakebin"; FS="$W/state"; H="$W/home"; mkdir -p "$FB" "$FS" "$H"
export FS
cat > "$FB/hostname" <<'EOF'
#!/bin/bash
echo "${FAKE_HOST:-bumblebee-20ec}"
EOF
for c in ros2 sudo systemctl; do printf '#!/bin/bash\necho "%s $*" >> "$FS/%s.log"\nexit 0\n' "$c" "$c" > "$FB/$c"; done
chmod +x "$FB"/*
STUB="$KIT/tests/pystub_r7"
SH="$KIT/pi/r7_marker_ids.sh"
O="$W/out.txt"; E="$W/err.txt"; L="$W/stub.log"
# запуск скрипта Pi так, как его запускает ssh (bash -c текст скрипта), с подделками; source заглушён (в WSL стоит настоящий ROS)
runmn() { # runmn <сценарий> <аргументы...>
  local scn="$1"; shift
  rm -f "$O" "$E" "$L"
  ( source(){ :; }; export -f source
    export BB_R7_SCN="$scn" BB_R7_STUBLOG="$L" PYTHONPATH="$STUB" PYTHONDONTWRITEBYTECODE=1 HOME="$H" PATH="$FB:/usr/bin:/bin"
    unset AMENT_PREFIX_PATH ROS_DISTRO RMW_IMPLEMENTATION
    bash -c "$(tr -d '\r' < "$SH")" _ "$@" > "$O" 2> "$E" )
  RC=$?
}
has() { grep -q -E "$1" "$O"; }
treesum() { find "$H" -type f -o -type l | sort | sha256sum; }

# ---------- M: шаг 25, скрипт Pi ----------
t "M0 bash -n r7_marker_ids.sh" 'bash -n "$SH"'
t "M0b встроенный python компилируется" 'sed -n "/^python3 - /,/^PY\$/p" "$SH" | sed "1d;\$d" > "$W/mn.py" && /usr/bin/python3 -m py_compile "$W/mn.py"'
CODE=$(grep -v -E '^[[:space:]]*#' "$SH")
t "M1 первая строка-комментарий ТОЛЬКО ЧТЕНИЕ, проверка hostname первой командой" 'sed -n 2p "$SH" | grep -q "^# ТОЛЬКО ЧТЕНИЕ" && [ "$(grep -v -E "^[[:space:]]*(#|$)" "$SH" | head -1)" = "[ \"\$(hostname)\" = \"bumblebee-20ec\" ] || { echo \"STOP: hostname is \$(hostname), expected bumblebee-20ec\" >&2; exit 1; }" ]'
t "M2 в коде нет sudo, rm, mv, cp, mkdir, tee, touch, chmod, systemctl, reboot, записи в файл" '! printf "%s\n" "$CODE" | grep -q -E "(^|[[:space:];|&(])(sudo|rm|mv|cp|mkdir|tee|touch|chmod|systemctl|reboot|shutdown)[[:space:]]" && [ -z "$(printf "%s\n" "$CODE" | sed -e "s#2>/dev/null##g" -e "s#>&2##g" -e "s#< /dev/null##g" | grep -E "[^-]>[^=]")" ]'
t "M3 в коде нет издателей, клиентов служб, /aruco_detect/wake, ros2 CLI, pgrep/pkill" '! printf "%s\n" "$CODE" | grep -q -E "create_publisher|create_client|wake|ros2 |pgrep|pkill|killall|set_mode|arming|param"'
t "M4 подписки только /mavros/state и /aruco_detect/markers" '[ "$(printf "%s\n" "$CODE" | grep -o -E "create_subscription\([A-Za-z]+, '"'"'[^'"'"']+'"'"'" | sort | tr "\n" " ")" = "create_subscription(MarkerArray, '"'"'/aruco_detect/markers'"'"' create_subscription(State, '"'"'/mavros/state'"'"' " ]'
FAKE_HOST=other-pi; export FAKE_HOST
runmn asleep pre 2 pre
t "M5 чужое имя хоста: код 1, STOP в stderr, в stdout пусто, python не запускался" '[ "$RC" = 1 ] && grep -q "STOP: hostname is other-pi" "$E" && [ ! -s "$O" ] && [ ! -e "$L" ]'
unset FAKE_HOST
for bad in "xx 2 pre" "pre 1 pre" "pre 11 pre" "rec 4 p00cm" "rec 31 p00cm" "rec 10 p0;cm" "rec ten p00cm" "rec 10 "; do
  # shellcheck disable=SC2086
  runmn asleep $bad
  t "M6 плохие аргументы «$bad»: код 4, python не запускался" '[ "$RC" = 4 ] && grep -q "^STOP:" "$E" && [ ! -e "$L" ]'
done
before=$(treesum)
runmn asleep pre 2 pre
t "M7 детектор спит (pre): код 0, MN_STATE connected=True armed=False, MN_DETECTOR camera_subscription=no msgs=0, конец BB_R7MN_DONE rc=0" '[ "$RC" = 0 ] && has "^MN_STATE connected=True armed=False mode=POSCTL$" && has "^MN_DETECTOR label=pre publishers=1 nodes=aruco_detect camera_subscription=no msgs=0 with_markers=0 seconds=2$" && has "^MN_END label=pre msgs=0 with_markers=0 ids=none$" && [ "$(tail -1 "$O")" = "BB_R7MN_DONE rc=0" ] && ! has "^MN_MSG"'
t "M8 заглушка, а не настоящий rclpy: узел bb_r7_marker_ids, подписки 2, издателей 0, shutdown" 'grep -q "^STUB rclpy imported$" "$L" && grep -q "^NODE bb_r7_marker_ids$" "$L" && [ "$(grep -c "^SUB " "$L")" = 2 ] && ! grep -q -E "^(PUB|CLIENT)" "$L" && grep -q "^SHUTDOWN$" "$L"'
t "M9 ros2, sudo, systemctl не вызывались; в HOME ничего не появилось" '[ ! -e "$FS/ros2.log" ] && [ ! -e "$FS/sudo.log" ] && [ ! -e "$FS/systemctl.log" ] && [ "$(treesum)" = "$before" ]'
runmn armed pre 2 pre
t "M10 дрон взведён: код 3, MN_REFUSED armed, окна записи не было" '[ "$RC" = 3 ] && has "^MN_REFUSED armed " && ! has "^MN_DETECTOR" && [ "$(tail -1 "$O")" = "BB_R7MN_DONE rc=3" ]'
runmn noconn rec 5 p00cm
t "M11 нет связи с FCU: код 3, MN_REFUSED fcu_not_connected" '[ "$RC" = 3 ] && has "^MN_REFUSED fcu_not_connected " && ! has "^MN_MSG"'
runmn nostate pre 2 pre
t "M12 /mavros/state молчит 8 с: код 3, MN_REFUSED no_mavros_state" '[ "$RC" = 3 ] && has "^MN_REFUSED no_mavros_state "'
runmn awake_ok rec 5 p05cm
n=$(grep -c "^MN_MSG " "$O")
t "M13 детектор не спит, запись 5 с: строки MN_MSG с номером и 4 углами, MN_END считает их, номера только 0" '[ "$RC" = 0 ] && [ "$n" -ge 20 ] && has "^MN_MSG t=[0-9]+\.[0-9]{3} n=1 id=0 c=466\.0,399\.0;239\.0,402\.0;237\.0,109\.0;464\.0,104\.0$" && has "^MN_MSG t=[0-9.]+ n=0$" && has "^MN_END label=p05cm msgs=$n with_markers=[0-9]+ ids=0:[0-9]+$" && has "camera_subscription=yes msgs=$n "'
runmn awake_false rec 5 p10cm
t "M14 ложный номер 38 в записи: MN_MSG id=38 и в MN_END ids=0:..,38:.." '[ "$RC" = 0 ] && has "^MN_MSG t=[0-9.]+ n=1 id=38 c=" && has "^MN_END label=p10cm msgs=[0-9]+ with_markers=[0-9]+ ids=0:[0-9]+,38:[0-9]+$"'
runmn awake_ok pre 2 pre
t "M15 pre при работающем детекторе: строк MN_MSG нет, msgs > 0, camera_subscription=yes" '[ "$RC" = 0 ] && ! has "^MN_MSG" && has "^MN_DETECTOR label=pre publishers=1 nodes=aruco_detect camera_subscription=yes msgs=[1-9][0-9]* "'
runmn armed_during rec 5 p15cm
t "M16 дрон взвели во время записи: код 3, MN_REFUSED armed_during, MN_END нет" '[ "$RC" = 3 ] && has "^MN_REFUSED armed_during " && ! has "^MN_END"'
runmn awake_nomsg pre 2 pre
t "M17 подписка детектора на камеру есть, а сообщений нет: msgs=0 (на ПК это НЕ ПРОВЕРЕНО)" '[ "$RC" = 0 ] && has "camera_subscription=yes msgs=0 "'
mkdir -p "$W/nomsgstub/rclpy" "$W/nomsgstub/mavros_msgs"; cp "$STUB"/rclpy/*.py "$W/nomsgstub/rclpy/"; cp "$STUB"/mavros_msgs/*.py "$W/nomsgstub/mavros_msgs/"
rm -f "$O" "$E"
( source(){ :; }; export -f source; export BB_R7_SCN=awake_ok PYTHONPATH="$W/nomsgstub" PYTHONDONTWRITEBYTECODE=1 HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$(tr -d '\r' < "$SH")" _ pre 2 pre > "$O" 2> "$E" ); RC=$?
t "M18 нет aruco_pose.msg: код 4, MN_ERROR markers_import_failed" '[ "$RC" = 4 ] && has "^MN_ERROR markers_import_failed" && [ "$(tail -1 "$O")" = "BB_R7MN_DONE rc=4" ]'
# M19 (r7 13.11 ~05:40): окружение ROS как у стека (как ros_env r6): из ~/start_bumblebee.sh исполняются только 4 известные строки source, посторонняя - нет.
# Отдельный HOME (H2), source подменён функцией, которая только пишет, что ей дали; настоящие файлы ROS не читаются.
H2="$W/home_m19"; mkdir -p "$H2/ros2_ws/install" "$H2/bench_ws/r2j/install"
printf 'source /opt/ros/jazzy/setup.bash\nsource /home/lb/ros2_ws/install/setup.bash\nsource /home/lb/evil_r7.sh\nsource /home/lb/bench_ws/r2j/install/local_setup.bash\n' > "$H2/start_bumblebee.sh"
: > "$H2/ros2_ws/install/setup.bash"; : > "$H2/bench_ws/r2j/install/local_setup.bash"; : > "$H2/evil_r7.sh"
SL="$W/src_m19.log"; : > "$SL"
( source(){ echo "SRC $1" >> "$SL"; }; export -f source; export SL BB_R7_SCN=asleep BB_R7_STUBLOG="$W/stub_m19.log" PYTHONPATH="$STUB" PYTHONDONTWRITEBYTECODE=1 HOME="$H2" PATH="$FB:/usr/bin:/bin"
  unset AMENT_PREFIX_PATH ROS_DISTRO RMW_IMPLEMENTATION; bash -c "$(tr -d '\r' < "$SH")" _ pre 2 pre > "$W/out_m19.txt" 2> "$W/err_m19.txt" ); RC=$?
t "M19 окружение как у стека: source профиля, jazzy и из start_bumblebee.sh только ros2_ws/install/setup.bash и bench_ws/r2j (известные строки), посторонняя строка не исполняется" '[ "$RC" = 0 ] && [ "$(tr "\n" "|" < "$SL")" = "SRC /etc/profile.d/bumblebee-ros.sh|SRC /opt/ros/jazzy/setup.bash|SRC $H2/ros2_ws/install/setup.bash|SRC $H2/bench_ws/r2j/install/local_setup.bash|" ] && ! grep -q evil "$SL" && grep -q "^MN_DETECTOR " "$W/out_m19.txt"'

# ---------- I: payload r7 на настоящих image_install.sh и image_rollback.sh ----------
IK="$KIT/image_r2j"
UP="$W/up"; mkdir -p "$UP"
cp -r "$IK/payload" "$UP/payload"; cp "$IK/image_manifest.final.tsv" "$IK/image_target.conf" "$UP/"
export PATH="$FB:$PATH"
o=$(bash "$IK/image_install.sh" "$UP" 2>&1); rc=$?
t "I1 настоящий image_target.conf (BACKUP_ROOT=TBD): image_install.sh отказывает до любых изменений (код 1, STOP TBD)" '[ "$rc" = 1 ] && printf "%s" "$o" | grep -q "=== STOP: DEST_ROOT or BACKUP_ROOT is TBD" && ! printf "%s" "$o" | grep -q "backup"'
o=$(bash "$IK/image_rollback.sh" "$UP" 2>&1); rc=$?
t "I2 настоящий image_target.conf (TBD): image_rollback.sh (06) отказывает до любых изменений (код 1, STOP TBD)" '[ "$rc" = 1 ] && printf "%s" "$o" | grep -q "=== STOP: DEST_ROOT or BACKUP_ROOT is TBD"'
o=$(bash "$IK/image_rollback.sh" "$UP" 20261113_100000 2>&1); rc=$?
t "I2b то же с явной меткой резерва: отказ TBD" '[ "$rc" = 1 ] && printf "%s" "$o" | grep -q "=== STOP: DEST_ROOT or BACKUP_ROOT is TBD"'
D="$W/dest"; B="$W/bak"; mkdir -p "$D"
printf 'DEST_ROOT=%s\nBACKUP_ROOT=%s\n' "$D" "$B" > "$UP/image_target.conf"
# «дрон» до установки: прежние версии файлов, которые r2j меняет, и камера по умолчанию; новых файлов нет; исправленный fcu_detect.py на месте
nold=0
while IFS=$'\t' read -r p s why src; do
  case "$p" in ''|'#'*) continue;; esac
  # v2: drone1211-changed - файл на дроне есть, но не r2j (копия 12.11); drone1211-absent (qos_relay.py) - на дроне его нет
  case "$why" in changed*|camera*|drone1211-changed*) mkdir -p "$D/$(dirname "$p")"; printf 'old %s\n' "$p" > "$D/$p"; chmod 644 "$D/$p"; nold=$((nold+1));; esac
done < "$IK/PAYLOAD_SOURCES_r2j.tsv"
mkdir -p "$D/ros2_ws/src/bumblebee/scripts"; printf 'fixed fcu 5932a00a\n' > "$D/ros2_ws/src/bumblebee/scripts/fcu_detect.py"
pre=$(cd "$D" && find . -type f | sort | xargs sha256sum)
nman=$(grep -c -v -E '^(#|[[:space:]]*$)' "$IK/image_manifest.final.tsv")
o=$(bash "$IK/image_install.sh" "$UP" 2>&1); rc=$?
t "I3 установка r7 на поддельный корень: код 0, BB_IMAGE_INSTALL_DONE files=68, в резерве $nold прежних и $((nman-nold)) новых" '[ "$rc" = 0 ] && [ "$nman" = 68 ] && [ "$nold" = 18 ] && printf "%s" "$o" | grep -q -E "^BB_IMAGE_INSTALL_DONE [0-9]{8}_[0-9]{6} files=68$" && printf "%s" "$o" | grep -q ": 18 old files, 50 new files$"'
bad=0
while IFS=$'\t' read -r p s; do case "$p" in ''|'#'*) continue;; esac; [ "$(sha256sum "$D/$p" | cut -c1-64)" = "$s" ] || bad=$((bad+1)); done < "$IK/image_manifest.final.tsv"
t "I4 после установки все 68 файлов на месте с sha256 манифеста" '[ "$bad" = 0 ]'
t "I5 исправленный fcu_detect.py на «дроне» не тронут, hover r6 и flight.py r2j стоят" '[ "$(cat "$D/ros2_ws/src/bumblebee/scripts/fcu_detect.py")" = "fixed fcu 5932a00a" ] && [ "$(sha256sum "$D/ros2_ws/src/bumblebee/examples/hover_marker0.py" | cut -c1-64)" = a11b195ce1507607967ff6a7402726d9eef7b4f12850a9e864f5ae27d1f513f7 ] && [ "$(sha256sum "$D/ros2_ws/src/bumblebee/examples/flight/flight.py" | cut -c1-64)" = b69cc5e72509bbe2f141e48844b999e3a046ac6a78d28484239536b426c807b3 ]'
o=$(bash "$IK/image_rollback.sh" "$UP" 2>&1); rc=$?
post=$(cd "$D" && find . -type f | sort | xargs sha256sum)
t "I6 откат (06 без метки): код 0, restored=18 moved_aside=50, «дрон» байт в байт как до установки" '[ "$rc" = 0 ] && printf "%s" "$o" | grep -q -E "^BB_IMAGE_ROLLBACK_DONE [0-9]{8}_[0-9]{6} restored=18 moved_aside=50 " && [ "$pre" = "$post" ]'
echo "ИТОГ r7 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
