#!/bin/bash
# run_tests_r16_pi.sh (Claude, 18.11.2026, набор r16) - тесты r16 в WSL БЕЗ дрона и без sudo. Пишет только в свою песочницу.
# U: pi/install_check.sh (09) и pi/overlay_fingerprint.sh (15): aruco_detect.py до 3 sha («r2j,jd2,v1»), vpe_fix.py до 2 («r2j,v1»), camera_fix.py до 2 («r2j,r2m_cam»), остальные узлы - 1;
#    метка по СОВПАВШЕМУ sha (shalab, перенесена из r15): aruco 2-е - POSEFIX_JD2, 3-е - POSEFIX_V1; vpe 2-е - POSEFIX_V1; camera 2-е - R2M_CAM. Строки RT - как в r14.
#    Правило «В1 только у одного из двух узлов - СТОП» проверяет ПК (тесты ПК V6/V7); здесь - метки, на которых оно стоит.
# Синтетические файлы (не настоящие узлы): A/J/Va - aruco r2j/jd2/В1, D - aruco jd, K - aruco jd3, X - чужой, V/Vv - vpe r2j/В1, C/M - camera r2j/r2m_cam, Q - qos_relay, B - launch, F - fcu.
# Запуск (WSL, низкий приоритет): nice -n 19 ionice -c3 bash tests/run_tests_r16_pi.sh [папка для песочницы, по умолчанию /tmp]. Итог: «ИТОГ r16 Pi: PASS n, FAIL m».
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r16pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
IC="$KIT/pi/install_check.sh"; FP="$KIT/pi/overlay_fingerprint.sh"
sha() { sha256sum "$1" | cut -c1-64; }
FB="$W/fakebin"; H="$W/home"; mkdir -p "$FB" "$H"
printf '#!/bin/bash\necho "${FAKE_HOST:-bumblebee-20ec}"\n' > "$FB/hostname"
printf '#!/bin/bash\nif [ "$1 $2 $3" = "pkg prefix bumblebee" ]; then echo "$HOME/ros2_ws/install/bumblebee"; exit 0; fi\nexit 1\n' > "$FB/ros2"
chmod +x "$FB"/*
t "U0 bash -n install_check.sh и overlay_fingerprint.sh" 'bash -n "$IC" && bash -n "$FP"'
CODE=$(cat "$IC" "$FP" | grep -v -E '^[[:space:]]*#')
t "U0b в коде обоих скриптов нет sudo, rm, mv, cp, tee, mkdir, touch, chmod, reboot, systemctl и перенаправления в файл (только чтение)" '! printf "%s\n" "$CODE" | grep -q -E "(^|[[:space:];|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|reboot|systemctl)[[:space:]]" && ! printf "%s\n" "$CODE" | sed -e "s#2>&1##g; s#> */dev/null##g; s#>&2##g; s#< */dev/null##g; s#<<<##g; s#<<##g" | grep -q ">"'
for F9 in "$IC" "$FP"; do
  t "U0c $(basename "$F9"): shalab и shamatch по одному разу и выше цикла узлов; цикл узлов через shalab с пределами 3/2/2/1 и метками POSEFIX_JD2,POSEFIX_V1 / POSEFIX_V1 / R2M_CAM; POSEFIX_JD3 нет; RT как в r14" '[ "$(grep -c "^shalab() {" "$F9")" = 1 ] && [ "$(grep -c "^shamatch() {" "$F9")" = 1 ] && [ "$(grep -n "^shalab() {" "$F9" | cut -d: -f1)" -lt "$(grep -n "while read -r want name; do" "$F9" | head -1 | cut -d: -f1)" ] && grep -q "if lab=\$(shalab \"\$got\" \"\$w\" \"\$labs\"); then" "$F9" && grep -q -F "aruco_detect.py) w=\$(printf '"'"'%s'"'"' \"\$want\" | cut -d, -f1-3); labs=\",POSEFIX_JD2,POSEFIX_V1\";; vpe_fix.py) w=\$(printf '"'"'%s'"'"' \"\$want\" | cut -d, -f1-2); labs=\",POSEFIX_V1\";;" "$F9" && ! grep -q POSEFIX_JD3 "$F9" && grep -q -F "case \"\$kind \$path\" in \"LAUNCH launch/bumblebee.launch.py\") w=\"\$want\"; lab=\" R2M_CAM\";; *) w=\"\${want%%,*}\"; lab=\"\";; esac" "$F9"'
