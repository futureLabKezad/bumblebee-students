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

"""alarm — show: red strobe on the whole body + urgent chirps on the buzzer."""
import _show
from _show import drone

RED = (255, 0, 0)
OFF = (0, 0, 0)
STROBE_HZ = 4.0


def frame(t):
    _show.fill(RED if (t * STROBE_HZ * 2) % 2 < 1 else OFF)


_show.run(frame, drone.TUNE_WARN, fps=16, gap=0.5)
