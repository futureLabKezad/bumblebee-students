#!/usr/bin/env python3
"""make_r2c.py - r2 revision c: navigate() always sends Python floats (F5) (Claude, 09.11.2026).

F5 (Gazebo, 3 runs on r2b, /work/goal_step5b_20261109/CHANGELOG_5B.md): flight_marker.py at fly_to(x=0, ...) and
flight_marker_loop.py at safe_land(x=0, y=0) abort python with
  _navigate_s.c:61: bumblebee__srv__navigate__request__convert_from_py: Assertion `PyFloat_Check(field)' failed.
Cause (proven, notes/F5_REPRO.txt): the examples pass the int 0 into float32 fields of the Navigate request.
Jazzy's Python field checks are off by default (ROS_PYTHON_CHECK_FIELDS unset), so the int reaches the C converter,
whose assert kills the process; the drone stays in OFFBOARD without a script. numpy.float32 does the same.
Fix: navigate() converts x, y, z, yaw, speed with float() before setattr (nan stays nan). Only examples/drone.py.
Usage: python3 -I make_r2c.py R2C_DIR   (drone.py there must be r2b's)
"""
import hashlib
import os
import sys

R2B_SHA = 'd5afa9a90131374a'

OLD = '''def navigate(**kwargs):
    global _arm_ref_z, _auto_arm_ok_t
    _init()
    req = srv.Navigate.Request()
    for k, v in kwargs.items():
        setattr(req, k, v)
'''

NEW = '''# F5 (09.11.2026, r2c): float32 fields of the Navigate request. Each must hold
# a Python float: an int (fly_to(x=0)) or a numpy.float32 passes the Python
# setter (ROS_PYTHON_CHECK_FIELDS is off by default) and then aborts the whole
# process in the rosidl C converter (assert PyFloat_Check, core dump), leaving
# the drone in OFFBOARD without a script. float() keeps nan as nan.
_NAVIGATE_FLOAT_FIELDS = ('x', 'y', 'z', 'yaw', 'speed')


def navigate(**kwargs):
    global _arm_ref_z, _auto_arm_ok_t
    _init()
    req = srv.Navigate.Request()
    for k, v in kwargs.items():
        if k in _NAVIGATE_FLOAT_FIELDS:
            v = float(v)
        setattr(req, k, v)
'''


def main():
    path = os.path.join(sys.argv[1], 'src', 'bumblebee', 'examples', 'drone.py')
    data = open(path, 'rb').read()
    sha = hashlib.sha256(data).hexdigest()
    if not sha.startswith(R2B_SHA):
        sys.exit('STOP: drone.py is not r2b (%s)' % sha[:16])
    t = data.decode('utf-8')
    if t.count(OLD) != 1:
        sys.exit('STOP: navigate() anchor: %d matches' % t.count(OLD))
    t = t.replace(OLD, NEW)
    open(path, 'wb').write(t.encode('utf-8'))
    print('r2c drone.py', hashlib.sha256(t.encode('utf-8')).hexdigest())


if __name__ == '__main__':
    main()
