# EXPERIMENT: pose fix V1.1 (keep doubtful poses with a large error, two fixes)

**Status: EXPERIMENT, not verified. Installed on the drone 20EC on 2026-11-19 as an
exception approved by the owner. Did NOT pass the Gazebo hover series C6 (10 runs in a
row). Do not use for students' flights. Never merge into `main` without a new decision
of the owner.**

## What it is
Two files against `feat/drone-image-r2j` (image r2j):

| File | r2j sha256 | V1.1 sha256 |
| --- | --- | --- |
| `drone/ros2_ws/src/bumblebee/src/python/aruco_detect.py` | `66f061ec…` | `81daec90eb32a61cccaefc623f9f685d8acbc402edcc7876140541be29c18472` |
| `drone/ros2_ws/src/bumblebee/src/python/vpe_fix.py` | `f0dc7c18…` | `39027fbd32cb0c19cae951cb19e2c37001faafc68d2d15f0a69aad36428b1f70` |

- **jd2** (inside `aruco_detect.py`): one joint pose from several markers (PnP over all
  visible map markers), the error taken from the fit.
- **V1**: a doubtful single-marker pose (over the detector speed filter, or over the
  xy-jump / speed limit of `vpe_fix`) is not dropped; it goes to the EKF with xy sigma
  1.0 m and without the 0.5 s pause.
- **V1.1** = V1 + two fixes:
  - D1: a doubtful frame is not smoothed and does not update the smoothing state, so a
    one-frame outlier no longer leaks into the next frames with the normal sigma 0.30 m;
  - D2: a doubtful frame does not update the yaw lock.
- `vpe_fix.py` is the same as in V1.

## What was checked
- Gazebo (6.1 detector frames/s, "as the drone"): V1 — C7 marker 10/10, C7 loop 10/10,
  C6 hover NOT passed (8 PASS, then a landing-chain failure on the floor; most likely not
  from V1). V1.1 — C6 x5: 5/5 PASS (information, not the 10-in-a-row series).
- Offline tests of D1/D2 (they fail on V1 and on deliberately broken copies), code pins.
- Two independent reviews (code: OK with notes; install package: OK).

## Not checked / known risks
- At a detector rate above 6.1 frames/s V1.1 was not tested. On the drone 20EC the
  detector ran at 8.5 frames/s with no marker in view (2026-11-19).
- A long false pose (more than ~2.5 s) was not tested; a doubtful pose with sigma 1.0 m
  passes the EKF gate (EKF2_EVP_GATE 5) of about 5 m.
- After a long series of doubtful frames the first normal frames may carry an old
  smoothed pose (model: up to ~0.27 m, V1: ~0.11 m).
- Needs `EKF2_EV_CTRL` without the height bit and `EKF2_EV_NOISE_MD = 0` in PX4.
- No autonomous flight of a real drone with this code yet.
