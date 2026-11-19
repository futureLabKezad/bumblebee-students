"""Layer 1: check a student’s Python flight program before it is sent (17.11.2026).

This is a HELPER for the student, not the protection: Python is flexible and a
determined program can get around a static check. The real protection is
layer 3 on the drone (the guarded `drone` module, a separate process, the
script lease, the pilot’s RC). Owner’s decision 17.11: «Python целиком».

Rules (whitelist):
  * import only: drone, time, math, random
  * drone.<name> only from STUDENT_API (no names starting with "_")
  * no attribute starting with "_" anywhere (blocks __class__, __subclasses__ ...)
  * no builtins that reach outside: open, exec, eval, compile, __import__,
    getattr/setattr/delattr, globals/locals/vars, input, breakpoint, help, memoryview
  * no "from drone import *"; "from drone import takeoff" only for STUDENT_API names
  * `drone` only as `drone.<name>`: not as a value (m = drone, f(drone), [drone]),
    no assignment or del of drone.<name> (review 17.11, item 4)
  * no `match` class patterns (they read any attribute by name), no string
    constants with "__" or "{x._y}" format fields (review 17.11, item 1)
  * no bare `except:` and no `except BaseException` (they would swallow the
    guard landing and the line limit; use `except Exception`)
Warnings (allowed, but the person should look):
  * no landing call at all
  * "while True" without a sleep/hover/flight call inside
"""
import ast
import re

_FORMAT_PRIVATE = re.compile(r'\{[^{}]*\.\s*_')

ALLOWED_IMPORTS = {'drone', 'time', 'math', 'random'}

# The student-facing drone API. Same names as drone.py (r2j) plus the new
# map helpers; PX4 writes, arming, mode changes, servo/wheel are not here.
STUDENT_API = {
    # flight
    'takeoff', 'fly_to', 'fly_to_marker', 'move', 'hover', 'safe_land', 'land_on_marker', 'land',
    # map and vision
    'require_map', 'marker_xy', 'markers_in_view', 'vision_pose_age', 'check_aruco',
    'wait_position_stable', 'active_map_name',
    # telemetry
    'get_pos', 'print_pos',
    # safety
    'enable_safe_interrupt', 'should_land',
    # read-only check of PX4 settings
    'check_flight_profile',
    # lights and sound
    'led_solid', 'led_blink', 'led_off', 'led_rainbow', 'led_breathe', 'beep', 'play_sound',
}
FLIGHT_CALLS = {'takeoff', 'fly_to', 'fly_to_marker', 'move', 'hover', 'safe_land', 'land_on_marker', 'land'}
LAND_CALLS = {'safe_land', 'land_on_marker', 'land'}
FORBIDDEN_BUILTINS = {'open', 'exec', 'eval', 'compile', '__import__', 'getattr', 'setattr', 'delattr',
                      'globals', 'locals', 'vars', 'input', 'breakpoint', 'help', 'memoryview'}
ALLOWED_DUNDER_NAMES = {'__name__'}    # "if __name__ == '__main__':" is common and harmless
KNOWN_DANGEROUS = {
    'set_param': 'changes PX4 parameters (saved to flash)',
    'apply_flight_profile': 'changes PX4 parameters',
    'arming': 'arms the motors directly',
    'set_mode': 'changes the flight mode directly',
    'navigate': 'low-level command; use fly_to / fly_to_marker',
    'set_servo_angle': 'servos are not used (owner’s decision 12.11)',
    'set_servo_speed': 'servos are not used (owner’s decision 12.11)',
    'read_px4_params': 'not needed in a flight program',
}


