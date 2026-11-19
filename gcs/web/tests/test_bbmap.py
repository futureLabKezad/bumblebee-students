"""Tests for bbflight.bbmap (step 1). Run: python -m unittest discover -s tests"""
import hashlib
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bbflight import bbmap  # noqa: E402

MAP_FINAL = os.path.join(os.path.dirname(HERE), 'testdata', 'map_final.txt')


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


class MapFinal(unittest.TestCase):
    def setUp(self):
        self.text = read(MAP_FINAL)
        self.mp = bbmap.from_map_txt(self.text, name='field_real')

    def test_reads_20_markers_no_errors(self):
        self.assertEqual(len(self.mp['markers']), 20)
        r = bbmap.check(self.mp)
        self.assertEqual(r['errors'], [])

    def test_canonical_lines_equal_the_file_byte_for_byte(self):
        data = [l for l in self.text.splitlines() if l.strip() and not l.startswith('#')]
        self.assertEqual(bbmap.canonical_lines(self.mp), data)

    def test_sha_is_sha_of_data_lines(self):
        data = [l for l in self.text.splitlines() if l.strip() and not l.startswith('#')]
        want = hashlib.sha256(('\n'.join(data) + '\n').encode()).hexdigest()
        self.assertEqual(bbmap.map_sha(self.mp), want)

    def test_json_round_trip_keeps_sha(self):
        js = bbmap.to_json(self.mp)
        back = bbmap.from_json(js)
        self.assertEqual(bbmap.map_sha(back), bbmap.map_sha(self.mp))
        txt = bbmap.to_map_txt(back)
        again = bbmap.from_map_txt(txt, name='field_real')
        self.assertEqual(bbmap.map_sha(again), bbmap.map_sha(self.mp))

    def test_corner_markers_warned_about(self):
        # neighbours of 18/19 are 0.68..0.95 m away: no warning at 1.2 m; this
        # documents the threshold, the real check is coverage (step 2)
        r = bbmap.check(self.mp)
        self.assertFalse(any('18' in w for w in r['warnings']))


def mk(markers, **kw):
    d = {'format': bbmap.FORMAT, 'name': 't', 'markers': markers}
    d.update(kw)
    return bbmap.from_json(json.dumps(d))


M0 = {'id': 0, 'length': 0.19, 'x': 0, 'y': 0, 'rot_z': 1.5708}
M1 = {'id': 1, 'length': 0.29, 'x': 0, 'y': 0.97, 'rot_z': 1.5708}


class BadMaps(unittest.TestCase):
    def errs(self, mp):
        return bbmap.check(mp)['errors']

    def test_duplicate_id(self):
        e = self.errs(mk([M0, M1, dict(M1, x=1.0)]))
        self.assertTrue(any('twice' in x for x in e), e)

    def test_no_marker_0(self):
        e = self.errs(mk([M1]))
        self.assertTrue(any('no marker 0' in x for x in e), e)

    def test_zero_length(self):
        e = self.errs(mk([M0, dict(M1, length=0)]))
        self.assertTrue(any('side' in x for x in e), e)

    def test_id_outside_dictionary(self):
        e = self.errs(mk([M0, dict(M1, id=120)]))
        self.assertTrue(any('dictionary' in x for x in e), e)

    def test_overlap(self):
        e = self.errs(mk([M0, dict(M1, y=0.15)]))
        self.assertTrue(any('overlap' in x for x in e), e)

    def test_touching_is_not_overlap(self):
        a = {'id': 0, 'length': 0.2, 'x': 0, 'y': 0, 'rot_z': 0}
        b = {'id': 1, 'length': 0.2, 'x': 0.2, 'y': 0, 'rot_z': 0}
        self.assertEqual(self.errs(mk([a, b])), [])

    def test_empty(self):
        self.assertTrue(self.errs(mk([])))

    def test_nan_rejected_on_read(self):
        with self.assertRaises(bbmap.MapError):
            mk([M0, dict(M1, x='nan')])

    def test_text_id_rejected(self):
        with self.assertRaises(bbmap.MapError):
            mk([M0, dict(M1, id='abc')])

    def test_fraction_id_rejected(self):
        with self.assertRaises(bbmap.MapError):
            mk([M0, dict(M1, id=1.5)])

    def test_short_line_is_error_detector_would_skip_it(self):
        mp = bbmap.from_map_txt('0 0.19 0 0 -0.32 1.57 0 0\n1 0.29 0 0.97\n')
        e = self.errs(mp)
        self.assertTrue(any('8 columns' in x for x in e), e)
        self.assertEqual(len(mp['markers']), 1)

    def test_mixed_z_is_error(self):
        mp = bbmap.from_map_txt('0 0.19 0 0 -0.32 1.57 0 0\n1 0.29 0 0.97 -0.10 1.57 0 0\n')
        self.assertTrue(any('different heights z' in x for x in self.errs(mp)))

    def test_tilted_marker_rejected(self):
        with self.assertRaises(bbmap.MapError):
            bbmap.from_map_txt('0 0.19 0 0 -0.32 1.57 0.3 0\n')

    def test_wrong_format(self):
        with self.assertRaises(bbmap.MapError):
            bbmap.from_json('{"format": "other/9", "markers": []}')

    def test_z_differs_from_drone_is_warning(self):
        r = bbmap.check(mk([M0, M1], z=-0.2))
        self.assertEqual(r['errors'], [])
        self.assertTrue(r['warnings'])

    # review 17.11, items 13, 18, 22, 23
    def test_name_with_line_break_cannot_add_a_marker(self):
        mp = mk([M0, M1], name='x\r5 0.29 1.5 1.5 -0.32 0 0 0 ')
        txt = bbmap.to_map_txt(mp)
        back = bbmap.from_map_txt(txt.replace('\r', '\n'))
        self.assertEqual(sorted(m['id'] for m in back['markers']), [0, 1])
        self.assertNotIn('\r', mp['name'])

    def test_nan_inf_ids_are_map_errors(self):
        for bad in ('nan', 'inf', '1e400'):
            with self.assertRaises(bbmap.MapError, msg=bad):
                bbmap.from_map_txt('%s 0.19 0 0 -0.32 1.57 0 0\n' % bad)

    def test_minus_zero_and_angle_wrap_give_same_sha(self):
        a = mk([M0, M1])
        b = mk([dict(M0, x=-0.0001, rot_z=1.5708 + 2 * 3.141592653589793), M1])
        self.assertEqual(bbmap.map_sha(a), bbmap.map_sha(b))

    def test_too_many_markers_rejected_fast(self):
        many = [{'id': i % 100, 'length': 0.1, 'x': i * 0.2, 'y': 0, 'rot_z': 0} for i in range(500)]
        with self.assertRaises(bbmap.MapError):
            mk(many)

    def test_far_neighbour_warning(self):
        r = bbmap.check(mk([M0, dict(M1, y=3.0)]))
        self.assertTrue(any('nearest' in w for w in r['warnings']), r)


if __name__ == '__main__':
    unittest.main()
