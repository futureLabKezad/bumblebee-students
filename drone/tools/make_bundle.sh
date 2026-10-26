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
# Build the drone update bundle: a tar.gz with install_on_drone.sh, MANIFEST
# and the listed files. Copy it to a drone by any means (scp, USB stick) and
# run it there:
#
#   drone/tools/make_bundle.sh [OUT.tgz [VERSION]]  # default: ./bumblebee-update.tgz, drone/VERSION
#   # on the drone, as user lb:
#   tar -xzf bumblebee-update.tgz && bash bb-update/install_on_drone.sh [--reset-name]
#
# bb-update/VERSION holds "<version> (repo <commit>)"; install_on_drone.sh
# writes it into /etc/bumblebee_version, which GET /api/info and
# check_drone.sh report.
set -euo pipefail

TOOLS="$(cd "$(dirname "$0")" && pwd)"
DRONE_DIR="$(dirname "$TOOLS")"
OUT="${1:-$PWD/bumblebee-update.tgz}"
VERSION="${2:-$(tr -d '[:space:]' < "$DRONE_DIR/VERSION")}"
[ -n "$VERSION" ] || { echo "no version: pass one or fill $DRONE_DIR/VERSION" >&2; exit 2; }
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/bb-update/payload"
cp "$TOOLS/install_on_drone.sh" "$TOOLS/MANIFEST" "$STAGE/bb-update/"
while read -r src _; do
    case "$src" in ''|'#'*) continue ;; esac
    mkdir -p "$STAGE/bb-update/payload/$(dirname "$src")"
    cp "$DRONE_DIR/$src" "$STAGE/bb-update/payload/$src"
done < "$TOOLS/MANIFEST"
# Record the version and the commit the bundle was built from.
COMMIT=$(git -c safe.directory='*' -C "$DRONE_DIR" describe --always --dirty 2>/dev/null || echo unknown)
echo "$VERSION (repo $COMMIT)" > "$STAGE/bb-update/VERSION"
# macOS (bsdtar): keep extended attributes / AppleDouble files out of the
# archive, otherwise GNU tar on the drone warns about unknown headers.
TAR_OPTS=()
tar --version 2>/dev/null | grep -q bsdtar && TAR_OPTS=(--no-xattrs --no-mac-metadata)
COPYFILE_DISABLE=1 tar ${TAR_OPTS[@]+"${TAR_OPTS[@]}"} -C "$STAGE" -czf "$OUT" bb-update
echo "$OUT ($(cat "$STAGE/bb-update/VERSION"))"
