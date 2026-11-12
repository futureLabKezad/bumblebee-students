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
example_flight.py -- multi-waypoint example using drone.py library.

Sequence:
    1. Take off to 1m
    2. Fly forward 2m (body frame)
    3. Fly right 1m  (body frame)
    4. Hover 3s
    5. Return to map origin (marker 0)
    6. Land

Uses drone.py library. Run: python3 example_flight.py
"""

import sys
sys.path.insert(0, '/home/lb/catkin_ws/src/bumblebee/bumblebee/examples')
import drone

print('=== Example flight starting ===')

# Step 1: take off to 1m
drone.takeoff(1.0)

# Step 2: move 2m forward relative to current heading
drone.move(x=2.0)

# Step 3: move 1m to the right (negative y = right in body frame)
drone.move(y=-1.0)

# Step 4: hover in place for 3 seconds
drone.hover(3.0)

# Step 5: return to map origin (marker 0)
drone.fly_to(x=0, y=0, z=1.0)

# Step 6: land
drone.safe_land()

print('=== Flight complete ===')
