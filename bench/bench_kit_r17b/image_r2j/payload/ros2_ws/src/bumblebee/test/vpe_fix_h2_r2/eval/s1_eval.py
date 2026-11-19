#!/usr/bin/env python3
# s1_eval.py -- session 1 helper (Claude, 29.10.2026). READ ONLY: reads /tmp/bumblebee.log, a T0 output file
# or a bag folder and prints what the plan asks to record plus a verdict. Writes nothing, sends nothing.
# The criteria are the plan's (v1 T0, T1, T5a; v2 SM1, 4.3 and the T1/T5a additions); nothing is relaxed.
# Exit code: 0 = passed, 1 = FAILED or STOP (plan: no further step, rollback 9.2), 2 = NOT CLEAR (send to Claude).
#   t0     LOG T0FILE PCFILE       v1 T0 "what the candidate must show" on the whole log of this boot; instead of the
#                                  PR line (owner decision 29.10): s1_pcache.py output PCFILE says FULL 1107/1107
#   t1pre  LOG                     v1 T1 step 1: last gate line is disarmed (warm-up) (the PR part of step 1 is
#                                  now s1_pcache.py in step07, owner decision 29.10)
#   prready LOG                    PR: parameters list received after the last HEARTBEAT and the last force pull
#                                  (no longer called by the kit: step08 T5a step 3 retry and step09r use s1_pcache.py
#                                  too since the Claude decision 29.10, fix_pr2/CLAUDE_DECISION.md)
#   t1     LOG OFFSET TKILL PID0 PCFILE  one T1 run: lines a-d, (e) = MAVROS cache full (s1_pcache.py output
#                                  PCFILE, decision 29.10), R, L, (c), simple_offboard lines, already processed
#   sm1    LOG OFFSET              SM1 lines and pass criteria (log part)
#   t5a    LOG OFFSET OLD          T5a lines: one reverting, one restored to OLD, no FAILED
#   pairs  LOG                     v1 7.1 step 2: every applied has a restored; H3 candidate 30.10: and no write with an
#                                  unknown outcome is left open (STOP)
#   bag    BAGDIR [N]              pose_cov messages while armed (armed intervals from /mavros/state in the bag);
#                                  N = armings in the experiment, another interval count is NOT CLEAR
#   ccount BD                      how many T1 runs had line (c)
#   after  LOG OFFSET T TEXT       first line with TEXT after the offset and time T
#   diedafterhb LOG OFFSET T       mavros_node died again after the new HEARTBEAT (7.4 retry rule)
import os
import re
import sys

NODE = re.compile(r'^\[(?P<proc>[^\]]+)\] \[(?P<lvl>[A-Z]+) (?P<ts>\d+\.\d+)\] \[(?P<lg>[^\]]*)\]: (?P<msg>.*)$')
LAUNCH = re.compile(r'^\[(?P<lvl>[A-Z]+)\] \[(?P<proc>[^\]]+)\]: (?P<msg>.*)$')

GATE = re.compile(r'vpe_fix: (?P<why>.*) -> publish=(?P<pub>True|False)$')
LINE_A = re.compile(r'vpe_fix: FCU state unknown: no /mavros/state for (?P<age>[0-9.]+)s \(no publish\) -> publish=False')
LINE_C = 'vpe_fix: /mavros/state connected=False'
LINE_D = re.compile(r'vpe_fix: FCU state known: armed=(?P<armed>\w+) mode=(?P<mode>\S*)')
DISARMED_GATE = 'vpe_fix: disarmed (warm-up) -> publish=True'
ARMED_MANUAL = 'vpe_fix: armed in manual (no publish) -> publish=False'
PR_DONE = 'PR: parameters list received'
HB = 'CON: Got HEARTBEAT'
FORCE_PULL = 'PR: start force pull'
VP_INIT = 'Plugin vision_pose initialized'
IGNORED = 'vpe_fix: ignored connected /mavros/state stamped'
REVERTING = 'vpe_fix gate: reverting'
CAND_START = 'vpe_fix ready: VPE gate=FCU_state_known&(DISARMED|(OFFBOARD&vision_ok)), state timeout 4.5s;'

# plan v2 4.3 and v1 4.5: lines that stop everything
STOP_TEXT = ['Takeoff detected', 'Land before takeoff', 'motors may be running', 'SAFETY_NET',
             'std::future_error', 'Promise already satisfied', 'has been constrained by']


class E:
    __slots__ = ('i', 'ts', 'proc', 'lvl', 'msg', 'raw')

    def __init__(self, i, ts, proc, lvl, msg, raw):
        self.i, self.ts, self.proc, self.lvl, self.msg, self.raw = i, ts, proc, lvl, msg, raw


def load(path, offset=0):
    with open(path, 'rb') as f:
        f.seek(int(offset))
        data = f.read()
    out = []
    for i, line in enumerate(data.decode('utf-8', 'replace').splitlines()):
        m = NODE.match(line)
        if m:
            out.append(E(i, float(m.group('ts')), m.group('proc'), m.group('lvl'), m.group('msg'), line))
            continue
        m = LAUNCH.match(line)
        if m:
            out.append(E(i, None, m.group('proc'), m.group('lvl'), m.group('msg'), line))
            continue
        out.append(E(i, None, '', '', line, line))
    return out


def has(e, text):
    return text in e.raw


def last_index(es, pred):
    r = -1
    for e in es:
        if pred(e):
            r = e.i
    return r


def show(title, es, limit=40):
    print('--- %s: %d' % (title, len(es)))
    for e in es[:limit]:
        print('    ' + e.raw[:300])
    if len(es) > limit:
        print('    ... (%d more)' % (len(es) - limit))


