#!/usr/bin/env python3
"""Pause of the vision gate after takeoff, from the Pi journal saved by 07 (READ ONLY, runs on the PC/WSL, never touches the drone).
Input: out\\takeoff_<time>_journal.txt (journalctl -u bumblebee -o short-iso-precise, filtered by pi/journal_window.sh).
It reads the vpe_fix gate lines "... -> publish=True|False" (node vpe_publisher), takes the first line with OFFBOARD as the entry into OFFBOARD
(takeoff), and prints facts only (no good/bad words):
  GATE_EVENTS      number of gate lines, first OFFBOARD line time
  OFFBOARD_CLOSED  every span "publish=False while OFFBOARD" (start, end, length in s); the last one may be open until the end of the journal
  NOTE             the gate logs only CHANGES of its decision, so the first OFFBOARD line is the first CHANGE seen in the journal, not necessarily the moment of the real entry into OFFBOARD (the journal window may start later); take FIRST_OK as an estimate\n  FIRST_OK         seconds from the first OFFBOARD line to the first "OFFBOARD + vision_ok" line
  LONGEST/TOTAL    the longest closed span and the sum of all closed spans after the OFFBOARD entry
  RESUME           number of "resume after ... without a publish" lines (r2j B2)
  PROFILE_FLIPS    number of "SEARCHING"/"NORMAL" profile lines of aruco_detect after the OFFBOARD entry
Usage: journal_vision_pauses.py FILE [...]   (python3 on the PC/WSL; no extra packages)
Exit: 0 always when the file could be read; 2 if a file could not be read."""
import re
import sys
from datetime import datetime

TS = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)([+-]\d\d:?\d\d)?')
GATE = re.compile(r'(.*?)->\s*publish=(True|False)')


def parse_ts(line):
    m = TS.match(line)
    if not m:
        return None
    s = m.group(1)
    fmt = '%Y-%m-%dT%H:%M:%S.%f' if '.' in s else '%Y-%m-%dT%H:%M:%S'
    return (datetime.strptime(s, fmt) - datetime(1970, 1, 1)).total_seconds()   # local wall clock of the Pi, only differences matter


def analyze(lines):
    events = []   # (t, publish, text)
    resumes = 0
    flips = []
    last_t = None
    for ln in lines:
        t = parse_ts(ln)
        if t is None:
            continue
        last_t = t
        g = GATE.search(ln)
        if g:
            events.append((t, g.group(2) == 'True', g.group(1).strip()))
        if 'resume after' in ln and 'without a publish' in ln:
            resumes += 1
        if 'SEARCHING' in ln or re.search(r'\bNORMAL\b', ln):
            flips.append(t)
    res = {'events': events, 'resume': resumes, 'last_t': last_t}
    off = next((e for e in events if 'OFFBOARD' in e[2]), None)
    res['t_off'] = off[0] if off else None
    closed = []
    start = None
    for t, pub, text in events:
        if res['t_off'] is None or t < res['t_off']:
            continue
        if not pub and 'OFFBOARD' in text and start is None:
            start = t
        elif pub and start is not None:
            closed.append((start, t))
            start = None
        elif not pub and 'OFFBOARD' not in text and start is not None:
            # the gate changed reason while closed (e.g. disarmed): the closed span ends there
            closed.append((start, t))
            start = None
    open_span = start is not None
    if open_span and last_t is not None:
        closed.append((start, last_t))
    res['closed'] = closed
    res['open'] = open_span
    ok = next((e for e in events if res['t_off'] is not None and e[0] >= res['t_off'] and e[1] and 'vision_ok' in e[2]), None)
    res['first_ok'] = (ok[0] - res['t_off']) if ok and res['t_off'] is not None else None
    res['flips'] = sum(1 for t in flips if res['t_off'] is not None and t >= res['t_off'])
    return res


def report(path):
    with open(path, encoding='utf-8', errors='replace') as fh:
        lines = fh.read().splitlines()
    r = analyze(lines)
    out = []
    p = out.append
    p('FILE %s lines=%d' % (path.replace('\\', '/').split('/')[-1], len(lines)))
    p('GATE_EVENTS %d first_OFFBOARD_line_at=%s' % (len(r['events']), '%.3f' % r['t_off'] if r['t_off'] is not None else 'none (в журнале нет строки шлюза с OFFBOARD)'))
    if r['t_off'] is None:
        p('OFFBOARD_CLOSED not measurable')
        p('RESUME %d' % r['resume'])
        return out
    p('OFFBOARD_CLOSED count=%d%s' % (len(r['closed']), ' (последний период открыт до конца журнала)' if r['open'] else ''))
    for a, b in r['closed']:
        p('  closed from=+%.2fs to=+%.2fs length_s=%.2f (время от первой строки с OFFBOARD)' % (a - r['t_off'], b - r['t_off'], b - a))
    lens = [b - a for a, b in r['closed']]
    p('LONGEST_CLOSED_S %s' % ('%.2f' % max(lens) if lens else '0.00'))
    p('TOTAL_CLOSED_S %.2f' % sum(lens))
    p('FIRST_OK_AFTER_OFFBOARD_S %s' % ('%.2f' % r['first_ok'] if r['first_ok'] is not None else 'none'))
    p('RESUME %d' % r['resume'])
    p('PROFILE_FLIPS_AFTER_OFFBOARD %d' % r['flips'])
    return out


def main(argv):
    if not argv:
        print('usage: journal_vision_pauses.py FILE [...]', file=sys.stderr)
        return 2
    rc = 0
    for f in argv:
        try:
            for l in report(f):
                print(l)
        except Exception as e:
            print('ERROR file=%s %r' % (f, e))
            rc = 2
        print('---')
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
