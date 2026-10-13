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

# run_trial.sh - one simulator trial run, identical in CI and in the Lima VM:
#
#   1. Gazebo Harmonic server, headless, cameras rendered on the CPU (Mesa
#      llvmpipe through Xvfb/GLX, or EGL with --render egl);
#   2. PX4 v1.16.1 SITL (stock airframe of --model) attached to it;
#   3. measure_rtf.py: RTF for --rtf-seconds with every camera subscribed
#      (= rendering), plus CPU/RAM of gz and px4;
#   4. smoke_flights.py: --flights automated flights (RTF/CPU/RAM sampled
#      in the background meanwhile);
#   5. stop everything, summarize.py -> summary.md / summary.json.
#
# Usage: run_trial.sh [--model x500_flow|x500_mono_cam_down] [--flights 10]
#                     [--rtf-seconds 120] [--min-rtf 0.3] [--render xvfb|egl]
#                     [--instance 0] [--out DIR]
# Env:   PX4_DIR (~/PX4-Autopilot, built by build_px4.sh), VENV
#        (~/.venvs/bb-sim-trial), GZ_VERBOSE (2), GZ_IP (127.0.0.1)
# Exit:  0 = trial criteria met, 1 = not met, 2 = could not run.
#
# Simulator only: MAVLink stays on 127.0.0.1 (PX4 SITL UDP ports) and gz
# transport on 127.0.0.1 in a private GZ_PARTITION; nothing reaches a drone.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=versions.env
. "$HERE/versions.env"

MODEL=x500_flow FLIGHTS=10 RTF_SECONDS=120 MIN_RTF=0.3 RENDER=xvfb INSTANCE=0 OUT=""
WORLD=default
usage() { sed -n '/^# Usage:/,/^# Exit:/p' "$0" | sed 's/^# \{0,1\}//'; }
while [ $# -gt 0 ]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --flights) FLIGHTS="$2"; shift 2 ;;
        --rtf-seconds) RTF_SECONDS="$2"; shift 2 ;;
        --min-rtf) MIN_RTF="$2"; shift 2 ;;
        --render) RENDER="$2"; shift 2 ;;
        --instance) INSTANCE="$2"; shift 2 ;;
        --out) OUT="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

die() { echo "run_trial: ERROR: $*" >&2; exit 2; }
case "$MODEL" in x500_flow|x500_mono_cam_down) ;; *) die "--model must be x500_flow or x500_mono_cam_down" ;; esac
case "$RENDER" in xvfb|egl) ;; *) die "--render must be xvfb or egl" ;; esac
[[ "$FLIGHTS" =~ ^[0-9]+$ ]] || die "--flights must be a whole number"
[[ "$RTF_SECONDS" =~ ^[1-9][0-9]*$ ]] || die "--rtf-seconds must be a positive whole number"
[[ "$MIN_RTF" =~ ^[0-9]*\.?[0-9]+$ ]] || die "--min-rtf must be a number"
[[ "$INSTANCE" =~ ^[0-9]$ ]] || die "--instance must be 0-9"
airframe_var="AIRFRAME_$MODEL"
AIRFRAME="${!airframe_var}"

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
BUILD="$PX4_DIR/build/px4_sitl_default"
VENV="${VENV:-$HOME/.venvs/bb-sim-trial}"
if [ -x "$VENV/bin/python" ]; then PY="$VENV/bin/python"; else PY="$(command -v python3)"; fi
GZ_VERBOSE="${GZ_VERBOSE:-2}"
MAV_PORT=$((14540 + INSTANCE))

OUT="${OUT:-$PWD/sim-trial-out/$MODEL-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
[ ! -e "$OUT/px4_rootfs" ] || die "$OUT was used by an earlier run - pass a new --out"
CMDLOG="$OUT/commands.log"
: > "$CMDLOG"
note() { echo "[$(date -u +%FT%TZ)] $*" | tee -a "$CMDLOG"; }
T0=$SECONDS
TIMES=""
mark() { TIMES="$TIMES\"$1\": $((SECONDS - T0)), "; note "phase $1 (+$((SECONDS - T0)) s)"; }

# ------------------------------------------------------------------ preflight
[ -x "$BUILD/bin/px4" ] || die "no PX4 SITL build in $BUILD (run build_px4.sh)"
ver_h="$BUILD/src/lib/version/build_git_version.h"
grep -q "PX4_GIT_VERSION_STR \"$PX4_COMMIT\"" "$ver_h" && grep -q "PX4_GIT_TAG_STR \"$PX4_TAG\"" "$ver_h" \
    || die "$BUILD is not PX4 $PX4_TAG ($PX4_COMMIT) - rebuild with build_px4.sh"