class Verdict:
    def __init__(self):
        self.fail = []
        self.stop = []
        self.unclear = []
        self.notes = []

    def finish(self, name):
        for n in self.notes:
            print('ЗАМЕТКА: ' + n)
        if self.stop:
            print('ИТОГ %s: СТОП: %s' % (name, '; '.join(self.stop)))
            print('По плану: дальше не идти, откат 9.2 (step10_rollback_reboot.cmd). Скажите Claude.')
            return 1
        if self.fail:
            print('ИТОГ %s: ПРОВАЛ: %s' % (name, '; '.join(self.fail)))
            print('По плану: дальше не идти, откат 9.2 (step10_rollback_reboot.cmd). Скажите Claude.')
            return 1
        if self.unclear:
            print('ИТОГ %s: НЕ ЯСНО: %s' % (name, '; '.join(self.unclear)))
            print('Дальше не идти. Скажите Claude: он посмотрит лог и ответит.')
            return 2
        print('ИТОГ %s: ПРОЙДЕН' % name)
        return 0


def scan_stops(es, v, allowed_died=0, allowed_started=0, died_proc='mavros_node-'):
    """v2 4.3 / v1 4.5 stop lines in a log part. allowed_*: our own kill of MAVROS (T1)."""
    hits = [e for e in es if any(t in e.raw for t in STOP_TEXT)]
    if hits:
        show('строки-стоп (п. 4.3)', hits)
        v.stop.append('в логе строка-стоп (%s)' % hits[0].raw[:120])
    died = [e for e in es if 'process has died' in e.raw]
    started = [e for e in es if 'process started with pid' in e.raw]
    own_died = [e for e in died if e.proc.startswith(died_proc)]
    other_died = [e for e in died if not e.proc.startswith(died_proc)]
    if other_died or len(own_died) > allowed_died:
        show('process has died', died)
        v.stop.append('process has died без нашего kill')
    other_started = [e for e in started if not e.proc.startswith(died_proc)]
    if other_started or len(started) > allowed_started:
        show('process started', started)
        v.stop.append('узлы перезапускались')
    ready = [e for e in es if 'vpe_fix ready' in e.raw]
    if ready:
        show('новая строка vpe_fix ready', ready)
        v.stop.append('vpe_fix перезапустился (v1 4.5)')
    nofcu = [e for e in es if 'No FCU state for' in e.raw and 'setpoint stream stopped' in e.raw]
    if nofcu:
        show('No FCU state ... setpoint stream stopped', nofcu)
        v.fail.append('simple_offboard: No FCU state ... setpoint stream stopped')
    ap = [e for e in es if 'already processed' in e.raw]
    show('CMD: ACK ... already processed (записать; не стоп, п. 4.3)', ap)
    if ap:
        v.notes.append('есть строки already processed: прислать Claude (на apt 2.14 их быть не должно)')
    tb = [e for e in es if 'Traceback' in e.raw or 'ValueError' in e.raw]
    if tb:
        show('Traceback / ValueError', tb)
        v.unclear.append('в логе Traceback или ValueError')


PC_NEED = 1107   # PX4 names of params_before.json (part 0a), _HASH_CHECK not counted (owner decision 29.10)


def read_pcache(path):
    """s1_pcache.py output: result FULL/FAIL, count, need, FULL_AT and PREV_AT (epoch s). Missing file = no result."""
    r = {'result': None, 'count': None, 'need': None, 'full_at': None, 'prev_at': None, 'line': '(нет вывода s1_pcache.py)'}
    try:
        text = open(path, encoding='utf-8', errors='replace').read()
    except (OSError, TypeError):
        return r
    for ln in text.splitlines():
        m = re.match(r'PCACHE_RESULT=(FULL|FAIL)(?: count=(-?\d+)/(\d+))?', ln)
        if m:
            r['result'], r['line'] = m.group(1), ln.strip()
            if m.group(2) is not None:
                r['count'], r['need'] = int(m.group(2)), int(m.group(3))
        m = re.match(r'PCACHE_FULL_AT=(\d+\.\d+)$', ln.strip())
        if m:
            r['full_at'] = float(m.group(1))
        m = re.match(r'PCACHE_PREV_AT=(\d+\.\d+)$', ln.strip())
        if m:
            r['prev_at'] = float(m.group(1))
    return r


def pcache_full(r):
    return r['result'] == 'FULL' and r['count'] == PC_NEED and r['need'] == PC_NEED and r['full_at'] is not None


