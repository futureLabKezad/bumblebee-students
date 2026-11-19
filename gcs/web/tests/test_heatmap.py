"""The coloured map, 18.11: heights from takeoff(), the blind spot, the hint, the heading."""
import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bbflight import bbmap, coverage, webapi  # noqa: E402
from bbflight.fakedrone import start_heading  # noqa: E402

with open(os.path.join(os.path.dirname(HERE), 'testdata', 'map_final.txt'), encoding='utf-8') as f:
    TXT = f.read()
MP = bbmap.from_map_txt(TXT, name='field_real')
MAP_JSON = bbmap.to_json(MP)


class Reference(unittest.TestCase):
    """The numbers the model takes from the drone (ЭТАЛОН_РАЗМЕРОВ_20EC, main_camera_640x480.yaml)."""

    def test_camera_mount_and_K_are_the_drones(self):
        for name in ('gazebo', 'drone'):
            cam = coverage.camera(name)
            self.assertEqual((cam['mount_fwd'], cam['mount_left'], cam['mount_down']), (0.081, 0.0, 0.034), name)
            self.assertEqual((cam['W'], cam['H'], cam['fx'], cam['fy'], cam['cx'], cam['cy']),
                             (640, 480, 251.99, 314.81, 352.09, 306.35), name)

    def test_heights_from_the_reference(self):
        self.assertEqual(coverage.BASE_ABOVE_FLOOR_REST, 0.217)                  # centre B, standing
        cam = coverage.camera('drone')
        rest = coverage.heights(coverage.z_base_after_takeoff(0.0, -0.32), cam, -0.32)
        self.assertAlmostEqual(rest['camera'], 0.183, places=6)                 # the lens, standing
        z = coverage.z_base_after_takeoff(0.9, -0.32)                           # drone.py: z_start + height
        self.assertAlmostEqual(z, 0.797, places=6)
        h = coverage.heights(z, cam, -0.32)
        self.assertAlmostEqual(h['base'], 1.117, places=6)
        self.assertAlmostEqual(h['camera'], 1.083, places=6)

    def test_chat_1_example_map_z_075(self):
        # «z 0,75 — это z base_link в карте; камера ≈ 0,75 − 0,034 + 0,32 = 1,04 м над полом»
        self.assertAlmostEqual(coverage.heights(0.75, coverage.camera('drone'), -0.32)['camera'], 1.036, places=6)


class Shades(unittest.TestCase):
    def test_blind_is_a_part_of_red_and_nothing_else_moves(self):
        for n, want in ((0.0, 'blind'), (0.4, 'blind'), (0.5, 'red'), (1.4, 'red'), (1.5, 'yellow'), (2.49, 'yellow'), (2.5, 'green')):
            self.assertEqual(coverage.shade(n), want, n)
            self.assertEqual(coverage.level(n), 'red' if want == 'blind' else want, n)
        self.assertEqual((coverage.RED_BELOW, coverage.GREEN_FROM), (1.5, 2.5))     # the thresholds are as before


class Heat(unittest.TestCase):
    def heat(self, h=0.9, turn=0.0, cam='drone'):
        return json.loads(webapi.heat(MAP_JSON, h, cam, 0.2, turn))

    def test_heat_is_the_grid_at_the_height_after_takeoff(self):
        g = self.heat()
        old = json.loads(webapi.grid(MAP_JSON, coverage.z_base_after_takeoff(0.9, MP['z']), 'drone', 0.2))
        self.assertEqual(g['counts'], old['counts'])
        self.assertAlmostEqual(g['heights']['camera'], 1.083, places=6)
        self.assertEqual(g['takeoff'], 0.9)
        self.assertEqual(g['blind_below'], 0.5)
        flat = [c for row in g['counts'] for c in row]
        self.assertTrue(any(coverage.shade(c) == 'blind' for c in flat))           # the margins see nothing
        self.assertTrue(any(coverage.shade(c) in ('yellow', 'green') for c in flat))

    def test_the_heading_is_reported_and_can_be_turned(self):
        start = math.degrees(start_heading(MP))
        self.assertAlmostEqual(self.heat()['heading_deg'], round(start, 1), places=6)
        self.assertAlmostEqual(self.heat()['start_heading_deg'], round(start, 1), places=6)
        turned = self.heat(turn=180)
        want = math.degrees(math.atan2(math.sin(math.radians(start + 180)), math.cos(math.radians(start + 180))))
        self.assertAlmostEqual(turned['heading_deg'], round(want, 1), places=6)
        self.assertNotEqual(turned['counts'], self.heat()['counts'])                # forward reaches further than back

    def test_higher_takeoff_sees_more(self):
        low, high = self.heat(0.5), self.heat(1.3)
        mean = lambda g: sum(sum(r) for r in g['counts'])  # noqa: E731
        self.assertGreater(mean(high), mean(low))

    def test_bad_input_is_an_error_not_a_crash(self):
        for h, turn in (('x', 0), (float('nan'), 0), (-1, 0), (0.9, float('inf'))):
            try:
                out = json.loads(webapi.heat(MAP_JSON, h, 'drone', 0.2, turn))
            except ValueError:
                self.fail('heat(%r, %r) raised' % (h, turn))
            self.assertIn('error', out)
        self.assertIn('error', json.loads(webapi.heat('{', 0.9)))


class Hint(unittest.TestCase):
    def point(self, x, y, h=0.9, turn=0.0):
        return json.loads(webapi.heat_point(MAP_JSON, x, y, h, 'drone', turn))

    def test_the_hint_agrees_with_the_coloured_map(self):
        g = json.loads(webapi.heat(MAP_JSON, 0.9, 'drone', 0.2, 0.0))
        for j in range(0, g['ny'], 3):
            for i in range(0, g['nx'], 3):
                p = self.point(g['x0'] + i * g['step'], g['y0'] + j * g['step'])
                self.assertAlmostEqual(p['mean'], g['counts'][j][i], places=2)
                self.assertEqual(p['shade'], coverage.shade(g['counts'][j][i]))

    def test_over_a_marker_it_is_seen_far_away_nothing(self):
        m0 = next(m for m in MP['markers'] if m['id'] == 0)
        p = self.point(m0['x'], m0['y'])
        self.assertIn(0, p['ids'])
        self.assertEqual(len(p['footprint']), 4)
        self.assertGreater(p['cone'][2], 0.9)                                        # max_tan 0.95 x camera 1.08 m
        self.assertAlmostEqual(p['camera'], 1.083, places=6)
        far = self.point(m0['x'] + 30, m0['y'] + 30)
        self.assertEqual((far['ids'], far['shade']), ([], 'blind'))

    def test_bad_points_are_errors(self):
        self.assertIn('error', json.loads(webapi.heat_point(MAP_JSON, 'a', 0, 0.9)))
        self.assertIn('error', json.loads(webapi.heat_point(MAP_JSON, float('nan'), 0, 0.9)))


if __name__ == '__main__':
    unittest.main()
