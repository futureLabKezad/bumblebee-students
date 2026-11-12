"""r2d T25 with real ROS: real drone.py subprocess + real simple_offboard (r2d install) + the package's faithful fake
FCU (test/fake_mavros.py, Px4Model with dynamics). No MAVLink, no Gazebo, no drone; ROS domain 89, localhost only,
every name under a private /bb_test_* namespace (the package's own guard_graph() checks the graph is private).

Scenarios (each a fresh drone.py process):
  kill    takeoff 0.5 m, hover; SIGKILL the script -> simple_offboard switches to AUTO.LAND within 4.5 s (r2e), lands, disarms
  pilot   takeoff, hover; the pilot switches to POSCTL, then SIGKILL -> no AUTO.LAND request, mode stays POSCTL (5 s)
  normal  takeoff, hover 1 s, safe_land -> exit 0, exactly one AUTO.LAND request, no lease landing in the log
  sigint  enable_safe_interrupt, takeoff, hover; SIGINT -> safe_land lands, exit 0, no lease landing in the log
Run (launcher environment + r2d install sourced): python3 test/test_r2d_lease_ros.py
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PKG_TEST = ROOT / 'src/bumblebee/test'
SDK = ROOT / 'src/bumblebee/examples/drone.py'
sys.path.insert(0, str(PKG_TEST))

LEASE_LINE = 'Script lease silent'


def sdk_child():
    kind = sys.argv[sys.argv.index('--sdk-child') + 1]
    remaps = [a for a in sys.argv if ':=' in a]
    assert remaps and all(a.split(':=', 1)[1].startswith('/bb_test_') for a in remaps)
    from test_safety import guard_graph
    guard_graph()
    spec = importlib.util.spec_from_file_location('real_flight_sdk', SDK)
    drone = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(drone)
    if kind == 'sigint':
        drone.enable_safe_interrupt()
    try:
        ok = drone.takeoff(height=.5, vision_timeout=20.)
        print('TAKEOFF %s' % ok, flush=True)
        if kind == 'normal':
            drone.hover(1.0)
            print('LANDED %s' % drone.safe_land(timeout=20.), flush=True)
            return
        print('HOVERING', flush=True)
        drone.hover(60.0)
        if kind == 'sigint':
            print('LANDED %s' % drone.safe_land(timeout=20.), flush=True)
    finally:
        drone._shutdown()


def worker():
    import rclpy
    from ament_index_python.packages import get_package_prefix
    from fake_mavros import FakeMavros
    from test_safety import TEST_NS, topic, guard_graph
    from executor_support import CooperativeExecutor as MultiThreadedExecutor
    assert os.environ.get('ROS_DOMAIN_ID') == '89'
    guard_graph()
    rclpy.init()
    fake = FakeMavros(faithful=True)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(fake)
    spin = threading.Thread(target=executor.spin, daemon=True)
    spin.start()
    binary = str(Path(get_package_prefix('bumblebee')) / 'lib/bumblebee/simple_offboard')
    assert binary.startswith(str(ROOT / 'install')), binary
    cpp_remaps = [('/tf', topic('/tf')), ('/tf_static', topic('/tf_static')),
                  (topic('/mavros/local_position/pose'), topic('/mavros/mavros/pose')),
                  (topic('/mavros/cmd/arming'), topic('/mavros/mavros/arming')),
                  (topic('/mavros/setpoint_position/local'), topic('/mavros/mavros/local'))]
    args = [binary, '--ros-args', '-r', '__ns:=' + TEST_NS, '-r', '__node:=simple_offboard_tested']
    for src, dst in cpp_remaps:
        args += ['-r', src + ':=' + dst]
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
            time.sleep(.01)

    def start(kind):
        a = [sys.executable, __file__, '--sdk-child', kind, '--ros-args', '-r', '__ns:=' + TEST_NS]
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

    def auto_land_requests():
        return [r for r in fake.snapshot('mode_requests') if 'LAND' in str(r)]

    try:
        until(lambda: 'ready' in cpp_log(), 20., 'controller ready')
        for kind in ['kill', 'pilot', 'normal', 'sigint']:
            fake.reset(dynamics=True)
            time.sleep(1.2)
            log_mark = len(cpp_log())
            child, out = start(kind)
            if kind == 'normal':
                child.wait(timeout=60.)
                text = ''.join(out)
                assert child.returncode == 0 and 'LANDED True' in text, text
                assert not fake.snapshot('true_armed')
                lands = auto_land_requests()
                assert len(lands) == 1, lands
                assert LEASE_LINE not in cpp_log()[log_mark:], cpp_log()[log_mark:]
                time.sleep(4.)                      # after the exit: lease silent, disarmed -> nothing
                assert len(auto_land_requests()) == 1
                rows.append({'kind': kind, 'rc': child.returncode, 'auto_land_requests': len(lands)})
                child = None
                time.sleep(3.3)
                continue
            until(lambda: any('HOVERING' in l for l in out) or child.poll() is not None, 40., 'hover')
            assert child.poll() is None, ''.join(out)
            assert fake.snapshot('true_armed') and fake.snapshot('true_mode') == 'OFFBOARD'
            time.sleep(1.0)
            if kind == 'pilot':
                fake.set_state(mode='POSCTL')       # the pilot's RC switch
                time.sleep(0.5)
            n_land = len(auto_land_requests())
            t_sig = time.monotonic()
            os.kill(child.pid, signal.SIGINT if kind == 'sigint' else signal.SIGKILL)
            if kind == 'kill':
                until(lambda: fake.snapshot('true_mode') == 'AUTO.LAND', 6., 'AUTO.LAND after SIGKILL')
                t_land = time.monotonic() - t_sig
                assert t_land < 4.5, t_land   # r2e: + up to 1 s for a State after the lease went overdue
                until(lambda: not fake.snapshot('true_armed'), 30., 'disarm after the lease landing')
                t_disarm = time.monotonic() - t_sig
                assert LEASE_LINE in cpp_log()[log_mark:]
                rows.append({'kind': kind, 'kill_to_auto_land_s': round(t_land, 2),
                             'kill_to_disarm_s': round(t_disarm, 2)})
            elif kind == 'pilot':
                time.sleep(5.)
                assert len(auto_land_requests()) == n_land, auto_land_requests()
                assert fake.snapshot('true_mode') == 'POSCTL' and fake.snapshot('true_armed')
                assert LEASE_LINE not in cpp_log()[log_mark:]
                rows.append({'kind': kind, 'mode_after_5s': fake.snapshot('true_mode'), 'armed': True})
                fake.set_state(armed=False)         # test cleanup: the pilot lands and disarms
            else:
                child.wait(timeout=40.)
                text = ''.join(out)
                assert child.returncode == 0 and 'LANDED True' in text, text
                assert not fake.snapshot('true_armed')
                assert LEASE_LINE not in cpp_log()[log_mark:], cpp_log()[log_mark:]
                rows.append({'kind': kind, 'rc': child.returncode,
                             'auto_land_requests': len(auto_land_requests()) - n_land})
            if child.poll() is None:
                child.wait(timeout=10.)
            child = None
            time.sleep(3.3)
        print('R2D_LEASE_ROS_PASS ' + json.dumps(rows), flush=True)
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.wait(timeout=5.)
        if cpp.poll() is None:
            cpp.send_signal(signal.SIGINT)
            try:
                cpp.wait(timeout=10.)
            except subprocess.TimeoutExpired:
                cpp.kill()
                cpp.wait(timeout=5.)
        sys.stderr.write(cpp_log()[-6000:])
        log.close()
        executor.shutdown()
        spin.join(timeout=5.)
        fake.destroy_node()
        rclpy.shutdown()


def main():
    env = dict(os.environ, ROS_DOMAIN_ID='89', ROS_LOCALHOST_ONLY='1', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',
               FASTDDS_BUILTIN_TRANSPORTS='UDPv4', PYTHONDONTWRITEBYTECODE='1')
    r = subprocess.run([sys.executable, __file__, '--worker'], env=env, text=True, capture_output=True, timeout=400.)
    print(r.stdout[-4000:])
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
