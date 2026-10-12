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
# Build a release SD image from a base image (the V1.0.0-beta snapshot):
#   1. apply the drone update from drone/tools (same files as deploy.sh),
#   2. strip per-drone state (Wi-Fi passwords, name, host keys, logs, history,
#      backups) so every flashed drone starts clean and gets its own identity,
#   3. shrink the root filesystem (cloud-init growpart/resizefs grow it back to
#      the card size on first boot) and compress for Raspberry Pi Imager.
#
# Runs as root on Linux (e.g. the Lima VM, or a CI runner):
#   sudo drone/image/make_release_image.sh BASE.img[.gz|.xz] OUT_DIR VERSION
set -euo pipefail

BASE=${1:?base image (.img, .img.gz or .img.xz)}
OUT=${2:?output directory}
VERSION=${3:?version, e.g. 1.0.1-rc1}
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
NAME="bumblebee-$VERSION-rpi5"
SLACK_MB=1024            # free space left in the shrunk root fs before first boot

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
for t in losetup e2fsck resize2fs sfdisk xz tar install zerofree openssl python3; do
    command -v "$t" >/dev/null || { echo "missing tool: $t" >&2; exit 1; }
done

say() { echo "==> $*"; }
WORK=$(mktemp -d /var/tmp/bbimg.XXXXXX)
MNT="$WORK/root"
IMG="$WORK/$NAME.img"
LOOP=""
cleanup() {
    set +e
    mountpoint -q "$MNT/boot/firmware" && umount "$MNT/boot/firmware"
    mountpoint -q "$MNT" && umount "$MNT"
    [ -n "$LOOP" ] && losetup -d "$LOOP"
    rm -rf "$WORK"
}
trap cleanup EXIT

# ---- 1. sparse working copy --------------------------------------------------
say "copying base image (sparse)"
case "$BASE" in
    *.gz) zcat "$BASE" | dd of="$IMG" bs=4M conv=sparse status=none ;;
    *.xz) xz -dc "$BASE" | dd of="$IMG" bs=4M conv=sparse status=none ;;
    *)    cp --sparse=always "$BASE" "$IMG" ;;
esac
LOOP=$(losetup -P --show -f "$IMG")
e2fsck -fy "${LOOP}p2" >/dev/null || [ $? -le 1 ]
mkdir -p "$MNT"
mount "${LOOP}p2" "$MNT"
mount "${LOOP}p1" "$MNT/boot/firmware"

# numeric owner of a "user:group" pair *inside the image*
img_owner() {
    local u=${1%%:*} g=${1#*:} uid gid
    uid=$(awk -F: -v n="$u" '$1 == n {print $3}' "$MNT/etc/passwd")
    gid=$(awk -F: -v n="$g" '$1 == n {print $3}' "$MNT/etc/group")
    [ -n "$uid" ] && [ -n "$gid" ] || { echo "no $1 in image" >&2; exit 1; }
    echo "$uid:$gid"
}

# ---- 2. apply the drone update -------------------------------------------------
say "applying drone update"
"$REPO/drone/tools/make_bundle.sh" "$WORK/bundle.tgz" >/dev/null
tar -C "$WORK" -xzf "$WORK/bundle.tgz"
BB_ROOT="$MNT" bash "$WORK/bb-update/install_on_drone.sh" --reset-name >/dev/null
rm -rf "$MNT/home/lb/.bumblebee-update"           # no rollback data in a release
while read -r src dst owner mode; do               # owners by image uid/gid
    case "$src" in ''|'#'*) continue ;; esac
    chown "$(img_owner "$owner")" "$MNT$dst"
    chmod "$mode" "$MNT$dst"
done < "$WORK/bb-update/MANIFEST"

# ---- 3. strip per-drone state ------------------------------------------------------
say "stripping per-drone state"
# per-drone runtime state (remembered flight-controller rate, ROS domain, ...)
rm -rf "$MNT/home/lb/.bumblebee"
rm -f "$MNT/etc/bumblebee/ros.env" "$MNT/etc/bumblebee/ros_domain"
sed -i '/^ROS_DOMAIN_ID=/d' "$MNT/etc/environment"
# identity: derived again on each drone (set_identity.sh)
rm -f "$MNT/home/lb/drone_name" "$MNT/home/lb/drone_name.mac" \
      "$MNT/etc/avahi/services/bumblebee.service"
