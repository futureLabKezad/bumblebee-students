#!/usr/bin/env python3
"""One-off (Claude 09.11): make run_scenario3.sh = run_scenario2.sh + test «упал только скрипт».
New keys: --kill-script-on PATTERN  (SIGKILL the script session only, when PATTERN first appears in script.log)
          --after-kill-s N          (keep PX4, Gazebo and all ROS nodes running and recorded N s after the kill; default 30)
Nothing else changes. run_scenario2.sh stays as it is."""
src = '/work/goal_step5b_20261109/run_scenario2.sh'
dst = '/work/goal_step5b_20261109/run_scenario3.sh'
s = open(src).read()


def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (old, s.count(old))
    s = s.replace(old, new)


rep('# Usage: bash run_scenario2.sh TAG AIRFRAME SCRIPT [--gui] [--timeout S] [--trial-aruco-always] [--trial-map-file]',
    '# Usage: bash run_scenario3.sh TAG AIRFRAME SCRIPT [--gui] [--timeout S] [--trial-aruco-always] [--trial-map-file]\n'
    '# Edition 3 (09.11, Claude): run_scenario2.sh + test «упал только скрипт»: --kill-script-on PATTERN sends SIGKILL to the\n'
    '#   script session only (the example script and its wrappers) when PATTERN first appears in script.log; PX4, Gazebo,\n'
    '#   MAVROS and all image ROS nodes keep running; --after-kill-s N (default 30) keeps recording N s after the kill.')
rep('    --end-if-idle) END_IF_IDLE=$2; shift ;;',
    '    --end-if-idle) END_IF_IDLE=$2; shift ;;\n'
    '    --kill-script-on) KILL_PAT=$2; shift ;;      # edition 3\n'
    '    --after-kill-s) AFTER_KILL_S=$2; shift ;;    # edition 3')
rep('END_AFTER_DISARM=15; END_IF_IDLE=60     # 5b', 'END_AFTER_DISARM=15; END_IF_IDLE=60; KILL_PAT=""; AFTER_KILL_S=30; KILLED=0     # 5b; ed.3')
rep('flock -n 9 || { echo "REFUSE: another run_scenario2.sh run holds', 'flock -n 9 || { echo "REFUSE: another run_scenario2/3.sh run holds')
rep('cp $STEP5B/run_scenario2.sh $STEP5/scenario_stack.launch.py "$RUN/snapshot/"',
    'cp $STEP5B/run_scenario2.sh $STEP5B/run_scenario3.sh $STEP5/scenario_stack.launch.py "$RUN/snapshot/"')
rep('(cd "$SNAP" && sha256sum run_scenario2.sh scenario_stack.launch.py', '(cd "$SNAP" && sha256sum run_scenario2.sh run_scenario3.sh scenario_stack.launch.py')
rep('''while kill -0 $SPID 2>/dev/null; do
  sleep 1
''', '''while kill -0 $SPID 2>/dev/null; do
  sleep 1
  if [ -n "$KILL_PAT" ] && [ $KILLED = 0 ] && grep -q -- "$KILL_PAT" "$RUN/script.log" 2>/dev/null; then   # edition 3
    KILLED=1; KILL_T=$(date +%s.%N)
    kill -KILL -- -"$(cat "$RUN/script.pid")" 2>/dev/null
    echo "{\\"kind\\": \\"script_killed\\", \\"wall\\": $KILL_T, \\"pattern\\": \\"$KILL_PAT\\", \\"signal\\": \\"KILL\\", \\"target\\": \\"script session only\\"}" > "$RUN/script_kill.json"
    echo "$(date -Is) killed by launcher (test «упал только скрипт»): SIGKILL to script session on pattern '$KILL_PAT'" > "$RUN/script_end.txt"
    echo "SCRIPT KILLED $(date -Is) on pattern '$KILL_PAT'; nodes kept; recording ${AFTER_KILL_S}s more"
    break
  fi
''')
rep('''wait $SPID; SCRIPT_RC=$?
''', '''wait $SPID; SCRIPT_RC=$?
if [ $KILLED = 1 ]; then   # edition 3: PX4, Gazebo and all ROS nodes stay alive and recorded
  sleep "$AFTER_KILL_S"
  echo "after-kill window ${AFTER_KILL_S}s done $(date -Is); alive: px4 $(pgrep -x px4 | wc -l), mavros_node $(pgrep -x mavros_node | wc -l), simple_offboard $(pgrep -x simple_offboard | wc -l)"
  echo "last state: $(grep '"kind": "state"' "$RUN/events.jsonl" 2>/dev/null | tail -1)"
fi
''')
rep('echo "ТОЛЬКО СИМУЛЯТОР: scenario $TAG', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.3 kill_script_on=${KILL_PAT:-none} after_kill_s=$AFTER_KILL_S): scenario $TAG')
open(dst, 'x').write(s)
print('ok')
