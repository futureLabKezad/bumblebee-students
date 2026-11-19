#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026). Состояние Raspberry Pi 20EC: процессор, температура, троттлинг, процессы, версии.
# Ничего не пишет на дрон, не создаёт файлов на Pi, не трогает узлы и полётный контроллер. Запускается из 01_snimok_do.cmd через ssh.
# stdout: строки "КЛЮЧ значение". Последняя строка BB_PI_STATE_DONE.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
echo "PI_DATE $(date '+%F %T %z')"
echo "PI_EPOCH $(date +%s)"
echo "PI_UPTIME $(uptime -p 2>/dev/null) | $(cut -d' ' -f1 /proc/uptime) s"
echo "PI_MODEL $(tr -d '\0' < /proc/device-tree/model 2>/dev/null)"
echo "PI_KERNEL $(uname -srm)"
echo "PI_OS $(. /etc/os-release 2>/dev/null; echo "$PRETTY_NAME")"
echo "PI_CPUS $(nproc)"
echo "PI_LOADAVG $(cut -d' ' -f1-3 /proc/loadavg)"
echo "PI_MEM_MB $(free -m 2>/dev/null | awk '/^Mem:/{print "total="$2" used="$3" available="$7}')"
echo "PI_DISK_ROOT $(df -h / 2>/dev/null | awk 'NR==2{print $2" used="$3" free="$4" use="$5}')"
if command -v vcgencmd >/dev/null 2>&1; then
  echo "PI_TEMP $(vcgencmd measure_temp 2>&1)"
  echo "PI_THROTTLED $(vcgencmd get_throttled 2>&1)"
  echo "PI_ARM_CLOCK $(vcgencmd measure_clock arm 2>&1)"
  echo "PI_CORE_VOLT $(vcgencmd measure_volts core 2>&1)"
else
  echo "PI_TEMP n/a (no vcgencmd) $(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)"
  echo "PI_THROTTLED n/a (no vcgencmd)"
fi
echo "PI_TOP_BY_CPU:"
ps -eo pid=,pcpu=,pmem=,etime=,comm= --sort=-pcpu 2>/dev/null | head -8 | while IFS= read -r l; do echo "  $l"; done
echo "PI_BUMBLEBEE_SERVICE $(systemctl is-active bumblebee 2>&1)"
echo "PI_BUMBLEBEE_STARTED $(systemctl show -p ActiveEnterTimestamp --value bumblebee 2>&1)"
echo "PI_NODES:"
timeout 20 ros2 node list < /dev/null 2>/dev/null | head -40 | while IFS= read -r l; do echo "  $l"; done
echo "PI_MAVROS_STATE_ONE_SAMPLE:"
timeout 8 ros2 topic echo --once --field connected /mavros/state < /dev/null 2>&1 | head -3 | while IFS= read -r l; do echo "  connected: $l"; done
timeout 8 ros2 topic echo --once --field armed /mavros/state < /dev/null 2>&1 | head -3 | while IFS= read -r l; do echo "  armed: $l"; done
timeout 8 ros2 topic echo --once --field mode /mavros/state < /dev/null 2>&1 | head -3 | while IFS= read -r l; do echo "  mode: $l"; done
echo "PI_DETECTOR_PROCESSES:"
ps -eo pid=,lstart=,args= 2>/dev/null | grep -E 'aruco_detect\.py|vpe_fix\.py|camera_fix\.py' | grep -v grep | grep -v 'BB_PI_STATE_MARK' | cut -c1-200 | while IFS= read -r l; do echo "  $l"; done
echo "PI_INSTALLED_FILES_SHA256:"
find /home/lb -maxdepth 8 \( -name aruco_detect.py -o -name vpe_fix.py -o -name camera_fix.py -o -name drone.py \) -path '*bumblebee*' 2>/dev/null | head -12 | while IFS= read -r f; do echo "  $(sha256sum "$f" 2>/dev/null | cut -c1-64)  $f"; done
echo "PI_VERSION_FILES:"
find /home/lb -maxdepth 4 -name VERSION 2>/dev/null | head -5 | while IFS= read -r f; do echo "  $f: $(head -c 80 "$f" 2>/dev/null | tr '\n' ' ')"; done
echo "PI_PACKAGES: $(dpkg-query -W -f='${Package}=${Version} ' ros-jazzy-mavros ros-jazzy-mavros-msgs ros-jazzy-rclpy 2>/dev/null)"
echo "PI_PYTHON $(python3 --version 2>&1)"
echo "PI_OPENCV $(timeout 30 python3 -B -c 'import cv2; print(cv2.__version__)' 2>&1 < /dev/null | tail -1 | cut -c1-120)"
echo "PI_JOURNAL_ACCESS $(journalctl -u bumblebee -n 1 --no-pager -o cat 2>&1 | head -1 | cut -c1-100)"
echo "BB_PI_STATE_DONE"
# BB_PI_STATE_MARK (метка: отбрасывает собственный процесс скрипта из списка процессов)
