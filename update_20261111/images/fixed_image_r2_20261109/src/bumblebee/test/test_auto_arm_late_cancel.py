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

"""P2: a Ctrl+C seen before navigate(auto_arm=True) returns is always a cancel (no ROS, no vehicle).

_call_auto_arm polls the pending Navigate request every 50 ms. If simple_offboard's success reply completes in the same
poll in which Ctrl+C set should_land, the takeoff is committed but still held on the ground (arm_settle_time): drone.py
requests /land once (none if a cancel /land already went out) and returns a failure that says the takeoff was cancelled
and carries the /land reply ('Takeoff not started: disarmed on the ground' inside the hold).
The doubles are test_drone_flight_guards' (virtual clock whose sleep advances time, fake node); the Navigate client
completes its reply at a chosen virtual time and answers a cancel if /land came first.

    python3 -m unittest discover -s test -p 'test_auto_arm_late_cancel.py'
"""
import os
import signal
import subprocess
import sys
import unittest
from types import SimpleNamespace

import test_drone_flight_guards as g

SUCCESS = 'Navigating from the ground start (takeoff not started yet)'   # simple_offboard's reply once committed
CANCELLED = 'Auto-arm cancelled: land requested; disarmed on the ground'  # its reply when /land came before the commit
LAND_IN_HOLD = 'Takeoff not started: disarmed on the ground'              # its /land reply inside the ground hold
LATE_PREFIX = 'Takeoff cancelled (Ctrl+C seen after simple_offboard committed the takeoff); '
LATE = (.02, .04)   # Ctrl+C and the success reply inside one 50 ms poll


class Client:
    """Navigate client: the reply completes at reply_at (virtual s after the call); a cancel if /land came first."""
    srv_name = '/navigate'

    def __init__(self, test, reply_at):
        self.test, self.reply_at, self.sent, self.removed, self.t0 = test, reply_at, 0, False, None

    def wait_for_service(self, timeout_sec=None):
        return True

    def call_async(self, req):
        self.sent += 1
        self.t0 = self.test.d.time.now
        return SimpleNamespace(done=self.done, result=self.result)

    def done(self):
        return self.test.d.time.now - self.t0 >= self.reply_at

    def result(self):
        land_before = [t for t in self.test.land_times if t - self.t0 < self.reply_at]
        return SimpleNamespace(success=not land_before, message=CANCELLED if land_before else SUCCESS)

    def remove_pending_request(self, future):
        self.removed = True


