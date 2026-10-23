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
    # PX4's own heartbeat, read from MAVROS's GCS port -- not /mavros/state,
    # which on a shared ROS domain can be another drone's.
    FCU=$(python3 "$HERE/payload/ros2_ws/src/bumblebee/scripts/fcu_armed.py" 2>/dev/null || true)
    if [ "$FCU" = "armed" ]; then
        say "drone is ARMED - refusing to update. Land and disarm first."
        exit 1
    fi
    if [ "$FCU" != "disarmed" ]; then
        say "could not read the flight controller's state (MAVROS not running?). Re-run with --force if the drone is on the ground."
        exit 1
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

# /etc/environment is not shipped but rewritten: set_identity.sh keeps this
# drone's ROS_DOMAIN_ID in it. Rollback restores it as it was before; copied
# before anything new is installed (the new NetworkManager hook could run
# set_identity.sh mid-install).
ENV_FILE="$ROOT/etc/environment"
if [ -e "$ENV_FILE" ]; then
    mkdir -p "$BACKUP/etc"
    $SUDO cp -p "$ENV_FILE" "$BACKUP/etc/environment"
    echo "$SUDO cp -p '$BACKUP/etc/environment' '$ENV_FILE.bbnew'" >> "$ROLLBACK"
    echo "$SUDO mv -f '$ENV_FILE.bbnew' '$ENV_FILE'" >> "$ROLLBACK"
fi

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

# Version stamp: GET /api/info and check_drone.sh report the first line of
# /etc/bumblebee_version. The new first line names this update; the image's
# own lines stay below it. Rollback puts the old file back.
VERSION_FILE="$ROOT/etc/bumblebee_version"
if [ -s "$HERE/VERSION" ]; then
    NEW_VERSION="Bumblebee $(head -n 1 "$HERE/VERSION"), update installed $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if [ -e "$VERSION_FILE" ]; then
        mkdir -p "$BACKUP/etc"
        $SUDO cp -p "$VERSION_FILE" "$BACKUP/etc/bumblebee_version"
        echo "$SUDO cp -p '$BACKUP/etc/bumblebee_version' '$VERSION_FILE'" >> "$ROLLBACK"
    else
        echo "$SUDO rm -f '$VERSION_FILE'" >> "$ROLLBACK"
    fi
    {
        echo "$NEW_VERSION"
        [ -e "$VERSION_FILE" ] && sed 's/^\(before: \)*/before: /' "$VERSION_FILE"   # one prefix after several updates
    } > "$BACKUP/bumblebee_version.new"
    $SUDO mkdir -p "$(dirname "$VERSION_FILE")"
    $SUDO install -m 0644 "$BACKUP/bumblebee_version.new" "$VERSION_FILE"
    rm -f "$BACKUP/bumblebee_version.new"
    say "version: $NEW_VERSION"
else
    say "no VERSION in the bundle: /etc/bumblebee_version left as it is"
fi

# Enable the clock-jump reaction and the per-minute domain re-check. Symlinks
# rather than `systemctl enable`, so it works the same on a running drone and
# on a mounted image (BB_ROOT).
WANTS="$ROOT/etc/systemd/system/timers.target.wants"
for t in bumblebee-clock-jump.timer bumblebee-identity-recheck.timer; do
    if [ ! -e "$WANTS/$t" ]; then
        $SUDO mkdir -p "$WANTS"
        $SUDO ln -sf "/etc/systemd/system/$t" "$WANTS/$t"
        echo "$SUDO rm -f '$WANTS/$t'" >> "$ROLLBACK"
        say "enabled $t"
    fi
done

MU_WANTS="$ROOT/etc/systemd/system/multi-user.target.wants"
if [ ! -e "$MU_WANTS/bumblebee-ros-watchdog.service" ]; then
    $SUDO mkdir -p "$MU_WANTS"
    $SUDO ln -sf /etc/systemd/system/bumblebee-ros-watchdog.service "$MU_WANTS/bumblebee-ros-watchdog.service"
    echo "$SUDO rm -f '$MU_WANTS/bumblebee-ros-watchdog.service'" >> "$ROLLBACK"
    say "enabled bumblebee-ros-watchdog.service"
fi

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
    CUSTOM=""
    [ -s "$NAME_FILE" ] && CUSTOM=$(tr -d '[:space:]' < "$NAME_FILE")
    case "$CUSTOM" in
        ''|bumblebee-[0-9]|bumblebee-[0-9][0-9]|bumblebee-[0-9][0-9][0-9]) CUSTOM="" ;;  # IP-derived: retired
    esac
    say "drone name: Bumblebee-$(echo "$MAC" | tr -d ':' | tail -c 5 | tr '[:lower:]' '[:upper:]')${CUSTOM:+ (custom name in $NAME_FILE wins: $CUSTOM)}"
fi

{
    echo "systemctl stop bumblebee-clock-jump.timer bumblebee-identity-recheck.timer bumblebee-ros-watchdog || true"
    echo "systemctl daemon-reload || true"
    echo "systemctl restart wifi-manager wifi-watchdog sys_metrics notify-manager bumblebee-identity || true"
    echo "echo 'rolled back to the state before $TS'"
    echo "echo 'Reboot the drone now (sudo reboot): the flight stack still runs with the update until then.'"
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
$SUDO systemctl start bumblebee-clock-jump.timer bumblebee-identity-recheck.timer || true
$SUDO systemctl restart bumblebee-ros-watchdog || true
[ -z "$ROOT" ] && $SUDO sysctl --system >/dev/null 2>&1 || true   # bigger DDS socket buffers
$SUDO systemctl restart wifi-manager wifi-watchdog sys_metrics
$SUDO systemctl restart notify-manager || true   # LED alarms; not part of the flight stack
$SUDO systemctl restart bumblebee-identity

say "done. Backup + rollback: $ROLLBACK"
say "Reboot the drone to finish: flight-controller rate detection, the per-drone"
say "ROS domain, the Wi-Fi power-save change and the video server take effect after a reboot."
