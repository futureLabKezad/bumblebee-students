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
CHECK_INTERVAL=${BB_CHECK_INTERVAL:-5}
RECONNECT_INTERVAL=${BB_RECONNECT_INTERVAL:-60}   # min hotspot uptime between probes for known wifi
RECONNECT_ATTEMPTS=${BB_RECONNECT_ATTEMPTS:-10}   # how many times to try rejoining a known wifi before hotspot
RECONNECT_TRY_INTERVAL=${BB_RECONNECT_TRY_INTERVAL:-6}  # seconds between attempts
RECONNECT_DEADLINE=${BB_RECONNECT_DEADLINE:-90}   # hard cap on the reconnect loop before the hotspot comes up
JOIN_TIMEOUT=${BB_JOIN_TIMEOUT:-40}               # max seconds a probe join from the hotspot may take
TRY_TIMEOUT=${BB_TRY_TIMEOUT:-20}                 # max seconds one reconnect attempt may block
PROBE_BACKOFF=${BB_PROBE_BACKOFF:-600}            # don't re-probe a network that just failed to join

# wifi_manager.py (user lb) touches this before a GCS-requested switch; hands
# off while it is fresh. Our own probes use a separate root-owned marker,
# because lb could not rewrite a root-owned file in sticky /tmp.
API_SWITCH_MARKER=${BB_API_SWITCH_MARKER:-/tmp/bumblebee-wifi-switch}
PROBE_MARKER=${BB_PROBE_MARKER:-/run/bumblebee-wifi-probe}   # read by the NM dispatcher
SWITCH_GRACE=${BB_SWITCH_GRACE:-45}
# Networks whose GCS-requested join failed ("uuid epoch"), see wifi_manager.py.
API_FAILED_LOG=${BB_API_FAILED_LOG:-/tmp/bumblebee-wifi-failed}
# Present while the GCS asked for hotspot mode: don't switch back to client.
HOTSPOT_PIN_MARKER=${BB_HOTSPOT_PIN_MARKER:-/tmp/bumblebee-hotspot-pinned}
WLAN_ADDRESS=${BB_WLAN_ADDRESS:-/sys/class/net/wlan0/address}
LOG=${BB_LOG:-/tmp/wifi-manager.log}

log() { echo "$(date): $1" >> "$LOG" 2>/dev/null || true; }

