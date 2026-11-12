#!/bin/bash
# ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY). К дрону не подключается. Goal step 5b scenario launcher, Claude, 09.11.2026.
# Copy of /work/goal_step5_20261106/run_scenario.sh (06.11); every addition is marked "5b:".
# One run: PX4 SITL v1.16.1 (airframe 4032 = 20EC as is, or a height-estimate candidate 4034/4035) + Gazebo with the
# marker field of the scripts' map (/work/sim/worlds/aruco_map, map sha 528b5adb = the image's map.txt) + the drone's
# own ROS 2 nodes (port-rc3, MAVROS bp02; step-5 scenario_stack.launch.py, unchanged) + an UNMODIFIED example script.
# The transmitter and a ground station are emulated (step-5 tools/rc_hold.py). Then: C2 parity, C1 pins, evaluation.
# Usage: bash run_scenario6.sh TAG AIRFRAME SCRIPT [--gui] [--timeout S] [--trial-aruco-always] [--trial-map-file]
# Edition 6 (09.11, Claude, C8 new checks): ed.5 + rc_hold3 (RUN/rc_lost stops RC override) + --inject-on PATTERN NTH ACTION
#   (fixed-string PATTERN on NTH script.log lines -> /work/c8_new_checks_20261109/c8_inject.py ACTION once:
#   markers_off | floor_off | rc_off) + --after-inject-s N (default 30). Maker: /work/c8_new_checks_20261109/make_run_scenario6.py
#   ed.6b (09.11, Claude, hand edits; the maker no longer reproduces this file): + floor_near_off; + sensor_block_on |
#   sensor_block_far_on (check (b) «пропал дальномер»: c8_inject.py starts c8_follow.py detached, RUN/follow.pid);
#   RUN/stop_follow is touched at the end of the script and in cleanup (the follower then exits; follow.pid is
#   killed with the other process groups).
#   ed.6c (09.11, Claude, orchestrator decision «пропал дальномер»): + --range-relay: starts
#   /work/c8_range_model_20261109/c8_range_relay.py (copied to the snapshot; setsid, RUN/rangerelay.pid, inherits
#   GZ_PARTITION/GZ_IP) right after the gz server is up; it forwards the lidar scan of model_v1b (--model
#   /work/c8_range_model_20261109/model_v1b/bumblebee, own topic /c8/lidar_raw) unchanged to the GZBridge topic until
#   RUN/range_off (+ inject ACTION range_off). Refuses a model with /c8/lidar_raw without --range-relay and vice versa.
#   Cleanup stops the relay after PX4 (RUN/stop_range_relay, then TERM/KILL of its own pid only).
# Edition 5 (09.11, Claude): ed.4 + --image r2d, disk guard (<8 GB free on C: = REFUSE), rc_hold2 + --pilot-pos-on PATTERN [--pilot-pos-nth N].
# Edition 4 (09.11, Claude): edition 3 + T22 model_v1 / plugin_v1 by default (--model DIR, --flow-plugin FILE|stock).
# Edition 3 (09.11, Claude): run_scenario2.sh + test «упал только скрипт»: --kill-script-on PATTERN sends SIGKILL to the
#   script session only (the example script and its wrappers) when PATTERN first appears in script.log; PX4, Gazebo,
#   MAVROS and all image ROS nodes keep running; --after-kill-s N (default 30) keeps recording N s after the kill.
#                              [--probe-param-events] [--script-height H] [--end-after-disarm S] [--end-if-idle S]
#   SCRIPT: flight.py | flight_marker.py | flight_marker_loop.py | /work/goal_step5b_20261109/scenarios/NAME.py
# Refuses to start while any px4 / gz / ruby / mavros_node process is alive; never overwrites a run folder.
# Stops only its own process groups (and GZ_PARTITION=bbtrial leftovers). Gazebo keeps its usual cache in ~/.gz.
# 5b additions (each written into RUN/run_options.json and the report):
#   * runs go to /work/goal_step5b_20261109/runs; one run at a time also through flock on .sim.lock; refuses also when
#     a process of an earlier run of this stand (env BB_STAND=goal_step5b) or a ROS-domain-83 ros2 daemon is alive;
#   * pkill stand-in (standin/bin/pkill) FIRST in PATH of the script process only; log RUN/standin_pkill.jsonl;
#   * --trial-map-file (REQUIRED for a script that calls set_aruco_map): drone.MAP_FILE -> RUN/aruco_map_written/map.txt
#     through tools/trial_runner.py (labelled trial option: /home/lb cannot be created without sudo);
#   * the script runs in its own session; if it does not exit by itself (finding F4), the launcher ends the script's
#     process group with SIGTERM once the drone has been disarmed for --end-after-disarm s (default 15) with no new
#     output, or, if it never armed, after --end-if-idle s (default 60) with no output; reason in RUN/script_end.txt;
#   * script output is also time-stamped by a read-only follower (RUN/script_ts.log);
#   * --probe-param-events: read-only F3 measurement node (tools/param_events_probe.py) during the run;
#   * PYTHONDONTWRITEBYTECODE=1: nothing (no __pycache__) is written into the image folders;
#   * after the run also tools/goal_eval2.py (step 5 goal_eval.py still runs unchanged).
set -uo pipefail
STEP5B=/work/goal_step5b_20261109
STEP5=/work/goal_step5_20261106
STEP4=/work/goal_step4_20261106
C8=/work/c8_new_checks_20261109   # ed.6
PX4=$HOME/PX4-Autopilot
B=$PX4/build/px4_sitl_default
DRONE=/work/pc_inventory_20261019/incident_motors_20261104/params_20261104_1145.params
PY=$HOME/px4-venv/bin/python3
PRODUCT=/work/ws_package1b_port_03
EXAMPLES=$PRODUCT/src/bumblebee/examples
ARUCO_DIR=/work/sim/worlds/aruco_map
TAG=${1:?TAG}; AF=${2:?AIRFRAME}; SCRIPT=${3:?SCRIPT}; shift 3
GUI=0; TIMEOUT=300; ARUCO_ALWAYS=0
IMAGE=port03; MAP_TRIAL=0; PROBE=0; SCRIPT_H_OPT=""; END_AFTER_DISARM=15; END_IF_IDLE=60; KILL_PAT=""; AFTER_KILL_S=30; KILLED=0; PILOT_PAT=""; PILOT_NTH=1; PILOT_DONE=0; INJ_PAT=""; INJ_NTH=1; INJ_ACT=""; INJ_DONE=0; AFTER_INJ_S=30; MODEL=/work/goal_t22_flow_20261109/model_v1/bumblebee; FLOWPLUG=/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so     # 5b; ed.3; ed.4
VISION_HZ=0   # ed.7 M-V12
RANGE_RELAY=0; RR=/work/c8_range_model_20261109/c8_range_relay.py; RR_TOPIC='<topic>/c8/lidar_raw</topic>'   # ed.6c
while [ $# -gt 0 ]; do
  case $1 in
    --gui) GUI=1 ;;
    --timeout) TIMEOUT=$2; shift ;;
    --trial-aruco-always) ARUCO_ALWAYS=1 ;;   # finding F1 work-around (detector never sleeps); labelled in the report
    --trial-map-file) MAP_TRIAL=1 ;;          # 5b: finding F2 work-around (map written into the run folder); labelled
    --probe-param-events) PROBE=1 ;;          # 5b: F3 measurement node (read-only)
    --script-height) SCRIPT_H_OPT=$2; shift ;;
    --image) IMAGE=$2; shift ;;   # 09.11: r2b = /work/fixed_image_r2_20261109 (src, install, manifest r2)
    --end-after-disarm) END_AFTER_DISARM=$2; shift ;;
    --end-if-idle) END_IF_IDLE=$2; shift ;;
    --kill-script-on) KILL_PAT=$2; shift ;;      # edition 3
    --model) MODEL=$2; shift ;;                  # edition 4
    --pilot-pos-on) PILOT_PAT=$2; shift ;;       # edition 5
    --pilot-pos-nth) PILOT_NTH=$2; shift ;;      # edition 5
    --flow-plugin) FLOWPLUG=$2; shift ;;         # edition 4 (stock = PX4 libOpticalFlowSystem.so)
    --after-kill-s) AFTER_KILL_S=$2; shift ;;    # edition 3
    --inject-on) INJ_PAT=$2; INJ_NTH=$3; INJ_ACT=$4; shift 3 ;;   # edition 6
    --after-inject-s) AFTER_INJ_S=$2; shift ;;   # edition 6
    --range-relay) RANGE_RELAY=1 ;;              # ed.6c
    --vision-max-hz) VISION_HZ=$2; shift ;;      # ed.7 M-V12: stand vision limiter (12 = 20EC)
    *) echo "unknown option $1"; exit 2 ;;
  esac
  shift
