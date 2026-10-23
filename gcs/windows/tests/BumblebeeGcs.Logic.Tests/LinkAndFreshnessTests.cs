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
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

public class LinkLogicTests
{
    [Fact]
    public void NoSocket_IsNoDrone_EvenWithAnOldState()
    {
        Assert.Equal(LinkState.NoDrone, LinkLogic.Compute(null, null, null, 100));
        Assert.Equal(LinkState.NoDrone, LinkLogic.Compute(null, 99.5, true, 100));
    }

    [Fact]
    public void FreshConnectedState_IsOk()
    {
        Assert.Equal(LinkState.Ok, LinkLogic.Compute(10, 99, true, 100));
    }

    [Fact]
    public void StateExactlyThreeSecondsOld_IsStillFresh()
    {
        Assert.Equal(LinkState.Ok, LinkLogic.Compute(10, 97.0, true, 100.0));
        Assert.Equal(LinkState.TelemetryFrozen, LinkLogic.Compute(10, 96.99, true, 100.0));
    }

    [Fact]
    public void FreshStateWithFcDisconnected_IsFcNotConnected()
    {
        Assert.Equal(LinkState.FcNotConnected, LinkLogic.Compute(10, 99, false, 100));
        Assert.Equal(LinkState.FcNotConnected, LinkLogic.Compute(10, 99, null, 100));
    }

    [Fact]
    public void StaleFcDisconnectedState_IsFrozen()
    {
        Assert.Equal(LinkState.TelemetryFrozen, LinkLogic.Compute(10, 90, false, 100));
    }

    [Fact]
    public void NoStateWithinThreeSecondsOfConnecting_IsFrozen()
    {
        // Socket opened at 100; nothing yet. During the first 3 s it is not frozen yet.
        Assert.Equal(LinkState.NoDrone, LinkLogic.Compute(100, null, null, 102.9));
        Assert.Equal(LinkState.TelemetryFrozen, LinkLogic.Compute(100, null, null, 103.1));
    }

    [Fact]
    public void StateFromAnEarlierSocket_DoesNotCount()
    {
        // Reconnect to the same drone: the last state (t=99) came over the old socket.
        Assert.Equal(LinkState.NoDrone, LinkLogic.Compute(99.5, 99, true, 100));
        Assert.Equal(LinkState.TelemetryFrozen, LinkLogic.Compute(99.5, 99, true, 102.6));
    }

    [Theory]
    [InlineData(LinkState.NoDrone, "No drone")]
    [InlineData(LinkState.FcNotConnected, "FC not connected")]
    [InlineData(LinkState.TelemetryFrozen, "Telemetry frozen")]
    [InlineData(LinkState.Ok, "OK")]
    public void Texts(LinkState s, string text) => Assert.Equal(text, LinkLogic.Text(s));

    [Fact]
    public void Colours_AsOnTheMac()
    {
        Assert.Equal(Tone.Ok, LinkLogic.ToneOf(LinkState.Ok));
        Assert.Equal(Tone.Warn, LinkLogic.ToneOf(LinkState.NoDrone));
        Assert.Equal(Tone.Danger, LinkLogic.ToneOf(LinkState.FcNotConnected));
        Assert.Equal(Tone.Danger, LinkLogic.ToneOf(LinkState.TelemetryFrozen));
    }

    [Fact]
    public void TileCaption()
    {
        var never = Freshness.Status(null, 100, 3);
        var stale = Freshness.Status(91.5, 100, 3);
        Assert.Equal("waiting for FC data", LinkLogic.Caption(LinkState.NoDrone, socketOpen: true, never));
        Assert.Equal("", LinkLogic.Caption(LinkState.NoDrone, socketOpen: false, stale));
        Assert.Equal("no data 8 s", LinkLogic.Caption(LinkState.TelemetryFrozen, socketOpen: true, stale));
        Assert.Equal("no data yet", LinkLogic.Caption(LinkState.TelemetryFrozen, socketOpen: true, never));
        Assert.Equal("", LinkLogic.Caption(LinkState.FcNotConnected, socketOpen: true, Freshness.Status(99, 100, 3)));
        Assert.Equal("", LinkLogic.Caption(LinkState.Ok, socketOpen: true, Freshness.Status(99, 100, 3)));
    }

