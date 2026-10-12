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

# This drone's ROS 2 domain (set_identity.sh may pick it after the unit started,
# when Wi-Fi comes up during the start delay -- so read it here, not only via
# the unit's EnvironmentFile).
if [ -r /etc/bumblebee/ros.env ]; then
    set -a
    . /etc/bumblebee/ros.env
    set +a
fi
source /opt/ros/jazzy/setup.bash
source /home/lb/ros2_ws/install/setup.bash
# diagnostic: flush ROS/DDS logs immediately so the last lines before a freeze land on disk
export RCUTILS_LOGGING_BUFFERED_STREAM=0
export RCUTILS_CONSOLE_OUTPUT_FORMAT='[{severity} {time}] [{name}]: {message}'
# Start after the first NTP sync when one is coming: the Raspberry Pi has no RTC
# and steps its clock at that sync, and ROS 2 nodes running across such a jump
# stop delivering data to each other (bumblebee-clock-jump.timer restarts them
# if it happens later anyway). On a hotspot or without internet nothing syncs:
# go ahead after 20 s.
for _ in $(seq 1 20); do
    [ -e /run/systemd/timesync/synchronized ] && break
    sleep 1
done
# The flight controller's MAVLink baud differs between drones (PX4 SER_TEL1_BAUD):
# find it before MAVROS opens the UART. Read-only; always prints a URL (the
# remembered/configured one if the flight controller is silent).
BB_FCU_URL=$(python3 /home/lb/ros2_ws/src/bumblebee/scripts/fcu_detect.py) || true
export BB_FCU_URL
exec ros2 launch bumblebee bumblebee.launch.py
