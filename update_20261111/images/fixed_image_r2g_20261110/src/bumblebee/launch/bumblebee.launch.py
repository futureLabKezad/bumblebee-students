# Copyright 2026 FutureLab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Main Bumblebee launch file (ROS 2 Jazzy)
Replaces bumblebee.launch (ROS 1 Noetic)
"""
import os
import importlib.util
from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, TimerAction, OpaqueFunction
from launch.conditions import IfCondition, UnlessCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource, AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression, EnvironmentVariable
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _mavros_candidate(context):
    # Read the owner's current YAML without modifying it. A malformed or
    # conflicting layout aborts launch before any connection is established.
    helper_path = Path(__file__).with_name('mavros_scoped_config.py')
    spec = importlib.util.spec_from_file_location('mavros_scoped_candidate', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    config = helper.write_scoped_config(
        LaunchConfiguration('mavros_params_path').perform(context),
        fcu_url=os.environ.get('BB_FCU_URL', '').strip() or None,
        tgt_system=int(LaunchConfiguration('fcu_sys_id').perform(context)))
    return [Node(package='mavros', executable='mavros_node', output='screen',
                 respawn=True, respawn_delay=5.0, parameters=[config],
                 arguments=helper.MAVROS_ARGUMENTS,
                 remappings=helper.MAVROS_REMAPPINGS)]


def generate_launch_description():
    # Arguments (same as ROS 1 version)
    args = [
        DeclareLaunchArgument('fcu_conn', default_value='uart',
                              description='FCU connection type: uart, usb, tcp, udp, sitl, hitl'),
        DeclareLaunchArgument('fcu_ip', default_value='127.0.0.1'),
        DeclareLaunchArgument('fcu_sys_id', default_value='1'),
        DeclareLaunchArgument('mavros_params_path', default_value='/home/lb/mavros_params.yaml'),
        DeclareLaunchArgument('gcs_bridge', default_value='tcp'),
        DeclareLaunchArgument('web_video_server', default_value='true'),
        DeclareLaunchArgument('rosbridge', default_value='true'),
        DeclareLaunchArgument('main_camera', default_value='true'),
        DeclareLaunchArgument('optical_flow', default_value='false'),
        DeclareLaunchArgument('aruco', default_value='true'),
        DeclareLaunchArgument('rangefinder_vl53l1x', default_value='false'),
        DeclareLaunchArgument('led', default_value='false'),
        DeclareLaunchArgument('blocks', default_value='false'),
        DeclareLaunchArgument('rc', default_value='false'),
        DeclareLaunchArgument('force_init', default_value='true'),
        DeclareLaunchArgument('simulator', default_value='false'),
        DeclareLaunchArgument(
            'aruco_exposure_preset',
            default_value='aruco_outdoor',
            description='libcamera AGC exposure mode preset for main_camera '
                        '(aruco_outdoor / aruco_indoor / aruco_dim). '
                        'TODO: wire preset into libcamera control flow once '
                        'v4l2_camera_node exposes a control to switch AGC mode at runtime.'),
    ]

    fcu_conn = LaunchConfiguration('fcu_conn')
    gcs_bridge = LaunchConfiguration('gcs_bridge')
    fcu_ip = LaunchConfiguration('fcu_ip')
    fcu_sys_id = LaunchConfiguration('fcu_sys_id')

    # ── MAVROS ──────────────────────────────────────────────────────────────
    # No global __node rename: each flight plugin keeps its own namespace.
    mavros_node = OpaqueFunction(function=_mavros_candidate)

    # ── SIMPLE OFFBOARD ─────────────────────────────────────────────────────
    simple_offboard = Node(
        package='bumblebee',
        executable='simple_offboard',
        name='simple_offboard',
        output='screen',
        parameters=[{
            'reference_frames.main_camera_optical': 'map',
            'terrain_frame_mode': 'range',
            'arming_timeout': 15.0,
            'setpoint_smooth_alpha': 0.5,  # 2026-06-05: REVERTED to original
        }],
        remappings=[
            # Explicit legacy aliases retained for unchanged SDK/relay consumers.
            ('/mavros/local_position/pose', '/mavros/mavros/pose'),
            ('/mavros/local_position/velocity_body', '/mavros/mavros/velocity_body'),
            # The MAVROS cmd plugin receives an explicit service alias.
            ('/mavros/cmd/arming', '/mavros/mavros/arming'),
            # All flight commands cross the independent stamp filter before MAVROS.
            ('/mavros/setpoint_position/local', '/setpoint_freshness/input/position'),
            ('/mavros/setpoint_raw/local', '/setpoint_freshness/input/position_raw'),
            ('/mavros/setpoint_attitude/attitude', '/setpoint_freshness/input/attitude'),
            ('/mavros/setpoint_raw/attitude', '/setpoint_freshness/input/attitude_raw'),
            ('/mavros/setpoint_attitude/cmd_vel', '/setpoint_freshness/input/rates'),
            ('/mavros/setpoint_attitude/thrust', '/setpoint_freshness/input/thrust'),
        ],
    )

    # Independent consumer; failure ends the stream, with no automatic respawn.
    setpoint_freshness = Node(
        package='bumblebee', executable='setpoint_freshness.py', name='setpoint_freshness',
        output='screen', respawn=False,
        remappings=[
            ('~/output/position', '/mavros/setpoint_position/local'),
            ('~/output/position_raw', '/mavros/setpoint_raw/local'),
            ('~/output/attitude', '/mavros/setpoint_attitude/attitude'),
            ('~/output/attitude_raw', '/mavros/setpoint_raw/attitude'),
            ('~/output/rates', '/mavros/setpoint_attitude/cmd_vel'),
            ('~/output/thrust', '/mavros/setpoint_attitude/thrust'),
        ],
    )

    # ── CAMERAS (v4l2_camera + libcamerify via RPi libcamera v0.7.0+rpt20260205) ────
    # libcamerify maps: /dev/video0 → libcamera:0 (i2c@88000) → main_camera (swapped)
    #                   /dev/video8 → libcamera:1 (i2c@80000) → second_camera (swapped)
    _LIBCAM = '/home/lb/libcamera/build'
    _libcam_extra_env = {
        'LD_PRELOAD': _LIBCAM + '/src/v4l2/v4l2-compat.so',
        'LD_LIBRARY_PATH': [
            _LIBCAM + '/src/libcamera:',
            _LIBCAM + '/src/libcamera/base:',
            _LIBCAM + '/subprojects/libpisp/src:',
            EnvironmentVariable('LD_LIBRARY_PATH', default_value=''),
        ],
        'LIBCAMERA_IPA_MODULE_PATH': _LIBCAM + '/src/ipa/rpi/pisp',
    }
    # Bottom camera: custom AGC tuning caps the shutter at 8 ms so auto
    # exposure trades motion blur for analogue gain. Stock ov5647.json lets
    # the shutter ramp to 66 ms indoors — in flight that blurs ArUco markers
    # into invisibility (2026-06-10: detection fell to ~0.3 Hz mid-air, vpe
    # reseed storm, drone darted). Applies to this process only; the forward
    # camera keeps the stock tuning.
    _libcam_main_env = dict(_libcam_extra_env)
    _libcam_main_env['LIBCAMERA_RPI_TUNING_FILE'] = '/home/lb/ov5647_aruco.json'
    # Operator-selectable exposure preset for ArUco (Block E). The preset name
    # is exposed as an env var so it can be inspected from /proc/<pid>/environ
    # and consumed by future control hooks. The actual AGC mode switch in
    # libcamera will be wired in a follow-up patch (see launch arg description).
    _libcam_main_env['ARUCO_EXPOSURE_PRESET'] = LaunchConfiguration('aruco_exposure_preset')

    main_camera = Node(
        package='v4l2_camera',
        executable='v4l2_camera_node',
        name='main_camera',
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        additional_env=_libcam_main_env,
        parameters=[{
            'video_device': '/dev/main_camera',
            'image_size': [640, 480],
            'pixel_format': 'YUYV',
            'camera_frame_id': 'main_camera_optical',
            'output_encoding': 'yuv422_yuy2',
            'camera_name': 'main_camera',
            'camera_info_url': 'file:///home/lb/.ros/camera_info/main_camera_640x480.yaml',
            # Request 30 fps from sensor (libcamerify proxies S_PARM).
            # aruco_detect itself will run at whatever it can; fresher frames = less latency.
            'time_per_frame': [1, 30],
        }],
        remappings=[
            ('image_raw', 'main_camera/image_raw_yuv'),
            ('camera_info', 'main_camera/camera_info_raw'),
        ],
    )

    main_camera_fix = Node(
        package='bumblebee',
        executable='camera_fix.py',
        name='main_camera_fix',
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        namespace='main_camera',
        parameters=[{
            'input_topic': 'image_raw_yuv',
            'output_topic': 'image_raw',
            'row_period': 5,
        }],
    )

    second_camera = Node(
        package='v4l2_camera',
        executable='v4l2_camera_node',
        name='second_camera',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
        additional_env=_libcam_extra_env,
        parameters=[{
            'video_device': '/dev/second_camera',
            'image_size': [640, 480],
            'pixel_format': 'YUYV',
            'camera_frame_id': 'second_camera_optical',
            'output_encoding': 'yuv422_yuy2',
            'camera_name': 'second_camera',
            'camera_info_url': 'file:///home/lb/.ros/camera_info/second_camera_320x240.yaml',
        }],
        remappings=[
            ('image_raw', 'second_camera/image_raw_yuv'),
            ('camera_info', 'second_camera/camera_info_raw'),
        ],
    )

    second_camera_fix = Node(
        package='bumblebee',
        executable='camera_fix.py',
        name='second_camera_fix',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
        namespace='second_camera',
        parameters=[{
            'input_topic': 'image_raw_yuv',
            'output_topic': 'image_raw',
            'row_period': 5,
        }],
    )

    optical_flow = Node(
        package='bumblebee',
        executable='optical_flow_node',
        name='optical_flow',
        output='screen',
        respawn=True,
        respawn_delay=3.0,
        condition=IfCondition(LaunchConfiguration('optical_flow')),
        parameters=[{
            'calc_flow_gyro': True,
            'roi_rad': 0.8,
            'disable_on_vpe': False,
        }],
        remappings=[
            ('image_raw', 'main_camera/image_raw'),
            ('camera_info', 'main_camera/camera_info'),
        ],
    )

    # ── ARUCO ────────────────────────────────────────────────────────────────
    aruco_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('bumblebee'), 'launch', 'aruco.launch.py'])
        ),
        condition=IfCondition(LaunchConfiguration('aruco')),
        launch_arguments={
            'aruco_vpe': 'true',
            'force_init': 'false',
        }.items(),
    )

    # ── CAMERA TF FRAME ──────────────────────────────────────────────────────
    main_camera_frame = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='main_camera_frame',
        # down + backward orientation
        arguments=['0.05', '0', '-0.07', '-1.5707963', '0', '3.1415926',
                   'base_link', 'main_camera_optical'],
    )

    second_camera_frame = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='second_camera_frame',
        arguments=['0.05', '0', '0.05', '-1.5707963', '0', '0',
                   'base_link', 'second_camera_optical'],
    )

    # ── CAMERA MARKERS ───────────────────────────────────────────────────────
    camera_markers = Node(
        package='bumblebee',
        executable='camera_markers',
        name='main_camera_markers',
        namespace='main_camera',
        parameters=[{'scale': 3.0}],
    )

    # ── MJPEG SERVER (replaces web_video_server, port 8080) ─────────────────
    web_video_server = Node(
        package='bumblebee',
        executable='ros_mjpeg_server.py',
        name='ros_mjpeg_server',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
        condition=IfCondition(LaunchConfiguration('web_video_server')),
    )

    # ── ROSBRIDGE ────────────────────────────────────────────────────────────
    rosbridge_launch = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            PathJoinSubstitution([FindPackageShare('rosbridge_server'), 'launch', 'rosbridge_websocket_launch.xml'])
        ),
        condition=IfCondition(LaunchConfiguration('rosbridge')),
    )

    # ── TF2 WEB REPUBLISHER ──────────────────────────────────────────────────
    tf2_web_republisher = Node(
        package='tf2_web_republisher',
        executable='tf2_web_republisher_node',
        name='tf2_web_republisher',
        output='screen',
        condition=IfCondition(LaunchConfiguration('rosbridge')),
    )

    # ── QOS RELAY (BEST_EFFORT → RELIABLE for rosbridge) ────────────────────
    qos_relay = Node(
        package='bumblebee',
        executable='qos_relay.py',
        name='qos_relay',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
    )

    # ── SET PARAMS ───────────────────────────────────────────────────────────
    set_params = Node(
        package='bumblebee',
        executable='set_params.py',
        name='set_params',
        output='screen',
    )

    # ── BUMBLEBEE BRIDGE ─────────────────────────────────────────────────────
    bumblebee_bridge = Node(
        package='bumblebee_bridge',
        executable='bumblebee_controller',
        name='bumblebee_unified_controller',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
        parameters=[{'mode': 'manual'}],
    )

    # ── WHEEL MOTOR INIT (send neutral stop to ATtiny on startup) ───────────
    wheel_init = ExecuteProcess(
        cmd=['python3', '-c',
             'import sys; sys.path.insert(0, "/home/lb/ros2_ws/src/bumblebee/examples"); '
             'import drone; drone.set_servo_speed(128); print("wheel: stop sent")'],
        output='screen',
    )

    # System metrics HTTP server (port 8888) is launched by the standalone
    # sys_metrics.service systemd unit on boot, not from here -- running it
    # in both places caused EADDRINUSE respawn loops in /tmp/bumblebee.log.

    # Delay second camera by 8s so main_camera fully claims ISP before second starts
    second_camera_delayed = TimerAction(period=8.0, actions=[second_camera, second_camera_fix])

    # Delay aruco and optical_flow by 15s so camera_fix publisher is ready
    aruco_delayed = TimerAction(period=15.0, actions=[aruco_launch, optical_flow])

    # ── RC CONTROL (servo CH9 + wheel CH7) ───────────────────────────────────
    servo_rc = Node(
        package='bumblebee',
        executable='servo_rc.py',
        name='servo_rc',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
    )
    wheel_rc = Node(
        package='bumblebee',
        executable='wheel_rc.py',
        name='wheel_rc',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
    )
    # Delay RC nodes by 25s so MAVROS RC topics are publishing
    rc_delayed = TimerAction(period=25.0, actions=[servo_rc, wheel_rc])

    return LaunchDescription(args + [
        mavros_node,
        simple_offboard,
        setpoint_freshness,
        qos_relay,
        main_camera,
        main_camera_fix,
        second_camera_delayed,
        main_camera_frame,
        second_camera_frame,
        camera_markers,
        aruco_delayed,
        rc_delayed,
        web_video_server,
        rosbridge_launch,
        tf2_web_republisher,
        set_params,
        bumblebee_bridge,
        wheel_init,
    ])
