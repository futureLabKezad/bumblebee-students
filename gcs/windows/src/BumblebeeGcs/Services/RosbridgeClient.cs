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

using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Models;

namespace BumblebeeGcs.Services;

/// <summary>
/// Минимальный rosbridge v2 клиент по WebSocket (ws://host:9090).
/// Подписывается на шесть топиков телеметрии и толкает распарсенные значения
/// в TelemetryStore на UI-потоке. Авто-реконнект при обрыве через 3 с.
/// GCS работает в режиме монитора — клиент никогда не публикует и не зовёт сервисы.
/// Тихий обрыв (дрон выключен, вне Wi-Fi): WebSocket ping каждые 2 с, без pong 4 с —
/// обрыв. Сокет, который отвечает на ping, но молчит (MAVROS стоит, FC отключён),
/// не рвётся: Link показывает «Telemetry frozen» / «FC not connected», как на Mac.
/// Без WinUI (UI-поток — IUiQueue), поэтому проверяется сокет-тестами на любой ОС.
/// </summary>
public sealed class RosbridgeClient
{
    public static readonly TimeSpan KeepAliveInterval = TimeSpan.FromSeconds(2);
    public static readonly TimeSpan KeepAliveTimeout = TimeSpan.FromSeconds(4);
    public const int ReconnectDelayMs = 3000;

    private readonly TelemetryStore _store;
    private readonly IUiQueue _dq;
    private readonly int _port;
    private ClientWebSocket? _ws;
    private string _host = "";
    private volatile bool _active;
    /// <summary>Advanced on every Connect/Disconnect (UI thread). Everything a socket task
    /// hands to the UI thread carries its generation and is dropped if it is not current.</summary>
    private readonly ConnectionGeneration _generation = new();

    /// <summary>ThrottleMs: rosbridge шлёт не чаще раза за интервал (0 = всё),
    /// оставляя самое свежее. Подключённый контроллер шлёт позу и скорость
    /// 30 Гц, IMU 50 Гц; экрану нужно меньше, и rosbridge (Python) с WiFi
    /// несут ~40 сообщений/с вместо ~115.</summary>
    private readonly record struct Sub(string Topic, string Type, int ThrottleMs);
    private static readonly Sub[] Subs =
    {
        new("/mavros/state",                "mavros_msgs/msg/State",          0),
        new("/mavros/statustext/recv",      "mavros_msgs/msg/StatusText",     0),
        new("/mavros/battery",              "sensor_msgs/msg/BatteryState",   1000),
        new("/mavros/mavros/pose",          "geometry_msgs/msg/PoseStamped",  100),
        new("/mavros/mavros/velocity_local","geometry_msgs/msg/TwistStamped", 100),
        new("/mavros/mavros/data",          "sensor_msgs/msg/Imu",            50),
    };

    /// <param name="port">9090 on every drone; tests point it at a local fake rosbridge.</param>
    public RosbridgeClient(TelemetryStore store, IUiQueue ui, int port = 9090)
    {
        _store = store;
        _dq = ui;
        _port = port;
    }

    /// <summary>Call on the UI thread.</summary>
    public void Connect(string host)
    {
        Disconnect();
        _host = host;
        _active = true;
        var gen = _generation.Advance();
        _ = OpenSocketAsync(gen);
    }

    /// <summary>Call on the UI thread.</summary>
    public void Disconnect()
    {
        _active = false;
        _generation.Advance();
        try { _ws?.Abort(); } catch { }
        _ws = null;
        OnUi(() => _store.ResetForReconnect(MonoClock.Now));
    }

    /// <summary>Run on the UI thread now (when already there) or enqueue.</summary>
    private void OnUi(Action a)
    {
        if (_dq.HasThreadAccess) a();
        else _dq.TryEnqueue(() => a());
    }

    /// <summary>Enqueue work of one socket generation; dropped if a newer connection started meanwhile.</summary>
    private void OnUiIfCurrent(int gen, Action a) =>
        _dq.TryEnqueue(() =>
        {
            if (_active && _generation.IsCurrent(gen)) a();
        });

