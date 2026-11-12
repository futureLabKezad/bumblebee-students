#!/usr/bin/env python3
"""compare_rel3.py - T28 proof: the C8 judge copy with --identity rel3_4030 gives the same reviews as the accepted judge.
For each of the 13 rel3 runs (26.10) it runs
  OLD: flight_verification_03/verify_flight.py, imported read-only (python -B, no bytecode); only its output-folder
       guard (module HERE) is pointed at OUT/old so nothing is written into the accepted folder;
  NEW: verify_flight_c8.py --identity rel3_4030 (own process), report into reviews/rel3_proof/;
and compares the whole JSON. Allowed differences, and only these: review_input_sha256.verifier (another file) and the
new key judge_identity. Also prints the saved 26.10 verdicts next to them.
Usage (WSL): /work/analysis/layout/.venv/bin/python -B -I compare_rel3_v2.py OUT_OLD_DIR NEW_SUBDIR   (v2: judge copy v2, owner variant A; NEW_SUBDIR under reviews/)
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ACC = Path('/work/parallel_work/20261015/integration/flight_verification_03')
NEWJ = Path('/work/c8_judge_r2e_20261109/verify_flight_c8.py')
PINS = ACC / 'frozen_inputs_32.json'
MAN = Path('/work/parallel_work/20261015/integration/combined_13/manifest.json')
RUNS = ['kill_01', 'freeze_02', 'mavros_restart_03', 'pilot_04', 'cancel_before_05', 'ack_cancel_06', 'cancel_off0_07',
        'cancel_off50_08', 'cancel_off200_09', 'cancel_off500_10', 'cancel_off900_11', 'cancel_off980_12', 'heartbeat_13']
PY = sys.executable


def old_review(tag, out):
    spec = importlib.util.spec_from_file_location('accepted_verify_flight', ACC / 'verify_flight.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.HERE = out.parent.resolve()          # output guard only; ROOT/LEGACY were fixed at import
    sys.argv = ['verify_flight.py', '--run', '/work/sim/runs/' + tag, '--expected-manifest', str(MAN),
                '--frozen-pins', str(PINS), '--out', str(out)]
    try:
        m.main()
    except SystemExit as e:
        return e.code


def strip(r):
    r = json.loads(json.dumps(r))
    r.get('review_input_sha256', {}).pop('verifier', None)
    r.pop('judge_identity', None)
    return r


def main():
    outold = Path(sys.argv[1])
    outold.mkdir(parents=True, exist_ok=False)
    newdir = NEWJ.parent / 'reviews' / sys.argv[2]
    newdir.mkdir(parents=True, exist_ok=False)
    rows, ok_all = [], True
    for s in RUNS:
        tag = 'INT_flight_pc_rel3_' + s
        fo = outold / (tag + '_review.json')
        fn = newdir / (tag + '_review.json')
        code_old = old_review(tag, fo)
        code_new = subprocess.run([PY, '-B', '-I', str(NEWJ), '--run', '/work/sim/runs/' + tag, '--expected-manifest',
                                   str(MAN), '--frozen-pins', str(PINS), '--out', str(fn), '--identity', 'rel3_4030'],
                                  stdout=subprocess.DEVNULL).returncode
        ro, rn = json.loads(fo.read_text()), json.loads(fn.read_text())
        same = strip(ro) == strip(rn) and code_old == code_new
        saved = json.loads((ACC / (tag + '_review.json')).read_text())
        saved_same_checks = ({k: v['status'] for k, v in saved['scenario_checks'].items()} ==
                             {k: v['status'] for k, v in ro['scenario_checks'].items()})
        ok_all = ok_all and same
        rows.append(dict(run=tag, old=ro['scenario_status'], new=rn['scenario_status'], exit_old=code_old,
                         exit_new=code_new, identical_except_verifier_sha=same, saved_2610=saved['scenario_status'],
                         saved_2610_same_check_statuses=saved_same_checks,
                         new_identity=rn.get('judge_identity', {}).get('identity')))
        print(json.dumps(rows[-1]), flush=True)
    summary = dict(all_identical=ok_all, runs=len(rows), rows=rows)
    (newdir / 'COMPARE_REL3.json').write_text(json.dumps(summary, indent=1) + '\n')
    print('ALL IDENTICAL' if ok_all else 'DIFFERENCES FOUND')
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())
