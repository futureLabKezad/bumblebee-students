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
# The name comes from the wlan0 MAC: bumblebee-<last 4 hex digits>, shown as
# Bumblebee-20EC -- the same id as the drone's own hotspot SSID, so a drone has
# one name everywhere, needs no network to get it (first boot in hotspot mode
# included) and keeps it whatever IP the router hands out.
#
# /home/lb/drone_name, if present, overrides it with a custom name. The file is
# bound to the MAC it was set on (drone_name.mac): a card cloned from another
# drone carries that drone's custom name, which is ignored here. Names the
# older scheme derived from the client IP (bumblebee-<octet>) are retired.
set -e

NAME_FILE=${BB_NAME_FILE:-/home/lb/drone_name}
MAC_FILE=${BB_MAC_FILE:-/home/lb/drone_name.mac}
SERVICE_FILE=${BB_SERVICE_FILE:-/etc/avahi/services/bumblebee.service}

MAC=$(cat "${BB_WLAN_ADDRESS:-/sys/class/net/wlan0/address}" 2>/dev/null | tr -d '[:space:]')
# Short hardware id, also used in the hotspot SSID (Bumblebee-<ID>).
HWID=$(echo "$MAC" | tr -d ':' | tail -c 5 | tr '[:lower:]' '[:upper:]')

custom_name() {
    local name
    [ -s "$NAME_FILE" ] || return 0
    name=$(tr -d '[:space:]' < "$NAME_FILE" | tr '[:upper:]' '[:lower:]')
    if [ -s "$MAC_FILE" ] && [ -n "$MAC" ] && [ "$(tr -d '[:space:]' < "$MAC_FILE")" != "$MAC" ]; then
        echo "set_identity: $NAME_FILE belongs to another drone ($(cat "$MAC_FILE")), ignoring it" >&2
        return 0
    fi
    case "$name" in
        bumblebee-[0-9]|bumblebee-[0-9][0-9]|bumblebee-[0-9][0-9][0-9])
            echo "set_identity: retiring IP-derived name $name" >&2
            rm -f "$NAME_FILE" "$MAC_FILE"
            return 0 ;;
    esac
    # hostname rules: letters, digits and inner hyphens, at most 63 chars
    if ! [[ "$name" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
        echo "set_identity: '$name' in $NAME_FILE is not a valid hostname, ignoring it" >&2
        return 0
    fi
    echo "$name"
}

if [ -z "$HWID" ]; then
    echo "set_identity: no wlan0 MAC yet, leaving hostname unchanged"
    exit 0
fi
NAME="$(custom_name || true)"
if [ -n "$NAME" ]; then
    # Bind a custom name to this drone the first time it is seen here.
    if [ ! -s "$MAC_FILE" ]; then
        echo "$MAC" > "$MAC_FILE"
        chown lb:lb "$MAC_FILE" 2>/dev/null || true
    fi
    if [[ "$NAME" =~ ^bumblebee-[0-9a-f]{4}$ ]]; then
        DISP="Bumblebee-$(tr '[:lower:]' '[:upper:]' <<< "${NAME:10}")"
    else
        DISP="$(tr '[:lower:]' '[:upper:]' <<< "${NAME:0:1}")${NAME:1}"
    fi
else
    NAME="bumblebee-$(tr '[:upper:]' '[:lower:]' <<< "$HWID")"
    DISP="Bumblebee-$HWID"
fi
echo "set_identity: name=$NAME display=$DISP"

# 1) Hostname -> avahi auto-advertises <name>.local
HOSTNAME_CHANGED=0
if [ "$(hostnamectl --static)" != "$NAME" ]; then
    hostnamectl set-hostname "$NAME"
    HOSTNAME_CHANGED=1
fi

# 2) DNS-SD service record advertising the ports the GCS app needs + friendly name.
#    Written to a temp file first: avahi is only poked when something changed,
#    because a reload withdraws and re-announces the service (the GCS would see
#    the drone vanish and come back on every DHCP renewal).
NEW_SERVICE=$(mktemp)
cat > "$NEW_SERVICE" <<EOF
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
SERVICE_CHANGED=0
if ! cmp -s "$NEW_SERVICE" "$SERVICE_FILE"; then
    install -m 0644 "$NEW_SERVICE" "$SERVICE_FILE"
    SERVICE_CHANGED=1
fi
rm -f "$NEW_SERVICE"

# 3) Let avahi pick up the new hostname + service record. A live hostname change
#    needs a full restart to re-evaluate the %h instance name; a plain reload is
#    enough when only the service file changed (and at boot the hostname is
#    already set before avahi starts).
if [ "$HOSTNAME_CHANGED" = "1" ]; then
    systemctl restart avahi-daemon 2>/dev/null || true
elif [ "$SERVICE_CHANGED" = "1" ]; then
    systemctl reload avahi-daemon 2>/dev/null || systemctl restart avahi-daemon 2>/dev/null || true
fi
