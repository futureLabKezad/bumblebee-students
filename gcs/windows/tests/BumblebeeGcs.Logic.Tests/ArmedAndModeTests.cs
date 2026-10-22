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

public class ArmedLogicTests
{
    [Theory]
    [InlineData(LinkState.NoDrone)]
    [InlineData(LinkState.FcNotConnected)]
    [InlineData(LinkState.TelemetryFrozen)]
    public void ArmedIsUnknown_UnlessTheLinkIsOk(LinkState link)
    {
        Assert.Null(ArmedLogic.Effective(link, true));
        Assert.Null(ArmedLogic.Effective(link, false));
    }

    [Fact]
    public void OkLink_PassesTheStateValue()
    {
        Assert.True(ArmedLogic.Effective(LinkState.Ok, true));
        Assert.False(ArmedLogic.Effective(LinkState.Ok, false));
        Assert.Null(ArmedLogic.Effective(LinkState.Ok, null));
    }

    [Fact]
    public void Tile_Disarmed_OnlyFromAKnownFalse()
    {
        var d = ArmedLogic.Display(false, false);
        Assert.Equal("DISARMED", d.Value);
        Assert.Equal(Tone.Neutral, d.Tone);
    }

    [Fact]
    public void Tile_Armed_IsDanger()
    {
        var d = ArmedLogic.Display(true, true);
        Assert.Equal("ARMED", d.Value);
        Assert.Equal(Tone.Danger, d.Tone);
    }

    [Theory]
    [InlineData(null)]
    [InlineData(false)]
    public void Tile_Unknown_IsCaution_WaitingForFc(bool? lastKnown)
    {
        var d = ArmedLogic.Display(null, lastKnown);
        Assert.Equal("UNKNOWN", d.Value);
        Assert.Equal("waiting for FC data", d.Caption);
        Assert.Equal(Tone.Caution, d.Tone);
    }

    [Fact]
    public void Tile_WasArmedAndBecameUnknown_SaysArmedLinkLost()
    {
        var d = ArmedLogic.Display(null, true);
        Assert.Equal("ARMED?", d.Value);
        Assert.Equal("link lost", d.Caption);
        Assert.Equal(Tone.Danger, d.Tone);
    }
}

public class ModeLogicTests
{
    [Theory]
    [InlineData("OFFBOARD", "program in control")]
    [InlineData("POSCTL", "pilot, position hold")]
    [InlineData("ALTCTL", "pilot, altitude hold")]
    [InlineData("STABILIZED", "pilot, manual")]
    [InlineData("ACRO", "pilot, manual")]
    [InlineData("MANUAL", "pilot, manual")]
    [InlineData("AUTO.LAND", "PX4 landing")]
    [InlineData("AUTO.LOITER", "PX4 holding")]
    [InlineData("AUTO.RTL", "PX4 returning")]
    [InlineData("AUTO.TAKEOFF", "PX4 taking off")]
    [InlineData("AUTO.MISSION", "PX4 automatic")]
    [InlineData("AUTO.PRECLAND", "PX4 automatic")]
    [InlineData("", "unknown")]
    [InlineData(null, "unknown")]
    [InlineData("RATTITUDE", "")]
    public void Explanations(string? mode, string text) => Assert.Equal(text, ModeLogic.Explain(mode));

    [Fact]
    public void DisplayMode_DashBeforeTheFirstState()
    {
        Assert.Equal("—", ModeLogic.DisplayMode(""));
        Assert.Equal("—", ModeLogic.DisplayMode(null));
        Assert.Equal("POSCTL", ModeLogic.DisplayMode("posctl"));
    }

