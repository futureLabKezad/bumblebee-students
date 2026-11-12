# Independent review: r2f vs r2e (10.11.2026)

Reviewer: independent code-review agent. Scope: read-only review of `/work/fixed_image_r2f_20261110` against `/work/fixed_image_r2e_20261109`.
No drone, no ssh, no Gazebo or simulator. Probes and logs are in `/work/review_r2f_20261110/`. ROS runs used domain 93, localhost only, nice 19.
Labels: **proved** (probe, test or direct code fact), **likely** (strong evidence without a control), **possible** (reasoned guess).

## Verdict: ACCEPT WITH SHOULDs

Both fixes are correct and minimal, and the diff holds exactly the two fixes. The tests tell r2e and r2f apart. All checksums verify.
The SHOULD items are about accuracy and completeness of the README and the docs. None needs a code change in r2f.
No MUST-FIX found.

## What I checked and how

| Check | Result | How |
|---|---|---|
| Diff contains only the two fixes | **proved** | `diff -rq` (build/log/pycache excluded): `src/` differs in exactly 6 files (drone.py, flight.py, flight_marker.py, flight_marker_loop.py, simple_offboard.cpp, test_drone_flight_guards.py). The hunks match T35 + T34 + 6 test edits. `notes/DIFF_r2f_vs_r2e.txt` is byte-equal in content to my own `diff -ruN` (md5 of the hunk bodies is equal). |
| install/ | **proved** | Same file list as r2e. In `lib/bumblebee` only the binaries differ. Also `SOURCES.txt` (egg-info, 17 more lines) and include order in `*__description.c` differ: build noise, harmless (NOTE N6). |
| Sums | **proved** | `sha256sum -c` OK for MANIFEST_SHA256.txt (333 files), SHA256SUMS (4), and INSTALL_SHA256.txt (16, run from `install/bumblebee/lib/bumblebee`). The image_manifest_r2.tsv column 3 matches the real sha of all 6 changed files. |
| No-ROS tests | **proved** | Rerun: test_r2f 16/16, guards 87 (2 skipped), q6 OK, r2b 5, r2c 6 (2 skipped), r2d 14, r2e OK. No files were written in r2f (`find -newer` is empty). |
| Test strength (mutation) | **proved** | `mutate_run.py`: 7 plausible wrong fixes of drone.py, and all 7 are killed by test_r2f.py. The mutants are: no dedupe; guard on raw time; safe_land on raw time; guard active before the first pose; dedupe on xy only; guard = min(raw, pose); RELIABLE QoS. |
| T34 ROS test with control | **proved** | Rerun on domain 93. r2f: 3/3 races give "Navigating from current setpoint". r2e control: 3/3 give "". Without the race both give from-setpoint (`flag_r2f.txt`, `flag_r2e.txt`). |
| T35 ROS subscription test | **proved** | Rerun: raw markers_used alone gives age = inf; new poses give 0.033 s; 1 s of repeats gives 1.207 s (`vpe_sub.txt`). The QoS match (BEST_EFFORT sub, RELIABLE depth-1 publisher) is shown by `get_subscription_count()` and by delivery. |
| gtest simple_offboard | **proved** | 23/23 (it has no case for the flag; the ROS test covers it). |
| Bit-identical "new" pose (false vision loss) | **proved for these logs** | `probe_identical_vio.py` over 85 Gazebo ULogs (goal_step5b runs). The source is `estimator_aid_src_ev_pos.observation` per distinct sample; "same" means within 1e-5 m. No same-run longer than 0.55 s: max 0.492 s armed (= vpe_fix 0.5 s repeat window) and 0.160 s disarmed, over 39 461 armed runs. New camera frames always moved the pose, also at rest on the ground. Exact-0 tolerance cannot be used: PX4 adds ~1e-7 m jitter to repeats. |

## MUST-FIX
None.

## SHOULD

