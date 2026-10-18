#!/usr/bin/env bash
# gpu_and_parity_check.sh - after setup_wsl_ubuntu2404.sh: is Gazebo really rendering on the GPU,
# how fast is the trial scene, and does the installed software equal the Mac VM?
#
# SIMULATOR ONLY. No MAVROS, no proxy, no parameter writes, no commands of any kind. PX4 SITL is
# started only inside the RTF probe, exactly like parallel_work/20261015/integration/rtf_probe_01.
# Runs are strictly one after another; every run folder is kept (also failed ones).
#
#   bash gpu_and_parity_check.sh gpu                 nvidia-smi, glxinfo -B, eglinfo -B, /dev nodes (seconds)
#   bash gpu_and_parity_check.sh render [MODES]      Gazebo camera scene per mode: waits for the first camera
#                                                    frame (cold shader cache, up to 120 s, time recorded), then
#                                                    12 s of frame rate; which GL renderer the gz server really
#                                                    used (~1-2.5 min per mode)
#   bash gpu_and_parity_check.sh probe [MODES]       RTF probe: rtf_probe_01/run.sh UNCHANGED (trial world,
#                                                    model 4030, camera + vision chain, 60 s GUI on + 60 s GUI
#                                                    paused) with a WSLg viewer instead of the Mac noVNC one
#                                                    (~4 min per mode)
#   bash gpu_and_parity_check.sh versions            compare installed versions with vm_inventory (seconds)
#   bash gpu_and_parity_check.sh isolation           check_isolation.py with the one known PC difference
#   bash gpu_and_parity_check.sh ulog-params A.ulg B.ulg   compare all PX4 parameters of two ULogs
#                                                    (e.g. Mac INT_flight_preflight_05 vs the first PC preflight)
#   bash gpu_and_parity_check.sh all                 gpu + versions + render + probe (~20-30 min:
#                                                    Claude must use run_in_background and poll the log)
#
# MODES (default: hr1 hr0 sw; render also tries hr1_d3d12; sw6 only when asked for):
#   hr1        gz sim --headless-rendering (EGL, no X) = run_sim default HR=1. On WSL this may silently
#              fall back to the CPU renderer llvmpipe because the GPU is /dev/dxg, not a DRM node.
#   hr0        HR=0 + DISPLAY=:0: GLX on WSLg -> Mesa d3d12 -> NVIDIA (expected GPU path)
#   sw         HR=1 + LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe: the SAME renderer TYPE as the Mac VM
#              (control experiment; also the parity fallback). NOTE: llvmpipe uses every CPU of the PC (the
#              trial scripts never set LP_NUM_THREADS); the Mac VM had 6 vCPU, so 'sw' here is faster than the Mac.
#   sw6        like sw + LP_NUM_THREADS=6: the closer Mac-like control (optional, not in the defaults; whether the
#              variable reached the gz server is recorded in server_env.txt of the probe)
#   hr1_d3d12  HR=1 + GALLIUM_DRIVER=d3d12 (diagnostic only: does EGL headless reach the GPU when forced?)
#
# render and probe refuse to run unless the WSL networking mode is 'nat' (PX4 SITL binds UDP to 0.0.0.0; in
# 'mirrored' mode those ports are shared with Windows and the local network).
#
# Results: /work/pc_inventory_<date>/{gpu_*,render_*,probe_*,parity_*}; probe runs in /work/sim/runs/RTF_probe_pc_*.
# Places that could not be checked from the Mac are marked "TODO-VERIFY".

set -uo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="$(dirname "$SCRIPT_PATH")"
HANDOVER="$(dirname "$HERE")"
INV="$HANDOVER/vm_inventory"
readonly WORK=/work
readonly NVSMI=/usr/lib/wsl/lib/nvidia-smi
readonly CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
readonly PROBE="$WORK/parallel_work/20261015/integration/rtf_probe_01/run.sh"
readonly MAC_PROBE="$WORK/sim/runs/RTF_probe_20261017_02"     # Mac reference: GUI on 0.29, paused 0.50
readonly PX4_OF_COMMIT_EXPECTED=8758bd5567aadf2f8ab5deee97701d2c495d0756   # = the VM build (vm_inventory/px4_opticalflow_commit.txt)
# gz-rendering writes the OGRE 2 log here (TODO-VERIFY the exact path on Harmonic; the others are fallbacks).
OGRE_LOG_CANDIDATES=("$HOME/.gz/rendering/ogre2.log" "$HOME/.gz/ogre2.log" "$HOME/.ignition/rendering/ogre2.log")

log() { echo "[check $(date +%H:%M:%S)] $*"; }
warn() { echo "[check $(date +%H:%M:%S)] WARNING: $*" >&2; }
die() { echo "[check $(date +%H:%M:%S)] ERROR: $*" >&2; exit 1; }
ts() { date +%Y%m%d_%H%M%S; }

[ "$(id -u)" != 0 ] || die "run as the normal user, not with sudo"
USER="${USER:-$(id -un)}"; HOME="${HOME:-$(getent passwd "$(id -un)" | cut -d: -f6)}"

