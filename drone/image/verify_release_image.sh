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
# Independent check of a release image built by make_release_image.sh.
# Runs as root on Linux:  sudo drone/image/verify_release_image.sh IMAGE.img.xz
set -euo pipefail

XZ=${1:?image .img.xz}
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK=$(mktemp -d /var/tmp/bbverify.XXXXXX)
MNT="$WORK/root"
LOOP=""
FAIL=0
cleanup() {
    set +e
    mountpoint -q "$MNT/boot/firmware" && umount "$MNT/boot/firmware"
    mountpoint -q "$MNT" && umount "$MNT"
    [ -n "$LOOP" ] && losetup -d "$LOOP"
    rm -rf "$WORK"
}
trap cleanup EXIT
ok()   { echo "  ok   $*"; }
bad()  { echo "  FAIL $*"; FAIL=1; }
check() { local msg=$1; shift; if "$@"; then ok "$msg"; else bad "$msg"; fi; }

echo "== checksum"
( cd "$(dirname "$XZ")" && sha256sum -c "$(basename "$XZ").sha256" ) && ok "sha256" || bad "sha256"
xz -dc "$XZ" > "$WORK/img"

echo "== partition table"
sfdisk -d "$WORK/img"
LOOP=$(losetup -P --show -fr "$WORK/img")
check "boot partition is FAT32 (type c)" bash -c "sfdisk -d '$WORK/img' | grep -q 'start=        2048,.*type=c'"
check "root fs is clean (e2fsck -n)" e2fsck -fn "${LOOP}p2"

mkdir -p "$MNT"
mount -o ro "${LOOP}p2" "$MNT"
mount -o ro "${LOOP}p1" "$MNT/boot/firmware"
echo "== root fs: $(df -h "$MNT" | awk 'NR==2 {print $2" total, "$4" free"}')"

echo "== free space holds no leftover passwords"
# Password-like strings in the raw image (free space included) that are not in
# any live file are residue of deleted files (e.g. old Wi-Fi configs).
# Strings in live files (package docs/examples) are covered by the checks below.
python3 - "$WORK/img" "$MNT" <<'PY' && ok "no deleted-file password residue" || bad "password residue in free space"
import mmap, re, subprocess, sys, tempfile
img, root = sys.argv[1], sys.argv[2]
pats = [rb'password: "([^"\n]{8,64})"', rb'\bpsk=([^\s]{8,64})']
with open(img, 'rb') as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    values = {m.group(1) for p in pats for m in re.finditer(p, mm)}
values.discard(b'12345678')                    # public hotspot password
with tempfile.NamedTemporaryFile() as tf:      # one pass over the live files for all values
    tf.write(b'\n'.join(values) + b'\n'); tf.flush()
    live = set(subprocess.run(['grep', '-rhoaF', '-f', tf.name, root],
                              capture_output=True).stdout.split(b'\n')) if values else set()
residue = [v for v in values if v not in live]
print('       %d password-like strings, %d not in any live file (values not printed)'
      % (len(values), len(residue)))
sys.exit(1 if residue else 0)
PY

echo "== update installed"
MAN="$REPO/drone/tools/MANIFEST"
while read -r src dst owner mode; do
    case "$src" in ''|'#'*) continue ;; esac
    cmp -s "$REPO/drone/$src" "$MNT$dst" || { bad "content $dst"; continue; }
    want_uid=$(awk -F: -v n="${owner%%:*}" '$1 == n {print $3}' "$MNT/etc/passwd")
    got=$(stat -c '%u %a' "$MNT$dst")
    [ "$got" = "$want_uid $((8#$mode))" ] || [ "$got" = "$want_uid ${mode#0}" ] \
        && ok "$dst ($got)" || bad "$dst owner/mode $got, want uid $want_uid mode $mode"
done < "$MAN"
check "ssh host-key drop-in present" test -f "$MNT/etc/systemd/system/ssh.service.d/10-bumblebee-hostkeys.conf"
check "version stamp" test -s "$MNT/etc/bumblebee_version"
echo "       $(cat "$MNT/etc/bumblebee_version" 2>/dev/null)"

