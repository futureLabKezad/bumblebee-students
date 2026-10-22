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
        var since = onSocket ?? opened;
        return now - since > StateFreshSec ? LinkState.TelemetryFrozen : LinkState.NoDrone;
    }

    /// <summary>The socket is open but the first state has not come yet (shown as "No drone · connecting…").</summary>
    public static bool IsConnecting(double? socketOpenedAt, double? stateAt, double now) =>
        socketOpenedAt is double opened && !(stateAt is double at && at >= opened) && now - opened <= StateFreshSec;

    public static string Text(LinkState s) => s switch
    {
        LinkState.FcNotConnected => "FC not connected",
        LinkState.TelemetryFrozen => "Telemetry frozen",
        LinkState.Ok => "OK",
        _ => "No drone",
    };

    public static Tone ToneOf(LinkState s) => s switch
    {
        LinkState.Ok => Tone.Ok,
        LinkState.FcNotConnected => Tone.Danger,
        _ => Tone.Warn,
    };

    /// <summary>The small line under the Link tile.</summary>
    public static string Caption(LinkState s, bool connecting, double? stateAge) => s switch
    {
        LinkState.Ok => "FC connected",
        LinkState.FcNotConnected => "MAVROS sees no FC",
        LinkState.TelemetryFrozen => stateAge is double a ? $"no state for {(int)Math.Floor(a)} s" : "no state yet",
        _ => connecting ? "connecting…" : "reconnecting…",
    };
}

/// <summary>Sources whose age the dashboard tracks (video is tracked per camera).</summary>
public enum TelemetrySource { State, Pose, Velocity, Imu, Attitude, Battery, Metrics }

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

    public static double? Age(double? arrivedAt, double now) =>
        arrivedAt is double t ? Math.Max(0, now - t) : null;

    /// <summary>True only when something arrived and is now older than the limit.</summary>
    public static bool IsStale(double? arrivedAt, double now, double limit) =>
        arrivedAt is double t && now - t > limit;

    /// <summary>"no data N s" when stale, null when fresh or when nothing arrived yet (then the value shows "—").</summary>
    public static string? StaleNote(double? arrivedAt, double now, double limit) =>
        arrivedAt is double t && now - t > limit ? NoDataText(now - t) : null;

    public static string NoDataText(double ageSec) => $"no data {(int)Math.Floor(Math.Max(0, ageSec))} s";
}
