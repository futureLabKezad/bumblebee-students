#!/usr/bin/env python3
"""august_logs.py - numbers for criteria C3-C4 from the August 2026 logs of bumblebee-20ec (Claude, 05.11.2026, goal step 2).

READ ONLY: reads .ulg files, writes one JSON + one text file into OUT_DIR (refuses to overwrite).
Usage: python -I august_logs.py ULOG_DIR OUT_DIR
Definitions (fixed before looking at the numbers):
  h          = height above the ground at take-off. If the EKF used the rangefinder in air (cs_rng_hgt or
               cs_rng_terrain > 50 % of in-air samples): vehicle_local_position.dist_bottom minus its median on the
               ground in the 2 s before lift-off (the EKF z drifts by up to ~0.3 m in a 5 min flight). Otherwise
               from vehicle_local_position.z the same way. Both are kept in the output (h_source says which).
  in air     = armed and vehicle_land_detected.landed == False.
  hover      = in air, h >= 0.5 m, |vz| <= 0.15 m/s, tilt <= 10 deg, horizontal speed <= 0.5 m/s (this last
               condition only if the EKF had a valid horizontal velocity in >= 50 % of the in-air time),
               in a run of at least 3 s (0.5 s trimmed at both ends).
  hover thrust = -vehicle_thrust_setpoint.xyz[2] in hover; also hover_thrust_estimate.hover_thrust (valid, in air).
  att error  = attitude setpoint (q_d, interpolated to the attitude time) minus attitude (q), roll and pitch, in hover.
  rise 0->1 m = time between the upward crossings of h = 0.05 m and h = 1.00 m (linear interpolation), same climb.
  touchdown  = last downward crossing of h = 0.05 m before the motors stop; motors stop = disarm or kill switch
               (actuator_armed.armed false or manual_lockdown/lockdown true), whichever is first.
  sensor period from 1 Hz logging: logged dt = 1 s +/- one sensor period, so period ~ (max dt - min dt) / 2.
"""
import json
import math
import os
import re
import sys

import numpy as np
from pyulog import ULog

TOPICS = ['vehicle_status', 'vehicle_land_detected', 'vehicle_local_position', 'vehicle_attitude',
          'vehicle_attitude_setpoint', 'vehicle_thrust_setpoint', 'hover_thrust_estimate', 'actuator_armed',
          'distance_sensor', 'sensor_optical_flow', 'vehicle_optical_flow', 'estimator_status_flags',
          'estimator_aid_src_ev_pos', 'estimator_aid_src_ev_hgt', 'estimator_aid_src_ev_yaw',
          'estimator_aid_src_optical_flow', 'estimator_aid_src_rng_hgt', 'telemetry_status', 'timesync_status',
          'manual_control_setpoint', 'takeoff_status', 'trajectory_setpoint', 'offboard_control_mode']
NAV = {0: 'MANUAL', 1: 'ALTCTL', 2: 'POSCTL', 3: 'MISSION', 4: 'LOITER', 5: 'RTL', 10: 'ACRO', 12: 'DESCEND',
       13: 'TERMINATION', 14: 'OFFBOARD', 15: 'STAB', 17: 'TAKEOFF', 18: 'LAND', 20: 'PRECLAND'}
PARAMS_OF_INTEREST = ['EKF2_EV_CTRL', 'EKF2_HGT_REF', 'EKF2_RNG_CTRL', 'EKF2_OF_CTRL', 'EKF2_EV_DELAY',
                      'SER_TEL1_BAUD', 'MAV_0_MODE', 'MAV_0_RATE', 'BAT1_SOURCE', 'COM_SPOOLUP_TIME',
                      'MPC_TKO_SPEED', 'MPC_TKO_RAMP_T', 'MPC_Z_VEL_MAX_UP', 'MPC_Z_V_AUTO_UP', 'MPC_LAND_SPEED',
                      'MPC_XY_VEL_MAX', 'MPC_ACC_HOR', 'MPC_THR_HOVER', 'MPC_USE_HTE', 'COM_DISARM_LAND',
                      'MC_ROLLRATE_P', 'MC_PITCHRATE_P', 'MC_ROLLRATE_I', 'MC_PITCHRATE_I', 'MC_ROLLRATE_D',
                      'MC_PITCHRATE_D', 'MC_ROLL_P', 'MC_PITCH_P', 'MC_BAT_SCALE_EN', 'SENS_FLOW_RATE']