done
mkdir -p "$W/v"
for x in A J Va D K X V Vv C M Q B F; do echo "синтетический файл $x" > "$W/v/$x"; done
S() { sha "$W/v/$1"; }
SA=$(S A); SJ=$(S J); SVA=$(S Va); SD=$(S D); SK=$(S K); SX=$(S X); SV=$(S V); SVV=$(S Vv); SC=$(S C); SM=$(S M); SQ=$(S Q); SB=$(S B); SF=$(S F)
LL="$SA,$SJ,$SVA  aruco_detect.py
$SV,$SVV  vpe_fix.py
$SC,$SM  camera_fix.py
$SQ  qos_relay.py"
RT1="$SB  LAUNCH  launch/bumblebee.launch.py
$SF  FCU  ros2_ws/src/bumblebee/scripts/fcu_detect.py"
gen() { # gen <шаблон> <LIST> <RT>
  printf '%s\n' "$2" > "$W/l.txt"; printf '%s\n' "$3" > "$W/r.txt"
  tr -d '\r' < "$1" | awk -v lf="$W/l.txt" -v rf="$W/r.txt" '{ if ($0=="#@@LIST@@") { while ((getline l < lf) > 0) print l; close(lf) } else if ($0=="#@@RT@@") { while ((getline l < rf) > 0) print l; close(rf) } else if ($0=="#@@BINS@@" || $0=="#@@CPP@@") print "# пусто"; else print }'
}
put() { # put <aruco> <vpe> <camera> <qos>
  for t9 in "$H/ros2_ws/install/bumblebee" "$H/bench_ws/r2j/install/bumblebee"; do
    mkdir -p "$t9/lib/bumblebee" "$t9/share/bumblebee/launch"
    cp "$W/v/$1" "$t9/lib/bumblebee/aruco_detect.py"; cp "$W/v/$2" "$t9/lib/bumblebee/vpe_fix.py"; cp "$W/v/$3" "$t9/lib/bumblebee/camera_fix.py"; cp "$W/v/$4" "$t9/lib/bumblebee/qos_relay.py"; cp "$W/v/B" "$t9/share/bumblebee/launch/bumblebee.launch.py"
  done
  mkdir -p "$H/ros2_ws/src/bumblebee/scripts"; cp "$W/v/F" "$H/ros2_ws/src/bumblebee/scripts/fcu_detect.py"
}
O="$W/out.txt"; E="$W/err.txt"
run_ic() { local txt; txt=$(gen "$IC" "$1" "$2"); ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" > "$O" 2> "$E" ); RC=$?; }
run_fp() { local txt; txt=$(gen "$FP" "$1" "$2"); ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" _ bumblebee > "$O" 2> "$E" ); RC=$?; }
n() { grep -c -- "$1" "$O"; }
for S9 in ic fp; do
  if [ $S9 = ic ]; then RUN=run_ic; P=INSTALL_FILE; N=09; PYOK() { grep -q -E "^BB_INSTALL_CHECK ok=$1 diff=$2 " "$O"; }
  else RUN=run_fp; P=PY_NODE; N=15; PYOK() { grep -q -E "^BB_FP_RESULT files=[0-9]+ py_ok=$1 py_bad=$2 " "$O"; }; fi
  put A V C Q; $RUN "$LL" "$RT1"
  t "U1$S9 $N r2j везде: OK без меток" '[ $RC = 0 ] && PYOK 4 0 && ! grep -q -E "POSEFIX|R2M_CAM" "$O"'
  put J V C Q; $RUN "$LL" "$RT1"
  t "U2$S9 $N aruco jd2: «OK POSEFIX_JD2», одна метка" 'PYOK 4 0 && grep -q -x "$P aruco_detect.py OK POSEFIX_JD2" "$O" && [ "$(n POSEFIX)" = 1 ]'
  put Va Vv C Q; $RUN "$LL" "$RT1"
  t "U3$S9 $N В1 (aruco 3-е sha, vpe 2-е): обе «OK POSEFIX_V1», POSEFIX_JD2 нет" 'PYOK 4 0 && grep -q -x "$P aruco_detect.py OK POSEFIX_V1" "$O" && grep -q -x "$P vpe_fix.py OK POSEFIX_V1" "$O" && [ "$(n POSEFIX)" = 2 ] && ! grep -q POSEFIX_JD2 "$O"'
  put Va Vv M Q; $RUN "$LL" "$RT1"
  t "U4$S9 $N В1 + camera r2m_cam: 2 POSEFIX_V1 и 1 R2M_CAM, метки не перепутаны" 'PYOK 4 0 && [ "$(n POSEFIX_V1)" = 2 ] && grep -q -x "$P camera_fix.py OK R2M_CAM" "$O" && [ "$(n R2M_CAM)" = 1 ]'
  put Va V C Q; $RUN "$LL" "$RT1"
  t "U5$S9 $N смесь aruco В1 + vpe r2j: aruco «OK POSEFIX_V1», vpe OK без метки (СТОП ставит ПК по числу POSEFIX_V1 = 1)" 'grep -q -x "$P aruco_detect.py OK POSEFIX_V1" "$O" && grep -q -x "$P vpe_fix.py OK" "$O" && [ "$(n POSEFIX_V1)" = 1 ]'
  put J Vv C Q; $RUN "$LL" "$RT1"
  t "U6$S9 $N смесь aruco jd2 + vpe В1: POSEFIX_JD2 и POSEFIX_V1 по одной" '[ "$(n POSEFIX_JD2)" = 1 ] && [ "$(n POSEFIX_V1)" = 1 ] && grep -q -x "$P vpe_fix.py OK POSEFIX_V1" "$O"'
  put D V C Q; $RUN "$LL" "$RT1"
  t "U7$S9 $N jd - DIFF want=r2j,jd2,v1" 'grep -q -x "$P aruco_detect.py DIFF got=$SD want=$SA,$SJ,$SVA" "$O" && PYOK 3 1'
  put K V C Q; $RUN "$LL" "$RT1"
  t "U8$S9 $N jd3 - DIFF (в r16 не допускается)" 'grep -q -x "$P aruco_detect.py DIFF got=$SK want=$SA,$SJ,$SVA" "$O" && PYOK 3 1'
  put A Va C Q; $RUN "$LL" "$RT1"
  t "U9$S9 $N файл aruco В1 под именем vpe_fix.py - DIFF want=r2j,v1(vpe)" 'grep -q -x "$P vpe_fix.py DIFF got=$SVA want=$SV,$SVV" "$O" && PYOK 3 1'
  put Vv V C Q; $RUN "$LL" "$RT1"
  t "U10$S9 $N файл vpe В1 под именем aruco_detect.py - DIFF" 'grep -q -x "$P aruco_detect.py DIFF got=$SVV want=$SA,$SJ,$SVA" "$O" && PYOK 3 1'
  put A V Vv Q; $RUN "$LL" "$RT1"
  t "U11$S9 $N файл vpe В1 под именем camera_fix.py - DIFF" 'grep -q -x "$P camera_fix.py DIFF got=$SVV want=$SC,$SM" "$O" && PYOK 3 1'
  put A X C Q; $RUN "$SA,$SJ,$SVA  aruco_detect.py
$SV,$SVV,$SX  vpe_fix.py
$SC,$SM  camera_fix.py
$SQ,$SX  qos_relay.py" "$RT1"
  t "U12$S9 $N у vpe_fix берутся только 2 первых sha: 3-е от ПК (чужой файл) - DIFF" 'grep -q -E "^$P vpe_fix.py DIFF got=$SX " "$O"'
  put A V C X; $RUN "$SA,$SJ,$SVA  aruco_detect.py
$SV,$SVV  vpe_fix.py
$SC,$SM  camera_fix.py
$SQ,$SX  qos_relay.py" "$RT1"
  t "U13$S9 $N у прочих узлов (qos_relay) только 1-е sha: «r2j,чужой» от ПК - чужой файл DIFF" 'grep -q -E "^$P qos_relay.py DIFF got=$SX " "$O"'
  put Va Vv C Q; $RUN "$SA,$SJ  aruco_detect.py
$SV  vpe_fix.py
$SC,$SM  camera_fix.py
$SQ  qos_relay.py" "$RT1"
  t "U14$S9 контроль $N: без sha В1 в списке (как r14) - оба узла DIFF (В1 пропускают именно строки списка)" 'grep -q -x "$P aruco_detect.py DIFF got=$SVA want=$SA,$SJ" "$O" && grep -q -x "$P vpe_fix.py DIFF got=$SVV want=$SV" "$O" && PYOK 2 2'
done
( export PATH="$FB:/usr/bin:/bin" FAKE_HOST=other; bash -c "$(gen "$IC" "$LL" "$RT1")" > "$O" 2> "$E" ); RC=$?
t "U15 09 на чужом hostname: код 1, STOP, вывода нет" '[ $RC = 1 ] && grep -q "STOP: hostname is other" "$E" && [ ! -s "$O" ]'
echo ""
echo "ИТОГ r16 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
