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

"""Off-drone tests for scripts/notify_manager.py and examples/animations/*.py.

No hardware and no ROS: drone.py is replaced by fakes. notify_manager runs
in-process with a fake clock (each LED write costs 10 ms like the real I2C
write), so its loop covers many seconds of drone time in milliseconds. The
animation scripts run in a subprocess with a stub drone module and virtual
time, so their flash rate is measured deterministically.

    python3 -m unittest discover -s test -p 'test_notify_manager.py'
"""
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
SCRIPT = os.path.join(PKG, 'scripts', 'notify_manager.py')
ANIM_DIR = os.path.join(PKG, 'examples', 'animations')
# The students' copy at the repository root (examples/README: "extracted from
# the drone's system image"). Absent where only the package is installed.
STUDENT_ANIM_DIR = os.path.normpath(os.path.join(PKG, '..', '..', '..', '..',
                                                 'examples', 'animations'))

# Same numbering as examples/drone.py.
LEDS = {'LED_1': 0, 'LED_2': 5, 'LED_3': 1, 'LED_4': 3, 'LED_5': 2, 'LED_6': 4}
STRIPS = tuple(sorted(LEDS.values()))
ALL = 255
PIXELS = 11
TUNE_ERROR = 'MFT180L8O5GEC<G'
TUNE_NOTIFY = 'MFT180L8O5E4C4'
MAX_FLASHES_PER_S = 3


def _import_stub():
    """Just enough of drone.py for notify_manager's module-level code."""
    m = types.ModuleType('drone')
    m.__dict__.update(LEDS)
    m.LED_ALL = m.STRIP_ALL = ALL
    m.TUNE_ERROR, m.TUNE_NOTIFY = TUNE_ERROR, TUNE_NOTIFY
    return m


def load_notify_manager():
    """A fresh notify_manager module (fresh globals) with a stub drone.

    The stub is only in sys.modules during the import: test_wifi_manager must
    still see "no drone.py" when it imports wifi_manager later in this run.
    """
    saved_mod, saved_path = sys.modules.get('drone'), list(sys.path)
    sys.modules['drone'] = _import_stub()
    try:
        spec = importlib.util.spec_from_file_location('notify_manager_under_test', SCRIPT)
        nm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nm)
    finally:
        sys.path[:] = saved_path
        if saved_mod is None:
            sys.modules.pop('drone', None)
        else:
            sys.modules['drone'] = saved_mod
    return nm


class FakeTime:
    """Stands in for the time module inside notify_manager."""

    def __init__(self):
        self.t = 1000.0
        self.on_sleep = None

    def monotonic(self):
        return self.t

    def time(self):
        return 1.7e9 + self.t

    def sleep(self, dt):
        self.t += max(0.0, dt)
        if self.on_sleep is not None:
            self.on_sleep()


class FakeDrone:
    """Records LED writes (with fake-clock time) and buzzer tunes."""
    TUNE_ERROR, TUNE_NOTIFY = TUNE_ERROR, TUNE_NOTIFY
    LED_ALL = STRIP_ALL = ALL

    def __init__(self, clock):
        self.clock = clock
        self.writes = []          # (t, strip, led, (r, g, b))
        self.tunes = []
        self.pos_age = float('inf')
        self._aruco_yaw_locked = False

    def set_led(self, strip, led, r, g, b):
        self.writes.append((self.clock.t, strip, led, (r, g, b)))
        self.clock.t += 0.010     # the real write sleeps 10 ms

    def led_off(self):
        self.set_led(ALL, ALL, 0, 0, 0)

    def play_tune(self, tune, *a, **k):
        self.tunes.append(tune)

    def _markers_pos_age(self):
        return self.pos_age

    def get_telemetry(self, frame_id='map'):
        return types.SimpleNamespace(connected=True)

    def led_take_control(self):
        pass

    def led_release_control(self):
        pass


for _name, _value in LEDS.items():
    setattr(FakeDrone, _name, _value)


