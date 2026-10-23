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

// SimDrone — мок дрона Bumblebee на localhost для end-to-end проверки GCS.
// Порты: rosbridge WS :9090, метрики :8888, API :8765, MJPEG :8080.
// HttpListener с префиксами localhost не требует прав администратора,
// поэтому в приложении подключаться нужно к хосту "localhost".
//
// Состояния полётного контроллера — те же, что у gcs/tools/mock_drone.py:
//   --fcu auto|disarmed|armed|stale|lost   (auto: ARMED/DISARMED каждые 30 с)
//   --telemetry normal|freeze              (freeze: сокет открыт, данных нет)
//   --battery ok|low
// Менять на ходу: http://localhost:8799/mock/set?fcu=armed&battery=low,
// посмотреть: http://localhost:8799/mock/state. Тихий обрыв связи — пауза
// процесса (Монитор ресурсов → «Приостановить процесс»).

using System.Collections.Concurrent;
using System.Drawing;
using System.Drawing.Imaging;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;

var sim = new SimState();
for (var i = 0; i + 1 < args.Length; i += 2)
{
    var err = sim.Set(args[i].TrimStart('-'), args[i + 1]);
    if (err != null) { Console.Error.WriteLine(err); return 2; }
}
Console.WriteLine("SimDrone: connect the GCS to host \"localhost\"");
_ = Task.Run(() => ControlServer(sim));
_ = Task.Run(() => RosbridgeServer(sim));
_ = Task.Run(() => JsonServer(8888, MetricsJson));
_ = Task.Run(() => ApiServer(sim));
_ = Task.Run(() => MjpegServer(sim));

var start = DateTime.UtcNow;
while (true)
{
    sim.Tick((DateTime.UtcNow - start).TotalSeconds);
    await Task.Delay(50); // 20 Hz
}

// ---------------------------------------------------------------- rosbridge

static async Task RosbridgeServer(SimState sim)
{
    var listener = new HttpListener();
    listener.Prefixes.Add("http://localhost:9090/");
    listener.Start();
    Console.WriteLine("[9090] rosbridge ws up");
    while (true)
    {
        var ctx = await listener.GetContextAsync();
        if (!ctx.Request.IsWebSocketRequest)
        {
            ctx.Response.StatusCode = 200; // TCP-проба скана считает порт открытым
            ctx.Response.Close();
            continue;
        }
        _ = Task.Run(async () =>
        {
            var ws = (await ctx.AcceptWebSocketAsync(null)).WebSocket;
            Console.WriteLine("[9090] client connected");
            var topics = new ConcurrentDictionary<string, bool>();
            _ = Task.Run(async () =>
            {
                var buf = new byte[16384];
                try
                {
                    while (ws.State == WebSocketState.Open)
                    {
                        var r = await ws.ReceiveAsync(buf, CancellationToken.None);
                        if (r.MessageType == WebSocketMessageType.Close) break;
                        var doc = JsonDocument.Parse(new ReadOnlyMemory<byte>(buf, 0, r.Count));
                        if (doc.RootElement.TryGetProperty("op", out var op) && op.GetString() == "subscribe" &&
                            doc.RootElement.TryGetProperty("topic", out var t) && t.GetString() is string topic)
                        {
                            topics[topic] = true;
                            Console.WriteLine($"[9090] subscribe {topic}");
                        }
                    }
                }
                catch { }
            });
            try
            {
                var lastStatus = DateTime.UtcNow;
                while (ws.State == WebSocketState.Open)
                {
                    foreach (var (topic, payload) in sim.Telemetry == "freeze" ? [] : sim.Publications())
                    {
                        if (!topics.ContainsKey(topic)) continue;
                        var msg = JsonSerializer.Serialize(new Dictionary<string, object?>
                        {
                            ["op"] = "publish",
                            ["topic"] = topic,
                            ["msg"] = payload,
                        });
                        await ws.SendAsync(Encoding.UTF8.GetBytes(msg), WebSocketMessageType.Text, true, CancellationToken.None);
                    }
                    if (sim.Telemetry != "freeze" && (DateTime.UtcNow - lastStatus).TotalSeconds > 12)
                    {
                        lastStatus = DateTime.UtcNow;
                        var msg = JsonSerializer.Serialize(new
                        {
                            op = "publish",
                            topic = "/mavros/statustext/recv",
                            msg = new { severity = 2, text = $"SIM checkpoint at {DateTime.Now:HH:mm:ss}" },
                        });
                        await ws.SendAsync(Encoding.UTF8.GetBytes(msg), WebSocketMessageType.Text, true, CancellationToken.None);
                    }
                    await Task.Delay(66); // ~15 Hz
                }
            }
            catch { }
            Console.WriteLine("[9090] client dropped");
        });
    }
}

