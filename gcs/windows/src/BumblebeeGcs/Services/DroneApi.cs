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

using System.Text;
using BumblebeeGcs.Logic;
using System.Text.Json;

namespace BumblebeeGcs.Services;

/// <summary>
/// HTTP-клиент для эндпоинтов дрона `/api/*` (бэкенд wifi_manager.py на :8765).
/// Покрывает LED, звуки/TTS (Entertainment) и wifi/auth (Settings).
/// </summary>
public sealed class DroneApi
{
    public const int Port = 8765;
    public string Host = "";

    /// <summary>Мимо системного прокси: дрон в локальной сети, школьный прокси до него не дотянется.</summary>
    private static readonly HttpClient Http = new(new SocketsHttpHandler { UseProxy = false })
    {
        Timeout = TimeSpan.FromSeconds(6),
    };

    /// <summary>Transport = запрос не дошёл / связь оборвалась (а не ошибка от дрона).
    /// Code — стабильный код ошибки дронов 1.0.2+; текст уже человеческий.</summary>
    public sealed class ApiException(string message, bool transport = false, string? code = null) : Exception(message)
    {
        public bool Transport { get; } = transport;
        public string? Code { get; } = code;
    }

    /// <summary>Plain words for any error of a request: the drone's reply, or no answer.</summary>
    public static string Describe(Exception ex) => ex is ApiException { Transport: true } t
        ? DroneErrorText.NoAnswer(t.Message)
        : ex.Message;

    /// <summary>The stable code of an error reply, if the drone sent one.</summary>
    public static string? CodeOf(Exception ex) => (ex as ApiException)?.Code;

    /// <summary>
    /// Почему дрон не смог подключиться к сети, которую ему передали
    /// (`last_error` в /api/wifi/status). Reason: wrong_password, not_found,
    /// no_ip, timeout, failed.
    /// </summary>
    public sealed record JoinError(string Ssid, string Reason, string Message, DateTime? TimeUtc = null);

    /// <summary>Id — последние 4 hex-цифры MAC дрона (как в SSID его хотспота и в TXT `id`);
    /// null у дронов со старым ПО.</summary>
    public readonly record struct WifiStatus(string Mode, string Ssid, string Ip, int Signal,
                                             string? Id = null, JoinError? LastError = null);
    public readonly record struct ScanNet(string Ssid, int Signal, bool InUse, string Band, int Freq,
                                          string Security = "")
    {
        public bool Secured => WifiNames.IsSecured(Security);
    }

    /// <summary>Who the drone is (GET /api/info, drones 1.0.2+).</summary>
    public sealed record DroneInfo(string Name, string Id, string Version);

    /// <summary>What the LEDs do now; Remaining (seconds until it stops by itself) from 1.0.2+.</summary>
    public readonly record struct LedStatus(bool LedOk, string? Animation, bool Busy, int? Remaining);

    private async Task<(byte[] Data, int Status)> RequestAsync(HttpMethod method, string path, object? json = null)
    {
        var host = Host;
        if (string.IsNullOrEmpty(host)) throw new ApiException("no drone");
        using var req = new HttpRequestMessage(method, $"http://{host}:{Port}{path}");
        if (json is not null)
            req.Content = new StringContent(JsonSerializer.Serialize(json), Encoding.UTF8, "application/json");
        HttpResponseMessage resp;
        try { resp = await Http.SendAsync(req); }
        catch (Exception ex) { throw new ApiException(ex.Message, transport: true); }
        using (resp)
        {
            var data = await resp.Content.ReadAsByteArrayAsync();
            return (data, (int)resp.StatusCode);
        }
    }

    /// <summary>The reply object of a request that must answer 200.</summary>
    private async Task<Dictionary<string, JsonElement>> OkAsync(HttpMethod method, string path, object? json = null)
    {
        var (data, status) = await RequestAsync(method, path, json);
        if (status != 200) throw Failure(data, status);
        return ObjectFrom(data);
    }

    /// <summary>The body of a GET that must answer 200 (an error reply is not data).</summary>
    private async Task<byte[]> GetAsync(string path)
    {
        var (data, status) = await RequestAsync(HttpMethod.Get, path);
        if (status != 200) throw Failure(data, status);
        return data;
    }

    static ApiException Failure(byte[] data, int status)
    {
        var obj = ObjectFrom(data);
        var code = Str(obj, "code");
        return new ApiException(DroneErrorText.Text(code, Str(obj, "error"), status), code: code);
    }

    static Dictionary<string, JsonElement> ObjectFrom(byte[] data)
    {
        try
        {
            using var doc = JsonDocument.Parse(data);
            if (doc.RootElement.ValueKind == JsonValueKind.Object)
                return doc.RootElement.EnumerateObject().ToDictionary(p => p.Name, p => p.Value.Clone());
        }
        catch { }
        return new Dictionary<string, JsonElement>();
    }

    // MARK: - LED

    public Task LedColorAsync(int r, int g, int b) => OkAsync(HttpMethod.Post, "/api/led/color", new { r, g, b });
    public Task LedAnimationAsync(string name) => OkAsync(HttpMethod.Post, "/api/led/animation", new { name });
    public Task LedResetAsync() => OkAsync(HttpMethod.Post, "/api/led/reset");

    // MARK: - Sounds / TTS

    /// <summary>Возвращает объект ответа сервера (может содержать "tune"/"phonemes").</summary>
    public Task<Dictionary<string, JsonElement>> PlayTuneAsync(string tune, string format) =>
        OkAsync(HttpMethod.Post, "/api/sounds/play", new { tune, format });

