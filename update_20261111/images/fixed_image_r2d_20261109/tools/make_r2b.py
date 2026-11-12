#!/usr/bin/env python3
"""make_r2b.py - r2 revision b: keep the marker detector awake for the whole preflight (Claude, 09.11.2026).

Found by chat «New chat» (by code): in r2 the wake was sent only inside check_aruco(), and the detector sleeps 5 s
after the last wake, so by wait_yaw_lock / wait_position_stable / require_vpe_link / takeoff's vision wait it could be
asleep again -> PREFLIGHT FAIL. Fix: a background daemon thread publishes /aruco_detect/wake every 2 s from the first
preflight call until the FCU is armed (the detector's own gate takes over), the script shuts down, or 180 s pass
without a new preflight call. Edits examples/drone.py of r2 in place (its sha must be r2.0's); examples unchanged.
Usage: python3 -I make_r2b.py R2_DIR
"""
import hashlib
import os
import sys

R20_SHA = 'ed6a4eca008ffaac'


def once(t, old, new, what):
    if t.count(old) != 1:
        sys.exit('STOP: %s: %d matches' % (what, t.count(old)))
    return t.replace(old, new)


WAKE_CODE = '''
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


'''


def main():
    r2 = sys.argv[1]
    p = os.path.join(r2, 'src/bumblebee/examples/drone.py')
    b = open(p, 'rb').read()
    if not hashlib.sha256(b).hexdigest().startswith(R20_SHA):
        sys.exit('STOP: drone.py is not r2.0')
    t = b.decode('utf-8')
    # 1. check_aruco: drop the per-loop wake, start the background wake instead
    t = once(t, "    # F1 (09.11.2026): the image's detector sleeps until the FCU is armed or in\n"
                "    # OFFBOARD (gate_by_flight_state, saves Pi CPU). Keep it awake during this\n"
                "    # preflight check: each message holds detection on for a few seconds.\n"
                "    wake_pub = _node.create_publisher(Bool, '/aruco_detect/wake', 10)\n"
                "    wake = Bool()\n    wake.data = True\n",
             "    _keep_detector_awake()   # F1: detector awake from here until arming\n", 'check_aruco wake')
    t = once(t, "            wake_pub.publish(wake)\n", "", 'check_aruco publish')
    t = once(t, "        _node.destroy_publisher(wake_pub)\n", "", 'check_aruco destroy')
    # 2. the other preflight steps and takeoff also (re)start it
    for fn in ('wait_yaw_lock', 'require_vpe_link', 'wait_position_stable', 'takeoff'):
        i = t.index('\ndef %s(' % fn)
        j = t.index('\n    _init()\n', i)
        k = j + len('\n    _init()\n')
        t = t[:k] + '    _keep_detector_awake()   # F1: keep the detector awake until arming\n' + t[k:]
    # 3. the wake code, before check_aruco
    t = once(t, '\ndef check_aruco(timeout=10, min_markers=1):\n',
             WAKE_CODE.rstrip('\n') + '\n\n\ndef check_aruco(timeout=10, min_markers=1):\n', 'wake code')
    # 4. shutdown stops it first
    t = once(t, "    global _initialized, _executor, _node\n    if not _initialized:\n        return\n"
                "    _initialized = False\n",
             "    global _initialized, _executor, _node\n    if not _initialized:\n        return\n"
             "    _initialized = False\n    _stop_detector_wake()   # F1: no wakes after the script ends\n",
             'shutdown')
    # 5. review T15, must-fix 3: a short or bad map line -> RuntimeError (was IndexError/ValueError)
    t = once(t, "    rows = {}\n    for line in lines:\n        p = line.split()\n"
                "        if not p or p[0].startswith('#'):\n            continue\n"
                "        rows[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]), float(p[5]) if len(p) > 5 else 1.571)\n"
                "    return rows\n",
             "    rows = {}\n    for n, line in enumerate(lines, 1):\n        p = line.split()\n"
             "        if not p or p[0].startswith('#'):\n            continue\n"
             "        try:\n"
             "            if len(p) < 4:\n"
             "                raise ValueError('%d columns, need at least 4: id length x y' % len(p))\n"
             "            i = int(p[0])\n"
             "            if i in rows:\n"
             "                raise ValueError('id %d twice' % i)\n"
             "            rows[i] = (float(p[1]), float(p[2]), float(p[3]), float(p[5]) if len(p) > 5 else 1.571)\n"
             "        except ValueError as e:\n"
             "            raise RuntimeError('set_aruco_map: bad line %d in map %s: %r (%s)' % (n, path, line, e))\n"
             "    if not rows:\n"
             "        raise RuntimeError('set_aruco_map: no markers in map %s' % path)\n"
             "    return rows\n", 'map rows')
    open(p, 'w', encoding='utf-8').write(t)
    print('drone.py r2.0 %s -> r2b %s' % (hashlib.sha256(b).hexdigest()[:16],
                                         hashlib.sha256(t.encode()).hexdigest()[:16]))


if __name__ == '__main__':
    main()
