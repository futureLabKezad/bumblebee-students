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
# Per-drone ROS 2 domain (see ros_domain.py): decision + the env file every
# ROS service, start_bumblebee.sh and login shells read (/etc/environment
# carries the domain to non-login sessions such as `ssh drone 'cmd'`).
ROS_STATE=${BB_ROS_STATE:-/etc/bumblebee/ros_domain}
ROS_ENV=${BB_ROS_ENV:-/etc/bumblebee/ros.env}
ETC_ENVIRONMENT=${BB_ETC_ENVIRONMENT:-/etc/environment}
SCRIPTS=$(dirname "$(readlink -f "$0")")
ROS_DOMAIN_PY=${BB_ROS_DOMAIN_PY:-$SCRIPTS/ros_domain.py}
FCU_ARMED_PY=${BB_FCU_ARMED_PY:-$SCRIPTS/fcu_armed.py}
PROC=${BB_PROC:-/proc}
# "<domain> <pid>": what start_bumblebee.sh launched the flight stack with
# (bumblebee.service RuntimeDirectory, so it goes away when the stack stops).
STACK_FILE=${BB_STACK_FILE:-/run/bumblebee-stack/domain}

# Runs at boot, from the NetworkManager hook and every minute from a timer:
# never two at once.
exec 9>"${BB_IDENTITY_LOCK:-/run/bumblebee-identity.lock}"
command -v flock >/dev/null 2>&1 && flock -w 60 9 || true

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

# 2) ROS 2 domain. On a client Wi-Fi (not at early boot, not on our own
#    hotspot) look at the domains other drones advertise and avoid them. What
#    counts is the domain the flight stack actually runs with: start_bumblebee.sh
#    reads ros.env under the same lock as this script and records the domain
#    right before `ros2 launch` ($STACK_FILE). Until then it has not chosen, so
#    a new domain is simply written and the stack picks it up; after that, the
#    stack is restarted onto a new domain only when PX4's own heartbeat says
#    disarmed -- read straight from the flight controller (fcu_armed.py), never
#    through ROS, where during a clash the other drone's state could answer.
#    Otherwise everything (files, advertisement, helpers) stays on the running
#    domain and the next pass (timer, every minute) tries again. The decision
#    is final before anything is written, and the restart follows right after.
client_ip() {
    ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 \
        | grep -v -E '^(10\.42\.|169\.254\.)' | head -n1
}
fcu_disarmed() {
    [ "$(python3 "$FCU_ARMED_PY" 2>/dev/null)" = "disarmed" ]
}
unit_domain() {
    # ROS_DOMAIN_ID the unit's main process runs with; '' if not running
    local pid
    systemctl is-active --quiet "$1" 2>/dev/null || return 0
    pid=$(systemctl show -p MainPID --value "$1" 2>/dev/null)
    [ -n "$pid" ] && [ "$pid" != "0" ] || return 0
    tr '\0' '\n' < "$PROC/$pid/environ" 2>/dev/null | sed -n 's/^ROS_DOMAIN_ID=//p' | tail -n1
}
mavros_running() {
    pgrep -f '^/opt/ros/jazzy/lib/mavros/mavros_node' >/dev/null 2>&1
}
stack_domain() {
    # Domain the flight stack has fixed for itself; '' while it has not.
    local d="" pid="" main
    systemctl is-active --quiet bumblebee 2>/dev/null || return 0
    main=$(systemctl show -p MainPID --value bumblebee 2>/dev/null)
    if [ -r "$STACK_FILE" ]; then
        read -r d pid < "$STACK_FILE" || true
        if [ -n "$pid" ] && [ "$pid" = "$main" ]; then
            echo "${d:-0}"
            return 0
        fi
    fi
    # start script without that record (older install): a running MAVROS
    if mavros_running; then
        d=$(unit_domain bumblebee)
        echo "${d:-0}"                        # started before domains existed
    fi
}
CUR_DOMAIN=$(sed -n 's/^ROS_DOMAIN_ID=//p' "$ROS_ENV" 2>/dev/null | tail -n1)
BROWSE=""
if [ -n "$(client_ip)" ]; then
    sleep "${BB_BROWSE_DELAY:-2}"      # let drones that just joined announce themselves
    BROWSE="--browse"
fi
DOMAIN=$(python3 "$ROS_DOMAIN_PY" --mac "$MAC" --id "$HWID" --state "$ROS_STATE" $BROWSE || true)
case "$DOMAIN" in ''|*[!0-9]*) DOMAIN="$CUR_DOMAIN" ;; esac
STACK_DOMAIN=$(stack_domain)
RESTART_STACK=0
if [ -n "$DOMAIN" ] && [ -n "$STACK_DOMAIN" ] && [ "$DOMAIN" != "$STACK_DOMAIN" ]; then
    if fcu_disarmed; then
        echo "set_identity: ROS domain $STACK_DOMAIN -> $DOMAIN, restarting the ROS services (PX4 disarmed)"
        RESTART_STACK=1
    else
        echo "set_identity: ROS domain $STACK_DOMAIN -> $DOMAIN deferred (PX4 not confirmed disarmed)" >&2
        DOMAIN="$STACK_DOMAIN"
        # remember the running domain, so the next pass checks it afresh
        # instead of moving later to a domain picked for a clash now gone
        python3 "$ROS_DOMAIN_PY" --mac "$MAC" --id "$HWID" --state "$ROS_STATE" --keep "$DOMAIN" >/dev/null || true
    fi
