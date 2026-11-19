#!/bin/bash
# r13_wsl_tree.sh (Claude, 17.11.2026, набор r13) - ТОЛЬКО ДЛЯ ТЕСТОВ, в WSL, без дрона. Поддельный «дом дрона» для сквозных тестов 09 и 15 через tests\fake_ssh_r13.cs.
# По образцу tests/r12_wsl_tree.sh набора r12 (в r11 его нет): дом r2j как на дроне после 05, 13 и 16 (оверлей ~/bench_ws/r2j, ~/ros2_ws/src), подделки hostname и ros2.
# Файлы берутся ТОЛЬКО ЧТЕНИЕМ: образ r2j /work/fixed_image_r2j_20261111, исправление порта /work/fcu_detect_fix_01, детекторы jd2 (/work/c6_fix_20261117/image_r2jd2)
# и jd (/work/c6_fix_20261117/image_r2jd, НЕ допускается), launch r2k (/work/image_r2k_20261117, в r13 НЕ допускается) и из набора; пишется только в <база>.
# Python-узлы кладутся туда же, куда их ставит пакет drone_pkg_posefix_jd2_20261117: ~/bench_ws/r2j/install/bumblebee/lib/bumblebee и ~/ros2_ws/src/bumblebee/src/python.
# runner13.sh запускает скрипт Pi с nice -n 19 ionice -c3 (в WSL идут серии Gazebo).
# Команды:
#   init <база>                 - дом r2j, подделки, runner13.sh; печатает sha детекторов (SHA_*)
#   variant <база> <вариант>    - r2j | jd2 | jd | jd2_as_vpe | jd2_as_cam | jd2_real | jd2_r2k | jd2_r2jcam | jd2_fcu_old (вариант ставится поверх r2j)
set -eu
CMD="${1:-}"; B="${2:-}"
KIT="$(cd "$(dirname "$0")/.." && pwd)"
I=/work/fixed_image_r2j_20261111; K2=/work/image_r2k_20261117; FCU=/work/fcu_detect_fix_01/scripts/fcu_detect.py
J2=/work/c6_fix_20261117/image_r2jd2/install/bumblebee/lib/bumblebee/aruco_detect.py
J2S=/work/c6_fix_20261117/image_r2jd2/src/bumblebee/src/python/aruco_detect.py
JD=/work/c6_fix_20261117/image_r2jd/install/bumblebee/lib/bumblebee/aruco_detect.py
case "$B" in /tmp/*|/mnt/*) ;; *) echo "STOP: база должна быть в /tmp или /mnt: $B" >&2; exit 2;; esac
H="$B/home"; FB="$B/fakebin"; P="$H/bench_ws/r2j/install/bumblebee"; S="$H/ros2_ws/src/bumblebee/src/python"
cpp_rel() { grep -v '^#' "$KIT/image_r2j/CPP_SOURCES_r2j.tsv" | cut -f2 | sed 's#^ros2_ws/src/bumblebee/##'; }
put_both() { cp "$1" "$P/lib/bumblebee/$2"; cp "$1" "$S/$2"; }
put_r2j() {
  cp "$I/install/bumblebee/share/bumblebee/launch/"*.py "$P/share/bumblebee/launch/"
  cp "$FCU" "$H/ros2_ws/src/bumblebee/scripts/fcu_detect.py"
  for t in "$H/ros2_ws/src/bumblebee" "$H/bench_ws/r2j/src/bumblebee"; do
    cp "$I/src/bumblebee/examples/flight/flight_marker.py" "$I/src/bumblebee/examples/flight/flight_marker_loop.py" "$t/examples/flight/"
  done
  for n in aruco_detect.py vpe_fix.py camera_fix.py; do cp "$I/install/bumblebee/lib/bumblebee/$n" "$P/lib/bumblebee/$n"; cp "$I/src/bumblebee/src/python/$n" "$S/$n"; done
}
case "$CMD" in
init)
  [ -d "$I/install/bumblebee" ] && [ -f "$FCU" ] && [ -f "$J2" ] && [ -f "$J2S" ] && [ -f "$JD" ] && [ -f "$K2/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" ] || { echo "STOP: нет образов r2j/r2k, детекторов jd2/jd или fcu_detect_fix_01 в /work" >&2; exit 2; }
  mkdir -p "$FB" "$P/lib/bumblebee" "$P/share/bumblebee/launch" "$H/ros2_ws/src/bumblebee/scripts" "$S"
  find "$I/install/bumblebee/lib/bumblebee" -maxdepth 1 -type f -exec cp {} "$P/lib/bumblebee/" \;
  for rel in $(cpp_rel); do
    for t in "$H/ros2_ws/src/bumblebee" "$H/bench_ws/r2j/src/bumblebee"; do mkdir -p "$(dirname "$t/$rel")"; cp "$I/src/bumblebee/$rel" "$t/$rel"; done
  done
  put_r2j
  # исходники «старые», бинарники «новые»: пакет пересобран (иначе 09 и 15 дадут STALE)
  find "$H/ros2_ws/src" "$H/bench_ws/r2j/src" -type f -exec touch -d '2026-01-01 00:00:00' {} +
  touch "$P/lib/bumblebee/"*
  printf '#!/bin/bash\necho "${FAKE_HOST:-bumblebee-20ec}"\n' > "$FB/hostname"
  cat > "$FB/ros2" <<'EOF'
#!/bin/bash
echo "ros2 $*" >> "$HOME/../ros2_calls.log"
case "$1 $2" in
  "pkg prefix") [ "${3:-}" = bumblebee ] && { echo "$HOME/bench_ws/r2j/install/bumblebee"; exit 0; }; exit 1 ;;
esac
echo "fake ros2: unexpected $*" >&2; exit 1
EOF
  chmod +x "$FB"/*
  printf '#!/bin/bash\nS=$(cat)\nexport HOME="%s" PATH="%s:/usr/bin:/bin"\nsource(){ :; }; export -f source\nexec nice -n 19 ionice -c3 bash -c "$S" _ "$@"\n' "$H" "$FB" > "$B/runner13.sh"
  chmod +x "$B/runner13.sh"
  echo "SHA_JD2 $(sha256sum "$J2" | cut -c1-64)"
  echo "SHA_JD2_SRC $(sha256sum "$J2S" | cut -c1-64)"
  echo "SHA_JD $(sha256sum "$JD" | cut -c1-64)"
  echo "SHA_R2J $(sha256sum "$I/install/bumblebee/lib/bumblebee/aruco_detect.py" | cut -c1-64)"
  echo "TREE13_OK $B"
  ;;
variant)
  V="${3:-}"; L="$P/share/bumblebee/launch"
  put_r2j
  case "$V" in
    r2j) ;;
    jd2) put_both "$J2" aruco_detect.py ;;
    jd) put_both "$JD" aruco_detect.py ;;
    jd2_as_vpe) put_both "$J2" vpe_fix.py ;;
    jd2_as_cam) put_both "$J2" camera_fix.py ;;
    jd2_real) put_both "$J2" aruco_detect.py
              for t in "$H/ros2_ws/src/bumblebee" "$H/bench_ws/r2j/src/bumblebee"; do cp "$KIT/real_map_20261116/flight_marker.py" "$KIT/real_map_20261116/flight_marker_loop.py" "$t/examples/flight/"; done ;;
    jd2_r2k) put_both "$J2" aruco_detect.py; cp "$K2/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" "$L/bumblebee.launch.py" ;;
    jd2_r2jcam) put_both "$J2" aruco_detect.py; cp "$KIT/image_r2j_cam/payload/bench_ws/r2j/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" "$L/bumblebee.launch.py" ;;
    jd2_fcu_old) put_both "$J2" aruco_detect.py; cp "$I/src/bumblebee/scripts/fcu_detect.py" "$H/ros2_ws/src/bumblebee/scripts/fcu_detect.py" ;;
    *) echo "STOP: вариант $V" >&2; exit 2 ;;
  esac
  touch -d '2026-01-01 00:00:00' "$H/ros2_ws/src/bumblebee/examples/flight/"*.py "$H/bench_ws/r2j/src/bumblebee/examples/flight/"*.py
  touch "$P/lib/bumblebee/"*
  echo "VARIANT13_OK $V aruco=$(sha256sum "$P/lib/bumblebee/aruco_detect.py" | cut -c1-16) vpe=$(sha256sum "$P/lib/bumblebee/vpe_fix.py" | cut -c1-16) cam=$(sha256sum "$P/lib/bumblebee/camera_fix.py" | cut -c1-16) launch=$(sha256sum "$L/bumblebee.launch.py" | cut -c1-16)"
  ;;
*) echo "STOP: команда init|variant" >&2; exit 2 ;;
esac
