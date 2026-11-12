#!/usr/bin/env python3
"""A9 (M1 of the A8 review): the px4_first logger-restart block of executor/run_sim.snapshot.sh, run alone with fake
px4-listener / px4-logger / px4-param (no PX4, no Gazebo). Expected for A9:
  SDLOG_MODE 0: stop, start -b 1000 -t (as A7/A8);
  SDLOG_MODE 1: stop, the boot log moved to OUT/boot_log_before_restart, start -b 1000 -t -e; then the restarted log is
                the only .ulg in rootfs/log (run.sh copies exactly one fresh ULog);
  SDLOG_MODE 2: refused (exit 2), no start.
Control: the A8 block with SDLOG_MODE 1 stops the logger and never starts it (the M1 finding).
argv: OUT_DIR (test scratch)"""
import os
import subprocess
import sys
from pathlib import Path

A9 = Path('/work/c8_judge_r2j_a13_20261111/executor/run_sim.snapshot.sh')
A8 = Path('/work/c8_judge_r2f_a8_20261110/executor/run_sim.snapshot.sh')
work = Path(sys.argv[1]) / 'a9_logger'
work.mkdir(parents=True, exist_ok=False)


def block(path):
    lines = path.read_text().splitlines()
    i = [n for n, l in enumerate(lines) if l.startswith('if [ "$C8_START_ORDER" = px4_first ]; then   # c8: logger restart')]
    assert len(i) == 1, i
    j = next(n for n in range(i[0] + 1, len(lines)) if lines[n] == 'fi')
    return '\n'.join(lines[i[0]:j + 1])


def run(path, mode, tag):
    t = work / tag
    b, out = t / 'b/bin', t / 'out'
    b.mkdir(parents=True)
    (out / 'rootfs/log/2026-11-10').mkdir(parents=True)
    if mode != 0:
        (out / 'rootfs/log/2026-11-10/09_00_00.ulg').write_text('boot log')
    calls = t / 'calls.txt'
    (b / 'px4-listener').write_text('#!/bin/sh\necho cs_tilt_align\n')
    # review S2: a started logger creates its file at once, like PX4 (a move after the start would take it away)
    (b / 'px4-logger').write_text('#!/bin/sh\necho "$*" >> %s\ncase "$1" in start) echo flight > %s ;; esac\n'
                                  % (calls, out / 'rootfs/log/2026-11-10/09_00_30.ulg'))
    (b / 'px4-param').write_text('#!/bin/sh\necho %d\n' % mode)
    for f in b.iterdir():
        f.chmod(0o755)
    script = 'set -euo pipefail\nB=%s\nOUT=%s\nC8_START_ORDER=px4_first\n%s\necho END\n' % (t / 'b', out, block(path))
    p = subprocess.run(['bash', '-c', script], capture_output=True, text=True, timeout=120)
    got = calls.read_text().splitlines() if calls.exists() else []
    logs = sorted(str(x.relative_to(out)) for x in out.rglob('*.ulg'))
    return p.returncode, got, logs, p.stdout + p.stderr


rc, calls, logs, txt = run(A9, 0, 'a9_mode0')
assert rc == 0 and calls == ['stop', 'start -b 1000 -t'] and logs == ['rootfs/log/2026-11-10/09_00_30.ulg'], (rc, calls, logs, txt)
rc, calls, logs, txt = run(A9, 1, 'a9_mode1')
assert rc == 0 and calls == ['stop', 'start -b 1000 -t -e'], (rc, calls, txt)
# the boot log aside, the restarted (flight) log the only .ulg in rootfs/log (what run.sh copies)
assert logs == ['boot_log_before_restart/09_00_00.ulg', 'rootfs/log/2026-11-10/09_00_30.ulg'], logs
assert 'c8: logger restarted (px4_first, SDLOG_MODE 1)' in txt, txt
rc, calls, logs, txt = run(A9, 2, 'a9_mode2')
assert rc == 2 and calls == ['stop'] and 'SDLOG_MODE 2 is not supported' in txt, (rc, calls, txt)
rc, calls, logs, txt = run(A8, 1, 'a8_mode1_control')
assert rc == 0 and calls == ['stop'], (rc, calls, txt)   # A8: stopped, never restarted
print('A9 logger restart: mode 0 as before, mode 1 with -e and the boot log aside, mode 2 refused; A8 control: no restart')
