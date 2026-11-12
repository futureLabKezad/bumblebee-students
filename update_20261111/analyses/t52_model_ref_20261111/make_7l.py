#!/usr/bin/env python3
"""make_7l.py (Claude «Симулятор», 11.11.2026; chat 1: r2j + A12, T52 trial runs may run on r2j). Launcher 7l =
/work/goal_step5b_20261109/run_scenario7k.sh (5a116042, not changed) + --image r2j -> /work/fixed_image_r2j_20261111
(SHA256SUMS 14fbcf74…, MANIFEST b0899329…; camera down (0.081, 0, -0.034) as model_v2; flight.py and flight_marker.py takeoff 0.9)
+ for image r2j: flight.py and flight_marker.py script height 0.9 (launcher info evaluators goal_eval/goal_eval2 only; the scored
c5/c7 evaluators read the height from the script) + edition text + 7l in the snapshot cp / versions lists. Writes ./run_scenario7l.sh.new ('x')."""
import hashlib
S = '/work/goal_step5b_20261109'
sha8 = lambda s: hashlib.sha256(s.encode()).hexdigest()[:8]
k = open(S + '/run_scenario7k.sh', encoding='utf-8').read(); assert sha8(k) == '5a116042'
R2J = '/work/fixed_image_r2j_20261111'
rep = [('[ "$IMAGE" = r2hf ] && R2=/work/fixed_image_r2h_20261110;', '[ "$IMAGE" = r2hf ] && R2=/work/fixed_image_r2h_20261110; [ "$IMAGE" = r2j ] && R2=%s;' % R2J),
       ('  flight.py) SCRIPT_REL=examples/flight/flight.py; SCRIPT_H=1.5; [ "${IMAGE:0:2}" = r2 ] && SCRIPT_H=0.8 ;;',
        '  flight.py) SCRIPT_REL=examples/flight/flight.py; SCRIPT_H=1.5; [ "${IMAGE:0:2}" = r2 ] && SCRIPT_H=0.8; [ "$IMAGE" = r2j ] && SCRIPT_H=0.9 ;;'),
       ('  flight_marker.py) SCRIPT_REL=examples/flight/flight_marker.py; SCRIPT_H=0.7 ;;',
        '  flight_marker.py) SCRIPT_REL=examples/flight/flight_marker.py; SCRIPT_H=0.7; [ "$IMAGE" = r2j ] && SCRIPT_H=0.9 ;;'),
       ('echo "ТОЛЬКО СИМУЛЯТОР (ed.7k af_4074_t52 sim_only_4074;', 'echo "ТОЛЬКО СИМУЛЯТОР (ed.7l image_r2j; ed.7k af_4074_t52 sim_only_4074;'),
       ('$STEP5B/run_scenario7j.sh $STEP5B/run_scenario7k.sh ', '$STEP5B/run_scenario7j.sh $STEP5B/run_scenario7k.sh $STEP5B/run_scenario7l.sh '),
       ('run_scenario7j.sh run_scenario7k.sh ', 'run_scenario7j.sh run_scenario7k.sh run_scenario7l.sh ')]
for a, b in rep:
    assert k.count(a) == 1, a
    k = k.replace(a, b)
l = k.split('\n', 2)
k = l[0] + '\n' + l[1] + '\n' + '# Edition 7l (11.11, Claude): ed.7k + --image r2j = %s; flight.py / flight_marker.py height 0.9 for r2j. Maker: /work/t52_model_ref_20261111/make_7l.py\n' % R2J + l[2]
with open('/work/t52_model_ref_20261111/run_scenario7l.sh.new', 'x', encoding='utf-8', newline='\n') as f:
    f.write(k)
print('7l', sha8(k))