pc_inv() {
  [ -d "$WORK" ] || die "$WORK missing (setup not done)"
  local p
  if [ -f "$WORK/.pc_inventory_dir" ]; then p="$(cat "$WORK/.pc_inventory_dir")"
  else p="$WORK/pc_inventory_$(date +%Y%m%d)"; echo "$p" > "$WORK/.pc_inventory_dir"; fi
  mkdir -p "$p"; echo "$p"
}

gpu_env_vars() { # extra exports found necessary by the setup (e.g. MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA)
  local f; f="$(pc_inv)/gpu_env.sh"
  [ -f "$f" ] && sed -n 's/^export \([A-Za-z_][A-Za-z0-9_]*=[^ ]*\)$/\1/p' "$f"
  true
}

mode_vars() { # prints VAR=value words for a mode (one per line)
  case "$1" in
    hr1) echo HR=1; gpu_env_vars ;;
    hr0) echo HR=0; echo DISPLAY=:0; echo QT_QPA_PLATFORM=xcb; gpu_env_vars ;;
    sw) echo HR=1; echo LIBGL_ALWAYS_SOFTWARE=1; echo GALLIUM_DRIVER=llvmpipe ;;
    sw6) echo HR=1; echo LIBGL_ALWAYS_SOFTWARE=1; echo GALLIUM_DRIVER=llvmpipe; echo LP_NUM_THREADS=6 ;;
    hr1_d3d12) echo HR=1; echo GALLIUM_DRIVER=d3d12; gpu_env_vars ;;
    *) die "unknown mode '$1' (hr1 hr0 sw sw6 hr1_d3d12)" ;;
  esac
}

base_env() { echo "HOME=$HOME"; echo "USER=$USER"; echo "LOGNAME=$USER"; echo "SHELL=/bin/bash"; echo "PATH=$CLEAN_PATH"; echo "LANG=C.UTF-8"; echo "TERM=dumb"; }

ogre_log() { # newest existing OGRE log
  local f best="" bt=0 t
  for f in "${OGRE_LOG_CANDIDATES[@]}"; do
    [ -f "$f" ] || continue
    t="$(stat -c %Y "$f")"; if [ "$t" -gt "$bt" ]; then bt=$t; best=$f; fi
  done
  echo "$best"
}

renderer_from_log() { # file -> one line: classification | GL lines
  local f=$1 lines cls
  [ -f "$f" ] || { echo "unknown | no OGRE log found"; return; }
  # TODO-VERIFY: OGRE-Next GL3+ prints "GL_RENDERER = ..." lines; otherwise fall back to keywords.
  lines="$(grep -m3 -E 'GL_(RENDERER|VENDOR|VERSION)' "$f" | tr -s ' ' | tr '\n' ';')"
  [ -n "$lines" ] || lines="$(grep -m3 -iE 'llvmpipe|softpipe|d3d12|nvidia|renderer' "$f" | tr -s ' ' | tr '\n' ';')"
  if echo "$lines" | grep -qi 'llvmpipe\|softpipe'; then cls="SOFTWARE (llvmpipe)"
  elif echo "$lines" | grep -qi 'd3d12' && echo "$lines" | grep -qi 'nvidia'; then cls="GPU (D3D12 NVIDIA)"
  elif echo "$lines" | grep -qi 'nvidia'; then cls="GPU? (NVIDIA, check)"
  else cls="unknown"; fi
  echo "$cls | ${lines:-no GL lines in $f}"
}

# Loopback-only rule: the WSL networking mode must be NAT (see the header). TODO-VERIFY: wslinfo output format.
require_nat() {
  local m=""
  if command -v wslinfo >/dev/null 2>&1; then m="$(wslinfo --networking-mode 2>/dev/null | tr -d '\r[:space:]')"; fi
  [ "$m" = nat ] || need_owner "WSL networking mode is '${m:-unknown}', must be 'nat' (mirrored mode shares the simulator's UDP
ports with Windows and the local network). Owner decision: networkingMode=nat (or no such line) in %UserProfile%\\.wslconfig,
then wsl --shutdown; if wslinfo is missing: wsl --update. Nothing was started."
  log "WSL networking mode: nat"
}

no_sim_running() {
  if pgrep -x px4 >/dev/null || pgrep -x mavros_node >/dev/null; then die "PX4 or MAVROS is running: runs are strictly one at a time. Stop it with bash /work/sim/stop_sim.sh (or exact PIDs)"; fi
  local p
  for p in $(pgrep -x gz) $(pgrep -x ruby); do
    if tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qE '^GZ_PARTITION=(bbtrial|bbgpucheck)$'; then
      die "a Gazebo process of the trial/check (pid $p) is still running: bash /work/sim/stop_sim.sh, or kill that exact PID"
    fi
  done
}

