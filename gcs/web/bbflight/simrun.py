"""Run a student’s program on the fake drone: path, events, warnings (17.11.2026).

    res = simrun.run(source, mp, cam=coverage.camera('gazebo'))

Steps: layer-1 check (codecheck) -> if ok, exec the program with
  * `import drone` -> the fake drone’s student module,
  * `import time`  -> a virtual clock (sleep does not wait),
  * print -> the run log,
  * builtins without open/exec/eval/...,
  * a line limit (sys.settrace) so "while True: pass" ends,
then: still in the air at the end or after an error -> the runner lands, as the
drone-side runner will.

The result is plain data (lists, dicts, numbers) so the HTML page can draw it.
"""
import builtins
import math
import random
import sys
import traceback

from . import bbmap, codecheck, coverage
from .fakedrone import FakeDrone, ProgramStopped, fake_time_module, student_module

FILENAME = '<program>'


class _LineLimit(BaseException):
    """BaseException so "except Exception" does not swallow it. NOTE: once the
    trace function raises, Python removes it; a program that catches this (bare
    except is refused by codecheck) or one heavy line (sum(range(10**12))) can
    still run forever here. The page runs simulations in a Web Worker and kills
    it by a wall-clock timer; the drone-side runner must use a separate process
    with a CPU-time limit (review 17.11, item 3)."""


def _program_line(tb):
    line = 0
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == FILENAME:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def run(source, mp, cam=None, line_limit=2000000, **cfg):
    chk = codecheck.check(source)
    res = {'check': chk, 'ran': False, 'ok': False, 'events': [], 'log': [], 'trace': [],
           'duration_s': 0.0, 'flight_s': 0.0, 'landed_by_guard': False,
           'map_sha': bbmap.map_sha(mp), 'map_name': mp.get('name', ''),
           'camera': (cam or {}).get('label', '')}
    if not chk['ok']:
        return res
    cam = cam or coverage.camera('gazebo')
    res['camera'] = cam.get('label', '')
    fd = FakeDrone(mp, cam, **cfg)
    mods = {'drone': student_module(fd), 'time': fake_time_module(fd), 'math': math, 'random': random}

    def importer(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split('.')[0]
        if level or root not in mods or '.' in name:
            raise ImportError('import "%s" is not allowed' % name)
        return mods[root]

    safe = {k: getattr(builtins, k) for k in dir(builtins) if not k.startswith('_')}
    for k in codecheck.FORBIDDEN_BUILTINS:
        safe.pop(k, None)
    safe['__import__'] = importer
    safe['__build_class__'] = builtins.__build_class__     # "class A: pass" (review item 19)
    safe['print'] = lambda *a, sep=' ', end='\n', **kw: fd.say(sep.join(str(x) for x in a))
    glb = {'__builtins__': safe, '__name__': '__main__'}

    count = [0]

    def local_trace(frame, event, arg):
        if event == 'line':
            count[0] += 1
            if count[0] > line_limit:
                raise _LineLimit()
        return local_trace

    def global_trace(frame, event, arg):
        if frame.f_code.co_filename == FILENAME:
            return local_trace
        return None

    end_reason = 'end of program'
    try:
        code = compile(source, FILENAME, 'exec')
        old = sys.gettrace()
        sys.settrace(global_trace)
        try:
            res['ran'] = True
            exec(code, glb)
        finally:
            sys.settrace(old)
    except ProgramStopped:
        end_reason = 'the drone stopped the program'
    except _LineLimit:
        end_reason = 'the program computed too long without commands'
        fd.event('error', 'the program ran more than %d lines without ending; looks like an endless loop' % line_limit, line=0)
    except SystemExit as e:
        end_reason = 'exit(%s)' % (e.code if e.code is not None else '')
        if e.code not in (None, 0):
            fd.event('warn', 'the program exited with code %s' % e.code, line=_program_line(sys.exc_info()[2]))
    except Exception as e:  # the student’s error: report it with the line
        tb = sys.exc_info()[2]
        end_reason = 'error in the program'
        fd.event('error', 'error: %s: %s' % (type(e).__name__, e), line=_program_line(tb))
        res['traceback'] = ''.join(traceback.format_exception_only(type(e), e)).strip()
    if fd.armed:
        if not fd.landed_by_guard:
            fd.event('error', 'the program ended with the drone in the air; the runner on the drone lands it', line=0)
        fd._descend()
    res['end_reason'] = end_reason
    res['events'] = fd.events
    res['log'] = fd.log
    res['trace'] = fd.trace
    res['duration_s'] = round(fd.t, 1)
    armed_t = [p[0] for p in fd.trace if p[5]]
    res['flight_s'] = round(armed_t[-1] - armed_t[0], 1) if armed_t else 0.0
    res['landed_by_guard'] = fd.landed_by_guard
    res['red_zone_s'] = round(fd.red_s, 1)
    res['ok'] = not any(e['level'] == 'error' for e in fd.events)
    res['limits'] = {k: fd.cfg[k] for k in ('z_min', 'z_max', 'takeoff_min', 'takeoff_max', 'speed_tested',
                                             'speed_max', 'field_margin', 'time_budget_s')}
    return res
