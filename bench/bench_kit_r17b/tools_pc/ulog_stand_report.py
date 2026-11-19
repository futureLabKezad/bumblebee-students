#!/usr/bin/env python3
"""ULog report for the bench and for flights (READ ONLY, runs on the PC/WSL, never touches the drone).
Claude runs it on .ulg files the owner copied from the SD card with QGC (Log Download) into out\\ulg\\.
It prints facts only (no good/bad words): what to compare against is in cards/КАРТОЧКИ_ШАГОВ_СТЕНДА.md.

Per log:
  - length, armed periods (vehicle_status.arming_state == 2), nav_state at the arm;
  - EKF vision (T42 §3): estimator_aid_src_ev_pos spacing -> pauses longer than 0.4 s (top 8);
    EKF horizontal resets: vehicle_local_position.xy_reset_counter changes with delta_xy, time, armed flag, dist_bottom;
    estimator_status_flags: share of time cs_ev_pos / cs_ev_vel / cs_opt_flow true;
  - T41: is the topic hover_thrust_estimate in the log, max vehicle_local_position.dist_bottom per armed period,
    after the max height, from the moment dist_bottom is back at its final (floor) reading: ground_contact / maybe_landed /
    landed times and the disarm time in seconds (T41: motors off about 4 s after the touch when HTE is absent, about 2.3 s with HTE);
  - battery_status: voltage min/max/mean, cell_count, warning max, connected;
  - topics that are absent are named as absent.
Usage: ulog_stand_report.py FILE.ulg [FILE2.ulg ...]   (python with pyulog; in WSL: /home/user/px4-venv/bin/python -B -I)
Exit: 0 always when the file could be read; 2 if a file could not be read."""
import os
import sys

import numpy as np
from pyulog import ULog

PAUSE_S = 0.4
TOPICS = ['vehicle_status', 'vehicle_land_detected', 'vehicle_local_position', 'estimator_status_flags',
          'estimator_aid_src_ev_pos', 'hover_thrust_estimate', 'battery_status']


def fmt(x, nd=3):
    return ('%.' + str(nd) + 'f') % x


def seconds(d, t0, key='timestamp'):
    return (d[key].astype(np.int64) - t0) / 1e6


def armed_periods(ts, armed):
    """[(t_arm, t_disarm)] from a boolean armed array sampled at ts."""
    out = []
    start = None
    for i in range(len(ts)):
        if armed[i] and start is None:
            start = ts[i]
        elif not armed[i] and start is not None:
            out.append((float(start), float(ts[i])))
            start = None
    if start is not None:
        out.append((float(start), float(ts[-1])))
    return out


def pauses(t_samples, gap_s=PAUSE_S):
    """spacing > gap_s between consecutive sample times -> [(start, end, length)] (sorted by time)."""
    t = np.sort(np.asarray(t_samples, dtype=float))
    if len(t) < 2:
        return []
    dt = np.diff(t)
    idx = np.flatnonzero(dt > gap_s)
    return [(float(t[i]), float(t[i + 1]), float(dt[i])) for i in idx]


def counter_changes(t, counter, dx, dy):
    """times where an unsigned 8-bit reset counter changes -> [(t, delta_xy_norm, dx, dy)]."""
    out = []
    for i in range(1, len(t)):
        if counter[i] != counter[i - 1]:
            out.append((float(t[i]), float(np.hypot(dx[i], dy[i])), float(dx[i]), float(dy[i])))
    return out


def share_true(ts, flag):
    if len(ts) < 2:
        return None
    dt = np.diff(ts)
    f = flag[:-1].astype(bool)
    tot = float(dt.sum())
    return float(dt[f].sum() / tot) if tot > 0 else None


