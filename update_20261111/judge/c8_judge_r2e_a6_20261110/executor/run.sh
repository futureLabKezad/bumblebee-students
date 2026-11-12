#!/usr/bin/env bash
set -euo pipefail
test "$PWD" = /work
TAG=${TAG:?}; SCENARIO=${SCENARIO:-land}
[[ "$TAG" =~ ^INT_flight_[a-zA-Z0-9_]+$ ]]
case "$SCENARIO" in preflight|land|kill|freeze|mavros_restart|pilot|cancel_before|cancel|ack_cancel|heartbeat|guard_hold|cleanup_hold) ;; *) exit 2;; esac
OWN=/work/c8_judge_r2e_a6_20261110/executor  # A6: this copy (revision b + apply order, ../DIFF_a6.md)
export BB_COMBINED_ROOT=${BB_COMBINED_ROOT:?reviewed combined candidate required}
# c8: target set as parameters; no default in run.sh (launcher/host_run_wsl_c8_r2e.sh passes them; defaults are there)
export C8_AIRFRAME=${C8_AIRFRAME:?} C8_PX4_ETC=${C8_PX4_ETC:?} C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:?} C8_PRODUCT_SRC=${C8_PRODUCT_SRC:?}
export C8_MAVROS_INSTALL=${C8_MAVROS_INSTALL:?} C8_MODEL=${C8_MODEL:?} C8_FLOW_PLUGIN=${C8_FLOW_PLUGIN:?} C8_START_ORDER=${C8_START_ORDER:?}
[[ "$C8_AIRFRAME" =~ ^[0-9]{4,5}$ ]]; case "$C8_START_ORDER" in gz_first|px4_first) ;; *) exit 2;; esac
[ "$(basename "$C8_MODEL")" = bumblebee ]; [ -f "$C8_MODEL/model.sdf" ]; [ -f "$C8_FLOW_PLUGIN" ]
[ "$(ls -d "$C8_PX4_ETC"/init.d-posix/airframes/"$C8_AIRFRAME"_* | wc -l)" = 1 ]
# c8: SIM_LOCK (as goal_step5b run_scenario5.sh) and disk guard (< 8 GB free on C: = refuse), before anything is created
grep -q "local_bc6f158c" /work/SIM_LOCK.txt || { echo 'Refusing: /work/SIM_LOCK.txt not held by Симулятор (local_bc6f158c)' >&2; exit 2; }
FREE_G=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d ' '); [ "${FREE_G:-0}" -ge 8 ] || { echo "Refusing: disk C: free ${FREE_G}G < 8G" >&2; exit 2; }
CAND=$BB_COMBINED_ROOT/parameters
OUT=/work/sim/runs/$TAG
GUARD=/tmp/bb_${TAG}
test ! -e "$OUT"; test ! -e "$GUARD"
if pgrep -x px4 >/dev/null || pgrep -x mavros_node >/dev/null; then
    echo 'Refusing concurrent PX4 or MAVROS' >&2; exit 2