    [Theory]
    [InlineData(true, "OFFBOARD", Controller.Program)]
    [InlineData(true, "POSCTL", Controller.Pilot)]
    [InlineData(true, "ALTCTL", Controller.Pilot)]
    [InlineData(true, "STABILIZED", Controller.Pilot)]
    [InlineData(true, "ACRO", Controller.Pilot)]
    [InlineData(true, "MANUAL", Controller.Pilot)]
    [InlineData(true, "AUTO.LAND", Controller.Px4)]
    [InlineData(true, "AUTO.RTL", Controller.Px4)]
    [InlineData(true, "AUTO.LOITER", Controller.Px4)]
    [InlineData(true, "", Controller.Unknown)]
    [InlineData(true, "RATTITUDE", Controller.Unknown)]
    [InlineData(false, "OFFBOARD", Controller.Disarmed)]
    [InlineData(false, "", Controller.Disarmed)]
    [InlineData(null, "OFFBOARD", Controller.Unknown)]
    public void WhoIsInControl(bool? armed, string mode, Controller who) =>
        Assert.Equal(who, ModeLogic.WhoIsInControl(armed, mode));

    [Theory]
    [InlineData(Controller.Program, "Program")]
    [InlineData(Controller.Pilot, "Pilot")]
    [InlineData(Controller.Px4, "PX4")]
    [InlineData(Controller.Disarmed, "Disarmed")]
    [InlineData(Controller.Unknown, "Unknown")]
    public void ControllerNames(Controller c, string text) => Assert.Equal(text, ModeLogic.ControllerText(c));

    [Fact]
    public void Events_PilotTakesOverFromTheProgram()
    {
        Assert.Equal("Pilot took control",
            ModeLogic.EventText(Controller.Program, "OFFBOARD", Controller.Pilot, "POSCTL"));
    }

    [Theory]
    [InlineData("AUTO.LAND", "PX4 is landing")]
    [InlineData("AUTO.RTL", "PX4 is returning")]
    [InlineData("AUTO.LOITER", "PX4 is holding")]
    [InlineData("AUTO.TAKEOFF", "PX4 is taking off")]
    [InlineData("AUTO.MISSION", "PX4 took control")]
    public void Events_Px4Modes(string mode, string text) =>
        Assert.Equal(text, ModeLogic.EventText(Controller.Program, "OFFBOARD", Controller.Px4, mode));

    [Fact]
    public void Events_OtherTransitions()
    {
        Assert.Equal("Program took control",
            ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Program, "OFFBOARD"));
        Assert.Equal("Pilot: altitude hold",
            ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Pilot, "ALTCTL"));
        Assert.Equal("Armed: pilot in control",
            ModeLogic.EventText(Controller.Disarmed, "POSCTL", Controller.Pilot, "POSCTL"));
        Assert.Equal("Disarmed",
            ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Disarmed, "POSCTL"));
        Assert.Equal("Mode → ALTCTL (pilot, altitude hold)",
            ModeLogic.EventText(Controller.Disarmed, "POSCTL", Controller.Disarmed, "ALTCTL"));
    }

    [Fact]
    public void Events_NoneForTheFirstValue_NoChange_OrUnknown()
    {
        Assert.Null(ModeLogic.EventText(Controller.Unknown, "", Controller.Program, "OFFBOARD"));
        Assert.Null(ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Pilot, "POSCTL"));
        Assert.Null(ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Unknown, "POSCTL"));
    }

    [Fact]
    public void ControlEvents_KeepTheLastFew_AndSurviveALinkGap()
    {
        var ev = new ControlEvents();
        Assert.Null(ev.Update(Controller.Disarmed, "POSCTL", "12:00:00"));   // baseline
        Assert.Equal("Armed: pilot in control", ev.Update(Controller.Pilot, "POSCTL", "12:00:01"));
        Assert.Null(ev.Update(Controller.Unknown, "POSCTL", "12:00:02"));     // link lost: no event
        Assert.Equal("Program took control", ev.Update(Controller.Program, "OFFBOARD", "12:00:05"));
        Assert.Equal("PX4 is landing", ev.Update(Controller.Px4, "AUTO.LAND", "12:00:09"));
        Assert.Equal("Disarmed", ev.Update(Controller.Disarmed, "AUTO.LAND", "12:00:20"));
        Assert.Equal(ControlEvents.Max, ev.Items.Count);
        Assert.Equal("Disarmed", ev.Items[0].Text);
        Assert.Equal("12:00:20", ev.Items[0].Time);
        ev.Reset();
        Assert.Empty(ev.Items);
        Assert.Null(ev.Update(Controller.Pilot, "POSCTL", "12:01:00"));      // new baseline after reset
    }
}
