#!/bin/bash
# test_ros_r2i.sh - r2i tests WITH ROS (T46): no Gazebo, no PX4, no drone; private domains, localhost only.
# 1) colcon test of the image (CMake-registered: gtest test_simple_offboard, the three simple_offboard launch tests,
#    the vpe_fix suites and pins r2/r3/r4) -> notes/colcon_test_r2i.log
# 2) controls of the S9 realtime launch test (test_06): r2h's test file on the r2i install (expected FAIL: the old 5.0 s
#    long gap no longer stops) and r2i's test file on the r2h install (expected FAIL: r2h stops at 4.5 s, before 5.45 s)
#    -> notes/test_logs/ros_control_*.txt
set -u
F=/work/fixed_image_r2i_20261111
R2H=/work/fixed_image_r2h_20261110
cd $F
OUT=notes/test_logs
mkdir -p $OUT notes/controls
envrun() {   # envrun INSTALL DOMAIN CMD...
    local inst=$1 dom=$2; shift 2
    env -i HOME=/home/user PATH=/usr/local/bin:/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 ROS_DOMAIN_ID=$dom \
        ROS_LOCALHOST_ONLY=1 INST=$inst bash -c 'source /opt/ros/jazzy/setup.bash; source /work/ws_mavros214_bp02/install/local_setup.bash;
        source $INST/local_setup.bash; "$@"' _ "$@"
}
echo "# r2i ROS tests $(date '+%d.%m.%Y %H:%M')"
envrun $F/install 95 nice -n 19 colcon test --base-paths src --executor sequential --packages-select bumblebee \
    --ctest-args -R "simple_offboard|vpe_fix" > notes/colcon_test_r2i.log 2>&1
echo "colcon test exit=$?"
envrun $F/install 95 colcon test-result --test-result-base build/bumblebee --verbose >> notes/colcon_test_r2i.log 2>&1
tail -3 notes/colcon_test_r2i.log
for x in build/bumblebee/test_results/bumblebee/*.xml; do
    echo "$(basename $x) $(grep -o '<testsuite[^>]*>' $x | head -1 | grep -o 'tests="[0-9]*"\|failures="[0-9]*"\|errors="[0-9]*"' | tr '\n' ' ')"
done
# controls: copies of the test file and its helpers in notes/controls/<name>/ (src is not touched)
T=src/bumblebee/test
mkdir -p notes/controls/old_test notes/controls/new_test
for h in fake_mavros.py test_safety.py executor_support.py fake_px4_model.py; do
    cp -p $T/$h notes/controls/old_test/; cp -p $T/$h notes/controls/new_test/
done
cp -p $R2H/$T/test_simple_offboard_px4model_launch.py notes/controls/old_test/
cp -p $T/test_simple_offboard_px4model_launch.py notes/controls/new_test/
envrun $R2H/install 98 timeout 300 launch_test notes/controls/old_test/test_simple_offboard_px4model_launch.py \
    > $OUT/ros_baseline_r2h_test_on_r2h.txt 2>&1
echo "baseline r2h test file on the r2h install exit=$? (expected 0): $(grep -E 'test_06.*(ok|FAIL|ERROR)' $OUT/ros_baseline_r2h_test_on_r2h.txt | head -2 | tr '\n' ' ')"
envrun $F/install 96 timeout 300 launch_test notes/controls/old_test/test_simple_offboard_px4model_launch.py \
    > $OUT/ros_control_r2h_test_on_r2i_EXPECTED_FAIL.txt 2>&1
echo "control r2h test_06 on the r2i install exit=$? (expected != 0): $(grep -E 'test_06.*(ok|FAIL|ERROR)|AssertionError' $OUT/ros_control_r2h_test_on_r2i_EXPECTED_FAIL.txt | head -3 | tr '\n' ' ')"
envrun $R2H/install 97 timeout 300 launch_test notes/controls/new_test/test_simple_offboard_px4model_launch.py \
    > $OUT/ros_control_r2i_test_on_r2h_EXPECTED_FAIL.txt 2>&1
echo "control r2i test_06 on the r2h install exit=$? (expected != 0): $(grep -E 'test_06.*(ok|FAIL|ERROR)|AssertionError' $OUT/ros_control_r2i_test_on_r2h_EXPECTED_FAIL.txt | head -3 | tr '\n' ' ')"
find notes/controls -name __pycache__ -type d -prune -exec rm -rf {} +