class _Checker(ast.NodeVisitor):
    def __init__(self):
        self.errors, self.warnings = [], []
        self.drone_names = set()       # local names bound to the drone module
        self.used = set()              # drone API names used
        self.loop_stack = []

    def err(self, node, text):
        self.errors.append({'line': getattr(node, 'lineno', 0), 'text': text})

    def warn(self, node, text):
        self.warnings.append({'line': getattr(node, 'lineno', 0), 'text': text})

    # imports -----------------------------------------------------------
    def visit_Import(self, node):
        for a in node.names:
            root = a.name.split('.')[0]
            if root not in ALLOWED_IMPORTS or '.' in a.name:
                self.err(node, 'import "%s" is not allowed: only %s' % (a.name, ', '.join(sorted(ALLOWED_IMPORTS))))
            elif root == 'drone':
                self.drone_names.add(a.asname or 'drone')
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        mod = node.module or ''
        if node.level or mod.split('.')[0] not in ALLOWED_IMPORTS or '.' in mod:
            self.err(node, 'import from "%s" is not allowed: only %s' % (mod, ', '.join(sorted(ALLOWED_IMPORTS))))
            return
        for a in node.names:
            if a.name == '*':
                self.err(node, '"from %s import *" is not allowed: write drone.name' % mod)
            elif mod == 'drone':
                self._api_name(node, a.name)
        self.generic_visit(node)

    # names and attributes -----------------------------------------------
    def _api_name(self, node, name):
        if name.startswith('_'):
            self.err(node, 'drone.%s is an internal function, not for students' % name)
        elif name in KNOWN_DANGEROUS:
            self.err(node, 'drone.%s is not allowed: %s' % (name, KNOWN_DANGEROUS[name]))
        elif name not in STUDENT_API:
            self.err(node, 'drone.%s is not in the list of commands for students' % name)
        else:
            self.used.add(name)

    def visit_Attribute(self, node):
        if node.attr.startswith('_'):
            self.err(node, 'the name "%s" with an underscore is not allowed' % node.attr)
        elif isinstance(node.value, ast.Name) and node.value.id in self.drone_names:
            self._api_name(node, node.attr)
            if not isinstance(node.ctx, ast.Load):
                self.err(node, 'drone.%s cannot be changed or deleted' % node.attr)
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in FORBIDDEN_BUILTINS:
            self.err(node, '"%s" is not allowed in a flight program' % node.id)
        elif node.id.startswith('__') and node.id not in ALLOWED_DUNDER_NAMES:
            self.err(node, 'the name "%s" is not allowed' % node.id)
        if node.id in self.drone_names:
            if not isinstance(node.ctx, ast.Load):
                self.err(node, 'the drone module cannot be replaced or deleted')
            else:
                parent = getattr(node, '_parent', None)
                if not (isinstance(parent, ast.Attribute) and parent.value is node):
                    self.err(node, 'drone can only be used as drone.command(...), not as a value')
        self.generic_visit(node)

    def visit_MatchClass(self, node):
        self.err(node, '"match ... case Class(...)" is not allowed in a flight program')
        self.generic_visit(node)

    def visit_Constant(self, node):
        if (isinstance(node.value, str) and node.value != '__main__'
                and ('__' in node.value or _FORMAT_PRIVATE.search(node.value))):
            self.err(node, 'a string with "__" or "{x._y}" is not allowed: that is how the insides of a program are read')
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        names = []
        t = node.type
        if t is None:
            self.err(node, 'a bare "except:" is not allowed; write "except Exception:"')
        else:
            for e in (t.elts if isinstance(t, ast.Tuple) else [t]):
                if isinstance(e, ast.Name):
                    names.append(e.id)
            if 'BaseException' in names:
                self.err(node, '"except BaseException" is not allowed; write "except Exception:"')
        self.generic_visit(node)

    def visit_Global(self, node):
        for n in node.names:
            if n in self.drone_names:
                self.err(node, 'the drone module cannot be replaced')
        self.generic_visit(node)

    # loops ----------------------------------------------------------------
    def visit_While(self, node):
        infinite = isinstance(node.test, ast.Constant) and bool(node.test.value)
        has_wait = False
        has_break = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                if sub.func.attr in ('sleep',) or sub.func.attr in FLIGHT_CALLS:
                    has_wait = True
            if isinstance(sub, (ast.Break, ast.Return, ast.Raise)):
                has_break = True
        if infinite and not has_break:
            self.warn(node, 'a "while True" loop without break: the program will not end by itself; the time guard will land the drone')
        elif infinite and not has_wait:
            self.warn(node, 'a "while True" loop without time.sleep or a flight command: it will hog the drone’s CPU')
        self.generic_visit(node)


def check(source):
    """{'ok': bool, 'errors': [{'line','text'}], 'warnings': [...], 'used': [api names]}."""
    try:
        return _check(source)
    except (RecursionError, MemoryError):          # e.g. 1+1+...+1 with 20 000 terms (review #2, item 13)
        return {'ok': False, 'errors': [{'line': 0, 'text': 'the program is too complex to check; simplify the expressions'}],
                'warnings': [], 'used': []}


def _check(source):
    try:
        tree = ast.parse(source, filename='<program>')
    except SyntaxError as e:
        return {'ok': False, 'errors': [{'line': e.lineno or 0, 'text': 'syntax error: %s' % e.msg}],
                'warnings': [], 'used': []}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._parent = parent
    c = _Checker()
    # imports first, so a "drone" used above its import line is still checked
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == 'drone':
                    c.drone_names.add(a.asname or 'drone')
    c.visit(tree)
    if not c.drone_names and not c.used:
        c.warnings.append({'line': 0, 'text': 'no "import drone": the program does not control the drone'})
    if (c.used & FLIGHT_CALLS) and not (c.used & LAND_CALLS):
        c.warnings.append({'line': 0, 'text': 'no landing (safe_land / land_on_marker / land): after the program the guard will land the drone'})
    c.errors.sort(key=lambda d: d['line'])
    c.warnings.sort(key=lambda d: d['line'])
    return {'ok': not c.errors, 'errors': c.errors, 'warnings': c.warnings, 'used': sorted(c.used)}