    private async Task OpenSocketAsync(int gen)
    {
        if (!_active || !_generation.IsCurrent(gen)) return;
        var ws = new ClientWebSocket();
        // .NET 9+: a PING every 2 s; no PONG within 4 s aborts the socket (silent drop).
        ws.Options.KeepAliveInterval = KeepAliveInterval;
        ws.Options.KeepAliveTimeout = KeepAliveTimeout;
        ws.Options.Proxy = null;   // never through a system proxy: the drone is on the local network
        var host = _host;
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await ws.ConnectAsync(new Uri($"ws://{host}:{_port}"), cts.Token);
        }
        catch
        {
            ws.Dispose();
            HandleDrop(gen);
            return;
        }
        if (!_active || !_generation.IsCurrent(gen)) { ws.Abort(); ws.Dispose(); return; }
        _ws = ws;

        foreach (var s in Subs)
        {
            var msg = s.ThrottleMs > 0
                ? JsonSerializer.Serialize(new { op = "subscribe", topic = s.Topic, type = s.Type,
                                                 throttle_rate = s.ThrottleMs, queue_length = 1 })
                : JsonSerializer.Serialize(new { op = "subscribe", topic = s.Topic, type = s.Type });
            try
            {
                await ws.SendAsync(Encoding.UTF8.GetBytes(msg), WebSocketMessageType.Text, true, CancellationToken.None);
            }
            catch { ws.Dispose(); HandleDrop(gen); return; }
        }

        // Socket open; the Link tile stays "No drone · waiting for FC data" until the first /mavros/state.
        OnUiIfCurrent(gen, () => _store.SocketOpened(host, MonoClock.Now));

        await ReceiveLoopAsync(ws, gen);
        ws.Dispose();
    }

    private async Task ReceiveLoopAsync(ClientWebSocket ws, int gen)
    {
        var chunk = new byte[64 * 1024];
        var message = new MemoryStream();
        // No silence watchdog: a drone that stops publishing but still answers pings is
        // "Telemetry frozen" on the open socket (reconnecting would only flip it to "No drone").
        // A dead link fails the receive through the keep-alive timeout.
        while (_active && _generation.IsCurrent(gen))
        {
            WebSocketReceiveResult result;
            try
            {
                result = await ws.ReceiveAsync(chunk, CancellationToken.None);
            }
            catch
            {
                try { ws.Abort(); } catch { }
                HandleDrop(gen);
                return;
            }
            if (result.MessageType == WebSocketMessageType.Close) { HandleDrop(gen); return; }
            message.Write(chunk, 0, result.Count);
            if (!result.EndOfMessage) continue;
            HandleText(Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length), gen);
            message.SetLength(0);
        }
    }

    private void HandleDrop(int gen)
    {
        if (!_active || !_generation.IsCurrent(gen)) return;
        // One collapsing log line ("rosbridge lost — reconnecting… · attempt N"), not a line per attempt.
        OnUiIfCurrent(gen, () => _store.SocketLost(MonoClock.Now));
        // Реконнект через 3 с (совпадает с поведением веба/мака).
        _ = Task.Delay(ReconnectDelayMs).ContinueWith(_ =>
        {
            if (_active && _generation.IsCurrent(gen)) _ = OpenSocketAsync(gen);
        });
    }

    // MARK: - Message parsing

    private void HandleText(string text, int gen)
    {
        // Bare NaN from Python's json is accepted; msg is a clone, safe for the UI thread.
        if (!RosMessages.TryParsePublish(text, out var topic, out var msg)) return;
        // The generation is checked again on the UI thread: a message of the previous
        // drone that was already queued when the user switched must not reach the screen.
        OnUiIfCurrent(gen, () =>
        {
            if (RosMessages.Apply(_store, topic, msg, MonoClock.Now)) _store.NotifyUpdated();
        });
    }
}