// ---------------------------------------------------------------- metrics :8888

static string MetricsJson()
{
    var rnd = Random.Shared;
    return JsonSerializer.Serialize(new
    {
        hostname = "sim-drone",
        cpu_temp = 52 + rnd.NextDouble() * 12,
        cpu_pct = 25 + rnd.NextDouble() * 40,
        load1 = 0.8 + rnd.NextDouble(),
        load5 = 0.9,
        load15 = 0.7,
        cpu_count = 4,
        mem_used = 1400 + rnd.Next(0, 300),
        mem_total = 3924,
        mem_pct = 40 + rnd.NextDouble() * 15,
    });
}

static async Task JsonServer(int port, Func<string> body)
{
    var listener = new HttpListener();
    listener.Prefixes.Add($"http://localhost:{port}/");
    listener.Start();
    Console.WriteLine($"[{port}] json up");
    while (true)
    {
        var ctx = await listener.GetContextAsync();
        var data = Encoding.UTF8.GetBytes(body());
        ctx.Response.ContentType = "application/json";
        await ctx.Response.OutputStream.WriteAsync(data);
        ctx.Response.Close();
    }
}

// ---------------------------------------------------------------- API :8765

static async Task ApiServer(SimState sim)
{
    var listener = new HttpListener();
    listener.Prefixes.Add("http://localhost:8765/");
    listener.Start();
    Console.WriteLine("[8765] api up");
    while (true)
    {
        var ctx = await listener.GetContextAsync();
        var path = ctx.Request.Url?.AbsolutePath ?? "/";
        var method = ctx.Request.HttpMethod;
        string reqBody = "";
        if (ctx.Request.HasEntityBody)
            using (var r = new StreamReader(ctx.Request.InputStream))
                reqBody = await r.ReadToEndAsync();
        Console.WriteLine($"[8765] {method} {path} {reqBody}");
        JsonElement body = default;
        try { body = JsonDocument.Parse(reqBody.Length > 0 ? reqBody : "{}").RootElement.Clone(); } catch { }

        var (status, response) = Api(sim, method, path, body);
        var data = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(response));
        ctx.Response.StatusCode = status;
        ctx.Response.ContentType = "application/json";
        await ctx.Response.OutputStream.WriteAsync(data);
        ctx.Response.Close();
    }
}