fi
# flight_trial_12: only the reviewed MAVROS 2.14.0 + backport-02 (#2138, #2149, #2093, 97a14ae1, 9a831aec) build; refuse before creating anything
(cd "$C8_MAVROS_INSTALL" && sha256sum -c --quiet "$OWN/MAVROS_BP02_SHA256SUMS.txt") || { echo 'Refusing: C8_MAVROS_INSTALL differs from MAVROS_BP02_SHA256SUMS.txt' >&2; exit 2; }  # c8: path is a parameter, the unchanged sums pin it
# flight_trial_13 / c8: only the pinned product install (c8: fixed image r2e, /work/fixed_image_r2e_20261109/install, MANIFEST_SHA256.txt d3e043c2)
echo "544f3179194b2fa14e16ff6add053e607ff14b0045d70b469ea61502642fd6ad  $OWN/PRODUCT_SHA256SUMS.txt" | sha256sum -c --quiet - || { echo 'Refusing: PRODUCT_SHA256SUMS.txt differs from the sha in run.sh' >&2; exit 2; }
(cd "$C8_PRODUCT_INSTALL" && sha256sum -c --quiet "$OWN/PRODUCT_SHA256SUMS.txt") || { echo 'Refusing: C8_PRODUCT_INSTALL differs from PRODUCT_SHA256SUMS.txt' >&2; exit 2; }
mkdir -p "$OUT" "$GUARD"; touch "$OUT/.start"
# Gazebo GUI (noVNC viewer) costs ~0.2 RTF; acceptance runs pause it (VIEW=paused, default) and
# say so in view_mode.txt. VIEW=on keeps the GUI for a watchable run under the same speed gate.
VIEW=${VIEW:-paused}; case "$VIEW" in paused|on) ;; *) exit 2;; esac
echo "$VIEW" > "$OUT/view_mode.txt"
MEASURING_CREATED=0
if [ "$VIEW" = paused ] && [ ! -e /work/sim/run/MEASURING ]; then touch /work/sim/run/MEASURING; MEASURING_CREATED=1; fi
printf '%s\n' '{"mode":"inhibit","token":"flight_initial"}' > "$GUARD/control.json"
export GZ_IP=127.0.0.1 GZ_PARTITION=bbtrial GEOGRAPHICLIB_GEOID_PATH=/work/sim/ros_stack/geoids
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4
export MAVLINK20=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 OPENCV_FOR_THREADS_NUM=2
export SITL_MAVROS_PARAMS="$OUT/mavros.yaml" SITL_MAVROS_RESPAWN=0
set +u
source /opt/ros/jazzy/setup.bash
source /work/ws_sitl/install/setup.bash
source "$C8_MAVROS_INSTALL/local_setup.bash"  # flight_trial_12: MAVROS 2.14.0 + backport-02 (c8: parameter, pinned above)
source "$C8_PRODUCT_INSTALL/local_setup.bash"  # c8: product parameter (r2e), pinned above
set -u
MPID=''; PROXY=''; CPID=''; FPID=''
cleanup() {
    for pid in "$FPID" "$CPID"; do
        if [ -n "$pid" ]; then kill -INT -- -"$pid" 2>/dev/null || true; fi
    done
    sleep 2
    for pid in "$FPID" "$CPID"; do
        if [ -n "$pid" ]; then kill -TERM -- -"$pid" 2>/dev/null || true; fi
    done
    if [ -n "$MPID" ]; then kill -INT -- -"$MPID" 2>/dev/null || true; fi
    touch "$OUT/proxy_stop"
    if [ -n "$PROXY" ]; then wait "$PROXY" 2>/dev/null || true; fi
    if [ -n "$MPID" ]; then sleep 2; kill -TERM -- -"$MPID" 2>/dev/null || true; fi
    cp -a "$GUARD" "$OUT/guard_final"
    bash /work/sim/stop_sim.sh
    if [ "$MEASURING_CREATED" = 1 ]; then rm -f /work/sim/run/MEASURING; fi
    python3 - "$OUT" <<'PY'
import json, shutil, sys
from pathlib import Path
out=Path(sys.argv[1]);folder=out/'rootfs/log'  # c8: run-owned PX4 rootfs (run_sim.snapshot.sh: px4 -w OUT/rootfs C8_PX4_ETC)
logs=sorted((p for p in folder.rglob('*.ulg') if p.stat().st_mtime >= (out/'.start').stat().st_mtime),key=lambda p:p.stat().st_mtime)
if logs: shutil.copy2(logs[-1],out/'flight.ulg')
(out/'ulog_copy_status.json').write_text(json.dumps({'fresh_log_count':len(logs),'copied':bool(logs),'source':str(logs[-1]) if logs else None})+'\n')
PY
}
trap cleanup EXIT
cp "$BB_COMBINED_ROOT/manifest.json" "$OUT/combined_manifest.json"
FIELD=/work/parallel_work/20261015/integration/field_measurements_01/generated
cmp "$FIELD/map.input.txt" /work/sim/worlds/aruco_map/map.input.txt   # detector map (vision.launch.py) must equal the field map
(cd "$FIELD" && find . -type f | sort | xargs sha256sum) > "$OUT/field_files.sha256"
cp "$FIELD/manifest.json" "$OUT/field_manifest.json"
cp "$OWN"/*.py "$OUT/"
cp "$OWN/run.sh" "$OWN/run_sim.snapshot.sh" "$OUT/"
# flight_trial_18 (mk_chain --sdk-from-product): drone.py from the product at its tag; its sha is checked here and in the frozen pins (repo_files, run_files, @run/drone.py)
# c8: product src is a parameter; the sha is r2e drone.py. c8-r2e-b (D3): flight_profile.py is the r2e copy (13 names), sha checked
echo "855f4cc4ad511a59b679092f3c587ce5689684edd53e3a0abbb72bd2226ac9ad  $C8_PRODUCT_SRC/examples/drone.py" | sha256sum -c --quiet - || { echo 'Refusing: product drone.py differs from the sha in run.sh' >&2; exit 2; }
echo "5b8e2a12a91445a1aba867fc22d84a8fd884a50ebd835da008a31c737633695b  $C8_PRODUCT_SRC/examples/flight_profile.py" | sha256sum -c --quiet - || { echo 'Refusing: product flight_profile.py differs from the sha in run.sh' >&2; exit 2; }
cp "$C8_PRODUCT_SRC/examples/drone.py" "$C8_PRODUCT_SRC/examples/flight_profile.py" "$OUT/"  # c8-r2e-b (D3)
sha256sum "$OWN"/*.py "$OWN/run.sh" "$CAND"/*.py "$CAND"/*.json "$BB_COMBINED_ROOT/vision/aruco_detect.py" "$C8_PRODUCT_INSTALL/bumblebee/lib/bumblebee/simple_offboard" "$C8_PRODUCT_SRC/src/python/setpoint_freshness.py" "$OUT/drone.py" > "$OUT/flight_source.sha256"  # c8: ledger names the product that really runs
# c8: honest record of this run's target set (parameters, PX4 build, model, flow plugin, the whole airframe chain)
AFDIR="$C8_PX4_ETC/init.d-posix/airframes"; mkdir "$OUT/airframe_chain"
{ env | grep '^C8_' | sort
  echo "px4_source_head $(git -C "$HOME/PX4-Autopilot" rev-parse HEAD)"
  sha256sum "$HOME/PX4-Autopilot/build/px4_sitl_default/bin/px4" "$C8_MODEL/model.sdf" "$C8_FLOW_PLUGIN" "$C8_PRODUCT_SRC/examples/drone.py"
  f=$(ls -d "$AFDIR/$C8_AIRFRAME"_*)
  for _ in $(seq 20); do [ -n "$f" ] || break; test -f "$f"; sha256sum "$f"; cp "$f" "$OUT/airframe_chain/"
    n=$(sed -n 's#^\. \${R}etc/init\.d-posix/airframes/\([^ ]*\).*#\1#p' "$f" | head -1); f=${n:+$AFDIR/$n}; done
} > "$OUT/c8_identity.txt"
python3 /work/sim/save_run_state.py "$TAG"
TAG=$TAG MODEL=bumblebee BB_AIRFRAME=$C8_AIRFRAME FLOOR=2 ARUCO=1 GST=0 SPAWN_POSE='-0.08 0 0.22 0 0 0' bash "$OUT/run_sim.snapshot.sh" > "$OUT/start.log" 2>&1
timeout 120 ~/px4-venv/bin/python "$OUT/sitl_setup.py" --out "$OUT" --expected-autostart "$C8_AIRFRAME" --obl 4 --guard "$GUARD" --rc-expected "$CAND/rc_expected09.json" --real-flight-params /work/sim/ros_stack/flight_real_params.json > "$OUT/setup.log" 2>&1
test -f "$OUT/rc_ready.json"
cp /work/sim/run/world.sdf "$OUT/world.sdf"
cp "$C8_MODEL/model.sdf" "$OUT/model.sdf"  # c8: model parameter; the airframe chain was copied into OUT/airframe_chain above
DELAY=0; [ "$SCENARIO" != ack_cancel ] || DELAY=4
~/px4-venv/bin/python "$CAND/mavlink_fault_proxy_profile.py" --out "$OUT" --profile-guard "$GUARD" --ack-delay "$DELAY" > "$OUT/proxy.log" 2>&1 &
PROXY=$!
for attempt in $(seq 30); do [ -f "$OUT/proxy_ready" ] && break; kill -0 "$PROXY"; sleep 1; done
test -f "$OUT/proxy_ready"
sed 's#udp://127.0.0.1:14540@127.0.0.1:14580#udp://127.0.0.1:14640@127.0.0.1:14680#' /work/sim/ros_stack/mavros214.yaml > "$OUT/mavros_legacy.yaml"
setsid /usr/bin/python3 "$OWN/start_mavros_bp02.py" "$OUT/mavros_legacy.yaml" "$OUT/mavros.yaml" > "$OUT/mavros.log" 2>&1 < /dev/null &
MPID=$!; printf '%s\n' "$MPID" > "$OUT/mavros.pid"
# flight_trial_12: evidence of the MAVROS libraries the running mavros_node really mapped (read-only, after 8 s)
( sleep 8; for f in $(grep -oE '/[^ ]*(mavros|mavconn)[^ ]*\.so[^ ]*' "/proc/$MPID/maps" 2>/dev/null | sort -u); do sha256sum "$f"; done > "$OUT/mavros_loaded_libs.txt" 2>&1 || true ) &
setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch /work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py > "$OUT/camera_stack.log" 2>&1 < /dev/null &
CPID=$!; printf '%s\n' "$CPID" > "$OUT/camera_stack.pid"
setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch "$OUT/flight.launch.py" > "$OUT/ros.log" 2>&1 < /dev/null &
FPID=$!; printf '%s\n' "$FPID" > "$OUT/ros.pid"
# flight_trial_13: evidence of the simple_offboard binary that really runs (read-only, after 15 s)
( sleep 15; for p in $(pgrep -x simple_offboard); do f=$(readlink -f /proc/$p/exe); sha256sum "$f"; done > "$OUT/product_loaded_bins.txt" 2>&1 || true ) &
timeout --signal=INT --kill-after=30 840 ~/px4-venv/bin/python "$OUT/supervisor.py" --out "$OUT" --candidate "$CAND" --guard "$GUARD" --scenario "$SCENARIO" > "$OUT/supervisor.log" 2>&1
