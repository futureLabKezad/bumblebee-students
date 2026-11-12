#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 09.11.2026). Какую карту меток загрузил работающий детектор и совпадает ли она с drone.MAP_FILE.
# Ничего не пишет на дрон, файлов на Pi не создаёт, узлы не трогает. Запускается из map_check.cmd через ssh.
# stdout: строки "КЛЮЧ значение"; последняя строка VERDICT SAME | DIFFERENT | UNKNOWN.
: hostname check skipped in PC dry run
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
MAP_FILE=/home/lb/ros2_ws/src/aruco_pose/map/map.txt   # drone.MAP_FILE (examples/drone.py:630)

NODE=$(timeout 20 ros2 node list < /dev/null 2>/dev/null | grep -x '/aruco_detect' || true)
echo "DETECTOR_NODE ${NODE:-none}"
LOADED=''
if [ -n "$NODE" ]; then
  LOADED=$(timeout 20 ros2 param get /aruco_detect map_file < /dev/null 2>/dev/null | sed -n 's/^String value is: //p')
  echo "USE_MAP_MARKERS $(timeout 20 ros2 param get /aruco_detect use_map_markers < /dev/null 2>/dev/null)"
fi
echo "DETECTOR_MAP_PARAM ${LOADED:-unknown}"
# detector start time: it reads the map once at start (aruco_detect.py:446)
PSL=$(ps -eo pid=,lstart=,args= | grep '[a]ruco_detect.py' | head -3)
echo "DETECTOR_PROCESS ${PSL:-none}"
DSTART=''
if [ -n "$PSL" ]; then
  PID=$(echo "$PSL" | head -1 | awk '{print $1}')
  DSTART=$(stat -c %Y "/proc/$PID" 2>/dev/null)
fi

sha() { sha256sum "$1" 2>/dev/null | awk '{print $1}'; }
for f in "$LOADED" "$MAP_FILE"; do
  [ -n "$f" ] || continue
  echo "FILE $f"
  echo "  REAL $(readlink -f "$f" 2>&1)"
  echo "  SHA256 $(sha "$f")"
  echo "  MTIME $(stat -c '%y' "$f" 2>&1)"
done
echo "OTHER_COPIES:"
find /home/lb/ros2_ws -maxdepth 8 -path '*aruco_pose*' -name 'map*.txt' 2>/dev/null | head -20 | while read -r f; do echo "  $(sha "$f")  $f"; done

V=UNKNOWN; WHY='detector not running or map_file not readable'
if [ -n "$LOADED" ] && [ -r "$LOADED" ] && [ -r "$MAP_FILE" ]; then
  if [ "$(sha "$LOADED")" != "$(sha "$MAP_FILE")" ]; then
    V=DIFFERENT; WHY='the detector map and MAP_FILE have different contents'
  elif [ -n "$DSTART" ] && [ "$(stat -c %Y "$LOADED")" -gt "$DSTART" ]; then
    V=UNKNOWN; WHY='the map file changed after the detector started; it still holds the older map'
  else
    V=SAME; WHY='same contents, file older than the detector start'
  fi
fi
echo "WHY $WHY"
echo "VERDICT $V"
