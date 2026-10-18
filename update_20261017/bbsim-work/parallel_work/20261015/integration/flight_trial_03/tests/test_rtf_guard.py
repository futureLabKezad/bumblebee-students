"""Offline test of the simulator-speed guard in supervisor.py (no ROS): the guard functions are
extracted from the source with ast and run against synthetic (wall, sim) series."""
import ast, sys, time
from pathlib import Path
src = Path(__file__).resolve().parents[1] / 'supervisor.py'
tree = ast.parse(src.read_text())
names = {'rtf_windows', 'rtf_sliding', 'rtf_recent', 'rtf_summary', 'require_rtf', 'check_rtf_whole_run',
         'EnvironmentInvalid', 'px4_time', 'paced_wait', 'wait', 'clock_offset', 'check_clock_continuity'}
consts = ('RTF_MIN', 'RTF_WINDOW', 'RTF_GATE_WINDOW', 'CLOCK_JUMP_MAX')
keep = [n for n in tree.body if (isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names) or
        (isinstance(n, ast.Assign) and any(getattr(t, 'id', '') in consts for t in n.targets))]
assert len(keep) == len(names) + len(consts), sorted(getattr(n, 'name', '') for n in keep)
ns = {'time': time, 'sim_clock': [], 'report': {}, 'events': [], 'heartbeats': []}
ns['event'] = lambda kind, **kw: ns['events'].append((kind, kw))
exec(compile(ast.Module(body=keep, type_ignores=[]), str(src), 'exec'), ns)
assert ns['RTF_MIN'] == 0.20 and ns['RTF_GATE_WINDOW'] == 10.0
def series(rtf, seconds, start_wall=0.0, start_sim=0.0, hz=10):
    return [(start_wall + i / hz, start_sim + rtf * i / hz) for i in range(int(seconds * hz) + 1)]
fails = 0
def check(name, cond):
    global fails
    print(('PASS ' if cond else 'FAIL ') + name); fails += 0 if cond else 1
ns['sim_clock'][:] = series(0.5, 30)
w = ns['rtf_windows']()
check('5 s diagnostic windows ~0.5 (6 in 30 s)', len(w) == 6 and all(abs(x[2] - 0.5) < 1e-6 for x in w))
g = ns['rtf_sliding']()
check('10 s sliding windows ~0.5', len(g) > 150 and all(abs(x[2] - 0.5) < 1e-6 for x in g))
check('recent 10 s ~0.5', abs(ns['rtf_recent'](10) - 0.5) < 1e-6)
# 4 s dip to 0.05 inside fast run: 10 s sliding window must catch it (0.5*6+0.05*4)/10=0.32 -> ok; 8 s dip -> 0.14 -> invalid
ns['sim_clock'][:] = series(0.5, 20) + series(0.05, 8, 20.1, 10.05) + series(0.5, 20, 28.2, 10.05 + 0.4 + 0.005)
ns['report'].clear(); ns['report']['guarded_start_wall'] = 0.0; ns['report']['clock_offset_start'] = ns['clock_offset']()
try:
    ns['check_rtf_whole_run'](); check('8 s stall inside fast run -> invalid', False)
except ns['EnvironmentInvalid'] as e:
    check('8 s stall inside fast run -> invalid', 'fell to' in str(e))
ns['sim_clock'][:] = series(0.3, 40); ns['report'].clear(); ns['report']['guarded_start_wall'] = 0.0; ns['report']['clock_offset_start'] = ns['clock_offset']()
ns['check_rtf_whole_run'](); check('steady 0.3 accepted', abs(ns['report']['rtf']['gate_min'] - 0.3) < 1e-6)
ns['sim_clock'][:] = series(0.19, 40); ns['report'].clear(); ns['report']['guarded_start_wall'] = 0.0; ns['report']['clock_offset_start'] = ns['clock_offset']()
try:
    ns['check_rtf_whole_run'](); check('steady 0.19 -> invalid', False)
except ns['EnvironmentInvalid']:
    check('steady 0.19 -> invalid', True)
ns['sim_clock'][:] = []; ns['report'].clear(); ns['report']['guarded_start_wall'] = 0.0; ns['report']['clock_offset_start'] = ns['clock_offset']()
try:
    ns['check_rtf_whole_run'](); check('no data -> invalid', False)
except ns['EnvironmentInvalid']:
    check('no data -> invalid', True)
now = time.monotonic()
ns['sim_clock'][:] = [(now - 12 + i / 10, 100 + 0.1 * i / 10) for i in range(120)]
try:
    ns['require_rtf']('pre', seconds=10, timeout=1); check('require_rtf 0.1 -> invalid', False)
except ns['EnvironmentInvalid'] as e:
    check('require_rtf 0.1 -> invalid', 'below 0.2' in str(e))
ns['sim_clock'][:] = [(now - 12 + i / 10, 100 + 0.5 * i / 10) for i in range(120)]
check('require_rtf 0.5 -> value', abs(ns['require_rtf']('pre', seconds=10, timeout=1) - 0.5) < 0.02)
# paced_wait: condition never true; PX4 time does not advance enough -> environment invalid
ns['sim_clock'][:] = [(time.monotonic(), 50.0)]
try:
    ns['paced_wait']('two heartbeats', lambda: False, 0.3, 2.0); check('paced_wait slow sim -> invalid', False)
except ns['EnvironmentInvalid'] as e:
    check('paced_wait slow sim -> invalid', 'simulator too slow' in str(e))
# paced_wait: condition false although PX4 time advanced enough -> real failure (AssertionError)
import threading
ns['sim_clock'][:] = [(time.monotonic(), 50.0)]
def advance():
    time.sleep(0.1); ns['sim_clock'].append((time.monotonic(), 53.0))
threading.Thread(target=advance).start()
try:
    ns['paced_wait']('two heartbeats', lambda: False, 0.3, 2.0); check('paced_wait sim advanced -> assertion', False)
except ns['EnvironmentInvalid']:
    check('paced_wait sim advanced -> assertion', False)
except AssertionError as e:
    check('paced_wait sim advanced -> assertion', str(e) == 'two heartbeats')
check('paced_wait records rows', len(ns['report']['paced_waits']) == 2 and ns['report']['paced_waits'][1]['px4_advance_s'] == 3.0)
check('paced_wait success returns True', ns['paced_wait']('ok', lambda: True, 0.1, 5.0) is True)
# host/VM suspend: realtime-monotonic offset jumps -> invalid even if RTF looked fine
ns['sim_clock'][:] = series(0.4, 40); ns['report'].clear(); ns['report']['guarded_start_wall'] = 0.0
ns['report']['clock_offset_start'] = ns['clock_offset']() - 817.0
try:
    ns['check_rtf_whole_run'](); check('817 s suspend -> invalid', False)
except ns['EnvironmentInvalid'] as e:
    check('817 s suspend -> invalid', 'suspended' in str(e))
ns['report']['clock_offset_start'] = ns['clock_offset']() - 1.9
ns['check_rtf_whole_run'](); check('1.9 s clock creep tolerated', abs(ns['report']['clock_offset_jump_s'] - 1.9) < 0.05)
sys.exit(1 if fails else 0)
