# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
drone.py -- core flight library for Bumblebee drone (ROS2).

All service clients, navigation helpers, and safety utilities live here.
Import this file in any flight script instead of duplicating boilerplate.

Quick start:
    import sys
    sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
    import drone

    drone.check_aruco()
    drone.takeoff(1.0)
    drone.fly_to(x=0, y=1.88, z=1)
    drone.fly_to(x=0, y=0,    z=1)
    drone.safe_land(x=0, y=0)

LED strip control (I2C -> ATtiny slave at 0x30):
    drone.set_led(drone.LED_3, 5, 0, 0, 100)   # strip 3, pixel 5, blue
    drone.set_led(drone.STRIP_ALL, drone.LED_ALL, 255, 0, 0)  # all red
    drone.led_off()                             # all off

Servo control (standard servo, VSG connector 2):
    drone.set_servo_angle(0)    # min angle
    drone.set_servo_angle(128)  # center
    drone.set_servo_angle(255)  # max angle

Wheel module (continuous servo / ESC, wheel VSG connector):
    drone.set_servo_speed(128)  # stop (neutral)
    drone.set_servo_speed(160)  # slow forward
    drone.set_servo_speed(20)   # slow reverse
    drone.set_servo_speed(255)  # full forward
    drone.set_servo_speed(0)    # full reverse

    t_dc, t_main = drone.read_temperature()  # read board temperatures (°C)