done
case $INJ_ACT in "") [ -z "$INJ_PAT" ] || { echo "REFUSE: --inject-on needs PATTERN NTH ACTION"; exit 2; } ;;   # ed.6
  markers_off|floor_off|rc_off|floor_near_off|sensor_block_on|sensor_block_far_on|range_off) [ -n "$INJ_PAT" ] && [[ $INJ_NTH =~ ^[1-9][0-9]*$ ]] || { echo "REFUSE: --inject-on PATTERN NTH ACTION (NTH >= 1)"; exit 2; } ;;
  *) echo "REFUSE: inject ACTION must be markers_off | floor_off | rc_off | floor_near_off | sensor_block_on | sensor_block_far_on | range_off"; exit 2 ;; esac
[[ $AFTER_INJ_S =~ ^[0-9]+$ ]] || { echo "REFUSE: --after-inject-s N"; exit 2; }
[[ $VISION_HZ =~ ^[0-9]+([.][0-9]+)?$ ]] || { echo "REFUSE: --vision-max-hz N"; exit 2; }   # ed.7
[ -f /work/goal_af4070_20261110/vision_throttle.py ] && [ -f /work/goal_af4070_20261110/scenario_stack_v12.launch.py ] && [ -f /work/goal_af4070_20261110/sim_only_4070_v2.json ] || { echo "REFUSE: ed.7 files missing in /work/goal_af4070_20261110"; exit 2; }
[ -f $C8/rc_hold3.py ] && [ -f $C8/c8_inject.py ] && [ -f $C8/c8_follow.py ] || { echo "REFUSE: no $C8/rc_hold3.py, c8_inject.py or c8_follow.py"; exit 2; }
RR_IN_MODEL=$(grep -cF -- "$RR_TOPIC" "$MODEL/model.sdf" 2>/dev/null); RR_IN_MODEL=${RR_IN_MODEL:-0}   # ed.6c
if [ $RANGE_RELAY = 1 ]; then
  [ -f $RR ] || { echo "REFUSE: no $RR"; exit 2; }
  [ "$RR_IN_MODEL" = 1 ] || { echo "REFUSE: --range-relay needs a model whose lidar publishes on /c8/lidar_raw (model_v1b), not $MODEL"; exit 2; }
