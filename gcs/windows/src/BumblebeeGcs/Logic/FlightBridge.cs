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

using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace BumblebeeGcs.Logic;

/// <summary>HTTP status (0 = no answer from the drone) and the JSON body of a mission-server reply.</summary>
public readonly record struct MissionReply(int Code, string Json);

/// <summary>
/// The six commands of the drone's mission server (bb_mission, port 8766). The app still
/// never arms, changes modes, sends setpoints or writes PX4 parameters: these ask the
/// drone's guarded runner, which checks everything again on the drone. Every call names
/// the drone: a takeoff asked about one drone is never sent to another.
/// </summary>
public interface IMissionApi
{
    Task<MissionReply> MapStatusAsync(string host);
    Task<MissionReply> PutMapAsync(string host, JsonElement map);
    Task<MissionReply> CheckAsync(string host, string program);
    /// <param name="mapSha">The map the person saw in «Взлёт?»: the drone refuses another one.</param>
    Task<MissionReply> StartAsync(string host, string program, string token, string mapSha, bool battery, bool rc, bool people);
    Task<MissionReply> StopAsync(string host);
    Task<MissionReply> StatusAsync(string host, long since);
}

/// <summary>What the app's own «Взлёт?» dialog shows: the map the DRONE has, not what the page says.</summary>
public sealed record TakeoffRequest(string Host, string MapName, string MapSha, int MarkerCount, int ProgramLines, string ProgramSha);

/// <summary>The answer to «Взлёт?»: yes; no (the window was shown and declined, or nobody
/// answered); or not asked at all (hidden section, another drone, an open question of the
/// app) -- then <see cref="Why"/> tells the page the reason.</summary>
public readonly record struct TakeoffAnswer(bool Yes, bool Asked, string Why)
{
    public static readonly TakeoffAnswer Go = new(true, true, "");
    public static TakeoffAnswer Declined(string why = "takeoff cancelled in the app’s window") => new(false, true, why);
    public static TakeoffAnswer NotAsked(string why) => new(false, false, why);
}

/// <summary>The text of «Взлёт?». Names are someone's free text: they come last and cleaned.</summary>
public static class TakeoffText
{
    public const int MaxNameChars = 32;

    /// <summary>The first 12 hex digits of a hash (anything else in it is dropped).</summary>
    public static string Short(string sha) => new(sha.Where(Uri.IsHexDigit).Take(12).ToArray());

    /// <summary>Letters, digits, space, '_', '-', '.', 32 at most: a name cannot imitate the lines above it.</summary>
    public static string SafeName(string name)
    {
        var sb = new StringBuilder();
        foreach (var ch in name)
        {
            if (sb.Length >= MaxNameChars) break;
            if (char.IsLetterOrDigit(ch) || ch is ' ' or '_' or '-' or '.') sb.Append(ch);
        }
        var text = sb.ToString().Trim();
        return text.Length == 0 ? "(no name)" : text;
    }

    public static string Body(TakeoffRequest r, string droneName, string link)
    {
        var who = string.IsNullOrEmpty(droneName) || droneName == r.Host ? r.Host : $"{SafeName(droneName)} ({r.Host})";
        return $"Drone {who} will arm the motors and fly the program.\n"
             + $"Program: {r.ProgramLines} lines, sha {Short(r.ProgramSha)}.\n"
             + $"Map on the drone: {r.MarkerCount} markers, sha {Short(r.MapSha)}.\n"
             + $"Map name: {SafeName(r.MapName)}\n"
             + $"Telemetry: {link}\n\n"
             + "RC in hand: CH8 stops. People are away from the field.";
    }
}

/// <summary>At most so many messages and characters per second; what is over is dropped unparsed.</summary>
public sealed class MessageBudget
{
    private readonly int _maxMessages, _maxChars;
    private readonly Func<long> _nowMs;
    private long _windowStart = long.MinValue;
    private int _messages;
    private long _chars;

    public MessageBudget(int maxMessages, int maxChars, Func<long> nowMs)
    {
        _maxMessages = maxMessages;
        _maxChars = maxChars;
        _nowMs = nowMs;
    }

    public bool Allow(int chars)
    {
        var now = _nowMs();
        if (_windowStart == long.MinValue || now - _windowStart >= 1000 || now < _windowStart)
        {
            _windowStart = now;
            _messages = 0;
            _chars = 0;
        }
        if (_messages >= _maxMessages || _chars + chars > _maxChars) return false;
        _messages++;
        _chars += chars;
        return true;
    }
}