"""

import atexit
import contextlib
import math
import os
import signal
import subprocess
import sys
import time
import threading

try:
    import smbus2 as _smbus2
    _SMBUS2_OK = True
except ImportError:
    _SMBUS2_OK = False

# ROS2 imports are deferred to _init() so LED functions work without
# sourcing the ROS2 environment (e.g. python3 led_strip.py).
rclpy      = None
Node       = None
srv        = None
Trigger    = None
CommandBool = None
SetMode    = None
ParamSetV2     = None
ParamPull      = None
ParameterValue = None
ParameterType  = None
MarkerArray    = None
Int32          = None
Bool           = None
PlayTuneV2     = None
State          = None
BatteryState   = None
GetParameters  = None
QoSProfile        = None
ReliabilityPolicy = None
DurabilityPolicy  = None


def _ros2_import():
    """Import ROS2 modules on first flight call."""
    global rclpy, Node, srv, Trigger, CommandBool, SetMode
    global ParamSetV2, ParamPull, ParameterValue, ParameterType, MarkerArray, Int32, Bool
    global GetParameters
    global PlayTuneV2
    global State, BatteryState, QoSProfile, ReliabilityPolicy, DurabilityPolicy
    if rclpy is not None:
        return
    import rclpy as _rclpy
    from rclpy.node import Node as _Node
    from bumblebee import srv as _srv
    from std_srvs.srv import Trigger as _Trigger
    from mavros_msgs.srv import CommandBool as _CB, SetMode as _SM, ParamSetV2 as _PS, ParamPull as _PP
    from rcl_interfaces.msg import ParameterValue as _PV, ParameterType as _PT
    from rcl_interfaces.srv import GetParameters as _GP
    from aruco_pose.msg import MarkerArray as _MA
    from std_msgs.msg import Int32 as _I32, Bool as _BO
    from mavros_msgs.msg import State as _State
    from sensor_msgs.msg import BatteryState as _BatteryState
    from rclpy.qos import (QoSProfile as _QoSP,
                           QoSReliabilityPolicy as _RP,
                           QoSDurabilityPolicy as _DP)
    State        = _State
    BatteryState = _BatteryState
    QoSProfile        = _QoSP
    ReliabilityPolicy = _RP
    DurabilityPolicy  = _DP
    rclpy       = _rclpy
    Node        = _Node
    srv         = _srv
    Trigger     = _Trigger
    CommandBool = _CB
    SetMode     = _SM
    ParamSetV2  = _PS
    ParamPull   = _PP
    GetParameters = _GP
    ParameterValue = _PV
    ParameterType  = _PT
    MarkerArray = _MA
    Int32       = _I32
    Bool        = _BO
    # PlayTuneV2 lives in mavros_msgs but older MAVROS builds may lack it.
    # Keep the import optional so the rest of the API stays usable.
    try:
        from mavros_msgs.msg import PlayTuneV2 as _PTV2
        globals()['PlayTuneV2'] = _PTV2
    except ImportError:
        globals()['PlayTuneV2'] = None

# ---------------------------------------------------------------------------
# LED strip constants  (ATtiny PA-pin indices used in I2C protocol)
# ---------------------------------------------------------------------------

LED_1    = 0   # PA0
LED_2    = 5   # PA5
LED_3    = 1   # PA1
LED_4    = 3   # PA3
LED_5    = 2   # PA2
LED_6    = 4   # PA4
LED_ALL  = 255  # all pixels in a strip
STRIP_ALL = 255  # all strips

_I2C_ADDR = 0x30  # ATtiny slave address
_REG_LED   = 0x04  # set LED command
_REG_SERVO = 0x01  # servo angle command
_REG_SPEED = 0x02  # wheel speed command
_REG_TEMP  = 0x03  # temperature request command

# ---------------------------------------------------------------------------
# Buzzer / PX4 PLAY_TUNE_V2 constants and presets
# ---------------------------------------------------------------------------
#
# Tunes are sent to /mavros/play_tune (mavros_msgs/PlayTuneV2). PX4 supports
# two encodings; we default to the simpler QBASIC one. The MAVLink
# PLAY_TUNE_V2 message hard-caps the tune string at 230 chars -- presets
# below stay well inside that limit.

TUNE_FORMAT_QBASIC = 1   # PlayTuneV2.QBASIC1_1
TUNE_FORMAT_MML    = 2   # PlayTuneV2.MML_MODERN

# Short notification tunes
TUNE_BEEP   = 'MFT200L32O5C'                       # ~0.1s beep
TUNE_OK     = 'MFT180L8O5CEG'                      # major triad C-E-G
TUNE_ERROR  = 'MFT180L8O5GEC<G'                    # descending minor motif
TUNE_NOTIFY = 'MFT180L8O5E4C4'                     # two-tone ding-dong
TUNE_ARMING = 'MFT180L8O4G4O5C4'                   # ready chirp

# Event tunes (call via play_sound('victory'), etc.)
TUNE_VICTORY   = 'MFT180L8O5CEGO6CL4C'          # rising fanfare -> high C
TUNE_FAIL      = 'MFT160L8O5C<L4AL8GL2<F'       # sad descending "wah"
TUNE_TAKEOFF   = 'MFT200L16O4CEGO5CEGO6C'       # quick rising run on lift-off
TUNE_LAND      = 'MFT200L16O6CO5GECO4GEC'       # mirror descending run on land
TUNE_WARN      = 'MFT200L16O5AP16AP16A'         # three urgent chirps
TUNE_COUNTDOWN = 'MFT160L8O5CP8CP8CP4O6C'       # 3-2-1-go ticks
TUNE_STARTUP   = 'MFT180L16O4CO5CO4GO5EC'       # boot/ready jingle

# Recognisable melodies (first phrase of each, QBASIC encoding)
TUNE_IMPERIAL_MARCH = 'MFT120L4O4GGGL8E<L16B>L4GL8E<L16B>L2G'
TUNE_MARIO          = 'MFT200L8O5EEP8EP8CEP8GP8P4<GP4'
TUNE_TETRIS         = 'MFT160L4O5EL8BL8>CL4DL8>CL8<BL4AL8AL8>CL4EL8DL8>C'

_i2c_bus = None

# Cross-process lock serializing all ATtiny 0x30 I2C access. notify_manager,
# wheel_rc and servo_rc each run these writers in a SEPARATE process; without a
# shared lock their transactions interleave on the same slave, and the ATtiny's
# clock-stretching can wedge the RP1 I2C bus (writers stuck in kernel D-state) --
# the exact failure the boot-time i2c_recover.sh works around. flock is released
# by the OS if the holder dies (no deadlock), and the 40 ms I2C_TIMEOUT ioctl in
# _led_init caps any single stuck transaction.
_I2C_LOCK_FILE = '/tmp/i2c_bus.lock'
_i2c_lock_fd = None


@contextlib.contextmanager
def _i2c_lock():
    """Serialize an I2C transaction across all processes that import drone."""
    global _i2c_lock_fd
    import fcntl
    if _i2c_lock_fd is None:
        _i2c_lock_fd = os.open(_I2C_LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o666)
    fcntl.flock(_i2c_lock_fd, fcntl.LOCK_EX)
    try:
        yield
    finally:
        try:
            fcntl.flock(_i2c_lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass


def _led_init():
    """Lazy-open I2C bus 1 with a short per-transaction timeout."""
    global _i2c_bus
    if _i2c_bus is not None:
        return
    if not _SMBUS2_OK:
        raise RuntimeError('smbus2 not installed -- run: pip3 install smbus2')
    import fcntl
    _i2c_bus = _smbus2.SMBus(1)
    # I2C_TIMEOUT (0x0702): cap each transaction at N jiffies.
    # Ubuntu HZ=250 -> 1 jiffy = 4ms; 10 jiffies = 40ms.
    # This prevents the RP1 I2C driver from blocking forever when
    # the ATtiny slave is busy / clock-stretching.
    try:
        fcntl.ioctl(_i2c_bus.fd, 0x0702, 10)
    except OSError:
        pass  # driver may ignore it; we still get Python TimeoutError


def _i2c_write_block(reg, data):
    """Write a block of bytes over I2C, reopening the bus on error."""
    global _i2c_bus
    with _i2c_lock():
        for attempt in range(2):
            try:
                _i2c_bus.write_i2c_block_data(_I2C_ADDR, reg, data)
                return
            except OSError:
                if attempt == 0:
                    # Bus error -- close and reopen
                    try:
                        _i2c_bus.close()
                    except Exception:
                        pass
                    _i2c_bus = None
                    time.sleep(0.01)
                    _led_init()
                else:
                    raise


def _i2c_write_byte(reg, value):
    """Write a single byte over I2C, reopening the bus on error."""
    global _i2c_bus
    with _i2c_lock():
        for attempt in range(2):
            try:
                _i2c_bus.write_byte_data(_I2C_ADDR, reg, value)
                return
            except OSError:
                if attempt == 0:
                    try:
                        _i2c_bus.close()
                    except Exception:
                        pass
                    _i2c_bus = None
                    time.sleep(0.01)
                    _led_init()
                else:
                    raise


def set_led(strip, led, r, g, b):
    """
    Set color of one LED or a whole strip via I2C.

    Args:
        strip  -- strip index (LED_1..LED_6) or STRIP_ALL (255) for all strips
        led    -- pixel index within strip (0-10) or LED_ALL (255) for all pixels
        r,g,b  -- brightness 0-255
    """
    _led_init()
    _i2c_write_block(_REG_LED, [strip & 0xFF, led & 0xFF,
                                r & 0xFF, g & 0xFF, b & 0xFF])
    time.sleep(0.010)


def led_off():
    """Turn off all LED strips."""
    set_led(STRIP_ALL, LED_ALL, 0, 0, 0)


# Lock file used to pause led_default.py while another script controls LEDs.
_LED_BUSY_FILE = '/tmp/led_busy'


def led_take_control():
    """
    Pause led_default.py and take exclusive LED control.

    Creates /tmp/led_busy. led_default.py polls this file and waits
    while it exists. Call led_release_control() when done.
    """
    open(_LED_BUSY_FILE, 'w').close()
    time.sleep(0.4)  # give led_default one poll cycle to stop


def led_release_control():
    """
    Release LED control back to led_default.py.

    Removes /tmp/led_busy so led_default.py resumes its pattern.
    """
    try:
        os.remove(_LED_BUSY_FILE)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# High-level LED animations
# ---------------------------------------------------------------------------
#
# These are blocking helpers: each runs for `duration` seconds and then
# returns. By default (manage_control=True) they take the /tmp/led_busy lock
# on entry so notify_manager pauses its background pattern, and release it on
# exit (in a finally), after which notify_manager resumes on its own.
#
# Only one writer touches the I2C bus (0x30) at a time -- there are no
# background timers/threads here, which keeps the bus safe.
#
# Frame period; the ATtiny write itself already sleeps ~10 ms (see set_led).
_LED_FRAME = 0.05

# Approximate ring order of the 6 strips around the airframe, used by
# led_rotate / led_wipe: front-L -> body-L -> rear-L -> rear-R -> body-R ->
# front-R.
LED_RING = [LED_2, LED_4, LED_1, LED_3, LED_5, LED_6]


def _hue_to_rgb(h):
    """Convert hue (0-359 degrees) to (r, g, b) at full saturation/value."""
    h = h % 360
    sector = int(h // 60)
    frac = (h % 60) / 60.0
    tbl = [
        (255, int(255 * frac), 0),
        (int(255 * (1 - frac)), 255, 0),
        (0, 255, int(255 * frac)),
        (0, int(255 * (1 - frac)), 255),
        (int(255 * frac), 0, 255),
        (255, 0, int(255 * (1 - frac))),
    ]
    return tbl[sector]


@contextlib.contextmanager
def _led_session(manage_control):
    """Optionally take/release the /tmp/led_busy lock around an animation."""
    if manage_control:
        led_take_control()
    try:
        yield
    finally:
        if manage_control:
            led_off()
            led_release_control()


def led_solid(r, g, b, duration=None, strip=STRIP_ALL, manage_control=True):
    """
    Fill `strip` (default all) with a solid color.

    duration=None  -- set the color and HOLD it. When manage_control=True the
                      /tmp/led_busy lock is taken and NOT released, so
                      notify_manager stays paused until you call led_off() or
                      led_release_control() (or another effect). Use this for a
                      persistent color.
    duration=<sec> -- hold the color for that long, then release control and
                      let notify_manager resume.
    """
    if duration is None:
        if manage_control:
            led_take_control()
        set_led(strip, LED_ALL, r, g, b)
        return
    with _led_session(manage_control):
        set_led(strip, LED_ALL, r, g, b)
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            time.sleep(_LED_FRAME)


def led_blink(r, g, b, freq=4.0, duration=3.0, strip=STRIP_ALL, manage_control=True):
    """Blink a color on/off at `freq` Hz for `duration` seconds."""
    with _led_session(manage_control):
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            on = int((time.monotonic() - t0) * freq * 2) % 2 == 0
            if on:
                set_led(strip, LED_ALL, r, g, b)
            else:
                set_led(strip, LED_ALL, 0, 0, 0)
            time.sleep(_LED_FRAME)


def led_strobe(r, g, b, freq=8.0, duration=3.0, strip=STRIP_ALL, manage_control=True):
    """Fast strobe -- same as led_blink but defaults to ~8 Hz (alarm look)."""
    led_blink(r, g, b, freq=freq, duration=duration, strip=strip,
              manage_control=manage_control)


def led_breathe(r, g, b, period=2.0, duration=4.0, min_b=0.1, max_b=1.0,
                strip=STRIP_ALL, manage_control=True):
    """Smooth sine "breathing" between min_b and max_b brightness."""
    w = 2.0 * math.pi / max(period, 1e-3)
    span = max_b - min_b
    with _led_session(manage_control):
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            t = time.monotonic() - t0
            br = min_b + span * (0.5 + 0.5 * math.sin(w * t))
            set_led(strip, LED_ALL, int(r * br), int(g * br), int(b * br))
            time.sleep(_LED_FRAME)


def led_pulse(r, g, b, freq=6.0, duration=3.0, strip=STRIP_ALL, manage_control=True):
    """Quick pulse -- breathing at a higher rate (ArUco-search look)."""
    led_breathe(r, g, b, period=1.0 / max(freq, 1e-3), duration=duration,
                min_b=0.2, max_b=1.0, strip=strip, manage_control=manage_control)


def led_rainbow(duration=5.0, step=6, brightness=0.4, strip=STRIP_ALL,
                manage_control=True):
    """Cycle a full-hue rainbow across `strip` for `duration` seconds."""
    with _led_session(manage_control):
        hue = 0
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            r, g, b = _hue_to_rgb(hue)
            set_led(strip, LED_ALL, int(r * brightness),
                    int(g * brightness), int(b * brightness))
            hue = (hue + step) % 360
            time.sleep(_LED_FRAME)


def led_rotate(r, g, b, duration=4.0, speed=6.0, trail=True, manage_control=True):
    """
    Rotate a single bright strip (a "beacon") around the 6-strip ring.

    speed -- strips advanced per second.
    trail -- if True, the previous strip glows dim for a comet-tail look.
    """
    ring = LED_RING
    n = len(ring)
    tr = (int(r * 0.3), int(g * 0.3), int(b * 0.3))
    with _led_session(manage_control):
        prev = -1
        t0 = time.monotonic()
        while time.monotonic() - t0 < duration:
            pos = int((time.monotonic() - t0) * speed) % n
            if pos != prev:
                prev = pos
                for i, st in enumerate(ring):
                    if i == pos:
                        set_led(st, LED_ALL, r, g, b)
                    elif trail and i == (pos - 1) % n:
                        set_led(st, LED_ALL, *tr)
                    else:
                        set_led(st, LED_ALL, 0, 0, 0)
            time.sleep(_LED_FRAME)


def led_wipe(r, g, b, duration=2.0, manage_control=True):
    """Fill the strips one by one along the ring (a "color wipe")."""
    ring = LED_RING
    n = len(ring)
    hold = max(duration, 0.0) / n
    with _led_session(manage_control):
        for st in ring:
            set_led(st, LED_ALL, r, g, b)
            time.sleep(hold)


def set_servo_angle(angle):
    """
    Set servo angle.

    Args:
        angle -- 0-255 (0 = full left, 128 = center, 255 = full right)
    """
    _led_init()
    _i2c_write_byte(_REG_SERVO, angle & 0xFF)
    time.sleep(0.02)


def set_servo_speed(speed):
    """
    Set wheel motor speed.

    Args:
        speed -- 0-255 (0 = max backward, 128 = stop, 255 = max forward)
    """
    _led_init()
    _i2c_write_byte(_REG_SPEED, speed & 0xFF)
    time.sleep(0.02)


def read_temperature():
    """
    Read temperatures from both on-board sensors.

    Returns:
        (t_dc, t_main) tuple in Celsius, or None on error.
    """
    _led_init()
    try:
        with _i2c_lock():
            _i2c_bus.write_byte(_I2C_ADDR, _REG_TEMP)
            time.sleep(0.05)
            data = _i2c_bus.read_i2c_block_data(_I2C_ADDR, 0, 2)
        t_dc, t_main = data[0], data[1]
        print('Temp: DC=%d°C  MAIN=%d°C' % (t_dc, t_main))
        return t_dc, t_main
    except Exception as e:
        print('Temp read error: ' + str(e))
        return None


# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_initialized = False
_node = None
_executor = None
_spin_thread = None

# Service client handles -- populated by _init()
_get_telemetry_client = None
_navigate_client      = None
_land_client          = None
_arming_client        = None
_set_mode_client      = None
_gate_param_client    = None  # /vpe_fix/set_param -- sole channel for PX4 param writes
_param_pull_client    = None  # /mavros/mavros/pull -- nudge MAVROS to re-emit ParameterEvent stream so gate cache can backfill missing PX4 params
_param_get_client     = None  # /mavros/mavros/get_parameters -- read PX4 params straight from MAVROS (check_flight_profile)
_play_tune_pub        = None  # /mavros/play_tune -- created lazily on first play_tune() call

# ArUco quality signals from /aruco_detect/{markers_used,yaw_locked}.
# Updated by background subscriptions in _init(). Used by preflight gates.
_aruco_markers_used      = 0
_aruco_markers_used_time = None  # time.monotonic() of last update
# Last time markers_used was >= 1. The topic streams ~6 Hz with value 0 when
# frames are dropped (reproj-error gate), so _aruco_markers_used_time alone
# cannot detect "camera alive but no usable markers".
_aruco_markers_pos_time  = None
_aruco_yaw_locked        = False
_aruco_yaw_locked_last_true_time = None  # rclpy Time of last True observation

# Cached FCU status from cheap background subscriptions (/mavros/state,
# /mavros/battery). Lets lightweight consumers (notify_manager) read
# connection/mode/battery WITHOUT the heavy /get_telemetry service call, which
# does TF lookups and stalls under CPU load -- a stall there used to surface as
# a false "FCU lost" -> red ERROR strobe on the LEDs.
_fcu_state_msg   = None   # latest mavros_msgs/State
_fcu_state_time  = None   # time.monotonic() of last State msg (immune to clock steps)
_battery_msg     = None   # latest sensor_msgs/BatteryState
_battery_time    = None   # time.monotonic() of last BatteryState msg

# Pilot wins (A4, 2026-10-13): the Pi never overrides a mode the pilot (RC)
# or a PX4 failsafe chose. Flight calls first wait up to this long for a
# fresh FCU state (the latched /mavros/state arrives shortly after _init());
# without one they refuse instead of guessing.
_FCU_STATE_WAIT = 2.0

# Map z of base_link recorded right before the Pi arms the drone through
# navigate(auto_arm=True), i.e. the floor of this flight (A7). Reference for
# the below-floor guard in navigate_wait and the landed check in arming(False);
# None until this script arms (then 0.0 is used: map z=0 is the resting
# base_link height, see DRONE_REST_Z_OFFSET). Cleared on the disarm edge.
_arm_ref_z = None
# _arm_ref_z of the last arm, kept after the disarm: safe_land's touchdown
# reference when the vehicle is already disarmed (e.g. on a platform after a
# ground-hold DISARM). Replaced at the next arm.
_last_arm_ref_z = None

# simple_offboard's takeoff ground hold (s7fix): after navigate(auto_arm=True)
# armed the drone from the ground, the setpoint stays below the vehicle for
# arm_settle_time (1.5 s) and a /land still disarms it up to 1 s later on a
# climb. Within this window the guards land through /land; later, in flight,
# they switch to AUTO.LAND at once as before. Measured on simple_offboard's
# clock (_hold_now).
_TAKEOFF_HOLD_S = 2.5
_auto_arm_ok_t = None   # _hold_now() of that arm; cleared on the disarm edge

# True once drone.py itself landed the armed vehicle from OFFBOARD (a
# navigate_wait guard, or the AUTO.LAND fallback of a guard or safe_land);
# cleared on the disarm edge or when the mode leaves AUTO.LAND. Only the
# wording depends on it: that landing is this script's, so messages do not
# blame the pilot.
_own_auto_land = False

# arming(False) counts the drone as landed within these limits (the same
# band safe_land uses to confirm touchdown).
_LANDED_DZ = 0.20   # m, |z - height at arm|
_LANDED_VZ = 0.10   # m/s, |vz|

# Set to True when Ctrl+C is pressed -- navigate_wait checks this each loop
should_land = False

# Set to True when navigate_wait aborts on vision loss / stale telemetry.
# safe_land checks it to skip the blind precision approach.
_vision_abort = False

# Path to the active ArUco map file read by the aruco_map node
MAP_FILE = '/home/lb/ros2_ws/src/aruco_pose/map/map.txt'

# Height of base_link above the marker plane when the drone rests on
# the floor. Calibrated for drone .3 (2026-05-12). Used by set_aruco_map
# to shift the map's z=0 plane up to the resting base_link altitude, so
# safe_land's `if t.z < 0.20` check fires when the drone is on the floor.
DRONE_REST_Z_OFFSET = 0.32


def _call(client, req, timeout=5.0, wait=None):
    """Synchronous service call helper (wait: service readiness limit, default timeout)."""
    if not client.wait_for_service(timeout_sec=timeout if wait is None else wait):
        raise Exception('Service %s not available' % client.srv_name)
    result = client.call(req, timeout_sec=timeout)
    if result is None:
        raise Exception('Service %s timed out' % client.srv_name)
    return result


def _cancel_land():
    """/land for a cancelled takeoff; never raises. Returns '/land: <reply>' or why it failed."""
    try:
        reply = land()
        if reply.success:
            return '/land: ' + (reply.message or 'landing (AUTO.LAND)')
        report = '/land rejected: ' + reply.message
    except Exception as e:
        report = '/land failed: %s' % e
    _node.get_logger().warn('Takeoff cancel ' + report)
    return report


def _call_auto_arm(req, timeout=45.0):
    """Await takeoff with cancellation from the ordinary calling thread.

    A Ctrl+C (should_land) seen before this returns is never lost (P2): when
    the success reply completed in the same 50 ms poll, simple_offboard has
    committed the takeoff and holds it on the ground (arm_settle_time); /land
    is requested once (none if a cancel /land already went out) and a failure
    is returned that says so and carries the /land reply.
    """
    global _auto_arm_ok_t
    client = _navigate_client
    future = None
    try:
        if not client.wait_for_service(timeout_sec=timeout):
            raise Exception('Service %s not available' % client.srv_name)
        if should_land:
            result = srv.Navigate.Response()
            result.success = False
            result.message = 'navigate cancelled (Ctrl+C), auto_arm not sent'
            return result
        future = client.call_async(req)
        deadline = time.monotonic() + timeout
        last_land_sent = float('-inf')
        land_report = None   # the last cancel /land's reply or error (P2)
        while not future.done():
            current = time.monotonic()
            if should_land and current - last_land_sent >= 2.0:
                last_land_sent = current
                land_report = _cancel_land()
            if time.monotonic() >= deadline:
                try:
                    land()
                except Exception as e:
                    _node.get_logger().warn('Takeoff timeout /land failed: ' + str(e))
                finally:
                    client.remove_pending_request(future)
                raise Exception('Service %s timed out; takeoff cancel requested' % client.srv_name)
            time.sleep(0.05)
        result = future.result()
        if result is None: raise Exception('Service %s returned no takeoff response' % client.srv_name)
        if should_land and result.success:
            # P2: Ctrl+C seen only after the success reply arrived (it may have come
            # a few ms before simple_offboard's commit tick): the takeoff is committed
            # and still held on the ground -> land it, report a cancel
            if land_report is None:
                _auto_arm_ok_t = _hold_now()   # simple_offboard's ground hold runs now
                land_report = _cancel_land()
            result = srv.Navigate.Response()
            result.success = False
            result.message = 'Takeoff cancelled (Ctrl+C seen after simple_offboard committed the takeoff); ' + land_report
            if not (land_report.startswith('/land: ') and 'disarmed' in land_report):
                result.message += '; motors may be running until landed'
            _node.get_logger().warn(result.message)
            return result
        if 'motors may be running' in result.message:
            _node.get_logger().warn(result.message)
        return result
    except KeyboardInterrupt:
        # Never call services in the signal handler; a plain KeyboardInterrupt reaches this thread.
        try:
            land()
        except Exception as e:
            _node.get_logger().warn('Interrupted takeoff /land failed: ' + str(e))
        finally:
            if future is not None: client.remove_pending_request(future)
        raise


def _init():
    """Initialize ROS2 node and service clients. Runs only once."""
    global _initialized, _node, _executor
    global _get_telemetry_client, _navigate_client, _land_client
    global _arming_client, _set_mode_client, _gate_param_client, _param_pull_client
    global _param_get_client

    if _initialized:
        return

    _ros2_import()

    # Disable rclcpp's built-in SIGINT handler so it doesn't call rcl_shutdown()
    # when Ctrl+C is pressed -- our custom handler in enable_safe_interrupt() handles it.
    try:
        from rclpy.signals import SignalHandlerOptions
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    except (ImportError, AttributeError):
        rclpy.init()
    _node = Node('flight')

    _get_telemetry_client = _node.create_client(srv.GetTelemetry, '/get_telemetry')
    _navigate_client      = _node.create_client(srv.Navigate,     '/navigate')
    _land_client          = _node.create_client(Trigger,          '/land')
    # MAVROS 2.14 (the drone) with launch name='mavros': the __node remap also
    # renames every plugin node, so plugin services live under /mavros/mavros/
    # (same target as simple_offboard's arming remap). /mavros/cmd/arming only
    # exists on MAVROS >= 2.15, and launch remaps do not reach this node.
    _arming_client        = _node.create_client(CommandBool,      '/mavros/mavros/arming')
    _set_mode_client      = _node.create_client(SetMode,          '/mavros/set_mode')
    _gate_param_client    = _node.create_client(srv.SetParam,     '/vpe_fix/set_param')
    _param_pull_client    = _node.create_client(ParamPull,       '/mavros/mavros/pull')
    # The MAVROS param plugin node is renamed to /mavros/mavros (launch
    # mavros_scoped_config.py: -r param:__node:=mavros), so its own
    # GetParameters sits next to /mavros/mavros/pull and answers from
    # MAVROS's parameter table (no /parameter_events stream).
    _param_get_client     = _node.create_client(GetParameters,   '/mavros/mavros/get_parameters')

    # Subscribe to ArUco quality signals so preflight helpers can gate on them.
    def _on_markers_used(msg):
        global _aruco_markers_used, _aruco_markers_used_time, _aruco_markers_pos_time
        _aruco_markers_used = int(msg.data)
        _aruco_markers_used_time = time.monotonic()
        if _aruco_markers_used >= 1:
            _aruco_markers_pos_time = _aruco_markers_used_time

    def _on_yaw_locked(msg):
        global _aruco_yaw_locked, _aruco_yaw_locked_last_true_time
        _aruco_yaw_locked = bool(msg.data)
        if _aruco_yaw_locked:
            _aruco_yaw_locked_last_true_time = _node.get_clock().now()

    _node.create_subscription(Int32, '/aruco_detect/markers_used', _on_markers_used, 10)
    _node.create_subscription(Bool,  '/aruco_detect/yaw_locked',   _on_yaw_locked,   10)

    # Cheap FCU status subscriptions (see get_fcu_status). /mavros/state is
    # RELIABLE + TRANSIENT_LOCAL; /mavros/battery is BEST_EFFORT.
    def _on_battery(msg):
        global _battery_msg, _battery_time
        _battery_msg = msg
        _battery_time = time.monotonic()

    _state_qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL)
    _node.create_subscription(State, '/mavros/state', _on_fcu_state, _state_qos)

    _batt_qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.BEST_EFFORT,
        durability=DurabilityPolicy.VOLATILE)
    _node.create_subscription(BatteryState, '/mavros/battery', _on_battery, _batt_qos)

    # SDK subscriptions and clients share the default mutually exclusive group.
    # Blocking service waits run on the caller's thread, outside these callbacks.
    # Keep the background spin thread and serialize callbacks without a worker pool.
    _executor = rclpy.executors.SingleThreadedExecutor()
    _executor.add_node(_node)
    global _spin_thread
    _spin_thread = threading.Thread(
        target=_executor.spin, name='drone-spin', daemon=False)
    _spin_thread.start()
    # F4 (09.11.2026): Python joins non-daemon threads BEFORE it runs atexit
    # handlers, so with only atexit.register(_shutdown) the spin thread kept
    # the process alive and a finished script hung until Ctrl+C.
    # threading._register_atexit hooks run before that join (Python >= 3.9).
    try:
        threading._register_atexit(_shutdown)
    except Exception:
        pass

    # Clean rclpy shutdown on interpreter exit. Without this, sys.exit() with
    # the executor still spinning makes rmw_fastrtps abort the process with
    # "terminate called without an active exception" / SIGABRT.
    atexit.register(_shutdown)

    _initialized = True


def _shutdown():
    """Tear down rclpy without racing the executor spin-thread.

    Round-2 (2026-05-27) reordered: shut down the executor FIRST (so it stops
    handing callbacks to the spin thread), then join the spin thread, then
    rclpy.shutdown(), then destroy_node(). The previous order called
    rclpy.shutdown() first, which sometimes unblocked the spin thread while
    the executor was still trying to schedule callbacks — leading to
    "cannot schedule new futures after interpreter shutdown" and
    std::terminate aborts from rmw_fastrtps.
    """
    global _initialized, _executor, _node
    if not _initialized:
        return
    _initialized = False
    _stop_detector_wake()   # F1: no wakes after the script ends
    _stop_script_lease()    # T25: armed in OFFBOARD after this -> simple_offboard lands
    try:
        if _executor is not None:
            _executor.shutdown(timeout_sec=2.0)
    except Exception:
        pass
    try:
        if _spin_thread is not None and _spin_thread.is_alive():
            _spin_thread.join(timeout=2.0)
    except Exception:
        pass
    try:
        if rclpy is not None and rclpy.ok():
            rclpy.shutdown()
    except Exception:
        pass
    try:
        if _node is not None:
            _node.destroy_node()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public service wrappers (mirror ROS1 ServiceProxy call interface)
# ---------------------------------------------------------------------------

def get_telemetry(**kwargs):
    _init()
    req = srv.GetTelemetry.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
    return _call(_get_telemetry_client, req)


# 0xFFFF mV: PX4 "unknown voltage" sentinel that MAVROS forwards verbatim.
_BATT_SENTINEL_V = 65.535


def get_fcu_status(max_age=3.0):
    """Lightweight FCU status from cached topic subscriptions -- NO service call.

    Reads the background /mavros/state and /mavros/battery subscriptions set up
    in _init(). Unlike get_telemetry(), this never does a service round-trip or
    TF lookup, so it does not stall under CPU load. Intended for indicators
    (notify_manager) that must not raise a false alarm when the graph is busy.

    Returns a dict:
      connected -- bool, FCU link up (State.connected AND state fresh)
      armed     -- bool
      mode      -- str  (PX4 flight mode, '' if unknown)
      cell      -- float per-cell voltage, or NaN if unavailable/sentinel
      ok        -- bool, a fresh State message is available
    """
    _init()
    now = time.monotonic()
    connected = False
    armed = False
    mode = ''
    ok = False
    if _fcu_state_msg is not None and _fcu_state_time is not None:
        age = now - _fcu_state_time
        ok = 0.0 <= age < max_age
        connected = bool(_fcu_state_msg.connected) and ok
        armed = bool(_fcu_state_msg.armed)
        mode = str(_fcu_state_msg.mode)

    cell = float('nan')
    if _battery_msg is not None and _battery_time is not None:
        bage = now - _battery_time
        if 0.0 <= bage < max_age:
            cells = list(_battery_msg.cell_voltage)
            if cells:
                c0 = float(cells[0])
                # Ignore the 0xFFFF sentinel and other invalid readings.
                if 0.0 < c0 < _BATT_SENTINEL_V:
                    cell = c0
    return {'connected': connected, 'armed': armed, 'mode': mode,
            'cell': cell, 'ok': ok}


def _on_fcu_state(msg):
    """/mavros/state callback: cache for get_fcu_status; end of flight on disarm."""
    global _fcu_state_msg, _fcu_state_time, _arm_ref_z, _own_auto_land, _auto_arm_ok_t
    prev = _fcu_state_msg
    # Armed -> disarmed with the link up: this flight is over, so its floor
    # reference must not leak into the next one (a link-loss State has
    # connected=False and armed=False and is not a disarm).
    if prev is not None and prev.armed and msg.connected and not msg.armed:
        _arm_ref_z = None
        _own_auto_land = False
        _auto_arm_ok_t = None
    # Out of AUTO.LAND (e.g. the pilot took over): a later one is not ours
    if prev is not None and prev.mode == 'AUTO.LAND' and msg.connected \
            and msg.mode != 'AUTO.LAND':
        _own_auto_land = False
    _fcu_state_msg = msg
    _fcu_state_time = time.monotonic()


# ---------------------------------------------------------------------------
# Pilot wins (A4, 2026-10-13)
# ---------------------------------------------------------------------------
#
# If the vehicle is armed and not in OFFBOARD, the pilot (RC mode switch) or a
# PX4 failsafe chose that mode: no drone.py code path may change it or start
# OFFBOARD control. With the FCU state unknown, nothing is commanded either --
# a stale state looks like "disarmed" and would let a flying drone be armed /
# switched. Limit: PX4 reports its mode at the HEARTBEAT rate (~1 Hz), so a
# takeover is seen up to ~1 s late.

def _fcu_mode_state(wait=0.0):
    """(known, armed, mode) of the FCU for the pilot-wins checks.

    First source: the cached /mavros/state (get_fcu_status -- monotonic age,
    no service call). Only when that is not fresh: simple_offboard's
    /get_telemetry, which blanks connected/armed/mode after its own state
    timeout. known=False when neither has a fresh state with the FCU link up;
    armed/mode must not be trusted then. wait > 0 keeps polling that long.
    """
    deadline = time.monotonic() + wait
    while True:
        s = get_fcu_status()
        if s['ok'] and s['connected']:
            return True, s['armed'], s['mode']
        try:
            t = get_telemetry()
            if t.connected:
                return True, bool(t.armed), str(t.mode)
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False, False, ''
        time.sleep(0.1)


def _no_control_reason(known, armed, mode):
    """Why the Pi must not command the FCU now, or None when it may.

    Allowed: disarmed (any mode -- the ground takeoff path) and armed in
    OFFBOARD (the Pi's own flight).
    """
    if not known:
        return 'FCU state unknown (no fresh /mavros/state or FCU link down)'
    if armed and mode == 'AUTO.LAND' and _own_auto_land:
        return 'landing in progress (this script switched to AUTO.LAND)'
    if armed and mode != 'OFFBOARD':
        return 'pilot/failsafe has control (armed, mode=%s)' % (mode or '?')
    return None


# Guard /land reply limit (s). In the hold /land answers once the DISARM is
# confirmed (usually < 1 s); when PX4 refuses it, after simple_offboard's own
# AUTO.LAND (3 s of refusals + set_mode + land_timeout 3 s), which this covers.
_GUARD_LAND_TIMEOUT = 8.0
# simple_offboard's /land refusals that mean someone else has the vehicle
# (checkPilot, land_only_in_offboard, a landing already in progress, the
# ground-hold path armed outside OFFBOARD)
_LAND_NOT_OURS = ('has control', 'not in OFFBOARD', 'Already landing', 'Land before takeoff')
# Fallback DISARM call limit (s): above MAVROS's command ACK timeout (5 s), so a
# lost ACK comes back as success=False, result=0 instead of a client timeout
_HOLD_DISARM_CALL_S = 6.0


def _hold_now():
    """simple_offboard's hold clock: the ROS clock under use_sim_time (SITL), else monotonic."""
    try:
        clock = _node.get_clock()
        if clock.ros_time_is_active:
            return clock.now().nanoseconds * 1e-9
    except Exception:
        pass
    return time.monotonic()


def _in_takeoff_hold():
    """True within _TAKEOFF_HOLD_S of navigate(auto_arm=True) arming from the ground.

    Fails closed: a negative elapsed time (clock switched or reset) is outside.
    """
    if _auto_arm_ok_t is None:
        return False
    elapsed = _hold_now() - _auto_arm_ok_t
    return 0.0 <= elapsed < _TAKEOFF_HOLD_S


def _land_if_offboard():
    """Guard action: land, only while the Pi holds the armed vehicle in OFFBOARD.

    In flight: AUTO.LAND at once, as before. In the takeoff's ground hold
    (_in_takeoff_hold; PX4 has not detected a takeoff) through
    simple_offboard's /land, which disarms on the ground: AUTO.LAND there
    would leave the motors running until PX4's preflight auto-disarm
    (COM_DISARM_PRFLT, 30 s). The wait for /land is bounded (1 s service
    readiness + _GUARD_LAND_TIMEOUT); when it fails and the Pi still holds the
    vehicle: _land_fallback(in_hold=True), whose DISARM re-checks the window.
    A refusal because someone else has the vehicle (pilot, PX4 failsafe, a
    landing in progress) is final, even if this script's cached state has not
    seen the mode change yet.
    """
    global _own_auto_land
    known, armed, mode = _fcu_mode_state()
    if not (known and armed and mode == 'OFFBOARD'):
        _node.get_logger().warn('Not landing: %s' % (
            _no_control_reason(known, armed, mode) or 'not armed'))
        return
    if not _in_takeoff_hold():
        _own_auto_land_switch()
        return
    # The AUTO.LAND that /land may switch to is this script's (wording only);
    # set first, so the disarm edge of a ground DISARM clears it
    _own_auto_land = True
    try:
        res = _call(_land_client, Trigger.Request(), timeout=_GUARD_LAND_TIMEOUT, wait=1.0)
        if res.success:
            _node.get_logger().info('Guard /land: %s' % (res.message or 'landing (AUTO.LAND)'))
            return
        _node.get_logger().warn('Guard /land rejected: ' + res.message)
        if any(s in res.message for s in _LAND_NOT_OURS):
            _own_auto_land = False
            return
        reason = res.message
    except Exception as e:
        _node.get_logger().error('Guard /land failed: %s' % e)
        reason = str(e)
    # An AUTO.LAND seen now is /land's own only if /land got as far as sending
    # it: its reply 'Land request timed out', or our call timing out after the
    # request went out ('Service ... timed out'), not 'not available'
    ours = 'timed out' in reason
    known, armed, mode = _fcu_mode_state()
    _own_auto_land = ours and known and armed and mode == 'AUTO.LAND'
    if known and armed and mode == 'OFFBOARD':
        _land_fallback(in_hold=True)


def _land_fallback(in_hold):
    """/land failed while the Pi still holds the armed vehicle in OFFBOARD.

    in_hold (the guard fired in the takeoff's ground hold): non-forced DISARM
    first (_hold_disarm, only while the window lasts) -- AUTO.LAND there would
    idle the motors until COM_DISARM_PRFLT. Otherwise, or when the DISARM is
    not confirmed and the Pi still holds the vehicle in OFFBOARD: AUTO.LAND.
    Never a DISARM after the window.
    """
    if in_hold and _in_takeoff_hold():
        _node.get_logger().warn('Falling back to DISARM on the ground')
        if _hold_disarm():
            return
        known, armed, mode = _fcu_mode_state()
        if not (known and armed and mode == 'OFFBOARD'):
            return   # disarmed meanwhile, unknown, or the pilot / a PX4 failsafe has control
    _node.get_logger().warn('Falling back to AUTO.LAND')
    _own_auto_land_switch()


def _hold_disarm():
    """Non-forced DISARM while the takeoff's ground hold lasts; True once accepted or disarmed.

    Only from _land_fallback(in_hold=True); every attempt re-checks
    _in_takeoff_hold() and armed-in-OFFBOARD, so none goes out after the
    window or against the pilot / a PX4 failsafe. Unlike arming(False) there
    is no EKF landed check: the vehicle is held on the ground and a NaN or
    jumped estimate is often why the guard fired; PX4 accepts a non-forced
    DISARM only while it reports landed. A lost ACK (MAVROS: success=False,
    result=0 after its 5 s ACK timeout, inside _HOLD_DISARM_CALL_S) or a
    client error is retried; any other result is PX4's refusal and ends it.
    """
    while _in_takeoff_hold():
        known, armed, mode = _fcu_mode_state()
        if not known or not armed or mode != 'OFFBOARD':
            return known and not armed
        if not _in_takeoff_hold():   # the state query may have taken a while
            break
        try:
            req = CommandBool.Request()
            req.value = False
            res = _call(_arming_client, req, timeout=_HOLD_DISARM_CALL_S, wait=1.0)
            if res.success:
                return True
            if res.result != 0:
                _node.get_logger().warn('DISARM fallback refused by PX4 (result %s)' % res.result)
                return False
        except Exception as e:
            _node.get_logger().error('DISARM fallback failed: %s' % e)
        time.sleep(0.5)
    known, armed, mode = _fcu_mode_state()
    return known and not armed


def _own_auto_land_switch():
    """set_mode('AUTO.LAND') from OFFBOARD, remembered as this script's landing."""
    global _own_auto_land
    try:
        if set_mode('AUTO.LAND').mode_sent:
            _own_auto_land = True
    except Exception as e:
        _node.get_logger().error('AUTO.LAND fallback failed: %s' % e)


def _record_arm_height():
    """Remember the map z of base_link right before the Pi arms (A7)."""
    global _arm_ref_z, _last_arm_ref_z
    try:
        t = get_telemetry(frame_id='map')
        _arm_ref_z = float(t.z) if t.z == t.z else None
    except Exception:
        _arm_ref_z = None
    _last_arm_ref_z = _arm_ref_z


def _landed_now():
    """(landed, detail) for arming(False): fresh map z near the height at arm, slow vz."""
    if _arm_ref_z is None:
        return False, 'height at arm unknown (this script did not arm the drone)'
    ref = _arm_ref_z
    try:
        t = get_telemetry(frame_id='map')   # fresh sample, never the cached one
    except Exception as e:
        return False, 'no telemetry: %s' % e
    z, vz = t.z, t.vz
    if not (z == z and vz == vz):
        return False, 'position unknown (NaN)'
    if abs(z - ref) > _LANDED_DZ or abs(vz) > _LANDED_VZ:
        return False, 'z=%.2f (height at arm %.2f) vz=%.2f' % (z, ref, vz)
    return True, ''


# Cache last-known-valid telemetry per frame_id; robust wrapper falls back to it.
_last_valid_telem = {}    # frame_id -> (telem, monotonic_time)
_last_stale_warn_t = {}   # frame_id -> last warn monotonic_time


def _get_telemetry_robust(frame_id='map', retries=4, retry_delay=0.1, allow_stale=True):
    """Retries get_telemetry on NaN; falls back to last cached valid telem.
    Returns the telem object (may still have NaN if no cache and all retries failed)."""
    last = None
    for _ in range(retries + 1):
        t = get_telemetry(frame_id=frame_id)
        last = t
        if t.x == t.x and t.y == t.y and t.z == t.z:
            _last_valid_telem[frame_id] = (t, time.monotonic())
            return t
        time.sleep(retry_delay)
    if allow_stale and frame_id in _last_valid_telem:
        cached, ts = _last_valid_telem[frame_id]
        age = time.monotonic() - ts
        now = time.monotonic()
        if now - _last_stale_warn_t.get(frame_id, 0.0) >= 2.0:
            _last_stale_warn_t[frame_id] = now
            print('WARN: telemetry stale frame=%s age=%.2fs' % (frame_id, age))
        return cached
    return last


def _telem_staleness(frame_id='map'):
    """Seconds since the last non-NaN telemetry sample for frame_id; +inf if never seen."""
    entry = _last_valid_telem.get(frame_id)
    if entry is None:
        return float('inf')
    return time.monotonic() - entry[1]


# F5 (09.11.2026, r2c): float32 fields of the Navigate request. Each must hold
# a Python float: an int (fly_to(x=0)) or a numpy.float32 passes the Python
# setter (ROS_PYTHON_CHECK_FIELDS is off by default) and then aborts the whole
# process in the rosidl C converter (assert PyFloat_Check, core dump), leaving
# the drone in OFFBOARD without a script. float() keeps nan as nan.
_NAVIGATE_FLOAT_FIELDS = ('x', 'y', 'z', 'yaw', 'speed')


def navigate(**kwargs):
    global _arm_ref_z, _auto_arm_ok_t
    _init()
    _start_script_lease()   # T25: simple_offboard lands if this process dies
    req = srv.Navigate.Request()
    for k, v in kwargs.items():
        if k in _NAVIGATE_FLOAT_FIELDS:
            v = float(v)
        setattr(req, k, v)
    # Pilot wins (A4): never start or retarget OFFBOARD control while the
    # pilot / a PX4 failsafe owns the armed vehicle or the state is unknown.
    # simple_offboard's serve() refuses the same; checking here as well gives
    # the script the reason and covers an older binary. (Keep the word
    # "position" out of the message: navigate_wait retries on it.)
    known, armed, mode = _fcu_mode_state(wait=_FCU_STATE_WAIT)
    reason = _no_control_reason(known, armed, mode)
    if reason is not None:
        res = srv.Navigate.Response()
        res.success = False
        res.message = 'navigate refused: ' + reason
        return res
    if req.auto_arm and not armed:
        _record_arm_height()   # on the ground: the floor of this flight
        result = _call_auto_arm(req, timeout=45.0)
        if result.success:
            _auto_arm_ok_t = _hold_now()   # simple_offboard's ground hold runs now
        # An explicit failed start does not establish a floor for this flight.
        # Keep the reference for an unresolved ARM so a ground DISARM is possible.
        if not result.success and 'motors may be running' not in result.message:
            _arm_ref_z = None
        return result
    return _call(_navigate_client, req, timeout=5.0)


def land():
    _init()
    return _call(_land_client, Trigger.Request(), timeout=15.0)


def _arming_refused(reason):
    print('arming refused: ' + reason)
    res = CommandBool.Response()
    res.success = False
    res.result = 2   # MAV_RESULT_DENIED; nothing was sent to the FCU
    return res


def arming(value):
    """Disarm on the ground only (A7, 2026-10-13); never arms.

    arming(True) is refused: the motors start only through takeoff() /
    navigate(auto_arm=True), which check the FCU state first.
    arming(False) is sent only when the drone is landed: z within 0.20 m of
    the height recorded at arm time and |vz| < 0.10 m/s (PX4 also denies a
    non-forced disarm in the air). In flight use safe_land(); the hard stop
    is the RC kill switch.

    Returns the CommandBool response (success=False when refused).
    """
    _init()
    if value:
        return _arming_refused(
            'motors start only through drone.takeoff() / navigate(auto_arm=True)')
    if not _arming_client.wait_for_service(timeout_sec=5.0):
        raise Exception('Service %s not available' % _arming_client.srv_name)
    known, armed, mode = _fcu_mode_state(wait=_FCU_STATE_WAIT)
    if not known:
        return _arming_refused(_no_control_reason(known, armed, mode))
    if armed:
        landed, detail = _landed_now()
        if not landed:
            return _arming_refused(
                'not landed (%s) -- use safe_land(); hard stop = RC kill switch' % detail)
    req = CommandBool.Request()
    req.value = False
    result = _arming_client.call(req, timeout_sec=5.0)
    if result is None:
        raise Exception('Service %s timed out' % _arming_client.srv_name)
    return result


def set_mode(custom_mode):
    """Switch the PX4 flight mode via /mavros/set_mode.

    Pilot wins (A4): refused (mode_sent=False, nothing sent) while the FCU
    state is unknown or the vehicle is armed and not in OFFBOARD -- the
    pilot or a PX4 failsafe chose that mode.
    """
    _init()
    if not _set_mode_client.wait_for_service(timeout_sec=5.0):
        raise Exception('Service %s not available' % _set_mode_client.srv_name)
    reason = _no_control_reason(*_fcu_mode_state(wait=_FCU_STATE_WAIT))
    if reason is not None:
        print('set_mode(%s) refused: %s' % (custom_mode, reason))
        res = SetMode.Response()
        res.mode_sent = False
        return res
    req = SetMode.Request()
    req.custom_mode = custom_mode
    result = _set_mode_client.call(req, timeout_sec=5.0)
    if result is None:
        raise Exception('Service %s timed out' % _set_mode_client.srv_name)
    return result


def play_tune(tune, format='QBASIC'):
    """Play a tune on the PX4 buzzer via MAVROS /mavros/play_tune.

    tune    -- tune string in QBASIC or MML notation (<=230 chars).
    format  -- 'QBASIC' (default) or 'MML'. Case-insensitive.

    The publisher is created lazily on first call. Requires the MAVROS
    play_tune plugin to be enabled (see mavros_params.yaml allowlist).
    Raises RuntimeError if mavros_msgs.PlayTuneV2 is unavailable on the
    current system.
    """
    _init()
    global _play_tune_pub
    if PlayTuneV2 is None:
        raise RuntimeError('mavros_msgs/PlayTuneV2 is not available on this system')
    tune_str = str(tune)
    if len(tune_str) > 230:
        raise ValueError('PLAY_TUNE_V2 tune string is limited to 230 chars (got %d)' % len(tune_str))
    if _play_tune_pub is None:
        _play_tune_pub = _node.create_publisher(PlayTuneV2, '/mavros/play_tune', 10)
    msg = PlayTuneV2()
    msg.format = TUNE_FORMAT_MML if str(format).upper() == 'MML' else TUNE_FORMAT_QBASIC
    msg.tune = tune_str
    _play_tune_pub.publish(msg)


# Named tune library for play_sound(). Keys are case-insensitive.
_TUNES = {
    'beep':      TUNE_BEEP,
    'ok':        TUNE_OK,
    'error':     TUNE_ERROR,
    'notify':    TUNE_NOTIFY,
    'arming':    TUNE_ARMING,
    'victory':   TUNE_VICTORY,
    'fail':      TUNE_FAIL,
    'takeoff':   TUNE_TAKEOFF,
    'land':      TUNE_LAND,
    'warn':      TUNE_WARN,
    'countdown': TUNE_COUNTDOWN,
    'startup':   TUNE_STARTUP,
    'imperial':  TUNE_IMPERIAL_MARCH,
    'mario':     TUNE_MARIO,
    'tetris':    TUNE_TETRIS,
}


def list_sounds():
    """Return the sorted list of named tunes available to play_sound()."""
    return sorted(_TUNES)


def play_sound(name, format='QBASIC'):
    """Play a named tune from the library, or a raw QBASIC/MML string.

    name -- a key from list_sounds() (case-insensitive), e.g. 'victory',
            'mario'. If it is not a known name it is treated as a raw tune
            string and played as-is, so play_sound('MFT180L8O5CEG') works too.
    """
    tune = _TUNES.get(str(name).lower(), name)
    play_tune(tune, format=format)


def beep(count=1, pitch='O5C', gap=True):
    """Play `count` short beeps in a single tune message.

    pitch -- QBASIC octave+note for the beep (default high C, 'O5C').
    gap   -- insert a short rest between beeps so they are distinct.
    """
    count = max(int(count), 1)
    rest = 'P16' if gap else ''
    tune = 'MFT200L16' + (pitch + rest) * count
    play_tune(tune)


def set_param(param_id, value, ttl_sec=0.0, persistent=False):
    """Apply a PX4 parameter through the vpe_fix gate.

    The gate is the only sanctioned PX4-param writer in this stack:
      - reads the current PX4 value and remembers it as the "original",
      - calls ParamSetV2 (with one force-pull retry on first failure),
      - reverts on DISARMED edge, on shutdown, or when ttl_sec expires.

    ttl_sec > 0      -> auto-revert after this many seconds (also on disarm).
    persistent=True  -> caller owns the value; gate will not auto-revert
                        (still reverts on a clean shutdown for safety).

    Returns the SetParam service response (.success, .message, .original_value).
    """
    _init()
    req = srv.SetParam.Request()
    req.param_id = str(param_id)
    req.value = float(value)
    req.ptype = 0 if isinstance(value, bool) or isinstance(value, int) else 1
    req.ttl_sec = float(ttl_sec)
    req.persistent = bool(persistent)
    return _call(_gate_param_client, req)


def _trigger_param_pull(timeout_s=10.0):
    """Call /mavros/mavros/pull(force_pull=True) and wait for completion.

    Used by read_px4_params: makes MAVROS fetch the PX4 parameter list again,
    so names MAVROS missed become readable through GetParameters (and, for
    the vpe_fix gate, show up again on /parameter_events).

    Returns True on completion, False on timeout. Does NOT touch the gate.
    """
    _init()
    if _param_pull_client is None:
        return False
    if not _param_pull_client.wait_for_service(timeout_sec=2.0):
        print('  WARN  /mavros/mavros/pull service not available')
        return False
    req = ParamPull.Request()
    req.force_pull = True
    fut = _param_pull_client.call_async(req)
    evt = threading.Event()
    fut.add_done_callback(lambda _f: evt.set())
    ok = evt.wait(timeout=timeout_s)
    print('  ParamPull(force=True) %s' % ('completed' if ok else 'timed out'))
    return ok


def _param_value_to_float(pv):
    """rcl_interfaces/ParameterValue -> float, or None if MAVROS does not have the param."""
    if pv is None:
        return None
    t = getattr(pv, 'type', 0)
    if t == 1:    # PARAMETER_BOOL
        return 1.0 if pv.bool_value else 0.0
    if t == 2:    # PARAMETER_INTEGER
        return float(pv.integer_value)
    if t == 3:    # PARAMETER_DOUBLE
        return float(pv.double_value)
    return None   # PARAMETER_NOT_SET: MAVROS has not received this param from PX4


def read_px4_params(names, pull_rounds=3, wait_s=5.0):
    """Read PX4 params straight from MAVROS's parameter table. Never writes anything.

    Uses the MAVROS param plugin's own GetParameters service
    (/mavros/mavros/get_parameters, the same node as /mavros/mavros/pull). It
    answers from MAVROS's table, so the /parameter_events stream is not
    involved (that stream drops events when ~1100 arrive in a burst: finding
    F3, 06.11.2026). A name MAVROS has not received from PX4 comes back as
    PARAMETER_NOT_SET; then MAVROS is asked to fetch the list again
    (ParamPull force_pull=True) and the read is retried, up to pull_rounds
    times. Returns {name: float} for every name that was read; names that
    could not be read are absent.
    """
    _init()
    values = {}
    missing = list(names)
    for round_idx in range(int(pull_rounds) + 1):
        if round_idx > 0:
            print('  ... read pass %d: %d params not in MAVROS yet (%s); '
                  'ParamPull(force=True) + %.0fs wait'
                  % (round_idx + 1, len(missing), ', '.join(missing), wait_s))
            try:
                _trigger_param_pull(timeout_s=10.0)
            except Exception as e:
                print('  WARN  ParamPull raised: %s' % e)
            time.sleep(wait_s)
        req = GetParameters.Request()
        req.names = list(missing)
        try:
            resp = _call(_param_get_client, req, timeout=5.0)
        except Exception as e:
            print('  WARN  GetParameters failed: %s' % e)
            continue
        got = list(getattr(resp, 'values', None) or [])
        still = []
        for i, name in enumerate(missing):
            v = _param_value_to_float(got[i]) if i < len(got) else None
            if v is None:
                still.append(name)
            else:
                values[name] = v
        missing = still
        if not missing:
            break
    return values


def _same_value(px4_value, wanted):
    """PX4 stores float32 (0.1 comes back as 0.10000000149): small relative tolerance."""
    return abs(float(px4_value) - float(wanted)) <= 1e-4 * max(1.0, abs(float(wanted)))


def check_flight_profile(profile_name):
    """Check that PX4 already holds every value of the profile. Never writes anything.

    Since 09.11.2026 the scripts do not write PX4 params. PX4 saves every
    parameter write it gets over MAVLink to flash (PX4 v1.16.1
    src/lib/parameters/parameters.cpp:449-450, param_autosave), so a value
    written before a flight would stay after a crash or a lost Pi. The owner
    sets the profile values once in QGC; a script checks them here and must
    refuse to fly when any value differs or cannot be read.

    Returns (matched, total, problems); problems lists 'NAME: PX4 x, profile y'
    or 'NAME: not read from PX4'.
    """
    _init()
    try:
        import flight_profile as _fp
    except ImportError as e:
        raise RuntimeError(
            'check_flight_profile: flight_profile.py not importable: %s' % e)
    if profile_name not in _fp.PROFILES:
        raise ValueError(
            'check_flight_profile: unknown profile %r (have: %s)'
            % (profile_name, sorted(_fp.PROFILES.keys())))
    profile = _fp.PROFILES[profile_name]
    print('Checking flight profile %r: %d PX4 params (read only, nothing is written)...'
          % (profile_name, len(profile)))
    values = read_px4_params(list(profile.keys()))
    matched = 0
    problems = []
    for name, wanted in profile.items():
        if name not in values:
            problems.append('%s: not read from PX4' % name)
        elif _same_value(values[name], wanted):
            matched += 1
        else:
            problems.append('%s: PX4 %g, profile %g' % (name, values[name], wanted))
    for p in problems:
        print('  MISMATCH  ' + p)
    print('Flight profile %r: %d/%d PX4 params match.' % (profile_name, matched, len(profile)))
    return matched, len(profile), problems


def apply_flight_profile(profile_name='INDOOR_ARUCO'):
    """Kept for old scripts. Since 09.11.2026 it does NOT write anything.

    It only runs check_flight_profile() and returns how many PX4 params
    already hold the profile value. A script must refuse to fly unless that
    number equals the profile size (see examples/flight/flight.py).
    Call it before arming, never in flight: a value MAVROS lacks triggers
    ParamPull(force_pull=True), which refetches MAVROS's whole parameter table.
    """
    print('NOTE: apply_flight_profile() no longer writes PX4 params; it only checks them.')
    matched, _total, _problems = check_flight_profile(profile_name)
    return matched


# ---------------------------------------------------------------------------
# ArUco map management
# ---------------------------------------------------------------------------

def _map_rows(markers):
    """{id: (length, x, y, rot_z)} from a set_aruco_map() marker list (same defaults as before)."""
    return {int(m['id']): (float(m['length']), float(m['x']), float(m['y']), float(m.get('rot_z', 1.571)))
            for m in markers}


def _read_map_file(path):
    """{id: (length, x, y, rot_z)} from an aruco_pose map file; RuntimeError if it cannot be read."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except OSError as e:
        raise RuntimeError('set_aruco_map: cannot read map %s: %s' % (path, e))
    rows = {}
    for n, line in enumerate(lines, 1):
        p = line.split()
        if not p or p[0].startswith('#'):
            continue
        try:
            if len(p) < 4:
                raise ValueError('%d columns, need at least 4: id length x y' % len(p))
            i = int(p[0])
            if i in rows:
                raise ValueError('id %d twice' % i)
            rows[i] = (float(p[1]), float(p[2]), float(p[3]), float(p[5]) if len(p) > 5 else 1.571)
        except ValueError as e:
            raise RuntimeError('set_aruco_map: bad line %d in map %s: %r (%s)' % (n, path, line, e))
    if not rows:
        raise RuntimeError('set_aruco_map: no markers in map %s' % path)
    return rows


def set_aruco_map(markers=None, map_file=None):
    """
    Check that the ArUco map a script wants is the map the detector already uses.

    Since 09.11.2026 (finding F2) this does NOT write the map and does NOT
    restart any node. The image's detector (aruco_detect.py) reads its map once
    at start (map_file parameter, launch/aruco.launch.py) and the C++ aruco_map
    node that used to be restarted is disabled, so a map written during a
    session never reached the detector: the route silently used the old map.

    Now: the same map -> OK; a different map -> RuntimeError before takeoff.
    To fly another map, put it into MAP_FILE and restart the drone stack.

    Two ways to use (as before):
        drone.set_aruco_map(map_file='/home/lb/maps/arena.txt')
        drone.set_aruco_map([{'id': 0, 'length': 0.19, 'x': 0, 'y': 0}, ...])
    """
    _init()
    if map_file is not None:
        want = _read_map_file(map_file)
    elif markers is not None:
        want = _map_rows(markers)
    else:
        raise RuntimeError('set_aruco_map: provide either markers list or map_file path')
    have = _read_map_file(MAP_FILE)
    problems = []
    for i in sorted(set(want) | set(have)):
        if i not in have:
            problems.append('id %d not in loaded map' % i)
        elif i not in want:
            problems.append('id %d only in loaded map' % i)
        elif any(abs(a - b) > 1e-3 for a, b in zip(want[i], have[i])):
            problems.append('id %d: wanted %s, loaded %s' % (i, want[i], have[i]))
    if problems:
        raise RuntimeError(
            'set_aruco_map: the map differs from the map the detector uses (%s): %s. '
            'The detector does not reload maps during a session; put the map into %s '
            'and restart the drone stack.' % (MAP_FILE, '; '.join(problems[:5]), MAP_FILE))
    print('Map check OK: %d markers, same as the loaded map %s' % (len(want), MAP_FILE))


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

def enable_safe_interrupt():
    """
    Register a Ctrl+C handler that sets should_land=True instead of
    killing the process immediately.
    """
    def _handler(sig, frame):
        global should_land
        should_land = True
        _node.get_logger().warn('Interrupt received -- cancelling takeoff / landing')
    signal.signal(signal.SIGINT, _handler)


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

def get_pos(frame_id='map'):
    """Return current (x, y, z) position as a tuple."""
    t = get_telemetry(frame_id=frame_id)
    return t.x, t.y, t.z


def print_pos(phase='INFO'):
    """Print current position and flight state, return telemetry object."""
    t = get_telemetry(frame_id='map')
    print('[%s] x=%.2f y=%.2f z=%.2f | armed=%s mode=%s' % (
        phase, t.x, t.y, t.z, t.armed, t.mode))
    return t


def print_pos_fresh(phase, timeout=4.0):
    """Spin get_telemetry until x,y,z are all finite or timeout. Returns telem."""
    deadline = time.monotonic() + timeout
    t = None
    while time.monotonic() < deadline:
        t = _get_telemetry_robust(frame_id='map')
        if t.x == t.x and t.y == t.y and t.z == t.z:
            print('[%s] x=%.2f y=%.2f z=%.2f | armed=%s mode=%s' % (
                phase, t.x, t.y, t.z, t.armed, t.mode))
            return t
        time.sleep(0.1)
    print('WARN: %s telemetry NaN after %.1fs' % (phase, timeout))
    return t


# ---------------------------------------------------------------------------
# ArUco safety check
# ---------------------------------------------------------------------------

def _markers_used_age():
    """Seconds since the last /aruco_detect/markers_used update; +inf if never seen."""
    if _aruco_markers_used_time is None:
        return float('inf')
    return time.monotonic() - _aruco_markers_used_time


def _markers_pos_age():
    """Seconds since aruco_detect last reported >=1 usable marker; +inf if never."""
    if _aruco_markers_pos_time is None:
        return float('inf')
    return time.monotonic() - _aruco_markers_pos_time


# ---------------------------------------------------------------------------
# F1 (09.11.2026, r2b): keep the marker detector awake during the preflight
# ---------------------------------------------------------------------------
# The image's detector (aruco_detect.py) sleeps until the FCU is armed or in
# OFFBOARD and stays awake WAKE_HOLD_S (5 s) after each /aruco_detect/wake.
# A preflight (check_aruco, wait_yaw_lock, wait_position_stable,
# require_vpe_link, takeoff's vision wait) can take minutes, so a background
# thread repeats the wake every WAKE_PERIOD_S until the FCU is armed (then the
# detector's own gate keeps it on), the script shuts down, or WAKE_MAX_S pass
# after the last preflight call -- no permanent CPU load on the ground.
WAKE_PERIOD_S = 2.0
WAKE_MAX_S = 180.0
_wake_lock = threading.Lock()
_wake_thread = None
_wake_stop = None
_wake_deadline = 0.0


def _fcu_is_armed():
    m = _fcu_state_msg
    return bool(m is not None and getattr(m, 'armed', False))


def _keep_detector_awake():
    """Start (or extend) the background wake. Idempotent; never raises."""
    global _wake_thread, _wake_stop, _wake_deadline
    try:
        with _wake_lock:
            _wake_deadline = time.monotonic() + WAKE_MAX_S
            if _wake_thread is not None and _wake_thread.is_alive():
                return
            pub = _node.create_publisher(Bool, '/aruco_detect/wake', 10)
            stop = threading.Event()

            def run():
                msg = Bool()
                msg.data = True
                try:
                    while not stop.is_set():
                        if _fcu_is_armed() or time.monotonic() > _wake_deadline:
                            break
                        pub.publish(msg)
                        stop.wait(WAKE_PERIOD_S)
                except Exception:
                    pass
                finally:
                    try:
                        _node.destroy_publisher(pub)
                    except Exception:
                        pass

            _wake_stop = stop
            _wake_thread = threading.Thread(target=run, name='aruco-wake', daemon=True)
            _wake_thread.start()
    except Exception as e:
        print('  WARN  detector wake not started: %s' % e)


def _stop_detector_wake():
    stop = _wake_stop
    if stop is not None:
        stop.set()
    t = _wake_thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=1.0)


# T25 (r2d, 09.11.2026): script lease. A flight script that died alone
# (SIGKILL, OOM, a crash of python itself) left the drone in OFFBOARD:
# simple_offboard kept streaming the last setpoint and the drone hovered
# (Gazebo k1_r2c_4059_kill_hover). From the first flight command on, this
# thread sends True on LEASE_TOPIC every LEASE_PERIOD_S. simple_offboard lands
# with its own /land when the lease is silent for script_lease_timeout (2 s)
# while armed in OFFBOARD; it never acts in another mode (the pilot's switch
# wins). Ctrl+C keeps the process, and so the lease, alive: safe_land runs as
# before. The lease ends with the process or in _shutdown().
LEASE_TOPIC = '/simple_offboard/script_lease'
LEASE_PERIOD_S = 0.5
_lease_lock = threading.Lock()
_lease_thread = None
_lease_stop = None


def _start_script_lease():
    """Start the lease once. Idempotent; never raises."""
    global _lease_thread, _lease_stop
    try:
        with _lease_lock:
            if _lease_thread is not None and _lease_thread.is_alive():
                return
            pub = _node.create_publisher(Bool, LEASE_TOPIC, 10)
            stop = threading.Event()

            def run():
                msg = Bool()
                msg.data = True
                try:
                    while not stop.is_set():
                        pub.publish(msg)
                        stop.wait(LEASE_PERIOD_S)
                except Exception:
                    pass

            _lease_stop = stop
            _lease_thread = threading.Thread(target=run, name='script-lease', daemon=True)
            _lease_thread.start()
    except Exception as e:
        print('  WARN  script lease not started: %s' % e)


def _stop_script_lease():
    stop = _lease_stop
    if stop is not None:
        stop.set()
    t = _lease_thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout=1.0)


def check_aruco(timeout=10, min_markers=1):
    """
    Wait until at least `min_markers` ArUco markers are visible.

    Returns the list of visible marker IDs on success, or [] on timeout.
    Single-marker geometry is fragile (mirror flip in IPPE_SQUARE), so
    autonomous flight should require min_markers >= 2 to lock yaw_world.
    """
    _init()
    print('=== ARUCO CHECK (min_markers=%d) ===' % min_markers)
    print('Waiting for ArUco markers (timeout %ds)...' % timeout)
    result = {'ids': []}

    def cb(msg):
        if msg.markers and len(msg.markers) >= min_markers:
            result['ids'] = [m.id for m in msg.markers]

    sub = _node.create_subscription(MarkerArray, '/aruco_detect/markers', cb, 1)
    _keep_detector_awake()   # F1: detector awake from here until arming
    deadline = time.time() + timeout
    try:
        while rclpy.ok() and not result['ids']:
            if time.time() > deadline:
                print('ERROR: <%d ArUco markers detected after %ds.' % (min_markers, timeout))
                return []
            time.sleep(0.2)
    finally:
        _node.destroy_subscription(sub)
    print('ArUco markers visible: %s -- OK' % result['ids'])
    return result['ids']


def require_aruco(min_markers=1, timeout=15.0):
    """
    Preflight: insist on at least `min_markers` ArUco markers in view.

    Default is 1 — single-marker flight is supported via the slow yaw-lock
    path in aruco_detect (3s of consistent observation). For pure multi-marker
    operation pass min_markers=2 to skip the slow path entirely.

    Raises RuntimeError if not satisfied — caller usually exits or aborts.
    """
    ids = check_aruco(timeout=timeout, min_markers=min_markers)
    if len(ids) < min_markers:
        raise RuntimeError(
            'require_aruco: need >=%d markers, got %d' % (min_markers, len(ids)))
    return ids


def wait_yaw_lock(timeout=15.0):
    """
    Wait until aruco_detect publishes /aruco_detect/yaw_locked = True.

    Yaw lock means we have observed >=2 markers continuously for >=1.5s; from
    that point on, single-marker frames disambiguate via the locked yaw and
    survive the velocity gate. Without yaw lock, autonomous flight WILL
    eventually hit the IPPE mirror flip when down to a single marker.
    """
    _init()
    _keep_detector_awake()   # F1: keep the detector awake until arming
    print('=== WAITING FOR YAW LOCK (timeout %.0fs) ===' % timeout)
    deadline = time.time() + timeout
    while time.time() < deadline and not _aruco_yaw_locked:
        m_age = _markers_used_age()
        print('  markers_used=%d age=%.1fs yaw_locked=%s' % (
            _aruco_markers_used,
            (m_age if m_age != float('inf') else -1.0),
            _aruco_yaw_locked))
        time.sleep(0.5)
    if _aruco_yaw_locked:
        print('  yaw_locked=True -- OK')
        return True
    print('ERROR: yaw lock not acquired within %.0fs' % timeout)
    return False


def yaw_lock_age():
    """Seconds since /aruco_detect/yaw_locked last reported True. Returns math.inf if never seen."""
    if _aruco_yaw_locked_last_true_time is None:
        return math.inf
    return (_node.get_clock().now() - _aruco_yaw_locked_last_true_time).nanoseconds / 1e9


def require_vpe_link(min_hz=8.0, window=2.0, timeout=15.0):
    """Block until /mavros/mavros/pose_cov sustains min_hz over `window` seconds.

    Raises RuntimeError on timeout. Detects vpe_fix self-lock or upstream
    silence (z-jump self-lock incident 2026-05-26): if vpe_fix's gate is
    stuck, pose_cov stops flowing and EKF2 will fly on baro+IMU only.
    """
    _init()
    _keep_detector_awake()   # F1: keep the detector awake until arming
    from geometry_msgs.msg import PoseWithCovarianceStamped as _PWCS
    from rclpy.qos import QoSProfile as _QoS, ReliabilityPolicy as _RP, DurabilityPolicy as _DP
    import collections as _collections

    stamps = _collections.deque()
    done = {'ok': False}
    needed = max(1, int(min_hz * window))

    def _cb(_msg):
        t = time.monotonic()
        stamps.append(t)
        cutoff = t - window
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        if len(stamps) >= needed:
            done['ok'] = True

    # BEST_EFFORT to match MAVROS publisher QoS (RELIABLE sub would silently drop messages).
    qos = _QoS(depth=5)
    qos.reliability = _RP.BEST_EFFORT
    qos.durability  = _DP.VOLATILE
    sub = _node.create_subscription(
        _PWCS, '/mavros/mavros/pose_cov', _cb, qos)
    try:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if done['ok']:
                return
            time.sleep(0.1)
        rate = len(stamps) / window if stamps else 0.0
        raise RuntimeError(
            'require_vpe_link: pose_cov %.1f Hz < %.1f Hz over %.1fs '
            '(check vpe_fix gate / ArUco visibility)'
            % (rate, min_hz, window))
    finally:
        _node.destroy_subscription(sub)


# ---------------------------------------------------------------------------
# Position stability check
# ---------------------------------------------------------------------------

def wait_position_stable(stable_secs=3.0, tolerance=0.15, timeout=30.0,
                         require_multi_markers=False, tolerance_adaptive=True):
    """
    Wait until EKF2 position is valid AND (optionally) ArUco geometry is reliable.

    Default mode (single-marker tolerant): stability requires only that telemetry
    is non-NaN and successive samples stay within `tolerance`. The yaw-lock path
    in aruco_detect (single- or multi-marker) is what guards against IPPE flips,
    so this function does not need to insist on >=2 markers.

    Strict mode (require_multi_markers=True): also requires >=2 markers in the
    last 1.0s for the entire stability window. Use this when you want to skip
    the slow single-marker yaw-lock path entirely.

    tolerance_adaptive (default True): mirror navigate_wait's adaptive tolerance
    — relax to 0.30 m when only one marker is visible (single-marker PnP Z is
    pitch/roll coupled, so a static drone still shows ~10-20cm position jitter),
    keep the strict 0.15 m floor when >=2 markers locked.

    Transient NaN readings (<2s) are ignored — they are TF2 timing gaps.
    Returns True when stable, False on timeout.
    """
    _init()
    _keep_detector_awake()   # F1: keep the detector awake until arming
    base_tolerance = tolerance
    print('=== POSITION STABLE CHECK ===')
    print('Waiting for stable position (%.1fs window, timeout %.0fs, multi=%s, adaptive=%s)...'
          % (stable_secs, timeout, require_multi_markers, tolerance_adaptive))
    deadline = time.time() + timeout
    stable_since = None
    last_pos = None
    nan_since = None

    while time.time() < deadline:
        t = get_telemetry(frame_id='map')
        if math.isnan(t.x) or math.isnan(t.y):
            if nan_since is None:
                nan_since = time.time()
            nan_secs = time.time() - nan_since
            if nan_secs > 2.0:
                stable_since = None
                last_pos = None
                print('  position: NaN for %.1fs -- EKF2 not converged' % nan_secs)
            time.sleep(0.5)
            continue

        nan_since = None

        if tolerance_adaptive:
            mu = _aruco_markers_used
            m_age = _markers_used_age()
            if mu == 1 and m_age <= 1.5:
                tolerance = max(base_tolerance, 0.30)
            else:
                tolerance = base_tolerance

        pos = (t.x, t.y, t.z)
        if last_pos is not None:
            jump = math.sqrt((pos[0] - last_pos[0])**2 + (pos[1] - last_pos[1])**2)
            if jump > tolerance:
                stable_since = None
                print('  position jumped %.3fm (tol=%.2f) -- resetting stability window' % (jump, tolerance))
        last_pos = pos

        markers_ok = True
        if require_multi_markers:
            m_age = _markers_used_age()
            markers_ok = (_aruco_markers_used >= 2 and m_age <= 1.0)
            if not markers_ok:
                stable_since = None

        if stable_since is None and markers_ok:
            stable_since = time.time()

        elapsed = (time.time() - stable_since) if stable_since is not None else 0.0
        print('  position: x=%.3f y=%.3f z=%.3f | markers=%d yaw=%s | stable %.1fs/%.1fs' % (
            t.x, t.y, t.z,
            _aruco_markers_used, _aruco_yaw_locked,
            elapsed, stable_secs))
        if stable_since is not None and elapsed >= stable_secs:
            print('  position stable -- OK')
            return True
        time.sleep(0.5)

    print('ERROR: position not stable after %.0fs' % timeout)
    return False


# ---------------------------------------------------------------------------
# Core navigation primitive
# ---------------------------------------------------------------------------

def navigate_wait(x=0.0, y=0.0, z=0.0, yaw=float('nan'), speed=0.5, frame_id='body',
                  tolerance=0.2, auto_arm=False, phase='FLIGHT', timeout=60.0,
                  tolerance_adaptive=False, vision_timeout=6.0, settle_speed=None):
    """
    Send a navigation command and block until the drone reaches the target.
    Returns True if reached within tolerance, False on timeout/disarm/interrupt,
    or when the pilot / a PX4 failsafe has control (then the guards below never
    switch the mode: pilot wins, A4).

    If tolerance_adaptive=True, override `tolerance` based on the current
    /aruco_detect/markers_used: >=2 markers -> 0.15 m, ==1 marker -> 0.25 m,
    otherwise the passed-in `tolerance` is kept.

    settle_speed (F7, r2d; default None = arrive at the first sample within
    tolerance, as before): also require the horizontal speed below
    settle_speed m/s on 2 successive samples within tolerance, so the point
    counts only once the drone has nearly stopped there.
    """
    global _vision_abort
    _init()
    if tolerance_adaptive:
        mu = _aruco_markers_used
        if mu >= 2:
            tolerance = 0.15
        elif mu == 1:
            tolerance = 0.25
        print('navigate_wait: adaptive tolerance=%.2f (markers_used=%d)' % (tolerance, mu))
    res = None
    for attempt in range(5):
        if should_land:
            _node.get_logger().warn('Navigate retry aborted -- should_land=True')
            return False
        res = navigate(x=x, y=y, z=z, yaw=yaw, speed=speed,
                       frame_id=frame_id, auto_arm=auto_arm)
        if res.success:
            break
        if 'No local position' in res.message or 'position' in res.message.lower():
            _node.get_logger().warn('Navigate attempt %d failed: %s -- retrying' % (
                attempt + 1, res.message))
            # Sleep in slices so Ctrl-C aborts within ~50 ms.
            for _ in range(10):
                if should_land:
                    break
                time.sleep(0.05)
        else:
            break
    if should_land and (res is None or not res.success):
        return False
    if not res.success:
        _node.get_logger().error('Navigate failed: ' + res.message)
        return False

    deadline = time.time() + timeout
    # Catastrophic-EKF-divergence guard. Set on first valid sample.
    last_pos = None    # (x, y, z) from previous iteration
    last_t = None      # wall time of previous sample
    settled = 0        # F7: successive samples within tolerance below settle_speed
    while rclpy.ok() and not should_land:
        telem = get_telemetry(frame_id='navigate_target')
        t = _get_telemetry_robust(frame_id='map')
        dist = math.sqrt(telem.x**2 + telem.y**2 + telem.z**2)
        print('[%s] x=%.2f y=%.2f z=%.2f | dist=%.2f' % (
            phase, t.x, t.y, t.z, dist))
        if not t.armed:
            known, f_armed, f_mode = _fcu_mode_state()
            if not known:
                _node.get_logger().warn('FCU state unknown -- stopping navigation.')
            elif f_armed:
                _node.get_logger().warn('Telemetry does not confirm armed state -- stopping navigation.')
            else:
                _node.get_logger().warn('Drone disarmed unexpectedly -- stopping.')
            return False
        # Pilot wins (A4, 2026-10-13): the pilot (RC mode switch) or a PX4
        # failsafe took the armed vehicle out of OFFBOARD. Stop before the
        # guards below, so none of them lands it (/land or AUTO.LAND).
        known, f_armed, f_mode = _fcu_mode_state()
        if known and f_armed and f_mode != 'OFFBOARD':
            _node.get_logger().warn(
                'pilot/failsafe has control (armed, mode=%s) -- %s stopped, '
                'mode left as is' % (f_mode, phase))
            return False
        # Vision watchdog (drift fix 2026-06-10): once vision has been seen,
        # >vision_timeout without a usable (>=1 marker) frame means the vpe
        # gate has closed (its freshness windows are 1.0/1.5 s + 0.5 s
        # hysteresis) and EKF2 is coasting on IMU+baro. Chasing the setpoint
        # in a diverging frame physically drives the drone away from the
        # markers — land now. Takeoff passes a larger value: motor spin-up
        # vibration + the marker leaving the frame at ground level make a
        # vision gap during the climb expected, not an emergency.
        if t.armed and _aruco_markers_pos_time is not None \
                and _markers_pos_age() > vision_timeout:
            _vision_abort = True
            _node.get_logger().error(
                'Vision lost for %.1fs (markers_used=0, limit %.1fs) -- EKF '
                'is coasting, landing'
                % (_markers_pos_age(), vision_timeout))
            _land_if_offboard()
            return False
        # Stale-telemetry watchdog: _get_telemetry_robust(allow_stale=True)
        # keeps returning a frozen cached position on NaN, so prolonged NaN
        # previously went unnoticed (and blinded the jump guard below).
        telem_stale = _telem_staleness('map')
        if t.armed and telem_stale > 5.0:
            _vision_abort = True
            _node.get_logger().error(
                'Telemetry stale for %.1fs (NaN position) -- '
                'landing' % telem_stale)
            _land_if_offboard()
            return False
        # Safety: detect EKF divergence (single-marker IPPE flip cascades).
        # Skip when telemetry is NaN — that is a transient TF gap, not a glitch.
        # Also skip cached (stale) samples: comparing a frozen position to
        # itself yields jump=0 and silently disables this guard.
        if telem_stale < 0.2 and not (math.isnan(t.x) or math.isnan(t.y) or math.isnan(t.z)):
            # Below-floor guard (A7, 2026-10-13): measured from the height
            # recorded at arm time (0.0 if this script did not arm). An EKF z
            # this far under the floor is a diverged estimate, so land like
            # the other guards; a mid-air disarm (the old action) would drop
            # a drone that may really be 1-2 m up, and PX4 denies it anyway.
            floor_z = _arm_ref_z if _arm_ref_z is not None else 0.0
            if t.z < floor_z - 0.5:
                _vision_abort = True
                _node.get_logger().error(
                    'EKF z=%.2f is %.2f m below the height at arm (%.2f) -- '
                    'EKF diverged, landing'
                    % (t.z, floor_z - t.z, floor_z))
                _land_if_offboard()
                return False
            # Upper-altitude runaway guard (symmetric to the below-ground check
            # above): a slow upward EKF drift never trips the 3 m/s jump guard.
            if frame_id == 'map' and t.z > z + 0.6:
                _vision_abort = True
                _node.get_logger().error(
                    'Altitude overshoot: z=%.2f > target %.2f +0.6 -- runaway '
                    'climb, landing' % (t.z, z))
                _land_if_offboard()
                return False
            now = time.time()
            if last_pos is not None and last_t is not None:
                dt = now - last_t
                jump = math.sqrt((t.x - last_pos[0])**2 +
                                 (t.y - last_pos[1])**2 +
                                 (t.z - last_pos[2])**2)
                if dt > 0 and jump / dt > 3.0:
                    _node.get_logger().error(
                        'Position jump %.2fm in %.2fs (%.1f m/s) -- '
                        'EKF likely diverged, landing' % (jump, dt, jump / dt))
                    # PX4 rejects arming(False) while airborne; AUTO.LAND is
                    # the only way for the script to force the FCU down.
                    _land_if_offboard()
                    return False
            last_pos = (t.x, t.y, t.z)
            last_t = now
        if dist < tolerance:
            if settle_speed is None:
                return True
            # F7 (r2d): count the point only once the drone has nearly stopped
            # there; a NaN speed compares False and does not count
            v_xy = math.hypot(t.vx, t.vy)
            settled = settled + 1 if v_xy < settle_speed else 0
            if settled >= 2:
                return True
        else:
            settled = 0
        if time.time() > deadline:
            _node.get_logger().warn('Navigate timed out after %.0fs (dist=%.2f)' % (timeout, dist))
            return False
        time.sleep(0.5)
    return False


# ---------------------------------------------------------------------------
# High-level flight commands
# ---------------------------------------------------------------------------

def takeoff(height=1.0, speed=0.4, vision_timeout=25.0):
    """Arm the drone and climb to height meters above the current position.

    vision_timeout: vision-watchdog limit for the climb leg. Spin-up
    vibration and the marker filling/leaving the frame at ground level
    routinely blank detection for several seconds; 25 s covers arming +
    a slow climb to re-acquisition altitude while still bounding an
    IMU/baro-only coast.

    Pilot wins (A4, 2026-10-13): refused -- prints why, returns False --
    when the FCU state is unknown or the vehicle is armed and not in
    OFFBOARD (the pilot or a PX4 failsafe has control). The mode of an armed
    vehicle is never switched: a retry after an AUTO.LAND abort used to put
    the airborne drone in STABILIZED, which with the throttle stick low
    drops it. Returns True when the target height was reached.
    """
    _init()
    _keep_detector_awake()   # F1: keep the detector awake until arming
    known, armed, mode = _fcu_mode_state(wait=_FCU_STATE_WAIT)
    reason = _no_control_reason(known, armed, mode)
    if reason is not None:
        print('takeoff refused: ' + reason)
        return False
    non_arm_modes = ('AUTO.LAND', 'AUTO.RTL', 'AUTO.LOITER',
                     'AUTO.MISSION', 'AUTO.TAKEOFF')
    # Disarmed on the ground only: leave an AUTO.* mode (e.g. AUTO.LAND
    # after the last landing) before auto_arm asks for OFFBOARD.
    if not armed and mode in non_arm_modes:
        print('Mode is %s -- switching to STABILIZED' % mode)
        try:
            set_mode('STABILIZED')
        except Exception as e:
            _node.get_logger().warn('set_mode STABILIZED failed: %s' % e)
        # set_mode is async on PX4 -- poll until mode actually changed.
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if _fcu_mode_state()[2] not in non_arm_modes:
                break
            time.sleep(0.1)
    t = _get_telemetry_robust(frame_id='map')
    # After mode switch the FCU briefly publishes NaN local position
    # (TF gap between LP and map frame). simple_offboard rejects navigate
    # with "No local position" for the first 1-2 attempts. Wait up to 1 s
    # for fresh, finite telemetry before issuing navigate.
    settle_deadline = time.time() + 1.0
    while time.time() < settle_deadline and not should_land:
        t = _get_telemetry_robust(frame_id='map')
        if not (math.isnan(t.x) or math.isnan(t.y) or math.isnan(t.z)):
            break
        time.sleep(0.05)
    # Lock X/Y in map frame using current position so arming/setpoint timing
    # cannot shift the horizontal target (body→map transform race).
    print('=== TAKEOFF to %.1fm ===' % height)
    return navigate_wait(x=t.x, y=t.y, z=t.z + height, speed=speed, frame_id='map',
                         auto_arm=True, phase='TAKEOFF', tolerance=0.15, timeout=30.0,
                         vision_timeout=vision_timeout)


def fly_to(x, y, z=1.0, speed=0.5, tolerance=0.2, tolerance_adaptive=False,
           settle_speed=None):
    """Fly to absolute map coordinates (x, y, z).

    settle_speed (F7, r2d): see navigate_wait; None keeps the old arrival.
    """
    _init()
    print('=== FLY TO (%.2f, %.2f, %.2f) ===' % (x, y, z))
    return navigate_wait(x=x, y=y, z=z, speed=speed, frame_id='map', phase='FLY_TO',
                         tolerance=tolerance, tolerance_adaptive=tolerance_adaptive,
                         settle_speed=settle_speed)


def move(x=0, y=0, z=0, speed=0.5):
    """Move relative to the drone current position and heading. True on arrival."""
    _init()
    print('=== MOVE by (%.2f, %.2f, %.2f) ===' % (x, y, z))
    return navigate_wait(x=x, y=y, z=z, speed=speed, frame_id='body', phase='MOVE')


def hover(seconds=3.0):
    """Hold current position for the given number of seconds.

    Returns True after the full hold. Pilot wins (A4): when the pilot or a
    PX4 failsafe has control (or the FCU state is unknown) nothing is sent
    and it returns False at once -- a navigate here would restart the
    setpoint stream and could pull PX4 back into OFFBOARD out of a failsafe.
    """
    global should_land
    if should_land:
        return False
    _init()
    if not _set_mode_client.wait_for_service(timeout_sec=5.0):
        raise Exception('Service %s not available' % _set_mode_client.srv_name)
    reason = _no_control_reason(*_fcu_mode_state(wait=_FCU_STATE_WAIT))
    if reason is not None:
        print('hover: %s -- not hovering' % reason)
        return False
    t = _get_telemetry_robust(frame_id='map')
    res = navigate(x=t.x, y=t.y, z=t.z, yaw=math.nan,
                   speed=0.3, frame_id='map', auto_arm=False)
    if not res.success:
        print('hover: navigate rejected: ' + res.message)
    print('Hovering %.1fs...' % seconds)
    deadline = time.time() + seconds
    while time.time() < deadline and not should_land:
        known, armed, mode = _fcu_mode_state()
        if known and armed and mode != 'OFFBOARD':
            print('hover: pilot/failsafe has control (armed, mode=%s) -- stopped' % mode)
            return False
        time.sleep(0.1)
    return bool(res.success) and not should_land


def safe_land(x=None, y=None, precision_speed=0.2, precision_tolerance=0.07,
              timeout=25.0):
    """Land with optional precision approach above the given x, y point.

    Landing descent rate (MPC_LAND_SPEED) is set globally by vpe_fix.py at
    boot; this function must not write that PX4 param. The precision_speed
    / precision_tolerance kwargs control the XY approach navigation only.

    Descent verification (z-jump self-lock incident 2026-05-26): the old
    "armed=False -> landed" check accepted a failsafe-disarm at altitude as
    success. Now we require a fresh disarmed FCU state, z<0.20 m or a height
    within 0.20 m of the arm height, and |vz|<0.10 m/s for 0.5 s. A confirmed
    disarm above 0.50 m outside the arm-height band is treated as a fall
    (sys.exit(2)). An unknown state cannot confirm touchdown. On timeout we
    exit(3).

    Pilot wins (A4, 2026-10-13): if the vehicle is armed and not in OFFBOARD
    (the pilot took over with the RC, or PX4 entered a failsafe mode), or
    they take over during the descent, nothing is sent -- no approach, no
    /land, no AUTO.LAND switch -- and it returns False. Armed in AUTO.LAND
    is a landing already in progress (usually a navigate_wait guard of this
    script switched to it after an abort): nothing is sent either, but the
    descent is watched as below, so the script still ends only after
    touchdown. Returns True once landed and disarmed.
    """
    _init()
    # Capture before commands: the disarm callback clears the global reference.
    ref_z = _arm_ref_z
    last_ref_z = _last_arm_ref_z

    known, armed, mode = _fcu_mode_state(wait=_FCU_STATE_WAIT)
    if ref_z is None and known and not armed:
        # Already disarmed (e.g. a ground-hold DISARM after a guard): touchdown
        # is judged against the last arm height, a platform included
        ref_z = last_ref_z
    if known and armed and mode == 'AUTO.LAND':
        print('safe_land: landing already in progress (AUTO.LAND) -- no commands '
              'sent, watching the descent')
        return _watch_descent(timeout, ref_z)
    if known and armed and mode != 'OFFBOARD':
        print('safe_land: pilot/failsafe has control (armed, mode=%s) -- '
              'no commands sent' % mode)
        return False
    if not known:
        # Only /land below: simple_offboard lands only from OFFBOARD and
        # checks the state itself.
        print('safe_land: FCU state unknown -> straight /land (no approach/hover)')

    # Fix #3B (2026-05-27): defend against NaN XY propagating from a stale START telem.
    if x is None or y is None or \
       (isinstance(x, float) and math.isnan(x)) or \
       (isinstance(y, float) and math.isnan(y)):
        print('safe_land: precision XY=NaN -> straight land (no precision approach)')
        x, y = None, None

    # Drift fix (2026-06-10): never fly a blind precision approach. If the
    # mission aborted on vision loss, or markers are silent right now, the
    # EKF position cannot be trusted — navigating to (x, y) may carry the
    # drone metres away. Land in place instead.
    if x is not None and (_vision_abort or
                          (_aruco_markers_pos_time is not None
                           and _markers_pos_age() > 3.0)):
        print('safe_land: vision unhealthy -> straight land (no precision approach)')
        x, y = None, None

    if known and x is not None and y is not None:
        t = _get_telemetry_robust(frame_id='map')
        print('Precision approach to (%.2f, %.2f)...' % (x, y))
        navigate_wait(x=x, y=y, z=t.z, speed=precision_speed,
                      frame_id='map', tolerance=precision_tolerance,
                      phase='APPROACH')

    if known:
        hover(seconds=1.5)

    print('=== LANDING ===')
    landing_ok = False
    not_ours = False
    try:
        res = land()
        if res.success:
            landing_ok = True
        else:
            _node.get_logger().warn('Land command rejected: ' + res.message)
            not_ours = any(s in res.message for s in _LAND_NOT_OURS)
    except Exception as e:
        _node.get_logger().error('Land service error: ' + str(e))

    # Fallback: /land failed (simple_offboard down, busy or timed out) while
    # the Pi still holds the vehicle in OFFBOARD -> AUTO.LAND directly, or a
    # DISARM first inside the takeoff's ground hold (_land_fallback). Pilot wins: an armed vehicle in any
    # other mode (the pilot or a PX4 failsafe moved it out of OFFBOARD) is
    # never switched from here, nor after /land was refused for that reason
    # (then the descent check below decides, once this script's state shows
    # the new mode); AUTO.LAND (e.g. a /land that timed out but switched late)
    # is watched.
    if not landing_ok and not not_ours:
        known, armed, mode = _fcu_mode_state()
        if known and armed and mode == 'OFFBOARD':
            _land_fallback(in_hold=_in_takeoff_hold())
        elif known and armed and mode != 'AUTO.LAND':
            print('safe_land: pilot/failsafe has control (armed, mode=%s) -- '
                  'no AUTO.LAND fallback' % mode)
            return False
    return _watch_descent(timeout, ref_z)


def _watch_descent(timeout, ref_z=None):
    """safe_land's read-only descent check: True once landed and disarmed.

    Sends nothing. Returns False when the pilot or a PX4 failsafe takes the
    armed vehicle out of AUTO.LAND/OFFBOARD; exits the script on a fall
    (sys.exit(2)) or when it does not land within timeout s (sys.exit(3)).
    """
    descent_ok_since = None
    t0 = time.monotonic()
    last_print = 0.0
    while True:
        known, f_armed, f_mode = _fcu_mode_state()
        disarmed = known and not f_armed
        t = _get_telemetry_robust(frame_id='map')
        z  = t.z  if t.z  is not None else float('nan')
        vz = t.vz if t.vz is not None else float('nan')
        armed = f_armed if known else 'unknown'
        now = time.monotonic()
        if now - last_print > 0.5:
            vz_str = ('%.2f' % vz) if vz == vz else 'nan'
            z_str  = ('%.2f' % z)  if z == z  else 'nan'
            print('[LAND] z=%s vz=%s armed=%s' % (z_str, vz_str, armed))
            last_print = now

        # Pilot wins: AUTO.LAND (ours, or one already in progress) or OFFBOARD
        # (switch still pending) are the only armed modes expected here. Any
        # other one means the pilot or a PX4 failsafe took over: stop
        # supervising, change nothing.
        if known and f_armed and f_mode not in ('AUTO.LAND', 'OFFBOARD'):
            print('safe_land: pilot/failsafe has control (armed, mode=%s) -- '
                  'stopped watching the descent' % f_mode)
            return False

        # The arm-height band also covers landing back on an elevated platform.
        # Never interpret an unknown FCU state as disarmed.
        on_takeoff_level = ref_z is not None and (z == z) and abs(z - ref_z) < 0.20
        if disarmed and (z == z) and (z < 0.20 or on_takeoff_level) \
                and (vz == vz) and abs(vz) < 0.10:
            if descent_ok_since is None:
                descent_ok_since = now
            elif now - descent_ok_since >= 0.5:
                print('Landed and disarmed.')
                return True
        else:
            descent_ok_since = None

        # Failsafe-disarm at altitude == drone fell.
        if disarmed and (z == z) and z > 0.50 and not on_takeoff_level:
            print('CRITICAL: failsafe disarm at altitude z=%.2f vz=%s -- drone fell from height'
                  % (z, ('%.2f' % vz) if vz == vz else 'nan'))
            sys.exit(2)

        if (now - t0) > timeout:
            z_str = ('%.2f' % z) if z == z else 'nan'
            print('LAND TIMEOUT: drone failed to descend, z=%s' % z_str)
            sys.exit(3)

        time.sleep(0.1)
