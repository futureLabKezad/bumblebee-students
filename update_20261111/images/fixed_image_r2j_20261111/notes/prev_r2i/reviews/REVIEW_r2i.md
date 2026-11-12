# REVIEW_r2i — independent review of image r2i (vs accepted r2h) and of C8 judge package A11

Reviewer: independent agent, 11.11.2026. Read-only, no Gazebo/PX4/drone/ssh. Offline only: g++ of test/test_state_link.cpp into /tmp, python3 -B test/test_r2i_changes.py.
Labels: доказано / скорее всего / возможно.

## VERDICT r2i: ACCEPT WITH NOTES

## MUST-FIX
None.

## SHOULD
1. **vpe_fix's stale-State rule no longer matches simple_offboard. Vision is cut while setpoints still stream.** (доказано by code and arithmetic)
   - vpe_fix.py:179–183 states the design rule: `_STATE_STALE_TIMEOUT = state_watchdog_timeout` (4.5 s), "VPE is never cut while simple_offboard still streams setpoints".
   - vpe_fix still counts "now − last State" (`_fcu_state_unknown`, ~line 808). r2i simple_offboard now counts from `state_rx + period` while poses flow (state_link.h).
   - With a HEARTBEAT-only loss, the gate closes at last State + 4.5 s, but the stream runs until last State + 5.5 s.
   - Gazebo S9 short gap, in about 50 % of phases (4 HEARTBEATs dropped, 5.0 s without State): no vision for ~0.5 s in OFFBOARD, then an EKF xy reset onto the B2 medoid. Long gap: ~1 s without vision before the stream stops.
   - Harm is small: a short dead-reckoning gap, and S9 is `acceptance_eligible=False` (gate.py:53–54). On a real UART a HEARTBEAT-only loss is скорее всего unrealistic.
   - The README does not analyse this. Either align vpe_fix (same fcuLinkSilentNs idea; would need its own P1 tests) or record it as an accepted difference and fix the comment at vpe_fix.py:179–183. That is chat 1's / owner's choice. It does not change P1 for real link loss.
2. **The HEARTBEAT-only stop moved from 4.5 s to 5.5 s after the last HEARTBEAT, and launch test_06 was rewritten to match.**
   - This is a contract change of an image test, not of a judge. It is justified, because the old contract cannot coexist with Gazebo S9 (proof in 1a).
   - It should still be stated to the owner explicitly as a changed number (rule 9 spirit).
3. **README wording is inexact** (доказано by test_state_link.cpp and the heartbeat_13 numbers).
   - (a) "≥ 5,0 с — всегда и до конца разрыва": the stop comes before the next HEARTBEAT *returns*, not before the drop window ends. In heartbeat_13 the long window ended at 74.464 and r2i stopped at 74.967. The test checks `f < back` (next HEARTBEAT), not the window end.
   - (b) "никогда не раньше 4,5 с настоящей потери" holds for HEARTBEAT-only loss. For a total loss the stop can come up to one pose period (~33 ms) earlier. The test allows `TH - FAST`, as the README itself says elsewhere ("± 1 отсчёт").
4. **`state_heartbeat_period` is not range-checked** (возможно, only on misconfiguration).
   - A value above ~1.0 delays every HEARTBEAT-only stop by the same amount: the stop is at last State + period + 4.5. S4 total loss is not affected, because it uses the pose stream.
   - Suggest clamping it to (0, 1.5] s or refusing other values at start. Nothing in the image overrides it (grep of launch/py/yaml).
5. **Dependence on local_position.**
   - If anything else publishes `/mavros/local_position/pose`, a dead MAVROS is no longer seen as a total loss. The stop then comes at last State + 5.5 s, which can be after the S4 respawn (kill + 5 s).
   - In the image only tests publish it (test_simple_offboard_launch.py, simtime, offboard.py); the product only subscribes (vpe_publisher.cpp:112, selfcheck) — скорее всего fine. Keep it that way, and say so in state_link.h.
   - If PX4 does not send LOCAL_POSITION_NED (no position estimate), the rule falls back to r2h's (возможно: S9-like behaviour returns on a drone without local position). The pose rate on the drone is unmeasured; the README already says so.

## Checked and fine

### 1. S9 / watchdog (simple_offboard + state_link.h)

