"""JSON-in / JSON-out functions for the HTML page (Pyodide in a Web Worker) (17.11.2026).

Every function takes and returns JSON text, so the page never touches Python
objects. The same calls will serve the GCS (WebView2 / WKWebView).
Results never contain NaN or Infinity (JSON.parse would fail): they become null.
"""
import json
import math

from . import bbmap, codecheck, coverage, simrun
from .fakedrone import start_heading

GRID_MAX_CELLS = 20000      # review item 14: a typo like 2900 instead of 2.900 must not hang the page


def _clean(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _out(obj):
    return json.dumps(_clean(obj), ensure_ascii=False, allow_nan=False, default=str)


def _map(map_json):
    return bbmap.from_json(map_json)


def cameras():
    return _out({k: {'label': v['label'], 'calibrated': v.get('calibrated', False)} for k, v in coverage.CAMERAS.items()})


def map_from_txt(text, name='field'):
    """Map JSON from map.txt text plus '_check' (the problems of the FILE, e.g. a
    short line the detector would skip, which the JSON form can no longer show)."""
    try:
        mp = bbmap.from_map_txt(text, name=name)
    except bbmap.MapError as e:
        return _out({'error': str(e)})
    out = json.loads(bbmap.to_json(mp))
    out['_check'] = bbmap.check(mp)
    return _out(out)


def map_check(map_json):
    """{'errors', 'warnings', 'sha', 'summary', 'txt', 'json', 'bounds', 'heading'} or {'error'} if unreadable."""
    try:
        mp = _map(map_json)
    except bbmap.MapError as e:
        return _out({'error': str(e)})
    r = bbmap.check(mp)
    r['sha'] = bbmap.map_sha(mp)
    r['summary'] = bbmap.summary(mp)
    r['txt'] = bbmap.to_map_txt(mp)
    r['json'] = bbmap.to_json(mp)
    r['bounds'] = bbmap.bounds(mp, 0.0) if mp['markers'] else None
    r['heading'] = start_heading(mp)
    return _out(r)


def grid(map_json, z_base, cam_name='gazebo', step=0.1, yaw=None):
    try:
        mp = _map(map_json)
    except bbmap.MapError as e:
        return _out({'error': str(e)})
    if not mp['markers']:
        return _out({'error': 'no markers'})
    if bbmap.check(mp)['errors']:
        return _out({'error': 'the map has errors; the coloured map is not computed'})
    step = float(step)
    x0, y0, x1, y1 = bbmap.bounds(mp, 0.6)
    cells = ((x1 - x0) / step + 1) * ((y1 - y0) / step + 1)
    if not step > 0 or cells > GRID_MAX_CELLS:
        return _out({'error': 'the field is too large for the coloured map (%.0f cells, limit %d)' % (cells, GRID_MAX_CELLS)})
    if yaw is None:
        yaw = start_heading(mp)
    return _out(coverage.grid(mp, float(z_base), float(yaw), coverage.camera(cam_name), step=step))


def _heat_args(map_json, takeoff_height, turn_deg):
    """The map (or an error text), base_link z after takeoff(takeoff_height), the heading:
    the start heading turned by turn_deg (counter-clockwise, degrees)."""
    try:
        mp = _map(map_json)
    except bbmap.MapError as e:
        return None, str(e), 0.0, 0.0
    try:
        height, turn = float(takeoff_height), float(turn_deg)
    except (TypeError, ValueError):
        height = turn = float('nan')
    if not (math.isfinite(height) and 0.0 < height <= 3.0 and math.isfinite(turn)):
        return None, 'the takeoff height or the heading is not a number within limits', 0.0, 0.0
    z_base = coverage.z_base_after_takeoff(height, mp.get('z', bbmap.DEFAULT_Z))
    yaw = start_heading(mp) + math.radians(turn) if mp['markers'] else math.radians(turn)
    yaw = math.atan2(math.sin(yaw), math.cos(yaw))
    return mp, None, z_base, yaw


def heat(map_json, takeoff_height, cam_name='gazebo', step=0.1, turn_deg=0.0):
    """The coloured map for the height the program takes off to (drone.takeoff(height)) and
    a heading; grid() plus 'heading_deg' (map frame, 0 = +x, counter-clockwise) and 'takeoff'."""
    mp, err, z_base, yaw = _heat_args(map_json, takeoff_height, turn_deg)
    if err:
        return _out({'error': err})
    out = json.loads(grid(map_json, z_base, cam_name, step, yaw))
    if 'error' not in out:
        out['heading_deg'] = round(math.degrees(yaw), 1)
        out['start_heading_deg'] = round(math.degrees(start_heading(mp)), 1)
        out['takeoff'] = float(takeoff_height)
    return _out(out)


def heat_point(map_json, x, y, takeoff_height, cam_name='gazebo', turn_deg=0.0):
    """coverage.point() for the hint under the cursor (same model as heat())."""
    mp, err, z_base, yaw = _heat_args(map_json, takeoff_height, turn_deg)
    if err:
        return _out({'error': err})
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        x = y = float('nan')
    if not (math.isfinite(x) and math.isfinite(y)):
        return _out({'error': 'the point is not a number'})
    if bbmap.check(mp)['errors']:
        return _out({'error': 'the map has errors'})
    out = coverage.point(mp, x, y, z_base, yaw, coverage.camera(cam_name))
    out['x'], out['y'] = x, y
    return _out(out)


def check_code(source):
    return _out(codecheck.check(source))


def simulate(source, map_json, cam_name='gazebo', cfg_json='{}'):
    try:
        mp = _map(map_json)
    except bbmap.MapError as e:
        return _out({'error': str(e)})
    mc = bbmap.check(mp)
    if mc['errors']:
        return _out({'error': 'the map has errors: ' + '; '.join(mc['errors'][:3])})
    cfg = json.loads(cfg_json or '{}')
    allowed = {'time_budget_s', 'z_rest', 'field_margin'}
    clean = {}
    for k, v in cfg.items():
        if k in allowed:
            f = float(v)
            if math.isfinite(f):
                clean[k] = f
    cam = coverage.camera(cam_name)
    res = simrun.run(source, mp, cam, **clean)
    res['cam'] = cam_name
    res['max_tan'] = cam.get('max_tan')
    res['mount_fwd'] = cam['mount_fwd']
    res['mount_down'] = cam['mount_down']
    res['z_floor'] = mp.get('z', bbmap.DEFAULT_Z)
    res['yaw'] = start_heading(mp)
    res['cam_K'] = {k: cam[k] for k in ('W', 'H', 'fx', 'fy', 'cx', 'cy')}
    return _out(res)
