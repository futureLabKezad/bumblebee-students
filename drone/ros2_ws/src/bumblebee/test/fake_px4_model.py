"""Deterministic, deliberately limited PX4 command/state model, without ROS.

This is a test model, not PX4 and not a replacement for a SITL deployment gate.
Times are injected monotonic seconds. Position dynamics omit attitude, estimator,
motor and aerodynamic behaviour. Resuming OFFBOARD after a POSCTL or AUTO.LAND
fallback is an explicit scenario option representing retained OFFBOARD intention.
It models mode availability, not MAVLink/DDS buffering or navigator trajectories.
"""
import math


class Px4Model:
    def __init__(self, now=0.0, mode='POSCTL', armed=False, pose=(0., 0., 0.),
                 floor_z=0.0, of_loss_t=1.0, obl_rc_act=0, dynamics=False,
                 resume_offboard=False, preflight_disarm_s=30.0,
                 land_disarm_s=2.0, land_speed=0.5):
        self.mode = mode
        self.intended_mode = mode
        self.armed = armed
        self.connected = True
        self.pose = tuple(pose)
        self.floor_z = floor_z
        self.of_loss_t = of_loss_t
        self.obl_rc_act = obl_rc_act
        self.dynamics = dynamics
        self.resume_offboard = resume_offboard
        self.preflight_disarm_s = preflight_disarm_s
        self.land_disarm_s = land_disarm_s
        self.land_speed = land_speed
        self.last_setpoint = -math.inf
        self.target = tuple(pose)
        self.arm_time = now if armed else None
        self.ever_airborne = armed and pose[2] > floor_z + 0.1
        self.touchdown_time = None
        self.last_tick = now
        self.offboard_fallback = False
        self.statustext = []
        self.events = []
        self.vz = 0.0

    def _event(self, now, kind, value):
        self.events.append((now, kind, value))

    def _deny(self, now, text):
        self.statustext.append((now, text))
        self._event(now, 'denial', text)
        return False

    def streaming(self, now):
        return now - self.last_setpoint < self.of_loss_t

    def setpoint(self, now, pose):
        self.last_setpoint = now
        self.target = tuple(pose)
        if (self.resume_offboard and self.offboard_fallback and
                self.intended_mode == 'OFFBOARD' and
                self.mode in ('POSCTL', 'AUTO.LAND')):
            self.mode = 'OFFBOARD'
            self.offboard_fallback = False
            self._event(now, 'mode', self.mode)

    def pilot_mode(self, now, mode):
        self.mode = self.intended_mode = mode
        self.offboard_fallback = False
        self._event(now, 'pilot_mode', mode)

    def command_mode(self, now, mode, accept_offboard=True):
        # Disarmed OFFBOARD is accepted without a stream. An armed switch needs
        # a usable stream. mode_sent on the ROS side means sent, not accepted.
        if mode == 'OFFBOARD' and (not accept_offboard or
                                  (self.armed and not self.streaming(now))):
            return self._deny(now, 'OFFBOARD denied: no recent setpoint')
        self.mode = self.intended_mode = mode
        self.offboard_fallback = False
        self._event(now, 'mode', mode)
        return True

    def command_arm(self, now, value, deny_disarm=False, deny_arm=False):
        if not value:
            if deny_disarm or (self.armed and abs(self.pose[2] - self.floor_z) > 0.1):
                return self._deny(now, 'Disarming denied: not landed')
            self.armed = False
            self.arm_time = None
            self._event(now, 'disarm', 'external command')
            return True
        if self.armed:
            return True
        if deny_arm:
            return self._deny(now, 'Arming denied by test prearm check')
        if self.mode in ('AUTO.LAND', 'AUTO.RTL', 'AUTO.DESCEND', 'DESCEND'):
            return self._deny(now, 'Arming denied in ' + self.mode)
        if self.mode == 'OFFBOARD' and not self.streaming(now):
            return self._deny(now, 'Arming denied: no recent OFFBOARD setpoint')
        self.armed = True
        self.arm_time = now
        self.ever_airborne = self.pose[2] > self.floor_z + 0.1
        self.touchdown_time = None
        self._event(now, 'arm', True)
        return True

    def heartbeat(self):
        # MAVROS disconnection state is unknown, rather than a real DISARM.
        return (self.connected, self.armed if self.connected else False,
                self.mode if self.connected else '')

    def tick(self, now):
        dt = max(0.0, now - self.last_tick)
        self.last_tick = now
        if self.armed and self.mode == 'OFFBOARD' and not self.streaming(now):
            self.mode = 'AUTO.LAND' if self.obl_rc_act == 4 else 'POSCTL'
            self.offboard_fallback = True
            self._event(now, 'offboard_loss', self.mode)
        self.vz = 0.0
        if not self.dynamics or not self.armed:
            return
        x, y, z = self.pose
        if self.mode == 'AUTO.LAND':
            next_z = max(self.floor_z, z - self.land_speed * dt)
        elif self.mode == 'OFFBOARD' and self.streaming(now):
            next_z = z + max(-0.5 * dt, min(0.5 * dt, self.target[2] - z))
        else:
            next_z = z
        self.vz = (next_z - z) / dt if dt else 0.0
        self.pose = (x, y, next_z)
        if next_z > self.floor_z + 0.1:
            self.ever_airborne = True
        if next_z <= self.floor_z + 1e-9:
            if self.touchdown_time is None:
                self.touchdown_time = now
            if (self.mode == 'AUTO.LAND' and
                    now - self.touchdown_time >= self.land_disarm_s):
                self.armed = False
                self.arm_time = None
                self._event(now, 'disarm', 'auto_disarm_land')
        else:
            self.touchdown_time = None
        if (self.armed and not self.ever_airborne and self.arm_time is not None and
                now - self.arm_time >= self.preflight_disarm_s):
            self.armed = False
            self.arm_time = None
            self._event(now, 'disarm', 'auto_disarm_preflight')
