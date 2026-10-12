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
using BumblebeeGcs.Models;
using Microsoft.UI.Dispatching;

namespace BumblebeeGcs.Services;

/// <summary>
/// Минимальный rosbridge v2 клиент по WebSocket (ws://host:9090).
/// Подписывается на шесть топиков телеметрии и толкает распарсенные значения
/// в TelemetryStore на UI-потоке. Авто-реконнект при обрыве через 3 с.
/// GCS работает в режиме монитора — клиент никогда не публикует и не зовёт сервисы.
/// </summary>
public sealed class RosbridgeClient
{
    private readonly TelemetryStore _store;
    private readonly DispatcherQueue _dq;
    private ClientWebSocket? _ws;
    private string _host = "";
    private bool _active;
    private int _generation;

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

    public RosbridgeClient(TelemetryStore store, DispatcherQueue dq)
    {
        _store = store;
        _dq = dq;
    }

    public void Connect(string host)
    {
        Disconnect();
        _host = host;
        _active = true;
        var gen = ++_generation;
        _ = OpenSocketAsync(gen);
    }

    public void Disconnect()
    {
        _active = false;
        _generation++;
        try { _ws?.Abort(); } catch { }
        _ws = null;
        _dq.TryEnqueue(_store.ResetForReconnect);
    }