class OsProxy:
    """os for notify_manager, except that os._exit() raises instead of exiting."""

    def __getattr__(self, name):
        return getattr(os, name)

    @staticmethod
    def _exit(code):
        raise SystemExit(code)


def dead_pid():
    """PID of a process that has exited and been reaped."""
    p = subprocess.Popen([sys.executable, '-c', ''])
    p.wait()
    return p.pid


def strip_timelines(writes, strips=STRIPS):
    """Per-strip list of (t, rgb), expanding STRIP_ALL (notify_manager uses LED_ALL)."""
    out = {s: [] for s in strips}
    for t, strip, _led, rgb in writes:
        for s in (strips if strip == ALL else (strip,)):
            if s in out:
                out[s].append((t, rgb))
    return out


def edges(timeline):
    """Rising and falling crossings of 50 % of the peak, for brightness and each channel.

    Returns a list of (signal_name, rising_times, falling_times) for every
    signal bright enough to matter.
    """
    result = []
    signals = (('brightness', lambda c: max(c)), ('red', lambda c: c[0]),
               ('green', lambda c: c[1]), ('blue', lambda c: c[2]))
    for name, f in signals:
        values = [(t, f(rgb)) for t, rgb in timeline]
        peak = max([v for _, v in values] or [0])
        if peak < 16:
            continue
        thr = peak / 2.0
        rising, falling, prev = [], [], None
        for t, v in values:
            if prev is not None:
                if prev < thr <= v:
                    rising.append(t)
                elif prev >= thr > v:
                    falling.append(t)
            prev = v
        result.append((name, rising, falling))
    return result


def max_per_second(times):
    """Most events inside any 1-second window."""
    best = 0
    for i, t0 in enumerate(times):
        n = sum(1 for t in times[i:] if t < t0 + 1.0)
        best = max(best, n)
    return best


def worst_flash_rate(timelines):
    """(max flashes in any second, min period between flashes, where) over all signals."""
    worst, min_period, where = 0, float('inf'), None
    for key, tl in timelines.items():
        for name, rising, falling in edges(tl):
            for times in (rising, falling):
                n = max_per_second(times)
                if n > worst:
                    worst, where = n, '%s %s' % (key, name)
                for a, b in zip(times, times[1:]):
                    min_period = min(min_period, b - a)
    return worst, min_period, where


class NotifyTestBase(unittest.TestCase):

    def setUp(self):
        self.nm = nm = load_notify_manager()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lock = os.path.join(self.tmp.name, 'led_busy')
        self.alarm = os.path.join(self.tmp.name, 'led_alarm')
        self.color = os.path.join(self.tmp.name, 'led_user_color')
        self.clock = FakeTime()
        self.drone = FakeDrone(self.clock)
        nm.time, nm.drone, nm.os = self.clock, self.drone, OsProxy()
        self.log = []                      # notify_manager's journal lines
        nm.print = lambda *a, **k: self.log.append(' '.join(str(x) for x in a))
        nm.LOCK_FILE, nm.ALARM_FILE, nm.USER_COLOR_FILE = self.lock, self.alarm, self.color
        nm._wifi.update(state='connected', t=self.clock.t - 100.0)
        self.fc_ok()

    # --- drone conditions ---------------------------------------------------
    def fc_ok(self):
        self.nm._telem.update(connected=True, ok=True, cell=float('nan'), mode='POSCTL')
        self.nm._seen_fcu = True
        self.nm._last_conn_t = self.clock.t

    def fc_lost(self, ago=5.0):
        self.nm._telem.update(connected=False, ok=False)
        self.nm._seen_fcu = True
        self.nm._last_conn_t = self.clock.t - ago

    def battery(self, cell):
        self.nm._telem.update(connected=True, ok=True, cell=cell)
        self.nm._last_conn_t = self.clock.t

    def make_lock(self, content=''):
        with open(self.lock, 'w') as f:
            f.write(content)

    def set_user_color(self, r, g, b):
        with open(self.color, 'w') as f:
            json.dump({'r': r, 'g': g, 'b': b}, f)

    # --- running ------------------------------------------------------------
    def run_for(self, seconds, events=()):
        """Run notify_manager's real main loop for `seconds` of fake time.

        events: (offset_s, callable) applied once the clock passes start+offset,
        without restarting the loop (so it keeps its previous-state memory).
        """
        start = self.clock.t
        end = start + seconds
        pending = sorted(events, key=lambda e: e[0])
        nm = self.nm

        def on_sleep():
            while pending and self.clock.t >= start + pending[0][0]:
                pending.pop(0)[1]()
            if self.clock.t >= end:
                nm._stop.set()
        self.clock.on_sleep = on_sleep
        nm._stop.clear()
        nm.main_loop()
        self.clock.on_sleep = None

    def writes_since(self, t):
        return [w for w in self.drone.writes if w[0] >= t]

    @staticmethod
    def red_only(writes):
        return [w for w in writes if w[3][0] > 0 and w[3][1] == 0 and w[3][2] == 0]

    @staticmethod
    def status_pattern(writes):
        """Writes to single strips: the IDLE / CONNECTING status patterns."""
        return [w for w in writes if w[1] != ALL]


