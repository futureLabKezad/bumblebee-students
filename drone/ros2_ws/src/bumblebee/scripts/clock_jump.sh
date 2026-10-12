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

# Run by bumblebee-clock-jump.timer (OnClockChange) whenever the system clock
# jumps. The Raspberry Pi has no RTC: it boots with the time it was switched off
# and steps to the real time at the first NTP sync -- at boot on a known Wi-Fi,
# or minutes later when a drone set up over its hotspot joins a Wi-Fi with
# internet. The ROS 2 nodes running at that moment stop delivering data to each
# other (rosbridge, notify_manager: "no telemetry", red strobe + error tune;
# reproduced on drone 20EC with `date -s "+5 minutes"`), so they are restarted:
#   * notify-manager and wifi-manager always (not part of flight control);
#   * the flight stack (bumblebee.service) only if PX4's own heartbeat says
#     disarmed -- never while armed or when its state is unknown.
set -u
HERE="$(dirname "$(readlink -f "$0")")"
log() { echo "clock_jump: $*"; }

log "system clock jumped (now $(date '+%F %T'))"
systemctl --no-block try-restart notify-manager wifi-manager 2>/dev/null || true

if pgrep -f 'mavros/mavros_node' >/dev/null 2>&1; then
    STATE=$(python3 "$HERE/fcu_armed.py" 2>/dev/null || true)
    if [ "$STATE" = "disarmed" ]; then
        log "flight controller disarmed: restarting the ROS stack"
        systemctl --no-block restart bumblebee 2>/dev/null || true
    else
        log "flight controller ${STATE:-unknown}: ROS stack NOT restarted; land and restart the drone"
    fi
fi
