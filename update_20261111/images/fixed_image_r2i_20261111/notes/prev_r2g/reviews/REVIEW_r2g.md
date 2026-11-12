# REVIEW r2g (= r2f + S4) — independent review, 10.11.2026

Reviewer: independent agent (read-only on r2f/r2g; probes in `/work/review_r2g_20261110/`). No drone, no Gazebo, no ROS run needed.
Labels: **доказано** = checked by a command/probe; **скорее всего** = reasoned from code, no control; **возможно** = hypothesis.

## Verdict: ACCEPT WITH SHOULDs
No MUST-FIX. The fix is exactly S4, small, and correct for every path I traced. One SHOULD (a test that does not
discriminate). Notes are hardening/documentation only.

## What was checked (results)
- `diff -rq r2f/src r2g/src`: only `examples/drone.py` differs — **доказано**. The diff (= `notes/DIFF_r2g_vs_r2f.txt`, matches
  byte-for-byte) adds `_vision_arm_t` (drone.py:579-581), sets/clears it in `_on_fcu_state` (:948, :957, :959-960), adds
  `_vision_silence_age()` (:1755-1765), and switches the two watchdogs to it (navigate_wait :2210-2218, safe_land :2473-2476)
  plus the takeoff warning text (:2348-2351). Nothing else — **доказано**.
- `tools/make_r2g.py` applied to a fresh copy of r2f drone.py reproduces r2g drone.py sha 068e6eb4… — **доказано**.
- `vision_pose_age()` (:1743-1752) is byte-identical to r2f (outside the diff hunks); `_on_vpe_pose` untouched; false
  frames (raw markers_used) still do not extend vision (test + mutation M5/M10 kill) — **доказано**.
- Sums: `sha256sum -c` OK for SHA256SUMS (4), MANIFEST_SHA256.txt (358), INSTALL_SHA256.txt (16, from
  install/bumblebee/lib/bumblebee); image_manifest_r2.tsv drone.py row = 068e6eb4… — **доказано**.
- Tests re-run in a copy (`/work/review_r2g_20261110/base`): test_r2g 27/27 OK; test_r2f on r2g fails exactly the 2 tests
  test_r2g replaces (warning text, source-string check); q6 17, r2b 5, r2c 6 (2 skip), r2d 14, r2e 2, guards 87 (2 skip) OK —
  **доказано**. ROS suites not re-run (S4 touches no ROS wiring; `/mavros/state` -> `_on_fcu_state` binding is already
  asserted by guards test :654).

### Arm reference — path by path (probes `probe_r2g.py`, output in probe_out.txt; all on the package FakeFCU)
| Case | Result |
|---|---|
| State callback thread vs script thread | Writer = spin thread only; reader = script thread. Safe except a theoretical double-read, see NOTE-3. |
| First State already armed (script started on an armed vehicle) | arm ref = first State seen; fly_to with no pose lands at ref+6.0..6.5 s (P3) — **доказано**. Conservative: ref ≥ real arm. |
| Link loss (connected=false, armed=false) | not a reset; ref kept across 5 s of link loss (P1) — **доказано**. |
| Re-arm after disarm | disarm edge clears; new flight gets a fresh ref; poses from ref+3 s → no landing (P4) — **доказано**. |
| Pose from an earlier flight, same process | `_vpe_pose_time` wins over the arm ref, so behaviour = r2f (age from that old pose). Documented in README "Что остаётся". |
| Poses only before the arm | `_vpe_pose_time` set → identical to r2f — **доказано** (test_pose_before_arm_counts_as_in_r2f). |
| safe_land when disarmed, no pose | ref None → silence None → no straight-land forcing, as r2f (P6) — **доказано**. |
| Ground hold / near-floor (T30) | Action unchanged (`_land_if_offboard`: /land in the 2.5 s hold, AUTO.LAND after). With the takeoff's 25 s limit the guard cannot fire inside the hold unless the ref is stale (NOTE-1). |
| Takeoff limit | from the arm the limit is never stricter than r2f's normal case (poses on the ground until spin-up, last pose ≤ arm). MAVROS State is ~1 Hz, so the ref is ≤ ~1 s after the real arm (slightly more lenient) — **скорее всего**. |

**Arm vs takeoff() call:** I agree with the arm. The watchdog only acts when `t.armed`; the takeoff() call precedes up to
2 s state wait + 3 s mode switch + 1 s settle + up to 45 s auto-arm call, none with motors running, which would eat the 25 s
climb budget; and fly_to/move after a pilot arm or on an already-armed vehicle would have no reference at all.

### Mutation testing (`mutate.py`, `mutate_out.txt`) — 11 mutants of the fix
Killed by test_r2g: M1 no disarm reset, M3 refresh ref on every armed State, M4 never set, M5 arm preferred over pose,
M6 safe_land 6 s, M7 limit +1 s, M8 safe_land back to r2f, M11 vision_pose_age() using the arm ref.
M10 (max(pose, arm)) survives test_r2g but is killed by guards (5 failures).
**Survivors:** M2 (reset the ref on the link-loss State) — see SHOULD-1; M9 (drop `msg.connected` when setting) — harmless
(MAVROS link-loss State carries armed=false).

