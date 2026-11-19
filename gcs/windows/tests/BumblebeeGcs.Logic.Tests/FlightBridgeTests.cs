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

using System.Text.Json;
using BumblebeeGcs.Logic;
using BumblebeeGcs.Logic.Tests.Fakes;
using BumblebeeGcs.Services;
using Xunit;

namespace BumblebeeGcs.Logic.Tests;

/// <summary>
/// The «Полёт» page talks to the drone only through FlightBridge, and the page is not
/// trusted: only the six commands; a takeoff only with a permission the bridge itself saw
/// the drone give, three check marks AND the app's own dialog; Stop always.
/// </summary>
public class FlightBridgeTests
{
    private const string Sha = "8a8ab61a53b9c6a5";
    private const string Token = "0123456789abcdef0123456789abcdef";
    private const string Program = "import drone\ndrone.takeoff(0.9)\ndrone.land()";
    private const string Host = "10.0.0.7";

    private static string StatusJson(bool running = false, bool confirmed = true, string sha = Sha) =>
        "{\"running\":" + (running ? "true" : "false") + ",\"map\":{\"active\":{\"sha\":\"" + sha
        + "\",\"name\":\"field_real\",\"n\":20},\"confirmed\":" + (confirmed ? "true" : "false") + "}}";

    private static string CheckJson(string token = Token, string sha = Sha) =>
        "{\"check\":{\"ok\":true},\"map\":{\"sha\":\"" + sha + "\",\"name\":\"field_real\",\"n\":20},\"map_confirmed\":true,"
        + "\"token\":\"" + token + "\",\"token_ttl_s\":120.0}";

    private sealed class FakeApi : IMissionApi
    {
        public List<string> Calls { get; } = new();
        public MissionReply Status = new(200, StatusJson());
        public MissionReply Check = new(200, CheckJson());
        public MissionReply Next = new(200, """{"ok":true}""");
        public MissionReply StartReply = new(200, "{\"started\":true,\"run\":\"run_1\",\"map_sha\":\"" + Sha + "\"}");
        public (string Host, string Program, string Token, string MapSha, bool Battery, bool Rc, bool People)? Started;
        public JsonElement? Map;
        public long Since = -1;
        public Task? Hold;                       // a request waits for this (the drone is slow)
        public bool StatusThrows;

        private async Task<MissionReply> After(MissionReply reply) { if (Hold is { } h) await h; return reply; }

        public Task<MissionReply> MapStatusAsync(string host) { Calls.Add("map_status"); return After(Next); }
        public Task<MissionReply> PutMapAsync(string host, JsonElement map) { Calls.Add("map_put"); Map = map.Clone(); return After(Next); }
        public Task<MissionReply> CheckAsync(string host, string program) { Calls.Add("check:" + program); return After(Check); }
        public Task? StartHold;                  // the start request is on its way for this long
        public async Task<MissionReply> StartAsync(string host, string program, string token, string mapSha, bool battery, bool rc, bool people)
        {
            Calls.Add("start");
            Started = (host, program, token, mapSha, battery, rc, people);
            if (StartHold is { } h) await h;
            return StartReply;
        }
        public Task<MissionReply> StopAsync(string host) { Calls.Add("stop"); return After(Next); }
        public Task<MissionReply> StatusAsync(string host, long since)
        {
            Calls.Add("status");
            Since = since;
            if (StatusThrows) throw new InvalidOperationException("boom");
            return After(Status);
        }
    }

    private sealed class Rig
    {
        public FakeApi Api { get; } = new();
        public List<TakeoffRequest> Asked { get; } = new();
        public Func<TakeoffRequest, Task<TakeoffAnswer>> Answer = _ => Task.FromResult(TakeoffAnswer.Go);
        public string DroneHost = Host;
        public long Now = 10_000;
        public FlightBridge Bridge { get; }

        public Rig()
        {
            Bridge = new FlightBridge(Api, r => { Asked.Add(r); return Answer(r); }, () => (DroneHost, "Bumblebee-20EC"), () => Now);
        }

