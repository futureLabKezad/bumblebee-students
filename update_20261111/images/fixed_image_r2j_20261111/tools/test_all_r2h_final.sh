#!/bin/bash
# test_all_r2h_final.sh - FINAL r2h checks WITHOUT ROS (T44). No drone, no Gazebo, no DDS.
# Run: bash tools/test_all_r2h_final.sh   -> notes/test_logs/*.txt and the summary on stdout
set -u
F=/work/fixed_image_r2h_20261110
cd $F
OUT=notes/test_logs
mkdir -p $OUT
H=src/bumblebee/test/vpe_fix_h2_r2
VPE=$F/src/bumblebee/src/python/vpe_fix.py
REF=$F/$H/ref/vpe_fix_r2g_3b8a93d4.py
plain() {    # plain LOG CMD...
    local log=$1; shift
    nice -n 19 timeout 900 "$@" > $OUT/$log 2>&1
    echo "$log exit=$? | $(grep -E '^(Ran|OK|FAILED)' $OUT/$log | tr '\n' ' ')"
}
echo "# r2h FINAL tests (no ROS) $(date '+%d.%m.%Y %H:%M')"
echo "## final vs candidate (T44)"
plain r2h_final.txt python3 -B test/test_r2h_final.py -v
echo "## r2h"
plain r2h_drone.txt python3 -B test/test_r2h.py -v
plain r2h_vpe.txt python3 -B test/test_r2h_vpe.py -v
plain r2h_pins.txt python3 -B test/test_pins_r2h.py -v
echo "## carried over from r2g"
for t in test_q6_fixes test_r2b_wake test_r2c_navigate_float test_r2d test_r2e; do plain $t.txt python3 -B test/$t.py; done
plain guards.txt python3 -B -m unittest discover -s src/bumblebee/test -p test_drone_flight_guards.py
plain notify.txt python3 -B -m unittest discover -s src/bumblebee/test -p test_notify_manager.py
T=$(mktemp -d)
g++ -std=c++17 -Wall -Wextra -Werror -I src/bumblebee/src/cpp test/test_script_lease.cpp -o $T/lease > $OUT/script_lease.txt 2>&1 \
    && $T/lease >> $OUT/script_lease.txt 2>&1; echo "script_lease.txt exit=$? | $(tail -1 $OUT/script_lease.txt)"
rm -rf $T
echo "## vpe_fix suites as CMake registers them (r2h)"
mkdir -p notes/h2_out
plain h2_r2.txt env H2_TARGET=$VPE H2_CONTROL=$F/$H/ref/vpe_fix_7f107882.py H2_EVAL=$F/$H/eval H2_OUT=$F/notes/h2_out \
    H2_REAL_S1=$F/$H/real_s1 python3 -B $H/tests_r2/test_h2_r2.py
plain h2_in_air.txt env H2_TARGET=$VPE H2_CONTROL=$F/$H/ref/vpe_fix_7f107882.py H2_OUT=$F/notes/h2_out python3 -B $H/tests_r2/test_in_air_writes.py
plain pins_r2_on_r2g_copy.txt env PIN_TARGET=$REF PIN_C33=$F/$H/ref/vpe_fix_c33_product.py PIN_P1=$F/$H/ref/vpe_fix_7f107882.py \
    PIN_HARNESS=$F/$H/tests_existing/harness python3 -B $H/tests_r2/test_pins_r2.py
plain pins_r3.txt env PIN_TARGET=$VPE PIN_R2G=$REF PIN_HARNESS=$F/$H/tests_existing/harness python3 -B $H/tests_r3/test_pins_r3.py
echo "## controls (EXPECTED to fail): r3 pins on r2g itself; the round-2 pins on r2h"
plain pins_r3_on_r2g_EXPECTED_FAIL.txt env PIN_TARGET=$REF PIN_R2G=$REF PIN_HARNESS=$F/$H/tests_existing/harness \
    python3 -B $H/tests_r3/test_pins_r3.py
plain pins_r2_on_r2h_EXPECTED_FAIL.txt env PIN_TARGET=$VPE PIN_C33=$F/$H/ref/vpe_fix_c33_product.py PIN_P1=$F/$H/ref/vpe_fix_7f107882.py \
    PIN_HARNESS=$F/$H/tests_existing/harness python3 -B $H/tests_r2/test_pins_r2.py
find . -name __pycache__ -type d -prune -exec rm -rf {} +
