#!/bin/bash
# Start PX4 v1.16.1 SITL + Gazebo Harmonic (headless) for the trial. SIMULATOR ONLY.
#   TAG=name MODEL=x500_flow_cam640 bash /work/sim/run_sim.sh      (returns once PX4 is up)
#   bash /work/sim/stop_sim.sh
# Knobs (env):
#   MODEL     x500 | x500_flow | x500_mono_cam_down | x500_flow_cam640 | bumblebee   (default x500_flow_cam640)
#   STOCK=1   use PX4's own launch path (HEADLESS=1, PX4 starts gz itself) instead of standalone
#   HR=1      pass --headless-rendering to gz sim (EGL, no X)                     (default 1)
#   ENGINE    ogre2 | ogre                                                         (default ogre2)
#   CAM_RATE  cam640 update rate, Hz                                               (default 30)
#   STEP      physics max_step_size, s                                             (default 0.004 = PX4 default)
#   SHADOWS   true | false: scene <shadows> AND every <cast_shadows> in the world  (default true = PX4 default)
#   LIDAR_RATE  x500_flow gpu_lidar rate, Hz (copy of the PX4 model in run/models) (default 50 = stock)
#   FLOW_RATE   optical_flow camera+sensor rate, Hz (copy of the PX4 model)        (default 50 = stock)
#   LP_NUM_THREADS  llvmpipe rasterizer threads (Mesa env, inherited by gz)         (default = nproc)
#   GST=0     drop PX4's GstCameraSystem (x264 video stream of the first camera)   (default 1 = PX4 default)
#   FLOOR=1   add bb_floor (8x8 m textured mat: noise for optical flow + ArUco grid) (default 0)
#   FLOOR=2   add bb_floor_noise (the same noise, no markers: use with ARUCO=1)
#   ARUCO=1   add the REAL marker field (map.txt, DICT_4X4_100) from /work/sim/worlds/aruco_map (default 0)
#   SPEED     PX4_SIM_SPEED_FACTOR (target real_time_factor)                       (default unset = 1)
set -euo pipefail
PX4=~/PX4-Autopilot
B=$PX4/build/px4_sitl_default
TAG=${TAG:-run}
MODEL=${MODEL:-x500_flow_cam640}
HR=${HR:-1}; ENGINE=${ENGINE:-ogre2}; CAM_RATE=${CAM_RATE:-30}; STEP=${STEP:-0.004}
SHADOWS=${SHADOWS:-true}; GST=${GST:-1}; FLOOR=${FLOOR:-0}; ARUCO=${ARUCO:-0}
ARUCO_DIR=/work/sim/worlds/aruco_map
OUT=/work/sim/runs/$TAG
RUN=/work/sim/run
mkdir -p "$OUT" "$RUN"
bash /work/sim/stop_sim.sh >/dev/null 2>&1 || true

case $MODEL in
  x500) AUTOSTART=4001 ;;
  x500_flow|x500_flow_cam640) AUTOSTART=4021 ;;
  x500_mono_cam_down) AUTOSTART=4014 ;;
  bumblebee) AUTOSTART=${BB_AIRFRAME:-4030} ;;   # the real Bumblebee (/work/sim/bumblebee_model); BB_AIRFRAME=4031 = demo estimator
  *) echo "unknown MODEL $MODEL"; exit 1 ;;
esac

export GZ_IP=127.0.0.1
export GZ_PARTITION=bbtrial
# clean PX4 state so every run starts from the airframe defaults
# Existing simulator state was moved by save_run_state.py before this script.
export GZ_SIM_RESOURCE_PATH=${GZ_SIM_RESOURCE_PATH:-} GZ_SIM_SYSTEM_PLUGIN_PATH=${GZ_SIM_SYSTEM_PLUGIN_PATH:-}
. $B/rootfs/gz_env.sh
export GZ_SIM_RESOURCE_PATH=$RUN/models:$GZ_SIM_RESOURCE_PATH
[ "$ARUCO" = 1 ] && export GZ_SIM_RESOURCE_PATH=$ARUCO_DIR/models:$GZ_SIM_RESOURCE_PATH

