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

namespace BumblebeeGcs.Logic;

/// <summary>Armed is tri-state: true, false or null (unknown).</summary>
public static class ArmedLogic
{
    /// <summary>
    /// The armed value the screen may trust: only from a fresh state of a connected FC.
    /// After a reset, reconnect, drop, a stale state or connected == false it is unknown.
    /// </summary>
    public static bool? Effective(LinkState link, bool? stateArmed) =>
        link == LinkState.Ok ? stateArmed : null;

    /// <param name="armed">The effective value (see <see cref="Effective"/>).</param>
    /// <param name="lastKnownArmed">The last value a connected FC reported; null after a drone switch.</param>
    public static TileText Display(bool? armed, bool? lastKnownArmed) => armed switch
    {
        true => new TileText("ARMED", "", Tone.Danger),
        false => new TileText("DISARMED", "", Tone.Neutral),
        null when lastKnownArmed == true => new TileText("ARMED?", "link lost", Tone.Danger),
        _ => new TileText("UNKNOWN", "waiting for FC data", Tone.Caution),
    };
}

/// <summary>Who flies the drone right now (display only, from armed and the PX4 mode).</summary>
public enum Controller { Unknown, Disarmed, Program, Pilot, Px4 }

/// <summary>PX4 mode names with a short explanation, and "who is in control".</summary>
public static class ModeLogic
{
    static string Norm(string? mode) => (mode ?? "").Trim().ToUpperInvariant();

    static bool IsPilotMode(string m) => m is "POSCTL" or "ALTCTL" or "STABILIZED" or "ACRO" or "MANUAL";

    /// <summary>Short explanation under the mode; "" for a mode without one.</summary>
    public static string Explain(string? mode) => Norm(mode) switch
    {
        "" => "unknown",
        "OFFBOARD" => "program in control",
        "POSCTL" => "pilot, position hold",
        "ALTCTL" => "pilot, altitude hold",
        "STABILIZED" or "ACRO" or "MANUAL" => "pilot, manual",
        "AUTO.LAND" => "PX4 landing",
        "AUTO.LOITER" => "PX4 holding",
        "AUTO.RTL" => "PX4 returning",
        "AUTO.TAKEOFF" => "PX4 taking off",
        var m when m.StartsWith("AUTO.", StringComparison.Ordinal) => "PX4 automatic",
        _ => "",
    };

    /// <summary>The mode as shown on the tile: "—" until a state with a mode arrives.</summary>
    public static string DisplayMode(string? mode) => Norm(mode) is { Length: > 0 } m ? m : Format.Dash;

    public static Controller WhoIsInControl(bool? armed, string? mode)
    {
        if (armed is null) return Controller.Unknown;
        if (armed == false) return Controller.Disarmed;
        var m = Norm(mode);
        if (m == "OFFBOARD") return Controller.Program;
        if (IsPilotMode(m)) return Controller.Pilot;
        if (m.StartsWith("AUTO.", StringComparison.Ordinal)) return Controller.Px4;
        return Controller.Unknown;
    }

    public static string ControllerText(Controller c) => c switch
    {
        Controller.Program => "Program",
        Controller.Pilot => "Pilot",
        Controller.Px4 => "PX4",
        Controller.Disarmed => "Disarmed",
        _ => "Unknown",
    };

    public static Tone ControllerTone(Controller c) => c switch
    {
        Controller.Program => Tone.Primary,
        Controller.Pilot => Tone.Ok,
        Controller.Px4 => Tone.Warn,
        Controller.Disarmed => Tone.Neutral,
        _ => Tone.Caution,
    };

    /// <summary>Caption under the controller plate.</summary>
    public static string ControllerCaption(Controller c, string? mode) => c switch
    {
        Controller.Unknown => "waiting for FC data",
        Controller.Disarmed => "on the ground, motors off",
        _ => $"{DisplayMode(mode)} · {Explain(mode)}",
    };

    /// <summary>
    /// The visible event line for a change of who is in control or of the mode, or null.
    /// No event for the first known value (prev == Unknown) or when control becomes unknown:
    /// link problems have their own banner.
    /// </summary>
    public static string? EventText(Controller prev, string? prevMode, Controller now, string? mode)
    {
        if (prev == Controller.Unknown || now == Controller.Unknown) return null;
        var m = Norm(mode);
        if (now == prev && m == Norm(prevMode)) return null;
        switch (now)
        {
            case Controller.Disarmed:
                return prev != Controller.Disarmed ? "Disarmed" : $"Mode → {DisplayMode(m)} ({Explain(m)})".Replace(" ()", "");
            case Controller.Program:
                if (prev == Controller.Disarmed) return "Armed: program in control";
                return prev != Controller.Program ? "Program took control" : null;
            case Controller.Pilot:
                if (prev == Controller.Disarmed) return "Armed: pilot in control";
                if (prev != Controller.Pilot) return "Pilot took control";
                var what = Explain(m);
                return "Pilot: " + (what.StartsWith("pilot, ", StringComparison.Ordinal) ? what["pilot, ".Length..] : DisplayMode(m));
            case Controller.Px4:
                return m switch
                {
                    "AUTO.LAND" => "PX4 is landing",
                    "AUTO.RTL" => "PX4 is returning",
                    "AUTO.LOITER" => "PX4 is holding",
                    "AUTO.TAKEOFF" => "PX4 is taking off",
                    _ => "PX4 took control",
                };
            default:
                return null;
        }
    }

    public static Tone EventTone(Controller now) => now switch
    {
        Controller.Disarmed => Tone.Neutral,
        _ => ControllerTone(now),
    };
}

/// <summary>One visible control event: "12:03:11 Pilot took control".</summary>
public sealed record ControlEvent(string Time, string Text, Tone Tone);

/// <summary>The last few control events, newest first; survives link gaps, cleared on a drone switch.</summary>
public sealed class ControlEvents
{
    public const int Max = 3;

    private readonly List<ControlEvent> _items = new();
    private Controller _lastKnown = Controller.Unknown;
    private string _lastMode = "";

    public IReadOnlyList<ControlEvent> Items => _items;
    public int Version { get; private set; }

    /// <summary>Feed the current controller and mode; returns the new event text, if any.</summary>
    public string? Update(Controller now, string? mode, string time)
    {
        if (now == Controller.Unknown) return null;
        var text = ModeLogic.EventText(_lastKnown, _lastMode, now, mode);
        _lastKnown = now;
        _lastMode = mode ?? "";
        if (text is null) return null;
        _items.Insert(0, new ControlEvent(time, text, ModeLogic.EventTone(now)));
        if (_items.Count > Max) _items.RemoveRange(Max, _items.Count - Max);
        Version++;
        return text;
    }

    public void Reset()
    {
        _items.Clear();
        _lastKnown = Controller.Unknown;
        _lastMode = "";
        Version++;
    }
}
