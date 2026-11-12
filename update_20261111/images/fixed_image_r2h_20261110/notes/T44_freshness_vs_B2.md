# T44: freshness opt-in in C8 vs r2h B2 (10.11.2026, session «Разборы и правки кода»)

**What.** In the C8 package (A9 executor/vpe_diagnostic_entry.py), vpe_fix runs wrapped by
candidate/parameters/vpe_freshness_optin.py (FreshnessMixin, combined_13). On the drone there is no wrapper:
aruco.launch.py starts vpe_fix.py directly (only a test-harness copy of the optin exists in the image).
The wrapper publishes only `last_pose`, with that pose's own measurement stamp (_StampedPublisher.publish:
`message.pose.pose is not pose` raises _NoFreshEmission → the publish is dropped).
r2h B2 publishes the medoid of the fresh poses for 0.5 s after a pause. When the medoid is not the newest pose,
the wrapper drops it. A drop does not set `_last_publish_time`, so after 0.3 s a new re-entry wait starts.

**Bench evidence (доказано on the offline bench, the real classes; PIN_C33 of the loaded optin module set to the file
under test, no file edited).** Probe: notes/probe/probe_freshness.py (output notes/probe/probe_freshness_out.txt).
Pause 2.1–3.1 s, then poses with 1 cm noise, 24 Hz, 20 seeds:

| variant | first sample after the pause | samples sent in the 0.5 s after the first (of 16) | largest gap in the first 0.6 s |
|---|---|---|---|
| r2g | 0.008 s | 16 | 0.033 s |
| r2g + freshness | 0.008 s | 16 | 0.033 s |
| r2h (as on the drone) | 0.108 s | 16 | 0.033 s |
| r2h + freshness (C8) | median 0.142, max 0.308 s | median 8, min 3 | **up to 0.70 s** |

A gap > 0.4 s makes PX4 stop EV again and reset onto one sample: the exact event B2 is meant to soften.
B1 is not affected: with the blinking marker there are 0 pauses > 0.4 s with or without freshness (r2g: 8 pauses of 1.03 s).

**Meaning.** An A10 built literally «как A9» tests B2 in C8 not as it runs on the drone (the drone has no wrapper).
The drone itself is not at risk from this. Options for chat 1: keep freshness (B2 partly suppressed in the count) /
C8 without freshness, like the drone / change freshness to accept the medoid (new code in the candidate).
