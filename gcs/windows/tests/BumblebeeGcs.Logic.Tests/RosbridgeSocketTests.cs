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
using System.Text.Json;
using BumblebeeGcs.Logic.Tests.Fakes;
using BumblebeeGcs.Models;
using BumblebeeGcs.Services;
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

/// <summary>
/// The real RosbridgeClient against a fake rosbridge on 127.0.0.1 (real time, a few seconds
/// each): Link states, the silent-drop detection (keep-alive 2 s / 4 s) and the reconnect. The store is re-evaluated every 100 ms, as AppState does
/// every 500 ms.
/// </summary>
[Collection("rosbridge sockets")]
public class RosbridgeSocketTests
{
    private sealed class Harness : IDisposable
    {
        public readonly TestUiQueue Ui = new();
        public readonly TelemetryStore Store = new();
        public readonly RosbridgeClient Client;
        private readonly Timer _tick;
        public int Alarms;

        public Harness(int port)
        {
            Client = new RosbridgeClient(Store, Ui, port);
            Store.AlarmRaised += () => Alarms++;
            _tick = new Timer(_ => Ui.TryEnqueue(() => Store.Evaluate(MonoClock.Now)), null, 100, 100);
        }

        public void Connect() => Ui.Run(() => Client.Connect("127.0.0.1"));

        public T Read<T>(Func<TelemetryStore, T> f) => Ui.Run(() => f(Store));

        /// <summary>Seconds until the condition holds; fails the test after the timeout.</summary>
        public async Task<double> WaitFor(Func<TelemetryStore, bool> cond, double timeoutSec, string what)
        {
            var start = MonoClock.Now;
            while (MonoClock.Now - start < timeoutSec)
            {
                if (Read(cond)) return MonoClock.Now - start;
                await Task.Delay(50);
            }
            throw new Xunit.Sdk.XunitException($"not within {timeoutSec} s: {what} (link {Read(s => s.Link)})");
        }

        public void Dispose()
        {
            try { Ui.Run(() => Client.Disconnect()); } catch { }
            _tick.Dispose();
            Ui.Dispose();
        }
    }

    [Fact]
    public async Task FrozenDrone_GoesFrozen_IsDroppedWithin6s_AndComesBack()
    {
        using var server = new FakeRosbridge();
        using var h = new Harness(server.Port);
        h.Connect();
        await h.WaitFor(s => s.Link == LinkState.Ok, 3, "OK");

        server.Frozen = true;   // like kill -STOP: TCP stays open, nothing moves, no pongs
        var frozen = await h.WaitFor(s => s.Link == LinkState.TelemetryFrozen, 4.5, "Telemetry frozen");
        Assert.InRange(frozen, 2.5, 4.5);
        // The screen already says so at ~3 s (above); the keep-alive (2 s ping, 4 s pong, which
        // .NET checks on its own timer) then closes the socket. It must close after "Telemetry
        // frozen", never before: ok -> frozen is what sounds the FC-lost alarm of an armed drone.
        var dropped = await h.WaitFor(s => !s.RosConnected, 7, "drop");
        Assert.True(dropped > 0.2, "the socket closed before the screen said Telemetry frozen");
        Assert.True(frozen + dropped <= 7.5, $"silent drop noticed after {frozen + dropped:F1} s");
        Assert.Equal(LinkState.NoDrone, h.Read(s => s.Link));
        var lost = h.Read(s => s.Messages.Entries.First(e => e.Key == LinkLog.Key).Text);
        Assert.StartsWith("rosbridge lost (no answer to ping for 4 s) — reconnecting…", lost);

        server.Frozen = false;
        await h.WaitFor(s => s.Link == LinkState.Ok, 8, "OK again after the reconnect");
        Assert.True(server.Accepted >= 2);
        // One collapsing link line, not a line per attempt.
        Assert.Single(h.Read(s => s.Messages.Entries.Where(e => e.Key == LinkLog.Key).ToList()));
    }

    [Fact]
    public async Task RosbridgeAliveButSilent_StaysFrozen_OnTheSameSocket()
    {
        // MAVROS stopped, rosbridge still answers pings: the Link tile says "Telemetry frozen"
        // and keeps saying it (as on the Mac); a reconnect would only flip it to "No drone".
        using var server = new FakeRosbridge();
        using var h = new Harness(server.Port);
        h.Connect();
        await h.WaitFor(s => s.Link == LinkState.Ok, 3, "OK");

        server.Publish = false;
        var frozen = await h.WaitFor(s => s.Link == LinkState.TelemetryFrozen, 4.5, "Telemetry frozen");
        Assert.InRange(frozen, 2.5, 4.5);
        await Task.Delay(8000);
        Assert.Equal(LinkState.TelemetryFrozen, h.Read(s => s.Link));
        Assert.True(h.Read(s => s.RosConnected));
        Assert.Equal(1, server.Accepted);
        Assert.Null(h.Read(s => s.Armed));

        server.Publish = true;
        await h.WaitFor(s => s.Link == LinkState.Ok, 3, "OK again on the same socket");
        Assert.Equal(1, server.Accepted);
    }

