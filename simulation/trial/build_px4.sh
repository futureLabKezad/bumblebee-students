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

# build_px4.sh [PX4_DIR] - PX4 SITL exactly at the pinned tag/commit
# (versions.env), for CI and the Lima VM. No root needed.
#
#   * clones PX4 at $PX4_TAG (or reuses PX4_DIR) and refuses any other commit
#     or locally modified tracked files;
#   * fetches only the submodules a SITL build uses, shallow, at the commits
#     recorded in the tag (NuttX, Gazebo Classic, jMAVSim etc. are skipped);
#   * pins PX4-OpticalFlow, which PX4 v1.16.1 itself clones at "master",
#     through a local mirror whose master is $PX4_OPTICALFLOW_COMMIT;
#   * builds px4_sitl_default (ccache if present) and checks that the Gazebo
#     bridge and the optical-flow plugin were really built and that the binary
#     embeds the pinned commit.
#
# Env: PX4_DIR (default ~/PX4-Autopilot), VENV (default ~/.venvs/bb-sim-trial),
#      CCACHE_DIR, BUILD_REPORT (file to write key=value results to).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=versions.env
. "$HERE/versions.env"

PX4_DIR="${1:-${PX4_DIR:-$HOME/PX4-Autopilot}}"
VENV="${VENV:-$HOME/.venvs/bb-sim-trial}"
BUILD="$PX4_DIR/build/px4_sitl_default"
MIRROR_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/bb-sim-trial"
OF_MIRROR="$MIRROR_DIR/PX4-OpticalFlow.git"
REPORT="${BUILD_REPORT:-/dev/null}"

die() { echo "build_px4: ERROR: $*" >&2; exit 1; }
log() { echo "[build_px4 $(date -u +%H:%M:%S)] $*"; }
report() { echo "$1=$2" >> "$REPORT"; }

# Submodules needed by px4_sitl_default (PX4 v1.16.1). Anything missing here
# would be initialised by PX4's own Tools/check_submodules.sh during the build
# (slower, full depth) - the build log would show it.
SITL_SUBMODULES=(
    src/modules/mavlink/mavlink
    src/lib/events/libevents
    src/drivers/gps/devices
    src/modules/uxrce_dds_client/Micro-XRCE-DDS-Client
    src/modules/zenoh/zenoh-pico
    src/lib/cdrstream/cyclonedds
    src/lib/cdrstream/rosidl
    src/lib/heatshrink/heatshrink
    src/lib/crypto/monocypher
    src/lib/crypto/libtomcrypt
    src/lib/crypto/libtommath
    src/drivers/cyphal/libcanard
    src/drivers/cyphal/public_regulated_data_types
    src/drivers/cyphal/legacy_data_types
    src/drivers/uavcan/libdronecan/dsdl
    src/drivers/uavcan/libdronecan/libuavcan/dsdl_compiler/pydronecan
    src/drivers/actuators/vertiq_io/iq-module-communication-cpp
    Tools/simulation/gz
)

if [ -x "$VENV/bin/python" ]; then
    export VIRTUAL_ENV="$VENV" PATH="$VENV/bin:$PATH"
else
    log "WARNING: no venv at $VENV (run setup_venv.sh); using $(command -v python3)"
fi
export PYTHONDONTWRITEBYTECODE=1   # keep __pycache__ out of the PX4 source tree
: > "$REPORT"
t0=$SECONDS

# --- 1. Source at the pinned tag ------------------------------------------------
if [ ! -e "$PX4_DIR/.git" ]; then
    log "Cloning PX4 $PX4_TAG into $PX4_DIR"
    git clone --quiet --depth 1 --branch "$PX4_TAG" --no-recurse-submodules "$PX4_REPO" "$PX4_DIR"
fi
head="$(git -C "$PX4_DIR" rev-parse HEAD)"
[ "$head" = "$PX4_COMMIT" ] || die "$PX4_DIR is at $head, expected $PX4_COMMIT ($PX4_TAG)"
tag_commit="$(git -C "$PX4_DIR" rev-parse -q --verify "refs/tags/$PX4_TAG^{commit}" || true)"
[ "$tag_commit" = "$PX4_COMMIT" ] \
    || die "tag $PX4_TAG missing or not at $PX4_COMMIT in $PX4_DIR (PX4's version header needs it)"
if [ -n "$(git -C "$PX4_DIR" status --porcelain --untracked-files=no --ignore-submodules=all)" ]; then
    git -C "$PX4_DIR" status --short --untracked-files=no --ignore-submodules=all >&2
    die "tracked files in $PX4_DIR are modified - the trial must run stock PX4 $PX4_TAG"
fi
log "PX4 $PX4_TAG = $head"

