#!/bin/bash
# test_all_r2j.sh - r2j checks WITHOUT ROS (T53; the r2i suite, test_r2j_changes instead of test_r2i_changes). No drone, no Gazebo, no DDS. ROS tests: tools/test_ros_r2i.sh.
# Run: bash tools/test_all_r2i.sh   -> notes/test_logs/*.txt and the summary on stdout
set -u
F=/work/fixed_image_r2j_20261111
cd $F
OUT=notes/test_logs
mkdir -p $OUT
H=src/bumblebee/test/vpe_fix_h2_r2
VPE=$F/src/bumblebee/src/python/vpe_fix.py
R2G_REF=$F/$H/ref/vpe_fix_r2g_3b8a93d4.py
R2H_REF=$F/$H/ref/vpe_fix_r2h_66d806ba.py
plain() {    # plain LOG CMD...
    local log=$1; shift
    nice -n 19 timeout 900 "$@" > $OUT/$log 2>&1
    echo "$log exit=$? | $(grep -E '^(Ran|OK|FAILED)' $OUT/$log | tr '\n' ' ')"
}
cxx() {      # cxx LOG SRC
    local log=$1 src=$2 bin=$F/build/r2i_test_bins/$(basename $2 .cpp)   # build/ is outside MANIFEST
    mkdir -p $F/build/r2i_test_bins
    g++ -std=c++17 -Wall -Wextra -Werror -I src/bumblebee/src/cpp $src -o $bin > $OUT/$log 2>&1 && $bin >> $OUT/$log 2>&1
    echo "$log exit=$? | $(tail -1 $OUT/$log)"
}
echo "# r2j tests (no ROS) $(date '+%d.%m.%Y %H:%M')"
echo "## r2i new"
plain r2j_changes.txt python3 -B test/test_r2j_changes.py -v
plain r2i_vpe.txt python3 -B test/test_r2i_vpe.py -v
cxx state_link.txt test/test_state_link.cpp
echo "## carried over from r2h (on r2i)"
plain r2h_drone.txt python3 -B test/test_r2h.py -v
plain r2h_vpe.txt python3 -B test/test_r2h_vpe.py -v
for t in test_q6_fixes test_r2b_wake test_r2c_navigate_float test_r2d test_r2e; do plain $t.txt python3 -B test/$t.py; done
plain guards.txt python3 -B -m unittest discover -s src/bumblebee/test -p test_drone_flight_guards.py
plain notify.txt python3 -B -m unittest discover -s src/bumblebee/test -p test_notify_manager.py
cxx script_lease.txt test/test_script_lease.cpp
echo "## vpe_fix suites as CMake registers them (r2i)"
mkdir -p notes/h2_out
plain h2_r2.txt env H2_TARGET=$VPE H2_CONTROL=$F/$H/ref/vpe_fix_7f107882.py H2_EVAL=$F/$H/eval H2_OUT=$F/notes/h2_out \
    H2_REAL_S1=$F/$H/real_s1 python3 -B $H/tests_r2/test_h2_r2.py
plain h2_in_air.txt env H2_TARGET=$VPE H2_CONTROL=$F/$H/ref/vpe_fix_7f107882.py H2_OUT=$F/notes/h2_out python3 -B $H/tests_r2/test_in_air_writes.py
plain pins_r2_on_r2g_copy.txt env PIN_TARGET=$R2G_REF PIN_C33=$F/$H/ref/vpe_fix_c33_product.py PIN_P1=$F/$H/ref/vpe_fix_7f107882.py \
    PIN_HARNESS=$F/$H/tests_existing/harness python3 -B $H/tests_r2/test_pins_r2.py
plain pins_r3_on_r2h_copy.txt env PIN_TARGET=$R2H_REF PIN_R2G=$R2G_REF PIN_HARNESS=$F/$H/tests_existing/harness python3 -B $H/tests_r3/test_pins_r3.py
plain pins_r4.txt env PIN_TARGET=$VPE PIN_R2H=$R2H_REF PIN_HARNESS=$F/$H/tests_existing/harness python3 -B $H/tests_r4/test_pins_r4.py
echo "## controls (EXPECTED to fail): r4 pins on r2h itself; r3 pins on r2i"
plain pins_r4_on_r2h_EXPECTED_FAIL.txt env PIN_TARGET=$R2H_REF PIN_R2H=$R2H_REF PIN_HARNESS=$F/$H/tests_existing/harness \
    python3 -B $H/tests_r4/test_pins_r4.py
plain pins_r3_on_r2i_EXPECTED_FAIL.txt env PIN_TARGET=$VPE PIN_R2G=$R2G_REF PIN_HARNESS=$F/$H/tests_existing/harness \
    python3 -B $H/tests_r3/test_pins_r3.py
find . -path ./build -prune -o -path ./install -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