    [Fact]
    public void SidebarLine()
    {
        Assert.Equal("linked", LinkLogic.SidebarText(LinkState.Ok, true));
        Assert.Equal("waiting for FC data", LinkLogic.SidebarText(LinkState.NoDrone, true));
        Assert.Equal("linking…", LinkLogic.SidebarText(LinkState.NoDrone, false));
        Assert.Equal("FC not connected", LinkLogic.SidebarText(LinkState.FcNotConnected, true));
        Assert.Equal("telemetry frozen", LinkLogic.SidebarText(LinkState.TelemetryFrozen, true));
    }
}

public class FreshnessTests
{
    [Fact]
    public void Limits_MatchTheSpec()
    {
        Assert.Equal(3.0, Freshness.Limit(TelemetrySource.State));
        Assert.Equal(2.0, Freshness.Limit(TelemetrySource.Pose));
        Assert.Equal(2.0, Freshness.Limit(TelemetrySource.Velocity));
        Assert.Equal(2.0, Freshness.Limit(TelemetrySource.Imu));
        Assert.Equal(2.0, Freshness.Limit(TelemetrySource.Attitude));
        Assert.Equal(5.0, Freshness.Limit(TelemetrySource.Battery));
        Assert.Equal(6.0, Freshness.Limit(TelemetrySource.Metrics));
        Assert.Equal(3.0, Freshness.VideoLimit);
    }

    [Fact]
    public void NothingArrived_IsNotStale_ButHasNoAge()
    {
        Assert.Null(Freshness.Age(null, 100));
        Assert.False(Freshness.IsStale(null, 100, 2));
    }

    [Fact]
    public void OlderThanLimit_IsStale_WithWholeSeconds()
    {
        Assert.False(Freshness.IsStale(98, 100, 2));
        Assert.True(Freshness.IsStale(97.9, 100, 2));
        Assert.Equal("no data 7 s", Freshness.NoDataText(7.9));
    }

    [Fact]
    public void Status_NeverFreshStale_AsOnTheMac()
    {
        var never = Freshness.Status(null, 100, 2);
        Assert.Equal(FreshKind.Never, never.Kind);
        Assert.False(never.IsFresh);                       // nothing came: greyed, value "—"
        Assert.Equal("no data yet", never.Note);

        var fresh = Freshness.Status(98, 100, 2);          // exactly at the limit is still fresh
        Assert.True(fresh.IsFresh);
        Assert.Null(fresh.Note);

        var stale = Freshness.Status(92.4, 100, 5);
        Assert.Equal(FreshKind.Stale, stale.Kind);
        Assert.False(stale.IsFresh);
        Assert.Equal("no data 7 s", stale.Note);
    }

    [Fact]
    public void ArrivalInTheFuture_CountsAsZeroAge()
    {
        Assert.Equal(0, Freshness.Age(101, 100));
    }
}

public class ConnectionGenerationTests
{
    [Fact]
    public void LateDataOfThePreviousConnection_IsRejected()
    {
        var g = new ConnectionGeneration();
        var first = g.Advance();
        Assert.True(g.IsCurrent(first));
        var second = g.Advance();
        Assert.False(g.IsCurrent(first));
        Assert.True(g.IsCurrent(second));
        g.Advance(); // disconnect
        Assert.False(g.IsCurrent(second));
    }
}

public class FormatTests
{
    [Fact]
    public void MissingValues_ShowADash_NeverZero()
    {
        Assert.Equal("—", Format.Signed(null, "m"));
        Assert.Equal("—", Format.Fixed(null, 2, "m"));
        Assert.Equal("—", Format.Degrees(null));
    }

    [Fact]
    public void Units()
    {
        Assert.Equal("+1.234 m", Format.Signed(1.2341, "m"));
        Assert.Equal("-0.500 m/s", Format.Signed(-0.5, "m/s"));
        Assert.Equal("+0.000 m", Format.Signed(0, "m"));
        Assert.Equal("1.52 m", Format.Fixed(1.524, 2, "m"));
        Assert.Equal("-3.5°", Format.Degrees(-3.46));
    }
}
