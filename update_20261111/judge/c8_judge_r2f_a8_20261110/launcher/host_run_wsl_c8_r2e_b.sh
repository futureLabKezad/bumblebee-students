#!/bin/bash
# ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY). К дрону не подключается.
# host_run_wsl_c8_r2e_b.sh = launcher v35-c8-r2f-a8 (A8, T38 10.11.2026: runner = c8_judge_r2f_a8_20261110/executor, image r2f, airframe 4070; A7 was v34, A6 v33, b v32) (Claude, T28 09.11.2026): copy of c8_executor_20261109/launcher/host_run_wsl_c8_r2e.sh
#   for the C8 executor revision b /work/c8_judge_r2e_20261109/executor. Changes: ../DIFF_exec_b.md (v31 changes: c8_executor_20261109/DIFF_r2e.md).
#   bash host_run_wsl_c8_r2e_b.sh TAG SCENARIO [VIEW]      (no TRIAL argument: the runner is fixed; TRIAL lines below are v29 history)
#   env (c8): C8_START_ORDER=gz_first|px4_first REQUIRED (no default); C8_AIRFRAME C8_PX4_ETC C8_PRODUCT_INSTALL C8_PRODUCT_SRC
#             C8_MAVROS_INSTALL C8_MODEL C8_FLOW_PLUGIN (defaults below); the files they name must be in the frozen pins.
#   Refuses: SIM_LOCK not held by local_bc6f158c, < 8 GB free on C:, a used TAG (runs are never overwritten).
#     TAG       ^INT_flight_[a-zA-Z0-9_]+$, never reused
#     SCENARIO  preflight|land|kill|freeze|mavros_restart|pilot|cancel_before|cancel|ack_cancel|heartbeat|guard_hold|cleanup_hold
#     VIEW      paused (default: GUI closed while measuring) | on (owner watches Gazebo; same speed gate)
#     TRIAL     02 (default, original field) | 03 (field_measurements_01 field) | 05 (02 + supervisor fixes)
#               | 06 (05 + the field block of 03 = field preflight with the supervisor fixes)
#               | 07 (06 + VPE freshness installed before the diagnostic wrapper; for combined_04 only)
#               | 08 (07 + supervisor waits 45 s + read-only audit of unwritten contract names; for combined_06 only)
#   env: RENDER=hr1 (default = acceptance renderer, owner decision 19.10.2026: GPU d3d12) | hr0 | sw
#        KEEP_AWAKE=0 (default: the owner set Windows sleep to "never" himself, 19.10.2026) | 1 = SetThreadExecutionState
#        for this run only (bounded 1800 s, no setting changed).
#        CANCEL_OFFSET_MS (v7): only with SCENARIO=cancel, one of 0|50|200|500|900|950|980 (plan §8 п.6); passed to run.sh and
#        recorded; refused for any other scenario or value. Unset with cancel = the supervisor default 500 (recorded).
#        BB_COMBINED_ROOT and BB_FROZEN_PINS are REQUIRED (v4: no default candidate). The candidate must equal the frozen
#        pins: same manifest path and SHA, every candidate file, the runner of TRIAL pinned, every pinned repo file unchanged.
# Runs the UNCHANGED flight_trial_0X/run.sh in a clean environment (like `limactl shell` did on the Mac), then writes
# /work/sim/runs/TAG/host_check.json. A run is VALID only if host_check valid_host=true (Windows did not sleep - proven from
# the System log; WSL clock ok before/after and no CLOCK_REALTIME step during the run; the gz server rendered with the
# requested renderer) AND the executor's own gates AND the independent verifier pass.
# Never deletes anything; stops only exact process groups it started.
set -u
echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY): host_run_wsl_c8_r2e_b.sh v35-c8-r2f-a8; no real drone, no ssh"
TAG=${1:?TAG}; SCENARIO=${2:?SCENARIO}; VIEW=${3:-paused}; TRIAL=c8
[ $# -le 3 ] || { echo "host_run_wsl_c8: REFUSED: no TRIAL argument in v35-c8-r2f-a8 (the runner is fixed)" >&2; exit 2; }
RENDER=${RENDER:-hr1}; KEEP_AWAKE=${KEEP_AWAKE:-0}
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
WORK=/work
INTEG=$WORK/parallel_work/20261015/integration
RUNNER=$WORK/c8_judge_r2f_a8_20261110/executor/run.sh   # A8: the only runner of this launcher
OUT=$WORK/sim/runs/$TAG
SIDE=$WORK/sim/runs/$TAG.launcher
CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PS=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
CLOCK_CHECK=$HOME/bb_pc_setup_patched_20261019/pc_handover_20261017/setup/wsl_clock_check.py
PC_INV="$(cat $WORK/.pc_inventory_dir 2>/dev/null || echo $WORK/pc_inventory_20261019)"
GPU_ENV=$PC_INV/gpu_env.sh
COMBINED=${BB_COMBINED_ROOT:-}
PINS=${BB_FROZEN_PINS:-}
OGRE_LOGS=("$HOME/.gz/rendering/ogre2.log" "$HOME/.gz/ogre2.log")
die() { echo "host_run_wsl: REFUSED: $*" >&2; exit 2; }

# ---- refusals before anything starts (nothing is created yet)
[ "$(id -u)" != 0 ] || die "run as the normal WSL user, not root"
# global lock: only one launcher at a time (held until this process exits)
exec 9>/tmp/bb_host_run_wsl.lock
flock -n 9 || die "another host_run_wsl.sh is running (one run at a time)"
[[ "$TAG" =~ ^INT_flight_[a-zA-Z0-9_]+$ ]] || die "TAG must match ^INT_flight_[a-zA-Z0-9_]+$"
case "$SCENARIO" in preflight|land|kill|freeze|mavros_restart|pilot|cancel_before|cancel|ack_cancel|heartbeat|guard_hold|cleanup_hold) ;; *) die "bad SCENARIO";; esac
case "$VIEW" in paused|on) ;; *) die "VIEW must be paused or on";; esac
[ "$TRIAL" = c8 ] || die "TRIAL is fixed to c8"   # c8
case "$RENDER" in hr1|hr0|sw) ;; *) die "RENDER must be hr1, hr0 or sw";; esac
case "$KEEP_AWAKE" in 0|1) ;; *) die "KEEP_AWAKE must be 0 or 1";; esac
CANCEL_OFFSET=${CANCEL_OFFSET_MS-}
if [ -n "${CANCEL_OFFSET_MS+x}" ]; then
  [ "$SCENARIO" = cancel ] || die "CANCEL_OFFSET_MS is only for SCENARIO=cancel"
  case "$CANCEL_OFFSET" in 0|50|200|500|900|950|980) ;; *) die "CANCEL_OFFSET_MS must be 0, 50, 200, 500, 900, 950 or 980";; esac
