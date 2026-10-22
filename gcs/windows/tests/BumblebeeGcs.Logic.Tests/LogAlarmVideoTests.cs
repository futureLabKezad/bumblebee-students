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

public class MessageLogTests
{
    [Fact]
    public void FcuLines_AreNeverPushedOutByAppLines()
    {
        var log = new MessageLog();
        log.AddFcu("Preflight Fail: ekf2 missing data", "12:00:00");
        log.AddFcu("Baro #0 failed", "12:00:01");
        for (var i = 0; i < 200; i++) log.AddApp($"app line {i}", "12:00:02");
        var fcu = log.Entries.Where(e => e.Kind == LogKind.Fcu).ToList();
        Assert.Equal(2, fcu.Count);
        Assert.Equal(MessageLog.AppMax, log.Entries.Count(e => e.Kind == LogKind.App));
    }

    [Fact]
    public void FcuRing_HasItsOwnCap()
    {
        var log = new MessageLog();
        for (var i = 0; i < 80; i++) log.AddFcu($"fcu {i}", "t");
        Assert.Equal(MessageLog.FcuMax, log.Entries.Count);
        Assert.Equal("[FCU] fcu 79", log.Entries[0].Text);
    }

    [Fact]
    public void Entries_AreNewestFirst_AcrossBothRings()
    {
        var log = new MessageLog();
        log.AddApp("a1", "t");
        log.AddFcu("f1", "t");
        log.AddApp("a2", "t");
        Assert.Equal(new[] { "a2", "[FCU] f1", "a1" }, log.Entries.Select(e => e.Text));
    }

    [Fact]
    public void SameKey_ReplacesTheNewestAppLine_AndMovesItUp()
    {
        var log = new MessageLog();
        log.AddApp("rosbridge lost", "12:00:00", "link");
        log.AddFcu("statustext", "12:00:01");
        var v = log.Version;
        log.AddApp("rosbridge lost · attempt 2", "12:00:03", "link");
        Assert.True(log.Version > v);
        Assert.Equal(2, log.Entries.Count);
        Assert.Equal("rosbridge lost · attempt 2", log.Entries[0].Text);
        Assert.Equal("12:00:03", log.Entries[0].Time);
        log.AddApp("mode → POSCTL", "12:00:04");
        log.AddApp("rosbridge lost", "12:00:05", "link");   // another app line came between: new line
        Assert.Equal(4, log.Entries.Count);
    }

    [Fact]
    public void ReconnectStorm_IsOneLineWithCounters()
    {
        var log = new MessageLog();
        var link = new LinkLog();
        void Add((string Text, string? Key) l) => log.AddApp(l.Text, "t", l.Key);

        Add(link.Connected("10.0.0.7"));
        Assert.Equal("rosbridge connected (10.0.0.7)", log.Entries[0].Text);
        Add(link.Failed());
        Assert.Equal("rosbridge lost — reconnecting…", log.Entries[0].Text);
        for (var i = 0; i < 20; i++) Add(link.Failed());
        Assert.Equal("rosbridge lost — reconnecting… · attempt 21", log.Entries[0].Text);
        Add(link.Connected("10.0.0.7"));
        Assert.Equal("rosbridge back (10.0.0.7) · lost 1×", log.Entries[0].Text);
        Add(link.Failed());
        Add(link.Connected("10.0.0.7"));
        Add(link.Failed());
        Assert.Equal("rosbridge lost — reconnecting… · lost 3×", log.Entries[0].Text);
        Assert.Equal(2, log.Entries.Count);   // "connected" + one collapsed line
    }

    [Fact]
    public void NeverConnected_SaysNotReachable()
    {
        var link = new LinkLog();
        Assert.Equal("rosbridge not reachable — retrying…", link.Failed().Text);
        Assert.Equal("rosbridge not reachable — retrying… · attempt 2", link.Failed().Text);
        Assert.Equal("rosbridge connected (h)", link.Connected("h").Text);
    }

