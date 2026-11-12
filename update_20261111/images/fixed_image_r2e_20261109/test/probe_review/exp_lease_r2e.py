"""Independent review probes for r2d T25 (script lease). Real drone.py (r2d, read-only) + a real simple_offboard
binary + the package's faithful fake FCU (fake_mavros, faithful=True). No MAVLink, no Gazebo, no drone.
ROS domain 94, localhost only, private /bb_test_* namespace (guard_graph checks the graph).

Usage (environment sourced as in the review brief):
  python3 exp_lease.py --binary <simple_offboard> [--lease-timeout S] --scenarios kill_at_offboard,stall:2.3,cpu
Scenarios:
  kill_at_offboard  SIGKILL the script the moment simple_offboard asks for OFFBOARD (inside navigate(auto_arm));
                    report whether the vehicle is landed by the watchdog or keeps hovering.
  kill_at_arm       same, at the first ARM request.
  stall:D           script alive and hovering; SIGSTOP simple_offboard for D s, SIGCONT; report mode requests.
  cpu               script alive and hovering; CPU of simple_offboard over 3.5 s idle vs 3.5 s while a /land is
                    blocked (fake set_mode reply delayed 4 s).
"""
import importlib.util
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

R2D = Path('/work/fixed_image_r2e_20261109')
PKG_TEST = R2D / 'src/bumblebee/test'
SDK = R2D / 'src/bumblebee/examples/drone.py'
sys.path.insert(0, str(PKG_TEST))
DOMAIN = '94'


def sdk_child():
    remaps = [a for a in sys.argv if ':=' in a]
    assert remaps and all(a.split(':=', 1)[1].startswith('/bb_test_') for a in remaps)
    from test_safety import guard_graph
    guard_graph()
    spec = importlib.util.spec_from_file_location('real_flight_sdk', SDK)
    drone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drone)
    try:
        ok = drone.takeoff(height=.5, vision_timeout=20.)
        print('TAKEOFF %s' % ok, flush=True)
        print('HOVERING', flush=True)
        drone.hover(60.0)
        print('HOVER_RETURNED', flush=True)
    finally:
        drone._shutdown()


def cpu_ticks(pid):
    with open('/proc/%d/stat' % pid) as f:
        parts = f.read().rsplit(')', 1)[1].split()
    return int(parts[11]) + int(parts[12])  # utime + stime (fields 14, 15)


