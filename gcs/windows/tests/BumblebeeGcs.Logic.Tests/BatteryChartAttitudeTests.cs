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

using BumblebeeGcs.Logic;
using BumblebeeGcs.Models;
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

public class BatteryTests
{
    [Theory]
    [InlineData(65.535, -0.01)]      // PX4 BAT1_SOURCE=-1 through MAVROS
    [InlineData(65.53500366, 0.5)]   // the same sentinel as float32
    [InlineData(null, 0.5)]          // rosbridge sends NaN as null
    [InlineData(double.NaN, 0.5)]
    [InlineData(0.0, 0.5)]
    [InlineData(-1.0, 0.5)]
    [InlineData(24.1, -0.01)]        // percentage < 0
    public void Sentinels_AreNotMeasured(double? v, double? p)
    {
        var r = BatteryReading.Classify(v, p);
        Assert.Equal(BatteryKind.NotMeasured, r.Kind);
        Assert.Equal("Not measured — check with a tester", r.Text);
        Assert.Equal("Not measured", r.Short);
        Assert.Equal("check with a tester", r.Caption);
        Assert.Null(r.Pct);
        Assert.Equal(Tone.Neutral, r.Tone);
    }

    [Fact]
    public void NormalReading()
    {
        var r = BatteryReading.Classify(24.1, 0.83);
        Assert.Equal(BatteryKind.Measured, r.Kind);
        Assert.Equal("24.10 V · 83%", r.Text);
        Assert.Equal("83%", r.Short);
        Assert.Equal("24.10 V", r.Caption);
        Assert.Equal(83, r.Pct!.Value, 6);
        Assert.Equal(Tone.Ok, r.Tone);
    }

    [Fact]
    public void VoltageWithoutPercentage_HasNoGuessedPercentage()
    {
        var r = BatteryReading.Classify(16.2, null);
        Assert.Equal(BatteryKind.Measured, r.Kind);
        Assert.Null(r.Pct);
        Assert.Equal("16.20 V · —", r.Text);
        Assert.Equal("16.2 V", r.Short);
        Assert.Equal(Tone.Neutral, r.Tone);
    }

    [Fact]
    public void NoData_BeforeTheFirstMessage()
    {
        var r = BatteryReading.NoData;
        Assert.Equal(BatteryKind.NoData, r.Kind);
        Assert.Equal("—", r.Text);
        Assert.Equal("—", r.Short);
    }

    [Theory]
    [InlineData(0.80, Tone.Ok)]
    [InlineData(0.40, Tone.Warn)]
    [InlineData(0.10, Tone.Danger)]
    public void Tones(double p, Tone tone) => Assert.Equal(tone, BatteryReading.Classify(22, p).Tone);

    [Fact]
    public void LowBattery_LoggedOnceBelow15_RearmedOnlyAbove20()
    {
        var latch = new LowBatteryLatch();
        Assert.False(latch.Update(30));
        Assert.False(latch.IsLow);
        Assert.True(latch.Update(14.9));    // first drop below 15 %: log
        Assert.True(latch.IsLow);
        Assert.False(latch.Update(14));     // still low: no repeat
        Assert.False(latch.Update(16));     // above 15 but not above 20: still low
        Assert.False(latch.Update(14.5));
        Assert.False(latch.Update(20));     // exactly 20 does not re-arm
        Assert.True(latch.IsLow);
        Assert.False(latch.Update(20.1));   // re-armed
        Assert.False(latch.IsLow);
        Assert.True(latch.Update(12));      // second drop: log again
        Assert.False(latch.Update(null));   // not measured: keeps the state
        Assert.True(latch.IsLow);
        latch.Reset();
        Assert.False(latch.IsLow);
    }
}

