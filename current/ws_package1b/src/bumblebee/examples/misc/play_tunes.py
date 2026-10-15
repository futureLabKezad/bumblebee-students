#!/usr/bin/env python3
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

"""Demo: play all preset tunes through PX4 buzzer via MAVROS."""

import time
import drone

PRESETS = [
    ('BEEP',     drone.TUNE_BEEP,           'QBASIC'),
    ('OK',       drone.TUNE_OK,             'QBASIC'),
    ('ERROR',    drone.TUNE_ERROR,          'QBASIC'),
    ('NOTIFY',   drone.TUNE_NOTIFY,         'QBASIC'),
    ('ARMING',   drone.TUNE_ARMING,         'QBASIC'),
    ('IMPERIAL', drone.TUNE_IMPERIAL_MARCH, 'QBASIC'),
    ('MARIO',    drone.TUNE_MARIO,          'QBASIC'),
    ('TETRIS',   drone.TUNE_TETRIS,         'QBASIC'),
]

for name, tune, fmt in PRESETS:
    print('Playing:', name)
    drone.play_tune(tune, fmt)
    time.sleep(4.0)
