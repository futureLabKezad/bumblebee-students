#!/bin/bash
# ТОЛЬКО ПК (PC ONLY), no simulator, no drone. Control check for finding F4 - goal step 5b, Claude, 09.11.2026.
# Question: why does a flight script not exit by itself after its last line (s04, 06.11)?
# Suspected mechanism (by code): drone._init() starts the ROS spin thread with daemon=False (drone.py:802-803) and
# registers drone._shutdown() with atexit (drone.py:806). CPython joins non-daemon threads BEFORE it runs atexit
# handlers, so the spin thread (stopped only by _shutdown) keeps the interpreter alive for ever.
# Control: the image's drone.py, unmodified, imported from the image folder; 4 tiny programs, each in its own session:
#   A  _init(); end of program                         -> expected: hangs (killed by this test after 15 s)
#   B  _init(); _shutdown(); end of program            -> expected: exits by itself (code 0)
#   C  enable_safe_interrupt(); _init(); end; SIGINT    -> expected: still hangs (Ctrl+C is swallowed by the handler)
#   D  _init(); sys.exit(1) (as `exit(1)` in the marker scripts after a failed check) -> expected: hangs
# Each program is stopped by this test with SIGTERM to ITS OWN process group only. ROS domain 83, localhost only.
# Usage: bash f4_control.sh OUT_DIR   (OUT_DIR must not exist)
set -uo pipefail
OUT=${1:?OUT_DIR}
[ -e "$OUT" ] && { echo "REFUSE: $OUT exists"; exit 2; }
for x in px4 gz ruby mavros_node; do pgrep -x $x > /dev/null && { echo "REFUSE: $x alive (simulator running)"; exit 2; }; done
mkdir -p "$OUT"
exec > >(tee -a "$OUT/f4_control.txt") 2>&1
set +u
source /opt/ros/jazzy/setup.bash
source /work/ws_sitl/install/setup.bash
for p in libmavconn mavros_msgs mavros_extras; do source /work/ws_mavros214/install/$p/share/$p/package.bash; done
source /work/ws_mavros214_bp02_rel/install/local_setup.bash
source /work/ws_package1b_port_03/install/local_setup.bash
set -u
export ROS_DOMAIN_ID=83 ROS_LOCALHOST_ONLY=1 FASTDDS_BUILTIN_TRANSPORTS=UDPv4 PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=/work/ws_package1b_port_03/src/bumblebee/examples:${PYTHONPATH:-}
echo "F4 control $(date -Is); drone.py sha256 $(sha256sum < /work/ws_package1b_port_03/src/bumblebee/examples/drone.py | cut -c1-64)"
echo "python $(/usr/bin/python3 -V 2>&1)"
run_case() { # name sigint(0/1) code
  local name=$1 sigint=$2 code=$3
  setsid /usr/bin/python3 -u -c "$code" > "$OUT/case_$name.log" 2>&1 < /dev/null &
  local pid=$! t0; t0=$(date +%s%N)
  local state="exited"
  for i in $(seq 150); do
    kill -0 $pid 2>/dev/null || break
    [ $sigint = 1 ] && [ $i = 60 ] && { kill -INT $pid; echo "  $name: SIGINT sent at 6 s"; }
    sleep 0.1
  done
  if kill -0 $pid 2>/dev/null; then
    state="STILL RUNNING after 15 s (threads: $(ls /proc/$pid/task | wc -l))"
    kill -TERM -- -$pid 2>/dev/null; sleep 1; kill -KILL -- -$pid 2>/dev/null
    wait $pid 2>/dev/null; rc=$?
  else
    wait $pid; rc=$?
  fi
  local dt=$(( ($(date +%s%N) - t0) / 100000000 ))
  printf '  case %s: %s, exit code %s, %d.%d s\n' "$name" "$state" "$rc" $((dt / 10)) $((dt % 10))
  sed 's/^/      /' "$OUT/case_$name.log" | head -8
}
PRE='import sys, threading, drone
print("drone module:", drone.__file__)'
run_case A 0 "$PRE
drone._init()
print('spin thread daemon:', drone._spin_thread.daemon, '| last line of the program')"
run_case B 0 "$PRE
drone._init()
drone._shutdown()
print('last line of the program (after _shutdown)')"
run_case C 1 "$PRE
drone._init()
drone.enable_safe_interrupt()
print('last line of the program; waiting for SIGINT')"
run_case D 0 "$PRE
drone._init()
print('sys.exit(1) now')
sys.exit(1)"
echo "done $(date -Is)"
