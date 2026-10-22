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

using System.Text.Json;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Models;
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

/// <summary>The store with rosbridge messages fed in, as the client does on the UI thread.</summary>
public class TelemetryStoreTests
{
    static JsonElement J(string json) => JsonDocument.Parse(json).RootElement.Clone();

    static void State(TelemetryStore s, bool connected, bool armed, string mode, double now) =>
        RosMessages.Apply(s, "/mavros/state",
            J($"{{\"connected\":{(connected ? "true" : "false")},\"armed\":{(armed ? "true" : "false")},\"mode\":\"{mode}\"}}"), now);

    static TelemetryStore Linked(double now = 100)
    {
        var s = new TelemetryStore();
        s.SocketOpened("10.0.0.7", now);
        return s;
    }

    [Fact]
    public void NewStore_ShowsNothingAsReal()
    {
        var s = new TelemetryStore();
        s.Evaluate(0);
        Assert.Equal(LinkState.NoDrone, s.Link);
        Assert.Null(s.Armed);
        Assert.Null(s.PosZ);
        Assert.Null(s.Roll);
        Assert.Null(s.SpeedH);
        Assert.Null(s.GyroMag);
        Assert.Equal(BatteryKind.NoData, s.Battery.Kind);
        Assert.Equal(Controller.Unknown, s.InControl);
    }

    [Fact]
    public void StateDrivesLinkArmedAndController()
    {
        var s = Linked();
        Assert.Equal(LinkState.NoDrone, s.Link);           // connecting
        State(s, true, true, "OFFBOARD", 100.5);
        Assert.Equal(LinkState.Ok, s.Link);
        Assert.True(s.Armed);
        Assert.Equal(Controller.Program, s.InControl);
        s.Evaluate(103.6);                                 // no state for > 3 s
        Assert.Equal(LinkState.TelemetryFrozen, s.Link);
        Assert.Null(s.Armed);
        Assert.Equal("ARMED?", ArmedLogic.Display(s.Armed, s.LastKnownArmed).Value);
    }

    [Fact]
    public void FcDisconnected_StateDoesNotOverwriteLastKnownArmed()
    {
        var s = Linked();
        State(s, true, true, "OFFBOARD", 100.5);
        State(s, false, false, "", 101);                   // MAVROS: FC gone, reports armed=false
        Assert.Equal(LinkState.FcNotConnected, s.Link);
        Assert.Null(s.Armed);
        Assert.True(s.LastKnownArmed);
    }

    [Fact]
    public void FcLost_WhileArmed_RaisesTheAlarmOnce()
    {
        var s = Linked();
        var sounds = 0;
        s.AlarmRaised += () => sounds++;
        State(s, true, true, "OFFBOARD", 100.5);
        State(s, false, false, "", 101);
        State(s, false, false, "", 102);
        Assert.Equal(1, sounds);
        Assert.True(s.FcAlarm.BannerVisible);
        Assert.Contains(s.Messages.Entries, e => e.Text == "Flight controller link lost");
        State(s, true, true, "OFFBOARD", 103);
        Assert.False(s.FcAlarm.BannerVisible);
    }

    [Fact]
    public void Reconnect_SameDrone_ArmedUnknown_LogKept()
    {
        var s = Linked();
        State(s, true, false, "POSCTL", 100.5);
        RosMessages.Apply(s, "/mavros/statustext/recv", J("{\"severity\":3,\"text\":\"Baro failed\"}"), 100.6);
        s.ResetForReconnect(101);
        Assert.Null(s.Armed);
        Assert.Equal(LinkState.NoDrone, s.Link);
        Assert.Contains(s.Messages.Entries, e => e.Text == "[FCU] Baro failed");
        Assert.Equal("POSCTL", s.Mode);                     // kept, shown greyed as stale
        s.SocketOpened("10.0.0.7", 104);
        Assert.Equal(LinkState.NoDrone, s.Link);           // the old state does not count
        Assert.Null(s.Armed);
    }

