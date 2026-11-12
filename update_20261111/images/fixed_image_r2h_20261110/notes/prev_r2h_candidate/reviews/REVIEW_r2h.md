# REVIEW r2h candidate (independent, read-only), 10.11.2026

Subject: `/work/fixed_image_r2h_candidate_20261110` vs reference r2g `/work/fixed_image_r2g_20261110`.
Scope: B1 and B2 in `src/bumblebee/src/python/vpe_fix.py`, W in `src/bumblebee/examples/drone.py`.
The reviewer did not run ROS, Gazebo or anything on the drone. The only file written is this one.
Labels: доказано / скорее всего / возможно.

## Verdict
**ACCEPT WITH NOTES, for simulator control runs only.** There is no unsafe gate opening and no stale-pose path.
r2h is reproducible from r2g, the tests pass, and the checksums were correct before the test run.
r2h is **not ready for the drone** as it is: **M1 must be resolved first.** At a low detector rate, B2 can stop all
vision publishing even though good poses keep arriving.

## What was checked and the result
1. **Diff (доказано).** `diff -ruN r2g/src r2h/src` lists exactly 2 files: drone.py and vpe_fix.py. Its body is identical to
   `notes/DIFF_r2h_vs_r2g.txt`; only the path header differs because the diff was run from a different directory.
   The builder runs `python3 -I tools/make_r2h.py` on a temporary copy of r2g's two files. Its output is **byte-identical to r2h**
   (vpe_fix f2c0519a…, drone.py fa6abf8b…). The r2g sha prefixes (3b8a93d4…, 068e6eb4…) match r2g. Every anchor is
   checked with count == 1. The anchors are honest: there are no hidden edits.
   `install/bumblebee/lib/bumblebee/vpe_fix.py` is identical to src (cmp).
2. **Checksums, checked BEFORE the tests (доказано).** `sha256sum -c --quiet SHA256SUMS` → OK.
   `sha256sum -c --quiet MANIFEST_SHA256.txt` → OK (414 entries).
   After the instructed test run, 14 MANIFEST entries fail, and all of them are `notes/test_logs/*.txt`, which the
   script rewrote with new timings. `SHA256SUMS` still passes. `notes/h2_out/*` was also rewritten; it is not in the MANIFEST.
   → See S4.
3. **Tests (доказано).** `bash tools/test_all_r2h.sh` gives exactly the same result lines as `notes/test_logs/SUMMARY_run.txt`
   (only the timings differ): r2h_drone 39 OK, r2h_vpe 11 OK, r2h_pins 5 OK, q6 17, r2b 5, r2c 6 (2 skipped), r2d 14,
   r2e 2, guards 87, notify 37, script_lease 19, h2_r2 33, in_air 1.
   The old pins `test_pins_r2.py` fail as expected on r2h (4 of 5) and pass on r2g (5 of 5).
   No `__pycache__` was left behind.
4. **README numbers (доказано).** I recomputed the gaps in `t42…/out/gate_log.jsonl`, SEARCHING→NORMAL + 8 frames at 24 Hz:
   152 gaps, median 0.833 s, p90 1.503 s, max 2.133 s, 58 of them > 0.9 s. This matches the README.
   C8: 7.22 / 7.14 s matches `c8_r2g_run_20261110/MARKERS_TIMING_20261110_v2.md:21`.
   PX4 `ev_pos_control.cpp` `startEvPosFusion`: without GNSS it calls `resetHorizontalPositionTo(measurement)`. This matches the README.
   Test counts: 27+12=39 and 7+4=11. The pin claims (6 changed methods, +1 method, +3 constants, +1 statement in
   aruco_map_callback) are true. The old-pins/CMake statement is honest: `CMakeLists.txt:214` registers it.

## Safety of B1 (vpe_fix.py:772-777, 1010-1025)
- **P1 unchanged (доказано, AST pins and code reading).** `_evaluate_gate` checks `_fcu_state_unknown()` first:
  never-connected, connected=False, a stale State (4.5 s) and a clock going backwards all give "closed".
  An armed vehicle that is not in OFFBOARD stays closed. Without yaw lock, a single marker is not fresh
  (`_single_marker_fresh` returns False). The new calls of `_apply_gate` (every markers_used message and every yaw_locked
  change) only re-evaluate the same decision, so they cannot open the gate in a state that r2g's decision forbids.
  The bench tests cover each case.
- **Stale poses (доказано).** `publish_timer` still returns when `last_pose` is older than 0.5 s, and B2 filters
  `_recent_poses` by the same 0.5 s. Under monotonic or steady ROS time, no pose older than 0.5 s is published.