# --- 2. Submodules (shallow, at the gitlinks recorded in the tag) ----------------
log "Submodules for SITL (${#SITL_SUBMODULES[@]})"
git -C "$PX4_DIR" submodule sync --quiet -- "${SITL_SUBMODULES[@]}"
git -C "$PX4_DIR" submodule update --init --recursive --depth 1 --jobs 8 -- "${SITL_SUBMODULES[@]}"
bad="$(git -C "$PX4_DIR" submodule status --recursive -- "${SITL_SUBMODULES[@]}" | grep -E '^[-+U]' || true)"
[ -z "$bad" ] || die "submodules not at the commits recorded in $PX4_TAG:
$bad"
gz_models="$(git -C "$PX4_DIR/Tools/simulation/gz" rev-parse HEAD)"
[ "$gz_models" = "$PX4_GZ_MODELS_COMMIT" ] \
    || die "Tools/simulation/gz at $gz_models, expected $PX4_GZ_MODELS_COMMIT"

# --- 3. PX4-OpticalFlow pinned via a local mirror --------------------------------
# PX4's optical_flow.cmake: ExternalProject GIT_REPOSITORY $PX4_OPTICALFLOW_REPO
# GIT_TAG master. A git "insteadOf" rule (environment only, no ~/.gitconfig
# change) sends that clone to a mirror whose master is the pinned commit.
mkdir -p "$MIRROR_DIR"
if [ ! -d "$OF_MIRROR" ]; then
    log "Mirroring PX4-OpticalFlow"
    git clone --quiet --bare "$PX4_OPTICALFLOW_REPO" "$OF_MIRROR"
fi
git -C "$OF_MIRROR" cat-file -e "$PX4_OPTICALFLOW_COMMIT^{commit}" 2>/dev/null \
    || git -C "$OF_MIRROR" fetch --quiet origin "$PX4_OPTICALFLOW_COMMIT"
git -C "$OF_MIRROR" update-ref refs/heads/master "$PX4_OPTICALFLOW_COMMIT"
export GIT_CONFIG_COUNT=1 \
       GIT_CONFIG_KEY_0="url.file://$OF_MIRROR.insteadOf" \
       GIT_CONFIG_VALUE_0="$PX4_OPTICALFLOW_REPO"

# --- 4. Build ----------------------------------------------------------------------
if command -v ccache >/dev/null; then
    export CCACHE_DIR="${CCACHE_DIR:-$HOME/.cache/ccache}" CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-3G}"
    export CCACHE_BASEDIR="$PX4_DIR" CCACHE_NOHASHDIR=1
    ccache --zero-stats >/dev/null
fi
log "make px4_sitl_default ($(nproc) CPUs)"
tb=$SECONDS
make -C "$PX4_DIR" px4_sitl_default
build_s=$((SECONDS - tb))
log "build took ${build_s}s"
if command -v ccache >/dev/null; then ccache --show-stats || true; fi

# --- 5. Check what was built ---------------------------------------------------------
[ -x "$BUILD/bin/px4" ] || die "no $BUILD/bin/px4"
# PX4 silently skips the Gazebo bridge when gz-transport is not found.
[ -e "$BUILD/bin/px4-gz_bridge" ] || die "gz_bridge module not built (Gazebo dev packages missing?)"
[ -f "$BUILD/rootfs/gz_env.sh" ] || die "no $BUILD/rootfs/gz_env.sh"
[ -f "$BUILD/src/modules/simulation/gz_plugins/libOpticalFlowSystem.so" ] \
    || die "OpticalFlowSystem gz plugin not built (x500_flow needs it)"
of_src="$BUILD/OpticalFlow/src/OpticalFlow"
of_head="$(git -C "$of_src" rev-parse HEAD 2>/dev/null || echo none)"
[ "$of_head" = "$PX4_OPTICALFLOW_COMMIT" ] \
    || die "PX4-OpticalFlow in the build is $of_head, expected $PX4_OPTICALFLOW_COMMIT
(an older build cloned upstream master: remove $BUILD/OpticalFlow and run again)"
ver_h="$BUILD/src/lib/version/build_git_version.h"
grep -q "PX4_GIT_VERSION_STR \"$PX4_COMMIT\"" "$ver_h" || die "binary does not embed commit $PX4_COMMIT"
grep -q "PX4_GIT_TAG_STR \"$PX4_TAG\"" "$ver_h" \
    || die "binary version is $(grep PX4_GIT_TAG_STR "$ver_h"), expected exactly $PX4_TAG (dirty tree?)"
gst="no"
[ -f "$BUILD/src/modules/simulation/gz_plugins/libGstCameraSystem.so" ] && gst="yes"
# Submodules actually checked out (PX4's build may have added some itself);
# every one is at the commit recorded in the tag or the status check fails.
subs="$(git -C "$PX4_DIR" submodule status --recursive | grep -v '^-' || true)"
echo "$subs"
if [[ "$subs" =~ (^|$'\n')[+U] ]]; then die "a submodule moved off its recorded commit during the build"; fi

report px4_tag "$PX4_TAG"
report px4_commit "$head"
report px4_gz_models_commit "$gz_models"
report px4_opticalflow_commit "$of_head"
report gst_camera_plugin_built "$gst"
report build_seconds "$build_s"
report total_seconds "$((SECONDS - t0))"
report nproc "$(nproc)"
report submodules_checked_out "$(echo "$subs" | grep -c . || true)"
log "OK: PX4 $PX4_TAG ($head) SITL ready in $BUILD (GstCameraSystem built: $gst; run_trial.sh never loads it)"
