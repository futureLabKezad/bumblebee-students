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

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression, PathJoinSubstitution
from launch_ros.actions import Node, ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    dir_z = LaunchConfiguration('direction_z')
    dir_y = LaunchConfiguration('direction_y')
    sim   = LaunchConfiguration('simulator')
    type_ = LaunchConfiguration('type')

    return LaunchDescription([
        DeclareLaunchArgument('direction_z', default_value='down',
                              description='Direction the camera points: down, up, forward, backward'),
        DeclareLaunchArgument('direction_y', default_value='backward',
                              description='Direction the camera cable points: backward, forward'),
        DeclareLaunchArgument('type', default_value='libcamera',
                              description='Camera interface: libcamera, v4l2'),
        DeclareLaunchArgument('camera_id', default_value='0'),
        DeclareLaunchArgument('device', default_value='/dev/video0'),
        DeclareLaunchArgument('width', default_value='320'),
        DeclareLaunchArgument('height', default_value='240'),
        DeclareLaunchArgument('fps', default_value='40'),
        DeclareLaunchArgument('simulator', default_value='false'),

        # TF: down + backward (default)
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             arguments=['0.05', '0', '-0.07', '-1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical'],
             condition=IfCondition(PythonExpression(["'", dir_z, "' == 'down' and '", dir_y, "' == 'backward'"]))),
        # TF: down + forward
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             arguments=['0.05', '0', '-0.07', '1.5707963', '0', '3.1415926', 'base_link', 'main_camera_optical'],
             condition=IfCondition(PythonExpression(["'", dir_z, "' == 'down' and '", dir_y, "' == 'forward'"]))),
        # TF: up + backward
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             arguments=['0.05', '0', '0.07', '1.5707963', '0', '0', 'base_link', 'main_camera_optical'],
             condition=IfCondition(PythonExpression(["'", dir_z, "' == 'up' and '", dir_y, "' == 'backward'"]))),
        # TF: up + forward
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             arguments=['0.05', '0', '0.07', '-1.5707963', '0', '0', 'base_link', 'main_camera_optical'],
             condition=IfCondition(PythonExpression(["'", dir_z, "' == 'up' and '", dir_y, "' == 'forward'"]))),
        # TF: forward
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             arguments=['0.03', '0', '0.05', '-1.5707963', '0', '-1.5707963', 'base_link', 'main_camera_optical'],
             condition=IfCondition(PythonExpression(["'", dir_z, "' == 'forward'"]))),
        # TF: backward
        Node(package='tf2_ros', executable='static_transform_publisher', name='main_camera_frame',
             arguments=['-0.03', '0', '0.05', '1.5707963', '0', '-1.5707963', 'base_link', 'main_camera_optical'],
             condition=IfCondition(PythonExpression(["'", dir_z, "' == 'backward'"]))),

        # Camera container (libcamera)
        ComposableNodeContainer(
            name='main_camera_nodelet_manager',
            namespace='',
            package='rclcpp_components',
            executable='component_container',
            composable_node_descriptions=[
                ComposableNode(
                    package='libcamera_ros',
                    plugin='libcamera_ros::LibcameraRos',
                    name='main_camera',
                    parameters=[{
                        'camera_name': '',
                        'camera_id': LaunchConfiguration('camera_id'),
                        'frame_id': 'main_camera_optical',
                        'calib_url': PathJoinSubstitution([
                            FindPackageShare('bumblebee'), 'camera_info',
                            ['fisheye_cam_', LaunchConfiguration('width'), 'x', LaunchConfiguration('height'), '.yaml']
                        ]),
                        'stream_role': 'still',
                        'pixel_format': 'RGB888',
                        'use_ros_time': True,
                        'resolution.width': LaunchConfiguration('width'),
                        'resolution.height': LaunchConfiguration('height'),
                        'control.fps': LaunchConfiguration('fps'),
                    }],
                    remappings=[
                        ('image_raw', 'main_camera/image_raw'),
                        ('camera_info', 'main_camera/camera_info'),
                    ],
                ),
            ],
            output='screen',
            condition=IfCondition(PythonExpression(["not ", sim, " and '", type_, "' == 'libcamera'"])),
        ),

        # Camera markers
        Node(
            package='bumblebee',
            executable='camera_markers',
            name='main_camera_markers',
            namespace='main_camera',
            parameters=[{'scale': 3.0}],
        ),
    ])