- **Thread safety (доказано).** The VPE subscriptions and timers (state, aruco_map, markers_used, yaw_locked, the 30 Hz
  publish, the 1 Hz tick, the 0.1 s watchdog) have no explicit group, so they share the node's default
  MutuallyExclusiveCallbackGroup. With the 8-thread executor they still run one at a time. The reentrant and handler
  groups only touch the parameter cache and overrides, which are behind their own locks. Calling `_apply_gate` from the
  callbacks is safe.
- **Log flooding (доказано by reading the code).** `_apply_gate` logs only when the decision changes. Closing needs
  1.0 or 1.5 s of freshness to expire plus 0.5 s of coasting, so a full open/close cycle lasts at least about 0.5 s
  (when yaw_locked flaps) and normally at least 1.5 s. That is at most a few lines per second.
  B2 logs one "resume after" line per pause (45 lines in 30 s in my worst probe).
- N1 below covers a mild widening of the window.

## Findings

### MUST-FIX (before any use beyond SITL control runs; not blocking for those runs)
**M1. B2 blocks ALL publishing when fewer than 3 accepted poses fit in 0.5 s, even though good poses keep arriving**
(`vpe_fix.py:1062-1065`, together with the wait state that starts at boot and after every gap).
`_reentry_pose` needs `_REENTRY_N=3` accepted poses no older than `_POSE_TIMEOUT=0.5` s, and `publish_timer` checks this
on its 30 Hz grid. Two consequences: the accepted pose rate must be above about 4.3 Hz, and at 6 Hz at least 3
**consecutive** accepted frames are needed.
I ran a probe on the authors' own event bench (test_r2h_vpe.Sim, armed OFFBOARD, single marker, yaw locked, 30 s),
with each scenario on r2h and on r2g. Results (доказано on the bench):

| detector rate and pattern | r2h samples sent | r2g samples sent |
|---|---|---|
| 4 Hz, all frames good | **0** | 870 |
| 6 Hz, every 3rd frame empty (phase k%3==0) | **0** | 870 |
| 6 Hz, every 4th frame empty | 215, 42 pauses > 0.4 s | 420, 13 pauses |
| 6 Hz, 20 % or 35 % random drops | about equal or better than r2g | |
| 10 Hz and 24 Hz with drops | better than r2g | |

In the 4 Hz and 6 Hz-k%3 rows, r2h logs "resume after start" and then never publishes.
The test suite models only a 24 Hz detector.
The image itself says the real drone runs much slower: `drone.py:571` ("The topic streams ~6 Hz") and
`vpe_fix.py:212` ("~2.5 s at 6 Hz"). The real rate is not proven (возможно about 6 Hz on the Pi).
On the drone this means no vision before arming, so preflight fails, which is safe. In the air it means EKF coasting
until the 6 s watchdog lands the vehicle.
Proposed fix, for the authors to choose:
- base the requirement on time rather than count (for example "N=3 within max(0.5 s, 2.5 frame periods)"), or
- allow N=2 below a measured rate, or
- fall back to the latest pose once the wait exceeds about 0.3–0.5 s.

Also add a 6 Hz test and a 6 Hz test with 1-in-3 drops.
The README should say now that B2 depends on the rate and has been checked only at 24 Hz (the SITL rate).

### SHOULD
- **S1. During the hold, a single missing or rejected frame silences publishing** (`vpe_fix.py:1062-1065`).
  `len(fresh) < 3` returns None also while `_reentry_until` is set. At 24 Hz this does little harm, but it can reopen
  a gap and start a new wait. The README describes the hold as "0.5 s of medoid" and does not mention this silence.
  Either publish the medoid of the poses that are available (≥1) during the hold, or document it.
- **S2. A reseed does not clear `_recent_poses`** (`vpe_fix.py:927-933` vs `999`). This is known and labelled возможно in
  the README. The fix is one line: `self._recent_poses.clear()` in the reseed branch of `_maybe_reseed`, so the medoid never
  mixes poses from before the reseed with the new baseline.
  This needs a new pin set; it is not a gate-criteria change.
- **S3. Weak assertion** `test/test_r2h_vpe.py:223-225`. For t < 5.99 it compares `m.x` with `m.x`, which is
  tautological. The check that does the work is the sorted-x check on line 227. Replace it with a real check
  (for example "x equals the last accepted pose at the publish time").
  There are also no tests for a backwards clock jump in B2, a missing frame during the hold, or a low detector rate
  (see M1).
- **S4. Running `tools/test_all_r2h.sh` makes `MANIFEST_SHA256.txt` fail** on the 14 `notes/test_logs/*.txt` files,
  because the timings change. Either drop the logs from the MANIFEST (keep them under their own sum) or have the
  script write to a scratch directory. The MANIFEST in the folder now fails `sha256sum -c`, because this review ran the
  tests on purpose (as instructed). Chat 1 should re-run `tools/finish_r2h.sh` or accept the new logs.
  `SHA256SUMS` still passes.

