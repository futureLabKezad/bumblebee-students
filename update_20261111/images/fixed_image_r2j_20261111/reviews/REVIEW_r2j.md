# REVIEW r2j + C8 package A12 (independent reviewer, 11.11.2026)

Scope: diffs, numbers, signs only. Read-only review; no Gazebo/PX4/drone run.
Reference: ЭТАЛОН_РАЗМЕРОВ_20EC.md sections 1, 2, 3.3 (origin = base_link = centre B; X fwd, Y left, Z up;
down camera lens (+0.081, 0, -0.034); forward camera (+0.113, 0, -0.002)).

## Verdict: ACCEPT WITH NOTES
The r2j image diff and the A12 diff are exactly the expected edits, numbers and signs match the reference,
angles are unchanged, and the hash chains verify. One blocker applies to *using* A12 for the C8 run (below):
its pins still name the old Gazebo model, so A12 as pinned would run the new TF against the old camera pose.

## MUST-FIX (before any C8 gate run on A12; does not touch r2j bytes)
1. A12 pins the old Gazebo model. `pins/frozen_inputs_c8_r2j_a12_01.json` names
   `goal_t22_flow_20261109/model_v1/bumblebee/model.sdf` = sha 21d0ad765497 (launcher default `C8_MODEL`), and
   that file has `main_camera_link` pose `0.05 0 -0.07` (model.sdf:768). The A12 runner TF is now
   (0.081, 0, -0.034). With the default set, TF and model disagree by exactly 3.1 cm (x) / 3.6 cm (z): the
   vision base_link estimate in Gazebo would be biased 3.1 cm back and 3.6 cm low vs ground truth. The default
   airframe is also still 4070 (launcher line 66), not the T52 set (4074). The launcher accepts only pinned
   files, so the T52 model cannot be swapped in without new pins. Needed: a repinned package (A13) with the
   T52 model (camera at 0.081, 0, -0.034) and the T52 parameter set before the single r2j gate run, or an
   explicit statement that A12 is not for the gate run. A12 README line 32 mentions T52 but not this pin gap.

## SHOULD
1. Forward camera: the reference gives body +0.113 with lens at +0.125. An optical frame normally sits at the
   lens; r2j uses 0.113 as section 3.3 says. Fine for now (camera not used in flight); note it if the forward
   camera is ever used for vision.
2. Out of scope, pre-existing (angles were deliberately not touched): the second camera TF angles
   (yaw -pi/2, pitch 0, roll 0) put the optical z-axis along base +Z (up), not forward. Not a dimension;
   flag for a later angle review only if the forward camera gets used.
3. DRONE_REST_Z_OFFSET = 0.32 stays in drone.py with a stale comment; fix to 0.217 or delete at the next
   drone.py edit, as the README proposes.

## Checked and fine (evidence)
### 1. Image r2j vs r2i
- `diff -r src`: only flight.py, bumblebee.launch.py, main_camera.launch.py, second_camera.launch.py.
- `diff -r test`: test_q6_fixes.py E1 (0.8 -> 0.9, header and assert), path retargets r2i->r2j in
  test_r2h.py / test_r2h_vpe.py / test_r2i_vpe.py, test_r2i_changes.py moved to test/r2i_only/, new
  test_r2j_changes.py. Nothing else.
- TF numbers (static_transform_publisher positional order x y z yaw pitch roll parent child):
  - bumblebee.launch.py main_camera_frame: 0.081 0 -0.034, yaw -1.5707963 pitch 0 roll 3.1415926 (angles = r2i).
  - main_camera.launch.py down+backward: 0.081 0 -0.034, -1.5707963 0 3.1415926 (angles = r2i).
  - main_camera.launch.py down+forward: 0.081 0 -0.034, +1.5707963 0 3.1415926 (angles = r2i).
  - bumblebee.launch.py second_camera_frame and second_camera.launch.py: 0.113 0 -0.002, -1.5707963 0 0 (= r2i).
  - Signs: forward +X, on centreline Y=0, below centre B -> negative Z. Matches reference section 2 / 3.3.
  - One comment line above each of the 5 TFs.
- flight.py: header "takeoff to 0.9m" and `drone.takeoff(height=0.9, speed=0.4)`; nothing else.
- Unchanged bytes (cmp vs r2i): drone.py (fa6abf8b), vpe_fix.py, simple_offboard.cpp, aruco_detect.py.
- image_manifest_r2.tsv: exactly 4 rows changed; column 3 equals sha256 of the r2j src file for flight.py
  (b69cc5e7), bumblebee.launch.py (62be01db), main_camera.launch.py (c11080f1), second_camera.launch.py
  (ba601759). `sha256sum -c SHA256SUMS` all OK. Installed launch files == src (cmp).
- bumblebee.launch.py does not include main_camera.launch.py / second_camera.launch.py (grep), so no
  duplicate TF publisher.
- "up", "forward", "backward" variants left unchanged: correct for 20EC. They describe other mounts
  (camera up / looking forward / backward); the reference has no data for them and 20EC uses down
  (default direction_z=down, direction_y=backward). Changing them would invent numbers.
### 2. Package A12 vs A11
- `diff -rq`: only path/version renames, pins (new frozen_inputs_c8_r2j_a12_01.json, sha 697408e7 =
  ACCEPTED_PINS_b.txt), PRODUCT_SHA256SUMS, launcher v39-c8-r2j-a12, run.sh, sitl_setup.py, tests, and
  executor/vision_c8.launch.py.
- vision_c8.launch.py: `--x 0.081 --y 0 --z -0.034 --yaw -1.5707963 --pitch 0 --roll 3.1415926
  --frame-id base_link --child-frame-id main_camera_optical`. ROS 2 flag syntax correct; values equal the
  r2j main_camera_frame; angles = A11.
- verify_flight_c8.py, expect/, legacy/, executor/gate.py: byte-identical to A11 (diff -rq / cmp).
- run.sh pin of PRODUCT_SHA256SUMS.txt = f378d6b6 (matches file); `sha256sum -c` of it inside
  /work/fixed_image_r2j_20261111/install: OK. a8_checks pins r2j MANIFEST_SHA256 b0899329.
- Product .so/binary sums all changed: expected after a clean colcon rebuild (non-reproducible build);
  the chain to the r2j install verifies, so fine.
- tests/RESULT_test_c8_b2.txt: `RESULT pass=31 fail=0`.
### 3. README r2j claims
- DRONE_REST_Z_OFFSET unused: `grep -rn` over src finds only drone.py:610 (comment) and :652 (assignment).
  Confirmed.
- Shift 3.1 cm / 3.6 cm: aruco_detect.py `_lookup_cam_to_base` uses lookup_transform(camera, base_link) and
  T_map_base = T_map_cam @ T_cam_base, so base = camera - offset. dx = 0.081 - 0.05 = +0.031 -> estimate
  3.1 cm back (same setpoint -> drone sits 3.1 cm forward); dz = -0.034 - (-0.07) = +0.036 -> base_link
  estimate 3.6 cm lower (standing: 0.183 + 0.034 = 0.217 vs 0.253). Signs and magnitudes correct
  (geometry; not yet seen in Gazebo, as the README says).
