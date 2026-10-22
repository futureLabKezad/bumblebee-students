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

using System.Globalization;

namespace BumblebeeGcs.Logic;

/// <summary>Vertical scale of the small line charts.</summary>
public static class ChartScale
{
    /// <summary>The altitude chart never spans less than 1 m, so 1-2 cm of noise stays a flat line.</summary>
    public const double AltitudeMinSpan = 1.0;

    /// <summary>
    /// Scale (lo, hi). Fixed bounds win; otherwise the data range, widened to at least
    /// minSpan around the middle of the data (all points stay visible).
    /// </summary>
    public static (double Lo, double Hi) Range(IReadOnlyList<double> data, double? fixedMin, double? fixedMax, double minSpan)
    {
        var span = Math.Max(minSpan, 1e-6);
        if (fixedMin is double fmin && fixedMax is double fmax)
            return fmax - fmin > 1e-9 ? (fmin, fmax) : (fmin, fmin + span);
        double dmin = 0, dmax = 0;
        if (data.Count > 0)
        {
            dmin = double.MaxValue;
            dmax = double.MinValue;
            foreach (var v in data)
            {
                if (v < dmin) dmin = v;
                if (v > dmax) dmax = v;
            }
        }
        if (fixedMin is double lo0) return (lo0, Math.Max(dmax, lo0 + span));
        if (fixedMax is double hi0) return (Math.Min(dmin, hi0 - span), hi0);
        if (dmax - dmin >= span) return (dmin, dmax);
        var mid = (dmin + dmax) / 2;
        return (mid - span / 2, mid + span / 2);
    }

    /// <summary>A scale label with as many decimals as the span needs.</summary>
    public static string Label(double v, double span)
    {
        var decimals = span >= 10 ? 0 : span >= 1 ? 1 : 2;
        var r = Math.Round(v, decimals);
        if (r == 0) r = 0;   // no "-0.0"
        return r.ToString("F" + decimals, CultureInfo.InvariantCulture);
    }
}

/// <summary>Attitude indicator math.</summary>
public static class AttitudeMath
{
    /// <summary>
    /// Vertical shift of the horizon in screen pixels (Y grows down). ROS pitch (REP-103,
    /// FLU body): +pitch is nose DOWN, so the horizon must move UP and more ground shows.
    /// </summary>
    public static double HorizonShiftPx(double pitchDeg, double pxPerDeg) => -pitchDeg * pxPerDeg;

    /// <summary>
    /// sensor_msgs/Imu orientation is usable: orientation_covariance[0] != -1 ("no orientation")
    /// and the quaternion is close to unit length.
    /// </summary>
    public static bool IsValidImuOrientation(double? covariance0, double x, double y, double z, double w)
    {
        if (covariance0 is not double c || c == -1) return false;
        if (!double.IsFinite(x) || !double.IsFinite(y) || !double.IsFinite(z) || !double.IsFinite(w)) return false;
        var norm = Math.Sqrt(x * x + y * y + z * z + w * w);
        return Math.Abs(norm - 1) < 0.05;
    }
}

public enum VideoState
{
    /// <summary>No frame yet: spinner "waiting for video…".</summary>
    Waiting,
    Live,
    /// <summary>The last frame is older than 3 s: "Video lost" over the frozen frame.</summary>
    Lost,
    /// <summary>ArUco topic with no frame for 3 s: the hint instead of an endless spinner.</summary>
    NoArucoFrames,
}

/// <summary>Camera status from the time of the last frame.</summary>
public static class VideoLogic
{
    public const string ArucoHint = "ArUco image appears only when the drone is armed or in OFFBOARD";
    public const string ArucoHintShort = "ArUco: only when armed or in OFFBOARD";

    /// <param name="lastFrameAt">Arrival of the last frame of the current stream; null = none yet.</param>
    /// <param name="startedAt">When the current stream (URL) was started.</param>
    public static VideoState Compute(double? lastFrameAt, double startedAt, double now, bool isAruco)
    {
        if (lastFrameAt is double t) return now - t > Freshness.VideoLimit ? VideoState.Lost : VideoState.Live;
        return isAruco && now - startedAt > Freshness.VideoLimit ? VideoState.NoArucoFrames : VideoState.Waiting;
    }

    /// <summary>The drone publishes ArUco images only when armed or in OFFBOARD (aruco_detect gate_by_flight_state).</summary>
    public static bool IsArucoTopic(string topic) => topic.Contains("aruco", StringComparison.OrdinalIgnoreCase);

    public static string LostCaption(double ageSec) => $"no frame for {(int)Math.Floor(Math.Max(0, ageSec))} s";
}

/// <summary>
/// "Flight controller link lost" on the laptop: when the link goes from OK to
/// "FC not connected" or "Telemetry frozen" while the drone was last known armed,
/// the alert sound plays once and a red banner stays until the link is OK again.
/// </summary>
public sealed class FcLostAlarm
{
    private LinkState _prev = LinkState.NoDrone;

    public bool BannerVisible { get; private set; }

    /// <summary>Feed every link evaluation; true = play the alert sound now.</summary>
    public bool Update(LinkState link, bool? lastKnownArmed)
    {
        var fire = _prev == LinkState.Ok
                   && (link == LinkState.FcNotConnected || link == LinkState.TelemetryFrozen)
                   && lastKnownArmed == true;
        if (fire) BannerVisible = true;
        if (link == LinkState.Ok) BannerVisible = false;
        _prev = link;
        return fire;
    }

    public void Reset()
    {
        _prev = LinkState.NoDrone;
        BannerVisible = false;
    }
}