fi
# ---- c8: target set (defaults = C8 set A8 of 10.11: airframe 4070 = 4061 + BAT1_SOURCE 0 + SDLOG_MODE 1, image r2f, T22 model_v1 + plugin_v1, MAVROS bp02)
C8_AIRFRAME=${C8_AIRFRAME:-4070}; C8_PX4_ETC=${C8_PX4_ETC:-/work/goal_step5b_20261109/px4_etc}
C8_PRODUCT_INSTALL=${C8_PRODUCT_INSTALL:-/work/fixed_image_r2f_20261110/install}; C8_PRODUCT_SRC=${C8_PRODUCT_SRC:-/work/fixed_image_r2f_20261110/src/bumblebee}
C8_MAVROS_INSTALL=${C8_MAVROS_INSTALL:-/work/ws_mavros214_bp02/install}
C8_MODEL=${C8_MODEL:-/work/goal_t22_flow_20261109/model_v1/bumblebee}; C8_FLOW_PLUGIN=${C8_FLOW_PLUGIN:-/work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so}
C8_START_ORDER=${C8_START_ORDER:-}
case "$C8_START_ORDER" in gz_first|px4_first) ;; *) die "C8_START_ORDER must be gz_first or px4_first (no default: README decision D4)";; esac
[[ "$C8_AIRFRAME" =~ ^[0-9]{4,5}$ ]] || die "C8_AIRFRAME must be an airframe number"
for v in C8_PX4_ETC C8_PRODUCT_INSTALL C8_PRODUCT_SRC C8_MAVROS_INSTALL C8_MODEL C8_FLOW_PLUGIN; do [[ "${!v}" == /* ]] || die "$v must be an absolute path"; done
[ "$(ls -d "$C8_PX4_ETC"/init.d-posix/airframes/"$C8_AIRFRAME"_* 2>/dev/null | wc -l)" = 1 ] || die "exactly one airframe file ${C8_AIRFRAME}_* is required in $C8_PX4_ETC/init.d-posix/airframes"
C8_AF_FILE="$(ls -d "$C8_PX4_ETC"/init.d-posix/airframes/"$C8_AIRFRAME"_*)"
{ [ "$(basename "$C8_MODEL")" = bumblebee ] && [ -f "$C8_MODEL/model.sdf" ]; } || die "C8_MODEL must be a folder named bumblebee with model.sdf"
[ -f "$C8_FLOW_PLUGIN" ] || die "missing C8_FLOW_PLUGIN $C8_FLOW_PLUGIN"
{ [ -f "$C8_PRODUCT_INSTALL/local_setup.bash" ] && [ -f "$C8_MAVROS_INSTALL/local_setup.bash" ] && [ -f "$C8_PRODUCT_SRC/examples/drone.py" ]; } || die "product or MAVROS path incomplete"
grep -q "local_bc6f158c" /work/SIM_LOCK.txt 2>/dev/null || die "/work/SIM_LOCK.txt is not held by Симулятор (local_bc6f158c)"
FREE_G=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d ' '); [ "${FREE_G:-0}" -ge 8 ] 2>/dev/null || die "disk C: free ${FREE_G:-?}G < 8G"
[ -f "$RUNNER" ] || die "missing $RUNNER"
# v4: the candidate is never defaulted (v3 silently used combined_03 when BB_COMBINED_ROOT was not set: six invalid runs
# on 19.10.2026, flight_trial_04_wsl_v3/RUNS.md). It must equal the separately frozen pins the verifier will use.
[ -n "$COMBINED" ] || die "BB_COMBINED_ROOT is required (no default candidate)"
[ -n "$PINS" ] || die "BB_FROZEN_PINS is required (the frozen pins JSON the verifier will use)"
[[ "$COMBINED" == /* ]] || die "BB_COMBINED_ROOT must be an absolute path"
[[ "$PINS" == /* ]] || die "BB_FROZEN_PINS must be an absolute path"
[ -f "$PINS" ] || die "BB_FROZEN_PINS $PINS is not a file"
# resolve FIRST; the check and run.sh then use the same resolved paths
COMBINED="$(realpath -e -- "$COMBINED")" && [ -d "$COMBINED" ] || die "BB_COMBINED_ROOT is not an existing directory"
PINS="$(realpath -e -- "$PINS")" || die "BB_FROZEN_PINS cannot be resolved"
# only pins listed (by SHA) in ACCEPTED_PINS.txt of THIS launcher version are accepted (changing it = new launcher version)
ACCEPTED_PINS=$HERE/ACCEPTED_PINS_b.txt   # c8-r2e-b: own accepted-pins list of this launcher version
[ -f "$ACCEPTED_PINS" ] || die "missing $ACCEPTED_PINS"
CAND_JSON="$(env C8_AF_FILE="$C8_AF_FILE" C8_MODEL_SDF="$C8_MODEL/model.sdf" C8_FLOW_PLUGIN="$C8_FLOW_PLUGIN" C8_DRONE_PY="$C8_PRODUCT_SRC/examples/drone.py" \
  python3 -I - "$COMBINED" "$PINS" "$TRIAL" "$WORK" "$ACCEPTED_PINS" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
comb, pins_p, trial, work, accepted_p = sys.argv[1:]
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
doc = {'combined_root': comb, 'frozen_pins': pins_p, 'trial': trial, 'problems': []}
P = doc['problems']
try:
    accepted = {l.split()[0] for l in open(accepted_p) if l.strip() and not l.startswith('#')}
    doc['frozen_pins_sha256'] = psha = sha(pins_p)
    if psha not in accepted: P.append('pins %s (sha %s) are not in %s' % (pins_p, psha[:12], accepted_p))
    try:
        pins = json.load(open(pins_p))
        if not isinstance(pins, dict): raise ValueError('not a JSON object')
    except Exception as e:
        P.append('pins unreadable: %s' % e); pins = {}
    croot = Path(comb)
    man = croot / 'manifest.json'
    exp = pins.get('expected_manifest')
    pf = pins.get('combined_files')
    if not isinstance(pf, dict) or not pf: P.append('pins have no combined_files object'); pf = {}
    if not exp: P.append('pins have no expected_manifest')
    elif not man.is_file(): P.append('%s missing' % man)
    else:
        if man.resolve() != Path(exp).resolve():
            P.append('candidate %s is not the pinned manifest %s' % (man.resolve(), exp))
        doc['manifest_sha256'] = msha = sha(man)
        if msha != pins.get('combined_manifest_sha256'):
            P.append('manifest sha256 differs from pins combined_manifest_sha256')
        try: mfiles = json.load(open(man)).get('files', {})
        except Exception as e: mfiles = {}; P.append('manifest unreadable: %s' % e)
        if mfiles != pf: P.append('manifest files differ from pins combined_files')
        bad = []
        for name, h in sorted(pf.items()):
            f = croot / name
            try:
                if f.is_symlink() or not f.resolve().is_relative_to(croot) or not f.is_file() or sha(f) != h: bad.append(name)
            except OSError: bad.append(name)
        if bad: P.append('candidate files differ from pins: ' + ', '.join(bad))
    # nothing else may be in the candidate (run.sh hashes $CAND/*.py into the ledger): only the pinned files,
    # manifest.json and README.md; no symlinks
    allowed = set(pf) | {'manifest.json', 'README.md'}
    extra = []
    for d, dirs, files in os.walk(croot):
        for n in dirs + files:
            full = Path(d) / n; rel = str(full.relative_to(croot))
            if full.is_symlink() or (n in files and rel not in allowed): extra.append(rel)
    if extra: P.append('unexpected entries in the candidate: ' + ', '.join(sorted(extra)[:20]))
    rf = pins.get('repo_files')
    if not isinstance(rf, dict) or not rf: P.append('pins have no repo_files object'); rf = {}
    runner = 'c8_judge_r2f_a8_20261110/executor/run.sh'  # A8: the fixed runner
    if runner not in rf: P.append('pins do not cover TRIAL %s (%s not pinned)' % (trial, runner))
    # c8: every file named by a C8_* parameter must be pinned in repo_files (another target set = new pins = new ACCEPTED_PINS)
    for key in ('C8_AF_FILE', 'C8_MODEL_SDF', 'C8_FLOW_PLUGIN', 'C8_DRONE_PY'):
        rel = os.path.relpath(os.path.realpath(os.environ[key]), work)
        if rel not in rf: P.append('pins do not cover %s (%s not pinned)' % (key, rel))
    bad = []
    for name, h in sorted(rf.items()):
        f = Path(work) / name
        try:
            if not f.is_file() or sha(f) != h: bad.append(name)
        except OSError: bad.append(name)
    if bad: P.append('pinned repo files changed: ' + ', '.join(bad))
except Exception as e:
    P.append('candidate check failed: %r' % e)
doc['ok'] = not P
print(json.dumps(doc)); sys.exit(0 if doc['ok'] else 3)
PY
)" || die "candidate does not match the frozen pins: $CAND_JSON"
[ -d "$WORK" ] && [ ! -L "$WORK" ] || die "/work must be a real directory, not a link"
case "$(findmnt -n -o FSTYPE --target "$WORK" 2>/dev/null)" in ext4) ;; *) die "/work must be on the WSL ext4 disk";; esac
[ ! -e "$OUT" ] && [ ! -e "$SIDE" ] && [ ! -e "$WORK/sim/runs/$TAG.runner.log" ] && [ ! -e "/tmp/bb_$TAG" ] \
  || die "TAG $TAG already used (runs are never overwritten)"
[ ! -e /work/sim/run/MEASURING ] || die "stale /work/sim/run/MEASURING exists (an earlier run did not clean up): investigate first"
[ -f "$GPU_ENV" ] || die "missing $GPU_ENV (setup step r04/u01)"
[ -f "$CLOCK_CHECK" ] || die "missing $CLOCK_CHECK"
[ -x "$PS" ] || die "powershell.exe not reachable (WSL interop)"
if pgrep -x px4 >/dev/null || pgrep -x mavros_node >/dev/null; then die "PX4 or MAVROS already running (one run at a time; bash /work/sim/stop_sim.sh)"; fi
for p in $(pgrep -x gz) $(pgrep -x ruby); do
  tr '\0' '\n' < "/proc/$p/environ" 2>/dev/null | grep -qE '^GZ_PARTITION=(bbtrial|bbgpucheck)$' && die "a trial Gazebo process (pid $p) is still running"
done
# no process of an earlier run may be alive: orphans (e.g. after a supervisor cleanup crash) keep sending RC overrides and
# answer /vpe_fix services of the next run (preflight_investigation/CORE_PROBLEMS.md item 3)
# A process belongs to a run if its FULL command line names a run folder/guard, or if it inherited run.sh's
# SITL_MAVROS_PARAMS=/work/sim/runs/TAG/mavros.yaml (mavros, vision.launch nodes, ros2 nodes carry no TAG in argv).
# Prints "pid<TAB>marker" (marker = command line + env marker). Never lists this launcher or its subshells.
proc_marker() { local pid=$1 c e
  c=$( { tr '\0' ' ' < "/proc/$pid/cmdline"; } 2>/dev/null) || return 1
  e=$( { tr '\0' '\n' < "/proc/$pid/environ"; } 2>/dev/null | sed -n 's/^SITL_MAVROS_PARAMS=//p' | head -1)
  printf '%s ENV:%s ' "$c" "$e"; }
run_procs() { local p pid m own_tag=${1:-}
  for p in /proc/[0-9]*; do pid=${p#/proc/}
    [ "$pid" = "$$" ] || [ "$pid" = "$BASHPID" ] && continue
    m=$(proc_marker "$pid") || continue
    if [ -z "$own_tag" ]; then
      case "$m" in *"$WORK/sim/runs/INT_"*|*"/tmp/bb_INT_"*) printf '%s\t%s\n' "$pid" "${m:0:300}";; esac
    elif [[ "$m" =~ /sim/runs/${own_tag}[/[:space:]] || "$m" =~ /tmp/bb_${own_tag}[/[:space:]] ]]; then
      printf '%s\t%s\n' "$pid" "${m:0:300}"
    fi
  done; }
LEFT="$(run_procs)"
[ -z "$LEFT" ] || die "processes of an earlier run are still alive (stop them by exact PID, never pkill -f):
$LEFT"
NETMODE="$(wslinfo --networking-mode 2>/dev/null | tr -d '\r[:space:]')"
[ "$NETMODE" = nat ] || die "WSL networking mode is '${NETMODE:-unknown}', must be nat"
GPU_VARS=(); while read -r v; do [ -n "$v" ] && GPU_VARS+=("$v"); done < <(sed -n 's/^export \([A-Za-z_][A-Za-z0-9_]*=[^ ]*\)$/\1/p' "$GPU_ENV")
if [ "$RENDER" != sw ] && [ "${#GPU_VARS[@]}" = 0 ]; then die "gpu_env.sh gives no variables: hr1/hr0 would silently render on the CPU"; fi
# atomic per-TAG lock: a second launcher with the same TAG cannot pass this line
mkdir "$SIDE" 2>/dev/null || die "could not create $SIDE (TAG in use by another launcher?)"
echo "ТОЛЬКО СИМУЛЯТОР (SIMULATOR ONLY) host_run_wsl_c8_r2e_b.sh v35-c8-r2f-a8" > "$SIDE/launcher.log"
echo "host_run_wsl: TAG=$TAG SCENARIO=$SCENARIO VIEW=$VIEW TRIAL=$TRIAL RENDER=$RENDER KEEP_AWAKE=$KEEP_AWAKE CANCEL_OFFSET_MS=${CANCEL_OFFSET:-default}" | tee -a "$SIDE/launcher.log"
echo "host_run_wsl_c8: C8_AIRFRAME=$C8_AIRFRAME C8_START_ORDER=$C8_START_ORDER C8_PX4_ETC=$C8_PX4_ETC C8_PRODUCT_INSTALL=$C8_PRODUCT_INSTALL C8_PRODUCT_SRC=$C8_PRODUCT_SRC C8_MAVROS_INSTALL=$C8_MAVROS_INSTALL C8_MODEL=$C8_MODEL C8_FLOW_PLUGIN=$C8_FLOW_PLUGIN" | tee -a "$SIDE/launcher.log"
echo "host_run_wsl: candidate $COMBINED matches frozen pins $PINS" | tee -a "$SIDE/launcher.log"
printf '%s\n' "$CAND_JSON" > "$SIDE/candidate_check.json"

# ---- background helpers + cleanup on any exit (Ctrl+C, closed window, error)
AWAKE_PID=""; CW_PID=""; VW_PID=""
cleanup_helpers() {
  touch "$SIDE/stop"
  [ -n "$VW_PID" ] && { wait "$VW_PID" 2>/dev/null; VW_PID=""; }
  [ -n "$CW_PID" ] && { kill "$CW_PID" 2>/dev/null; wait "$CW_PID" 2>/dev/null; CW_PID=""; }
  [ -n "$AWAKE_PID" ] && { kill -TERM -- "-$AWAKE_PID" 2>/dev/null; wait "$AWAKE_PID" 2>/dev/null; AWAKE_PID=""; }
}
on_signal() { echo "host_run_wsl: interrupted ($1): helpers stopped; this run is INVALID and its folders are kept" | tee -a "$SIDE/launcher.log"; cleanup_helpers; exit 130; }
trap 'on_signal INT' INT; trap 'on_signal TERM' TERM; trap 'on_signal HUP' HUP

# ---- clock check BEFORE (40 s). Not ok -> refuse: timing of the whole run would be meaningless.
python3 -B "$CLOCK_CHECK" 40 --json "$SIDE/clock_before.json" >> "$SIDE/launcher.log" 2>&1
CB=$?
[ "$CB" = 0 ] || { echo "clock check before: exit $CB (see $SIDE/clock_before.json)" | tee -a "$SIDE/launcher.log"; die "WSL clock not ok; run wsl_clock_check.py and fix the time sources first"; }

# ---- environment for run.sh (clean, like limactl shell) + renderer
ENV_RUN=(HOME="$HOME" USER="$USER" LOGNAME="$USER" SHELL=/bin/bash PATH="$CLEAN_PATH" LANG=C.UTF-8 TERM=dumb
  TAG="$TAG" SCENARIO="$SCENARIO" VIEW="$VIEW" BB_COMBINED_ROOT="$COMBINED"
  C8_AIRFRAME="$C8_AIRFRAME" C8_PX4_ETC="$C8_PX4_ETC" C8_PRODUCT_INSTALL="$C8_PRODUCT_INSTALL" C8_PRODUCT_SRC="$C8_PRODUCT_SRC"
  C8_MAVROS_INSTALL="$C8_MAVROS_INSTALL" C8_MODEL="$C8_MODEL" C8_FLOW_PLUGIN="$C8_FLOW_PLUGIN" C8_START_ORDER="$C8_START_ORDER")  # c8
[ -n "$CANCEL_OFFSET" ] && ENV_RUN+=(CANCEL_OFFSET_MS="$CANCEL_OFFSET")
case "$RENDER" in
  hr1) ENV_RUN+=(HR=1 "${GPU_VARS[@]}") ;;
  hr0) ENV_RUN+=(HR=0 DISPLAY=:0 QT_QPA_PLATFORM=xcb "${GPU_VARS[@]}") ;;
  sw)  ENV_RUN+=(HR=1 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe) ;;   # never gpu_env.sh in sw mode
esac
[ -n "${XDG_RUNTIME_DIR:-}" ] && ENV_RUN+=(XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR")
printf '%s\n' "${ENV_RUN[@]}" > "$SIDE/env_passed.txt"

# ---- host facts before
{ echo "== wsl.exe --version"; /mnt/c/Windows/System32/wsl.exe --version 2>&1 | tr -d '\0\r'
  echo "== uname -r"; uname -r; echo "== nproc"; nproc; echo "== free -b"; free -b
  echo "== powercfg /getactivescheme"; /mnt/c/Windows/System32/powercfg.exe /getactivescheme 2>&1 | tr -d '\r'; } > "$SIDE/host_before.txt" 2>&1
/usr/lib/wsl/lib/nvidia-smi --query-gpu=name,driver_version,utilization.gpu,clocks.gr --format=csv > "$SIDE/nvidia_before.csv" 2>&1
if [ "$RENDER" != sw ]; then env DISPLAY=:0 "${GPU_VARS[@]}" glxinfo -B > "$SIDE/glxinfo_B.txt" 2>&1; fi

START_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; START_EPOCH=$(date +%s); START_LOCAL="$(date '+%Y-%m-%d %H:%M:%S %z')"

# ---- optional: keep Windows awake for this run only (bounded 1800 s)
if [ "$KEEP_AWAKE" = 1 ]; then
  KA_PS=$(cat <<'PSEOF'
$null = Add-Type -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);' -Name K -Namespace W
$end = (Get-Date).AddSeconds(1800)
while ((Get-Date) -lt $end) { $r = [W.K]::SetThreadExecutionState([uint32]2147483649); "$(Get-Date -Format o) SetThreadExecutionState rc=$r"; Start-Sleep 30 }
PSEOF
)
  KA_B64="$(printf '%s' "$KA_PS" | iconv -f utf-8 -t utf-16le | base64 -w0)"
  setsid "$PS" -NoProfile -NonInteractive -EncodedCommand "$KA_B64" > "$SIDE/keep_awake.log" 2>&1 < /dev/null &
  AWAKE_PID=$!
fi

# ---- realtime-step watcher during the run (no ROS); must be alive at the end, else clock_ok=false
python3 -B "$HERE/clock_watch.py" "$SIDE/clock_during.csv" > "$SIDE/clock_watch.err" 2>&1 &
CW_PID=$!

# ---- Gazebo window (WSLg) for VIEW=on; it also exits when this launcher ($$) is gone
if [ "$VIEW" = on ]; then
  setsid bash "$HERE/viewer_wslg.sh" "$SIDE" "$RENDER" "$GPU_ENV" "$$" > "$SIDE/viewer_stdout.log" 2>&1 < /dev/null &
  VW_PID=$!
fi

# ---- the unchanged executor
( cd "$WORK" && env -i "${ENV_RUN[@]}" bash "$RUNNER" ) > "$WORK/sim/runs/$TAG.runner.log" 2>&1
RC=$?

END_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"; END_EPOCH=$(date +%s); END_LOCAL="$(date '+%Y-%m-%d %H:%M:%S %z')"
CW_ALIVE=0; kill -0 "$CW_PID" 2>/dev/null && CW_ALIVE=1
cleanup_helpers
trap - INT TERM HUP
# leftovers of THIS run (run.sh and its stop_sim.sh are done): record, hash $OUT, stop by exact PID (re-checked right
# before each signal), hash $OUT again. Leftovers or a changed $OUT are recorded in host_check.json and make it invalid.
sleep 2
out_hash() { [ -d "$OUT" ] && (cd "$OUT" && find . -type f -print0 | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -c1-64) || echo none; }
OUT_HASH_BEFORE="$(out_hash)"
LEFT_OWN="$(run_procs "$TAG")"
: > "$SIDE/leftover_processes.txt"
if [ -n "$LEFT_OWN" ]; then
  printf '%s\n' "$LEFT_OWN" > "$SIDE/leftover_processes.txt"
  signal_if_same() { local sig=$1 pid=$2 was=$3 now; now=$(proc_marker "$pid") || return 0
    [ "${now:0:300}" = "$was" ] && kill "-$sig" "$pid" 2>/dev/null; return 0; }
  while IFS=$'\t' read -r pid was; do signal_if_same INT "$pid" "$was"; done <<< "$LEFT_OWN"; sleep 3
  while IFS=$'\t' read -r pid was; do signal_if_same TERM "$pid" "$was"; done <<< "$LEFT_OWN"; sleep 2
  while IFS=$'\t' read -r pid was; do now=$(proc_marker "$pid") && [ "${now:0:300}" = "$was" ] && printf 'still alive\t%s\n' "$pid" >> "$SIDE/leftover_processes.txt"; done <<< "$LEFT_OWN"
fi
OUT_HASH_AFTER="$(out_hash)"
printf '%s\n%s\n' "$OUT_HASH_BEFORE" "$OUT_HASH_AFTER" > "$SIDE/out_hash_around_leftover_stop.txt"
/usr/lib/wsl/lib/nvidia-smi --query-gpu=name,driver_version,utilization.gpu,clocks.gr --format=csv > "$SIDE/nvidia_after.csv" 2>&1
# server renderer evidence: the viewer's copy of the server log if VIEW=on, else the newest OGRE log written during the run
if [ -f "$SIDE/ogre2_server.log" ] && [ "$(stat -c %Y "$SIDE/ogre2_server.log")" -ge "$START_EPOCH" ] \
   && grep -q 'GL_RENDERER' "$SIDE/ogre2_server.log" && [ "$(grep -c . "$SIDE/viewer.log" 2>/dev/null)" -gt 0 ]; then
  cp "$SIDE/ogre2_server.log" "$SIDE/ogre2.log"
else for f in "${OGRE_LOGS[@]}"; do if [ -f "$f" ] && [ "$(stat -c %Y "$f")" -ge "$START_EPOCH" ]; then cp "$f" "$SIDE/ogre2.log"; break; fi; done; fi

# ---- clock check AFTER
python3 -B "$CLOCK_CHECK" 40 --json "$SIDE/clock_after.json" >> "$SIDE/launcher.log" 2>&1
CA=$?

# ---- Windows sleep evidence in the run window +-60 s (Kernel-Power 41/42/107/109/506/507, Power-Troubleshooter 1).
# "No events" is recognised by the language-independent error id NoMatchingEventsFound.
"$PS" -NoProfile -NonInteractive -Command "\$s=[datetime]::Parse('$START_UTC').ToUniversalTime().ToLocalTime().AddSeconds(-60); \$e=[datetime]::Parse('$END_UTC').ToUniversalTime().ToLocalTime().AddSeconds(60); try { \$ev=Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=\$s; EndTime=\$e} -ErrorAction Stop | Where-Object { (\$_.ProviderName -eq 'Microsoft-Windows-Kernel-Power' -and \$_.Id -in 41,42,107,109,506,507) -or (\$_.ProviderName -eq 'Microsoft-Windows-Power-Troubleshooter' -and \$_.Id -eq 1) }; 'QUERY_OK'; foreach(\$x in \$ev){ \$x.TimeCreated.ToUniversalTime().ToString('o') + ' ' + \$x.ProviderName + ' ' + \$x.Id } } catch { if (\$_.FullyQualifiedErrorId -match 'NoMatchingEventsFound') { 'QUERY_OK' } else { 'QUERY_FAILED ' + \$_.FullyQualifiedErrorId + ' ' + \$_.Exception.Message } }" \
  > "$SIDE/windows_power_events.txt" 2>&1

mkdir -p "$OUT"
python3 -I - "$OUT/host_check.json" "$SIDE" "$TAG" "$SCENARIO" "$VIEW" "$TRIAL" "$RENDER" "$KEEP_AWAKE" "$RC" "$START_LOCAL" "$END_LOCAL" \
  "$START_UTC" "$END_UTC" "$START_EPOCH" "$END_EPOCH" "$CB" "$CA" "$NETMODE" "$COMBINED" "$CW_ALIVE" "$PINS" <<'PY'
import json, os, sys
(out, side, tag, scen, view, trial, render, keep, rc, start, end, s_utc, e_utc, s_ep, e_ep, cb, ca, netmode, combined,
 cw_alive, pins_path) = sys.argv[1:]
def rd(name):
    try: return open(os.path.join(side, name), errors='replace').read()
    except OSError: return None
def js(name):
    try: return json.load(open(os.path.join(side, name)))
    except (OSError, ValueError): return None
ev = (rd('windows_power_events.txt') or '').replace('\r', '').splitlines()
query_ok = any(l.strip() == 'QUERY_OK' for l in ev)
events = [l for l in ev if l.strip() and l.strip() != 'QUERY_OK' and not l.startswith('QUERY_FAILED') and not l.startswith('#<')]
awake = (not events) if query_ok else None
during = (rd('clock_during.csv') or '').splitlines()
steps = [l for l in during if 'realtime_step' in l]
watch_ok = cw_alive == '1' and any(',start,' in l for l in during)
clock_ok = cb == '0' and ca == '0' and watch_ok and not steps
ogre = rd('ogre2.log') or ''
gl = [l.strip() for l in ogre.splitlines() if 'GL_RENDERER' in l or 'GL_VENDOR' in l][:3]
gltxt = ' '.join(gl).lower()
if 'llvmpipe' in gltxt or 'softpipe' in gltxt: cls = 'SOFTWARE (llvmpipe)'
elif 'd3d12' in gltxt and 'nvidia' in gltxt: cls = 'GPU (D3D12 NVIDIA)'
else: cls = 'unknown'
renderer_ok = (cls == 'SOFTWARE (llvmpipe)') if render == 'sw' else (cls == 'GPU (D3D12 NVIDIA)')
ka = [l for l in (rd('keep_awake.log') or '').splitlines() if 'SetThreadExecutionState rc=' in l]
leftovers = [l for l in (rd('leftover_processes.txt') or '').splitlines() if l.strip()]
oh = (rd('out_hash_around_leftover_stop.txt') or '').split()
out_unchanged = len(oh) == 2 and oh[0] == oh[1]
cand = js('candidate_check.json')
candidate_ok = bool(cand and cand.get('ok') is True)
doc = {'tag': tag, 'scenario': scen, 'view': view, 'trial': 'c8_judge_r2f_a8_20261110/executor', 'combined_root': combined,
       'runner_exit': int(rc), 'host_start': start, 'host_end': end, 'host_start_utc': s_utc, 'host_end_utc': e_utc,
       'host_start_epoch': int(s_ep), 'host_end_epoch': int(e_ep),
       'power_before': None, 'power_after': None, 'low_power_mode_before': None, 'low_power_mode_after': None,
       'host_sleep_events': events, 'windows_event_query_ok': query_ok, 'windows_event_window_margin_s': 60,
       'host_awake_whole_run': awake,
       'keep_awake': {'requested': keep == '1', 'set_thread_execution_state_results': ka},
       'wsl': {'networking_mode': netmode, 'host_before': rd('host_before.txt'),
               'nvidia_smi_before': rd('nvidia_before.csv'), 'nvidia_smi_after': rd('nvidia_after.csv'),
               'glxinfo_B': rd('glxinfo_B.txt'), 'renderer_mode': render, 'ogre2_gl_lines': gl,
               'server_renderer': cls, 'renderer_ok': renderer_ok,
               'env_passed': (rd('env_passed.txt') or '').splitlines()},
       'clock': {'check_before': js('clock_before.json'), 'check_after': js('clock_after.json'),
                 'check_before_exit': int(cb), 'check_after_exit': int(ca), 'watcher_ok': watch_ok,
                 'realtime_steps_during_run': steps, 'clock_ok': clock_ok},
       'leftover_processes': leftovers, 'out_unchanged_while_stopping_leftovers': out_unchanged,
       'frozen_pins': pins_path, 'candidate_check': cand, 'candidate_ok': candidate_ok,
       'valid_host': bool(awake) and clock_ok and renderer_ok and not leftovers and out_unchanged and candidate_ok,
       'note': 'valid_host=false (host slept or sleep not provable, WSL clock not ok, the gz server did not render with the '
               'requested renderer, processes of this run outlived run.sh, or the candidate check is missing) makes the run '
               'INVALID regardless of its result. '
               'power_*/low_power_mode_* are Mac fields (null on the PC). Launcher files: ' + side}
json.dump(doc, open(out, 'w'), indent=2)
print(json.dumps({'tag': tag, 'runner_exit': int(rc), 'host_awake_whole_run': awake, 'clock_ok': clock_ok,
                  'server_renderer': cls, 'leftovers': len(leftovers), 'valid_host': doc['valid_host']}))
PY
echo "host_run_wsl: done, runner exit $RC; host_check: $OUT/host_check.json" | tee -a "$SIDE/launcher.log"
exit $RC
