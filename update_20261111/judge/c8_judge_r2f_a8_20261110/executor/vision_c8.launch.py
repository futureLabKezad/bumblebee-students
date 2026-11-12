"""Ground camera chain for a separately frozen integration candidate.

C8 A7 copy (10.11.2026) of combined_trial_tools/vision.launch.py (sha c9fe8ba6): only the candidate-location
check differs. It requires exactly the C8 package candidate c8_judge_r2f_a8_20261110/candidate (the shared file accepts
only .../integration/combined_*). The detector-vs-manifest sha check is unchanged."""
import hashlib
import json
import os
from pathlib import Path
from launch import LaunchDescription
from launch.actions import ExecuteProcess
from launch_ros.actions import Node


def generate_launch_description():
    if (os.environ.get('ROS_LOCALHOST_ONLY') != '1' or
            os.environ.get('ROS_DOMAIN_ID') != '83' or
            os.environ.get('GZ_PARTITION') != 'bbtrial'):
        raise RuntimeError('Isolated SITL environment required')
    root = Path(os.environ['BB_COMBINED_ROOT']).resolve()
    if root != Path('/work/c8_judge_r2f_a8_20261110/candidate'):   # C8 A7: only this package's frozen candidate
        raise RuntimeError('C8 package candidate required')
    detector_path = root/'vision/aruco_detect.py'
    manifest = json.loads((root/'manifest.json').read_text())
    if hashlib.sha256(detector_path.read_bytes()).hexdigest() != manifest['files']['vision/aruco_detect.py']:
        raise RuntimeError('Detector differs from reviewed copy')
    py = '/work/sim/ros_stack/.venv/bin/python'
    common = {'use_sim_time': True}
    detector = {**common, 'dictionary': 1, 'estimate_poses': True,
        'send_tf': True, 'use_map_markers': True, 'length': .15,
        'corner_refinement_method': 3, 'min_marker_perimeter_rate': .03,
        'map_file': '/work/sim/worlds/aruco_map/map.input.txt',
        'adaptive_thresh_win_size_max': 51, 'use_unsharp': True,
        'unsharp_sigma': 1., 'unsharp_amount': .6, 'aruco3_downscale_every_n': 4,
        'track_roi_expand': 1.5, 'track_roi_min_px': 60, 'track_sweep_min': 3,
        'track_sweep_max': 21, 'track_sweep_step': 6, 'track_keepalive_frames': 3}
    arguments = ['--ros-args', '-r', '__node:=aruco_detect']
    for key, value in detector.items():
        arguments += ['-p', key+':='+str(value).lower() if isinstance(value, bool)
                      else key+':='+str(value)]
    for source, target in [('image_raw', 'main_camera/image_raw'),
            ('camera_info', 'main_camera/camera_info'), ('map_markers', 'aruco_map/map'),
            ('markers', 'aruco_detect/markers'), ('debug', 'aruco_detect/debug'),
            ('map_pose', 'aruco_map/pose'), ('map_image', 'aruco_map/image')]:
        arguments += ['-r', source+':='+target]
    return LaunchDescription([
        ExecuteProcess(cmd=[py, '/work/sim/ros_stack/gz_camera_bridge.py',
            '--ros-args', '-p', 'use_sim_time:=true', '-p', 'mode:=strict'], output='screen'),
        Node(package='bumblebee', executable='camera_fix.py', name='main_camera_fix',
             namespace='main_camera', prefix=py, parameters=[common], output='screen'),
        ExecuteProcess(cmd=[py, str(detector_path), *arguments], output='screen'),
        Node(package='tf2_ros', executable='static_transform_publisher',
            name='sitl_camera_tf', parameters=[common], output='screen', arguments=[
            '--x', '0.05', '--y', '0', '--z', '-0.07', '--yaw', '-1.5707963',
            '--pitch', '0', '--roll', '3.1415926', '--frame-id', 'base_link',
            '--child-frame-id', 'main_camera_optical']),
    ])
