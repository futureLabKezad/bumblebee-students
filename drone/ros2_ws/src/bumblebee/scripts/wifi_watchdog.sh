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

HOTSPOT_CONN="bumblebee-hotspot"
CHECK_INTERVAL=5
RECONNECT_INTERVAL=60
RECONNECT_ATTEMPTS=10      # how many times to try rejoining a known wifi before hotspot
RECONNECT_TRY_INTERVAL=6   # seconds between attempts (10 x 6 ~= 60s before hotspot)

SWITCH_MARKER=/tmp/bumblebee-wifi-switch   # touched by wifi_manager.py before an API Wi-Fi switch
SWITCH_GRACE=45            # seconds to stay hands-off after an API-driven switch
CONNECTING_GRACE=45        # seconds a "connecting" wlan0 is given before we intervene

log() { echo "$(date): $1" >> /tmp/wifi-manager.log 2>/dev/null || true; }

# Stable hotspot SSID: Bumblebee-<last 4 hex digits of the wlan0 MAC>, so the
# GCS keeps seeing the same network across fallbacks. Random only if no MAC.
hotspot_ssid() {
    local mac
    mac=$(tr -d ':\n' < /sys/class/net/wlan0/address 2>/dev/null)
    if [ ${#mac} -ge 4 ]; then
        echo "Bumblebee-$(echo "${mac: -4}" | tr '[:lower:]' '[:upper:]')"
    else
        echo "Bumblebee-$((RANDOM % 9000 + 1000))"
    fi
}

# Seconds since wifi_manager.py last started a switch (large if never).
since_api_switch() {
    local t
    t=$(cat "$SWITCH_MARKER" 2>/dev/null)
    case "$t" in ''|*[!0-9]*) echo 999999; return ;; esac
    echo $(( $(date +%s) - t ))
}

# Saved client profile to retry: highest autoconnect-priority, then most
# recently used (not simply the first one listed).
best_client_conn() {
    nmcli -t -f NAME,TYPE,AUTOCONNECT-PRIORITY,TIMESTAMP con show 2>/dev/null \
        | awk -F: -v hs="$HOTSPOT_CONN" '$2 == "802-11-wireless" && $1 != hs {print $3 ":" $4 ":" $1}' \
        | sort -t: -k1,1nr -k2,2nr | head -1 | cut -d: -f3-
}

log "wifi_watchdog started"

last_reconnect=0
hotspot_starting=0
connecting_since=0

while true; do
    CONN=$(nmcli -t -f DEVICE,CONNECTION device status 2>/dev/null | grep "^wlan0:" | cut -d: -f2)
    STATE=$(nmcli -t -f DEVICE,STATE device status 2>/dev/null | grep "^wlan0:" | cut -d: -f2)

    # The GCS just asked for a switch: let NetworkManager finish it.
    if [ "$(since_api_switch)" -lt "$SWITCH_GRACE" ]; then
        sleep $CHECK_INTERVAL
        continue
    fi

    # A join is in progress (auth / DHCP): don't fire "con up" over it.
    case "$STATE" in
        connecting*)
            now=$(date +%s)
            [ "$connecting_since" -eq 0 ] && connecting_since=$now
            if [ $((now - connecting_since)) -lt $CONNECTING_GRACE ]; then
                sleep $CHECK_INTERVAL
                continue
            fi
            log "wlan0 stuck in '$STATE' for ${CONNECTING_GRACE}s"
            ;;
        *) connecting_since=0 ;;
    esac

    if [ "$CONN" = "$HOTSPOT_CONN" ]; then
        hotspot_starting=0
        now=$(date +%s)
        if [ $((now - last_reconnect)) -ge $RECONNECT_INTERVAL ]; then
            last_reconnect=$now
            nmcli dev wifi rescan 2>/dev/null
            sleep 3
            VISIBLE=$(nmcli -t -f SSID dev wifi list 2>/dev/null | sort -u)
            KNOWN=$(nmcli -t -f NAME,TYPE con show 2>/dev/null | grep "802-11-wireless" | cut -d: -f1 | grep -v "^$HOTSPOT_CONN$")
            # line-wise (SSIDs may contain spaces), exact SSID match
            while IFS= read -r name; do
                [ -z "$name" ] && continue
                SSID=$(nmcli -t -f 802-11-wireless.ssid con show "$name" 2>/dev/null | cut -d: -f2-)
                [ -z "$SSID" ] && SSID="$name"
                if echo "$VISIBLE" | grep -qxF -- "$SSID"; then
                    log "known network '$SSID' visible, switching from hotspot"
                    nmcli connection down "$HOTSPOT_CONN" 2>/dev/null
                    nmcli connection modify "$name" connection.autoconnect yes 2>/dev/null
                    nmcli connection up "$name" 2>/dev/null && log "connected to $SSID" || log "failed to connect to $SSID"
                    break
                fi
            done <<< "$KNOWN"
        fi
        sleep $CHECK_INTERVAL
        continue
    fi

    # Reset autoconnect for all known wifi connections
    nmcli -t -f NAME,TYPE con show 2>/dev/null | grep "802-11-wireless" | cut -d: -f1 | while read name; do
        [ "$name" = "$HOTSPOT_CONN" ] && continue
        nmcli connection modify "$name" connection.autoconnect yes 2>/dev/null
    done

    # wlan0 not connected and not already on the hotspot:
    # actively try to rejoin a known wifi RECONNECT_ATTEMPTS times, raise hotspot only if all fail.
    # Never reboots — this is the sole path on wifi loss (boot-time AND in-flight).
    if [ "$STATE" != "connected" ] && [ "$hotspot_starting" -eq 0 ]; then
        CLIENT_CONN=$(best_client_conn)
        log "wlan0 not connected (state=$STATE), reconnect loop to ${CLIENT_CONN:-<none>}"
        reconnected=0
        for i in $(seq 1 "$RECONNECT_ATTEMPTS"); do
            ST=$(nmcli -t -f DEVICE,STATE device status 2>/dev/null | grep "^wlan0:" | cut -d: -f2)
            case "$ST" in
                connecting*) ;;   # previous attempt still in progress
                *) [ -n "$CLIENT_CONN" ] && nmcli connection up "$CLIENT_CONN" 2>/dev/null ;;
            esac
            sleep "$RECONNECT_TRY_INTERVAL"
            ST=$(nmcli -t -f DEVICE,STATE device status 2>/dev/null | grep "^wlan0:" | cut -d: -f2)
            if [ "$ST" = "connected" ]; then
                log "reconnected on attempt $i"
                reconnected=1
                break
            fi
            log "reconnect attempt $i/$RECONNECT_ATTEMPTS failed"
        done
        if [ "$reconnected" -eq 0 ]; then
            SSID=$(hotspot_ssid)
            log "reconnect failed after $RECONNECT_ATTEMPTS attempts, activating hotspot $SSID"
            nmcli connection modify "$HOTSPOT_CONN" wifi.ssid "$SSID" 2>/dev/null
            hotspot_starting=1
            nmcli connection up "$HOTSPOT_CONN" 2>/dev/null && log "hotspot up: $SSID" || { log "ERROR: hotspot failed"; hotspot_starting=0; }
        fi
    fi

    sleep $CHECK_INTERVAL
done
