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
using BumblebeeGcs.Models;
using Microsoft.UI.Dispatching;

namespace BumblebeeGcs.Services;

/// <summary>Корневое состояние приложения — порт AppState из AppMain.swift.</summary>
public sealed class AppState
{
    public readonly DroneScanner Scanner;
    public readonly TelemetryStore Telemetry = new();
    public readonly MetricsClient Metrics;
    public readonly DroneApi Api = new();
    public readonly WifiHandoff Handoff;
    public readonly RosbridgeClient Ros;

    public string DroneHost { get; private set; } = "";
    public bool Connected { get; private set; }
    public string? LastHost => _settings.LastHost;
    public List<KnownDrone> KnownDrones => _settings.KnownDrones;

    public event Action? ConnectedChanged;
    /// <summary>Reconnect (Ctrl+R) was pressed: cameras reopen their streams too.</summary>
    public event Action? Reconnected;

    private readonly AppSettings _settings = AppSettings.Load();
    /// <summary>Re-evaluates link/armed/alarms twice a second: staleness needs no message.</summary>
    private readonly DispatcherQueueTimer _monitor;

    public AppState(DispatcherQueue dq)
    {
        Scanner = new DroneScanner(dq);
        Metrics = new MetricsClient(dq);
        Handoff = new WifiHandoff(dq, _settings);
        Ros = new RosbridgeClient(Telemetry, dq);

        Telemetry.AlarmRaised += AlertSound.Play;
        _monitor = dq.CreateTimer();
        _monitor.Interval = TimeSpan.FromMilliseconds(500);
        _monitor.Tick += (_, _) => Telemetry.Evaluate(MonoClock.Now);
        _monitor.Start();
    }

    public void Connect(string ip)
    {
        ip = ip.Trim();
        if (ip.Length == 0) return;
        // Другой дрон: трек, графики, журнал, поза, батарея, режим, armed и метрики
        // прошлого не должны остаться на экране. Тот же дрон — журнал сохраняется.
        if (ip != DroneHost)
        {
            Telemetry.ResetAll(MonoClock.Now);
            Metrics.Clear();
        }
        DroneHost = ip;
        Api.Host = ip;
        Ros.Connect(ip);
        Metrics.Start(ip);
        Connected = true;
        _settings.LastHost = ip;
        RememberDrone(ip);
        _settings.Save();
        KeepAwake.Begin();
        ConnectedChanged?.Invoke();
    }

    /// <summary>Upsert дрона во «флот», по хосту. Bonjour-имя приоритетнее.</summary>
    private void RememberDrone(string host)
    {
        var name = Scanner.Found.FirstOrDefault(d => d.Ip == host)?.Name ?? host;
        var existing = _settings.KnownDrones.FirstOrDefault(d => d.Host == host);
        if (existing is not null)
        {
            if (name != host) existing.Name = name;
        }
        else
        {
            _settings.KnownDrones.Add(new KnownDrone(host, name));
        }
    }

    public void Reconnect()
    {
        if (!Connected || DroneHost.Length == 0) return;
        Ros.Connect(DroneHost);
        Metrics.Start(DroneHost);
        Reconnected?.Invoke();
    }

    public void Disconnect()
    {
        Ros.Disconnect();
        Metrics.Stop();
        Connected = false;
        KeepAwake.End();
        ConnectedChanged?.Invoke();
    }
}