    [Fact]
    public async Task FcGone_WhileArmed_FcNotConnected_ArmedLinkLost_AlarmOnce()
    {
        using var server = new FakeRosbridge { Armed = true, Mode = "OFFBOARD" };
        using var h = new Harness(server.Port);
        h.Connect();
        await h.WaitFor(s => s.Link == LinkState.Ok && s.Armed == true, 3, "OK, armed");
        Assert.Equal(Controller.Program, h.Read(s => s.InControl));

        server.Armed = false;          // MAVROS reports armed=false once the FC is gone
        server.FcConnected = false;
        await h.WaitFor(s => s.Link == LinkState.FcNotConnected, 2, "FC not connected");
        await Task.Delay(1000);
        Assert.Null(h.Read(s => s.Armed));
        Assert.Equal("ARMED? link lost", h.Read(s => ArmedLogic.Display(s.Armed, s.LastKnownArmed).Value));
        Assert.Equal(1, h.Read(_ => h.Alarms));
        Assert.True(h.Read(s => s.FcAlarm.BannerVisible));

        server.FcConnected = true;
        await h.WaitFor(s => s.Link == LinkState.Ok, 2, "OK again");
        Assert.False(h.Read(s => s.FcAlarm.BannerVisible));
        Assert.Equal("DISARMED", h.Read(s => ArmedLogic.Display(s.Armed, s.LastKnownArmed).Value));
    }

    [Fact]
    public async Task NoServer_IsNoDrone_WithOneCollapsedLine()
    {
        var port = FreePort();
        // How long THIS machine takes to refuse a connect to a closed local port. Windows Server (CI) refuses
        // at once; Windows 11 sends the SYN twice more first (2.06 s here, 25.11.2026; with those retries
        // switched off on the same port: 0 ms). The app is right to wait for the refusal, so the wait below
        // counts it: attempt 3 fails after 3 refusals + 2 reconnect delays. The margin stays the 3 s it was
        // (9 s = 2 x 3 s + 3 s with an instant refusal); every assertion is unchanged.
        var refusal = RefusalSeconds(port);
        Assert.True(refusal < 4.0, $"a closed local port was refused only after {refusal:F1} s: that is the client's 5 s connect timeout, not a refusal");
        using var h = new Harness(port);
        h.Connect();
        // 9 is the old number, on purpose not read from RosbridgeClient.ReconnectDelayMs: a longer reconnect
        // delay in the app must still fail here, as before.
        await h.WaitFor(s => s.Messages.Entries.Count == 1 && s.Messages.Entries[0].Text.Contains("attempt 3"),
            9 + 3 * refusal,
            "three failed attempts in one line");
        Assert.Equal(LinkState.NoDrone, h.Read(s => s.Link));
        var text = h.Read(s => s.Messages.Entries[0].Text);
        Assert.StartsWith("rosbridge not reachable (network error", text);
        Assert.Contains("— retrying…", text);
    }

    [Fact]
    public async Task OnlySubscribeIsEverSent()
    {
        using var server = new FakeRosbridge();
        using var h = new Harness(server.Port);
        h.Connect();
        await h.WaitFor(s => s.Link == LinkState.Ok, 3, "OK");
        var ops = server.ClientTexts.Select(t => JsonDocument.Parse(t).RootElement.GetProperty("op").GetString()).ToList();
        Assert.Equal(6, ops.Count);
        Assert.All(ops, op => Assert.Equal("subscribe", op));
        var topics = server.ClientTexts.Select(t => JsonDocument.Parse(t).RootElement.GetProperty("topic").GetString()).ToList();
        Assert.Contains("/mavros/state", topics);
        Assert.Contains("/mavros/battery", topics);
    }

    /// <summary>Seconds until the OS refuses a plain TCP connect to a closed port on 127.0.0.1 (the worst of two tries).</summary>
    private static double RefusalSeconds(int port)
    {
        var worst = 0.0;
        for (var i = 0; i < 2; i++)
        {
            using var s = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            var start = MonoClock.Now;
            var refused = false;
            try { s.Connect(IPAddress.Loopback, port); }
            catch (SocketException e) when (e.SocketErrorCode == SocketError.ConnectionRefused) { refused = true; }
            Assert.True(refused, $"port {port} on 127.0.0.1 is not closed: the test needs a port nobody listens on");
            worst = Math.Max(worst, MonoClock.Now - start);
        }
        return worst;
    }

    private static int FreePort()
    {
        var l = new TcpListener(IPAddress.Loopback, 0);
        l.Start();
        var port = ((IPEndPoint)l.LocalEndpoint).Port;
        l.Stop();
        return port;
    }
}
