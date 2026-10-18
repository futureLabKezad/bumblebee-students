#!/usr/bin/env bash
# setup_wsl_ubuntu2404.sh - rebuild the Bumblebee simulator environment (the old Lima VM "bbsim")
# on a Windows PC: WSL2 + Ubuntu 24.04 x86_64 + NVIDIA GPU through WSLg (Mesa d3d12).
#
# SIMULATOR ONLY. Nothing here talks to a real drone, sends MAVLink, arms motors or writes PX4
# parameters. No passwords are stored or typed by this script: the owner types the sudo password.
#
# Two phases, because Claude Code cannot answer a sudo password prompt:
#
#   ROOT phase - the OWNER runs it once in a SECOND Ubuntu window (not the window where Claude runs:
#   Windows Terminal "+" -> Ubuntu 24.04, or Start -> Ubuntu 24.04) and types his password there once:
#       sudo bash setup_wsl_ubuntu2404.sh root
#     r01 host checks (WSL2, Ubuntu 24.04, x86_64, NVIDIA visible through /dev/dxg, WSL networking mode
#         nat, free space on the Windows drive that holds the WSL disk, earlier apt upgrades)
#     r02 /work (real directory), ~/bbsim-work -> /work, /repo -> ~/bumblebee-students
#     r03 apt: Ubuntu archive snapshot 20261017T120000Z (the live ubuntu.sources is MOVED, not deleted);
#         stops (exit 10) if installed packages are NEWER than the snapshot
#     r04 mesa-utils + x11-utils + display and GPU check (glxinfo -B must show D3D12 + NVIDIA); without
#         the GPU it stops with exit 10 unless the owner recorded BB_ALLOW_NO_GPU=1
#     r05 ROS 2 Jazzy snapshot repo (snapshots.ros.org 2026-10-05, key fingerprint checked), then a dry
#         run (apt-get install -s) of every package set below, before anything is installed
#     r06 Gazebo Harmonic 8.15.0: the repo's reviewed CI installer (clean /repo, files pinned by SHA256)
#         with 124 exact pins, then apt-mark hold
#     r07 ROS 2 Jazzy packages exactly like the VM's install_ros.sh (with recommends)
#     r08 PX4 build dependencies exactly like the VM's sim/03_deps_build.sh (no recommends), plus the
#         python3-* packages PX4's requirements.txt resolved to in the VM (the VM got them from its image)
#     r09 small tools that existed in the VM (xdotool, jq, htop, ...)
#     r10 record installed versions + back up the downloaded .deb files
#
#   USER phase - Claude Code runs it as the normal user (no sudo), best with run_in_background:
#       bash setup_wsl_ubuntu2404.sh user
#     u01 host + GPU check again (as the user, WSLg display)
#     u02 restored inputs present and unchanged (pinned SHA256), /repo at b31ca69, apt phase done
#     u03 move the aarch64/macOS builds and venvs of the snapshot aside (never deleted)
#     u04 geoid egm96-5 for MAVROS (checked against its SHA256)
#     u05 Python venvs with the VM's exact versions (x86_64 wheels, pip --require-hashes)
#     u06 PX4 v1.16.1 (94cb2012) + airframes 4030/4031 + PX4-OpticalFlow 8758bd5 (as in the VM),
#         Python requirements checked against the VM first, make px4_sitl (jobs sized by free memory)
#     u07 MAVROS 2.14.0 from /work/ws_mavros214/src (VM build line)
#     u08 ws_sitl (VM build line)
#     u09 ws_package1b build + colcon test (VM build/test lines; counts compared with the VM)
#     u10 ENVIRONMENT_REPORT.md + inventory files in the VM format
#
# Other commands:
#   bash setup_wsl_ubuntu2404.sh check            read-only host + GPU check, changes nothing
#   bash setup_wsl_ubuntu2404.sh list             list the steps
#   bash setup_wsl_ubuntu2404.sh step u06_px4     re-run single steps (r* steps need sudo)
#
# Every step is idempotent: it checks what is already done and only adds what is missing.
# A step that fails stops the script; fix the cause and re-run that step.
# Exit code 10 = the owner must do something first (the message says what).
# Owner-accepted deviations (only after the owner said yes; each is written to ~/bb_pc_setup_logs/DEVIATIONS.md
# once and then stays accepted): BB_ALLOW_NO_GPU=1, BB_ALLOW_NEWER_PKGS=1, BB_ALLOW_PY_DIFF=1.
#   With sudo pass them through env:  sudo env BB_ALLOW_NO_GPU=1 bash setup_wsl_ubuntu2404.sh root
# Logs: ~/bb_pc_setup_logs/   Inventory + report: /work/pc_inventory_<date>/ (path kept in /work/.pc_inventory_dir)
#
# Places where facts could not be checked from the Mac are marked "TODO-VERIFY".

set -uo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
HERE="$(dirname "$SCRIPT_PATH")"
HANDOVER="$(dirname "$HERE")"                       # .../pc_handover_20261017
INV="$HANDOVER/vm_inventory"                         # read-only facts collected from the VM on 17.10

# ---------------------------------------------------------------- pins (do not change silently)
readonly PX4_REPO=https://github.com/PX4/PX4-Autopilot.git
readonly PX4_TAG=v1.16.1
readonly PX4_COMMIT=94cb2012792b2ae89f0b147cfee53ee31ae550be
readonly PX4_GZ_MODELS_COMMIT=e05f4312d3f28aa621157610584a4870406cb6d3
readonly PX4_OF_REPO=https://github.com/PX4/PX4-OpticalFlow.git
# PX4-OpticalFlow exactly as built in the VM: confirmed on 17.10 from the VM's build tree
# (vm_inventory/px4_opticalflow_commit.txt: build/px4_sitl_default/OpticalFlow/src/OpticalFlow = 8758bd5).
# PX4 v1.16.1 itself clones "master" at build time, so it is pinned here through a local mirror.
# (The repo's CI pins the older 5d60b9e; that is NOT what the VM used.)
readonly PX4_OF_COMMIT=8758bd5567aadf2f8ab5deee97701d2c495d0756
readonly UBUNTU_SNAPSHOT="${UBUNTU_SNAPSHOT:-20261017T120000Z}"
readonly ROS_SNAPSHOT_URL="${ROS_SNAPSHOT_URL:-http://snapshots.ros.org/jazzy/2026-10-05/ubuntu}"
readonly ROS_SNAPSHOT_KEY_FPR=4B63CF8FDE49746E98FA01DDAD19BAB3CBF125EA
readonly REPO_COMMIT=b31ca69c174a360273f75a5257ced0a5ac56bd3b
readonly GZ_SIM_VERSION=8.15.0

readonly SHA_AIRFRAME_4030=c960b610480842c6207cc34b7ec8feef6070262210d9f217ea2303e28bf76279
readonly SHA_AIRFRAME_4031=aae41a117943a520d37e56bac95da10da182ef08e70624087cdd703b5dacab3c
readonly SHA_MODEL_SDF=474fd2962efa69744ba747724e1e2c752179851a7b29c289b6fd60da69464729
readonly SHA_MAP_INPUT=528b5adb467dc91e819e0c4cb9a5ff44439319fff23c3293799b8ee3fe43e611
readonly SHA_MAVROS_TGZ=d52d2e07a9b511a31444de360161857f07d7ab7098b1093495f6e9e845d7a060
readonly SHA_GEOID_PGM=c4b25a03ec5845cec4778a54b580aeda676363f2205a89137e8677b2337af3ec
readonly SHA_GEOID_TBZ=c46224f8f723dc915d97179f4e1580a98d6c742fe2b82cd8fef0ecaaad13e614
readonly SHA_COMBINED03_MANIFEST=5262098fe1545462cf4d7e861324a5b7fe11fada3fca7225df0c32597a34a146
readonly SHA_VERIFY_FLIGHT=189b85c0eadd142497436225930e981947ac658191a41503508d1691adf09799
readonly SHA_LEGACY_VERIFIER=1f6e2b0bf4b4885f370591d303951eed2cfe10de40ab8a711527378a40ff3e88
readonly SHA_MAVROS_SCOPED=c4f578a0c9630b8ab375a97b04ccb1df352c2402a81e21fab48678f67ee3b5da
readonly SHA_SUPERVISOR=95d84234b9665a8ee4122d18069c79f1100c556217d9a241eacbecb64c63be53
readonly SHA_VM_SIMPLE_OFFBOARD_AARCH64=41803d1c5cb793f40d9d1ed96bb8383ec48f030a6a439f768a4c6606ca85c9b1
# The repo's installer files at b31ca69 (they run as root in r06; a CRLF or local edit must not slip through).
declare -A SHA_REPO_INSTALLER=(
  [simulation/trial/install_deps.sh]=07a60526f59e2e0b3ee2b3484fc9fb4bcab532b75934a6a92fe44680bd22ab55
  [simulation/trial/apt_prefetch.sh]=a73d7f1aee9fae4427b05bef01c836517b0778bd434cca51b1b438de13cc3fb3
  [simulation/trial/versions.env]=1dc3e2204649ef5a30d172a64892e33f1a92fd4866070168632b9c0122ab5f85
  [simulation/trial/apt-gz-harmonic.txt]=40f50699d332d3f4a4f440a1abc04c1eae1d668fa1d2b2304c902f86cd9a27bc
  [simulation/trial/apt-ubuntu.txt]=95e02d1774616ce20e0575d72722a037ba747aa3eef717684f194fbfcab2da2d
)
# ws_package1b colcon test in the VM on 15.10 (junit XML in build/bumblebee/test_results):
# 14 result files (ctest: "0 tests failed out of 14"), 160 tests, 0 errors, 0 failures, 1 skipped.
readonly VM_TEST_COUNTS="files=14 tests=160 errors=0 failures=0 skipped=1"

readonly WORK=/work
readonly QUARANTINE="$WORK/_foreign_binaries_20261017"
readonly MARKER=.bb_pc_x86_64
readonly CLEAN_PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
readonly NVSMI=/usr/lib/wsl/lib/nvidia-smi

# apt package sets. They reproduce the VM, see install_ros.sh and sim/03_deps_build.sh in /work.
ROS_BASE_TOOLS=(software-properties-common curl gnupg lsb-release locales)
ROS_PKGS=(ros-jazzy-ros-base ros-dev-tools python3-colcon-common-extensions
  ros-jazzy-mavros ros-jazzy-mavros-msgs ros-jazzy-tf2-geometry-msgs ros-jazzy-cv-bridge
  ros-jazzy-image-transport ros-jazzy-image-proc ros-jazzy-image-geometry ros-jazzy-rclcpp-components
  ros-jazzy-visualization-msgs libgeographiclib-dev geographiclib-tools python3-lxml
  libopencv-dev python3-opencv python3-numpy python3-pytest)
# gz-harmonic is NOT repeated here: it is installed (pinned) in r06; naming it again could upgrade it.
PX4_DEPS=(astyle build-essential ccache cmake cppcheck file g++ gcc gdb git lcov libssl-dev
  libxml2-dev libxml2-utils make ninja-build python3 python3-dev python3-pip python3-setuptools
  python3-wheel rsync shellcheck unzip zip python3-venv bc dmidecode libunwind-dev cppzmq-dev
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly
  gstreamer1.0-libav libeigen3-dev libgstreamer-plugins-base1.0-dev libimage-exiftool-perl
  libopencv-dev pkg-config protobuf-compiler)
# PX4 Tools/setup/requirements.txt was satisfied in the VM by these apt packages of its cloud image (the
# px4-venv uses --system-site-packages; no install script asked for them). Same versions from the snapshot.
PX4_PY_APT=(python3-jinja2 python3-jsonschema python3-yaml python3-serial python3-psutil python3-requests
  python3-six python3-packaging python3-pygments python3-argcomplete python3-coverage python3-empy
  python3-lxml python3-numpy python3-setuptools python3-wheel)
# Present in the VM but in no install script. fluxbox/x11vnc/novnc/websockify (the Mac noVNC viewer)
# are deliberately left out: WSLg gives a real display (DISPLAY=:0).
TOOL_PKGS=(mesa-utils x11-utils xdotool jq htop sysstat tmux screen lsof net-tools bzip2)

ROOT_STEPS=(r01_host r02_dirs r03_apt_ubuntu r04_gpu r05_ros_repo r06_gazebo r07_ros r08_px4_deps r09_tools r10_record)
USER_STEPS=(u01_host_gpu u02_inputs u03_quarantine u04_geoids u05_venvs u06_px4 u07_mavros u08_ws_sitl u09_ws_package1b u10_report)

# ---------------------------------------------------------------- who we are
if [ "$(id -u)" = 0 ]; then
  if [ -z "${SUDO_USER:-}" ] || [ "${SUDO_USER}" = root ]; then
    echo "Run this from your normal Ubuntu user (a second Ubuntu window, not Claude's) as: sudo bash $SCRIPT_PATH root" >&2
    exit 2
  fi
  TU="$SUDO_USER"
else
  TU="$(id -un)"
fi
TH="$(getent passwd "$TU" | cut -d: -f6)"
TG="$(id -gn "$TU")"
LOGDIR="$TH/bb_pc_setup_logs"
mkdir -p "$LOGDIR"
[ "$(id -u)" = 0 ] && chown "$TU:$TG" "$LOGDIR"