**S1. README says `wait_quorum` runs "on the ground". It runs in flight with no vision watchdog.**
- Where: `README.md:19` ("Не менял (на земле, по сырому счёту): … `wait_quorum`"). Same claim in `test/test_r2f.py:213` ("wait_quorum (on the ground)"). The draft said it right (`R2F_DRAFT.md:27`: "Также без сторожа: wait_quorum, hover()").
- Fact (**proved**, code): `flight_marker.py:168,178,185` call `wait_quorum` after takeoff, before each waypoint. Each call can hover up to 15 s on raw `markers_used >= 2`.
- The hover watchdogs in that script cannot fire. `hover_vw(1.5/2.0/1.0)` uses `silent_limit=6.0`, and `flight_marker_loop.py:118-125` hovers 1 s against 1+3 s. The T35 finding called them "dead"; r2f changed their condition, but they still cannot fire. README:16 lists them as watchdog places without saying so.
- Failure scenario (reasoned): markers are lost (C8) while `flight_marker.py` waits for quorum. Nothing lands for up to 15 s; then SystemExit and `safe_land`. A false double detection can also pass the quorum.
- Not a change request for r2f (the owner chose variant 1). The README should list wait_quorum, and the dead hover_vw/loop hover, under "Что остаётся" as in flight without a working vision watchdog.

**S2. A label is too strong for the T34 0.1 m sag.**
- Where: `README.md:22`. The text "Уставка проседала примерно на 0,1 м" sits under "Было (доказано по коду)".
- The source labels it weaker. T35 README: "s9_c6r3_03 … упала с 1,01 до 0,90 (скорее всего, этот путь)" and "С7: … ~0,1 м ниже (возможно)". The code path is proved; the 0.1 m effect is likely/possible. Rule 10 asks for correct labels.

**S3. The reseed residual is understated, and one known cost is missing.**
- Where: `README.md:46`: "Такая поза продлит зрение".
- By code (**proved**, `vpe_fix.py:913-917`, `:958-990`): after a reseed, `last_pose` is the false pose. Later false frames consistent with it pass the jump and velocity gates and are accepted as normal poses (`:982`). Each one is a NEW pose for `vision_pose_age()`.
- Failure scenario (possible): false detections that recur every < 6 s after one reseed hold off the r2f watchdog for as long as they last, not once. PX4 also gets those poses.
- Also missing from "Что остаётся": the T35 card minus "30 messages/s extra for drone.py – measure on the Pi". The new subscription runs on the single-threaded spin executor (`drone.py:798`, `:822`).

**S4. Without any vpe_fix pose the watchdog stays off for the whole flight. Two of the three example scripts never check that poses flow.**
- Where: `drone.py:2188` (`_vpe_pose_time is not None`) and `:2326-2328` (warning only).
- `flight.py:88` calls `require_vpe_link`. `flight_marker.py` and `flight_marker_loop.py` do not; they only check raw counts (`check_aruco`, `wait_position_stable`).
- Failure scenario (reasoned): vpe_fix does not publish before takeoff. Causes: respawn, gate closed by an unknown or stale FCU State, or poses rejected on the ground. The vehicle has a position source (for example flow). The script takes off, and the only sign is a log warning. If vision then never comes, no vision watchdog fires.
- In r2e the first raw frame armed the watchdog, so this is a small regression in a double-fault case.
- Ask: say so in the README. Any change (refuse takeoff, or start the clock at arming) is for a later revision and is the owner's choice.

## NOTE

