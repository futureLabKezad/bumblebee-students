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

// Everything in BumblebeeGcs.Logic is plain C# without WinUI, so the decisions
// the screen makes (link state, armed, battery text, ...) are unit-tested in
// gcs/windows/tests/BumblebeeGcs.Logic.Tests. The views only map Tone to a colour.

using System.Diagnostics;
using System.Globalization;

namespace BumblebeeGcs.Logic;

/// <summary>Colour role of a value; the UI maps it to the palette.</summary>
public enum Tone { Neutral, Primary, Ok, Caution, Warn, Danger }

/// <summary>What a hero tile shows: the value, a small line under it and its colour.</summary>
public readonly record struct TileText(string Value, string Caption, Tone Tone);

/// <summary>Monotonic seconds for arrival times (wall-clock jumps must not make data look fresh or stale).</summary>
public static class MonoClock
{
    public static double Now => Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency;
}

/// <summary>
/// Connection generation: every connect/disconnect advances it, and data captured
/// under an older number is dropped on the UI thread (late answers of the previous drone).
/// </summary>
public sealed class ConnectionGeneration
{
    private int _current;

    public int Current => Volatile.Read(ref _current);

    /// <summary>Start a new generation; returns its number. Call on the UI thread.</summary>
    public int Advance() => Interlocked.Increment(ref _current);

    public bool IsCurrent(int generation) => generation == Current;
}

/// <summary>Number formatting for the dashboard: "—" until a value exists, units always shown.</summary>
public static class Format
{
    public const string Dash = "—";
    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    /// <summary>"+1.234 m" / "-0.500 m/s".</summary>
    public static string Signed(double? v, string unit) =>
        v is double x ? x.ToString("+0.000;-0.000;+0.000", Inv) + " " + unit : Dash;

    /// <summary>"1.52 m" with the given decimals; unit may be empty.</summary>
    public static string Fixed(double? v, int decimals, string unit = "") =>
        v is double x ? x.ToString("F" + decimals, Inv) + (unit.Length > 0 ? " " + unit : "") : Dash;

    /// <summary>"-3.5°".</summary>
    public static string Degrees(double? v) => v is double x ? x.ToString("F1", Inv) + "°" : Dash;
}