# ---------------------------------------------------------------- t0
def cmd_t0(log, t0file, pcfile=None):
    es = load(log)
    v = Verdict()
    t0 = open(t0file, encoding='utf-8', errors='replace').read()
    ready = [e for e in es if 'vpe_fix ready' in e.raw]
    show('строка старта vpe_fix', ready)
    if len(ready) != 1 or CAND_START not in ready[0].raw:
        v.fail.append('строка старта кандидата не ровно одна или не та')
    known = [e for e in es if LINE_D.search(e.raw)]
    show('FCU state known', known)
    if not any(LINE_D.search(e.raw).group('armed') == 'False' for e in known):
        v.fail.append('нет vpe_fix: FCU state known: armed=False')
    warm = [e for e in es if DISARMED_GATE in e.raw]
    if not warm:
        v.fail.append('нет vpe_fix: disarmed (warm-up) -> publish=True')
    else:
        print('--- disarmed (warm-up): ' + warm[0].raw[:200])
    cache = [e for e in es if 'vpe_fix gate: cache' in e.raw or 'ParamPull service unavailable' in e.raw]
    show('кэш параметров vpe_fix', cache)
    if not any('cache HOT' in e.raw for e in cache):
        v.fail.append('нет vpe_fix gate: cache HOT (v1 T0)')
    if any('degraded' in e.raw or 'ParamPull service unavailable' in e.raw for e in cache):
        v.fail.append('cache warm-up degraded или ParamPull service unavailable: T5a нельзя (v1 T0)')
    # owner decision 29.10: instead of the line PR: parameters list received -- the MAVROS parameter cache holds all
    # 1107 PX4 names (s1_pcache.py, ListParameters only, every 1 s, at most 120 s). Not full = FAILED, as before.
    pc = read_pcache(pcfile)
    print('--- кэш параметров MAVROS (вместо строки PR, решение владельца 29.10): ' + pc['line'][:300])
    if not pcache_full(pc):
        v.fail.append('в кэше параметров MAVROS не все %d имён PX4 за 120 с (v1 T0, решение владельца 29.10)' % PC_NEED)
    # for the record only (not a criterion since 29.10): the PR lines of MAVROS
    pr = [e for e in es if PR_DONE in e.raw]
    show('строка PR: parameters list received (только для записи, с 29.10 не критерий)', pr)
    if not pr:
        prl = [e for e in es if 'PR: ' in e.raw and 'different index' not in e.raw]
        show('последние строки PR: (без different index) — для разбора, на итог не влияют', prl[-8:])
        ndi = len([e for e in es if 'different index' in e.raw])
        print('--- строк PR: ... different index: %d' % ndi)
    elif 'are missed' in pr[-1].raw:
        v.notes.append('PR: часть параметров пропущена: ' + pr[-1].raw[-80:])
    fp = last_index(es, lambda e: FORCE_PULL in e.raw)
    if pr and fp > pr[-1].i:
        v.notes.append('после последней строки PR был новый force pull: список ещё грузится')
    if known:
        first = known[0].i
        ign = [e for e in es if IGNORED in e.raw and e.i > first]
        show('ignored после первой FCU state known (должно быть 0)', ign)
        if ign:
            v.fail.append('%d строк ignored после FCU state known' % len(ign))
        early = [e for e in es if IGNORED in e.raw and e.i < first]
        if early:
            v.notes.append('%d строк ignored до первой FCU state known (одна при старте допустима, записать)' % len(early))
    for need, why in (('connected: true', '/mavros/state: connected true'), ('armed: false', '/mavros/state: armed false'),
                      ('Publisher count: 1', 'издатель /mavros/state ровно 1'),
                      ('System clock synchronized: yes', 'System clock synchronized: yes')):
        if need not in t0:
            v.fail.append('нет «%s» (%s)' % (need, why))
    if re.search(r'Publisher count: ([2-9]|\d\d)', t0):
        v.stop.append('издателей /mavros/state больше 1')
    n_mav = len(re.findall(r'^\d+ /opt/ros/jazzy/lib/mavros/mavros_node', t0, flags=re.M))
    n_vpe = len(re.findall(r'^\d+ python3 \S*/vpe_fix\.py', t0, flags=re.M))
    print('--- строк mavros_node: %d, строк vpe_fix.py: %d (нужно 1 и 1)' % (n_mav, n_vpe))
    if n_mav != 1 or n_vpe != 1:
        v.fail.append('не по одной строке mavros_node и vpe_fix.py')
    return v.finish('T0′ (v1 T0)')


# ---------------------------------------------------------------- preconditions
def pr_after_restart(es):
    hb = last_index(es, lambda e: HB in e.raw)
    fp = last_index(es, lambda e: FORCE_PULL in e.raw)
    pr = last_index(es, lambda e: PR_DONE in e.raw)
    return pr > max(hb, fp) and pr >= 0, hb, fp, pr


def cmd_prready(log):
    es = load(log)
    ok, hb, fp, pr = pr_after_restart(es)
    print('строки лога: последняя CON: Got HEARTBEAT #%d, последний PR: start force pull #%d, последняя PR: parameters list received #%d'
          % (hb, fp, pr))
    if ok:
        print('PR ГОТОВ: список параметров MAVROS загружен после последнего запуска и последнего force pull')
        return 0
    print('PR НЕ ГОТОВ: после последнего запуска MAVROS (или force pull) нет строки PR: parameters list received')
    return 1


def cmd_t1pre(log):
    es = load(log)
    gates = [e for e in es if GATE.search(e.raw)]
    last = gates[-1].raw if gates else ''
    print('последняя строка шлюза vpe_fix: ' + (last[:200] or '(нет)'))
    ok1 = DISARMED_GATE in last
    if not ok1:
        print('НЕ ГОТОВ: последняя строка шлюза не disarmed (warm-up) -> publish=True (v1 T1 шаг 1)')
    # the PR part of step 1 is checked by s1_pcache.py in step07 (owner decision 29.10)
    return 0 if ok1 else 1