    private async Task OpenSocketAsync(int gen)
    {
        if (!_active || gen != _generation) return;
        var ws = new ClientWebSocket();
        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await ws.ConnectAsync(new Uri($"ws://{_host}:9090"), cts.Token);
        }
        catch
        {
            ws.Dispose();
            HandleDrop(gen);
            return;
        }
        if (!_active || gen != _generation) { ws.Abort(); ws.Dispose(); return; }
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
            catch { HandleDrop(gen); return; }
        }

        _dq.TryEnqueue(() =>
        {
            _store.SetRosConnected(true);
            _store.Log($"rosbridge connected ({_host})");
            _store.NotifyUpdated();
        });

        await ReceiveLoopAsync(ws, gen);
    }

    private async Task ReceiveLoopAsync(ClientWebSocket ws, int gen)
    {
        var chunk = new byte[64 * 1024];
        var message = new MemoryStream();
        while (_active && gen == _generation)
        {
            WebSocketReceiveResult result;
            try { result = await ws.ReceiveAsync(chunk, CancellationToken.None); }
            catch { HandleDrop(gen); return; }
            if (result.MessageType == WebSocketMessageType.Close) { HandleDrop(gen); return; }
            message.Write(chunk, 0, result.Count);
            if (!result.EndOfMessage) continue;
            HandleText(Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length));
            message.SetLength(0);
        }
    }

    private void HandleDrop(int gen)
    {
        if (!_active || gen != _generation) return;
        _dq.TryEnqueue(() =>
        {
            _store.SetRosConnected(false);
            _store.Log("rosbridge lost — reconnecting…");
            _store.NotifyUpdated();
        });
        // Реконнект через 3 с (совпадает с поведением веба/мака).
        _ = Task.Delay(3000).ContinueWith(_ =>
        {
            if (_active && gen == _generation) _ = OpenSocketAsync(gen);
        });
    }

    // MARK: - Message parsing

    private void HandleText(string text)
    {
        JsonDocument doc;
        try { doc = JsonDocument.Parse(text); }
        catch { return; }
        using (doc)
        {
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object) return;
            if (!root.TryGetProperty("op", out var op) || op.GetString() != "publish") return;
            if (!root.TryGetProperty("topic", out var topicEl) || topicEl.GetString() is not string topic) return;
            if (!root.TryGetProperty("msg", out var msg) || msg.ValueKind != JsonValueKind.Object) return;
            // JsonElement живёт внутри документа — клонируем для перехода на UI-поток.
            var msgClone = msg.Clone();
            _dq.TryEnqueue(() => Apply(topic, msgClone));
        }
    }

    static double? Num(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;

    static JsonElement? Obj(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Object ? v : null;

    private void Apply(string topic, JsonElement msg)
    {
        switch (topic)
        {
            case "/mavros/state":
            {
                if (msg.TryGetProperty("mode", out var modeEl) && modeEl.GetString() is string mode && mode != _store.Mode)
                {
                    _store.Mode = mode;
                    _store.Log($"mode → {mode}");
                }
                if (msg.TryGetProperty("armed", out var armedEl) &&
                    armedEl.ValueKind is JsonValueKind.True or JsonValueKind.False)
                    _store.Armed = armedEl.GetBoolean();
                _store.Touch();
                break;
            }
            case "/mavros/statustext/recv":
            {
                var sev = (int)(Num(msg, "severity") ?? 99);
                if (sev <= 4 && msg.TryGetProperty("text", out var txtEl) && txtEl.GetString() is string txt)
                    _store.Log($"[FCU] {txt}");
                break;
            }
            case "/mavros/battery":
            {
                var v = Num(msg, "voltage") ?? double.NaN;
                var pRaw = Num(msg, "percentage") ?? double.NaN;
                _store.BatteryVoltage = double.IsFinite(v) && v > 0 && v < 60 ? v : null;
                double? pct = null;
                if (double.IsFinite(pRaw) && pRaw >= 0 && pRaw <= 1)
                    pct = pRaw * 100;
                else if (_store.BatteryVoltage is double bv)
                    pct = Math.Max(0, Math.Min(100, (bv / 6 - 3.3) / (4.2 - 3.3) * 100)); // 6S estimate
                _store.BatteryPct = pct;
                if (pct is double p)
                {
                    TelemetryStore.PushChart(_store.ChartBat, p);
                    if (p < 15 && _store.BatteryVoltage is double bv2)
                        _store.Log($"WARNING LOW BATTERY: {bv2:F2} V");
                }
                _store.Touch();
                break;
            }
            case "/mavros/mavros/pose":
            {
                if (Obj(msg, "pose") is not JsonElement pose ||
                    Obj(pose, "position") is not JsonElement p ||
                    Obj(pose, "orientation") is not JsonElement o) return;
                _store.PosX = Num(p, "x") ?? 0;
                _store.PosY = Num(p, "y") ?? 0;
                _store.PosZ = Num(p, "z") ?? 0;
                var e = MathUtil.QuatToEuler(Num(o, "x") ?? 0, Num(o, "y") ?? 0, Num(o, "z") ?? 0, Num(o, "w") ?? 1);
                _store.Roll = e.Roll; _store.Pitch = e.Pitch; _store.Yaw = e.Yaw;
                _store.PushTrail(_store.PosX, _store.PosY);
                TelemetryStore.PushChart(_store.ChartAlt, _store.PosZ);
                _store.Touch();
                break;
            }
            case "/mavros/mavros/velocity_local":
            {
                if (Obj(msg, "twist") is not JsonElement twist ||
                    Obj(twist, "linear") is not JsonElement l) return;
                _store.Vx = Num(l, "x") ?? 0;
                _store.Vy = Num(l, "y") ?? 0;
                _store.Vz = Num(l, "z") ?? 0;
                TelemetryStore.PushChart(_store.ChartSpd, _store.SpeedH);
                _store.Touch();
                break;
            }
            case "/mavros/mavros/data":
            {
                if (Obj(msg, "angular_velocity") is not JsonElement av ||
                    Obj(msg, "linear_acceleration") is not JsonElement la) return;
                double gx = Num(av, "x") ?? 0, gy = Num(av, "y") ?? 0, gz = Num(av, "z") ?? 0;
                double ax = Num(la, "x") ?? 0, ay = Num(la, "y") ?? 0, az = Num(la, "z") ?? 0;
                _store.GyroMag = Math.Sqrt(gx * gx + gy * gy + gz * gz) * 180 / Math.PI;
                _store.AccelMag = Math.Sqrt(ax * ax + ay * ay + az * az);
                break;
            }
            default:
                return;
        }
        _store.NotifyUpdated();
    }
}
