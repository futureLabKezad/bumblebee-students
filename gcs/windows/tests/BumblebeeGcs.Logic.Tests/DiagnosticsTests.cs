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

using System.Text;
using BumblebeeGcs.Logic;
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

/// <summary>The "Copy diagnostics" report (same cases as the Mac app) and the crash log format.</summary>
public class DiagnosticsTests
{
    private static DiagnosticsInput Input(bool connected = true) => new()
    {
        NowUtc = new DateTime(2026, 10, 23, 8, 0, 0, DateTimeKind.Utc),
        App = "GCS 1.2.0",
        Os = "Microsoft Windows 10.0.26100 (X64)",
        Connected = connected,
        DroneHost = "192.168.1.50",
        DroneName = "Bumblebee-20EC",
        DroneId = "20EC",
        DroneSoftware = "Bumblebee 1.0.2-rc1 (repo v1.0.1-26-g28071be), update installed 2026-10-23T05:57:04Z",
        Link = "OK", Armed = "DISARMED", Mode = "POSCTL", Control = "Disarmed",
        Battery = "Not measured — check with a tester",
        ComputerWifi = "Classroom",
        Found = new[]
        {
            new DiagnosticsInput.FoundDrone("Bumblebee-20EC", "192.168.1.50", "20EC", true),
            new DiagnosticsInput.FoundDrone("Drone", "192.168.1.60", null, false),
        },
        UnknownDevices = 1,
        Hotspots = new[] { "Bumblebee-ABCD" },
        RememberedDrones = new[] { new DiagnosticsInput.Remembered("Bumblebee-20EC", "20EC", "192.168.1.50") },
        Messages = Enumerable.Range(1, 40).Select(i => $"10:00:{i % 60:00} line {i}").ToList(),
    };

    [Fact]
    public void TheReportNamesWhatMatters()
    {
        var r = Diagnostics.Report(Input());
        Assert.Contains("App: GCS 1.2.0 · Microsoft Windows 10.0.26100 (X64)", r);
        Assert.Contains("Drone: Bumblebee-20EC · 192.168.1.50 · id 20EC · software Bumblebee 1.0.2-rc1", r);
        Assert.Contains("Link: OK · State: DISARMED · Mode: POSCTL · Control: Disarmed", r);
        Assert.Contains("This computer's Wi-Fi: Classroom", r);
        Assert.Contains("Drone · 192.168.1.60 · id unknown · not answering", r);
        Assert.Contains("+ 1 other device(s) with port 9090 open", r);
        Assert.Contains("Drone hotspots nearby: Bumblebee-ABCD", r);
        Assert.Contains("Last crash: none recorded", r);
    }

    [Fact]
    public void OnlyTheNewestMessages()
    {
        var r = Diagnostics.Report(Input());
        Assert.Contains("line 30\n", r);
        Assert.DoesNotContain("line 31", r);
    }

    [Fact]
    public void NotConnected()
    {
        var r = Diagnostics.Report(Input(connected: false));
        Assert.Contains("Drone: not connected", r);
        Assert.DoesNotContain("Link:", r);
    }

    [Fact]
    public void OlderDroneSoftware() =>
        Assert.Contains("software unknown (before 1.0.2)", Diagnostics.Report(Input() with { DroneSoftware = null }));

    [Fact]
    public void CrashLogKeepsTheNewestEntryFirstLine()
    {
        var t = new DateTime(2026, 10, 22, 11, 30, 0, DateTimeKind.Utc);
        var log = CrashLogFormat.Append("", CrashLogFormat.Entry(t.AddDays(-2), "GCS 1.1.0", "unhandled UI exception", new InvalidOperationException("old")));
        log = CrashLogFormat.Append(log, CrashLogFormat.Entry(t, "GCS 1.2.0", "unobserved task exception", new TimeoutException("new one")));
        Assert.Equal("2026-10-22T11:30:00Z GCS 1.2.0 unobserved task exception: System.TimeoutException: new one",
            CrashLogFormat.LastEntryHeader(log));
        Assert.Null(CrashLogFormat.LastEntryHeader(""));
    }

    [Fact]
    public void CrashLogStaysSmall()
    {
        var log = "";
        var big = new string('x', 10_000);
        for (var i = 0; i < 100; i++)
            log = CrashLogFormat.Append(log, CrashLogFormat.Entry(DateTime.UtcNow, "GCS 1.2.0", "unhandled exception", new Exception(big + i)));
        Assert.True(Encoding.UTF8.GetByteCount(log) <= CrashLogFormat.MaxBytes);
        Assert.Contains("x99", log);
    }
}