    [Fact]
    public void ResetAll_ClearsEverythingOfThePreviousDrone()
    {
        var s = Linked();
        State(s, true, true, "OFFBOARD", 100.1);
        RosMessages.Apply(s, "/mavros/mavros/pose",
            J("{\"pose\":{\"position\":{\"x\":1,\"y\":2,\"z\":1.5},\"orientation\":{\"x\":0,\"y\":0,\"z\":0,\"w\":1}}}"), 100.2);
        RosMessages.Apply(s, "/mavros/mavros/velocity_local", J("{\"twist\":{\"linear\":{\"x\":1,\"y\":0,\"z\":0}}}"), 100.3);
        RosMessages.Apply(s, "/mavros/mavros/data",
            J("{\"angular_velocity\":{\"x\":0,\"y\":0,\"z\":1},\"linear_acceleration\":{\"x\":0,\"y\":0,\"z\":9.8}}"), 100.4);
        RosMessages.Apply(s, "/mavros/battery", J("{\"voltage\":20.4,\"percentage\":0.12}"), 100.5);
        RosMessages.Apply(s, "/mavros/statustext/recv", J("{\"severity\":2,\"text\":\"x\"}"), 100.6);
        Assert.NotEmpty(s.PosTrail);
        Assert.True(s.LowBattery.IsLow);

        s.ResetAll(101);

        Assert.Empty(s.PosTrail);
        Assert.Empty(s.ChartAlt);
        Assert.Empty(s.ChartSpd);
        Assert.Empty(s.ChartBat);
        Assert.Empty(s.Messages.Entries);
        Assert.Empty(s.Events.Items);
        Assert.Null(s.PosX);
        Assert.Null(s.PosZ);
        Assert.Null(s.Roll);
        Assert.Null(s.Vx);
        Assert.Null(s.GyroMag);
        Assert.Null(s.AccelMag);
        Assert.Equal(BatteryKind.NoData, s.Battery.Kind);
        Assert.Equal("", s.Mode);
        Assert.Null(s.Armed);
        Assert.Null(s.LastKnownArmed);
        Assert.False(s.LowBattery.IsLow);
        Assert.False(s.FcAlarm.BannerVisible);
        Assert.Equal(LinkState.NoDrone, s.Link);
        Assert.Null(s.PoseAt);
        Assert.Null(s.BatteryAt);
    }

    [Fact]
    public void Attitude_FromPose_WhenImuHasNoOrientation()
    {
        var s = Linked();
        RosMessages.Apply(s, "/mavros/mavros/data",
            J("{\"orientation\":{\"x\":0,\"y\":0,\"z\":0,\"w\":0},\"orientation_covariance\":[-1,0,0,0,0,0,0,0,0]," +
              "\"angular_velocity\":{\"x\":0,\"y\":0,\"z\":0},\"linear_acceleration\":{\"x\":0,\"y\":0,\"z\":9.8}}"), 100.1);
        Assert.Null(s.Pitch);
        var sn = Math.Sin(5 * Math.PI / 180); var cs = Math.Cos(5 * Math.PI / 180);
        RosMessages.Apply(s, "/mavros/mavros/pose",
            J($"{{\"pose\":{{\"position\":{{\"x\":0,\"y\":0,\"z\":1}},\"orientation\":{{\"x\":0,\"y\":{sn.ToString(System.Globalization.CultureInfo.InvariantCulture)},\"z\":0,\"w\":{cs.ToString(System.Globalization.CultureInfo.InvariantCulture)}}}}}}}"), 100.2);
        Assert.Equal(10, s.Pitch!.Value, 6);
        Assert.False(s.AttitudeFromImu);
    }

    [Fact]
    public void Attitude_FromImu_WhenValid_PoseDoesNotOverrideIt()
    {
        var s = Linked();
        var sn = Math.Sin(5 * Math.PI / 180).ToString(System.Globalization.CultureInfo.InvariantCulture);
        var cs = Math.Cos(5 * Math.PI / 180).ToString(System.Globalization.CultureInfo.InvariantCulture);
        RosMessages.Apply(s, "/mavros/mavros/data",
            J($"{{\"orientation\":{{\"x\":0,\"y\":{sn},\"z\":0,\"w\":{cs}}},\"orientation_covariance\":[0.01,0,0,0,0.01,0,0,0,0.01]," +
              "\"angular_velocity\":{\"x\":0,\"y\":0,\"z\":0},\"linear_acceleration\":{\"x\":0,\"y\":0,\"z\":9.8}}"), 100.1);
        Assert.Equal(10, s.Pitch!.Value, 6);
        Assert.True(s.AttitudeFromImu);
        // Pose with level orientation 0.5 s later: the fresh IMU attitude wins.
        RosMessages.Apply(s, "/mavros/mavros/pose",
            J("{\"pose\":{\"position\":{\"x\":0,\"y\":0,\"z\":1},\"orientation\":{\"x\":0,\"y\":0,\"z\":0,\"w\":1}}}"), 100.6);
        Assert.Equal(10, s.Pitch!.Value, 6);
        Assert.Equal(1, s.PosZ);
        // IMU orientation gone stale (> 2 s): the pose takes over.
        RosMessages.Apply(s, "/mavros/mavros/pose",
            J("{\"pose\":{\"position\":{\"x\":0,\"y\":0,\"z\":1},\"orientation\":{\"x\":0,\"y\":0,\"z\":0,\"w\":1}}}"), 102.5);
        Assert.Equal(0, s.Pitch!.Value, 6);
        Assert.False(s.AttitudeFromImu);
    }

