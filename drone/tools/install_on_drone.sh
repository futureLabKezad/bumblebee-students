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
# Never touches the flight stack: bumblebee.service, MAVROS, simple_offboard
# and PX4 parameters are not restarted or modified. Refuses to run while the
# drone is armed.
#
#   install_on_drone.sh [--reset-name] [--force]
#     --reset-name  forget /home/lb/drone_name and derive a new name (use on
#                   drones flashed from the V1.0.0-beta image, which all
#                   carry "bumblebee-4")
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
        echo "$SUDO cp -p '$BACKUP$dst' '$dest'" >> "$ROLLBACK"
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
if [ "$RESET_NAME" -eq 1 ]; then
    rm -f "$NAME_FILE" "$MAC_FILE"
    say "drone name reset; a new one is derived from the client IP"
elif [ -s "$NAME_FILE" ] && [ ! -s "$MAC_FILE" ] && [ -n "$MAC" ]; then
    # Keep this drone's current name and bind it to its own wlan0 MAC, so a
    # card later cloned into another drone gets a fresh name there.
    echo "$MAC" > "$MAC_FILE"
    say "keeping name '$(tr -d '[:space:]' < "$NAME_FILE")' (bound to $MAC)"
fi
[ -z "$ROOT" ] && chown lb:lb "$NAME_FILE" "$MAC_FILE" 2>/dev/null || true

{
    echo "systemctl restart wifi-manager wifi-watchdog sys_metrics bumblebee-identity || true"
    echo "echo 'rolled back to the state before $TS'"
} | { [ -n "$SUDO" ] && sed 's/^systemctl/sudo systemctl/' || cat; } >> "$ROLLBACK"
chmod +x "$ROLLBACK"

# ---- 4. restart only the non-flight services that changed ------------------
$SUDO systemctl restart wifi-manager wifi-watchdog sys_metrics
$SUDO systemctl restart bumblebee-identity

say "done. Backup + rollback: $ROLLBACK"
say "Wi-Fi power-save change applies on the next reconnect or reboot."