echo "== per-drone state removed"
check "no saved client Wi-Fi profiles" bash -c "! ls '$MNT'/etc/netplan/90-NM-*.yaml | xargs -r grep -L 'name: \"bumblebee-hotspot\"' | grep -q ."
check "hotspot profile kept" bash -c "grep -lq 'name: \"bumblebee-hotspot\"' '$MNT'/etc/netplan/90-NM-*.yaml"
check "no Wi-Fi password in boot network-config" bash -c "! grep -qiE 'wifis|password' '$MNT/boot/firmware/network-config'"
check "no drone_name" test ! -e "$MNT/home/lb/drone_name"
check "no remembered flight-controller rate" test ! -e "$MNT/home/lb/.bumblebee/fcu_url"
check "clock-jump timer enabled" test -L "$MNT/etc/systemd/system/timers.target.wants/bumblebee-clock-jump.timer"
check "ROS domain re-check timer enabled" test -L "$MNT/etc/systemd/system/timers.target.wants/bumblebee-identity-recheck.timer"
check "flight stack records its ROS domain (runtime dir)" grep -qx 'RuntimeDirectory=bumblebee-stack' "$MNT/etc/systemd/system/bumblebee.service.d/stack-domain.conf"
check "services use Fast DDS over UDP" grep -qx 'Environment=FASTDDS_BUILTIN_TRANSPORTS=UDPv4' "$MNT/etc/systemd/system/bumblebee.service.d/ros-env.conf"
check "ROS watchdog enabled" test -L "$MNT/etc/systemd/system/multi-user.target.wants/bumblebee-ros-watchdog.service"
check "no ROS domain baked in (chosen per drone)" bash -c "test ! -e '$MNT/etc/bumblebee/ros.env' && test ! -e '$MNT/etc/bumblebee/ros_domain' && ! grep -q '^ROS_DOMAIN_ID=' '$MNT/etc/environment'"
check "no ROS discovery range forced" bash -c "! grep -rqs ROS_AUTOMATIC_DISCOVERY_RANGE '$MNT'/etc/bumblebee '$MNT'/etc/systemd/system '$MNT'/etc/profile.d '$MNT'/home/lb/start_bumblebee.sh"
check "launch file: src and install copies match" cmp -s "$MNT/home/lb/ros2_ws/src/bumblebee/launch/bumblebee.launch.py" "$MNT/home/lb/ros2_ws/install/bumblebee/share/bumblebee/launch/bumblebee.launch.py"
check "machine-id empty" test ! -s "$MNT/etc/machine-id"
check "no ssh host keys" bash -c "! ls '$MNT'/etc/ssh/ssh_host_* >/dev/null 2>&1"
check "no shell history" bash -c "test ! -e '$MNT/home/lb/.bash_history' && test ! -e '$MNT/root/.bash_history'"
check "journal empty" bash -c "[ -z \"\$(ls -A '$MNT'/var/log/journal 2>/dev/null)\" ]"
check "no dev backups in /home/lb" bash -c "! ls -d '$MNT'/home/lb/bumblebee-backup-* >/dev/null 2>&1"
check "hostname reset" grep -qx bumblebee "$MNT/etc/hostname"
check "no credentials in cloud-init cache / backups" bash -c "! grep -rlsE 'password|passwd|psk' '$MNT/var/lib/cloud' '$MNT/var/backups' | grep -q ."
check "cloud-init instance marker kept" bash -c "ls -d '$MNT'/var/lib/cloud/instances/*/ >/dev/null 2>&1 && test -e '$MNT/var/lib/cloud/data/instance-id'"
check "no crash dumps" bash -c "[ -z \"\$(ls -A '$MNT'/var/crash 2>/dev/null)\" ]"
check "random-seed removed" test ! -e "$MNT/var/lib/systemd/random-seed"
check "iSCSI initiator name reset" grep -qx 'GenerateName=yes' "$MNT/etc/iscsi/initiatorname.iscsi"
check "boot user-data password is the documented 'lb'" python3 -W ignore -c "
import crypt, re, sys
h = re.search(r'^\s*passwd:\s*\"?([^\"\s]+)', open('$MNT/boot/firmware/user-data').read(), re.M).group(1)
sys.exit(0 if crypt.crypt('lb', h) == h else 1)"

echo "== things that must still be there"
for p in /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/simple_offboard \
         /home/lb/ros2_ws/install/bumblebee/lib/bumblebee/qos_relay.py \
         /home/lb/libcamera/build/src/v4l2/v4l2-compat.so \
         /home/lb/opencv47_venv/bin/python3 /home/lb/mavros_params.yaml \
         /home/lb/ov5647_aruco.json /home/lb/.ros/camera_info/main_camera_640x480.yaml \
         /etc/systemd/system/bumblebee.service /etc/polkit-1/rules.d/49-bumblebee-nm.rules \
         /var/lib/cloud/instances /boot/firmware/user-data /boot/firmware/meta-data; do
    check "$p" test -e "$MNT$p"
done

echo
[ "$FAIL" = 0 ] && echo "ALL CHECKS PASSED" || { echo "SOME CHECKS FAILED"; exit 1; }
