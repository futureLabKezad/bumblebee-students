#!/bin/bash
# run_tests_r11_pi.sh (Claude, 16.11.2026, набор r11) - тесты r11 в WSL БЕЗ дрона, без ROS и без sudo. Ничего не пишет вне песочницы.
# Проверяет сверку C++ исходников и примеров полёта в pi/install_check.sh (шаг 09) и pi/overlay_fingerprint.sh (шаг 15) после правки r11:
# поле want в списке может быть «sha_r2j,sha_real» (image_r2j/EXAMPLES_REAL_20261116.tsv); совпадение с любым - OK, второе помечается REAL_MAP; всё прочее - как в r9.
# Подделки: hostname и ros2 первыми в PATH, «source» заглушён функцией, HOME = песочница. Списки подставляются так же, как это делает ПК (строка #@@CPP@@ -> строки списка).
# Запуск (WSL, низкий приоритет): nice -n 19 ionice -c3 bash tests/run_tests_r11_pi.sh [папка для песочницы, по умолчанию /tmp]. Итог: «ИТОГ r11 Pi: PASS n, FAIL m», код 0 только при FAIL 0.
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r11pi_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
FB="$W/fakebin"; H="$W/home"; mkdir -p "$FB" "$H"
printf '#!/bin/bash\necho "${FAKE_HOST:-bumblebee-20ec}"\n' > "$FB/hostname"
# ros2 pkg prefix bumblebee -> install песочницы
printf '#!/bin/bash\nif [ "$1 $2 $3" = "pkg prefix bumblebee" ]; then echo "$HOME/ros2_ws/install/bumblebee"; exit 0; fi\nexit 1\n' > "$FB/ros2"
chmod +x "$FB"/*
IC="$KIT/pi/install_check.sh"; FP="$KIT/pi/overlay_fingerprint.sh"
EX="$KIT/image_r2j/payload/ros2_ws/src/bumblebee/examples"; RM="$KIT/real_map_20261116"
ALT="$KIT/image_r2j/EXAMPLES_REAL_20261116.tsv"
O="$W/out.txt"; E="$W/err.txt"
t "Q0 bash -n install_check.sh и overlay_fingerprint.sh" 'bash -n "$IC" && bash -n "$FP"'
t "Q0b первая команда обоих скриптов - проверка hostname, как в r9" '[ "$(grep -v -E "^[[:space:]]*(#|$)" "$IC" | head -1 | cut -c1-39)" = "[ \"\$(hostname)\" = \"bumblebee-20ec\" ] ||" ] && [ "$(grep -v -E "^[[:space:]]*(#|$)" "$FP" | head -1 | cut -c1-39)" = "[ \"\$(hostname)\" = \"bumblebee-20ec\" ] ||" ]'
CODE=$(cat "$IC" "$FP" | grep -v -E '^[[:space:]]*#')
t "Q0c в коде обоих скриптов нет sudo, rm, mv, cp, tee, mkdir, touch, chmod, reboot, systemctl (только чтение, как в r9)" '! printf "%s\n" "$CODE" | grep -q -E "(^|[[:space:];|&(])(sudo|rm|mv|cp|tee|mkdir|touch|chmod|reboot|systemctl)[[:space:]]"'

# дерево «дрона»: C++ файлы - синтетические (их содержимое тут не важно), примеры полёта - настоящие файлы r2j из payload набора
SRC="$H/ros2_ws/src/bumblebee"
mkdir -p "$SRC/src/cpp" "$SRC/examples/flight" "$H/ros2_ws/install/bumblebee/lib/bumblebee"
for f in CMakeLists.txt package.xml src/cpp/a.cpp src/cpp/b.h; do echo "synthetic $f" > "$SRC/$f"; done
cp "$EX/drone.py" "$EX/flight_profile.py" "$SRC/examples/";cp "$EX/flight/flight.py" "$EX/flight/flight_marker.py" "$EX/flight/flight_marker_loop.py" "$SRC/examples/flight/"
# список как в CPP_SOURCES_r2j.tsv: «sha256  путь  флаг» (примеры полёта - sha r2j из настоящего списка набора)
CPPR2J=$(grep -v '^#' "$KIT/image_r2j/CPP_SOURCES_r2j.tsv" | grep 'examples/' | awk -F'\t' '{print $1"  "$2"  "$3}')
SYN=$(for f in CMakeLists.txt package.xml src/cpp/a.cpp src/cpp/b.h; do fl=-; [ "$f" = src/cpp/b.h ] && fl=R; echo "$(sha256sum "$SRC/$f" | cut -c1-64)  ros2_ws/src/bumblebee/$f  $fl"; done)
# слияние со списком real так же, как BL-ApplyRealAlt на ПК: «sha_r2j,sha_real»
mk_list() { # mk_list <с_alt 0|1>
  printf '%s\n' "$SYN"
  if [ "$1" = 1 ]; then
    printf '%s\n' "$CPPR2J" | while read -r s p fl; do a=$(grep -v '^#' "$ALT" | awk -F'\t' -v p="$p" '$2==p{print $1}'); if [ -n "$a" ]; then echo "$s,$a  $p  $fl"; else echo "$s  $p  $fl"; fi; done
  else printf '%s\n' "$CPPR2J"; fi
}
NEX=$(printf '%s\n' "$CPPR2J" | grep -c .)
NALL=$((NEX + 4))
gen() { # gen <шаблон> <список CPP> -> текст скрипта с подстановкой (#@@LIST@@, #@@BINS@@, #@@RT@@ - пусто)
  local tpl="$1"; printf '%s\n' "$2" > "$W/body.txt"
  tr -d '\r' < "$tpl" | awk -v bf="$W/body.txt" '{ if ($0=="#@@CPP@@") { while ((getline l < bf) > 0) print l; close(bf) } else if ($0=="#@@LIST@@" || $0=="#@@BINS@@" || $0=="#@@RT@@") print "# пусто"; else print }'
}
run_ic() { # run_ic <с_alt>
  local txt; txt=$(gen "$IC" "$(mk_list "$1")")
  ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" > "$O" 2> "$E" ); RC=$?
}
run_fp() {
  local txt; txt=$(gen "$FP" "$(mk_list "$1")")
  ( source(){ :; }; export -f source; export HOME="$H" PATH="$FB:/usr/bin:/bin"; bash -c "$txt" _ bumblebee > "$O" 2> "$E" ); RC=$?
}
icres() { grep -o -E 'BB_INSTALL_CHECK .*' "$O" | head -1; }
altpaths_ok() { local p; for p in $(grep -v '^#' "$ALT" | cut -f2); do printf '%s\n' "$CPPR2J" | grep -q "  $p  -$" || return 1; done; return 0; }
t "Q1 список примеров real: ровно 2 строки, пути есть в CPP_SOURCES_r2j.tsv с флагом «-», sha = копии real_map_20261116" '[ "$(grep -v "^#" "$ALT" | grep -c .)" = 2 ] && [ "$(grep -v "^#" "$ALT" | cut -f1 | sort | tr "\n" " ")" = "$(sha256sum "$RM/flight_marker.py" "$RM/flight_marker_loop.py" | cut -c1-64 | sort | tr "\n" " ")" ] && altpaths_ok'

# --- 09 install_check.sh ---
run_ic 1
t "I1 дрон с примерами r2j, список с alt: все C++ и примеры OK ($NALL), REAL_MAP нет, отличий 0" '[ "$RC" = 0 ] && icres | grep -q "cpp_ok=$NALL cpp_diff=0 cpp_missing=0" && ! grep -q REAL_MAP "$O"'
run_ic 0
t "I1b тот же дрон, список БЕЗ alt (как r9): так же OK ($NALL) - для r2j поведение не изменилось" '[ "$RC" = 0 ] && icres | grep -q "cpp_ok=$NALL cpp_diff=0 cpp_missing=0"'
cp "$RM/flight_marker.py" "$RM/flight_marker_loop.py" "$SRC/examples/flight/"
run_ic 1
t "I2 на дроне примеры карты real, список с alt: OK ($NALL), две строки «OK - REAL_MAP» для flight_marker и flight_marker_loop" '[ "$RC" = 0 ] && icres | grep -q "cpp_ok=$NALL cpp_diff=0 cpp_missing=0" && [ "$(grep -c "^CPP_SRC .* OK - REAL_MAP$" "$O")" = 2 ] && grep -q "^CPP_SRC ros2_ws/src/bumblebee/examples/flight/flight_marker.py OK - REAL_MAP$" "$O" && grep -q "^CPP_SRC ros2_ws/src/bumblebee/examples/flight/flight_marker_loop.py OK - REAL_MAP$" "$O"'
run_ic 0
t "I2b примеры real, список БЕЗ alt (r9): 2 отличия (DIFF) - это то, что r11 исправляет" '[ "$RC" = 0 ] && icres | grep -q "cpp_diff=2" '
cp "$RM/aruco_z_test.py" "$SRC/examples/flight/flight_marker.py"
run_ic 1
t "I3 вместо flight_marker.py лежит другой файл (aruco_z_test real): DIFF 1, остальное OK" '[ "$RC" = 0 ] && icres | grep -q "cpp_ok=$((NALL-1)) cpp_diff=1 cpp_missing=0" && grep -q "^CPP_SRC ros2_ws/src/bumblebee/examples/flight/flight_marker.py DIFF got=" "$O"'
cp "$EX/flight/flight_marker.py" "$SRC/examples/flight/flight_marker.py"; cp "$RM/flight_marker.py" "$SRC/examples/flight/flight.py"
run_ic 1
t "I4 alt действует только для своего пути: flight.py, подменённый flight_marker real, - DIFF" '[ "$RC" = 0 ] && icres | grep -q "cpp_diff=1" && grep -q "^CPP_SRC ros2_ws/src/bumblebee/examples/flight/flight.py DIFF got=" "$O"'
cp "$EX/flight/flight.py" "$SRC/examples/flight/flight.py"; mv "$SRC/examples/flight/flight_marker_loop.py" "$W/loop_aside.py"
run_ic 1
t "I5 нет файла flight_marker_loop.py: MISSING 1 (пустой sha не совпадает ни с чем)" '[ "$RC" = 0 ] && icres | grep -q "cpp_missing=1" && grep -q "^CPP_SRC ros2_ws/src/bumblebee/examples/flight/flight_marker_loop.py MISSING" "$O"'
mv "$W/loop_aside.py" "$SRC/examples/flight/flight_marker_loop.py"
echo "changed" >> "$SRC/src/cpp/a.cpp"
run_ic 1
t "I6 C++ исходник изменён: DIFF, как в r9 (alt касается только двух примеров)" '[ "$RC" = 0 ] && icres | grep -q "cpp_diff=1" && grep -q "^CPP_SRC ros2_ws/src/bumblebee/src/cpp/a.cpp DIFF" "$O"'
echo "synthetic src/cpp/a.cpp" > "$SRC/src/cpp/a.cpp"
FAKE_HOST=other-pi; export FAKE_HOST
run_ic 1
t "I7 чужое имя хоста: код 1, STOP, сверки нет" '[ "$RC" = 1 ] && grep -q "STOP: hostname is other-pi" "$E" && [ ! -s "$O" ]'
unset FAKE_HOST

# --- 15 overlay_fingerprint.sh (оверлей ~/bench_ws/r2j) ---
OV="$H/bench_ws/r2j"; mkdir -p "$OV/install/bumblebee/lib/bumblebee" "$OV/src"
cp "$EX/flight/flight.py" "$EX/flight/flight_marker.py" "$EX/flight/flight_marker_loop.py" "$SRC/examples/flight/"   # копия ros2_ws/src в оверлей, как делает 13: примеры r2j
cp -r "$SRC" "$OV/src/"
fpres() { grep -o -E 'BB_FP_RESULT .*' "$O" | head -1; }
run_fp 1
t "F1 оверлей с примерами r2j, список с alt: src_ok=$NALL src_bad=0, REAL_MAP нет" '[ "$RC" = 0 ] && fpres | grep -q "src_ok=$NALL src_bad=0" && ! grep -q REAL_MAP "$O"'
cp "$RM/flight_marker.py" "$RM/flight_marker_loop.py" "$OV/src/bumblebee/examples/flight/"
run_fp 1
t "F2 в оверлее примеры карты real: src_ok=$NALL, две строки «SRC ... OK - REAL_MAP»" '[ "$RC" = 0 ] && fpres | grep -q "src_ok=$NALL src_bad=0" && [ "$(grep -c "^SRC bumblebee/examples/flight/flight_marker\(_loop\)\?\.py OK - REAL_MAP$" "$O")" = 2 ]'
run_fp 0
t "F2b то же БЕЗ alt (r9): src_bad=2" '[ "$RC" = 0 ] && fpres | grep -q "src_bad=2"'
cp "$RM/aruco_z_test.py" "$OV/src/bumblebee/examples/flight/flight_marker_loop.py"
run_fp 1
t "F3 в оверлее вместо flight_marker_loop.py чужой файл: src_bad=1, DIFF" '[ "$RC" = 0 ] && fpres | grep -q "src_bad=1" && grep -q "^SRC bumblebee/examples/flight/flight_marker_loop.py DIFF" "$O"'
echo ""
echo "ИТОГ r11 Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