def worker():
    import rclpy
    from std_srvs.srv import Trigger
    from fake_mavros import FakeMavros
    from test_safety import TEST_NS, topic, guard_graph
    from executor_support import CooperativeExecutor as MultiThreadedExecutor
    assert os.environ.get('ROS_DOMAIN_ID') == DOMAIN
    binary = sys.argv[sys.argv.index('--binary') + 1]
    scenarios = sys.argv[sys.argv.index('--scenarios') + 1].split(',')
    lease_timeout = None
    if '--lease-timeout' in sys.argv:
        lease_timeout = sys.argv[sys.argv.index('--lease-timeout') + 1]
    guard_graph()
    rclpy.init()
    fake = FakeMavros(faithful=True)
    land_cli = fake.create_client(Trigger, topic('/land'))
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(fake)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()
    cpp_remaps = [('/tf', topic('/tf')), ('/tf_static', topic('/tf_static')),
                  (topic('/mavros/local_position/pose'), topic('/mavros/mavros/pose')),
                  (topic('/mavros/cmd/arming'), topic('/mavros/mavros/arming')),
                  (topic('/mavros/setpoint_position/local'), topic('/mavros/mavros/local'))]
    args = [binary, '--ros-args', '-r', '__ns:=' + TEST_NS, '-r', '__node:=simple_offboard_tested']
    for src, dst in cpp_remaps:
        args += ['-r', src + ':=' + dst]
    if lease_timeout is not None:
        args += ['-p', 'script_lease_timeout:=' + lease_timeout]
    log = tempfile.TemporaryFile(mode='w+')
    cpp = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    child = None
    rows = []

    def cpp_log():
        log.seek(0)
        text = log.read()
        log.seek(0, 2)
        return text

    def until(pred, timeout, what):
        end = time.monotonic() + timeout
        while not pred():
            assert time.monotonic() < end, 'timeout: ' + what
            assert cpp.poll() is None, 'controller exited unexpectedly'
            time.sleep(.002)

    def start():
        a = [sys.executable, __file__, '--sdk-child', '--ros-args', '-r', '__ns:=' + TEST_NS]
        names = ['/get_telemetry', '/navigate', '/land', '/mavros/mavros/arming', '/mavros/set_mode',
                 '/vpe_fix/set_param', '/mavros/mavros/pull', '/aruco_detect/markers_used',
                 '/aruco_detect/yaw_locked', '/aruco_detect/wake', '/mavros/state', '/mavros/battery',
                 '/tf', '/tf_static', '/clock']
        for n in names:
            a += ['-r', n + ':=' + topic(n)]
        a += ['-r', '/simple_offboard/script_lease:=' + topic('/simple_offboard_tested/script_lease')]
        lines = []
        p = subprocess.Popen(a, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        threading.Thread(target=lambda: [lines.append(l) for l in p.stdout], daemon=True).start()
        return p, lines

    def mode_reqs():
        return fake.snapshot('mode_requests')

    def stop_child():
        nonlocal child
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=5.)
        child = None

    def hover_up(out):
        until(lambda: any('HOVERING' in l for l in out) or child.poll() is not None, 40., 'hover')
        assert child.poll() is None, ''.join(out)
        assert fake.snapshot('true_armed') and fake.snapshot('true_mode') == 'OFFBOARD'

    try:
        until(lambda: 'ready' in cpp_log(), 20., 'controller ready')
        for sc in scenarios:
            fake.reset(dynamics=True)
            time.sleep(4.0)   # past arm_hold_after_land of a previous scenario
            mark = len(cpp_log())
            if sc.endswith('_late'):
                fake.set_state(arming='late', arm_delay=2.0)   # ARM executed at once, reported 2 s later
            child, out = start()
            row = {'scenario': sc}
            if sc.startswith('kill_at_'):
                if sc.startswith('kill_at_offboard'):
                    until(lambda: 'OFFBOARD' in mode_reqs(), 40., 'OFFBOARD request')
                else:
                    until(lambda: True in fake.snapshot('arming_requests'), 40., 'ARM request')
                os.kill(child.pid, signal.SIGKILL)
                t_kill = time.monotonic()
                child.wait(timeout=5.)
                n0 = len(mode_reqs())
                samples = []
                end = t_kill + 15.
                while time.monotonic() < end:
                    samples.append((round(time.monotonic() - t_kill, 2), fake.snapshot('true_mode'),
                                    fake.snapshot('true_armed'), round(fake.snapshot('pose')[2], 2)))
                    time.sleep(.5)
                lands = [r for r in mode_reqs()[n0:] if 'LAND' in r]
                row.update({'auto_land_requests_after_kill': len(lands),
                            'lease_line': 'Script lease silent' in cpp_log()[mark:],
                            'at_15s': samples[-1], 'first_armed_offboard_s': next(
                                (s[0] for s in samples if s[1] == 'OFFBOARD' and s[2]), None)})
                child = None
            elif sc.startswith('stall'):
                d = float(sc.split(':')[1])
                hover_up(out)
                time.sleep(1.0 + (hash(sc) % 7) / 10.)  # vary the phase vs the 1 Hz heartbeat
                n0 = len(mode_reqs())
                os.kill(cpp.pid, signal.SIGSTOP)
                time.sleep(d)
                os.kill(cpp.pid, signal.SIGCONT)
                t_cont = time.monotonic()
                modes = []
                while time.monotonic() < t_cont + 6.:
                    m = fake.snapshot('true_mode')
                    if not modes or modes[-1][1] != m:
                        modes.append((round(time.monotonic() - t_cont, 2), m))
                    time.sleep(.01)
                reqs = mode_reqs()[n0:]
                text = cpp_log()[mark:]
                row.update({'stall_s': d, 'mode_requests_after': reqs, 'true_mode_trace': modes,
                            'lease_line': 'Script lease silent' in text,
                            'lease_lines': [l for l in text.splitlines() if 'lease' in l.lower()][:4]})
                stop_child()
            elif sc == 'cpu':
                hover_up(out)
                time.sleep(1.0)
                hz = os.sysconf('SC_CLK_TCK')
                c0 = cpu_ticks(cpp.pid); t0 = time.monotonic()
                time.sleep(3.5)
                idle = (cpu_ticks(cpp.pid) - c0) / hz / (time.monotonic() - t0)
                fake.set_state(mode_reply_delay=4.0)
                assert land_cli.wait_for_service(timeout_sec=5.)
                fut = land_cli.call_async(Trigger.Request())
                time.sleep(0.3)
                c0 = cpu_ticks(cpp.pid); t0 = time.monotonic()
                time.sleep(3.3)
                busy = (cpu_ticks(cpp.pid) - c0) / hz / (time.monotonic() - t0)
                end = time.monotonic() + 15.
                while not fut.done() and time.monotonic() < end:
                    time.sleep(.05)
                fake.set_state(mode_reply_delay=0.0)
                row.update({'cpu_idle_cores': round(idle, 3), 'cpu_while_land_blocked_cores': round(busy, 3),
                            'land_reply': (fut.result().success, fut.result().message) if fut.done() else None})
                stop_child()
            rows.append(row)
            print('ROW ' + json.dumps(row), flush=True)
            fake.reset(dynamics=True)
            time.sleep(1.0)
        print('EXP_DONE ' + json.dumps(rows), flush=True)
    finally:
        stop_child()
        if cpp.poll() is None:
            try:
                os.kill(cpp.pid, signal.SIGCONT)
            except Exception:
                pass
            cpp.send_signal(signal.SIGINT)
            try:
                cpp.wait(timeout=10.)
            except subprocess.TimeoutExpired:
                cpp.kill()
                cpp.wait(timeout=5.)
        sys.stderr.write(cpp_log()[-5000:])
        log.close()
        executor.shutdown()
        spin.join(timeout=5.)
        fake.destroy_node()
        rclpy.shutdown()


def main():
    env = dict(os.environ, ROS_DOMAIN_ID=DOMAIN, ROS_LOCALHOST_ONLY='1', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               FASTDDS_BUILTIN_TRANSPORTS='UDPv4', PYTHONDONTWRITEBYTECODE='1')
    r = subprocess.run([sys.executable, __file__, '--worker'] + sys.argv[1:], env=env, text=True,
                       capture_output=True, timeout=900.)
    print(r.stdout[-8000:])
    if r.returncode != 0:
        print(r.stderr[-8000:])
    sys.exit(r.returncode)


if __name__ == '__main__':
    if '--sdk-child' in sys.argv:
        sdk_child()
    elif '--worker' in sys.argv:
        worker()
    else:
        main()