        public async Task<JsonElement> Send(string message) => Reply(await Bridge.HandleAsync(message));
        public Task<JsonElement> CheckProgram(string program = Program) =>
            Send(JsonSerializer.Serialize(new { bb = 1, id = 3, cmd = "mission_check", body = new { program } }));
        /// <summary>The honest page: check on the drone, then «ВЗЛЁТ». A second passes first: the message budget.</summary>
        public async Task<JsonElement> CheckThenStart(string program = Program)
        {
            Now += 1000;
            await CheckProgram(program);
            return await Send(Start(program: program));
        }
    }

    private static JsonElement Reply(string? json)
    {
        Assert.NotNull(json);
        using var doc = JsonDocument.Parse(json!);
        return doc.RootElement.Clone();
    }

    private static string Code(JsonElement reply) => reply.GetProperty("data").GetProperty("code").GetString() ?? "";

    private static string Start(bool battery = true, bool rc = true, bool people = true, string token = Token, string program = Program) =>
        JsonSerializer.Serialize(new
        {
            bb = 1, id = 5, cmd = "mission_start",
            body = new { program, token, confirm = new { battery_multimeter = battery, rc_in_hand_ch8 = rc, people_clear = people, takeoff_clicked = true } },
        });

    private const string StopMsg = """{"bb":1,"id":9,"cmd":"mission_stop"}""";

    [Fact]
    public async Task WhatIsNotABridgeMessageGetsNoReply()
    {
        var rig = new Rig();
        foreach (var bad in new[] { "not json", "[1,2]", "{}", """{"bb":2,"id":1,"cmd":"hello"}""", """{"bb":1,"cmd":"hello"}""",
                                    """{"bb":1,"id":"x","cmd":"hello"}""", """{"bb":1,"id":1,"cmd":5}""", """{"bb":1.5,"id":1,"cmd":"hello"}""",
                                    "{\"bb\":1,\"id\":1,\"cmd\":\"\\ud800\"}" })
            Assert.Null(await rig.Bridge.HandleAsync(bad));
        Assert.Null(await rig.Bridge.HandleAsync("{\"bb\":1,\"id\":1,\"cmd\":\"hello\",\"pad\":\"" + new string('x', FlightBridge.MaxMessageChars) + "\"}"));
        Assert.Empty(rig.Api.Calls);
    }

    [Fact]
    public async Task HelloNamesTheDroneTheAppIsConnectedTo()
    {
        var rig = new Rig();
        var r = await rig.Send("""{"bb":1,"id":7,"cmd":"hello","body":null}""");
        Assert.Equal(7, r.GetProperty("id").GetInt64());
        Assert.Equal(200, r.GetProperty("code").GetInt32());
        Assert.Equal(Host, r.GetProperty("data").GetProperty("host").GetString());
        Assert.True(r.GetProperty("data").GetProperty("connected").GetBoolean());
        var none = new Rig { DroneHost = "" };
        Assert.False((await none.Send("""{"bb":1,"id":1,"cmd":"hello"}""")).GetProperty("data").GetProperty("connected").GetBoolean());
    }

    [Fact]
    public async Task OnlyTheSixCommandsExist()
    {
        var rig = new Rig();
        foreach (var cmd in new[] { "arm", "set_param", "navigate", "exec", "", "MISSION_STOP" })
        {
            var r = await rig.Send(JsonSerializer.Serialize(new { bb = 1, id = 1, cmd, body = new { x = 1 } }));
            Assert.Equal(0, r.GetProperty("code").GetInt32());
            Assert.Equal("bad_request", Code(r));
        }
        Assert.Empty(rig.Api.Calls);
    }

    [Fact]
    public async Task MapAndCheckAndStatusArePassedOn()
    {
        var rig = new Rig();
        var put = await rig.Send("""{"bb":1,"id":1,"cmd":"map_put","body":{"map":{"name":"m","markers":[]}}}""");
        Assert.Equal(200, put.GetProperty("code").GetInt32());
        Assert.True(put.GetProperty("data").GetProperty("ok").GetBoolean());
        Assert.Equal("m", rig.Api.Map!.Value.GetProperty("name").GetString());
        Assert.Equal(0, (await rig.Send("""{"bb":1,"id":2,"cmd":"map_put","body":{"map":"text"}}""")).GetProperty("code").GetInt32());
        Assert.Equal(Token, (await rig.CheckProgram("import drone")).GetProperty("data").GetProperty("token").GetString());
        await rig.Send("""{"bb":1,"id":4,"cmd":"mission_status","since":42}""");
        Assert.Equal(42, rig.Api.Since);
        await rig.Send("""{"bb":1,"id":5,"cmd":"mission_status","since":-9}""");
        Assert.Equal(0, rig.Api.Since);
        Assert.Equal(new[] { "map_put", "check:import drone", "status", "status" }, rig.Api.Calls);
        var tooLong = JsonSerializer.Serialize(new { bb = 1, id = 6, cmd = "mission_check", body = new { program = new string('x', FlightBridge.MaxProgramChars + 1) } });
        Assert.Equal(0, (await rig.Send(tooLong)).GetProperty("code").GetInt32());
    }

