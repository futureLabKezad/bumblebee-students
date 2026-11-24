"""A "not real" drone with the student drone API, for the 2D simulation (17.11.2026).

Kinematic model on a virtual clock (time.sleep does not wait). Same function
names and return values as drone.py (r2j) where they exist, plus the new map
helpers (require_map, marker_xy, fly_to_marker, land_on_marker, markers_in_view).
Differences on purpose (the student module on the drone will do the same):
  * fly_to(x, y, z=None): z=None keeps the current height (drone.py: z=1.0 map).
  * Guards of layer 3 are modelled: outside the field, height or speed outside
    the tested range, time over budget, no markers for 6 s -> the command is
    refused or the drone lands, as the guarded module on the drone will do.

What it does NOT model: wind, EKF and vision errors, PX4 failsafes, the pilot.
Times are fitted to 19 Gazebo runs of flight_marker.py on the real-field map
(calib/timing_gazebo.py): takeoff 15.1 s, legs of ~1 m at 0.10 m/s 14-28 s.
"""
import math
import sys

from . import bbmap, coverage

DEFAULTS = {
    'z_rest': -0.11,            # height of base_link on the floor in map z (model.sdf: legs at -0.217, markers at 0.004)
    'start': None,              # None -> the Gazebo stand: 0.111 m behind marker 0 along the heading
    'start_back_m': 0.111,
    'start_yaw': None,          # None -> rot_z(marker 0) - pi/2 (Gazebo spawn yaw offset -0.0264 rad; detector yaw_world ~1.1 deg)
    # tested range (plan R1: outside it the guard REFUSES the command; numbers are the owner’s to approve)
    # flight_marker takeoff 0.9 (cruise z 0.79), flight_marker_loop takeoff 1.3 (cruise z 1.19), both run in Gazebo
    'z_min': 0.30, 'z_max': 1.20,
    'takeoff_min': 0.5, 'takeoff_max': 1.3, 'climb_speed_max': 0.4,
    'speed_tested': 0.10, 'speed_max': 0.10,
    'field_margin': 0.30,
    'time_budget_s': 300.0,
    # timing: FITTED on the 19 Gazebo runs fB_c7marker (not a check; checked on other routes, README)
    # takeoff segment 15.1 s = 7.4 arm + 0.9/0.15 climb + 0.2 + the script’s 1.5 s hover;
    # legs: 2.06 m in 25.6 s, 0.98 m in 13.1 s, 0.97 m in 21.1 s at 0.10 m/s -> overhead 6.6 s per leg;
    # landing 6.5 s = approach + descent at 0.30 m/s + ~3 s until "Disarmed by landing"
    'arm_delay_s': 7.4, 'climb_mps': 0.15, 'climb_hold_s': 0.2,
    'leg_overhead_s': 6.6, 'nav_timeout_s': 60.0,
    'land_mps': 0.30, 'land_extra_s': 3.0,
    'quorum_timeout_s': 15.0, 'vision_timeout_s': 6.0,
    'dt': 0.1, 'trace_every_s': 0.2,
    'hard_limit_s': 1800.0,
}


# PX4 limits of the G2 profile (the same on 20EC, 2503 and e6b1 after G1-G6): the simulated drone
# never moves faster than these. The guards (0.10 m/s) are stricter, so normally they do not bite.
PX4_PROFILE = {'xy_mps': 0.25, 'up_mps': 1.0, 'down_mps': 0.4, 'takeoff_mps': 0.8, 'jerk': 1.5}


