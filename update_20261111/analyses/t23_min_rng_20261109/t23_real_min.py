#!/usr/bin/env python3
"""T23: on real 20EC ULogs, EKF dist_bottom (HAGL estimate) min in 0.5 s after each landed 1->0 edge,
next to the value just before. initTerrain() sets HAGL to EKF2_MIN_RNG at the in_air edge.
Run: python3 -I -B t23_real_min.py ULG..."""
import os, sys
import numpy as np
from pyulog import ULog
rows = []
for f in sys.argv[1:]:
    try:
        u = ULog(f, ["vehicle_land_detected", "vehicle_local_position"])
    except Exception:
        continue
    P = u.initial_parameters
    T = {d.name: d for d in u.data_list}
    if "vehicle_land_detected" not in T or "vehicle_local_position" not in T:
        continue
    t0 = u.start_timestamp
    lt = (T["vehicle_land_detected"].data["timestamp"] - t0) / 1e6
    lan = T["vehicle_land_detected"].data["landed"]
    lp = T["vehicle_local_position"]
    pt = (lp.data["timestamp"] - t0) / 1e6
    db = lp.data["dist_bottom"]
    for e in np.where((lan[:-1] == 1) & (lan[1:] == 0))[0][:3]:
        te = lt[e + 1]
        pre = db[(pt > te - 0.6) & (pt < te - 0.05)]
        w = (pt >= te - 0.05) & (pt < te + 0.5)
        if not len(pre) or not w.any():
            continue
        k = np.argmin(db[w])
        rows.append((os.path.basename(f), P.get("EKF2_HGT_REF"), P.get("EKF2_RNG_CTRL"), P.get("EKF2_MIN_RNG"),
                     te, np.median(pre), db[w][k], pt[w][k] - te, np.diff(pt[w]).mean() if w.sum() > 1 else 0))
for r in rows:
    print("%-34s HR=%s RC=%s MIN=%.2f t=%7.2f hagl_before=%.3f min_after=%.3f at +%.3f s (dt %.3f)" % r)