def topic(u, name, mid=0):
    for d in u.data_list:
        if d.name == name and d.multi_id == mid:
            return d.data
    return None


def euler(q0, q1, q2, q3):
    roll = np.arctan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2))
    pitch = np.arcsin(np.clip(2 * (q0 * q2 - q3 * q1), -1, 1))
    return roll, pitch


def step_at(t_src, v_src, t):
    """value of a step signal (last message at or before t)."""
    i = np.searchsorted(t_src, t, side='right') - 1
    out = np.where(i >= 0, v_src[np.clip(i, 0, None)], v_src[0])
    return out


def runs(mask, t, min_len, max_gap=0.15, trim=0.5):
    """list of (t0, t1) of runs where mask is true for >= min_len s."""
    out = []
    start = None
    last = None
    for ti, m in zip(t, mask):
        if m:
            if start is None or (last is not None and ti - last > max_gap):
                if start is not None and last - start >= min_len:
                    out.append((start + trim, last - trim))
                start = ti
            last = ti
        else:
            if start is not None and last - start >= min_len:
                out.append((start + trim, last - trim))
            start = None
    if start is not None and last - start >= min_len:
        out.append((start + trim, last - trim))
    return out


def in_windows(t, wins):
    m = np.zeros(len(t), bool)
    for a, b in wins:
        m |= (t >= a) & (t <= b)
    return m


def crossings(t, h, level, up=True):
    out = []
    for i in range(1, len(h)):
        a, b = h[i - 1], h[i]
        if (up and a < level <= b) or ((not up) and a > level >= b):
            f = (level - a) / (b - a) if b != a else 0.0
            out.append(float(t[i - 1] + f * (t[i] - t[i - 1])))
    return out


