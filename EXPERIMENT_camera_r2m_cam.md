# EXPERIMENT: front camera at 5 frames/s (r2m_cam)

**Status: EXPERIMENT, not verified — NOT installed on the drone; the frame
rates below are a model, not measured. Approved by the owner for the drone
20EC on 2026-11-18 and independently reviewed (OK with notes); live check
pending.**

- Do not use for students' flights.
- Never merge this branch into `main` without a new decision of the owner.
- The change does not touch flight: only the GCS front view reads this camera.

## What it changes
Two files against `feat/drone-image-r2j` (image r2j):

| File | r2j sha256 | r2m_cam sha256 |
| --- | --- | --- |
| `drone/ros2_ws/src/bumblebee/src/python/camera_fix.py` | `4a15d699…` | `e133481dd3c46bb49691bd40716a08b3e2418e3ab80acc7118569c7a8d74d7e1` |
| `drone/ros2_ws/src/bumblebee/launch/bumblebee.launch.py` | `62be01db…` | `5c867929421f7b5fa4d8f4a6d4816258afe7d0d9e196c04a612ee9a97b4ca483` |

- `camera_fix.py` gets a node parameter `max_rate_hz` (float). `0` (default):
  every frame, exactly as r2j. Above 0: a frame is kept only if at least
  0.9 / `max_rate_hz` s passed since the last kept one; the other frames are
  dropped before any copy, conversion or publish. `camera_info` is published
  only with a kept frame. The 2 × 10 s watchdog still sees every received frame.
- `bumblebee.launch.py` sets `'max_rate_hz': 5.0` for `second_camera_fix`
  (front camera) only. The down camera and the ArUco detector stay as in r2j.
- The front sensor itself keeps about 28 frames/s: `v4l2_camera` 0.7.1 on the
  drone has no `time_per_frame`, so an earlier attempt with that parameter had
  no effect.

## Expected effect (model of `ros_mjpeg_server.py`, not measured on the drone)
| | r2j | r2m_cam |
| --- | --- | --- |
| front `camera_fix` publishes | ~28 /s | ~5 /s |
| GCS app front view (`fps=12`) | ~9.5 /s | ~5 /s |
| `www/gcs.html` (`fps=5`) | ~4.6 /s | ~3.1–3.2 /s |

## Review notes (independent review 2026-11-17: OK with notes, no blockers)
- `max_rate_hz` must be a float: an integer `5` makes the front `camera_fix`
  fail at start and restart in a loop.
- It is read once at start; `ros2 param set` while running changes nothing.
- The rate is about 5, not exactly 5: it depends on the frame arrival jitter.

## Live check (pending, read only)
On the drone after installation: `/second_camera/image_raw` about 5 Hz,
`/main_camera/image_raw` about 30 Hz, and the CPU load of the front
`camera_fix`.