of_head="$(git -C "$BUILD/OpticalFlow/src/OpticalFlow" rev-parse HEAD 2>/dev/null || echo none)"
[ "$of_head" = "$PX4_OPTICALFLOW_COMMIT" ] || die "PX4-OpticalFlow in the build is $of_head, expected $PX4_OPTICALFLOW_COMMIT"
command -v gz >/dev/null || die "gz not found (install_deps.sh)"
gz_ver="$(gz sim --versions 2>/dev/null || true)"
gz_ver="${gz_ver%%$'\n'*}"
gz_ver="${gz_ver//[[:space:]]/}"
[ "$gz_ver" = "$GZ_SIM_VERSION" ] || die "gz sim $gz_ver installed, expected $GZ_SIM_VERSION"
"$PY" -c 'import pymavlink, gz.transport13, gz.msgs10' 2>/dev/null \
    || die "$PY lacks pymavlink or the Gazebo Python bindings (setup_venv.sh, install_deps.sh)"
if [ "$RENDER" = xvfb ]; then command -v Xvfb >/dev/null || die "Xvfb not installed"; fi

# ------------------------------------------------------------------ environment
export GZ_IP="${GZ_IP:-127.0.0.1}"
export GZ_PARTITION="bbtrial-${HOSTNAME%%.*}-$$"      # private gz transport namespace
export LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe   # CPU rendering, also where a GPU exists
unset GZ_SIM_RESOURCE_PATH GZ_SIM_SYSTEM_PLUGIN_PATH GZ_SIM_SERVER_CONFIG_PATH
set +u
# shellcheck disable=SC1091
. "$BUILD/rootfs/gz_env.sh"     # PX4_GZ_MODELS/WORLDS/PLUGINS, resource + plugin paths
set -u
# PX4's server.config minus GstCameraSystem (x264 video streaming of the first
# camera - not part of our system, would only add CPU load).
grep -v 'GstCameraSystem' "$PX4_GZ_SERVER_CONFIG" > "$OUT/server.config"
export GZ_SIM_SERVER_CONFIG_PATH="$OUT/server.config"

XVFB_PID="" GZ_PID="" PX4_PID="" MON_PID=""
# stop_child PID SIGNAL TARGET: signal TARGET (a PID, or -PGID for a group),
# reap PID, SIGKILL TARGET if it is still there after 20 s. (wait, not
# kill -0: an exited child stays visible as a zombie until it is reaped.)
stop_child() {
    local pid=$1 sig=$2 target=$3 guard
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || return 0
    kill "-$sig" -- "$target" 2>/dev/null
    ( sleep 20; kill -KILL -- "$target" 2>/dev/null ) &
    guard=$!
    wait "$pid" 2>/dev/null
    kill "$guard" 2>/dev/null
    wait "$guard" 2>/dev/null
    return 0
}
stop_all() {
    set +e
    stop_child "$MON_PID" TERM "$MON_PID"
    stop_child "$PX4_PID" INT "$PX4_PID"           # PX4 shuts down cleanly on SIGINT
    stop_child "$GZ_PID" TERM "-$GZ_PID"           # gz runs in its own process group
    stop_child "$XVFB_PID" TERM "$XVFB_PID"
    MON_PID="" PX4_PID="" GZ_PID="" XVFB_PID=""
    # PX4 links its ROMFS (etc) and test data into its working directory; drop
    # the links (also on an aborted run) so the results hold only this run's files.
    rm -f "$OUT/px4_rootfs/etc" "$OUT/px4_rootfs/test_data"
    set -e
}
trap stop_all EXIT
trap 'exit 130' INT TERM

