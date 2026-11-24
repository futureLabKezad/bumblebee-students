"""Pre-flight review of a program: what will go wrong, why, how to prevent it (24.11.2026).

    rep = preflight.review(source, mp, cam, sim_result)

Input: the result of simrun.run() for this program and map. Output: plain data for the page:
  {'verdict': 'ready'|'check'|'not_ready', 'findings': [...], 'stats': {...}}
Each finding: {'level': 'error'|'warn'|'info', 'code', 'line', 't', 'x', 'y', 'title', 'why', 'fix'}.

What is checked (owner's task 24.11, via chat 1):
  * every error and warning of the code check and of the guards in the simulation, with a fix
  * close to the edge of the field (the guard lands the drone outside the map + 0.30 m)
  * flying outside the marker area (few markers in view there)
  * height: the rangefinder under 1 m -- PX4 learns the hover thrust only above 1 m
  * markers lost from view on the way; the red zone
  * flight time against the budget; the battery has no current sensor
  * no require_map
  * sharp turns and flying backwards (the camera sees less behind the drone)
Numbers that are not facts about the drone are marked so in 'why'.
"""
import math

from . import bbmap, coverage, hints
from .fakedrone import DEFAULTS, PX4_PROFILE

# 20EC reference (ЭТАЛОН_РАЗМЕРОВ_20EC, model 1:1): rangefinder lens 0.183 m above the floor when
# the drone stands; PX4 adds (RNG_POS - IMU_POS)z = 0.05 m -> it reads ~0.233 m on the floor.
RNG_ON_FLOOR = 0.233
HTE_MIN = 1.0              # PX4 1.16.1 MulticopterHoverThrustEstimator: in air only when dist_bottom > 1 m
EDGE_WARN_M = 0.15         # closer than this to the guard border -> warning
TIME_WARN_SHARE = 0.8      # flight time over 80 % of the budget -> warning
TURN_DEG = 100.0           # direction change sharper than this -> a note
BACKWARD_DEG = 120.0       # flying more than this away from the nose -> a note
MOVE_MPS = 0.03            # slower than this counts as standing
START_NEAR_M = 0.30        # «right over the start marker» for the red-zone advice


def _f(item, **kw):
    item.setdefault('line', 0)
    item.setdefault('t', None)
    item.setdefault('x', None)
    item.setdefault('y', None)
    item.setdefault('why', '')
    item.setdefault('fix', hints.fix_for(item['title']))
    item.update(kw)
    return item


def _airborne(trace, z_rest):
    return [p for p in trace if p[5] and p[3] > z_rest + 0.2]


def _edge(mp, trace, z_rest, margin):
    """(closest distance to the guard border, the point) over the airborne path; and the
    first point outside the marker area."""
    if not mp['markers']:
        return None, None, None
    x0, y0, x1, y1 = bbmap.bounds(mp, 0.0)
    gx0, gy0, gx1, gy1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
    best, at, outside = None, None, None
    for p in _airborne(trace, z_rest):
        d = min(p[1] - gx0, gx1 - p[1], p[2] - gy0, gy1 - p[2])
        if best is None or d < best:
            best, at = d, p
        if outside is None and not (x0 - 1e-6 <= p[1] <= x1 + 1e-6 and y0 - 1e-6 <= p[2] <= y1 + 1e-6):
            outside = p
    return best, at, outside


def _turns(trace, yaw):
    """Moving directions between stops: sharp changes and backward flight (relative to the nose)."""
    turns, backward = [], []
    prev_dir = None
    for a, b in zip(trace, trace[1:]):
        dt = b[0] - a[0]
        if dt <= 0 or not b[5]:
            continue
        dx, dy = b[1] - a[1], b[2] - a[2]
        v = math.hypot(dx, dy) / dt
        if v < MOVE_MPS:
            continue
        d = math.atan2(dy, dx)
        if prev_dir is not None:
            ang = abs(math.degrees(math.atan2(math.sin(d - prev_dir), math.cos(d - prev_dir))))
            if ang > TURN_DEG and (not turns or b[0] - turns[-1][0] > 3.0):
                turns.append((b[0], b[1], b[2], ang))
        rel = abs(math.degrees(math.atan2(math.sin(d - yaw), math.cos(d - yaw))))
        if rel > BACKWARD_DEG and (not backward or b[0] - backward[-1][1] > 3.0):
            backward.append([b[0], b[0], b[1], b[2]])
        elif rel > BACKWARD_DEG and backward:
            backward[-1][1] = b[0]
        prev_dir = d
    return turns, backward


