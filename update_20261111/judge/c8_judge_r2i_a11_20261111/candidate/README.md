# combined_c8_r2e (T28, 09.11.2026). ТОЛЬКО СИМУЛЯТОР. flight_accepted=false
combined_13 + r2e: flight_profile.py (13 names), vpe_fix.py (3b8a93d4), aruco_detect.py (66f061ec); pins of the
closure (profile sha, 13), freshness and profile opt-in (vpe sha), honest airframe check (D7), RC contract 4061 (D1).
Changed files: manifest.json changed_from_combined_13; every line: ../DIFF_exec_b.md.
A8 (T38, 10.11.2026): image r2f (the three image copies above are byte-identical in r2f), airframe 4070 (vpe_profile_optin.py checks 4070). README.md is not a pinned candidate file.
A9 (T39, 10.11.2026): image r2g (the three image copies are byte-identical in r2g); the rest as A8.
A10 (T44, 10.11.2026): image FINAL r2h: vpe_fix.py = r2h (66d806ba); the vpe_fix pin of vpe_profile_optin.py = r2h; vpe_freshness_optin.py is kept as in A9 but NOT loaded (chat 1 variant B: vpe_fix publishes as on the drone); flight_profile.py and aruco_detect.py byte-identical in r2g and r2h; the rest as A9.
A11 (T46, 11.11.2026): image r2i: vpe_fix.py = r2i (f0dc7c18, vision in AUTO.LAND); the vpe_fix pin of vpe_profile_optin.py = r2i; the rest as A10 (variant B: no freshness opt-in).