    [Fact]
    public async Task TakeoffNeedsTheThreeMarksAndAWellFormedToken()
    {
        var rig = new Rig();
        await rig.CheckProgram();
        foreach (var msg in new[] { Start(battery: false), Start(rc: false), Start(people: false), Start(token: ""), Start(token: "zz-not-hex-zz"),
                                    Start(token: new string('a', 7)), Start(token: new string('a', 129)) })
            Assert.Equal(0, (await rig.Send(msg)).GetProperty("code").GetInt32());
        Assert.Empty(rig.Asked);                       // the dialog is not even shown
        Assert.DoesNotContain("status", rig.Api.Calls);
        Assert.DoesNotContain("start", rig.Api.Calls);
    }

    [Fact]
    public async Task TheDialogOpensOnlyForAPermissionTheBridgeSawTheDroneGive()
    {
        var rig = new Rig();
        Assert.Equal("bad_token", Code(await rig.Send(Start())));                       // no check at all
        await rig.CheckProgram();
        Assert.Equal("bad_token", Code(await rig.Send(Start(token: "00000000"))));      // a made-up token
        Assert.Equal("changed", Code(await rig.Send(Start(program: Program + "\n# more"))));
        rig.Now += (FlightBridge.PermissionSeconds + 1) * 1000L;
        Assert.Equal("bad_token", Code(await rig.Send(Start())));                       // too old
        rig.Api.Check = new MissionReply(200, """{"check":{"ok":false,"errors":[{"text":"x"}]},"map_confirmed":true}""");
        await rig.CheckProgram();
        Assert.Equal("bad_token", Code(await rig.Send(Start())));                       // the drone gave none
        rig.Api.Check = new MissionReply(200, CheckJson());
        await rig.CheckProgram();
        rig.DroneHost = "10.0.0.8";
        Assert.Equal("bad_token", Code(await rig.Send(Start())));                       // given by another drone
        Assert.Empty(rig.Asked);
        Assert.DoesNotContain("start", rig.Api.Calls);
    }

    [Fact]
    public async Task TakeoffIsAskedInTheAppWithTheMapTheDroneHas()
    {
        var rig = new Rig();
        var r = await rig.CheckThenStart();
        Assert.Equal(200, r.GetProperty("code").GetInt32());
        Assert.Equal("run_1", r.GetProperty("data").GetProperty("run").GetString());
        Assert.Equal(new TakeoffRequest(Host, "field_real", Sha, 20, 3, FlightBridge.Sha256Hex(Program)), Assert.Single(rig.Asked));
        Assert.Equal((Host, Program, Token, Sha, true, true, true), rig.Api.Started);
        Assert.Equal(new[] { "check:" + Program, "status", "start" }, rig.Api.Calls);
        Assert.True(rig.Bridge.MissionActive);
    }

    [Fact]
    public async Task OnePermissionOpensTheDialogOnceAndCancelIsFollowedByAPause()
    {
        var rig = new Rig { Answer = _ => Task.FromResult(TakeoffAnswer.Declined()) };
        Assert.Equal("cancelled", Code(await rig.CheckThenStart()));
        Assert.Single(rig.Asked);
        Assert.Null(rig.Api.Started);
        Assert.Equal("cancelled", Code(await rig.CheckThenStart()));                     // the pause: no window, even after a new check
        Assert.Single(rig.Asked);
        rig.Now += FlightBridge.CancelPauseSeconds * 1000L + 1;
        Assert.Equal("bad_token", Code(await rig.Send(Start())));                       // that permission went with the refused try
        Assert.Single(rig.Asked);
        Assert.Equal("cancelled", Code(await rig.CheckThenStart()));                     // a new check after the pause: asked again
        Assert.Equal(2, rig.Asked.Count);
    }

