#!/bin/bash
# mutation_check_r7_pi.sh (Claude, 13.11.2026, набор r7) - «у тестов есть зубы» для tests/run_tests_r7_pi.sh: на КОПИИ (в песочнице WSL) портит по одному месту
# в pi/r7_marker_ids.sh, в копии манифеста и в копии image_install.sh и проверяет, что тест ловит порчу ровно в ожидаемых проверках. Сам набор не меняет,
# к дрону не обращается. Сначала прогон копии без порчи (M0: ждём FAIL 0).
# Запуск (WSL, низкий приоритет, один поток): nice -n 19 ionice -c3 bash proverka_r7/mutation_check_r7_pi.sh [папка песочницы, по умолчанию /tmp]
set -u
KIT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-/tmp}"
mkdir -p "$BASE"
W=$(mktemp -d "$BASE/r7mut_XXXXXX")
C="$W/kit"; mkdir -p "$C/pi" "$C/tests" "$C/image_r2j" "$W/sb"
cp "$KIT/pi/r7_marker_ids.sh" "$C/pi/"; cp "$KIT/tests/run_tests_r7_pi.sh" "$C/tests/"; cp -r "$KIT/tests/pystub_r7" "$C/tests/"
for f in image_install.sh image_rollback.sh image_target.conf image_manifest.final.tsv PAYLOAD_SOURCES_r2j.tsv; do cp "$KIT/image_r2j/$f" "$C/image_r2j/"; done
cp -r "$KIT/image_r2j/payload" "$C/image_r2j/"
fails() { bash "$C/tests/run_tests_r7_pi.sh" "$W/sb" 2>&1 | grep '^FAIL ' | awk '{print $2}' | sort -u | tr '\n' ' '; }
spoil() { # spoil <файл> <было> <стало>: заменяет первое вхождение, иначе код 3
  python3 - "$1" "$2" "$3" <<'PY'
import sys
f, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(f, encoding='utf-8').read()
if a not in t:
    sys.exit(3)
open(f, 'w', encoding='utf-8', newline='').write(t.replace(a, b, 1))
PY
}
OK=1
B0=$(fails)
echo "MUT M0 (без порчи): FAIL: ${B0:-нет}"
[ -z "$B0" ] || OK=0
mut() { # mut <id> <что> <ожидаемые FAIL через пробел> <файл> <было> <стало>
  local id="$1" what="$2" want="$3" f="$C/$4"
  cp "$f" "$W/orig"
  if ! spoil "$f" "$5" "$6"; then echo "MUT $id ($what): ПОРЧА НЕ ЛЕГЛА"; OK=0; return; fi
  local got; got=$(fails)
  cp "$W/orig" "$f"
  local w; w=$(printf '%s\n' $want | sort -u | tr '\n' ' ')
  if [ -z "$got" ]; then echo "MUT $id ($what): НЕ ПОЙМАНО"; OK=0
  elif [ "$got" = "$w" ]; then echo "MUT $id ($what): поймано, FAIL: $got"
  else echo "MUT $id ($what): поймано, но не там: FAIL: $got; ждали: $w"; OK=0; fi
}
mut P1 'нет проверки имени хоста' 'M1 M5' pi/r7_marker_ids.sh '[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }' 'true'
mut P2 'издатель в /aruco_detect/wake (детектор будится)' 'M3 M8' pi/r7_marker_ids.sh "    node.create_subscription(MarkerArray, '/aruco_detect/markers', on_markers, 10)" "    node.create_subscription(MarkerArray, '/aruco_detect/markers', on_markers, 10)
    node.create_publisher(MarkerArray, '/aruco_detect/wake', 10)"
mut P3 'взведённый дрон не отказ' 'M10' pi/r7_marker_ids.sh "    if st['a']:
        p('MN_REFUSED armed (" "    if False:
        p('MN_REFUSED armed ("
mut P4 'ros2 node list без --no-daemon (демон ros2)' 'M3 M9' pi/r7_marker_ids.sh 'echo "MN_META script' 'timeout 20 ros2 node list < /dev/null 2>/dev/null | head -1
echo "MN_META script'
mut P5 'нет остановки, если дрон взвели во время записи' 'M16' pi/r7_marker_ids.sh "        if st.get('a'):" "        if False:"
mut P6 'углы меток не пишутся' 'M13 M14' pi/r7_marker_ids.sh "parts.append('id=%d c=%s' % (i, corners(mk)))" "parts.append('id=%d' % i)"
mut P7 'скрипт пишет файл в HOME' 'M2 M9' pi/r7_marker_ids.sh 'echo "MN_META script' 'touch "$HOME/.bb_r7_x"
echo "MN_META script'
mut P8 'в манифесте нет строки hover r6' 'I3 I5 I6' image_r2j/image_manifest.final.tsv $'ros2_ws/src/bumblebee/examples/hover_marker0.py\ta11b195ce1507607967ff6a7402726d9eef7b4f12850a9e864f5ae27d1f513f7\n' ''
mut P9 'установщик без отказа при TBD' 'I1' image_r2j/image_install.sh 'case "${DEST_ROOT:-TBD}${BACKUP_ROOT:-TBD}" in *TBD*) echo "=== STOP: DEST_ROOT or BACKUP_ROOT is TBD"; exit 1;; esac' ':'
if [ "$OK" = 1 ]; then echo "ИТОГ мутаций r7 Pi: все порчи пойманы ровно в ожидаемых проверках, без порчи FAIL 0 (копия: $W)"; else echo "ИТОГ мутаций r7 Pi: ЕСТЬ НЕПОЙМАННЫЕ или лишние (копия: $W)"; fi
[ "$OK" = 1 ]
