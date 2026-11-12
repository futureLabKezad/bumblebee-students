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

import rclpy
from threading import Thread, Event

def long_callback(fn):
    """
    Decorator fixing a rclpy issue for long-running topic callbacks, primarily
    for image processing.

    Usage example:

    @long_callback
    def image_callback(msg):
        # perform image processing
        # ...

    node.create_subscription(Image, 'main_camera/image_raw', image_callback, 1)
    """
    e = Event()

    def thread():
        while rclpy.ok():
            e.wait()
            e.clear()
            fn(thread.current_msg)

    thread.current_msg = None
    Thread(target=thread, daemon=True).start()

    def wrapper(msg):
        thread.current_msg = msg
        e.set()

    return wrapper
