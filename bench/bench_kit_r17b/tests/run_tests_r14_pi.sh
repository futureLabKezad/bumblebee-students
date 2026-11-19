#!/bin/bash
# run_tests_r14_pi.sh (Claude, 17.11.2026, набор r14) - тесты r14 в WSL БЕЗ дрона и без sudo. Пишет только в свою песочницу.
# Q: pi/install_check.sh (09) и pi/overlay_fingerprint.sh (15): второе sha допускается и подписывается ПО ИМЕНИ узла / ПУТИ: aruco_detect.py - POSEFIX_JD2 (r13),
#    camera_fix.py - R2M_CAM, LAUNCH launch/bumblebee.launch.py - R2M_CAM; у всех других узлов и строк RT принимается только первое sha (r2j), даже если ПК прислал два.
# Синтетические файлы (не настоящие узлы): A/J - aruco r2j/jd2, C/M - camera_fix r2j/r2m_cam, V/X - vpe_fix r2j/чужой, B/BM - bumblebee.launch r2j/r2m_cam, R/RX - aruco.launch r2j/чужой, F - fcu.
# Запуск (WSL, низкий приоритет): nice -n 19 ionice -c3 bash tests/run_tests_r14_pi.sh [папка для песочницы, по умолчанию /tmp]. Итог: «ИТОГ r14 Pi: PASS n, FAIL m».
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r14pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
IC="$KIT/pi/install_check.sh"; FP="$KIT/pi/overlay_fingerprint.sh"
sha() { sha256sum "$1" | cut -c1-64; }
FB="$W/fakebin"; H="$W/home"; mkdir -p "$FB" "$H"
printf '#!/bin/bash\necho "${FAKE_HOST:-bumblebee-20ec}"\n' > "$FB/hostname"
printf '#!/bin/bash\nif [ "$1 $2 $3" = "pkg prefix bumblebee" ]; then echo "$HOME/ros2_ws/install/bumblebee"; exit 0; fi\nexit 1\n' > "$FB/ros2"
chmod +x "$FB"/*
t "Q0 bash -n install_check.sh и overlay_fingerprint.sh" 'bash -n "$IC" && bash -n "$FP"'
CODE=$(cat "$IC" "$FP" | grep -v -E '^[[:space:]]*#')
t "Q0b в коде обоих скриптов нет sudo, rm, mv, cp, tee, mkdir, touch, chmod, reboot, systemctl и перенаправления в файл (только чтение, как в r13)" '! printf "%s\n" "$CODE" | grep -q -E "(^|[[:space:];|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|reboot|systemctl)[[:space:]]" && ! printf "%s\n" "$CODE" | sed -e "s#2>&1##g; s#> */dev/null##g; s#>&2##g; s#< */dev/null##g; s#<<<##g; s#<<##g" | grep -q ">"'
CASEN='case "$name" in aruco_detect.py) w="$want"; lab=" POSEFIX_JD2";; camera_fix.py) w="$want"; lab=" R2M_CAM";; *) w="${want%%,*}"; lab="";; esac'
CASER='case "$kind $path" in "LAUNCH launch/bumblebee.launch.py") w="$want"; lab=" R2M_CAM";; *) w="${want%%,*}"; lab="";; esac'
t "Q0c в обоих скриптах метка второго sha - по имени узла (по одной строке case) и по пути launch (по одной строке case); фиксированных меток «любой второй sha» в узлах и RT нет; shamatch одна и выше цикла узлов" '[ "$(grep -c -F "$CASEN" "$IC")" = 1 ] && [ "$(grep -c -F "$CASEN" "$FP")" = 1 ] && [ "$(grep -c -F "$CASER" "$IC")" = 1 ] && [ "$(grep -c -F "$CASER" "$FP")" = 1 ] && ! grep -q "|| vmark=\" POSEFIX_JD2\"" "$IC" "$FP" && [ "$(grep -c "^shamatch() {" "$IC")" = 1 ] && [ "$(grep -c "^shamatch() {" "$FP")" = 1 ] && [ "$(grep -n "^shamatch() {" "$IC" | cut -d: -f1)" -lt "$(grep -n "while read -r want name; do" "$IC" | head -1 | cut -d: -f1)" ]'
mkdir -p "$W/v"
for x in A J C M V X B BM R RX F; do echo "синтетический файл $x" > "$W/v/$x"; done
S() { sha "$W/v/$1"; }
SA=$(S A); SJ=$(S J); SC=$(S C); SM=$(S M); SV=$(S V); SX=$(S X); SB=$(S B); SBM=$(S BM); SR=$(S R); SRX=$(S RX); SF=$(S F)
L_ALT="$SA,$SJ  aruco_detect.py
$SC,$SM  camera_fix.py
$SV  vpe_fix.py"
RT_ALT="$SB,$SBM  LAUNCH  launch/bumblebee.launch.py
$SR  LAUNCH  launch/aruco.launch.py
$SF  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"
gen() { # gen <шаблон> <LIST> <RT>
  printf '%s\n' "$2" > "$W/l.txt"; printf '%s\n' "$3" > "$W/r.txt"
  tr -d '\r' < "$1" | awk -v lf="$W/l.txt" -v rf="$W/r.txt" '{ if ($0=="#@@LIST@@") { while ((getline l < lf) > 0) print l; close(lf) } else if ($0=="#@@RT@@") { while ((getline l < rf) > 0) print l; close(rf) } else if ($0=="#@@BINS@@" || $0=="#@@CPP@@") print "# пусто"; else print }'
}
put() { # put <aruco> <camera> <vpe> <bumblebee.launch> <aruco.launch>
  for t9 in "$H/ros2_ws/install/bumblebee" "$H/bench_ws/r2j/install/bumblebee"; do
    mkdir -p "$t9/lib/bumblebee" "$t9/share/bumblebee/launch"
    cp "$W/v/$1" "$t9/lib/bumblebee/aruco_detect.py"; cp "$W/v/$2" "$t9/lib/bumblebee/camera_fix.py"; cp "$W/v/$3" "$t9/lib/bumblebee/vpe_fix.py"
    cp "$W/v/$4" "$t9/share/bumblebee/launch/bumblebee.launch.py"; cp "$W/v/$5" "$t9/share/bumblebee/launch/aruco.launch.py"
  done
  mkdir -p "$H/ros2_ws/src/bumblebee/scripts"; cp "$W/v/F" "$H/ros2_ws/src/bumblebee/scripts/fcu_detect.py"
}
O="$W/out.txt"; E="$W/err.txt"
run_ic() { local txt; txt=$(gen "$IC" "$1" "$2"); ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" > "$O" 2> "$E" ); RC=$?; }
run_fp() { local txt; txt=$(gen "$FP" "$1" "$2"); ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" _ bumblebee > "$O" 2> "$E" ); RC=$?; }
n() { grep -c -- "$1" "$O"; }
for S9 in ic fp; do
  if [ $S9 = ic ]; then RUN=run_ic; P=INSTALL_FILE; N=09; RTS=BB_RTPY; PYOK() { grep -q -E "^BB_INSTALL_CHECK ok=$1 diff=$2 " "$O"; }
  else RUN=run_fp; P=PY_NODE; N=15; RTS=BB_FP_RT; PYOK() { grep -q -E "^BB_FP_RESULT files=[0-9]+ py_ok=$1 py_bad=$2 " "$O"; }; fi
  put A C V B R; $RUN "$L_ALT" "$RT_ALT"
  t "Q1$S9 $N r2j + r2j: всё OK, меток нет; узлы ok=3, RT ok=3" '[ $RC = 0 ] && PYOK 3 0 && grep -q -x "$RTS ok=3 diff=0 missing=0" "$O" && ! grep -q -E "POSEFIX_JD2|R2M_CAM" "$O"'
  put J C V B R; $RUN "$L_ALT" "$RT_ALT"
  t "Q2$S9 $N jd2 + r2j: ровно одна метка POSEFIX_JD2 (у aruco_detect.py), R2M_CAM нет" 'PYOK 3 0 && grep -q -x "$P aruco_detect.py OK POSEFIX_JD2" "$O" && [ "$(n POSEFIX_JD2)" = 1 ] && [ "$(n R2M_CAM)" = 0 ]'
  put A M V BM R; $RUN "$L_ALT" "$RT_ALT"
  t "Q3$S9 $N r2j + r2m_cam: «$P camera_fix.py OK R2M_CAM» и «RT_FILE LAUNCH launch/bumblebee.launch.py OK R2M_CAM», POSEFIX_JD2 нет" 'PYOK 3 0 && grep -q -x "$P camera_fix.py OK R2M_CAM" "$O" && grep -q -x "RT_FILE LAUNCH launch/bumblebee.launch.py OK R2M_CAM" "$O" && grep -q -x "$RTS ok=3 diff=0 missing=0" "$O" && [ "$(n R2M_CAM)" = 2 ] && [ "$(n POSEFIX_JD2)" = 0 ]'
  put J M V BM R; $RUN "$L_ALT" "$RT_ALT"
  t "Q4$S9 $N jd2 + r2m_cam: POSEFIX_JD2 x1 и R2M_CAM x2, метки не перепутаны" 'PYOK 3 0 && grep -q -x "$P aruco_detect.py OK POSEFIX_JD2" "$O" && grep -q -x "$P camera_fix.py OK R2M_CAM" "$O" && grep -q -x "RT_FILE LAUNCH launch/bumblebee.launch.py OK R2M_CAM" "$O" && [ "$(n POSEFIX_JD2)" = 1 ] && [ "$(n R2M_CAM)" = 2 ]'
  put A J V B R; $RUN "$L_ALT" "$RT_ALT"
  t "Q5$S9 $N файл jd2 под именем camera_fix.py: DIFF want=r2j,r2m_cam (второе sha узла - только своё)" 'grep -q -x "$P camera_fix.py DIFF got=$SJ want=$SC,$SM" "$O" && PYOK 2 1 && ! grep -q -E "OK (POSEFIX_JD2|R2M_CAM)" "$O"'
  put M C V B R; $RUN "$L_ALT" "$RT_ALT"
  t "Q6$S9 $N файл r2m_cam под именем aruco_detect.py: DIFF want=r2j,jd2" 'grep -q -x "$P aruco_detect.py DIFF got=$SM want=$SA,$SJ" "$O" && PYOK 2 1'
  put A C X B R; $RUN "$SA,$SJ  aruco_detect.py
$SC,$SM  camera_fix.py
$SV,$SX  vpe_fix.py" "$RT_ALT"
  t "Q7$S9 $N метка ПО ИМЕНИ: даже если ПК прислал vpe_fix.py «r2j,чужой», у vpe_fix принимается только первое sha - чужой файл DIFF" 'grep -q -x "$P vpe_fix.py DIFF got=$SX want=$SV,$SX" "$O" && PYOK 2 1 && ! grep -q "vpe_fix.py OK" "$O"'
  put A C V B RX; $RUN "$L_ALT" "$SB,$SBM  LAUNCH  launch/bumblebee.launch.py
$SR,$SRX  LAUNCH  launch/aruco.launch.py
$SF  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"
  t "Q8$S9 $N метка ПО ПУТИ: aruco.launch.py с «r2j,чужой» от ПК - чужой файл DIFF (второе sha только у bumblebee.launch.py)" 'grep -q -x "RT_FILE LAUNCH launch/aruco.launch.py DIFF got=$SRX want=$SR,$SRX" "$O" && grep -q -x "$RTS ok=2 diff=1 missing=0" "$O"'
  put A C V BM R; $RUN "$L_ALT" "$SB  LAUNCH  launch/bumblebee.launch.py
$SR  LAUNCH  launch/aruco.launch.py
$SF  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"
  t "Q9$S9 контроль $N: без второго sha (как r13) launch r2m_cam - DIFF (r2m_cam пропускает именно строка списка)" 'grep -q -x "RT_FILE LAUNCH launch/bumblebee.launch.py DIFF got=$SBM want=$SB" "$O" && grep -q -x "$RTS ok=2 diff=1 missing=0" "$O"'
  put A M V B R; $RUN "$SA,$SJ  aruco_detect.py
$SC  camera_fix.py
$SV  vpe_fix.py" "$RT_ALT"
  t "Q10$S9 контроль $N: без второго sha camera_fix r2m_cam - DIFF" 'grep -q -x "$P camera_fix.py DIFF got=$SM want=$SC" "$O" && PYOK 2 1'
  put A M V BM R; $RUN "$SA,$SJ  aruco_detect.py
$SM,$SC  camera_fix.py
$SV  vpe_fix.py" "$SBM,$SB  LAUNCH  launch/bumblebee.launch.py
$SR  LAUNCH  launch/aruco.launch.py
$SF  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"
  t "Q11$S9 $N метка только у ВТОРОГО sha: при порядке «r2m_cam,r2j» файлы r2m_cam - OK без метки" 'grep -q -x "$P camera_fix.py OK" "$O" && grep -q -x "RT_FILE LAUNCH launch/bumblebee.launch.py OK" "$O" && ! grep -q R2M_CAM "$O"'
  put A C V B R; cp "$W/v/X" "$H/ros2_ws/src/bumblebee/scripts/fcu_detect.py"; $RUN "$L_ALT" "$RT_ALT"
  t "Q12$S9 $N fcu_detect.py по-прежнему строго (чужой - DIFF)" 'grep -q -x "RT_FILE FCU ros2_ws/src/bumblebee/scripts/fcu_detect.py DIFF got=$SX want=$SF" "$O"'
done
( export PATH="$FB:/usr/bin:/bin" FAKE_HOST=other; bash -c "$(gen "$IC" "$L_ALT" "$RT_ALT")" > "$O" 2> "$E" ); RC=$?
t "Q13 09 на чужом hostname: код 1, STOP, вывода нет" '[ $RC = 1 ] && grep -q "STOP: hostname is other" "$E" && [ ! -s "$O" ]'
( export PATH="$FB:/usr/bin:/bin" FAKE_HOST=other; bash -c "$(gen "$FP" "$L_ALT" "$RT_ALT")" _ bumblebee > "$O" 2> "$E" ); RC=$?
t "Q14 15 на чужом hostname: код 1, STOP, вывода нет" '[ $RC = 1 ] && grep -q "STOP: hostname is other" "$E" && [ ! -s "$O" ]'
echo ""
echo "ИТОГ r14 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
