#!/usr/bin/env bash
set -euo pipefail
test "$PWD" = /work
TAG=${TAG:?}; SCENARIO=${SCENARIO:-land}
[[ "$TAG" =~ ^INT_flight_[a-zA-Z0-9_]+$ ]]
case "$SCENARIO" in preflight|land|kill|freeze|mavros_restart|pilot|cancel_before|cancel|ack_cancel|heartbeat) ;; *) exit 2;; esac
OWN=/work/parallel_work/20261015/integration/flight_trial_01
export BB_COMBINED_ROOT=${BB_COMBINED_ROOT:?reviewed combined candidate required}
CAND=$BB_COMBINED_ROOT/parameters
OUT=/work/sim/runs/$TAG
GUARD=/tmp/bb_${TAG}
test ! -e "$OUT"; test ! -e "$GUARD"
if pgrep -x px4 >/dev/null || pgrep -x mavros_node >/dev/null; then
    echo 'Refusing concurrent PX4 or MAVROS' >&2; exit 2
fi
mkdir -p "$OUT" "$GUARD"; touch "$OUT/.start"
printf '%s\n' '{"mode":"inhibit","token":"flight_initial"}' > "$GUARD/control.json"
export GZ_IP=127.0.0.1 GZ_PARTITION=bbtrial GEOGRAPHICLIB_GEOID_PATH=/work/sim/ros_stack/geoids
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4
export MAVLINK20=1 PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 OPENCV_FOR_THREADS_NUM=2
export SITL_MAVROS_PARAMS="$OUT/mavros.yaml" SITL_MAVROS_RESPAWN=0
set +u
source /opt/ros/jazzy/setup.bash
source /work/ws_sitl/install/setup.bash
source /work/ws_mavros214/install/local_setup.bash
source /work/ws_package1b/install/local_setup.bash
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
    python3 - "$OUT" <<'PY'
import json, shutil, sys
from pathlib import Path
out=Path(sys.argv[1]);folder=Path.home()/'PX4-Autopilot/build/px4_sitl_default/rootfs/log'
logs=sorted((p for p in folder.rglob('*.ulg') if p.stat().st_mtime >= (out/'.start').stat().st_mtime),key=lambda p:p.stat().st_mtime)
if logs: shutil.copy2(logs[-1],out/'flight.ulg')
(out/'ulog_copy_status.json').write_text(json.dumps({'fresh_log_count':len(logs),'copied':bool(logs),'source':str(logs[-1]) if logs else None})+'\n')
PY
}
trap cleanup EXIT
cp "$BB_COMBINED_ROOT/manifest.json" "$OUT/combined_manifest.json"
cp "$OWN"/*.py "$OUT/"
cp "$OWN/run.sh" "$OWN/run_sim.snapshot.sh" "$OUT/"
cp /work/ws_package1b/src/bumblebee/examples/drone.py /work/ws_package1b/src/bumblebee/examples/flight_profile.py "$OUT/"
sha256sum "$OWN"/*.py "$OWN/run.sh" "$CAND"/*.py "$CAND"/*.json "$BB_COMBINED_ROOT/vision/aruco_detect.py" /work/ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard /work/ws_package1b/src/bumblebee/src/python/setpoint_freshness.py "$OUT/drone.py" > "$OUT/flight_source.sha256"
python3 /work/sim/save_run_state.py "$TAG"
TAG=$TAG MODEL=bumblebee BB_AIRFRAME=4030 FLOOR=2 ARUCO=1 GST=0 SPAWN_POSE='-0.08 0 0.22 0 0 0' bash "$OUT/run_sim.snapshot.sh" > "$OUT/start.log" 2>&1
timeout 120 ~/px4-venv/bin/python "$OUT/sitl_setup.py" --out "$OUT" --obl 4 --guard "$GUARD" --rc-expected "$CAND/rc_expected09.json" --real-flight-params /work/sim/ros_stack/flight_real_params.json > "$OUT/setup.log" 2>&1
test -f "$OUT/rc_ready.json"
cp /work/sim/run/world.sdf "$OUT/world.sdf"
cp /work/sim/bumblebee_model/models/bumblebee/model.sdf "$OUT/model.sdf"
cp /work/sim/bumblebee_model/airframes/4030_gz_bumblebee "$OUT/4030_gz_bumblebee"
DELAY=0; [ "$SCENARIO" != ack_cancel ] || DELAY=4
~/px4-venv/bin/python "$CAND/mavlink_fault_proxy_profile.py" --out "$OUT" --profile-guard "$GUARD" --ack-delay "$DELAY" > "$OUT/proxy.log" 2>&1 &
PROXY=$!
for attempt in $(seq 30); do [ -f "$OUT/proxy_ready" ] && break; kill -0 "$PROXY"; sleep 1; done
test -f "$OUT/proxy_ready"
sed 's#udp://127.0.0.1:14540@127.0.0.1:14580#udp://127.0.0.1:14640@127.0.0.1:14680#' /work/sim/ros_stack/mavros214.yaml > "$OUT/mavros_legacy.yaml"
setsid /usr/bin/python3 /work/parallel_work/20261015/integration/combined_trial_tools/start_mavros.py "$OUT/mavros_legacy.yaml" "$OUT/mavros.yaml" > "$OUT/mavros.log" 2>&1 < /dev/null &
MPID=$!; printf '%s\n' "$MPID" > "$OUT/mavros.pid"
setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch /work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py > "$OUT/camera_stack.log" 2>&1 < /dev/null &
CPID=$!; printf '%s\n' "$CPID" > "$OUT/camera_stack.pid"
setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch "$OUT/flight.launch.py" > "$OUT/ros.log" 2>&1 < /dev/null &
FPID=$!; printf '%s\n' "$FPID" > "$OUT/ros.pid"
timeout --signal=INT --kill-after=30 840 ~/px4-venv/bin/python "$OUT/supervisor.py" --out "$OUT" --candidate "$CAND" --guard "$GUARD" --scenario "$SCENARIO" > "$OUT/supervisor.log" 2>&1