/// <summary>
/// Between the «Полёт» web page (gcs/web, inside WebView2) and the drone. The page has no
/// network to the drone (its Content-Security-Policy); it posts messages
/// {bb: 1, id, cmd, body, since} and gets {bb: 1, id, code, data} back. Only the commands
/// below exist. The page is not trusted (it runs a student's Python and loads students' maps):
///   * a takeoff needs a permission this bridge itself saw in the drone's reply to a check
///     of this very program, the three check marks, no mission running, and a click in the
///     app's own dialog (confirmTakeoff), which page code cannot press; one permission opens
///     the dialog once, and after «Отмена» there is a pause;
///   * while the dialog is open the map and the program on the drone cannot be changed from
///     here, and the drone is told which map the person saw;
///   * messages are limited per second and one request of a kind runs at a time;
///   * Stop needs nothing and is never dropped.
/// Not thread-safe: call it from one thread (the UI thread). No UI types here: unit-tested
/// in tests/BumblebeeGcs.Logic.Tests/FlightBridgeTests.cs.
/// </summary>
public sealed class FlightBridge
{
    public const int MaxMessageChars = 400_000;
    public const int MaxProgramChars = 100_000;      // the mission server's own limit
    public const int MaxMessagesPerSecond = 20;
    public const int MaxCharsPerSecond = 1_000_000;
    public const int PermissionSeconds = 120;        // the drone's own life of a start token
    public const int CancelPauseSeconds = 5;

    private sealed record Permission(string Token, string Host, string ProgramSha, string MapSha, long UntilMs);

    private readonly IMissionApi _api;
    private readonly Func<TakeoffRequest, Task<TakeoffAnswer>> _confirmTakeoff;
    private readonly Func<(string Host, string Name)> _drone;
    private readonly Func<long> _nowMs;
    private readonly MessageBudget _budget;
    private readonly HashSet<string> _inFlight = new();
    private Task<MissionReply>? _stop;
    private Permission? _permission;
    private bool _starting;
    private long _noDialogUntilMs = long.MinValue;
    private long _stops;                             // every Stop asked here or by the app's own button
    private long _floodStopAtMs = long.MinValue;

    /// <summary>A mission this app started (or saw in a status reply) is running on the drone.</summary>
    public bool MissionActive { get; private set; }
    public event Action? MissionActiveChanged;

    /// <summary>«Взлететь» was clicked and the start request is on its way to the drone.</summary>
    public bool TakeoffInFlight { get; private set; }
    public event Action? TakeoffInFlightChanged;

    /// <summary>The app's own STOP FLIGHT button tells the bridge: a start that is still on its
    /// way must not win the race (the bridge stops again once that start is settled).</summary>
    public void NoteStop() => _stops++;

    public FlightBridge(IMissionApi api, Func<TakeoffRequest, Task<TakeoffAnswer>> confirmTakeoff,
                        Func<(string Host, string Name)> drone, Func<long>? nowMs = null)
    {
        _api = api;
        _confirmTakeoff = confirmTakeoff;
        _drone = drone;
        _nowMs = nowMs ?? (() => Environment.TickCount64);
        _budget = new MessageBudget(MaxMessagesPerSecond, MaxCharsPerSecond, _nowMs);
    }

    /// <summary>One message from the page (JSON text) -> the reply for the page (JSON text);
    /// null when the message is not for the bridge or is over the budget (no reply is sent).</summary>
    public async Task<string?> HandleAsync(string message)
    {
        if (message.Length > MaxMessageChars) return null;
        if (!_budget.Allow(message.Length))
        {
            // Over the budget nothing is parsed and nothing is answered -- but a Stop is never
            // lost: what looks like one still goes to the drone, once a second at most.
            if (message.Length <= 256 && message.Contains("\"mission_stop\"", StringComparison.Ordinal)) FloodStop();
            return null;
        }
        long id;
        string cmd;
        JsonElement root;
        try
        {
            using var doc = JsonDocument.Parse(message);
            root = doc.RootElement.Clone();
            if (root.ValueKind != JsonValueKind.Object) return null;
            if (!root.TryGetProperty("bb", out var bb) || bb.ValueKind != JsonValueKind.Number
                || !bb.TryGetInt32(out var version) || version != 1) return null;
            if (!root.TryGetProperty("id", out var idEl) || idEl.ValueKind != JsonValueKind.Number
                || !idEl.TryGetInt64(out id)) return null;
            if (!root.TryGetProperty("cmd", out var cmdEl) || cmdEl.ValueKind != JsonValueKind.String) return null;
            cmd = cmdEl.GetString() ?? "";
        }
        catch (Exception) { return null; }       // not JSON, or a broken \uXXXX pair in a string

        MissionReply reply;
        try { reply = await DispatchAsync(cmd, root); }
        catch (Exception ex) { reply = Problem("app error: " + ex.GetType().Name, "app_error"); }
        return Compose(id, reply);
    }

