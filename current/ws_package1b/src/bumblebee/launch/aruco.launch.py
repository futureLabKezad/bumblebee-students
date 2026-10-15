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
aruco.launch.py — запуск узлов ArUco-навигации (ROS 2)
Заменяет aruco.launch (ROS 1)
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    args = [
        DeclareLaunchArgument('aruco_detect', default_value='true'),
        DeclareLaunchArgument('aruco_map', default_value='true'),
        DeclareLaunchArgument('aruco_vpe', default_value='false'),
        DeclareLaunchArgument('placement', default_value='floor',
                              description='Markers placement: floor, ceiling, unknown'),
        DeclareLaunchArgument('length', default_value='0.15',
                              description='Length of not-in-map markers (m)'),
        DeclareLaunchArgument('map', default_value='map.txt',
                              description='Markers map file name'),
        DeclareLaunchArgument('force_init', default_value='false'),
        DeclareLaunchArgument('disable', default_value='false',
                              description='Disable detection, only run force_init'),
    ]

    aruco_detect_enabled = PythonExpression([
        "'", LaunchConfiguration('aruco_detect'), "' == 'true' and '",
        LaunchConfiguration('disable'), "' == 'false'"
    ])

    vpe_enabled = PythonExpression([
        "('", LaunchConfiguration('aruco_vpe'), "' == 'true' or '",
        LaunchConfiguration('force_init'), "' == 'true')"
    ])

    map_path = PathJoinSubstitution([
        FindPackageShare('aruco_pose'), 'map', LaunchConfiguration('map')
    ])

    # ── aruco_detect (Python — bypasses image_transport QoS issues) ──────────
    aruco_detect = Node(
        package='bumblebee',
        executable='aruco_detect.py',
        name='aruco_detect',
        output='screen',
        respawn=True,
        respawn_delay=1.0,
        condition=IfCondition(aruco_detect_enabled),
        parameters=[{
            'dictionary': 1,            # DICT_4X4_100
            'estimate_poses': True,
            'send_tf': True,
            'use_map_markers': LaunchConfiguration('aruco_map'),
            'length': 0.15,
            'corner_refinement_method': 3,  # APRILTAG — best subpixel under perspective
            'min_marker_perimeter_rate': 0.03,
            'map_file': map_path,
            # ── Detection-boost (Stage 1) ──
            # Narrower threshold sweep: 6 windows instead of 11 (~40% CPU saved here)
            'adaptive_thresh_win_size_max': 51,
            # Unsharp mask after CLAHE — restores edges under motion blur / oblique
            'use_unsharp': True,
            'unsharp_sigma': 1.0,
            'unsharp_amount': 0.6,
            # Aruco3 emulation — periodic downscale pass catches small markers at altitude
            'aruco3_downscale_every_n': 4,
            # ROI tracking — re-detect inside expanded previous-frame bboxes first
            'track_roi_expand': 1.5,
            'track_roi_min_px': 60,
            'track_sweep_min': 3,
            'track_sweep_max': 21,
            'track_sweep_step': 6,
            'track_keepalive_frames': 3,
        }],
        remappings=[
            ('image_raw',    'main_camera/image_raw'),
            ('camera_info',  'main_camera/camera_info'),
            ('map_markers',  'aruco_map/map'),
            ('markers',      'aruco_detect/markers'),
            ('debug',        'aruco_detect/debug'),
            ('map_pose',     'aruco_map/pose'),
            ('map_image',    'aruco_map/image'),
        ],
    )

    # ── aruco_map (C++) — DISABLED, replaced by Python aruco_detect.py ───────
    # aruco_map = Node(
    #     package='aruco_pose',
    #     executable='aruco_map',
    #     name='aruco_map',
    #     ...
    # )

    # ── vpe_fix — robust 30Hz VPE publisher using cached ArUco pose ───────────
    vpe_publisher = Node(
        package='bumblebee',
        executable='vpe_fix.py',
        name='vpe_publisher',
        output='screen',
        respawn=True,
        respawn_delay=5.0,
        condition=IfCondition(vpe_enabled),
    )

    return LaunchDescription(args + [aruco_detect, vpe_publisher])
