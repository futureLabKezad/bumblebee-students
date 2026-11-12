#!/usr/bin/env python3
"""One-off (Claude 09.11): run_scenario5.sh = run_scenario4.sh +
  --image r2d                      (/work/fixed_image_r2d_20261109, manifest image_manifest_r2.tsv of r2d)
  disk guard                       (REFUSE when /mnt/c has < 8 GB free; АРХИТЕКТУРА_РАБОТЫ.md §8)
  rc_hold2.py                      (pilot take-over: CH6 -> Position when RUN/pilot_pos exists)
  --pilot-pos-on PATTERN [--pilot-pos-nth N]   (touch RUN/pilot_pos when PATTERN has appeared N times in script.log;
                                    then, after the script ends, keep recording --after-kill-s s, like the kill test)
run_scenario2/3/4.sh stay as they are."""
src = '/work/goal_step5b_20261109/run_scenario4.sh'
dst = '/work/goal_step5b_20261109/run_scenario5.sh'
s = open(src).read()


def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (old, s.count(old))
    s = s.replace(old, new)


rep('# Usage: bash run_scenario4.sh', '# Usage: bash run_scenario5.sh')
rep('# Edition 4 (09.11, Claude)', '# Edition 5 (09.11, Claude): ed.4 + --image r2d, disk guard (<8 GB free on C: = REFUSE), rc_hold2 + --pilot-pos-on PATTERN [--pilot-pos-nth N].\n# Edition 4 (09.11, Claude)')
rep('    --model) MODEL=$2; shift ;;                  # edition 4',
    '    --model) MODEL=$2; shift ;;                  # edition 4\n'
    '    --pilot-pos-on) PILOT_PAT=$2; shift ;;       # edition 5\n'
    '    --pilot-pos-nth) PILOT_NTH=$2; shift ;;      # edition 5')
rep('KILLED=0; MODEL=', 'KILLED=0; PILOT_PAT=""; PILOT_NTH=1; PILOT_DONE=0; MODEL=')
rep('[ "$IMAGE" = r2c ] && R2=/work/fixed_image_r2c_20261109;',
    '[ "$IMAGE" = r2c ] && R2=/work/fixed_image_r2c_20261109; [ "$IMAGE" = r2d ] && R2=/work/fixed_image_r2d_20261109;')
rep('case $AF in ', 'FREE_G=$(df --output=avail -B1G /mnt/c | tail -1 | tr -d " ")   # ed.5 disk guard\n'
    '[ "${FREE_G:-0}" -ge 8 ] || { echo "REFUSE: disk C: free ${FREE_G}G < 8G (АРХИТЕКТУРА_РАБОТЫ.md §8)"; exit 2; }\n'
    'case $AF in ')
rep('cp $STEP5/tools/rc_hold.py $STEP5/tools/goal_eval.py "$RUN/snapshot/tools/"',
    'cp $STEP5/tools/rc_hold.py $STEP5B/tools/rc_hold2.py $STEP5/tools/goal_eval.py "$RUN/snapshot/tools/"')
rep('setsid $PY -I $SNAP/tools/rc_hold.py "$RUN"', 'setsid $PY -I $SNAP/tools/rc_hold2.py "$RUN"')
rep('''  if [ -n "$KILL_PAT" ] && [ $KILLED = 0 ]''', '''  if [ -n "$PILOT_PAT" ] && [ $PILOT_DONE = 0 ] && [ "$(grep -c -- "$PILOT_PAT" "$RUN/script.log" 2>/dev/null)" -ge "$PILOT_NTH" ]; then   # edition 5
    PILOT_DONE=1; touch "$RUN/pilot_pos"
    echo "{\\"kind\\": \\"pilot_pos_request\\", \\"wall\\": $(date +%s.%N), \\"pattern\\": \\"$PILOT_PAT\\", \\"nth\\": $PILOT_NTH}" > "$RUN/pilot_pos.json"
    echo "PILOT TAKES POSITION $(date -Is) on pattern '$PILOT_PAT' #$PILOT_NTH"
  fi
  if [ -n "$KILL_PAT" ] && [ $KILLED = 0 ]''')
rep('if [ $KILLED = 1 ]; then   # edition 3', 'if [ $KILLED = 1 ] || [ $PILOT_DONE = 1 ]; then   # edition 3 (+ ed.5 pilot take-over)')
rep('echo "ТОЛЬКО СИМУЛЯТОР (ed.4', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.5 image=$IMAGE pilot_pos_on=${PILOT_PAT:-none}#$PILOT_NTH; ed.4')
rep('sha256sum run_scenario2.sh run_scenario3.sh run_scenario4.sh', 'sha256sum run_scenario2.sh run_scenario3.sh run_scenario4.sh run_scenario5.sh')
rep('$STEP5B/run_scenario4.sh $STEP5/scenario_stack.launch.py', '$STEP5B/run_scenario4.sh $STEP5B/run_scenario5.sh $STEP5/scenario_stack.launch.py')
open(dst, 'x').write(s)
print('ok')