# ---------------------------------------------------------------- t1
def cmd_t1(log, offset, tkill, pid0, pcfile=None):
    es = load(log, offset)
    tk = float(tkill)
    v = Verdict()
    after = [e for e in es if e.ts is None or e.ts >= tk]
    print('kill (date +%%s.%%N): %.3f, старый PID %s' % (tk, pid0))

    def first(pred, src=None):
        for e in (src if src is not None else es):
            if pred(e):
                return e
        return None

    a = first(lambda e: e.ts is not None and e.ts >= tk and LINE_A.search(e.raw) is not None)
    died = [e for e in es if 'process has died' in e.raw and e.proc.startswith('mavros_node-')]
    started = first(lambda e: 'process started with pid' in e.raw and e.proc.startswith('mavros_node-'))
    vp = first(lambda e: e.ts is not None and e.ts >= tk and VP_INIT in e.raw)
    hb = first(lambda e: e.ts is not None and e.ts >= tk and HB in e.raw)
    c = first(lambda e: e.ts is not None and e.ts >= tk and LINE_C in e.raw)
    d = first(lambda e: e.ts is not None and e.ts >= tk and LINE_D.search(e.raw) is not None)
    d2 = first(lambda e: e.ts is not None and d is not None and e.i > d.i and DISARMED_GATE in e.raw)
    pe = first(lambda e: e.ts is not None and hb is not None and e.i > hb.i and PR_DONE in e.raw)

    def t(e):
        return '%.3f (+%.2f с от kill)' % (e.ts, e.ts - tk) if e is not None and e.ts is not None else 'нет'

    print('a  закрытие шлюза: %s' % t(a))
    if a is not None:
        print('   ' + a.raw[:220])
    print('b  process has died: %s' % ('; '.join(x.raw[:160] for x in died) or 'нет'))
    print('b  process started: %s' % (started.raw[:160] if started else 'нет'))
    print('b  vision_pose initialized: %s' % t(vp))
    print('b  CON: Got HEARTBEAT: %s' % t(hb))
    print('c  connected=False: %s' % ('да, ' + t(c) if c else 'нет'))
    if c is not None:
        m = re.search(r'armed=(\w+)', c.raw)
        print('   armed=%s; %s' % (m.group(1) if m else '?', c.raw[:220]))
    print('d  FCU state known: %s' % t(d))
    if d is not None:
        print('   ' + d.raw[:220])
    print('d  disarmed (warm-up) после d: %s' % t(d2))
    # (e) by the owner decision 29.10: the MAVROS parameter cache holds all 1107 PX4 names (s1_pcache.py, polled
    # every 1 s from the new CON: Got HEARTBEAT); L = kill -> first answer with all 1107 names (+-1 s)
    pc = read_pcache(pcfile)
    full = pcache_full(pc)
    if full:
        fa = pc['full_at']
        print('e  кэш параметров MAVROS: все %d имён: %.3f (+%.2f с от kill%s)'
              % (PC_NEED, fa, fa - tk, ', +%.2f с от CON: Got HEARTBEAT' % (fa - hb.ts) if hb is not None and hb.ts else ''))
        if pc['prev_at'] is not None:
            print('   стал полным между +%.2f и +%.2f с от kill (опрос раз в 1 с)' % (pc['prev_at'] - tk, fa - tk))
    else:
        print('e  кэш параметров MAVROS: не все %d имён за 120 с: %s' % (PC_NEED, pc['line'][:200]))
    print('   (для записи) строка PR: parameters list received: %s' % t(pe))
    if pe is not None and 'are missed' in pe.raw:
        print('   N пропущено: ' + pe.raw[-60:])
    if d is not None:
        print('R = %.2f с' % (d.ts - tk))
    # N2 (verify 29.10): L is the upper edge of the window PREV->FULL; print its real width
    win = pc['full_at'] - pc['prev_at'] if full and pc['prev_at'] is not None else None
    if win is not None:
        print('L = %.2f с (кэш MAVROS полон; окно PREV→FULL %.2f с: настоящий момент между L−%.2f с и L)'
              % (pc['full_at'] - tk, win, win))
    elif full:
        print('L = %.2f с (кэш MAVROS полон уже при первом ответе: только верхняя граница)' % (pc['full_at'] - tk))
    else:
        print('L = нет (кэш MAVROS не полон за 120 с)')
    if full and pc['prev_at'] is None:
        v.notes.append('кэш MAVROS был полон уже при первом ответе: L — только верхняя граница, прислать Claude')
    elif win is not None and win > 1.5:
        v.notes.append('окно PREV→FULL %.2f с (больше 1,5 с): L точнее ±1 с не получилось, настоящий момент до %.2f с раньше L'
                       % (win, win))
    if not full:
        v.notes.append('L не измерено: кэш параметров MAVROS не полон за 120 с (следующий шаг 1 проверит снова)')
    print('C=%s' % ('да' if c is not None else 'нет'))

    # criteria (v1 T1 "пройден")
    if a is None:
        v.fail.append('нет строки (a) закрытия шлюза')
    else:
        age = float(LINE_A.search(a.raw).group('age'))
        if age < 4.50:
            v.fail.append('возраст в (a) %.2f < 4,50 с' % age)
        elif age > 4.7:
            v.notes.append('возраст в (a) %.2f с больше 4,7: записать и прислать Claude (v1 T1)' % age)
        if not (3.5 <= a.ts - tk <= 4.6):
            v.notes.append('(a) через %.2f с после kill (ожидали 3,5–4,6)' % (a.ts - tk))
    if a is not None:
        if vp is None:
            v.unclear.append('нет Plugin vision_pose initialized нового MAVROS: порядок (a) не сравнить')
        elif not a.ts < vp.ts:
            v.fail.append('(a) не раньше vision_pose initialized')
    if d is None:
        v.fail.append('нет строки (d) FCU state known (MAVROS не вернулся за 60 с: стоп по v1 4.5)')
    else:
        m = LINE_D.search(d.raw)
        if m.group('armed') != 'False':
            v.stop.append('(d) armed=%s' % m.group('armed'))
        if d.ts - tk > 60:
            v.stop.append('(d) позже 60 с после kill (v1 4.5)')
        opened = [e for e in es if e.ts is not None and e.ts >= tk and e.i < d.i
                  and GATE.search(e.raw) and GATE.search(e.raw).group('pub') == 'True']
        if opened:
            show('шлюз открылся до (d)', opened)
            v.fail.append('шлюз открылся раньше (d)')
        if d2 is None:
            v.fail.append('после (d) нет disarmed (warm-up) -> publish=True')
        win = [e for e in es if (e.ts is None or e.ts >= tk) and e.i <= d.i]
        ign = [e for e in win if IGNORED in e.raw]
        rev = [e for e in win if REVERTING in e.raw]
        show('ignored от kill до (d) (нужно 0)', ign)
        show('reverting от kill до (d) (нужно 0)', rev)
        if ign or rev:
            v.fail.append('от kill до (d) есть ignored или reverting')
        so = [e for e in win if 'simple_offboard' in e.proc or 'simple_offboard' in e.raw]
        show('строки simple_offboard между kill и FCU state known (ожидаем ничего или сброс уставки)', so)
    if len(died) != 1:
        v.stop.append('строк [mavros_node-N]: process has died %d, а kill был один' % len(died))
    if started is None:
        v.stop.append('нет process started нового mavros_node')
    scan_stops(after, v, allowed_died=1, allowed_started=1)
    return v.finish('T1')


