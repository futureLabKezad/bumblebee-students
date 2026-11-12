"""Pinned flight controller and freshness filter, isolated from camera/VPE launch."""
import json
import os
from pathlib import Path
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    assert os.environ['ROS_DOMAIN_ID'] == '83' and os.environ['ROS_LOCALHOST_ONLY'] == '1'
    routes = json.loads(Path('/work/ws_package1b/setpoint_freshness_sitl_reference.json').read_text())
    common = {'use_sim_time': True}
    return LaunchDescription([
        Node(package='bumblebee', executable='setpoint_freshness.py',
             name='setpoint_freshness', output='screen', parameters=[common],
             remappings=[tuple(r) for r in routes['filter_node']['remappings']]),
        Node(package='bumblebee', executable='simple_offboard', name='simple_offboard',
             output='screen', parameters=[common, {
                 'reference_frames.main_camera_optical': 'map',
                 'terrain_frame_mode': 'range', 'arming_timeout': 15.,
                 'setpoint_smooth_alpha': .5}],
             remappings=[('/mavros/local_position/pose', '/mavros/mavros/pose'),
                 ('/mavros/local_position/velocity_body', '/mavros/mavros/velocity_body'),
                 ('/mavros/cmd/arming', '/mavros/mavros/arming')]
                 + [tuple(r) for r in routes['simple_offboard_remappings']]),
    ])
