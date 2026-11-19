#!/bin/bash
# ТОЛЬКО ЧТЕНИЕ (Claude, 10.11.2026). Один вопрос к MAVROS: связь с контроллером и взведён ли дрон. Ничего не публикует и не пишет.
# stdout: BB_ARM connected=<true|false|?> armed=<true|false|?>, затем BB_ARM_STATE_DONE. Запускается из run_armcheck.ps1.
[ "$(hostname)" = "bumblebee-20ec" ] || { echo "STOP: hostname is $(hostname), expected bumblebee-20ec" >&2; exit 1; }
source /etc/profile.d/bumblebee-ros.sh < /dev/null 2>/dev/null
source /opt/ros/jazzy/setup.bash < /dev/null 2>/dev/null
c=$(timeout 8 ros2 topic echo --once --field connected /mavros/state < /dev/null 2>/dev/null | head -1 | tr -d ' \r' | tr 'A-Z' 'a-z')
a=$(timeout 8 ros2 topic echo --once --field armed /mavros/state < /dev/null 2>/dev/null | head -1 | tr -d ' \r' | tr 'A-Z' 'a-z')
[ "$c" = "true" ] || [ "$c" = "false" ] || c="?"
[ "$a" = "true" ] || [ "$a" = "false" ] || a="?"
echo "BB_ARM connected=$c armed=$a"
echo "BB_ARM_STATE_DONE"
# BB_ARM_STATE_MARK