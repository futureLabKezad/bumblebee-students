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
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

/// <summary>Connect-screen decisions, the same cases as the Mac app's DiscoveryLogicTests, plus
/// the scan adapter and the window size (Windows only).</summary>
public class DiscoveryLogicTests
{
    private static readonly DateTime T0 = new(2026, 10, 23, 8, 0, 0, DateTimeKind.Utc);

    private static JsonElement Json(string s) => JsonDocument.Parse(s).RootElement.Clone();

    [Fact]
    public void RememberedByIdNotByAddress()
    {
        var fleet = KnownFleet.Upsert(new List<KnownDrone>(), "20ec", "Bumblebee-20EC", "192.168.1.50", T0);
        fleet = KnownFleet.Upsert(fleet, "20EC", "Bumblebee-20EC", "192.168.1.77", T0);
        Assert.Single(fleet);
        Assert.Equal("192.168.1.77", fleet[0].LastIp);
        Assert.Equal("20EC", fleet[0].DroneId);
        Assert.True(fleet[0].Verified);
    }

    [Fact]
    public void DirectConnectionsOfTwoDronesAreTwoDrones()
    {
        var fleet = KnownFleet.Upsert(new List<KnownDrone>(), "AAAA", "Bumblebee-AAAA", "10.42.0.1", T0);
        fleet = KnownFleet.Upsert(fleet, "BBBB", "Bumblebee-BBBB", "10.42.0.1", T0);
        Assert.Equal(new[] { "BBBB", "AAAA" }, fleet.Select(k => k.DroneId));
    }

    [Fact]
    public void AnIdReplacesTheUnverifiedEntryOfItsAddress()
    {
        var fleet = KnownFleet.Upsert(new List<KnownDrone>(), null, "192.168.1.50", "192.168.1.50", T0);
        Assert.False(fleet[0].Verified);
        Assert.Equal("ip:192.168.1.50", fleet[0].Key);
        fleet = KnownFleet.Upsert(fleet, "20EC", "Bumblebee-20EC", "192.168.1.50", T0);
        Assert.Single(fleet);
        Assert.Equal("20EC", fleet[0].DroneId);
    }

    [Fact]
    public void AKnownNameIsNotReplacedByAnAddress()
    {
        var fleet = KnownFleet.Upsert(new List<KnownDrone>(), "20EC", "Lab-3", "192.168.1.50", T0);
        fleet = KnownFleet.Upsert(fleet, "20EC", "192.168.1.51", "192.168.1.51", T0);
        Assert.Equal("Lab-3", fleet[0].Name);
    }

    [Fact]
    public void Forget()
    {
        var fleet = KnownFleet.Upsert(new List<KnownDrone>(), "20EC", "x", "1.2.3.4", T0);
        Assert.Empty(KnownFleet.Forget(fleet, "20EC"));
    }

    [Fact]
    public void OldEntriesMoveOver()
    {
        var fleet = KnownFleet.Migrate(new[] { ("10.0.0.5", "Bumblebee-5"), ("10.0.0.6", "Bumblebee-6") }, "10.0.0.6", T0);
        Assert.Equal("10.0.0.6", fleet[0].LastIp);
        Assert.Equal("Bumblebee-6", fleet[0].Name);
        Assert.Equal(2, fleet.Count);
        Assert.All(fleet, k => Assert.False(k.Verified));
        Assert.Empty(KnownFleet.Migrate(Array.Empty<(string, string)>(), null, T0));
    }

    [Fact]
    public void FleetSurvivesJson()
    {
        var fleet = KnownFleet.Upsert(new List<KnownDrone>(), "20EC", "Lab-3", "192.168.1.50", T0);
        var back = JsonSerializer.Deserialize<List<KnownDrone>>(JsonSerializer.Serialize(fleet))!;
        Assert.Equal(fleet, back);
    }

    [Fact]
    public void TheLastDroneIsFoundByItsId()
    {
        var last = new KnownDrone("20EC", "Bumblebee-20EC", "192.168.1.50", T0);
        Assert.Equal("192.168.1.77", KnownFleet.CurrentIp(last, new[] { ("192.168.1.77", (string?)"20EC") }));
        Assert.Equal("192.168.1.50", KnownFleet.CurrentIp(last, new[] { ("192.168.1.50", (string?)"ABCD") }));
        var old = new KnownDrone("", "x", "10.0.0.5", T0);
        Assert.Equal("10.0.0.5", KnownFleet.CurrentIp(old, new[] { ("10.0.0.9", (string?)null) }));
    }