def cmd_after(log, offset, tkill, text):
    """first line after OFFSET containing TEXT whose time is >= TKILL (launch lines have no time: taken by order)"""
    tk = float(tkill)
    for e in load(log, offset):
        if text in e.raw and (e.ts is None or e.ts >= tk):
            print(e.raw[:220])
            return 0
    return 1


def cmd_diedafterhb(log, offset, tkill):
    """plan 7.4 retry rule: a new [mavros_node-N]: process has died after the new CON: Got HEARTBEAT?"""
    es = load(log, offset)
    tk = float(tkill)
    hb = next((e for e in es if e.ts is not None and e.ts >= tk and HB in e.raw), None)
    if hb is None:
        return 1
    d = [e for e in es if e.i > hb.i and 'process has died' in e.raw and e.proc.startswith('mavros_node-')]
    for e in d:
        print(e.raw[:200])
    return 0 if d else 1


def cmd_ccount(bd):
    n = 0
    yes = 0
    for k in range(1, 6):
        p = os.path.join(bd, 't1_run%d.txt' % k)
        if not os.path.exists(p):
            continue
        s = open(p, encoding='utf-8', errors='replace').read()
        n += 1
        if '\nC=да' in s:
            yes += 1
    print('T1: записей %d, строка (c) пришла в %d' % (n, yes))
    return 0 if yes > 0 else 1


# ---------------------------------------------------------------- sm1
def cmd_sm1(log, offset):
    es = load(log, offset)
    v = Verdict()
    groups = [
        ('FCU: Armed by', 'FCU: Armed by'),
        ('vpe_fix: armed in manual', ARMED_MANUAL),
        ('aruco: detection ACTIVE', 'aruco: detection ACTIVE'),
        ('FCU: Disarmed by', 'FCU: Disarmed by'),
        ('vpe_fix: disarmed (warm-up)', DISARMED_GATE),
        ('aruco: detection IDLE', 'aruco: detection IDLE'),
    ]
    counts = {}
    for title, text in groups:
        lines = [e for e in es if text in e.raw]
        counts[title] = len(lines)
        show('ожидаем 2: ' + title, lines)
    for title in ('vpe_fix: armed in manual', 'aruco: detection ACTIVE', 'vpe_fix: disarmed (warm-up)', 'aruco: detection IDLE'):
        if counts[title] != 2:
            v.unclear.append('%s: %d строк, а взводов по плану 2' % (title, counts[title]))
    if counts['FCU: Armed by'] != 2 or counts['FCU: Disarmed by'] != 2:
        v.notes.append('строк FCU: Armed by / FCU: Disarmed by %d / %d (в 0б на этом дроне PX4 1.16 их текстом не слал, '
                       'MAVROS 2.14 писал FCU: EVENT ...): решает Claude' % (counts['FCU: Armed by'], counts['FCU: Disarmed by']))
    modes = [e for e in es if 'aruco: detection ACTIVE' in e.raw]
    bad = [e for e in modes if 'mode=STABILIZED' not in e.raw]
    if bad:
        show('взвод НЕ в STABILIZED', bad)
        v.stop.append('взвод не в Stabilized (v1 4.4)')
    so_err = [e for e in es if 'simple_offboard' in e.proc and e.lvl in ('ERROR', 'FATAL')]
    so_warn = [e for e in es if 'simple_offboard' in e.proc and e.lvl == 'WARN']
    show('ошибки simple_offboard (нужно 0)', so_err)
    show('предупреждения simple_offboard', so_warn)
    if so_err:
        v.fail.append('ошибки simple_offboard')
    if so_warn:
        v.unclear.append('предупреждения simple_offboard')
    scan_stops(es, v, allowed_died=0, allowed_started=0)
    return v.finish('SM1 (лог)')


# ---------------------------------------------------------------- t5a / pairs
PAIR = re.compile(r'vpe_fix gate: (?P<kind>applied|restored|FAILED to restore) (?P<name>[A-Z0-9_]+)=(?P<val>[-0-9.eE+]+)')


