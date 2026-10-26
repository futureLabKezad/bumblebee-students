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

using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;

namespace BumblebeeGcs.Logic.Tests.Fakes;

/// <summary>
/// A tiny MJPEG server on 127.0.0.1 like the drone's :8080: every 50 ms it writes one
/// "JPEG" (SOI, the topic name, EOI) so a test can tell which topic a frame came from.
/// It counts open connections, can drop them all (server restart) or freeze (TCP open,
/// no bytes: a drone that rebooted under a half-open connection).
/// </summary>
public sealed class FakeMjpegServer : IDisposable
{
    private readonly TcpListener _listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource _cts = new();
    private readonly ConcurrentDictionary<TcpClient, CancellationTokenSource> _conns = new();
    private int _accepted;

    /// <summary>Keep connections open but send nothing.</summary>
    public volatile bool Frozen;

    public int Port { get; }
    public int Accepted => Volatile.Read(ref _accepted);
    public int Open => _conns.Count;

    public FakeMjpegServer()
    {
        _listener.Start();
        Port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        _ = AcceptLoop();
    }

    public Uri Url(string topic) => new($"http://127.0.0.1:{Port}/stream?topic={topic}&type=mjpeg");

    /// <summary>Close every open connection (the server restarts).</summary>
    public void DropAll()
    {
        foreach (var c in _conns.Values) c.Cancel();
    }

    /// <summary>The topic written into a fake frame.</summary>
    public static string TopicOf(byte[] frame) => Encoding.ASCII.GetString(frame, 2, frame.Length - 4);

    private async Task AcceptLoop()
    {
        while (!_cts.IsCancellationRequested)
        {
            TcpClient c;
            try { c = await _listener.AcceptTcpClientAsync(_cts.Token); }
            catch { return; }
            Interlocked.Increment(ref _accepted);
            _ = Serve(c);
        }
    }

    private async Task Serve(TcpClient client)
    {
        var conn = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token);
        _conns[client] = conn;
        var ct = conn.Token;
        var stream = client.GetStream();
        try
        {
            var request = await ReadRequest(stream, ct);
            var topic = TopicFromRequest(request);
            var head = "HTTP/1.1 200 OK\r\nContent-Type: multipart/x-mixed-replace; boundary=frame\r\n" +
                       "Connection: close\r\nCache-Control: no-cache\r\n\r\n";
            await stream.WriteAsync(Encoding.ASCII.GetBytes(head), ct);

            // The client closing its side ends the connection even while frozen.
            var closed = WatchForClose(stream, conn);
            var jpeg = new byte[] { 0xFF, 0xD8 }.Concat(Encoding.ASCII.GetBytes(topic)).Concat(new byte[] { 0xFF, 0xD9 }).ToArray();
            var part = Encoding.ASCII.GetBytes($"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {jpeg.Length}\r\n\r\n");
            while (!ct.IsCancellationRequested)
            {
                if (!Frozen)
                {
                    await stream.WriteAsync(part, ct);
                    await stream.WriteAsync(jpeg, ct);
                    await stream.WriteAsync(Encoding.ASCII.GetBytes("\r\n"), ct);
                }
                await Task.Delay(50, ct);
            }
            await closed;
        }
        catch { /* client gone, dropped or test over */ }
        finally
        {
            _conns.TryRemove(client, out _);
            conn.Cancel();
            client.Dispose();
        }
    }

    private static async Task WatchForClose(NetworkStream stream, CancellationTokenSource conn)
    {
        var buf = new byte[256];
        try
        {
            while (await stream.ReadAsync(buf, conn.Token) > 0) { }
        }
        catch { }
        conn.Cancel();
    }

    private static async Task<string> ReadRequest(NetworkStream stream, CancellationToken ct)
    {
        var sb = new StringBuilder();
        var one = new byte[1];
        while (!sb.ToString().EndsWith("\r\n\r\n", StringComparison.Ordinal))
        {
            if (await stream.ReadAsync(one, ct) == 0) throw new IOException("closed during request");
            sb.Append((char)one[0]);
        }
        return sb.ToString();
    }

    private static string TopicFromRequest(string request)
    {
        var line = request.Split("\r\n")[0];             // GET /stream?topic=X&... HTTP/1.1
        var q = line.IndexOf("topic=", StringComparison.Ordinal);
        if (q < 0) return "?";
        var rest = line[(q + "topic=".Length)..];
        var end = rest.IndexOfAny(new[] { '&', ' ' });
        return Uri.UnescapeDataString(end < 0 ? rest : rest[..end]);
    }

    public void Dispose()
    {
        _cts.Cancel();
        _listener.Stop();
    }
}
