#!/usr/bin/env python3
"""r2i (T46, no ROS): the difference r2h -> r2i is exactly the table EDITS of tools/make_r2i.py plus the declared new
files. Every edited file, with EDITS applied backwards, is r2h's file byte for byte; every other src file is r2h's;
drone.py, flight.py and camera_fix.py are r2h's bytes; flight_marker takes off to 0.9 m; the camera_fix manifest row
has no PENDING and names the file src holds; the manifest rows that changed are the declared ones.
Run: python3 -B test/test_r2i_changes.py -v   (from the r2i folder)
"""
import filecmp
import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R2H = Path('/work/fixed_image_r2h_20261110')
assert ROOT.name == 'fixed_image_r2i_20261111', ROOT
spec = importlib.util.spec_from_file_location('make_r2i', ROOT / 'tools/make_r2i.py')
MK = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MK)
S = 'src/bumblebee/'
P = 'drone/ros2_ws/src/bumblebee/'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def files(root):
    return {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts}


class Changes(unittest.TestCase):
    def test_r2h_is_the_accepted_one(self):
        self.assertEqual(sha(R2H / 'SHA256SUMS'), MK.R2H_SUMS)

    def test_edits_backwards_give_r2h_bytes(self):
        by_file = {}
        for rel, old, new, why in MK.EDITS:
            by_file.setdefault(rel, []).append((old, new))
        for rel, pairs in by_file.items():
            t = (ROOT / rel).read_text()
            for old, new in reversed(pairs):
                self.assertEqual(t.count(new), 1, (rel, new[:60]))
                t = t.replace(new, old)
            if rel == 'image_manifest_r2.tsv':
                continue                                  # other rows: test_manifest_rows
            self.assertEqual(t, (R2H / rel).read_text(), rel)

    def test_src_files_differ_only_as_declared(self):
        a, b = files(R2H / 'src'), files(ROOT / 'src')
        new = {k[len('src/'):] for k in MK.NEW_FILES if k.startswith('src/')} | \
              {'bumblebee/test/vpe_fix_h2_r2/ref/vpe_fix_r2h_66d806ba.py'}
        self.assertEqual(b - a, new)
        self.assertEqual(a - b, set())
        edited = {rel[len('src/'):] for rel, *_ in MK.EDITS if rel.startswith('src/')}
        diff = {f for f in a if not filecmp.cmp(R2H / 'src' / f, ROOT / 'src' / f, shallow=False)}
        self.assertEqual(diff, edited)

    def test_drone_py_flight_py_camera_fix_are_r2h(self):
        for f in ('examples/drone.py', 'examples/flight/flight.py', 'src/python/camera_fix.py'):
            self.assertEqual(sha(ROOT / S / f), sha(R2H / S / f), f)
        self.assertEqual(sha(ROOT / S / 'examples/drone.py'), MK.R2H_DRONE)
        self.assertEqual(sha(ROOT / S / 'src/python/camera_fix.py'), MK.CAMERA_FIX)
        self.assertIn('takeoff(height=0.8', (ROOT / S / 'examples/flight/flight.py').read_text())

    def test_flight_marker_one_line(self):
        a = (R2H / S / 'examples/flight/flight_marker.py').read_text().splitlines()
        b = (ROOT / S / 'examples/flight/flight_marker.py').read_text().splitlines()
        self.assertEqual(len(a), len(b))
        d = [(i + 1, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
        self.assertEqual(d, [(159, '    drone.takeoff(height=0.7, speed=0.4)', '    drone.takeoff(height=0.9, speed=0.4)')])

    def test_manifest_rows(self):
        def rows(p):
            return {r.split('\t')[0]: r.split('\t') for r in Path(p).read_text().split('\n') if r and not r.startswith('#')}
        a, b = rows(R2H / 'image_manifest_r2.tsv'), rows(ROOT / 'image_manifest_r2.tsv')
        cam = b[P + 'src/python/camera_fix.py']
        self.assertEqual(cam[1], MK.CAMERA_FIX)
        self.assertEqual(cam[2], MK.CAMERA_FIX)
        self.assertEqual(cam[2], sha(ROOT / S / 'src/python/camera_fix.py'))
        self.assertNotIn('PENDING', '\n'.join('\t'.join(r) for r in b.values()))
        changed = {k for k in a if k in b and a[k] != b[k]}
        expect = {P + 'src/python/camera_fix.py', P + 'src/python/vpe_fix.py', P + 'src/cpp/simple_offboard.cpp',
                  P + 'examples/flight/flight_marker.py', P + 'CMakeLists.txt', P + 'test/vpe_fix_h2_r2/README.md',
                  P + 'test/test_simple_offboard_px4model_launch.py'}
        self.assertEqual(changed, expect)
        self.assertEqual(set(b) - set(a), {P + 'src/cpp/state_link.h', P + 'test/vpe_fix_h2_r2/ref/vpe_fix_r2h_66d806ba.py',
                                           P + 'test/vpe_fix_h2_r2/tests_r4/test_pins_r4.py'})
        self.assertEqual(set(a) - set(b), set())
        for k in expect | (set(b) - set(a)):
            self.assertEqual(b[k][2], sha(ROOT / 'src' / k[len('drone/ros2_ws/src/'):]), k)


if __name__ == '__main__':
    unittest.main()
