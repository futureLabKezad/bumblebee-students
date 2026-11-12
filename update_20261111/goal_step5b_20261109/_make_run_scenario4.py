#!/usr/bin/env python3
"""One-off (Claude 09.11): make run_scenario4.sh = run_scenario3.sh + T22 model edition as the DEFAULT (chat 1: all runs on model_v1).
  default model  /work/goal_t22_flow_20261109/model_v1/bumblebee   (flow 62.5 Hz)
  default plugin /work/goal_t22_flow_20261109/plugin_v1/libOpticalFlowSystemT22.so (rate limiter off)
  --model DIR / --flow-plugin FILE|stock  to choose another model / the stock PX4 plugin (comparisons only)
  policy snapshot: /work/goal_t22_flow_20261109/sim_only_t22.json (params as sim_only_r2.json + model_differences M-T22)
run_scenario2.sh and run_scenario3.sh stay as they are."""
src = '/work/goal_step5b_20261109/run_scenario3.sh'
dst = '/work/goal_step5b_20261109/run_scenario4.sh'
s = open(src).read()


def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (old, s.count(old))
    s = s.replace(old, new)


T22 = '/work/goal_t22_flow_20261109'
rep('# Usage: bash run_scenario3.sh', '# Usage: bash run_scenario4.sh')
rep('# Edition 3 (09.11, Claude)', '# Edition 4 (09.11, Claude): edition 3 + T22 model_v1 / plugin_v1 by default (--model DIR, --flow-plugin FILE|stock).\n# Edition 3 (09.11, Claude)')
rep('    --kill-script-on) KILL_PAT=$2; shift ;;      # edition 3',
    '    --kill-script-on) KILL_PAT=$2; shift ;;      # edition 3\n'
    '    --model) MODEL=$2; shift ;;                  # edition 4\n'
    '    --flow-plugin) FLOWPLUG=$2; shift ;;         # edition 4 (stock = PX4 libOpticalFlowSystem.so)')
rep('KILL_PAT=""; AFTER_KILL_S=30; KILLED=0     # 5b; ed.3',
    f'KILL_PAT=""; AFTER_KILL_S=30; KILLED=0; MODEL={T22}/model_v1/bumblebee; FLOWPLUG={T22}/plugin_v1/libOpticalFlowSystemT22.so     # 5b; ed.3; ed.4')
rep('cp $STEP5B/sim_only_r2.json "$RUN/snapshot/sim_only.json"', f'cp {T22}/sim_only_t22.json "$RUN/snapshot/sim_only.json"   # ed.4')
rep('sha256sum run_scenario2.sh run_scenario3.sh scenario_stack.launch.py', 'sha256sum run_scenario2.sh run_scenario3.sh run_scenario4.sh scenario_stack.launch.py')
rep('cp $STEP5B/run_scenario2.sh $STEP5B/run_scenario3.sh $STEP5/scenario_stack.launch.py "$RUN/snapshot/"',
    'cp $STEP5B/run_scenario2.sh $STEP5B/run_scenario3.sh $STEP5B/run_scenario4.sh $STEP5/scenario_stack.launch.py "$RUN/snapshot/"')
rep('  echo "model_sdf $(sha256sum < $STEP4/model/bumblebee/model.sdf | cut -c1-64)"',
    '  echo "model_sdf $MODEL $(sha256sum < $MODEL/model.sdf | cut -c1-64)"\n'
    '  [ "$FLOWPLUG" = stock ] && echo "flow_plugin stock" || echo "flow_plugin $FLOWPLUG $(sha256sum < $FLOWPLUG | cut -c1-64)"')
rep('cp -r $STEP4/model/bumblebee /work/sim/models/bb_floor_noise "$RUN/models/"',
    '[ "$(basename $MODEL)" = bumblebee ] || { echo "REFUSE: --model folder must be named bumblebee"; exit 2; }\n'
    'cp -r $MODEL /work/sim/models/bb_floor_noise "$RUN/models/"')
rep('export GZ_SIM_SERVER_CONFIG_PATH=$RUN/server.config\n',
    'if [ "$FLOWPLUG" != stock ]; then [ -f "$FLOWPLUG" ] || { echo "REFUSE: no $FLOWPLUG"; exit 2; }; '
    'sed -i "s|filename=\\"libOpticalFlowSystem.so\\"|filename=\\"$FLOWPLUG\\"|" "$RUN/server.config"; fi   # ed.4\n'
    'export GZ_SIM_SERVER_CONFIG_PATH=$RUN/server.config\n')
rep('echo "ТОЛЬКО СИМУЛЯТОР (ed.3', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.4 model=$MODEL flow_plugin=$FLOWPLUG; ed.3')
open(dst, 'x').write(s)
print('ok')
