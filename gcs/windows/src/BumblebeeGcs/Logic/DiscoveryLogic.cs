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
using System.Text.Json.Serialization;

namespace BumblebeeGcs.Logic;

// The connect screen's decisions, without WinUI so the tests can check them: which drones
// are remembered and how, when a row is live, stale or gone, what is a drone and what is
// just a device with port 9090 open, what a drone hotspot in the Wi-Fi list means. Same
// rules as the Mac app (DiscoveryLogic.swift).

/// <summary>
/// A drone this PC connected to before, keyed by its hardware id (last 4 hex digits of its
/// Wi-Fi MAC: DNS-SD TXT id, /api/wifi/status, hotspot SSID suffix), so a new address after
/// DHCP or a direct connection over its hotspot (10.42.0.1 on every drone) still names the
/// same drone. Drone software without an id is kept by address, unverified.
/// </summary>
public sealed record KnownDrone(string DroneId, string Name, string LastIp, DateTime LastSeenUtc)
{
    [JsonIgnore] public string Key => DroneId.Length == 0 ? "ip:" + LastIp : DroneId;
    [JsonIgnore] public bool Verified => DroneId.Length > 0;
}

public static class KnownFleet
{
    /// <summary>The fleet after a successful connection to ip (droneId null or "" if the drone has
    /// none). An entry with an id replaces an unverified entry of the same address; most recent first.</summary>
    public static List<KnownDrone> Upsert(IReadOnlyList<KnownDrone> list, string? droneId, string name, string ip, DateTime nowUtc)
    {
        var id = (droneId ?? "").ToUpperInvariant();
        bool Same(KnownDrone k) => id.Length > 0 ? k.DroneId == id : k.DroneId.Length == 0 && k.LastIp == ip;
        var old = list.FirstOrDefault(Same);
        var outList = list.Where(k => !Same(k) && !(id.Length > 0 && k.DroneId.Length == 0 && k.LastIp == ip)).ToList();
        var keepName = old is not null && name == ip ? old.Name : name;
        outList.Insert(0, new KnownDrone(id, keepName, ip, nowUtc));
        return outList;
    }

    /// <summary>The fleet without one drone ("Forget").</summary>
    public static List<KnownDrone> Forget(IReadOnlyList<KnownDrone> list, string key) =>
        list.Where(k => k.Key != key).ToList();

    /// <summary>Entries of the 1.1.0 format (host + name, no id) and the old last host.</summary>
    public static List<KnownDrone> Migrate(IReadOnlyList<(string Host, string Name)> hosts, string? lastHost, DateTime nowUtc)
    {
        var outList = hosts.Select(h => new KnownDrone("", h.Name, h.Host, DateTime.MinValue)).ToList();
        if (!string.IsNullOrEmpty(lastHost))
        {
            outList.RemoveAll(k => k.LastIp == lastHost);
            var name = hosts.FirstOrDefault(h => h.Host == lastHost).Name ?? lastHost;
            outList.Insert(0, new KnownDrone("", name, lastHost, nowUtc));
        }
        return outList;
    }

    /// <summary>Where the drone is now: the address DNS-SD reports for its id, else its last address.</summary>
    public static string CurrentIp(KnownDrone drone, IEnumerable<(string Ip, string? DroneId)> found)
    {
        if (drone.Verified)
            foreach (var f in found)
                if (string.Equals(f.DroneId, drone.DroneId, StringComparison.OrdinalIgnoreCase)) return f.Ip;
        return drone.LastIp;
    }
}

public enum Liveness { Live, Unsure, Gone }

/// <summary>A found row is re-probed (TCP :9090) every PeriodSeconds. One miss greys it,
/// GoneAfter misses in a row remove it; a DNS-SD "removed" waits LostGraceSeconds.</summary>
public static class LivenessRule
{
    public const double PeriodSeconds = 10;
    public const int GoneAfter = 3;
    public const double LostGraceSeconds = 8;

    public static Liveness Of(int misses) =>
        misses <= 0 ? Liveness.Live : misses < GoneAfter ? Liveness.Unsure : Liveness.Gone;
}

/// <summary>A subnet-scan host with TCP 9090 open is a drone only when the drone's REST API
/// or metrics answer like a drone.</summary>
public readonly record struct DeviceKind(bool IsDrone, string? DroneId = null, string? Name = null)
{
    /// <param name="wifiStatus">JSON of GET :8765/api/wifi/status (null: no answer or not JSON).</param>
    /// <param name="metrics">JSON of GET :8888/.</param>
    public static DeviceKind Classify(JsonElement? wifiStatus, JsonElement? metrics)
    {
        if (wifiStatus is { ValueKind: JsonValueKind.Object } s &&
            s.TryGetProperty("mode", out var mode) && mode.ValueKind == JsonValueKind.String)
        {
            var id = s.TryGetProperty("id", out var i) && i.ValueKind == JsonValueKind.String && i.GetString() is { Length: > 0 } v
                ? v.ToUpperInvariant() : null;
            return new DeviceKind(true, id, id is null ? null : "Bumblebee-" + id);
        }
        if (metrics is { ValueKind: JsonValueKind.Object } m &&
            (m.TryGetProperty("cpu_pct", out _) || m.TryGetProperty("mem_total", out _)))
        {
            string? host = null;
            if (m.TryGetProperty("name", out var n) && n.ValueKind == JsonValueKind.String) host = n.GetString();
            else if (m.TryGetProperty("hostname", out var h) && h.ValueKind == JsonValueKind.String) host = h.GetString();
            return new DeviceKind(true, null, string.IsNullOrEmpty(host) ? null : host);
        }
        return new DeviceKind(false);
    }
}