stop_group() { # exact process group started with setsid; never pkill -f
  local g=$1
  [ -n "$g" ] || return 0
  kill -INT -- "-$g" 2>/dev/null; sleep 2
  kill -TERM -- "-$g" 2>/dev/null; sleep 1
  kill -KILL -- "-$g" 2>/dev/null
  return 0
}

# ------------------------------------------------------------------ gpu
cmd_gpu() {
  local out; out="$(pc_inv)/gpu_$(ts)"; mkdir -p "$out"
  { uname -a; echo; ls -l /dev/dxg /dev/dri 2>&1; echo; ls /usr/lib/wsl/lib 2>&1; } > "$out/host.txt"
  "$NVSMI" > "$out/nvidia_smi.txt" 2>&1
  "$NVSMI" --query-gpu=name,driver_version,memory.total,pstate,clocks.max.gr --format=csv >> "$out/nvidia_smi.txt" 2>&1
  env DISPLAY=:0 glxinfo -B > "$out/glxinfo_B.txt" 2>&1
  eglinfo -B > "$out/eglinfo_B.txt" 2>&1 || true        # TODO-VERIFY: eglinfo present in mesa-utils on noble
  env LIBGL_ALWAYS_SOFTWARE=1 DISPLAY=:0 glxinfo -B > "$out/glxinfo_B_software.txt" 2>&1
  dpkg-query -W libgl1-mesa-dri libegl-mesa0 mesa-utils > "$out/mesa_versions.txt" 2>&1
  local r; r="$(grep -m1 'OpenGL renderer string' "$out/glxinfo_B.txt")"
  log "GLX (WSLg, default):  $r"
  log "GLX (forced software): $(grep -m1 'OpenGL renderer string' "$out/glxinfo_B_software.txt")"
  log "EGL platforms/devices (eglinfo -B), first renderer lines:"
  grep -iE 'platform|renderer' "$out/eglinfo_B.txt" | head -12 | sed 's/^/    /'
  "$NVSMI" -L
  if echo "$r" | grep -q D3D12 && echo "$r" | grep -q NVIDIA; then log "GPU check: OK (OpenGL on the NVIDIA GPU through d3d12)"
  else warn "GPU check: OpenGL is NOT on the NVIDIA GPU: $r"; return 1; fi
  log "saved in $out"
}

# ------------------------------------------------------------------ render
write_check_world() { # minimal scene: ground, box, light, one 640x480 camera at 30 Hz
  cat > "$1" <<'EOF'
<?xml version="1.0"?>
<sdf version="1.9">
  <world name="bbgpucheck">
    <physics name="default" type="ignored"><max_step_size>0.004</max_step_size><real_time_factor>1.0</real_time_factor></physics>
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <light type="directional" name="sun"><cast_shadows>true</cast_shadows><pose>0 0 10 0 0 0</pose>
      <diffuse>1 1 1 1</diffuse><specular>0.2 0.2 0.2 1</specular><direction>-0.5 0.1 -0.9</direction></light>
    <model name="ground"><static>true</static><link name="l"><visual name="v"><geometry><plane><normal>0 0 1</normal><size>20 20</size></plane></geometry>
      <material><ambient>0.6 0.6 0.6 1</ambient><diffuse>0.6 0.6 0.6 1</diffuse></material></visual></link></model>
    <model name="box"><static>true</static><pose>2 0 0.5 0 0 0</pose><link name="l"><visual name="v"><geometry><box><size>1 1 1</size></box></geometry>
      <material><ambient>0.8 0.1 0.1 1</ambient><diffuse>0.8 0.1 0.1 1</diffuse></material></visual></link></model>
    <model name="cam"><static>true</static><pose>0 0 1 0 0.3 0</pose>
      <link name="l"><sensor name="camera" type="camera"><topic>bbgpucheck/camera</topic><update_rate>30</update_rate><always_on>1</always_on>
        <camera><horizontal_fov>1.2</horizontal_fov><image><width>640</width><height>480</height></image><clip><near>0.1</near><far>50</far></clip></camera>
      </sensor></link></model>
  </world>
</sdf>
EOF
}

