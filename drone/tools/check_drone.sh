#!/bin/bash
# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Quick read-only health report of a drone running a Bumblebee release image.
# Run on the drone as lb:  bash check_drone.sh   (changes nothing)
ok()  { printf '  [OK]   %s\n' "$*"; }
bad() { printf '  [FAIL] %s\n' "$*"; }
chk() { local m=$1; shift; if "$@" >/dev/null 2>&1; then ok "$m"; else bad "$m"; fi; }

echo "== system"
echo "  version:  $(cat /etc/bumblebee_version 2>/dev/null || echo 'none (not a release image)')"
echo "  hostname: $(hostname)   custom name: $(cat ~/drone_name 2>/dev/null || echo none)"
echo "  root fs:  $(df -h / | awk 'NR==2 {print $2" size, "$4" free"}')"
chk "root partition grown to the card (> 10 GB)" test "$(df -BG --output=size / | tail -1 | tr -dc 0-9)" -gt 10
chk "machine-id generated" test -s /etc/machine-id
chk "own SSH host keys generated" ls /etc/ssh/ssh_host_ed25519_key

echo "== services"
for u in bumblebee wifi-manager wifi-watchdog notify-manager sys_metrics avahi-daemon NetworkManager; do
    chk "$u running" systemctl is-active --quiet "$u"
done
chk "bumblebee-identity ran" systemctl is-active --quiet bumblebee-identity

echo "== network"
nmcli -t -f DEVICE,STATE,CONNECTION device status 2>/dev/null | grep '^wlan0' | sed 's/^/  wlan0: /'
echo "  hotspot SSID: $(nmcli -g 802-11-wireless.ssid connection show bumblebee-hotspot 2>/dev/null)"
echo "  IPv4: $(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}')"
chk "Bonjour record advertised (_bumblebee._tcp)" test -s /etc/avahi/services/bumblebee.service
grep -o 'name=[^<]*\|id=[^<]*' /etc/avahi/services/bumblebee.service 2>/dev/null | sed 's/^/  /'
for p in 8765:wifi-api 9090:rosbridge 8080:video 8888:metrics 22:ssh; do
    chk "port ${p%%:*} (${p#*:}) listening" bash -c "ss -Hltn | grep -q ':${p%%:*} '"
done
chk "Wi-Fi API answers" curl -fsS -m 5 http://127.0.0.1:8765/api/wifi/status

echo "== flight stack"
echo "  flight controller link: $(cat ~/.bumblebee/fcu_url 2>/dev/null || echo 'not detected yet') (detected at start)"
grep -h 'fcu_detect' /tmp/bumblebee.log 2>/dev/null | tail -1 | sed 's/^/  /'
DOMAIN=$(sed -n 's/^ROS_DOMAIN_ID=//p' /etc/bumblebee/ros.env 2>/dev/null)
echo "  ROS 2 domain: ${DOMAIN:-0 (shared with every drone on this Wi-Fi!)}  (laptop rviz: export ROS_DOMAIN_ID=${DOMAIN:-0})"
chk "cameras present (/dev/main_camera, /dev/second_camera)" test -e /dev/main_camera -a -e /dev/second_camera
chk "flight controller UART present (/dev/ttyAMA0)" test -e /dev/ttyAMA0
STATE=$(bash -c 'source /etc/profile.d/bumblebee-ros.sh 2>/dev/null; source /opt/ros/jazzy/setup.bash; source ~/ros2_ws/install/setup.bash; timeout 10 ros2 topic echo --once /mavros/state' 2>/dev/null)
if echo "$STATE" | grep -q '^connected: true'; then ok "MAVROS connected to PX4 ($(echo "$STATE" | grep -E '^(armed|mode):' | tr '\n' ' '))"
else bad "MAVROS not connected to PX4 (is the flight controller powered?)"; fi
echo "  recent errors in /tmp/bumblebee.log:"
grep -iE 'error|exception|traceback' /tmp/bumblebee.log 2>/dev/null | grep -v 'Address already in use' | tail -5 | sed 's/^/    /'
