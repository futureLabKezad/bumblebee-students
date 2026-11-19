"""Marker map format v1 for the Bumblebee GCS and drone (17.11.2026).

One map = list of ArUco markers on the floor: id, side length, x, y, rot_z.
Two forms, same content:

  JSON (GCS editor):
      {"format": "bumblebee-map/1", "name": "field_real", "z": -0.32,
       "markers": [{"id": 0, "length": 0.19, "x": 0.0, "y": 0.0, "rot_z": 1.5446}, ...]}

  map.txt (what the drone’s detector reads, aruco_detect.py _load_map_file):
      # id  length  x  y  z  rot_z  rot_y  rot_x
      0   0.190   0.000   0.000   -0.320  1.5446  0.000  0.000

Facts this follows (r2j image, read 17.11):
  * aruco_detect.py skips a line with fewer than 8 columns WITHOUT an error,
    while drone.py _read_map_file accepts 4+ columns. So the canonical text
    always has all 8 columns, and check() treats short lines as errors.
  * The detector uses dictionary 1 (DICT_4X4_100): ids 0..99.
  * z of the marker plane is -0.32 on the drone (DRONE_REST_Z_OFFSET); the
    GCS does not let a user type z, it takes it from the drone setting.

map_sha() is the sha256 of the canonical text: the GCS and the drone compute
it the same way, so "map accepted" can be compared by sha.
"""
import hashlib
import json
import math

FORMAT = 'bumblebee-map/1'
DEFAULT_Z = -0.32          # marker plane in map z, r2j DRONE_REST_Z_OFFSET
DICT_MAX_ID = 99           # DICT_4X4_100
MIN_LENGTH = 0.03          # m; smaller is not a printable floor marker
MAX_LENGTH = 1.00          # m
MAX_ABS_XY = 50.0          # m; a typo guard, not a field limit
HEADER = '# id\tlength\tx\ty\tz\trot_z\trot_y\trot_x'


class MapError(ValueError):
    """The map cannot be read at all (bad JSON, bad numbers)."""


MAX_MARKERS = 100          # the dictionary has 100 ids; more means duplicates or garbage


def clean_name(name):
    """Map name without control characters or line breaks (anything str.splitlines cuts on)."""
    s = ''.join(ch for ch in str(name) if ch.isprintable() and ch not in '  \x85')
    return s.strip()[:64]


def _num(v, what):
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        raise MapError('%s: not a number: %r' % (what, v))
    if math.isnan(f) or math.isinf(f):
        raise MapError('%s: not a finite number: %r' % (what, v))
    return f


def _marker(d, n):
    if not isinstance(d, dict):
        raise MapError('marker #%d: expected an object, got %r' % (n, d))
    try:
        mid = d['id']
    except KeyError:
        raise MapError('marker #%d: no id' % n)
    if isinstance(mid, bool) or not isinstance(mid, (int, float, str)):
        raise MapError('marker #%d: bad id %r' % (n, mid))
    try:
        fid = float(mid)
    except (ValueError, OverflowError):
        raise MapError('marker #%d: bad id %r' % (n, mid))
    if not math.isfinite(fid):
        raise MapError('marker #%d: bad id %r' % (n, mid))
    if fid != int(fid):
        raise MapError('marker #%d: id must be a whole number, got %r' % (n, mid))
    m = {'id': int(fid)}
    for key in ('length', 'x', 'y'):
        if key not in d:
            raise MapError('marker id %d: no %s' % (m['id'], key))
        m[key] = _num(d[key], 'marker id %d %s' % (m['id'], key))
    m['rot_z'] = _num(d.get('rot_z', 0.0), 'marker id %d rot_z' % m['id'])
    return m


