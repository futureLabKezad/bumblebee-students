#!/usr/bin/env python3
"""T45: c8 flow runs (floor_near_off) - landing phases per run, read-only.
For each run: truth drift relative to the truth position at injection (as c8_new_eval), split into phases:
  A  landing start -> last EV fusion,  B  last EV fusion -> first flow fusion after it ("blind"),  C  flow -> touchdown;
EV during the hover and landing (fused share, obs - truth change = vision bias), EKF velocity resets (vxy_reset_counter,
delta_vxy) at flow start, EKF minus truth velocity in each phase, flow quality, tilt, heights.
Usage: ~/px4-venv/bin/python3 -B t49_phases.py OUT.jsonl RUN_TAG [...]"""
import glob, json, math, sys
import numpy as np
from pyulog import ULog

RUNS = sys.argv[2:]   # t49_phases (11.11): runs from the command line; was the T45 list:
# RUNS = ['c8r2h_flow_01', 'c8r2h_flow_02', 'c8r2h_flow_03', 'ctl_r2h_flow_01', 'c8r2g_flow_02', 'c8r2g_flow_03', 'c8r2g_flow_04']
B = '/work/goal_step5b_20261109/runs/'


def load(run):
    ev = json.load(open(B + run + '/c8_new_eval.json'))
    u = ULog(glob.glob(B + run + '/rootfs/log/*/' + ev['ulog'])[0])
    def g(n, mid=0):
        return next((d.data for d in u.data_list if d.name == n and d.multi_id == mid), None)
    return ev, u, g


def tt(d, key='timestamp'):
    return d[key] / 1e6


def interp(d, key, t, tkey='timestamp'):
    return float(np.interp(t, tt(d, tkey), d[key]))


def step(d, key, t):
    i = max(0, int(np.searchsorted(tt(d), t, side='right')) - 1)
    return d[key][i]