class AlarmOverLockTest(NotifyTestBase):
    """Finding 1: a user colour or show must not silence ERROR / LOW_BATTERY."""

    def test_fc_lost_shows_over_user_color(self):
        self.make_lock('')                 # wifi_manager's /api/led/color lock
        self.fc_lost()
        self.run_for(1.0)
        self.assertTrue(self.red_only(self.drone.writes),
                        'FC-lost alarm not painted while /tmp/led_busy is held')
        self.assertTrue(os.path.exists(self.alarm), '/tmp/led_alarm not raised')
        with open(self.alarm) as f:
            self.assertEqual(f.read().strip(), str(os.getpid()))
        self.assertEqual(len([m for m in self.log if 'drawn over' in m]), 1,
                         'the journal should say once that the user LEDs are paused')

    def test_low_battery_shows_over_user_show(self):
        self.make_lock(str(os.getpid()))   # a live show / animation owns the lock
        self.battery(3.4)
        self.run_for(3.0)
        self.assertTrue(self.red_only(self.drone.writes),
                        'LOW_BATTERY not painted while /tmp/led_busy is held')

    def test_buzzer_is_independent_of_the_lock(self):
        self.make_lock('')
        self.battery(3.4)
        self.run_for(3.0)
        self.assertIn(self.nm.TUNE_LOWBATT, self.drone.tunes)

    def test_normal_states_still_yield_to_the_lock(self):
        self.make_lock(str(os.getpid()))
        self.run_for(5.0)                  # IDLE
        self.assertEqual(self.drone.writes, [])

    def test_static_user_color_comes_back_after_the_alarm(self):
        self.make_lock('')
        self.set_user_color(0, 0, 200)
        self.fc_lost()
        self.run_for(2.0)
        self.fc_ok()
        t = self.clock.t
        self.run_for(3.0)
        self.assertEqual([w[3] for w in self.writes_since(t)], [(0, 0, 200)],
                         'expected exactly one write after the alarm: the user colour')
        self.assertFalse(os.path.exists(self.alarm), '/tmp/led_alarm left behind')
        self.assertTrue(os.path.exists(self.lock), 'user lock must survive the alarm')

    def test_animation_owner_gets_the_leds_back(self):
        self.make_lock(str(os.getpid()))   # a running animation; no user colour
        self.fc_lost()
        self.run_for(2.0)
        self.assertTrue(self.red_only(self.drone.writes))
        self.fc_ok()
        t = self.clock.t
        self.run_for(3.0)
        # One blank so no red is left on strips the animation repaints lazily,
        # then hands off: the animation paints again once /tmp/led_alarm is gone.
        self.assertEqual([w[3] for w in self.writes_since(t)], [(0, 0, 0)])
        self.assertFalse(os.path.exists(self.alarm))

    def test_older_user_color_is_not_restored_over_a_newer_owner(self):
        self.set_user_color(0, 200, 0)
        st = os.stat(self.color)
        os.utime(self.color, ns=(st.st_atime_ns, st.st_mtime_ns - 10 ** 9))
        self.make_lock(str(os.getpid()))   # an animation started after that colour
        self.fc_lost()
        self.run_for(1.0)
        self.fc_ok()
        t = self.clock.t
        self.run_for(1.0)
        self.assertEqual([w[3] for w in self.writes_since(t)], [(0, 0, 0)])

    def test_reset_during_alarm_returns_to_status_lights(self):
        self.make_lock('')
        self.fc_lost()
        self.run_for(1.0)
        os.remove(self.lock)               # /api/led/reset
        self.fc_ok()
        t = self.clock.t
        self.run_for(1.0)
        self.assertTrue(self.status_pattern(self.writes_since(t)))
        self.assertFalse(os.path.exists(self.alarm))


