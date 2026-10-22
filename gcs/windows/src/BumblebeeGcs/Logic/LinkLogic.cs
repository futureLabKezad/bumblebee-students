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

namespace BumblebeeGcs.Logic;

/// <summary>What the Link tile says. Only Ok means the screen shows live flight-controller data.</summary>
public enum LinkState
{
    /// <summary>No open rosbridge socket (or it has just opened and no state came yet).</summary>
    NoDrone,
    /// <summary>A fresh /mavros/state says connected == false: MAVROS runs, the FC does not answer.</summary>
    FcNotConnected,
    /// <summary>The socket is open but /mavros/state stopped (or never came) for more than 3 s.</summary>
    TelemetryFrozen,
    /// <summary>A fresh /mavros/state with connected == true.</summary>
    Ok,
}

/// <summary>Link state from the socket and /mavros/state arrival times, like drone.py get_fcu_status.</summary>
public static class LinkLogic
{
    /// <summary>A state older than this is not fresh (drone.py uses the same 3 s).</summary>
    public const double StateFreshSec = 3.0;

    /// <param name="socketOpenedAt">When the current rosbridge socket opened; null = no open socket.</param>
    /// <param name="stateAt">Arrival of the last /mavros/state (it may be from an earlier socket).</param>
    /// <param name="stateConnected">The connected field of that state.</param>
    public static LinkState Compute(double? socketOpenedAt, double? stateAt, bool? stateConnected, double now)
    {
        if (socketOpenedAt is not double opened) return LinkState.NoDrone;
        // A state that came over an earlier socket says nothing about this one.
        double? onSocket = stateAt is double at && at >= opened ? at : null;
        if (onSocket is double t && now - t <= StateFreshSec)
            return stateConnected == true ? LinkState.Ok : LinkState.FcNotConnected;
        // No fresh state on this socket: frozen once 3 s have passed since the last state
        // or, if none came yet, since the socket opened (the first state is on its way).
        var since = onSocket ?? opened;
        return now - since > StateFreshSec ? LinkState.TelemetryFrozen : LinkState.NoDrone;
    }

    public static string Text(LinkState s) => s switch
    {
        LinkState.FcNotConnected => "FC not connected",
        LinkState.TelemetryFrozen => "Telemetry frozen",
        LinkState.Ok => "OK",
        _ => "No drone",
    };

    /// <summary>Same colours as the Mac app: no socket is a warning, a socket without a live FC is danger.</summary>
    public static Tone ToneOf(LinkState s) => s switch
    {
        LinkState.Ok => Tone.Ok,
        LinkState.NoDrone => Tone.Warn,
        _ => Tone.Danger,
    };

    /// <summary>The small line under the Link tile ("" = none).</summary>
    /// <param name="socketOpen">The rosbridge socket is open (it may still wait for the first state).</param>
    /// <param name="state">Freshness of the last /mavros/state.</param>
    public static string Caption(LinkState s, bool socketOpen, FreshStatus state) => s switch
    {
        LinkState.NoDrone => socketOpen ? "waiting for FC data" : "",
        LinkState.TelemetryFrozen => state.Note ?? "",
        _ => "",
    };

    /// <summary>The line under the drone address in the sidebar.</summary>
    public static string SidebarText(LinkState s, bool socketOpen) => s switch
    {
        LinkState.Ok => "linked",
        LinkState.FcNotConnected => "FC not connected",
        LinkState.TelemetryFrozen => "telemetry frozen",
        _ => socketOpen ? "waiting for FC data" : "linking…",
    };
}

/// <summary>Sources whose age the dashboard tracks (video is tracked per camera).</summary>
public enum TelemetrySource { State, Pose, Velocity, Imu, Attitude, Battery, Metrics }

public enum FreshKind
{
    /// <summary>Nothing arrived yet: the value shows "—" (never 0) and the panel is grey.</summary>
    Never,
    Fresh,
    /// <summary>Older than the source's limit: grey with "no data N s".</summary>
    Stale,
}

/// <summary>Freshness of one source, as the Mac app's Freshness.Status.</summary>
public readonly record struct FreshStatus(FreshKind Kind, int Seconds)
{
    public bool IsFresh => Kind == FreshKind.Fresh;

    /// <summary>Caption for a greyed panel; null while the data is fresh.</summary>
    public string? Note => Kind switch
    {
        FreshKind.Fresh => null,
        FreshKind.Never => "no data yet",
        _ => Freshness.NoDataText(Seconds),
    };
}

/// <summary>Per-source freshness: a panel older than its limit is greyed with "no data N s".</summary>
public static class Freshness
{
    public const double VideoLimit = 3.0;

    public static double Limit(TelemetrySource s) => s switch
    {
        TelemetrySource.State => 3.0,
        TelemetrySource.Battery => 5.0,
        TelemetrySource.Metrics => 6.0,
        _ => 2.0,   // pose, velocity, imu, attitude
    };

    public static FreshStatus Status(double? arrivedAt, double now, double limit)
    {
        if (arrivedAt is not double t) return new FreshStatus(FreshKind.Never, 0);
        var age = Math.Max(0, now - t);
        return age <= limit ? new FreshStatus(FreshKind.Fresh, 0)
                            : new FreshStatus(FreshKind.Stale, (int)Math.Floor(age));
    }

    public static FreshStatus Status(double? arrivedAt, double now, TelemetrySource s) =>
        Status(arrivedAt, now, Limit(s));

    public static double? Age(double? arrivedAt, double now) =>
        arrivedAt is double t ? Math.Max(0, now - t) : null;

    /// <summary>True only when something arrived and is now older than the limit.</summary>
    public static bool IsStale(double? arrivedAt, double now, double limit) =>
        arrivedAt is double t && now - t > limit;

    public static string NoDataText(double ageSec) => $"no data {(int)Math.Floor(Math.Max(0, ageSec))} s";
}