- **N1 – T34 fix is correct (proved by ROS test, reasoned for the other paths).**
  - The flag is set only on the auto_arm path after `offboardAndArm()` returned. At that point `setpoint_type_` is still NAVIGATE or NAVIGATE_GLOBAL: `busy_` blocks a concurrent serve, and `land()` waits for `busy_`.
  - A later non-OFFBOARD State clears the flag again, as do a pilot takeover (`stopStream`), a disarm edge (`resetSetpoint`) and an arm failure (catch, then `resetSetpoint`). So the flag does not leak.
  - When already armed in OFFBOARD, `offboardAndArm()` returns early, and the flag was already true (`:1545`) and not cleared: no change.
  - set_position(auto_arm) is untouched (POSITION).
  - The ground hold still wins over the flag (`:1530-1533`).
  - The first navigate's own `nav_start_` is set before arming and is not affected.
  - The race injection (an old-mode heartbeat inside the set_mode window) is realistic: MAVROS publishes State per heartbeat at 1 Hz.
- **N2 – Behaviour change from T34 to re-check in Gazebo (likely).**
  - In r2e the race fired often, so the first fly_to after takeoff usually started from `local_position_`. In r2f it starts from the smoothed setpoint (`position_msg_`).
  - This is the intended upstream behaviour, but it is a different de-facto start for C5–C7. The README already asks to re-run C5–C8.
- **N3 – Thread safety is OK (reasoned).**
  - `_on_vpe_pose` runs on the single spin thread. Readers do single global loads under the GIL, and `_vpe_pose_time` only goes from None to a float.
  - `vision_pose_age()` can return a few-µs negative age if a callback lands between `monotonic()` and the load. Harmless.
- **N4 – Repeats are bit-identical by code (proved).** `vpe_fix.py:1060` publishes the same `last_pose` object and serialization is exact, so the dedupe works. A new frame giving an identical pose was not seen (table above). With a real camera's sensor noise it is even less likely (likely).
- **N5 – flight.py hover watchdog margin (possible).**
  - It now sees vpe_fix gaps (1 s + 3 s). The largest PX4 vision gap at flight height in the series was 3.03 s (T35 README).
  - An early safe_land in flight.py hover is possible but rare. It is covered by the C5–C8 re-run.
- **N6 – Checksums and build noise.**
  - `MANIFEST_SHA256.txt` lists `.pytest_cache/*` (5 files). That is volatile: a later pytest run from the r2f folder with other node ids rewrites `v/cache/nodeids`, and the manifest check then fails. Suggest moving it aside or excluding it in the next revision.
  - README:71 says only binaries differ in install/. Also `SOURCES.txt` and the include order in `*__description.c` differ (harmless).
- **N7 – Stale comments.** `flight.py:27`, `:110` ("no markers at all") and `drone.py:2179` ("usable (>=1 marker) frame") still describe raw counts. Cosmetic.
- **N8 – Test bound change after the first failure is analytically correct.** The `_failed_first_run` bound went from `< 6.5` to `<= 6.5 + 1e-6`. navigate_wait checks every 0.5 s on the fake clock, so the first check with age > 6.0 is at exactly 6.5. It is the reviewers' own new test, not a gate or criterion.
- **N9 – Remaining raw-count users, intentionally unchanged.** `navigate_wait(tolerance_adaptive=True)` (only from `wait_position_stable`, on the ground), the preflight checks, `wait_yaw_lock`, notify_manager LEDs, and hover r4 outside the image. `drone.hover()` has no watchdog, as README:19 says.
- **N10 – The README section "Как скрипт узнаёт «зрение есть»" (README:25-43) is accurate.**
  - The function, inf before the first pose, the topic, the QoS and the "after `_init()`" condition are all right; `require_vpe_link` and `takeoff` both call `_init()`.
  - The example loop matches flight.py.
  - One detail to add: vpe_fix stops publishing when armed in a manual mode (`vpe_fix.py:800-801`), so the age also grows after a pilot takeover.

## Files
- Probes: `/work/review_r2f_20261110/probe_identical_vio.py` with `.out` and `probe_near_identical_1e-5.out`; `mutate_run.py` (mutants in `mut/`); `run_ros.sh`.
- ROS logs: `flag_r2f.txt`, `flag_r2e.txt`, `vpe_sub.txt`, `gtest.txt`.
