#!/bin/bash
# Mac-side launcher for one flight_trial_03 run (field_measurements_01 candidate). SIMULATOR ONLY.
#   host_run.sh TAG SCENARIO [VIEW]
# Keeps the Mac awake for the run (caffeinate -i: no idle sleep, only while the run lasts, no setting
# changed), records power state, and afterwards checks the macOS power log for any sleep inside the
# run window: a host sleep freezes the VM and makes the run INVALID (see RTF_MIN.md, preflight_04).
set -u
TAG=${1:?TAG}; SCENARIO=${2:?SCENARIO}; VIEW=${3:-paused}
WORK="/Users/arsenij/Documents/Bumbl code/bbsim-work"; OUT="$WORK/sim/runs/$TAG"
L=~/.local/lima/bin/limactl
START=$(date '+%Y-%m-%d %H:%M:%S %z'); START_EPOCH=$(date +%s)
POWER_BEFORE=$(pmset -g batt | tr '\n' ' '); LPM_BEFORE=$(pmset -g | awk '/lowpowermode/ {print $2}')
caffeinate -i -m "$L" shell --workdir /work bbsim -- env TAG="$TAG" SCENARIO="$SCENARIO" VIEW="$VIEW" \
  BB_COMBINED_ROOT=${BB_COMBINED_ROOT:-/work/parallel_work/20261015/integration/combined_03} \
  ${BB_EXTRA_ENV:-} bash /work/parallel_work/20261015/integration/flight_trial_03/run.sh
RC=$?
END=$(date '+%Y-%m-%d %H:%M:%S %z'); END_EPOCH=$(date +%s)
POWER_AFTER=$(pmset -g batt | tr '\n' ' '); LPM_AFTER=$(pmset -g | awk '/lowpowermode/ {print $2}')
SLEEPS=$(pmset -g log | awk -v s="$(date -r "$START_EPOCH" '+%Y-%m-%d %H:%M:%S')" -v e="$(date -r "$END_EPOCH" '+%Y-%m-%d %H:%M:%S')" \
  '{t=$1" "$2} t>=s && t<=e && /Entering Sleep|Wake from|DarkWake from/ {print}' | head -20)
mkdir -p "$OUT"
python3 -I - "$OUT/host_check.json" "$TAG" "$SCENARIO" "$VIEW" "$RC" "$START" "$END" "$POWER_BEFORE" "$POWER_AFTER" "$LPM_BEFORE" "$LPM_AFTER" "$SLEEPS" <<'PY'
import json, sys
(out, tag, scen, view, rc, start, end, pb, pa, lb, la, sleeps) = sys.argv[1:]
rows = [l for l in sleeps.splitlines() if l.strip()]
json.dump({'tag': tag, 'scenario': scen, 'view': view, 'runner_exit': int(rc), 'host_start': start, 'host_end': end,
           'power_before': pb.strip(), 'power_after': pa.strip(), 'low_power_mode_before': lb, 'low_power_mode_after': la,
           'host_sleep_events': rows, 'host_awake_whole_run': not rows,
           'note': 'host_awake_whole_run=false makes the run INVALID regardless of its result'},
          open(out, 'w'), indent=2)
print(json.dumps({'tag': tag, 'runner_exit': int(rc), 'host_awake_whole_run': not rows, 'low_power_mode': [lb, la]}))
PY
exit $RC
