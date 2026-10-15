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

# wifi_fallback.sh — run at boot by wifi-fallback.service
# Generates a fresh bumblebee-XXXX SSID, waits 40s for wlan0 to connect,
# activates hotspot if it doesn't.

RAND=$((RANDOM % 9000 + 1000))
SSID="bumblebee-${RAND}"

log() {
    echo "$(date): $1" >> /tmp/wifi-manager.log
}

# Wait up to 10s for NetworkManager to be fully ready
for i in $(seq 1 5); do
    if nmcli -t device status > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

# Update the hotspot profile with the new SSID (non-fatal if profile missing)
if nmcli con modify bumblebee-hotspot wifi.ssid "${SSID}" 2>> /tmp/wifi-manager.log; then
    log "hotspot SSID set to ${SSID}"
else
    log "WARNING: could not set hotspot SSID (profile may be missing)"
fi

# Wait up to 40s for wlan0 to reach connected state
for i in $(seq 1 20); do
    STATE=$(nmcli -t -f DEVICE,STATE device status 2>/dev/null | grep "^wlan0:" | cut -d: -f2 || true)
    if [ "${STATE}" = "connected" ]; then
        log "wlan0 connected, hotspot not needed"
        exit 0
    fi
    sleep 2
done

# Timeout — activate hotspot
log "timeout, activating hotspot ${SSID}"
if ! nmcli con up bumblebee-hotspot 2>> /tmp/wifi-manager.log; then
    log "ERROR: failed to activate hotspot"
    exit 1
fi