class StaleLockTest(NotifyTestBase):
    """A lock nobody will ever release must not freeze the status lights."""

    def test_lock_of_a_dead_owner_is_ignored_and_removed(self):
        self.make_lock('%d\n' % dead_pid())
        t0 = self.clock.t
        self.run_for(3.0)
        pattern = self.status_pattern(self.drone.writes)
        self.assertTrue(pattern, 'status lights stayed off under a dead owner\'s lock')
        self.assertFalse(os.path.exists(self.lock))
        self.assertEqual(len([m for m in self.log if 'stale' in m]), 1)
        # A short grace period: a lock being rewritten is not judged on one read.
        self.assertGreaterEqual(pattern[0][0] - t0, 0.9)

    def test_lock_of_a_live_owner_is_kept_however_old(self):
        self.nm.LEGACY_LOCK_MAX_S = 3.0
        self.make_lock(str(os.getpid()))
        self.run_for(20.0)
        self.assertEqual(self.drone.writes, [])
        self.assertTrue(os.path.exists(self.lock))

    def test_ownerless_lock_expires(self):
        self.nm.LEGACY_LOCK_MAX_S = 3.0
        self.make_lock('')
        self.run_for(2.5)
        self.assertEqual(self.drone.writes, [])
        self.run_for(1.5)
        self.assertTrue(self.status_pattern(self.drone.writes))
        self.assertFalse(os.path.exists(self.lock), 'expired lock not removed, so the '
                         'next /api/led/color would not re-create it')

    def test_new_user_color_renews_an_ownerless_lock(self):
        self.nm.LEGACY_LOCK_MAX_S = 3.0
        self.make_lock('')
        self.run_for(2.0)
        self.set_user_color(10, 20, 30)   # wifi_manager: another /api/led/color
        self.run_for(2.0)
        self.assertEqual(self.drone.writes, [])
        self.run_for(1.5)
        self.assertTrue(self.status_pattern(self.drone.writes))

    def test_old_file_time_alone_does_not_expire_a_lock(self):
        # After boot the clock jumps (NTP / clock_jump.sh): every lock suddenly
        # looks old by wall clock. Age is counted on the monotonic clock.
        self.make_lock('')
        os.utime(self.lock, (1.0, 1.0))
        self.run_for(2.0)
        self.assertEqual(self.drone.writes, [])