def leg_fractions(d, T, speed, dt, steps):
    """Fraction of a straight leg of length d done after each of `steps` steps of dt (index 0..steps).

    Velocity: a smooth ramp up to the cruise speed (jerk-limited: ramp time 2*sqrt(v/jerk)),
    cruise, a ramp down; then the drone holds the point until T. Without `speed` the leg is
    spread over the whole T (as in 1.3, but with soft ends)."""
    if d < 1e-9 or steps <= 0:
        return [1.0] * (steps + 1)
    v = float(speed) if speed and speed > 0 else d / T
    tr = 2.0 * math.sqrt(v / PX4_PROFILE['jerk'])
    tm = min(T, d / v + tr)
    if tm < 2 * tr:
        tr = tm / 2.0
    vc = d / max(1e-9, tm - tr)

    def vel(t):
        if t >= tm:
            return 0.0
        u = min(1.0, t / tr, (tm - t) / tr) if tr > 0 else 1.0
        return vc * u * u * (3 - 2 * u)

    out, s = [0.0], 0.0
    for k in range(1, steps + 1):
        s += vel((k - 0.5) * dt) * dt
        out.append(s)
    total = out[-1] or 1.0
    return [min(1.0, f / total) for f in out]


class ProgramStopped(BaseException):
    """The simulated drone ended the program (guard landing, time limit).
    BaseException on purpose: "except Exception" in the student’s program must
    not swallow it (review 17.11, item 2); bare except is refused by codecheck."""


def start_heading(mp):
    """Heading of the drone on the stand in map frame: rot_z(marker 0) - pi/2 (Gazebo spawn)."""
    m0 = next((m for m in mp['markers'] if m['id'] == 0), None)
    return (m0['rot_z'] - math.pi / 2) if m0 else 0.0


def _student_line():
    f = sys._getframe(1)
    while f is not None:
        if f.f_code.co_filename == '<program>':
            return f.f_lineno
        f = f.f_back
    return 0