### Install (independent, `install_check.sh` → `install_check_out.txt`; not their script)
All 40 differing files under install/ checked: 18 ELF files identical after swapping the equal-length folder name and
removing `.note.gnu.build-id` from both with objcopy (build-ids are 20 bytes and differ); 17 .pyc identical after the
16-byte header; 4 setup scripts differ only by the path; `egg-info/SOURCES.txt` lists fewer files in r2g (setuptools
metadata, not loaded at runtime). No files only in one tree. The claim in `notes/INSTALL_DIFF_r2f_r2g.txt` (16 files of
lib/bumblebee: path + build-id only) is **доказано**; it is narrower than the whole install, see NOTE-5.

## MUST-FIX
None.

## SHOULD
**SHOULD-1 — test_r2g.py:125 `test_link_loss_state_is_not_a_disarm` does not discriminate.** The virtual clock does not move
between the link-loss State and the re-armed State, so a mutant that clears `_vision_arm_t` on the link-loss State and
re-sets it on reconnect gives the same value and passes (M2 survived — **доказано**). Failure scenario it should catch: a
future edit resets on link loss → after a 10 s link drop mid-flight the no-vision count restarts and a no-pose flight gets
another 6/25 s of coasting. Fix: `self.clock.sleep(5.0)` before and during the link loss (as in probe P1, which passes on r2g).

## NOTE
**NOTE-1 — stale arm ref when a disarm happens during a link loss** (drone.py:953-960). The ref is cleared only on the
connected armed→disarmed edge (same rule as `_arm_ref_z`, `_auto_arm_ok_t`). Sequence: armed, link lost
(connected=false, armed=false), vehicle disarms while the link is down, link returns disarmed → no edge, ref stays. Probe P2
(**доказано** on FakeFCU): 60 s later the next `takeoff()` in the same process, still with no vpe_fix pose ever, fires
`Vision lost for 60.0s (... since the arm, limit 25.0s)` at the first sample → `/land` in the ground hold (disarm on the
ground). Safe side (no flight), and needs: zero poses in the whole process + link loss spanning a disarm + a second
takeoff. Hardening if ever touched: clear `_vision_arm_t` on any `connected and not armed` State (link-loss State stays excluded).

**NOTE-2 — takeoff budget does not carry into the next leg.** Probe P5 (**доказано**): takeoff without any pose returns True
(1 m climb in ~3 s); poses begin at arm+8 s; the following `fly_to` lands at arm+6.0 s. r2f: fly_to completes. This is the
intended S4 behaviour (flying 6 s with no vision), and `flight.py` would already safe_land on its own hover check, but the
README could say plainly: "takeoff() can succeed with no vision; the first fly_to/move then lands at once if > 6 s since
the arm". Same applies to `examples/flight/navigate_wait.py:29` (takeoff leg via `navigate_wait(auto_arm=True)` with the
default 6 s limit, not 25 s): with no pose before the arm it now lands 6 s after the arm — no stricter than r2f's normal
"poses on the ground" case.

**NOTE-3 — `_vision_silence_age()` reads `_vision_arm_t` twice** (drone.py:1763-1764). If the disarm-edge State (spin
thread) lands between the `is not None` check and the subtraction, `time.monotonic() - None` raises TypeError in the script
thread. Probe `race_probe.py` (exact function source, toggling thread, switch interval 1 µs, Python 3.12.3): 24.7 M calls,
32 M toggles, 0 errors — not reproduced (**возможно**, CPython 3.12 does not seem to switch threads inside that window). At
the moment it could happen the vehicle is already disarmed. One-line hardening: `a = _vision_arm_t; return None if a is None
else time.monotonic() - a` (same for `_vpe_pose_time`).

**NOTE-4 — error wording** (drone.py:2216): "since the arm" is chosen by re-reading `_vpe_pose_time` after `silence` was
computed; a pose arriving in between only changes the wording. Cosmetic.

**NOTE-5 — README/labels.** The r2g README section is accurate against code and tests (27 = 16 r2f + 9 S4 + 2 controls;
limits 25/6/3 s; reset rules). It does not mention the install comparison (`notes/INSTALL_DIFF_r2f_r2g.txt`), which covers
only lib/bumblebee; the full install also differs in .so libs/pyc/setup scripts (path + build-id + pyc header) and
egg-info SOURCES.txt (metadata). Claims in the r2g section carry no доказано/скорее всего labels although the header
announces them; most are test-backed, the "Почему от взвода" reasoning is by code (= скорее всего).

## Probe files (`/work/review_r2g_20261110/`)
`base/` (copy of r2g test+src; test_r2g path pointer changed to the copy), `mutate.py` + `mutate_out.txt`,
`probe_r2g.py` (P1-P6), `race_probe.py`, `race_probe_count.py`, `install_check.sh` + `install_check_out.txt`,
`mk/` (make_r2g.py reproduction).