public enum HotspotKind { Hidden, LostWifi, New }

/// <summary>A Bumblebee-XXXX network nearby; its suffix is the drone's id, so a known drone
/// that lost its classroom Wi-Fi is told apart from a new one.</summary>
public readonly record struct HotspotRow(HotspotKind Kind, string? Name = null)
{
    public static string? IdOf(string ssid)
    {
        if (!ssid.StartsWith("bumblebee-", StringComparison.OrdinalIgnoreCase)) return null;
        var rest = ssid["bumblebee-".Length..].ToUpperInvariant();
        return rest.Length == 0 ? null : rest;
    }

    public static HotspotRow Of(string ssid, IEnumerable<KnownDrone> known, ISet<string> visibleIds)
    {
        if (IdOf(ssid) is not string id) return new(HotspotKind.New);
        if (visibleIds.Contains(id)) return new(HotspotKind.Hidden);
        var k = known.FirstOrDefault(d => d.DroneId == id);
        return k is not null ? new(HotspotKind.LostWifi, k.Name) : new(HotspotKind.New);
    }
}

public static class ManualAddress
{
    /// <summary>null when text is an IPv4 address or a host name, else why not.</summary>
    public static string? Problem(string text)
    {
        var t = text.Trim();
        if (t.Length == 0) return null;
        var parts = t.Split('.');
        if (parts.Length == 4 && parts.All(p => p.Length > 0 && p.All(char.IsAsciiDigit)))
            return parts.All(p => int.TryParse(p, out var n) && n <= 255) ? null : "Not a valid IP address.";
        if (t.All(c => char.IsAsciiLetterOrDigit(c) || c is '.' or '-') && t[0] is not ('.' or '-') && t.Any(char.IsAsciiLetter))
            return null;
        return "Type an IP address (e.g. 192.168.1.50) or a name like bumblebee-20ec.local.";
    }

    public static string NoAnswer(string host) =>
        $"No drone answers at {host} (port 9090). Check the address, or connect anyway if the drone is still starting.";
}

public static class ConnectIdentity
{
    public static string MismatchText(string expectedName, string foundId) =>
        $"At this address answers Bumblebee-{foundId}, not {expectedName}. " +
        "Its address may have changed: pick it again in the drone list.";
}

/// <summary>
/// The adapter whose /24 the subnet scan sweeps: one with a default gateway (the network the
/// PC is really on), never a virtual one (WSL2/Hyper-V vEthernet, VirtualBox, VMware), Wi-Fi
/// before Ethernet. Link-local addresses do not count.
/// </summary>
public static class ScanAdapter
{
    public sealed record Candidate(string Name, string Description, bool Wireless, bool HasGateway, string Ipv4);

    public static bool IsVirtual(Candidate c)
    {
        var s = (c.Name + " " + c.Description).ToLowerInvariant();
        return s.Contains("vethernet") || s.Contains("hyper-v") || s.Contains("virtualbox") ||
               s.Contains("vmware") || s.Contains("wsl") || s.Contains("virtual");
    }

    public static string? Prefix(IEnumerable<Candidate> candidates)
    {
        var best = candidates
            .Where(c => !c.Ipv4.StartsWith("169.254.", StringComparison.Ordinal) && !IsVirtual(c))
            .OrderBy(c => c.HasGateway ? 0 : 1)
            .ThenBy(c => c.Wireless ? 0 : 1)
            .FirstOrDefault();
        if (best is null) return null;
        var o = best.Ipv4.Split('.');
        return o.Length == 4 ? $"{o[0]}.{o[1]}.{o[2]}." : null;
    }
}

/// <summary>
/// The window's size in physical pixels: the wanted size (in DIPs) times the display scale, but
/// never more than 95 % of the work area (screen without the taskbar), and a minimum size that
/// fits it too. At 150 % on 1920x1080, 1280x820 DIPs used to be 1920x1230 px: taller than the screen.
/// </summary>
public static class WindowFit
{
    public static (int Width, int Height, int MinWidth, int MinHeight) Size(
        double wantW, double wantH, double minW, double minH, double scale, int workW, int workH)
    {
        int Fit(double dips, int work, double share) => (int)Math.Min(dips * scale, work * share);
        return (Fit(wantW, workW, 0.95), Fit(wantH, workH, 0.95), Fit(minW, workW, 0.95), Fit(minH, workH, 0.95));
    }
}
