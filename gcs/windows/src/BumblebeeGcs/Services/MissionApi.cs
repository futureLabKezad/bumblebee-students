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
using System.Text.Encodings.Web;
using System.Text.Json;
using BumblebeeGcs.Logic;

namespace BumblebeeGcs.Services;

/// <summary>
/// HTTP client of the drone's mission server (bb_mission, :8766): the map and the flight
/// program of the «Полёт» section. Exactly the six paths below (gcs/tools/check_watch_only.py
/// lists them); a reply is passed on as it came, a missing answer is code 0.
/// </summary>
public sealed class MissionApi : IMissionApi
{
    public const int Port = 8766;

    private readonly int _port;

    /// <summary>Past the system proxy, like DroneApi: the drone is on the local network.
    /// A few connections at most: the page cannot make the app flood the drone.</summary>
    private static readonly HttpClient Http = new(
        new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false, MaxConnectionsPerServer = 4 })
    {
        Timeout = Timeout.InfiniteTimeSpan,             // every request has its own deadline below
        MaxResponseContentBufferSize = 4 * 1024 * 1024,
    };

    /// <summary>Stop has its own connections: it never waits behind the other requests.</summary>
    private static readonly HttpClient StopHttp = new(new SocketsHttpHandler { UseProxy = false, AllowAutoRedirect = false })
    {
        Timeout = Timeout.InfiniteTimeSpan,
        MaxResponseContentBufferSize = 64 * 1024,
    };

    private const int TimeoutMs = 12_000;               // POST /api/map waits up to 3 s for the detector's answer
    /// <summary>Stop is tried again when the drone did not answer (the command is harmless twice): 9 s in all.</summary>
    private static readonly int[] StopTimeoutsMs = { 2000, 3000, 4000 };

    /// <summary>Cyrillic as it is, not \uXXXX: the drone limits a request body in bytes.</summary>
    private static readonly JsonSerializerOptions Json = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };

    public MissionApi(int port = Port)
    {
        _port = port;
    }

    public Task<MissionReply> MapStatusAsync(string host) => SendAsync(Http, TimeoutMs, host, HttpMethod.Get, "/api/map/status");

    public Task<MissionReply> PutMapAsync(string host, JsonElement map) =>
        SendAsync(Http, TimeoutMs, host, HttpMethod.Post, "/api/map", new { map });

    public Task<MissionReply> CheckAsync(string host, string program) =>
        SendAsync(Http, TimeoutMs, host, HttpMethod.Post, "/api/mission/check", new { program });

    /// <summary>Called by FlightBridge only after the person clicked «Взлететь» in the app's own dialog.</summary>
    public Task<MissionReply> StartAsync(string host, string program, string token, string mapSha, bool battery, bool rc, bool people) =>
        SendAsync(Http, TimeoutMs, host, HttpMethod.Post, "/api/mission/start", new
        {
            program,
            token,
            map_sha = mapSha,
            confirm = new { battery_multimeter = battery, rc_in_hand_ch8 = rc, people_clear = people, takeoff_clicked = true },
        });

    public async Task<MissionReply> StopAsync(string host)
    {
        MissionReply last = default;
        foreach (var timeoutMs in StopTimeoutsMs)
        {
            last = await SendAsync(StopHttp, timeoutMs, host, HttpMethod.Post, "/api/mission/stop");
            if (last.Code != 0 || string.IsNullOrEmpty(host)) break;      // the drone answered, or there is no drone to ask
        }
        return last;
    }

    public Task<MissionReply> StatusAsync(string host, long since) =>
        SendAsync(Http, TimeoutMs, host, HttpMethod.Get, "/api/mission/status", query: "?since=" + since);

    private async Task<MissionReply> SendAsync(HttpClient http, int timeoutMs, string host, HttpMethod method, string path,
                                               object? json = null, string query = "")
    {
        if (string.IsNullOrEmpty(host)) return FlightBridge.Problem("the app is not connected to a drone", "no_drone");
        try
        {
            using var req = new HttpRequestMessage(method, "http://" + host + ":" + _port + path + query);
            // A new connection for every request: the small server on the drone closes idle ones,
            // and a request sent into a connection that is being closed is lost.
            req.Headers.ConnectionClose = true;
            if (json is not null)
                req.Content = new StringContent(JsonSerializer.Serialize(json, Json), Encoding.UTF8, "application/json");
            using var deadline = new CancellationTokenSource(timeoutMs);
            using var resp = await http.SendAsync(req, deadline.Token);
            var text = await resp.Content.ReadAsStringAsync(deadline.Token);
            return new MissionReply((int)resp.StatusCode, text);
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or IOException or UriFormatException)
        {
            return FlightBridge.Problem(
                "the mission server on the drone does not answer (it may not be installed on this drone): " + ex.Message, "no_answer");
        }
    }
}
