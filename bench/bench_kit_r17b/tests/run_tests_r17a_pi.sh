#!/bin/bash
# run_tests_r17a_pi.sh (Claude, 19.11.2026, набор r17a) - тесты r17a в WSL БЕЗ дрона и без sudo. Пишет только в свою песочницу.
# V: НАСТОЯЩИЙ pi/vision_measure.sh (шаг 03) в поддельном окружении tests/r17a_wsl_vm.sh: строки детектора «joint rms median» / «MAP != FIELD?» / «map mismatch cleared»
#    берутся из журнала стека (/tmp/bumblebee.log; в тесте - файл через BB_TEST_LOG), только НОВЫЕ байты с начала замера, только чтение; не больше 60 (JR_CUT);
#    нет журнала - JR_NOLOG; journald - как в r16 (без «joint»), обрезка head -80 помечается J_CUT.
# Запуск (WSL, низкий приоритет): nice -n 19 ionice -c3 bash tests/run_tests_r17a_pi.sh [папка для песочницы, по умолчанию /tmp]. Итог: «ИТОГ r17a Pi: PASS n, FAIL m».
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-${TMPDIR:-/tmp}}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r17api_XXXXXX")
PASS=0; FAIL=0
res() { if [ "$2" = 0 ]; then PASS=$((PASS+1)); echo "PASS $1"; else FAIL=$((FAIL+1)); echo "FAIL $1 ${3:-}"; fi; }
t() { local id="$1"; shift; if eval "$@"; then res "$id" 0; else res "$id" 1 "($*)"; fi; }
VM="$KIT/pi/vision_measure.sh"; H="$KIT/tests/r17a_wsl_vm.sh"
O="$W/out.txt"; E="$W/err.txt"
t "V0 bash -n vision_measure.sh и r17a_wsl_vm.sh" 'bash -n "$VM" && bash -n "$H"'
# код скрипта вне python-вставки: журнал стека только читается (нет записи в LOGF, нет rm, mv, cp, tee, truncate, sed -i)
SHC=$(awk '/<<.PY.$/{skip=1; next} /^PY$/{skip=0; next} !skip' "$VM" | grep -v '^[[:space:]]*#')
v0b() {
  printf '%s\n' "$SHC" | grep -q -E '(>|>>) *"?[$]LOGF' && return 1
  printf '%s\n' "$SHC" | grep -q -E '(^|[[:space:];|&(])(rm|mv|cp|tee|truncate|touch|chmod)[[:space:]]' && return 1
  printf '%s\n' "$SHC" | grep -q -F 'sed -i' && return 1
  printf '%s\n' "$SHC" | grep -q -F 'tail -c +$((LOG0 + 1)) "$LOGF"' || return 1
  [ "$(printf '%s\n' "$SHC" | grep -c -F 'LOGF')" -ge 4 ]
}
t "V0b vision_measure.sh вне python: журнал стека только читается (LOGF: присвоение, stat, -f, tail -c +LOG0+1, echo), записи и удаления нет" v0b
v0c() { grep -q -F 'LOGF="${BB_TEST_LOG:-/tmp/bumblebee.log}"' "$VM" && ! grep -q -F 'BB_TEST_LOG' "$KIT/run_measure.ps1" && ! grep -q -F 'BB_TEST_LOG' "$KIT/lib/bb_common.ps1"; }
t "V0c по умолчанию читается /tmp/bumblebee.log; BB_TEST_LOG - только тест (run_measure.ps1 и bb_common.ps1 его не задают)" v0c
t "V0d фильтр journald как в r16: слова «joint» в строке journalctl нет" '! grep "journalctl -u bumblebee" "$VM" | grep -q joint'
INIT=$(bash "$H" init "$W/vm" 2>&1); t "V0e поддельное окружение готово" 'printf "%s" "$INIT" | grep -q "VM17A_OK $W/vm"'
run() { local n="$1"; CASE=$(bash "$H" case "$W/vm" "$n" 2>&1 | sed -n "s/^CASE17A_OK $n //p"); PRE=""; [ -f "$CASE/bumblebee.log" ] && PRE=$(cat "$CASE/bumblebee.log"); bash "$W/vm/vm_runner.sh" 12 hand_center measure 1 < "$VM" > "$O" 2> "$E"; RC=$?; }
jr() { grep -c '^JR ' "$O"; }
run joint
t "V1 joint: код 0, BB_BENCH_DONE rc=0; ровно 3 строки JR (median 1.23, MAP != FIELD? 3.10, cleared 1.50 - по порядку), JR_COUNT 3; СТАРЫХ строк (9.91, 9.92) нет; JR_CUT, JR_NOLOG нет" '[ $RC = 0 ] && grep -q -x "BB_BENCH_DONE rc=0" "$O" && [ "$(jr)" = 3 ] && [ "$(grep "^JR " "$O" | sed -n 1p | grep -c "joint rms median 1.23 px")" = 1 ] && [ "$(grep "^JR " "$O" | sed -n 2p | grep -c "MAP != FIELD? joint PnP rms median 3.10")" = 1 ] && [ "$(grep "^JR " "$O" | sed -n 3p | grep -c "map mismatch cleared (rms median 1.50")" = 1 ] && grep -q -x "JR_COUNT 3" "$O" && ! grep -q -E "9\.91|9\.92" "$O" && ! grep -q -E "^JR_(CUT|NOLOG)" "$O"'
t "V1b joint: строка JR - целиком строка журнала стека (с [aruco_detect.py-19] [INFO ...]); строки JR - после python и до BB_BENCH_DONE" 'grep -q -x "JR \[aruco_detect.py-19\] \[INFO 1793342400.201\] \[aruco_detect\]: aruco_detect: joint rms median 1.23 px (2 s, n=12)" "$O" && [ "$(grep -n "^META python_exit" "$O" | cut -d: -f1)" -lt "$(grep -n "^JR " "$O" | head -1 | cut -d: -f1)" ] && [ "$(grep -n "^JR_COUNT" "$O" | cut -d: -f1)" -lt "$(grep -n "^BB_BENCH_DONE" "$O" | cut -d: -f1)" ]'
v1c() { [ "$(cat "$CASE/bumblebee.log")" = "$(printf '%s\n' "$PRE"; cat "$CASE/append.txt")" ] && [ "$(wc -l < "$CASE/bumblebee.log")" = 8 ]; }
t "V1c joint: журнал стека скриптом не изменён (после замера = журнал до замера + строки «детектора»)" v1c
run none
t "V2 none: строк joint за замер нет - JR_COUNT 0, ни одной строки JR (старые не берутся), код 0" '[ $RC = 0 ] && [ "$(jr)" = 0 ] && grep -q -x "JR_COUNT 0" "$O" && ! grep -q -E "9\.91|9\.92" "$O"'
run many
t "V3 many: 75 строк - показаны первые 60 (n=1..60), JR_CUT shown=60 total=75, JR_COUNT 75" '[ $RC = 0 ] && [ "$(jr)" = 60 ] && grep -q -x "JR_CUT shown=60 total=75" "$O" && grep -q -x "JR_COUNT 75" "$O" && grep "^JR " "$O" | head -1 | grep -q "n=1)" && grep "^JR " "$O" | tail -1 | grep -q "n=60)" && ! grep -q "n=61)" "$O"'
run nolog
t "V4 nolog: файла журнала нет - JR_NOLOG, JR_COUNT нет, строк JR нет, код 0 (замер записан)" '[ $RC = 0 ] && grep -q -x "JR_NOLOG" "$O" && ! grep -q "^JR_COUNT" "$O" && [ "$(jr)" = 0 ] && [ ! -e "$CASE/bumblebee.log" ]'
run nolognew
t "V4b nolognew: журнала до замера не было (размер не прочитан), появился во время замера - JR_NOLOG (без данных, а не «весь файл»)" '[ $RC = 0 ] && grep -q -x "JR_NOLOG" "$O" && [ "$(jr)" = 0 ] && ! grep -q "^JR_COUNT" "$O"'
run trunc
t "V5 trunc: журнал во время замера укорочен - JR_NOTE «log shrank», читаются новые строки (2), старых нет" '[ $RC = 0 ] && grep -q -x "JR_NOTE log shrank, reading all" "$O" && [ "$(jr)" = 2 ] && grep -q -x "JR_COUNT 2" "$O" && ! grep -q -E "9\.91|9\.92" "$O"'
run pyfail
t "V6 pyfail: замер упал (python код 1) - строк JR/JR_COUNT/JR_NOLOG/J нет, BB_BENCH_DONE rc=1, код 1" '[ $RC = 1 ] && grep -q -x "BB_BENCH_DONE rc=1" "$O" && ! grep -q -E "^(JR|JR_COUNT|JR_NOLOG|JR_CUT|JR_NOTE|J|J_CUT)( |$)" "$O"'
run jcut
t "V7 jcut: journald 95 нужных строк - J 80 и J_CUT shown=80 total=95; строк journald со словом joint в J нет; JR из журнала стека 1" '[ $RC = 0 ] && [ "$(grep -c "^J " "$O")" = 80 ] && grep -q -x "J_CUT shown=80 total=95" "$O" && ! grep "^J " "$O" | grep -q joint && [ "$(jr)" = 1 ] && grep -q -x "JR_COUNT 1" "$O"'
run joint
t "V7b joint (journald пуст): одна строка «J (... нужных строк нет ...)», J_CUT нет" '[ "$(grep -c "^J " "$O")" = 1 ] && grep -q "^J (в журнале bumblebee за время замера нужных строк нет" "$O" && ! grep -q "^J_CUT" "$O"'
run long
t "V8 long: строка joint длиннее 300 - в JR обрезана до 220 символов" '[ "$(jr)" = 1 ] && [ "$(grep "^JR " "$O" | awk "{print length}")" -le 223 ] && [ "$(grep "^JR " "$O" | awk "{print length}")" -ge 200 ]'
( export PATH="/usr/bin:/bin"; bash "$VM" 12 hand_center measure 1 > "$O" 2> "$E" < /dev/null ); RC=$?
t "V9 на чужом hostname (WSL): код 1, STOP, вывода нет (как в r16/r17)" '[ $RC = 1 ] && grep -q "STOP: hostname is" "$E" && [ ! -s "$O" ]'
echo ""
echo "ИТОГ r17a Pi: PASS $PASS, FAIL $FAIL (песочница $W)"
[ "$FAIL" = 0 ]