# H3 candidate (Claude, 30.10.2026, finding Н3 of session 1; round 2 after the review): a write whose outcome is not
# known is open until a later line for that name says what PX4 holds. Opens: vpe_fix 'set NAME=V failed ...' (attempt 1
# or the final line), any other 'future timeout' line, a SetParam response success=False after a request (except the
# gate's own refusals, which never write). Closes: 'restored NAME=X'; 'set NAME=V failed, not sent' after the attempt-1
# line of the same call; an applied line (vpe_fix 'applied NAME=V (orig=X)', round-1 'applied (confirmed after unknown
# outcome) NAME=V (orig=X)', SetParam response 'applied ...' with original_value=X) ONLY if X equals the value NAME had
# before the unknown write (round 2, review MEDIUM). That value comes from the log: the '(orig=X)' of the unknown line
# itself, else the orig of the applied still open for NAME (first-write original), else the last 'restored NAME=X'.
# When none of these is in the log, only the retry of the same call closes (the next line for NAME after its attempt-1
# line, same value; it read its orig before attempt 1), and only with orig != value (a first write never has orig equal
# to the written value). An applied whose orig differs or cannot be checked: НЕ ЯСНО (rc 2), sticky.
# Not a close: 'FAILED to restore', 'noop: already V' (30.10: PX4 holds the new value), round-1 'dropped' (round 2: a
# cache value proves nothing), the round-2 vpe_fix lines 'noop ... kept UNCONFIRMED' and 'restore of ... held'.
# bal: a 'restored' with no applied open no longer goes below 0 (round 2: the restore of an unconfirmed write has no
# applied line; it must not hide a later applied without restored).
SETFAIL = re.compile(r'vpe_fix gate: set (?P<name>[A-Z0-9_]+)=(?P<val>[-0-9.eE+]+) failed(?P<rest>.*)$')
CONFIRMED = re.compile(r'vpe_fix gate: applied \(confirmed after unknown outcome\) (?P<name>[A-Z0-9_]+)=(?P<val>[-0-9.eE+]+)')
DROPPED = re.compile(r'vpe_fix gate: dropped (?P<name>[A-Z0-9_]+)=(?P<val>[-0-9.eE+]+) \(PX4 shows the original')
KEPT = re.compile(r'vpe_fix gate: (?:noop (?P<n1>[A-Z0-9_]+)=\S+ override with unknown write outcome kept'
                  r'|restore of (?P<n2>[A-Z0-9_]+)=\S+ \(.*\) held)')
ORIG = re.compile(r'\(orig=(?P<orig>[-0-9.eE+]+)')
SP_REQ = re.compile(r"SetParam_Request\(param_id='(?P<name>[A-Z0-9_]+)', value=(?P<val>[-0-9.eE+]+)")
SP_RESP = re.compile(r"SetParam_Response\(success=(?P<ok>True|False), message=(?P<q>['\"])(?P<msg>.*?)(?P=q)"
                     r"(?:, original_value=(?P<orig>[-0-9.eE+]+|nan))?")
SP_NO_WRITE = ('refused:', 'cache warming up', "param '")   # gate answers given before any write


def _num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _same(a, b):
    """values of the log: %g in vpe_fix lines (6 digits), full repr in SetParam responses"""
    return a is not None and b is not None and abs(a - b) <= 1e-5 * max(1.0, abs(a), abs(b))


def pair_scan(raws):
    """raws: log lines in order -> (bal, unknown, shown, unclear): bal[name] = applied - restored (never below 0),
    unknown[name] = the line that opened a write with an unknown outcome and was not closed, shown = the lines used,
    unclear[name] = why an applied after an unknown write could not close it (НЕ ЯСНО)"""
    bal, unknown, shown, unclear, req, req_val = {}, {}, [], {}, None, None
    chain, last, base, att1 = {}, {}, {}, {}

    def open_unknown(name, r, orig=None):
        if name not in unknown:
            unknown[name] = r
            base[name] = orig if orig is not None else (chain.get(name) if bal.get(name, 0) > 0 else last.get(name))
        elif orig is not None and (base.get(name) is None or name in att1):
            base[name] = orig

    def applied(name, orig, r, same_call, val, count=True):
        if name in unknown:
            b = base.get(name)
            # known value before the unknown write: orig must equal it. Not known: only the retry of the same call
            # closes, and only with orig != the written value (a first write never has orig == value: skip-if-equal)
            if (_same(b, orig) if b is not None
                    else same_call and orig is not None and val is not None and not _same(orig, val)):
                unknown.pop(name, None)
                base.pop(name, None)
            else:
                unknown.pop(name, None)
                base.pop(name, None)
                unclear.setdefault(name, 'applied после записи с неизвестным исходом: orig=%s, а до той записи было '
                                         '%s (%s)' % ('?' if orig is None else '%g' % orig,
                                                      'не известно по логу' if b is None else '%g' % b, r.strip()[:160]))
        att1.pop(name, None)
        # VERIFY PROPOSAL (not part of round 2): first-write-wins means every applied of one chain carries the same
        # orig, and a new chain must start from the value the last restore wrote. Anything else: journal original
        # differs from PX4's real original (stale cache or a set racing a restore).
        if count and orig is not None:
            if bal.get(name, 0) > 0 and chain.get(name) is not None and not _same(chain[name], orig):
                unclear.setdefault(name, 'orig=%g внутри цепочки, а первая запись цепочки orig=%g (%s)'
                                   % (orig, chain[name], r.strip()[:160]))
            elif bal.get(name, 0) <= 0 and last.get(name) is not None and not _same(last[name], orig):
                unclear.setdefault(name, 'orig=%g у новой цепочки, а последний restored записал %g (%s)'
                                   % (orig, last[name], r.strip()[:160]))
        if count:
            if bal.get(name, 0) <= 0:
                chain[name] = orig
                bal[name] = 0
            bal[name] += 1

    for r in raws:
        m = SETFAIL.search(r)
        if m:
            shown.append(r)
            n, v, rest = m.group('name'), _num(m.group('val')), m.group('rest')
            if rest.startswith(', not sent'):
                if n in att1 and _same(att1[n], v):
                    unknown.pop(n, None)
                    base.pop(n, None)
                att1.pop(n, None)
            elif rest.startswith(' (attempt 1'):
                open_unknown(n, r)
                att1[n] = v
            else:
                mo = ORIG.search(rest)
                open_unknown(n, r, _num(mo.group('orig')) if mo else None)
                att1.pop(n, None)
            continue
        m = CONFIRMED.search(r)
        if m:
            shown.append(r)
            mo = ORIG.search(r)
            applied(m.group('name'), _num(mo.group('orig')) if mo else None, r, False, _num(m.group('val')))
            continue
        m = DROPPED.search(r)
        if m:
            shown.append(r)
            att1.pop(m.group('name'), None)
            continue
        m = KEPT.search(r)
        if m:
            shown.append(r)
            continue
        m = PAIR.search(r)
        if m:
            shown.append(r)
            n, v = m.group('name'), _num(m.group('val'))
            if m.group('kind') == 'applied':
                mo = ORIG.search(r)
                applied(n, _num(mo.group('orig')) if mo else None, r, n in att1 and _same(att1[n], v), v)
            elif m.group('kind') == 'restored':
                unknown.pop(n, None)
                base.pop(n, None)
                att1.pop(n, None)
                bal[n] = max(0, bal.get(n, 0) - 1)
                if bal[n] == 0:
                    chain.pop(n, None)
                last[n] = v
            else:
                att1.pop(n, None)
                last.pop(n, None)
            continue
        m = SP_REQ.search(r)
        if m:
            req, req_val = m.group('name'), _num(m.group('val'))
            continue
        m = SP_RESP.search(r)
        if m:
            shown.append(r)
            msg, name = m.group('msg'), req or '?'
            if m.group('ok') == 'False' and not msg.startswith(SP_NO_WRITE):
                att1.pop(name, None)
                open_unknown(name, r)
            elif m.group('ok') == 'True' and msg.startswith('applied'):
                applied(name, _num(m.group('orig')), r, name in att1 and _same(att1[name], req_val), req_val,
                        count=False)
            else:
                att1.pop(name, None)
            req, req_val = None, None
            continue
        if 'future timeout' in r:
            shown.append(r)
            open_unknown('?', r)
    return bal, unknown, shown, unclear


