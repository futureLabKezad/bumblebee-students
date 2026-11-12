# vpe_fix H2 round 2: tests carried by port-rc3

Copies (byte for byte) of the round-2 hand-over `/work/pc_inventory_20261019/vpe_fix_h2_r2_20261030` (accepted 02.11.2026)
and of the verifier's strict pairs evaluator. Offline: ROS is stubbed (`rosstub.py`), no DDS, no simulator.
Registered in `CMakeLists.txt` (BUILD_TESTING) with `ament_add_pytest_test`, like the other package tests.

| test | what |
|---|---|
| `tests_r2/test_pins_r2.py` (5) | code pins: every P1 part equal to the accepted P1 file 7f107882; only the 4 declared H2 parts differ. Replaces the two P1 lock tests of vpe_p1_fix_02 (owner decision 02.11.2026, «Заменить», ANSWER=REPLACE) |
| `tests_r2/test_h2_r2.py` (33) | unknown write outcome: the override is kept until a write of its original; guarantee matrix; replay of 30.10 |
| `tests_r2/test_in_air_writes.py` (1) | no extra ParamSet while armed against 7f107882 (1198 scenarios) |

Data: `ref/` = vpe_fix 7f107882 (port-rc2) and c33a52bf (P1 suite reference), `eval/` = strict s1_eval (ef7a76fc, verifier
02.11) and the session-1 s1_eval 01badf57, `real_s1/` = the two bench session-1 logs of 30.10 (T5a, MAVROS died on a
param write). The file under test is `src/python/vpe_fix.py` (env PIN_TARGET / H2_TARGET).