### NOTE
- **N1. B1 widens a window** (`vpe_fix.py:772-777`, 809-824). In OFFBOARD with yaw locked, the gate can now stay open
  up to about 1.5 s + 0.5 s hysteresis after the last frame with ≥1 marker, while the latest markers_used messages are 0.
  In r2g this window lasted only until the next 1 Hz tick that saw a 0 (≤ about 1 s, depending on the phase).
  A pose received while markers_used is 0 could therefore be published. This matters only if aruco_map publishes a pose
  for a frame that markers_used counts as 0 (скорее всего it does not; the aruco_detect source is not in the image,
  so this is not verified). The 0.5 s pose age and the z/xy/velocity guards still apply. Acceptable for SITL;
  check on the drone logs.
- **N2.** Under the sim clock, a backwards clock jump makes negative ages count as "fresh" in B2 (`(now - t) <= 0.5`),
  and `_reentry_until` can lie far in the future. Because the deque refreshes with each accepted pose, the published
  sample is still the medoid of the last 3. The same weakness already exists in r2g's `publish_timer` age check.
  SITL only; the drone uses monotonic time.
- **N3.** During the hold, `out.pose.covariance = last_cov` belongs to the latest pose, not to the medoid. The difference
  is negligible.
- **N4. W (drone.py:1763-1821, 2345). It is correct.**
  - `_wd_stamp` takes one reading per event. `_on_vpe_pose` and `_on_fcu_state` write `*_wd` before `*_t`, and the
    reader passes `*_t` first. A torn read can only yield `stamp[2] != mono_t`, which falls back to monotonic from the
    older moment. That is conservative.
  - A ROS clock reading 0, or a change of clock kind, falls back to monotonic. A negative age gives +inf, which lands
    the vehicle (SITL only: a restarted Gazebo during a flight; acceptable).
  - `vision_pose_age()` is unchanged and monotonic.
  - The `_vpe_pose_time` / `_vision_arm_t` moments are paired in production code. Only `test_drone_flight_guards.py`
    sets `_vpe_pose_time` directly, which takes the monotonic fallback (the r2g behaviour).
  - The checks in `navigate_wait` run in the same order (disarm → pilot → vision → stale → floor/ceiling → jump).
    `_wait_watching_vision` always sleeps at least one 0.1 s slice, so the loop cannot spin.
  - `should_land` now ends the wait within 0.1 s, which is better than before.
  - The safe_land 3.0 s check uses the same `_vision_silence_age()`, so it is consistent.
  - The race where a disarm sets `_vision_arm_t=None` between the None check and its use in `_vision_silence_age`
    (TypeError) also existed in r2g.
- **N5.** W measures sim seconds only when the drone.py node has `use_sim_time:=true`. The C8 supervisor passes it
  (`sim/runs/INT_flight_C8a9_*/supervisor.py:298`). The goal_step5/5b `run_scenario*.sh` scripts start the script as
  plain `python3 -u` (`goal_step5_20261106/run_scenario.sh:196`), so W runs on monotonic time there, exactly like r2g.
  Keep this in mind when comparing C6/s10 and C8 timings.
- **N6.** A frozen /clock (Gazebo paused or crashed) stops the vision silence count in SITL. This matches lockstep PX4,
  but it differs from r2g.

## Summary for chat 1
- r2h is clean and reproducible. P1 and the gate decision are untouched, and there is no stale-pose or unsafe-open path.
- B1 and W are good.
- B2 works at the SITL rate of 24 Hz. Below about 4.3 Hz, or at 6 Hz with every 3rd frame empty, it **never publishes**
  (M1). Fix it or prove the drone's detector rate before r2h goes anywhere near the drone. Until then, mention the 24 Hz
  assumption in the README.


## Re-check of edition 3 (same reviewer, 10.11.2026, narrow scope)

**Verdict for ed.3: ACCEPT WITH NOTES, for simulator control runs. M1 is resolved. No MUST-FIX.**
The open question for the drone is now only N5/N1: the real detector rate and how aruco_map behaves on frames with 0 markers.
Taking r2h onto the drone is still the owner's decision.

What I did (read-only; nothing written except this section):
- **Checksums before anything else (доказано):** `sha256sum -c --quiet SHA256SUMS` passed, and `sha256sum -c --quiet MANIFEST_SHA256.txt` passed.
  After my test runs both still pass, because I did not run `test_all_r2h.sh`. No `__pycache__` is left.
