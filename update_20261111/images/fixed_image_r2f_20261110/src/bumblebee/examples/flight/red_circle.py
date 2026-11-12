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

# This example makes the drone find and follow the red circle.
# Input topic: main_camera/image_raw
# Output topics: cv/mask, cv/red_circle

import time
import threading
import rclpy
from rclpy.node import Node
from rclpy.duration import Duration
import cv2
import numpy as np
from math import nan
from sensor_msgs.msg import Image, CameraInfo
from geometry_msgs.msg import PointStamped, Point
from cv_bridge import CvBridge
from bumblebee import long_callback
from bumblebee.srv import SetPosition, GetTelemetry
import tf2_ros
import tf2_geometry_msgs
import image_geometry

rclpy.init()
node = Node('cv')
bridge = CvBridge()

_executor = rclpy.executors.MultiThreadedExecutor()
_executor.add_node(node)
threading.Thread(target=_executor.spin, daemon=True).start()

tf_buffer = tf2_ros.Buffer()
tf_listener = tf2_ros.TransformListener(tf_buffer, node)

mask_pub = node.create_publisher(Image, '~/mask', 1)
point_pub = node.create_publisher(PointStamped, '~/red_circle', 1)

set_position_client = node.create_client(SetPosition, 'set_position')
get_telemetry_client = node.create_client(GetTelemetry, 'get_telemetry')


def _call(client, req, timeout=2.0):
    future = client.call_async(req)
    deadline = time.time() + timeout
    while not future.done() and time.time() < deadline:
        time.sleep(0.005)
    return future.result()


# read camera info once
camera_info_msg = [None]
_ci_event = threading.Event()
def _ci_cb(msg):
    camera_info_msg[0] = msg
    _ci_event.set()
_ci_sub = node.create_subscription(CameraInfo, 'main_camera/camera_info', _ci_cb, 1)
_ci_event.wait(timeout=5.0)
node.destroy_subscription(_ci_sub)

camera_model = image_geometry.PinholeCameraModel()
if camera_info_msg[0]:
    camera_model.fromCameraInfo(camera_info_msg[0])


def img_xy_to_point(xy, dist):
    xy_rect = camera_model.rectifyPoint(xy)
    ray = camera_model.projectPixelTo3dRay(xy_rect)
    return Point(x=ray[0] * dist, y=ray[1] * dist, z=dist)


def get_center_of_mass(mask):
    M = cv2.moments(mask)
    if M['m00'] == 0:
        return None
    return M['m10'] // M['m00'], M['m01'] // M['m00']


follow_red_circle = False


@long_callback
def image_callback(msg):
    img = bridge.imgmsg_to_cv2(msg, 'bgr8')
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    mask1 = cv2.inRange(img_hsv, (0, 150, 150), (15, 255, 255))
    mask2 = cv2.inRange(img_hsv, (160, 150, 150), (180, 255, 255))
    mask = cv2.bitwise_or(mask1, mask2)

    if mask_pub.get_subscription_count() > 0:
        mask_pub.publish(bridge.cv2_to_imgmsg(mask, 'mono8'))

    xy = get_center_of_mass(mask)
    if xy is None:
        return

    telem_req = GetTelemetry.Request()
    telem_req.frame_id = 'terrain'
    telem = _call(get_telemetry_client, telem_req)
    if telem is None:
        return
    altitude = telem.z
    xy3d = img_xy_to_point(xy, altitude)
    target = PointStamped()
    target.header = msg.header
    target.point = xy3d
    point_pub.publish(target)

    if follow_red_circle:
        try:
            setpoint = tf_buffer.transform(target, 'map', timeout=Duration(seconds=0.2))
            req = SetPosition.Request()
            req.x = setpoint.point.x
            req.y = setpoint.point.y
            req.z = nan
            req.yaw = nan
            req.frame_id = setpoint.header.frame_id
            _call(set_position_client, req)
        except Exception:
            pass


node.create_subscription(Image, 'main_camera/image_raw', image_callback, 1)

node.get_logger().info('Hit enter to follow the red circle')
input()
follow_red_circle = True

rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
