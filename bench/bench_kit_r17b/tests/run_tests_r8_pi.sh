#!/bin/bash
# run_tests_r8_pi.sh (Claude, 13.11.2026, набор r8) - тесты r8 в WSL БЕЗ дрона, без ROS и без sudo. Ничего не пишет вне песочницы.
# P: pi/r8_marker_wake.sh (шаг 25 r8) на поддельном rclpy (tests/pystub_r8, сценарий BB_R8_SCN); настоящий ROS не подключается: «source» заглушён функцией,
#    PYTHONPATH = заглушка, поддельные ros2, sudo, systemctl, hostname первыми в PATH; журнал стека - файл песочницы (BB_TEST_LOG), карта - папка песочницы (BB_R8_SHARE).
#    Проверяется: wake только после проверки /mavros/state и только во время окна, единственная публикация - wake, номера/центры/углы, позы, RESEEDED из журнала с нужного байта.
# Запуск (WSL, низкий приоритет, один поток): nice -n 19 ionice -c3 bash tests/run_tests_r8_pi.sh [папка для песочницы, по умолчанию /tmp]
# Итог: строка «ИТОГ r8 Pi: PASS n, FAIL m», код 0 только при FAIL 0.
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r8pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
FB="$W/fakebin"; FS="$W/state"; H="$W/home"; mkdir -p "$FB" "$FS" "$H"
export FS
printf '#!/bin/bash\necho "${FAKE_HOST:-bumblebee-20ec}"\n' > "$FB/hostname"
for c in ros2 sudo systemctl; do printf '#!/bin/bash\necho "%s $*" >> "$FS/%s.log"\nexit 0\n' "$c" "$c" > "$FB/$c"; done
chmod +x "$FB"/*
STUB="$KIT/tests/pystub_r8"
SH="$KIT/pi/r8_marker_wake.sh"
O="$W/out.txt"; E="$W/err.txt"; L="$W/stub.log"
# карта песочницы: тот же вид, что map.txt поля 20EC (номера 0-20 без 17, метка 0 в 0,0,-0.32)
SHARE="$W/share"; mkdir -p "$SHARE/aruco_pose/map"
{ printf '# id\tlength\tx\ty\tz\trot_z\trot_y\trot_x\n'; printf '0\t0.190\t0.000\t0.000\t-0.320\t1.571\t0.000\t0.000\n'
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 18 19 20; do printf '%s\t0.290\t0.%03d\t0.730\t-0.320\t1.571\t0.000\t0.000\n' "$i" "$i"; done; } > "$SHARE/aruco_pose/map/map.txt"
MAPSHA=$(sha256sum "$SHARE/aruco_pose/map/map.txt" | cut -c1-64)
LOGF="$W/bumblebee.log"
printf '[launch]: All log files can be found below /home/lb/.ros/log/x\n[vpe_fix.py-7] [WARN] [1.0] [vpe_fix]: vpe_fix: gate RESEEDED (z-jump) age=9.99s new_xyz=(3.400,0.000,-0.220)\n' > "$LOGF"
LOG0=$(stat -c %s "$LOGF")
# запуск скрипта Pi так, как его запускает ssh (bash -c текст скрипта), с подделками; source заглушён (в WSL стоит настоящий ROS)
runw() { # runw <сценарий> <аргументы...>; окружение сценария - в переменных XP (поза), XR (RESEEDED), XL (журнал), XS (share)
  local scn="$1"; shift
  rm -f "$O" "$E" "$L"
  ( source(){ :; }; export -f source
    export BB_R8_SCN="$scn" BB_R8_STUBLOG="$L" PYTHONPATH="$STUB" PYTHONDONTWRITEBYTECODE=1 HOME="$H" PATH="$FB:/usr/bin:/bin"
    export BB_R8_POSE="${XP:-0,0}" BB_TEST_LOG="${XL:-$LOGF}" BB_R8_SHARE="${XS-$SHARE}"
    [ -n "${XR:-}" ] && export BB_R8_RESEED="$XR"
    unset AMENT_PREFIX_PATH ROS_DISTRO RMW_IMPLEMENTATION
    bash -c "$(tr -d '\r' < "$SH")" _ "$@" > "$O" 2> "$E" )
  RC=$?
}
has() { grep -q -E "$1" "$O"; }
treesum() { find "$H" -type f -o -type l | sort | sha256sum; }

# ---------- P: шаг 25 r8, скрипт Pi ----------
t "P0 bash -n r8_marker_wake.sh" 'bash -n "$SH"'
t "P0b встроенный python компилируется" 'sed -n "/^python3 - /,/^PY\$/p" "$SH" | sed "1d;\$d" > "$W/w8.py" && /usr/bin/python3 -m py_compile "$W/w8.py"'
CODE=$(grep -v -E '^[[:space:]]*#' "$SH")
t "P1 первая строка-комментарий «МЕНЯЕТ ДРОН временно», проверка hostname первой командой" 'sed -n 2p "$SH" | grep -q "^# МЕНЯЕТ ДРОН временно" && [ "$(grep -v -E "^[[:space:]]*(#|$)" "$SH" | head -1)" = "[ \"\$(hostname)\" = \"bumblebee-20ec\" ] || { echo \"STOP: hostname is \$(hostname), expected bumblebee-20ec\" >&2; exit 1; }" ]'
t "P2 в коде нет sudo, rm, mv, cp, mkdir, tee, touch, chmod, systemctl, reboot, записи в файл; python открывает файлы только на чтение" '! printf "%s\n" "$CODE" | grep -q -E "(^|[[:space:];|&(])(sudo|rm|mv|cp|mkdir|tee|touch|chmod|systemctl|reboot|shutdown)[[:space:]]" && [ -z "$(printf "%s\n" "$CODE" | sed -e "/^python3 - /,/^PY\$/d" -e "s#2>/dev/null##g" -e "s#>&2##g" -e "s#< /dev/null##g" | grep -E "[^-]>[^=]")" ] && ! printf "%s\n" "$CODE" | grep -q -E "open\([^)]*, *.(w|a|r\+|x)" && [ "$(printf "%s\n" "$CODE" | grep -c -E "open\(")" = 2 ]'
t "P3 единственный издатель - Bool в /aruco_detect/wake; нет клиентов служб, ros2 CLI, set_mode, arming, записи параметров" '[ "$(printf "%s\n" "$CODE" | grep -c "create_publisher")" = 1 ] && printf "%s\n" "$CODE" | grep -q "create_publisher(M\[.Bool.\], ./aruco_detect/wake." && ! printf "%s\n" "$CODE" | grep -q -E "create_client|ros2 |set_mode|SetMode|arming|CommandBool|ParamSet|param set|/mavros/cmd|setpoint"'
t "P3b нет pgrep, pkill, killall" '! printf "%s\n" "$CODE" | grep -q -E "pgrep|pkill|killall"'
t "P4 подписки ровно 4: /mavros/state, /aruco_detect/markers, /aruco_map/pose, /mavros/local_position/pose" '[ "$(printf "%s\n" "$CODE" | grep -o -E "create_subscription\([^,]+, '"'"'[^'"'"']+'"'"'" | sed -E "s/.*'"'"'([^'"'"']+)'"'"'/\1/" | sort | tr "\n" " ")" = "/aruco_detect/markers /aruco_map/pose /mavros/local_position/pose /mavros/state " ]'
t "P4b wake создаётся только после всех отказов по /mavros/state (в тексте издатель ниже последнего MN_REFUSED armed)" '[ "$(grep -n "create_publisher" "$SH" | cut -d: -f1)" -gt "$(grep -n "MN_REFUSED armed (" "$SH" | cut -d: -f1)" ] && [ "$(grep -n "create_publisher" "$SH" | cut -d: -f1)" -gt "$(grep -n "MN_REFUSED fcu_not_connected" "$SH" | cut -d: -f1)" ]'
FAKE_HOST=other-pi; export FAKE_HOST
runw r2j_ok pre 4 pre start
t "P5 чужое имя хоста: код 1, STOP в stderr, в stdout пусто, python не запускался" '[ "$RC" = 1 ] && grep -q "STOP: hostname is other-pi" "$E" && [ ! -s "$O" ] && [ ! -e "$L" ]'
unset FAKE_HOST
for bad in "xx 4 pre start" "pre 3 pre start" "pre 11 pre start" "rec 4 p00cm start" "rec 31 p00cm start" "rec 10 p0;cm start" "rec ten p00cm start" "rec 10 p00cm" "rec 10 p00cm -5" "rec 10 p00cm 12a" "rec 10 p00cm 1234567890123456"; do
  # shellcheck disable=SC2086
  runw r2j_ok $bad
  t "P6 плохие аргументы «$bad»: код 4, python не запускался" '[ "$RC" = 4 ] && grep -q "^STOP:" "$E" && [ ! -e "$L" ]'
done
before=$(treesum)
runw noconn pre 4 pre start
t "P7 нет связи с FCU: код 3, MN_REFUSED fcu_not_connected, издателя wake нет, публикаций нет" '[ "$RC" = 3 ] && has "^MN_REFUSED fcu_not_connected " && ! grep -q -E "^(PUB|PUBLISH|TIMER)" "$L" && ! has "^MN_WAKE" && [ "$(tail -1 "$O")" = "BB_R8MN_DONE rc=3" ]'
runw armed rec 5 p00cm start
t "P8 дрон взведён: код 3, MN_REFUSED armed, wake не посылался" '[ "$RC" = 3 ] && has "^MN_REFUSED armed " && ! grep -q -E "^(PUB|PUBLISH|TIMER)" "$L" && ! has "^MN_MSG|^MN_END"'
runw nostate pre 4 pre start
t "P9 /mavros/state молчит 8 с: код 3, MN_REFUSED no_mavros_state, wake не посылался" '[ "$RC" = 3 ] && has "^MN_REFUSED no_mavros_state " && ! grep -q -E "^(PUB|PUBLISH)" "$L"'
XP="0,-0.05" runw r2j_ok rec 5 p05cm "$LOG0"
n=$(grep -c "^MN_MSG " "$O"); np=$(grep -c "^MN_POSE " "$O"); nw=$(grep -c "^PUBLISH /aruco_detect/wake data=True$" "$L")
t "P10 r2j, запись 5 с: MN_MSG с номером, центром и 4 углами; MN_END считает их; номера только 0" '[ "$RC" = 0 ] && [ "$n" -ge 20 ] && has "^MN_MSG t=[0-9]+\.[0-9]{3} n=1 id=0 ctr=351\.5,253\.5 c=466\.0,399\.0;239\.0,402\.0;237\.0,109\.0;464\.0,104\.0$" && has "^MN_MSG t=[0-9.]+ n=0$" && has "^MN_END label=p05cm msgs=$n with_markers=[0-9]+ ids=0:[0-9]+ poses=$np$"'
t "P11 позы /aruco_map/pose: x, y, z, yaw; MN_DETECTOR poses=; EKF - сведения" '[ "$np" -ge 5 ] && has "^MN_POSE t=[0-9.]+ x=0\.000 y=-0\.050 z=-0\.220 yaw=1\.571$" && has "^MN_DETECTOR label=p05cm publishers=1 nodes=aruco_detect camera_subscription=yes msgs=$n with_markers=[0-9]+ poses=$np seconds=5$" && has "^MN_EKF n=[1-9][0-9]* x=0\.010 y=0\.000 z=-0\.010 "'
t "P12 wake: издатель один, первый сигнал сразу, потом 1 Гц (2 с разгона + 5 с окна = 7-9 сигналов), таймер остановлен до конца; MN_WAKE sent= совпадает" '[ "$(grep -c "^PUB /aruco_detect/wake$" "$L")" = 1 ] && [ "$nw" -ge 7 ] && [ "$nw" -le 9 ] && grep -q "^DESTROY_TIMER$" "$L" && [ "$(grep -n "^DESTROY_TIMER$" "$L" | cut -d: -f1)" -lt "$(grep -n "^SHUTDOWN$" "$L" | cut -d: -f1)" ] && has "^MN_WAKE sent=$nw topic=/aruco_detect/wake hz=1 warmup_s=2$"'
t "P13 карта: путь share/aruco_pose/map/map.txt, sha256, номера 0-20 без 17, метка 0 в 0,0,-0.32" 'has "^MN_MAP file=$SHARE/aruco_pose/map/map.txt sha256=$MAPSHA ids=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,18,19,20 m0=0\.000,0\.000,-0\.320$"'
t "P14 журнал стека с байта $LOG0: старая строка RESEEDED (до окна) не попала, reseeded=0" 'has "^MN_LOG file=$LOGF readable=yes from=$LOG0 to=$LOG0 rotated=no cut=no lines=0 reseeded=0 deferred=0 rejected=0$" && ! has "^MN_RESEED"'
t "P15 ros2, sudo, systemctl не вызывались; в HOME ничего не появилось; журнал стека не изменён" '[ ! -e "$FS/ros2.log" ] && [ ! -e "$FS/sudo.log" ] && [ ! -e "$FS/systemctl.log" ] && [ "$(treesum)" = "$before" ] && [ "$(stat -c %s "$LOGF")" = "$LOG0" ]'
runw rc3 pre 4 pre start
t "P16 rc3 (детектор не слушает wake): wake посылался, но msgs=0, camera_subscription=no, код 0 (на ПК это НЕ ПРОВЕРЕНО)" '[ "$RC" = 0 ] && grep -q "^PUBLISH /aruco_detect/wake data=True$" "$L" && has "^MN_DETECTOR label=pre publishers=1 nodes=aruco_detect camera_subscription=no msgs=0 with_markers=0 poses=0 seconds=4$" && has "^MN_END label=pre msgs=0 with_markers=0 ids=none poses=0$"'
runw armed_during rec 5 p10cm start
t "P17 дрон взвели во время записи: код 3, MN_WAKE, потом MN_REFUSED armed_during, таймер wake остановлен, MN_END нет" '[ "$RC" = 3 ] && has "^MN_WAKE sent=" && has "^MN_REFUSED armed_during " && grep -q "^DESTROY_TIMER$" "$L" && ! has "^MN_END"'
cp "$LOGF" "$W/log_r.txt"
XL="$W/log_r.txt" XR="0.400,0.000,-0.220" runw r2j_ok pre 4 pre start
t "P18 RESEEDED во время окна (vpe_fix дописал строку): MN_RESEED reason=xy-jump x=0.400 y=0.000 z=-0.220, reseeded=1, старая строка не попала" '[ "$RC" = 0 ] && has "^MN_RESEED reason=xy-jump x=0\.400 y=0\.000 z=-0\.220 line=\[vpe_fix\.py-7\]" && has "^MN_LOG file=$W/log_r.txt readable=yes from=$LOG0 to=[0-9]+ rotated=no cut=no lines=1 reseeded=1 " && [ "$(grep -c "^MN_RESEED" "$O")" = 1 ]'
XL="$W/log_r.txt" runw r2j_ok pre 4 pre 0
t "P19 чтение журнала с байта 0: видны обе строки RESEEDED (старая 3.400 и новая 0.400)" '[ "$RC" = 0 ] && has "^MN_RESEED reason=z-jump x=3\.400 y=0\.000 z=-0\.220 " && has "^MN_RESEED reason=xy-jump x=0\.400 " && has " reseeded=2 "'
XL="$W/log_r.txt" runw r2j_ok pre 4 pre 99999999
t "P20 байт больше размера журнала (файл начат заново): rotated=yes, чтение с начала" 'has "^MN_LOG file=$W/log_r.txt readable=yes from=99999999 to=[0-9]+ rotated=yes " && has " reseeded=2 "'
XL="$W/no_such_log.txt" runw r2j_ok pre 4 pre start
t "P21 журнала нет: MN_LOG readable=no (на ПК это НЕ ПРОВЕРЕНО), запись идёт" '[ "$RC" = 0 ] && has "^MN_LOG file=$W/no_such_log.txt readable=no " && has "^MN_END "'
XS="" runw r2j_ok pre 4 pre start
t "P22 пакета aruco_pose нет: MN_MAP error=share_not_found_..." '[ "$RC" = 0 ] && has "^MN_MAP error=share_not_found_PackageNotFoundError$"'
XS="$W/empty_share" runw r2j_ok pre 4 pre start
t "P23 файла карты нет: MN_MAP error=unreadable_FileNotFoundError" 'has "^MN_MAP error=unreadable_FileNotFoundError file=$W/empty_share/aruco_pose/map/map.txt$"'
runw false5 rec 5 p10cm start
t "P24 ложный номер 5 (с карты): MN_MSG id=5 с центром и в MN_END ids=0:..,5:.." '[ "$RC" = 0 ] && has "^MN_MSG t=[0-9.]+ n=1 id=5 ctr=" && has "^MN_END label=p10cm msgs=[0-9]+ with_markers=[0-9]+ ids=0:[0-9]+,5:[0-9]+ poses=[0-9]+$"'
mkdir -p "$W/nomsgstub"; cp -r "$STUB/rclpy" "$STUB/mavros_msgs" "$STUB/std_msgs" "$STUB/geometry_msgs" "$STUB/ament_index_python" "$W/nomsgstub/"
rm -f "$O" "$E"
( source(){ :; }; export -f source; export BB_R8_SCN=r2j_ok PYTHONPATH="$W/nomsgstub" PYTHONDONTWRITEBYTECODE=1 HOME="$H" PATH="$FB:/usr/bin:/bin" BB_TEST_LOG="$LOGF" BB_R8_SHARE="$SHARE"; bash -c "$(tr -d '\r' < "$SH")" _ pre 4 pre start > "$O" 2> "$E" ); RC=$?
t "P25 нет aruco_pose.msg: код 4, MN_ERROR markers_import_failed, wake не посылался" '[ "$RC" = 4 ] && has "^MN_ERROR markers_import_failed" && [ "$(tail -1 "$O")" = "BB_R8MN_DONE rc=4" ] && ! has "^MN_WAKE"'
# P26: окружение ROS как у стека (как M19 r7): из ~/start_bumblebee.sh исполняются только 4 известные строки source, посторонняя - нет
H2="$W/home_p26"; mkdir -p "$H2/ros2_ws/install" "$H2/bench_ws/r2j/install"
printf 'source /opt/ros/jazzy/setup.bash\nsource /home/lb/ros2_ws/install/setup.bash\nsource /home/lb/evil_r8.sh\nsource /home/lb/bench_ws/r2j/install/local_setup.bash\n' > "$H2/start_bumblebee.sh"
: > "$H2/ros2_ws/install/setup.bash"; : > "$H2/bench_ws/r2j/install/local_setup.bash"; : > "$H2/evil_r8.sh"
SL="$W/src_p26.log"; : > "$SL"
( source(){ echo "SRC $1" >> "$SL"; }; export -f source; export SL BB_R8_SCN=noconn BB_R8_STUBLOG="$W/stub_p26.log" PYTHONPATH="$STUB" PYTHONDONTWRITEBYTECODE=1 HOME="$H2" PATH="$FB:/usr/bin:/bin" BB_TEST_LOG="$LOGF" BB_R8_SHARE="$SHARE"
  unset AMENT_PREFIX_PATH ROS_DISTRO RMW_IMPLEMENTATION; bash -c "$(tr -d '\r' < "$SH")" _ pre 4 pre start > "$W/out_p26.txt" 2> "$W/err_p26.txt" ); RC=$?
t "P26 окружение как у стека: source профиля, jazzy и из start_bumblebee.sh только известные строки, посторонняя не исполняется" '[ "$RC" = 3 ] && [ "$(tr "\n" "|" < "$SL")" = "SRC /etc/profile.d/bumblebee-ros.sh|SRC /opt/ros/jazzy/setup.bash|SRC $H2/ros2_ws/install/setup.bash|SRC $H2/bench_ws/r2j/install/local_setup.bash|" ]'
echo "ИТОГ r8 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