count_frames_py() { cat <<'PY'
# argv: first_frame_timeout_s measure_s server_start_epoch
# The first ogre2 start on d3d12 compiles shaders with a cold cache: wait for the FIRST camera frame (and record
# how long it took), warm up 2 s more, and only then measure. No frame within the timeout = 'frames': 0.
import json, sys, threading, time
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image
from gz.msgs10.world_stats_pb2 import WorldStatistics
timeout, secs, srv_start = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
lock = threading.Lock(); frames = []; stats = []; first = []
def on_img(m):
    now, d = time.monotonic(), m.data[::97]
    with lock:
        if not first: first.append(time.time())
        frames.append((now, m.width, m.height, sum(d) / max(1, len(d))))
def on_stats(m):
    with lock: stats.append((time.monotonic(), m.sim_time.sec + m.sim_time.nsec * 1e-9))
n = Node()
assert n.subscribe(Image, '/bbgpucheck/camera', on_img), 'cannot subscribe camera'
assert n.subscribe(WorldStatistics, '/world/bbgpucheck/stats', on_stats), 'cannot subscribe stats'
t0 = time.monotonic()
while time.monotonic() - t0 < timeout:
    with lock:
        if first: break
    time.sleep(0.2)
with lock: first_s = round(first[0] - srv_start, 1) if first else None
if first_s is None:
    print(json.dumps({'frames': 0, 'first_frame_s': None, 'first_frame_timeout_s': timeout, 'camera_hz': 0.0, 'rtf': None}))
    sys.exit(0)
time.sleep(2.0)
with lock: frames.clear(); stats.clear()
time.sleep(secs)
with lock: f, s = list(frames), list(stats)
fps = (len(f) - 1) / (f[-1][0] - f[0][0]) if len(f) > 1 and f[-1][0] > f[0][0] else 0.0
rtf = (s[-1][1] - s[0][1]) / (s[-1][0] - s[0][0]) if len(s) > 1 and s[-1][0] > s[0][0] else None
print(json.dumps({'first_frame_s': first_s, 'frames': len(f), 'camera_hz': round(fps, 2),
                  'size': [f[-1][1], f[-1][2]] if f else None,
                  'mean_pixel_sample': round(f[-1][3], 1) if f else None, 'rtf': round(rtf, 3) if rtf else None}))
PY
}

check_modes() { local m; for m in "$@"; do mode_vars "$m" > /dev/null; done; }

cmd_render() {
  local modes=("$@"); [ "${#modes[@]}" -gt 0 ] || modes=(hr1 hr0 sw hr1_d3d12)
  check_modes "${modes[@]}"
  require_nat
  no_sim_running
  local out; out="$(pc_inv)/render_$(ts)"; mkdir -p "$out"
  write_check_world "$out/world.sdf"
  count_frames_py > "$out/count_frames.py"
  local m summary="$out/SUMMARY.txt"
  printf '%-10s | %-22s | %s\n' mode renderer "first frame after start (s) / camera Hz / RTF (12 s after warm-up)" > "$summary"
  for m in "${modes[@]}"; do
    local d="$out/$m" vars=() args=(-s -r --verbose=3) start gpid
    mkdir -p "$d"
    mapfile -t vars < <(base_env; mode_vars "$m"; echo GZ_PARTITION=bbgpucheck; echo GZ_IP=127.0.0.1)
    printf '%s\n' "${vars[@]}" > "$d/env.txt"
    printf '%s\n' "${vars[@]}" | grep -qx HR=1 && args+=(--headless-rendering)
    log "render check $m: gz sim ${args[*]} (env: $(printf '%s ' "${vars[@]}" | grep -oE '(HR|DISPLAY|LIBGL_ALWAYS_SOFTWARE|GALLIUM_DRIVER|LP_NUM_THREADS|MESA_[A-Z_]+)=[^ ]*' | tr '\n' ' '))"
    start="$(date +%s)"
    setsid env -i "${vars[@]}" gz sim "${args[@]}" "$out/world.sdf" > "$d/gz.log" 2>&1 < /dev/null &
    gpid=$!
    sleep 1
    env -i "${vars[@]}" /usr/bin/python3 -I "$out/count_frames.py" 120 12 "$start" > "$d/frames.json" 2> "$d/frames.err"
    local ol; ol="$(ogre_log)"
    if [ -n "$ol" ] && [ "$(stat -c %Y "$ol")" -ge "$start" ]; then cp "$ol" "$d/ogre2.log"; fi
    stop_group "$gpid"
    local rend; rend="$(renderer_from_log "$d/ogre2.log")"
    printf '%-10s | %-22s | %s\n' "$m" "${rend%% |*}" "$(cat "$d/frames.json" 2>/dev/null || echo 'no frames')" >> "$summary"
    echo "  $m: $rend" >> "$out/GL_LINES.txt"
    grep -iE 'error|\[err\]' "$d/gz.log" | head -5 > "$d/gz_errors.txt"
  done
  cat "$summary"
  log "details: $out (GL lines: $out/GL_LINES.txt)"
}

