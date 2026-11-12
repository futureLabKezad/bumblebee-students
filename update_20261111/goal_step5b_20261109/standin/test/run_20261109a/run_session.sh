#!/bin/bash
export BB_STANDIN_SID=$$ BB_STANDIN_LOG=/work/goal_step5b_20261109/standin/test/run_20261109a/standin_calls.jsonl
export PATH=/work/goal_step5b_20261109/standin/bin:$PATH
bash -c 'exec -a /dummy/install/aruco_pose/lib/aruco_pose/aruco_map sleep 300' &
echo "inside_match $!" > /work/goal_step5b_20261109/standin/test/run_20261109a/pids.txt
sleep 301 &
echo "inside_nomatch $!" >> /work/goal_step5b_20261109/standin/test/run_20261109a/pids.txt
/usr/bin/python3 -c 'import time; time.sleep(302)' --ros-args -r map_markers:=aruco_map/map -r map_pose:=aruco_map/pose &
echo "inside_aruco_detect_like $!" >> /work/goal_step5b_20261109/standin/test/run_20261109a/pids.txt
sleep 0.5
echo "which pkill: $(command -v pkill)" > /work/goal_step5b_20261109/standin/test/run_20261109a/which.txt
pkill -f aruco_pose/aruco_map > /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stdout.txt 2> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stderr.txt; echo "call1 $?" > /work/goal_step5b_20261109/standin/test/run_20261109a/exit_codes.txt
pkill -f aruco_pose/aruco_map >> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stdout.txt 2>> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stderr.txt; echo "call2_nomatch $?" >> /work/goal_step5b_20261109/standin/test/run_20261109a/exit_codes.txt
pkill -f 'aruco_.*map' >> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stdout.txt 2>> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stderr.txt; echo "call3_regex $?" >> /work/goal_step5b_20261109/standin/test/run_20261109a/exit_codes.txt
pkill -x sleep >> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stdout.txt 2>> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stderr.txt; echo "call4_other_form $?" >> /work/goal_step5b_20261109/standin/test/run_20261109a/exit_codes.txt
BB_STANDIN_SID=1 pkill -f aruco_pose/aruco_map >> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stdout.txt 2>> /work/goal_step5b_20261109/standin/test/run_20261109a/standin_stderr.txt; echo "call5_wrong_sid $?" >> /work/goal_step5b_20261109/standin/test/run_20261109a/exit_codes.txt
sleep 0.5
touch /work/goal_step5b_20261109/standin/test/run_20261109a/session_done
sleep 30