else
  [ "$RR_IN_MODEL" = 0 ] || { echo "REFUSE: $MODEL publishes the lidar on /c8/lidar_raw: without --range-relay PX4 gets no rangefinder"; exit 2; }
  [ "$INJ_ACT" = range_off ] && { echo "REFUSE: inject range_off needs --range-relay"; exit 2; }
fi
FREE_G=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d " ")   # ed.5 disk guard
[ "${FREE_G:-0}" -ge 8 ] || { echo "REFUSE: disk C: free ${FREE_G}G < 8G (АРХИТЕКТУРА_РАБОТЫ.md §8)"; exit 2; }
case $AF in 4032|4034|4035|4036|4037|4038|4044|4045|4046|4047|4055|4056|4057|4058|4059|4060|4061|4070) ;; *) echo "AIRFRAME not allowed"; exit 2 ;; esac
IMG_SRC=$PRODUCT/src/bumblebee; IMG_INSTALL=$PRODUCT/install; IMG_PINS=""
if [ "${IMAGE:0:2}" = r2 ]; then R2=/work/fixed_image_r2_20261109; [ "$IMAGE" = r2c ] && R2=/work/fixed_image_r2c_20261109; [ "$IMAGE" = r2d ] && R2=/work/fixed_image_r2d_20261109; [ "$IMAGE" = r2e ] && R2=/work/fixed_image_r2e_20261109; [ "$IMAGE" = r2f ] && R2=/work/fixed_image_r2f_20261110; IMG_SRC=$R2/src/bumblebee; IMG_INSTALL=$R2/install; EXAMPLES=$IMG_SRC/examples
  IMG_PINS="--src $IMG_SRC --install $IMG_INSTALL --manifest $R2/image_manifest_r2.tsv"; fi