# ------------------------------------------------------------------ probe
# WSLg replacement of the Mac viewer (sim/viewer_attach.sh: Xvfb :1 + noVNC, pkill -f): follows the
# trial server, starts `gz sim -g` on DISPLAY=:0 with the server's gz-transport settings, records the
# GUI's exact process group, and closes ONLY that group while /work/sim/run/MEASURING exists.
viewer_helper() {
  local mode=$1 side=$2 last="" gpid="" srv envs=() gui_started=0 copied_gui=0 t0
  local gui_vars=(DISPLAY=:0 QT_QPA_PLATFORM=xcb)
  if [ "$mode" = sw ] || [ "$mode" = sw6 ]; then gui_vars+=(LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe)
    [ "$mode" = sw6 ] && gui_vars+=(LP_NUM_THREADS=6)
  else local v; while read -r v; do [ -n "$v" ] && gui_vars+=("$v"); done < <(gpu_env_vars); fi
  [ -n "${XDG_RUNTIME_DIR:-}" ] && gui_vars+=("XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR")
  while [ ! -e "$side/stop" ]; do
    if [ -e /work/sim/run/MEASURING ]; then
      if [ -n "$gpid" ]; then stop_group "$gpid"; echo "$(date +%T) MEASURING: GUI group $gpid closed" >> "$side/viewer.log"; gpid=""; fi
      sleep 1; continue
    fi
    srv="$(cat /work/sim/run/gz.pid 2>/dev/null || true)"
    if [ -n "$srv" ] && [ "$srv" != "$last" ] && tr '\0' '\n' < "/proc/$srv/environ" 2>/dev/null | grep -qx 'GZ_PARTITION=bbtrial'; then
      last=$srv; t0="$(date +%s)"
      echo "$(date +%T) server $srv found" >> "$side/viewer.log"
      # Evidence of what really reached the gz server (renderer variables are not written to config.txt).
      tr '\0' '\n' < "/proc/$srv/environ" 2>/dev/null \
        | grep -E '^(HR|DISPLAY|QT_QPA_PLATFORM|LIBGL_ALWAYS_SOFTWARE|GALLIUM_DRIVER|LP_NUM_THREADS|MESA_[A-Z0-9_]+|GZ_PARTITION|GZ_IP)=' \
        > "$side/server_env.txt" || true
      # Let the server create its own render engine first and keep its OGRE log (the GUI rewrites it).
      local i ol
      for i in $(seq 40); do
        ol="$(ogre_log)"
        if [ -n "$ol" ] && [ "$(stat -c %Y "$ol")" -ge "$t0" ] && grep -q 'GL_RENDERER\|RenderSystem' "$ol"; then break; fi
        sleep 1
      done
      ol="$(ogre_log)"; [ -n "$ol" ] && cp "$ol" "$side/ogre2_server.log"
      mapfile -t envs < <(tr '\0' '\n' < "/proc/$srv/environ" | grep -E '^GZ_(PARTITION|IP|SIM_RESOURCE_PATH|SIM_SYSTEM_PLUGIN_PATH)=')
      setsid env -i "HOME=$HOME" "USER=$USER" "PATH=$CLEAN_PATH" LANG=C.UTF-8 "${envs[@]}" "${gui_vars[@]}" gz sim -g \
        > "$side/gui.log" 2>&1 < /dev/null &
      gpid=$!; gui_started="$(date +%s)"; copied_gui=0
      echo "$(date +%T) GUI started, group $gpid, env: ${gui_vars[*]}" >> "$side/viewer.log"
    fi
    if [ -n "$gpid" ] && [ "$copied_gui" = 0 ] && [ $(( $(date +%s) - gui_started )) -ge 20 ]; then
      ol="$(ogre_log)"; [ -n "$ol" ] && cp "$ol" "$side/ogre2_gui.log"; copied_gui=1
    fi
    sleep 1
  done
  [ -n "$gpid" ] && stop_group "$gpid"
  return 0
}

summary_line() { # run_dir label -> "rtf_total / 5s_min"
  python3 -I - "$1/summary_$2.json" <<'PY' 2>/dev/null || echo "-"
import json, sys
r = json.loads(open(sys.argv[1]).read().strip().splitlines()[-1])
f = lambda x: '-' if x is None else '%.3f' % x
print(f"{f(r.get('rtf_total'))} (5 s min {f(r.get('rtf_5s_min'))}, {r.get('messages')} msgs)")
PY
}