/// <summary>
/// The drone's REST API as image 1.0.2 answers it (wifi_manager.py): error replies carry a
/// stable code; Wi-Fi changes and sounds need a fresh, linked, disarmed FC ("unknown = armed");
/// the network in use is removed only with confirm_active; animations stop after 120 s.
/// </summary>
static (int Status, object Body) Api(SimState sim, string method, string path, JsonElement body)
{
    static (int, object) Fail(int status, string code, string error) => (status, new { error, code });
    string Field(string key) =>
        body.ValueKind == JsonValueKind.Object && body.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String
            ? v.GetString() ?? "" : "";
    (int, object)? Refusal() => sim.FcuFlightState() switch
    {
        "disarmed" => null,
        "armed" => Fail(409, "armed", "the drone is armed: refused until it is disarmed"),
        _ => Fail(503, "fc_unknown", "flight controller state unknown (not linked, or no fresh state), so it counts as armed"),
    };
    bool Protected(string n) => n.Trim().ToLowerInvariant() is var l &&
                                (l == "bumblebee-hotspot" || l.StartsWith("bumblebee-") || l.EndsWith(".bb-pending"));

    switch (path)
    {
        case "/api/wifi/status":
            return (200, new { mode = "client", ssid = "SimNet-5G", ip = "127.0.0.1", signal = 78, id = SimState.Id });
        case "/api/info":
            return (200, new { name = "Bumblebee-" + SimState.Id, id = SimState.Id, version = "SimDrone", ros_domain = (int?)null, contract = 1 });
        case "/api/wifi/scan":
            return (200, new object[]
            {
                new { ssid = "SimNet-5G", signal = 78, security = "WPA2", in_use = true, band = "5", freq = 5300 },
                new { ssid = "HomeWifi", signal = 55, security = "WPA2", in_use = false, band = "2.4", freq = 2412 },
                new { ssid = "Cafe", signal = 40, security = "", in_use = false, band = "2.4", freq = 2462 },
                new { ssid = "Bumblebee-ABCD", signal = 60, security = "WPA2", in_use = false, band = "2.4", freq = 2437 },
                new { ssid = "Neighbor6E", signal = 23, security = "WPA3", in_use = false, band = "6", freq = 5955 },
            });
        case "/api/wifi/networks":
            return (200, new object[] { new { name = "SimNet-5G" }, new { name = "FieldRouter" } });
        case "/api/wifi/save" or "/api/wifi/apply-now" or "/api/wifi/apply-boot":
        {
            var ssid = Field("ssid").Trim();
            if (ssid.Length == 0) return Fail(400, "ssid_required", "ssid required");
            var pass = Field("password");
            if (path == "/api/wifi/save" && pass.Length > 0 && (Encoding.UTF8.GetByteCount(pass) is < 8 or > 64))
                return Fail(400, "bad_password_length", "a Wi-Fi password has 8 to 63 characters (or is exactly 64 hex digits)");
            if (Protected(ssid)) return Fail(409, "protected_network", $"'{ssid}' is the drones' own setup hotspot");
            if (Refusal() is { } r) return r;
            return (200, path == "/api/wifi/save" ? new { ok = true, pending = pass.Length > 0 } : new { ok = true });
        }
        case "/api/wifi/network":
        {
            var ssid = Field("ssid").Trim();
            if (Protected(ssid)) return Fail(409, "protected_network", $"'{ssid}' is the drones' own setup hotspot");
            if (Refusal() is { } r) return r;
            var confirmed = body.ValueKind == JsonValueKind.Object && body.TryGetProperty("confirm_active", out var c) &&
                            c.ValueKind == JsonValueKind.True;
            if (ssid == "SimNet-5G" && !confirmed)
                return Fail(409, "active_network", $"'{ssid}' is the network the drone is using right now");
            return (200, confirmed ? new { ok = true, deferred = true } : new { ok = true });
        }
        case "/api/wifi/mode":
            return Refusal() ?? (200, new { ok = true, mode = Field("mode") });
        case "/api/led/animation":
            sim.StartAnimation(Field("name"));
            return (200, new { ok = true, name = Field("name"), pid = 4242, max_s = SimState.ShowMaxS });
        case "/api/led/color" or "/api/led/reset":
            sim.StopAnimation();
            return (200, new { ok = true });
        case "/api/led/status":
            return (200, sim.LedStatus());
        case "/api/sounds/tts":
            return Refusal() ?? (200, new { ok = true, tune = "MFT180L8O5CDEFG", phonemes = "k-o-t" });
        case "/api/sounds/play":
            return Refusal() ?? (200, new { ok = true });
        case "/api/fcu/status":
            return (200, sim.FcuStatus());
        default:
            return (200, new { ok = true });
    }
}

// ---------------------------------------------------------------- управление :8799

static async Task ControlServer(SimState sim)
{
    var listener = new HttpListener();
    listener.Prefixes.Add("http://localhost:8799/");
    listener.Start();
    Console.WriteLine("[8799] control up: /mock/state, /mock/set?fcu=...&telemetry=...&battery=...");
    while (true)
    {
        var ctx = await listener.GetContextAsync();
        var path = ctx.Request.Url?.AbsolutePath ?? "/";
        string? err = null;
        if (path == "/mock/set")
        {
            foreach (string? key in ctx.Request.QueryString.AllKeys)
            {
                if (key != null) err ??= sim.Set(key, ctx.Request.QueryString[key] ?? "");
            }
        }
        else if (path != "/mock/state")
        {
            err = $"unknown path {path}";
        }
        ctx.Response.StatusCode = err == null ? 200 : 400;
        var data = Encoding.UTF8.GetBytes(err == null ? sim.StateJson() : JsonSerializer.Serialize(new { error = err }));
        ctx.Response.ContentType = "application/json";
        await ctx.Response.OutputStream.WriteAsync(data);
        ctx.Response.Close();
    }
}

// ---------------------------------------------------------------- MJPEG :8080

