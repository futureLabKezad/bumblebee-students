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

/// <summary>Settings decisions, the same cases as the Mac app's SettingsLogicTests.</summary>
public class SettingsLogicTests
{
    private static readonly DateTime T0 = new(2026, 10, 23, 8, 0, 0, DateTimeKind.Utc);

    [Fact]
    public void CodesWinOverTheDronesText()
    {
        Assert.Contains("ARMED", DroneErrorText.Text("armed", "x", 409));
        Assert.Contains("counts as armed", DroneErrorText.Text("fc_unknown", "x", 503));
        Assert.Contains("8 to 63", DroneErrorText.Text("bad_password_length", "x", 400));
        Assert.Contains("hotspot", DroneErrorText.Text("protected_network", "x", 409));
    }

    [Fact]
    public void OlderDronesTextIsShownAsItIs()
    {
        Assert.Equal("led unavailable", DroneErrorText.Text(null, "led unavailable", 503));
        Assert.Equal("new text", DroneErrorText.Text("something_new", "new text", 400));
        Assert.Equal("HTTP 500", DroneErrorText.Text(null, null, 500));
    }

    [Fact]
    public void JoinReasons()
    {
        Assert.Equal("wrong password for Lab", JoinReasonText.Text("wrong_password", "Lab"));
        Assert.Equal("the drone can't see Lab", JoinReasonText.Text("not_found", "Lab"));
        Assert.Contains("armed", JoinReasonText.Text("fc_unknown", "Lab"));
        Assert.Equal("the drone couldn't join Lab", JoinReasonText.Text("failed", "Lab"));
    }

    [Fact]
    public void OldFailureIsNotShownForever()
    {
        Assert.Contains("wrong password for Lab",
            JoinReasonText.Banner("Lab", "wrong_password", T0, T0.AddMinutes(1)));
        Assert.Null(JoinReasonText.Banner("Lab", "wrong_password", T0, T0.AddMinutes(31)));
        Assert.NotNull(JoinReasonText.Banner("Lab", "timeout", null, T0));
    }

    [Theory]
    [InlineData("bumblebee-hotspot", true)]
    [InlineData("Bumblebee-20EC", true)]
    [InlineData("BUMBLEBEE-ABCD", true)]
    [InlineData(" bumblebee-x ", true)]
    [InlineData("Lab.bb-pending", true)]
    [InlineData("Lab", false)]
    [InlineData("Bumblebees", false)]
    [InlineData("my-bumblebee-net", false)]
    [InlineData("", false)]
    public void ProtectedNames(string name, bool expected) => Assert.Equal(expected, WifiNames.IsProtected(name));

    [Theory]
    [InlineData("WPA2", true)]
    [InlineData("WPA1 WPA2", true)]
    [InlineData("", false)]
    [InlineData("--", false)]
    [InlineData(" -- ", false)]
    public void Security(string s, bool expected) => Assert.Equal(expected, WifiNames.IsSecured(s));

    [Fact]
    public void ScanSsidMatchesItsProfile()
    {
        Assert.True(WifiNames.Same("Classroom", "Classroom"));
        Assert.True(WifiNames.Same("Classroom", "netplan-wlan0-Classroom"));
        Assert.False(WifiNames.Same("Class", "Classroom"));
        Assert.False(WifiNames.Same("", ""));
    }

    [Fact]
    public void PasswordLength()
    {
        Assert.Equal(PasswordResult.Length, PasswordCheck.Check("1234567", true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check("12345678", true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check(new string('a', 63), true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check(new string('a', 64), true));
        Assert.Equal(PasswordResult.Length, PasswordCheck.Check(new string('z', 64), true));
        Assert.Equal(PasswordResult.Length, PasswordCheck.Check(new string('a', 65), true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check("пароль12", true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check("абвг", true));
        Assert.Equal(PasswordResult.Length, PasswordCheck.Check("абв", true));
    }

    [Fact]
    public void SpacesAtTheEndsAreRefusedNotTrimmed()
    {
        Assert.Equal(PasswordResult.Spaces, PasswordCheck.Check(" password", true));
        Assert.Equal(PasswordResult.Spaces, PasswordCheck.Check("password ", true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check("pass word", true));
    }

    [Fact]
    public void EmptyPassword()
    {
        Assert.Equal(PasswordResult.Missing, PasswordCheck.Check("", true));
        Assert.Equal(PasswordResult.Ok, PasswordCheck.Check("", false));
        Assert.True(PasswordCheck.NeedsPassword(false, true));
        Assert.False(PasswordCheck.NeedsPassword(false, false));
        Assert.True(PasswordCheck.NeedsPassword(false, null));
        Assert.False(PasswordCheck.NeedsPassword(true, true));
    }

    [Fact]
    public void Identity()
    {
        Assert.Equal(IdentityKind.Same, DroneIdentity.Check("20EC", "20ec").Kind);
        var other = DroneIdentity.Check("20EC", "abcd");
        Assert.Equal(IdentityKind.Different, other.Kind);
        Assert.Equal("ABCD", other.Now);
        Assert.True(other.Blocks);
        Assert.Equal(IdentityKind.Unknown, DroneIdentity.Check(null, "ABCD").Kind);
        Assert.Equal(IdentityKind.Unknown, DroneIdentity.Check("20EC", null).Kind);
        Assert.Equal(IdentityKind.Unknown, DroneIdentity.Check("20EC", "").Kind);
        Assert.False(DroneIdentity.Check("20EC", null).Blocks);
    }

    [Fact]
    public void FollowUp()
    {
        Assert.Equal(FollowUpKind.WaitHere, ApplyFollowUp.Decide("Lab", "Lab", "20EC").Kind);
        Assert.Equal(FollowUpKind.WaitHere, ApplyFollowUp.Decide("netplan-wlan0-Lab", "Lab", "20EC").Kind);
        Assert.Equal(FollowUpKind.WaitHere, ApplyFollowUp.Decide("Lab", "", "20EC").Kind);
        var other = ApplyFollowUp.Decide("Lab", "Home", "20EC");
        Assert.Equal(FollowUpKind.OtherNetwork, other.Kind);
        Assert.Contains("Home", other.Text("Bumblebee-20EC", "Lab"));
        Assert.Equal(FollowUpKind.NoId, ApplyFollowUp.Decide("Lab", "Lab", null).Kind);
    }

    [Fact]
    public void MatchById()
    {
        Assert.True(DroneMatch.Accepts("20EC", "20ec", 0));
        Assert.False(DroneMatch.Accepts("20EC", "ABCD", 30));
        Assert.False(DroneMatch.Accepts("20EC", null, 30));
    }

    [Fact]
    public void WithoutAnIdDronesAlreadyThereDoNotCount()
    {
        Assert.False(DroneMatch.Accepts(null, null, 0.5));
        Assert.True(DroneMatch.Accepts(null, null, 6));
        Assert.False(DroneMatch.Accepts(null, "ABCD", 6));
    }

    [Theory]
    [InlineData(null, PasswordMemory.Save)]
    [InlineData("WrongPassword", PasswordMemory.Forget)]
    [InlineData("Isolated", PasswordMemory.Save)]
    [InlineData("NoAddress", PasswordMemory.Save)]
    [InlineData("NotFound", PasswordMemory.Save)]
    [InlineData("DroneSilent", PasswordMemory.Keep)]
    [InlineData("Other", PasswordMemory.Keep)]
    public void PasswordIsKeptOnlyWhenItWorked(string? failure, PasswordMemory expected) =>
        Assert.Equal(expected, PasswordMemoryRule.After(failure));
}
