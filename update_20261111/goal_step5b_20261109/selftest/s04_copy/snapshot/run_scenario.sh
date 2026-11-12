#!/bin/bash
# ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY). К дрону не подключается. Goal step 5 scenario launcher, Claude, 06.11.2026.
# One run: PX4 SITL v1.16.1 (airframe 4032 = 20EC as is, or a height-estimate candidate 4034/4035) + Gazebo with the
# marker field of the scripts' map (/work/sim/worlds/aruco_map, map sha 528b5adb = the image's map.txt) + the drone's
# own ROS 2 nodes (port-rc3, MAVROS bp02; scenario_stack.launch.py) + an UNMODIFIED example script of the image.
# The transmitter and a ground station are emulated (tools/rc_hold.py). Then: C2 parity, C1 pins, goal evaluation.
# Usage: bash run_scenario.sh TAG AIRFRAME SCRIPT [--gui] [--timeout S]
#   SCRIPT: flight.py (others need the pkill guard and map handling, not built yet).
# Refuses to start while any px4 / gz / ruby / mavros_node process is alive; never overwrites a run folder.
# Stops only its own process groups (and GZ_PARTITION=bbtrial leftovers). Gazebo keeps its usual cache in ~/.gz.
set -uo pipefail
STEP5=/work/goal_step5_20261106
STEP4=/work/goal_step4_20261106
PX4=$HOME/PX4-Autopilot
B=$PX4/build/px4_sitl_default
DRONE=/work/pc_inventory_20261019/incident_motors_20261104/params_20261104_1145.params
PY=$HOME/px4-venv/bin/python3
PRODUCT=/work/ws_package1b_port_03
EXAMPLES=$PRODUCT/src/bumblebee/examples
ARUCO_DIR=/work/sim/worlds/aruco_map
TAG=${1:?TAG}; AF=${2:?AIRFRAME}; SCRIPT=${3:?SCRIPT}; shift 3
GUI=0; TIMEOUT=300; ARUCO_ALWAYS=0
while [ $# -gt 0 ]; do
  case $1 in
    --gui) GUI=1 ;;
    --timeout) TIMEOUT=$2; shift ;;
    --trial-aruco-always) ARUCO_ALWAYS=1 ;;   # finding F1 work-around (detector never sleeps); labelled in the report
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done
case $AF in 4032|4034|4035) ;; *) echo "AIRFRAME must be 4032, 4034 or 4035"; exit 2 ;; esac
case $SCRIPT in
  flight.py) SCRIPT_REL=examples/flight/flight.py; SCRIPT_H=1.5 ;;   # takeoff(height=1.5) in the image's code
  *) echo "SCRIPT not supported yet: $SCRIPT"; exit 2 ;;
esac
RUN=$STEP5/runs/$TAG
[ -e "$RUN" ] && { echo "REFUSE: $RUN exists (never overwrite)"; exit 2; }
busy=$( { pgrep -x px4; pgrep -x gz; pgrep -x ruby; pgrep -x mavros_node; } | tr '\n' ' ')
if [ -n "${busy// /}" ]; then
  echo "REFUSE: simulator/ROS processes alive: $busy(one simulator at a time; not touching them)"
  ps -o pid,etime,args -p "$(echo $busy | tr ' ' ',')"
  exit 2
fi
mkdir -p "$RUN/rootfs" "$RUN/models" "$RUN/snapshot/tools"
exec > >(tee -a "$RUN/launcher.log") 2>&1
echo "ТОЛЬКО СИМУЛЯТОР: scenario $TAG airframe $AF script $SCRIPT gui=$GUI timeout=${TIMEOUT}s trial_aruco_always=$ARUCO_ALWAYS $(date -Is)"