    [Fact]
    public void LivenessRules()
    {
        Assert.Equal(Liveness.Live, LivenessRule.Of(0));
        Assert.Equal(Liveness.Unsure, LivenessRule.Of(1));
        Assert.Equal(Liveness.Unsure, LivenessRule.Of(2));
        Assert.Equal(Liveness.Gone, LivenessRule.Of(3));
        Assert.True(LivenessRule.PeriodSeconds * LivenessRule.GoneAfter <= 30);
    }

    [Fact]
    public void ADroneAnswersLikeADrone()
    {
        Assert.Equal(new DeviceKind(true, "20EC", "Bumblebee-20EC"), DeviceKind.Classify(Json("""{"mode":"client","id":"20ec"}"""), null));
        Assert.Equal(new DeviceKind(true), DeviceKind.Classify(Json("""{"mode":"client"}"""), null));
        Assert.Equal(new DeviceKind(true, null, "Bumblebee-7"), DeviceKind.Classify(null, Json("""{"cpu_pct":12.0,"name":"Bumblebee-7"}""")));
    }

    [Fact]
    public void OtherDevicesAreNotDrones()
    {
        Assert.False(DeviceKind.Classify(null, null).IsDrone);
        Assert.False(DeviceKind.Classify(Json("""{"status":"ok"}"""), Json("""{"hostname":"laptop"}""")).IsDrone);
    }

    [Fact]
    public void HotspotRows()
    {
        var known = new[] { new KnownDrone("20EC", "Lab-3", "1.2.3.4", T0) };
        Assert.Equal(new HotspotRow(HotspotKind.LostWifi, "Lab-3"), HotspotRow.Of("Bumblebee-20EC", known, new HashSet<string>()));
        Assert.Equal(HotspotKind.Hidden, HotspotRow.Of("Bumblebee-20EC", known, new HashSet<string> { "20EC" }).Kind);
        Assert.Equal(HotspotKind.New, HotspotRow.Of("Bumblebee-ABCD", known, new HashSet<string>()).Kind);
        Assert.Equal("20EC", HotspotRow.IdOf("Bumblebee-20ec"));
        Assert.Null(HotspotRow.IdOf("Classroom"));
    }

    [Theory]
    [InlineData("192.168.1.50", true)]
    [InlineData(" 10.42.0.1 ", true)]
    [InlineData("bumblebee-20ec.local", true)]
    [InlineData("localhost", true)]
    [InlineData("", true)]
    [InlineData("192.168.1.256", false)]
    [InlineData("192.168.1", false)]
    [InlineData("http://192.168.1.5", false)]
    [InlineData("192 168 1 5", false)]
    public void ManualAddresses(string text, bool ok) => Assert.Equal(ok, ManualAddress.Problem(text) is null);

    [Fact]
    public void ScanTheRealNetworkNotAVirtualAdapter()
    {
        var wsl = new ScanAdapter.Candidate("vEthernet (WSL)", "Hyper-V Virtual Ethernet Adapter", false, false, "172.27.16.1");
        var lan = new ScanAdapter.Candidate("Ethernet", "Realtek PCIe GbE", false, true, "192.168.1.20");
        var wifi = new ScanAdapter.Candidate("Wi-Fi", "Intel Wi-Fi 6E", true, true, "10.255.254.40");
        var linkLocal = new ScanAdapter.Candidate("Ethernet 2", "USB LAN", false, false, "169.254.3.4");
        Assert.Equal("192.168.1.", ScanAdapter.Prefix(new[] { wsl, lan }));
        Assert.Equal("10.255.254.", ScanAdapter.Prefix(new[] { wsl, lan, wifi }));
        Assert.Null(ScanAdapter.Prefix(new[] { wsl, linkLocal }));
        Assert.True(ScanAdapter.IsVirtual(new ScanAdapter.Candidate("Ethernet 3", "VirtualBox Host-Only Ethernet Adapter", false, false, "192.168.56.1")));
    }

    [Fact]
    public void WindowFitsTheScreen()
    {
        // 150 % on 1920x1080 (work area 1920x1032): the 1230 px tall window no longer fits as asked.
        var (w, h, minW, minH) = WindowFit.Size(1280, 820, 1100, 720, 1.5, 1920, 1032);
        Assert.True(w <= 1920 && h <= 1032 * 0.95 + 1, $"{w}x{h}");
        Assert.True(minH <= 1032, $"min height {minH}");
        // 100 % on a 1366x768 projector.
        (w, h, minW, minH) = WindowFit.Size(1280, 820, 1100, 720, 1.0, 1366, 728);
        Assert.True(h <= 728 && minH <= 728);
        // Plenty of room: the wanted size.
        (w, h, _, _) = WindowFit.Size(1280, 820, 1100, 720, 1.0, 2560, 1400);
        Assert.Equal((1280, 820), (w, h));
    }
}
