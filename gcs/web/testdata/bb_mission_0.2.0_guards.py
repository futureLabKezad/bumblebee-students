"""Layer 3: the limits every student command passes through (17.11.2026).

Plan R1: outside the tested range the guard REFUSES the command. Landing is
never refused. After a guard landing no flight command runs again
(independent review 17.11, item 2). Heights are measured from the floor the
drone took off from (z at takeoff), not from EKF z (review item 17: the EKF z
zero drifts -0.57..+0.28 between Gazebo runs).

The same numbers as the simulation (bbflight.fakedrone.DEFAULTS), approved by
the owner as the tested range; changing them is the owner's decision.
"""
import math

LIMITS = {
    'takeoff_min': 0.5, 'takeoff_max': 1.3,      # C7 «метка» 0.9, «петля» 1.3 (Gazebo)
    'climb_speed_max': 0.4,
    'height_min': 0.41, 'height_max': 1.31,      # above the takeoff floor (sim: z 0.30..1.20 with floor -0.11)
    'speed_max': 0.10,                           # tested speed; above -> refused
    'field_margin': 0.30,
    'time_budget_s': 300.0,
    'vision_timeout_s': 6.0,                     # drone.py navigate_wait vision_timeout
    'quorum_timeout_s': 15.0,
    'duration_max_s': 1800.0,
    # Battery (owner 17.11, via chat 1): 6S LiHV 4500 mAh, full 4.35 V/cell = 26.1 V; the owner's landing
    # threshold is 20 V REAL, at once. PX4 overstates the voltage the more, the lower the charge
    # (multimeter/PX4: 24.2/24.23, 23.7/23.96, 23.4/23.84, 22.7/23.58, 22.6/23.50), so until that is
    # fixed: warn and land at 23.0 V AS SHOWN BY PX4. No current sensor: flight time by the timer only.
    # The PX4 percentage is computed for 4.2 V/cell -- wrong, never shown as the truth.
    'land_voltage_px4': 23.0,
}


def battery_low(voltage, lim=None):
    """True when the PX4 voltage is known and at or below the landing threshold."""
    v = (lim or LIMITS)['land_voltage_px4']
    try:
        f = float(voltage)
    except (TypeError, ValueError):
        return False
    return math.isfinite(f) and 0.0 < f <= v


class ProgramStopped(BaseException):
    """The guard ended the program. BaseException: "except Exception" must not catch it."""


class Refused(Exception):
    """A command outside the tested range: the command is not sent, the call returns False."""


def finite(v, what):
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        raise Refused('%s: a number is needed, not %r' % (what, v))
    if not math.isfinite(f):
        raise Refused('%s: the number %r is not valid' % (what, v))
    return f


class Guard:
    def __init__(self, bounds, limits=None):
        """bounds: (xmin, ymin, xmax, ymax) of the marker corners of the ACTIVE map."""
        self.lim = dict(LIMITS)
        if limits:
            self.lim.update(limits)
        m = self.lim['field_margin']
        self.field = (bounds[0] - m, bounds[1] - m, bounds[2] + m, bounds[3] + m)
        self.stopped = False
        self.t_takeoff = None        # clock value at the first takeoff
        self.floor_z = None          # map z of base_link right before takeoff

    # --- checks that raise Refused (the command is not sent) -----------------
    def duration(self, v, what):
        f = finite(v, what)
        if not 0 <= f <= self.lim['duration_max_s']:
            raise Refused('%s = %r: a number from 0 to %.0f s is needed' % (what, v, self.lim['duration_max_s']))
        return f

    def takeoff(self, height, speed):
        self.check_running()
        h, v = finite(height, 'takeoff height'), finite(speed, 'takeoff speed')
        if not self.lim['takeoff_min'] <= h <= self.lim['takeoff_max']:
            raise Refused('takeoff to %.2f m is outside the tested %.1f–%.1f m' % (h, self.lim['takeoff_min'], self.lim['takeoff_max']))
        if not 0 < v <= self.lim['climb_speed_max']:
            raise Refused('takeoff speed %.2f m/s is outside 0–%.1f' % (v, self.lim['climb_speed_max']))
        return h, v

    def inside(self, x, y):
        x0, y0, x1, y1 = self.field
        return x0 <= x <= x1 and y0 <= y <= y1

    def target(self, x, y, z, speed):
        """Check a fly-to target; returns (x, y, z, speed) as floats."""
        self.check_running()
        x, y, z, v = finite(x, 'x'), finite(y, 'y'), finite(z, 'z'), finite(speed, 'speed')
        if not 0 < v <= self.lim['speed_max']:
            raise Refused('speed %.2f m/s is outside the tested 0–%.2f' % (v, self.lim['speed_max']))
        if not self.inside(x, y):
            raise Refused('point (%.2f, %.2f) is outside the field' % (x, y))
        if self.floor_z is None:
            raise Refused('the drone has not taken off — takeoff first')
        hz = z - self.floor_z
        if not self.lim['height_min'] <= hz <= self.lim['height_max']:
            raise Refused('height above the floor %.2f m is outside the tested %.2f–%.2f' % (hz, self.lim['height_min'], self.lim['height_max']))
        return x, y, z, v

    def landing_speed(self, v):
        """Landing is never refused: the approach speed is limited instead (review item 5)."""
        try:
            f = float(v)
        except (TypeError, ValueError):
            f = float('nan')
        if not (math.isfinite(f) and 0 < f <= self.lim['speed_max']):
            return self.lim['speed_max'], True
        return f, False

    # --- state ----------------------------------------------------------------
    def check_running(self):
        if self.stopped:
            raise ProgramStopped('the program was stopped by a guard')

    def over_budget(self, now):
        return self.t_takeoff is not None and now - self.t_takeoff > self.lim['time_budget_s']
