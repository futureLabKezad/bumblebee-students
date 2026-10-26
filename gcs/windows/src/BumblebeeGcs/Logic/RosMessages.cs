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

using System.Text;
using System.Text.Json;
using BumblebeeGcs.Models;

namespace BumblebeeGcs.Logic;

/// <summary>
/// Parses one rosbridge "publish" message of a subscribed topic into the store.
/// Runs on the UI thread (the client checks the connection generation first).
/// </summary>
public static class RosMessages
{
    /// <summary>
    /// One rosbridge frame: true for {"op":"publish","topic":...,"msg":{...}} (msg is a clone,
    /// safe to hand to the UI thread). rosbridge serialises with Python's json, which may write
    /// NaN, Infinity and -Infinity bare (not valid JSON); they become null here, as the Mac app's
    /// JSON5 parser reads them, so a BatteryState with NaN fields is not thrown away.
    /// </summary>
    public static bool TryParsePublish(string text, out string topic, out JsonElement msg)
    {
        topic = "";
        msg = default;
        JsonDocument doc;
        try
        {
            doc = JsonDocument.Parse(text);
        }
        catch (JsonException)
        {
            if (NonFiniteToNull(text) is not string fixedText) return false;
            try { doc = JsonDocument.Parse(fixedText); }
            catch (JsonException) { return false; }
        }
        using (doc)
        {
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object || Str(root, "op") != "publish" ||
                Str(root, "topic") is not string t || Obj(root, "msg") is not JsonElement m) return false;
            topic = t;
            msg = m.Clone();
            return true;
        }
    }

    /// <summary>Bare NaN / Infinity / -Infinity outside strings replaced by null; null if there were none.</summary>
    static string? NonFiniteToNull(string text)
    {
        StringBuilder? sb = null;
        bool inString = false, escaped = false;
        var copied = 0;
        for (var i = 0; i < text.Length; i++)
        {
            var c = text[i];
            if (inString)
            {
                if (escaped) escaped = false;
                else if (c == '\\') escaped = true;
                else if (c == '"') inString = false;
                continue;
            }
            if (c == '"') { inString = true; continue; }
            var len = At(text, i, "NaN") ? 3 : At(text, i, "Infinity") ? 8 : At(text, i, "-Infinity") ? 9 : 0;
            if (len == 0) continue;
            sb ??= new StringBuilder(text.Length);
            sb.Append(text, copied, i - copied).Append("null");
            i += len - 1;
            copied = i + 1;
        }
        if (sb is null) return null;
        sb.Append(text, copied, text.Length - copied);
        return sb.ToString();
    }

    static bool At(string text, int i, string word) => string.CompareOrdinal(text, i, word, 0, word.Length) == 0;

    /// <summary>Returns true when the store changed.</summary>
    public static bool Apply(TelemetryStore s, string topic, JsonElement msg, double now)
    {
        switch (topic)
        {
            case "/mavros/state":
                s.ApplyState(Bool(msg, "connected"), Bool(msg, "armed"), Str(msg, "mode"), now);
                return true;

            case "/mavros/statustext/recv":
            {
                var sev = (int)(Num(msg, "severity") ?? 99);
                if (sev > 4 || Str(msg, "text") is not string txt) return false;
                s.LogFcu(txt);
                return true;
            }

            case "/mavros/battery":
                s.ApplyBattery(BatteryReading.Classify(Num(msg, "voltage"), Num(msg, "percentage")), now);
                return true;

            case "/mavros/mavros/pose":
            {
                if (Obj(msg, "pose") is not JsonElement pose ||
                    Obj(pose, "position") is not JsonElement p) return false;
                Euler? att = null;
                if (Obj(pose, "orientation") is JsonElement o)
                    att = MathUtil.QuatToEuler(Num(o, "x") ?? 0, Num(o, "y") ?? 0, Num(o, "z") ?? 0, Num(o, "w") ?? 1);
                s.ApplyPose(Num(p, "x") ?? 0, Num(p, "y") ?? 0, Num(p, "z") ?? 0, att, now);
                return true;
            }

            case "/mavros/mavros/velocity_local":
            {
                if (Obj(msg, "twist") is not JsonElement twist ||
                    Obj(twist, "linear") is not JsonElement l) return false;
                s.ApplyVelocity(Num(l, "x") ?? 0, Num(l, "y") ?? 0, Num(l, "z") ?? 0, now);
                return true;
            }

            case "/mavros/mavros/data":
            {
                if (Obj(msg, "angular_velocity") is not JsonElement av ||
                    Obj(msg, "linear_acceleration") is not JsonElement la) return false;
                double gx = Num(av, "x") ?? 0, gy = Num(av, "y") ?? 0, gz = Num(av, "z") ?? 0;
                double ax = Num(la, "x") ?? 0, ay = Num(la, "y") ?? 0, az = Num(la, "z") ?? 0;
                s.ApplyImu(Math.Sqrt(gx * gx + gy * gy + gz * gz) * 180 / Math.PI,
                           Math.Sqrt(ax * ax + ay * ay + az * az),
                           ImuAttitude(msg), now);
                return true;
            }

            default:
                return false;
        }
    }

    /// <summary>Attitude from sensor_msgs/Imu orientation, or null when the IMU gives none.</summary>
    static Euler? ImuAttitude(JsonElement msg)
    {
        if (Obj(msg, "orientation") is not JsonElement o) return null;
        double? cov0 = msg.TryGetProperty("orientation_covariance", out var cov) &&
                       cov.ValueKind == JsonValueKind.Array && cov.GetArrayLength() > 0 &&
                       cov[0].ValueKind == JsonValueKind.Number
            ? cov[0].GetDouble() : null;
        double x = Num(o, "x") ?? double.NaN, y = Num(o, "y") ?? double.NaN,
               z = Num(o, "z") ?? double.NaN, w = Num(o, "w") ?? double.NaN;
        return AttitudeMath.IsValidImuOrientation(cov0, x, y, z, w) ? MathUtil.QuatToEuler(x, y, z, w) : null;
    }

    static double? Num(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;

    static bool? Bool(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False ? v.GetBoolean() : null;

    static string? Str(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    static JsonElement? Obj(JsonElement e, string prop) =>
        e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.Object ? v : null;
}
