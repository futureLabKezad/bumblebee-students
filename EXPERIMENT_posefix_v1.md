# EXPERIMENT: pose fix V1 (keep doubtful poses with a large error)

**Status: EXPERIMENT — NOT passed Gazebo C6 (8 PASS then a landing-chain
failure on the floor, not from V1 — most likely); C7 marker 10/10, loop 10/10
at 6.1 fps; not tested at 7.6 fps; code not independently reviewed; not
installed on any drone.**

- Do not use for students' flights. This branch is never to be merged into `main`.

## What it changes
Two files against `feat/drone-image-r2j` (image r2j):

| File | r2j sha256 | V1 sha256 |
| --- | --- | --- |
| `drone/ros2_ws/src/bumblebee/src/python/aruco_detect.py` | `66f061ec…` | `890dafbfde99541a0742e26acc81e5f5a222390e7b8244e31fbbfc8f4ccc4338` |
| `drone/ros2_ws/src/bumblebee/src/python/vpe_fix.py` | `f0dc7c18…` | `39027fbd32cb0c19cae951cb19e2c37001faafc68d2d15f0a69aad36428b1f70` |

V1 = the jd2 detector (joint pose from several markers, see branch
`exp/posefix-jd2x`) plus "do not drop a doubtful pose, send it with a large
error":
- `aruco_detect.py`: a single-marker pose that the detector's speed filter used
  to drop is published with an xy sigma of 1.0 m (`_SUSPECT_SIGMA_XY`) and
  becomes the filter's reference. It is not counted as an outlier, so there is
  no 0.5 s pause after three of them. With several markers nothing changes.
- `vpe_fix.py`: a pose that used to be dropped for an xy jump > 0.15 m or a
  speed > 1.5 m/s goes on to PX4 with an xy sigma of at least 1.0 m. The z
  checks (floor, ceiling, z jump > 0.3 m) are unchanged.

Why: PX4 (1.16.1) resets its xy position to the first vision pose after a
vision pause longer than 0.4 s; the dropped poses made those pauses.

## Gazebo results (simulation only, measured field map, detector throttled to 6.1 fps "as the drone")
| Series | Result |
| --- | --- |
| C6 hover over marker 0, ×10 | NOT passed: runs 1–8 PASS; run 9 invalid (simulator real-time factor); run 10 FAIL on the floor after landing |
| C7 fly to a marker and land, ×10 | 10/10 in a row, landing 0.040–0.085 m from the marker |
| C7 loop over markers, ×10 | 10/10 in a row, landing 0.069–0.120 m from the marker |

- The C6 run 10 failure (most likely not from V1): at touchdown the optical-flow
  spike drops PX4's terrain estimate, PX4 switches optical flow off for 2 s, the
  position drifts by 0.30 m and PX4 reports `local_position_invalid`. The
  project's analysis puts this chain on PX4 and the touchdown, not on the
  flight code.
- Not tested: 7.6 fps; a wrong single-marker pose held for longer than about 2.5 s;
  touchdown faster than 0.40 m/s; the real camera.
- Known risk (from the code, not tested to the end): with `EKF2_EVP_GATE` 5 a
  pose with sigma 1.0 m passes the EKF gate up to about 5 m away and becomes
  the reference of the detector's and `vpe_fix`'s filters.

## Package tests
`test_vpe_fix_pins_r4` (`colcon test`) FAILS on this branch: it pins
`vpe_fix.py` to r2i/r2j and V1 changes methods it does not allow. The r2j file
passes the same test. The test was not changed; the other package tests were
not run on this branch.
