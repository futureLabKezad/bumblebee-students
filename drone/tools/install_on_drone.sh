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
# Runs ON THE DRONE (copied there by deploy.sh). Installs the files listed in
# MANIFEST next to this script, backing up every file it replaces, and writes
# a rollback.sh into the backup directory.
#
# Never restarts the flight stack: bumblebee.service, MAVROS and simple_offboard
# keep running, and PX4 parameters are not touched. Files of the flight stack
# (start_bumblebee.sh, the launch file) take effect at the next reboot.
# Refuses to run while the drone is armed.
#
#   install_on_drone.sh [--reset-name] [--force]
#     --reset-name  forget a custom name in /home/lb/drone_name; the drone is
#                   then called Bumblebee-<last 4 hex digits of its MAC> again
#     --force       skip the "is it armed?" check (only if ROS is not running)
#
# BB_ROOT=/some/dir runs against a fake root for testing (no sudo/systemctl).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${BB_ROOT:-}"
RESET_NAME=0
FORCE=0
for a in "$@"; do
    case "$a" in
        --reset-name) RESET_NAME=1 ;;
        --force) FORCE=1 ;;
        *) echo "unknown option: $a" >&2; exit 2 ;;
    esac
done

if [ -n "$ROOT" ]; then
    SUDO=""
    systemctl() { echo "(test) systemctl $*"; }
else
    SUDO="sudo"
fi

say() { echo "[bumblebee-update] $*"; }

# ---- 1. safety: never while armed -------------------------------------------
if [ -z "$ROOT" ] && [ "$FORCE" -eq 0 ]; then
    if [ -f /opt/ros/jazzy/setup.bash ]; then
        set +u
        # shellcheck disable=SC1091
        # this drone's ROS domain, or /mavros/state is not visible
        [ -r /etc/bumblebee/ros.env ] && { set -a; . /etc/bumblebee/ros.env; set +a; }
        source /opt/ros/jazzy/setup.bash
        [ -f /home/lb/ros2_ws/install/setup.bash ] && source /home/lb/ros2_ws/install/setup.bash
        set -u
        STATE=$(timeout 8 ros2 topic echo --once /mavros/state 2>/dev/null || true)
        if echo "$STATE" | grep -q '^armed: true'; then
            say "drone is ARMED - refusing to update. Land and disarm first."
            exit 1
        fi
        if [ -z "$STATE" ]; then
            say "could not read /mavros/state (stack not running?). Re-run with --force if the drone is on the ground."
            exit 1
        fi
    fi
fi

# ---- 2. backup + install ---------------------------------------------------
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="$ROOT/home/lb/.bumblebee-update/$TS"
mkdir -p "$BACKUP"
ROLLBACK="$BACKUP/rollback.sh"
{
    echo '#!/bin/bash'
    echo "# Restores the files replaced by the update of $TS."
    echo 'set -e'
} > "$ROLLBACK"

# MANIFEST lines: <source relative to payload> <destination> <owner> <mode>
while read -r src dst owner mode; do
    case "$src" in ''|'#'*) continue ;; esac
    dest="$ROOT$dst"
    if [ -e "$dest" ]; then
        mkdir -p "$BACKUP$(dirname "$dst")"
        $SUDO cp -p "$dest" "$BACKUP$dst"
        # copy next to it, then rename: a script that is running right now
        # (watchdog, dispatcher) keeps reading the old inode instead of a
        # half-rewritten file
        # (two lines, so `set -e` in rollback.sh stops on either failing)
        echo "$SUDO cp -p '$BACKUP$dst' '$dest.bbnew'" >> "$ROLLBACK"
        echo "$SUDO mv -f '$dest.bbnew' '$dest'" >> "$ROLLBACK"
    else
        echo "$SUDO rm -f '$dest'" >> "$ROLLBACK"
    fi
    $SUDO mkdir -p "$(dirname "$dest")"
    $SUDO install -m "$mode" "$HERE/payload/$src" "$dest"
    [ -z "$ROOT" ] && $SUDO chown "$owner" "$dest"
    say "installed $dst"