class LateCancel(unittest.TestCase):
    def setUp(self):
        self.d = g.load_drone()
        self.d.time = g.FakeTime()
        self.d._node = g.FakeNode()
        self.d.srv = SimpleNamespace(Navigate=g.NAVIGATE)
        self.land_times = []
        self.hold_at_land = []   # drone.py's hold start as each /land goes out
        self.set_land(lambda: SimpleNamespace(success=True, message=LAND_IN_HOLD))

    def set_land(self, fn):
        def land():
            self.land_times.append(self.d.time.now)
            self.hold_at_land.append(self.d._auto_arm_ok_t)
            return fn()
        self.d.land = land

    def logged(self, text):
        return any(text in m for m in self.d._node.log)

    def call(self, ctrl_c_at, reply_at):
        client = Client(self, reply_at)
        self.d._navigate_client = client
        start = self.d.time.now
        if ctrl_c_at is not None:
            self.d.time.on_advance.append(
                lambda dt: setattr(self.d, 'should_land', True) if self.d.time.now - start >= ctrl_c_at else None)
        return self.d._call_auto_arm(g.NAVIGATE.Request(), timeout=45.0), client

    def assert_cancelled(self, result):
        self.assertTrue(self.land_times, 'Ctrl+C lost: no /land, navigate returned %r' % (result.message,))
        self.assertFalse(result.success, 'Ctrl+C lost: navigate returned success (%r)' % (result.message,))
        self.assertIn('cancel', result.message.lower())
        self.assertIn('disarmed on the ground', result.message.lower())

    # the P2 window: Ctrl+C and the success reply inside the same 50 ms poll
    def test_ctrl_c_then_success_reply_in_the_same_sleep(self):
        self.assert_cancelled(self.call(*LATE)[0])

    def test_ctrl_c_just_before_the_wake(self):
        self.assert_cancelled(self.call(.049, .0495)[0])

    def test_ctrl_c_in_a_later_interval(self):
        self.assert_cancelled(self.call(.31, .34)[0])

    def test_land_requested_once(self):
        self.call(*LATE)
        self.assertEqual(len(self.land_times), 1)

    def test_hold_start_recorded_before_the_land(self):
        # later fallbacks (s7fix-07 hold window) know the ground hold: its start is the moment the late branch acts,
        # set BEFORE /land goes out (a disarm edge during /land then clears it, never the reverse)
        start = self.d.time.now
        self.call(*LATE)
        self.assertEqual(len(self.hold_at_land), 1)
        self.assertEqual(self.hold_at_land[0], self.land_times[0])
        self.assertGreaterEqual(self.hold_at_land[0] - start, .04)    # not before the reply arrived

    def test_disarmed_reply_has_no_motors_marker(self):
        result, _ = self.call(*LATE)
        self.assertNotIn('motors may be running', result.message)
        self.assertEqual(result.message, LATE_PREFIX + '/land: ' + LAND_IN_HOLD)
        self.assertTrue(self.logged(result.message))

    def test_land_raises_is_reported_not_raised(self):
        def boom():
            raise Exception('Service /land timed out')
        self.set_land(boom)
        result, _ = self.call(*LATE)
        self.assertFalse(result.success)
        self.assertEqual(len(self.land_times), 1)
        self.assertIn('/land failed: Service /land timed out', result.message)
        self.assertIn('motors may be running', result.message)
        self.assertTrue(self.logged(result.message))   # navigate_wait does not print it: the log must

    def test_land_rejected_keeps_the_marker(self):
        # a rejection text that happens to contain 'disarmed' must not drop the marker
        self.set_land(lambda: SimpleNamespace(success=False, message='not disarmed: Copter is not in OFFBOARD mode'))
        result, _ = self.call(*LATE)
        self.assertFalse(result.success)
        self.assertIn('/land rejected: not disarmed: Copter is not in OFFBOARD mode', result.message)
        self.assertIn('motors may be running', result.message)
        self.assertTrue(self.logged(result.message))

    def test_airborne_auto_land_reply(self):
        # reply seen after the hold (e.g. a stalled executor): simple_offboard switches to AUTO.LAND, message ''
        self.set_land(lambda: SimpleNamespace(success=True, message=''))
        result, _ = self.call(*LATE)
        self.assertFalse(result.success)
        self.assertIn('landing (AUTO.LAND)', result.message)
        self.assertIn('motors may be running', result.message)

    def test_in_loop_land_then_success_no_second_land(self):
        # Ctrl+C seen at the top of the loop, /land sent; simple_offboard had already committed, so the reply is success
        # while /land disarmed in the hold: one /land, a failure carrying its reply
        class Committed(Client):
            def result(self):
                return SimpleNamespace(success=True, message=SUCCESS)
        self.d._navigate_client = Committed(self, .12)
        self.d.time.on_advance.append(lambda dt: setattr(self.d, 'should_land', True))
        result = self.d._call_auto_arm(g.NAVIGATE.Request(), timeout=45.0)
        self.assertEqual(len(self.land_times), 1)
        self.assertFalse(result.success)
        self.assertEqual(result.message, LATE_PREFIX + '/land: ' + LAND_IN_HOLD)
        self.assertIsNone(self.d._auto_arm_ok_t)   # set only when the late branch itself sends /land

    # behaviour that stays as it was
    def test_ctrl_c_well_before_the_reply_cancels(self):
        result, client = self.call(.02, .5)
        self.assertEqual(len(self.land_times), 1)
        self.assertFalse(result.success)
        self.assertEqual(result.message, CANCELLED)
        self.assertEqual(client.sent, 1)

    def test_no_ctrl_c_success_is_returned(self):
        result, _ = self.call(None, .04)
        self.assertTrue(result.success)
        self.assertEqual(result.message, SUCCESS)
        self.assertEqual(self.land_times, [])

    def test_ctrl_c_after_return_is_the_callers(self):
        # Ctrl+C after _call_auto_arm returned: success stands; navigate_wait / the script's safe_land handle it
        result, _ = self.call(None, .04)
        self.d.should_land = True
        self.assertTrue(result.success)
        self.assertEqual(self.land_times, [])

    def test_ctrl_c_before_send_sends_nothing(self):
        self.d.should_land = True
        client = Client(self, .04)
        self.d._navigate_client = client
        result = self.d._call_auto_arm(g.NAVIGATE.Request())
        self.assertFalse(result.success)
        self.assertEqual((client.sent, self.land_times), (0, []))


class RealSignal(unittest.TestCase):
    def test_real_sigint_as_the_reply_completes(self):
        """Real SIGINT with enable_safe_interrupt, raised inside future.done() the moment it reports done."""
        script = r'''
import os, signal
from types import SimpleNamespace
import test_drone_flight_guards as g
g.DRONE_PY = os.environ['P2_DRONE_PY']
d = g.load_drone(); d._node = g.FakeNode(); d.srv = SimpleNamespace(Navigate=g.NAVIGATE)
class C:
    srv_name = '/navigate'; n = 0
    def wait_for_service(self, timeout_sec=None): return True
    def call_async(self, req):
        def done():
            C.n += 1
            if C.n < 3: return False
            if C.n == 3: os.kill(os.getpid(), signal.SIGINT)   # Ctrl+C as the success reply completes
            return True
        return SimpleNamespace(done=done, result=lambda: SimpleNamespace(success=True, message='Takeoff committed'))
    def remove_pending_request(self, f): pass
d._navigate_client = C()
def land():
    print('LAND', flush=True); return SimpleNamespace(success=True, message='Takeoff not started: disarmed on the ground')
d.land = land
d.enable_safe_interrupt()
r = d._call_auto_arm(g.NAVIGATE.Request(), timeout=10)
print('SUCCESS' if r.success else 'CANCELLED: ' + r.message, flush=True)
'''
        env = dict(os.environ, P2_DRONE_PY=g.DRONE_PY)
        proc = subprocess.run([sys.executable, '-B', '-c', script], cwd=os.path.dirname(os.path.abspath(__file__)),
                              env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        lines = proc.stdout.splitlines()
        self.assertEqual(lines[0], 'LAND')
        self.assertTrue(lines[1].startswith('CANCELLED: Takeoff cancelled'), lines)
        self.assertIn('disarmed on the ground', lines[1])


if __name__ == '__main__':
    unittest.main()