# ---------------------------------------------------------------- helpers
ts() { date +%Y%m%d_%H%M%S; }
log() { echo "[setup $(date +%H:%M:%S)] $*"; }
warn() { echo "[setup $(date +%H:%M:%S)] WARNING: $*" >&2; }
die() { echo "[setup $(date +%H:%M:%S)] ERROR: $*" >&2; exit 1; }
need_owner() { echo "" >&2; echo "=== NEEDS THE OWNER (exit 10) ===" >&2; echo "$*" >&2; exit 10; }
sha_of() { sha256sum "$1" | cut -d' ' -f1; }
count_lines() { grep -c -- "$1" "$2" 2>/dev/null || true; }   # prints 0 instead of failing
check_sha() { # file expected label
  [ -f "$1" ] || die "missing: $1 ($3)"
  local got; got="$(sha_of "$1")"
  [ "$got" = "$2" ] || die "SHA256 mismatch for $3: $1 is $got, expected $2"
  log "sha ok: $3"
}
is_root() { [ "$(id -u)" = 0 ]; }
as_user() { if is_root; then sudo -u "$TU" -H -- "$@"; else "$@"; fi; }
mkdir_user() { # create dirs owned by the target user
  local d; for d in "$@"; do
    if is_root; then install -d -o "$TU" -g "$TG" -m 0755 "$d"; else mkdir -p "$d"; fi
  done
}
chown_user() { if is_root; then chown -R "$TU:$TG" "$@"; fi; }
apt_get() { DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 -o Acquire::Retries=10 "$@"; }

pc_inv() { # the PC inventory folder (created once, then reused by every script)
  [ -d "$WORK" ] || die "$WORK does not exist yet (step r02_dirs)"
  local p
  if [ -f "$WORK/.pc_inventory_dir" ]; then
    p="$(cat "$WORK/.pc_inventory_dir")"
  else
    p="$WORK/pc_inventory_$(date +%Y%m%d)"
    echo "$p" > "$WORK/.pc_inventory_dir"
    chown_user "$WORK/.pc_inventory_dir"
  fi
  mkdir_user "$p"
  echo "$p"
}

# Run a command in a clean environment (like the VM's `limactl shell`): no ROS, no venv, no
# Windows PATH entries. Extra VAR=value words may come before the command.
clean_env() {
  local extra=()
  [ -n "${MAKEFLAGS:-}" ] && extra+=("MAKEFLAGS=$MAKEFLAGS")
  env -i HOME="$TH" USER="$TU" LOGNAME="$TU" SHELL=/bin/bash PATH="$CLEAN_PATH" LANG=C.UTF-8 TERM=dumb \
    "${extra[@]}" "$@"
}

# Compile jobs sized by AVAILABLE memory (not total; WSL gets only part of the host RAM):
#   mavros_extras needs ~2-3 GB per job (the VM OOM-killed a parallel build at 7 GB) -> 3 GB per job;
#   PX4 SITL (ninja, nproc+2 jobs by default) -> ~1 GB per job.
jobs_for_mem() { # GB_per_job
  local per=$1 avail_kb n j
  avail_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"; n="$(nproc)"
  j=$(( avail_kb / (per * 1024 * 1024) )); [ "$j" -lt 1 ] && j=1; [ "$j" -gt "$n" ] && j="$n"
  echo "$j"
}

# Owner-accepted deviations. KEY e.g. NO_GPU: BB_ALLOW_NO_GPU=1 (given by the owner after a clear explanation)
# writes one line to $LOGDIR/DEVIATIONS.md; a key that is already recorded there stays accepted on re-runs.
DEVIATIONS="$LOGDIR/DEVIATIONS.md"
allowed() { # KEY -> true if the owner accepted it now (env) or earlier (recorded)
  local key=$1 var="BB_ALLOW_$1"
  [ -f "$DEVIATIONS" ] && grep -q -- "^- .* \[$key\]" "$DEVIATIONS" && return 0
  [ "${!var:-0}" = 1 ]
}
record_deviation() { # KEY text
  local key=$1; shift
  if [ ! -f "$DEVIATIONS" ] || ! grep -q -- "^- .* \[$key\]" "$DEVIATIONS"; then
    [ -f "$DEVIATIONS" ] || echo "# Deviations from the Mac VM accepted by the owner (setup_wsl_ubuntu2404.sh)" > "$DEVIATIONS"
    echo "- $(date -Is) [$key] $*" >> "$DEVIATIONS"
    if [ "$(id -u)" = 0 ]; then chown "$TU:$TG" "$DEVIATIONS"; fi
  fi
  warn "owner-accepted deviation [$key]: $* (recorded in $DEVIATIONS)"
}
owner_or_allowed() { # KEY short_text long_message
  local key=$1 short=$2 msg=$3
  if allowed "$key"; then record_deviation "$key" "$short"; return 0; fi
  need_owner "$msg

Only if the owner decides to go on anyway (a recorded deviation from the Mac VM), re-run with
BB_ALLOW_$key=1 (root steps: sudo env BB_ALLOW_$key=1 bash $SCRIPT_PATH ...)."
}

# WSL networking mode must be NAT: in "mirrored" mode PX4 SITL's UDP ports (bound to 0.0.0.0) are shared with
# Windows and the LAN (QGroundControl could reach the simulator). TODO-VERIFY: wslinfo output format on the PC.
wsl_netmode() { if command -v wslinfo >/dev/null 2>&1; then wslinfo --networking-mode 2>/dev/null | tr -d '\r[:space:]'; fi; }
netmode_check() {
  local m; m="$(wsl_netmode)"
  log "WSL networking mode: ${m:-unknown}"
  case "$m" in
    nat) ;;
    "") need_owner "Cannot read the WSL networking mode (wslinfo missing: WSL is too old).
Owner, in PowerShell: wsl --update, then wsl --shutdown, then open Ubuntu again (Start -> Ubuntu 24.04)." ;;
    *) need_owner "WSL networking mode is '$m'; it must be 'nat' (in mirrored mode the simulator's UDP ports are
shared with Windows and the local network). Owner: remove the networkingMode line from %UserProfile%\\.wslconfig
(or set networkingMode=nat), then in PowerShell: wsl --shutdown, and open Ubuntu again." ;;
  esac
}

# Free space on the WINDOWS drive that holds the WSL virtual disk (ext4.vhdx). `df /` inside WSL shows the
# virtual size (~1 TB), not real free space, and the vhdx never shrinks by itself.
# The drive is read from the registry (BasePath of this distro); fallback C:. TODO-VERIFY on the PC.
windows_drive_mount() {
  local base="" reg=/mnt/c/Windows/System32/reg.exe name="${WSL_DISTRO_NAME:-}" pfx='\\?\'
  # sudo drops WSL_DISTRO_NAME; `wslpath -w /` prints \\wsl.localhost\<distro>\ (TODO-VERIFY as root)
  [ -n "$name" ] || name="$(wslpath -w / 2>/dev/null | tr -d '\r' | awk -F'\\' '{print $4}')"
  if [ -n "$name" ] && [ -x "$reg" ]; then
    base="$(timeout 20 "$reg" query 'HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss' /s 2>/dev/null | tr -d '\r' \
      | awk -v want="$name" '
          /^HKEY_/ { if (n == want && b != "") { print b; exit } n = ""; b = ""; next }
          $1 == "DistributionName" { n = $3 }
          $1 == "BasePath" { sub(/^[ \t]*BasePath[ \t]+REG_(EXPAND_)?SZ[ \t]+/, ""); b = $0 }
          END { if (n == want && b != "") print b }')"
  fi
  base="${base#"$pfx"}"
  [ -n "$base" ] || echo "WARNING: the drive of the WSL disk was not found in the registry (sudo/interop); assuming C:. If Ubuntu lives on another drive, check its free space by hand." >&2
  local letter; letter="$(printf '%s' "${base:-C:}" | cut -c1 | tr 'A-Z' 'a-z')"
  case "$letter" in [a-z]) echo "/mnt/$letter" ;; *) echo /mnt/c ;; esac
}
disk_checks() {
  local inside; inside="$(df -BG --output=avail / | tail -1 | tr -dc 0-9)"
  log "free on / inside WSL: ${inside} GB (virtual disk size, information only)"
  local mnt avail need=60
  mnt="$(windows_drive_mount)"
  # After the restore the big data is already on the disk: then only a margin is required.
  [ -f "$WORK/.pc_restore_extract_ok" ] && need=20
  if [ -d "$mnt" ] && avail="$(df -BG --output=avail "$mnt" 2>/dev/null | tail -1 | tr -dc 0-9)" && [ -n "$avail" ]; then
    log "free on the Windows drive $mnt (holds the WSL disk): ${avail} GB (needed now: $need GB)"
    [ "$avail" -ge "$need" ] || need_owner "Only ${avail} GB free on the Windows drive ${mnt#/mnt/} (the WSL virtual disk lives there).
Needed: $need GB (restore ~11 GB + apt ~6 GB + PX4 ~6 GB + builds). The WSL disk does not shrink by itself.
Owner: free space on that drive in Windows (do not delete anything from Ubuntu), then tell Claude."
  else
    warn "cannot read free space of the Windows drive ($mnt not mounted?): owner, check that drive C: has $need GB free"
  fi
}

apt_upgrade_history() { # warn when apt already upgraded packages here (unattended-upgrades, apt upgrade)
  local n=0 f c
  for f in /var/log/apt/history.log /var/log/apt/history.log.*; do
    [ -f "$f" ] || continue
    c="$(zgrep -c '^Upgrade:' "$f" 2>/dev/null || true)"; n=$(( n + ${c:-0} ))
  done
  if [ "$n" -gt 0 ]; then
    warn "apt history shows $n upgrade transaction(s) on this Ubuntu (e.g. automatic security updates). Packages newer
than the 17.10 snapshot may exist; step r03 checks every installed package against the snapshot."
  else
    log "apt history: no upgrades so far"
  fi
}

# GPU checks may be turned into warnings only by the owner's recorded decision (BB_ALLOW_NO_GPU=1).
gpu_problem() {
  owner_or_allowed NO_GPU "no NVIDIA GPU path in WSL: $1" "$1
Owner: update the NVIDIA driver on Windows, in PowerShell run 'wsl --update' and 'wsl --shutdown', then open
Ubuntu again (Start -> Ubuntu 24.04). Never install an NVIDIA Linux driver inside WSL. If it still fails, the
options are: native Ubuntu (dual boot), or finish the install without the GPU and measure the CPU renderer first."
}

# ---------------------------------------------------------------- shared checks
host_checks() {
  log "uname -a: $(uname -a)"
  [ "$(uname -m)" = x86_64 ] || die "needs x86_64, this is $(uname -m)"
  # shellcheck disable=SC1091
  . /etc/os-release
  [ "${VERSION_ID:-}" = 24.04 ] && [ "${VERSION_CODENAME:-}" = noble ] \
    || die "needs Ubuntu 24.04 (noble), this is ${PRETTY_NAME:-unknown}. Install with: wsl --install -d Ubuntu-24.04"
  if ! uname -r | grep -q -- '-microsoft-standard-WSL2'; then
    die "this is not a WSL2 kernel ($(uname -r)). This script is only for WSL2. A native Ubuntu dual boot
needs a different recipe (NVIDIA proprietary driver, EGL device rendering) - that is the owner's decision."
  fi
  netmode_check
  if dpkg-query -W -f '${db:Status-Abbrev} ${Package}\n' 2>/dev/null | awk '$1=="ii"{print $2}' \
      | grep -qE '^(nvidia-driver-|libnvidia-gl-|nvidia-utils-)'; then
    die "NVIDIA *Linux* driver packages are installed inside WSL. They break the WSL GPU path (the driver
comes from Windows through /usr/lib/wsl/lib). Not removing anything: tell the owner, he decides."
  fi
  if [ ! -e /dev/dxg ]; then gpu_problem "/dev/dxg is missing: the GPU is not passed into WSL."
  elif [ ! -x "$NVSMI" ]; then gpu_problem "$NVSMI not found (it comes from the Windows NVIDIA driver)."
  else
    local gpus; gpus="$("$NVSMI" -L 2>&1 || true)"
    echo "$gpus"
    echo "$gpus" | grep -q 'NVIDIA' || gpu_problem "nvidia-smi does not list an NVIDIA GPU: $gpus"
  fi
  log "CPUs: $(getconf _NPROCESSORS_ONLN), RAM: $(free -g | awk '/^Mem:/ {print $2}') GB (MemAvailable $(awk '/^MemAvailable:/ {printf "%d", $2/1048576}' /proc/meminfo) GB)"
  disk_checks
  [ "$(ps -p 1 -o comm=)" = systemd ] || warn "PID 1 is not systemd (WSL /etc/wsl.conf [boot] systemd=true is the 24.04 default)"
  # DISPLAY=:0 needs /tmp/.X11-unix/X0 itself (the /mnt/wslg copy alone is not enough).
  if [ -e /tmp/.X11-unix/X0 ]; then log "WSLg X socket /tmp/.X11-unix/X0 present"
  else warn "WSLg X socket /tmp/.X11-unix/X0 not found (/mnt/wslg/.X11-unix/X0: $([ -e /mnt/wslg/.X11-unix/X0 ] && echo present || echo missing)).
GUI (HR=0, viewer) and the GPU check need it. Owner: in PowerShell 'wsl --shutdown', then open Ubuntu again."; fi
}