    [Fact]
    public async Task AWindowThatWasNotShownGivesItsReasonAndNoPause()
    {
        var rig = new Rig { Answer = _ => Task.FromResult(TakeoffAnswer.NotAsked("the Flight section is not shown now")) };
        var r = await rig.CheckThenStart();
        Assert.Equal("not_asked", Code(r));
        Assert.Equal("the Flight section is not shown now", r.GetProperty("data").GetProperty("error").GetString());
        rig.Answer = _ => Task.FromResult(TakeoffAnswer.Go);
        Assert.Equal(200, (await rig.CheckThenStart()).GetProperty("code").GetInt32());   // at once: no pause
        var empty = await new Rig { Answer = _ => Task.FromResult(default(TakeoffAnswer)) }.CheckThenStart();   // an answer nobody filled in is «no»
        Assert.Equal("not_asked", Code(empty));
        Assert.False(string.IsNullOrEmpty(empty.GetProperty("data").GetProperty("error").GetString()));
    }

    [Fact]
    public async Task AStopWhileTheStartIsOnItsWayWins()
    {
        var rig = new Rig();
        var sent = new TaskCompletionSource();
        rig.Api.StartHold = sent.Task;
        var flying = new List<bool>();
        rig.Bridge.TakeoffInFlightChanged += () => flying.Add(rig.Bridge.TakeoffInFlight);
        await rig.CheckProgram();
        var start = rig.Bridge.HandleAsync(Start());
        Assert.True(rig.Bridge.TakeoffInFlight);
        Assert.Equal(200, (await rig.Send(StopMsg)).GetProperty("code").GetInt32());      // it may reach the drone first: «нечего останавливать»
        sent.SetResult();
        Assert.Equal("stopped", Code(Reply(await start)));                               // so the bridge stops again after the start
        Assert.Equal(new[] { "check:" + Program, "status", "start", "stop", "stop" }, rig.Api.Calls);
        Assert.Equal(new[] { true, false }, flying);

        var app = new Rig();                                                             // the same with the app's own STOP FLIGHT
        var sent2 = new TaskCompletionSource();
        app.Api.StartHold = sent2.Task;
        await app.CheckProgram();
        var start2 = app.Bridge.HandleAsync(Start());
        app.Bridge.NoteStop();
        sent2.SetResult();
        Assert.Equal("stopped", Code(Reply(await start2)));
        Assert.Equal("stop", app.Api.Calls[^1]);
    }

    [Fact]
    public async Task AStartWithoutAnAnswerIsFollowedByAStop()
    {
        var rig = new Rig();
        rig.Api.StartReply = FlightBridge.Problem("silent", "no_answer");
        var r = await rig.CheckThenStart();
        Assert.Equal("no_answer", Code(r));
        Assert.Contains("STOP", r.GetProperty("data").GetProperty("error").GetString());
        Assert.Equal("stop", rig.Api.Calls[^1]);
        Assert.False(rig.Bridge.MissionActive);
    }

    [Fact]
    public async Task NoDialogWhenAMissionRunsOrTheMapIsNotTheCheckedOneOrTheDroneIsSilent()
    {
        var rig = new Rig();
        rig.Api.Status = new MissionReply(200, StatusJson(running: true));
        Assert.Equal("busy", Code(await rig.CheckThenStart()));
        rig.Api.Status = new MissionReply(200, """{"map":{"active":null,"confirmed":true}}""");     // «running» missing: taken as running
        Assert.Equal("busy", Code(await rig.CheckThenStart()));
        rig.Api.Status = new MissionReply(200, StatusJson(confirmed: false));
        Assert.Equal("map_not_confirmed", Code(await rig.CheckThenStart()));
        rig.Api.Status = new MissionReply(200, """{"running":false,"map":{"active":null,"confirmed":false}}""");
        Assert.Equal("map_not_confirmed", Code(await rig.CheckThenStart()));
        rig.Api.Status = new MissionReply(200, StatusJson(sha: "ffff0000ffff0000"));                // another map than the checked one
        Assert.Equal("changed", Code(await rig.CheckThenStart()));
        rig.Api.Status = FlightBridge.Problem("silent", "no_answer");
        Assert.Equal("no_answer", Code(await rig.CheckThenStart()));
        rig.Api.Status = new MissionReply(200, "<html>");
        Assert.Equal("bad_reply", Code(await rig.CheckThenStart()));
        Assert.Empty(rig.Asked);
        Assert.Null(rig.Api.Started);
    }

