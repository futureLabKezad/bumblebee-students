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
    /// <summary>Id of the drone this session talks to (last 4 hex digits of its MAC, as in DNS-SD
    /// TXT and /api/wifi/status); null until known or on drone software without one. Settings
    /// refuses changes when another id answers.</summary>
    public string? DroneId { get; set; }

    /// <summary>An animation or show this session started and has not stopped since. Disconnect,
    /// another drone and closing the app stop it (best effort); the drone itself stops every
    /// animation after 2 minutes anyway.</summary>
    public bool StartedLedAnimation { get; set; }

    /// <summary>Stops the animation this session started on the current drone.</summary>
    /// <param name="waitMs">Wait this long for the reply (the app is closing); 0 = do not wait.</param>
    public void StopOwnLedAnimation(int waitMs = 0)
    {
        if (!StartedLedAnimation || DroneHost.Length == 0) return;
        StartedLedAnimation = false;
        var api = new DroneApi { Host = DroneHost };
        var reset = Task.Run(async () => { try { await api.LedResetAsync(); } catch { } });
        if (waitMs > 0) reset.Wait(waitMs);
    }

    /// <summary>The drone's name for confirmations and messages.</summary>
    public string DroneName
    {
        get
        {
            var n = Scanner.Found.FirstOrDefault(d => d.Ip == DroneHost)?.Name;
            if (!string.IsNullOrEmpty(n) && n != DroneHost) return n;
            return string.IsNullOrEmpty(DroneId) ? DroneHost : "Bumblebee-" + DroneId;
        }
    }
    /// <summary>Drones this PC connected to, most recent first (Logic/DiscoveryLogic.cs).</summary>
    public IReadOnlyList<KnownDrone> KnownDrones => _settings.Fleet;
    /// <summary>The last drone, for the connect screen's first card.</summary>
    public KnownDrone? LastDrone => _settings.Fleet.FirstOrDefault();
    /// <summary>Set when the drone answering at the address is not the one picked.</summary>
    public string? IdentityMismatch { get; set; }

    public event Action? ConnectedChanged;
    /// <summary>Reconnect (Ctrl+R) was pressed: cameras reopen their streams too.</summary>
    public event Action? Reconnected;
    /// <summary>The fleet changed (remembered or forgotten drone).</summary>
    public event Action? FleetChanged;
    /// <summary>IdentityMismatch was set: the shell asks whether to stay connected.</summary>
    public event Action? IdentityMismatchFound;

    private readonly AppSettings _settings = AppSettings.Load();
    private readonly DispatcherQueue _dq;
    /// <summary>Re-evaluates link/armed/alarms twice a second: staleness needs no message.</summary>
    private readonly DispatcherQueueTimer _monitor;

    public AppState(DispatcherQueue dq)
    {
        _dq = dq;
        if (_settings.MigrateFleet()) _settings.Save();
        Scanner = new DroneScanner(dq);
        Metrics = new MetricsClient(dq);
        Handoff = new WifiHandoff(dq, _settings);
        Ros = new RosbridgeClient(Telemetry, new DispatcherUiQueue(dq));

        Telemetry.AlarmRaised += AlertSound.Play;
        // A drone is remembered only once it answered: a mistyped address or a device that
        // is not a drone never becomes the "last drone".
        Telemetry.ConnectionChanged += () => { if (Telemetry.RosConnected) RememberCurrent(); };
        _monitor = dq.CreateTimer();
        _monitor.Interval = TimeSpan.FromMilliseconds(500);
        _monitor.Tick += (_, _) => Telemetry.Evaluate(MonoClock.Now);
        _monitor.Start();
    }

    /// <param name="expectedId">The id of the drone picked (Last drone card, a DNS-SD row);
    /// the id answering at ip is checked against it.</param>
    public void Connect(string ip, string? expectedId = null)
    {
        ip = ip.Trim();
        if (ip.Length == 0) return;
        // Другой дрон: трек, графики, журнал, поза, батарея, режим, armed и метрики
        // прошлого не должны остаться на экране. Тот же дрон — журнал сохраняется.
        if (ip != DroneHost)
        {
            StopOwnLedAnimation();
            Telemetry.ResetAll(MonoClock.Now);
            Metrics.Clear();
            DroneId = null;
        }
        IdentityMismatch = null;
        DroneHost = ip;
        Api.Host = ip;
        Ros.Connect(ip);
        Metrics.Start(ip);
        Connected = true;
        KeepAwake.Begin();
        ConnectedChanged?.Invoke();
        _ = CheckIdentityAsync(ip, expectedId);
    }

    /// <summary>Reads the id answering at host; remembers the drone when it answers.</summary>
    private async Task CheckIdentityAsync(string host, string? expectedId)
    {
        DroneApi.WifiStatus status;
        try { status = await Api.WifiStatusAsync(); }
        catch { return; }
        _dq.TryEnqueue(() =>
        {
            if (host != DroneHost || !Connected) return;
            if (status.Id is string id)
            {
                DroneId = id;
                if (!string.IsNullOrEmpty(expectedId) && !string.Equals(expectedId, id, StringComparison.OrdinalIgnoreCase))
                {
                    var name = _settings.Fleet.FirstOrDefault(k => k.DroneId == expectedId.ToUpperInvariant())?.Name
                               ?? "Bumblebee-" + expectedId;
                    IdentityMismatch = ConnectIdentity.MismatchText(name, id);
                    IdentityMismatchFound?.Invoke();
                    return;
                }
            }
            RememberCurrent();
        });
    }

    /// <summary>Upsert the current drone into the fleet (by id when known).</summary>
    private void RememberCurrent()
    {
        if (!Connected || DroneHost.Length == 0 || IdentityMismatch is not null) return;
        _settings.Fleet = KnownFleet.Upsert(_settings.Fleet, DroneId, DroneName, DroneHost, DateTime.UtcNow);
        _settings.Save();
        FleetChanged?.Invoke();
    }

    /// <summary>"Forget" on the connect screen.</summary>
    public void Forget(KnownDrone drone)
    {
        _settings.Fleet = KnownFleet.Forget(_settings.Fleet, drone.Key);
        _settings.Save();
        FleetChanged?.Invoke();
    }

    // MARK: - Diagnostics

    /// <summary>The "Copy diagnostics" report (Logic/Diagnostics.cs): no passwords.</summary>
    public async Task<string> DiagnosticsTextAsync()
    {
        var info = Connected ? await Api.InfoAsync() : null;
        Handoff.RefreshCurrentSsid();
        var t = Telemetry;
        var input = new DiagnosticsInput
        {
            NowUtc = DateTime.UtcNow,
            App = AppVersion.Label,
            Os = $"{System.Runtime.InteropServices.RuntimeInformation.OSDescription} " +
                 $"({System.Runtime.InteropServices.RuntimeInformation.OSArchitecture})",
            Connected = Connected,
            DroneHost = DroneHost,
            DroneName = DroneName,
            DroneId = DroneId,
            DroneSoftware = info?.Version,
            Link = LinkLogic.Text(t.Link),
            Armed = ArmedLogic.Display(t.Armed, t.LastKnownArmed).Value,
            Mode = ModeLogic.DisplayMode(t.Mode),
            Control = ModeLogic.ControllerText(t.InControl),
            Battery = t.Battery.Text,
            ComputerWifi = Handoff.CurrentSsid,
            OnDroneHotspot = Handoff.OnDroneHotspot,
            Found = Scanner.Drones.Select(d => new DiagnosticsInput.FoundDrone(d.Name, d.Ip, d.DroneId, d.Liveness == Liveness.Live)).ToList(),
            UnknownDevices = Scanner.UnknownDevices.Count(),
            Hotspots = Handoff.Hotspots.Select(h => h.Ssid).ToList(),
            RememberedDrones = _settings.Fleet.Select(k => new DiagnosticsInput.Remembered(k.Name, k.DroneId, k.LastIp)).ToList(),
            Messages = t.Messages.Entries.Select(e => $"{e.Time} {e.Text}").ToList(),
            LastCrash = CrashLog.Last(),
        };
        return Diagnostics.Report(input);
    }

    /// <summary>Puts the report on the clipboard; true when it is there.</summary>
    public async Task<bool> CopyDiagnosticsAsync()
    {
        var text = await DiagnosticsTextAsync();
        try
        {
            var data = new Windows.ApplicationModel.DataTransfer.DataPackage();
            data.SetText(text);
            Windows.ApplicationModel.DataTransfer.Clipboard.SetContent(data);
            Windows.ApplicationModel.DataTransfer.Clipboard.Flush();
            return true;
        }
        catch { return false; }
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
        StopOwnLedAnimation();
        Ros.Disconnect();
        Metrics.Stop();
        Connected = false;
        IdentityMismatch = null;
        KeepAwake.End();
        ConnectedChanged?.Invoke();
    }
}