def _blind(trace, z_rest):
    """Stretches in the air with almost no marker in view (mean < 0.5): [(t0, t1, x, y)]."""
    out, cur = [], None
    for p in _airborne(trace, z_rest):
        if p[4] < coverage.BLIND_BELOW:
            if cur is None:
                cur = [p[0], p[0], p[1], p[2]]
            cur[1] = p[0]
        elif cur is not None:
            out.append(tuple(cur))
            cur = None
    if cur is not None:
        out.append(tuple(cur))
    return out


def review(source, mp, cam, res, budget_s=None):
    findings = []
    chk = res.get('check') or {'errors': [], 'warnings': [], 'used': []}
    for e in chk['errors']:
        findings.append(_f({'level': 'error', 'code': 'CODE', 'line': e['line'], 'title': e['text'],
                            'why': 'The check runs the same way on the drone: the drone will not accept this program.'}))
    for w in chk['warnings']:
        findings.append(_f({'level': 'warn', 'code': 'CODE', 'line': w['line'], 'title': w['text']}))
    stats = {}
    if not res.get('ran'):
        return _done(findings, stats)

    cfg = dict(DEFAULTS)
    lim = res.get('limits') or {}
    z_rest = cfg['z_rest']
    margin = lim.get('field_margin', cfg['field_margin'])
    budget = budget_s or lim.get('time_budget_s', cfg['time_budget_s'])
    trace = res.get('trace') or []
    yaw = res.get('yaw', 0.0) or 0.0

    start = trace[0] if trace else None
    for ev in res.get('events', []):
        if ev['level'] == 'info':
            continue
        item = {'level': ev['level'], 'code': 'SIM', 'line': ev.get('line', 0), 't': ev['t'],
                'x': ev.get('x'), 'y': ev.get('y'), 'title': ev['text'], 'why': ''}
        # review 24.11, M8: the red zone right after takeoff over the start marker needs other advice
        # than «route over the markers». The level stays a warning (what counts as a problem is the owner's).
        if 'red zone' in ev['text'] and start and ev.get('x') is not None \
                and math.hypot(ev['x'] - start[1], ev['y'] - start[2]) < START_NEAR_M:
            item['why'] = 'Right after takeoff over the start marker the camera sees about one marker (in the model, as in Gazebo).'
            item['fix'] = 'Put more markers around the start marker so that two or more are in view, or take off a little higher.'
        findings.append(_f(item))

    if 'require_map' not in chk.get('used', []) and any(n in chk.get('used', []) for n in ('fly_to', 'fly_to_marker', 'move')):
        findings.append(_f({'level': 'warn', 'code': 'MAP_NAME', 'title': 'the program does not call drone.require_map(...)',
                            'why': 'The route only makes sense on its own map. If the drone has another map, it flies to other places.',
                            'fix': "Put drone.require_map('%s') near the top." % (mp.get('name') or 'field')}))

    air = _airborne(trace, z_rest)
    if air:
        # edge of the field
        best, at, outside = _edge(mp, trace, z_rest, margin)
        if best is not None and best < EDGE_WARN_M and best >= 0:
            findings.append(_f({'level': 'warn', 'code': 'EDGE', 't': at[0], 'x': at[1], 'y': at[2],
                                'title': 'the path comes %.0f cm from the border where the guard lands the drone' % (best * 100),
                                'why': 'The guard lands the drone outside the map + %.2f m. A real drone drifts around its target (5–15 cm is an estimate, not measured).' % margin,
                                'fix': 'Keep the route at least 15 cm inside: move the point inwards or add markers at the edge.'}))
        if outside is not None:
            findings.append(_f({'level': 'info', 'code': 'OUTSIDE_MARKERS', 't': outside[0], 'x': outside[1], 'y': outside[2],
                                'title': 'the drone flies outside the area covered by markers',
                                'why': 'There the camera sees fewer markers, so the position is less sure.',
                                'fix': 'Add markers there (Map tab) or keep the route over the markers.'}))
        # height and the rangefinder
        hz = max(p[3] for p in air) - z_rest
        rng = RNG_ON_FLOOR + hz
        stats['max_height_m'] = round(hz, 2)
        stats['rangefinder_m'] = round(rng, 2)
        if rng <= HTE_MIN:
            findings.append(_f({'level': 'warn', 'code': 'HTE', 'title': 'the rangefinder reads about %.2f m in flight, not above 1 m' % rng,
                                'why': 'PX4 1.16 learns the hover thrust only when the rangefinder reads more than 1 m (code, proven). '
                                       'Without it PX4 detects the landing later: in Gazebo (test T41) the motors stopped after ~4 s instead of ~2.3 s; not measured on the drone. '
                                       'The reading is computed from the 20EC model (likely), not measured on this drone.',
                                'fix': 'Take off to 0.9 m or higher (allowed up to 1.3 m).'}))
        elif rng < HTE_MIN + 0.05:
            findings.append(_f({'level': 'info', 'code': 'HTE', 'title': 'the rangefinder reads about %.2f m: only just above the PX4 1 m threshold' % rng,
                                'why': 'PX4 learns the hover thrust above 1 m. A few centimetres of error and it does not (computed, likely).',
                                'fix': 'Take off to 0.9 m or higher for a safe margin.'}))
        # markers lost on the way (before the 6 s guard)
        for t0, t1, x, y in _blind(trace, z_rest):
            findings.append(_f({'level': 'warn', 'code': 'BLIND', 't': t0, 'x': x, 'y': y,
                                'title': 'no marker in view for %.1f s from %.1f s' % (max(0.2, t1 - t0), t0),
                                'why': 'Without markers the position comes only from the flow sensor and drifts. After %.0f s the guard lands the drone.'
                                       % cfg['vision_timeout_s'],
                                'fix': hints.fix_for('no marker in view for')}))
        # turns and flying backwards
        turns, backward = _turns(trace, yaw)
        for t, x, y, ang in turns:
            findings.append(_f({'level': 'info', 'code': 'TURN', 't': t, 'x': x, 'y': y,
                                'title': 'sharp turn: %.0f°' % ang,
                                'why': 'The drone stops at each point (it waits until it arrives), so a turn is a stop and a new start. '
                                       'The simulation found no problem here.',
                                'fix': 'Nothing to do; for a smoother path split it into smaller turns.'}))
        for t0, t1, x, y in backward:
            findings.append(_f({'level': 'info', 'code': 'BACKWARD', 't': t0, 'x': x, 'y': y,
                                'title': 'the drone flies backwards (tail first) for %.0f s' % max(1.0, t1 - t0),
                                'why': 'The down camera looks further forward (tan 0.97) than back (tan 0.55): '
                                       'flying tail first it sees the markers ahead later.',
                                'fix': 'Plan the route so the drone mostly flies nose first, or keep more markers on the way.'}))
        # time and battery
        fl = res.get('flight_s', 0.0)
        if budget and fl > TIME_WARN_SHARE * budget and fl <= budget:
            findings.append(_f({'level': 'warn', 'code': 'TIME', 'title': 'the flight takes %.0f s of the %.0f s budget' % (fl, budget),
                                'why': 'The timing is fitted to Gazebo runs, not measured on the drone (on a route outside the fitting it was off by ~10 %): leave a margin.',
                                'fix': 'Shorten hovers or the route so there is at least 20 % of the budget left.'}))
        # battery (review 24.11, M6, d3): one line in the numbers, not a card on every flight
        stats['battery'] = ('%.0f s in the air, counted by the timer only (no current sensor). The drone lands at 23.0 V by PX4; '
                            'the owner’s limit is 20 V by a multimeter (PX4 over-reads).' % fl)
        stats['flight_s'] = fl
        stats['path_m'] = round(sum(math.dist(a[1:4], b[1:4]) for a, b in zip(trace, trace[1:]) if b[5]), 2)
        stats['min_markers'] = round(min(p[4] for p in air), 1)
        stats['red_zone_s'] = res.get('red_zone_s', 0.0)
        stats['edge_m'] = None if best is None else round(best, 2)
    stats['duration_s'] = res.get('duration_s', 0.0)
    stats['px4_profile'] = dict(PX4_PROFILE)
    return _done(findings, stats)


_ORDER = {'error': 0, 'warn': 1, 'info': 2}


def _done(findings, stats):
    findings.sort(key=lambda f: (_ORDER[f['level']], f['t'] if f['t'] is not None else -1, f['line']))
    if any(f['level'] == 'error' for f in findings):
        verdict = 'not_ready'
    elif any(f['level'] == 'warn' for f in findings):
        verdict = 'check'
    else:
        verdict = 'ready'
    return {'verdict': verdict, 'findings': findings, 'stats': stats}