    [Fact]
    public async Task WhileTheDialogIsOpenTheMapAndTheProgramStayAndStopStillWorks()
    {
        var rig = new Rig();
        var answer = new TaskCompletionSource<TakeoffAnswer>();
        rig.Answer = _ => answer.Task;
        await rig.CheckProgram();
        var first = rig.Bridge.HandleAsync(Start());
        Assert.Equal("busy", Code(await rig.Send(Start())));
        Assert.Equal("busy", Code(await rig.Send("""{"bb":1,"id":1,"cmd":"map_put","body":{"map":{"name":"other","markers":[]}}}""")));
        Assert.Equal("busy", Code(await rig.CheckProgram("import drone")));
        Assert.Equal(200, (await rig.Send("""{"bb":1,"id":2,"cmd":"mission_status","since":0}""")).GetProperty("code").GetInt32());
        Assert.Null(rig.Api.Map);
        Assert.DoesNotContain("check:import drone", rig.Api.Calls);
        answer.SetResult(TakeoffAnswer.Go);
        Assert.Equal(200, Reply(await first).GetProperty("code").GetInt32());
        Assert.Single(rig.Api.Calls, c => c == "start");

        var stopped = new Rig();                                 // a Stop while the window is open: sent, and no takeoff after «yes»
        var late = new TaskCompletionSource<TakeoffAnswer>();
        stopped.Answer = _ => late.Task;
        await stopped.CheckProgram();
        var second = stopped.Bridge.HandleAsync(Start());
        Assert.Equal(200, (await stopped.Send(StopMsg)).GetProperty("code").GetInt32());
        late.SetResult(TakeoffAnswer.Go);
        Assert.Equal("stopped", Code(Reply(await second)));
        Assert.Null(stopped.Api.Started);
        Assert.Single(stopped.Api.Calls, c => c == "stop");
    }

    [Fact]
    public async Task AnotherDroneWhileTheDialogIsOpenMeansNoStart()
    {
        var rig = new Rig();
        rig.Answer = _ => { rig.DroneHost = "10.0.0.8"; return Task.FromResult(TakeoffAnswer.Go); };     // the app was switched meanwhile
        Assert.Equal("cancelled", Code(await rig.CheckThenStart()));
        Assert.Null(rig.Api.Started);
    }

    [Fact]
    public async Task AMissionStartedWithAnotherMapThanShownIsStoppedAtOnce()
    {
        var rig = new Rig();
        rig.Api.StartReply = new MissionReply(200, """{"started":true,"run":"run_1","map_sha":"1111222233334444"}""");
        Assert.Equal("map_mismatch", Code(await rig.CheckThenStart()));
        Assert.Equal("stop", rig.Api.Calls[^1]);
    }

    [Fact]
    public async Task StopAlwaysGoesThrough()
    {
        var rig = new Rig { DroneHost = "" };
        Assert.Equal(200, (await rig.Send(StopMsg)).GetProperty("code").GetInt32());
        for (var i = 0; i < FlightBridge.MaxMessagesPerSecond + 5; i++) await rig.Bridge.HandleAsync("""{"bb":1,"id":1,"cmd":"hello"}""");
        Assert.Null(await rig.Bridge.HandleAsync("""{"bb":1,"id":1,"cmd":"hello"}"""));              // over the budget
        // A Stop over the budget is not parsed and not answered, but it still goes to the drone -- once a second at most.
        Assert.Null(await rig.Bridge.HandleAsync(StopMsg));
        Assert.Equal(2, rig.Api.Calls.Count(c => c == "stop"));
        Assert.Null(await rig.Bridge.HandleAsync(StopMsg));
        Assert.Equal(2, rig.Api.Calls.Count(c => c == "stop"));
        rig.Now += 1000;
        Assert.Equal(200, (await rig.Send(StopMsg)).GetProperty("code").GetInt32());
        Assert.Equal(3, rig.Api.Calls.Count(c => c == "stop"));
    }

