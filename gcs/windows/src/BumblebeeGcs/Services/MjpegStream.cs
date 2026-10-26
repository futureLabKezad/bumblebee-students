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

namespace BumblebeeGcs.Services;

/// <summary>
/// Нативный MJPEG (multipart/x-mixed-replace) клиент. Стримит с
/// http://host:8080/stream?..., режет поток по JPEG SOI/EOI маркерам и отдаёт
/// последний полный кадр. Порт MJPEGStream.swift: при пачке кадров декодируется
/// только самый свежий; авто-ретрай через 1.2 с; лимит буфера 4 МБ.
/// Одно соединение на поток: Start сначала отменяет прошлое. Сторож простоя 10 с
/// (сервер дрона шлёт keep-alive каждые 5 с): полуоткрытое соединение после
/// перезагрузки дрона рвётся само, и видео возвращается без участия пользователя.
/// </summary>
public sealed class MjpegStream
{
    /// <summary>(stream id, сырые байты JPEG последнего полного кадра) — фоновый поток!
    /// Id растёт с каждым Start: кадр старого топика узнаётся по id != CurrentId.</summary>
    public event Action<int, byte[]>? FrameReady;
    public event Action<bool>? ReceivingChanged;

    /// <summary>No byte for this long: the connection is dead (the server's keep-alive comes every 5 s).</summary>
    public const int DefaultIdleTimeoutMs = 10_000;
    public const int RetryDelayMs = 1200;

    /// <summary>Idle watchdog of this stream (tests use a shorter one).</summary>
    public int IdleTimeoutMs { get; init; } = DefaultIdleTimeoutMs;

    private static readonly HttpClient Http = new(new SocketsHttpHandler
    {
        ConnectTimeout = TimeSpan.FromSeconds(5),
        UseProxy = false,   // дрон в локальной сети, школьный прокси до него не дотянется
    })
    { Timeout = Timeout.InfiniteTimeSpan };

    private Uri? _currentUrl;
    private CancellationTokenSource? _cts;
    private volatile int _id;

    /// <summary>Id of the running stream (0 = none).</summary>
    public int CurrentId => _id;

    /// <param name="force">Restart even when the URL is the same (Reconnect).</param>
    public void Start(Uri url, bool force = false)
    {
        if (!force && url == _currentUrl && _cts is not null) return;
        Stop();
        _currentUrl = url;
        var cts = new CancellationTokenSource();
        _cts = cts;
        var id = ++_id;
        _ = RunAsync(url, id, cts.Token);
    }

    public void Stop()
    {
        if (_cts is not null)
        {
            _cts.Cancel();   // closes the old HTTP connection before a new one opens
            _cts = null;
            _id++;
        }
        _currentUrl = null;
        ReceivingChanged?.Invoke(false);
    }

    private async Task RunAsync(Uri url, int id, CancellationToken ct)
    {
        var buffer = new FrameBuffer();
        var chunk = new byte[64 * 1024];
        while (!ct.IsCancellationRequested)
        {
            buffer.Clear();
            try
            {
                using var idle = CancellationTokenSource.CreateLinkedTokenSource(ct);
                idle.CancelAfter(IdleTimeoutMs);
                using var req = new HttpRequestMessage(HttpMethod.Get, url);
                using var resp = await Http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, idle.Token);
                await using var stream = await resp.Content.ReadAsStreamAsync(idle.Token);
                while (true)
                {
                    idle.CancelAfter(IdleTimeoutMs);
                    var n = await stream.ReadAsync(chunk, idle.Token);
                    if (n <= 0) break;
                    buffer.Append(chunk, n);
                    if (buffer.ExtractLastFrame() is byte[] frame && !ct.IsCancellationRequested)
                    {
                        FrameReady?.Invoke(id, frame);
                        ReceivingChanged?.Invoke(true);
                    }
                    // Страховка от бесконечного роста, если полный кадр не приходит.
                    if (buffer.Count > 4 * 1024 * 1024) buffer.Clear();
                }
            }
            catch when (ct.IsCancellationRequested) { return; }
            catch { /* сервер перезапускается / wifi моргнул / сторож простоя */ }

            if (ct.IsCancellationRequested) return;
            ReceivingChanged?.Invoke(false);
            try { await Task.Delay(RetryDelayMs, ct); } catch { return; }
        }
    }

    /// <summary>Растущий байтовый буфер с выделением последнего полного JPEG (SOI..EOI).</summary>
    private sealed class FrameBuffer
    {
        private byte[] _data = new byte[256 * 1024];
        private int _len;

        public int Count => _len;

        public void Clear() => _len = 0;

        public void Append(byte[] chunk, int n)
        {
            if (_len + n > _data.Length)
                Array.Resize(ref _data, Math.Max(_data.Length * 2, _len + n));
            Array.Copy(chunk, 0, _data, _len, n);
            _len += n;
        }

        /// <summary>
        /// Съедает все полные JPEG в буфере, возвращая только ПОСЛЕДНИЙ (свежайший).
        /// Мусор до SOI отбрасывается.
        /// </summary>
        public byte[]? ExtractLastFrame()
        {
            byte[]? last = null;
            var pos = 0;
            while (true)
            {
                var start = IndexOfMarker(pos, 0xFF, 0xD8);
                if (start < 0) break;
                var end = IndexOfMarker(start + 2, 0xFF, 0xD9);
                if (end < 0)
                {
                    // Полного кадра ещё нет — компактируем, отбросив мусор до SOI.
                    if (start > 0) Compact(start);
                    return last;
                }
                var frameLen = end + 2 - start;
                last = new byte[frameLen];
                Array.Copy(_data, start, last, 0, frameLen);
                pos = end + 2;
            }
            if (pos > 0) Compact(pos);
            return last;
        }

        private int IndexOfMarker(int from, byte a, byte b)
        {
            for (var i = Math.Max(0, from); i < _len - 1; i++)
                if (_data[i] == a && _data[i + 1] == b) return i;
            return -1;
        }

        private void Compact(int from)
        {
            Array.Copy(_data, from, _data, 0, _len - from);
            _len -= from;
        }
    }
}
