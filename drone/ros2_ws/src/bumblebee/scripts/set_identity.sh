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

# Assign a stable, unique identity to this drone so it advertises <name>.local
# and a _bumblebee._tcp Bonjour service the GCS app auto-discovers by name.
#
# The name is derived once from the drone's wlan0 client-IP last octet
# (172.20.10.4 -> bumblebee-4) and persisted in /home/lb/drone_name, which the
# operator may edit to override. On later boots the file is authoritative, so
# the name never drifts even while the drone is in hotspot/AP mode (10.42.0.1).
set -e

NAME_FILE=/home/lb/drone_name
# wlan0 MAC the name was assigned on. A card cloned from another drone carries
# that drone's name; a MAC mismatch means "new drone", so the name is re-derived.
# No binding file (drones set up before this existed): keep the name as is.
MAC_FILE=/home/lb/drone_name.mac
SERVICE_FILE=/etc/avahi/services/bumblebee.service

MAC=$(cat /sys/class/net/wlan0/address 2>/dev/null | tr -d '[:space:]')
# Short hardware id, also used in the hotspot SSID (Bumblebee-<ID>).
HWID=$(echo "$MAC" | tr -d ':' | tail -c 5 | tr '[:lower:]' '[:upper:]')

read_name() {
    [ -s "$NAME_FILE" ] || return 0
    if [ -s "$MAC_FILE" ] && [ -n "$MAC" ] && [ "$(tr -d '[:space:]' < "$MAC_FILE")" != "$MAC" ]; then
        echo "set_identity: $NAME_FILE belongs to another drone ($(cat "$MAC_FILE")), re-deriving" >&2
        return 0
    fi
    tr -d '[:space:]' < "$NAME_FILE"
}

derive_name() {
    # last octet of the wlan0 client IPv4; skip hotspot (10.42.x) / link-local
    local ip octet
    ip=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)
    case "$ip" in
        ""|10.42.*|169.254.*) return 0 ;;
    esac
    octet=$(echo "$ip" | awk -F. '{print $4}')
    [ -n "$octet" ] && echo "bumblebee-$octet"
}

# Guard command substitutions so `set -e` doesn't abort when the file is absent
# (first run) or no client IP is available yet.
NAME="$(read_name || true)"
if [ -z "$NAME" ]; then
    NAME="$(derive_name || true)"
    if [ -n "$NAME" ]; then
        echo "$NAME" > "$NAME_FILE"
        [ -n "$MAC" ] && echo "$MAC" > "$MAC_FILE"
        chown lb:lb "$NAME_FILE" "$MAC_FILE" 2>/dev/null || true
    fi
fi
if [ -z "$NAME" ]; then
    echo "set_identity: no client IP yet, leaving hostname unchanged"
    exit 0
fi

# Human-friendly display name (Bumblebee-4).
DISP="$(tr '[:lower:]' '[:upper:]' <<< ${NAME:0:1})${NAME:1}"
echo "set_identity: name=$NAME display=$DISP"

# 1) Hostname -> avahi auto-advertises <name>.local
HOSTNAME_CHANGED=0
if [ "$(hostnamectl --static)" != "$NAME" ]; then
    hostnamectl set-hostname "$NAME"
    HOSTNAME_CHANGED=1
fi

# 2) DNS-SD service record advertising the ports the GCS app needs + friendly name
cat > "$SERVICE_FILE" <<EOF
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">%h</name>
  <service>
    <type>_bumblebee._tcp</type>
    <port>9090</port>
    <txt-record>name=$DISP</txt-record>
    <txt-record>rosbridge=9090</txt-record>
    <txt-record>mjpeg=8080</txt-record>
    <txt-record>metrics=8888</txt-record>
    <txt-record>api=8765</txt-record>
    <txt-record>id=$HWID</txt-record>
  </service>
</service-group>
EOF

# 3) Let avahi pick up the new hostname + service record. A live hostname change
#    needs a full restart to re-evaluate the %h instance name; a plain reload is
#    enough when only the service file changed (and at boot the hostname is
#    already set before avahi starts).
if [ "$HOSTNAME_CHANGED" = "1" ]; then
    systemctl restart avahi-daemon 2>/dev/null || true
else
    systemctl reload avahi-daemon 2>/dev/null || systemctl restart avahi-daemon 2>/dev/null || true
fi