class FlashRateTest(NotifyTestBase):
    """No status light may flash more than 3 times per second."""

    def flash_stats(self, seconds=4.0):
        self.run_for(1.5)                  # let debounced states settle
        t = self.clock.t
        self.run_for(seconds)
        return worst_flash_rate(strip_timelines(self.writes_since(t)))

    def test_error_flash_period_at_least_a_third_of_a_second(self):
        self.fc_lost()
        n, period, where = self.flash_stats()
        self.assertGreater(n, 0, 'ERROR does not flash at all')
        self.assertLessEqual(n, MAX_FLASHES_PER_S, 'ERROR: %d flashes/s on %s' % (n, where))
        self.assertGreaterEqual(period, 1.0 / 3, 'ERROR flash period %.3f s' % period)

    def test_every_status_state_within_the_limit(self):
        setups = {
            'ERROR': lambda: self.fc_lost(),
            'LOW_BATTERY': lambda: self.battery(3.4),
            'HOTSPOT': lambda: self.nm._wifi.update(state='hotspot'),
            'CONNECTING': lambda: self.nm._wifi.update(state='connecting', t=self.clock.t - 10),
            'IDLE': lambda: None,
            'ARUCO_SEARCH': lambda: setattr(self.drone, 'pos_age', 2.0),
            'ARUCO_LOCK': lambda: (setattr(self.drone, 'pos_age', 0.5),
                                   setattr(self.drone, '_aruco_yaw_locked', True)),
        }
        for state, setup in setups.items():
            with self.subTest(state=state):
                self.setUp()
                setup()
                n, period, where = self.flash_stats()
                self.assertEqual(self.nm.resolve_state(), state)
                self.assertLessEqual(n, MAX_FLASHES_PER_S,
                                     '%s: %d flashes/s on %s' % (state, n, where))

    def rising_brightness(self, seconds=4.0):
        self.run_for(1.5)
        t = self.clock.t
        self.run_for(seconds)
        tl = strip_timelines(self.writes_since(t))[STRIPS[0]]
        return tl, edges(tl)[0][1]

    def test_error_and_low_battery_look_different(self):
        self.fc_lost()
        err, err_rising = self.rising_brightness()
        self.assertGreater(min(max(rgb) for _, rgb in err), 0,
                           'ERROR goes fully dark: keep a dim floor (pulse, not strobe)')
        self.setUp()
        self.battery(3.4)
        _, low_rising = self.rising_brightness()
        err_rising, low_rising = len(err_rising), len(low_rising)
        self.assertGreater(low_rising, 0)
        self.assertGreaterEqual(err_rising, 2 * low_rising,
                                'ERROR (%d) and LOW_BATTERY (%d) blink at similar rates'
                                % (err_rising, low_rising))


class FcLostSoundTest(NotifyTestBase):
    """The buzzer sits on the FC: the FC-lost alarm is light-only on the drone."""

    def test_error_never_plays_a_tune(self):
        self.nm._telem['connected'] = True   # even when telemetry claims a link
        self.nm.handle_sound('ERROR', None)
        self.nm.handle_sound('ERROR', 'IDLE')
        self.assertEqual(self.drone.tunes, [])

    def test_loop_in_error_plays_nothing(self):
        self.fc_lost()
        self.run_for(10.0)
        self.assertEqual(self.drone.tunes, [])

    def test_selftest_does_not_fake_the_fc_lost_tune(self):
        with self.assertRaises(SystemExit):
            self.nm.selftest()
        self.assertNotIn(TUNE_ERROR, self.drone.tunes)
        self.assertTrue(self.drone.tunes, 'selftest should still play the other tunes')

    def test_fc_back_chimes_connected(self):
        self.fc_lost()
        self.run_for(2.0, events=[(1.0, self.fc_ok)])
        self.assertEqual(self.drone.tunes, [TUNE_NOTIFY])


class LowBatteryDebounceTest(NotifyTestBase):
    """LOW_BATTERY now paints over user LEDs, so it must not flap."""

    def states(self, seconds, step=0.05):
        out = []
        end = self.clock.t + seconds
        while self.clock.t < end:
            out.append(self.nm.resolve_state())
            self.clock.t += step
        return out

    def test_single_low_reading_is_ignored(self):
        self.battery(3.4)
        first = self.states(0.5)
        self.battery(3.9)
        rest = self.states(6.0)
        self.assertNotIn('LOW_BATTERY', first + rest)

    def test_low_battery_holds_through_a_short_recovery(self):
        self.battery(3.4)
        self.states(2.0)
        self.battery(3.9)                 # sag recovers for a moment
        self.assertEqual(set(self.states(4.0)), {'LOW_BATTERY'})
        self.assertEqual(self.states(2.0)[-1], 'IDLE')