- **Diff from ed.2 to ed.3 (доказано):** I diffed against `notes/_before_review_r2h/src_files/vpe_fix.py`, which is ed.2 (f2c0519a…, the version I reviewed).
  The changes are:
  - the new constant `_REENTRY_MAX_WAIT = 0.3`;
  - two lines in the reseed branch of `_maybe_reseed` (`_recent_poses.clear()` and `append((now, seed))`);
  - the fresh-pose filter, wait-exit and medoid code in `_reentry_pose`.

  `drone.py` is byte-identical to ed.2. Running `tools/make_r2h.py` ed.3 on a copy of r2g gives byte-identical r2h. The installed `vpe_fix.py` equals the one in `src`.
- **Tests (доказано):**
  - `python3 -B test/test_r2h_vpe.py -v`: 16 OK.
  - `python3 -B test/test_pins_r2h.py -v`: 5 OK.
  - The control log `notes/test_logs/control_new_tests_on_pre_review_vpe.txt` shows 4 of the 5 new tests failing on ed.2 (3 FAIL, 1 ERROR), as the README says.
  - The README says honestly that the S1 test does not tell ed.2 and ed.3 apart at 24 Hz.
- **Pins (доказано):** 7 changed methods (the previous 6 plus `_maybe_reseed`), 1 added method and 4 added constants. This is honest and matches my diff.
  The S3 self-compare is gone.
- **My probe, re-run on ed.3** (authors' Sim with `frame=1/hz`, armed OFFBOARD, 1 marker, yaw locked, 30 s; samples sent / pauses > 0.4 s):

  | scenario | r2h | r2g | max published pose age |
  |---|---|---|---|
  | 4 Hz, all good | **870 / 0** | 870 / 0 | 0.25 s both |
  | 6 Hz, every 3rd empty (k%3==0) | **870 / 0** | 870 / 0 | |
  | 6 Hz, every 3rd empty (k%3==2) | **870 / 0** | 0 / 0 | r2g's 0 is an artefact of the 1 Hz tick phase |
  | 6 Hz, every 4th empty | **870 / 0** | 420 / 13 | |
  | 5 Hz, every 3rd empty | **870 / 0** | 570 / 9 | |
  | 6 Hz, 35 % random drops | **754 / 4** | 545 / 6 | |
  | 4 Hz, 20 % random drops | **816 / 1** | 682 / 4 | |
  | 24 Hz, 35 % random drops | **870 / 0** | 570 / 7 | |

  In every scenario r2h sends at least as many samples as r2g, with fewer or equal long pauses.
  The largest age of a published pose is 0.5 s or less, the same bound as r2g (доказано on the bench).
- **Stale poses (доказано by reading the code):** `fresh` keeps only poses no older than `_POSE_TIMEOUT` (0.5 s), and `publish_timer` still returns when `last_pose` is older than 0.5 s.
  No pose older than 0.5 s can be published, except with a backwards sim-clock jump (N2, as before).
- **State machine (доказано by reading the code):** there is no new stuck state.
  - The wait ends as soon as `fresh` is non-empty and either 3 poses are fresh or the oldest fresh pose is at least 0.3 s old. A fresh pose stays fresh until it is 0.5 s old, so the 30 Hz timer always reaches the 0.3 s point while that pose is still fresh.
  - The hold now publishes the medoid of 1 to 3 poses and only goes silent when there is no fresh pose at all. That is the same condition under which r2g's 0.5 s timeout also stops.
  - A backwards clock jump makes `waited` negative, which only lengthens the wait until 3 poses arrive or the clock catches up. This is temporary and SITL only.
- **Reseed (доказано by reading the code):** the seed is exactly what r2g starts to publish as `last_pose` (with `last_pose_time = now`), so storing it with `now` changes nothing about freshness.
  Clearing the history removes the poses from before the reseed (my S2). This is safe, and B2Reseed covers it.

New finding (ed.3):
- **SHOULD-2 (vpe_fix.py, `_reentry_pose` + `_medoid`):** with exactly 2 fresh poses, both have the same medoid cost, and `_medoid` keeps the first one because it compares with a strict `<`. That is the **older** pose.
  On the timeout path with 1 pose, the first sample after a pause is 0.3 to 0.5 s old.
  So with a slow detector the EKF reset sample after a pause is systematically one frame older: about +0.17 s at 6 Hz, and in my 6 Hz 35 % drop probe the mean age was 0.183 s against 0.167 s for r2g.
  This is bounded by the 0.5 s limit, so it is not a safety issue. It does work against B2's goal (a better reset sample) at about 6 Hz.
  Suggested fix, without touching `_medoid` (which is pinned and shared with reseed): in `_reentry_pose`, when fewer than 3 fresh poses are available, publish the newest one, or pass `fresh` newest-first so that a tie picks the newest.
  Check it in a Simulator run; it is not blocking.

My earlier S1–S4 and M1 are addressed; N1–N6 are unchanged.
