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
navigate_wait.py -- minimal example using navigate_wait directly.

Shows how to use the low-level navigate_wait function from drone.py
when you need full control over speed, tolerance, and frame_id.

Uses drone.py library. Run: python3 navigate_wait.py
"""

import sys
sys.path.insert(0, '/home/lb/catkin_ws/src/bumblebee/bumblebee/examples')
import drone

# Take off 1 meter above the ground using body frame (relative)
drone.navigate_wait(z=1, frame_id='body', auto_arm=True, phase='TAKEOFF')

# Fly 1 meter forward relative to the drone current heading
drone.navigate_wait(x=1, frame_id='body', phase='FORWARD')

# Land
drone.safe_land()
