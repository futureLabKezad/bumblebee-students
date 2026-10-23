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
using BumblebeeGcs.Models;
using Microsoft.UI.Dispatching;

namespace BumblebeeGcs.Services;

/// <summary>Опрашивает системные метрики дрона (http://host:8888/) каждые 2 с.
/// Ошибка запроса не стирает прошлые значения: панель сереет по LastArrival (6 с).</summary>
public sealed class MetricsClient
{
    public SystemMetrics Metrics;
    /// <summary>Monotonic time of the last good answer; null = none from this drone yet.</summary>
    public double? LastArrival { get; private set; }
    public event Action? Updated;

    private static readonly HttpClient Http = new(new SocketsHttpHandler { UseProxy = false })   // мимо прокси
    {
        Timeout = TimeSpan.FromSeconds(2),
    };

    private readonly DispatcherQueue _dq;
    private DispatcherQueueTimer? _timer;
    private string _host = "";
    /// <summary>A late answer of an earlier Start (another drone) is dropped on the UI thread.</summary>
    private readonly ConnectionGeneration _generation = new();

    public MetricsClient(DispatcherQueue dq) => _dq = dq;

    /// <summary>Call on the UI thread. A different host starts from empty metrics.</summary>
    public void Start(string host)
    {
        Stop();
        if (host != _host) Clear();
        _host = host;
        var gen = _generation.Current;
        _ = FetchAsync(host, gen);
        var t = _dq.CreateTimer();
        t.Interval = TimeSpan.FromSeconds(2);
        t.Tick += (_, _) => _ = FetchAsync(host, gen);
        t.Start();
        _timer = t;
    }

    public void Stop()
    {
        _timer?.Stop();
        _timer = null;
        _generation.Advance();
    }

    /// <summary>Forget the previous drone's metrics ("—" until the new one answers).</summary>
    public void Clear()
    {
        Metrics = default;
        LastArrival = null;
        Updated?.Invoke();
    }

    private async Task FetchAsync(string host, int gen)
    {
        JsonDocument doc;
        try
        {
            var data = await Http.GetByteArrayAsync($"http://{host}:8888/");
            doc = JsonDocument.Parse(data);
        }
        catch { return; }

        using (doc)
        {
            var o = doc.RootElement;
            if (o.ValueKind != JsonValueKind.Object) return;
            var m = new SystemMetrics
            {
                CpuTemp = Num(o, "cpu_temp"),
                CpuPct = Num(o, "cpu_pct"),
                Load1 = Num(o, "load1"),
                Load5 = Num(o, "load5"),
                Load15 = Num(o, "load15"),
                CpuCount = (int?)Num(o, "cpu_count"),
                MemUsed = (int?)Num(o, "mem_used"),
                MemTotal = (int?)Num(o, "mem_total"),
                MemPct = Num(o, "mem_pct"),
            };
            _dq.TryEnqueue(() =>
            {
                if (_host != host || !_generation.IsCurrent(gen)) return;
                Metrics = m;
                LastArrival = MonoClock.Now;
                Updated?.Invoke();
            });
        }
    }

    static double? Num(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;
}