echo bumblebee > "$MNT/etc/hostname"
# saved client Wi-Fi networks (with their passwords); keep the hotspot profile
for f in "$MNT"/etc/netplan/90-NM-*.yaml; do
    [ -e "$f" ] || continue
    grep -q 'name: "bumblebee-hotspot"' "$f" || rm -f "$f"
done
rm -f "$MNT"/etc/NetworkManager/system-connections/*
rm -f "$MNT"/var/lib/NetworkManager/*.lease "$MNT"/var/lib/NetworkManager/timestamps \
      "$MNT"/var/lib/NetworkManager/seen-bssids "$MNT"/var/lib/NetworkManager/secret_key
# boot partition cloud-init network config: drop any Wi-Fi credentials
if [ -f "$MNT/boot/firmware/network-config" ]; then
    cat > "$MNT/boot/firmware/network-config" <<'NETCFG'
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: true
      dhcp6: true
      optional: true
NETCFG
fi
rm -rf "$MNT/boot/firmware/System Volume Information"   # Windows chkdsk leftover
# boot partition cloud-init user-data: the seed carried the hash of a private
# password (set in Raspberry Pi Imager for the dev card). It is only used if
# cloud-init ever sees a new instance; make it the documented default "lb",
# the same password /etc/shadow has.
if [ -f "$MNT/boot/firmware/user-data" ]; then
    LB_HASH=$(openssl passwd -6 lb)
    LB_HASH="$LB_HASH" python3 - "$MNT/boot/firmware/user-data" <<'PY'
import os, re, sys
p = sys.argv[1]
text = open(p).read()
text = re.sub(r'^(\s*passwd:\s*).*$', lambda m: m.group(1) + '"%s"' % os.environ['LB_HASH'],
              text, flags=re.M)
open(p, 'w').write(text)
PY
fi
# cloud-init keeps copies of the seed it booted with (user-data with the
# password hash, network-config with Wi-Fi passwords) in its instance cache.
# Drop those copies but keep the instance markers, so cloud-init does not
# treat the first boot of a flashed card as a new instance (it re-reads the
# seed from the boot partition when the cache is gone).
for d in "$MNT"/var/lib/cloud/instances/*/; do
    [ -d "$d" ] || continue
    rm -f "$d"obj.pkl "$d"user-data.txt* "$d"vendor-data*.txt* "$d"cloud-config.txt \
          "$d"network-config* "$d"datasource
