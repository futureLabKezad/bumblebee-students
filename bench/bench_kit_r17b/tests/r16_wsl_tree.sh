#!/bin/bash
# r16_wsl_tree.sh (Claude, 18.11.2026, набор r16) - ТОЛЬКО ДЛЯ ТЕСТОВ, в WSL, без дрона. Поддельный «дом дрона» для сквозных тестов 09 и 15 (r16: вариант В1 - aruco_detect.py и vpe_fix.py).
# Дом, камеру r2m_cam и детекторы r2j/jd2/jd строят tests/r14_wsl_tree.sh и tests/r13_wsl_tree.sh (образы в /work - только чтение); здесь поверх них кладутся узлы В1
# туда же, куда их ставит пакет drone_pkg_posefix_v1_20261118 (как jd2): ~/bench_ws/r2j/install/bumblebee/lib/bumblebee и ~/ros2_ws/src/bumblebee/src/python.
# В1 - ТОЛЬКО ЧТЕНИЕМ из /work/jv1_20261118/image_r2jv1, jd3 (не допускается) - из /work/jd3_20261118/image_r2jd3. Пишется только в <база>.
# Команды:
#   init <база>                      - r14_wsl_tree.sh init + SHA_V1_*; печатает TREE16_OK
#   variant <база> <узлы> <камера>   - узлы: r2j | jd2 | jd | v1 (aruco и vpe В1) | v1_aruco (aruco В1, vpe r2j) | v1_vpe (aruco r2j, vpe В1) | jd2_vpe_v1 (aruco jd2, vpe В1)
#                                      | jd3 (aruco jd3) | v1_aruco_mod (aruco В1 + строка, vpe В1) | v1_vpe_mod (aruco В1, vpe В1 + строка) | v1_vpe_as_cam (vpe В1 под именем camera_fix.py);
#                                      камера: как в r14_wsl_tree.sh (r2j | r2m | cam_only ...)
set -eu
CMD="${1:-}"; B="${2:-}"
KIT="$(cd "$(dirname "$0")/.." && pwd)"
I=/work/jv1_20261118/image_r2jv1
VA="$I/install/bumblebee/lib/bumblebee/aruco_detect.py"; VV="$I/install/bumblebee/lib/bumblebee/vpe_fix.py"
J3=/work/jd3_20261118/image_r2jd3/install/bumblebee/lib/bumblebee/aruco_detect.py
case "$B" in /tmp/*|/mnt/*) ;; *) echo "STOP: база должна быть в /tmp или /mnt: $B" >&2; exit 2;; esac
H="$B/home"; P="$H/bench_ws/r2j/install/bumblebee"; S="$H/ros2_ws/src/bumblebee/src/python"
put_both() { cp "$1" "$P/lib/bumblebee/$2"; cp "$1" "$S/$2"; }
case "$CMD" in
init)
  [ -f "$VA" ] && [ -f "$VV" ] && [ -f "$I/src/bumblebee/src/python/aruco_detect.py" ] && [ -f "$I/src/bumblebee/src/python/vpe_fix.py" ] && [ -f "$J3" ] || { echo "STOP: нет образа В1 или jd3 в /work" >&2; exit 2; }
  bash "$KIT/tests/r14_wsl_tree.sh" init "$B"
  echo "SHA_V1_ARUCO $(sha256sum "$VA" | cut -c1-64)"
  echo "SHA_V1_ARUCO_SRC $(sha256sum "$I/src/bumblebee/src/python/aruco_detect.py" | cut -c1-64)"
  echo "SHA_V1_VPE $(sha256sum "$VV" | cut -c1-64)"
  echo "SHA_V1_VPE_SRC $(sha256sum "$I/src/bumblebee/src/python/vpe_fix.py" | cut -c1-64)"
  echo "SHA_JD3 $(sha256sum "$J3" | cut -c1-64)"
  echo "TREE16_OK $B"
  ;;
variant)
  V="${3:-}"; C="${4:-}"
  case "$V" in r2j|jd2|jd) base="$V";; jd2_vpe_v1) base=jd2;; v1|v1_aruco|v1_vpe|jd3|v1_aruco_mod|v1_vpe_mod|v1_vpe_as_cam) base=r2j;; *) echo "STOP: узлы $V" >&2; exit 2;; esac
  bash "$KIT/tests/r14_wsl_tree.sh" variant "$B" "$base" "$C" > /dev/null
  L="$P/lib/bumblebee"
  case "$V" in
    v1) put_both "$VA" aruco_detect.py; put_both "$VV" vpe_fix.py ;;
    v1_aruco) put_both "$VA" aruco_detect.py ;;
    v1_vpe|jd2_vpe_v1) put_both "$VV" vpe_fix.py ;;
    jd3) put_both "$J3" aruco_detect.py ;;
    v1_aruco_mod) put_both "$VV" vpe_fix.py; { cat "$VA"; echo "# x"; } > "$L/aruco_detect.py" ;;
    v1_vpe_mod) put_both "$VA" aruco_detect.py; { cat "$VV"; echo "# x"; } > "$L/vpe_fix.py" ;;
    v1_vpe_as_cam) cp "$VV" "$L/camera_fix.py" ;;
  esac
  touch "$L/"*
  echo "VARIANT16_OK $V $C aruco=$(sha256sum "$L/aruco_detect.py" | cut -c1-16) vpe=$(sha256sum "$L/vpe_fix.py" | cut -c1-16) cam=$(sha256sum "$L/camera_fix.py" | cut -c1-16) launch=$(sha256sum "$P/share/bumblebee/launch/bumblebee.launch.py" | cut -c1-16)"
  ;;
*) echo "STOP: команда init|variant" >&2; exit 2 ;;
esac