    [Fact]
    public async Task ThePageCannotFloodTheAppOrTheDrone()
    {
        var rig = new Rig();
        const string status = """{"bb":1,"id":1,"cmd":"mission_status","since":0}""";
        for (var i = 0; i < FlightBridge.MaxMessagesPerSecond; i++) Assert.NotNull(await rig.Bridge.HandleAsync(status));
        Assert.Null(await rig.Bridge.HandleAsync(status));                                 // the 21st in a second is dropped
        Assert.Equal(FlightBridge.MaxMessagesPerSecond, rig.Api.Calls.Count);
        var big = "{\"bb\":1,\"id\":1,\"cmd\":\"hello\",\"pad\":\"" + new string('x', FlightBridge.MaxCharsPerSecond / 3) + "\"}";
        var chars = new Rig();                                                              // and so is what is over a million characters a second
        Assert.NotNull(await chars.Bridge.HandleAsync(big));
        Assert.NotNull(await chars.Bridge.HandleAsync(big));
        Assert.Null(await chars.Bridge.HandleAsync(big));
        rig.Now += 1000;
        Assert.NotNull(await rig.Bridge.HandleAsync(status));

        var held = new Rig();                                                               // one request of a kind at a time
        var gate = new TaskCompletionSource();
        held.Api.Hold = gate.Task;
        var first = held.Bridge.HandleAsync(status);
        Assert.Equal("busy", Code(await held.Send(status)));
        var stop1 = held.Bridge.HandleAsync(StopMsg);
        var stop2 = held.Bridge.HandleAsync(StopMsg);
        gate.SetResult();
        Assert.Equal(200, Reply(await first).GetProperty("code").GetInt32());
        Assert.Equal(200, Reply(await stop1).GetProperty("code").GetInt32());
        Assert.Equal(200, Reply(await stop2).GetProperty("code").GetInt32());
        Assert.Single(held.Api.Calls, c => c == "status");
        Assert.Single(held.Api.Calls, c => c == "stop");                                    // two stops, one request
        Assert.Equal(200, (await held.Send(status)).GetProperty("code").GetInt32());
    }

    [Fact]
    public async Task AFailureInsideATakeoffLeavesTheBridgeUsable()
    {
        var rig = new Rig();
        rig.Api.StatusThrows = true;
        Assert.Equal("app_error", Code(await rig.CheckThenStart()));
        rig.Api.StatusThrows = false;
        Assert.Equal(200, (await rig.CheckThenStart()).GetProperty("code").GetInt32());
    }

    [Fact]
    public async Task MissionActiveFollowsTheStartAndTheStatus()
    {
        var rig = new Rig();
        var changes = 0;
        rig.Bridge.MissionActiveChanged += () => changes++;
        await rig.CheckThenStart();
        Assert.True(rig.Bridge.MissionActive);
        rig.Now += 1000;
        await rig.Send("""{"bb":1,"id":4,"cmd":"mission_status","since":0}""");            // {"running":false,...}
        Assert.False(rig.Bridge.MissionActive);
        Assert.Equal(2, changes);
    }

    [Fact]
    public void TheTakeoffTextCannotBeFakedByAName()
    {
        var name = "field_real», 20 markers, sha 8a8ab61a53b9 «\nDrone 10.0.0.9";
        var text = TakeoffText.Body(new TakeoffRequest(Host, name, "1f3c1f3c1f3c1f3c", 12, 25, FlightBridge.Sha256Hex(Program)), Host, "OK");
        var lines = text.Split('\n');
        Assert.Equal("Drone 10.0.0.7 will arm the motors and fly the program.", lines[0]);
        Assert.StartsWith("Program: 25 lines, sha " + FlightBridge.Sha256Hex(Program)[..12], lines[1]);
        Assert.Equal("Map on the drone: 12 markers, sha 1f3c1f3c1f3c.", lines[2]);
        Assert.StartsWith("Map name: ", lines[3]);
        Assert.DoesNotContain('»', lines[3]);
        Assert.DoesNotContain(',', lines[3]);
        Assert.True(TakeoffText.SafeName(name).Length <= TakeoffText.MaxNameChars);
        Assert.Equal(7, lines.Length);                                   // the name added no line
        Assert.Equal("(no name)", TakeoffText.SafeName("«»,;\n"));
        Assert.Equal("abc123", TakeoffText.Short("abc123zz"));
    }

