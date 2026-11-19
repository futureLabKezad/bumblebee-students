#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2; решение чата 1 в 19:58). Проверка перед сборкой пакета bumblebee из исходников r2j на Pi (13_sborka_bumblebee_r2j.cmd).
# Ничего не пишет на дрон, файлов на Pi не создаёт, ничего не останавливает и не запускает. Список «sha256  путь  флаг» (C++ исходники и файлы сборки r2j) подставляет ПК вместо строки #@@CPP@@ в памяти; sha256 скрипта висения hover r6 вместо #@@HOVER@@ (r3).
# Условия (иначе STOP): служба bumblebee НЕ активна (останавливает владелец сам, с паролем); исходники образа уже стоят в ~/ros2_ws/src/bumblebee и их sha256 сходятся с r2j (значит, установка образа 05 сделана);
# ~/bench_ws/r2j ещё нет (ничего не перезаписывается); нет ~/.colcon/defaults.yaml (он тихо меняет сборку); свободно на диске не меньше 3000 МБ; нет запущенных colcon, cmake, make, cc1plus;
# нужные пакеты apt стоят (как в проверке 29.10, набор s0b: step8b_build.sh).
# stdout: BBPRE <ключ> <значение>, BB_BBPRE_RESULT OK или STOP <причины>, BB_BBPRE_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
# BB_BBPRE_MARK
CPP='
#@@CPP@@
'
HOVERTXT='
#@@HOVER@@
'
HOVER=$(printf '%s\n' "$HOVERTXT" | grep -E '^[0-9a-f]{64}$' | head -1)
why=""
svc=$(systemctl is-active bumblebee 2>&1 | head -1)
echo "BBPRE service_bumblebee $svc"
[ "$svc" = "active" ] && why="$why служба_bumblebee_активна(остановите_сами_sudo_systemctl_stop_bumblebee)"
if [ -e "$HOME/bench_ws/r2j" ]; then echo "BBPRE exists $HOME/bench_ws/r2j"; why="$why уже_есть_bench_ws_r2j"; else echo "BBPRE absent $HOME/bench_ws/r2j"; fi
if [ -e "$HOME/.colcon/defaults.yaml" ]; then echo "BBPRE colcon_defaults present"; why="$why есть_colcon_defaults"; else echo "BBPRE colcon_defaults absent"; fi
ok=0; bad=0
while read -r want path flag; do
  case "$want" in ''|\#*) continue;; esac
  f="$HOME/$path"
  if [ ! -f "$f" ]; then echo "BBPRE src MISSING $path"; bad=$((bad+1)); continue; fi
  got=$(sha256sum "$f" 2>/dev/null | cut -c1-64)
  if [ "$got" = "$want" ]; then ok=$((ok+1)); else echo "BBPRE src DIFF $path"; bad=$((bad+1)); fi
done <<< "$CPP"
echo "BBPRE src_ok=$ok src_bad=$bad"
# r3 (замечание проверки 11.11): скрипт висения hover r6 (sha256 из required_shas.txt, подставляет ПК) должен лежать в ~/ros2_ws/src/bumblebee/examples (так он попадёт в копию оверлея, и 07 сверит его перед отсчётом)
if [ -z "$HOVER" ]; then echo "BBPRE hover_r6 NOSHA"; why="$why нет_суммы_hover_r6_в_скрипте"; else
  hv=$(find "$HOME/ros2_ws/src/bumblebee/examples" -type f -name '*.py' -exec sha256sum {} + 2>/dev/null | grep -c "^$HOVER ")
  echo "BBPRE hover_r6 found=$hv"
  [ "${hv:-0}" -ge 1 ] || why="$why нет_hover_r6_в_ros2_ws_src_bumblebee_examples(сначала_05_install_r2j)"
fi
[ "$bad" -gt 0 ] && why="$why исходники_не_равны_r2j(сначала_05_install_r2j)"
free=$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
echo "BBPRE disk_free_mb ${free:-unknown}"
if [ -z "$free" ] || [ "$free" -lt 3000 ]; then why="$why мало_места_на_диске"; fi
busy=$(ps -eo comm= 2>/dev/null | grep -c -E '^(colcon|cmake|make|cc1plus)$')
echo "BBPRE builders_running $busy"
[ "${busy:-0}" -gt 0 ] && why="$why идёт_сборка"
dpkg-query -W -f='${Package} ${db:Status-Abbrev} ${Version}\n' ros-jazzy-ament-cmake ros-jazzy-ament-cmake-python ros-jazzy-rosidl-default-generators ros-jazzy-rosidl-default-runtime ros-jazzy-rclcpp ros-jazzy-rclcpp-components ros-jazzy-rclpy ros-jazzy-rcl-interfaces ros-jazzy-rosgraph-msgs ros-jazzy-std-msgs ros-jazzy-std-srvs ros-jazzy-geometry-msgs ros-jazzy-sensor-msgs ros-jazzy-visualization-msgs ros-jazzy-tf2 ros-jazzy-tf2-ros ros-jazzy-tf2-geometry-msgs ros-jazzy-mavros-msgs ros-jazzy-cv-bridge ros-jazzy-image-transport ros-jazzy-image-proc ros-jazzy-image-geometry libopencv-dev libgeographiclib-dev python3-yaml 2>&1 | while IFS= read -r l; do echo "BBPRE dep $l"; done
nd=$(dpkg-query -W -f='${db:Status-Abbrev}\n' ros-jazzy-ament-cmake ros-jazzy-ament-cmake-python ros-jazzy-rosidl-default-generators ros-jazzy-rosidl-default-runtime ros-jazzy-rclcpp ros-jazzy-rclcpp-components ros-jazzy-rclpy ros-jazzy-rcl-interfaces ros-jazzy-rosgraph-msgs ros-jazzy-std-msgs ros-jazzy-std-srvs ros-jazzy-geometry-msgs ros-jazzy-sensor-msgs ros-jazzy-visualization-msgs ros-jazzy-tf2 ros-jazzy-tf2-ros ros-jazzy-tf2-geometry-msgs ros-jazzy-mavros-msgs ros-jazzy-cv-bridge ros-jazzy-image-transport ros-jazzy-image-proc ros-jazzy-image-geometry libopencv-dev libgeographiclib-dev python3-yaml 2>/dev/null | grep -c -v '^ii')
[ "${nd:-1}" != "0" ] && why="$why не_все_пакеты_apt_стоят"
echo "BBPRE live_prefix $(timeout 30 ros2 pkg prefix bumblebee < /dev/null 2>/dev/null | head -1)"
echo "BBPRE uname $(uname -srm)"
if [ -z "$why" ]; then echo "BB_BBPRE_RESULT OK"; else echo "BB_BBPRE_RESULT STOP$why"; fi
echo "BB_BBPRE_DONE"