case $SCRIPT in
  flight.py) SCRIPT_REL=examples/flight/flight.py; SCRIPT_H=1.5; [ "${IMAGE:0:2}" = r2 ] && SCRIPT_H=0.8 ;;                    # takeoff(height=1.5) in the image's code
  flight_marker.py) SCRIPT_REL=examples/flight/flight_marker.py; SCRIPT_H=0.7 ;;      # 5b: takeoff(height=0.7)
  flight_marker_loop.py) SCRIPT_REL=examples/flight/flight_marker_loop.py; SCRIPT_H=1.3 ;;   # 5b: takeoff(height=1.3)
  $STEP5B/scenarios/*.py) SCRIPT_REL=$SCRIPT; SCRIPT_H=1.0 ;;
  /work/c6_hover_script_r2_20261109/hover_marker0.py) SCRIPT_REL=$SCRIPT; SCRIPT_H=1.0 ;;
  /work/c6_hover_script_r5_20261110/hover_marker0.py) SCRIPT_REL=$SCRIPT; SCRIPT_H=1.0 ;;   # ed.7b: C6 script r5 (3620d300, r2f+)
  /work/c6_hover_script_r4_20261110/hover_marker0.py) SCRIPT_REL=$SCRIPT; SCRIPT_H=1.0 ;;   # ed.7: C6 script r4 (655777c2)
  /work/c6_hover_script_r3_20261109/hover_marker0.py) SCRIPT_REL=$SCRIPT; SCRIPT_H=1.0 ;;   # ed.5: C6 script r3 (9aabddd6, variant B: flies to marker 0 centre)   # ed.5: C6 script r2 (cdc96ba6) from «Скрипты полёта»                         # 5b: new scenario (not image code)
  *) echo "SCRIPT not supported: $SCRIPT"; exit 2 ;;
esac
[ -n "$SCRIPT_H_OPT" ] && SCRIPT_H=$SCRIPT_H_OPT
case $SCRIPT_REL in *..*) echo "REFUSE: '..' in the script path"; exit 2 ;; esac
if [ "${SCRIPT_REL:0:1}" = / ]; then SCRIPT_PATH=$SCRIPT_REL; else SCRIPT_PATH=$IMG_SRC/$SCRIPT_REL; fi
[ -f "$SCRIPT_PATH" ] || { echo "no such script: $SCRIPT_PATH"; exit 2; }
USES_MAP=0; grep -q 'set_aruco_map(' "$SCRIPT_PATH" && USES_MAP=1
if [ $USES_MAP = 1 ] && [ $MAP_TRIAL = 0 ]; then
  echo "REFUSE: $SCRIPT calls drone.set_aruco_map(), which writes /home/lb/... (absent on the PC, no sudo)."
  echo "        Run it only with the labelled trial option --trial-map-file."; exit 2
fi
RUN=$STEP5B/runs/$TAG
# SIM_LOCK (АРХИТЕКТУРА_РАБОТЫ.md, 09.11): refuse unless the lock is held by this chat
grep -q "local_bc6f158c" /work/SIM_LOCK.txt 2>/dev/null || { echo "REFUSE: /work/SIM_LOCK.txt not held by Симулятор (local_bc6f158c)"; exit 2; }
[ -e "$RUN" ] && { echo "REFUSE: $RUN exists (never overwrite)"; exit 2; }
exec 9> "$STEP5B/.sim.lock"                                                            # 5b: one run at a time
flock -n 9 || { echo "REFUSE: another run_scenario2/3.sh run holds $STEP5B/.sim.lock"; exit 2; }
busy=$( { pgrep -x px4; pgrep -x gz; pgrep -x ruby; pgrep -x mavros_node; } | tr '\n' ' ')
if [ -n "${busy// /}" ]; then
  echo "REFUSE: simulator/ROS processes alive: $busy(one simulator at a time; not touching them)"
  ps -o pid,etime,args -p "$(echo $busy | tr ' ' ',')"
  exit 2
fi
# 5b: leftovers of an earlier run of this stand (own processes only; their environment carries BB_STAND)
left=$(for e in /proc/[0-9]*/environ; do tr '\0' '\n' < "$e" 2>/dev/null | grep -qx 'BB_STAND=goal_step5b' && { p=${e#/proc/}; echo -n "${p%/environ} "; }; done)
if [ -n "${left// /}" ]; then
  echo "REFUSE: processes of an earlier stand run alive: $left(not touching them)"; ps -o pid,etime,args -p "$(echo $left | tr ' ' ',')"; exit 2
fi
d83=$(ps -eo pid=,args= | awk '/--name ros2-daemon --ros-domain-id 83( |$)/ && !/awk/ {print $1}' | tr '\n' ' ')
[ -n "${d83// /}" ] && { echo "REFUSE: a ROS-domain-83 ros2 daemon is alive ($d83); not touching it"; exit 2; }
export BB_STAND=goal_step5b PYTHONDONTWRITEBYTECODE=1                                   # 5b
mkdir -p "$RUN/rootfs" "$RUN/models" "$RUN/snapshot/tools" "$RUN/snapshot/standin"
exec > >(tee -a "$RUN/launcher.log") 2>&1
echo "ТОЛЬКО СИМУЛЯТОР (ed.7b logger_by_SDLOG_MODE r5 sim_only=4070v2; ed.7 vision_max_hz=$VISION_HZ; ed.6c range_relay=$RANGE_RELAY; ed.6 inject_on=${INJ_PAT:-none}#$INJ_NTH:${INJ_ACT:-none} after_inject_s=$AFTER_INJ_S rc=rc_hold3; ed.5 image=$IMAGE pilot_pos_on=${PILOT_PAT:-none}#$PILOT_NTH; ed.4 model=$MODEL flow_plugin=$FLOWPLUG; ed.3 kill_script_on=${KILL_PAT:-none} after_kill_s=$AFTER_KILL_S): scenario $TAG airframe $AF script $SCRIPT gui=$GUI timeout=${TIMEOUT}s trial_aruco_always=$ARUCO_ALWAYS trial_map_file=$MAP_TRIAL probe_param_events=$PROBE script_height=$SCRIPT_H end_after_disarm=${END_AFTER_DISARM}s end_if_idle=${END_IF_IDLE}s $(date -Is)"
# 5b: run options and every trial deviation, machine-readable
python3 -I -B - "$RUN/run_options.json" "$TAG" "$AF" "$SCRIPT" "$SCRIPT_PATH" "$GUI" "$TIMEOUT" "$ARUCO_ALWAYS" "$MAP_TRIAL" \
  "$PROBE" "$SCRIPT_H" "$END_AFTER_DISARM" "$END_IF_IDLE" "$USES_MAP" <<'PY'
import json, sys
(out, tag, af, script, path, gui, timeout, aruco, mapt, probe, h, ead, eii, uses) = sys.argv[1:]
dev = []
if aruco == '1':
    dev.append('trial-aruco-always (F1): aruco_detect gate_by_flight_state=False, detector works before arming')
if mapt == '1':
    dev.append('trial-map-file (F2): drone.MAP_FILE -> RUN/aruco_map_written/map.txt instead of /home/lb/...')
if uses == '1':
    dev.append('pkill stand-in (F2): `pkill` in the script PATH acts only inside the script session (rule 13)')
if probe == '1':
    dev.append('probe-param-events (F3): an extra read-only ROS node subscribes to /parameter_events')
json.dump({'tag': tag, 'airframe': int(af), 'script': script, 'script_path': path, 'gui': gui == '1',
           'timeout_s': int(timeout), 'trial_aruco_always': aruco == '1', 'trial_map_file': mapt == '1',
           'probe_param_events': probe == '1', 'script_height_m': float(h), 'end_after_disarm_s': int(ead),
           'end_if_idle_s': int(eii), 'script_calls_set_aruco_map': uses == '1', 'trial_deviations': dev,
           'stand_always': ['F4 handling: launcher ends a script that does not exit by itself (script_end.txt)',
                            'script output time-stamped by a read-only follower (script_ts.log)',
                            'PYTHONDONTWRITEBYTECODE=1']},
          open(out, 'x'), indent=1)
PY

# --- snapshot + versions
cp $STEP5B/run_scenario2.sh $STEP5B/run_scenario3.sh $STEP5B/run_scenario4.sh $STEP5B/run_scenario5.sh $STEP5B/run_scenario6.sh $STEP5B/run_scenario7.sh $STEP5B/run_scenario7b.sh $STEP5/scenario_stack.launch.py "$RUN/snapshot/"
cp $STEP5/tools/rc_hold.py $STEP5B/tools/rc_hold2.py $STEP5/tools/goal_eval.py "$RUN/snapshot/tools/"
cp $C8/rc_hold3.py $C8/c8_inject.py $C8/c8_follow.py "$RUN/snapshot/tools/"              # ed.6 (+ c8_follow ed.6b)
[ $RANGE_RELAY = 1 ] && cp $RR "$RUN/snapshot/tools/"                                     # ed.6c
cp $STEP5B/tools/pins_check2.py $STEP5B/tools/goal_eval2.py $STEP5B/tools/trial_runner.py $STEP5B/tools/line_stamp.py \
   $STEP5B/tools/param_events_probe.py "$RUN/snapshot/tools/"                         # 5b
cp -r $STEP5B/standin/bin "$RUN/snapshot/standin/"                                     # 5b
[ "${SCRIPT_REL:0:1}" = / ] && cp "$SCRIPT_PATH" "$RUN/snapshot/scenario_$(basename "$SCRIPT_PATH")"   # 5b
cp /work/goal_af4070_20261110/sim_only_4070_v2.json "$RUN/snapshot/sim_only.json"   # ed.7 (was sim_only_t22.json, ed.4)
cp /work/goal_af4070_20261110/scenario_stack_v12.launch.py "$RUN/snapshot/scenario_stack.launch.py"   # ed.7 M-V12 (stand launch + optional vision limiter)
cp /work/goal_af4070_20261110/vision_throttle.py "$RUN/snapshot/tools/"   # ed.7
cp $STEP4/tools/param_parity.py $STEP4/tools/sitl_param_names.txt "$RUN/snapshot/tools/"
SNAP=$RUN/snapshot
{
  echo "date $(date -Is)"
  echo "px4_source_head $(cd $PX4 && git rev-parse HEAD)"
  echo "px4_binary_sha256 $(sha256sum < $B/bin/px4 | cut -c1-64)"
  echo "gz $(gz sim --versions 2>/dev/null | head -1)"
  echo "airframe $AF $(sha256sum $STEP5B/px4_etc/init.d-posix/airframes/${AF}_* | cut -c1-64)"
  echo "airframe 4032 $(sha256sum $STEP5B/px4_etc/init.d-posix/airframes/4032_* | cut -c1-64)"
  echo "model_sdf $MODEL $(sha256sum < $MODEL/model.sdf | cut -c1-64)"
  echo "range_relay $RANGE_RELAY"   # ed.6c (relay sha256: tools/c8_range_relay.py below)
  [ "$FLOWPLUG" = stock ] && echo "flow_plugin stock" || echo "flow_plugin $FLOWPLUG $(sha256sum < $FLOWPLUG | cut -c1-64)"
  echo "aruco_world $(sha256sum < $ARUCO_DIR/default.sdf | cut -c1-64) map $(sha256sum < $ARUCO_DIR/map.input.txt | cut -c1-64)"
  echo "product $(tail -1 $PRODUCT/RC3_PROVENANCE.txt | cut -c1-80)"
  echo "script $SCRIPT_REL $(sha256sum < "$SCRIPT_PATH" | cut -c1-64)"
  (cd "$SNAP" && sha256sum run_scenario2.sh run_scenario3.sh run_scenario4.sh run_scenario5.sh run_scenario6.sh run_scenario7.sh run_scenario7b.sh scenario_stack.launch.py sim_only.json tools/* standin/bin/*)
} > "$RUN/versions.txt"
cat "$RUN/versions.txt"
$PY -I $SNAP/tools/pins_check2.py "$RUN" "$SCRIPT_REL" $IMG_PINS

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
[ "$(basename $MODEL)" = bumblebee ] || { echo "REFUSE: --model folder must be named bumblebee"; exit 2; }
cp -r $MODEL /work/sim/models/bb_floor_noise "$RUN/models/"
export GZ_SIM_RESOURCE_PATH=$RUN/models:$ARUCO_DIR/models:$GZ_SIM_RESOURCE_PATH
cp $PX4_GZ_SERVER_CONFIG "$RUN/server.config"
if [ "$FLOWPLUG" != stock ]; then [ -f "$FLOWPLUG" ] || { echo "REFUSE: no $FLOWPLUG"; exit 2; }; sed -i "s|filename=\"libOpticalFlowSystem.so\"|filename=\"$FLOWPLUG\"|" "$RUN/server.config"; fi   # ed.4
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
  touch "$RUN/stop_rc" "$RUN/stop_probe" "$RUN/stop_stamp" "$RUN/stop_follow"   # ed.6b: + stop_follow
  # 5b: the script's own session / process group (script, ros2 CLI and a ros2 daemon it may have spawned)
  [ -f "$RUN/script.pid" ] && kill -TERM -- -"$(cat "$RUN/script.pid")" 2>/dev/null
  for _ in $(seq 30); do [ -f "$RUN/probe.pid" ] && kill -0 "$(cat "$RUN/probe.pid")" 2>/dev/null || break; sleep 0.5; done
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
  if [ -f "$RUN/rangerelay.pid" ]; then   # ed.6c: after PX4; only the relay's own pid (checked by its command line)
    touch "$RUN/stop_range_relay"
    RRP=$(cat "$RUN/rangerelay.pid")
    for _ in $(seq 20); do kill -0 "$RRP" 2>/dev/null || break; sleep 0.2; done
    if grep -qa c8_range_relay.py /proc/$RRP/cmdline 2>/dev/null; then
      kill -TERM "$RRP" 2>/dev/null; sleep 1
      grep -qa c8_range_relay.py /proc/$RRP/cmdline 2>/dev/null && kill -KILL "$RRP" 2>/dev/null
    fi
    rm -f "$RUN/rangerelay.pid"
  fi
  for f in ros rc px4 gui gz stats script probe stamp follow; do                       # 5b: + script probe stamp; ed.6b: + follow
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
  setsid $B/bin/px4 -d -w "$RUN/rootfs" "$STEP5B/px4_etc" > "$RUN/px4.log" 2>&1 < /dev/null &
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
if [ $RANGE_RELAY = 1 ]; then   # ed.6c: lidar relay right after the gz server; PX4 (started first) is still in its startup script
  setsid /usr/bin/python3 -I -B "$SNAP/tools/c8_range_relay.py" "$RUN" --max-s $((TIMEOUT + 3600)) > "$RUN/c8_range_relay.stderr" 2>&1 < /dev/null &
  echo $! > "$RUN/rangerelay.pid"
  for _ in $(seq 150); do [ -e "$RUN/c8_range_relay_ready" ] && break; sleep 0.1; done
  echo "range relay ready: $([ -e "$RUN/c8_range_relay_ready" ] && echo yes || echo NO) pid $(cat "$RUN/rangerelay.pid") $(date -Is)"
  [ -e "$RUN/c8_range_relay_ready" ] || { echo "STOP: range relay not ready (RUN/c8_range_relay.stderr)"; exit 2; }
fi
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
SDLM=$($B/bin/px4-param show -q SDLOG_MODE)   # ed.7b: restart like PX4 rc.logging (was: only when SDLOG_MODE = 0)
case $SDLM in 0) LGA="" ;; 1) LGA="-e" ;; 2) LGA="-f" ;; 3) LGA="-x" ;; 4) LGA="-a" ;; *) LGA=none ;; esac
[ "$LGA" = none ] || $B/bin/px4-logger start -b 1000 -t $LGA
echo "logger SDLOG_MODE=$SDLM args=-b 1000 -t $LGA"
echo "logger restarted"

# --- transmitter + ground station emulation, parameter read for C2
setsid $PY -I $SNAP/tools/rc_hold3.py "$RUN" "$DRONE" --max-s $((TIMEOUT + 300)) > "$RUN/rc_hold.log" 2>&1 < /dev/null &
echo $! > "$RUN/rc.pid"
for _ in $(seq 60); do [ -e "$RUN/rc_ready" ] && break; sleep 1; done
echo "rc_hold ready: $([ -e "$RUN/rc_ready" ] && echo yes || echo NO)"

# --- the drone's ROS 2 nodes
set +u
source /opt/ros/jazzy/setup.bash
source /work/ws_sitl/install/setup.bash                       # aruco_pose messages (drone.py imports them)
for p in libmavconn mavros_msgs mavros_extras; do source /work/ws_mavros214/install/$p/share/$p/package.bash; done
source /work/ws_mavros214_bp02_rel/install/local_setup.bash
source $IMG_INSTALL/local_setup.bash
set -u
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 MAVLINK20=1
export GEOGRAPHICLIB_GEOID_PATH=/work/sim/ros_stack/geoids
export BB_FCU_URL=udp://127.0.0.1:14540@127.0.0.1:14580 BB_TRIAL_ARUCO_ALWAYS=$ARUCO_ALWAYS
cp /work/sim/ros_stack/mavros214.yaml "$RUN/mavros_source.yaml"
export BB_MAVROS_SOURCE_YAML=$RUN/mavros_source.yaml BB_MAVROS_SCOPED_YAML=$RUN/mavros_scoped.yaml
echo "ros: mavros $(ros2 pkg prefix mavros) bumblebee $(ros2 pkg prefix bumblebee)"
if [ $PROBE = 1 ]; then                                                                  # 5b: F3 measurement node
  WATCH=$(python3 -I -B -c "import sys; sys.path.insert(0, '$EXAMPLES'); import flight_profile as f; print(' '.join(sorted({k for p in f.PROFILES.values() for k in p})))")
  setsid /usr/bin/python3 -B $SNAP/tools/param_events_probe.py "$RUN" --max-s $((TIMEOUT + 900)) --watch $WATCH > "$RUN/probe.log" 2>&1 < /dev/null &
  echo $! > "$RUN/probe.pid"
  sleep 3
  echo "param events probe started (watch: $WATCH)"
fi
export BB_VISION_MAX_HZ=$VISION_HZ BB_VISION_THROTTLE=$SNAP/tools/vision_throttle.py BB_VISION_LOG=$RUN/vision_throttle.log   # ed.7
setsid ros2 launch "$SNAP/scenario_stack.launch.py" > "$RUN/ros.log" 2>&1 < /dev/null &
echo $! > "$RUN/ros.pid"
for i in $(seq 90); do grep -q "Got HEARTBEAT, connected" "$RUN/ros.log" 2>/dev/null && break; sleep 1; done
echo "mavros: $(grep -m1 -o 'Got HEARTBEAT, connected.*' "$RUN/ros.log" || echo 'NOT connected') after ${i}s"
for i in $(seq 90); do grep -q "parameters list received" "$RUN/ros.log" 2>/dev/null && break; sleep 1; done
echo "mavros params: $(grep -m1 -o 'parameters list received.*' "$RUN/ros.log" || echo 'NOT complete') after ${i}s"
sleep 10    # let the camera, detector and vpe_fix start; on the drone a script starts long after boot

# --- the unmodified example script of the image (5b: own session, pkill stand-in in its PATH, F4 handling)
cd "$RUN"
echo "script start $(date -Is)"
if [ $MAP_TRIAL = 1 ]; then
  SCRIPT_CMD=(/usr/bin/python3 -u "$SNAP/tools/trial_runner.py" --map-file "$([ "${IMAGE:0:2}" = r2 ] && echo /work/ws_sitl/install/aruco_pose/share/aruco_pose/map/map.txt || echo "$RUN/aruco_map_written/map.txt")"
              --record "$RUN/trial_runner.json" "$SCRIPT_PATH")
  [ "${IMAGE:0:2}" = r2 ] && SCRIPT_CMD=(/usr/bin/python3 -u "$SNAP/tools/trial_runner.py" --map-readonly
              --map-file /work/ws_sitl/install/aruco_pose/share/aruco_pose/map/map.txt --record "$RUN/trial_runner.json" "$SCRIPT_PATH")   # 09.11 r2b: map read-only
else
  SCRIPT_CMD=(/usr/bin/python3 -u "$SCRIPT_PATH")
fi
: > "$RUN/script.log"
setsid /usr/bin/python3 -I $SNAP/tools/line_stamp.py "$RUN/script.log" "$RUN/script_ts.log" "$RUN/stop_stamp" < /dev/null > "$RUN/stamp.log" 2>&1 &
echo $! > "$RUN/stamp.pid"
setsid -w bash -c 'echo $$ > "$0/script.pid"; export BB_STANDIN_SID=$$ BB_STANDIN_LOG="$0/standin_pkill.jsonl" PATH="$1:$PATH" PYTHONPATH="$2:${PYTHONPATH:-}"; shift 2; exec timeout --signal=INT --kill-after=20 "$@"' \
  "$RUN" "$SNAP/standin/bin" "$EXAMPLES" "$TIMEOUT" "${SCRIPT_CMD[@]}" > "$RUN/script.log" 2>&1 < /dev/null &
SPID=$!
ARMED_SEEN=0; DISARM_T=0; END_REASON=""
while kill -0 $SPID 2>/dev/null; do
  sleep 1
  if [ -n "$INJ_PAT" ] && [ $INJ_DONE = 0 ] && [ "$(grep -cF -- "$INJ_PAT" "$RUN/script.log" 2>/dev/null)" -ge "$INJ_NTH" ]; then   # edition 6
    INJ_DONE=1
    python3 -I -B -c 'import json, sys, time; json.dump({"kind": "inject_request", "wall": round(time.time(), 4), "pattern": sys.argv[2], "nth": int(sys.argv[3]), "action": sys.argv[4]}, open(sys.argv[1], "x"))' \
      "$RUN/inject_request.json" "$INJ_PAT" "$INJ_NTH" "$INJ_ACT"
    timeout 60 /usr/bin/python3 -I -B "$SNAP/tools/c8_inject.py" "$RUN" "$INJ_ACT" >> "$RUN/c8_inject.log" 2>&1; INJ_RC=$?
    echo "INJECTED $INJ_ACT $(date -Is) on pattern '$INJ_PAT' #$INJ_NTH: c8_inject exit $INJ_RC; $(tail -1 "$RUN/c8_inject.log")"
  fi
  if [ -n "$PILOT_PAT" ] && [ $PILOT_DONE = 0 ] && [ "$(grep -c -- "$PILOT_PAT" "$RUN/script.log" 2>/dev/null)" -ge "$PILOT_NTH" ]; then   # edition 5
    PILOT_DONE=1; touch "$RUN/pilot_pos"
    echo "{\"kind\": \"pilot_pos_request\", \"wall\": $(date +%s.%N), \"pattern\": \"$PILOT_PAT\", \"nth\": $PILOT_NTH}" > "$RUN/pilot_pos.json"
    echo "PILOT TAKES POSITION $(date -Is) on pattern '$PILOT_PAT' #$PILOT_NTH"
  fi
  if [ -n "$KILL_PAT" ] && [ $KILLED = 0 ] && grep -q -- "$KILL_PAT" "$RUN/script.log" 2>/dev/null; then   # edition 3
    KILLED=1; KILL_T=$(date +%s.%N)
    kill -KILL -- -"$(cat "$RUN/script.pid")" 2>/dev/null
    echo "{\"kind\": \"script_killed\", \"wall\": $KILL_T, \"pattern\": \"$KILL_PAT\", \"signal\": \"KILL\", \"target\": \"script session only\"}" > "$RUN/script_kill.json"
    echo "$(date -Is) killed by launcher (test «упал только скрипт»): SIGKILL to script session on pattern '$KILL_PAT'" > "$RUN/script_end.txt"
    echo "SCRIPT KILLED $(date -Is) on pattern '$KILL_PAT'; nodes kept; recording ${AFTER_KILL_S}s more"
    break
  fi
  last=$(grep '"kind": "state"' "$RUN/events.jsonl" 2>/dev/null | tail -1)
  case $last in
    *'"armed": true'*) ARMED_SEEN=1; DISARM_T=0 ;;
    *'"armed": false'*) [ $ARMED_SEEN = 1 ] && [ $DISARM_T = 0 ] && DISARM_T=$(date +%s) ;;
  esac
  now=$(date +%s); idle=$(( now - $(stat -c %Y "$RUN/script.log" 2>/dev/null || echo $now) ))
  if [ $ARMED_SEEN = 1 ] && [ $DISARM_T != 0 ] && [ $(( now - DISARM_T )) -ge $END_AFTER_DISARM ] && [ $idle -ge $END_AFTER_DISARM ]; then
    END_REASON="ended by launcher: disarmed $(( now - DISARM_T )) s ago, no output for ${idle} s, script did not exit by itself (F4)"
  elif [ $ARMED_SEEN = 0 ] && [ $idle -ge $END_IF_IDLE ]; then
    END_REASON="ended by launcher: never armed, no output for ${idle} s, script did not exit by itself (F4)"
  fi
  if [ -n "$END_REASON" ] && kill -0 $SPID 2>/dev/null; then
    echo "$(date -Is) $END_REASON" > "$RUN/script_end.txt"
    echo "$END_REASON"
    kill -TERM -- -"$(cat "$RUN/script.pid")" 2>/dev/null
    break
  fi
  END_REASON=""
done
wait $SPID; SCRIPT_RC=$?
if [ $KILLED = 1 ] || [ $PILOT_DONE = 1 ]; then   # edition 3 (+ ed.5 pilot take-over): PX4, Gazebo and all ROS nodes stay alive and recorded
  sleep "$AFTER_KILL_S"
  echo "after-kill window ${AFTER_KILL_S}s done $(date -Is); alive: px4 $(pgrep -x px4 | wc -l), mavros_node $(pgrep -x mavros_node | wc -l), simple_offboard $(pgrep -x simple_offboard | wc -l)"
  echo "last state: $(grep '"kind": "state"' "$RUN/events.jsonl" 2>/dev/null | tail -1)"
fi
if [ $INJ_DONE = 1 ]; then   # edition 6: PX4, Gazebo and all ROS nodes stay alive and recorded after the script
  sleep "$AFTER_INJ_S"
  echo "after-inject window ${AFTER_INJ_S}s done $(date -Is); last state: $(grep '"kind": "state"' "$RUN/events.jsonl" 2>/dev/null | tail -1)"
else
  [ -n "$INJ_PAT" ] && echo "NOT INJECTED: pattern '$INJ_PAT' did not reach $INJ_NTH lines in script.log"
fi
[ -e "$RUN/script_end.txt" ] || echo "$(date -Is) exited by itself, code $SCRIPT_RC" > "$RUN/script_end.txt"
echo "script exit $SCRIPT_RC $(date -Is); $(cat "$RUN/script_end.txt")"
touch "$RUN/stop_stamp" "$RUN/stop_probe" "$RUN/stop_follow"   # ed.6b: + stop_follow (box follower)
for _ in $(seq 40); do [ -f "$RUN/probe.pid" ] && kill -0 "$(cat "$RUN/probe.pid")" 2>/dev/null || break; sleep 0.5; done
sleep 5
cleanup
trap - EXIT
echo "stopped $(date -Is); alive px4/gz/ruby/mavros_node: $( { pgrep -x px4; pgrep -x gz; pgrep -x ruby; pgrep -x mavros_node; } | tr '\n' ' ')"
echo "alive ROS-domain-83 ros2 daemon after cleanup: $(ps -eo pid=,args= | awk '/--name ros2-daemon --ros-domain-id 83( |$)/ && !/awk/ {print $1}' | tr '\n' ' ')"

$PY -I $SNAP/tools/param_parity.py "$RUN" "$DRONE" $SNAP/sim_only.json "$AF"
echo "parity exit $?"
ULG=$(ls -t "$RUN"/rootfs/log/*/*.ulg 2>/dev/null | head -1)
if [ -n "$ULG" ]; then
  $PY -I $SNAP/tools/goal_eval.py "$RUN" "$ULG" --script-height $SCRIPT_H
else
  echo "no ULog (never armed)"
fi
$PY -I $SNAP/tools/goal_eval2.py "$RUN" --script "$SCRIPT" --script-height $SCRIPT_H ${ULG:+--ulog "$ULG"}   # 5b
echo "goal_eval2 exit $?"
tail -15 "$RUN/script.log"
(cd "$RUN" && find . -type f ! -name SHA256SUMS.txt ! -name launcher.log -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt)
echo "done $TAG $(date -Is)"
