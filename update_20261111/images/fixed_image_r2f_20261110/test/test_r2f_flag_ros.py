"""r2f T34 with real ROS: real simple_offboard binary + the package's faithful fake FCU (test/fake_mavros.py, Px4Model).
No MAVLink, no Gazebo, no drone; localhost only, every name under the private /bb_test_* namespace (guard_graph()).

The T34 race, made deterministic: a MAVROS heartbeat that left PX4 just before the OFFBOARD switch (POSCTL, disarmed)
reaches simple_offboard after navigate(auto_arm) set nav_from_sp_flag_ (simple_offboard.cpp handleState clears the
flag on every State not in OFFBOARD). The fake publishes that heartbeat inside its set_mode handler, before the switch.
Then, after the arm settle, a second navigate: its reply says where the segment starts.
  r2f: "Navigating from current setpoint" (flag set again after offboardAndArm)
  control (--binary of r2e): the reply is NOT that (start from local_position_, the T34 finding)
  r2f without the injected heartbeat: "Navigating from current setpoint" (unchanged path)
Run (jazzy + ws_sitl + mavros bp02 + the install under test sourced, ROS_DOMAIN_ID set, ROS_LOCALHOST_ONLY=1):
  python3 test/test_r2f_flag_ros.py --binary INSTALL/lib/bumblebee/simple_offboard --expect r2f|r2e
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'src/bumblebee/test'))

FROM_SP = 'Navigating from current setpoint'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--binary', required=True)
    ap.add_argument('--expect', choices=['r2f', 'r2e'], required=True)
    ap.add_argument('--rounds', type=int, default=3)
    a = ap.parse_args()

    import rclpy
    from bumblebee import srv
    from std_srvs.srv import Trigger
    from fake_mavros import FakeMavros
    from test_safety import TEST_NS, topic, guard_graph
    from executor_support import CooperativeExecutor as MultiThreadedExecutor
    guard_graph()

    class RaceFake(FakeMavros):
        inject = False

        def _set_mode(self, request, response):
            if self.inject and request.custom_mode == 'OFFBOARD':
                self.publish_state(heartbeat=True)   # heartbeat sent before the switch: POSCTL, disarmed
                time.sleep(0.3)                      # let simple_offboard's handleState() take it
            return super()._set_mode(request, response)

    rclpy.init()
    fake = RaceFake(faithful=True)
    node = rclpy.create_node('r2f_flag_test')
    clients = {n: node.create_client(k, topic(n)) for n, k in
               [('navigate', srv.Navigate), ('release', Trigger)]}
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(fake)
    ex.add_node(node)
    threading.Thread(target=ex.spin, daemon=True).start()

    remaps = [('/tf', topic('/tf')), ('/tf_static', topic('/tf_static')),
              (topic('/mavros/local_position/pose'), topic('/mavros/mavros/pose')),
              (topic('/mavros/cmd/arming'), topic('/mavros/mavros/arming')),
              (topic('/mavros/setpoint_position/local'), topic('/mavros/mavros/local'))]
    args = [a.binary, '--ros-args', '-r', '__ns:=' + TEST_NS, '-r', '__node:=simple_offboard_tested',
            '-p', 'arming_timeout:=15.0', '-p', 'state_watchdog_timeout:=4.5']
    for s, d in remaps:
        args += ['-r', s + ':=' + d]
    log = tempfile.TemporaryFile(mode='w+')
    cpp = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)

    def until(pred, timeout, what):
        end = time.monotonic() + timeout
        while not pred():
            assert time.monotonic() < end, 'timeout: ' + what
            assert cpp.poll() is None, 'controller exited'
            time.sleep(.01)

    def call(name, req, timeout=25.):
        f = clients[name].call_async(req)
        until(f.done, timeout, name + ' reply')
        return f.result()

    def nav(auto_arm, x=0., z=1.):
        r = srv.Navigate.Request()
        r.x, r.y, r.z, r.yaw, r.speed = x, 0., z, math.nan, .4
        r.frame_id, r.auto_arm = 'map', auto_arm
        return call('navigate', r)

    rows = []
    try:
        for c in clients.values():
            assert c.wait_for_service(timeout_sec=20.)
        cases = [('race', True)] * a.rounds + [('plain', False)]
        for kind, inject in cases:
            call('release', Trigger.Request())
            fake.reset()
            time.sleep(1.2)
            RaceFake.inject = inject
            r1 = nav(True)
            RaceFake.inject = False
            assert r1.success, r1.message
            assert fake.snapshot('true_armed') and fake.snapshot('true_mode') == 'OFFBOARD'
            time.sleep(2.5)                      # past arm_settle_time (1.5 s): ground hold over
            r2 = nav(False, x=.3)
            assert r2.success, r2.message
            rows.append({'kind': kind, 'first': r1.message, 'second': r2.message,
                         'mode_requests': fake.snapshot('mode_requests')})
            # end of the round: release here, a fresh disarmed fake at the next start (as the package tests do)
    finally:
        cpp.terminate()
        try:
            cpp.wait(timeout=10.)
        except subprocess.TimeoutExpired:
            cpp.kill()
        ex.shutdown()
        rclpy.shutdown()
    for r in rows:
        assert r['mode_requests'][0] == 'OFFBOARD', r
    race = [r for r in rows if r['kind'] == 'race']
    plain = [r for r in rows if r['kind'] == 'plain']
    if a.expect == 'r2f':
        assert all(r['second'] == FROM_SP for r in race), race
    else:
        assert all(r['second'] != FROM_SP for r in race), race
    assert all(r['second'] == FROM_SP for r in plain), plain
    print('R2F_FLAG_ROS_PASS expect=%s %s' % (a.expect, json.dumps(rows)))


if __name__ == '__main__':
    main()