# trial model (camera rate knob)
test ! -e "$RUN/models"; mkdir -p "$RUN/models"
cp -r /work/sim/models/x500_flow_cam640 /work/sim/models/bb_floor $RUN/models/
[ "$FLOOR" = 2 ] && cp -r /work/sim/models/bb_floor_noise $RUN/models/
sed "s/@CAM_RATE@/$CAM_RATE/" /work/sim/models/x500_flow_cam640/model.sdf.in > $RUN/models/x500_flow_cam640/model.sdf
mv $RUN/models/x500_flow_cam640/model.sdf.in $RUN/models/x500_flow_cam640/model.sdf.in.source
[ "$MODEL" = bumblebee ] && cp -r /work/sim/bumblebee_model/models/bumblebee $RUN/models/
if [ -n "${LIDAR_RATE:-}" ]; then
  cp -r $PX4_GZ_MODELS/x500_flow $RUN/models/
  sed -i "s#<update_rate>50</update_rate>#<update_rate>$LIDAR_RATE</update_rate>#" $RUN/models/x500_flow/model.sdf
fi
if [ -n "${FLOW_RATE:-}" ]; then
  cp -r $PX4_GZ_MODELS/optical_flow $RUN/models/
  sed -i "s#<update_rate>50</update_rate>#<update_rate>$FLOW_RATE</update_rate>#g" $RUN/models/optical_flow/model.sdf
fi

# server config (render engine + optional GstCameraSystem)
sed -e "s#<render_engine>ogre2</render_engine>#<render_engine>$ENGINE</render_engine>#" $PX4_GZ_SERVER_CONFIG > $RUN/server.config
[ "$GST" = 0 ] && sed -i '/GstCameraSystem/d' $RUN/server.config
export GZ_SIM_SERVER_CONFIG_PATH=$RUN/server.config

{
  echo "TAG=$TAG MODEL=$MODEL AUTOSTART=$AUTOSTART STOCK=${STOCK:-0} HR=$HR ENGINE=$ENGINE CAM_RATE=$CAM_RATE STEP=$STEP SHADOWS=$SHADOWS GST=$GST FLOOR=$FLOOR ARUCO=$ARUCO SPEED=${SPEED:-} LIDAR_RATE=${LIDAR_RATE:-} FLOW_RATE=${FLOW_RATE:-} LP_NUM_THREADS=${LP_NUM_THREADS:-} SPAWN_POSE=${SPAWN_POSE:-default}"
  echo "date: $(date -Is)  px4: pinned local build, hashes recorded separately  gz: $(gz sim --versions | head -1)"
} | tee $OUT/config.txt

cd $B/rootfs
if [ "${STOCK:-0}" = 1 ]; then
  # exactly what `HEADLESS=1 make px4_sitl gz_<model>` runs (PX4 starts `gz sim -r -s default.sdf` itself)
  export GZ_SIM_SERVER_CONFIG_PATH=$PX4_GZ_SERVER_CONFIG
  HEADLESS=1 PX4_SIM_MODEL=gz_$MODEL ${SPEED:+PX4_SIM_SPEED_FACTOR=$SPEED} \
    setsid $B/bin/px4 -d > $OUT/px4.log 2>&1 < /dev/null &
  echo $! > $RUN/px4.pid
else
  # world = PX4 default.sdf with knobs + the model included (PX4 attaches with PX4_GZ_MODEL_NAME)
  python3 - "$PX4_GZ_WORLDS/default.sdf" "$RUN/world.sdf" "$MODEL" "$STEP" "$SHADOWS" "$FLOOR" "$ARUCO" "$ARUCO_DIR/default.sdf" "${SPAWN_POSE:-}" <<'PY'
