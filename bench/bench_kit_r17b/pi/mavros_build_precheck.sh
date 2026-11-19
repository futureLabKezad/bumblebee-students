#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026, набор r2; решение чата 1 в 19:45). Проверка перед сборкой MAVROS bp02 на Pi (11_sborka_mavros_bp02.cmd): можно ли начинать и в каком состоянии apt-MAVROS сейчас.
# Ничего не пишет на дрон, файлов на Pi не создаёт, ничего не останавливает и не запускает.
# Условия начала (иначе STOP): служба bumblebee НЕ активна (её останавливает владелец сам, с паролем: правило 7); ~/bench_ws/mavros и ~/bench_ws/incoming/rc3_mavros ещё не существуют (сборка ничего не перезаписывает);
# свободно на диске не меньше 3000 МБ; нет запущенных colcon, cmake, make, cc1plus. Дополнительно печатается состояние apt-MAVROS (это «резерв нынешнего состояния»: сборка apt не меняет).
# stdout: MBPRE <ключ> <значение>, в конце BB_MBPRE_RESULT OK или STOP <причины>, BB_MBPRE_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
# BB_MBPRE_MARK
why=""
svc=$(systemctl is-active bumblebee 2>&1 | head -1)
echo "MBPRE service_bumblebee $svc"
[ "$svc" = "active" ] && why="$why служба_bumblebee_активна(остановите_сами_sudo_systemctl_stop_bumblebee)"
for p in "$HOME/bench_ws/mavros" "$HOME/bench_ws/incoming/rc3_mavros"; do
  if [ -e "$p" ]; then echo "MBPRE exists $p"; why="$why уже_есть_$(basename "$p")"; else echo "MBPRE absent $p"; fi
done
free=$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
echo "MBPRE disk_free_mb ${free:-unknown}"
if [ -z "$free" ] || [ "$free" -lt 3000 ]; then why="$why мало_места_на_диске"; fi
busy=$(ps -eo comm= 2>/dev/null | grep -c -E '^(colcon|cmake|make|cc1plus)$')
echo "MBPRE builders_running $busy"
[ "${busy:-0}" -gt 0 ] && why="$why идёт_сборка"
echo "MBPRE apt_state $(dpkg-query -W -f='${Package}=${Version} ' ros-jazzy-mavros ros-jazzy-libmavconn ros-jazzy-mavros-msgs ros-jazzy-mavros-extras 2>&1 | tr '\n' ' ')"
echo "MBPRE active_prefix $(timeout 30 ros2 pkg prefix mavros < /dev/null 2>/dev/null | head -1)"
echo "MBPRE uname $(uname -srm)"
if [ -z "$why" ]; then echo "BB_MBPRE_RESULT OK"; else echo "BB_MBPRE_RESULT STOP$why"; fi
echo "BB_MBPRE_DONE"
