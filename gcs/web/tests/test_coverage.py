"""Tests for bbflight.coverage (step 2)."""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bbflight import bbmap, coverage  # noqa: E402
from bbflight.fakedrone import start_heading  # noqa: E402

with open(os.path.join(os.path.dirname(HERE), 'testdata', 'map_final.txt'), encoding='utf-8') as f:
    MP = bbmap.from_map_txt(f.read(), name='field_real')
CRUISE = 0.75              # true map z over the markers in the Gazebo C7 runs: 0.71-0.85 (calib_gazebo.json v2)
YAW = start_heading(MP)    # rot_z(marker 0) - pi/2 = Gazebo spawn, -1.5 deg


def one(mid, length=0.29, x=0.0, y=0.0, rot=0.0):
    return {'format': bbmap.FORMAT, 'name': 't', 'z': -0.32,
            'markers': [{'id': mid, 'length': length, 'x': x, 'y': y, 'rot_z': rot}]}


class Geometry(unittest.TestCase):
    def test_point_under_camera_projects_to_image_centre(self):
        cam = coverage.camera('gazebo')
        ox, oy = coverage.camera_xy(1.0, 2.0, 0.3, cam)
        u, v = coverage.project(ox, oy, 1.0, 2.0, 0.8, 0.3, cam, -0.32)
        self.assertAlmostEqual(u, cam['cx'], places=6)
        self.assertAlmostEqual(v, cam['cy'], places=6)

    def test_forward_is_image_up_right_is_image_right(self):
        cam = coverage.camera('gazebo')
        ox, oy = coverage.camera_xy(0, 0, 0.0, cam)      # yaw 0: forward = +x map, left = +y map
        u, v = coverage.project(ox + 0.2, oy, 0, 0, 0.8, 0.0, cam, -0.32)
        self.assertLess(v, cam['cy'])                      # forward -> up in the image
        u2, _ = coverage.project(ox, oy - 0.2, 0, 0, 0.8, 0.0, cam, -0.32)
        self.assertGreater(u2, cam['cx'])                  # body right (-y) -> image right

    def test_marker_under_drone_visible_in_flight_not_on_ground_contact(self):
        cam = coverage.camera('gazebo')
        mp = one(0)
        self.assertEqual(coverage.visible_ids(mp, -0.081, 0, 0.8, 0.0, cam), [0])
        self.assertEqual(coverage.visible_ids(mp, -0.081, 0, -0.32 + 0.034 + 0.01, 0.0, cam), [])

    def test_far_marker_not_visible(self):
        cam = coverage.camera('gazebo')
        self.assertEqual(coverage.visible_ids(one(0, x=3.0), 0, 0, 0.8, 0.0, cam), [])

    def test_max_tan_limits_reach(self):
        full = coverage.camera('gazebo', max_tan=None)
        lim = coverage.camera('gazebo')
        mp = one(0, x=0.081, y=-1.0)                       # 1.0 m to the right (yaw 0) at h ~1.09 m: far corner tan ~1.05 (frame 1.14, cone 0.95)
        self.assertEqual(coverage.visible_ids(mp, 0, 0, 0.8, 0.0, full), [0])
        self.assertEqual(coverage.visible_ids(mp, 0, 0, 0.8, 0.0, lim), [])

    def test_backward_sees_less_than_forward(self):
        # K: forward (image up) tan 0.97, backward (image down) tan 0.55
        cam = coverage.camera('gazebo', max_tan=None)
        ahead, behind = one(0, x=0.081 + 0.80), one(0, x=0.081 - 0.80)
        self.assertEqual(coverage.visible_ids(ahead, 0, 0, 0.8, 0.0, cam), [0])
        self.assertEqual(coverage.visible_ids(behind, 0, 0, 0.8, 0.0, cam), [])

    def test_footprint_corners_match_projection(self):
        cam = coverage.camera('gazebo')
        fp = coverage.footprint(0.3, -0.2, 0.8, 0.7, cam, -0.32)
        self.assertEqual(len(fp), 4)
        for px, py in fp:          # every corner projects onto the image border
            u, v = coverage.project(px, py, 0.3, -0.2, 0.8, 0.7, cam, -0.32)
            self.assertTrue(min(abs(u), abs(u - cam['W'])) < 1e-6 or min(abs(v), abs(v - cam['H'])) < 1e-6, (u, v))


class RealField(unittest.TestCase):
    """What the calibrated Gazebo model says about the real-field map (documents step 2)."""

    def count(self, x, y, cam='gazebo'):
        return coverage.expected_count(MP, x, y, CRUISE, YAW, coverage.camera(cam))

    def test_corner_18_19_and_10_are_red(self):
        # Gazebo, true z 0.71-0.74: over 10, 18, 19 >= 2 markers in 0-0.7 % of frames
        for mid in (10, 18, 19):
            m = next(mm for mm in MP['markers'] if mm['id'] == mid)
            self.assertEqual(coverage.level(self.count(m['x'], m['y'])), 'red', mid)

    def test_other_markers_not_red(self):
        # Gazebo, true z 0.71-0.85: over these >= 2 markers in 74-93 % of frames
        for mid in (0, 1, 2, 3, 5, 6, 7, 8, 13, 16):
            m = next(mm for mm in MP['markers'] if mm['id'] == mid)
            self.assertNotEqual(coverage.level(self.count(m['x'], m['y'])), 'red', mid)

    def test_camera_is_the_drone_calibration(self):
        # main_camera_640x480.yaml on the drone (c002c604) = Gazebo model.sdf intrinsics
        for name in ('gazebo', 'drone'):
            c = coverage.camera(name)
            self.assertEqual((c['W'], c['H'], c['fx'], c['fy'], c['cx'], c['cy']), (640, 480, 251.99, 314.81, 352.09, 306.35))
        self.assertFalse(coverage.camera('drone')['calibrated'])

    def test_grid_shape_and_levels(self):
        g = coverage.grid(MP, CRUISE, YAW, coverage.camera('gazebo'), step=0.2)
        self.assertEqual(len(g['counts']), g['ny'])
        self.assertEqual(len(g['counts'][0]), g['nx'])
        flat = [c for row in g['counts'] for c in row]
        self.assertTrue(any(coverage.level(c) == 'green' for c in flat))
        self.assertTrue(any(coverage.level(c) == 'red' for c in flat))

    def test_grid_matches_point_function(self):
        cam = coverage.camera('gazebo')
        g = coverage.grid(MP, CRUISE, YAW, cam, step=0.25)
        for j in (0, g['ny'] // 2, g['ny'] - 1):
            for i in (0, g['nx'] // 2, g['nx'] - 1):
                x, y = g['x0'] + i * g['step'], g['y0'] + j * g['step']
                self.assertAlmostEqual(g['counts'][j][i], coverage.expected_count(MP, x, y, CRUISE, YAW, cam), places=2)


if __name__ == '__main__':
    unittest.main()
