#!/bin/bash
# run_tests_r13_pi.sh (Claude, 17.11.2026, набор r13) - тесты r13 в WSL БЕЗ дрона и без sudo. Пишет только в свою песочницу.
# P: сверка python-узлов в pi/install_check.sh (09) и pi/overlay_fingerprint.sh (15): поле want у aruco_detect.py может быть «sha_r2j,sha_jd2»
#    (image_r2j/POSEFIX_JD2_20261117.tsv); совпадение с любым - OK, второе помечается POSEFIX_JD2; все остальные узлы и строки RT - строго, как в r11.
# Синтетические файлы (не настоящие узлы): A - «aruco r2j», J - «aruco jd2», D - «aruco jd», V - «vpe_fix r2j», C - «camera_fix r2j».
# Запуск (WSL, низкий приоритет): nice -n 19 ionice -c3 bash tests/run_tests_r13_pi.sh [папка для песочницы, по умолчанию /tmp]. Итог: «ИТОГ r13 Pi: PASS n, FAIL m».
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r13pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
IC="$KIT/pi/install_check.sh"; FP="$KIT/pi/overlay_fingerprint.sh"
sha() { sha256sum "$1" | cut -c1-64; }
FB="$W/fakebin"; H="$W/home"; mkdir -p "$FB" "$H"
printf '#!/bin/bash\necho "${FAKE_HOST:-bumblebee-20ec}"\n' > "$FB/hostname"
printf '#!/bin/bash\nif [ "$1 $2 $3" = "pkg prefix bumblebee" ]; then echo "$HOME/ros2_ws/install/bumblebee"; exit 0; fi\nexit 1\n' > "$FB/ros2"
chmod +x "$FB"/*
t "P0 bash -n install_check.sh и overlay_fingerprint.sh" 'bash -n "$IC" && bash -n "$FP"'
CODE=$(cat "$IC" "$FP" | grep -v -E '^[[:space:]]*#')
t "P0b в коде обоих скриптов по-прежнему нет sudo, rm, mv, cp, tee, mkdir, touch, chmod, reboot, systemctl и перенаправления в файл (только чтение, как в r11)" '! printf "%s\n" "$CODE" | grep -q -E "(^|[[:space:];|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|reboot|systemctl)[[:space:]]" && ! printf "%s\n" "$CODE" | sed -e "s#2>&1##g; s#> */dev/null##g; s#>&2##g; s#< */dev/null##g; s#<<<##g; s#<<##g" | grep -q ">"'
for S in IC FP; do
  F=$([ $S = IC ] && echo "$IC" || echo "$FP")
  t "P0c$S ровно одно определение shamatch, и оно ВЫШЕ цикла python-узлов (while read -r want name)" '[ "$(grep -c "^shamatch() {" "$F")" = 1 ] && [ "$(grep -n "^shamatch() {" "$F" | cut -d: -f1)" -lt "$(grep -n "while read -r want name; do" "$F" | head -1 | cut -d: -f1)" ]'
