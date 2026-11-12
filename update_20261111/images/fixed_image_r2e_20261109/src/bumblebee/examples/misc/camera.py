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

# Example on basic working with the camera and image processing:
# - cuts out a central square from the camera image
# - publishes this cropped image to the topic ~/center
# - computes the average color and prints its name

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
from bumblebee import long_callback


def get_color_name(h):
    if h < 15:   return 'red'
    elif h < 30: return 'orange'
    elif h < 60: return 'yellow'
    elif h < 90: return 'green'
    elif h < 120: return 'cyan'
    elif h < 150: return 'blue'
    elif h < 170: return 'magenta'
    else:         return 'red'


rclpy.init()
node = Node('cv')
bridge = CvBridge()
center_pub = node.create_publisher(Image, '~/center', 1)
printed_color = None


@long_callback
def image_callback(msg):
    img = bridge.imgmsg_to_cv2(msg, 'bgr8')
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    w = img.shape[1]
    h = img.shape[0]
    r = 20
    center = img_hsv[h // 2 - r:h // 2 + r, w // 2 - r:w // 2 + r]

    mean_hue = center[:, :, 0].mean()
    color = get_color_name(mean_hue)
    global printed_color
    if color != printed_color:
        print(color)
        printed_color = color

    center = cv2.cvtColor(center, cv2.COLOR_HSV2BGR)
    center_pub.publish(bridge.cv2_to_imgmsg(center, 'bgr8'))


# process every frame:
node.create_subscription(Image, 'main_camera/image_raw', image_callback, 1)

# process 5 frames per second:
# node.create_subscription(Image, 'main_camera/image_raw_throttled', image_callback, 1)

rclpy.spin(node)
node.destroy_node()
rclpy.shutdown()