(
    set +e
    echo "== date";      date -u +%FT%TZ
    echo "== host";      uname -a; grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release
    echo "== cpu";       nproc; lscpu 2>/dev/null | grep -E '^(Architecture|Model name|CPU\(s\)|Thread|Core|Socket|CPU max MHz|Hypervisor)' || true
    echo "== memory";    free -m
    echo "== disk";      df -h "$OUT" | tail -n1
    echo "== ci";        env | grep -E '^(ImageOS|ImageVersion|RUNNER_(OS|ARCH|NAME|ENVIRONMENT)|GITHUB_(SHA|REF_NAME|RUN_ID|RUN_ATTEMPT))=' || echo "not CI"
    echo "== px4";       echo "$PX4_TAG $PX4_COMMIT ($(git -C "$PX4_DIR" describe --tags --always 2>/dev/null)), airframe $AIRFRAME, model $MODEL"
    echo "== px4 gz models"; git -C "$PX4_DIR/Tools/simulation/gz" rev-parse HEAD
    echo "== px4-opticalflow"; echo "$of_head"
    echo "== gz";        gz sim --versions | head -n1
    echo "== python";    "$PY" --version; "$PY" -c 'import importlib.metadata as m; print("pymavlink", m.version("pymavlink"))'
    echo "== packages";  dpkg-query -W -f '${Package} ${Version}\n' libgz-sim8 libgz-rendering8-ogre2 \
                             libogre-next-2.3.0 libgz-sensors8-camera libgl1-mesa-dri libegl-mesa0 xvfb \
                             2>/dev/null || true
    echo "== render";    echo "$RENDER, LIBGL_ALWAYS_SOFTWARE=$LIBGL_ALWAYS_SOFTWARE GALLIUM_DRIVER=$GALLIUM_DRIVER"
    echo "== gz env";    env | grep -E '^(GZ_|PX4_GZ)' | sort
) > "$OUT/system.txt" 2>&1
dpkg-query -W -f '${Package}\t${Version}\t${Architecture}\n' 2>/dev/null | sort > "$OUT/packages.tsv" || true
"$PY" -m pip freeze --all > "$OUT/pip-freeze.txt" 2>/dev/null || true
note "trial: model $MODEL (airframe $AIRFRAME), $FLIGHTS flights, RTF window ${RTF_SECONDS}s >= $MIN_RTF, render $RENDER, out $OUT"
mark start

# ------------------------------------------------------------------ rendering
if [ "$RENDER" = xvfb ]; then
    dfile="$OUT/.xvfb-display"
    : > "$dfile"
    note "Xvfb -displayfd 7 -screen 0 1280x1024x24 -nolisten tcp -noreset"
    Xvfb -displayfd 7 -screen 0 1280x1024x24 -nolisten tcp -noreset 7> "$dfile" > "$OUT/xvfb.log" 2>&1 &
    XVFB_PID=$!
    for _ in $(seq 100); do [ -s "$dfile" ] && break; sleep 0.1; done
    [ -s "$dfile" ] || die "Xvfb did not start (see xvfb.log)"
    disp="$(tr -dc '0-9' < "$dfile")"
    export DISPLAY=":$disp"
    rm -f "$dfile"
    glxinfo -B > "$OUT/renderer.txt" 2>&1 || true
    HEADLESS_FLAG=()
else
    unset DISPLAY
    eglinfo -B > "$OUT/renderer.txt" 2>&1 || true
    HEADLESS_FLAG=(--headless-rendering)
fi
grep -iE 'renderer|device|driver' "$OUT/renderer.txt" 2>/dev/null | sed -n '1,5s/^/  /p' || true
mark display_ready

# ------------------------------------------------------------------ Gazebo
note "gz sim --verbose=$GZ_VERBOSE -r -s ${HEADLESS_FLAG[*]:-} $PX4_GZ_WORLDS/$WORLD.sdf  (GZ_PARTITION=$GZ_PARTITION GZ_IP=$GZ_IP)"
setsid gz sim --verbose="$GZ_VERBOSE" -r -s ${HEADLESS_FLAG[@]+"${HEADLESS_FLAG[@]}"} \
    "$PX4_GZ_WORLDS/$WORLD.sdf" > "$OUT/gz.log" 2>&1 < /dev/null &
GZ_PID=$!
ok=""
for _ in $(seq 240); do
    kill -0 "$GZ_PID" 2>/dev/null || { tail -n 30 "$OUT/gz.log" >&2; die "gz sim exited"; }
    info="$(gz service -i --service "/world/$WORLD/scene/info" 2>&1 || true)"
    if [[ "$info" == *"Service providers"* ]]; then ok=1; break; fi
    sleep 0.5
done
[ -n "$ok" ] || { tail -n 30 "$OUT/gz.log" >&2; die "Gazebo world '$WORLD' not ready after 120 s"; }
mark gz_ready

