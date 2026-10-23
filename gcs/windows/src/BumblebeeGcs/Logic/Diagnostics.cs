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

using System.Globalization;
using System.Text;

namespace BumblebeeGcs.Logic;

/// <summary>
/// "Copy diagnostics": one plain-text report a teacher can paste into a message when something
/// goes wrong in class. Built from values only, so the tests check it; it never holds a Wi-Fi
/// password. Same report as the Mac app (DiagnosticsLogic.swift).
/// </summary>
public sealed record DiagnosticsInput
{
    public sealed record FoundDrone(string Name, string Ip, string? DroneId, bool Live);
    public sealed record Remembered(string Name, string DroneId, string LastIp);

    public DateTime NowUtc { get; init; }
    public string App { get; init; } = "";           // "GCS 1.1.0"
    public string Os { get; init; } = "";            // "Windows 11 (10.0.26100, X64)"
    public bool Connected { get; init; }
    public string DroneHost { get; init; } = "";
    public string DroneName { get; init; } = "";
    public string? DroneId { get; init; }
    public string? DroneSoftware { get; init; }      // first line of /etc/bumblebee_version, via /api/info
    public string Link { get; init; } = "";
    public string Armed { get; init; } = "";
    public string Mode { get; init; } = "";
    public string Control { get; init; } = "";
    public string Battery { get; init; } = "";
    public string ComputerWifi { get; init; } = "";  // "" = unknown (no Location permission)
    public bool OnDroneHotspot { get; init; }
    public IReadOnlyList<FoundDrone> Found { get; init; } = Array.Empty<FoundDrone>();
    public int UnknownDevices { get; init; }
    public IReadOnlyList<string> Hotspots { get; init; } = Array.Empty<string>();
    public IReadOnlyList<Remembered> RememberedDrones { get; init; } = Array.Empty<Remembered>();
    public IReadOnlyList<string> Messages { get; init; } = Array.Empty<string>();   // newest first
    public string? LastCrash { get; init; }
}

public static class Diagnostics
{
    public const int MaxMessages = 30;

    public static string Report(DiagnosticsInput d)
    {
        var inv = CultureInfo.InvariantCulture;
        var sb = new StringBuilder();
        void Line(string s = "") => sb.Append(s).Append('\n');

        Line($"Bumblebee GCS diagnostics — {d.NowUtc.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss", inv)} (UTC {d.NowUtc.ToString("HH:mm:ss", inv)})");
        Line($"App: {d.App} · {d.Os}");
        Line();
        if (d.Connected)
        {
            Line($"Drone: {d.DroneName} · {d.DroneHost} · id {d.DroneId ?? "unknown"} · software {d.DroneSoftware ?? "unknown (before 1.0.2)"}");
            Line($"Link: {d.Link} · State: {d.Armed} · Mode: {d.Mode} · Control: {d.Control}");
            Line($"Battery: {d.Battery}");
        }
        else
        {
            Line("Drone: not connected");
        }
        Line($"This computer's Wi-Fi: {(d.ComputerWifi.Length == 0 ? "unknown" : d.ComputerWifi)}" +
             (d.OnDroneHotspot ? " (a drone's own hotspot)" : ""));
        Line();
        Line($"Drones found ({d.Found.Count}):");
        foreach (var f in d.Found)
            Line($"  {f.Name} · {f.Ip} · id {f.DroneId ?? "unknown"}{(f.Live ? "" : " · not answering")}");
        if (d.UnknownDevices > 0) Line($"  + {d.UnknownDevices} other device(s) with port 9090 open");
        Line($"Drone hotspots nearby: {(d.Hotspots.Count == 0 ? "none" : string.Join(", ", d.Hotspots))}");
        Line($"Remembered drones ({d.RememberedDrones.Count}):");
        foreach (var r in d.RememberedDrones)
            Line($"  {r.Name} · id {(r.DroneId.Length == 0 ? "unknown" : r.DroneId)} · last {r.LastIp}");
        Line();
        Line("Last messages (newest first):");
        if (d.Messages.Count == 0) Line("  none");
        foreach (var m in d.Messages.Take(MaxMessages)) Line($"  {m}");
        Line();
        sb.Append($"Last crash: {d.LastCrash ?? "none recorded"}");
        return sb.ToString();
    }
}

/// <summary>The crash log: entries start with "ISO-time version kind: message"; the newest
/// entry's first line is what diagnostics shows. The file keeps its newest MaxBytes.</summary>
public static class CrashLogFormat
{
    public const int MaxBytes = 256 * 1024;

    public static string Entry(DateTime nowUtc, string version, string kind, Exception ex) =>
        $"{nowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture)} {version} {kind}: " +
        $"{ex.GetType().FullName}: {ex.Message}\n{ex}\n\n";

    public static string? LastEntryHeader(string log)
    {
        string? last = null;
        foreach (var line in log.Split('\n'))
            if (line.Length > 20 && char.IsAsciiDigit(line[0]) && line[4] == '-' && line.Contains(": ")) last = line.TrimEnd('\r');
        return last;
    }

    /// <summary>The log with the new entry, cut to its newest MaxBytes (at a line start).</summary>
    public static string Append(string log, string entry)
    {
        var all = log + entry;
        if (Encoding.UTF8.GetByteCount(all) <= MaxBytes) return all;
        var tail = all[^Math.Min(all.Length, MaxBytes / 2)..];
        var nl = tail.IndexOf('\n');
        return nl >= 0 ? tail[(nl + 1)..] : tail;
    }
}