static async Task MjpegServer(SimState sim)
{
    var listener = new HttpListener();
    listener.Prefixes.Add("http://localhost:8080/");
    listener.Start();
    Console.WriteLine("[8080] mjpeg up");
    while (true)
    {
        var ctx = await listener.GetContextAsync();
        var topic = ctx.Request.QueryString["topic"] ?? "?";
        Console.WriteLine($"[8080] stream start {topic}");
        _ = Task.Run(async () =>
        {
            var resp = ctx.Response;
            resp.ContentType = "multipart/x-mixed-replace; boundary=frame";
            // Без Content-Length HttpListener требует chunked; HttpClient на
            // стороне GCS прозрачно раздекодирует chunked обратно в байты.
            resp.SendChunked = true;
            var stream = resp.OutputStream;
            try
            {
                var n = 0;
                while (true)
                {
                    var jpeg = RenderFrame(topic, n++, sim);
                    var header = Encoding.ASCII.GetBytes(
                        $"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {jpeg.Length}\r\n\r\n");
                    await stream.WriteAsync(header);
                    await stream.WriteAsync(jpeg);
                    await stream.WriteAsync(Encoding.ASCII.GetBytes("\r\n"));
                    await stream.FlushAsync();
                    await Task.Delay(83); // ~12 fps
                }
            }
            catch { Console.WriteLine($"[8080] stream end {topic}"); }
            try { resp.Close(); } catch { }
        });
    }
}

static byte[] RenderFrame(string topic, int n, SimState sim)
{
    using var bmp = new Bitmap(320, 240);
    using var g = Graphics.FromImage(bmp);
    var baseColor = topic.Contains("aruco") ? Color.FromArgb(30, 60, 30) : Color.FromArgb(25, 30, 45);
    g.Clear(baseColor);
    using (var pen = new Pen(Color.FromArgb(70, 90, 120)))
        for (var i = 0; i < 320; i += 40)
        {
            g.DrawLine(pen, i, 0, i, 240);
            if (i < 240) g.DrawLine(pen, 0, i, 320, i);
        }
    // «Дрон» — движущийся маркер.
    var cx = 160 + (float)(Math.Sin(n * 0.05) * 100);
    var cy = 120 + (float)(Math.Cos(n * 0.07) * 60);
    g.FillEllipse(Brushes.Orange, cx - 10, cy - 10, 20, 20);
    g.DrawString($"{topic}", new Font("Consolas", 9), Brushes.White, 4, 4);
    g.DrawString($"{DateTime.Now:HH:mm:ss.f}  z={sim.Z:F2}m", new Font("Consolas", 9), Brushes.White, 4, 222);
    using var ms = new MemoryStream();
    bmp.Save(ms, ImageFormat.Jpeg);
    return ms.ToArray();
}

// ---------------------------------------------------------------- состояние полёта

sealed class SimState
{
    static readonly Dictionary<string, string[]> Choices = new()
    {
        ["fcu"] = ["auto", "disarmed", "armed", "stale", "lost"],
        ["telemetry"] = ["normal", "freeze"],
        ["battery"] = ["ok", "low"],
    };

    /// <summary>The simulated drone's id (last 4 hex digits of a MAC), as in /api/wifi/status.</summary>
    public const string Id = "51D0";
    /// <summary>Animations stop by themselves after this long (wifi_manager.py SHOW_MAX_S).</summary>
    public const int ShowMaxS = 120;

    string? _animation;
    DateTime _animationEnds;
    readonly object _ledLock = new();

    public void StartAnimation(string name)
    {
        lock (_ledLock) { _animation = name; _animationEnds = DateTime.UtcNow.AddSeconds(ShowMaxS); }
    }

    public void StopAnimation()
    {
        lock (_ledLock) _animation = null;
    }

    public object LedStatus()
    {
        lock (_ledLock)
        {
            if (_animation is not null && DateTime.UtcNow >= _animationEnds) _animation = null;
            int? remaining = _animation is null ? null : (int)Math.Ceiling((_animationEnds - DateTime.UtcNow).TotalSeconds);
            return new { led_ok = true, animation = _animation, pid = _animation is null ? (int?)null : 4242,
                         busy = _animation is not null, remaining_s = remaining };
        }
    }

    /// <summary>As wifi_manager.py _fcu_flight_state: disarmed only from a fresh, linked state.</summary>
    public string FcuFlightState() => Fcu switch
    {
        "auto" or "disarmed" or "armed" => Armed ? "armed" : "disarmed",
        _ => Armed ? "armed" : "unknown",
    };

