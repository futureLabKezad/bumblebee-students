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
        Assert.Equal("ARMED? link lost", d.Value);   // one value, as on the Mac
        Assert.Equal("", d.Caption);
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
    [InlineData(null, "")]            // no State yet: nothing to explain
    [InlineData("RATTITUDE", "")]     // unknown names are shown as they are
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

    // Events follow the Mac app: a line when the hands on the drone change, and
    // when PX4 changes its own manoeuvre. Mode changes inside one owner are only
    // "mode → X" lines in the Messages panel.
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
        Assert.Equal("Pilot took control",
            ModeLogic.EventText(Controller.Disarmed, "POSCTL", Controller.Pilot, "POSCTL"));
        Assert.Equal("Program took control",
            ModeLogic.EventText(Controller.Disarmed, "OFFBOARD", Controller.Program, "OFFBOARD"));
        Assert.Equal("Disarmed",
            ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Disarmed, "POSCTL"));
        Assert.Equal("PX4 is returning",
            ModeLogic.EventText(Controller.Px4, "AUTO.LAND", Controller.Px4, "AUTO.RTL"));
    }

    [Fact]
    public void Events_NoneForTheFirstValue_NoChange_SameOwner_OrUnknown()
    {
        Assert.Null(ModeLogic.EventText(Controller.Unknown, "", Controller.Program, "OFFBOARD"));
        Assert.Null(ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Pilot, "POSCTL"));
        Assert.Null(ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Pilot, "ALTCTL"));
        Assert.Null(ModeLogic.EventText(Controller.Disarmed, "POSCTL", Controller.Disarmed, "OFFBOARD"));
        Assert.Null(ModeLogic.EventText(Controller.Px4, "AUTO.LAND", Controller.Px4, "AUTO.LAND"));
        Assert.Null(ModeLogic.EventText(Controller.Pilot, "POSCTL", Controller.Unknown, "POSCTL"));
    }

    [Fact]
    public void ControlEvents_SameSequenceAsTheMacApp()
    {
        var ev = new ControlEvents();
        Assert.Null(ev.Update(Controller.Disarmed, "POSCTL", "12:00:00"));    // first look is not an event
        Assert.Null(ev.Latest);
        Assert.Equal("Pilot took control", ev.Update(Controller.Pilot, "POSCTL", "12:00:01"));
        Assert.Null(ev.Update(Controller.Pilot, "POSCTL", "12:00:02"));
        Assert.Null(ev.Update(Controller.Pilot, "ALTCTL", "12:00:03"));       // pilot changing hold mode
        Assert.Equal("Program took control", ev.Update(Controller.Program, "OFFBOARD", "12:00:04"));
        Assert.Equal("Pilot took control", ev.Update(Controller.Pilot, "POSCTL", "12:00:05"));
        Assert.Equal("PX4 is holding", ev.Update(Controller.Px4, "AUTO.LOITER", "12:00:06"));
        Assert.Equal("PX4 is landing", ev.Update(Controller.Px4, "AUTO.LAND", "12:00:07"));
        Assert.Null(ev.Update(Controller.Unknown, "AUTO.LAND", "12:00:08"));  // link lost: no event
        Assert.Null(ev.Update(Controller.Px4, "AUTO.LAND", "12:00:09"));      // same as before the gap
        Assert.Equal("PX4 is returning", ev.Update(Controller.Px4, "AUTO.RTL", "12:00:10"));
        Assert.Equal("PX4 is taking off", ev.Update(Controller.Px4, "AUTO.TAKEOFF", "12:00:11"));
        Assert.Equal("PX4 took control", ev.Update(Controller.Px4, "AUTO.MISSION", "12:00:12"));
        Assert.Equal("Disarmed", ev.Update(Controller.Disarmed, "AUTO.MISSION", "12:00:20"));
        Assert.Equal(new ControlEvent("12:00:20", "Disarmed", "AUTO.MISSION"), ev.Latest);
        var v = ev.Version;
        ev.Reset();
        Assert.Null(ev.Latest);
        Assert.NotEqual(v, ev.Version);
        Assert.Null(ev.Update(Controller.Pilot, "POSCTL", "12:01:00"));       // new first look after reset
    }

    [Fact]
    public void ControlTile_WaitsForFcData_OnlyWhileArmedIsUnknown()
    {
        Assert.Equal("waiting for FC data", ModeLogic.ControlCaption(Controller.Unknown, null));
        Assert.Equal("", ModeLogic.ControlCaption(Controller.Unknown, true));   // armed in a mode we do not know
        Assert.Equal("", ModeLogic.ControlCaption(Controller.Program, true));
        Assert.Equal("", ModeLogic.ControlCaption(Controller.Disarmed, false));
    }

    [Theory]
    [InlineData("OFFBOARD", "OFFBOARD · program in control")]
    [InlineData("AUTO.LAND", "AUTO.LAND · PX4 landing")]
    [InlineData("RATTITUDE", "RATTITUDE")]
    [InlineData("", "")]
    public void EventLine_ModeWithItsExplanation(string mode, string text) =>
        Assert.Equal(text, ModeLogic.ModeWithExplanation(mode));

    [Theory]
    [InlineData("CMODE(50593792)", "AUTO.LOITER")]   // 0x03040000
    [InlineData("CMODE(393216)", "OFFBOARD")]        // main 6
    [InlineData("CMODE(196608)", "POSCTL")]          // main 3
    [InlineData("CMODE(100925440)", "AUTO.LAND")]    // 0x06040000
    [InlineData("CMODE(4096)", "CMODE(4096)")]       // unknown numbers stay as they are
    [InlineData("CMODE(x)", "CMODE(x)")]
    [InlineData("POSCTL", "POSCTL")]
    [InlineData("", "")]
    public void ModeNumbersFromMavros_AreNamed(string raw, string name) =>
        Assert.Equal(name, ModeLogic.Normalize(raw));
}
