"""The student drone commands for the editor: signature, one line of help, a snippet (24.11.2026).

Flight studio (GCS 1.4) shows these in the autocomplete list and in the "Commands" panel.
The set of names is codecheck.STUDENT_API (a test checks it); the signatures are the ones of
the guarded module on the drone (bb_mission student_drone.py) and of drone.py r2j for the
lights and sound. Limits in the help are the guards of bb_mission 0.2.0 (guards.py).
"""
from .codecheck import STUDENT_API

# group, signature, help, snippet (what Tab inserts after "drone.")
DOCS = {
    # --- flight ---
    'takeoff': ('flight', 'takeoff(height=1.0, speed=0.4)',
                'Arm and climb to `height` m above the floor where the drone stands. Allowed 0.5–1.3 m, speed up to 0.4 m/s. '
                'Returns False if the guard refuses.', 'takeoff(height=0.9)'),
    'fly_to': ('flight', 'fly_to(x, y, z=None, speed=0.10)',
               'Fly to the map point (x, y) in metres. z=None keeps the height. Speed up to 0.10 m/s (tested). '
               'The point must be inside the map + 0.30 m.', 'fly_to(0.0, 0.0, speed=0.10)'),
    'fly_to_marker': ('flight', 'fly_to_marker(marker_id, z=None, speed=0.10, quorum=2)',
                      'Fly over the marker with this ID (its place comes from the map on the drone). '
                      'Waits until `quorum` markers are in view first.', 'fly_to_marker(1, speed=0.10)'),
    'move': ('flight', 'move(x=0, y=0, z=0, speed=0.10)',
             'Move relative to the drone: x forward, y left, z up, in metres.', 'move(x=0.5, speed=0.10)'),
    'hover': ('flight', 'hover(seconds=3.0)', 'Hold the position for some seconds.', 'hover(2.0)'),
    'safe_land': ('flight', 'safe_land(x=None, y=None, precision_speed=0.10)',
                  'Land: over (x, y) if given, else where the drone is. Landing is never refused.', 'safe_land()'),
    'land_on_marker': ('flight', 'land_on_marker(marker_id)', 'Fly over the marker and land on it.', 'land_on_marker(0)'),
    'land': ('flight', 'land()', 'Land where the drone is now (PX4 AUTO.LAND).', 'land()'),
    # --- map and vision ---
    'require_map': ('map', 'require_map(name_or_sha)',
                    'Stop the program unless the drone has this map (name or the first 8+ characters of its sha). '
                    'Put it first: the route only makes sense on its own map.', "require_map('field')"),
    'marker_xy': ('map', 'marker_xy(marker_id) -> (x, y)', 'Where the marker is in the map, metres.', 'marker_xy(0)'),
    'markers_in_view': ('map', 'markers_in_view() -> int', 'How many markers the down camera sees now.', 'markers_in_view()'),
    'vision_pose_age': ('map', 'vision_pose_age() -> float', 'Seconds since the last position from markers.', 'vision_pose_age()'),
    'check_aruco': ('map', 'check_aruco(timeout=10, min_markers=1) -> bool',
                    'Before takeoff: does the camera see a marker under the drone?', 'check_aruco(timeout=10)'),
    'wait_position_stable': ('map', 'wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0) -> bool',
                             'Before takeoff: wait until the position from markers stops jumping.',
                             'wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0)'),
    'active_map_name': ('map', 'active_map_name() -> str', 'Name of the map the drone flies by.', 'active_map_name()'),
    # --- telemetry ---
    'get_pos': ('telemetry', 'get_pos() -> (x, y, z)', 'Where the drone is now, map frame, metres.', 'get_pos()'),
    'print_pos': ('telemetry', 'print_pos(phase="INFO")', 'Print the position into the log.', 'print_pos()'),
    # --- safety ---
    'enable_safe_interrupt': ('safety', 'enable_safe_interrupt()', 'Kept for old programs; STOP of the app and CH8 on the RC work without it.',
                              'enable_safe_interrupt()'),
    'should_land': ('safety', 'should_land', 'True when STOP was pressed: end your loop and land.', 'should_land'),
    'check_flight_profile': ('safety', 'check_flight_profile(profile_name) -> (ok, total, problems)',
                             'Read-only check of PX4 settings. Only before takeoff: in the air it is refused.',
                             "check_flight_profile('name')"),
    # --- lights and sound ---
    'led_solid': ('lights', 'led_solid(r, g, b, duration=None)', 'All LEDs one colour (0–255 each).', 'led_solid(0, 255, 0)'),
    'led_blink': ('lights', 'led_blink(r, g, b, freq=4.0, duration=3.0)', 'Blink the LEDs.', 'led_blink(255, 160, 0)'),
    'led_breathe': ('lights', 'led_breathe(r, g, b, period=2.0, duration=4.0)', 'Slowly pulse the LEDs.', 'led_breathe(0, 120, 255)'),
    'led_rainbow': ('lights', 'led_rainbow(duration=5.0)', 'Rainbow on the LEDs.', 'led_rainbow()'),
    'led_off': ('lights', 'led_off()', 'LEDs off.', 'led_off()'),
    'beep': ('lights', 'beep(count=1)', 'Beep from the flight controller.', 'beep(2)'),
    'play_sound': ('lights', 'play_sound(name)', 'Play a tune by name.', "play_sound('ok')"),
}

GROUPS = [('flight', 'Flight'), ('map', 'Map and vision'), ('telemetry', 'Position'), ('safety', 'Safety'),
          ('lights', 'Lights and sound')]

# Plain Python the editor also completes (allowed by codecheck).
PY_WORDS = ['import', 'from', 'if', 'elif', 'else', 'for', 'in', 'while', 'break', 'continue', 'def', 'return',
            'try', 'except', 'finally', 'with', 'as', 'and', 'or', 'not', 'is', 'None', 'True', 'False', 'pass',
            'lambda', 'class', 'global', 'print', 'range', 'len', 'abs', 'min', 'max', 'round', 'int', 'float',
            'str', 'list', 'dict', 'enumerate', 'zip', 'sorted', 'sum', 'exit', 'Exception',
            'time.sleep', 'time.time', 'math.pi', 'math.sqrt', 'math.hypot', 'math.cos', 'math.sin', 'math.atan2',
            'math.radians', 'math.degrees', 'random.random', 'random.choice', 'random.uniform', 'random.randint']


def docs():
    """[{'name', 'group', 'sig', 'help', 'snippet'}] in group order, then by name."""
    order = {g: i for i, (g, _t) in enumerate(GROUPS)}
    out = [{'name': n, 'group': g, 'sig': s, 'help': h, 'snippet': sn} for n, (g, s, h, sn) in DOCS.items()]
    out.sort(key=lambda d: (order[d['group']], d['name']))
    return out


def missing():
    """Names of STUDENT_API without help and help without a name (a test wants both empty)."""
    return sorted(STUDENT_API - set(DOCS)), sorted(set(DOCS) - STUDENT_API)