import re, sys, math
src, dst, model, step, shadows, floor, aruco, aruco_world, spawn_pose = sys.argv[1:]
s = open(src, encoding='utf-8-sig').read()
s = re.sub(r'<max_step_size>[^<]*</max_step_size>', f'<max_step_size>{step}</max_step_size>', s)
s = re.sub(r'<real_time_update_rate>[^<]*</real_time_update_rate>',
           f'<real_time_update_rate>{round(1 / float(step))}</real_time_update_rate>', s)
s = re.sub(r'<shadows>[^<]*</shadows>', f'<shadows>{shadows}</shadows>', s)
if shadows == 'false':
    s = s.replace('<cast_shadows>true</cast_shadows>', '<cast_shadows>false</cast_shadows>')
z0 = '0.22' if model == 'bumblebee' else '0'   # bumblebee feet are 0.217 m below its origin
if spawn_pose:
    values = list(map(float, spawn_pose.split()))
    if len(values) != 6 or not all(map(math.isfinite, values)):
        raise ValueError('SPAWN_POSE must have six finite x y z roll pitch yaw values')
else:
    spawn_pose = f'0 0 {z0} 0 0 0'
inc = f'<include><uri>model://{model}</uri><name>{model}_0</name><pose>{spawn_pose}</pose></include>\n'
if floor in ('1', '2'):
    fl = 'bb_floor' if floor == '1' else 'bb_floor_noise'
    inc = f'<include><uri>model://{fl}</uri><name>{fl}</name><pose>0 0 0.002 0 0 0</pose></include>\n' + inc
if aruco == '1':
    # the marker includes of the generated field; their print surface is at z 0 there, so lift them
    # 2 mm above PX4's ground plane (no z-fighting; same as bb_floor)
    for uri, x, y, z, r, p, yaw in re.findall(
            r'<include>\s*<uri>(model://aruco_\d+)</uri>\s*<pose>(\S+) (\S+) (\S+) (\S+) (\S+) (\S+)</pose>\s*</include>',
            open(aruco_world).read()):
        lift = 0.002 if floor == '0' else 0.004   # above the ground plane / above a floor mat at 2 mm
        inc = (f'<include><uri>{uri}</uri><pose>{x} {y} {float(z) + lift:.6g} {r} {p} {yaw}</pose></include>\n'
               + inc)
s = s.replace('</world>', inc + '  </world>')
open(dst, 'w').write(s)
PY
  GZ_ARGS="--verbose=2 -r -s"
  [ "$HR" = 1 ] && GZ_ARGS="$GZ_ARGS --headless-rendering"
  [ "$ENGINE" != ogre2 ] && GZ_ARGS="$GZ_ARGS --render-engine $ENGINE"
  echo "gz sim $GZ_ARGS $RUN/world.sdf" >> $OUT/config.txt
  setsid gz sim $GZ_ARGS $RUN/world.sdf > $OUT/gz.log 2>&1 < /dev/null &
  echo $! > $RUN/gz.pid
  for i in $(seq 60); do
    gz service -i --service /world/default/scene/info 2>/dev/null | grep -q "Service providers" && break
    sleep 1
  done
  [ -n "${SPEED:-}" ] && gz service -s /world/default/set_physics --reqtype gz.msgs.Physics --reptype gz.msgs.Boolean \
      --timeout 5000 --req "real_time_factor: $SPEED" >> $OUT/config.txt 2>&1
  PX4_GZ_STANDALONE=1 PX4_SYS_AUTOSTART=$AUTOSTART PX4_GZ_MODEL_NAME=${MODEL}_0 PX4_GZ_WORLD=default \
    setsid $B/bin/px4 -d > $OUT/px4.log 2>&1 < /dev/null &
  echo $! > $RUN/px4.pid
fi

# wait until PX4 has finished its startup script
for i in $(seq 120); do
  grep -q "Startup script returned successfully" $OUT/px4.log 2>/dev/null && break
  if grep -qE "ERROR \[init\]|Startup script returned with return value" $OUT/px4.log 2>/dev/null; then break; fi
  sleep 1
done
echo "startup: $(grep -E 'Startup script|ERROR \[init\]' $OUT/px4.log | head -3 | tr '\n' ' ') after ${i}s"