def main():
    out = open(sys.argv[1], 'w')
    for run in RUNS:
        ev, u, g = load(run)
        t0 = ev['t_inj_sim_s']
        tl = t0 + ev['landing_start_after_inj_s']
        td = t0 + ev['touchdown_after_inj_s']
        gt, lp, sf, att = g('vehicle_local_position_groundtruth'), g('vehicle_local_position'), g('estimator_status_flags'), g('vehicle_attitude')
        evp, of, vof = g('estimator_aid_src_ev_pos'), g('estimator_aid_src_optical_flow'), g('vehicle_optical_flow')
        ds = g('distance_sensor')
        p0 = np.array([interp(gt, 'x', t0), interp(gt, 'y', t0)])
        drift = lambda t: float(np.hypot(interp(gt, 'x', t) - p0[0], interp(gt, 'y', t) - p0[1]))
        hgt = lambda t: -interp(gt, 'z', t)
        # EV fusion samples
        ef_t = tt(evp)[evp['fused'] == 1]
        last_ev = float(ef_t[(ef_t <= td)].max()) if len(ef_t[(ef_t <= td)]) else None
        ev_land = ef_t[(ef_t >= tl) & (ef_t <= td)]
        ev_hover = ef_t[(ef_t >= t0 + 2) & (ef_t < tl)]
        # EV gaps during hover (> 0.4 s)
        hov = np.sort(ev_hover)
        gaps = np.diff(hov) if len(hov) > 1 else np.array([])
        # flow fusion
        of_f = tt(of)[of['fused'] == 1]
        flow_after = of_f[of_f > (last_ev if last_ev else tl)]
        first_flow = float(flow_after.min()) if len(flow_after) else None
        # velocity resets
        r = []
        rc = lp['vxy_reset_counter']
        for i in np.nonzero(np.diff(rc.astype(int)))[0]:
            t = tt(lp)[i + 1]
            if t0 - 1 <= t <= td + 0.5:
                r.append({'t_rel_land': round(t - tl, 3), 'delta_vxy': [round(float(lp['delta_vxy[0]'][i + 1]), 3), round(float(lp['delta_vxy[1]'][i + 1]), 3)]})
        pr = []
        prc = lp['xy_reset_counter']
        for i in np.nonzero(np.diff(prc.astype(int)))[0]:
            t = tt(lp)[i + 1]
            if t0 - 1 <= t <= td + 0.5:
                pr.append({'t_rel_land': round(t - tl, 3), 'delta_xy': [round(float(lp['delta_xy[0]'][i + 1]), 3), round(float(lp['delta_xy[1]'][i + 1]), 3)]})
        # velocity error EKF - truth, mean over phases; truth displacement over phases
        def phase(a, b):
            if a is None or b is None or b <= a:
                return None
            ts = np.arange(a, b, 0.02)
            ex = np.array([interp(lp, 'vx', t) - interp(gt, 'vx', t) for t in ts])
            ey = np.array([interp(lp, 'vy', t) - interp(gt, 'vy', t) for t in ts])
            dx = interp(gt, 'x', b) - interp(gt, 'x', a)
            dy = interp(gt, 'y', b) - interp(gt, 'y', a)
            tilt = []
            for t in ts[::5]:
                q = [step(att, 'q[%d]' % k, t) for k in range(4)]
                tilt.append(math.degrees(math.acos(max(-1, min(1, 1 - 2 * (q[1] ** 2 + q[2] ** 2))))))
            return {'dur': round(b - a, 3), 'truth_disp': [round(dx, 3), round(dy, 3)], 'truth_disp_norm': round(math.hypot(dx, dy), 3),
                    'vel_err_mean': [round(float(ex.mean()), 3), round(float(ey.mean()), 3)],
                    'vel_err_max_norm': round(float(np.max(np.hypot(ex, ey))), 3), 'tilt_max_deg': round(max(tilt), 1),
                    'h_start': round(hgt(a), 3), 'h_end': round(hgt(b), 3)}
        # vision bias: EV observation minus truth (change vs its value at injection, both NED-ish local)
        def evbias(a, b):
            m = (tt(evp) >= a) & (tt(evp) <= b)
            if not m.any():
                return None
            ts = tt(evp)[m]
            bx = evp['observation[0]'][m] - np.array([interp(gt, 'x', t) for t in ts])
            by = evp['observation[1]'][m] - np.array([interp(gt, 'y', t) for t in ts])
            return {'n': int(m.sum()), 'fused_share': round(float(evp['fused'][m].mean()), 3),
                    'bias_mean': [round(float(bx.mean()), 3), round(float(by.mean()), 3)],
                    'bias_sd': [round(float(bx.std()), 3), round(float(by.std()), 3)]}
        qual = None
        if vof is not None:
            m = (tt(vof) >= (first_flow or td)) & (tt(vof) <= td)
            if m.any():
                qual = {'median': float(np.median(vof['quality'][m])), 'min': int(vof['quality'][m].min()), 'n': int(m.sum())}
        lev = None if last_ev is None else round(last_ev - tl, 3)
        rec = {'run': run, 'drift_td_eval': ev['drift_touchdown_m'], 'land_after_inj': ev['landing_start_after_inj_s'],
               'td_after_land': round(td - tl, 3), 'drift_at_land': round(drift(tl), 3), 'drift_at_last_ev': None if last_ev is None else round(drift(last_ev), 3),
               'drift_at_first_flow': None if first_flow is None else round(drift(first_flow), 3), 'drift_td': round(drift(td), 3),
               'last_ev_rel_land': lev, 'h_at_last_ev': None if last_ev is None else round(hgt(last_ev), 3),
               'first_flow_rel_land': None if first_flow is None else round(first_flow - tl, 3),
               'blind_s': None if (first_flow is None or last_ev is None) else round(first_flow - last_ev, 3),
               'ev_fused_hover_share_per_s': round(len(ev_hover) / max(1e-6, (tl - t0 - 2)), 2),
               'ev_hover_gaps_gt_0p4': int((gaps > 0.4).sum()), 'ev_hover_gap_max': round(float(gaps.max()), 3) if len(gaps) else None,
               'ev_fused_in_landing': int(len(ev_land)),
               'phaseA_land_to_lastev': phase(tl, last_ev if last_ev and last_ev > tl else None),
               'phaseB_blind': phase(max(tl, last_ev) if last_ev else tl, first_flow),
               'phaseC_flow_to_td': phase(first_flow, td),
               'vel_resets': r, 'pos_resets': pr,
               'evbias_hover_last10s': evbias(tl - 10, tl), 'evbias_landing': evbias(tl, td),
               'flow_quality_C': qual}
        out.write(json.dumps(rec) + '\n')
        print(run, 'drift_td', rec['drift_td'], 'last_ev', lev, 'h', rec['h_at_last_ev'], 'blind', rec['blind_s'], 'resets', r[-3:])
    out.close()


if __name__ == '__main__':
    main()