    [Fact]
    public void Clear_EmptiesBothRings()
    {
        var log = new MessageLog();
        log.AddApp("a", "t");
        log.AddFcu("f", "t");
        log.Clear();
        Assert.Empty(log.Entries);
    }
}

public class FcLostAlarmTests
{
    [Theory]
    [InlineData(LinkState.FcNotConnected)]
    [InlineData(LinkState.TelemetryFrozen)]
    public void OkToLost_WhileArmed_SoundsOnce_BannerUntilOk(LinkState lost)
    {
        var a = new FcLostAlarm();
        Assert.False(a.Update(LinkState.Ok, true));
        Assert.True(a.Update(lost, true));
        Assert.True(a.BannerVisible);
        Assert.False(a.Update(lost, true));                 // once
        Assert.False(a.Update(LinkState.NoDrone, true));    // socket dropped later: banner stays
        Assert.True(a.BannerVisible);
        Assert.False(a.Update(LinkState.Ok, true));
        Assert.False(a.BannerVisible);
    }

    [Fact]
    public void Disarmed_OrUnknown_NoAlarm()
    {
        var a = new FcLostAlarm();
        a.Update(LinkState.Ok, false);
        Assert.False(a.Update(LinkState.FcNotConnected, false));
        Assert.False(a.BannerVisible);
        a.Update(LinkState.Ok, null);
        Assert.False(a.Update(LinkState.TelemetryFrozen, null));
        Assert.False(a.BannerVisible);
    }

    [Fact]
    public void SocketClosedFromOk_IsNotAnFcAlarm()
    {
        var a = new FcLostAlarm();
        a.Update(LinkState.Ok, true);
        Assert.False(a.Update(LinkState.NoDrone, true));
        Assert.False(a.BannerVisible);
    }

    [Fact]
    public void Reset_ClearsTheBanner()
    {
        var a = new FcLostAlarm();
        a.Update(LinkState.Ok, true);
        a.Update(LinkState.TelemetryFrozen, true);
        a.Reset();
        Assert.False(a.BannerVisible);
        Assert.False(a.Update(LinkState.TelemetryFrozen, true));   // no OK before it
    }
}

public class VideoLogicTests
{
    [Fact]
    public void WaitingThenLiveThenLost()
    {
        Assert.Equal(VideoState.Waiting, VideoLogic.Compute(null, 100, 101, isAruco: false));
        Assert.Equal(VideoState.Waiting, VideoLogic.Compute(null, 100, 130, isAruco: false));
        Assert.Equal(VideoState.Live, VideoLogic.Compute(104, 100, 106.9, isAruco: false));
        Assert.Equal(VideoState.Lost, VideoLogic.Compute(104, 100, 107.1, isAruco: false));
    }

    [Fact]
    public void Aruco_WithoutFrames_ShowsTheHintAfter3s()
    {
        Assert.Equal(VideoState.Waiting, VideoLogic.Compute(null, 100, 102.9, isAruco: true));
        Assert.Equal(VideoState.NoArucoFrames, VideoLogic.Compute(null, 100, 103.1, isAruco: true));
        Assert.Equal("ArUco image appears only when the drone is armed or in OFFBOARD", VideoLogic.ArucoHint);
    }

    [Fact]
    public void ArucoTopics()
    {
        Assert.True(VideoLogic.IsArucoTopic("/aruco_detect/debug"));
        Assert.True(VideoLogic.IsArucoTopic("/aruco_map/image"));
        Assert.False(VideoLogic.IsArucoTopic("/main_camera/image_raw"));
    }

    [Fact]
    public void LostText() => Assert.Equal("12 s", VideoLogic.LostCaption(12.7));

    [Fact]
    public void PictureInPictureHint() =>
        Assert.Equal("ArUco map: armed or OFFBOARD only", VideoLogic.ArucoHintShort);
}