cmd_probe() {
  local modes=("$@"); [ "${#modes[@]}" -gt 0 ] || modes=(hr1 hr0 sw)
  check_modes "${modes[@]}"
  require_nat
  [ -f "$PROBE" ] || die "missing $PROBE (restore not done?)"
  [ -x "$WORK/sim/ros_stack/.venv/bin/python" ] || die "ros_stack venv missing (setup step u05_venvs)"
  [ -x "$HOME/PX4-Autopilot/build/px4_sitl_default/bin/px4" ] || die "PX4 SITL not built (setup step u06_px4)"
  [ -f "$WORK/ws_package1b/install/local_setup.bash" ] || die "ws_package1b is not built on this PC (rtf_probe_01/run.sh sources its install; setup step u09_ws_package1b)"
  local inv sum; inv="$(pc_inv)"; sum="$inv/probe_summary_$(ts).md"
  {
    echo "# RTF probe on the PC ($(date -Is))"
    echo
    echo "Same scene as rtf_probe_01 (world + model 4030 + FLOOR=2 + ARUCO=1 + GST=0 + camera/vision chain, no MAVROS)."
    echo "Mac reference ($MAC_PROBE, 6 vCPU llvmpipe): GUI on $(summary_line "$MAC_PROBE" gui_on); paused $(summary_line "$MAC_PROBE" gui_paused)"
    echo "Trial gate: RTF >= 0.20 on every 10 s window of the guarded phase."
    echo "This PC: $(getconf _NPROCESSORS_ONLN) CPUs. 'sw' (llvmpipe) uses all of them; the Mac VM had 6 vCPU, so 'sw' is the same renderer TYPE"
    echo "but not the same CPU budget ('sw6' = LP_NUM_THREADS=6 is the closer control). nproc in rtf_probe_01's host.txt is limited by"
    echo "OMP_NUM_THREADS and is NOT the CPU count."
    echo
    echo "| tag | mode | server renderer | GUI renderer | RTF GUI on | RTF GUI paused | result |"
    echo "|---|---|---|---|---|---|---|"
  } > "$sum"
  local m n tag side rc OUT hpid npid vars
  for m in "${modes[@]}"; do
    no_sim_running
    n=1; while :; do tag="RTF_probe_pc_$(date +%Y%m%d)_$(printf %02d "$n")_$m"; [ -e "$WORK/sim/runs/$tag" ] || break; n=$((n + 1)); done
    side="$inv/probes/$tag"; mkdir -p "$side"; OUT="$WORK/sim/runs/$tag"
    mapfile -t vars < <(base_env; mode_vars "$m")
    printf '%s\n' "${vars[@]}" > "$side/env.txt"
    log "probe $tag (mode $m): about 4 minutes; GUI on DISPLAY=:0 during the first 60 s window, closed for the second"
    "$NVSMI" --query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,clocks.gr,power.draw --format=csv -l 2 > "$side/nvidia_smi.csv" 2>&1 &
    npid=$!
    viewer_helper "$m" "$side" &
    hpid=$!
    ( cd "$WORK" && env -i "${vars[@]}" TAG="$tag" bash "$PROBE" ) > "$side/probe_stdout.log" 2>&1
    rc=$?
    touch "$side/stop"
    for _ in $(seq 15); do kill -0 "$hpid" 2>/dev/null || break; sleep 1; done
    kill "$hpid" 2>/dev/null; kill "$npid" 2>/dev/null
    wait "$hpid" 2>/dev/null; wait "$npid" 2>/dev/null
    { uptime; free -g; } > "$side/host_after.txt"
    if [ -d "$OUT" ]; then mkdir -p "$OUT/pc_sidecar"; cp -a "$side/." "$OUT/pc_sidecar/"; fi
    local rs rg; rs="$(renderer_from_log "$side/ogre2_server.log")"; rg="$(renderer_from_log "$side/ogre2_gui.log")"
    printf '| %s | %s | %s | %s | %s | %s | %s |\n' "$tag" "$m" "${rs%% |*}" "${rg%% |*}" \
      "$(summary_line "$OUT" gui_on)" "$(summary_line "$OUT" gui_paused)" "$([ "$rc" = 0 ] && echo ok || echo "FAILED rc=$rc (kept)")" >> "$sum"
    echo "  $tag server: $rs" >> "$sum.gl_lines"; echo "  $tag gui: $rg" >> "$sum.gl_lines"
    [ "$rc" = 0 ] || warn "probe $tag failed (rc $rc): run folder kept; see $side/probe_stdout.log and $OUT/start.log"
  done
  {
    echo
    echo "GL lines: $sum.gl_lines"
    echo
    echo "Reading: the GPU helps only if the server renderer says GPU. 'sw' is the Mac-like control: if 'sw' here is"
    echo "already far above 0.20, a Mac-equal renderer is affordable on this PC. Choose the acceptance renderer"
    echo "(owner decision), record it, and keep it the same for every acceptance run."
  } >> "$sum"
  cat "$sum"
}

