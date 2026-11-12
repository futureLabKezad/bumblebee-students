import numpy as np
from pyulog import ULog
u = ULog("/work/goal_step5b_20261109/selftest/s04_copy/rootfs/log/2026-11-06/12_08_47.ulg")
t0 = u.start_timestamp
for d in u.data_list:
    if d.name == "vehicle_local_position_groundtruth": gt = d.data
t = (gt["timestamp"] - t0)/1e6
print(len(t), t[:3], t[-3:], np.all(np.diff(t) > 0))
for tt in [0, 5, 10, 20, 27.02, 30.9]:
    i = np.searchsorted(t, tt)
    print(tt, i, gt["x"][min(i, len(t)-1)], gt["y"][min(i, len(t)-1)], np.interp(tt, t, gt["y"]))
print(gt["x"].dtype, gt["y"][:5], gt["y"][-5:])
