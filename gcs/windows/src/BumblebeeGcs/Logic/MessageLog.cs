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

namespace BumblebeeGcs.Logic;

public enum LogKind { App, Fcu }

/// <summary>One line of the Messages panel. Seq orders lines across both rings.</summary>
public sealed record LogEntry(string Time, string Text, LogKind Kind, long Seq, string? Key = null);

/// <summary>
/// The Messages panel: PX4 statustext lines and app lines in separate rings, so a
/// reconnect storm or repeated app lines can never push out what PX4 said.
/// An app line with a key replaces the newest app line with the same key
/// (one line with a counter instead of a line per reconnect attempt).
/// </summary>
public sealed class MessageLog
{
    public const int AppMax = 20, FcuMax = 50;

    private readonly List<LogEntry> _app = new(), _fcu = new();   // newest first
    private long _seq;
    private List<LogEntry>? _merged;

    /// <summary>Changes on every add/replace/clear; the view redraws when it changes.</summary>
    public int Version { get; private set; }

    /// <summary>All lines, newest first.</summary>
    public IReadOnlyList<LogEntry> Entries => _merged ??= Merge();

    public void AddApp(string text, string time, string? key = null)
    {
        var e = new LogEntry(time, text, LogKind.App, ++_seq, key);
        if (key is not null && _app.Count > 0 && _app[0].Key == key)
            _app[0] = e;
        else
        {
            _app.Insert(0, e);
            if (_app.Count > AppMax) _app.RemoveRange(AppMax, _app.Count - AppMax);
        }
        Changed();
    }

    public void AddFcu(string text, string time)
    {
        _fcu.Insert(0, new LogEntry(time, "[FCU] " + text, LogKind.Fcu, ++_seq));
        if (_fcu.Count > FcuMax) _fcu.RemoveRange(FcuMax, _fcu.Count - FcuMax);
        Changed();
    }

    public void Clear()
    {
        _app.Clear();
        _fcu.Clear();
        Changed();
    }

    private void Changed()
    {
        _merged = null;
        Version++;
    }

    private List<LogEntry> Merge()
    {
        var all = new List<LogEntry>(_app.Count + _fcu.Count);
        int i = 0, j = 0;
        while (i < _app.Count || j < _fcu.Count)
        {
            if (j >= _fcu.Count || (i < _app.Count && _app[i].Seq > _fcu[j].Seq)) all.Add(_app[i++]);
            else all.Add(_fcu[j++]);
        }
        return all;
    }
}

/// <summary>
/// Texts for rosbridge connect/drop lines. The first connect is its own line; every
/// later drop, failed attempt and reconnect updates one "link" line with counters.
/// Call on the UI thread; Reset on a new session (connect or reconnect).
/// </summary>
public sealed class LinkLog
{
    public const string Key = "link";

    private bool _connected, _everConnected;
    private int _drops, _attempts;

    public (string Text, string? Key) Connected(string host)
    {
        _connected = true;
        _attempts = 0;
        if (!_everConnected || _drops == 0)
        {
            _everConnected = true;
            return ($"rosbridge connected ({host})", null);
        }
        return ($"rosbridge back ({host}) · lost {_drops}×", Key);
    }

    /// <summary>The socket dropped or a connect attempt failed (reason: see DropReason).</summary>
    public (string Text, string? Key) Failed(string? reason = null)
    {
        if (_connected)
        {
            _connected = false;
            _drops++;
            _attempts = 0;
        }
        _attempts++;
        var why = reason is null ? "" : $" ({reason})";
        var text = _everConnected ? $"rosbridge lost{why} — reconnecting…" : $"rosbridge not reachable{why} — retrying…";
        if (_drops > 1) text += $" · lost {_drops}×";
        if (_attempts > 1) text += $" · attempt {_attempts}";
        return (text, Key);
    }

    public void Reset()
    {
        _connected = _everConnected = false;
        _drops = _attempts = 0;
    }
}

/// <summary>
/// Why the rosbridge socket was given up, for the Messages panel and "Copy diagnostics":
/// a silent link (no pong), the drone closing it, or a network error (same texts as the Mac app).
/// </summary>
public static class DropReason
{
    public const string NoPong = "no answer to ping for 4 s";
    public const string ClosedByDrone = "closed by the drone";

    public static string Network(string? detail)
    {
        var d = (detail ?? "").Trim();
        return d.Length == 0 ? "network error" : $"network error: {d}";
    }

    /// <summary>
    /// A failed connect or receive: the keep-alive timeout (.NET aborts the socket when no pong
    /// came within KeepAliveTimeout and says so in the message) is a silent link, anything else
    /// a network error with the innermost message.
    /// </summary>
    public static string Of(Exception ex)
    {
        for (Exception? e = ex; e is not null; e = e.InnerException)
        {
            if (e.Message.Contains("Pong", StringComparison.OrdinalIgnoreCase)
                || e.Message.Contains("KeepAlive", StringComparison.OrdinalIgnoreCase))
                return NoPong;
        }
        var inner = ex;
        while (inner.InnerException is not null) inner = inner.InnerException;
        return Network(inner.Message);
    }
}