    public Task<Dictionary<string, JsonElement>> TtsAsync(string text, string lang) =>
        OkAsync(HttpMethod.Post, "/api/sounds/tts", new { text, lang });

    public async Task<LedStatus> LedStatusAsync()
    {
        var o = ObjectFrom(await GetAsync("/api/led/status"));
        var anim = Str(o, "animation");
        return new LedStatus(
            o.TryGetValue("led_ok", out var ok) && ok.ValueKind == JsonValueKind.True,
            string.IsNullOrEmpty(anim) ? null : anim,
            o.TryGetValue("busy", out var b) && b.ValueKind == JsonValueKind.True,
            o.TryGetValue("remaining_s", out var r) && r.ValueKind == JsonValueKind.Number ? (int)r.GetDouble() : null);
    }

    /// <summary>GET /api/info; null from drones before 1.0.2 (404) or without an answer.</summary>
    public async Task<DroneInfo?> InfoAsync()
    {
        try
        {
            var o = ObjectFrom(await GetAsync("/api/info"));
            return Str(o, "name") is string name ? new DroneInfo(name, Str(o, "id") ?? "", Str(o, "version") ?? "") : null;
        }
        catch { return null; }
    }

    public static string? Str(Dictionary<string, JsonElement> obj, string key) =>
        obj.TryGetValue(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    // MARK: - WiFi / auth

    public async Task<WifiStatus> WifiStatusAsync()
    {
        var o = ObjectFrom(await GetAsync("/api/wifi/status"));
        JoinError? lastError = null;
        if (o.TryGetValue("last_error", out var le) && le.ValueKind == JsonValueKind.Object)
        {
            static string Field(JsonElement e, string key) =>
                e.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() ?? "" : "";
            DateTime? time = le.TryGetProperty("time", out var t) && t.ValueKind == JsonValueKind.Number
                ? DateTimeOffset.FromUnixTimeSeconds((long)t.GetDouble()).UtcDateTime : null;
            lastError = new JoinError(Field(le, "ssid"), Field(le, "reason"), Field(le, "message"), time);
        }
        var id = Str(o, "id");
        return new WifiStatus(
            Str(o, "mode") ?? "—",
            Str(o, "ssid") ?? "—",
            Str(o, "ip") ?? "—",
            o.TryGetValue("signal", out var s) && s.ValueKind == JsonValueKind.Number ? (int)s.GetDouble() : 0,
            string.IsNullOrEmpty(id) ? null : id,
            lastError);
    }

    public Task WifiSetModeAsync(string mode) => OkAsync(HttpMethod.Post, "/api/wifi/mode", new { mode });

    public async Task<bool> LoginAsync(string pin)
    {
        var (_, status) = await RequestAsync(HttpMethod.Post, "/api/auth/login", new { pin });
        return status == 200;
    }

    public async Task LogoutAsync()
    {
        try { await RequestAsync(HttpMethod.Post, "/api/auth/logout"); } catch { }
    }

    public async Task<List<ScanNet>> WifiScanAsync()
    {
        var data = await GetAsync("/api/wifi/scan");
        var list = new List<ScanNet>();
        try
        {
            using var doc = JsonDocument.Parse(data);
            if (doc.RootElement.ValueKind != JsonValueKind.Array) return list;
            foreach (var el in doc.RootElement.EnumerateArray())
            {
                if (el.ValueKind != JsonValueKind.Object) continue;
                list.Add(new ScanNet(
                    el.TryGetProperty("ssid", out var ss) ? ss.GetString() ?? "" : "",
                    el.TryGetProperty("signal", out var sg) && sg.ValueKind == JsonValueKind.Number ? (int)sg.GetDouble() : 0,
                    el.TryGetProperty("in_use", out var iu) && iu.ValueKind == JsonValueKind.True,
                    el.TryGetProperty("band", out var bd) ? bd.GetString() ?? "" : "",
                    el.TryGetProperty("freq", out var fq) && fq.ValueKind == JsonValueKind.Number ? (int)fq.GetDouble() : 0,
                    el.TryGetProperty("security", out var sc) && sc.ValueKind == JsonValueKind.String ? sc.GetString() ?? "" : ""));
            }
        }
        catch { }
        return list;
    }

    public async Task<List<string>> SavedNetworksAsync()
    {
        var data = await GetAsync("/api/wifi/networks");
        var list = new List<string>();
        try
        {
            using var doc = JsonDocument.Parse(data);
            if (doc.RootElement.ValueKind != JsonValueKind.Array) return list;
            foreach (var el in doc.RootElement.EnumerateArray())
                if (el.ValueKind == JsonValueKind.Object &&
                    el.TryGetProperty("name", out var n) && n.GetString() is string name)
                    list.Add(name);
        }
        catch { }
        return list;
    }

    /// <param name="confirmActive">The user confirmed removing the network the drone uses now
    /// (drones 1.0.2+ refuse it otherwise with code active_network).</param>
    public Task RemoveNetworkAsync(string ssid, bool confirmActive = false) => confirmActive
        ? OkAsync(HttpMethod.Delete, "/api/wifi/network", new { ssid, confirm_active = true })
        : OkAsync(HttpMethod.Delete, "/api/wifi/network", new { ssid });
    public Task SaveNetworkAsync(string ssid, string password) => OkAsync(HttpMethod.Post, "/api/wifi/save", new { ssid, password });
    public Task ApplyNowAsync(string ssid) => OkAsync(HttpMethod.Post, "/api/wifi/apply-now", new { ssid });
    public Task ApplyBootAsync(string ssid) => OkAsync(HttpMethod.Post, "/api/wifi/apply-boot", new { ssid });
}
