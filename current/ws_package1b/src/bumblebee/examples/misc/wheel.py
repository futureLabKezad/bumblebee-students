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

import sys
import time
sys.path.insert(0, '/home/lb/ros2_ws/src/bumblebee/examples')
import drone

# Speed presets (match Arduino demo values)
STOP     = 128  # Neutral (~1500 us)
FWD_SLOW = 160  # Slow forward
BWD_SLOW = 20   # Slow reverse

# Cycle Stop -> Forward -> Backward every 3s (mirrors Arduino demo)
if __name__ == '__main__':
    states = [
        ('STOP',     STOP),
        ('FORWARD',  FWD_SLOW),
        ('BACKWARD', BWD_SLOW),
    ]

    try:
        print('Wheel: Stop -> Forward -> Backward (cycle every 3s)')
        i = 0
        while True:
            name, speed = states[i % len(states)]
            print(f'Wheel: {name} ({speed})')
            drone.set_servo_speed(speed)
            time.sleep(3)
            i += 1
    except KeyboardInterrupt:
        print('Interrupted')
    finally:
        drone.set_servo_speed(STOP)