# Stable hotspot SSID: Bumblebee-<last 4 hex digits of the wlan0 MAC>, so the
# GCS keeps seeing the same network across fallbacks. Random only if no MAC.
hotspot_ssid() {
    local mac
    mac=$(tr -d ':\n' < "$WLAN_ADDRESS" 2>/dev/null)
    if [ ${#mac} -ge 4 ]; then
        echo "Bumblebee-$(echo "${mac: -4}" | tr '[:lower:]' '[:upper:]')"
    else
        echo "Bumblebee-$((RANDOM % 9000 + 1000))"
    fi
}

# Seconds since wifi_manager.py last started a switch (large if never).
since_api_switch() {
    local t
    t=$(cat "$API_SWITCH_MARKER" 2>/dev/null)
    case "$t" in ''|*[!0-9]*) echo 999999; return ;; esac
    echo $(( $(date +%s) - t ))
}

wlan0_field() {   # CONNECTION or STATE of wlan0
    nmcli -t -f DEVICE,"$1" device status 2>/dev/null | grep "^wlan0:" | cut -d: -f2-
}

# A GCS (or SSH) session is open over the hotspot right now: an established
# TCP connection from a hotspot client to one of our service ports.
clients_on_hotspot() {
    ss -Htn state established \
        '( sport = :8765 or sport = :9090 or sport = :8080 or sport = :8888 or sport = :22 )' 2>/dev/null \
        | awk '{print $4}' | grep -q '^10\.42\.'
}

hotspot_uuid() {
    nmcli -t -f UUID,NAME con show 2>/dev/null | awk -F: -v hs="$HOTSPOT_CONN" '$2 == hs {print $1; exit}'
}

# Saved client Wi-Fi profiles as "visible:priority:timestamp:uuid", best first:
# networks in range, then autoconnect-priority, then most recently used.
# UUIDs never contain ':' (names may), so they are safe in nmcli -t output.
ranked_client_conns() {
    local hs visible uuid kind prio ts ssid vis
    hs=$(hotspot_uuid)
    visible=$(nmcli -t -f SSID dev wifi list --rescan no 2>/dev/null)
    nmcli -t -f UUID,TYPE,AUTOCONNECT-PRIORITY,TIMESTAMP con show 2>/dev/null |
    while IFS=: read -r uuid kind prio ts; do
        [ "$kind" = "802-11-wireless" ] || continue
        [ "$uuid" = "$hs" ] && continue
        # -g escapes ':' and '\' like `dev wifi list -t`, so compare escaped forms
        ssid=$(nmcli -g 802-11-wireless.ssid con show "$uuid" 2>/dev/null)
        vis=0
        [ -n "$ssid" ] && grep -qxF -- "$ssid" <<< "$visible" && vis=1
        echo "$vis:${prio:-0}:${ts:-0}:$uuid"
    done | sort -t: -k1,1nr -k2,2nr -k3,3nr
}

con_label() {
    nmcli -g connection.id con show "$1" 2>/dev/null || echo "$1"
}

raise_hotspot() {
    local ssid
    ssid=$(hotspot_ssid)
    log "$1, activating hotspot $ssid"
    nmcli connection modify "$HOTSPOT_CONN" wifi.ssid "$ssid" 2>/dev/null
    hotspot_starting=1
    if nmcli connection up "$HOTSPOT_CONN" 2>/dev/null; then
        log "hotspot up: $ssid"
        last_reconnect=$(date +%s)   # keep it up >= RECONNECT_INTERVAL before probing
    else
        log "ERROR: hotspot failed"
        hotspot_starting=0
    fi
}

# Failed probe joins as "uuid epoch" lines (plain variable: no bash-4 features,
# so the script also runs under the test harness on macOS bash 3.2).
FAILED=""
failed_at() {   # latest failure of a profile, from our probes or from the GCS
    { echo "$FAILED"; cat "$API_FAILED_LOG" 2>/dev/null; } |
        awk -v u="$1" '$1 == u && $2 > t {t = $2} END {print t + 0}'
}
in_backoff() { [ $(( $(date +%s) - $(failed_at "$1") )) -lt "$PROBE_BACKOFF" ]; }
mark_failed() { FAILED="$(awk -v u="$1" '$1 != u' <<< "$FAILED")"$'\n'"$1 $(date +%s)"; }

log "wifi_watchdog started"

last_reconnect=0
hotspot_starting=0
api_grace=0

while true; do
    CONN=$(wlan0_field CONNECTION)
    STATE=$(wlan0_field STATE)

    # The GCS just asked for a switch: let NetworkManager finish it.
    if [ "$(since_api_switch)" -lt "$SWITCH_GRACE" ]; then
        api_grace=1
        sleep "$CHECK_INTERVAL"
        continue
    fi
    # ...and it did not end up connected: bring the hotspot straight back so the
    # GCS can reach the drone, instead of a long reconnect loop.
    if [ "$api_grace" = 1 ]; then
        api_grace=0
        if [ "$STATE" != "connected" ]; then
            raise_hotspot "GCS-requested switch did not connect"
            sleep "$CHECK_INTERVAL"
            continue
        fi
    fi

    if [ "$CONN" = "$HOTSPOT_CONN" ]; then
        hotspot_starting=0
        now=$(date +%s)
        if [ -e "$HOTSPOT_PIN_MARKER" ] || clients_on_hotspot; then
            :   # GCS asked for hotspot mode, or is using the hotspot right now
        elif [ $((now - last_reconnect)) -ge "$RECONNECT_INTERVAL" ]; then
            last_reconnect=$now
            nmcli dev wifi rescan 2>/dev/null
            sleep 3
            while IFS=: read -r vis _ _ uuid; do
                [ "$vis" = "1" ] || break   # ranked: visible ones come first
                in_backoff "$uuid" && continue
                name=$(con_label "$uuid")
                log "known network '$name' visible, switching from hotspot"
                date +%s > "$PROBE_MARKER" 2>/dev/null
                nmcli connection down "$HOTSPOT_CONN" 2>/dev/null
                nmcli connection modify "$uuid" connection.autoconnect yes 2>/dev/null
                if nmcli -w "$JOIN_TIMEOUT" connection up "$uuid" 2>/dev/null; then
                    log "connected to $name"
                else
                    mark_failed "$uuid"
                    raise_hotspot "failed to connect to $name"
                fi
                rm -f "$PROBE_MARKER"
                break
            done < <(ranked_client_conns)
        fi
        sleep "$CHECK_INTERVAL"
        continue
    fi

    # Re-enable autoconnect on known wifi connections that lost it. Only touch
    # profiles that need it: every modify rewrites a netplan file and reloads NM.
    hs=$(hotspot_uuid)
    nmcli -t -f UUID,TYPE,AUTOCONNECT con show 2>/dev/null | while IFS=: read -r uuid kind auto; do
        [ "$kind" = "802-11-wireless" ] && [ "$uuid" != "$hs" ] && [ "$auto" = "no" ] || continue
        nmcli connection modify "$uuid" connection.autoconnect yes 2>/dev/null
    done

    # wlan0 not connected and not already on the hotspot:
    # actively try to rejoin a known wifi RECONNECT_ATTEMPTS times, raise hotspot only if all fail.
    # Never reboots — this is the sole path on wifi loss (boot-time AND in-flight).
    if [ "$STATE" != "connected" ] && [ "$hotspot_starting" -eq 0 ]; then
        # best profile not just failed (by the GCS or by us)
        CLIENT_CONN=""
        while IFS=: read -r _ _ _ uuid; do
            in_backoff "$uuid" || { CLIENT_CONN=$uuid; break; }
        done < <(ranked_client_conns)
        log "wlan0 not connected (state=$STATE), reconnect loop to $( [ -n "$CLIENT_CONN" ] && con_label "$CLIENT_CONN" || echo '<none>')"
        reconnected=0
        deadline=$(( $(date +%s) + RECONNECT_DEADLINE ))
        for i in $(seq 1 "$RECONNECT_ATTEMPTS"); do
            [ -n "$CLIENT_CONN" ] || break        # nothing worth trying: hotspot now
            [ "$(date +%s)" -lt "$deadline" ] || break
            ST=$(wlan0_field STATE)
            case "$ST" in
                connecting*) ;;   # previous attempt still in progress: don't restart it
                *) nmcli -w "$TRY_TIMEOUT" connection up "$CLIENT_CONN" 2>/dev/null ;;
            esac
            sleep "$RECONNECT_TRY_INTERVAL"
            ST=$(wlan0_field STATE)
            if [ "$ST" = "connected" ]; then
                log "reconnected on attempt $i"
                reconnected=1
                break
            fi
            log "reconnect attempt $i/$RECONNECT_ATTEMPTS failed"
        done
        if [ "$reconnected" -eq 0 ]; then
            raise_hotspot "reconnect failed after $RECONNECT_ATTEMPTS attempts"
        fi
    fi

    sleep "$CHECK_INTERVAL"
done