# glxinfo as the target user on the WSLg display. Prints the renderer line.
gl_renderer() { as_user env DISPLAY=:0 "$@" glxinfo -B 2>&1 | grep -m1 'OpenGL renderer string' || true; }

gpu_gl_check() { # writes $1/gpu_env.sh (extra exports needed for the GPU, possibly none)
  local out=$1 r
  command -v glxinfo >/dev/null || die "glxinfo missing (mesa-utils): run step r04_gpu first (sudo)"
  command -v xdpyinfo >/dev/null || die "xdpyinfo missing (x11-utils): run step r04_gpu first (sudo)"
  printf '# Extra environment for GPU rendering on this PC (sourced by the PC launcher / probes).\n' > "$out/gpu_env.sh"
  # 1) Is the WSLg display reachable at all? (Different cause and different advice than a wrong renderer.)
  if ! as_user env DISPLAY=:0 xdpyinfo > "$out/xdpyinfo.txt" 2>&1; then
    ls -la /tmp/.X11-unix /mnt/wslg/.X11-unix >> "$out/xdpyinfo.txt" 2>&1 || true
    chown_user "$out"
    need_owner "The WSLg display :0 is not reachable (saved: $out/xdpyinfo.txt). This is NOT a GPU driver problem.
Owner, in PowerShell: wsl --shutdown, then open Ubuntu again (Start -> Ubuntu 24.04). If it stays, run 'wsl --update'."
  fi
  # 2) Which renderer does OpenGL use on that display?
  as_user env DISPLAY=:0 glxinfo -B > "$out/glxinfo_B.txt" 2>&1 || true
  as_user env DISPLAY=:0 eglinfo -B > "$out/eglinfo_B.txt" 2>&1 || true   # TODO-VERIFY: eglinfo ships in mesa-utils 9.0.0 on noble
  if [ -x "$NVSMI" ]; then "$NVSMI" > "$out/nvidia_smi.txt" 2>&1 || true; fi
  ls -l /dev/dxg /dev/dri* > "$out/dev_nodes.txt" 2>&1 || true
  r="$(gl_renderer)"; log "default: $r"
  if echo "$r" | grep -q 'D3D12' && echo "$r" | grep -q 'NVIDIA'; then
    log "GPU OK: OpenGL through Mesa d3d12 on the NVIDIA GPU"
  else
    r="$(gl_renderer MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA)"; log "with MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA: $r"
    if echo "$r" | grep -q 'D3D12' && echo "$r" | grep -q 'NVIDIA'; then
      warn "the default adapter is not the NVIDIA GPU (iGPU?). Every run must export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA (written to gpu_env.sh)"
      echo 'export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA' >> "$out/gpu_env.sh"
    else
      chown_user "$out"
      gpu_problem "The display works, but OpenGL in WSLg is NOT on the NVIDIA GPU ($r). Saved: $out/glxinfo_B.txt."
      echo "# NO GPU: owner-accepted deviation, see $DEVIATIONS (renderer: $r)" >> "$out/gpu_env.sh"
    fi
  fi
  chown_user "$out"
}

# ---------------------------------------------------------------- ROOT steps
step_r01_host() { host_checks; apt_upgrade_history; }

step_r02_dirs() {
  # /work must be a REAL directory: sitl_setup.py:312-313, start_mavros.py:18, save_run_state.py:8,
  # vision.launch.py:16-19, pipeline_probe.py:67 resolve() paths and compare them with literal /work/...;
  # run.sh:3 checks "$PWD" = /work. A symlink /work -> elsewhere makes every trial refuse to start.
  if [ -L "$WORK" ]; then
    die "$WORK is a symlink ($(readlink "$WORK")). It must be a real directory. Move the link aside (owner) and re-run."
  elif [ ! -e "$WORK" ]; then
    install -d -o "$TU" -g "$TG" -m 0755 "$WORK"; log "created $WORK"
  elif [ -d "$WORK" ]; then
    local owner; owner="$(stat -c %U "$WORK")"
    if [ "$owner" != "$TU" ]; then
      if [ -z "$(ls -A "$WORK")" ]; then chown "$TU:$TG" "$WORK"; log "chown $WORK -> $TU"
      else die "$WORK belongs to $owner and is not empty: check what it is (do not delete), then re-run"; fi
    fi
  else
    die "$WORK exists but is not a directory"
  fi
  local fs; fs="$(findmnt -n -o FSTYPE -T "$WORK" || true)"
  [ "$fs" = ext4 ] || warn "$WORK is on '$fs', expected ext4 (the WSL virtual disk). Never put /work on /mnt/c."
  # Convenience link in the other direction (allowed: nothing resolves ~/bbsim-work).
  if [ -L "$TH/bbsim-work" ]; then
    [ "$(readlink "$TH/bbsim-work")" = "$WORK" ] || die "$TH/bbsim-work points to $(readlink "$TH/bbsim-work"), expected $WORK"
  elif [ -e "$TH/bbsim-work" ]; then
    die "$TH/bbsim-work exists and is not a link to $WORK. The work tree must live at $WORK. Move it aside (never delete) and re-run."
  else
    as_user ln -s "$WORK" "$TH/bbsim-work"; log "linked $TH/bbsim-work -> $WORK"
  fi
  # /repo: in the VM a read-only mount of the repo clone. Nothing calls resolve() on /repo, so a symlink is fine.
  local want="$TH/bumblebee-students"
  if [ -L /repo ]; then
    [ "$(readlink /repo)" = "$want" ] || die "/repo points to $(readlink /repo), expected $want"
  elif [ -e /repo ]; then
    die "/repo exists and is not a symlink to $want: check it (do not delete) and re-run"
  else
    ln -s "$want" /repo; log "linked /repo -> $want"
  fi
  [ -d "$want/.git" ] || warn "$want is not cloned yet: run restore_snapshot.sh repo (Claude, no sudo) before step r06_gazebo"
  pc_inv >/dev/null
}

step_r03_apt_ubuntu() {
  # Ubuntu packages from the dated snapshot = the state of the VM on 17.10 (1664/1664 relevant VM
  # packages have the same version there). Consequence for the owner: this WSL distro no longer gets
  # Ubuntu updates while the snapshot is active. Undo = move the files back from /etc/apt/sources-disabled.
  cat > /etc/apt/apt.conf.d/80-bumblebee-sim <<'EOF'
// Bumblebee simulator PC (setup_wsl_ubuntu2404.sh): keep downloaded .deb files (OSRF keeps only the
// newest Gazebo build, so the cache is the only way to repeat this exact install) and retry downloads.
Binary::apt::APT::Keep-Downloaded-Packages "true";
APT::Keep-Downloaded-Packages "true";
Acquire::Retries "10";
EOF
  mkdir -p /etc/apt/sources-disabled
  local f
  for f in /etc/apt/sources.list.d/ubuntu.sources; do
    if [ -e "$f" ]; then mv "$f" "/etc/apt/sources-disabled/$(basename "$f").$(ts)"; log "moved $f to /etc/apt/sources-disabled/"; fi
  done
  if grep -qE '^[[:space:]]*deb ' /etc/apt/sources.list 2>/dev/null; then
    mv /etc/apt/sources.list "/etc/apt/sources-disabled/sources.list.$(ts)"; log "moved /etc/apt/sources.list (had active lines)"
  fi
  if dpkg-query -W -f '${db:Status-Abbrev}\n' ros2-apt-source 2>/dev/null | grep -q '^ii'; then
    die "ros2-apt-source is installed: it adds the LIVE ROS repo whose newer packages would win over the snapshot. Ask the owner before removing it."
  fi
  # TODO-VERIFY: Ubuntu Release files carry no Valid-Until; Check-Valid-Until is off only as a precaution
  # for an old snapshot (signatures are still checked).
  cat > /etc/apt/sources.list.d/ubuntu-snapshot.sources <<EOF
# Bumblebee simulator PC: Ubuntu archive frozen at the Lima VM's state (17.10.2026).
Types: deb
URIs: https://snapshot.ubuntu.com/ubuntu/${UBUNTU_SNAPSHOT}
Suites: noble noble-updates noble-security
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Check-Valid-Until: no
EOF
  apt_get update
  # The WSL image may already contain packages NEWER than the snapshot: Ubuntu 24.04 in WSL runs systemd,
  # so unattended-upgrades / apt-daily install live security updates between `wsl --install` and this step.
  # apt never downgrades them, and a -dev package from the snapshot (libc6-dev, libssl-dev, python3.12-dev,
  # libxml2-dev, zlib1g-dev, ...) then cannot be installed next to its newer runtime: r06-r08 would stop
  # half-way with "unmet dependencies". So stop HERE, before anything is installed, and let the owner decide.
  installed_vs_snapshot
}

# Compare every installed package with the configured (snapshot) sources. Writes the lists to the log folder.
installed_vs_snapshot() {
  local base; base="$LOGDIR/apt_installed_vs_snapshot_$(ts)"
  dpkg-query -W -f '${db:Status-Abbrev}\t${binary:Package}\t${Version}\n' | awk -F'\t' '$1 ~ /^ii/ {print $2 "\t" $3}' > "$base.installed"
  cut -f1 "$base.installed" | xargs -r env LC_ALL=C apt-cache policy > "$base.policy" 2>/dev/null || true
  python3 -I - "$base.installed" "$base.policy" "$(dpkg --print-architecture)" > "$base.txt" <<'PY'
import re, subprocess, sys
native = ':' + sys.argv[3]
def norm(n): return n[:-len(native)] if n.endswith(native) else n   # libc6:amd64 (Multi-Arch: same) -> libc6
inst = {norm(a): b for a, b in (l.rstrip('\n').split('\t', 1) for l in open(sys.argv[1]) if '\t' in l)}
tables, pkg, ver = {}, None, None
for line in open(sys.argv[2], errors='replace'):
    line = line.rstrip('\n')
    m = re.match(r'^(\S+):$', line)
    if m: pkg = norm(m.group(1)); tables[pkg] = {}; ver = None; continue
    m = re.match(r'^ (?:\*\*\*| {3}) (\S+) -?\d+$', line)
    if m and pkg: ver = m.group(1); tables[pkg].setdefault(ver, []); continue
    m = re.match(r'^ {8}-?\d+ (.+)$', line)
    if m and pkg and ver: tables[pkg][ver].append(m.group(1))
def gt(a, b): return subprocess.run(['dpkg', '--compare-versions', a, 'gt', b]).returncode == 0
newer, older, local, unparsed = [], [], [], []
for name, v in sorted(inst.items()):
    t = tables.get(name)
    if t is None: unparsed.append(name); continue
    if any('/var/lib/dpkg/status' not in s for s in t.get(v, [])): continue   # this exact version is in the snapshot
    repo = [x for x, srcs in t.items() if any('/var/lib/dpkg/status' not in s for s in srcs)]
    if not repo: local.append((name, v)); continue
    top = repo[0]
    for x in repo[1:]:
        if gt(x, top): top = x
    (newer if gt(v, top) else older).append((name, v, top))
for n, v, t in newer: print(f'NEWER\t{n}\tinstalled {v}\tsnapshot {t}')
for n, v, t in older: print(f'OLDER\t{n}\tinstalled {v}\tsnapshot {t}')
for n, v in local: print(f'LOCAL\t{n}\tinstalled {v}\tnot in any configured source')
for n in unparsed: print(f'UNPARSED\t{n}')
print(f'SUMMARY\tinstalled {len(inst)}\tnewer {len(newer)}\tolder {len(older)}\tlocal {len(local)}\tunparsed {len(unparsed)}', file=sys.stderr)
PY
  chown_user "$base".*
  local nn; nn="$(count_lines '^NEWER' "$base.txt")"
  log "installed vs snapshot: $nn newer, $(count_lines '^OLDER' "$base.txt") older (parity check will show them), $(count_lines '^LOCAL' "$base.txt") not in the sources; list: $base.txt"
  if [ "$nn" != 0 ]; then
    grep '^NEWER' "$base.txt" | head -40 >&2
    owner_or_allowed NEWER_PKGS "$nn installed packages newer than snapshot $UBUNTU_SNAPSHOT ($base.txt)" \
"$nn installed packages are NEWER than the Ubuntu snapshot $UBUNTU_SNAPSHOT (list above and in $base.txt),
most likely automatic security updates. Installing the simulator now would probably stop half-way. Options (owner decides):
 1) Re-install a fresh Ubuntu-24.04 in WSL and start the root phase right after creating the user. Consequence: everything
    inside this Ubuntu is lost (wsl --unregister deletes it); nothing important is there yet only if the restore has not run.
 2) Go on with the newer packages as a recorded deviation from the Mac VM (the install may still fail on -dev packages).
 3) Use a later snapshot date (UBUNTU_SNAPSHOT=...): every package then differs from the VM, so parity is weaker."
  fi
}

step_r04_gpu() {
  apt_get install -y --no-install-recommends mesa-utils x11-utils ca-certificates curl gnupg
  local out; out="$(pc_inv)/gpu_root_phase_$(ts)"; mkdir_user "$out"
  gpu_gl_check "$out"
  cp "$out/gpu_env.sh" "$(pc_inv)/gpu_env.sh"; chown_user "$(pc_inv)/gpu_env.sh"
}