class StartupTest(NotifyTestBase):

    def run_main(self):
        nm = self.nm
        nm.signal = types.SimpleNamespace(signal=lambda *a: None, SIGTERM=15, SIGINT=2)
        nm.threading = types.SimpleNamespace(
            Thread=lambda **k: types.SimpleNamespace(start=lambda: None),
            Event=nm.threading.Event, Lock=nm.threading.Lock)
        self.clock.on_sleep = nm._stop.set
        saved = sys.argv
        sys.argv = ['notify_manager.py']
        try:
            nm.main()
        finally:
            sys.argv = saved

    def test_restart_does_not_blank_the_lock_owner(self):
        # clock_jump.sh restarts notify-manager; the user's colour must survive.
        self.make_lock(str(os.getpid()))
        with open(self.alarm, 'w') as f:
            f.write('%d\n' % dead_pid())   # left by a crashed instance
        self.run_main()
        self.assertEqual(self.drone.writes, [])
        self.assertFalse(os.path.exists(self.alarm), 'stale /tmp/led_alarm kept')

    def test_start_blanks_leds_when_free(self):
        self.run_main()
        self.assertEqual(self.drone.writes[0][1:], (ALL, ALL, (0, 0, 0)))

    def test_stop_does_not_blank_the_lock_owner(self):
        self.make_lock(str(os.getpid()))
        self.run_for(1.0)
        with self.assertRaises(SystemExit):
            self.nm._shutdown(15, None)    # systemctl restart notify-manager
        self.assertEqual(self.drone.writes, [])

    def test_stop_during_alarm_gives_the_leds_back(self):
        self.make_lock('')
        self.set_user_color(9, 8, 7)
        self.fc_lost()
        self.run_for(1.0)
        t = self.clock.t
        with self.assertRaises(SystemExit):
            self.nm._shutdown(15, None)
        self.assertEqual([w[3] for w in self.writes_since(t)], [(9, 8, 7)])
        self.assertFalse(os.path.exists(self.alarm))


# --- examples/animations/*.py ------------------------------------------------
STUB_DRONE = r'''
import os, time
LED_1, LED_2, LED_3, LED_4, LED_5, LED_6 = 0, 5, 1, 3, 2, 4
LED_ALL = STRIP_ALL = 255
LED_RING = [LED_2, LED_4, LED_1, LED_3, LED_5, LED_6]
_LED_BUSY_FILE = os.environ['STUB_LED_BUSY']
_LED_ALARM_FILE = os.environ['STUB_LED_ALARM']
_log = open(os.environ['STUB_LED_LOG'], 'w', buffering=1)
_lock_logged = False


def set_led(strip, led, r, g, b):
    global _lock_logged
    if not _lock_logged:
        _lock_logged = True
        try:
            with open(_LED_BUSY_FILE) as f:
                content = f.read().strip()
        except OSError:
            content = ''
        _log.write('LOCK %s\n' % (content or '-'))
    _log.write('%.6f %d %d %d %d %d\n' % (time.monotonic(), strip, led, r, g, b))
    time.sleep(0.010)


def led_off():
    set_led(STRIP_ALL, LED_ALL, 0, 0, 0)


def led_take_control():
    open(_LED_BUSY_FILE, 'w').close()
    time.sleep(0.4)


def led_release_control():
    try:
        os.remove(_LED_BUSY_FILE)
    except FileNotFoundError:
        pass
'''

