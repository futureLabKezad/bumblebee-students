#!/usr/bin/env python3
"""_make_run_scenario7f.py (Claude «Симулятор», 10.11.2026). run_scenario7f.sh = ed.7e + --image r2h
(/work/fixed_image_r2h_candidate_20261110, CANDIDATE for control runs only, T43 of chat 1; not scored). Nothing else.
N5 of REVIEW_r2h.md: the script is still started as plain python3 (no use_sim_time), so drone.py W counts monotonic
(wall) time on this stand, like r2g. Writes run_scenario7f.sh (open 'x'); run_scenario7e.sh is not changed."""
import hashlib, os
D = '/work/goal_step5b_20261109'
src = open(os.path.join(D, 'run_scenario7e.sh'), encoding='utf-8').read()
print('ed.7e sha8', hashlib.sha256(src.encode()).hexdigest()[:8])
rep = [
    ('[ "$IMAGE" = r2g ] && R2=/work/fixed_image_r2g_20261110;',
     '[ "$IMAGE" = r2g ] && R2=/work/fixed_image_r2g_20261110; [ "$IMAGE" = r2h ] && R2=/work/fixed_image_r2h_candidate_20261110;'),
    ('echo "ТОЛЬКО СИМУЛЯТОР (ed.7e hover_r6;', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.7f image_r2h_candidate; ed.7e hover_r6;'),
]
for a, b in rep:
    assert src.count(a) == 1, a
    src = src.replace(a, b)
n = src.count('run_scenario7e.sh ')
assert n == 2, n   # snapshot copy list and versions.txt sha list
# r2 (REVIEW_7f_ctl.md B1): the cp list needs the full path ($STEP5B/), the sha list runs inside $SNAP (bare name)
for a, b in (('run_scenario7c.sh $STEP5B/run_scenario7e.sh ', 'run_scenario7c.sh $STEP5B/run_scenario7e.sh $STEP5B/run_scenario7f.sh '),
             ('run_scenario7c.sh run_scenario7e.sh ', 'run_scenario7c.sh run_scenario7e.sh run_scenario7f.sh ')):
    assert src.count(a) == 1, a
    src = src.replace(a, b)
assert src.count('$STEP5B/run_scenario7f.sh ') == 1 and src.count(' run_scenario7f.sh ') == 1
head = ('# Edition 7f (10.11, Claude): ed.7e + --image r2h = /work/fixed_image_r2h_candidate_20261110 (control runs, not scored;\n'
        '#   drone.py W on wall time here: no use_sim_time, REVIEW_r2h N5). Maker: _make_run_scenario7f.py\n')
lines = src.split('\n', 2)
src = lines[0] + '\n' + lines[1] + '\n' + head + lines[2]
with open(os.path.join(D, 'run_scenario7f.sh'), 'x', encoding='utf-8', newline='\n') as f:
    f.write(src)
print('ed.7f sha8', hashlib.sha256(src.encode()).hexdigest()[:8])
