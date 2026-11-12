#!/bin/bash
# ТОЛЬКО ПК (PC ONLY). Test of the pkill stand-in with dummy processes - goal step 5b, Claude, 09.11.2026.
# Starts its own dummy processes (sleep / python sleep with a chosen argv), calls the stand-in, checks who survived,
# then stops ONLY the dummies it started, by their PIDs. Never uses pkill / pgrep -f.
# Usage: bash test_standin.sh OUT_DIR   (OUT_DIR must not exist)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
STANDIN=$HERE/bin/pkill
OUT=${1:?OUT_DIR}
[ -e "$OUT" ] && { echo "REFUSE: $OUT exists"; exit 2; }
mkdir -p "$OUT"
LOG=$OUT/standin_calls.jsonl
REPORT=$OUT/test_report.txt
exec > >(tee -a "$REPORT") 2>&1
echo "stand-in test $(date -Is); stand-in sha256 $(sha256sum < "$STANDIN" | cut -c1-64)"
PAT=aruco_pose/aruco_map
alive() { kill -0 "$1" 2>/dev/null && echo alive || echo dead; }
FAIL=0
check() { # name pid expected
  local got; got=$(alive "$2")
  if [ "$got" = "$3" ]; then echo "  OK   $1 (pid $2): $got"; else echo "  FAIL $1 (pid $2): $got, expected $3"; FAIL=1; fi
}

# 1. dummy OUTSIDE the run: its own session, command line contains the pattern exactly like the C++ node would
setsid bash -c 'exec -a /dummy/install/aruco_pose/lib/aruco_pose/aruco_map sleep 300' < /dev/null > /dev/null 2>&1 &
sleep 0.5
OUTSIDE_PID=$(ps -eo pid,sid,args | awk '$3=="/dummy/install/aruco_pose/lib/aruco_pose/aruco_map" && $1==$2 {print $1}' | head -1)
echo "outside dummy pid $OUTSIDE_PID (own session)"

# 2. the "run session": a session leader that starts 3 dummies and calls the stand-in like drone.py does
cat > "$OUT/run_session.sh" <<EOF
#!/bin/bash
export BB_STANDIN_SID=\$\$ BB_STANDIN_LOG=$LOG
export PATH=$HERE/bin:\$PATH
bash -c 'exec -a /dummy/install/aruco_pose/lib/aruco_pose/aruco_map sleep 300' &
echo "inside_match \$!" > $OUT/pids.txt
sleep 301 &
echo "inside_nomatch \$!" >> $OUT/pids.txt
/usr/bin/python3 -c 'import time; time.sleep(302)' --ros-args -r map_markers:=aruco_map/map -r map_pose:=aruco_map/pose &
echo "inside_aruco_detect_like \$!" >> $OUT/pids.txt
sleep 0.5
echo "which pkill: \$(command -v pkill)" > $OUT/which.txt
pkill -f $PAT > $OUT/standin_stdout.txt 2> $OUT/standin_stderr.txt; echo "call1 \$?" > $OUT/exit_codes.txt
pkill -f $PAT >> $OUT/standin_stdout.txt 2>> $OUT/standin_stderr.txt; echo "call2_nomatch \$?" >> $OUT/exit_codes.txt
pkill -f 'aruco_.*map' >> $OUT/standin_stdout.txt 2>> $OUT/standin_stderr.txt; echo "call3_regex \$?" >> $OUT/exit_codes.txt
pkill -x sleep >> $OUT/standin_stdout.txt 2>> $OUT/standin_stderr.txt; echo "call4_other_form \$?" >> $OUT/exit_codes.txt
BB_STANDIN_SID=1 pkill -f $PAT >> $OUT/standin_stdout.txt 2>> $OUT/standin_stderr.txt; echo "call5_wrong_sid \$?" >> $OUT/exit_codes.txt
sleep 0.5
touch $OUT/session_done
sleep 30
EOF
setsid bash "$OUT/run_session.sh" < /dev/null > "$OUT/run_session.out" 2>&1 &
SESSION_LEADER=$!
for _ in $(seq 40); do [ -e "$OUT/session_done" ] && break; sleep 0.25; done
echo "which: $(cat "$OUT/which.txt")"
echo "exit codes:"; sed 's/^/  /' "$OUT/exit_codes.txt"
echo "stand-in stdout bytes $(wc -c < "$OUT/standin_stdout.txt"), stderr bytes $(wc -c < "$OUT/standin_stderr.txt")"
IN_MATCH=$(awk '$1=="inside_match"{print $2}' "$OUT/pids.txt")
IN_NOMATCH=$(awk '$1=="inside_nomatch"{print $2}' "$OUT/pids.txt")
IN_DETECT=$(awk '$1=="inside_aruco_detect_like"{print $2}' "$OUT/pids.txt")
echo "survival:"
check "inside run session, cmdline has the pattern" "$IN_MATCH" dead
check "inside run session, other cmdline" "$IN_NOMATCH" alive
check "inside run session, aruco_detect-like remaps (aruco_map/map)" "$IN_DETECT" alive
check "OUTSIDE the run session, cmdline has the pattern" "$OUTSIDE_PID" alive
grep -q '^call1 0$' "$OUT/exit_codes.txt" || { echo "  FAIL call1 exit"; FAIL=1; }
grep -q '^call2_nomatch 1$' "$OUT/exit_codes.txt" || { echo "  FAIL call2 exit"; FAIL=1; }
grep -q '^call3_regex 2$' "$OUT/exit_codes.txt" || { echo "  FAIL call3 exit"; FAIL=1; }
grep -q '^call4_other_form 2$' "$OUT/exit_codes.txt" || { echo "  FAIL call4 exit"; FAIL=1; }
grep -q '^call5_wrong_sid 3$' "$OUT/exit_codes.txt" || { echo "  FAIL call5 exit"; FAIL=1; }
[ "$(wc -c < "$OUT/standin_stdout.txt")" = 0 ] && [ "$(wc -c < "$OUT/standin_stderr.txt")" = 0 ] || { echo "  FAIL stand-in printed something"; FAIL=1; }
# outside-session match must be listed as untouched in call 1
python3 - "$LOG" "$OUTSIDE_PID" <<'PY' || FAIL=1
import json, sys
recs = [json.loads(l) for l in open(sys.argv[1])]
c1 = recs[0]
out = [e['pid'] for e in c1.get('matched_outside_session_untouched', [])]
ok = int(sys.argv[2]) in out and len(c1.get('signalled', [])) == 1
print('  %s call1 log: signalled %s, outside untouched %s' % ('OK  ' if ok else 'FAIL', c1.get('signalled'), out))
sys.exit(0 if ok else 1)
PY
# cleanup: only the dummies this test started, by PID
for p in $IN_NOMATCH $IN_DETECT $OUTSIDE_PID; do kill "$p" 2>/dev/null; done
kill -- -"$SESSION_LEADER" 2>/dev/null
sleep 0.5
echo "after cleanup: $(for p in $IN_MATCH $IN_NOMATCH $IN_DETECT $OUTSIDE_PID $SESSION_LEADER; do echo -n "$p:$(alive $p) "; done)"
[ $FAIL = 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $FAIL