def stats(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return None
    return {'n': int(len(x)), 'median': float(np.median(x)), 'mean': float(np.mean(x)), 'std': float(np.std(x)),
            'p05': float(np.percentile(x, 5)), 'p25': float(np.percentile(x, 25)),
            'p75': float(np.percentile(x, 75)), 'p95': float(np.percentile(x, 95)),
            'min': float(np.min(x)), 'max': float(np.max(x))}


def params_at(u, t_us):
    p = {k: u.initial_parameters.get(k) for k in PARAMS_OF_INTEREST}
    for ts, name, val in u.changed_parameters:
        if name in p and ts <= t_us:
            p[name] = val
    return p


def analyze(path):
    u = ULog(path, TOPICS, disable_str_exceptions=True)
    t0 = u.start_timestamp
    S = lambda a: (np.asarray(a, float) - t0) / 1e6  # noqa: E731
    res = {'file': os.path.basename(path), 'duration_s': (u.last_timestamp - t0) / 1e6}
    res['params_initial'] = {k: u.initial_parameters.get(k) for k in PARAMS_OF_INTEREST}
    res['param_changes_in_log'] = [[round((ts - t0) / 1e6, 2), n, v] for ts, n, v in u.changed_parameters
                                   if n in PARAMS_OF_INTEREST]
    vs = topic(u, 'vehicle_status')
    if vs is None:
        res['error'] = 'no vehicle_status'
        return res
    tvs = S(vs['timestamp'])
    armed = vs['arming_state'] == 2
    nav = vs['nav_state']
    # mode sequence while armed
    seq = []
    for ti, a, n in zip(tvs, armed, nav):
        if a and (not seq or seq[-1][1] != NAV.get(int(n), str(int(n)))):
            seq.append([round(float(ti), 1), NAV.get(int(n), str(int(n)))])
    res['modes_armed'] = seq
    aa = topic(u, 'actuator_armed')
    taa = S(aa['timestamp'])
    lock = aa['armed'].astype(bool) & ((aa['manual_lockdown'] > 0) | (aa['lockdown'] > 0))
    run = aa['armed'].astype(bool) & ~lock
    # motors-stop events: run -> not run
    stops = [float(taa[i]) for i in range(1, len(taa)) if run[i - 1] and not run[i]]
    starts = [float(taa[i]) for i in range(1, len(taa)) if (not run[i - 1]) and run[i]]
    if len(run) and run[0]:
        starts = [float(taa[0])] + starts
    res['motor_run_intervals'] = [[round(a, 2), round(next((s for s in stops if s > a), float('nan')), 2)] for a in starts]
    res['kill_switch_used'] = bool(np.any(aa['manual_lockdown'] > 0))
    ld = topic(u, 'vehicle_land_detected')
    tld = S(ld['timestamp'])
    lp = topic(u, 'vehicle_local_position')
    tlp = S(lp['timestamp'])
    z = lp['z'].astype(float)
    vz = lp['vz'].astype(float)
    vxy = np.hypot(lp['vx'].astype(float), lp['vy'].astype(float))
    db = np.where(lp['dist_bottom_valid'] > 0, lp['dist_bottom'].astype(float), np.nan)
    armed_lp = step_at(tvs, armed, tlp).astype(bool)
    landed_lp = step_at(tld, ld['landed'], tlp).astype(bool)
    in_air = armed_lp & ~landed_lp
    res['armed_s'] = float(np.sum(np.diff(tlp)[armed_lp[1:]])) if len(tlp) > 1 else 0.0
    res['in_air_s'] = float(np.sum(np.diff(tlp)[in_air[1:]])) if len(tlp) > 1 else 0.0
    # ground reference per take-off: median z (and dist_bottom) during the 2 s before each air period
    db_raw = lp['dist_bottom'].astype(float)
    h_z = np.full(len(tlp), np.nan)
    h_db = np.full(len(tlp), np.nan)
    air_runs = runs(in_air, tlp, 0.5, max_gap=0.3, trim=0.0)
    z_ground = None
    db_ground = None
    grounds = []
    for a, b in air_runs:
        pre = (tlp >= a - 2.5) & (tlp < a - 0.2) & ~in_air
        if np.sum(pre) >= 3:
            z_ground = float(np.median(z[pre]))
            db_ground = float(np.median(db_raw[pre]))
        if z_ground is None:
            z_ground = float(np.median(z[tlp < a])) if np.any(tlp < a) else float(z[0])
            db_ground = float(np.median(db_raw[tlp < a])) if np.any(tlp < a) else float(db_raw[0])
        grounds.append([round(a, 1), round(z_ground, 3), round(db_ground, 3)])
        seg = (tlp >= a - 3.0) & (tlp <= b + 10.0)
        h_z[seg] = z_ground - z[seg]
        h_db[seg] = db_raw[seg] - db_ground
    res['air_periods'] = [[round(a, 1), round(b, 1)] for a, b in air_runs]
    res['ground_ref_t_z_db'] = grounds
    fl0 = topic(u, 'estimator_status_flags')
    rng_used = 0.0
    if fl0 is not None and len(tlp):
        tf0 = S(fl0['timestamp'])
        air_f0 = step_at(tlp, in_air, tf0).astype(bool)
        if np.any(air_f0):
            rng_used = float(np.mean(fl0['cs_rng_hgt'][air_f0] | fl0['cs_rng_terrain'][air_f0]))
    use_db = rng_used > 0.5 and np.any(np.isfinite(h_db))
    h = h_db if use_db else h_z
    res['h_source'] = 'dist_bottom (range)' if use_db else 'local z'
    res['h_max'] = float(np.nanmax(h)) if np.any(np.isfinite(h)) else None
    res['h_z_max'] = float(np.nanmax(h_z)) if np.any(np.isfinite(h_z)) else None
    res['h_db_max'] = float(np.nanmax(h_db)) if np.any(np.isfinite(h_db)) else None
    res['dist_bottom_valid_frac'] = round(float(np.mean(lp['dist_bottom_valid'] > 0)), 3)
    res['xy_valid_frac_in_air'] = round(float(np.mean(lp['xy_valid'][in_air] > 0)), 3) if np.any(in_air) else None
    res['v_xy_valid_frac_in_air'] = round(float(np.mean(lp['v_xy_valid'][in_air] > 0)), 3) if np.any(in_air) else None
    ds = topic(u, 'distance_sensor')
    if ds is not None and len(tlp):
        tds_ = S(ds['timestamp'])
        dbi = np.interp(tds_, tlp, db_raw)
        res['dist_bottom_minus_range_m'] = stats(dbi - ds['current_distance'].astype(float))
        on_ground = ~step_at(tlp, in_air, tds_).astype(bool)
        res['range_on_ground_m'] = stats(ds['current_distance'][on_ground])
    if 'nav_state_user_intention' in vs:
        diff = vs['nav_state'] != vs['nav_state_user_intention']
        res['mode_fallbacks'] = sorted(set('%s->%s' % (NAV.get(int(a), a), NAV.get(int(b), b))
                                           for a, b, d in zip(vs['nav_state_user_intention'], vs['nav_state'], diff) if d))
    if 'failsafe' in vs:
        res['failsafe_frac_armed'] = round(float(np.mean(vs['failsafe'][armed])), 3) if np.any(armed) else 0.0
    keys = ('position', 'flow', 'failsafe', 'kill', 'disarm', 'arm', 'land', 'takeoff', 'offboard', 'estimat',
            'height', 'range', 'fallback', 'lockdown', 'mode', 'ekf', 'vision', 'odometry')
    res['messages'] = [[round((m.timestamp - t0) / 1e6, 1), m.message] for m in u.logged_messages
                       if any(k in m.message.lower() for k in keys)][:60]
    # attitude
    att = topic(u, 'vehicle_attitude')
    tat = S(att['timestamp'])
    r, p = euler(att['q[0]'], att['q[1]'], att['q[2]'], att['q[3]'])
    tilt_lp = np.degrees(np.interp(tlp, tat, np.hypot(r, p)))
    vxy_ok = lp['v_xy_valid'] > 0
    res['hover_uses_vxy'] = bool(np.any(in_air) and np.mean(vxy_ok[in_air]) >= 0.5)
    vxy_cond = (vxy <= 0.5) if res['hover_uses_vxy'] else np.ones(len(tlp), bool)
    hover_mask = in_air & (h >= 0.5) & (np.abs(vz) <= 0.15) & vxy_cond & (tilt_lp <= 10)
    hover_mask &= np.isfinite(h)
    wins = runs(hover_mask, tlp, 3.0)
    res['hover_windows'] = [[round(a, 1), round(b, 1)] for a, b in wins]
    res['hover_s'] = float(sum(b - a for a, b in wins))
    if wins:
        hm = in_windows(tlp, wins)
        res['hover_h'] = stats(h[hm])
        res['hover_vz_std'] = float(np.std(vz[hm]))
        res['hover_vxy'] = stats(vxy[hm])
        res['hover_modes'] = sorted(set(NAV.get(int(n), str(int(n))) for n in step_at(tvs, nav, tlp[hm])))
        ts = topic(u, 'vehicle_thrust_setpoint')
        tts = S(ts['timestamp'])
        thr = -ts['xyz[2]'].astype(float)
        res['hover_thrust_sp'] = stats(thr[in_windows(tts, wins)])
        # thrust per window: early vs late (battery sag, no voltage compensation)
        res['hover_thrust_sp_by_window'] = [[round(a, 1), round(b, 1), round(float(np.median(thr[(tts >= a) & (tts <= b)])), 4)]
                                            for a, b in wins if np.any((tts >= a) & (tts <= b))]
        sp = topic(u, 'vehicle_attitude_setpoint')
        tsp = S(sp['timestamp'])
        rs, ps = euler(sp['q_d[0]'], sp['q_d[1]'], sp['q_d[2]'], sp['q_d[3]'])
        am = in_windows(tat, wins)
        er = np.degrees(np.interp(tat[am], tsp, rs) - r[am])
        ep = np.degrees(np.interp(tat[am], tsp, ps) - p[am])
        res['att_err_roll_deg'] = stats(er)
        res['att_err_pitch_deg'] = stats(ep)
        res['att_roll_deg'] = stats(np.degrees(r[am]))
        res['att_pitch_deg'] = stats(np.degrees(p[am]))
    hte = topic(u, 'hover_thrust_estimate')
    if hte is not None:
        th = S(hte['timestamp'])
        ok = (hte['valid'] > 0) & step_at(tlp, in_air, th).astype(bool)
        res['hte_in_air'] = stats(hte['hover_thrust'][ok])
        if wins:
            res['hte_hover'] = stats(hte['hover_thrust'][in_windows(th, wins)])
    # climbs 0.05 -> 1.0 m
    climbs = []
    hh = np.where(np.isfinite(h), h, -1.0)
    ups05 = crossings(tlp, hh, 0.05, True)
    for tu in ups05:
        later = (tlp > tu)
        idx = np.where(later)[0]
        t1 = None
        for i in idx:
            if hh[i] < 0.05:
                break
            if hh[i] >= 1.0:
                c = crossings(tlp[i - 1:i + 1], hh[i - 1:i + 1], 1.0, True)
                t1 = c[0] if c else float(tlp[i])
                break
        if t1 is not None:
            c05 = crossings(tlp, hh, 0.5, True)
            t05 = next((c for c in c05 if tu < c <= t1), None)
            pr = params_at(u, int(tu * 1e6 + t0))
            win = (tlp >= tu - 0.11) & (tlp <= t1 + 0.11)
            zr = lp['z_reset_counter'][win]
            climbs.append({'t_005': round(tu, 2), 't_100': round(t1, 2), 'rise_005_100_s': round(t1 - tu, 2),
                           'z_reset_during': bool(len(zr) and zr.max() != zr.min()),
                           'rise_005_050_s': round(t05 - tu, 2) if t05 else None,
                           'mode': NAV.get(int(step_at(tvs, nav, np.array([tu]))[0]), '?'),
                           'MPC_TKO_SPEED': pr['MPC_TKO_SPEED'], 'MPC_Z_VEL_MAX_UP': pr['MPC_Z_VEL_MAX_UP'],
                           'COM_SPOOLUP_TIME': pr['COM_SPOOLUP_TIME'],
                           'vz_max_up': float(-np.min(vz[win])) if np.any(win) else None})
    res['climbs_0_to_1m'] = climbs
    # touchdown -> motors stop
    tds = []
    downs = crossings(tlp, hh, 0.05, False)
    for ts_ in stops:
        prev = [d for d in downs if d <= ts_ and ts_ - d < 60]
        hs = float(np.interp(ts_, tlp, hh))
        landed_t = None
        if prev:
            td = prev[-1]
            lt = [float(x) for x, l in zip(tld, ld['landed']) if l and x >= td - 0.5 and x <= ts_ + 0.5]
            landed_t = lt[0] if lt else None
        kill = bool(np.any((aa['manual_lockdown'] > 0) & (np.abs(taa - ts_) < 0.3)))
        mode = NAV.get(int(step_at(tvs, nav, np.array([ts_ - 0.05]))[0]), '?')
        tds.append({'t_stop': round(ts_, 2), 'h_at_stop': round(hs, 3), 'kill_switch': kill, 'mode_before': mode,
                    't_touchdown': round(prev[-1], 2) if prev else None,
                    'stop_minus_touchdown_s': round(ts_ - prev[-1], 2) if prev else None,
                    'landed_minus_touchdown_s': round(landed_t - prev[-1], 2) if (prev and landed_t) else None})
    res['motor_stops'] = tds
    # sensors
    sens = {}
    for name in ('distance_sensor', 'sensor_optical_flow', 'vehicle_optical_flow'):
        d = topic(u, name)
        if d is None:
            continue
        t = d['timestamp'].astype(float) / 1e6
        dt = np.diff(t)
        e = {'n_logged': int(len(t)), 'logged_rate_hz': float((len(t) - 1) / (t[-1] - t[0])) if len(t) > 1 else None,
             'dt_logged': stats(dt)}
        if len(dt) > 5:
            e['period_est_ms_from_dt_range'] = float((np.percentile(dt, 99) - np.percentile(dt, 1)) / 2 * 1000)
            e['period_est_ms_from_dt_std'] = float(np.std(dt) * math.sqrt(6) * 1000)
        if 'integration_timespan_us' in d:
            its = d['integration_timespan_us'].astype(float)
            e['integration_timespan_ms'] = stats(its / 1000)
        if name == 'distance_sensor':
            e['device_ids'] = sorted(set(int(x) for x in d['device_id']))
            e['type'] = sorted(set(int(x) for x in d['type']))
            e['max_distance'] = float(np.max(d['max_distance']))
            e['signal_quality'] = stats(d['signal_quality'])
        if name == 'sensor_optical_flow':
            e['device_ids'] = sorted(set(int(x) for x in d['device_id']))
            e['quality'] = stats(d['quality'])
            e['latency_ms'] = stats((d['timestamp'].astype(float) - d['timestamp_sample'].astype(float)) / 1000)
        sens[name] = e
    res['sensors'] = sens
    # estimator flags: what was fused while in air
    fl = topic(u, 'estimator_status_flags')
    if fl is not None:
        tf = S(fl['timestamp'])
        air_f = step_at(tlp, in_air, tf).astype(bool) if len(tlp) else np.zeros(len(tf), bool)
        fr = {}
        for k in ('cs_ev_pos', 'cs_ev_hgt', 'cs_ev_vel', 'cs_ev_yaw', 'cs_opt_flow', 'cs_rng_hgt', 'cs_baro_hgt',
                  'cs_rng_terrain', 'cs_opt_flow_terrain', 'cs_mag_hdg', 'cs_mag_3d', 'cs_inertial_dead_reckoning',
                  'cs_gnd_effect', 'cs_rng_fault', 'cs_rng_kin_consistent'):
            if k in fl:
                fr[k] = round(float(np.mean(fl[k][air_f])) if np.any(air_f) else float(np.mean(fl[k])), 3)
        fr['basis'] = 'in air' if np.any(air_f) else 'whole log'
        res['ekf_fusion_fraction'] = fr
        if 'reset_count_pos_ne' in fl:
            res['ekf_resets'] = {k: int(fl[k][-1] - fl[k][0]) for k in fl if k.startswith('reset_count')}
    for name in ('estimator_aid_src_ev_pos', 'estimator_aid_src_ev_hgt', 'estimator_aid_src_optical_flow',
                 'estimator_aid_src_rng_hgt'):
        d = topic(u, name)
        if d is None:
            res.setdefault('aid_src', {})[name] = None
            continue
        e = {'n': int(len(d['timestamp']))}
        if 'fused' in d:
            e['fused_frac'] = round(float(np.mean(d['fused'])), 3)
        tr = [k for k in d if k.startswith('test_ratio')]
        if tr:
            e['test_ratio_max'] = round(float(np.nanmax(np.vstack([d[k] for k in tr]))), 2)
        if 'innovation_rejected' in d:
            e['rejected_frac'] = round(float(np.mean(d['innovation_rejected'])), 3)
        res.setdefault('aid_src', {})[name] = e
    tel = []
    for mid in range(4):
        d = topic(u, 'telemetry_status', mid)
        if d is None:
            continue
        e = {'mid': mid, 'rx_msgs': int(d['rx_message_count'][-1]) if 'rx_message_count' in d else None,
             'rx_rate_avg_max': float(np.max(d['rx_rate_avg'])) if 'rx_rate_avg' in d else None}
        if 'heartbeat_type_onboard_controller' in d:
            e['hb_onboard_frac'] = round(float(np.mean(d['heartbeat_type_onboard_controller'])), 3)
        tel.append(e)
    res['telemetry'] = tel
    res['timesync_msgs'] = int(len(topic(u, 'timesync_status')['timestamp'])) if topic(u, 'timesync_status') is not None else 0
    res['offboard_control_mode_msgs'] = int(len(topic(u, 'offboard_control_mode')['timestamp'])) if topic(u, 'offboard_control_mode') is not None else 0
    return res


def main():
    ulog_dir, out_dir = sys.argv[1], sys.argv[2]
    out_json = os.path.join(out_dir, 'august_logs_raw.json')
    if os.path.exists(out_json):
        print('STOP: refuse to overwrite ' + out_json)
        sys.exit(2)
    files = {}
    for f in os.listdir(ulog_dir):
        m = re.match(r'log_(\d+)_', f)
        if m:
            files[int(m.group(1))] = os.path.join(ulog_dir, f)
    ids = [i for i in sorted(files) if 0 <= i <= 148]
    out = {}
    for i in ids:
        try:
            out[i] = analyze(files[i])
        except Exception as ex:  # keep going, record the error
            out[i] = {'file': os.path.basename(files[i]), 'error': repr(ex)}
        print(i, out[i].get('error', ''), 'air %.1f s' % out[i].get('in_air_s', 0), flush=True)
    with open(out_json, 'w') as f:
        json.dump(out, f, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))
    print('wrote', out_json)


if __name__ == '__main__':
    main()
