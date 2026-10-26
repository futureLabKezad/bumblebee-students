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
using System.Security.Cryptography;
using System.Text;

namespace BumblebeeGcs.Logic.Tests.Fakes;

/// <summary>
/// A tiny rosbridge on 127.0.0.1 with a hand-written WebSocket server, so a test can do what
/// a real drone does to the laptop: stop publishing while still answering pings (MAVROS dead,
/// rosbridge alive), or freeze completely like `kill -STOP` (no reads, no writes, no pongs).
/// It publishes /mavros/state every 200 ms and records every text frame the client sends.
/// </summary>
public sealed class FakeRosbridge : IDisposable
{
    private readonly TcpListener _listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource _cts = new();
    private readonly ConcurrentBag<TcpClient> _clients = new();
    private int _accepted;

    /// <summary>Send /mavros/state every 200 ms.</summary>
    public volatile bool Publish = true;
    /// <summary>No reads, no writes, no pongs: a drone switched off without closing TCP.</summary>
    public volatile bool Frozen;
    public volatile bool FcConnected = true;
    public volatile bool Armed;
    public volatile string Mode = "POSCTL";

    public int Port { get; }
    public int Accepted => Volatile.Read(ref _accepted);
    /// <summary>Text frames from the client (subscribe requests), in order.</summary>
    public ConcurrentQueue<string> ClientTexts { get; } = new();

    public FakeRosbridge()
    {
        _listener.Start();
        Port = ((IPEndPoint)_listener.LocalEndpoint).Port;
        _ = AcceptLoop();
    }

    private async Task AcceptLoop()
    {
        while (!_cts.IsCancellationRequested)
        {
            TcpClient c;
            try { c = await _listener.AcceptTcpClientAsync(_cts.Token); }
            catch { return; }
            Interlocked.Increment(ref _accepted);
            _clients.Add(c);
            _ = Serve(c);
        }
    }

    private async Task Serve(TcpClient client)
    {
        using var conn = CancellationTokenSource.CreateLinkedTokenSource(_cts.Token);
        var ct = conn.Token;
        var stream = client.GetStream();
        var writeLock = new SemaphoreSlim(1, 1);
        try
        {
            var key = await ReadHandshake(stream, ct);
            var accept = Convert.ToBase64String(SHA1.HashData(Encoding.ASCII.GetBytes(key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")));
            var resp = "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n" +
                       $"Sec-WebSocket-Accept: {accept}\r\n\r\n";
            await stream.WriteAsync(Encoding.ASCII.GetBytes(resp), ct);

            var publisher = PublishLoop(stream, writeLock, ct);
            await ReadLoop(stream, writeLock, ct);
            conn.Cancel();
            await publisher;
        }
        catch { /* client gone or test over */ }
        finally
        {
            conn.Cancel();
            client.Dispose();
        }
    }

    private async Task PublishLoop(NetworkStream stream, SemaphoreSlim writeLock, CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(200, ct);
                if (Frozen || !Publish) continue;
                var json = "{\"op\":\"publish\",\"topic\":\"/mavros/state\",\"msg\":{" +
                           $"\"connected\":{(FcConnected ? "true" : "false")},\"armed\":{(Armed ? "true" : "false")}," +
                           $"\"mode\":\"{Mode}\"}}}}";
                await Send(stream, writeLock, 0x1, Encoding.UTF8.GetBytes(json), ct);
            }
        }
        catch { /* connection closed */ }
    }

    private async Task ReadLoop(NetworkStream stream, SemaphoreSlim writeLock, CancellationToken ct)
    {
        var head = new byte[2];
        while (!ct.IsCancellationRequested)
        {
            // Frozen: leave the client's bytes (pings) unread and unanswered.
            while (Frozen && !ct.IsCancellationRequested) await Task.Delay(50, ct);
            if (!await ReadExactly(stream, head, ct)) return;
            var opcode = head[0] & 0x0F;
            long len = head[1] & 0x7F;
            if (len == 126)
            {
                var b = new byte[2];
                if (!await ReadExactly(stream, b, ct)) return;
                len = (b[0] << 8) | b[1];
            }
            else if (len == 127)
            {
                var b = new byte[8];
                if (!await ReadExactly(stream, b, ct)) return;
                len = 0;
                foreach (var x in b) len = (len << 8) | x;
            }
            var mask = new byte[4];
            if ((head[1] & 0x80) != 0 && !await ReadExactly(stream, mask, ct)) return;
            var payload = new byte[len];
            if (len > 0 && !await ReadExactly(stream, payload, ct)) return;
            for (var i = 0; i < payload.Length; i++) payload[i] ^= mask[i % 4];

            switch (opcode)
            {
                case 0x1:
                    ClientTexts.Enqueue(Encoding.UTF8.GetString(payload));
                    break;
                case 0x8:
                    return;
                case 0x9:
                    if (!Frozen) await Send(stream, writeLock, 0xA, payload, ct);
                    break;
            }
        }
    }

    private static async Task Send(NetworkStream stream, SemaphoreSlim writeLock, int opcode, byte[] payload, CancellationToken ct)
    {
        var header = payload.Length < 126
            ? new byte[] { (byte)(0x80 | opcode), (byte)payload.Length }
            : new byte[] { (byte)(0x80 | opcode), 126, (byte)(payload.Length >> 8), (byte)payload.Length };
        await writeLock.WaitAsync(ct);
        try
        {
            await stream.WriteAsync(header, ct);
            await stream.WriteAsync(payload, ct);
        }
        finally { writeLock.Release(); }
    }

    private static async Task<string> ReadHandshake(NetworkStream stream, CancellationToken ct)
    {
        var sb = new StringBuilder();
        var one = new byte[1];
        while (!sb.ToString().EndsWith("\r\n\r\n", StringComparison.Ordinal))
        {
            if (await stream.ReadAsync(one, ct) == 0) throw new IOException("closed during handshake");
            sb.Append((char)one[0]);
        }
        foreach (var line in sb.ToString().Split("\r\n"))
            if (line.StartsWith("Sec-WebSocket-Key:", StringComparison.OrdinalIgnoreCase))
                return line["Sec-WebSocket-Key:".Length..].Trim();
        throw new IOException("no Sec-WebSocket-Key");
    }

    private static async Task<bool> ReadExactly(NetworkStream stream, byte[] buf, CancellationToken ct)
    {
        var got = 0;
        while (got < buf.Length)
        {
            var n = await stream.ReadAsync(buf.AsMemory(got), ct);
            if (n == 0) return false;
            got += n;
        }
        return true;
    }

    public void Dispose()
    {
        _cts.Cancel();
        _listener.Stop();
        foreach (var c in _clients)
        {
            try { c.Dispose(); } catch { }
        }
    }
}
