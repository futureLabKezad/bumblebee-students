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
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('ws281x', default_value='true'),
        DeclareLaunchArgument('led_effect', default_value='true'),
        DeclareLaunchArgument('led_notify', default_value='true'),
        DeclareLaunchArgument('led_count', default_value='72'),
        DeclareLaunchArgument('gpio_pin', default_value='21'),
        DeclareLaunchArgument('simulator', default_value='false'),

        # ws281x LED strip driver
        Node(
            package='ws281x',
            executable='ws281x_node',
            name='led',
            output='screen',
            parameters=[{
                'led_count': LaunchConfiguration('led_count'),
                'gpio_pin': LaunchConfiguration('gpio_pin'),
                'brightness': 64,
                'strip_type': 'WS2811_STRIP_GRB',
                'target_frequency': 800000,
                'dma': 10,
                'invert': False,
            }],
            condition=IfCondition(PythonExpression([
                LaunchConfiguration('ws281x'), " and not ", LaunchConfiguration('simulator')
            ])),
        ),

        # High-level LED effects + event notifications
        Node(
            package='bumblebee',
            executable='led',
            name='led_effect',
            output='screen',
            parameters=[{
                'led': 'led',
                'blink_rate': 2.0,
                'fade_period': 0.5,
                'rainbow_period': 5.0,
                'notify': {
                    'startup':      {'r': 255, 'g': 255, 'b': 255},
                    'connected':    {'effect': 'rainbow'},
                    'disconnected': {'effect': 'blink', 'r': 255, 'g': 50, 'b': 50},
                    'acro':         {'r': 245, 'g': 155, 'b': 0},
                    'stabilized':   {'r': 30,  'g': 180, 'b': 50},
                    'altctl':       {'r': 255, 'g': 255, 'b': 40},
                    'posctl':       {'r': 50,  'g': 100, 'b': 220},
                    'offboard':     {'r': 220, 'g': 20,  'b': 250},
                    'low_battery':  {'threshold': 3.6, 'effect': 'blink_fast', 'r': 255, 'g': 0, 'b': 0},
                    'error':        {'effect': 'flash', 'r': 255, 'g': 0, 'b': 0},
                },
            }],
            condition=IfCondition(LaunchConfiguration('led_effect')),
        ),
    ])