done
rm -f "$MNT"/var/lib/cloud/data/*.json "$MNT"/var/lib/cloud/data/previous-hostname
# unique per machine: regenerated on first boot
: > "$MNT/etc/machine-id"
rm -f "$MNT/var/lib/systemd/random-seed"
if [ -e "$MNT/etc/iscsi/initiatorname.iscsi" ]; then   # reset, as the package ships it:
    printf 'GenerateName=yes\n' > "$MNT/etc/iscsi/initiatorname.iscsi"   # unique name on first use
    chmod 600 "$MNT/etc/iscsi/initiatorname.iscsi"
fi
rm -f "$MNT"/etc/ssh/ssh_host_*
install -d "$MNT/etc/systemd/system/ssh.service.d"
install -m 0644 "$REPO/drone/image/ssh-hostkeys.conf" \
    "$MNT/etc/systemd/system/ssh.service.d/10-bumblebee-hostkeys.conf"
# logs, shell history, temp files, ROS logs, package cache
rm -rf "$MNT"/var/log/journal/*
find "$MNT/var/log" -type f \( -name '*.gz' -o -name '*.[0-9]' -o -name '*.old' \) -delete
find "$MNT/var/log" -type f -exec truncate -s 0 {} +
rm -f "$MNT"/home/lb/.bash_history "$MNT"/root/.bash_history \
      "$MNT"/home/lb/.python_history "$MNT"/home/lb/.lesshst "$MNT"/home/lb/.viminfo "$MNT"/root/.viminfo
rm -rf "$MNT"/home/lb/.ros/log "$MNT"/tmp/* "$MNT"/var/tmp/*
rm -f "$MNT"/var/cache/apt/archives/*.deb
rm -rf "$MNT"/var/crash/* "$MNT"/var/backups/*           # crash dumps; old passwd/shadow copies
rm -rf "$MNT"/home/lb/ros2_ws/log "$MNT"/home/lb/.cache "$MNT"/home/lb/.sudo_as_admin_successful
# hand-made backups and freeze dumps from the development drone
rm -rf "$MNT"/home/lb/bumblebee-backup-* "$MNT"/home/lb/freeze_* "$MNT"/home/lb/examples_baks_*
find "$MNT/home/lb" -maxdepth 1 -name '*.bak*' -delete
find "$MNT/home/lb/ros2_ws/src" "$MNT/home/lb/ros2_ws/install" -type f -name '*.bak*' -delete

# ---- 4. version stamp --------------------------------------------------------------
COMMIT=$(git -c safe.directory='*' -C "$REPO" describe --always --dirty 2>/dev/null || echo unknown)
printf 'Bumblebee %s (repo %s), built %s from %s\n' \
    "$VERSION" "$COMMIT" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(basename "$BASE")" \
    > "$MNT/etc/bumblebee_version"

# ---- 5. checks -------------------------------------------------------------------
say "checking"
if grep -rlE 'psk|password' "$MNT"/etc/netplan "$MNT"/etc/NetworkManager/system-connections 2>/dev/null \
        | xargs -r grep -L 'name: "bumblebee-hotspot"' | grep .; then
    echo "client Wi-Fi credentials left in the image" >&2; exit 1
fi
if grep -rlsE 'password|passwd|psk' "$MNT/var/lib/cloud" "$MNT/var/backups" | grep .; then
    echo "credentials left in the cloud-init cache / backups" >&2; exit 1
fi
[ -s "$MNT/etc/machine-id" ] && { echo "machine-id not cleared" >&2; exit 1; }
ls "$MNT"/etc/ssh/ssh_host_* >/dev/null 2>&1 && { echo "ssh host keys left" >&2; exit 1; }
while read -r src dst _; do
    case "$src" in ''|'#'*) continue ;; esac
    cmp -s "$WORK/bb-update/payload/$src" "$MNT$dst" || { echo "not installed: $dst" >&2; exit 1; }
done < "$WORK/bb-update/MANIFEST"

# Deleted files stay readable in free space (old Wi-Fi passwords, history,
# logs). Zero the free clusters of the FAT boot partition here; the root fs
# is zeroed with zerofree after shrinking.
dd if=/dev/zero of="$MNT/boot/firmware/.zero" bs=1M status=none 2>/dev/null || true
sync; rm -f "$MNT/boot/firmware/.zero"; sync

umount "$MNT/boot/firmware" "$MNT"

# ---- 6. shrink -------------------------------------------------------------------
say "shrinking root filesystem"
e2fsck -fy "${LOOP}p2" >/dev/null || [ $? -le 1 ]
resize2fs -M "${LOOP}p2" >/dev/null 2>&1
BS=$(dumpe2fs -h "${LOOP}p2" 2>/dev/null | awk -F: '/^Block size/ {gsub(/ /,"",$2); print $2}')
BLOCKS=$(dumpe2fs -h "${LOOP}p2" 2>/dev/null | awk -F: '/^Block count/ {gsub(/ /,"",$2); print $2}')
BLOCKS=$((BLOCKS + SLACK_MB * 1024 * 1024 / BS))
resize2fs "${LOOP}p2" "$BLOCKS" >/dev/null 2>&1
e2fsck -fy "${LOOP}p2" >/dev/null || [ $? -le 1 ]
say "zeroing free space"
zerofree "${LOOP}p2"
START=$(sfdisk -d "$IMG" | awk -F'[=,]' '/'"$(basename "$IMG")"'2 / {gsub(/ /,"",$2); print $2}')
SECTORS=$(( (BLOCKS * BS + 511) / 512 ))
SECTORS=$(( (SECTORS + 2047) / 2048 * 2048 ))   # round up to 1 MiB
losetup -d "$LOOP"; LOOP=""
echo "start=$START, size=$SECTORS" | sfdisk --no-reread -N 2 "$IMG" >/dev/null
truncate -s $(( (START + SECTORS) * 512 )) "$IMG"

# ---- 7. compress ------------------------------------------------------------------
say "compressing"
mkdir -p "$OUT"
xz -T0 -6 -c "$IMG" > "$OUT/$NAME.img.xz"
(cd "$OUT" && sha256sum "$NAME.img.xz" > "$NAME.img.xz.sha256")
say "done: $OUT/$NAME.img.xz ($(du -h "$OUT/$NAME.img.xz" | cut -f1), raw $(du -h --apparent-size "$IMG" | cut -f1))"
cat "$OUT/$NAME.img.xz.sha256"
