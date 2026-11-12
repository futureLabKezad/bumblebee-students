#!/usr/bin/env python3
"""r2j (T53, no ROS): the difference r2i -> r2j is exactly the table EDITS of tools/make_r2j.py (camera translations of
the 20EC reference, ЭТАЛОН_РАЗМЕРОВ_20EC.md) and the declared test files. Checks: EDITS backwards give r2i's bytes; only
the three launch files and flight.py (0.9 m) differ in src; every static_transform_publisher of the down camera (the two «down» variants and
bumblebee.launch.py) and of the forward camera has the reference translation and r2i's angles; the other mounting
variants are untouched; drone.py, vpe_fix.py, simple_offboard.cpp and flight scripts are r2i's bytes;
DRONE_REST_Z_OFFSET is defined once and used nowhere in code; the manifest rows that changed are the three launch rows.
Run: python3 -B test/test_r2j_changes.py -v   (from the r2j folder)
"""
import ast
import filecmp
import hashlib
import importlib.util
import io
import re
import tokenize
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R2I = Path('/work/fixed_image_r2i_20261111')
assert ROOT.name == 'fixed_image_r2j_20261111', ROOT
spec = importlib.util.spec_from_file_location('make_r2j', ROOT / 'tools/make_r2j.py')
MK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MK)
S = 'src/bumblebee/'
P = 'drone/ros2_ws/src/bumblebee/'
DOWN = (0.081, 0.0, -0.034)      # reference: down camera lens from centre B (forward, left, up)
FWD = (0.113, 0.0, -0.002)       # reference: forward camera


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


def tf_args(path):
    """[(child_frame, [x, y, z, yaw, pitch, roll])] of every static_transform_publisher arguments list in a launch file"""
    out = []
    for n in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(n, ast.keyword) and n.arg == 'arguments' and isinstance(n.value, ast.List):
            v = [ast.literal_eval(e) for e in n.value.elts]
            if len(v) == 8 and v[6] == 'base_link':
                out.append((v[7], [float(x) for x in v[:6]]))
    return out


class Changes(unittest.TestCase):
    def test_r2i_is_the_reviewed_one(self):
        self.assertEqual(sha(R2I / 'SHA256SUMS'), MK.R2I_SUMS)

    def test_edits_backwards_give_r2i_bytes(self):
        by_file = {}
        for rel, old, new, why in MK.EDITS:
            by_file.setdefault(rel, []).append((old, new))
        for rel, pairs in by_file.items():
            t = (ROOT / rel).read_text()
            for old, new in reversed(pairs):
                self.assertEqual(t.count(new), 1, (rel, new[:60]))
                t = t.replace(new, old)
            self.assertEqual(t, (R2I / rel).read_text(), rel)

    def test_src_differs_only_in_the_launch_files(self):
        a, b = files(R2I / 'src'), files(ROOT / 'src')
        self.assertEqual(a, b)
        diff = {f for f in a if not filecmp.cmp(R2I / 'src' / f, ROOT / 'src' / f, shallow=False)}
        self.assertEqual(diff, {'bumblebee/launch/bumblebee.launch.py', 'bumblebee/launch/main_camera.launch.py',
                                'bumblebee/launch/second_camera.launch.py', 'bumblebee/examples/flight/flight.py'})

    def test_flight_py_two_lines(self):
        a = (R2I / S / 'examples/flight/flight.py').read_text().splitlines()
        b = (ROOT / S / 'examples/flight/flight.py').read_text().splitlines()
        self.assertEqual(len(a), len(b))
        d = [(x, y) for x, y in zip(a, b) if x != y]
        self.assertEqual(d, [('flight.py -- single- or multi-marker ArUco preflight, takeoff to 0.8m, hover, land.',
                              'flight.py -- single- or multi-marker ArUco preflight, takeoff to 0.9m, hover, land.'),
                             ('    drone.takeoff(height=0.8, speed=0.4)', '    drone.takeoff(height=0.9, speed=0.4)')])

    def test_reference_translations_and_unchanged_angles(self):
        for f in ('bumblebee.launch.py', 'main_camera.launch.py', 'second_camera.launch.py'):
            new, old = tf_args(ROOT / S / 'launch' / f), tf_args(R2I / S / 'launch' / f)
            self.assertEqual(len(new), len(old), f)
            for (cn, vn), (co, vo) in zip(new, old):
                self.assertEqual(cn, co, f)
                self.assertEqual(vn[3:], vo[3:], f)                       # angles untouched
                if cn == 'main_camera_optical' and vo[:3] == [0.05, 0.0, -0.07]:
                    self.assertEqual(tuple(vn[:3]), DOWN, f)            # the down camera
                elif cn == 'second_camera_optical':
                    self.assertEqual(tuple(vn[:3]), FWD, f)
                else:
                    self.assertEqual(vn, vo, f)                         # up / forward / backward variants: unchanged
        mc = [v for c, v in tf_args(ROOT / S / 'launch/main_camera.launch.py') if tuple(v[:3]) == DOWN]
        self.assertEqual(len(mc), 2)                                     # both «down» variants
        bl = dict(tf_args(ROOT / S / 'launch/bumblebee.launch.py'))
        self.assertEqual(tuple(bl['main_camera_optical'][:3]), DOWN)
        self.assertEqual(tuple(bl['second_camera_optical'][:3]), FWD)

    def test_flight_code_is_r2i(self):
        for f in ('examples/drone.py', 'src/python/vpe_fix.py', 'src/cpp/simple_offboard.cpp', 'src/cpp/state_link.h',
                  'examples/flight/flight_marker.py', 'src/python/aruco_detect.py',
                  'src/python/camera_fix.py', 'examples/flight_profile.py'):
            self.assertEqual(sha(ROOT / S / f), sha(R2I / S / f), f)

    def test_drone_rest_z_offset_is_defined_and_unused(self):
        """T53 item 3: DRONE_REST_Z_OFFSET (0.32) is assigned once; no code reads it (comments only)"""
        names = []
        for root in (ROOT / S / 'examples', ROOT / S / 'src', ROOT / S / 'scripts'):
            for p in root.rglob('*.py'):
                toks = tokenize.generate_tokens(io.StringIO(p.read_text(errors='replace')).readline)
                names += [(str(p.relative_to(ROOT)), t.start[0]) for t in toks
                          if t.type == tokenize.NAME and t.string == 'DRONE_REST_Z_OFFSET']
        self.assertEqual(names, [(S + 'examples/drone.py', 652)])
        self.assertIn('DRONE_REST_Z_OFFSET = 0.32', (ROOT / S / 'examples/drone.py').read_text())

    def test_manifest_rows(self):
        def rows(p):
            return {r.split('\t')[0]: r.split('\t') for r in Path(p).read_text().split('\n') if r and not r.startswith('#')}
        a, b = rows(R2I / 'image_manifest_r2.tsv'), rows(ROOT / 'image_manifest_r2.tsv')
        self.assertEqual(set(a), set(b))
        changed = {k for k in a if a[k] != b[k]}
        launch = {P + 'launch/bumblebee.launch.py', P + 'launch/main_camera.launch.py', P + 'launch/second_camera.launch.py',
                  P + 'examples/flight/flight.py'}
        self.assertEqual(changed, launch)
        for k in launch:
            self.assertEqual(b[k][2], sha(ROOT / 'src' / k[len('drone/ros2_ws/src/'):]), k)
        self.assertNotIn('PENDING', '\n'.join('\t'.join(r) for r in b.values()))


if __name__ == '__main__':
    unittest.main()