class FakeDrone:
    def __init__(self, mp, cam, **cfg):
        self.mp = mp
        self.cam = cam
        self.cfg = dict(DEFAULTS)
        self.cfg.update(cfg)
        self.ids = {m['id']: m for m in mp['markers']}
        m0 = self.ids.get(0)
        yaw = self.cfg['start_yaw']
        if yaw is None:
            yaw = start_heading(mp)
        if self.cfg['start'] is not None:
            self.x, self.y = self.cfg['start']
        elif m0:
            b = self.cfg['start_back_m']
            self.x, self.y = m0['x'] - b * math.cos(yaw), m0['y'] - b * math.sin(yaw)
        else:
            self.x, self.y = 0.0, 0.0
        self.z = self.cfg['z_rest']
        self.yaw = yaw
        self.t = 0.0
        self.armed = False
        self.landed_by_guard = False
        self.stopped = False       # after a guard landing: no more flight commands
        self.trace = []
        self.events = []
        self.log = []
        self._last_trace = -1e9
        self._last_seen = 0.0
        self._silent_since = None
        self._budget_warned = False
        self._in_red = False
        self._red_run = 0.0
        self._green_run = 0.0
        self.red_s = 0.0           # time in the air with a mean count < RED_BELOW
        self._field = bbmap.bounds(mp, self.cfg['field_margin'])
        self.should_land = False
        self._sample(force=True)

    # --- bookkeeping ----------------------------------------------------
    def event(self, level, text, line=None):
        self.events.append({'t': round(self.t, 2), 'x': round(self.x, 3), 'y': round(self.y, 3),
                            'z': round(self.z, 3), 'level': level, 'text': text,
                            'line': _student_line() if line is None else line})

    def say(self, text):
        self.log.append({'t': round(self.t, 2), 'text': str(text)})

    def count(self):
        """Mean markers in view (coverage.expected_count). On the floor: the full frame,
        one point (the start check; Gazebo stand saw marker 0 from -0.111 m)."""
        if self.z < self.cfg['z_rest'] + 0.1:
            cam = dict(self.cam, max_tan=None)
            return float(len(coverage.visible_ids(self.mp, self.x, self.y, self.z, self.yaw, cam)))
        return coverage.expected_count(self.mp, self.x, self.y, self.z, self.yaw, self.cam)

    def _sample(self, force=False):
        if force or self.t - self._last_trace >= self.cfg['trace_every_s'] - 1e-9:
            n = self.count()
            self.trace.append([round(self.t, 2), round(self.x, 3), round(self.y, 3), round(self.z, 3), round(n, 1),
                               1 if self.armed else 0])
            self._last_trace = self.t

    def _inside(self, x, y):
        x0, y0, x1, y1 = self._field
        return x0 <= x <= x1 and y0 <= y <= y1

    def _tick(self, dt):
        """Advance the clock by dt, run the guards. Raises ProgramStopped."""
        self.t += dt
        if self.t > self.cfg['hard_limit_s']:
            if not self.stopped:
                self.event('error', 'the program runs longer than %.0f s; simulation stopped' % self.cfg['hard_limit_s'])
            self.stopped = True
            raise ProgramStopped('hard limit')
        if not self.armed:
            self._sample()
            return
        n = self.count()
        if n >= 0.5:
            self._last_seen = self.t
            self._silent_since = None
        else:
            if self._silent_since is None:
                self._silent_since = self.t
            if self.t - self._silent_since > self.cfg['vision_timeout_s']:
                self.event('error', 'no marker in view for %.0f s; the vision guard lands the drone' % self.cfg['vision_timeout_s'])
                self._guard_land()
        # red zone with 2 s hysteresis: one warning per stretch, not per wobble
        red = n < coverage.RED_BELOW and self.z > self.cfg['z_rest'] + 0.3
        if red:
            self.red_s += dt
            self._red_run += dt
            self._green_run = 0.0
            if not self._in_red and self._red_run >= 2.0:
                self._in_red = True
                self.event('warn', '%.1f markers in view on average for 2 s: red zone, vision unreliable' % n)
        else:
            self._green_run += dt
            self._red_run = 0.0
            if self._green_run >= 2.0:
                self._in_red = False
        if self.t > self.cfg['time_budget_s']:
            if not self._budget_warned:
                self._budget_warned = True
                self.event('error', 'flight time over the budget of %.0f s; the time guard lands the drone' % self.cfg['time_budget_s'])
            self._guard_land()
        self._sample()

    def _guard_land(self):
        """Guard landing: land, and refuse every later flight command (review 17.11, item 2)."""
        if self.armed:
            self._descend()
        self.landed_by_guard = True
        self.stopped = True
        raise ProgramStopped('guard landing')

    def _check_stopped(self):
        if self.stopped:
            raise ProgramStopped('stopped by a guard')

    def _dur(self, v, what):
        """A duration from the student: a finite number, >= 0, <= the hard limit (review item 6)."""
        try:
            f = float(v)
        except (TypeError, ValueError, OverflowError):
            raise ValueError('%s: a number of seconds is needed, not %r' % (what, v))
        if not math.isfinite(f) or f < 0 or f > self.cfg['hard_limit_s']:
            raise ValueError('%s = %r: a number from 0 to %.0f s is needed' % (what, v, self.cfg['hard_limit_s']))
        return f

    def _wait(self, seconds):
        t_end = self.t + seconds
        while self.t < t_end - 1e-9:
            self._tick(min(self.cfg['dt'], t_end - self.t))

    def _descend(self):
        while self.z > self.cfg['z_rest'] + 1e-6:
            step = min(self.cfg['land_mps'] * self.cfg['dt'], self.z - self.cfg['z_rest'])
            self.z -= step
            self.t += self.cfg['dt']
            self._sample()
        self.z = self.cfg['z_rest']
        self.t += self.cfg['land_extra_s']
        self.armed = False
        self._sample(force=True)

    def _move_to(self, x, y, z, duration, speed=None):
        """Move along the straight line in `duration` s (the fitted leg time). 1.4 (24.11): the
        drone no longer slides at an even pace -- it speeds up to `speed`, cruises, slows down
        and waits at the point for the rest of the time. The shape follows the PX4 G2 profile; it was
        NOT compared with Gazebo positions (review 2, 24.11, m8) -- only the total leg time is fitted.
        Same path and the same total time as 1.3; only where the drone is inside the leg changed."""
        x0, y0, z0 = self.x, self.y, self.z
        steps = max(1, int(round(duration / self.cfg['dt'])))
        frac = leg_fractions(math.dist((x0, y0, z0), (x, y, z)), steps * self.cfg['dt'], speed, self.cfg['dt'], steps)
        for k in range(1, steps + 1):
            a = frac[k]
            self.x, self.y, self.z = x0 + a * (x - x0), y0 + a * (y - y0), z0 + a * (z - z0)
            if not self._inside(self.x, self.y):
                self.event('error', 'the drone is leaving the field (%.2f, %.2f); the guard lands the drone' % (self.x, self.y))
                self._guard_land()
            self._tick(self.cfg['dt'])

    def _airborne(self):
        return self.armed and self.z > self.cfg['z_rest'] + 0.2

    # --- student API: map ---------------------------------------------------
    def active_map_name(self):
        return self.mp.get('name', '')

    def require_map(self, name_or_sha):
        sha = bbmap.map_sha(self.mp)
        s = str(name_or_sha).strip()
        name = self.mp.get('name', '')
        by_name = bool(s) and bool(name) and s == name
        by_sha = len(s) >= 8 and all(c in '0123456789abcdef' for c in s.lower()) and sha.startswith(s.lower())
        if by_name or by_sha:
            self.say('map "%s" accepted (%d markers, sha %s)' % (self.mp.get('name'), len(self.ids), sha[:12]))
            return True
        self.event('error', 'the program expects map "%s", the drone has "%s" (sha %s)' % (s, self.mp.get('name'), sha[:12]))
        raise RuntimeError('require_map: the drone has another map')

    def marker_xy(self, marker_id):
        m = self.ids.get(int(marker_id))
        if m is None:
            self.event('error', 'marker %s is not in the map' % marker_id)
            raise RuntimeError('marker_xy: marker %s is not in the map' % marker_id)
        return (m['x'], m['y'])

    def markers_in_view(self):
        return int(round(self.count()))

    def vision_pose_age(self):
        return 0.05 if self.count() >= 0.5 else round(self.t - self._last_seen, 2)

    def check_aruco(self, timeout=10, min_markers=1):
        timeout = self._dur(timeout, 'check_aruco timeout')
        n = self.count()
        if n >= min_markers:
            self._tick(0.2)
            self.say('ArUco markers visible: %d -- OK' % round(n))
            return True
        self._wait(timeout)
        self.event('error', 'at the start the camera does not see %s marker(s); check how the drone stands' % min_markers)
        return False

    def wait_position_stable(self, stable_secs=3.0, tolerance=0.15, timeout=30.0, **_kw):
        stable_secs = self._dur(stable_secs, 'wait_position_stable stable_secs')
        timeout = self._dur(timeout, 'wait_position_stable timeout')
        if self.count() >= 1:
            self._wait(stable_secs)
            return True
        self._wait(timeout)
        self.event('error', 'the position did not become stable: no markers in view')
        return False

    # --- student API: flight ------------------------------------------------
    def takeoff(self, height=1.0, speed=0.4, vision_timeout=25.0):
        self._check_stopped()
        if self.armed:
            self.say('takeoff refused: already armed')
            return False
        height, speed = float(height), float(speed)
        lo, hi = self.cfg['takeoff_min'], self.cfg['takeoff_max']
        if not lo <= height <= hi:
            self.event('error', 'guard: takeoff to %s m is outside the tested %.1f-%.1f m; command refused' % (_num(height), lo, hi))
            return False
        if not 0 < speed <= self.cfg['climb_speed_max']:
            self.event('error', 'guard: climb speed %s m/s is outside 0-%.1f; command refused' % (_num(speed), self.cfg['climb_speed_max']))
            return False
        if self.count() < 1:
            self.event('error', 'guard: no marker in view on the ground; takeoff refused')
            return False
        self.say('=== TAKEOFF to %.1fm ===' % height)
        self.armed = True
        self.event('info', 'arming and takeoff to %.2f m' % height)
        self._wait(self.cfg['arm_delay_s'])
        target = self.z + height
        self._move_to(self.x, self.y, target, height / self.cfg['climb_mps'], self.cfg['climb_mps'])
        self._wait(self.cfg['climb_hold_s'])
        return True

    def _nav(self, x, y, z, speed, what):
        self._check_stopped()
        if not self._airborne():
            self.event('error', '%s: the drone is not in the air; command refused' % what)
            return False
        if z is None:
            z = self.z
        if not 0 < speed <= self.cfg['speed_max']:      # also refuses NaN (review item 20)
            self.event('error', 'guard: speed %s m/s is outside the tested 0-%.2f; command refused' % (_num(speed), self.cfg['speed_max']))
            return False
        if not self.cfg['z_min'] <= z <= self.cfg['z_max']:
            self.event('error', 'guard: height z=%s is outside the tested %.2f-%.2f; command refused' % (_num(z), self.cfg['z_min'], self.cfg['z_max']))
            return False
        if not self._inside(x, y):
            self.event('error', 'guard: point (%s, %s) is outside the field; command refused' % (_num(x), _num(y)))
            return False
        d = math.dist((self.x, self.y, self.z), (x, y, z))
        self.say('=== %s (%.2f, %.2f, %.2f) ===' % (what.upper(), x, y, z))
        duration = d / speed + self.cfg['leg_overhead_s']
        if duration > self.cfg['nav_timeout_s']:
            part = self.cfg['nav_timeout_s'] / duration
            self._move_to(self.x + part * (x - self.x), self.y + part * (y - self.y), self.z + part * (z - self.z),
                          self.cfg['nav_timeout_s'])
            self.event('warn', '%s: did not arrive within %.0f s (too slow or too far)' % (what, self.cfg['nav_timeout_s']))
            return False
        self._move_to(x, y, z, duration, speed)
        return True

    # default speed 0.10 m/s: the tested speed (drone.py has 0.5 -> refused by the guard)
    def fly_to(self, x, y, z=None, speed=0.10, tolerance=0.2, tolerance_adaptive=False, settle_speed=None):
        return self._nav(float(x), float(y), None if z is None else float(z), float(speed), 'fly to')

    def fly_to_marker(self, marker_id, z=None, speed=0.10, quorum=2, quorum_timeout=None):
        self._check_stopped()
        x, y = self.marker_xy(marker_id)
        if not self._airborne():
            self.event('error', 'fly_to_marker: the drone is not in the air; command refused')
            return False
        t_lim = self.cfg['quorum_timeout_s'] if quorum_timeout is None else self._dur(quorum_timeout, 'quorum_timeout')
        # quorum of N within the timeout needs one good frame: the mean count >= N - 0.5
        if self.count() < quorum - 0.5:
            self._wait(t_lim)
            if self.count() < quorum - 0.5:
                self.event('warn', 'before flying to marker %s fewer than %s markers were in view for %.0f s; command not executed' % (marker_id, quorum, t_lim))
                return False
        return self._nav(x, y, None if z is None else float(z), float(speed), 'fly to marker %s' % marker_id)

    def move(self, x=0, y=0, z=0, speed=0.10):
        """Relative to the drone: x forward, y left, z up (drone.py frame_id='body')."""
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        x, y = float(x), float(y)
        tx, ty = self.x + c * x - s * y, self.y + s * x + c * y
        return self._nav(tx, ty, self.z + float(z), float(speed), 'move')

    def hover(self, seconds=3.0):
        self._check_stopped()
        seconds = self._dur(seconds, 'hover')
        if not self._airborne():
            self.say('hover: not in the air')
            return False
        self._wait(seconds)
        return True

    def safe_land(self, x=None, y=None, precision_speed=0.10, precision_tolerance=0.07, timeout=25.0):
        """Landing is never refused; the approach speed is limited to the tested speed (review item 5)."""
        if not self.armed:
            return True
        self.say('=== LANDING ===')
        try:
            v = float(precision_speed)
        except (TypeError, ValueError):
            v = float('nan')
        if not 0 < v <= self.cfg['speed_max']:
            self.event('warn', 'landing approach speed %s m/s limited to %.2f m/s' % (_num(v), self.cfg['speed_max']))
            v = self.cfg['speed_max']
        if x is not None and y is not None:
            tx, ty = float(x), float(y)
            if self._inside(tx, ty):
                d = math.hypot(tx - self.x, ty - self.y)
                self._move_to(tx, ty, self.z, d / v + 0.5, v)
            else:
                self.event('warn', 'landing point (%s, %s) is outside the field; landing where it is' % (_num(tx), _num(ty)))
        self._descend()
        self.event('info', 'landing')
        return True

    def land_on_marker(self, marker_id):
        x, y = self.marker_xy(marker_id)
        return self.safe_land(x, y)

    def land(self):
        if self.armed:
            self._descend()
            self.event('info', 'landing (AUTO.LAND) where it is')
        return True

    # --- telemetry and the rest -------------------------------------------------
    def get_pos(self, frame_id='map'):
        return (self.x, self.y, self.z)

    def print_pos(self, phase='INFO'):
        self.say('[%s] x=%.2f y=%.2f z=%.2f' % (phase, self.x, self.y, self.z))

    def enable_safe_interrupt(self):
        return None

    def check_flight_profile(self, profile_name):
        self.say('check_flight_profile(%s): not checked in the simulation' % profile_name)
        return (1, 1, [])

    def _light(self, *a, **kw):
        return None

    def beep(self, count=1, *a, **kw):
        self.say('beep x%d' % int(count))

    def play_sound(self, name, *a, **kw):
        self.say('sound "%s"' % name)


