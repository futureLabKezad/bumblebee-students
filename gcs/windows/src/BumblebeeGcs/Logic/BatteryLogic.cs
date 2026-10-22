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

public enum BatteryKind
{
    /// <summary>No /mavros/battery message yet.</summary>
    NoData,
    /// <summary>Messages come, but the FC does not measure the battery (PX4 BAT1_SOURCE=-1).</summary>
    NotMeasured,
    /// <summary>A real voltage; the percentage may still be missing.</summary>
    Measured,
}

/// <summary>
/// One /mavros/battery reading, classified by its data (not by a flag in the app),
/// so the text changes by itself once the drone starts measuring the battery.
/// </summary>
public readonly record struct BatteryReading(BatteryKind Kind, double? Voltage, double? Pct)
{
    /// <summary>MAVROS turns SYS_STATUS voltage_battery = UINT16_MAX into 65.535 V.</summary>
    public const double SentinelVolts = 65.535;

    public static readonly BatteryReading NoData = new(BatteryKind.NoData, null, null);

    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    /// <param name="voltage">BatteryState.voltage; rosbridge sends NaN as null.</param>
    /// <param name="percentage">BatteryState.percentage, 0..1; MAVROS sends -0.01 when unknown.</param>
    public static BatteryReading Classify(double? voltage, double? percentage)
    {
        var v = voltage ?? double.NaN;
        var p = percentage ?? double.NaN;
        var noVoltage = !double.IsFinite(v) || v <= 0 || Math.Abs(v - SentinelVolts) < 0.01;
        if (noVoltage || (double.IsFinite(p) && p < 0))
            return new BatteryReading(BatteryKind.NotMeasured, null, null);
        // No guessed percentage from the voltage: the pack's cell count is unknown here.
        double? pct = double.IsFinite(p) && p <= 1 ? p * 100 : null;
        return new BatteryReading(BatteryKind.Measured, v, pct);
    }

    /// <summary>The full line in the Telemetry panel.</summary>
    public string Text => Kind switch
    {
        BatteryKind.NotMeasured => "Not measured — check with a tester",
        BatteryKind.Measured => $"{Volts(2)} · {(Pct is double p ? PctText(p) : Format.Dash)}",
        _ => Format.Dash,
    };

    /// <summary>The value on the hero tile.</summary>
    public string Short => Kind switch
    {
        BatteryKind.NotMeasured => "Not measured",
        BatteryKind.Measured => Pct is double p ? PctText(p) : Volts(1),
        _ => Format.Dash,
    };

    /// <summary>The small line under the hero tile.</summary>
    public string Caption => Kind switch
    {
        BatteryKind.NotMeasured => "check with a tester",
        BatteryKind.Measured when Pct is not null => Volts(2),
        _ => "",
    };

    public Tone Tone => Pct is double p
        ? (p > 55 ? Tone.Ok : p > 25 ? Tone.Warn : Tone.Danger)
        : Tone.Neutral;

    /// <summary>True when the battery icon may show a charge level (otherwise a neutral icon).</summary>
    public bool HasLevel => Kind == BatteryKind.Measured && Pct is not null;

    string Volts(int decimals) => Voltage is double v ? v.ToString("F" + decimals, Inv) + " V" : Format.Dash;

    static string PctText(double p) => p.ToString("F0", Inv) + "%";
}

/// <summary>
/// LOW BATTERY with hysteresis: logged once when the charge drops below 15 %,
/// re-armed only above 20 %. While low, the app shows a persistent red banner.
/// </summary>
public sealed class LowBatteryLatch
{
    public const double LowBelowPct = 15, RearmAbovePct = 20;

    public bool IsLow { get; private set; }

    /// <summary>Feed the percentage (null = not measured / no data: state kept); true = log the line now.</summary>
    public bool Update(double? pct)
    {
        if (pct is not double p) return false;
        if (!IsLow && p < LowBelowPct)
        {
            IsLow = true;
            return true;
        }
        if (IsLow && p > RearmAbovePct) IsLow = false;
        return false;
    }

    public void Reset() => IsLow = false;
}
