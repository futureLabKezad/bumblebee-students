#!/usr/bin/env bash
# SIMULATOR ONLY. Measure Gazebo real-time factor with the trial world, model and camera/vision chain
# (no MAVROS, no proxy, no parameter writes, no commands): 60 s with the noVNC GUI, 60 s with it paused.
set -euo pipefail
test "$PWD" = /work
TAG=${TAG:?}; [[ "$TAG" =~ ^RTF_probe_[a-zA-Z0-9_]+$ ]]
OUT=/work/sim/runs/$TAG; test ! -e "$OUT"
if pgrep -x px4 >/dev/null || pgrep -x mavros_node >/dev/null; then echo 'Refusing: PX4 or MAVROS running' >&2; exit 2; fi
mkdir -p "$OUT"; touch "$OUT/.start"
OWN=/work/parallel_work/20261015/integration/flight_trial_01
export GZ_IP=127.0.0.1 GZ_PARTITION=bbtrial GEOGRAPHICLIB_GEOID_PATH=/work/sim/ros_stack/geoids
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 OPENCV_FOR_THREADS_NUM=2
export BB_COMBINED_ROOT=/work/parallel_work/20261015/integration/combined_03
CPID=''
cleanup() {
  if [ -n "$CPID" ]; then kill -INT -- -"$CPID" 2>/dev/null || true; sleep 3; kill -TERM -- -"$CPID" 2>/dev/null || true; fi
  bash /work/sim/stop_sim.sh
  rm -f /work/sim/run/MEASURING
}
trap cleanup EXIT
rm -f /work/sim/run/MEASURING
{ uname -a; nproc; uptime; } > "$OUT/host.txt"
python3 /work/sim/save_run_state.py "$TAG"   # moves the previous sim state into $OUT/pre_run_backup
TAG=$TAG MODEL=bumblebee BB_AIRFRAME=4030 FLOOR=2 ARUCO=1 GST=0 SPAWN_POSE='-0.08 0 0.22 0 0 0' bash "$OWN/run_sim.snapshot.sh" > "$OUT/start.log" 2>&1
set +u; source /opt/ros/jazzy/setup.bash; source /work/ws_package1b/install/local_setup.bash; set -u
setsid /usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch /work/parallel_work/20261015/integration/combined_trial_tools/vision.launch.py > "$OUT/camera_stack.log" 2>&1 < /dev/null &
CPID=$!
sleep 25   # GUI attach + vision start (wall)
ps -eo pid,pcpu,etime,args --sort=-pcpu | head -15 > "$OUT/ps_gui_on.txt"
/usr/bin/python3 "$(dirname "$0")/stats_probe.py" --out "$OUT/stats.jsonl" --seconds 60 --label gui_on | tee "$OUT/summary_gui_on.json"
touch /work/sim/run/MEASURING; sleep 8
ps -eo pid,pcpu,etime,args --sort=-pcpu | head -15 > "$OUT/ps_gui_paused.txt"
/usr/bin/python3 "$(dirname "$0")/stats_probe.py" --out "$OUT/stats.jsonl" --seconds 60 --label gui_paused | tee "$OUT/summary_gui_paused.json"
uptime >> "$OUT/host.txt"
echo "=== RTF PROBE DONE $TAG"
