#!/usr/bin/env python3
"""T42 (READ ONLY): summary of out/ev_gaps.jsonl. Per in-air EV pause (> 0.4 s, the EKF stops EV fusion after
2 x EV_MAX_INTERVAL): its reset at the resume, and the split reset = EV-EKF = vision part - EKF drift part.
Prints a per-run line and an overall table; writes out/resets_table.tsv. Usage: t42_table.py out/ev_gaps.jsonl"""
import json, sys
import numpy as np

rows = []
for line in open(sys.argv[1]):
    d = json.loads(line)
    for a in d['arms']:
        for g in a['gaps']:
            if g['len'] <= 0.4:
                continue
            r = g['reset'][0] if g['reset'] else None
            rows.append(dict(run=d['run'], to_from_arm=g['to_from_arm'], len=g['len'], h=g['h_truth_end'], air=g['in_air'],
                             of=g['of_fused'], reset=r[1] if r else None, reset_vec=r[2] if r else None,
                             drift=g['ekf_drift_vec'], ev=g['ev_err_vec'], evmekf=g['ev_minus_ekf_vec']))
        big = [m for m in a['moves_gt_0p08_lt_0p2s']]
        print(d['run'], 'moves>0.08/<0.2s:', [(m['from'], m['move'], m['h_truth'], [r[1] for r in m['reset_in_move']]) for m in big])
with open('out/resets_table.tsv', 'w') as f:
    f.write('run\tresume_s_from_arm\tpause_s\th_truth_m\tin_air\tflow_fused\treset_m\tEV-EKF_m\tEKF_drift_m\tEV_err_m\n')
    for r in rows:
        f.write('%s\t%.2f\t%.2f\t%.3f\t%s\t%s\t%s\t%.3f\t%.3f\t%.3f\n' % (
            r['run'], r['to_from_arm'], r['len'], r['h'], r['air'], r['of'], r['reset'],
            np.hypot(*r['evmekf']), np.hypot(*r['drift']), np.hypot(*r['ev'])))
air = [r for r in rows if r['air'] and r['reset'] is not None]
print('\nin-air pauses > 0.4 s:', len([r for r in rows if r['air']]), 'with a reset at the resume:', len(air))
R = np.array([r['reset'] for r in air]); D = np.array([np.hypot(*r['drift']) for r in air]); E = np.array([np.hypot(*r['ev']) for r in air])
L = np.array([r['len'] for r in air]); H = np.array([r['h'] for r in air])
P = np.array([np.hypot(*r['evmekf']) for r in air])
print('reset m: median %.3f p90 %.3f max %.3f; >0.10: %d' % (np.median(R), np.percentile(R, 90), R.max(), (R > 0.10).sum()))
print('reset vs EV-EKF just after resume: median |diff| %.3f m' % np.median(np.abs(R - P)))
print('EKF drift (vs truth) part: median %.3f max %.3f | vision error part: median %.3f max %.3f' % (np.median(D), D.max(), np.median(E), E.max()))
# which part dominates (projection on the reset direction)
dom = []
for r in air:
    v = np.array(r['reset_vec']); n = np.linalg.norm(v)
    if n < 1e-6:
        continue
    u = v / n
    dom.append((float(np.dot(np.array(r['ev']), u)), float(-np.dot(np.array(r['drift']), u)), n))
dom = np.array(dom)
print('along the reset: vision part median %.3f, EKF-drift part median %.3f (sum ~ reset)' % (np.median(dom[:, 0]), np.median(dom[:, 1])))
big = dom[dom[:, 2] > 0.08]
print('resets > 0.08 (%d): vision part median %.3f, drift part median %.3f' % (len(big), np.median(big[:, 0]), np.median(big[:, 1])))
print('corr reset~pause length %.2f, reset~height %.2f, drift~pause %.2f' % (np.corrcoef(R, L)[0, 1], np.corrcoef(R, H)[0, 1], np.corrcoef(D, L)[0, 1]))
for lo, hi in ((0, 0.25), (0.25, 0.45), (0.45, 0.7), (0.7, 2)):
    m = (H >= lo) & (H < hi)
    if m.any():
        print('h %.2f-%.2f: n %d reset median %.3f max %.3f | vision part median %.3f | drift median %.3f | pause median %.1f s' % (
            lo, hi, m.sum(), np.median(R[m]), R[m].max(), np.median(E[m]), np.median(D[m]), np.median(L[m])))