fi
NEW_ENV=$(mktemp)
{
    echo "# Generated by set_identity.sh: this drone's ROS 2 settings, read by every"
    echo "# Bumblebee service that runs ROS nodes, start_bumblebee.sh and login shells."
    if [ -n "$DOMAIN" ]; then
        echo "#"
        echo "# Each drone on a Wi-Fi gets its own ROS_DOMAIN_ID (ros_domain.py), so drones"
        echo "# never see each other's topics or services."
        echo "# rviz/rqt on a laptop: export ROS_DOMAIN_ID=$DOMAIN"
        echo "ROS_DOMAIN_ID=$DOMAIN"
    fi
    echo "#"
    echo "# Fast DDS over UDP only, for the services too (the original image set this"
    echo "# in /etc/environment, which only login sessions read). With the default"
    echo "# shared-memory transport the drone's nodes stopped receiving each other's"
    echo "# data 1-2 minutes after MAVROS began streaming the flight controller at"
    echo "# full rate, until restarted (Fast-DDS #6569); over UDP it ran 15+ min clean."
    echo "FASTDDS_BUILTIN_TRANSPORTS=UDPv4"
} > "$NEW_ENV"
if ! cmp -s "$NEW_ENV" "$ROS_ENV"; then
    mkdir -p "$(dirname "$ROS_ENV")"
    install -m 0644 "$NEW_ENV" "$ROS_ENV"
fi
rm -f "$NEW_ENV"
# exactly one ROS_DOMAIN_ID line in /etc/environment (PAM: every login,
# including non-interactive `ssh drone 'cmd'`)
if [ -n "$DOMAIN" ] || grep -q '^ROS_DOMAIN_ID=' "$ETC_ENVIRONMENT" 2>/dev/null; then
    NEW_ETC=$(mktemp)
    grep -v '^ROS_DOMAIN_ID=' "$ETC_ENVIRONMENT" 2>/dev/null > "$NEW_ETC" || true
    [ -n "$DOMAIN" ] && echo "ROS_DOMAIN_ID=$DOMAIN" >> "$NEW_ETC"
    cmp -s "$NEW_ETC" "$ETC_ENVIRONMENT" || install -m 0644 "$NEW_ETC" "$ETC_ENVIRONMENT"
    rm -f "$NEW_ETC"
fi

# 3) DNS-SD service record advertising the ports the GCS app needs + friendly name.
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
    <txt-record>ros_domain=${DOMAIN:-0}</txt-record>
  </service>
</service-group>
EOF
SERVICE_CHANGED=0
if ! cmp -s "$NEW_SERVICE" "$SERVICE_FILE"; then
    install -m 0644 "$NEW_SERVICE" "$SERVICE_FILE"
    SERVICE_CHANGED=1
fi
rm -f "$NEW_SERVICE"

# 4) A new ROS domain: restart what runs ROS nodes so they meet again -- the
#    flight stack right after its disarmed check above (nothing slow in
#    between); otherwise only the helpers not yet on this domain (not
#    flight-critical: always safe to restart).
if [ "$RESTART_STACK" = "1" ]; then
    systemctl --no-block try-restart bumblebee wifi-manager notify-manager 2>/dev/null || true
else
    AUX=""
    for u in wifi-manager notify-manager; do
        d=$(unit_domain "$u")
        if systemctl is-active --quiet "$u" 2>/dev/null && [ "${d:-0}" != "${DOMAIN:-0}" ]; then
            AUX="$AUX $u"
        fi
    done
    [ -z "$AUX" ] || systemctl --no-block try-restart $AUX 2>/dev/null || true
fi

# 5) Let a running avahi pick up the new hostname + service record. A live
#    hostname change needs a full restart to re-evaluate the %h instance name; a
#    reload is enough when only the service file changed. At boot avahi is not
#    running yet (bumblebee-identity.service is ordered before it) and reads both
#    when it starts. --no-block: never wait for the job -- inside that service a
#    blocking restart of avahi waits for the service itself, forever.
if systemctl is-active --quiet avahi-daemon 2>/dev/null; then
    if [ "$HOSTNAME_CHANGED" = "1" ]; then
        systemctl --no-block restart avahi-daemon 2>/dev/null || true
    elif [ "$SERVICE_CHANGED" = "1" ]; then
        systemctl --no-block reload-or-restart avahi-daemon 2>/dev/null || true
    fi
fi
