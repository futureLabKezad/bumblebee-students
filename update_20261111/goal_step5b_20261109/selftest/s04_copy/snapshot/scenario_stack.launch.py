"""scenario_stack.launch.py - goal step 5 (Claude, 06.11.2026). SIMULATOR ONLY.

The drone's own ROS 2 nodes (product workspace /work/ws_package1b_port_03 = port-rc3, MAVROS bp02), with the node
names, parameters and remappings copied from the product's bumblebee.launch.py and aruco.launch.py. Differences from
the drone, each forced by the simulator (listed in the step-5 report):
  * camera: Gazebo camera bridge (/work/sim/ros_stack/gz_camera_bridge.py, mode strict -> image_raw_yuv) instead of
    v4l2_camera + libcamera; it also publishes /clock, so every node runs with use_sim_time true;
  * MAVROS: same scoped config helper (product mavros_scoped_config.py), source YAML = SITL copy of mavros214.yaml,
    fcu_url from BB_FCU_URL (must be udp://127.0.0.1:...), use_sim_time true;
  * aruco map file: /work/sim/worlds/aruco_map/map.input.txt (sha256 528b5adb... = the image's aruco_pose/map/map.txt);
  * Python nodes run with /work/sim/ros_stack/.venv/bin/python (OpenCV contrib, as all old SITL runs);
  * not started (no flight role): web video, rosbridge, tf2_web_republisher, qos_relay, camera_markers, set_params
    (read-only diagnostic), second camera, bumblebee_bridge, LED, RC.
"""
import importlib.util
import os
from pathlib import Path

from launch import LaunchDescription
from launch.actions import ExecuteProcess, OpaqueFunction
from launch_ros.actions import Node

PRODUCT_LAUNCH = Path('/work/ws_package1b_port_03/src/bumblebee/launch')
PY = '/work/sim/ros_stack/.venv/bin/python'
GZ_CAMERA_BRIDGE = '/work/sim/ros_stack/gz_camera_bridge.py'
MAP_FILE = '/work/sim/worlds/aruco_map/map.input.txt'
SIM = {'use_sim_time': True}


def _guard():
    if os.environ.get('ROS_LOCALHOST_ONLY') != '1' or os.environ.get('ROS_DOMAIN_ID') != '83':
        raise RuntimeError('SITL only: ROS_LOCALHOST_ONLY=1 and ROS_DOMAIN_ID=83 required')
    url = os.environ.get('BB_FCU_URL', '')
    if not url.startswith('udp://127.0.0.1:'):
        raise RuntimeError('SITL only: BB_FCU_URL must be udp://127.0.0.1:...')
    if not os.environ.get('BB_MAVROS_SOURCE_YAML'):
        raise RuntimeError('BB_MAVROS_SOURCE_YAML required (SITL copy of mavros214.yaml)')


def _mavros(context):
    spec = importlib.util.spec_from_file_location('mavros_scoped_config', PRODUCT_LAUNCH / 'mavros_scoped_config.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    config = helper.write_scoped_config(os.environ['BB_MAVROS_SOURCE_YAML'],
                                        os.environ.get('BB_MAVROS_SCOPED_YAML') or None,
                                        fcu_url=os.environ['BB_FCU_URL'], tgt_system=1, use_sim_time=True)
    return [Node(package='mavros', executable='mavros_node', output='screen',
                 respawn=False, parameters=[config],
                 arguments=helper.MAVROS_ARGUMENTS, remappings=helper.MAVROS_REMAPPINGS)]


def _detector_overrides():
    """Trial-only knob (06.11, finding F1): the image's aruco_detect sleeps while disarmed and not in OFFBOARD
    (gate_by_flight_state=True by default), but flight.py checks markers BEFORE arming, so it can never pass.
    BB_TRIAL_ARUCO_ALWAYS=1 sets gate_by_flight_state=False (detection always on, as before the gate existed).
    Default: off (the image as it is)."""
    return {'gate_by_flight_state': False} if os.environ.get('BB_TRIAL_ARUCO_ALWAYS') == '1' else {}