    double _t;
    public double X, Y, Z, Roll, Pitch, Yaw, Vx, Vy, Vz;
    public double Voltage = 25.2;
    public volatile bool Armed;
    public volatile string Fcu = "auto", Telemetry = "normal", Battery = "ok";

    /// <summary>Validates and applies one setting; returns an error or null.</summary>
    public string? Set(string key, string value)
    {
        if (!Choices.TryGetValue(key, out var allowed) || !allowed.Contains(value))
            return $"bad {key}={value} (choose {(allowed == null ? "fcu|telemetry|battery" : string.Join("|", allowed))})";
        switch (key)
        {
            case "fcu": Fcu = value; break;
            case "telemetry": Telemetry = value; break;
            case "battery": Battery = value; break;
        }
        if (value is "armed" or "disarmed") Armed = value == "armed";
        if (value == "lost") Armed = false;
        Console.WriteLine($"[sim] {StateJson()}");
        return null;
    }

    public string StateJson() => JsonSerializer.Serialize(new { fcu = Fcu, telemetry = Telemetry, battery = Battery });

    /// <summary>Same meaning as /api/fcu/status on the drone (wifi_manager.py over
    /// drone.get_fcu_status): stale keeps the last armed flag and mode, lost
    /// (MAVROS says connected=false) reports disarmed.</summary>
    public object FcuStatus()
    {
        var connected = Fcu is "auto" or "disarmed" or "armed";
        var lost = Fcu == "lost";
        return new { ok = connected, connected, armed = !lost && Armed, mode = lost ? "" : Mode };
    }

    string Mode => Armed ? "OFFBOARD" : "STABILIZED";

    public void Tick(double t)
    {
        _t = t;
        X = 3 * Math.Cos(t * 0.3);
        Y = 3 * Math.Sin(t * 0.3);
        Z = 1.5 + 0.5 * Math.Sin(t * 0.15);
        Vx = -0.9 * Math.Sin(t * 0.3);
        Vy = 0.9 * Math.Cos(t * 0.3);
        Vz = 0.075 * Math.Cos(t * 0.15);
        Roll = 10 * Math.Sin(t * 0.5);
        Pitch = 8 * Math.Cos(t * 0.4);
        Yaw = (t * 12) % 360 - 180;
        Voltage = Battery == "low" ? 20.4 : Math.Max(19.8, 25.2 - t * 0.01);
        if (Fcu == "auto") Armed = (int)(t / 30) % 2 == 1;
    }

    static object Quat(double rollDeg, double pitchDeg, double yawDeg)
    {
        double r = rollDeg * Math.PI / 360, p = pitchDeg * Math.PI / 360, y = yawDeg * Math.PI / 360;
        double cr = Math.Cos(r), sr = Math.Sin(r), cp = Math.Cos(p), sp = Math.Sin(p), cy = Math.Cos(y), sy = Math.Sin(y);
        return new
        {
            w = cr * cp * cy + sr * sp * sy,
            x = sr * cp * cy - cr * sp * sy,
            y = cr * sp * cy + sr * cp * sy,
            z = cr * cp * sy - sr * sp * cy,
        };
    }

    public IEnumerable<(string Topic, object Msg)> Publications()
    {
        var pct = Math.Clamp((Voltage / 6 - 3.3) / (4.2 - 3.3), 0, 1);
        if (Fcu == "lost")
            yield return ("/mavros/state", new { connected = false, mode = "", armed = false });
        else if (Fcu != "stale")   // stale: no fresh State at all
            yield return ("/mavros/state", new { connected = true, mode = Mode, armed = Armed });
        yield return ("/mavros/battery", new { voltage = Voltage, percentage = pct });
        yield return ("/mavros/mavros/pose", new
        {
            pose = new { position = new { x = X, y = Y, z = Z }, orientation = Quat(Roll, Pitch, Yaw) },
        });
        yield return ("/mavros/mavros/velocity_local", new
        {
            twist = new { linear = new { x = Vx, y = Vy, z = Vz } },
        });
        yield return ("/mavros/mavros/data", new
        {
            angular_velocity = new
            {
                x = 0.08 * Math.Sin(_t * 2),
                y = 0.06 * Math.Cos(_t * 1.7),
                z = 0.21,
            },
            linear_acceleration = new
            {
                x = 0.4 * Math.Sin(_t),
                y = 0.3 * Math.Cos(_t * 1.2),
                z = 9.81 + 0.2 * Math.Sin(_t * 3),
            },
        });
    }
}