def cmd_pairs(log):
    es = load(log)
    bal, unknown, shown, unclear = pair_scan(e.raw for e in es)
    print('--- %s: %d' % ("vpe_fix gate: applied/restored/FAILED, set ... failed, confirmed/dropped/kept/held, future "
                          "timeout, SetParam_Response", len(shown)))
    for r in shown[:40]:
        print('    ' + r[:300])
    if len(shown) > 40:
        print('    ... (%d more)' % (len(shown) - 40))
    bad = {k: n for k, n in bal.items() if n > 0}
    rc = 0
    if unknown:
        print('СТОП: ИСХОД ЗАПИСИ НЕ ИЗВЕСТЕН (Н2): %s' % '; '.join('%s: %s' % (k, v.strip()[:160])
                                                                    for k, v in sorted(unknown.items())))
        print('    PX4 мог принять значение, а vpe_fix его не вернёт. Свежее чтение значения в PX4, вернуть руками '
              'в QGC, если оно не исходное. Скажите Claude.')
        rc = 1
    if bad:
        print('ПАР НЕТ: applied без restored: %s' % bad)
        rc = 1
    if unclear:
        print('НЕ ЯСНО: %s' % '; '.join('%s: %s' % kv for kv in sorted(unclear.items())))
        print('    orig= в строке applied не сверить с значением до записи с неизвестным исходом: vpe_fix мог запомнить '
              'не то исходное. Свежее чтение значения в PX4, сверить с протоколом. Скажите Claude.')
        rc = rc or 2
    if rc:
        return rc
    print('ПАРЫ ЕСТЬ: у каждой applied есть restored (или applied не было), записей с неизвестным исходом нет')
    return 0


