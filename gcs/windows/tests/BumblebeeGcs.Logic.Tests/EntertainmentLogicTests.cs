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

/// <summary>Entertainment decisions, the same cases as the Mac app's EntertainmentLogicTests.</summary>
public class EntertainmentLogicTests
{
    [Fact]
    public void SoundsOnlyWhenDisarmedIsKnown()
    {
        Assert.Null(SoundGate.BlockedReason(false));
        Assert.Contains("ARMED", SoundGate.BlockedReason(true));
        Assert.Contains("unknown", SoundGate.BlockedReason(null));
    }

    [Fact]
    public void Remaining()
    {
        Assert.Equal("stops by itself in 1:45", LedText.Remaining(105));
        Assert.Equal("stops by itself in 0:07", LedText.Remaining(7));
        Assert.Null(LedText.Remaining(0));
        Assert.Null(LedText.Remaining(null));
    }

    [Fact]
    public void SentIsNotPlayed() => Assert.Equal("Sent to the drone: beep", LedText.Sent("beep"));

    [Fact]
    public void CatalogMatchesTheDrone()
    {
        Assert.Equal(
            new[] { "breathing", "fire", "police", "rainbow", "rainbow_theater", "strobe", "theater" },
            LedCatalog.Animations.OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal(new[] { "alarm", "party", "siren", "victory" }, LedCatalog.Shows.OrderBy(n => n, StringComparer.Ordinal));
        Assert.Equal("Rainbow Theater", LedCatalog.Label("rainbow_theater"));
    }
}