**1a. Proof: no design passes Gazebo S9 and keeps "stop 4.5 s after the last HEARTBEAT" for HEARTBEAT-only loss** (доказано)
- HEARTBEATs come at t = φ + k (1 Hz). A drop window [a, a+D) removes m HEARTBEATs. The receiver then sees (m+1) s between States.
- During a HEARTBEAT-only loss, State arrivals are the only evidence (poses carry no HEARTBEAT information). So any rule is a threshold T on the time since the last State.
- D = 3.5 s: m = 3 or 4. m = 4 when a HEARTBEAT falls within the first 0.5 s of the window, which is 50 % of phases (r2h failed 72/143 in the test sweep). The silence is then 5.0 s, so passing the short window needs T ≥ 5.0 s.
- D = 5.0 s: m = 5 for generic phases, so the next State comes 6.0 s after the last one. Stopping needs T < 6.0 s.
- So T ∈ [5.0, 6.0), and T = 4.5 is excluded. r2i uses T = period + 4.5 = 5.5 s: the middle of that interval, with a 0.5 s margin each side. Gazebo's largest HEARTBEAT gap over 77 flights was 1.24 s (vpe_fix.py:177).

**1b. Total link loss at loss time L** (доказано)
- The fast stream stops at L. If L is within one period of the last State, the start is the last pose (≤ L) and the stop comes at L + 4.5 s minus up to one pose period.
- My rebuild of test_state_link.cpp (g++ -O1, /tmp): all cases OK. Sweep: "link loss: stop after the loss began r2i <= 4.510 s, r2h <= 4.510 s"; "S9 phases: 143, r2h stopped the 3.5 s gap in 72 of them, r2i in none".
- If the pose stream had already stopped before the last State, the start is the State: the r2h rule, which stops earlier (the safe side).

**1c. S4 (MAVROS killed at K, respawn after 5 s + startup)** (доказано)
- r2i stops at ≈ K + 4.5 s. r2h stopped in (K+3.5, K+4.5]. The worst-case margin to the respawn (≥ K + 5 s; vision_pose came up 5.49–6.22 s after the last State in SITL, vpe_fix.py:181–183) is unchanged.
- A pose from the respawned MAVROS would move the start to state_rx + 1 s. That can happen only after K + 5, after the stop.
- The comment above the watchdog (simple_offboard.cpp:1268–1281) is still true.

**1d. S2 freeze, S3 kill, pilot** (доказано by code)
- S2 (SIGSTOP 2 s, gate.py:521–527): stopOnPublisherResume() runs first in publishSetpoint() on the steady clock (simple_offboard.cpp:1263); unchanged.
- S3 (SIGKILL of simple_offboard): the watchdog is not involved.
- Pilot: handleState() unchanged.
- The only behaviour change is a later stop, and only while poses keep arriving without States.

**1e. Edge cases of fcuLinkSilentNs** (доказано by code)
- Both times use the same clock: monotonicNs() (simple_offboard.cpp:705 and :758).
- `state_rx_ns_ = 0` (State with a stale or zero stamp) gives now − 0, so it stops if armed, as r2h.
- Pose header stamps are not used (receipt time), so stale or zero pose stamps do not matter.
- `fast_rx = 0` or `period ≤ 0` falls back to r2h.
- use_sim_time: same as r2h (both freeze with /clock).
- No local_position: falls back to r2h (see SHOULD 5).
- All of this is under mutex_ (pose write at :756–758, read at :1282).

### 2. vpe_fix in AUTO.LAND
- **P1 / P1b hold** (доказано by code; test_r2i_vpe 8 OK per logs):
  - `_evaluate_gate` checks unknown FCU state first and closes.
  - connected=False closes at once (unchanged).
  - `state_callback` now also re-decides at once on an AUTO.LAND edge (`self.in_auto_land != was_auto_land`).
  - LAND → disarm: "disarmed (warm-up)" plus the revert on the disarm edge, unchanged.
- **Possible harms, none blocking** (возможно; only Gazebo C8 and the drone can show them):
  - **Single marker near the floor:** the gate opens on ≥ 1 marker within 1.5 s plus 0.5 s hysteresis. Near the floor a planar-ambiguous single marker can push xy in the last ~0.3 m. The existing guards still apply: `_XY_JUMP_MAX` 0.15 m, `_Z_JUMP_MAX` 0.3 m, `_Z_FLOOR_GUARD` −0.3 m.
  - **Re-entry during LAND after a pause > 0.4 s:** EKF xy is reset onto the B2 medoid (3 poses, ≤ 0.3 s wait). Whether PX4 Land shifts its xy setpoint with the reset counter was not verified in PX4 source here.
  - **A failsafe LAND that came from lost position:** vision coming back may clear the failsafe. A return to OFFBOARD is blocked, because simple_offboard stops its stream on any non-own exit from OFFBOARD (handleState, left_offboard) — скорее всего safe.
- Other armed modes stay silent (`not (in_offboard or in_auto_land)`).

