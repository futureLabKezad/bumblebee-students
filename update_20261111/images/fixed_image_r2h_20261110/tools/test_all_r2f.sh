#!/bin/bash
# test_all_r2f.sh - every r2f check after the build. Run from anywhere: bash tools/test_all_r2f.sh
# No drone, no Gazebo. ROS parts: localhost only, domain 91, private /bb_test_* names (guard_graph()).
set -u
F=/work/fixed_image_r2f_20261110
R2E=/work/fixed_image_r2e_20261109
cd $F
OUT=notes/test_logs
mkdir -p $OUT
E="source /opt/ros/jazzy/setup.bash; source /work/ws_sitl/install/setup.bash; source /work/ws_mavros214_bp02/install/setup.bash"
rosrun() {   # rosrun INSTALL LOG CMD...
    local inst=$1 log=$2; shift 2
    env -i HOME=$HOME PATH=/usr/bin:/bin ROS_DOMAIN_ID=${DOM:-91} ROS_LOCALHOST_ONLY=1 \
        bash -c "$E; source $inst/local_setup.bash; nice -n 19 timeout 600 $*" > $OUT/$log 2>&1
    echo "$log exit=$?"
}
plain() {    # plain LOG CMD...
    local log=$1; shift
    nice -n 19 timeout 600 "$@" > $OUT/$log 2>&1
    echo "$log exit=$? | $(grep -E '^(Ran|OK|FAILED)' $OUT/$log | tr '\n' ' ')"
}
echo "# r2f tests $(date '+%d.%m.%Y %H:%M')"
echo "## no ROS"
plain r2f.txt python3 -B test/test_r2f.py -v
for t in test_q6_fixes test_r2b_wake test_r2c_navigate_float test_r2d test_r2e; do plain $t.txt python3 -B test/$t.py; done
plain guards.txt python3 -B -m unittest discover -s src/bumblebee/test -p test_drone_flight_guards.py
plain notify.txt python3 -B -m unittest discover -s src/bumblebee/test -p test_notify_manager.py
T=$(mktemp -d)
g++ -std=c++17 -Wall -Wextra -Werror -I src/bumblebee/src/cpp test/test_script_lease.cpp -o $T/lease > $OUT/script_lease.txt 2>&1 \
    && $T/lease >> $OUT/script_lease.txt 2>&1; echo "script_lease.txt exit=$? | $(tail -1 $OUT/script_lease.txt)"
rm -rf $T
echo "## ROS, no Gazebo"
rosrun $F/install gtest_simple_offboard.txt build/bumblebee/test_simple_offboard
tail -3 $OUT/gtest_simple_offboard.txt
rosrun $F/install flag_ros_r2f.txt python3 -B test/test_r2f_flag_ros.py --binary $F/install/bumblebee/lib/bumblebee/simple_offboard --expect r2f
grep -h 'R2F_FLAG_ROS_PASS' $OUT/flag_ros_r2f.txt
rosrun $R2E/install flag_ros_r2e_control.txt python3 -B test/test_r2f_flag_ros.py --binary $R2E/install/bumblebee/lib/bumblebee/simple_offboard --expect r2e
grep -h 'R2F_FLAG_ROS_PASS' $OUT/flag_ros_r2e_control.txt
rosrun $F/install vpe_sub_ros.txt python3 -B test/test_r2f_vpe_sub_ros.py
grep -h 'R2F_VPE_SUB_ROS_PASS' $OUT/vpe_sub_ros.txt
rosrun $F/install cancel_launch.txt python3 -B -m pytest -q src/bumblebee/test/test_drone_py_cancel_launch.py
tail -1 $OUT/cancel_launch.txt
DOM=89 rosrun $F/install lease_ros.txt python3 -B test/test_r2d_lease_ros.py
grep -h 'R2D_LEASE_ROS_PASS' $OUT/lease_ros.txt | cut -c1-300