public class ChartScaleTests
{
    [Fact]
    public void AltitudeNoise_IsDrawnOnAOneMetreSpan()
    {
        var data = Enumerable.Range(0, 120).Select(i => 1.0 + 0.01 * Math.Sin(i * 0.3)).ToList();
        var (lo, hi) = ChartScale.Range(data, null, null, ChartScale.AltitudeMinSpan);
        Assert.Equal(1.0, hi - lo, 9);
        Assert.Equal(1.0, (lo + hi) / 2, 2);
        Assert.Equal("0.5", ChartScale.Label(lo, hi - lo));
        Assert.Equal("1.5", ChartScale.Label(hi, hi - lo));
    }

    [Fact]
    public void RealClimb_KeepsItsOwnSpan()
    {
        var data = new List<double> { 0.2, 0.8, 1.6, 2.4 };
        var (lo, hi) = ChartScale.Range(data, null, null, ChartScale.AltitudeMinSpan);
        Assert.Equal(0.2, lo, 9);
        Assert.Equal(2.4, hi, 9);
    }

    [Fact]
    public void SkewedNarrowData_StaysInsideTheRange()
    {
        var data = new List<double> { 0.0, 0.01, 0.95 };
        var (lo, hi) = ChartScale.Range(data, null, null, 1.0);
        Assert.True(lo <= 0.0 && hi >= 0.95);
        Assert.Equal(1.0, hi - lo, 9);
    }

    [Fact]
    public void FixedScales_AreKept()
    {
        var data = new List<double> { 1, 2, 3 };
        Assert.Equal((0.0, 5.0), ChartScale.Range(data, 0, 5, 1.0));
        Assert.Equal((0.0, 100.0), ChartScale.Range(data, 0, 100, 1.0));
    }

    [Fact]
    public void OneFixedBound_GrowsTheOther()
    {
        var data = new List<double> { 0.1, 0.2 };
        Assert.Equal((0.0, 1.0), ChartScale.Range(data, 0, null, 1.0));
    }

    [Fact]
    public void Labels_FollowTheSpan()
    {
        Assert.Equal("100", ChartScale.Label(100, 100));
        Assert.Equal("2.5", ChartScale.Label(2.5, 5));
        Assert.Equal("0.25", ChartScale.Label(0.25, 0.5));
    }
}

public class AttitudeTests
{
    // +10 degrees about the body Y axis (ROS FLU: Y points left): the nose goes DOWN.
    static readonly double S5 = Math.Sin(5 * Math.PI / 180), C5 = Math.Cos(5 * Math.PI / 180);

    [Fact]
    public void NoseDownQuaternion_GivesPositivePitch()
    {
        var e = MathUtil.QuatToEuler(0, S5, 0, C5);
        Assert.Equal(10, e.Pitch, 6);
        Assert.Equal(0, e.Roll, 6);
        Assert.Equal(0, e.Yaw, 6);
    }

    [Fact]
    public void NoseDown_MovesTheHorizonUp_SoMoreGroundShows()
    {
        // Screen Y grows downwards: a negative shift moves the horizon line up.
        Assert.True(AttitudeMath.HorizonShiftPx(10, 2.0) < 0);
        Assert.Equal(-20, AttitudeMath.HorizonShiftPx(10, 2.0), 9);
        Assert.True(AttitudeMath.HorizonShiftPx(-10, 2.0) > 0);
    }

    [Fact]
    public void ImuOrientation_ValidOnlyWithCovarianceAndUnitQuaternion()
    {
        Assert.True(AttitudeMath.IsValidImuOrientation(0.0, 0, S5, 0, C5));
        Assert.False(AttitudeMath.IsValidImuOrientation(-1.0, 0, S5, 0, C5));   // "no orientation" per sensor_msgs/Imu
        Assert.False(AttitudeMath.IsValidImuOrientation(null, 0, S5, 0, C5));
        Assert.False(AttitudeMath.IsValidImuOrientation(0.0, 0, 0, 0, 0));       // empty quaternion
        Assert.False(AttitudeMath.IsValidImuOrientation(0.0, 0, 0, 0, 0.5));
        Assert.False(AttitudeMath.IsValidImuOrientation(0.0, double.NaN, 0, 0, 1));
        Assert.True(AttitudeMath.IsValidImuOrientation(0.0, 0, 0, 0, 1.02));
    }
}
