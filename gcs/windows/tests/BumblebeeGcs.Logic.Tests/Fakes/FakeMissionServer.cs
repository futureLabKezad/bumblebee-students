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

using System.Net;
using System.Net.Sockets;
using System.Text;

namespace BumblebeeGcs.Logic.Tests.Fakes;

/// <summary>
/// A tiny HTTP/1.1 server on 127.0.0.1 standing in for the drone's mission server
/// (bb_mission, :8766): one request per connection, the reply comes from the test.
/// </summary>
public sealed class FakeMissionServer : IDisposable
{
    public sealed record Request(string Method, string Target, string ContentType, string Body);

    private readonly TcpListener _listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource _cts = new();
    private readonly Func<Request, (int Code, string Json)> _handler;
    private readonly List<Request> _requests = new();

    public int Port { get; }

    public FakeMissionServer(Func<Request, (int Code, string Json)> handler)
    {
        _handler = handler;
        _listener.Start();
        Port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        _ = AcceptLoopAsync();
    }

    public IReadOnlyList<Request> Requests
    {
        get { lock (_requests) return _requests.ToList(); }
    }

    private async Task AcceptLoopAsync()
    {
        try
        {
            while (!_cts.IsCancellationRequested)
            {
                var client = await _listener.AcceptTcpClientAsync(_cts.Token);
                _ = ServeAsync(client);
            }
        }
        catch (OperationCanceledException) { }
        catch (ObjectDisposedException) { }
        catch (SocketException) { }
    }

    private async Task ServeAsync(TcpClient client)
    {
        using (client)
        {
            try
            {
                var stream = client.GetStream();
                var data = new MemoryStream();
                var chunk = new byte[8192];
                var headerEnd = -1;
                while (headerEnd < 0)
                {
                    var n = await stream.ReadAsync(chunk, _cts.Token);
                    if (n == 0) return;
                    data.Write(chunk, 0, n);
                    headerEnd = Encoding.Latin1.GetString(data.GetBuffer(), 0, (int)data.Length).IndexOf("\r\n\r\n", StringComparison.Ordinal);
                }
                var head = Encoding.Latin1.GetString(data.GetBuffer(), 0, headerEnd).Split("\r\n");
                var first = head[0].Split(' ');
                var length = 0;
                var contentType = "";
                foreach (var line in head.Skip(1))
                {
                    var colon = line.IndexOf(':');
                    if (colon < 0) continue;
                    var name = line[..colon].Trim();
                    var value = line[(colon + 1)..].Trim();
                    if (name.Equals("Content-Length", StringComparison.OrdinalIgnoreCase)) length = int.Parse(value);
                    if (name.Equals("Content-Type", StringComparison.OrdinalIgnoreCase)) contentType = value;
                }
                while (data.Length < headerEnd + 4 + length)
                {
                    var n = await stream.ReadAsync(chunk, _cts.Token);
                    if (n == 0) return;
                    data.Write(chunk, 0, n);
                }
                var body = Encoding.UTF8.GetString(data.GetBuffer(), headerEnd + 4, length);
                var request = new Request(first[0], first.Length > 1 ? first[1] : "", contentType, body);
                lock (_requests) _requests.Add(request);
                var (code, json) = _handler(request);
                var payload = Encoding.UTF8.GetBytes(json);
                var header = Encoding.ASCII.GetBytes(
                    $"HTTP/1.1 {code} X\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: {payload.Length}\r\nConnection: close\r\n\r\n");
                await stream.WriteAsync(header, _cts.Token);
                await stream.WriteAsync(payload, _cts.Token);
                await stream.FlushAsync(_cts.Token);
            }
            catch (OperationCanceledException) { }
            catch (IOException) { }
            catch (SocketException) { }
        }
    }

    public void Dispose()
    {
        _cts.Cancel();
        _listener.Stop();
    }
}
