#!/usr/bin/env python3
"""T28 test helper: the source ledger run.sh will write (flight_source.sha256) must equal the pins' ledger_files, keyed
exactly as the judge keys it (verify_flight_c8.py provenance: '/sim/runs/' -> '@run/<name>', '/work/' prefix stripped).
The run.sh ledger line is checked as text first (a changed line = this test must be updated, it fails).
argv: PINS_JSON. Exit 0 = equal."""
import glob
import hashlib
import json
import sys
from pathlib import Path

D = Path('/work/c8_judge_r2h_a10_20261110')
LINE = ('sha256sum "$OWN"/*.py "$OWN/run.sh" "$CAND"/*.py "$CAND"/*.json "$BB_COMBINED_ROOT/vision/aruco_detect.py" '
        '"$C8_PRODUCT_INSTALL/bumblebee/lib/bumblebee/simple_offboard" "$C8_PRODUCT_SRC/src/python/setpoint_freshness.py" '
        '"$OUT/drone.py" > "$OUT/flight_source.sha256"')
run_sh = (D / 'executor/run.sh').read_text()
assert run_sh.count(LINE) == 1, 'run.sh ledger line changed'
OWN, CAND, COMB = D / 'executor', D / 'candidate/parameters', D / 'candidate'
INST, SRC = Path('/work/fixed_image_r2h_20261110/install'), Path('/work/fixed_image_r2h_20261110/src/bumblebee')
files = (sorted(glob.glob(str(OWN / '*.py'))) + [str(OWN / 'run.sh')] + sorted(glob.glob(str(CAND / '*.py')))
         + sorted(glob.glob(str(CAND / '*.json'))) + [str(COMB / 'vision/aruco_detect.py'),
         str(INST / 'bumblebee/lib/bumblebee/simple_offboard'), str(SRC / 'src/python/setpoint_freshness.py')])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()  # noqa: E731
ledger = {f[len('/work/'):]: sha(f) for f in files}
ledger['@run/drone.py'] = sha(SRC / 'examples/drone.py')   # run.sh copies the product drone.py (sha checked) into OUT
pins = json.loads(Path(sys.argv[1]).read_text())['ledger_files']
diff = sorted(k for k in set(ledger) | set(pins) if ledger.get(k) != pins.get(k))
print(json.dumps({'entries': len(ledger), 'pins': len(pins), 'differ': diff}))
sys.exit(0 if not diff and len(ledger) == len(files) + 1 else 1)
