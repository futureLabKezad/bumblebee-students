# EXPERIMENT: pose fix jd2 (joint pose from several markers)

**Status: EXPERIMENT — NOT passed Gazebo series C6 (hover over one marker:
1 FAIL of 5 valid runs at 6.1 fps, series stopped at that FAIL; 5 FAIL of 10
at 7.6 fps). Not verified. Approved by the owner as an exception for the drone
20EC on 2026-11-18. Do not use for students' flights. Never merge into `main`.**

- Not installed on the drone yet: on 2026-11-18 the installation stopped after
  its first step (propellers off), and nothing else was installed up to
  2026-11-19.
- This branch is never to be merged into `main`.

## What it changes
One file against `feat/drone-image-r2j` (image r2j):
`drone/ros2_ws/src/bumblebee/src/python/aruco_detect.py`,
sha256 `b89bfb4327a184f5327ae83fa1e84752f0a2deac2a5a6ea5744bbb857072a915`
(r2j: `66f061ec…`). `vpe_fix.py` stays the r2j file (`f0dc7c18…`).

jd2 computes the drone's pose from several markers at once:
- With 2 or more map markers in the frame the detector solves **one** PnP over
  the corners of all used markers (a joint pose) instead of averaging the
  per-marker poses.
- The xy covariance of the joint pose comes from the fit:
  sigma >= 6 × RMS × depth / fx.
- RMS hysteresis: the joint pose is used from RMS <= 3.5 px and kept while
  RMS <= 5 px. When it is rejected, the mean pose is sent with sigma 0.30 m.
- New topic `/aruco_detect/map_mismatch`: `True` while the median joint RMS
  of the last 2 s is above 2.5 px ("the map does not match the floor").
- One marker in the frame: as in r2j.

## Gazebo results (simulation only, measured field map, detector throttled "as the drone")
| Test | Valid runs | PASS |
| --- | --- | --- |
| C6 hover over marker 0, 6.1 fps | 5 | 4 (series stopped at the first FAIL) |
| C6 hover over marker 0, 7.6 fps | 10 | 5 |
| C7 fly to a marker and land | 10 | 10 |
| C7 loop over markers | 10 | 10 |
| Control, old field map: C6, C7 marker, C7 loop | 3 each | 3 each |

The C6 FAILs are jumps of the PX4 position estimate (> 0.10 m) over the small
marker 0 (0.19 m). The project's analysis links them to pauses of the vision
pose while only that marker is in view (most likely; see `exp/posefix-v1`).

## Review
Independent code review (2026-11-17): no critical findings, nothing makes the
covariance tighter than r2j. Major note: the thresholds (3.5 / 5 px, 2.5 px)
were tuned in Gazebo and are not checked on the real camera. The reviewer
expects a joint RMS of about 3 px there, so `map_mismatch` may be on most of
the time and the 0.30 m fallback may be frequent.