    private async Task<MissionReply> DispatchAsync(string cmd, JsonElement root)
    {
        var body = root.TryGetProperty("body", out var b) && b.ValueKind == JsonValueKind.Object ? b : default;
        var (host, name) = _drone();
        switch (cmd)
        {
            case "hello":
                return new MissionReply(200, JsonSerializer.Serialize(new { host, name, connected = !string.IsNullOrEmpty(host) }));
            case "mission_stop":
                return await StopAsync(host);            // always, with no checks
            case "map_status" or "map_put" or "mission_check" or "mission_start" or "mission_status":
                break;
            default:
                return Problem("unknown command", "bad_request");
        }
        if (_starting && cmd == "mission_start") return Problem("a takeoff is already being confirmed in the app’s window", "busy");
        if (_starting && cmd is "map_put" or "mission_check")
            return Problem("the “Take off?” window is open: the map and the program cannot be changed now", "busy");
        if (!_inFlight.Add(cmd)) return Problem("the app is still waiting for the drone’s answer to the same command", "busy");
        try
        {
            switch (cmd)
            {
                case "map_status":
                    return await _api.MapStatusAsync(host);
                case "map_put":
                    if (body.ValueKind != JsonValueKind.Object || !body.TryGetProperty("map", out var map)
                        || map.ValueKind != JsonValueKind.Object)
                        return Problem("no map in the request", "bad_request");
                    return await _api.PutMapAsync(host, map);
                case "mission_check":
                {
                    if (ProgramOf(body, out var program) is { } bad) return bad;
                    _permission = null;                   // a new check replaces the old permission
                    var reply = await _api.CheckAsync(host, program);
                    _permission = PermissionOf(reply, host, program);
                    return reply;
                }
                case "mission_start":
                    return await StartAsync(body, host);
                default:                                  // mission_status
                {
                    long since = 0;
                    if (root.TryGetProperty("since", out var s) && s.ValueKind == JsonValueKind.Number) s.TryGetInt64(out since);
                    var reply = await _api.StatusAsync(host, Math.Max(0, since));
                    if (reply.Code == 200 && Running(reply.Json) is bool running) SetActive(running);
                    return reply;
                }
            }
        }
        finally { _inFlight.Remove(cmd); }
    }

    /// <summary>Stops asked at the same time share one request to the drone.</summary>
    private async Task<MissionReply> StopAsync(string host)
    {
        NoteStop();
        if (_stop is { } running) return await running;
        var mine = _api.StopAsync(host);
        _stop = mine;
        try { return await mine; }
        finally { _stop = null; }
    }

    /// <summary>A Stop among messages over the budget: sent without parsing and without a reply.</summary>
    private void FloodStop()
    {
        var now = _nowMs();
        if (_stop is not null || (_floodStopAtMs != long.MinValue && now >= _floodStopAtMs && now - _floodStopAtMs < 1000)) return;
        _floodStopAtMs = now;
        _ = StopQuietlyAsync(_drone().Host);
    }

    private async Task StopQuietlyAsync(string host)
    {
        try { await StopAsync(host); }
        catch (Exception) { }                    // nobody waits for this one
    }

