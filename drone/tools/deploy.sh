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
# Push the files listed in MANIFEST to a running drone and install them
# (with backup + rollback.sh) via install_on_drone.sh. Run from a laptop:
#
#   drone/tools/deploy.sh <drone-ip-or-name.local> [--reset-name] [--force]
#
# You will be asked for the `lb` password (ssh, then sudo on the drone).
set -euo pipefail

[ $# -ge 1 ] || { sed -n '16,22p' "$0"; exit 2; }
HOST="$1"; shift
case "$HOST" in *@*) ;; *) HOST="lb@$HOST" ;; esac

TOOLS="$(cd "$(dirname "$0")" && pwd)"
DRONE_DIR="$(dirname "$TOOLS")"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE/bb-update/payload"
cp "$TOOLS/install_on_drone.sh" "$TOOLS/MANIFEST" "$STAGE/bb-update/"
while read -r src _; do
    case "$src" in ''|'#'*) continue ;; esac
    mkdir -p "$STAGE/bb-update/payload/$(dirname "$src")"
    cp "$DRONE_DIR/$src" "$STAGE/bb-update/payload/$src"
done < "$TOOLS/MANIFEST"
COPYFILE_DISABLE=1 tar -C "$STAGE" -czf "$STAGE/bb-update.tgz" bb-update

echo "Uploading update to $HOST ..."
scp -q "$STAGE/bb-update.tgz" "$HOST:/tmp/bb-update.tgz"
ssh -t "$HOST" "rm -rf /tmp/bb-update && tar -C /tmp -xzf /tmp/bb-update.tgz && bash /tmp/bb-update/install_on_drone.sh $*"