def from_json(text_or_obj):
    """Map dict from the JSON form (str or already-parsed object). MapError if unreadable."""
    if isinstance(text_or_obj, str):
        try:
            obj = json.loads(text_or_obj)
        except ValueError as e:
            raise MapError('bad JSON: %s' % e)
    else:
        obj = text_or_obj
    if not isinstance(obj, dict):
        raise MapError('expected a JSON object')
    fmt = obj.get('format', FORMAT)
    if fmt != FORMAT:
        raise MapError('unknown map format %r (expected %r)' % (fmt, FORMAT))
    markers = obj.get('markers')
    if not isinstance(markers, list):
        raise MapError('"markers" must be a list')
    if len(markers) > MAX_MARKERS:
        raise MapError('%d markers: more than the dictionary has IDs (%d)' % (len(markers), MAX_MARKERS))
    return {
        'format': FORMAT,
        'name': clean_name(obj.get('name', '')),
        'z': _num(obj.get('z', DEFAULT_Z), 'z'),
        'markers': [_marker(d, n) for n, d in enumerate(markers, 1)],
    }


def from_map_txt(text, name=''):
    """Map dict from map.txt text. Lines with < 8 columns are kept as problems
    (the detector would silently skip them), reported by check()."""
    markers, short, zs = [], [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        p = line.split()
        if len(p) < 8:
            short.append((n, raw))
            continue
        try:
            m = _marker({'id': p[0], 'length': p[1], 'x': p[2], 'y': p[3], 'rot_z': p[5]}, n)
            z = _num(p[4], 'line %d z' % n)
            ry, rx = _num(p[6], 'line %d rot_y' % n), _num(p[7], 'line %d rot_x' % n)
        except MapError as e:
            raise MapError('line %d: %s' % (n, e))
        if abs(ry) > 1e-9 or abs(rx) > 1e-9:
            raise MapError('line %d: rot_y/rot_x must be 0 for a floor marker' % n)
        zs.append(z)
        markers.append(m)
        if len(markers) > MAX_MARKERS:
            raise MapError('more than %d markers: more than the dictionary has IDs' % MAX_MARKERS)
    z = zs[0] if zs else DEFAULT_Z
    mp = {'format': FORMAT, 'name': clean_name(name), 'z': z, 'markers': markers}
    if short:
        mp['_short_lines'] = short
    if any(abs(v - z) > 1e-6 for v in zs):
        mp['_mixed_z'] = sorted(set(round(v, 4) for v in zs))
    return mp


def to_json(mp, indent=1):
    out = {'format': FORMAT, 'name': mp.get('name', ''), 'z': mp.get('z', DEFAULT_Z),
           'markers': [{'id': m['id'], 'length': m['length'], 'x': m['x'], 'y': m['y'],
                        'rot_z': m['rot_z']} for m in mp['markers']]}
    return json.dumps(out, indent=indent, ensure_ascii=False)


def _f(v, digits):
    """Fixed decimals without a '-0.000' (the same map must give the same sha)."""
    s = '%.*f' % (digits, v)
    return s[1:] if s.startswith('-') and float(s) == 0.0 else s


def _wrap(a):
    """Angle in (-pi, pi]: rot_z and rot_z + 2*pi are the same marker."""
    a = math.atan2(math.sin(a), math.cos(a))
    return math.pi if a <= -math.pi else a


def canonical_lines(mp):
    """The data lines of map.txt, in the given marker order, fixed decimals."""
    z = mp.get('z', DEFAULT_Z)
    return ['%d\t%s\t%s\t%s\t%s\t%s\t0.000\t0.000'
            % (m['id'], _f(m['length'], 3), _f(m['x'], 3), _f(m['y'], 3), _f(z, 3), _f(_wrap(m['rot_z']), 4))
            for m in mp['markers']]


def to_map_txt(mp):
    """Full map.txt text the drone detector reads (header comment + 8-column lines).
    The map name is NOT written into the file (a name with a line break could
    add a marker line); the header carries only the sha."""
    head = HEADER + '   sha256 ' + map_sha(mp)
    return '\n'.join([head] + canonical_lines(mp)) + '\n'


def map_sha(mp):
    """sha256 of the canonical data lines (no comments): same on the GCS and the drone."""
    body = '\n'.join(canonical_lines(mp)) + '\n'
    return hashlib.sha256(body.encode('ascii')).hexdigest()


def corners(m):
    """4 corners (x, y) of a marker square on the floor, map frame."""
    h = m['length'] / 2.0
    c, s = math.cos(m['rot_z']), math.sin(m['rot_z'])
    return [(m['x'] + c * dx - s * dy, m['y'] + s * dx + c * dy)
            for dx, dy in ((-h, h), (h, h), (h, -h), (-h, -h))]


def _overlap(a, b):
    """True if two convex polygons overlap (separating axis test); touching is not overlap."""
    for poly in (a, b):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            ax, ay = y1 - y2, x2 - x1
            pa = [ax * x + ay * y for x, y in a]
            pb = [ax * x + ay * y for x, y in b]
            if max(pa) <= min(pb) + 1e-9 or max(pb) <= min(pa) + 1e-9:
                return False
    return True


def check(mp, expect_z=DEFAULT_Z, need_id0=True):
    """Problems of a map: {'errors': [...], 'warnings': [...]} (lists of str).

    errors   -> the map must not be sent to the drone
    warnings -> it may be sent, but the person should look
    """
    errors, warnings = [], []
    for n, raw in mp.get('_short_lines', []):
        errors.append('line %d: fewer than 8 columns, the drone’s detector would skip it silently: %r' % (n, raw.strip()))
    if mp.get('_mixed_z'):
        errors.append('markers at different heights z: %s; all markers must lie on the floor' % mp['_mixed_z'])
    markers = mp.get('markers', [])
    if not markers:
        errors.append('the map has no markers')
        return {'errors': errors, 'warnings': warnings}
    if len(markers) > MAX_MARKERS:
        errors.append('%d markers: more than the dictionary has IDs (%d)' % (len(markers), MAX_MARKERS))
        return {'errors': errors, 'warnings': warnings}
    seen = {}
    for m in markers:
        i = m['id']
        if i in seen:
            errors.append('marker %d is listed twice' % i)
        seen[i] = m
        if not 0 <= i <= DICT_MAX_ID:
            errors.append('marker %d: ID outside the 4x4_100 dictionary (0..%d)' % (i, DICT_MAX_ID))
        if not MIN_LENGTH <= m['length'] <= MAX_LENGTH:
            errors.append('marker %d: side %.3f m outside %.2f..%.2f m' % (i, m['length'], MIN_LENGTH, MAX_LENGTH))
        if abs(m['x']) > MAX_ABS_XY or abs(m['y']) > MAX_ABS_XY:
            errors.append('marker %d: position (%.2f, %.2f) m looks like a typo' % (i, m['x'], m['y']))
    if need_id0 and 0 not in seen:
        errors.append('no marker 0: the drone takes off from it and the map is checked against it on the ground')
    good = [m for m in markers if MIN_LENGTH <= m['length'] <= MAX_LENGTH]
    polys = [(m['id'], corners(m)) for m in good]
    for a in range(len(polys)):
        for b in range(a + 1, len(polys)):
            if polys[a][0] != polys[b][0] and _overlap(polys[a][1], polys[b][1]):
                errors.append('markers %d and %d overlap' % (polys[a][0], polys[b][0]))
    z = mp.get('z', DEFAULT_Z)
    if expect_z is not None and abs(z - expect_z) > 1e-6:
        warnings.append('floor height z=%.3f, the drone uses %.3f; z comes from the drone’s settings' % (z, expect_z))
    if len(good) >= 2:
        for m in good:
            d = min(math.hypot(m['x'] - o['x'], m['y'] - o['y']) for o in good if o is not m)
            if d > 1.2:
                warnings.append('marker %d: the nearest neighbour is %.2f m away; over it few markers will be in view' % (m['id'], d))
    return {'errors': errors, 'warnings': warnings}


def summary(mp):
    """Short text for the 'map accepted' reply: name, number of markers, sha."""
    return 'map "%s": %d markers, sha256 %s' % (mp.get('name', ''), len(mp.get('markers', [])), map_sha(mp)[:12])


def bounds(mp, margin=0.0):
    """(xmin, ymin, xmax, ymax) of all marker corners, plus margin."""
    pts = [p for m in mp['markers'] for p in corners(m)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