def _num(v):
    """A number for a message: 2 decimals, or its repr if it is not finite."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return repr(v)
    return ('%.2f' % f) if math.isfinite(f) else repr(f)


def student_module(fd):
    """A module-like object with ONLY the student API names.

    Each name is a plain wrapper function, not a bound method, so there is no
    __self__ pointing at the fake drone (review 17.11, item 1). Dunder access
    is refused by codecheck; the real isolation is the Web Worker / process.
    """
    import types
    from .codecheck import STUDENT_API
    mod = types.ModuleType('drone')

    def wrap(name):
        target = fd._light if name in ('led_solid', 'led_blink', 'led_off', 'led_rainbow', 'led_breathe') else getattr(fd, name)

        def api(*args, **kwargs):
            return target(*args, **kwargs)
        api.__name__ = name
        api.__qualname__ = name
        return api

    for name in STUDENT_API:
        if name != 'should_land':
            setattr(mod, name, wrap(name))
    mod.should_land = False
    return mod


def fake_time_module(fd, epoch=1794850000.0):
    import time as real_time
    import types
    mod = types.ModuleType('time')

    def sleep(s):
        fd._check_stopped()
        fd._wait(fd._dur(s, 'time.sleep'))

    mod.sleep = sleep
    mod.time = lambda: epoch + fd.t
    mod.monotonic = lambda: fd.t
    mod.perf_counter = lambda: fd.t
    mod.strftime = lambda fmt, tt=None: real_time.strftime(fmt, real_time.gmtime(epoch + fd.t) if tt is None else tt)
    mod.localtime = lambda s=None: real_time.gmtime(epoch + fd.t if s is None else s)
    mod.gmtime = mod.localtime
    return mod
