// Copyright 2026 FutureLab
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

using System.Runtime.InteropServices;

namespace BumblebeeGcs.Services;

/// <summary>
/// The Windows system alert sound ("Critical Stop" in the sound scheme) for the
/// FC-lost alarm. The drone itself cannot beep when its FC is gone (the buzzer is on
/// the FC), so the laptop does. Plays asynchronously; silent if sounds are off.
/// </summary>
public static class AlertSound
{
    private const uint MB_ICONHAND = 0x00000010;

    [DllImport("user32.dll")]
    private static extern bool MessageBeep(uint uType);

    public static void Play()
    {
        try { MessageBeep(MB_ICONHAND); } catch { }
    }
}
