#!/bin/bash
# r17a_wsl_vm.sh (Claude, 19.11.2026, набор r17a) - ТОЛЬКО ДЛЯ ТЕСТОВ, в WSL, без дрона и без sudo. Поддельное окружение для настоящего pi/vision_measure.sh (шаг 03):
# подделки hostname (bumblebee-20ec), python3 (вместо замера: читает скрипт со stdin, дописывает заготовленные строки «детектора» в ТЕСТОВЫЙ журнал стека,
# печатает строку SUMMARY markers_used), journalctl (печатает заготовку). Журнал стека - <папка случая>/bumblebee.log через BB_TEST_LOG (как в r8_marker_wake.sh);
# настоящий /tmp/bumblebee.log не читается и не трогается. Пишется только в <база>; ничего не удаляется (каждый случай - новая папка).
# Команды:
#   init <база>          - подделки и <база>/vm_runner.sh (скрипт Pi со stdin, аргументы как у ssh после «_»; nice -n 19 ionice -c3); печатает VM17A_OK <база>
#   case <база> <имя>    - новая папка случая (журнал до замера, строки, которые «детектор» допишет во время замера, journald), она же текущая; печатает CASE17A_OK <имя> <папка>
#     joint  - в журнале до замера СТАРЫЕ строки joint (9.91/9.92); во время замера: median 1.23, MAP != FIELD? 3.10, cleared 1.50 и посторонние строки
#     none   - старые строки joint есть, новых нет
#     many   - 75 новых строк «joint rms median» (n=1..75)
#     nolog  - файла журнала нет
#     nolognew - файла журнала до замера нет, он появляется во время замера (размер до замера не прочитан)
#     trunc  - журнал во время замера укорочен (перезапуск стека) и в нём 2 новые строки joint
#     pyfail - замер упал (python3 код 1), строки joint дописаны
#     jcut   - journald: 95 нужных строк и 3 строки joint; в журнале стека 1 новая строка joint
#     long   - новая строка joint длиной больше 300 символов
set -eu
CMD="${1:-}"; B="${2:-}"
case "$B" in /tmp/?*) ;; *) echo "STOP: база должна быть в /tmp: '$B'" >&2; exit 2;; esac
FB="$B/fb"
L() { printf '[aruco_detect.py-19] [%s 1793342400.%s] [aruco_detect]: aruco_detect: %s\n' "$1" "$2" "$3"; }
case "$CMD" in
init)
  mkdir -p "$FB" "$B/home"
  printf '#!/bin/bash\necho bumblebee-20ec\n' > "$FB/hostname"
  cat > "$FB/python3" <<'EOF'
#!/bin/bash
cat > /dev/null
C="${BB17A_CASE_DIR:?}"
if [ -f "$C/trunc" ]; then : > "$BB_TEST_LOG"; fi
if [ -f "$C/append.txt" ]; then cat "$C/append.txt" >> "$BB_TEST_LOG"; fi
echo "SUMMARY markers_used msgs=732 with_ge1=700 (95.6%) with_0=32 hz_all=6.10"
exit "$(cat "$C/py_rc" 2>/dev/null || echo 0)"
EOF
  cat > "$FB/journalctl" <<'EOF'
#!/bin/bash
C="${BB17A_CASE_DIR:?}"
if [ -f "$C/journal.txt" ]; then cat "$C/journal.txt"; fi
exit 0
EOF
  printf '#!/bin/bash\nS=$(cat)\nC=$(cat "%s/current")\nexport HOME="%s/home" PATH="%s:/usr/bin:/bin" BB_TEST_LOG="$C/bumblebee.log" BB17A_CASE_DIR="$C"\nsource(){ :; }; export -f source\nexec nice -n 19 ionice -c3 bash -c "$S" _ "$@"\n' "$B" "$B" "$FB" > "$B/vm_runner.sh"
  chmod +x "$FB"/* "$B/vm_runner.sh"
  echo "VM17A_OK $B"
  ;;
case)
  N="${3:-}"
  C=$(mktemp -d "$B/case_${N}_XXXXXX")
  OLD1=$(L INFO 100 'joint rms median 9.91 px (2 s, n=11)'); OLD2=$(L WARN 101 'MAP != FIELD? joint PnP rms median 9.92 px over 2 s (> 2.5)')
  NOISE='[vpe_fix.py-20] [INFO 1793342400.200] [vpe_publisher]: vpe_fix gate: ok'
  case "$N" in
    joint)  printf '%s\n%s\n%s\n' "$OLD1" "$OLD2" "$NOISE" > "$C/bumblebee.log"
            { echo "$NOISE"; L INFO 201 'joint rms median 1.23 px (2 s, n=12)'; L WARN 202 'MAP != FIELD? joint PnP rms median 3.10 px over 2 s (> 2.5)'; L INFO 203 'map mismatch cleared (rms median 1.50 px)'; L INFO 204 'aruco: detection ACTIVE (armed=False)'; } > "$C/append.txt";;
    none)   printf '%s\n%s\n%s\n' "$OLD1" "$OLD2" "$NOISE" > "$C/bumblebee.log"
            { echo "$NOISE"; L INFO 204 'aruco: detection ACTIVE (armed=False)'; } > "$C/append.txt";;
    many)   printf '%s\n' "$NOISE" > "$C/bumblebee.log"
            for i in $(seq 1 75); do L INFO "$((300 + i))" "joint rms median 1.$((10 + i)) px (2 s, n=$i)"; done > "$C/append.txt";;
    nolog)  : ;;
    nolognew) { L INFO 201 'joint rms median 1.23 px (2 s, n=12)'; } > "$C/append.txt";;
    trunc)  printf '%s\n%s\n%s\n' "$OLD1" "$OLD2" "$NOISE" > "$C/bumblebee.log"; : > "$C/trunc"
            { L INFO 211 'joint rms median 1.31 px (2 s, n=13)'; L INFO 212 'joint rms median 1.32 px (2 s, n=14)'; } > "$C/append.txt";;
    pyfail) printf '%s\n' "$NOISE" > "$C/bumblebee.log"; echo 1 > "$C/py_rc"
            { L INFO 201 'joint rms median 1.23 px (2 s, n=12)'; } > "$C/append.txt";;
    jcut)   printf '%s\n' "$NOISE" > "$C/bumblebee.log"
            { L INFO 201 'joint rms median 1.23 px (2 s, n=12)'; } > "$C/append.txt"
            { for i in $(seq 1 95); do echo "aruco: detection ACTIVE k=$i"; done; for i in 1 2 3; do echo "aruco_detect: joint rms median 5.0$i px (2 s, n=1$i)"; done; } > "$C/journal.txt";;
    long)   printf '%s\n' "$NOISE" > "$C/bumblebee.log"
            { L INFO 221 "joint rms median 1.41 px (2 s, n=15) $(printf 'x%.0s' $(seq 1 300))"; } > "$C/append.txt";;
    *) echo "STOP: неизвестный случай '$N'" >&2; exit 2;;
  esac
  printf '%s' "$C" > "$B/current"
  echo "CASE17A_OK $N $C"
  ;;
*) echo "STOP: команда init | case" >&2; exit 2;;
esac