step_r05_ros_repo() {
  # ROS 2 Jazzy from snapshots.ros.org (247/247 VM ROS packages have the same upstream version there).
  # The live packages.ros.org keeps only the newest sync, so it would drift.
  local tmp; tmp="$(mktemp -d)"; chmod 700 "$tmp"
  curl -fsSL --retry 5 "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x${ROS_SNAPSHOT_KEY_FPR}" -o "$tmp/key.asc"
  mkdir -m 700 "$tmp/gnupg"
  local fpr; fpr="$(gpg --batch --homedir "$tmp/gnupg" --with-colons --show-keys "$tmp/key.asc" | awk -F: '$1=="fpr"{print $10; exit}')"
  [ "$fpr" = "$ROS_SNAPSHOT_KEY_FPR" ] || die "ROS snapshot key fingerprint is '$fpr', expected $ROS_SNAPSHOT_KEY_FPR"
  gpg --batch --homedir "$tmp/gnupg" --dearmor < "$tmp/key.asc" > "$tmp/key.gpg"
  install -m 0644 "$tmp/key.gpg" /usr/share/keyrings/ros-snapshots-archive-keyring.gpg
  log "ROS snapshot key installed (fingerprint $fpr)"
  # Disable any LIVE ROS source (moved, not deleted).
  local f
  for f in /etc/apt/sources.list.d/*; do
    [ -f "$f" ] || continue
    case "$f" in */ros2-snapshot.sources) continue ;; esac
    if grep -q 'packages.ros.org' "$f"; then mv "$f" "/etc/apt/sources-disabled/$(basename "$f").$(ts)"; log "moved live ROS source $f"; fi
  done
  # http on purpose: snapshots.ros.org serves a TLS certificate for another host name; integrity
  # comes from the GPG signature checked against the key above.
  cat > /etc/apt/sources.list.d/ros2-snapshot.sources <<EOF
# Bumblebee simulator PC: ROS 2 Jazzy frozen at the Lima VM's state (sync 2026-10-05).
Types: deb
URIs: ${ROS_SNAPSHOT_URL}
Suites: noble
Components: main
Signed-By: /usr/share/keyrings/ros-snapshots-archive-keyring.gpg
Check-Valid-Until: no
EOF
  apt_get update
  local cand; cand="$(apt-cache policy ros-jazzy-ros-base | awk '/Candidate:/ {print $2}')"
  log "ros-jazzy-ros-base candidate: $cand (VM: 0.11.0-1noble.20261006.040749 on arm64)"
  case "$cand" in 0.11.0-1noble*) ;; *) die "unexpected ros-jazzy-ros-base candidate '$cand' (TODO-VERIFY snapshot date)";; esac
  cand="$(apt-cache policy ros-jazzy-mavros-msgs | awk '/Candidate:/ {print $2}')"
  case "$cand" in 2.16.0-1noble*) log "ros-jazzy-mavros-msgs candidate $cand" ;; *) die "unexpected ros-jazzy-mavros-msgs candidate '$cand' (VM had 2.16.0)";; esac
  simulate_installs
}

# Dry run (apt-get install -s changes nothing) of every package set of r06-r09 against the snapshots, so a
# conflict stops the root phase BEFORE Gazebo, ROS or PX4 are half-installed. The 124 Gazebo pins cannot be
# simulated yet (the OSRF source is added by install_deps.sh in r06); apt-get install of the pins there is
# all-or-nothing anyway.
simulate_one() { # label recommends(0|1) packages...
  local label=$1 rec=$2 out opt=(); shift 2
  out="$LOGDIR/apt_simulate_${label}_$(ts).txt"
  [ "$rec" = 1 ] || opt=(--no-install-recommends)
  if ! LC_ALL=C apt_get install -s "${opt[@]}" "$@" > "$out" 2>&1; then
    chown_user "$out"; tail -25 "$out" >&2
    need_owner "apt dry run '$label' failed: these packages cannot be installed together from the snapshots
(log: $out). Nothing was installed. Usual cause: packages newer than the snapshot (see step r03). Tell the owner
the short reason; the options are the same as in step r03 (fresh Ubuntu, recorded deviation, other snapshot)."
  fi
  chown_user "$out"
  if grep -q '^Remv ' "$out"; then
    grep '^Remv ' "$out" | head -20 >&2
    need_owner "apt dry run '$label' would REMOVE packages (log: $out). Nothing was installed. Owner decision needed."
  fi
  log "dry run $label: $(count_lines '^Inst ' "$out") package(s) would be installed, none removed"
}
simulate_installs() {
  local ub=() f=/repo/simulation/trial/apt-ubuntu.txt
  if [ -f "$f" ]; then
    mapfile -t ub < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' -e '/^[[:space:]]*$/d' "$f")
    simulate_one repo_apt_ubuntu 0 "${ub[@]}"
  else
    warn "$f missing (repo not cloned yet): its packages are not part of the dry run"
  fi
  simulate_one ros 1 "${ROS_BASE_TOOLS[@]}" "${ROS_PKGS[@]}"
  simulate_one px4_tools 0 "${PX4_DEPS[@]}" "${PX4_PY_APT[@]}" "${TOOL_PKGS[@]}"
  simulate_one all_sets 0 "${ub[@]}" "${ROS_BASE_TOOLS[@]}" "${ROS_PKGS[@]}" "${PX4_DEPS[@]}" "${PX4_PY_APT[@]}" "${TOOL_PKGS[@]}"
}

gz_pins_file() { echo /repo/simulation/trial/apt-gz-harmonic.txt; }

step_r06_gazebo() {
  [ -f /repo/simulation/trial/install_deps.sh ] || die "/repo/simulation/trial/install_deps.sh missing: run restore_snapshot.sh repo first (Claude)"
  local head; head="$(as_user git -C "$TH/bumblebee-students" rev-parse HEAD)"
  [ "$head" = "$REPO_COMMIT" ] || die "/repo is at $head, expected $REPO_COMMIT"
  # install_deps.sh runs as root: the clone must be exactly b31ca69 (no local edits) and the files byte-exact.
  [ -z "$(as_user git -C "$TH/bumblebee-students" status --porcelain)" ] \
    || die "/repo has local changes; install_deps.sh would run them as root. Do not discard anything: ask the owner."
  local rel
  for rel in "${!SHA_REPO_INSTALLER[@]}"; do check_sha "/repo/$rel" "${SHA_REPO_INSTALLER[$rel]}" "$rel @ b31ca69"; done
  if dpkg-query -W -f '${db:Status-Abbrev} ${Version}\n' libgz-sim8 2>/dev/null | grep -q "^ii *${GZ_SIM_VERSION}-1~noble"; then
    log "Gazebo $GZ_SIM_VERSION already installed; re-running the installer only re-checks the pins"
  fi
  # The repo's reviewed CI installer: Ubuntu packages of apt-ubuntu.txt, the OSRF key checked by sha256,
  # exactly the 124 pinned Harmonic packages, fails on any unpinned OSRF package, requires gz sim 8.15.0.
  # Its prefetch downloads Ubuntu .debs from UBUNTU_POOL_MIRRORS when snapshot.ubuntu.com is slow and
  # accepts a file only if size + SHA256 match the snapshot index. Note: if the prefetch itself fails,
  # install_deps.sh empties /var/cache/apt/archives (apt then downloads and verifies everything itself).
  UBUNTU_POOL_MIRRORS="${UBUNTU_POOL_MIRRORS-http://archive.ubuntu.com/ubuntu}" bash /repo/simulation/trial/install_deps.sh \
    || die "install_deps.sh failed. If it says the pinned Gazebo versions are not installable, OSRF has published a newer
Harmonic since 17.10: STOP and ask the owner (options: accept the new version as a recorded deviation, or find the old .debs)."
  local v; v="$(gz sim --versions 2>/dev/null | head -1 | tr -d '[:space:]')"
  [ "$v" = "$GZ_SIM_VERSION" ] || die "gz sim --versions = '$v', expected $GZ_SIM_VERSION"
  if [ "${BB_APT_HOLD:-1}" = 1 ]; then
    # OSRF is the only live repository left; hold its packages so no later apt command upgrades them.
    # Undo: sudo apt-mark unhold <packages>
    # shellcheck disable=SC2046
    apt-mark hold $(sed -e 's/#.*//' -e 's/=.*//' -e '/^[[:space:]]*$/d' "$(gz_pins_file)") >/dev/null
    log "apt-mark hold: $(apt-mark showhold | wc -l) packages held"
  else
    warn "BB_APT_HOLD=0: Gazebo packages are NOT held"
  fi
}

step_r07_ros() {
  apt_get install -y "${ROS_BASE_TOOLS[@]}"
  locale-gen en_US.UTF-8
  apt_get install -y "${ROS_PKGS[@]}"
  local v
  v="$(dpkg-query -W -f '${Version}' ros-jazzy-mavros-msgs)"; case "$v" in 2.16.0-*) ;; *) die "ros-jazzy-mavros-msgs $v, expected 2.16.0 (VM)";; esac
  v="$(dpkg-query -W -f '${Version}' ros-jazzy-mavlink)"; case "$v" in 2026.9.9-*) ;; *) die "ros-jazzy-mavlink $v, expected 2026.9.9 (VM)";; esac
  [ -f /opt/ros/jazzy/setup.bash ] || die "/opt/ros/jazzy/setup.bash missing"
  log "ROS 2 Jazzy installed: ros-base $(dpkg-query -W -f '${Version}' ros-jazzy-ros-base)"
}

step_r08_px4_deps() {
  apt_get install -y --no-install-recommends "${PX4_DEPS[@]}"
  # Python modules of PX4's requirements.txt, as the VM had them from apt (u06 checks them before building).
  apt_get install -y --no-install-recommends "${PX4_PY_APT[@]}"
  # gz-harmonic must still be the pinned one (holds protect it; this is a second look).
  local v; v="$(gz sim --versions 2>/dev/null | head -1 | tr -d '[:space:]')"
  [ "$v" = "$GZ_SIM_VERSION" ] || die "Gazebo changed to '$v' during the PX4 deps install"
}

step_r09_tools() {
  apt_get install -y --no-install-recommends "${TOOL_PKGS[@]}"
}

