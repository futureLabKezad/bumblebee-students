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
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('camera_id', default_value='1'),
        DeclareLaunchArgument('width',     default_value='320'),
        DeclareLaunchArgument('height',    default_value='240'),
        DeclareLaunchArgument('fps',       default_value='5'),

        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='second_camera_frame',
            arguments=['0.05', '0', '0.05', '-1.5707963', '0', '0',
                       'base_link', 'second_camera_optical'],
        ),

        ComposableNodeContainer(
            name='second_camera_nodelet_manager',
            namespace='',
            package='rclcpp_components',
            executable='component_container',
            composable_node_descriptions=[
                ComposableNode(
                    package='libcamera_ros',
                    plugin='libcamera_ros::LibcameraRos',
                    name='second_camera',
                    parameters=[{
                        'camera_name': '',
                        'camera_id': LaunchConfiguration('camera_id'),
                        'frame_id': 'second_camera_optical',
                        'stream_role': 'video',
                        'pixel_format': 'RGB888',
                        'use_ros_time': True,
                        'resolution.width': LaunchConfiguration('width'),
                        'resolution.height': LaunchConfiguration('height'),
                        'control.fps': LaunchConfiguration('fps'),
                    }],
                    remappings=[
                        ('image_raw', 'second_camera/image_raw'),
                        ('camera_info', 'second_camera/camera_info'),
                    ],
                ),
            ],
            output='screen',
        ),
    ])
