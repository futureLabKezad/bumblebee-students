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
using BumblebeeGcs.Logic.Tests.Fakes;
using BumblebeeGcs.Services;
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

/// <summary>
/// The real MjpegStream against a fake :8080 on 127.0.0.1: one connection per view on tab
/// switches, frames of the old topic never shown, and the video coming back by itself after
/// a server restart or a half-open connection (idle watchdog).
/// </summary>
[Collection("mjpeg sockets")]
public class MjpegSocketTests
{
    private sealed class Frames
    {
        public readonly ConcurrentQueue<(int Id, string Topic)> All = new();
        public Frames(MjpegStream s) => s.FrameReady += (id, bytes) => All.Enqueue((id, FakeMjpegServer.TopicOf(bytes)));
        public int Count => All.Count;
    }

    private static async Task Until(Func<bool> cond, double timeoutSec, string what)
    {
        var start = MonoClock.Now;
        while (!cond())
        {
            if (MonoClock.Now - start > timeoutSec) throw new Xunit.Sdk.XunitException($"not within {timeoutSec} s: {what}");
            await Task.Delay(25);
        }
    }

    [Fact]
    public async Task SwitchingTopics_KeepsExactlyOneConnection_AndNoOldFrames()
    {
        using var server = new FakeMjpegServer();
        var stream = new MjpegStream();
        var frames = new Frames(stream);
        try
        {
            stream.Start(server.Url("/main_camera/image_raw"));
            await Until(() => frames.Count > 0, 3, "first frame");
            for (var i = 0; i < 20; i++)
            {
                stream.Start(server.Url(i % 2 == 0 ? "/aruco_detect/debug" : "/main_camera/image_raw"));
                await Task.Delay(30);
            }
            stream.Start(server.Url("/aruco_detect/debug"));
            var last = stream.CurrentId;
            await Until(() => server.Open == 1, 3, $"exactly one open connection (open: {server.Open})");
            await Until(() => frames.All.Any(f => f.Id == last), 3, "a frame of the last topic");
            await Task.Delay(300);
            Assert.Equal(1, server.Open);
            Assert.All(frames.All.Where(f => f.Id == last), f => Assert.Equal("/aruco_detect/debug", f.Topic));
        }
        finally { stream.Stop(); }
        await Until(() => server.Open == 0, 3, "no connection after Stop");
    }

    [Fact]
    public async Task ServerRestart_TheVideoComesBackByItself()
    {
        using var server = new FakeMjpegServer();
        var stream = new MjpegStream();
        var frames = new Frames(stream);
        try
        {
            stream.Start(server.Url("/main_camera/image_raw"));
            await Until(() => frames.Count > 0, 3, "first frame");
            server.DropAll();
            await Until(() => server.Accepted >= 2, 3, "a new connection (retry after 1.2 s)");
            var before = frames.Count;
            await Until(() => frames.Count > before, 3, "frames again");
            Assert.Equal(1, server.Open);
        }
        finally { stream.Stop(); }
    }

    [Fact]
    public async Task HalfOpenConnection_IsDroppedByTheIdleWatchdog_AndReopened()
    {
        using var server = new FakeMjpegServer();
        // 10 s on the drone (its keep-alive comes every 5 s); 1.5 s keeps the test short.
        var stream = new MjpegStream { IdleTimeoutMs = 1500 };
        var frames = new Frames(stream);
        try
        {
            stream.Start(server.Url("/second_camera/image_raw"));
            await Until(() => frames.Count > 0, 3, "first frame");
            server.Frozen = true;   // TCP open, no bytes: the drone rebooted under us
            var t0 = MonoClock.Now;
            await Until(() => server.Accepted >= 2, 5, "reconnect after the idle timeout");
            Assert.InRange(MonoClock.Now - t0, 1.4, 4.0);
            await Until(() => server.Open == 1, 3, "the half-open connection is closed");
            server.Frozen = false;
            var before = frames.Count;
            await Until(() => frames.Count > before, 4, "frames again");
        }
        finally { stream.Stop(); }
    }
}