    private async Task<MissionReply> StartAsync(JsonElement body, string host)
    {
        if (ProgramOf(body, out var program) is { } bad) return bad;
        var token = body.TryGetProperty("token", out var t) && t.ValueKind == JsonValueKind.String ? t.GetString() ?? "" : "";
        if (!IsToken(token)) return NoPermission();
        var confirm = body.TryGetProperty("confirm", out var c) && c.ValueKind == JsonValueKind.Object ? c : default;
        bool battery = Flag(confirm, "battery_multimeter"), rc = Flag(confirm, "rc_in_hand_ch8"), people = Flag(confirm, "people_clear");
        if (!(battery && rc && people))
            return Problem("tick the three items: battery, RC and CH8, people away", "not_confirmed");
        var now = _nowMs();
        if (now < _noDialogUntilMs)
        {
            _permission = null;                  // the page spent its permission on this try as well
            return Problem($"the takeoff was just cancelled: wait {CancelPauseSeconds} s and check the program on the drone again", "cancelled");
        }
        // Only a permission this bridge saw the drone give, for this program, on this drone -- and only once.
        var permission = _permission;
        if (permission is null || permission.Token != token || permission.Host != host || now > permission.UntilMs)
            return NoPermission();
        var programSha = Sha256Hex(program);
        if (permission.ProgramSha != programSha)
            return Problem("the program changed after the check: check it on the drone again", "changed");
        _permission = null;
        _starting = true;
        // From here a Stop (the page's or the app's own button) cancels this takeoff, wherever
        // it catches it: before the window is answered, or crossing the start request on the network.
        var stopsBefore = _stops;
        try
        {
            // What the person is asked about is what the DRONE reports, not what the page claims.
            var status = await _api.StatusAsync(host, int.MaxValue);
            if (status.Code != 200) return status;
            string mapName = "", sha = "";
            int n = 0;
            bool confirmed = false, running = true;
            try
            {
                using var doc = JsonDocument.Parse(status.Json);
                var r = doc.RootElement;
                running = !(r.TryGetProperty("running", out var run) && run.ValueKind == JsonValueKind.False);
                if (r.TryGetProperty("map", out var m) && m.ValueKind == JsonValueKind.Object)
                {
                    confirmed = m.TryGetProperty("confirmed", out var cf) && cf.ValueKind == JsonValueKind.True;
                    if (m.TryGetProperty("active", out var a) && a.ValueKind == JsonValueKind.Object)
                    {
                        mapName = a.TryGetProperty("name", out var an) && an.ValueKind == JsonValueKind.String ? an.GetString() ?? "" : "";
                        sha = a.TryGetProperty("sha", out var ash) && ash.ValueKind == JsonValueKind.String ? ash.GetString() ?? "" : "";
                        if (a.TryGetProperty("n", out var cnt) && cnt.ValueKind == JsonValueKind.Number) cnt.TryGetInt32(out n);
                    }
                }
            }
            catch (JsonException) { return Problem("the drone sent an unclear answer about the mission and the map", "bad_reply"); }
            if (running) return Problem("a mission is already running on the drone: STOP first", "busy");
            if (!confirmed || sha.Length == 0)
                return Problem("the map on the drone is not confirmed by the detector: first “Send the map to the drone”", "map_not_confirmed");
            if (sha != permission.MapSha)
                return Problem("the map on the drone changed after the check: check the program on the drone again", "changed");
            var lines = program.Count(ch => ch == '\n') + 1;
            var answer = await _confirmTakeoff(new TakeoffRequest(host, mapName, sha, n, lines, programSha));
            if (!answer.Yes)
            {
                // the pause follows a window that was shown; without a window the page gets the reason
                if (answer.Asked) _noDialogUntilMs = _nowMs() + CancelPauseSeconds * 1000L;
                return Problem(string.IsNullOrEmpty(answer.Why) ? "takeoff cancelled in the app’s window" : answer.Why,
                               answer.Asked ? "cancelled" : "not_asked");
            }
            if (_drone().Host != host) return Problem("the app is now connected to another drone: no takeoff", "cancelled");
            if (_stops != stopsBefore) return Problem("STOP was pressed while the “Take off?” window was open: no takeoff", "stopped");
            MissionReply reply;
            SetTakeoffInFlight(true);
            try { reply = await _api.StartAsync(host, program, token, sha, battery, rc, people); }
            finally { SetTakeoffInFlight(false); }
            if (reply.Code == 0)
            {
                // No answer: the drone may have started all the same.
                var stopped = await _api.StopAsync(host);
                return Problem("the drone did not answer the start command. " + StopSaid(stopped, "STOP sent to be safe"), "no_answer");
            }
            if (reply.Code != 200) return reply;
            SetActive(true);
            if (_stops != stopsBefore)
            {
                var stopped = await _api.StopAsync(host);
                return Problem("STOP was pressed while the start was on its way to the drone. " + StopSaid(stopped, "Mission stopped"), "stopped");
            }
            if (Text(reply.Json, "map_sha") is { } flown && flown != sha)
            {
                var stopped = await _api.StopAsync(host);
                return Problem("the drone started the mission with another map than the one in the “Take off?” window. " + StopSaid(stopped, "STOP sent"), "map_mismatch");
            }
            return reply;
        }
        finally { _starting = false; }
    }

    /// <summary>What to tell the person about a Stop the bridge sent by itself.</summary>
    private static string StopSaid(MissionReply stop, string done) =>
        stop.Code == 200 ? done + "." : "STOP did NOT reach the drone: stop with the RC (CH8).";