# ------------------------------------------------------------------ versions
cmd_versions() {
  local inv out; inv="$(pc_inv)"; out="$inv/parity_versions_$(ts).txt"
  dpkg-query -W -f '${Package}\t${Version}\t${Architecture}\n' | sort > "$inv/dpkg_all_now.tsv"
  local px4="$HOME/PX4-Autopilot" ofc=""
  ofc="$(git -C "$px4/build/px4_sitl_default/OpticalFlow/src/OpticalFlow" rev-parse HEAD 2>/dev/null || true)"
  {
    python3 -I - "$INV" "$inv/dpkg_all_now.tsv" <<'PY'
import sys, re
from pathlib import Path
inv, pc_tsv = Path(sys.argv[1]), Path(sys.argv[2])
def read(p):
    d = {}
    for line in Path(p).read_text().splitlines():
        parts = line.split('\t')
        if len(parts) >= 2: d[parts[0]] = parts[1]
    return d
vm_rel, vm_all, pc = read(inv / 'dpkg_relevant.tsv'), read(inv / 'dpkg_all.tsv'), read(pc_tsv)
def norm(name, v):
    # ROS build stamps differ per architecture: compare upstream version + debian revision up to "noble".
    if name.startswith('ros-jazzy-'):
        m = re.match(r'^(.*?noble)', v); return m.group(1) if m else v
    return v
expected_missing = {'ros2-apt-source', 'fluxbox', 'x11vnc', 'novnc', 'websockify', 'python3-novnc', 'python3-websockify'}
same, diff, missing = [], [], []
for name, v in sorted(vm_rel.items()):
    if name not in pc: missing.append(name); continue
    (same if norm(name, v) == norm(name, pc[name]) else diff).append((name, v, pc[name]))
print('== dpkg: VM relevant packages (vm_inventory/dpkg_relevant.tsv) vs this PC')
print(f'equal {len(same)}, different {len(diff)}, missing {len(missing)} (of {len(vm_rel)})')
for n, a, b in diff: print(f'  DIFF    {n}: VM {a} | PC {b}')
for n in missing: print(f'  MISSING {n}' + ('   (expected: not used on the PC)' if n in expected_missing else ''))
pat = re.compile(r'^(ros-jazzy-|gz-|libgz|python3-gz|libogre|libsdformat|python3-sdformat|mesa|libgl1-mesa|libegl-mesa|libglx-mesa|python3-numpy$|libopencv-dev$|python3-opencv$)')
others = sorted(n for n in pc if pat.match(n) and n not in vm_rel)
extra = [n for n in others if n not in vm_all]
diff2 = [(n, vm_all[n], pc[n]) for n in others if n in vm_all and norm(n, vm_all[n]) != norm(n, pc[n])]
print(f'== ROS/Gazebo/Mesa/OpenCV packages outside the relevant list: {len(extra)} only on the PC, {len(diff2)} with another version than in the VM')
for n in extra: print(f'  EXTRA   {n} {pc[n]}')
for n, a, b in diff2: print(f'  DIFF    {n}: VM {a} | PC {b}')
real = diff + diff2 + [(m,) for m in missing if m not in expected_missing]
print(f'== SUMMARY dpkg: {len(real)} difference(s) to explain' )
PY
    echo
    echo "== gz sim --versions: PC $(gz sim --versions 2>/dev/null | head -1) | VM $(head -1 "$INV/gz_versions.txt")"
    echo "== PX4: HEAD $(git -C "$px4" rev-parse HEAD 2>/dev/null) (VM $(sed -n 2p "$INV/px4_git.txt"))"
    if [ -d "$px4/.git" ]; then
      local vm pc
      vm="$(grep -E '^[ +U-]?[0-9a-f]{40} ' "$INV/px4_git.txt" | sed -E 's/^[ +U-]?([0-9a-f]{40}) ([^ ]+).*/\1 \2/' | sort)"
      pc="$(git -C "$px4" submodule status --recursive | sed -E 's/^[ +U-]?([0-9a-f]{40}) ([^ ]+).*/\1 \2/' | sort)"
      if [ "$vm" = "$pc" ]; then echo "   submodules: equal to the VM ($(echo "$pc" | wc -l))"; else echo "   submodules: DIFFERENT"; diff <(echo "$vm") <(echo "$pc"); fi
      echo "   local changes: $(git -C "$px4" status --porcelain | tr '\n' ';')"
      echo "   VM local changes: $(grep -E '^( M|\?\?) ' "$INV/px4_git.txt" | tr '\n' ';')"
    fi
    echo "== PX4-OpticalFlow in the build: ${ofc:-none} (expected $PX4_OF_COMMIT_EXPECTED = VM build)$([ "$ofc" = "$PX4_OF_COMMIT_EXPECTED" ] && echo ' OK' || echo ' DIFFERENT')"
    echo
    echo "== pip freeze vs the VM"
    python3 -I - "$INV" "$HOME" "$WORK" <<'PY'
import subprocess, sys
from pathlib import Path
inv, home, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
def freeze(py):
    try: out = subprocess.run([str(py), '-m', 'pip', 'freeze', '--disable-pip-version-check'], capture_output=True, text=True, timeout=120).stdout
    except Exception as e: return None
    return {l.split('==')[0].lower().replace('_', '-'): l.split('==')[1] for l in out.splitlines() if '==' in l}
def vmfile(p):
    d = {}
    for l in Path(p).read_text().splitlines():
        if '==' in l: d[l.split('==')[0].lower().replace('_', '-')] = l.split('==')[1]
    return d
def compare(label, pcd, vmd, only=None):
    if pcd is None: print(f'{label}: venv missing'); return
    keys = sorted(set(vmd) | set(pcd)) if only is None else sorted(only)
    diffs = [(k, vmd.get(k), pcd.get(k)) for k in keys if vmd.get(k) != pcd.get(k)]
    print(f'{label}: {len(keys) - len(diffs)} equal, {len(diffs)} different')
    for k, a, b in diffs: print(f'   {k}: VM {a} | PC {b}')
vm_px4 = sorted(inv.glob('pip__home_*px4-venv.txt'))
compare('px4-venv (all, incl. system site)', freeze(home / 'px4-venv/bin/python'), vmfile(vm_px4[0]) if vm_px4 else {})
compare('ros_stack .venv (all, incl. system site)', freeze(work / 'sim/ros_stack/.venv/bin/python'), vmfile(inv / 'pip__work_sim_ros_stack_.venv.txt'))
compare('system python3', freeze(Path('/usr/bin/python3')), vmfile(inv / 'pip_system_python3.txt'))
mac = {  # recorded on the Mac 17.10 (vm_inventory only has their pyvenv.cfg)
 'analysis/layout/.venv': {'contourpy': '1.3.0', 'cycler': '0.12.1', 'fonttools': '4.60.2', 'importlib-resources': '6.5.2', 'kiwisolver': '1.4.7',
   'matplotlib': '3.9.4', 'numpy': '2.0.2', 'packaging': '26.3', 'pillow': '11.3.0', 'pyparsing': '3.3.3', 'python-dateutil': '2.9.0.post0', 'six': '1.17.0', 'zipp': '3.23.1'},
 'parallel_work/20261015/vision/.venv': {'numpy': '1.26.4', 'opencv-contrib-python-headless': '4.10.0.84'},
 'sim/worlds/aruco_map/.venv': {'numpy': '2.0.2', 'opencv-contrib-python-headless': '5.0.0.93'}}
for rel, want in mac.items():
    compare(rel + ' (former Mac venv; Python 3.9.6 -> 3.12 is expected)', freeze(work / rel / 'bin/python'), want)
PY
    echo
    echo "== check_isolation.py"
    cmd_isolation 2>&1
  } 2>&1 | tee "$out"
  log "saved $out"
}

