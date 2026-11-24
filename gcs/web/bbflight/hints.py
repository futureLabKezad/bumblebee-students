"""«How to fix» for every message of the code check and of the simulation (24.11.2026).

The messages themselves come from codecheck.py (the same file is on the drone) and from the
simulated drone; this module only adds advice, so the drone-side texts stay untouched.
fix_for(text) -> one or two plain sentences, '' when there is nothing useful to add.
"""
import difflib
import re

from .codecheck import STUDENT_API

# (pattern, advice). The first match wins; patterns are searched in the message text.
RULES = [
    # --- code check (layer 1) ---
    (r'syntax error', 'Look at this line and the one above it: a missing “:” after if/for/while/def/try, '
                      'a bracket or quote that is not closed, or a wrong indent (use 4 spaces).'),
    (r'^import .* is not allowed|^import from', 'Only four modules are available: import drone, time, math, random.'),
    (r'from \S+ import \*', 'Write “import drone” and then drone.takeoff(...), drone.fly_to(...).'),
    (r'is an internal function', 'Names that start with “_” are the insides of the module. Use the commands from the list.'),
    (r'drone\.\w+ is not allowed: (changes PX4|arms|changes the flight mode)',
     'The program never changes PX4 settings, arms or switches modes itself: use takeoff, fly_to, land; the guards do the rest.'),
    (r'drone\.\w+ is not allowed', 'This command is not for flight programs. Use fly_to / fly_to_marker / move instead.'),
    (r'cannot be changed or deleted|cannot be replaced', 'Do not assign to drone or its commands; just call them: drone.hover(2).'),
    (r'with an underscore', 'Rename it without the leading “_”: such names are blocked because they reach into Python’s insides.'),
    (r'drone can only be used as', 'Call commands directly, e.g. drone.takeoff(height=0.9); do not keep drone in a variable or pass it on.'),
    (r'"except BaseException"|bare "except:"', 'Write “except Exception:”. The guard’s landing must not be caught by the program.'),
    (r'is not allowed in a flight program', 'Files, eval, exec and similar do not exist on the drone. Use print(...) to show values.'),
    (r'a string with "__"', 'Remove “__” from the text, or write it another way.'),
    (r'match \.\.\. case Class', 'Use if / elif instead of “match … case Class(…)”.'),
    (r'"while True" loop without break', 'Give the loop an end: for i in range(5): …, or “if drone.should_land: break”.'),
    (r'"while True" loop without time\.sleep', 'Put time.sleep(0.2) or a flight command inside the loop.'),
    (r'no "import drone"', 'Add “import drone” as the first line.'),
    (r'no landing', 'End with drone.land_on_marker(0) inside “finally:”, so it lands even after an error.'),
    (r'too complex to check', 'Split the long expression into several lines with variables.'),
    # --- guards in the simulation (layer 3, the same numbers as on the drone) ---
    (r'takeoff to .* outside the tested', 'Use drone.takeoff(height=0.9). Allowed: 0.5–1.3 m.'),
    (r'climb speed .* outside|takeoff speed', 'Leave the speed out (0.4 m/s) or give at most speed=0.4.'),
    (r'no marker in view on the ground', 'Stand the drone over marker 0, nose as on the map; check that the map has marker 0 under it.'),
    (r'speed .* outside the tested', 'Use speed=0.10 or less: that is the speed tested in Gazebo.'),
    # review 24.11, M5: the simulation speaks in map z (0.30–1.20), the drone in height above the floor (0.41–1.31)
    (r'height z=.* outside the tested',
     'Give z from 0.30 to 1.20 (map z; the same as 0.41–1.31 m above the floor), or leave z out to keep the takeoff height.'),
    (r'height above the floor.* outside the tested',
     'Keep the height 0.41–1.31 m above the floor, or leave z out to keep the takeoff height.'),
    (r'outside the field|leaving the field',
     'Pick a point inside the markers (the map + 0.30 m). Check the units: metres, not centimetres; check the sign of x and y.'),
    (r'not in the air; command refused', 'Take off first: “if not drone.takeoff(height=0.9): exit(1)”.'),
    (r'no marker in view for|did not become stable|vision unreliable|red zone',
     'Route the drone over the markers, add markers along the way (Map tab), or fly a little higher: '
     'the camera then sees more floor.'),
    (r'over the budget', 'Shorten the route or the hovers: the drone’s time guard lands it 300 s after takeoff.'),
    (r'ended with the drone in the air|ended in the air', 'Put the landing in “finally:” at the end of the program.'),
    (r'did not arrive within', 'Split the leg: at 0.10 m/s one command can cover about 5 m within its 60 s.'),
    (r'expects map', 'Send this map to the drone (Drone tab) or change the name in drone.require_map(...).'),
    (r'marker \S+ is not in the map', 'Add the marker in the Map tab, or use an ID that the map has.'),
    (r'markers were in view for', 'Fly where at least two markers are seen (green on the map), or give quorum=1.'),
    (r'at the start the camera does not see', 'Stand the drone over marker 0 before the start.'),
    (r'endless loop|computed too long', 'A loop does not end. Give it a counter (for i in range(...)) or a break.'),
    (r'exited with code', 'exit(...) was called: one of your own checks before takeoff failed.'),
    (r'NameError', 'A name is misspelled or used before it is given a value.'),
    (r'TypeError', 'A command got a wrong number or kind of values: see its line in Commands (Ctrl+Space).'),
    (r'ZeroDivisionError', 'A division by zero: check the value before dividing.'),
    (r'IndentationError|TabError', 'Indent with 4 spaces, the same in every line of a block.'),
    (r'error: \w+Error', 'A Python error in this line. The drone lands when the program fails.'),
]
_COMPILED = [(re.compile(p), fix) for p, fix in RULES]
_UNKNOWN_CMD = re.compile(r'drone\.(\w+) is not in the list of commands')


def fix_for(text):
    t = str(text)
    m = _UNKNOWN_CMD.search(t)
    if m:
        close = difflib.get_close_matches(m.group(1), sorted(STUDENT_API), n=1, cutoff=0.6)
        return ('Did you mean drone.%s? ' % close[0] if close else '') + \
            'Type “drone.” and press Ctrl+Space to see all commands.'
    for rx, fix in _COMPILED:
        if rx.search(t):
            return fix
    return ''