# Runs one animation with virtual time: time.sleep() only advances a counter,
# so a 4 s run takes milliseconds and every interval is exact. SIGTERM (what
# wifi_manager sends) arrives at STUB_END_S; the alarm flag appears/disappears
# at STUB_ALARM_ON_S/STUB_ALARM_OFF_S as notify_manager would do it.
RUNNER = r'''
import os, runpy, signal, sys, time
stub_dir, anim_dir, script = sys.argv[1:4]
env = os.environ
END = float(env['STUB_END_S'])
ON = float(env.get('STUB_ALARM_ON_S', 'inf'))
OFF = float(env.get('STUB_ALARM_OFF_S', 'inf'))
T0 = 1000.0
now = [T0]
flags = {'term': False, 'on': False, 'off': False}

def tick():
    t = now[0] - T0
    if t >= ON and not flags['on']:
        flags['on'] = True
        with open(env['STUB_LED_ALARM'], 'w') as f:
            f.write(env['STUB_ALARM_PID'] + '\n')
    if t >= OFF and not flags['off']:
        flags['off'] = True
        os.remove(env['STUB_LED_ALARM'])
    if t >= END and not flags['term']:
        flags['term'] = True
        os.kill(os.getpid(), signal.SIGTERM)
    if t >= END + 5.0:
        sys.stderr.write('animation ignored SIGTERM\n')
        os._exit(3)

def sleep(dt):
    now[0] += max(0.0, dt)
    tick()

time.sleep = sleep
time.monotonic = lambda: now[0]
time.time = lambda: 1.7e9 + now[0]
sys.path.insert(0, stub_dir)
import drone  # the stub; cached, so the script's own "import drone" gets it
sys.path.insert(0, anim_dir)
sys.argv = [script]
runpy.run_path(script, run_name='__main__')
'''

T0 = 1000.0


def animation_names():
    return sorted(f[:-3] for f in os.listdir(ANIM_DIR)
                  if f.endswith('.py') and not f.startswith('_'))


