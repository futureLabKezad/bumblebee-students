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

using System.Globalization;

namespace BumblebeeGcs.Logic;

// The Entertainment screen's decisions, without WinUI so the tests can check them.
// Same rules as the Mac app (EntertainmentLogic.swift).

public static class LedCatalog
{
    /// <summary>Animations the drone knows (wifi_manager.py ANIMATIONS), LEDs only.</summary>
    public static readonly string[] Animations =
        { "breathing", "rainbow", "police", "strobe", "fire", "theater", "rainbow_theater" };

    /// <summary>Shows: LEDs plus a buzzer melody the drone repeats while disarmed.</summary>
    public static readonly string[] Shows = { "party", "siren", "alarm", "victory" };

    /// <summary>"rainbow_theater" -> "Rainbow Theater".</summary>
    public static string Label(string name) =>
        CultureInfo.InvariantCulture.TextInfo.ToTitleCase(name.Replace('_', ' '));
}

/// <summary>
/// The buzzer sits on the flight controller: the drone (1.0.2+) refuses tunes and speech unless
/// a fresh, linked state says disarmed, so PX4's own warning tones are never covered. The
/// buttons follow the same rule.
/// </summary>
public static class SoundGate
{
    /// <summary>null: sounds may be sent. armed as the dashboard trusts it (null = unknown).</summary>
    public static string? BlockedReason(bool? armed) => armed switch
    {
        false => null,
        true => "Sounds are off while the drone is ARMED, so PX4's own warning tones can be heard.",
        null => "Sounds are off: the drone's state is unknown (no live flight-controller data).",
    };
}

public static class LedText
{
    /// <summary>"stops by itself in 1:45" for the seconds the drone reports; null without.</summary>
    public static string? Remaining(int? seconds) =>
        seconds is int s && s > 0 ? $"stops by itself in {s / 60}:{s % 60:00}" : null;

    /// <summary>The drone accepted the tune; whether the buzzer plays is up to PX4.</summary>
    public static string Sent(string what) => $"Sent to the drone: {what}";
}