    [Fact]
    public void Battery_SentinelAndNull_AreNotMeasured()
    {
        var s = Linked();
        RosMessages.Apply(s, "/mavros/battery", J("{\"voltage\":65.535,\"percentage\":-0.01}"), 100.1);
        Assert.Equal(BatteryKind.NotMeasured, s.Battery.Kind);
        RosMessages.Apply(s, "/mavros/battery", J("{\"voltage\":null,\"percentage\":null}"), 100.2);
        Assert.Equal(BatteryKind.NotMeasured, s.Battery.Kind);
        Assert.Empty(s.ChartBat);
        Assert.Equal(100.2, s.BatteryAt);
    }

    [Fact]
    public void LowBattery_LoggedOnce_PerDrop()
    {
        var s = Linked();
        for (var i = 0; i < 30; i++)
            RosMessages.Apply(s, "/mavros/battery", J("{\"voltage\":20.4,\"percentage\":0.12}"), 100 + i);
        Assert.Single(s.Messages.Entries, e => e.Text.StartsWith("LOW BATTERY"));
        Assert.Equal("LOW BATTERY: 20.40 V · 12%", s.Messages.Entries.First(e => e.Text.StartsWith("LOW")).Text);
        Assert.True(s.LowBattery.IsLow);
    }

    [Fact]
    public void ModeChange_IsAnEvent_AndALogLine()
    {
        var s = Linked();
        State(s, true, true, "OFFBOARD", 100.1);
        State(s, true, true, "POSCTL", 100.9);
        Assert.Equal("Pilot took control", s.Events.Items[0].Text);
        Assert.Contains(s.Messages.Entries, e => e.Text == "mode → POSCTL");
    }

    [Fact]
    public void StatusText_OnlyWarningsAndWorse()
    {
        var s = Linked();
        RosMessages.Apply(s, "/mavros/statustext/recv", J("{\"severity\":6,\"text\":\"info\"}"), 100.1);
        RosMessages.Apply(s, "/mavros/statustext/recv", J("{\"severity\":4,\"text\":\"warn\"}"), 100.2);
        Assert.Equal(new[] { "[FCU] warn" }, s.Messages.Entries.Where(e => e.Kind == LogKind.Fcu).Select(e => e.Text));
    }

    [Fact]
    public void SocketLost_IsOneCollapsingLine()
    {
        var s = Linked();
        for (var i = 0; i < 10; i++) s.SocketLost(101 + i);
        Assert.Equal(2, s.Messages.Entries.Count);
        Assert.Equal("rosbridge lost — reconnecting… · attempt 10", s.Messages.Entries[0].Text);
        Assert.Equal(LinkState.NoDrone, s.Link);
    }

    [Fact]
    public void Freshness_PerSource()
    {
        var s = Linked();
        RosMessages.Apply(s, "/mavros/mavros/velocity_local", J("{\"twist\":{\"linear\":{\"x\":3,\"y\":4,\"z\":-1}}}"), 100);
        Assert.Equal(5, s.SpeedH!.Value, 9);
        Assert.Equal(1, s.SpeedV!.Value, 9);
        Assert.Equal(100, s.VelocityAt);
        Assert.Null(Freshness.StaleNote(s.VelocityAt, 102, Freshness.Limit(TelemetrySource.Velocity)));
        Assert.Equal("no data 2 s", Freshness.StaleNote(s.VelocityAt, 102.1, Freshness.Limit(TelemetrySource.Velocity)));
    }
}