done
t "P0d цикл узлов через shamatch с меткой POSEFIX_JD2 (по одной строке в каждом скрипте); строки RT - прежнее точное сравнение (как r11, без R2K_CAM)" '[ "$(grep -c "if shamatch \"\$got\" \"\$want\"; then ok=\$((ok+1)); vmark=\"\"; \[ \"\$got\" = \"\${want%%,\*}\" \] || vmark=\" POSEFIX_JD2\"; echo \"INSTALL_FILE \$name OK\$vmark\"" "$IC")" = 1 ] && [ "$(grep -c "if shamatch \"\$got\" \"\$want\"; then pok=\$((pok+1)); vmark=\"\"; \[ \"\$got\" = \"\${want%%,\*}\" \] || vmark=\" POSEFIX_JD2\"; echo \"PY_NODE \$name OK\$vmark\"" "$FP")" = 1 ] && [ "$(grep -c "if \[ \"\$got\" = \"\$want\" \]; then rtok=" "$IC")" = 1 ] && [ "$(grep -c "if \[ \"\$got\" = \"\$want\" \]; then rtok=" "$FP")" = 1 ] && ! grep -q R2K_CAM "$IC" "$FP"'
mkdir -p "$W/v"
echo "aruco r2j" > "$W/v/A"; echo "aruco jd2 posefix" > "$W/v/J"; echo "aruco jd old" > "$W/v/D"; echo "vpe_fix r2j" > "$W/v/V"; echo "camera_fix r2j" > "$W/v/C"
SA=$(sha "$W/v/A"); SJ=$(sha "$W/v/J"); SD=$(sha "$W/v/D"); SV=$(sha "$W/v/V"); SC=$(sha "$W/v/C")
L_ALT="$SA,$SJ  aruco_detect.py
$SV  vpe_fix.py
$SC  camera_fix.py"
L_NOALT="$SA  aruco_detect.py
$SV  vpe_fix.py
$SC  camera_fix.py"
gen() { # gen <шаблон> <список LIST>: #@@LIST@@ -> список, прочие маркеры - пусто (как подставляет ПК)
  printf '%s\n' "$2" > "$W/body.txt"
  tr -d '\r' < "$1" | awk -v bf="$W/body.txt" '{ if ($0=="#@@LIST@@") { while ((getline l < bf) > 0) print l; close(bf) } else if ($0=="#@@RT@@" || $0=="#@@BINS@@" || $0=="#@@CPP@@") print "# пусто"; else print }'
}
put() { # put <aruco: A|J|D|-> <vpe: V|J> <camera: C|J>
  for d in "$H/ros2_ws/install/bumblebee/lib/bumblebee" "$H/bench_ws/r2j/install/bumblebee/lib/bumblebee"; do
    mkdir -p "$d"; rm -f "$d/aruco_detect.py"
    [ "$1" != - ] && cp "$W/v/$1" "$d/aruco_detect.py"
    cp "$W/v/$2" "$d/vpe_fix.py"; cp "$W/v/$3" "$d/camera_fix.py"
  done
}
O="$W/out.txt"; E="$W/err.txt"
run_ic() { local txt; txt=$(gen "$IC" "$1"); ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" > "$O" 2> "$E" ); RC=$?; }
run_fp() { local txt; txt=$(gen "$FP" "$1"); ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" _ bumblebee > "$O" 2> "$E" ); RC=$?; }
for S in ic fp; do
  if [ $S = ic ]; then RUN=run_ic; P=INSTALL_FILE; N=09; SUMOK() { grep -q -E "^BB_INSTALL_CHECK ok=$1 diff=$2 missing=$3 " "$O"; }
  else RUN=run_fp; P=PY_NODE; N=15; SUMOK() { grep -q -E "^BB_FP_RESULT files=[0-9]+ py_ok=$1 py_bad=$(( $2 + $3 )) " "$O"; }; fi
  put A V C; $RUN "$L_ALT"
  t "P1$S $N: aruco r2j при want r2j,jd2 - OK без метки, итог ok=3 diff=0" '[ $RC = 0 ] && grep -q -x "$P aruco_detect.py OK" "$O" && ! grep -q POSEFIX_JD2 "$O" && SUMOK 3 0 0'
  put J V C; $RUN "$L_ALT"
  t "P2$S $N: aruco jd2 - «$P aruco_detect.py OK POSEFIX_JD2» ровно одна метка; vpe_fix и camera_fix OK без метки; ok=3" '[ $RC = 0 ] && grep -q -x "$P aruco_detect.py OK POSEFIX_JD2" "$O" && [ "$(grep -c POSEFIX_JD2 "$O")" = 1 ] && grep -q -x "$P vpe_fix.py OK" "$O" && grep -q -x "$P camera_fix.py OK" "$O" && SUMOK 3 0 0'
  put D V C; $RUN "$L_ALT"
  t "P3$S $N: старый jd - DIFF got=<jd> want=r2j,jd2, ok=2 diff=1, метки нет" 'grep -q -x "$P aruco_detect.py DIFF got=$SD want=$SA,$SJ" "$O" && SUMOK 2 1 0 && ! grep -q POSEFIX_JD2 "$O"'
  put A J C; $RUN "$L_ALT"
  t "P4$S $N: файл jd2 под именем vpe_fix.py (у него want только r2j) - DIFF, поблажка только для aruco_detect.py" 'grep -q -x "$P vpe_fix.py DIFF got=$SJ want=$SV" "$O" && SUMOK 2 1 0 && ! grep -q POSEFIX_JD2 "$O"'
  put A V J; $RUN "$L_ALT"
  t "P5$S $N: файл jd2 под именем camera_fix.py - DIFF" 'grep -q -x "$P camera_fix.py DIFF got=$SJ want=$SC" "$O" && SUMOK 2 1 0'
  put - V C; $RUN "$L_ALT"
  if [ $S = ic ]; then t "P6$S $N: нет aruco_detect.py - MISSING want=r2j,jd2, missing=1" 'grep -q -x "INSTALL_FILE aruco_detect.py MISSING want=$SA,$SJ" "$O" && SUMOK 2 0 1'
  else t "P6$S $N: нет aruco_detect.py - MISSING, py_bad=1" 'grep -q -x "PY_NODE aruco_detect.py MISSING" "$O" && SUMOK 2 0 1'; fi
  put J V C; $RUN "$L_NOALT"
  t "P7$S контроль $N: без второго sha (как r11) aruco jd2 - DIFF (значит, jd2 пропускает именно строка списка, а не ослабление)" 'grep -q -x "$P aruco_detect.py DIFF got=$SJ want=$SA" "$O" && SUMOK 2 1 0'
  put J V C; $RUN "$SJ,$SA  aruco_detect.py
$SV  vpe_fix.py
$SC  camera_fix.py"
  t "P8$S $N: метка POSEFIX_JD2 ставится только для ВТОРОГО sha (первое = r2j): при порядке «jd2,r2j» файл jd2 - OK без метки" 'grep -q -x "$P aruco_detect.py OK" "$O" && ! grep -q POSEFIX_JD2 "$O"'
  put J V C; $RUN "$SA,  aruco_detect.py
$SV  vpe_fix.py
$SC  camera_fix.py"
  t "P9$S $N: пустое второе значение («sha_r2j,») ничего лишнего не пропускает: файл jd2 - DIFF" 'grep -q -x "$P aruco_detect.py DIFF got=$SJ want=$SA," "$O" && SUMOK 2 1 0'
done
( export PATH="$FB:/usr/bin:/bin" FAKE_HOST=other; bash -c "$(gen "$IC" "$L_ALT")" > "$O" 2> "$E" ); RC=$?
t "P10 09 на чужом hostname: код 1, STOP, вывода нет" '[ $RC = 1 ] && grep -q "STOP: hostname is other" "$E" && [ ! -s "$O" ]'
( export PATH="$FB:/usr/bin:/bin" FAKE_HOST=other; bash -c "$(gen "$FP" "$L_ALT")" _ bumblebee > "$O" 2> "$E" ); RC=$?
t "P11 15 на чужом hostname: код 1, STOP, вывода нет" '[ $RC = 1 ] && grep -q "STOP: hostname is other" "$E" && [ ! -s "$O" ]'
echo ""
echo "ИТОГ r13 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
