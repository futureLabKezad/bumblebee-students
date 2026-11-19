#!/bin/bash
# r17_wsl_tree.sh (Claude, 19.11.2026, набор r17) - ТОЛЬКО ДЛЯ ТЕСТОВ, в WSL, без дрона. Поддельный «дом дрона» для сквозных тестов 09 и 15 (r17: вариант В1.1).
# Дом, камеру r2m_cam, детекторы r2j/jd2/jd/jd3 и старый В1 строят tests/r16_wsl_tree.sh, r14_wsl_tree.sh, r13_wsl_tree.sh (образы в /work - только чтение);
# здесь поверх них кладутся узлы В1.1 туда же, куда их ставит пакет (как jd2/В1): ~/bench_ws/r2j/install/bumblebee/lib/bumblebee и ~/ros2_ws/src/bumblebee/src/python.
# В1.1 - ТОЛЬКО ЧТЕНИЕМ из /work/jv11_20261119/image_r2jv11. Пишется только в <база>.
# Команды:
#   init <база>                      - r16_wsl_tree.sh init + SHA_V11_*; печатает TREE17_OK
#   variant <база> <узлы> <камера>   - узлы: варианты r16 (r2j | jd2 | jd | jd3 | v1 | v1_vpe | jd2_vpe_v1) и v11 (aruco и vpe В1.1) | v11_aruco (aruco В1.1, vpe r2j)
#                                      | v11_mod (aruco В1.1 + строка, vpe В1.1) | v1a_v11 (aruco старый В1, vpe В1.1 - как после r16); камера: как в r14_wsl_tree.sh
set -eu
CMD="${1:-}"; B="${2:-}"
KIT="$(cd "$(dirname "$0")/.." && pwd)"
I=/work/jv11_20261119/image_r2jv11
VA="$I/install/bumblebee/lib/bumblebee/aruco_detect.py"; VV="$I/install/bumblebee/lib/bumblebee/vpe_fix.py"
case "$B" in /tmp/*|/mnt/*) ;; *) echo "STOP: база должна быть в /tmp или /mnt: $B" >&2; exit 2;; esac
H="$B/home"; P="$H/bench_ws/r2j/install/bumblebee"; S="$H/ros2_ws/src/bumblebee/src/python"
put_both() { cp "$1" "$P/lib/bumblebee/$2"; cp "$1" "$S/$2"; }
case "$CMD" in
init)
  [ -f "$VA" ] && [ -f "$VV" ] && [ -f "$I/src/bumblebee/src/python/aruco_detect.py" ] && [ -f "$I/src/bumblebee/src/python/vpe_fix.py" ] || { echo "STOP: нет образа В1.1 в /work/jv11_20261119" >&2; exit 2; }
  bash "$KIT/tests/r16_wsl_tree.sh" init "$B"
  echo "SHA_V11_ARUCO $(sha256sum "$VA" | cut -c1-64)"
  echo "SHA_V11_ARUCO_SRC $(sha256sum "$I/src/bumblebee/src/python/aruco_detect.py" | cut -c1-64)"
  echo "SHA_V11_VPE $(sha256sum "$VV" | cut -c1-64)"
  echo "SHA_V11_VPE_SRC $(sha256sum "$I/src/bumblebee/src/python/vpe_fix.py" | cut -c1-64)"
  echo "TREE17_OK $B"
  ;;
variant)
  V="${3:-}"; C="${4:-}"
  case "$V" in r2j|jd2|jd|jd3|v1|v1_vpe|jd2_vpe_v1) base="$V";; v11|v11_aruco|v11_mod) base=r2j;; v1a_v11) base=v1;; *) echo "STOP: узлы $V" >&2; exit 2;; esac
  bash "$KIT/tests/r16_wsl_tree.sh" variant "$B" "$base" "$C" > /dev/null
  L="$P/lib/bumblebee"
  case "$V" in
    v11) put_both "$VA" aruco_detect.py; put_both "$VV" vpe_fix.py ;;
    v11_aruco) put_both "$VA" aruco_detect.py ;;
    v11_mod) put_both "$VV" vpe_fix.py; { cat "$VA"; echo "# x"; } > "$L/aruco_detect.py" ;;
    v1a_v11) put_both "$VV" vpe_fix.py ;;
  esac
  touch "$L/"*
  echo "VARIANT17_OK $V $C aruco=$(sha256sum "$L/aruco_detect.py" | cut -c1-16) vpe=$(sha256sum "$L/vpe_fix.py" | cut -c1-16) cam=$(sha256sum "$L/camera_fix.py" | cut -c1-16) launch=$(sha256sum "$P/share/bumblebee/launch/bumblebee.launch.py" | cut -c1-16)"
  ;;
*) echo "STOP: команда init|variant" >&2; exit 2 ;;
esac