def report(path):
    out = []
    p = out.append
    u = ULog(path, TOPICS, disable_str_exceptions=True)
    t0 = np.int64(u.start_timestamp)
    D = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    last_ts = max([float(d['timestamp'][-1] - t0) / 1e6 for d in D.values() if len(d['timestamp'])] or [0.0])
    p('LOG file=%s size_bytes=%d length_s=%s' % (os.path.basename(path), os.path.getsize(path), fmt(last_ts, 1)))
    absent = [n for n in TOPICS if n not in D]
    p('TOPICS_ABSENT %s' % (','.join(absent) or 'none'))
    p('HOVER_THRUST_ESTIMATE in_log=%s msgs=%d' % ('yes' if 'hover_thrust_estimate' in D else 'no',
                                                    len(D['hover_thrust_estimate']['timestamp']) if 'hover_thrust_estimate' in D else 0))
    periods = []
    st = D.get('vehicle_status')
    if st is not None:
        ts = seconds(st, t0)
        periods = armed_periods(ts, st['arming_state'] == 2)
        p('ARMED_PERIODS %d' % len(periods))
        for i, (a, b) in enumerate(periods):
            nav = st['nav_state'][(ts >= a) & (ts <= b)]
            p('ARMED %d from=%s to=%s dur_s=%s nav_states=%s' % (i + 1, fmt(a, 1), fmt(b, 1), fmt(b - a, 1),
                                                                 ','.join(str(int(v)) for v in sorted(set(nav.tolist())))))
    else:
        p('ARMED_PERIODS unknown (no vehicle_status)')
    lp = D.get('vehicle_local_position')
    tl = seconds(lp, t0) if lp is not None else None
    if lp is not None and 'dist_bottom' in lp:
        for i, (a, b) in enumerate(periods):
            sel = (tl >= a) & (tl <= b)
            if sel.any():
                db = lp['dist_bottom'][sel]
                p('DIST_BOTTOM_MAX armed=%d max_m=%s (HTE starts only after dist_bottom > 1.0 m, T41)' % (i + 1, fmt(float(np.nanmax(db)))))
    elif lp is None:
        p('DIST_BOTTOM_MAX unknown (no vehicle_local_position)')
    # EKF vision
    ev = D.get('estimator_aid_src_ev_pos')
    if ev is not None:
        key = 'timestamp_sample' if 'timestamp_sample' in ev else 'timestamp'
        tev = seconds(ev, t0, key)
        p('EV_POS samples=%d' % len(tev))
        if len(tev) > 2 and (len(tev) - 1) / max(float(tev[-1] - tev[0]), 1e-9) < 5.0:
            p('EV_POS_NOTE log rate below 5 Hz: the profile thins the vision topic, so pauses over 0.4 s below may be gaps in logging, not in the data')
        scopes = periods or [(0.0, last_ts)]
        for i, (a, b) in enumerate(scopes):
            tt = tev[(tev >= a) & (tev <= b)]
            ps = pauses(tt)
            p('EV_PAUSES_OVER_%ss scope=%s from=%s to=%s count=%d samples=%d' % (fmt(PAUSE_S, 1), 'armed %d' % (i + 1) if periods else 'whole log',
                                                                                  fmt(a, 1), fmt(b, 1), len(ps), len(tt)))
            for s, e, ln in sorted(ps, key=lambda x: -x[2])[:8]:
                p('  pause start=%s end=%s length_s=%s' % (fmt(s, 2), fmt(e, 2), fmt(ln, 2)))
        # whole log too, if there were armed periods (disarmed stand tests)
        if periods:
            ps = pauses(tev)
            p('EV_PAUSES_OVER_%ss scope=whole log count=%d samples=%d' % (fmt(PAUSE_S, 1), len(ps), len(tev)))
            for s, e, ln in sorted(ps, key=lambda x: -x[2])[:8]:
                p('  pause start=%s end=%s length_s=%s' % (fmt(s, 2), fmt(e, 2), fmt(ln, 2)))
        if len(tev) > 2:
            span = float(tev[-1] - tev[0])
            p('EV_POS_RATE_HZ mean=%s (samples between first and last: %d over %s s; the log profile may thin it out)' % (
                fmt((len(tev) - 1) / span if span > 0 else 0.0, 2), len(tev), fmt(span, 1)))
    else:
        p('EV_POS (no estimator_aid_src_ev_pos in this log: the profile may not log it)')
    if lp is not None and 'xy_reset_counter' in lp:
        rs = counter_changes(tl, lp['xy_reset_counter'], lp['delta_xy[0]'], lp['delta_xy[1]']) if 'delta_xy[0]' in lp else []
        p('XY_RESETS count=%d (vehicle_local_position.xy_reset_counter changes)' % len(rs))
        for t, n, dx, dy in rs[:30]:
            armed_flag = any(a <= t <= b for a, b in periods)
            h = float(np.interp(t, tl, lp['dist_bottom'])) if 'dist_bottom' in lp else float('nan')
            p('  reset t=%s size_m=%s dx=%s dy=%s armed=%s dist_bottom=%s' % (fmt(t, 2), fmt(n), fmt(dx), fmt(dy), 'yes' if armed_flag else 'no', fmt(h, 2)))
        if len(rs) > 30:
            p('  ... and %d more resets not listed' % (len(rs) - 30))
        if rs:
            big = sorted(rs, key=lambda x: -x[1])[:3]
            p('XY_RESETS_LARGEST %s' % ' '.join('%s@%s' % (fmt(n), fmt(t, 1)) for t, n, _dx, _dy in big))
    else:
        p('XY_RESETS (no xy_reset_counter in vehicle_local_position)')
    fl = D.get('estimator_status_flags')
    if fl is not None:
        tf = seconds(fl, t0)
        for name in ('cs_ev_pos', 'cs_ev_vel', 'cs_ev_hgt', 'cs_ev_yaw', 'cs_opt_flow', 'cs_gps'):
            if name in fl:
                sh = share_true(tf, fl[name])
                p('EKF_FLAG %s true_share=%s' % (name, fmt(sh, 3) if sh is not None else 'n/a'))
    else:
        p('EKF_FLAGS (no estimator_status_flags)')
    # landing chain
    ld = D.get('vehicle_land_detected')
    if ld is not None and periods and lp is not None:
        tld = seconds(ld, t0)
        for i, (a, b) in enumerate(periods):
            sel = (tl >= a) & (tl <= b)
            if not sel.any() or 'dist_bottom' not in lp:
                continue
            tt = tl[sel]; db = lp['dist_bottom'][sel]
            k = int(np.nanargmax(db))
            t_top = float(tt[k])
            db_end = float(db[-1])
            after = np.flatnonzero((tt >= t_top) & (db <= db_end + 0.03))
            t_floor = float(tt[after[0]]) if len(after) else None
            if t_floor is None:
                p('LANDING armed=%d floor level not found (dist_bottom did not come back to its final reading)' % (i + 1))
                continue

            def first(flag):
                m = (tld >= t_floor) & (ld[flag] == 1) if flag in ld else None
                if m is None or not m.any():
                    return None
                return float(tld[np.flatnonzero(m)[0]])
            gc, ml, lnd = first('ground_contact'), first('maybe_landed'), first('landed')

            def rel(x):
                return fmt(x - t_floor, 2) if x is not None else 'n/a'
            p('LANDING armed=%d floor_reached_at=%s s (first time after the max height with dist_bottom within 0.03 m of the final reading %s m); '
              'seconds after it: ground_contact=%s maybe_landed=%s landed=%s disarm=%s' % (
                  i + 1, fmt(t_floor, 1), fmt(db_end, 2), rel(gc), rel(ml), rel(lnd), fmt(b - t_floor, 2)))
    elif ld is None:
        p('LANDING (no vehicle_land_detected)')
    bat = D.get('battery_status')
    if bat is not None and len(bat['timestamp']):
        v = bat['voltage_v']
        extra = []
        if 'cell_count' in bat:
            extra.append('cell_count=%s' % ','.join(str(int(c)) for c in sorted(set(bat['cell_count'].tolist()))))
        if 'warning' in bat:
            extra.append('warning_max=%d warning_values=%s' % (int(bat['warning'].max()), ','.join(str(int(c)) for c in sorted(set(bat['warning'].tolist())))))
        if 'connected' in bat:
            extra.append('connected_share=%s' % fmt(float(bat['connected'].astype(float).mean()), 2))
        p('BATTERY samples=%d voltage_v min=%s max=%s mean=%s %s' % (len(v), fmt(float(v.min()), 2), fmt(float(v.max()), 2), fmt(float(v.mean()), 2), ' '.join(extra)))
    else:
        p('BATTERY (no battery_status in this log)')
    return out


def main(argv):
    if not argv:
        print('usage: ulog_stand_report.py FILE.ulg [...]', file=sys.stderr)
        return 2
    rc = 0
    for f in argv:
        try:
            for line in report(f):
                print(line)
        except Exception as e:
            print('ERROR file=%s %r' % (f, e))
            rc = 2
        print('---')
    return rc


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