step_r10_record() {
  local out; out="$(pc_inv)/root_phase_$(ts)"; mkdir_user "$out"
  dpkg-query -W -f '${Package}\t${Version}\t${Architecture}\n' | sort > "$out/dpkg_all.tsv"
  { for f in /etc/apt/sources.list.d/*; do echo "== $f"; cat "$f"; done; echo "== disabled:"; ls -l /etc/apt/sources-disabled; } > "$out/apt_sources.txt" 2>&1
  apt-mark showhold > "$out/apt_holds.txt"
  gz sim --versions > "$out/gz_versions.txt" 2>&1 || true
  # Back up the downloaded .debs into the user's home (OSRF keeps only the newest build).
  local bk="$TH/apt_debs_20261017"; mkdir_user "$bk"
  local n=0 f
  for f in /var/cache/apt/archives/*.deb; do
    [ -f "$f" ] || continue
    [ -e "$bk/$(basename "$f")" ] || { cp -p "$f" "$bk/"; n=$((n + 1)); }
  done
  chown_user "$bk" "$out"
  log "backed up $n new .deb files to $bk ($(du -sh "$bk" | cut -f1))"
  log "root phase record: $out"
  cat <<'EOF'

======================================================================
 ГОТОВО: системная часть установлена.
 Это окно можно закрыть. Вернитесь в окно с Claude и напишите:
 «root готов». Дальше Claude всё сделает сам (без пароля).
======================================================================
EOF
}

# ---------------------------------------------------------------- USER steps
step_u01_host_gpu() {
  host_checks
  local out; out="$(pc_inv)/gpu_user_phase_$(ts)"; mkdir_user "$out"
  gpu_gl_check "$out"
  if ! cmp -s "$out/gpu_env.sh" "$(pc_inv)/gpu_env.sh" 2>/dev/null; then
    cp "$out/gpu_env.sh" "$(pc_inv)/gpu_env.sh"; log "gpu_env.sh updated"
  fi
}

step_u02_inputs() {
  [ -f "$WORK/sim/run_sim.sh" ] || need_owner "The work folder is not restored yet. Claude: run  bash $HERE/restore_snapshot.sh all"
  [ -f "$WORK/pc_handover_20261017/vm_inventory/dpkg_relevant.tsv" ] \
    || need_owner "The 17.10 update is not overlaid on /work yet. Claude: run  bash $HERE/restore_snapshot.sh overlay"
  [ -f /opt/ros/jazzy/setup.bash ] && command -v gz >/dev/null \
    || need_owner "The apt part is missing. Owner, in a SECOND Ubuntu window (not Claude's window):  sudo bash $SCRIPT_PATH root"
  local I="$WORK/parallel_work/20261015/integration"
  check_sha "$WORK/sim/bumblebee_model/airframes/4030_gz_bumblebee" "$SHA_AIRFRAME_4030" "airframe 4030 (accepted selected-real)"
  check_sha "$WORK/sim/bumblebee_model/airframes/4031_gz_bumblebee_demo" "$SHA_AIRFRAME_4031" "airframe 4031"
  check_sha "$WORK/sim/bumblebee_model/models/bumblebee/model.sdf" "$SHA_MODEL_SDF" "bumblebee model.sdf"
  check_sha "$WORK/sim/worlds/aruco_map/map.input.txt" "$SHA_MAP_INPUT" "marker map (original field)"
  check_sha "$I/field_measurements_01/generated/map.input.txt" "$SHA_MAP_INPUT" "marker map (field candidate)"
  check_sha "$WORK/sim/ros_stack/mavros-2.14.0.tar.gz" "$SHA_MAVROS_TGZ" "MAVROS 2.14.0 source tarball"
  check_sha "$I/combined_03/manifest.json" "$SHA_COMBINED03_MANIFEST" "combined_03 manifest"
  check_sha "$I/flight_verification_01/verify_flight.py" "$SHA_VERIFY_FLIGHT" "verify_flight.py"
  check_sha "$WORK/analysis/exp_scripts/verify_package1b_gates.py" "$SHA_LEGACY_VERIFIER" "legacy verifier"
  check_sha "$WORK/ws_package1b/src/bumblebee/launch/mavros_scoped_config.py" "$SHA_MAVROS_SCOPED" "mavros_scoped_config.py"
  check_sha "$I/flight_trial_02/supervisor.py" "$SHA_SUPERVISOR" "flight_trial_02 supervisor.py"
  (cd "$I/flight_trial_02" && sha256sum -c --quiet SHA256SUMS.txt) || die "flight_trial_02 SHA256SUMS.txt check failed"
  (cd "$I/flight_trial_03" && sha256sum -c --quiet SHA256SUMS.txt) || die "flight_trial_03 SHA256SUMS.txt check failed"
  log "flight_trial_02/03 SHA256SUMS ok"
  [ "$(readlink /repo)" = "$TH/bumblebee-students" ] || die "/repo is not the expected symlink (step r02_dirs)"
  [ "$(git -C /repo rev-parse HEAD)" = "$REPO_COMMIT" ] || die "/repo is not at $REPO_COMMIT"
  [ -z "$(git -C /repo status --porcelain)" ] || die "/repo has local changes; it must be clean"
  log "/repo clean at $REPO_COMMIT"
}

move_aside() { # move a path from /work into the quarantine folder (same relative path); never delete
  local src=$1 rel dest
  rel="${src#"$WORK"/}"; dest="$QUARANTINE/$rel"
  [ -e "$dest" ] && dest="$dest.$(ts)"
  mkdir -p "$(dirname "$dest")"
  mv -T "$src" "$dest"
  printf '%s\t%s\t%s\n' "$(date -Is)" "$src" "$dest" >> "$QUARANTINE/MOVED.tsv"
  log "moved aside: $src -> $dest"
}

# A tree made on THIS PC: finished ($MARKER), started by this script ($MARKER.started, written before colcon/venv
# creation, so a failed build is not mistaken for the snapshot's), or a build tree whose CMake system files all
# say x86_64.
pc_made_tree() {
  local d=$1 f n=0
  [ -e "$d/$MARKER" ] || [ -e "$d/$MARKER.started" ] && return 0
  for f in "$d"/*/CMakeFiles/*/CMakeSystem.cmake; do
    [ -f "$f" ] || continue
    grep -q 'CMAKE_SYSTEM_PROCESSOR "x86_64"' "$f" || return 1
    n=$((n + 1))
  done
  [ "$n" -gt 0 ]
}
mark_started() { local d; for d in "$@"; do mkdir -p "$d"; echo "started $(date -Is) on $(uname -m) by setup_wsl_ubuntu2404.sh" > "$d/$MARKER.started"; done; }
need_pc_tree_or_none() { # ws/sub must not exist, or be a tree made on this PC
  [ ! -e "$1" ] || pc_made_tree "$1" || die "$1 is from the snapshot (aarch64): run step u03_quarantine first"
}

step_u03_quarantine() {
  # The snapshot holds aarch64 Linux builds (CMakeCache -> /usr/lib/aarch64-linux-gnu) and macOS/aarch64
  # venvs. They cannot run here and would confuse colcon. Trees made on this PC (pc_made_tree) are left
  # alone, also after a failed build. colcon log/ folders stay in place as text evidence.
  mkdir -p "$QUARANTINE"
  local ws sub v f n=0
  for ws in "$WORK"/ws "$WORK"/ws_*; do
    [ -d "$ws" ] || continue
    for sub in build install; do
      if [ -d "$ws/$sub" ] && ! pc_made_tree "$ws/$sub"; then move_aside "$ws/$sub"; n=$((n + 1)); fi
    done
  done
  for v in sim/ros_stack/.venv analysis/layout/.venv parallel_work/20261015/vision/.venv sim/worlds/aruco_map/.venv; do
    if [ -d "$WORK/$v" ] && ! pc_made_tree "$WORK/$v"; then move_aside "$WORK/$v"; n=$((n + 1)); fi
  done
  # Stale PID files would make stop_sim.sh kill unrelated process groups on this PC.
  for f in "$WORK"/sim/run/*.pid "$WORK/sim/run/MEASURING"; do
    if [ -e "$f" ]; then move_aside "$f"; n=$((n + 1)); fi
  done
  log "moved aside: $n item(s); list: $QUARANTINE/MOVED.tsv"
  log "note: check_isolation.py now reports ws_package1b/install/.../simple_offboard as missing/changed - expected (aarch64 binary pinned in baseline_manifest.json; never edit that manifest)"
}

step_u04_geoids() {
  local g="$WORK/sim/ros_stack/geoids/egm96-5.pgm"
  if [ -f "$g" ]; then
    check_sha "$g" "$SHA_GEOID_PGM" "geoid egm96-5.pgm"
  else
    check_sha "$WORK/sim/ros_stack/egm96-5.tar.bz2" "$SHA_GEOID_TBZ" "geoid tarball egm96-5.tar.bz2"
    local tmp="$TH/.cache/bb_pc_setup/geoid_extract_$(ts)"; mkdir -p "$tmp"
    tar -xjf "$WORK/sim/ros_stack/egm96-5.tar.bz2" -C "$tmp"
    local pgm; pgm="$(find "$tmp" -name egm96-5.pgm | head -1)"
    check_sha "$pgm" "$SHA_GEOID_PGM" "extracted egm96-5.pgm"
    mkdir -p "$(dirname "$g")"; cp -p "$pgm" "$g"
  fi
  # MAVROS finds it through GEOGRAPHICLIB_GEOID_PATH=/work/sim/ros_stack/geoids (run.sh:24). Not installed
  # system-wide, like the VM. TODO-VERIFY: whether the VM also had /usr/share/GeographicLib/geoids.
  if command -v GeoidEval >/dev/null; then
    # The simulated field's origin (sim/worlds/aruco_map/default.sdf spherical_coordinates).
    log "GeoidEval test (sim origin 47.397971 8.546164): $(echo '47.397971 8.546164' | GeoidEval -n egm96-5 -d "$WORK/sim/ros_stack/geoids" 2>&1 || true)"
  fi
}

# --- exact pins (x86_64 cp312 wheels; sha256 from PyPI for these exact files). A hash mismatch means
# STOP and investigate. Never drop --require-hashes to make it pass.
pins_px4_venv() { cat <<'EOF'
cerberus==1.3.8 --hash=sha256:46c029e3e2a4735408ed36bec14ef2cbf3e50d8ebe47fb34ee1e54b2da814df2
contourpy==1.3.3 --hash=sha256:4d00e655fcef08aba35ec9610536bfe90267d7ab5ba944f7032549c55a146da1
cycler==0.12.1 --hash=sha256:85cef7cff222d8644161529808465972e51340599459b8ac3ccbac5a854e0d30
fastcrc==0.5.0 --hash=sha256:5b408763b66c86ad493ccad836348ee18adc53d5f0072ce158e783b9bbd48eba
fonttools==4.66.1 --hash=sha256:7b8ff9e0edbcee2fbf7dff0c41b9041c1901c26acf64e23adb67495012df11de --hash=sha256:7234ae9e28db64273fbbfa72caebd0a97e3bdba6b05064114741b9539ef339d0
future==1.0.0 --hash=sha256:929292d34f5872e70396626ef385ec22355a1fae8ad29e1a734c3e43f9fbc216
importlib-resources==7.1.0 --hash=sha256:1bd7b48b4088eddb2cd16382150bb515af0bd2c70128194392725f82ad2c96a1
kconfiglib==14.1.0 --hash=sha256:edcd35a20e7e138a9a9e96149027f805f785e818d2eae400b6fa8b0c8845114a
kiwisolver==1.5.1 --hash=sha256:34633ecf50d16187ab8e5528b7a2530f2feb4e23f300db4672538b51cfc5cd38
matplotlib==3.11.2 --hash=sha256:df4f7784aca81a94f254c0a2767d592ee25f407e488f5fa7203e51093fb6ca27
mpmath==1.3.0 --hash=sha256:a0b2b9fe80bbcd81a6647ff13108738cfb482d481d826cc0e02f5b35e5c88d2c
nunavut==2.3.1 --hash=sha256:c40583e9ef0e4ddadb4f1246cf6193aa2ee9d5f61e4e94eddab6d493246b4c15
pandas==3.0.6 --hash=sha256:0704044b676496b8350e023b09f174a26772456c974a2b11c36bebb558c9490d
pkgconfig==1.6.0 --hash=sha256:98e71754855e9563838d952a160eb577edabb57782e49853edb5381927e6bea1
pycryptodome==3.24.1 --hash=sha256:93619c3117a8f14ea1267b427e465d152a66c89c3d3c643262070c05b2855aae
pydsdl==1.25.0 --hash=sha256:2bc7c46813f4c3e3df928aff3546844f5f6a8400cca5e81b241c7a1e4c23ba9c
pymavlink==2.4.50 --hash=sha256:570d22774bc7e53f55a637f46b9defa78321924c6a2e50a5790fb22b0e6a0709
pyros-genmsg==0.5.8 --hash=sha256:2319ae7e66f8f3d03d13d9927cf5938131fdeaacc38cc1727c9af1b11c29a784
pyulog==1.2.4 --hash=sha256:6830f2c2649a77b00c318a3e519fe87badc8c5f45b8c21cf17a279600d5f3db6
sympy==1.14.0 --hash=sha256:e091cc3e99d2141a0ba2847328f5479b05d94a6635cb96148ccb3f34671bd8f5
toml==0.10.2 --hash=sha256:806143ae5bfb6a3c6e736a764057db0e6a0e05e338b5630894a5f779cabb4f9b
EOF
}
pins_ros_stack() { cat <<'EOF'
opencv-contrib-python-headless==4.10.0.84 --hash=sha256:89c16eb5f888aee7bf664106e12c423705d29d1b094876b66aa4e33d4e8ec905
EOF
}
pins_vision() { cat <<'EOF'
numpy==1.26.4 --hash=sha256:675d61ffbfa78604709862923189bad94014bef562cc35cf61d3a07bba02a7ed
opencv-contrib-python-headless==4.10.0.84 --hash=sha256:89c16eb5f888aee7bf664106e12c423705d29d1b094876b66aa4e33d4e8ec905
EOF
}
pins_aruco_map() { cat <<'EOF'
numpy==2.0.2 --hash=sha256:0123ffdaa88fa4ab64835dcbde75dcdf89c453c922f18dced6e27c90d1d0ec5a
opencv-contrib-python-headless==5.0.0.93 --hash=sha256:2ff190c4ebfa2839bdcaff1810061bc82f9ce5cf37e28953fb57fa5ed519b9d1 --hash=sha256:63ddadd47e36fbc903d5ac141d5c90bd305a8044188dd4936a73de80007c9e6c
EOF
}
pins_layout() { cat <<'EOF'
contourpy==1.3.0 --hash=sha256:3634b5385c6716c258d0419c46d05c8aa7dc8cb70326c9a4fb66b69ad2b52e09
cycler==0.12.1 --hash=sha256:85cef7cff222d8644161529808465972e51340599459b8ac3ccbac5a854e0d30
fonttools==4.60.2 --hash=sha256:98d0719f1b11c2817307d2da2e94296a3b2a3503f8d6252a101dca3ee663b917 --hash=sha256:73cf92eeda67cf6ff10c8af56fc8f4f07c1647d989a979be9e388a49be26552a
importlib-resources==6.5.2 --hash=sha256:789cfdc3ed28c78b67a06acb8126751ced69a3d5f79c095a98298cd8a760ccec
kiwisolver==1.4.7 --hash=sha256:693902d433cf585133699972b6d7c42a8b9f8f826ebcaf0132ff55200afc599e
matplotlib==3.9.4 --hash=sha256:173ac3748acaac21afcc3fa1633924609ba1b87749006bc25051c52c422a5d00
numpy==2.0.2 --hash=sha256:0123ffdaa88fa4ab64835dcbde75dcdf89c453c922f18dced6e27c90d1d0ec5a
packaging==26.3 --hash=sha256:d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c
pillow==11.3.0 --hash=sha256:67172f2944ebba3d4a7b54f2e95c786a3a50c21b88456329314caaa28cda70f6 --hash=sha256:676b2815362456b5b3216b4fd5bd89d362100dc6f4945154ff172e206a22c024
pyparsing==3.3.3 --hash=sha256:ece8c00a69cf01b45d0b1dedabb469c90d8caf996d4fda40f147627a122849a4
python-dateutil==2.9.0.post0 --hash=sha256:a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427
six==1.17.0 --hash=sha256:4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274
zipp==3.23.1 --hash=sha256:0b3596c50a5c700c9cb40ba8d86d9f2cc4807e9bedb06bcdf7fac85633e444dc
EOF
}

make_venv() { # path system_site(0|1) pins_function label
  local path=$1 sys=$2 pins=$3 label=$4 req
  if { [ -e "$path/$MARKER" ] || [ -e "$path/$MARKER.started" ]; } && [ -x "$path/bin/python" ]; then
    log "$label: $path exists (made on this PC); re-checking the pins"
  else
    if [ -e "$path" ]; then
      local old="$path.moved_$(ts)"; mv -T "$path" "$old"; log "$label: existing $path without PC marker moved to $old"
    fi
    if [ "$sys" = 1 ]; then /usr/bin/python3 -m venv --system-site-packages "$path"; else /usr/bin/python3 -m venv "$path"; fi
    mark_started "$path"
  fi
  req="$(mktemp)"; "$pins" > "$req"
  "$path/bin/python" -m pip install --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes -r "$req" \
    || die "$label: pip install with pinned hashes failed. Do NOT remove the hashes. Compare with
https://pypi.org/pypi/<name>/<version>/json (the cp312 manylinux x86_64 or py3-none-any wheel) and investigate."
  if ! "$path/bin/python" -m pip check --disable-pip-version-check; then
    if [ "$sys" = 1 ]; then warn "$label: pip check reports problems (system site packages are included; compare with the VM before acting)"
    else die "$label: pip check failed"; fi
  fi
  echo "created $(date -Is) on $(uname -m) by setup_wsl_ubuntu2404.sh (system_site=$sys)" > "$path/$MARKER"
  local inv; inv="$(pc_inv)"
  { "$path/bin/python" --version 2>&1; "$path/bin/python" -m pip freeze --disable-pip-version-check 2>/dev/null; } \
    > "$inv/pip_$(echo "$path" | tr '/' '_').txt"
  log "$label ok: $path ($("$path/bin/python" --version 2>&1))"
}

step_u05_venvs() {
  # ~/px4-venv: --system-site-packages like the VM (numpy 1.26.4, empy, rclpy come from apt); only the
  # 21 packages that were local to the VM venv are installed with pip. NOT the CI setup_venv.sh (numpy 2.x).
  make_venv "$TH/px4-venv" 1 pins_px4_venv "px4-venv"
  # Camera/vision chain (gz_camera_bridge.py, camera_fix.py, aruco_detect.py) - same as the VM.
  make_venv "$WORK/sim/ros_stack/.venv" 1 pins_ros_stack "ros_stack venv"
  # Former Mac-only venvs (Xcode Python 3.9 on the Mac), recreated as Linux venvs with the same package
  # versions. Python 3.9.6 -> 3.12.3 is a recorded deviation.
  make_venv "$WORK/analysis/layout/.venv" 0 pins_layout "analysis/layout venv (verifier numpy)"
  make_venv "$WORK/parallel_work/20261015/vision/.venv" 0 pins_vision "vision venv"
  make_venv "$WORK/sim/worlds/aruco_map/.venv" 0 pins_aruco_map "aruco_map venv"
  local cv; cv="$("$WORK/sim/ros_stack/.venv/bin/python" -c 'import cv2, numpy; print(cv2.__version__, numpy.__version__)')"
  [ "$cv" = "4.10.0 1.26.4" ] || die "ros_stack venv: cv2/numpy = '$cv', expected '4.10.0 1.26.4'"
  log "ros_stack venv: cv2 4.10.0 with system numpy 1.26.4 (as in the VM)"
}

px4_submodules_match_vm() {
  local px4=$1 vm pc
  vm="$(grep -E '^[ +U-]?[0-9a-f]{40} ' "$INV/px4_git.txt" | sed -E 's/^[ +U-]?([0-9a-f]{40}) ([^ ]+).*/\1 \2/' | sort)"
  pc="$(git -C "$px4" submodule status --recursive | sed -E 's/^[ +U-]?([0-9a-f]{40}) ([^ ]+).*/\1 \2/' | sort)"
  if [ "$vm" != "$pc" ]; then
    diff <(echo "$vm") <(echo "$pc") || true
    return 1
  fi
}

# PX4's Python requirements must be met exactly like in the VM BEFORE the long build (otherwise code generation
# fails half-way, or the venv silently differs). The VM venv used --system-site-packages: most modules came
# from apt python3-* packages of the VM image (installed here by r08).
px4_python_check() {
  local PX4=$1 py="$TH/px4-venv/bin/python" inv out rc=0 vmf="" f
  inv="$(pc_inv)"; out="$inv/px4_python_check_$(ts).txt"
  echo "== pip install --dry-run --no-index -r Tools/setup/requirements.txt (numpy<2 as in the VM)" > "$out"
  clean_env bash --noprofile --norc -c '"$0" -m pip install --disable-pip-version-check --dry-run --no-index \
    -r "$1" -c <(echo "numpy<2")' "$py" "$PX4/Tools/setup/requirements.txt" >> "$out" 2>&1 || rc=$?
  echo "rc=$rc" >> "$out"
  for f in "$INV"/pip__home_*px4-venv.txt; do if [ -f "$f" ]; then vmf=$f; break; fi; done
  [ -n "$vmf" ] || die "VM px4-venv pip list (pip__home_*px4-venv.txt) missing in $INV"
  python3 -I - "$PX4/Tools/setup/requirements.txt" "$vmf" "$py" >> "$out" 2>&1 <<'PY'
import re, subprocess, sys
req, vmf, py = sys.argv[1:]
key = lambda n: re.sub(r'[-_.]+', '-', n).lower()
names = [key(re.split(r'[<>=!~ ;\[]', l.strip(), 1)[0]) for l in open(req) if l.strip() and not l.startswith('#')]
vm = {key(l.split('==')[0]): l.split('==')[1].strip() for l in open(vmf) if '==' in l}
out = subprocess.run([py, '-m', 'pip', 'freeze', '--disable-pip-version-check', '--all'], capture_output=True, text=True).stdout
pc = {key(l.split('==')[0]): l.split('==')[1].strip() for l in out.splitlines() if '==' in l}
diff = [(n, vm.get(n), pc.get(n)) for n in names if vm.get(n) != pc.get(n)]
print(f'== requirements.txt names vs the VM px4-venv: {len(names)} names, {len(diff)} different')
for n, a, b in diff: print(f'DIFF {n}: VM {a} | PC {b}')
PY
  chown_user "$out"
  if ! grep -qx 'rc=0' "$out" || grep -q '^DIFF ' "$out"; then
    grep -E '^(DIFF |ERROR|rc=)' "$out" | head -30 >&2
    owner_or_allowed PY_DIFF "PX4 Python requirements differ from the VM ($out)" \
"PX4's Python requirements are not met exactly like in the VM (details: $out). Nothing was built.
Usual cause: a python3-* apt package is missing or has another version. Fix (owner, second Ubuntu window):
  sudo bash $SCRIPT_PATH step r08_px4_deps
then Claude re-runs: bash $SCRIPT_PATH step u06_px4"
  else
    log "PX4 Python requirements met, all versions equal to the VM px4-venv ($out)"
  fi
}

step_u06_px4() {
  local PX4="$TH/PX4-Autopilot" B
  B="$PX4/build/px4_sitl_default"
  [ -x "$TH/px4-venv/bin/python" ] || die "~/px4-venv missing: run step u05_venvs first"
  grep -qx "$PX4_OF_COMMIT" "$INV/px4_opticalflow_commit.txt" \
    || die "vm_inventory/px4_opticalflow_commit.txt does not contain the pinned PX4-OpticalFlow $PX4_OF_COMMIT"
  if [ ! -d "$PX4/.git" ]; then
    log "cloning PX4 $PX4_TAG with all submodules (~2.3 GB, same command as the VM's sim/02_clone_px4.sh)"
    git -c core.autocrlf=false clone --branch "$PX4_TAG" --recurse-submodules --shallow-submodules -j8 "$PX4_REPO" "$PX4"
  fi
  [ "$(git -C "$PX4" rev-parse HEAD)" = "$PX4_COMMIT" ] || die "PX4 HEAD is $(git -C "$PX4" rev-parse HEAD), expected $PX4_COMMIT"
  [ "$(git -C "$PX4" rev-parse -q --verify "refs/tags/$PX4_TAG^{commit}")" = "$PX4_COMMIT" ] || die "tag $PX4_TAG missing or not at $PX4_COMMIT"
  [ "$(git -C "$PX4/Tools/simulation/gz" rev-parse HEAD)" = "$PX4_GZ_MODELS_COMMIT" ] || die "Tools/simulation/gz is not at $PX4_GZ_MODELS_COMMIT"
  if git -C "$PX4" submodule status --recursive | grep -qE '^[-U]'; then
    git -C "$PX4" submodule status --recursive | grep -E '^[-U]'
    die "some PX4 submodules are not checked out (clone incomplete?). Fix with: git -C ~/PX4-Autopilot submodule update --init --recursive"
  fi
  px4_submodules_match_vm "$PX4" || die "PX4 submodule commits differ from the VM (vm_inventory/px4_git.txt)"
  log "PX4 $PX4_TAG = $PX4_COMMIT, submodules equal to the VM"
  px4_python_check "$PX4"

  # Airframes 4030/4031 exactly like the VM: files from /work/sim/bumblebee_model/airframes + the CMakeLists diff.
  local AF="$PX4/ROMFS/px4fmu_common/init.d-posix/airframes" a
  for a in 4030_gz_bumblebee 4031_gz_bumblebee_demo; do
    if [ -e "$AF/$a" ] && ! cmp -s "$WORK/sim/bumblebee_model/airframes/$a" "$AF/$a"; then
      local bk="$TH/PX4-Autopilot.airframe_backups/$(ts)"; mkdir -p "$bk"; mv "$AF/$a" "$bk/"; log "old $a moved to $bk"
    fi
    [ -e "$AF/$a" ] || cp -p "$WORK/sim/bumblebee_model/airframes/$a" "$AF/$a"
  done
  check_sha "$AF/4030_gz_bumblebee" "$SHA_AIRFRAME_4030" "ROMFS 4030_gz_bumblebee"
  check_sha "$AF/4031_gz_bumblebee_demo" "$SHA_AIRFRAME_4031" "ROMFS 4031_gz_bumblebee_demo"
  if git -C "$PX4" apply --check "$INV/px4_airframes_cmake.diff" 2>/dev/null; then
    git -C "$PX4" apply "$INV/px4_airframes_cmake.diff"; log "applied px4_airframes_cmake.diff"
  elif git -C "$PX4" apply --reverse --check "$INV/px4_airframes_cmake.diff" 2>/dev/null; then
    log "px4_airframes_cmake.diff already applied"
  else
    die "px4_airframes_cmake.diff neither applies nor is applied: inspect $AF/CMakeLists.txt"
  fi
  local want got
  want="$(printf '%s\n' ' M ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt' \
    '?? ROMFS/px4fmu_common/init.d-posix/airframes/4030_gz_bumblebee' \
    '?? ROMFS/px4fmu_common/init.d-posix/airframes/4031_gz_bumblebee_demo' | sort)"
  got="$(git -C "$PX4" status --porcelain | sort)"
  [ "$got" = "$want" ] || { echo "$got"; die "PX4 tree has other local changes than the VM (vm_inventory/px4_local_changes.txt)"; }

  # PX4-OpticalFlow pinned through a local mirror (same trick as the repo's simulation/trial/build_px4.sh).
  local MIRROR="$TH/.cache/bb-sim-trial/PX4-OpticalFlow.git"
  mkdir -p "$(dirname "$MIRROR")"
  [ -d "$MIRROR" ] || git clone --quiet --bare "$PX4_OF_REPO" "$MIRROR"
  git -C "$MIRROR" cat-file -e "$PX4_OF_COMMIT^{commit}" 2>/dev/null || git -C "$MIRROR" fetch --quiet origin "$PX4_OF_COMMIT"
  git -C "$MIRROR" update-ref refs/heads/master "$PX4_OF_COMMIT"
  if [ -d "$B/OpticalFlow/src/OpticalFlow/.git" ]; then
    local of_now; of_now="$(git -C "$B/OpticalFlow/src/OpticalFlow" rev-parse HEAD)"
    [ "$of_now" = "$PX4_OF_COMMIT" ] || die "the existing build used PX4-OpticalFlow $of_now, not $PX4_OF_COMMIT.
Move $B aside (mv, never delete) and re-run this step."
  fi
  # ninja would run nproc+2 jobs; WSL gets only part of the host RAM, so size the jobs by free memory
  # (PX4's Makefile passes j=N to ninja as -jN). Job count does not change the binary.
  local j; j="$(jobs_for_mem 1)"
  log "building PX4 SITL (make px4_sitl j=$j, RelWithDebInfo like the VM); PX4-OpticalFlow pinned to $PX4_OF_COMMIT"
  clean_env PYTHONDONTWRITEBYTECODE=1 GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0="url.file://$MIRROR.insteadOf" GIT_CONFIG_VALUE_0="$PX4_OF_REPO" \
    bash --noprofile --norc -c '. "$HOME/px4-venv/bin/activate" && make -C "$HOME/PX4-Autopilot" px4_sitl "j=$0"' "$j"

  # Post-build checks (same as build_px4.sh plus the airframes).
  [ -x "$B/bin/px4" ] || die "no $B/bin/px4"
  [ -e "$B/bin/px4-gz_bridge" ] || die "gz_bridge module not built"
  [ -f "$B/rootfs/gz_env.sh" ] || die "no $B/rootfs/gz_env.sh"
  [ -f "$B/src/modules/simulation/gz_plugins/libOpticalFlowSystem.so" ] || die "libOpticalFlowSystem.so not built"
  [ -f "$B/src/modules/simulation/gz_plugins/libGstCameraSystem.so" ] || warn "libGstCameraSystem.so not built (the VM built it; runs drop it with GST=0)"
  [ "$(git -C "$B/OpticalFlow/src/OpticalFlow" rev-parse HEAD)" = "$PX4_OF_COMMIT" ] || die "OpticalFlow in the build is not $PX4_OF_COMMIT"
  grep -q "$PX4_COMMIT" "$B/src/lib/version/build_git_version.h" || die "binary does not embed $PX4_COMMIT"
  log "version header: $(grep -E 'PX4_GIT_TAG_STR|PX4_GIT_VERSION_STR' "$B/src/lib/version/build_git_version.h" | tr -s ' ' | tr '\n' ' ')"
  # TODO-VERIFY: the VM printed "PX4_GIT_TAG: v1.16.1" at configure time although CMakeLists.txt was modified.
  grep -q 'PX4_GIT_TAG_STR "v1.16.1"' "$B/src/lib/version/build_git_version.h" || warn "PX4_GIT_TAG_STR is not exactly v1.16.1 - compare with ver_sw_release in the Mac preflight_05 ULog"
  check_sha "$B/etc/init.d-posix/airframes/4030_gz_bumblebee" "$SHA_AIRFRAME_4030" "built airframe 4030"
  check_sha "$B/etc/init.d-posix/airframes/4031_gz_bumblebee_demo" "$SHA_AIRFRAME_4031" "built airframe 4031"
  if git -C "$PX4" submodule status --recursive | grep -qE '^[+U]'; then die "a PX4 submodule moved during the build"; fi
  got="$(git -C "$PX4" status --porcelain | sort)"
  [ "$got" = "$want" ] || { echo "$got"; die "the build left changes in the PX4 source tree"; }
  local inv; inv="$(pc_inv)"
  { echo "$PX4_TAG"; git -C "$PX4" rev-parse HEAD; git -C "$PX4" status --porcelain; git -C "$PX4" submodule status --recursive; } > "$inv/px4_git.txt"
  git -C "$PX4" diff -- ROMFS/px4fmu_common/init.d-posix/airframes/CMakeLists.txt > "$inv/px4_airframes_cmake.diff"
  echo "$PX4_OF_COMMIT" > "$inv/px4_opticalflow_commit.txt"
  cp "$B/rootfs/gz_env.sh" "$inv/px4_gz_env.sh"
  log "PX4 SITL built and checked"
}

colcon_clean_build() { # workspace  extra-env...  -- colcon args...
  local ws=$1; shift
  local envs=() ; while [ "$#" -gt 0 ] && [ "$1" != -- ]; do envs+=("$1"); shift; done; shift
  local args; printf -v args '%q ' "$@"
  # Fresh shell with ONLY /opt/ros/jazzy sourced (like the VM's first configure). Not sourcing
  # ws_mavros214 keeps mavros_msgs 2.16.0 headers from apt, exactly as the VM builds did.
  # BB_PREFIX_FIRST (MAVROS only) is put in front of CMAKE_PREFIX_PATH after sourcing, as in the VM.
  clean_env "${envs[@]}" bash --noprofile --norc -c "set -eo pipefail; source /opt/ros/jazzy/setup.bash; set -u
    if [ -n \"\${BB_PREFIX_FIRST:-}\" ]; then export CMAKE_PREFIX_PATH=\"\$BB_PREFIX_FIRST:\${CMAKE_PREFIX_PATH:-}\"; fi
    echo \"CMAKE_PREFIX_PATH=\${CMAKE_PREFIX_PATH:-}\"; cd '$ws'; colcon $args"
}

mark_built() { local ws=$1 d; for d in build install; do echo "built $(date -Is) on $(uname -m) by setup_wsl_ubuntu2404.sh" > "$ws/$d/$MARKER"; done; }

cache_value() { { grep -h "^$2=" "$1"/build/*/CMakeCache.txt 2>/dev/null || true; } | sort -u; }

step_u07_mavros() {
  local ws="$WORK/ws_mavros214"
  need_pc_tree_or_none "$ws/build"; need_pc_tree_or_none "$ws/install"
  check_sha "$WORK/sim/ros_stack/mavros-2.14.0.tar.gz" "$SHA_MAVROS_TGZ" "MAVROS 2.14.0 tarball"
  # The source tree must be exactly the tarball (it has no .git). One file is allowed on top:
  # libmavconn's configure step (em_expand) writes include/mavconn/mavlink_dialect.hpp INTO the source tree,
  # so the VM build left it there. It is regenerated by the next configure from the pinned apt mavlink
  # 2026.9.9; it is not deleted. Every other difference stays fatal.
  local chk="$TH/.cache/bb_pc_setup/mavros_src_check" gen="$ws/src/mavros-source/libmavconn/include/mavconn/mavlink_dialect.hpp"
  if [ ! -d "$chk/mavros-2.14.0" ]; then mkdir -p "$chk"; tar -xzf "$WORK/sim/ros_stack/mavros-2.14.0.tar.gz" -C "$chk"; fi
  [ ! -e "$chk/mavros-2.14.0/libmavconn/include/mavconn/mavlink_dialect.hpp" ] || die "the tarball itself contains mavlink_dialect.hpp: re-check the exclusion"
  diff -r -x mavlink_dialect.hpp "$chk/mavros-2.14.0" "$ws/src/mavros-source" >/dev/null || die "$ws/src/mavros-source differs from mavros-2.14.0.tar.gz"
  if [ -f "$gen" ]; then log "generated (allowed) $gen sha256 $(sha_of "$gen") - from the VM build; configure regenerates it"; fi
  log "MAVROS source tree == mavros-2.14.0.tar.gz (plus the generated mavlink_dialect.hpp)"
  [ -d "$WORK/sim/ros_stack/ros_deps/opt/ros/jazzy/share/angles/cmake" ] || die "angles (ros_deps) missing"
  local j; j="$(jobs_for_mem 3)"
  log "colcon build MAVROS 2.14 (VM build line; MAKEFLAGS=-j$j, ~3 GB of free memory per job)"
  mark_started "$ws/build" "$ws/install"
  MAKEFLAGS="-j$j" colcon_clean_build "$ws" BB_PREFIX_FIRST="$WORK/sim/ros_stack/ros_deps/opt/ros/jazzy" -- \
    build --packages-up-to mavros mavros_extras --executor sequential --event-handlers console_direct- --cmake-args -DBUILD_TESTING=OFF
  [ -x "$ws/install/mavros/lib/mavros/mavros_node" ] || die "mavros_node not built"
  file -b "$ws/install/mavros/lib/mavros/mavros_node" | grep -q 'x86-64' || die "mavros_node is not x86-64"
  cache_value "$ws" angles_DIR:PATH | grep -q "$WORK/sim/ros_stack/ros_deps/opt/ros/jazzy/share/angles/cmake" || die "angles_DIR is not the ros_deps tree"
  cache_value "$ws" mavlink_DIR:PATH | grep -q '/opt/ros/jazzy/share/mavlink/cmake' || die "mavlink_DIR is not apt ros-jazzy-mavlink"
  grep -q '<version>2.14.0</version>' "$ws/install/mavros/share/mavros/package.xml" || die "installed mavros is not 2.14.0"
  mark_built "$ws"
  log "MAVROS 2.14.0 built: $(sha_of "$ws/install/mavros/lib/mavros/mavros_node")  mavros_node"
}

step_u08_ws_sitl() {
  local ws="$WORK/ws_sitl"
  need_pc_tree_or_none "$ws/build"; need_pc_tree_or_none "$ws/install"
  mark_started "$ws/build" "$ws/install"
  colcon_clean_build "$ws" -- build --packages-select bumblebee aruco_pose --event-handlers console_direct-
  cache_value "$ws" mavros_msgs_DIR:PATH | grep -qx 'mavros_msgs_DIR:PATH=/opt/ros/jazzy/share/mavros_msgs/cmake' \
    || die "ws_sitl did not build against apt mavros_msgs 2.16 (VM parity): $(cache_value "$ws" mavros_msgs_DIR:PATH).
Move build/ install/ aside and rebuild with --cmake-args -Dmavros_msgs_DIR=/opt/ros/jazzy/share/mavros_msgs/cmake"
  mark_built "$ws"
  if [ -d /repo/drone/ros2_ws/src/bumblebee ]; then
    if diff -rq "$ws/src/bumblebee" /repo/drone/ros2_ws/src/bumblebee >/dev/null; then log "ws_sitl/src/bumblebee == repo b31ca69 drone/ros2_ws/src/bumblebee"
    else warn "ws_sitl/src/bumblebee differs from /repo (record only; never rsync over it)"; fi
  fi
  log "ws_sitl built (led_msgs absent -> LED node skipped, as in the VM)"
}

step_u09_ws_package1b() {
  local ws="$WORK/ws_package1b"
  need_pc_tree_or_none "$ws/build"; need_pc_tree_or_none "$ws/install"
  # NEVER use /work/build_test.sh here: it rsyncs --delete /repo over src/ and would destroy the
  # package 1b sources, which exist ONLY in this folder (and the archive), not in git.
  mark_started "$ws/build" "$ws/install"
  colcon_clean_build "$ws" -- build --packages-select bumblebee --executor sequential --event-handlers console_direct+
  cache_value "$ws" mavros_msgs_DIR:PATH | grep -qx 'mavros_msgs_DIR:PATH=/opt/ros/jazzy/share/mavros_msgs/cmake' \
    || die "ws_package1b did not build against apt mavros_msgs 2.16 (VM parity): $(cache_value "$ws" mavros_msgs_DIR:PATH).
Move build/ install/ aside and rebuild with --cmake-args -Dmavros_msgs_DIR=/opt/ros/jazzy/share/mavros_msgs/cmake"
  local so="$ws/install/bumblebee/lib/bumblebee/simple_offboard"
  [ -x "$so" ] || die "simple_offboard not built"
  file -b "$so" | grep -q 'x86-64' || die "simple_offboard is not x86-64"
  mark_built "$ws"
  log "simple_offboard x86-64 sha256 $(sha_of "$so") (the Mac/aarch64 pin was $SHA_VM_SIMPLE_OFFBOARD_AARCH64)"
  # Tests exactly like the VM. Isolated DDS domain (96 = offline checks), loopback only, no .pyc in src.
  # TODO-VERIFY: the VM's ROS_DOMAIN_ID for colcon test is not recorded.
  local inv rc=0; inv="$(pc_inv)"
  colcon_clean_build "$ws" ROS_DOMAIN_ID=96 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 PYTHONDONTWRITEBYTECODE=1 -- \
    test --return-code-on-test-failure --packages-select bumblebee --executor sequential --event-handlers console_direct+ --ctest-args -V -j1 \
    > "$inv/ws_package1b_colcon_test.log" 2>&1 || rc=$?
  colcon_clean_build "$ws" -- test-result --test-result-base build/bumblebee/test_results --verbose > "$inv/ws_package1b_test_result.txt" 2>&1 || true
  tail -5 "$inv/ws_package1b_test_result.txt"
  [ "$rc" = 0 ] || die "colcon test failed (rc $rc): $inv/ws_package1b_colcon_test.log. Compare with the VM's last test logs in $ws/log/test_2026-10-15_* before changing anything."
  # Same number of tests as in the VM (a test that silently did not run is also a difference).
  local pc_counts; pc_counts="$(junit_counts "$ws/build/bumblebee/test_results")"
  echo "PC: $pc_counts | VM 15.10: $VM_TEST_COUNTS" > "$inv/ws_package1b_test_counts.txt"
  if [ -d "$QUARANTINE/ws_package1b/build/bumblebee/test_results" ]; then
    echo "VM (recounted from $QUARANTINE/ws_package1b/build/bumblebee/test_results): $(junit_counts "$QUARANTINE/ws_package1b/build/bumblebee/test_results")" >> "$inv/ws_package1b_test_counts.txt"
  fi
  cat "$inv/ws_package1b_test_counts.txt"
  [ "$pc_counts" = "$VM_TEST_COUNTS" ] || die "ws_package1b test counts differ from the VM: PC '$pc_counts', VM '$VM_TEST_COUNTS'.
Find out which tests ran differently (junit XML in $ws/build/bumblebee/test_results) before going on; never edit the tests."
  log "ws_package1b tests passed with the same counts as the VM 15.10 ($VM_TEST_COUNTS)"
}

junit_counts() { # dir with junit XML -> "files=N tests=N errors=N failures=N skipped=N"
  python3 -I - "$1" <<'PY'
import glob, sys, xml.etree.ElementTree as ET
t = e = f = s = 0
files = sorted(glob.glob(sys.argv[1] + '/**/*.xml', recursive=True))
for p in files:
    r = ET.parse(p).getroot()
    for x in ([r] if r.tag == 'testsuite' else r.findall('testsuite')):
        t += int(x.get('tests', 0)); e += int(x.get('errors', 0)); f += int(x.get('failures', 0))
        s += int(x.get('skipped', x.get('skip', 0)) or 0)
print(f'files={len(files)} tests={t} errors={e} failures={f} skipped={s}')
PY
}

step_u10_report() {
  local inv R; inv="$(pc_inv)"; R="$inv/ENVIRONMENT_REPORT.md"
  # Informational: everything below runs with errexit OFF so a missing tool never aborts the report.
  (
  set +e +o pipefail
  local PX4="$TH/PX4-Autopilot" B="$TH/PX4-Autopilot/build/px4_sitl_default" f wslver=""
  kv() { dpkg-query -W -f '${Version}' "$1" 2>/dev/null || echo "-"; }
  vmv() { awk -F'\t' -v p="$1" '$1==p {print $2}' "$INV/dpkg_all.tsv"; }
  dpkg-query -W -f '${Package}\t${Version}\t${Architecture}\n' | sort > "$inv/dpkg_all.tsv"
  awk -F'\t' 'NR==FNR {want[$1]=1; next} ($1 in want)' "$INV/dpkg_relevant.tsv" "$inv/dpkg_all.tsv" > "$inv/dpkg_relevant.tsv"
  gz sim --versions > "$inv/gz_versions.txt" 2>&1
  { uname -a; cat /etc/os-release; nproc; free -g; } > "$inv/system.txt"
  { findmnt -T /work; ls -l /repo; } > "$inv/mounts.txt" 2>&1
  { git -C /repo rev-parse --abbrev-ref HEAD; git -C /repo rev-parse HEAD; } > "$inv/repo_git.txt" 2>&1
  for f in "$B/bin/px4" "$B/src/modules/simulation/gz_plugins/libOpticalFlowSystem.so" \
           "$B/src/modules/simulation/gz_plugins/libGstCameraSystem.so" \
           "$WORK/ws_mavros214/install/mavros/lib/mavros/mavros_node" \
           "$WORK/ws_mavros214/install/mavros/lib/libmavros_plugins.so" \
           "$WORK/ws_mavros214/install/mavros_extras/lib/libmavros_extras_plugins.so" \
           "$WORK/ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard" \
           "$WORK/ws_sitl/install/bumblebee/lib/bumblebee/simple_offboard"; do
    if [ -f "$f" ]; then sha256sum "$f"; fi
  done > "$inv/sha256_binaries.txt"
  if [ -x /mnt/c/Windows/System32/wsl.exe ]; then wslver="$(timeout 20 /mnt/c/Windows/System32/wsl.exe --version 2>/dev/null | tr -d '\0\r')"; fi
  {
    echo "# ENVIRONMENT_REPORT - Bumblebee simulator on the Windows PC (WSL2)"
    echo
    echo "Written $(date -Is) by setup_wsl_ubuntu2404.sh step u10_report. SIMULATOR ONLY."
    echo
    echo "## Host"
    echo '```'
    uname -a; grep PRETTY_NAME /etc/os-release
    echo "CPU: $(lscpu | awk -F: '/Model name/ {gsub(/^ +/,"",$2); print $2; exit}') x $(nproc)"
    free -h | head -2; df -h /work | tail -1; echo "PID 1: $(ps -p 1 -o comm=)"
    echo "WSL networking mode: $(wsl_netmode || true) (must be nat)"
    echo "Windows drive with the WSL disk: $(windows_drive_mount) $(df -h --output=avail "$(windows_drive_mount)" 2>/dev/null | tail -1) free"
    echo; echo "wsl --version:"; echo "${wslver:-(not available here: ask the owner to paste 'wsl --version' from PowerShell)}"
    echo '```'
    echo
    echo "## GPU"
    echo '```'
    "$NVSMI" -L 2>&1; "$NVSMI" --query-gpu=name,driver_version,memory.total --format=csv 2>&1
    env DISPLAY=:0 glxinfo -B 2>&1 | grep -E 'OpenGL (vendor|renderer|core profile version)|Device:'
    echo "gpu_env.sh:"; cat "$inv/gpu_env.sh" 2>/dev/null
    echo '```'
    echo
    echo "## Key versions (PC vs VM)"
    echo
    echo "| package | PC | VM (arm64) |"; echo "|---|---|---|"
    for f in libgz-sim8 libgz-rendering8-ogre2 libogre-next-2.3.0 gz-harmonic python3-gz-transport13 ros-jazzy-ros-base \
             ros-jazzy-rclcpp ros-jazzy-rclpy ros-jazzy-fastrtps ros-jazzy-rmw-fastrtps-cpp ros-jazzy-mavros ros-jazzy-mavros-msgs \
             ros-jazzy-mavlink ros-jazzy-cv-bridge python3-numpy libopencv-dev libgl1-mesa-dri libegl-mesa0 gcc-13 cmake python3.12 \
             libgeographiclib-dev mesa-utils; do
      echo "| $f | $(kv "$f") | $(vmv "$f") |"
    done
    echo
    echo "## PX4"
    echo '```'
    echo "HEAD $(git -C "$PX4" rev-parse HEAD 2>/dev/null)"
    grep -E 'PX4_GIT_(TAG|VERSION)_STR' "$B/src/lib/version/build_git_version.h" 2>/dev/null
    echo "PX4-OpticalFlow in build: $(git -C "$B/OpticalFlow/src/OpticalFlow" rev-parse HEAD 2>/dev/null) (pinned $PX4_OF_COMMIT = the VM's build, vm_inventory/px4_opticalflow_commit.txt)"
    sha256sum "$B/etc/init.d-posix/airframes/4030_gz_bumblebee" "$B/etc/init.d-posix/airframes/4031_gz_bumblebee_demo" 2>/dev/null
    echo '```'
    echo
    echo "## MAVROS and workspaces (CMakeCache)"
    echo '```'
    for f in ws_mavros214 ws_sitl ws_package1b; do
      echo "$f:"; cache_value "$WORK/$f" mavros_msgs_DIR:PATH; cache_value "$WORK/$f" angles_DIR:PATH
      cache_value "$WORK/$f" mavlink_DIR:PATH; cache_value "$WORK/$f" CMAKE_BUILD_TYPE:STRING
    done
    echo; echo "ws_package1b tests:"; tail -3 "$inv/ws_package1b_test_result.txt" 2>/dev/null; cat "$inv/ws_package1b_test_counts.txt" 2>/dev/null
    echo '```'
    echo
    echo "## Binaries (sha256)"
    echo '```'; cat "$inv/sha256_binaries.txt"; echo "(Mac/aarch64 simple_offboard was $SHA_VM_SIMPLE_OFFBOARD_AARCH64)"; echo '```'
    echo
    echo "## Python venvs"
    echo '```'
    for f in "$TH/px4-venv" "$WORK/sim/ros_stack/.venv" "$WORK/analysis/layout/.venv" "$WORK/parallel_work/20261015/vision/.venv" "$WORK/sim/worlds/aruco_map/.venv"; do
      if [ -x "$f/bin/python" ]; then
        echo "$f: $("$f/bin/python" --version 2>&1)"
        "$f/bin/python" -m pip freeze --disable-pip-version-check 2>/dev/null | grep -iE '^(numpy|opencv|pymavlink|matplotlib|pyulog)=' | sed 's/^/    /'
      fi
    done
    echo '```'
    echo
    echo "## Expected differences from the Mac VM (by design, not parity failures)"
    echo
    echo "- Architecture x86_64 vs aarch64: every binary hash differs; float results are not bit-identical."
    echo "- Renderer: the VM used llvmpipe (CPU). Here: see gpu_and_parity_check.sh (GPU d3d12 vs llvmpipe control)."
    echo "- Former Mac venvs: Python 3.9.6 -> 3.12.3 with the same package versions."
    echo "- check_isolation.py: ws_package1b/install/bumblebee/lib/bumblebee/simple_offboard differs (aarch64 pin in baseline_manifest.json; never edit it)."
    echo "- frozen_inputs_03.json cannot verify PC runs: a NEW frozen_inputs_NN.json (freeze_pins.py) is needed before the first PC trial."
    echo "- ros2-apt-source, fluxbox, x11vnc, novnc, websockify are not installed (snapshot repo; WSLg display)."
    echo "- MAVROS source tree: libmavconn/include/mavconn/mavlink_dialect.hpp is generated by configure (not in the tarball)."
    echo
    echo "## Owner-accepted deviations"
    echo
    if [ -f "$DEVIATIONS" ]; then grep '^- ' "$DEVIATIONS"; else echo "none"; fi
    echo
    echo "Detailed comparison with vm_inventory: bash $HERE/gpu_and_parity_check.sh versions"
  } > "$R"
  )
  if [ -f "$DEVIATIONS" ]; then cp "$DEVIATIONS" "$inv/DEVIATIONS.md"; fi
  log "written $R"
  bash "$HERE/gpu_and_parity_check.sh" versions || warn "version comparison reported a problem (see its output)"
  cat <<EOF2

USER PHASE DONE. Next (Claude): bash $HERE/gpu_and_parity_check.sh all   (about 15-25 min: use run_in_background)
EOF2
}

# ---------------------------------------------------------------- runner
declare -A DESC=(
  [r01_host]="host checks" [r02_dirs]="/work, ~/bbsim-work, /repo" [r03_apt_ubuntu]="Ubuntu snapshot apt source + newer-package check"
  [r04_gpu]="mesa-utils + display + GPU check" [r05_ros_repo]="ROS 2 snapshot repo + apt dry run" [r06_gazebo]="Gazebo 8.15.0 pinned + hold"
  [r07_ros]="ROS 2 Jazzy packages" [r08_px4_deps]="PX4 build deps + python3 modules" [r09_tools]="tools" [r10_record]="record + .deb backup"
  [u01_host_gpu]="host + GPU check (user)" [u02_inputs]="restored inputs" [u03_quarantine]="move foreign builds aside"
  [u04_geoids]="geoid egm96-5" [u05_venvs]="Python venvs" [u06_px4]="PX4 v1.16.1 SITL build" [u07_mavros]="MAVROS 2.14.0"
  [u08_ws_sitl]="ws_sitl" [u09_ws_package1b]="ws_package1b build + test" [u10_report]="ENVIRONMENT_REPORT"
)

run_step() {
  local name=$1 lg rc
  declare -F "step_$name" >/dev/null || die "unknown step '$name' (see: $0 list)"
  case "$name" in
    r*) is_root || need_owner "Step $name needs root. Owner, in a SECOND Ubuntu window (not Claude's window; type the password there): sudo bash $SCRIPT_PATH step $name" ;;
    u*) is_root && die "step $name must run as the normal user, not with sudo" ;;
  esac
  lg="$LOGDIR/$(ts)_$name.log"
  echo; echo "==================== STEP $name: ${DESC[$name]} ===================="
  ( set -Eeuo pipefail; trap 'echo "[setup] failed at line $LINENO: $BASH_COMMAND" >&2' ERR; "step_$name" ) 2>&1 | tee -a "$lg"
  rc=${PIPESTATUS[0]}
  is_root && chown "$TU:$TG" "$lg" 2>/dev/null
  if [ "$rc" != 0 ]; then
    echo "==================== STEP $name FAILED (exit $rc). Log: $lg" >&2
    echo "Fix the cause, then re-run only this step: bash $SCRIPT_PATH step $name  (r* steps with sudo)" >&2
    [ "$name" = "${name#r}" ] || echo "Владельцу: шаг $name не прошёл. Скопируйте последние строки и отправьте их Claude." >&2
    exit "$rc"
  fi
  echo "==================== STEP $name OK (log $lg)"
}

usage() { sed -n '2,/^$/p' "$SCRIPT_PATH"; }

main() {
  local cmd=${1:-}
  case "$cmd" in
    root)
      is_root || need_owner "Owner, in a SECOND Ubuntu window (not Claude's window; type the password there): sudo bash $SCRIPT_PATH root"
      cat <<'EOF'
======================================================================
 Установка системной части симулятора (один раз).
 Займёт 30-90 минут, зависит от интернета. Не закрывайте это окно
 и окно с Claude, пока не появится слово ГОТОВО.
 Что меняется в Ubuntu (WSL) надолго:
  - пакеты берутся из «замороженных» снимков, как в ВМ на Mac:
    Ubuntu - снимок 17.10, ROS - снимок 05.10
    (обычные обновления Ubuntu в этой WSL отключены, файлы перенесены
    в /etc/apt/sources-disabled, ничего не удалено);
  - пакеты Gazebo закреплены (apt-mark hold);
  - скачанные .deb сохраняются в ~/apt_debs_20261017.
 К дрону и моторам эта установка отношения не имеет.
======================================================================
EOF
      local s; for s in "${ROOT_STEPS[@]}"; do run_step "$s"; done ;;
    user)
      local s; for s in "${USER_STEPS[@]}"; do run_step "$s"; done ;;
    step)
      shift; [ "$#" -gt 0 ] || die "usage: $0 step NAME [NAME...]"
      local s; for s in "$@"; do run_step "$s"; done ;;
    check)
      ( set -Eeuo pipefail; host_checks
        if command -v glxinfo >/dev/null; then echo "renderer: $(gl_renderer)"; else echo "glxinfo not installed yet (root phase step r04)"; fi ) ;;
    list)
      local s; for s in "${ROOT_STEPS[@]}" "${USER_STEPS[@]}"; do printf '%-18s %s\n' "$s" "${DESC[$s]}"; done ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