def generate_launch_description():
    _guard()
    nodes = [
        OpaqueFunction(function=_mavros),
        # camera source (SITL substitute for v4l2_camera_node): Gazebo camera -> /main_camera/image_raw_yuv,
        # /main_camera/camera_info_raw and /clock
        ExecuteProcess(cmd=[PY, GZ_CAMERA_BRIDGE, '--ros-args', '-p', 'use_sim_time:=true', '-p', 'mode:=strict'],
                       output='screen'),
        Node(package='bumblebee', executable='camera_fix.py', name='main_camera_fix', output='screen',
             namespace='main_camera', prefix=PY,
             parameters=[SIM, {'input_topic': 'image_raw_yuv', 'output_topic': 'image_raw', 'row_period': 5}]),
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             parameters=[SIM],
             arguments=['0.05', '0', '-0.07', '-1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical']),
        Node(package='bumblebee', executable='aruco_detect.py', name='aruco_detect', output='screen', prefix=PY,
             parameters=[SIM, {
                 'dictionary': 1, 'estimate_poses': True, 'send_tf': True, 'use_map_markers': True, 'length': 0.15,
                 'corner_refinement_method': 3, 'min_marker_perimeter_rate': 0.03, 'map_file': MAP_FILE,
                 'adaptive_thresh_win_size_max': 51, 'use_unsharp': True, 'unsharp_sigma': 1.0, 'unsharp_amount': 0.6,
                 'aruco3_downscale_every_n': 4, 'track_roi_expand': 1.5, 'track_roi_min_px': 60, 'track_sweep_min': 3,
                 'track_sweep_max': 21, 'track_sweep_step': 6, 'track_keepalive_frames': 3},
                         _detector_overrides()],
             remappings=[('image_raw', 'main_camera/image_raw'), ('camera_info', 'main_camera/camera_info'),
                         ('map_markers', 'aruco_map/map'), ('markers', 'aruco_detect/markers'),
                         ('debug', 'aruco_detect/debug'), ('map_pose', 'aruco_map/pose'),
                         ('map_image', 'aruco_map/image')]),
        Node(package='bumblebee', executable='vpe_fix.py', name='vpe_publisher', output='screen', prefix=PY,
             parameters=[SIM]),
        Node(package='bumblebee', executable='simple_offboard', name='simple_offboard', output='screen',
             parameters=[SIM, {'reference_frames.main_camera_optical': 'map', 'terrain_frame_mode': 'range',
                               'arming_timeout': 15.0, 'setpoint_smooth_alpha': 0.5}],
             remappings=[('/mavros/local_position/pose', '/mavros/mavros/pose'),
                         ('/mavros/local_position/velocity_body', '/mavros/mavros/velocity_body'),
                         ('/mavros/cmd/arming', '/mavros/mavros/arming'),
                         ('/mavros/setpoint_position/local', '/setpoint_freshness/input/position'),
                         ('/mavros/setpoint_raw/local', '/setpoint_freshness/input/position_raw'),
                         ('/mavros/setpoint_attitude/attitude', '/setpoint_freshness/input/attitude'),
                         ('/mavros/setpoint_raw/attitude', '/setpoint_freshness/input/attitude_raw'),
                         ('/mavros/setpoint_attitude/cmd_vel', '/setpoint_freshness/input/rates'),
                         ('/mavros/setpoint_attitude/thrust', '/setpoint_freshness/input/thrust')]),
        Node(package='bumblebee', executable='setpoint_freshness.py', name='setpoint_freshness', output='screen',
             parameters=[SIM],
             remappings=[('~/output/position', '/mavros/setpoint_position/local'),
                         ('~/output/position_raw', '/mavros/setpoint_raw/local'),
                         ('~/output/attitude', '/mavros/setpoint_attitude/attitude'),
                         ('~/output/attitude_raw', '/mavros/setpoint_raw/attitude'),
                         ('~/output/rates', '/mavros/setpoint_attitude/cmd_vel'),
                         ('~/output/thrust', '/mavros/setpoint_attitude/thrust')]),
    ]
    return LaunchDescription(nodes)
