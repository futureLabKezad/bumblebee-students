#!/usr/bin/env bash
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

# install_deps.sh - system packages for the simulator trial on Ubuntu 24.04
# (amd64 in CI, arm64 in the Lima VM). Needs root: sudo ./install_deps.sh
#
#   1. Ubuntu packages listed in apt-ubuntu.txt (from whatever archive apt
#      points at; CI points it at a dated snapshot first). The .deb files are
#      downloaded beforehand by apt_prefetch.sh: in parallel, each checked
#      against the hash in apt's signed index, in CI mostly from the Azure
#      Ubuntu mirror (identical files; the snapshot is slow).
#   2. Gazebo Harmonic from packages.osrfoundation.org at the exact versions
#      in apt-gz-harmonic.txt (apt key checked by sha256), then a check that
#      every installed OSRF package is in that list at that version.
#
# Same repository file and keyring path as PX4's Tools/setup/ubuntu.sh, so it
# coexists with a machine that was set up the PX4 way.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=versions.env
. "$HERE/versions.env"

die() { echo "install_deps: ERROR: $*" >&2; exit 1; }
log() { echo "[install_deps $(date -u +%H:%M:%S)] $*"; }
# Package lines of a list file (comments and blank lines dropped).
pkgs() { sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^[[:space:]]*$/d' "$1"; }

[ "$(id -u)" = 0 ] || die "run as root (sudo $0)"
# shellcheck source=/dev/null
. /etc/os-release
[ "${VERSION_CODENAME:-}" = noble ] || die "needs Ubuntu 24.04 (noble), found ${PRETTY_NAME:-unknown}"

export DEBIAN_FRONTEND=noninteractive LC_ALL=C   # C collation for sort/comm below
APT_INSTALL=(apt-get install -y --no-install-recommends -o Dpkg::Use-Pty=0)
# Download what the next install needs first: in parallel, from
# UBUNTU_POOL_MIRRORS where possible, every file checked against the index apt
# already verified (apt_prefetch.sh). Whatever it misses, apt-get fetches itself.
prefetch() {
    xargs "$HERE/apt_prefetch.sh" \
        || log "prefetch failed (exit $?); apt-get downloads the packages itself"
}

log "Ubuntu packages ($(pkgs "$HERE/apt-ubuntu.txt" | wc -l) from apt-ubuntu.txt)"
apt-get update
pkgs "$HERE/apt-ubuntu.txt" | prefetch
pkgs "$HERE/apt-ubuntu.txt" | xargs "${APT_INSTALL[@]}"

log "Gazebo Harmonic apt repository (key sha256 $OSRF_KEY_SHA256)"
keyring=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg
tmpkey="$(mktemp)"
curl -fsSL --retry 5 "$OSRF_KEY_URL" -o "$tmpkey"
echo "$OSRF_KEY_SHA256  $tmpkey" | sha256sum -c - >/dev/null \
    || die "OSRF apt key at $OSRF_KEY_URL does not match the pinned sha256"
install -m 0644 "$tmpkey" "$keyring"
rm -f "$tmpkey"
echo "deb [arch=$(dpkg --print-architecture) signed-by=$keyring] $OSRF_APT_URL noble main" \
    > /etc/apt/sources.list.d/gazebo-stable.list
apt-get update

log "Gazebo Harmonic packages ($(pkgs "$HERE/apt-gz-harmonic.txt" | wc -l) pinned in apt-gz-harmonic.txt)"
pkgs "$HERE/apt-gz-harmonic.txt" | prefetch
if ! pkgs "$HERE/apt-gz-harmonic.txt" | xargs "${APT_INSTALL[@]}"; then
    echo "::error::Pinned Gazebo Harmonic versions are not installable. packages.osrfoundation.org" \
         "keeps only the newest build of each package; if Harmonic was updated, regenerate" \
         "simulation/trial/apt-gz-harmonic.txt (see README.md) and re-run the trial." >&2
    exit 1
fi

log "Checking installed Gazebo packages against the pins"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
pkgs "$HERE/apt-gz-harmonic.txt" | sort > "$tmp/pins"
dpkg-query -W -f '${db:Status-Abbrev} ${Package}=${Version}\n' \
    | awk '$1 == "ii" { print $2 }' | sort > "$tmp/installed"
# Every pin installed at exactly that version ...
missing="$(comm -23 "$tmp/pins" "$tmp/installed")"
[ -z "$missing" ] || die "pinned packages not installed at the pinned version:
$missing"
# ... and no other OSRF package. OSRF noble builds carry "~noble" in the
# version (Ubuntu's own noble archive has none), e.g. 8.15.0-1~noble.
grep -E '=[^=]*~noble' "$tmp/installed" > "$tmp/osrf" || true
extra="$(comm -13 "$tmp/pins" "$tmp/osrf")"
[ -z "$extra" ] || die "OSRF packages installed that are not pinned in apt-gz-harmonic.txt:
$extra"

gz_ver="$(gz sim --versions 2>/dev/null || true)"
gz_ver="${gz_ver%%$'\n'*}"
gz_ver="${gz_ver//[[:space:]]/}"
[ "$gz_ver" = "$GZ_SIM_VERSION" ] || die "gz sim reports '$gz_ver', expected $GZ_SIM_VERSION"
log "OK: $(wc -l < "$tmp/pins") Gazebo packages exactly as pinned, gz sim $gz_ver"
