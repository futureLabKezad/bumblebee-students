#!/usr/bin/env python3
"""One-off (Claude 09.11): tools/rc_hold2.py = step-5 rc_hold.py + pilot take-over to Position (file RUN/pilot_pos)."""
s = open('/work/goal_step5_20261106/tools/rc_hold.py').read()


def rep(o, n):
    global s
    assert s.count(o) == 1, o
    s = s.replace(o, n)


rep("Usage: python3 -I rc_hold.py RUN_DIR DRONE.params [--max-s N]",
    "rc_hold2 (09.11, Claude, stand 5B ed.5): copy of step-5 rc_hold.py + pilot take-over: when RUN/pilot_pos appears, the\n"
    "mode switch CH6 (RC_MAP_FLTMODE 6 on 20EC) goes from 1000 (slot 1 STAB) to 1999 (RC6_MAX, slot 6 = POSCTL, COM_FLTMODE6 2):\n"
    "what a pilot does to take the drone from the script. Logged once as event pilot_pos.\n"
    "Usage: python3 -I rc_hold2.py RUN_DIR DRONE.params [--max-s N]")
rep("            ch = list(BASE)\n            ch[2] = 1499 if state['armed'] else 1000\n",
    "            ch = list(BASE)\n            ch[2] = 1499 if state['armed'] else 1000\n"
    "            if os.path.exists(os.path.join(run_dir, 'pilot_pos')):   # rc_hold2: pilot takes Position\n"
    "                ch[5] = 1999\n"
    "                if not state.get('pilot_pos'):\n"
    "                    state['pilot_pos'] = True\n"
    "                    log('pilot_pos', ch6=1999)\n")
open('/work/goal_step5b_20261109/tools/rc_hold2.py', 'x').write(s)
print('ok')