cmd_isolation() {
  local inv; inv="$(pc_inv)"
  (cd "$WORK" && python3 -I -B parallel_work/20261015/integration/check_isolation.py) > "$inv/check_isolation_latest.json"
  python3 -I - "$inv/check_isolation_latest.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1])); errs = r.get('errors', [])
known = [e for e in errs if e.get('file') == 'ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard']
other = [e for e in errs if e not in known]
print(f"shared files {r.get('shared_files_checked')}, errors {len(errs)}: known PC difference (aarch64 simple_offboard pin) {len(known)}, unexpected {len(other)}")
for e in other: print('   UNEXPECTED', e)
print('   -> OK' if not other and r.get('shared_files_checked') == 187 else '   -> INVESTIGATE (never edit baseline_manifest.json)')
sys.exit(0 if not other else 1)
PY
}

# ------------------------------------------------------------------ ulog params
cmd_ulog_params() {
  [ "$#" = 2 ] || die "usage: $0 ulog-params A.ulg B.ulg"
  python3 -I - "$1" "$2" <<'PY'
import struct, sys
def read(path):
    d = open(path, 'rb').read()
    assert d[:7] == b'ULog\x01\x12\x35', f'{path}: not a ULog file'
    i, first, last, info = 16, {}, {}, {}
    while i + 3 <= len(d):
        size, typ = struct.unpack_from('<HB', d, i); i += 3
        body = d[i:i + size]; i += size
        t = chr(typ)
        if t not in ('P', 'I') or not body: continue
        klen = body[0]; key = body[1:1 + klen].decode(errors='replace'); val = body[1 + klen:]
        if ' ' not in key: continue
        ty, name = key.split(' ', 1)
        if ty == 'int32_t': v = struct.unpack('<i', val[:4])[0]
        elif ty == 'float': v = struct.unpack('<f', val[:4])[0]
        elif ty.startswith('char['): v = val.decode(errors='replace')
        else: v = val.hex()
        if t == 'P':
            first.setdefault(name, v); last[name] = v
        else:
            info[name] = v
    return first, last, info
a, b = read(sys.argv[1]), read(sys.argv[2])
for k in ('ver_sw', 'ver_sw_release', 'sys_toolchain_ver', 'sys_name', 'sys_os_ver'):
    print(f'INFO {k}: A {a[2].get(k)} | B {b[2].get(k)}')
for label, x, y in (('initial', a[0], b[0]), ('final', a[1], b[1])):
    keys = sorted(set(x) | set(y))
    diffs = [(k, x.get(k), y.get(k)) for k in keys if x.get(k) != y.get(k)]
    print(f'== {label} parameter values: {len(keys)} names, {len(diffs)} different')
    for k, p, q in diffs: print(f'   {k}: A {p} | B {q}')
PY
}

cmd_all() {
  cmd_gpu || warn "GPU check did not confirm the NVIDIA GPU - continuing with the measurements (they show what is used)"
  cmd_versions
  cmd_render
  cmd_probe
  log "ALL DONE. Tell the owner the result in short simple Russian: which renderer, RTF numbers vs the Mac (0.29 / 0.50)."
}

main() {
  local cmd=${1:-}; [ "$#" -gt 0 ] && shift
  case "$cmd" in
    gpu) cmd_gpu ;;
    render) cmd_render "$@" ;;
    probe) cmd_probe "$@" ;;
    versions) cmd_versions ;;
    isolation) cmd_isolation ;;
    ulog-params) cmd_ulog_params "$@" ;;
    all) cmd_all ;;
    *) sed -n '2,/^$/p' "$SCRIPT_PATH"; exit 2 ;;
  esac
}

main "$@"