def cmd_t5a(log, offset, old):
    es = load(log, offset)
    v = Verdict()
    oldv = float(old)
    applied = [e for e in es if 'vpe_fix gate: applied MPC_TKO_SPEED=0.3' in e.raw]
    show('applied', applied)
    if len(applied) != 1:
        v.unclear.append('строк applied MPC_TKO_SPEED=0.3: %d' % len(applied))
    else:
        m = re.search(r'\(orig=([-0-9.eE+]+)\)', applied[0].raw)
        if not m or abs(float(m.group(1)) - oldv) > 1e-3:
            v.unclear.append('orig в applied не равен прочитанному «до» %g' % oldv)
    arm = [e for e in es if ARMED_MANUAL in e.raw]
    dis = [e for e in es if DISARMED_GATE in e.raw]
    show('armed in manual (no publish) -> publish=False', arm)
    show('disarmed (warm-up) -> publish=True', dis)
    if len(arm) != 1 or len(dis) != 1:
        v.unclear.append('взводов/разоружений в логе %d/%d, а по плану 1/1' % (len(arm), len(dis)))
    act = [e for e in es if 'aruco: detection ACTIVE' in e.raw]
    if any('mode=STABILIZED' not in e.raw for e in act):
        v.stop.append('взвод не в Stabilized (v1 4.4)')
    rev = [e for e in es if "vpe_fix gate: reverting 1 non-persistent overrides (disarmed): ['MPC_TKO_SPEED']" in e.raw]
    rev_any = [e for e in es if REVERTING in e.raw]
    res = [e for e in es if 'vpe_fix gate: restored MPC_TKO_SPEED=' in e.raw]
    failed = [e for e in es if 'FAILED to restore' in e.raw]
    show('reverting (нужна 1)', rev_any)
    show('restored (нужна 1)', res)
    show('FAILED to restore (нужно 0)', failed)
    if failed:
        v.fail.append('FAILED to restore: вернуть значение (step09r_t5a_revert_all.cmd), стоп; T2 не делать')
    if len(rev) != 1 or len(rev_any) != 1:
        v.fail.append('строк reverting %d (нужна одна, про MPC_TKO_SPEED, disarmed)' % len(rev_any))
    if len(res) != 1:
        v.fail.append('строк restored %d (нужна одна)' % len(res))
    else:
        m = re.search(r'restored MPC_TKO_SPEED=([-0-9.eE+]+) \(disarmed\)', res[0].raw)
        if not m or abs(float(m.group(1)) - oldv) > 1e-3:
            v.fail.append('restored не к старому значению %g' % oldv)
    if dis:
        pubs = [e for e in es if 'vpe_fix: published' in e.raw and e.i > dis[0].i]
        if len(pubs) > 1:
            show('vpe_fix: published после разоружения (допустима одна)', pubs)
            v.unclear.append('после разоружения больше одной строки vpe_fix: published')
    scan_stops(es, v, allowed_died=0, allowed_started=0)
    return v.finish('T5а (лог)')


# ---------------------------------------------------------------- bag
def cmd_bag(bagdir, expect=None):
    """expect: how many armings the experiment had (SM1 2, T5a 1); another count in the bag is NOT CLEAR (L8)"""
    v = Verdict()
    try:
        import yaml
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
        meta = yaml.safe_load(open(os.path.join(bagdir, 'metadata.yaml'), encoding='utf-8'))
        sid = meta['rosbag2_bagfile_information']['storage_identifier']
        r = rosbag2_py.SequentialReader()
        r.open(rosbag2_py.StorageOptions(uri=bagdir, storage_id=sid),
               rosbag2_py.ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr'))
        types = {t.name: t.type for t in r.get_all_topics_and_types()}
        st_type = get_message(types['/mavros/state']) if '/mavros/state' in types else None
        states, poses = [], []
        while r.has_next():
            topic, data, t = r.read_next()
            if topic == '/mavros/state' and st_type is not None:
                m = deserialize_message(data, st_type)
                states.append((t, bool(m.armed), m.mode))
            elif topic == '/mavros/mavros/pose_cov':
                poses.append(t)
    except Exception as ex:  # noqa: BLE001 -- any read problem is "not clear", never a pass
        print('bag не прочитан: %r' % (ex,))
        v.unclear.append('bag не прочитан (Claude посчитает на ПК)')
        return v.finish('bag pose_cov')
    states.sort()
    poses.sort()
    print('bag: /mavros/state %d сообщений, /mavros/mavros/pose_cov %d сообщений' % (len(states), len(poses)))
    if not states:
        v.unclear.append('в bag нет /mavros/state: интервалы взвода не найти')
        return v.finish('bag pose_cov')
    intervals = []
    start = None
    for t, armed, mode in states:
        if armed and start is None:
            start = (t, mode)
        elif not armed and start is not None:
            intervals.append((start[0], t, start[1]))
            start = None
    if start is not None:
        intervals.append((start[0], states[-1][0] + 1, start[1] + ' (до конца записи)'))
    print('интервалов взвода в bag: %d' % len(intervals))
    inside = 0
    edge = 0
    for a, b, mode in intervals:
        n_in = [p for p in poses if a <= p < b]
        n_edge = [p for p in n_in if p - a <= 500000000 or b - p <= 500000000]
        print('  взведён %.3f–%.3f (%.1f с), режим %s: pose_cov %d (из них в 0,5 с от края %d)'
              % (a / 1e9, b / 1e9, (b - a) / 1e9, mode, len(n_in), len(n_edge)))
        inside += len(n_in) - len(n_edge)
        edge += len(n_edge)
    if inside:
        v.fail.append('%d сообщений pose_cov, пока взведён' % inside)
    if edge:
        v.unclear.append('%d сообщений pose_cov в 0,5 с от края взвода (Claude разберёт порядок)' % edge)
    if not intervals:
        v.unclear.append('в bag не видно взвода')
    elif expect is not None and len(intervals) != int(expect):
        v.unclear.append('интервалов взвода в bag %d, а взводов в опыте %s: взвод мог пройти мимо записи' % (len(intervals), expect))
    print('pose_cov пока взведён: %d (+%d у края)' % (inside, edge))
    return v.finish('bag pose_cov')


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    c, a = argv[1], argv[2:]
    if c == 't0':
        return cmd_t0(*a)
    if c == 't1pre':
        return cmd_t1pre(*a)
    if c == 'prready':
        return cmd_prready(*a)
    if c == 't1':
        return cmd_t1(*a)
    if c == 'sm1':
        return cmd_sm1(*a)
    if c == 't5a':
        return cmd_t5a(*a)
    if c == 'pairs':
        return cmd_pairs(*a)
    if c == 'bag':
        return cmd_bag(*a)
    if c == 'ccount':
        return cmd_ccount(*a)
    if c == 'after':
        return cmd_after(*a)
    if c == 'diedafterhb':
        return cmd_diedafterhb(*a)
    print('неизвестная команда ' + c)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