# ------------------------------------------------------------------ PX4 SITL
mkdir -p "$OUT/px4_rootfs"
note "PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART=$AIRFRAME PX4_SIM_MODEL=gz_$MODEL PX4_GZ_WORLD=$WORLD HEADLESS=1 $BUILD/bin/px4 -d -i $INSTANCE -w $OUT/px4_rootfs $BUILD/etc"
PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART="$AIRFRAME" PX4_SIM_MODEL="gz_$MODEL" PX4_GZ_WORLD="$WORLD" HEADLESS=1 \
    setsid "$BUILD/bin/px4" -d -i "$INSTANCE" -w "$OUT/px4_rootfs" "$BUILD/etc" \
    > "$OUT/px4.log" 2>&1 < /dev/null &
PX4_PID=$!
ok=""
for _ in $(seq 360); do
    kill -0 "$PX4_PID" 2>/dev/null || { tail -n 40 "$OUT/px4.log" >&2; die "PX4 exited during startup"; }
    if grep -q "Startup script returned successfully" "$OUT/px4.log"; then ok=1; break; fi
    if grep -q "Startup script returned with return value" "$OUT/px4.log"; then break; fi
    sleep 0.5
done
[ -n "$ok" ] || { tail -n 40 "$OUT/px4.log" >&2; die "PX4 startup failed or took over 180 s (px4.log)"; }
mark px4_started

PROCS=(--proc "gz=$GZ_PID" --proc "px4=$PX4_PID")
[ -n "$XVFB_PID" ] && PROCS+=(--proc "xvfb=$XVFB_PID")

# ------------------------------------------------------------------ 1. RTF with cameras rendering
note "$PY measure_rtf.py --world $WORLD --duration $RTF_SECONDS --warmup 10 --require-camera --min-rtf $MIN_RTF ${PROCS[*]}"
set +e
"$PY" "$HERE/measure_rtf.py" --world "$WORLD" --duration "$RTF_SECONDS" --warmup 10 --wait 120 \
    --require-camera --min-rtf "$MIN_RTF" --label "rtf ($MODEL, vehicle on the ground)" "${PROCS[@]}" \
    --out "$OUT/rtf.json" --samples "$OUT/rtf_samples.jsonl" 2>&1 | tee "$OUT/rtf.log"
rtf_rc=${PIPESTATUS[0]}
set -e
note "measure_rtf exit $rtf_rc"
mark rtf_done
kill -0 "$PX4_PID" 2>/dev/null && kill -0 "$GZ_PID" 2>/dev/null || die "PX4 or Gazebo died during the RTF measurement"

# ------------------------------------------------------------------ 2. smoke flights (+ RTF meanwhile)
"$PY" "$HERE/measure_rtf.py" --world "$WORLD" --duration 0 --warmup 0 --wait 60 --require-camera \
    --label "rtf during flights ($MODEL)" "${PROCS[@]}" \
    --out "$OUT/rtf_flights.json" --samples "$OUT/rtf_flights_samples.jsonl" > "$OUT/rtf_flights.log" 2>&1 &
MON_PID=$!
note "$PY smoke_flights.py --url udpin:127.0.0.1:$MAV_PORT --flights $FLIGHTS --expect-commit $PX4_COMMIT"
set +e
"$PY" "$HERE/smoke_flights.py" --url "udpin:127.0.0.1:$MAV_PORT" --flights "$FLIGHTS" \
    --expect-commit "$PX4_COMMIT" --out "$OUT/flights.json" 2>&1 | tee "$OUT/flights.log"
flights_rc=${PIPESTATUS[0]}
set -e
note "smoke_flights exit $flights_rc"
mark flights_done
stop_child "$MON_PID" TERM "$MON_PID"            # writes rtf_flights.json on SIGTERM
MON_PID=""
cat "$OUT/rtf_flights.log"

# ------------------------------------------------------------------ stop + summary
stop_all
mark stopped
printf '{%s"rtf_exit": %s, "flights_exit": %s}\n' "$TIMES" "$rtf_rc" "$flights_rc" > "$OUT/timings.json"
note "logs: $(find "$OUT/px4_rootfs/log" -name '*.ulg' 2>/dev/null | wc -l) ulog files"
set +e
"$PY" "$HERE/summarize.py" --dir "$OUT" --model "$MODEL" --render "$RENDER" --flights "$FLIGHTS" \
    --min-rtf "$MIN_RTF" ${BUILD_REPORT:+--build-report "$BUILD_REPORT"}
rc=$?
set -e
exit "$rc"