    private void SetTakeoffInFlight(bool value)
    {
        if (TakeoffInFlight == value) return;
        TakeoffInFlight = value;
        TakeoffInFlightChanged?.Invoke();
    }

    private void SetActive(bool active)
    {
        if (MissionActive == active) return;
        MissionActive = active;
        MissionActiveChanged?.Invoke();
    }

    private static bool IsToken(string token) => token.Length is >= 8 and <= 128 && token.All(Uri.IsHexDigit);

    private static MissionReply NoPermission() =>
        Problem("no valid permission: press “Check the program on the drone” again", "bad_token");

    /// <summary>The permission in the drone's reply to a check (it gives one only for a clean program and a confirmed map).</summary>
    private Permission? PermissionOf(MissionReply reply, string host, string program)
    {
        if (reply.Code != 200) return null;
        try
        {
            using var doc = JsonDocument.Parse(reply.Json);
            var r = doc.RootElement;
            if (r.ValueKind != JsonValueKind.Object) return null;
            var token = r.TryGetProperty("token", out var t) && t.ValueKind == JsonValueKind.String ? t.GetString() ?? "" : "";
            var mapSha = r.TryGetProperty("map", out var m) && m.ValueKind == JsonValueKind.Object
                         && m.TryGetProperty("sha", out var s) && s.ValueKind == JsonValueKind.String ? s.GetString() ?? "" : "";
            if (!IsToken(token) || mapSha.Length == 0) return null;
            double life = PermissionSeconds;
            if (r.TryGetProperty("token_ttl_s", out var ttl) && ttl.ValueKind == JsonValueKind.Number && ttl.TryGetDouble(out var seconds))
                life = Math.Clamp(seconds, 0, PermissionSeconds);
            return new Permission(token, host, Sha256Hex(program), mapSha, _nowMs() + (long)(life * 1000));
        }
        catch (JsonException) { return null; }
    }

    private static bool? Running(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind == JsonValueKind.Object && doc.RootElement.TryGetProperty("running", out var r))
                return r.ValueKind == JsonValueKind.True ? true : r.ValueKind == JsonValueKind.False ? false : null;
        }
        catch (JsonException) { }
        return null;
    }

    private static string? Text(string json, string name)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.ValueKind == JsonValueKind.Object && doc.RootElement.TryGetProperty(name, out var v)
                && v.ValueKind == JsonValueKind.String)
                return v.GetString();
        }
        catch (JsonException) { }
        return null;
    }

    /// <summary>As the drone computes it: SHA-256 of the UTF-8 text, hex.</summary>
    public static string Sha256Hex(string text) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();

    /// <summary>The program text of a request, or the error reply.</summary>
    private static MissionReply? ProgramOf(JsonElement body, out string program)
    {
        program = "";
        if (body.ValueKind != JsonValueKind.Object || !body.TryGetProperty("program", out var p)
            || p.ValueKind != JsonValueKind.String)
            return Problem("no program in the request", "bad_request");
        program = p.GetString() ?? "";
        return program.Length > MaxProgramChars ? Problem("the program is too long", "bad_request") : null;
    }

    private static bool Flag(JsonElement obj, string name) =>
        obj.ValueKind == JsonValueKind.Object && obj.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.True;

    /// <summary>A reply made by the app itself (code 0: the drone was not asked or did not answer).</summary>
    public static MissionReply Problem(string text, string code) =>
        new(0, JsonSerializer.Serialize(new { error = text, code }));

    /// <summary>{bb, id, code, data}: data is the drone's JSON object as it came, or an error object.</summary>
    private static string Compose(long id, MissionReply reply)
    {
        using var stream = new MemoryStream();
        using (var w = new Utf8JsonWriter(stream))
        {
            w.WriteStartObject();
            w.WriteNumber("bb", 1);
            w.WriteNumber("id", id);
            w.WriteNumber("code", reply.Code);
            w.WritePropertyName("data");
            var written = false;
            try
            {
                using var doc = JsonDocument.Parse(reply.Json);
                if (doc.RootElement.ValueKind == JsonValueKind.Object) { doc.RootElement.WriteTo(w); written = true; }
            }
            catch (JsonException) { }
            if (!written)
            {
                w.WriteStartObject();
                w.WriteString("error", reply.Code == 0 ? "no answer from the drone" : "the drone sent an unclear answer");
                w.WriteEndObject();
            }
            w.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }
}