class AnimationRun:
    def __init__(self, name, tmp, end_s=4.0, alarm_on=None, alarm_off=None, alarm_pid=None):
        self.name = name
        d = os.path.join(tmp, name)
        os.mkdir(d)
        with open(os.path.join(d, 'drone.py'), 'w') as f:
            f.write(STUB_DRONE)
        self.lock = os.path.join(d, 'led_busy')
        self.alarm = os.path.join(d, 'led_alarm')
        self.log = os.path.join(d, 'led.log')
        env = dict(os.environ, STUB_LED_BUSY=self.lock, STUB_LED_ALARM=self.alarm,
                   STUB_LED_LOG=self.log, STUB_END_S=str(end_s))
        if alarm_on is not None:
            env.update(STUB_ALARM_ON_S=str(alarm_on), STUB_ALARM_OFF_S=str(alarm_off),
                       STUB_ALARM_PID=str(alarm_pid))
        self.proc = subprocess.Popen(
            [sys.executable, '-c', RUNNER, d, ANIM_DIR, os.path.join(ANIM_DIR, name + '.py')],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.end_s = end_s

    def finish(self, timeout=20):
        try:
            out, _ = self.proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            out, _ = self.proc.communicate()
            raise AssertionError('%s did not stop: %s' % (self.name, out.decode(errors='replace')))
        self.output = out.decode(errors='replace')
        self.lock_content, self.writes = None, []
        if not os.path.exists(self.log):
            return self
        with open(self.log) as f:
            for line in f:
                if line.startswith('LOCK '):
                    self.lock_content = line[5:].strip()
                    continue
                t, strip, led, r, g, b = line.split()
                self.writes.append((float(t) - T0, int(strip), int(led),
                                    (int(r), int(g), int(b))))
        return self

    def pixel_timelines(self, until):
        """Per-(strip, pixel) list of (t, rgb) before `until` (the SIGTERM time)."""
        out = {(s, p): [] for s in STRIPS for p in range(PIXELS)}
        for t, strip, led, rgb in self.writes:
            if t >= until:
                break
            for s in (STRIPS if strip == ALL else (strip,)):
                for p in (range(PIXELS) if led == ALL else (led,)):
                    out[(s, p)].append((t, rgb))
        return out


class AnimationTest(unittest.TestCase):
    """The GCS Entertainment animations and shows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_no_animation_flashes_more_than_3_times_per_second(self):
        runs = [AnimationRun(n, self.tmp.name) for n in animation_names()]
        problems = []
        for run in runs:
            run.finish()
            self.assertEqual(run.proc.returncode, 0, '%s crashed:\n%s' % (run.name, run.output))
            self.assertTrue(run.writes, '%s wrote nothing' % run.name)
            n, _, where = worst_flash_rate(run.pixel_timelines(until=run.end_s))
            if n > MAX_FLASHES_PER_S:
                problems.append('%s: %d flashes/s (%s)' % (run.name, n, where))
        self.assertEqual(problems, [])

    def test_animations_record_their_pid_in_the_lock_and_release_it(self):
        runs = [AnimationRun(n, self.tmp.name, end_s=1.0) for n in animation_names()]
        for run in runs:
            run.finish()
            with self.subTest(animation=run.name):
                self.assertEqual(run.lock_content, str(run.proc.pid),
                                 'notify_manager cannot tell when this owner is gone')
                self.assertFalse(os.path.exists(run.lock), 'lock not released')

    def test_animation_pauses_while_the_alarm_is_shown(self):
        run = AnimationRun('rainbow', self.tmp.name, end_s=4.0,
                           alarm_on=1.5, alarm_off=2.5, alarm_pid=os.getpid()).finish()
        during = [w for w in run.writes if 1.5 <= w[0] < 2.5]
        after = [w for w in run.writes if 2.5 <= w[0] < 3.5]
        self.assertEqual(during, [], 'animation painted over the FC-lost alarm')
        self.assertTrue(after, 'animation did not come back after the alarm')

    def test_alarm_flag_of_a_dead_notify_manager_is_ignored(self):
        run = AnimationRun('rainbow', self.tmp.name, end_s=4.0,
                           alarm_on=1.5, alarm_off=3.9, alarm_pid=dead_pid()).finish()
        during = [w for w in run.writes if 2.0 <= w[0] < 3.5]
        self.assertTrue(during, 'a crashed notify_manager must not leave animations dark')


class StudentCopyTest(unittest.TestCase):
    """examples/animations at the repository root is what students read, copy
    to the drone and run. It must be the drone's own scripts, so it keeps the
    3 flashes/s limit and pauses under the FC-lost / low-battery alarm too."""

    def setUp(self):
        if not os.path.isdir(STUDENT_ANIM_DIR):
            self.skipTest('no repository examples/ here (installed package only)')

    @staticmethod
    def read(path):
        with open(path, 'rb') as f:
            return f.read()

    def test_student_copies_are_the_drone_scripts(self):
        different = []
        for f in sorted(os.listdir(STUDENT_ANIM_DIR)):
            if not f.endswith('.py'):
                continue
            ours = os.path.join(ANIM_DIR, f)
            if not os.path.exists(ours):
                different.append('%s: not on the drone' % f)
            elif self.read(ours) != self.read(os.path.join(STUDENT_ANIM_DIR, f)):
                different.append('%s: differs from the drone copy' % f)
        self.assertEqual(different, [], 'copy them from %s' % ANIM_DIR)

    def test_student_copies_have_the_helpers_they_import(self):
        missing = []
        for f in sorted(os.listdir(STUDENT_ANIM_DIR)):
            if not f.endswith('.py'):
                continue
            tree = ast.parse(self.read(os.path.join(STUDENT_ANIM_DIR, f)))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    helper = name.split('.')[0] + '.py'
                    if (os.path.exists(os.path.join(ANIM_DIR, helper))
                            and not os.path.exists(os.path.join(STUDENT_ANIM_DIR, helper))):
                        missing.append('%s imports %s' % (f, helper))
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