# --- snapshot + versions
cp $STEP5/run_scenario.sh $STEP5/scenario_stack.launch.py "$RUN/snapshot/"
cp $STEP5/tools/rc_hold.py $STEP5/tools/goal_eval.py $STEP5/tools/pins_check.py "$RUN/snapshot/tools/"
cp $STEP4/sim_only.json "$RUN/snapshot/"
cp $STEP4/tools/param_parity.py $STEP4/tools/sitl_param_names.txt "$RUN/snapshot/tools/"
SNAP=$RUN/snapshot
{
  echo "date $(date -Is)"
  echo "px4_source_head $(cd $PX4 && git rev-parse HEAD)"
  echo "px4_binary_sha256 $(sha256sum < $B/bin/px4 | cut -c1-64)"
  echo "gz $(gz sim --versions 2>/dev/null | head -1)"
  echo "airframe $AF $(sha256sum $STEP4/px4_etc/init.d-posix/airframes/${AF}_* | cut -c1-64)"
  echo "airframe 4032 $(sha256sum $STEP4/px4_etc/init.d-posix/airframes/4032_* | cut -c1-64)"
  echo "model_sdf $(sha256sum < $STEP4/model/bumblebee/model.sdf | cut -c1-64)"
  echo "aruco_world $(sha256sum < $ARUCO_DIR/default.sdf | cut -c1-64) map $(sha256sum < $ARUCO_DIR/map.input.txt | cut -c1-64)"
  echo "product $(tail -1 $PRODUCT/RC3_PROVENANCE.txt | cut -c1-80)"
  echo "script $SCRIPT_REL $(sha256sum < $PRODUCT/src/bumblebee/$SCRIPT_REL | cut -c1-64)"
  (cd "$SNAP" && sha256sum run_scenario.sh scenario_stack.launch.py sim_only.json tools/*)
} > "$RUN/versions.txt"
cat "$RUN/versions.txt"
$PY -I $SNAP/tools/pins_check.py "$RUN" "$SCRIPT_REL"

# --- clock check (PC rule, /work/CLAUDE.md)
python3 -B $HOME/bb_pc_setup_patched_20261019/pc_handover_20261017/setup/wsl_clock_check.py 40 > "$RUN/clock_check.txt" 2>&1
CLOCK=$?
echo "clock check exit $CLOCK: $(tail -1 "$RUN/clock_check.txt")"
[ $CLOCK -eq 10 ] && { echo "STOP: clock fight (see clock_check.txt)"; exit 10; }

# --- Gazebo environment: own partition, GPU renderer, marker field over the noise mat (as old ARUCO=1 FLOOR=2)
export GZ_IP=127.0.0.1 GZ_PARTITION=bbtrial
export GZ_SIM_RESOURCE_PATH=${GZ_SIM_RESOURCE_PATH:-} GZ_SIM_SYSTEM_PLUGIN_PATH=${GZ_SIM_SYSTEM_PLUGIN_PATH:-}
. $B/rootfs/gz_env.sh
. /work/pc_inventory_20261019/gpu_env.sh
cp -r $STEP4/model/bumblebee /work/sim/models/bb_floor_noise "$RUN/models/"
export GZ_SIM_RESOURCE_PATH=$RUN/models:$ARUCO_DIR/models:$GZ_SIM_RESOURCE_PATH
cp $PX4_GZ_SERVER_CONFIG "$RUN/server.config"
export GZ_SIM_SERVER_CONFIG_PATH=$RUN/server.config
python3 - "$PX4_GZ_WORLDS/default.sdf" "$RUN/world.sdf" "$ARUCO_DIR/default.sdf" <<'PY'
import re, sys
src, dst, aruco_world = sys.argv[1:]
s = open(src, encoding='utf-8-sig').read()
s = re.sub(r'<max_step_size>[^<]*</max_step_size>', '<max_step_size>0.004</max_step_size>', s)
s = re.sub(r'<real_time_update_rate>[^<]*</real_time_update_rate>', '<real_time_update_rate>250</real_time_update_rate>', s)
inc = '<include><uri>model://bb_floor_noise</uri><name>bb_floor_noise</name><pose>0 0 0.002 0 0 0</pose></include>\n'
n = 0
for uri, x, y, z, r, p, yaw in re.findall(r'<include>\s*<uri>(model://aruco_\d+)</uri>\s*<pose>(\S+) (\S+) (\S+) (\S+) (\S+) (\S+)</pose>\s*</include>',
                                          open(aruco_world).read()):
    inc += f'<include><uri>{uri}</uri><pose>{x} {y} {float(z) + 0.004:.6g} {r} {p} {yaw}</pose></include>\n'   # 4 mm over the mat
    n += 1
# spawn as the old harness: 8 cm behind marker 0 so the camera sees it whole
inc += '<include><uri>model://bumblebee</uri><name>bumblebee_0</name><pose>-0.08 0 0.22 0 0 0</pose></include>\n'
open(dst, 'w').write(s.replace('</world>', inc + '  </world>'))
print(f'world: {n} markers')
PY

PIDS_STARTED=""
cleanup() {
  touch "$RUN/stop_rc"
  [ -f "$RUN/ros.pid" ] && kill -INT -- -"$(cat "$RUN/ros.pid")" 2>/dev/null
  for _ in $(seq 20); do [ -f "$RUN/ros.pid" ] && kill -0 "$(cat "$RUN/ros.pid")" 2>/dev/null || break; sleep 0.5; done
  for f in rc px4 gui gz; do
    [ -f "$RUN/$f.pid" ] && kill -INT -- -"$(cat "$RUN/$f.pid")" 2>/dev/null
    [ $f = px4 ] && for _ in $(seq 20); do kill -0 "$(cat "$RUN/px4.pid" 2>/dev/null)" 2>/dev/null || break; sleep 0.5; done
  done
  for _ in $(seq 20); do
    alive=0
    for f in gui gz; do [ -f "$RUN/$f.pid" ] && kill -0 "$(cat "$RUN/$f.pid")" 2>/dev/null && alive=1; done
    [ $alive = 0 ] && break
    sleep 0.5
  done
  for f in ros rc px4 gui gz stats; do
    [ -f "$RUN/$f.pid" ] && kill -KILL -- -"$(cat "$RUN/$f.pid")" 2>/dev/null
    rm -f "$RUN/$f.pid"
  done
  for p in $(pgrep -x px4) $(pgrep -x gz) $(pgrep -x ruby); do
    tr '\0' '\n' < /proc/$p/environ 2>/dev/null | grep -qx 'GZ_PARTITION=bbtrial' && kill -KILL "$p" 2>/dev/null
  done
  sleep 1
}
trap cleanup EXIT

# --- PX4 first, then Gazebo (step 4 finding: Gazebo-first makes the EKF reject the rangefinder)
cd "$RUN/rootfs"
PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART=$AF PX4_GZ_MODEL_NAME=bumblebee_0 PX4_GZ_WORLD=default \
  setsid $B/bin/px4 -d -w "$RUN/rootfs" "$STEP4/px4_etc" > "$RUN/px4.log" 2>&1 < /dev/null &
echo $! > "$RUN/px4.pid"
for i in $(seq 40); do grep -q "Waiting for Gazebo world\|Standalone PX4 launch" "$RUN/px4.log" 2>/dev/null && break; sleep 0.5; done
cd "$RUN"
setsid gz sim --verbose=2 -r -s --headless-rendering "$RUN/world.sdf" > "$RUN/gz.log" 2>&1 < /dev/null &
echo $! > "$RUN/gz.pid"
for i in $(seq 60); do
  gz service -i --service /world/default/scene/info 2>/dev/null | grep -q "Service providers" && break
  sleep 1
done
echo "gz server up after ${i}s"
if [ $GUI = 1 ]; then
  setsid gz sim -g > "$RUN/gui.log" 2>&1 < /dev/null &
  echo $! > "$RUN/gui.pid"
  ( for _ in $(seq 90); do gz service -l 2>/dev/null | grep -qx /gui/follow && break; sleep 1; done
    sleep 3
    gz service -s /gui/follow --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean --timeout 5000 --req 'data: "bumblebee_0"'
    gz service -s /gui/follow/offset --reqtype gz.msgs.Vector3d --reptype gz.msgs.Boolean --timeout 5000 --req 'x: -2.2, y: -2.2, z: 1.8'
  ) > "$RUN/gui_follow.log" 2>&1 &
fi
( setsid bash -c "while true; do echo \"\$(date +%T) \$(gz topic -e -t /world/default/stats -n 1 2>/dev/null | grep -m1 real_time_factor)\"; sleep 10; done" > "$RUN/rtf.txt" 2>&1 < /dev/null & echo $! > "$RUN/stats.pid" )
for i in $(seq 120); do
  grep -q "Startup script returned successfully" "$RUN/px4.log" 2>/dev/null && break
  grep -qE "ERROR \[init\]|Startup script returned with return value" "$RUN/px4.log" 2>/dev/null && break
  sleep 1
done
echo "px4 startup: $(grep -E 'Startup script|ERROR \[init\]' "$RUN/px4.log" | head -3 | tr '\n' ' ') after ${i}s"
for _ in $(seq 30); do $B/bin/px4-listener estimator_status_flags -n 1 2>/dev/null | grep -q cs_tilt_align && break; sleep 1; done
$B/bin/px4-logger stop; sleep 1
[ "$($B/bin/px4-param show -q SDLOG_MODE)" = 0 ] && $B/bin/px4-logger start -b 1000 -t
echo "logger restarted"

# --- transmitter + ground station emulation, parameter read for C2
setsid $PY -I $SNAP/tools/rc_hold.py "$RUN" "$DRONE" --max-s $((TIMEOUT + 300)) > "$RUN/rc_hold.log" 2>&1 < /dev/null &
echo $! > "$RUN/rc.pid"
for _ in $(seq 60); do [ -e "$RUN/rc_ready" ] && break; sleep 1; done
echo "rc_hold ready: $([ -e "$RUN/rc_ready" ] && echo yes || echo NO)"

# --- the drone's ROS 2 nodes
set +u
source /opt/ros/jazzy/setup.bash
source /work/ws_sitl/install/setup.bash                       # aruco_pose messages (drone.py imports them)
for p in libmavconn mavros_msgs mavros_extras; do source /work/ws_mavros214/install/$p/share/$p/package.bash; done
source /work/ws_mavros214_bp02_rel/install/local_setup.bash
source $PRODUCT/install/local_setup.bash
set -u
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 MAVLINK20=1
export GEOGRAPHICLIB_GEOID_PATH=/work/sim/ros_stack/geoids
export BB_FCU_URL=udp://127.0.0.1:14540@127.0.0.1:14580 BB_TRIAL_ARUCO_ALWAYS=$ARUCO_ALWAYS
cp /work/sim/ros_stack/mavros214.yaml "$RUN/mavros_source.yaml"
export BB_MAVROS_SOURCE_YAML=$RUN/mavros_source.yaml BB_MAVROS_SCOPED_YAML=$RUN/mavros_scoped.yaml
echo "ros: mavros $(ros2 pkg prefix mavros) bumblebee $(ros2 pkg prefix bumblebee)"
setsid ros2 launch "$SNAP/scenario_stack.launch.py" > "$RUN/ros.log" 2>&1 < /dev/null &
echo $! > "$RUN/ros.pid"
for i in $(seq 90); do grep -q "Got HEARTBEAT, connected" "$RUN/ros.log" 2>/dev/null && break; sleep 1; done
echo "mavros: $(grep -m1 -o 'Got HEARTBEAT, connected.*' "$RUN/ros.log" || echo 'NOT connected') after ${i}s"
for i in $(seq 90); do grep -q "parameters list received" "$RUN/ros.log" 2>/dev/null && break; sleep 1; done
echo "mavros params: $(grep -m1 -o 'parameters list received.*' "$RUN/ros.log" || echo 'NOT complete') after ${i}s"
sleep 10    # let the camera, detector and vpe_fix start; on the drone a script starts long after boot

# --- the unmodified example script of the image
cd "$RUN"
echo "script start $(date -Is)"
PYTHONPATH=$EXAMPLES:${PYTHONPATH:-} timeout --signal=INT --kill-after=20 $TIMEOUT /usr/bin/python3 -u "$PRODUCT/src/bumblebee/$SCRIPT_REL" > "$RUN/script.log" 2>&1
echo "script exit $? $(date -Is)"
sleep 5
cleanup
trap - EXIT
echo "stopped $(date -Is); alive px4/gz/ruby/mavros_node: $( { pgrep -x px4; pgrep -x gz; pgrep -x ruby; pgrep -x mavros_node; } | tr '\n' ' ')"

$PY -I $SNAP/tools/param_parity.py "$RUN" "$DRONE" $SNAP/sim_only.json "$AF"
echo "parity exit $?"
ULG=$(ls -t "$RUN"/rootfs/log/*/*.ulg 2>/dev/null | head -1)
if [ -n "$ULG" ]; then
  $PY -I $SNAP/tools/goal_eval.py "$RUN" "$ULG" --script-height $SCRIPT_H
else
  echo "no ULog (never armed)"
fi
tail -15 "$RUN/script.log"
(cd "$RUN" && find . -type f ! -name SHA256SUMS.txt ! -name launcher.log -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt)
echo "done $TAG $(date -Is)"
