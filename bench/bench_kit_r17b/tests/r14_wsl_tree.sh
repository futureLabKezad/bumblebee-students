#!/bin/bash
# r14_wsl_tree.sh (Claude, 17.11.2026, набор r14) - ТОЛЬКО ДЛЯ ТЕСТОВ, в WSL, без дрона. Поддельный «дом дрона» для сквозных тестов 09 и 15 (r14: камера r2m_cam).
# Дом и варианты r2j/jd2/... строит tests/r13_wsl_tree.sh (образы в /work - только чтение); здесь поверх него меняются только два файла оверлея, которые ставит пакет
# drone_pkg_r2m_cam_20261117: ~/bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py и .../share/bumblebee/launch/bumblebee.launch.py (копии в ~/ros2_ws остаются r2j, как после 44).
# Файлы r2m_cam - ТОЛЬКО ЧТЕНИЕМ из /work/image_r2m_cam_20261117; «чужие» - camera_fix.py варианта r2j_cam из набора (dabd5076) и launch r2k (/work/image_r2k_20261117). Пишется только в <база>.
# Команды:
#   init <база>                     - r13_wsl_tree.sh init + строки SHA_R2M_*; печатает TREE14_OK
#   variant <база> <основа> <камера> - основа: вариант r13_wsl_tree.sh (r2j | jd2 | jd | jd2_real | jd2_as_vpe ...);
#                                     камера: r2j | r2m | cam_only (только camera_fix r2m) | launch_only (только launch r2m) | cam_other (camera_fix r2j_cam) | launch_other (launch r2k)
#                                             | cam_as_vpe (camera_fix r2m под именем vpe_fix.py) | launch_as_main (launch r2m под именем main_camera.launch.py)
set -eu
CMD="${1:-}"; B="${2:-}"
KIT="$(cd "$(dirname "$0")/.." && pwd)"
M=/work/image_r2m_cam_20261117; K2=/work/image_r2k_20261117
MC="$M/install/bumblebee/lib/bumblebee/camera_fix.py"; ML="$M/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py"
case "$B" in /tmp/*|/mnt/*) ;; *) echo "STOP: база должна быть в /tmp или /mnt: $B" >&2; exit 2;; esac
H="$B/home"; P="$H/bench_ws/r2j/install/bumblebee"; L="$P/share/bumblebee/launch"
case "$CMD" in
init)
  [ -f "$MC" ] && [ -f "$ML" ] && [ -f "$M/src/bumblebee/src/python/camera_fix.py" ] && [ -f "$M/src/bumblebee/launch/bumblebee.launch.py" ] || { echo "STOP: нет образа r2m_cam в /work" >&2; exit 2; }
  bash "$KIT/tests/r13_wsl_tree.sh" init "$B"
  echo "SHA_R2M_CAM $(sha256sum "$MC" | cut -c1-64)"
  echo "SHA_R2M_CAM_SRC $(sha256sum "$M/src/bumblebee/src/python/camera_fix.py" | cut -c1-64)"
  echo "SHA_R2M_LAUNCH $(sha256sum "$ML" | cut -c1-64)"
  echo "SHA_R2M_LAUNCH_SRC $(sha256sum "$M/src/bumblebee/launch/bumblebee.launch.py" | cut -c1-64)"
  echo "TREE14_OK $B"
  ;;
variant)
  V="${3:-}"; C="${4:-}"
  bash "$KIT/tests/r13_wsl_tree.sh" variant "$B" "$V" > /dev/null
  case "$C" in
    r2j) ;;
    r2m) cp "$MC" "$P/lib/bumblebee/camera_fix.py"; cp "$ML" "$L/bumblebee.launch.py" ;;
    cam_only) cp "$MC" "$P/lib/bumblebee/camera_fix.py" ;;
    launch_only) cp "$ML" "$L/bumblebee.launch.py" ;;
    cam_other) cp "$MC" "$P/lib/bumblebee/camera_fix.py"; cp "$ML" "$L/bumblebee.launch.py"; cp "$KIT/image_r2j_cam/payload/bench_ws/r2j/install/bumblebee/lib/bumblebee/camera_fix.py" "$P/lib/bumblebee/camera_fix.py" ;;
    launch_other) cp "$MC" "$P/lib/bumblebee/camera_fix.py"; cp "$K2/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py" "$L/bumblebee.launch.py" ;;
    cam_as_vpe) cp "$MC" "$P/lib/bumblebee/vpe_fix.py" ;;
    launch_as_main) cp "$ML" "$L/main_camera.launch.py" ;;
    *) echo "STOP: камера $C" >&2; exit 2 ;;
  esac
  touch "$P/lib/bumblebee/"*
  echo "VARIANT14_OK $V $C aruco=$(sha256sum "$P/lib/bumblebee/aruco_detect.py" | cut -c1-16) cam=$(sha256sum "$P/lib/bumblebee/camera_fix.py" | cut -c1-16) vpe=$(sha256sum "$P/lib/bumblebee/vpe_fix.py" | cut -c1-16) launch=$(sha256sum "$L/bumblebee.launch.py" | cut -c1-16) main=$(sha256sum "$L/main_camera.launch.py" | cut -c1-16)"
  ;;
*) echo "STOP: команда init|variant" >&2; exit 2 ;;
esac
