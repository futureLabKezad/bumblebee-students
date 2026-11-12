# Independent review: A10 edition 2 (c8_judge_r2h_a10_20261110), 10.11.2026

VERDICT: ACCEPT WITH NOTES (no MUST-FIX; 4 SHOULD, all text/test quality, none touches pins, run code, launcher or judge)

Method: read-only, WSL only. No Gazebo/PX4, no drone, no ssh. Only this file was written.

## A. Changed-file set (доказано)
- `sha256sum -c notes/_ed1/SHA256SUMS.txt` on the current tree: exactly 5 FAILED:
  PROGRESS.md, README.md, executor/tests/test_entry_order.log, executor/tests/test_entry_order.py, tests/a10_checks.py.
  No file of the ed.1 list is missing.
- The notes/_ed1 copies hash to the ed.1 list values (69316a9a, 8b5b6cdb, 9ae9130e, 312e476f, 9905a27f): they are the true ed.1 files.
- Files not in the ed.1 list: SHA256SUMS.txt (rewritten), tools/patch_ed2.py, notes/_ed1/*, tests/out_185336/ (59 files),
  and reviews/tests_out_185336/ (4 json: kill_as_c8_4061/4070, a7kill_as_c8_4061/4070). The last group is not in the claim (see S4).
- Line count 136 -> 205 = +59 +4 +5 +1. Current `sha256sum -c SHA256SUMS.txt` passes (rc 0).
- Pin file sha = 9ec805e7... (unchanged). tools/patch_ed2.py edits only tests/a10_checks.py and README.md (anchor count asserted == 1).
- Note: the "31/31" tally of the ed.2 run is printed to stdout only (test_c8_b2.sh line 205); out_185336 holds per-test logs but no RESULT line.

## B. ProfileVpe claim
Facts (доказано, by code):
- Drone: /work/fixed_image_r2h_20261110/src/bumblebee/launch/aruco.launch.py starts `vpe_fix.py` (node vpe_publisher, only if aruco_vpe or force_init).
  vpe_fix.py main() = plain VpeFix + MultiThreadedExecutor(num_threads=8). No ProfileVpe on the drone.
- candidate/parameters/vpe_fix.py sha 66d806ba... == drone image vpe_fix.py == diagnostic TARGET_SHA256 == opt-in pin.
- ProfileVpe own methods: _arm_ttl, _handle_revert_all, _handle_set_param, _initial_pull_tick, _param_set_once, _restore_one,
  _result, _revert_all, _revert_all_non_persistent (overrides) + allow_profile_flight, prepare_profile, profile_pending_tick (new).
  None of publish_timer, aruco_map_callback, _reentry_pose, _medoid, _maybe_reseed, state_callback, _evaluate_gate/_apply_gate,
  get_clock is overridden. header.stamp = get_clock().now() in the inherited publish_timer. The gate does not read the param cache,
  so the no-op _initial_pull_tick does not change gate or pose. The overridden revert paths only touch parameters.
- __init__ adds: profile_control, an Event, RosRawBridge(node) (publisher only on /uas1/mavlink_sink, raw group), OptInControl.
- Opt-in main() adds: 2 Trigger services and a 0.05 s profile_pending_tick timer on _cb_grp_handlers, a separate
  MutuallyExclusive raw group, and MultiThreadedExecutor(num_threads=4) instead of 8. rclpy.init(args=ros_args).
- The A10 composition also wraps VpeFix._evaluate_gate with the diagnostic wrapper (vpe_diagnostic_entry.py), not ProfileVpe.

Assessment: what is published and how the stamp is computed are unchanged (доказано). When the 30 Hz timer actually fires, and
so the stamp values/cadence, is NOT proven identical: executor size, extra timer/services/raw callbacks, no initial ParamPull flood,
and the disarm-edge restore moved off the default group (on the drone _restore_one runs synchronously inside state_callback in
the default group shared with publish_timer; in ProfileVpe it is deferred to the handler-group timer). The README sub-bullet
says this ("возможно"), but the bold heading says "публикацию и время позы он не меняет (доказано по коду)" -> S1.

## C. New test_entry_order.py
- Re-run by this reviewer (ROS sourced, python3 -B, no node): ALL OK, rc 0, output identical to the log.
- a10_order checks: MRO[:2] == ProfileVpe, VpeFix; same VpeFix class; _evaluate_gate is the diagnostic wrapper (__wrapped__);
  loaded vpe_fix sha == TARGET_SHA256; no FreshnessMixin; ProfileVpe defines no pose-path method. Meaningful.
- Inline mutation checks by this reviewer (no files written): without the wrapper gate_is_wrapper = False (would FAIL);
  an extra class between ProfileVpe and VpeFix makes MRO[:2] = ProfileVpe, Bad (would FAIL). So the main check can fail.
- Control: vpe_freshness_optin.install(vpe_fix r2h, enabled=True) raises ValueError 'c33 VPE source PIN mismatch'
  (vpe_freshness_optin.py line 271-272, path-or-sha check vs PIN_C33 = r2g). The test requires that exact string, so it fails
  for the right reason (the pin), not for an import or environment error.
- Limits -> S2, S3.

## MUST-FIX
none.

## SHOULD
S1 (README wording). Replace the heading "ProfileVpe ... публикацию и время позы он не меняет (доказано по коду)" with two labels:
   "путь позы и формула времени (now() в publish_timer) не меняются - доказано по коду; расписание вызова таймера 30 Гц может
   отличаться (4 потока вместо 8, таймер 0,05 с, сырой MAVLink, нет ParamPull, restore вне группы по умолчанию) - возможно, не измерено".
   Add the deferred disarm-edge restore to the list of non-pose differences.
S2 (test scope). test_entry_order.py rebuilds the composition by copying the entry's statements; it does not execute or parse
   executor/vpe_diagnostic_entry.py, so drift between entry and test is not caught here. Its mixin_in_mro=False is tautological
   (the test itself never installs freshness). Both are covered elsewhere (a10_checks.py AST check of the entry; test_c8_b2.sh
   items 6-7, 'vpe_freshness_optin' not in entry). Say in README that this test duplicates d2_vpe_composition and adds only the
   "no pose-path override in ProfileVpe" check, or derive the composition from the entry file.
S3 (control). The only control tests the freshness file's pin, not the a10_order assertions. Add one negative case
   (e.g. unwrapped gate, or a ProfileVpe subclass overriding publish_timer) that must FAIL.
S4 (claim list). README "Редакция 2" should also name reviews/tests_out_185336/ (4 json written by the ed.2 test run, like
   reviews/tests_out_184229 in ed.1) and say the 31/31 tally is from stdout.