done < "$HERE/MANIFEST"

# ---- 3. drone identity -----------------------------------------------------
NAME_FILE="$ROOT/home/lb/drone_name"
MAC_FILE="$ROOT/home/lb/drone_name.mac"
MAC=$(cat "$ROOT/sys/class/net/wlan0/address" 2>/dev/null | tr -d '[:space:]' || true)
for f in "$NAME_FILE" "$MAC_FILE"; do
    if [ -e "$f" ]; then
        cp -p "$f" "$BACKUP/$(basename "$f")"
        echo "cp -p '$BACKUP/$(basename "$f")' '$f'" >> "$ROLLBACK"
    else
        echo "rm -f '$f'" >> "$ROLLBACK"
    fi
done
# set_identity.sh names the drone after its MAC and retires the old IP-derived
# names (bumblebee-4 from the V1.0.0-beta image included) by itself; a custom
# name in drone_name is kept and bound to this drone's MAC there.
if [ "$RESET_NAME" -eq 1 ]; then
    rm -f "$NAME_FILE" "$MAC_FILE"
    say "custom drone name removed"
fi
if [ ${#MAC} -ge 17 ]; then
    CUSTOM=$(tr -d '[:space:]' < "$NAME_FILE" 2>/dev/null || true)
    case "$CUSTOM" in
        ''|bumblebee-[0-9]|bumblebee-[0-9][0-9]|bumblebee-[0-9][0-9][0-9]) CUSTOM="" ;;  # IP-derived: retired
    esac
    say "drone name: Bumblebee-$(echo "$MAC" | tr -d ':' | tail -c 5 | tr '[:lower:]' '[:upper:]')${CUSTOM:+ (custom name in $NAME_FILE wins: $CUSTOM)}"
fi

{
    echo "systemctl daemon-reload || true"
    echo "systemctl restart wifi-manager wifi-watchdog sys_metrics bumblebee-identity || true"
    echo "echo 'rolled back to the state before $TS'"
} | { [ -n "$SUDO" ] && sed 's/^systemctl/sudo systemctl/' || cat; } >> "$ROLLBACK"
chmod +x "$ROLLBACK"

# ---- 4. stable hotspot SSID --------------------------------------------------
# The profile keeps the random SSID of its last activation until the watchdog
# raises it again; set the stable one now (an active hotspot keeps its current
# SSID until it is next brought up).
if [ -z "$ROOT" ] && [ ${#MAC} -ge 17 ]; then
    HS_SSID="Bumblebee-$(echo "$MAC" | tr -d ':' | tail -c 5 | tr '[:lower:]' '[:upper:]')"
    OLD_SSID=$($SUDO nmcli -g 802-11-wireless.ssid connection show bumblebee-hotspot 2>/dev/null || true)
    if [ -n "$OLD_SSID" ] && [ "$OLD_SSID" != "$HS_SSID" ]; then
        $SUDO nmcli connection modify bumblebee-hotspot wifi.ssid "$HS_SSID"
        echo "$SUDO nmcli connection modify bumblebee-hotspot wifi.ssid '$OLD_SSID'" >> "$ROLLBACK"
        say "hotspot SSID: $OLD_SSID -> $HS_SSID"
    fi
fi

# ---- 5. restart only the non-flight services that changed ------------------
$SUDO systemctl daemon-reload            # unit files and drop-ins may have changed
$SUDO systemctl restart wifi-manager wifi-watchdog sys_metrics
$SUDO systemctl restart bumblebee-identity

say "done. Backup + rollback: $ROLLBACK"
say "Reboot the drone to finish: flight-controller rate detection, the per-drone"
say "ROS domain and the Wi-Fi power-save change take effect after a reboot."
