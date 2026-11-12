"""r2c (F5): navigate() puts only Python floats into the float32 fields of the Navigate request.

Part 1, no ROS: a strict stand-in Request rejects a non-float like the rosidl C converter's assert(PyFloat_Check).
  int, numpy int/float32/float64, nan, inf, bool in each of x, y, z, yaw, speed -> the request holds a float.
Part 2, real rosidl (skipped without a sourced ROS + bumblebee install): each case runs in its own python process,
  navigate() builds the real srv.Navigate request and call_async() serializes it through the C converter
  (no server, ROS_DOMAIN_ID 77, discovery OFF). r2c: every case exits 0. Control: r2b drone.py with int -> abort.
Run: python3 -m unittest discover -s test -p 'test_r2c_navigate_float.py'   (from fixed_image_r2c_20261109)
"""
import importlib.util
import math
import os
import subprocess
import sys
import textwrap
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DRONE_PY = os.path.join(ROOT, 'src', 'bumblebee', 'examples', 'drone.py')
R2B_DRONE_PY = os.path.join(ROOT, 'notes', 'prev_r2b', 'drone.py')
FIELDS = ('x', 'y', 'z', 'yaw', 'speed')
BASE = dict(x=0.5, y=1.4, z=0.8, yaw=float('nan'), speed=0.1, frame_id='map', auto_arm=False)

try:
    import numpy
except ImportError:
    numpy = None


def cases():
    c = [('int0', 0), ('int7', 7), ('neg_int', -2), ('nan', float('nan')), ('inf', float('inf')), ('bool', True)]
    if numpy is not None:
        c += [('np_int64', numpy.int64(3)), ('np_float32', numpy.float32(0.5)), ('np_float64', numpy.float64(0.5))]
    return c


class StrictRequest:
    """Like the C converter: a float32/bool/string field must already have the right Python type."""
    def __setattr__(self, k, v):
        if k in FIELDS:
            assert isinstance(v, float), 'PyFloat_Check(%s=%r)' % (k, v)
        object.__setattr__(self, k, v)


def load(path):
    spec = importlib.util.spec_from_file_location('drone_r2c_under_test', path)
    d = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d)
    d._initialized = True
    d.srv = types.SimpleNamespace(Navigate=types.SimpleNamespace(Request=StrictRequest))
    d._fcu_mode_state = lambda wait=0.0: (True, True, 'OFFBOARD')
    d.sent = []
    d._call = lambda client, req, timeout=5.0, wait=None: (d.sent.append(req), types.SimpleNamespace(success=True))[1]
    return d


class NavigateFloatTest(unittest.TestCase):

    def setUp(self):
        self.d = load(DRONE_PY)

    def test_stand_in_rejects_int_like_c(self):
        with self.assertRaises(AssertionError):
            setattr(StrictRequest(), 'x', 0)

    def test_every_float_field_every_value(self):
        for field in FIELDS:
            for name, val in cases():
                with self.subTest(field=field, value=name):
                    self.d.sent.clear()
                    kw = dict(BASE)
                    kw[field] = val
                    self.assertTrue(self.d.navigate(**kw).success)
                    got = getattr(self.d.sent[0], field)
                    self.assertIs(type(got), float)
                    want = float(val)
                    self.assertTrue(math.isnan(got) if math.isnan(want) else got == want)

    def test_other_fields_untouched(self):
        self.d.navigate(**BASE)
        req = self.d.sent[0]
        self.assertEqual(req.frame_id, 'map')
        self.assertIs(req.auto_arm, False)

    def test_examples_calls(self):
        # the calls that crashed in Gazebo (F5): fly_to(x=0, y=1.4, z=0.8) and safe_land's approach (x=0, y=0)
        self.d.navigate(x=0, y=1.4, z=0.8, speed=0.10, frame_id='map', auto_arm=False)
        self.d.navigate(x=0, y=0, z=0.8, speed=0.1, frame_id='map', auto_arm=False)
        for req in self.d.sent:
            for f in ('x', 'y', 'z', 'speed'):
                self.assertIs(type(getattr(req, f)), float)


CHILD = textwrap.dedent('''
    import importlib.util, sys, types
    path, field, kind = sys.argv[1], sys.argv[2], sys.argv[3]
    import numpy
    val = {'int0': 0, 'int7': 7, 'nan': float('nan'), 'bool': True, 'np_int64': numpy.int64(3),
           'np_float32': numpy.float32(0.5), 'np_float64': numpy.float64(0.5), 'float': 0.5}[kind]
    spec = importlib.util.spec_from_file_location('drone_child', path)
    d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
    d._ros2_import()
    import rclpy
    rclpy.init()
    node = rclpy.create_node('r2c_navigate_float_test')
    d._node = node
    d._navigate_client = node.create_client(d.srv.Navigate, '/r2c_test_navigate_no_server')
    d._initialized = True
    d._fcu_mode_state = lambda wait=0.0: (True, True, 'OFFBOARD')
    d._call = lambda client, req, timeout=5.0, wait=None: (client.call_async(req), types.SimpleNamespace(success=True))[1]
    kw = dict(x=0.5, y=1.4, z=0.8, yaw=float('nan'), speed=0.1, frame_id='map', auto_arm=False)
    kw[field] = val
    d.navigate(**kw)
    print('SERIALIZED_OK', flush=True)
    import os; os._exit(0)
''')


def ros_ready():
    try:
        importlib.util.find_spec('rclpy')
        from bumblebee import srv  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


@unittest.skipUnless(ros_ready(), 'needs sourced ROS jazzy + bumblebee install + numpy')
class RealRosidlTest(unittest.TestCase):

    def run_child(self, path, field, kind):
        env = dict(os.environ, ROS_DOMAIN_ID='77', ROS_AUTOMATIC_DISCOVERY_RANGE='OFF', PYTHONDONTWRITEBYTECODE='1')
        p = subprocess.run([sys.executable, '-c', CHILD, path, field, kind], env=env, timeout=60,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                           preexec_fn=lambda: __import__('resource').setrlimit(
                               __import__('resource').RLIMIT_CORE, (0, 0)))
        return p.returncode, p.stdout + p.stderr

    def test_r2c_every_field_serializes(self):
        for field in FIELDS:
            for kind in ('int0', 'int7', 'nan', 'bool', 'np_int64', 'np_float32', 'np_float64'):
                with self.subTest(field=field, kind=kind):
                    rc, out = self.run_child(DRONE_PY, field, kind)
                    self.assertEqual(rc, 0, out[-400:])
                    self.assertIn('SERIALIZED_OK', out)

    @unittest.skipUnless(os.path.exists(R2B_DRONE_PY), 'no notes/prev_r2b/drone.py')
    def test_control_r2b_int_aborts(self):
        rc, out = self.run_child(R2B_DRONE_PY, 'x', 'int0')
        self.assertEqual(rc, -6, out[-400:])   # SIGABRT
        self.assertIn('PyFloat_Check', out)
        rc, out = self.run_child(R2B_DRONE_PY, 'x', 'float')
        self.assertEqual(rc, 0, out[-400:])


if __name__ == '__main__':
    unittest.main()