    [Fact]
    public async Task ASilentOrBrokenDroneReplyBecomesAnErrorObject()
    {
        var rig = new Rig();
        rig.Api.Next = new MissionReply(502, "<html>bad gateway</html>");
        var r = await rig.Send(StopMsg);
        Assert.Equal(502, r.GetProperty("code").GetInt32());
        Assert.True(r.GetProperty("data").TryGetProperty("error", out _));
    }
}

/// <summary>MissionApi against a local fake server: the six paths, their bodies, a missing answer.</summary>
public class MissionApiSocketTests
{
    private const string Local = "127.0.0.1";

    [Fact]
    public async Task TheSixPathsAndTheirBodies()
    {
        using var server = new FakeMissionServer(_ => (200, """{"ok":true}"""));
        var api = new MissionApi(server.Port);
        using var map = JsonDocument.Parse("""{"name":"m","markers":[{"id":0}]}""");
        Assert.Equal(200, (await api.MapStatusAsync(Local)).Code);
        Assert.Equal(200, (await api.PutMapAsync(Local, map.RootElement)).Code);
        Assert.Equal(200, (await api.CheckAsync(Local, "import drone  # привет")).Code);
        Assert.Equal(200, (await api.StartAsync(Local, "p", "abcd", "8a8a", true, true, false)).Code);
        Assert.Equal(200, (await api.StopAsync(Local)).Code);
        Assert.Equal(200, (await api.StatusAsync(Local, 7)).Code);

        var seen = server.Requests;
        Assert.Equal(new[]
        {
            "GET /api/map/status", "POST /api/map", "POST /api/mission/check", "POST /api/mission/start",
            "POST /api/mission/stop", "GET /api/mission/status?since=7",
        }, seen.Select(r => r.Method + " " + r.Target).ToArray());
        Assert.StartsWith("application/json", seen[1].ContentType);
        using var put = JsonDocument.Parse(seen[1].Body);
        Assert.Equal(0, put.RootElement.GetProperty("map").GetProperty("markers")[0].GetProperty("id").GetInt32());
        Assert.Contains("привет", seen[2].Body);     // Cyrillic as it is: the drone limits the body in bytes
        using var start = JsonDocument.Parse(seen[3].Body);
        var confirm = start.RootElement.GetProperty("confirm");
        Assert.True(confirm.GetProperty("battery_multimeter").GetBoolean());
        Assert.True(confirm.GetProperty("rc_in_hand_ch8").GetBoolean());
        Assert.False(confirm.GetProperty("people_clear").GetBoolean());
        Assert.True(confirm.GetProperty("takeoff_clicked").GetBoolean());
        Assert.Equal("abcd", start.RootElement.GetProperty("token").GetString());
        Assert.Equal("8a8a", start.RootElement.GetProperty("map_sha").GetString());
        Assert.Equal("", seen[4].Body);            // Stop carries nothing
    }

    [Fact]
    public async Task ADronesRefusalIsPassedOnAsItCame()
    {
        using var server = new FakeMissionServer(_ => (409, """{"error":"дрон взведён","code":"armed"}"""));
        var reply = await new MissionApi(server.Port).CheckAsync(Local, "x");
        Assert.Equal(409, reply.Code);
        Assert.Contains("armed", reply.Json);
    }

    [Fact]
    public async Task StopIsTriedAgainWhenTheConnectionIsDropped()
    {
        var n = 0;
        using var server = new FakeMissionServer(_ => Interlocked.Increment(ref n) == 1 ? throw new IOException("dropped") : (200, """{"result":"ok"}"""));
        var reply = await new MissionApi(server.Port).StopAsync(Local);
        Assert.Equal(200, reply.Code);
        Assert.Equal(2, server.Requests.Count);
    }

    [Fact]
    public async Task NoServerOrNoDroneIsCodeZero()
    {
        int port;
        using (var server = new FakeMissionServer(_ => (200, "{}"))) port = server.Port;     // closed again
        var silent = await new MissionApi(port).MapStatusAsync(Local);
        Assert.Equal(0, silent.Code);
        Assert.Contains("no_answer", silent.Json);
        var none = await new MissionApi().StopAsync("");
        Assert.Equal(0, none.Code);
        Assert.Contains("no_drone", none.Json);
    }
}