### 3. Bytes and scope (доказано by sha256sum / diff -rq)
- Same bytes as r2h: drone.py fa6abf8b, flight.py ed352ff1, camera_fix.py 4a15d699.
- `diff -rq` of src r2h → r2i: only CMakeLists.txt, flight_marker.py (one line, 0.7 → 0.9), simple_offboard.cpp, vpe_fix.py, test_simple_offboard_px4model_launch.py and vpe_fix_h2_r2/README.md. New files: state_link.h, ref/vpe_fix_r2h_66d806ba.py, tests_r4/.
- test_r2i_changes.py: 6 OK (rerun by me).
- Outside src: test_r2h.py and test_r2h_vpe.py each have one path-retarget line; test_r2h_final.py and test_pins_r2h.py were moved to test/r2h_only. These are not in EDITS (test folder only), so not a product change.
- Judges, S tests and criteria are not in this folder. The A11 check below confirms the judge and gate bytes are A10's.

---

# A11 — C8 judge package /work/c8_judge_r2i_a11_20261111 vs A10 ed. 2

## VERDICT A11: ACCEPT WITH NOTES

## MUST-FIX
None.

## SHOULD
1. **31/31 is not checkable from saved files.**
   - tests/test_c8_b2.sh prints `RESULT pass=… fail=…` only to stdout (line 205). tests/out_130657 holds 38 per-test entries but no saved RESULT line.
   - The 31 `t` cases exist in the script. "31/31" rests on PROGRESS.md line 4 (возможно true; I did not rerun, because the A11 folder is read-only for this review).
   - Suggest `tee` of the RESULT line into the out dir.
2. r2i SHOULD 1 (vision cut ~0.5–1 s during S9 HEARTBEAT gaps) will show in A11 heartbeat runs. Read S9 diagnostics with that in mind.

## Checked and fine (доказано unless marked)

**(1) Same bytes as A10 (cmp):**
- verify_flight_c8.py, executor/gate.py, executor/run_sim.snapshot.sh, candidate/parameters/vpe_freshness_optin.py.
- expect/ and legacy/: diff -rq shows no differences.
- The only other copy of vpe_freshness_optin.py is test output (tests/out_130657/mix/), not part of the package.

**(2) After the renames** (A10 → A11 folder, fixed_image_r2h → r2i, make_a10 → make_a11) and CR stripping, the remaining differences are exactly:
- candidate vpe_fix = r2i f0dc7c18 (sha equal to the image's src);
- the vpe_fix sha in vpe_profile_optin.py and in executor/vpe_gate_diagnostic_p1.py (66d806ba → f0dc7c18);
- the helper sha in vpe_diagnostic_entry.py (220fccd7 → 8627e8c9);
- run.sh: PRODUCT_SHA256SUMS sha 48e9d830 → 05ffb9e6 (= the file's actual sha), plus comments;
- the MANIFEST reference 548bd261 → 855f9f93 (= the actual sha of r2i MANIFEST_SHA256.txt) in a8_checks.py;
- launcher v37 → v38, ACCEPTED_PINS_b → f6de13cf (= the actual pins sha);
- the pins and manifest filenames in tests;
- a8_checks.py: an added `.replace` for the A11 comment.
- sitl_setup.py and vision_c8.launch.py differ only by renames and comments. test_entry_order.py, a6, a7, a8_judge_*, a9, d1 and ledger_check differ only by renames or line endings (0 lines after normalization).

**PRODUCT_SHA256SUMS:** 505 paths in the same order as A10. It passes `sha256sum -c` on r2i's install and fails 36 lines on r2h's install.

**Pins frozen_inputs_c8_r2i_a11_01.json:**
- Key sets of combined_files (15), repo_files (72), run_files (17) and ledger_files (32) equal A10's after the renames. No r2h or A10 strings are left.
- Every sha was recomputed and matches. The exceptions are run_files drone.py, run_files flight_profile.py and @run/drone.py: run-time copies with no file in executor/. Their shas equal A10's and the image bytes (fa6abf8b, 5b8e2a12).
- combined_manifest_sha256 02c5faf4 = manifest.json. sdk drone.py sha OK. legacy_verifier_sha256 equals A10's.
- c8_target: only path renames and an added "a11" note. Identity `c8_4070` is unchanged (judge bytes are A10's).
- The changed shas are exactly the vpe_fix / helper / run.sh / PRODUCT / simple_offboard (src and install) / MANIFEST / tsv / vision_c8.launch / sitl_setup entries expected from r2i.

**(3) tests/a10_vpe_as_drone.py: line endings only.** The A10 copy has CRLF on 159/159 lines, the A11 copy has 0 CRs. After `tr -d '\r'` and the renames the diff is 0 lines. The chat-1 hypothesis is confirmed.

**(4) Bindings unchanged:** expect/ and executor/gate.py (scenario list gate.py:19, S9 at :597–618, kill/freeze at :521–535, S4 oracle) are byte-identical to A10, and judge identity c8_4070 is unchanged.

**(5)** See SHOULD 1.
