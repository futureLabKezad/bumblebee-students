#!/usr/bin/env python3
"""T28 test helper (D1): run the REAL parameter-composition lines of executor/sitl_setup.py main() (taken from the file
by text, from 'params = json.loads(' to the 'kept_airframe_values' line) and compare what setup would write with the
values PX4 holds on airframe 4061 before any setup (ULog of goal run l1_r2e_4061_loop, no sitl_setup there).
argv: ULOG ALLOWED_OVER_4061 (comma list of names setup may still change on 4061; '' = none)
Prints JSON; exit 0 = setup changes on 4061 exactly the allowed names, 1 = otherwise.
Interpreter: ~/px4-venv/bin/python3 (pyulog)."""
import json
import sys
import textwrap
import types
from pathlib import Path

from pyulog import ULog

SETUP = Path('/work/c8_judge_r2g_a9_20261110/executor/sitl_setup.py')
src = SETUP.read_text().splitlines(True)
a = next(i for i, l in enumerate(src) if l.strip().startswith("params = json.loads(Path('/work/sim/ros_stack/rc_real_params.json')"))
b = next(i for i, l in enumerate(src) if "report['kept_airframe_values']" in l)
block = textwrap.dedent(''.join(src[a:b + 1]))
ns = {'json': json, 'Path': Path, 'args': types.SimpleNamespace(real_flight_params='/work/sim/ros_stack/flight_real_params.json', obl=4),
      'report': {}}
for line in src:
    if line.startswith('KEEP_AIRFRAME'):
        exec(line, ns)
exec(block, ns)
params, report = ns['params'], ns['report']
p4061 = ULog(sys.argv[1]).initial_parameters
assert p4061.get('SYS_AUTOSTART') == 4061
allowed = set(filter(None, sys.argv[2].split(',')))
changes = {k: {'4061': p4061.get(k), 'setup_writes': v['value']} for k, v in params.items()
           if p4061.get(k) is None or abs(float(p4061[k]) - float(v['value'])) > 1e-3}
ok = set(changes) == allowed
print(json.dumps({'block_lines': [a + 1, b + 1], 'kept_airframe_values': report.get('kept_airframe_values'),
                  'setup_changes_on_4061': changes, 'allowed': sorted(allowed), 'ok': ok}))
sys.exit(0 if ok else 1)
